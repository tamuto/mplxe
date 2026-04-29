"""CSV / JSON read & write helpers used by batch processing.

Reads return ``(rows, fieldnames)``: a list of dicts and the canonical column
order. Writes accept the same shape so the I/O layer stays symmetric.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import typer

Row = dict[str, Any]
Format = str  # "csv" | "json"


def detect_format(path: Path, override: str | None = None) -> Format:
    if override:
        f = override.lower()
        if f not in {"csv", "json"}:
            raise typer.BadParameter(f"unsupported format: {override}")
        return f
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".csv", ".tsv", ".txt"}:
        return "csv"
    raise typer.BadParameter(
        f"cannot infer format from extension '{suffix}' — pass --format explicitly"
    )


def read_table(path: Path, fmt: Format) -> tuple[list[Row], list[str]]:
    if not path.exists():
        typer.secho(f"error: input file not found: {path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if fmt == "csv":
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows = [dict(r) for r in reader]
        return rows, fieldnames

    if fmt == "json":
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise typer.BadParameter(
                "JSON input must be an array of objects at the top level"
            )
        rows = [dict(r) for r in data if isinstance(r, dict)]
        # Stable column order: order of first appearance across rows.
        fieldnames: list[str] = []
        seen: set[str] = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
        return rows, fieldnames

    raise typer.BadParameter(f"unsupported format: {fmt}")


def write_table(
    rows: Sequence[Row],
    fieldnames: Sequence[str],
    fmt: Format,
    path: Path | None,
) -> None:
    """Write rows in ``fmt`` to ``path``, or stdout when ``path`` is None."""
    if fmt == "csv":
        if path is None:
            _write_csv(sys.stdout, rows, fieldnames)
        else:
            with path.open("w", encoding="utf-8", newline="") as f:
                _write_csv(f, rows, fieldnames)
        return

    if fmt == "json":
        text = json.dumps(
            [dict(r) for r in rows], ensure_ascii=False, indent=2
        )
        if path is None:
            sys.stdout.write(text + "\n")
        else:
            path.write_text(text + "\n", encoding="utf-8")
        return

    raise typer.BadParameter(f"unsupported format: {fmt}")


def _write_csv(stream, rows: Sequence[Row], fieldnames: Sequence[str]) -> None:
    writer = csv.DictWriter(stream, fieldnames=list(fieldnames))
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in fieldnames})
