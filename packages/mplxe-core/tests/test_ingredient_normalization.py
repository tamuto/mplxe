"""Tests for the ingredient normalization spec.

Covers the reference example "鶏もも肉 皮つき 30g" plus a handful of
deterministic / edge-case checks.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mplxe import (
    Dictionary,
    DictionaryEntry,
    NormalizePipeline,
    PipelineConfig,
    Rule,
    RuleSet,
    load_pipeline_config,
)


# examples/ lives at the repo root, outside the core package.
YAML_PATH = (
    Path(__file__).resolve().parents[3] / "examples" / "ingredients.yaml"
)


@pytest.fixture(scope="module")
def pipeline() -> NormalizePipeline:
    config = load_pipeline_config(YAML_PATH)
    return NormalizePipeline(config)


# --------------------------------------------------------------------- spec


def test_reference_case(pipeline: NormalizePipeline) -> None:
    """The headline example from the spec."""
    result = pipeline.normalize("鶏もも肉 皮つき 30g")

    assert result.canonical_name == "鶏肉"
    assert result.category == "肉類"
    assert result.attributes["part"] == "もも"
    assert result.attributes["skin"] == "あり"
    assert result.attributes["amount"] == 30
    assert result.attributes["unit"] == "g"

    # all expected rules fired
    assert "amount_g" in result.matched_rules
    assert "skin_on" in result.matched_rules
    assert "part_momo" in result.matched_rules
    # dictionary hit also recorded
    assert any(
        r.startswith("dict:ingredients:鶏肉") for r in result.matched_rules
    )

    # human-readable explanations were produced
    assert result.explanations
    assert any("確定" in e for e in result.explanations)

    # high but not perfect confidence
    assert 0.5 < result.confidence <= 1.0


# --------------------------------------------------------------------- variants


def test_bare_canonical(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("鶏肉")
    assert result.canonical_name == "鶏肉"
    assert result.category == "肉類"
    # no rule attributes — just dictionary
    assert result.attributes == {}


def test_chicken_with_skin_compact(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("鶏肉皮付き")
    assert result.canonical_name == "鶏肉"
    assert result.attributes["skin"] == "あり"


def test_full_japanese_separators(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("国産鶏肉・皮なし・ゆで")
    assert result.canonical_name == "鶏肉"
    assert result.attributes["origin"] == "国産"
    assert result.attributes["skin"] == "なし"
    assert result.attributes["cooking_method"] == "ゆで"


def test_unicode_normalization_full_width(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("鶏肉 ３０ｇ")  # full-width digits + g
    assert result.attributes["amount"] == 30
    assert result.attributes["unit"] == "g"


# --------------------------------------------------------------------- robustness


def test_unknown_text_does_not_raise(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("totally unknown product name")
    assert result.canonical_name is None
    assert result.category is None
    assert any("no dictionary match" in w for w in result.warnings)
    assert result.confidence == 0.0


def test_empty_input(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("")
    assert result.canonical_name is None
    assert result.confidence == 0.0
    assert any("empty" in w for w in result.warnings)


def test_deterministic(pipeline: NormalizePipeline) -> None:
    a = pipeline.normalize("鶏もも肉 皮つき 30g")
    b = pipeline.normalize("鶏もも肉 皮つき 30g")
    assert a.model_dump() == b.model_dump()


# --------------------------------------------------------------------- priority


def test_priority_resolution() -> None:
    """Higher-priority rule overrides lower for the same attribute."""
    config = PipelineConfig(
        dictionaries={
            "items": Dictionary(
                name="items",
                entries=[
                    DictionaryEntry(
                        canonical_name="item",
                        category="x",
                        synonyms=["item"],
                    )
                ],
            )
        },
        rules=RuleSet(
            rules=[
                Rule(
                    id="low",
                    type="keyword",
                    keywords=["foo"],
                    attributes={"label": "low"},
                    priority=1,
                ),
                Rule(
                    id="high",
                    type="keyword",
                    keywords=["foo"],
                    attributes={"label": "high"},
                    priority=10,
                ),
            ]
        ),
    )
    pipeline = NormalizePipeline(config)
    result = pipeline.normalize("item foo")
    assert result.attributes["label"] == "high"


# --------------------------------------------------------------------- explain


def test_explanations_include_rule_ids(pipeline: NormalizePipeline) -> None:
    result = pipeline.normalize("鶏もも肉 皮つき 30g")
    explain_text = "\n".join(result.explanations)
    assert "amount_g" in explain_text
    assert "skin_on" in explain_text
    assert "part_momo" in explain_text
