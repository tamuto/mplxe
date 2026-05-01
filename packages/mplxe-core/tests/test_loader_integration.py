"""Directory-based RuleLoader integration.

Loads the examples/rules/ tree and verifies that namespaces are derived
from the directory layout, dictionaries from multiple files merge, and
the resulting PipelineConfig produces correct normalizations.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mplxe import NormalizePipeline, load_rules


RULES_DIR = Path(__file__).resolve().parents[3] / "examples" / "rules"


@pytest.fixture(scope="module")
def pipeline() -> NormalizePipeline:
    return NormalizePipeline(load_rules(RULES_DIR))


def test_loader_assigns_path_namespaces() -> None:
    config = load_rules(RULES_DIR)
    by_id = {r.id: r for r in config.rules.rules}

    assert by_id["amount_g"].namespace == "common.amount"
    assert by_id["origin_domestic"].namespace == "common.origin"
    assert by_id["skin_on"].namespace == "ingredients.meat"
    assert by_id["cut_sliced"].namespace == "ingredients.vegetable"


def test_loader_merges_same_named_dictionary() -> None:
    config = load_rules(RULES_DIR)
    # both meat.yaml and vegetable.yaml declare a dictionary named "ingredients";
    # entries should be combined into one Dictionary
    ing = config.dictionaries["ingredients"]
    canonicals = {e.canonical_name for e in ing.entries}
    assert {"鶏肉", "豚肉", "牛肉", "玉ねぎ", "人参", "じゃがいも"} <= canonicals
    # entry namespaces must reflect their source file
    by_canonical = {e.canonical_name: e for e in ing.entries}
    assert by_canonical["鶏肉"].namespace == "ingredients.meat"
    assert by_canonical["人参"].namespace == "ingredients.vegetable"


def test_loaded_pipeline_normalizes_full_case(
    pipeline: NormalizePipeline,
) -> None:
    result = pipeline.normalize("国産鶏もも肉 皮付き 30g")
    assert result.canonical_name == "鶏肉"
    assert result.category == "肉類"
    assert result.attributes["origin"] == "国産"
    assert result.attributes["skin"] == "あり"
    assert result.attributes["part"] == "もも"
    assert result.attributes["amount"] == 30
    assert result.attributes["unit"] == "g"


def test_namespace_filter_only_meat_excludes_vegetable_canonicals() -> None:
    pipeline = NormalizePipeline(
        load_rules(RULES_DIR),
        enabled_namespaces=["ingredients.meat", "common.*"],
    )
    # 人参 is in ingredients.vegetable → masked out → no canonical
    result = pipeline.normalize("人参 30g")
    assert result.canonical_name is None
    assert result.attributes.get("unit") == "g"
