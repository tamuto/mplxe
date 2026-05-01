"""Priority + override behavior in the conflict resolver."""
from __future__ import annotations

from mplxe import (
    Dictionary,
    DictionaryEntry,
    NormalizePipeline,
    PipelineConfig,
    Rule,
    RuleSet,
)


def _config(rules: list[Rule]) -> PipelineConfig:
    return PipelineConfig(
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
        rules=RuleSet(rules=rules),
    )


def test_higher_priority_wins_silently() -> None:
    pipeline = NormalizePipeline(
        _config(
            [
                Rule(id="low", type="keyword", keywords=["foo"],
                     attributes={"label": "low"}, priority=1),
                Rule(id="high", type="keyword", keywords=["foo"],
                     attributes={"label": "high"}, priority=10),
            ]
        )
    )
    result = pipeline.normalize("item foo")
    assert result.attributes["label"] == "high"
    assert result.attribute_conflicts == []


def test_tied_priority_with_override_picks_override() -> None:
    pipeline = NormalizePipeline(
        _config(
            [
                Rule(id="a", type="keyword", keywords=["foo"],
                     attributes={"label": "a"}, priority=10),
                Rule(id="b", type="keyword", keywords=["foo"],
                     attributes={"label": "b"}, priority=10, override=True),
            ]
        )
    )
    result = pipeline.normalize("item foo")
    assert result.attributes["label"] == "b"
    # tied with distinct values → conflict still recorded for transparency
    assert len(result.attribute_conflicts) == 1
    c = result.attribute_conflicts[0]
    assert c.field == "label"
    assert c.resolved_by == "b"
    assert {cc.rule_id for cc in c.candidates} == {"a", "b"}


def test_tied_priority_no_override_records_conflict_first_wins() -> None:
    pipeline = NormalizePipeline(
        _config(
            [
                Rule(id="first", type="keyword", keywords=["foo"],
                     attributes={"label": "first"}, priority=10),
                Rule(id="second", type="keyword", keywords=["foo"],
                     attributes={"label": "second"}, priority=10),
            ]
        )
    )
    result = pipeline.normalize("item foo")
    assert result.attributes["label"] == "first"
    assert len(result.attribute_conflicts) == 1
    assert any("attribute conflict" in w for w in result.warnings)


def test_tied_priority_same_value_no_conflict() -> None:
    pipeline = NormalizePipeline(
        _config(
            [
                Rule(id="a", type="keyword", keywords=["foo"],
                     attributes={"label": "same"}, priority=10),
                Rule(id="b", type="keyword", keywords=["bar"],
                     attributes={"label": "same"}, priority=10),
            ]
        )
    )
    result = pipeline.normalize("item foo bar")
    assert result.attributes["label"] == "same"
    assert result.attribute_conflicts == []


def test_fallback_only_fills_holes() -> None:
    pipeline = NormalizePipeline(
        _config(
            [
                Rule(id="primary", type="keyword", keywords=["foo"],
                     attributes={"color": "red"}, priority=5),
                Rule(id="fb", type="keyword", keywords=["item"],
                     attributes={"color": "default", "shape": "circle"},
                     priority=99, fallback=True),
            ]
        )
    )
    result = pipeline.normalize("item foo")
    # primary set color → fallback's color claim is ignored even though
    # fallback's nominal priority is higher
    assert result.attributes["color"] == "red"
    # but fallback still contributed shape (no other claim)
    assert result.attributes["shape"] == "circle"


def test_defaults_fill_when_no_canonical_match() -> None:
    config = PipelineConfig(
        dictionaries={},
        rules=RuleSet(rules=[]),
        defaults={"canonical_name": "unknown", "category": "misc"},
    )
    pipeline = NormalizePipeline(config)
    result = pipeline.normalize("totally unrelated")
    assert result.canonical_name == "unknown"
    assert result.category == "misc"
