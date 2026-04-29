"""Greedy clustering of similar strings for the suggest command.

The default implementation is intentionally simple: O(n^2 / 2) string
comparisons, which is fine for the tens-of-thousands range typical of
one normalization pass. Strings are processed in frequency-desc order
so the most common variant of a cluster becomes its representative.

Future extension points:
  * TF-IDF n-gram clustering for very large inputs
  * embedding-based clustering (sentence transformers)
  * union-find with a blocking key to scale past O(n^2)
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from .similarity import fuzzy_score


def greedy_cluster(
    texts: Iterable[str],
    *,
    min_score: float = 75.0,
) -> dict[str, int]:
    """Group texts into clusters by pairwise fuzzy similarity.

    Returns a mapping ``text -> cluster_id`` where cluster ids are 1-based
    and assigned in the order representatives are picked.

    Algorithm (per spec):
      1. order strings by frequency desc, then alphabetically for determinism
      2. take the first unassigned string and make it the representative
      3. attach every still-unassigned string with score >= min_score
      4. advance to the next unassigned string

    Empty strings are skipped — they cluster to nothing useful.
    """
    counts = Counter(t for t in texts if t)
    ordered = sorted(counts.keys(), key=lambda t: (-counts[t], t))

    cluster_of: dict[str, int] = {}
    next_cluster_id = 0

    for rep in ordered:
        if rep in cluster_of:
            continue
        next_cluster_id += 1
        cluster_of[rep] = next_cluster_id
        for other in ordered:
            if other in cluster_of:
                continue
            if fuzzy_score(rep, other) >= min_score:
                cluster_of[other] = next_cluster_id

    return cluster_of
