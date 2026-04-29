"""`mplxe suggest` — produce review hints for unmapped / low-confidence rows.

Design intent
-------------
This command is a *suggestion generator*, not an auto-fixer. It surfaces
which texts a human reviewer should look at to grow the dictionary or
add rules. It deliberately does NOT:

  * rewrite rules.yaml
  * auto-confirm a canonical_name
  * call an LLM
  * trust its own confidence numbers

Two input modes
---------------
* ``raw``    — un-normalized rows; we run pipeline.normalize on each.
* ``review`` — output of ``mplxe batch``; we read existing
  ``canonical_name`` / ``confidence`` columns. Falls back to ``raw`` if
  those columns are absent.

Future extension points
-----------------------
* LLM suggestion provider (delegate to ``mplxe.extensions.LLMSuggestionProvider``)
* embedding-based clustering / similarity
* TF-IDF n-gram clustering
* rule generation assistant (suggest new rules from frequent unknown patterns)
* interactive approval workflow (apply approved suggestions to rules.yaml)
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from mplxe.tokenizer import SimpleTokenizer

from ..utils.clustering import greedy_cluster
from ..utils.formatter import make_console
from ..utils.io import detect_format, read_table, write_table
from ..utils.loader import load_pipeline
from ..utils.similarity import (
    Candidate,
    ScoredCandidate,
    build_candidates_from_config,
    find_nearest,
    require_rapidfuzz,
)

OUTPUT_COLUMNS = [
    "cluster_id",
    "text",
    "count",
    "current_canonical_name",
    "current_category",
    "current_confidence",
    "suggestion_type",
    "nearest_canonical_name",
    "nearest_matched_term",
    "nearest_score",
    "candidate_json",
    "reason",
]

# A token must appear at least this many times across the input to be
# reported as a frequent unknown token. Keeps the summary tight.
UNKNOWN_TOKEN_MIN_COUNT = 2


def suggest_command(
    input_path: Annotated[
        Path,
        typer.Argument(help="Input CSV or JSON file.", metavar="INPUT"),
    ],
    column: Annotated[
        str,
        typer.Option("--column", "-c", help="Column containing text to analyze."),
    ],
    rules: Annotated[
        Path | None,
        typer.Option(
            "--rules", "-r",
            help="Rules YAML. Required for --mode raw; optional for review.",
        ),
    ] = None,
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
    mode: Annotated[
        str,
        typer.Option(
            "--mode", "-m",
            help="raw (normalize on the fly) or review (use existing canonical_name).",
        ),
    ] = "raw",
    min_score: Annotated[
        int,
        typer.Option(
            "--min-score",
            help="Minimum fuzzy score (0-100) for clustering and dictionary suggestions.",
        ),
    ] = 75,
    low_confidence: Annotated[
        float,
        typer.Option(
            "--low-confidence",
            help="Confidence threshold below which a row is flagged for review.",
        ),
    ] = 0.7,
    top_k: Annotated[
        int,
        typer.Option("--top-k", help="Top-k dictionary candidates to keep per row."),
    ] = 3,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Log per-row diagnostics to stderr."),
    ] = False,
) -> None:
    """Generate review suggestions from un-normalized or batch-normalized rows."""
    err_console = make_console(stderr=True)

    try:
        require_rapidfuzz()
    except RuntimeError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from e

    mode_lc = mode.lower()
    if mode_lc not in {"raw", "review"}:
        typer.secho(
            f"error: --mode must be 'raw' or 'review', got '{mode}'",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    in_fmt = detect_format(input_path)
    out_fmt = _resolve_output_format(fmt, output, in_fmt)

    rows, _fieldnames = read_table(input_path, in_fmt)

    if not rows:
        err_console.print("[yellow]warning:[/yellow] input has no rows")
        write_table([], OUTPUT_COLUMNS, out_fmt, output)
        return

    if column not in rows[0]:
        available = ", ".join(rows[0].keys()) or "(none)"
        typer.secho(
            f"error: column '{column}' not found in input. "
            f"Available columns: {available}",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    pipeline = None
    candidates: list[Candidate] = []
    rule_keywords: set[str] = set()
    if rules is not None:
        pipeline = load_pipeline(rules)
        candidates = build_candidates_from_config(pipeline.config)
        rule_keywords = {
            kw
            for r in pipeline.config.rules.rules
            for kw in (r.keywords or [])
        }
    elif verbose:
        err_console.print(
            "[dim]no --rules: dictionary similarity disabled[/dim]"
        )

    has_review_columns = (
        mode_lc == "review"
        and "canonical_name" in rows[0]
        and "confidence" in rows[0]
    )
    if mode_lc == "review" and not has_review_columns:
        if verbose:
            err_console.print(
                "[dim]review mode: no canonical_name/confidence columns "
                "— falling back to raw[/dim]"
            )
        mode_lc = "raw"

    if mode_lc == "raw" and pipeline is None:
        typer.secho(
            "error: --mode raw requires --rules to normalize rows",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    enriched = _enrich_rows(
        rows, column, pipeline, has_review_columns, err_console, verbose
    )
    targets = [e for e in enriched if _is_target(e, low_confidence)]

    text_count: Counter[str] = Counter(e["text"] for e in targets if e["text"])
    clusters = greedy_cluster(text_count.keys(), min_score=float(min_score))

    # First-occurrence enriched record per unique text — used as the per-text view.
    first_seen: dict[str, dict] = {}
    for e in targets:
        first_seen.setdefault(e["text"], e)

    suggestions: list[dict[str, Any]] = []
    unmatched_count = 0
    low_conf_count = 0

    ordered_texts = sorted(
        text_count.keys(),
        key=lambda t: (clusters.get(t, 0), -text_count[t], t),
    )
    for text in ordered_texts:
        e = first_seen[text]
        count = text_count[text]
        cur_canonical = e["canonical_name"]
        cur_category = e["category"]
        cur_conf = float(e["confidence"])
        warnings_list = e.get("warnings", [])

        nearest = (
            find_nearest(text, candidates, top_k=top_k, min_score=float(min_score))
            if candidates
            else []
        )

        sug_types = _suggestion_types(
            cur_canonical=cur_canonical,
            cur_conf=cur_conf,
            low_confidence=low_confidence,
            nearest=nearest,
            warnings_list=warnings_list,
            cluster_id=clusters.get(text, 0),
            cluster_sizes=_cluster_sizes(clusters),
            has_dictionary=bool(candidates),
        )
        if not cur_canonical:
            unmatched_count += count
        if cur_canonical and cur_conf < low_confidence:
            low_conf_count += count

        suggestions.append({
            "cluster_id": clusters.get(text, 0),
            "text": text,
            "count": count,
            "current_canonical_name": cur_canonical,
            "current_category": cur_category,
            "current_confidence": round(cur_conf, 3),
            "suggestion_type": ",".join(sug_types),
            "nearest_canonical_name": nearest[0].canonical_name if nearest else "",
            "nearest_matched_term": nearest[0].matched_term if nearest else "",
            "nearest_score": round(nearest[0].score, 1) if nearest else None,
            "candidate_json": json.dumps(
                [_candidate_to_dict(c) for c in nearest], ensure_ascii=False
            ),
            "reason": _build_reason(
                cur_canonical=cur_canonical,
                cur_conf=cur_conf,
                low_confidence=low_confidence,
                nearest=nearest,
                sug_types=sug_types,
                warnings_list=warnings_list,
            ),
        })

    unknown_tokens = _find_unknown_tokens(
        enriched, candidates, rule_keywords, min_count=UNKNOWN_TOKEN_MIN_COUNT
    )

    write_table(suggestions, OUTPUT_COLUMNS, out_fmt, output)

    _render_summary(
        err_console,
        input_rows=len(rows),
        target_count=len(targets),
        cluster_count=len(set(clusters.values())),
        unmatched=unmatched_count,
        low_confidence=low_conf_count,
        suggestions=suggestions,
        unknown_tokens=unknown_tokens,
        output=output,
    )


# --------------------------------------------------------------------------- helpers


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


def _enrich_rows(
    rows: list[dict],
    column: str,
    pipeline,
    has_review_columns: bool,
    err_console,
    verbose: bool,
) -> list[dict]:
    """Compute current_* fields for each row, normalizing on the fly when needed."""
    out: list[dict] = []
    for i, row in enumerate(rows):
        text = str(row.get(column, "") or "").strip()
        try:
            if has_review_columns:
                out.append({
                    "text": text,
                    "row_index": i,
                    "canonical_name": str(row.get("canonical_name", "") or "").strip(),
                    "category": str(row.get("category", "") or "").strip(),
                    "confidence": _to_float(row.get("confidence")),
                    "warnings": [],
                })
            else:
                result = pipeline.normalize(text)
                out.append({
                    "text": text,
                    "row_index": i,
                    "canonical_name": result.canonical_name or "",
                    "category": result.category or "",
                    "confidence": float(result.confidence),
                    "warnings": list(result.warnings),
                })
                if verbose:
                    err_console.print(
                        f"[dim]#{i + 1}[/dim] {text!r} → "
                        f"canonical={result.canonical_name!r} "
                        f"confidence={result.confidence}"
                    )
        except Exception as e:  # defensive: per-row failures must not abort the run
            err_console.print(
                f"[yellow]warning:[/yellow] row #{i + 1} failed: {e}"
            )
            out.append({
                "text": text,
                "row_index": i,
                "canonical_name": "",
                "category": "",
                "confidence": 0.0,
                "warnings": [f"failed: {e}"],
            })
    return out


def _is_target(e: dict, low_confidence: float) -> bool:
    if not e.get("text"):
        return False
    if not e.get("canonical_name"):
        return True
    if not e.get("category"):
        return True
    if float(e.get("confidence", 0.0)) < low_confidence:
        return True
    if e.get("warnings"):
        return True
    return False


def _to_float(v: Any) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _cluster_sizes(clusters: dict[str, int]) -> dict[int, int]:
    sizes: Counter[int] = Counter()
    for cid in clusters.values():
        sizes[cid] += 1
    return dict(sizes)


def _suggestion_types(
    *,
    cur_canonical: str,
    cur_conf: float,
    low_confidence: float,
    nearest: list[ScoredCandidate],
    warnings_list: list[str],
    cluster_id: int,
    cluster_sizes: dict[int, int],
    has_dictionary: bool,
) -> list[str]:
    """Decide which suggestion_type tags apply to a row.

    Multiple tags are allowed and joined with ',' in the output column. The
    full list is also reflected in `candidate_json` / `reason`.
    """
    tags: list[str] = []
    if not cur_canonical:
        tags.append("unmatched")
    elif cur_conf < low_confidence:
        tags.append("low_confidence")

    if nearest:
        tags.append("nearest_dictionary")
        if not cur_canonical:
            tags.append("possible_synonym")
    elif has_dictionary and not cur_canonical:
        tags.append("unknown_token")

    if cluster_id and cluster_sizes.get(cluster_id, 0) > 1:
        tags.append("similar_cluster")

    if warnings_list and "unmatched" not in tags:
        tags.append("possible_rule")

    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out or ["unmatched"]


def _candidate_to_dict(c: ScoredCandidate) -> dict[str, Any]:
    return {
        "canonical_name": c.canonical_name,
        "matched_term": c.matched_term,
        "score": round(c.score, 1),
        "source": c.source,
    }


def _build_reason(
    *,
    cur_canonical: str,
    cur_conf: float,
    low_confidence: float,
    nearest: list[ScoredCandidate],
    sug_types: list[str],
    warnings_list: list[str],
) -> str:
    parts: list[str] = []
    if "unmatched" in sug_types:
        parts.append("既存辞書にマッチしませんでした。")
    elif "low_confidence" in sug_types:
        parts.append(
            f"現在の confidence {cur_conf:.3f} が閾値 {low_confidence} を下回っています。"
        )
    if nearest:
        n = nearest[0]
        parts.append(
            f"既存辞書の {n.source}「{n.matched_term}」"
            f"（canonical: {n.canonical_name}）と類似度 {n.score:.0f} で一致しました。"
        )
    if "similar_cluster" in sug_types:
        parts.append("同じクラスタに類似した未分類表現が存在します。")
    if "unknown_token" in sug_types and not nearest:
        parts.append("辞書に近い候補が見つかりませんでした — 新規 synonym/rule の追加を検討してください。")
    for w in warnings_list:
        parts.append(f"warning: {w}")
    return " ".join(parts) or "確認対象として抽出されました。"


def _find_unknown_tokens(
    enriched: list[dict],
    candidates: list[Candidate],
    rule_keywords: set[str],
    *,
    min_count: int,
) -> list[tuple[str, int]]:
    """Tokenize each row's text and return frequent tokens not present in rules."""
    tokenizer = SimpleTokenizer()
    known = {c.matched_term for c in candidates} | {
        c.canonical_name for c in candidates
    } | set(rule_keywords)

    counter: Counter[str] = Counter()
    for e in enriched:
        text = e.get("text", "") or ""
        if not text:
            continue
        for tok in tokenizer.tokenize(text):
            t = tok.text
            if not t:
                continue
            if t in known:
                continue
            # skip pure-numeric tokens — those are typically captured by amount rules
            if t.isdigit():
                continue
            counter[t] += 1
    return [(t, c) for t, c in counter.most_common() if c >= min_count]


