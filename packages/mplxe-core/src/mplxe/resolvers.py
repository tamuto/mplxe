"""Attribute conflict resolution.

After dictionary and rule matching, a single attribute (e.g. `skin`) may
have been claimed by multiple matches with different values. The resolver
picks one and reports which other claims were displaced.

The default policy is:

  1. Group all candidate (attr → value) claims by attribute.
  2. Drop fallback claims for any attribute that already has a non-fallback
     candidate. Fallbacks only fill holes.
  3. The highest priority wins. If only one candidate is at the top tier,
     it is selected silently.
  4. If multiple candidates tie at the top tier with different values:
       - if exactly one of them has `override=true`, that one wins
       - otherwise, the first declared candidate wins and an
         `AttributeConflict` is recorded
  5. If multiple candidates tie with the same value, no conflict is recorded.

Seed values (e.g. attributes carried in from a chosen dictionary entry, or
configured `defaults`) are modeled as candidates with their own priority,
so the same algorithm covers all sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol, runtime_checkable

from .models import (
    AttributeConflict,
    AttributeConflictCandidate,
    Match,
)


@dataclass
class AttrCandidate:
    """A single (attribute, value) claim from one source."""

    rule_id: str
    field: str
    value: Any
    priority: int
    override: bool = False
    fallback: bool = False
    namespace: str | None = None


@runtime_checkable
class ConflictResolver(Protocol):
    def resolve(
        self,
        candidates: list[AttrCandidate],
    ) -> tuple[dict[str, Any], list[AttributeConflict]]: ...


class DefaultConflictResolver:
    """Priority-and-override conflict resolver. See module docstring."""

    def resolve(
        self,
        candidates: list[AttrCandidate],
    ) -> tuple[dict[str, Any], list[AttributeConflict]]:
        by_field: dict[str, list[AttrCandidate]] = {}
        for c in candidates:
            by_field.setdefault(c.field, []).append(c)

        resolved: dict[str, Any] = {}
        conflicts: list[AttributeConflict] = []

        for field, cands in by_field.items():
            non_fb = [c for c in cands if not c.fallback]
            active = non_fb if non_fb else cands

            top_pri = max(c.priority for c in active)
            top_tier = [c for c in active if c.priority == top_pri]

            distinct = _distinct_values(top_tier)
            if len(distinct) <= 1:
                # unique value at the top, possibly with multiple agreeing rules
                winner = top_tier[0]
                resolved[field] = winner.value
                continue

            override_winners = [c for c in top_tier if c.override]
            if len(override_winners) == 1:
                winner = override_winners[0]
            else:
                winner = top_tier[0]  # stable: first declared wins

            resolved[field] = winner.value
            conflicts.append(
                AttributeConflict(
                    field=field,
                    candidates=[
                        AttributeConflictCandidate(
                            rule_id=c.rule_id,
                            value=c.value,
                            priority=c.priority,
                            override=c.override,
                            namespace=c.namespace,
                        )
                        for c in top_tier
                    ],
                    resolved_value=winner.value,
                    resolved_by=winner.rule_id,
                )
            )

        return resolved, conflicts


def candidates_from_matches(
    matches: Iterable[Match],
) -> list[AttrCandidate]:
    """Flatten Match.attributes into per-attribute candidates."""
    out: list[AttrCandidate] = []
    for m in matches:
        for k, v in m.attributes.items():
            out.append(
                AttrCandidate(
                    rule_id=m.rule_id,
                    field=k,
                    value=v,
                    priority=m.priority,
                    override=m.override,
                    fallback=m.fallback,
                    namespace=m.namespace,
                )
            )
    return out


def _distinct_values(cands: list[AttrCandidate]) -> list[Any]:
    """List-based dedup for possibly-unhashable attribute values."""
    seen: list[Any] = []
    for c in cands:
        if c.value not in seen:
            seen.append(c.value)
    return seen


__all__ = [
    "AttrCandidate",
    "ConflictResolver",
    "DefaultConflictResolver",
    "candidates_from_matches",
]
