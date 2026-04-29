"""`mplxe normalize` — single-string normalization with JSON output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from ..utils.formatter import make_console, render_json, result_to_dict
from ..utils.loader import load_pipeline


def normalize_command(
    text: Annotated[str, typer.Argument(help="Text to normalize.")],
    rules: Annotated[
        Path,
        typer.Option("--rules", "-r", help="Path to the rules YAML file."),
    ],
    pretty: Annotated[
        bool,
        typer.Option("--pretty", help="Pretty-print JSON with syntax highlighting."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write JSON to this file instead of stdout."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print diagnostic information to stderr."),
    ] = False,
) -> None:
    """Normalize a single string and emit the result as JSON."""
    err_console = make_console(stderr=True)
    if verbose:
        err_console.print(f"[dim]Loading rules from {rules}[/dim]")

    pipeline = load_pipeline(rules)
    result = pipeline.normalize(text)

    if verbose and result.warnings:
        for w in result.warnings:
            err_console.print(f"[yellow]warning:[/yellow] {w}")

    if output is not None:
        payload = result_to_dict(result)
        text_out = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
        output.write_text(text_out + "\n", encoding="utf-8")
        if verbose:
            err_console.print(f"[dim]wrote {output}[/dim]")
        return

    render_json(result, pretty=pretty, console=make_console())
