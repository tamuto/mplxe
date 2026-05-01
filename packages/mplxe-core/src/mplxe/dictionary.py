"""Dictionary matcher interface and a longest-synonym default.

A dictionary is a collection of canonical entries, each with a list of
synonyms. The matcher's job is to find which canonical entries the input
text refers to. The default implementation does longest-substring matching
across all synonyms, sorted by length descending, with priority as a
tie-breaker. This is deterministic and good enough for v1.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Dictionary, DictionaryEntry, Match


@runtime_checkable
class DictionaryMatcher(Protocol):
    def match(self, text: str) -> list[Match]: ...


class LongestSynonymDictionaryMatcher:
    """Longest-first synonym matcher.

    For each (synonym, entry) pair, finds all occurrences in text. The
    returned matches carry the canonical_name and category of the matching
    entry so downstream code does not need to look the entry up again.
    """

    def __init__(self, dictionaries: dict[str, Dictionary]):
        self.dictionaries = dictionaries
        self._index = self._build_index(dictionaries)

    @staticmethod
    def _build_index(
        dicts: dict[str, Dictionary],
    ) -> list[tuple[str, str, DictionaryEntry]]:
        index: list[tuple[str, str, DictionaryEntry]] = []
        for dict_name, d in dicts.items():
            for entry in d.entries:
                seen: set[str] = set()
                # the canonical name is always treated as a synonym of itself
                for syn in [entry.canonical_name, *entry.synonyms]:
                    if syn and syn not in seen:
                        index.append((syn, dict_name, entry))
                        seen.add(syn)
        # longest synonym first; higher entry priority wins ties
        index.sort(key=lambda t: (-len(t[0]), -t[2].priority))
        return index

    def match(self, text: str) -> list[Match]:
        if not text:
            return []
        results: list[Match] = []
        for synonym, dict_name, entry in self._index:
            start = 0
            while True:
                pos = text.find(synonym, start)
                if pos == -1:
                    break
                end = pos + len(synonym)
                results.append(
                    Match(
                        rule_id=f"dict:{dict_name}:{entry.canonical_name}",
                        matched_text=synonym,
                        start=pos,
                        end=end,
                        attributes=dict(entry.attributes),
                        canonical_name=entry.canonical_name,
                        category=entry.category,
                        score=1.0,
                        kind="dictionary",
                        priority=entry.priority,
                        namespace=entry.namespace,
                    )
                )
                start = pos + 1
        results.sort(key=lambda m: (m.start, -len(m.matched_text)))
        _mark_suppressed_by_longer(results)
        return results


def _mark_suppressed_by_longer(matches: list[Match]) -> None:
    """Mark shorter dictionary matches whose span overlaps a longer one.

    A match M is suppressed by another match L when their spans overlap and
    L's matched_text is strictly longer. The longest non-overlapping cover
    wins; same-length overlapping matches are both kept for the caller to
    decide. Suppression is in-place — the input list is mutated.
    """
    for m in matches:
        if m.suppressed:
            continue
        m_len = m.end - m.start
        for other in matches:
            if other is m:
                continue
            other_len = other.end - other.start
            if other_len <= m_len:
                continue
            # spans overlap iff each starts before the other ends
            if other.start < m.end and m.start < other.end:
                m.suppressed = True
                m.suppressed_by = other.rule_id
                break
