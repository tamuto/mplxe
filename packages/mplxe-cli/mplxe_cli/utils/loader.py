"""Pipeline loader — translates a YAML path or directory into a NormalizePipeline.

Accepts either:
  * a single YAML file → ``load_pipeline_config``
  * a directory tree   → ``load_rules`` (namespaces from relative paths)
"""
from __future__ import annotations

from pathlib import Path

import typer

from mplxe import NormalizePipeline, load_pipeline_config, load_rules
from mplxe.errors import ConfigError


def load_pipeline(rules_path: Path) -> NormalizePipeline:
    """Load a NormalizePipeline from a rules YAML file or directory.

    Exits with a clear error message if the path is missing or malformed,
    so command implementations can stay focused on the happy path.
    """
    if not rules_path.exists():
        typer.secho(
            f"error: rules path not found: {rules_path}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        config = (
            load_rules(rules_path)
            if rules_path.is_dir()
            else load_pipeline_config(rules_path)
        )
    except ConfigError as e:
        typer.secho(f"error: invalid rules: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from e
    return NormalizePipeline(config)
