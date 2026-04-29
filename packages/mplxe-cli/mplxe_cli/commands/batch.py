"""`mplxe batch` — bulk-normalize one column of a CSV / JSON file.

Adds four columns to each row:

* ``canonical_name``
* ``category``
* ``attributes``  (JSON string)
* ``confidence``

Designed to be quiet by default (just a progress bar to stderr) so the
output stream stays clean for piping. ``--verbose`` flips on per-row logs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from ..utils.formatter import make_console
from ..utils.io import detect_format, read_table, write_table
from ..utils.loader import load_pipeline

OUTPUT_COLUMNS = ["canonical_name", "category", "attributes", "confidence"]


def batch_command(
    input_path: Annotated[
        Path,
        typer.Argument(help="Input CSV or JSON file.", metavar="INPUT"),
    ],
    rules: Annotated[
        Path,
        typer.Option("--rules", "-r", help="Path to the rules YAML file."),
    ],
    column: Annotated[
        str,
        typer.Option("--column", "-c", help="Column containing the text to normalize."),
    ] = "name",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (defaults to stdout)."),
    ] = None,
    fmt: Annotated[
        str | None,
        typer.Option(
            "--format", "-f",
            help="Output format: csv or json. Inferred from --output when omitted.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Log every row and its result to stderr."),
    ] = False,
) -> None:
    """Normalize ``--column`` for every row in INPUT."""
    err_console = make_console(stderr=True)

    in_fmt = detect_format(input_path)
    out_fmt = _resolve_output_format(fmt, output, in_fmt)

    if verbose:
        err_console.print(
            f"[dim]input={input_path} format={in_fmt} | "
            f"output={output or '<stdout>'} format={out_fmt}[/dim]"
        )

    pipeline = load_pipeline(rules)
    rows, fieldnames = read_table(input_path, in_fmt)

    if not rows:
        err_console.print("[yellow]warning:[/yellow] input has no rows")
        write_table([], _output_fieldnames(fieldnames), out_fmt, output)
        return

    if column not in rows[0]:
        available = ", ".join(rows[0].keys()) or "(none)"
        typer.secho(
            f"error: column '{column}' not found in input. "
            f"Available columns: {available}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    out_rows: list[dict] = []
    failures = 0

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=err_console,
        transient=not verbose,
    ) as progress:
        task = progress.add_task("normalizing", total=len(rows))
        for i, row in enumerate(rows):
            text = row.get(column, "") or ""
            try:
                result = pipeline.normalize(str(text))
                row[OUTPUT_COLUMNS[0]] = result.canonical_name or ""
                row[OUTPUT_COLUMNS[1]] = result.category or ""
                row[OUTPUT_COLUMNS[2]] = json.dumps(
                    result.attributes, ensure_ascii=False
                )
                row[OUTPUT_COLUMNS[3]] = result.confidence
                if verbose:
                    err_console.print(
                        f"[dim]#{i + 1}[/dim] {text!r} → "
                        f"canonical={result.canonical_name!r} "
                        f"confidence={result.confidence}"
                    )
                if result.warnings and verbose:
                    for w in result.warnings:
                        err_console.print(f"  [yellow]warning:[/yellow] {w}")
            except Exception as e:  # defensive: per-row failures must not abort the batch
                failures += 1
                row[OUTPUT_COLUMNS[0]] = ""
                row[OUTPUT_COLUMNS[1]] = ""
                row[OUTPUT_COLUMNS[2]] = "{}"
                row[OUTPUT_COLUMNS[3]] = 0.0
                err_console.print(
                    f"[yellow]warning:[/yellow] row #{i + 1} failed: {e}"
                )
            out_rows.append(row)
            progress.advance(task)

    write_table(out_rows, _output_fieldnames(fieldnames), out_fmt, output)

    if verbose or failures:
        err_console.print(
            f"[bold]done[/bold] — {len(out_rows)} rows, "
            f"{failures} failure{'s' if failures != 1 else ''}"
        )


def _resolve_output_format(
    explicit: str | None, output: Path | None, fallback: str
) -> str:
    if explicit:
        return detect_format(Path("dummy"), override=explicit)
    if output is not None:
        try:
            return detect_format(output)
        except typer.BadParameter:
            return fallback
    return fallback


def _output_fieldnames(input_fieldnames: list[str]) -> list[str]:
    """Append the four output columns, skipping any that already exist."""
    base = list(input_fieldnames)
    for c in OUTPUT_COLUMNS:
        if c not in base:
            base.append(c)
    return base
