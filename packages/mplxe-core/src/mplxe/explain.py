"""Human-readable explanations for a NormalizeResult.

Kept separate from the pipeline so callers can re-render explanations in a
different language or format without re-running normalization.
"""
from __future__ import annotations

from .models import NormalizeResult


def build_explanations(result: NormalizeResult) -> list[str]:
    lines: list[str] = []

    if result.original_text != result.normalized_text:
        lines.append(
            f"前処理: '{result.original_text}' → '{result.normalized_text}'"
        )

    if result.tokens:
        lines.append("トークン化: " + " | ".join(t.text for t in result.tokens))

    dict_matches = [m for m in result.matches if m.kind == "dictionary"]
    rule_matches = [m for m in result.matches if m.kind != "dictionary"]
    active_dicts = [m for m in dict_matches if not m.suppressed]
    suppressed_dicts = [m for m in dict_matches if m.suppressed]

    if active_dicts:
        for m in active_dicts:
            ns = f" [{m.namespace}]" if m.namespace else ""
            lines.append(
                f"辞書ヒット{ns}: '{m.matched_text}' (位置 {m.start}-{m.end}) "
                f"→ canonical='{m.canonical_name}', "
                f"category='{m.category or '(未設定)'}'"
            )
    elif result.canonical_name is None:
        lines.append("辞書ヒットなし: canonical_name は決定できませんでした")

    for m in suppressed_dicts:
        by = m.suppressed_by or "(unknown)"
        lines.append(
            f"辞書候補抑制: '{m.matched_text}' (位置 {m.start}-{m.end}, "
            f"canonical='{m.canonical_name}', category='{m.category or '(未設定)'}') "
            f"はより長い辞書語 {by} に内包されたため抑制されました"
        )

    for m in rule_matches:
        attrs = ", ".join(f"{k}={v}" for k, v in m.attributes.items())
        ns = f" [{m.namespace}]" if m.namespace else ""
        flags = []
        if m.override:
            flags.append("override")
        if m.fallback:
            flags.append("fallback")
        flag_str = f" {{{','.join(flags)}}}" if flags else ""
        lines.append(
            f"ルール適用{ns}: id={m.rule_id}{flag_str} '{m.matched_text}' "
            f"(位置 {m.start}-{m.end}) → {attrs or '(属性なし)'}"
        )

    for c in result.attribute_conflicts:
        cand_lines = [
            f"  - rule={cc.rule_id} value={cc.value!r} "
            f"priority={cc.priority} override={cc.override}"
            for cc in c.candidates
        ]
        lines.append(
            f"属性衝突: field={c.field} → 決定値={c.resolved_value!r} "
            f"(rule={c.resolved_by})\n" + "\n".join(cand_lines)
        )

    if result.canonical_name:
        lines.append(
            f"確定: canonical_name='{result.canonical_name}', "
            f"category='{result.category}', "
            f"attributes={result.attributes}, "
            f"confidence={result.confidence}"
        )

    for w in result.warnings:
        lines.append(f"警告: {w}")

    return lines
