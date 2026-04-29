"""Pipeline loader — translates a YAML path into a ready-to-use NormalizePipeline."""
from __future__ import annotations

from pathlib import Path

import typer

from mplxe import NormalizePipeline, load_pipeline_config
from mplxe.errors import ConfigError


def load_pipeline(rules_path: Path) -> NormalizePipeline:
    """Load a NormalizePipeline from a YAML rules file.

    Exits with a clear error message if the file is missing or malformed,
    so command implementations can stay focused on the happy path.
    """
    if not rules_path.exists():
        typer.secho(
            f"error: rules file not found: {rules_path}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        config = load_pipeline_config(rules_path)
    except ConfigError as e:
        typer.secho(f"error: invalid rules file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from e
    return NormalizePipeline(config)
