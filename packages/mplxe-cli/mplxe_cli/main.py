"""Top-level Typer app for `mplxe`.

Each command is registered as a subcommand. The intent is that this is the
primary day-to-day interface — the same pipeline you would call from Python,
from the shell.
"""
from __future__ import annotations

from typing import Annotated

import typer

import mplxe as _mplxe_core

from . import __version__
from .commands.batch import batch_command
from .commands.explain import explain_command
from .commands.normalize import normalize_command
from .commands.suggest import suggest_command

app = typer.Typer(
    name="mplxe",
    help="Rule-based text normalization — CLI front-end for mplxe-core.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("normalize", help="Normalize a single string and print JSON.")(
    normalize_command
)
app.command("batch", help="Normalize a column of a CSV/JSON file.")(batch_command)
app.command(
    "explain",
    help="Show a human-readable breakdown of how a string is normalized.",
)(explain_command)
app.command(
    "suggest",
    help="Suggest review targets (unmatched / low-confidence rows) without LLM.",
)(suggest_command)


def _version_callback(value: bool) -> None:
    if value:
        core_version = getattr(_mplxe_core, "__version__", "unknown")
        typer.echo(f"mplxe-cli {__version__} (mplxe-core {core_version})")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version", help="Show version and exit.",
            callback=_version_callback, is_eager=True,
        ),
    ] = False,
) -> None:
    """mplxe — rule-based text normalization CLI."""


if __name__ == "__main__":
    app()
