"""End-to-end attribute conflict scenarios.

Anchors the spec's reference case "鶏もも肉 皮なし 皮付き 30g": skin is
claimed by two rules of equal priority with different values, so the
result must record an `attribute_conflict` for `skin`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mplxe import NormalizePipeline, load_rules


RULES_DIR = Path(__file__).resolve().parents[3] / "examples" / "rules"


@pytest.fixture(scope="module")
def pipeline() -> NormalizePipeline:
    return NormalizePipeline(load_rules(RULES_DIR))


def test_skin_conflict_is_recorded(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("鶏もも肉 皮なし 皮付き 30g")

    assert result.canonical_name == "鶏肉"
    assert result.attributes["amount"] == 30
    assert result.attributes["unit"] == "g"
    assert result.attributes["part"] == "もも"
    # skin attribute resolved (some value), and conflict recorded
    assert "skin" in result.attributes
    assert result.attributes["skin"] in {"あり", "なし"}

    skin_conflicts = [
        c for c in result.attribute_conflicts if c.field == "skin"
    ]
    assert len(skin_conflicts) == 1
    conflict = skin_conflicts[0]
    rule_ids = {c.rule_id for c in conflict.candidates}
    assert {"skin_on", "skin_off"} <= rule_ids

    # warning surfaced too
    assert any("attribute conflict" in w for w in result.warnings)
    # explanation rendered
    assert any("属性衝突" in e for e in result.explanations)


def test_no_conflict_for_non_overlapping_attrs(
    pipeline: NormalizePipeline,
) -> None:
    result = pipeline.normalize("鶏もも肉 皮付き 30g")
    assert result.attribute_conflicts == []
