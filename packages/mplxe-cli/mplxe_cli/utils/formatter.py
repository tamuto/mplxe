"""Rich-based renderers for human-friendly CLI output."""
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mplxe import NormalizeResult


def make_console(stderr: bool = False) -> Console:
    return Console(stderr=stderr, soft_wrap=False)


def result_to_dict(result: NormalizeResult) -> dict[str, Any]:
    """Plain JSON-serializable view of a NormalizeResult.

    Excludes verbose token / match arrays — those are surfaced by ``explain``.
    """
    return {
        "original_text": result.original_text,
        "normalized_text": result.normalized_text,
        "canonical_name": result.canonical_name,
        "category": result.category,
        "attributes": result.attributes,
        "matched_rules": result.matched_rules,
        "confidence": result.confidence,
        "warnings": result.warnings,
    }


def render_json(result: NormalizeResult, *, pretty: bool, console: Console) -> None:
    payload = result_to_dict(result)
    if pretty:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        console.print(Syntax(text, "json", theme="ansi_dark", background_color="default"))
    else:
        console.print_json(data=payload, ensure_ascii=False)


def render_explain(result: NormalizeResult, *, console: Console) -> None:
    """Render an explain report — the human-readable view of one normalization."""
    console.print(
        Panel.fit(Text(result.original_text, style="bold"), title="Input", border_style="cyan")
    )

    if result.original_text != result.normalized_text:
        console.print(
            f"[dim]Normalized:[/dim] [bold]{result.normalized_text}[/bold]"
        )

    # Tokens
    if result.tokens:
        token_text = "[" + ", ".join(t.text for t in result.tokens) + "]"
        console.print(f"\n[bold cyan]Tokens:[/bold cyan]\n  {token_text}")
    else:
        console.print("\n[bold cyan]Tokens:[/bold cyan]\n  [dim](none)[/dim]")

    # Dictionary matches — split active vs suppressed so reviewers can see
    # which shorter candidates were dropped because a longer term covered them.
    dict_matches = [m for m in result.matches if m.kind == "dictionary"]
    active_dicts = [m for m in dict_matches if not m.suppressed]
    suppressed_dicts = [m for m in dict_matches if m.suppressed]

    console.print("\n[bold cyan]Dictionary Match:[/bold cyan]")
    if active_dicts:
        for m in active_dicts:
            arrow = f"[green]{m.matched_text}[/green] → [bold]{m.canonical_name}[/bold]"
            cat = f" [dim]({m.category})[/dim]" if m.category else ""
            console.print(f"  {arrow}{cat}")
    else:
        console.print("  [dim](no match)[/dim]")

    if suppressed_dicts:
        console.print(
            "\n[bold cyan]Suppressed Matches:[/bold cyan] "
            "[dim](covered by a longer dictionary term — ignored for "
            "canonical / category / confidence)[/dim]"
        )
        for m in suppressed_dicts:
            arrow = (
                f"[strike]{m.matched_text}[/strike] → "
                f"[dim]{m.canonical_name}[/dim]"
            )
            cat = f" [dim]({m.category})[/dim]" if m.category else ""
            by = f" [dim]suppressed by: {m.suppressed_by}[/dim]" if m.suppressed_by else ""
            console.print(f"  {arrow}{cat}{by}")

    # Rules applied
    rule_matches = [m for m in result.matches if m.kind != "dictionary"]
    console.print("\n[bold cyan]Rules Applied:[/bold cyan]")
    if rule_matches:
        for m in rule_matches:
            attrs = ", ".join(f"{k}={v}" for k, v in m.attributes.items())
            console.print(
                f"  - [yellow]{m.rule_id}[/yellow] "
                f"[dim](matched '{m.matched_text}')[/dim] → {attrs}"
            )
    else:
        console.print("  [dim](none)[/dim]")

    # Result table
    console.print("\n[bold cyan]Result:[/bold cyan]")
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("canonical_name", str(result.canonical_name or "[dim](unresolved)[/dim]"))
    table.add_row("category", str(result.category or "[dim]-[/dim]"))
    if result.attributes:
        attrs_table = Table(show_header=False, box=None, padding=(0, 1))
        attrs_table.add_column(style="dim")
        attrs_table.add_column()
        for k, v in result.attributes.items():
            attrs_table.add_row(str(k), str(v))
        table.add_row("attributes", attrs_table)
    else:
        table.add_row("attributes", "[dim]{}[/dim]")
    table.add_row("confidence", _confidence_str(result.confidence))
    console.print(table)

    if result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in result.warnings:
            console.print(f"  - {w}")


def _confidence_str(value: float) -> str:
    if value >= 0.8:
        color = "green"
    elif value >= 0.5:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{value:.3f}[/{color}]"
