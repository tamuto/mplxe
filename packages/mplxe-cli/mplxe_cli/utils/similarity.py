"""Fuzzy similarity helpers for the suggest command.

Wraps rapidfuzz with a small façade so the suggest pipeline can stay
agnostic of the underlying scorer. The interface is intentionally narrow
(`Candidate`, `ScoredCandidate`, `find_nearest`) so a future embedding-
or TF-IDF-based provider can replace the rapidfuzz backend without
touching `suggest.py`.

Future extension points:
  * embedding-based similarity provider
  * TF-IDF n-gram similarity provider
  * domain-aware scoring (per-dictionary weights)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

try:
    from rapidfuzz import fuzz as _fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _fuzz = None
    _HAS_RAPIDFUZZ = False


@dataclass(frozen=True)
class Candidate:
    """A potential match drawn from rules.yaml — canonical, synonym, or rule keyword."""

    canonical_name: str
    matched_term: str
    source: str  # "dictionary.canonical" | "dictionary.synonym" | "rule.keyword"
    category: str | None = None


@dataclass(frozen=True)
class ScoredCandidate:
    canonical_name: str
    matched_term: str
    source: str
    score: float
    category: str | None = None


def require_rapidfuzz() -> None:
    """Raise RuntimeError with install guidance if rapidfuzz is missing."""
    if not _HAS_RAPIDFUZZ:
        raise RuntimeError(
            "rapidfuzz is required for `mplxe suggest`. "
            "Install it with: pip install rapidfuzz"
        )


def fuzzy_score(a: str, b: str) -> float:
    """Combined fuzzy score in [0, 100].

    Returns the max of ratio / partial_ratio / token_sort_ratio. partial_ratio
    helps short Japanese strings where one is a substring of the other;
    token_sort_ratio handles word-order variation.
    """
    if not a or not b:
        return 0.0
    if not _HAS_RAPIDFUZZ:
        return 0.0
    return max(
        _fuzz.ratio(a, b),
        _fuzz.partial_ratio(a, b),
        _fuzz.token_sort_ratio(a, b),
    )


def find_nearest(
    text: str,
    candidates: Iterable[Candidate],
    *,
    top_k: int = 3,
    min_score: float = 0.0,
    exclude_canonicals: Iterable[str] | None = None,
) -> list[ScoredCandidate]:
    """Return the top_k most similar candidates above min_score.

    Ties are broken by the order candidates appear in the input iterable,
    so callers should pass them in priority order if they care.

    `exclude_canonicals` drops any candidate whose canonical_name is in the
    set — used by suggest to hide canonicals that the pipeline already
    chose or explicitly suppressed (covered by a longer dictionary term).
    """
    if not text:
        return []
    excluded = set(exclude_canonicals or ())
    scored: list[ScoredCandidate] = []
    for c in candidates:
        if c.canonical_name in excluded:
            continue
        s = fuzzy_score(text, c.matched_term)
        if s >= min_score:
            scored.append(
                ScoredCandidate(
                    canonical_name=c.canonical_name,
                    matched_term=c.matched_term,
                    source=c.source,
                    score=s,
                    category=c.category,
                )
            )
    # Within a (canonical, score) group keep the highest-scoring entry only,
    # so the top-k isn't dominated by near-duplicate synonyms of the same canonical.
    by_canonical: dict[str, ScoredCandidate] = {}
    for sc in scored:
        prev = by_canonical.get(sc.canonical_name)
        if prev is None or sc.score > prev.score:
            by_canonical[sc.canonical_name] = sc
    deduped = sorted(by_canonical.values(), key=lambda x: x.score, reverse=True)
    return deduped[:top_k]


def build_candidates_from_config(config) -> list[Candidate]:
    """Flatten a PipelineConfig's dictionaries into a Candidate list."""
    out: list[Candidate] = []
    for _name, dictionary in config.dictionaries.items():
        for entry in dictionary.entries:
            out.append(
                Candidate(
                    canonical_name=entry.canonical_name,
                    matched_term=entry.canonical_name,
                    source="dictionary.canonical",
                    category=entry.category,
                )
            )
            for syn in entry.synonyms:
                if syn == entry.canonical_name:
                    continue
                out.append(
                    Candidate(
                        canonical_name=entry.canonical_name,
                        matched_term=syn,
                        source="dictionary.synonym",
                        category=entry.category,
                    )
                )
    return out
