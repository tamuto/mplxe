"""`mplxe explain` — verbose, human-readable view of a single normalization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from ..utils.formatter import make_console, render_explain, result_to_dict
from ..utils.loader import load_pipeline


def explain_command(
    text: Annotated[str, typer.Argument(help="Text to analyze.")],
    rules: Annotated[
        Path,
        typer.Option("--rules", "-r", help="Path to the rules YAML file."),
    ],
    pretty: Annotated[
        bool,
        typer.Option(
            "--pretty",
            help="No-op for explain — output is always rich-formatted.",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o",
            help="Write a JSON dump of the result to this file (in addition to stdout).",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print diagnostic information."),
    ] = False,
) -> None:
    """Analyze a single string and render the full breakdown to stdout."""
    err_console = make_console(stderr=True)
    if verbose:
        err_console.print(f"[dim]Loading rules from {rules}[/dim]")

    pipeline = load_pipeline(rules)
    result = pipeline.normalize(text)

    render_explain(result, console=make_console())

    if output is not None:
        payload = result_to_dict(result)
        # Include the full token & match detail when the user asked for an output dump.
        payload["tokens"] = [t.model_dump() for t in result.tokens]
        payload["matches"] = [m.model_dump() for m in result.matches]
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if verbose:
            err_console.print(f"[dim]wrote {output}[/dim]")
