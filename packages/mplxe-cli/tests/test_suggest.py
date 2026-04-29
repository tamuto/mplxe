"""End-to-end tests for the `mplxe suggest` command."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from mplxe_cli.main import app
from mplxe_cli.utils.clustering import greedy_cluster
from mplxe_cli.utils.similarity import (
    Candidate,
    find_nearest,
    fuzzy_score,
)

RULES = Path(__file__).resolve().parents[2].parent / "examples" / "ingredients.yaml"
runner = CliRunner()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------------- unit


def test_fuzzy_score_identical_is_100() -> None:
    assert fuzzy_score("鶏もも肉", "鶏もも肉") == 100


def test_fuzzy_score_partial_match_is_high() -> None:
    # partial_ratio rescues short Japanese substrings
    assert fuzzy_score("鶏もも", "鶏もも肉") >= 80


def test_find_nearest_returns_top_k_unique_canonicals() -> None:
    candidates = [
        Candidate("鶏肉", "鶏もも肉", "dictionary.synonym"),
        Candidate("鶏肉", "鶏むね肉", "dictionary.synonym"),
        Candidate("豚肉", "豚バラ", "dictionary.synonym"),
    ]
    result = find_nearest("鶏もも", candidates, top_k=2, min_score=50)
    assert result, "expected at least one match"
    # de-dup by canonical: at most one entry per canonical_name
    canonicals = [r.canonical_name for r in result]
    assert len(canonicals) == len(set(canonicals))
    assert result[0].canonical_name == "鶏肉"


def test_greedy_cluster_groups_similar_strings() -> None:
    texts = ["鶏もも皮付き", "鶏もも皮つき", "鶏もも皮付", "豚バラ"]
    clusters = greedy_cluster(texts, min_score=70)
    # the three "鶏もも" variants share a cluster; 豚バラ is its own.
    chicken_ids = {clusters[t] for t in texts[:3]}
    assert len(chicken_ids) == 1
    assert clusters["豚バラ"] not in chicken_ids


# --------------------------------------------------------------------------- e2e


def test_suggest_raw_csv(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text(
        "id,ingredient_name\n"
        "1,鶏もも肉 皮つき 30g\n"
        "2,鶏もも皮付\n"
        "3,謎の食材A\n"
        "4,謎の食材A\n",
        encoding="utf-8",
    )
    out = tmp_path / "suggestions.csv"
    res = runner.invoke(
        app,
        [
            "suggest", str(src),
            "--column", "ingredient_name",
            "--rules", str(RULES),
            "--output", str(out),
            "--min-score", "70",
        ],
    )
    assert res.exit_code == 0, res.stdout

    rows = _read_csv(out)
    texts = {r["text"] for r in rows}
    # row 1 normalizes cleanly to 鶏肉 — should NOT be a suggestion target
    assert "鶏もも肉 皮つき 30g" not in texts
    assert "鶏もも皮付" in texts
    assert "謎の食材A" in texts

    # 鶏もも皮付 should have a nearest dictionary suggestion (鶏肉)
    chicken = next(r for r in rows if r["text"] == "鶏もも皮付")
    assert chicken["nearest_canonical_name"] == "鶏肉"
    assert "nearest_dictionary" in chicken["suggestion_type"]

    # 謎の食材A should be flagged unmatched and dedup'd to a single row with count=2
    nazo = next(r for r in rows if r["text"] == "謎の食材A")
    assert nazo["count"] == "2"
    assert "unmatched" in nazo["suggestion_type"]


def test_suggest_review_uses_existing_columns(tmp_path: Path) -> None:
    src = tmp_path / "batched.csv"
    src.write_text(
        "id,ingredient_name,canonical_name,category,confidence\n"
        "1,鶏もも肉 皮つき 30g,鶏肉,肉類,0.95\n"
        "2,謎の食材B,,,0.0\n"
        "3,微妙な肉,鶏肉,肉類,0.4\n",
        encoding="utf-8",
    )
    out = tmp_path / "suggestions.csv"
    res = runner.invoke(
        app,
        [
            "suggest", str(src),
            "--column", "ingredient_name",
            "--rules", str(RULES),
            "--output", str(out),
            "--mode", "review",
            "--low-confidence", "0.7",
        ],
    )
    assert res.exit_code == 0, res.stdout

    rows = _read_csv(out)
    texts = {r["text"] for r in rows}
    # row 1 has high confidence — not a target
    assert "鶏もも肉 皮つき 30g" not in texts
    # row 2 unmatched, row 3 low confidence — both targets
    assert "謎の食材B" in texts
    assert "微妙な肉" in texts

    low = next(r for r in rows if r["text"] == "微妙な肉")
    assert "low_confidence" in low["suggestion_type"]
    assert low["current_canonical_name"] == "鶏肉"


def test_suggest_review_falls_back_to_raw_when_columns_missing(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text(
        "id,ingredient_name\n1,謎の食材C\n", encoding="utf-8"
    )
    out = tmp_path / "suggestions.csv"
    res = runner.invoke(
        app,
        [
            "suggest", str(src),
            "--column", "ingredient_name",
            "--rules", str(RULES),
            "--output", str(out),
            "--mode", "review",
        ],
    )
    assert res.exit_code == 0, res.stdout
    rows = _read_csv(out)
    assert any(r["text"] == "謎の食材C" for r in rows)


def test_suggest_json_output(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text(
        "id,ingredient_name\n1,鶏もも皮付\n2,謎の食材D\n", encoding="utf-8"
    )
    out = tmp_path / "suggestions.json"
    res = runner.invoke(
        app,
        [
            "suggest", str(src),
            "--column", "ingredient_name",
            "--rules", str(RULES),
            "--output", str(out),
            "--format", "json",
        ],
    )
    assert res.exit_code == 0, res.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    by_text = {row["text"]: row for row in payload}
    assert "鶏もも皮付" in by_text
    # candidate_json is a string field even in JSON output (cell-level JSON)
    candidates = json.loads(by_text["鶏もも皮付"]["candidate_json"])
    assert any(c["canonical_name"] == "鶏肉" for c in candidates)


def test_suggest_missing_column_exits_2(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text("id,name\n1,foo\n", encoding="utf-8")
    res = runner.invoke(
        app,
        [
            "suggest", str(src),
            "--column", "missing",
            "--rules", str(RULES),
        ],
    )
    assert res.exit_code == 2


def test_suggest_raw_without_rules_exits_2(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text("id,ingredient_name\n1,foo\n", encoding="utf-8")
    res = runner.invoke(
        app,
        ["suggest", str(src), "--column", "ingredient_name"],
    )
    assert res.exit_code == 2


def test_suggest_review_without_rules_runs(tmp_path: Path) -> None:
    """Review mode with existing columns should run even without --rules."""
    src = tmp_path / "batched.csv"
    src.write_text(
        "id,ingredient_name,canonical_name,category,confidence\n"
        "1,謎の食材E,,,0.0\n",
        encoding="utf-8",
    )
    out = tmp_path / "suggestions.csv"
    res = runner.invoke(
        app,
        [
            "suggest", str(src),
            "--column", "ingredient_name",
            "--output", str(out),
            "--mode", "review",
        ],
    )
    assert res.exit_code == 0, res.stdout
    rows = _read_csv(out)
    assert any(r["text"] == "謎の食材E" for r in rows)
