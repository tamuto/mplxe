"""End-to-end smoke tests for the CLI."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mplxe_cli.main import app

RULES = Path(__file__).resolve().parents[2].parent / "examples" / "ingredients.yaml"
runner = CliRunner()


def test_version() -> None:
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "mplxe" in res.stdout


def test_normalize_outputs_json() -> None:
    res = runner.invoke(
        app,
        ["normalize", "鶏もも肉 皮つき 30g", "--rules", str(RULES)],
    )
    assert res.exit_code == 0, res.stdout
    payload = json.loads(res.stdout)
    assert payload["canonical_name"] == "鶏肉"
    assert payload["attributes"]["skin"] == "あり"
    assert payload["attributes"]["amount"] == 30


def test_normalize_missing_rules_exits_2(tmp_path: Path) -> None:
    res = runner.invoke(
        app,
        ["normalize", "x", "--rules", str(tmp_path / "missing.yaml")],
    )
    assert res.exit_code == 2


def test_batch_csv_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text("id,name\n1,鶏もも肉 皮つき 30g\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    res = runner.invoke(
        app,
        [
            "batch", str(src),
            "--column", "name",
            "--rules", str(RULES),
            "--output", str(out),
        ],
    )
    assert res.exit_code == 0, res.stdout
    body = out.read_text(encoding="utf-8")
    assert "canonical_name" in body
    assert "鶏肉" in body


def test_batch_bad_column_exits_2(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text("id,name\n1,foo\n", encoding="utf-8")
    res = runner.invoke(
        app,
        ["batch", str(src), "--column", "missing", "--rules", str(RULES)],
    )
    assert res.exit_code == 2


def test_explain_renders_sections() -> None:
    res = runner.invoke(
        app, ["explain", "鶏もも肉 30g", "--rules", str(RULES)]
    )
    assert res.exit_code == 0, res.stdout
    out = res.stdout
    assert "Tokens" in out
    assert "Dictionary Match" in out
    assert "Rules Applied" in out
    assert "Result" in out
