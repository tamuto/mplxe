"""The orchestrating NormalizePipeline.

Pipeline stages:

  1. preprocess        — Unicode (NFKC) + whitespace normalization
  2. tokenize          — segment to Tokens (default: whitespace + punctuation)
  3. dictionary match  — find canonical_name candidates by synonym lookup
  4. rule match        — extract attributes via regex/keyword rules
  5. resolve           — pick the best canonical, then run the conflict
                         resolver across all candidate attributes
  6. explain           — render human-readable explanations

Namespaces let a single pipeline target a subset of the loaded rules:

    NormalizePipeline(
        config,
        enabled_namespaces=["ingredients.*", "common.*"],
        disabled_namespaces=["ingredients.experimental.*"],
    )

Filtering happens once at construction; matching never sees the masked-out
rules. The pipeline never raises during normalization — anything unexpected
becomes a warning on the returned NormalizeResult.
"""
from __future__ import annotations

import fnmatch
from typing import Callable, Iterable

from .dictionary import DictionaryMatcher, LongestSynonymDictionaryMatcher
from .explain import build_explanations
from .models import (
    Dictionary,
    DictionaryEntry,
    Match,
    NormalizeInput,
    NormalizeResult,
    PipelineConfig,
    Rule,
    RuleSet,
)
from .normalizer import preprocess
from .resolvers import (
    AttrCandidate,
    ConflictResolver,
    DefaultConflictResolver,
    candidates_from_matches,
)
from .rules import DefaultRuleMatcher, RuleMatcher
from .tokenizer import SimpleTokenizer, Tokenizer


class NormalizePipeline:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        tokenizer: Tokenizer | None = None,
        dictionary_matcher: DictionaryMatcher | None = None,
        rule_matcher: RuleMatcher | None = None,
        conflict_resolver: ConflictResolver | None = None,
        enabled_namespaces: list[str] | None = None,
        disabled_namespaces: list[str] | None = None,
        rule_filter: Callable[[Rule], bool] | None = None,
    ) -> None:
        self.config = _filter_config(
            config,
            enabled=enabled_namespaces,
            disabled=disabled_namespaces,
            rule_filter=rule_filter,
        )
        self.enabled_namespaces = enabled_namespaces
        self.disabled_namespaces = disabled_namespaces
        self.tokenizer: Tokenizer = tokenizer or SimpleTokenizer()
        self.dictionary_matcher: DictionaryMatcher = (
            dictionary_matcher
            or LongestSynonymDictionaryMatcher(self.config.dictionaries)
        )
        self.rule_matcher: RuleMatcher = rule_matcher or DefaultRuleMatcher()
        self.conflict_resolver: ConflictResolver = (
            conflict_resolver or DefaultConflictResolver()
        )

    def normalize(self, text: str | NormalizeInput) -> NormalizeResult:
        input_obj = (
            text if isinstance(text, NormalizeInput) else NormalizeInput(text=text)
        )
        original = input_obj.text or ""
        result = NormalizeResult(original_text=original, normalized_text=original)

        try:
            normalized = preprocess(original)
            result.normalized_text = normalized

            if not normalized:
                result.warnings.append("input text was empty after preprocessing")
                result.explanations = build_explanations(result)
                return result

            result.tokens = self.tokenizer.tokenize(normalized)

            dict_matches = self.dictionary_matcher.match(normalized)
            rule_matches = self.rule_matcher.match(
                normalized, self.config.rules.rules
            )

            result.matches = [*dict_matches, *rule_matches]
            result.matched_rules = sorted({m.rule_id for m in result.matches})

            best_dict = self._select_canonical(dict_matches)
            if best_dict is not None:
                result.canonical_name = best_dict.canonical_name
                result.category = best_dict.category

            attrs, conflicts = self._resolve_attributes(best_dict, rule_matches)
            result.attributes = attrs
            result.attribute_conflicts = conflicts
            for c in conflicts:
                result.warnings.append(
                    f"attribute conflict: {c.field} resolved to {c.resolved_value!r} "
                    f"by {c.resolved_by} ({len(c.candidates)} candidates tied)"
                )

            if result.canonical_name is None and self.config.defaults.get(
                "canonical_name"
            ):
                result.canonical_name = self.config.defaults["canonical_name"]
            if result.category is None and self.config.defaults.get("category"):
                result.category = self.config.defaults["category"]

            result.confidence = self._confidence(
                normalized, dict_matches, rule_matches
            )

            if result.canonical_name is None:
                result.warnings.append(
                    "no dictionary match — canonical_name unresolved"
                )

        except Exception as e:  # pragma: no cover — defensive: never raise
            result.warnings.append(f"unexpected error during normalization: {e}")

        result.explanations = build_explanations(result)
        return result

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _select_canonical(dict_matches: Iterable[Match]) -> Match | None:
        ms = list(dict_matches)
        if not ms:
            return None
        # longest matched text wins; ties broken by earlier start position,
        # then higher priority
        return max(ms, key=lambda m: (len(m.matched_text), -m.start, m.priority))

    def _resolve_attributes(
        self,
        best_dict: Match | None,
        rule_matches: list[Match],
    ) -> tuple[dict[str, object], list]:
        candidates: list[AttrCandidate] = []
        if best_dict is not None:
            candidates.extend(candidates_from_matches([best_dict]))
        candidates.extend(candidates_from_matches(rule_matches))
        return self.conflict_resolver.resolve(candidates)

    @staticmethod
    def _confidence(
        normalized: str,
        dict_matches: list[Match],
        rule_matches: list[Match],
    ) -> float:
        if not dict_matches and not rule_matches:
            return 0.0
        score = 0.0
        if dict_matches:
            score += 0.5
        if rule_matches:
            score += 0.1
        if normalized:
            covered = bytearray(len(normalized))
            for m in (*dict_matches, *rule_matches):
                for i in range(m.start, min(m.end, len(normalized))):
                    covered[i] = 1
            coverage = sum(covered) / len(normalized)
            score += 0.4 * coverage
        return round(min(score, 1.0), 3)


# ---------------------------------------------------------------- filtering


def _matches_any(ns: str | None, patterns: list[str]) -> bool:
    target = ns or ""
    return any(fnmatch.fnmatchcase(target, p) for p in patterns)


def _filter_config(
    config: PipelineConfig,
    *,
    enabled: list[str] | None,
    disabled: list[str] | None,
    rule_filter: Callable[[Rule], bool] | None,
) -> PipelineConfig:
    """Return a new PipelineConfig with rules and dict entries filtered.

    If `enabled` is None, all namespaces are kept. `disabled` always
    subtracts. `rule_filter` further trims rules; it does not affect
    dictionary entries.
    """
    if enabled is None and disabled is None and rule_filter is None:
        return config

    def keep_ns(ns: str | None) -> bool:
        if enabled is not None and not _matches_any(ns, enabled):
            return False
        if disabled is not None and _matches_any(ns, disabled):
            return False
        return True

    kept_rules: list[Rule] = []
    for r in config.rules.rules:
        if not keep_ns(r.namespace):
            continue
        if rule_filter is not None and not rule_filter(r):
            continue
        kept_rules.append(r)

    kept_dicts: dict[str, Dictionary] = {}
    for name, d in config.dictionaries.items():
        kept_entries: list[DictionaryEntry] = [e for e in d.entries if keep_ns(e.namespace)]
        if kept_entries:
            kept_dicts[name] = Dictionary(name=name, entries=kept_entries)

    return PipelineConfig(
        dictionaries=kept_dicts,
        rules=RuleSet(rules=kept_rules),
        options=dict(config.options),
        defaults=dict(config.defaults),
    )
