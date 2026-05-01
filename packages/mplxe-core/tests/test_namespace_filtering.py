"""Namespace filtering on the pipeline.

Verifies that enabled_namespaces / disabled_namespaces / rule_filter
correctly mask rules and dictionary entries before matching runs.
"""
from __future__ import annotations

from mplxe import (
    Dictionary,
    DictionaryEntry,
    NormalizePipeline,
    PipelineConfig,
    Rule,
    RuleSet,
)


def _make_config() -> PipelineConfig:
    return PipelineConfig(
        dictionaries={
            "items": Dictionary(
                name="items",
                entries=[
                    DictionaryEntry(
                        canonical_name="鶏肉",
                        category="肉類",
                        synonyms=["鶏肉"],
                        namespace="ingredients.meat",
                    ),
                    DictionaryEntry(
                        canonical_name="人参",
                        category="野菜",
                        synonyms=["人参"],
                        namespace="ingredients.vegetable",
                    ),
                ],
            )
        },
        rules=RuleSet(
            rules=[
                Rule(
                    id="amount_g",
                    type="regex",
                    pattern=r"(?P<amount>[0-9]+)\s*g",
                    attributes={"unit": "g"},
                    priority=10,
                    namespace="common.amount",
                ),
                Rule(
                    id="skin_on",
                    type="keyword",
                    keywords=["皮付き"],
                    attributes={"skin": "あり"},
                    priority=10,
                    namespace="ingredients.meat",
                ),
                Rule(
                    id="cut_sliced",
                    type="keyword",
                    keywords=["スライス"],
                    attributes={"cut": "スライス"},
                    priority=5,
                    namespace="ingredients.vegetable",
                ),
            ]
        ),
    )


def test_enabled_namespaces_glob() -> None:
    pipeline = NormalizePipeline(
        _make_config(),
        enabled_namespaces=["ingredients.meat", "common.*"],
    )
    result = pipeline.normalize("鶏肉 皮付き 30g スライス")

    assert result.canonical_name == "鶏肉"
    assert result.attributes["skin"] == "あり"
    assert result.attributes["amount"] == 30
    assert result.attributes["unit"] == "g"
    # vegetable rule must have been masked out
    assert "cut" not in result.attributes
    assert "cut_sliced" not in result.matched_rules


def test_disabled_namespaces() -> None:
    pipeline = NormalizePipeline(
        _make_config(),
        disabled_namespaces=["ingredients.vegetable"],
    )
    result = pipeline.normalize("鶏肉 人参 30g")
    # 人参 entry was filtered out so it cannot become canonical
    assert result.canonical_name == "鶏肉"
    assert result.attributes["unit"] == "g"


def test_rule_filter_callable() -> None:
    pipeline = NormalizePipeline(
        _make_config(),
        rule_filter=lambda r: r.priority >= 10,
    )
    result = pipeline.normalize("鶏肉 皮付き スライス")
    assert "skin" in result.attributes  # priority 10 kept
    assert "cut" not in result.attributes  # priority 5 dropped


def test_no_filters_keeps_everything() -> None:
    pipeline = NormalizePipeline(_make_config())
    result = pipeline.normalize("鶏肉 皮付き 30g")
    assert result.canonical_name == "鶏肉"
    assert result.attributes["skin"] == "あり"
    assert result.attributes["unit"] == "g"


def test_empty_enabled_filters_everything() -> None:
    """Defensive: enabled_namespaces=[] means 'match nothing'."""
    pipeline = NormalizePipeline(
        _make_config(), enabled_namespaces=[]
    )
    result = pipeline.normalize("鶏肉 皮付き 30g")
    assert result.canonical_name is None
    assert result.attributes == {}