def _render_summary(
    console,
    *,
    input_rows: int,
    target_count: int,
    cluster_count: int,
    unmatched: int,
    low_confidence: int,
    suggestions: list[dict],
    unknown_tokens: list[tuple[str, int]],
    output: Path | None,
) -> None:
    console.print()
    console.print("[bold green]Suggestions generated[/bold green]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column(justify="right")
    table.add_row("Input rows", f"{input_rows:,}")
    table.add_row("Suggestion targets", f"{target_count:,}")
    table.add_row("Clusters", f"{cluster_count:,}")
    table.add_row("Unmatched", f"{unmatched:,}")
    table.add_row("Low confidence", f"{low_confidence:,}")
    console.print(table)

    by_cluster: dict[int, list[dict]] = {}
    for s in suggestions:
        by_cluster.setdefault(s["cluster_id"], []).append(s)
    cluster_views = sorted(
        (
            (cid, sum(s["count"] for s in items), items)
            for cid, items in by_cluster.items()
            if cid  # 0 means "no cluster"
        ),
        key=lambda x: (-x[1], x[0]),
    )
    if cluster_views:
        console.print("\n[bold cyan]Top clusters:[/bold cyan]")
        for i, (cid, size, items) in enumerate(cluster_views[:5], start=1):
            preview = " / ".join(s["text"] for s in items[:5])
            extra = "" if len(items) <= 5 else f" / … (+{len(items) - 5})"
            console.print(
                f"  {i}. {preview}{extra}  "
                f"[dim](cluster #{cid}, {size} occurrence{'s' if size != 1 else ''})[/dim]"
            )

    if unknown_tokens:
        console.print("\n[bold cyan]Frequent unknown tokens:[/bold cyan]")
        for t, c in unknown_tokens[:10]:
            console.print(f"  - {t} [dim]({c}x)[/dim]")

    if output is not None:
        console.print(f"\n[dim]Wrote suggestions to:[/dim] {output}")
