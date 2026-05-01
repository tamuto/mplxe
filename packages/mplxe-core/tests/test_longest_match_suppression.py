"""Longest dictionary match suppresses overlapping shorter matches.

When two synonyms from different entries overlap on the same span, the
longer one is preferred and the shorter is marked as suppressed. The
suppressed match must not contribute to canonical selection, attribute
resolution, or confidence — it only stays in the result for transparency.
"""
from __future__ import annotations

import pytest

from mplxe import (
    Dictionary,
    DictionaryEntry,
    NormalizePipeline,
    PipelineConfig,
    RuleSet,
)


def _ahiru_dict() -> Dictionary:
    return Dictionary(
        name="ingredients",
        entries=[
            DictionaryEntry(
                canonical_name="あひる卵",
                category="卵類",
                synonyms=["あひる卵"],
            ),
            DictionaryEntry(
                canonical_name="あひる",
                category="その他肉類",
                synonyms=["あひる", "かも"],
            ),
        ],
    )


@pytest.fixture
def pipeline() -> NormalizePipeline:
    config = PipelineConfig(
        dictionaries={"ingredients": _ahiru_dict()},
        rules=RuleSet(rules=[]),
    )
    return NormalizePipeline(config)


def test_longest_dictionary_match_suppresses_shorter_match(
    pipeline: NormalizePipeline,
) -> None:
    result = pipeline.normalize("あひる卵 ピータン")

    # the longer dictionary term wins
    assert result.canonical_name == "あひる卵"
    assert result.category == "卵類"

    dict_matches = [m for m in result.matches if m.kind == "dictionary"]
    by_text = {m.matched_text: m for m in dict_matches}

    # both entries hit, but only the longer one is active
    assert "あひる卵" in by_text
    assert "あひる" in by_text
    assert by_text["あひる卵"].suppressed is False
    assert by_text["あひる"].suppressed is True
    assert by_text["あひる"].suppressed_by == by_text["あひる卵"].rule_id

    # suppressed candidate must not appear as an attribute conflict source
    assert all(
        c.field != "category" for c in result.attribute_conflicts
    ), "suppressed match leaked into attribute conflicts"
    assert not any(
        "category" in w.lower() and "conflict" in w.lower()
        for w in result.warnings
    )

    # confidence stays high — the suppressed shorter match must not deduct
    # from the score. Lower bound is generous so the assertion stays robust
    # to small tweaks in the coverage formula.
    assert result.confidence >= 0.6

    # explanation surfaces the suppression for transparency
    explain_text = "\n".join(result.explanations)
    assert "あひる卵" in explain_text
    assert "辞書候補抑制" in explain_text
    assert "あひる" in explain_text


def test_non_overlapping_matches_are_not_suppressed() -> None:
    config = PipelineConfig(
        dictionaries={
            "ingredients": Dictionary(
                name="ingredients",
                entries=[
                    DictionaryEntry(
                        canonical_name="あひる卵",
                        category="卵類",
                        synonyms=["あひる卵"],
                    ),
                    DictionaryEntry(
                        canonical_name="鶏肉",
                        category="肉類",
                        synonyms=["鶏肉"],
                    ),
                ],
            )
        },
        rules=RuleSet(rules=[]),
    )
    pipeline = NormalizePipeline(config)
    result = pipeline.normalize("あひる卵 鶏肉")

    dict_matches = [m for m in result.matches if m.kind == "dictionary"]
    assert {m.matched_text for m in dict_matches} == {"あひる卵", "鶏肉"}
    # disjoint spans → neither is suppressed
    assert all(not m.suppressed for m in dict_matches)
    assert all(m.suppressed_by is None for m in dict_matches)

    # canonical falls back to the longest among the active matches
    assert result.canonical_name == "あひる卵"
    assert result.category == "卵類"
