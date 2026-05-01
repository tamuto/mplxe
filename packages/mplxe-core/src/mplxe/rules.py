"""Rule matcher interface and default implementation.

Two rule kinds are supported in v1:

- `regex`  — a single named pattern. Named groups are promoted to
             attributes (numeric coercion is applied where possible).
- `keyword` — a list of literal strings; any substring hit fires the rule.

Each rule may also declare a static `attributes` dict that is merged into
every match. The rule's `priority`, `override`, `fallback`, and `namespace`
flow through onto each emitted Match so the conflict resolver in the
pipeline can decide who wins without re-reading the rule list.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from .errors import RuleError
from .models import Match, Rule


@runtime_checkable
class RuleMatcher(Protocol):
    def match(self, text: str, rules: list[Rule]) -> list[Match]: ...


class DefaultRuleMatcher:
    """Stateless regex/keyword rule matcher with a small compile cache."""

    def __init__(self) -> None:
        self._regex_cache: dict[str, re.Pattern[str]] = {}

    def _compiled(self, rule: Rule) -> re.Pattern[str]:
        if rule.pattern is None:
            raise RuleError(f"rule {rule.id!r}: type 'regex' but no pattern")
        cached = self._regex_cache.get(rule.id)
        if cached is None:
            try:
                cached = re.compile(rule.pattern)
            except re.error as e:
                raise RuleError(
                    f"rule {rule.id!r}: invalid regex {rule.pattern!r}: {e}"
                ) from e
            self._regex_cache[rule.id] = cached
        return cached

    def match(self, text: str, rules: list[Rule]) -> list[Match]:
        if not text or not rules:
            return []
        out: list[Match] = []
        for rule in rules:
            if rule.type == "regex":
                out.extend(self._match_regex(text, rule))
            elif rule.type == "keyword":
                out.extend(self._match_keyword(text, rule))
            else:
                raise RuleError(f"rule {rule.id!r}: unsupported type {rule.type!r}")
        out.sort(key=lambda m: (m.start, m.rule_id))
        return out

    def _match_regex(self, text: str, rule: Rule) -> list[Match]:
        pattern = self._compiled(rule)
        matches: list[Match] = []
        for m in pattern.finditer(text):
            attrs = dict(rule.attributes)
            for name, value in m.groupdict().items():
                if value is None:
                    continue
                attrs[name] = _coerce(value)
            matches.append(self._build_match(rule, m.group(0), m.start(), m.end(), attrs, "regex"))
        return matches

    def _match_keyword(self, text: str, rule: Rule) -> list[Match]:
        matches: list[Match] = []
        for kw in rule.keywords:
            if not kw:
                continue
            start = 0
            while True:
                pos = text.find(kw, start)
                if pos == -1:
                    break
                matches.append(
                    self._build_match(
                        rule, kw, pos, pos + len(kw), dict(rule.attributes), "keyword"
                    )
                )
                start = pos + 1
        return matches

    @staticmethod
    def _build_match(
        rule: Rule,
        matched_text: str,
        start: int,
        end: int,
        attributes: dict[str, object],
        kind: str,
    ) -> Match:
        return Match(
            rule_id=rule.id,
            matched_text=matched_text,
            start=start,
            end=end,
            attributes=attributes,
            score=1.0,
            kind=kind,  # type: ignore[arg-type]
            priority=rule.priority,
            override=rule.override,
            fallback=rule.fallback,
            namespace=rule.namespace,
        )


def _coerce(value: str) -> int | float | str:
    """Best-effort numeric coercion for regex named-group values."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
