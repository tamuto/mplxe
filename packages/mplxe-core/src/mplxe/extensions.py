"""Extension-point Protocols for future LLM and code-generation support.

These are intentionally just type stubs in v1. The deterministic core never
calls them — they exist so that downstream packages can plug in optional
helpers (review tooling, rule curation, codegen targets) without touching
mplxe-core itself.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import DictionaryEntry, NormalizeResult, PipelineConfig, Rule


@runtime_checkable
class LLMSuggestionProvider(Protocol):
    """Hook for LLM-assisted, human-in-the-loop suggestions.

    Implementations are advisory only: their outputs are meant to be reviewed
    before being merged into a YAML config. The core normalizer must remain
    deterministic.
    """

    def suggest_dictionary_entries(
        self, samples: list[str]
    ) -> list[DictionaryEntry]: ...

    def suggest_rules(self, samples: list[str]) -> list[Rule]: ...

    def cluster_unmatched(self, samples: list[str]) -> dict[str, list[str]]: ...

    def detect_anomalies(
        self, results: list[NormalizeResult]
    ) -> list[NormalizeResult]: ...


@runtime_checkable
class CodeGenerator(Protocol):
    """Hook for emitting executable code from a PipelineConfig.

    Lets a curated rule set be compiled to a faster representation
    (Python AST, Rust, SQL CASE expressions, etc.) for batch jobs.
    """

    def generate(self, config: PipelineConfig, target: str) -> str: ...

    def supported_targets(self) -> list[str]: ...


__all__ = ["LLMSuggestionProvider", "CodeGenerator", "Any"]
