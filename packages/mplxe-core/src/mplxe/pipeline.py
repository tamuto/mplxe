"""The orchestrating NormalizePipeline.

Pipeline stages:

  1. preprocess        — Unicode (NFKC) + whitespace normalization
  2. tokenize          — segment to Tokens (default: whitespace + punctuation)
  3. dictionary match  — find canonical_name candidates by synonym lookup
  4. rule match        — extract attributes via regex/keyword rules
  5. resolve           — pick the best canonical and merge attributes by priority
  6. explain           — render human-readable explanations

The pipeline never raises during normalization — anything unexpected becomes
a warning on the returned NormalizeResult.
"""
from __future__ import annotations

from typing import Iterable

from .dictionary import DictionaryMatcher, LongestSynonymDictionaryMatcher
from .explain import build_explanations
from .models import (
    Match,
    NormalizeInput,
    NormalizeResult,
    PipelineConfig,
    Rule,
)
from .normalizer import preprocess
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
    ) -> None:
        self.config = config
        self.tokenizer: Tokenizer = tokenizer or SimpleTokenizer()
        self.dictionary_matcher: DictionaryMatcher = (
            dictionary_matcher or LongestSynonymDictionaryMatcher(config.dictionaries)
        )
        self.rule_matcher: RuleMatcher = rule_matcher or DefaultRuleMatcher()
        self._rules_by_id: dict[str, Rule] = {r.id: r for r in config.rules.rules}

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

            result.attributes = self._merge_attributes(best_dict, rule_matches)
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
        # longest matched text wins; ties broken by earlier start position
        return max(ms, key=lambda m: (len(m.matched_text), -m.start))

    def _merge_attributes(
        self, best_dict: Match | None, rule_matches: Iterable[Match]
    ) -> dict[str, object]:
        attrs: dict[str, object] = {}
        if best_dict is not None:
            attrs.update(best_dict.attributes)

        # Apply rule attributes ordered by priority ascending so higher
        # priority overrides lower on conflict. Stable ordering is preserved
        # within the same priority by the original match order.
        sorted_rule_matches = sorted(
            rule_matches,
            key=lambda m: self._priority_for(m.rule_id),
        )
        for m in sorted_rule_matches:
            attrs.update(m.attributes)
        return attrs

    def _priority_for(self, rule_id: str) -> int:
        rule = self._rules_by_id.get(rule_id)
        return rule.priority if rule is not None else 0

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
