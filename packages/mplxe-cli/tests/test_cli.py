"""End-to-end smoke tests for the CLI."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mplxe_cli.main import app

EXAMPLES = Path(__file__).resolve().parents[2].parent / "examples"
RULES = EXAMPLES / "ingredients.yaml"
RULES_DIR = EXAMPLES / "rules"
runner = CliRunner()


def test_version() -> None:
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    out = res.stdout
    # both packages must be reported so users can verify which mplxe-core
    # the installed CLI is talking to
    assert "mplxe-cli" in out
    assert "mplxe-core" in out
    import mplxe as _core
    assert _core.__version__ in out
    from mplxe_cli import __version__ as cli_version
    assert cli_version in out


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


def test_normalize_with_rules_directory() -> None:
    """`--rules <dir>` should load every YAML under the tree via load_rules."""
    res = runner.invoke(
        app,
        ["normalize", "鶏もも肉 皮つき 30g", "--rules", str(RULES_DIR)],
    )
    assert res.exit_code == 0, res.stdout
    payload = json.loads(res.stdout)
    assert payload["canonical_name"] == "鶏肉"
    assert payload["attributes"]["amount"] == 30


def test_normalize_missing_rules_dir_exits_2(tmp_path: Path) -> None:
    res = runner.invoke(
        app,
        ["normalize", "x", "--rules", str(tmp_path / "missing_dir")],
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


def test_explain_separates_suppressed_matches(tmp_path: Path) -> None:
    """`mplxe explain` must show suppressed dictionary candidates in their own
    labeled section so reviewers can see which shorter terms were dropped
    by a longer match."""
    rules_yaml = tmp_path / "rules.yaml"
    rules_yaml.write_text(
        "dictionaries:\n"
        "  ingredients:\n"
        "    - canonical_name: あひる卵\n"
        "      category: 卵類\n"
        "      synonyms: [あひる卵]\n"
        "    - canonical_name: あひる\n"
        "      category: その他肉類\n"
        "      synonyms: [あひる, かも]\n"
        "rules: []\n",
        encoding="utf-8",
    )
    res = runner.invoke(
        app, ["explain", "あひる卵 ピータン", "--rules", str(rules_yaml)]
    )
    assert res.exit_code == 0, res.stdout
    out = res.stdout
    # active dictionary section keeps the chosen longer term
    assert "Dictionary Match" in out
    assert "あひる卵" in out
    # suppressed section appears with the dropped shorter term
    assert "Suppressed Matches" in out
    # the suppressing rule_id is referenced so reviewers can trace it
    assert "dict:ingredients:あひる卵" in out


def test_explain_omits_suppressed_section_when_none(tmp_path: Path) -> None:
    """No suppressed-matches section should appear for clean inputs."""
    res = runner.invoke(
        app, ["explain", "鶏もも肉 30g", "--rules", str(RULES)]
    )
    assert res.exit_code == 0, res.stdout
    assert "Suppressed Matches" not in res.stdout
