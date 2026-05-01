"""Pydantic data models for mplxe."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    text: str
    start: int
    end: int


class Attribute(BaseModel):
    """A single attribute extracted from text.

    Stored on Match / NormalizeResult collections; used standalone when callers
    want a typed view of an attribute's provenance.
    """

    name: str
    value: Any
    source_rule_id: str | None = None
    confidence: float = 1.0


class Match(BaseModel):
    """A single rule or dictionary hit against the input text.

    `priority`, `override`, and `fallback` are propagated from the source
    Rule / DictionaryEntry so the conflict resolver does not need to do a
    second lookup. Dictionary matches always have override=False, fallback=False.
    """

    rule_id: str
    matched_text: str
    start: int
    end: int
    attributes: dict[str, Any] = Field(default_factory=dict)
    canonical_name: str | None = None
    category: str | None = None
    score: float = 1.0
    kind: Literal["dictionary", "regex", "keyword"] = "keyword"
    priority: int = 0
    override: bool = False
    fallback: bool = False
    namespace: str | None = None


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["regex", "keyword"]
    pattern: str | None = None
    keywords: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    override: bool = False
    fallback: bool = False
    namespace: str | None = None
    group: str | None = None
    description: str | None = None


class RuleSet(BaseModel):
    """A flat collection of rules. Hierarchy is expressed via `namespace`."""

    rules: list[Rule] = Field(default_factory=list)


class DictionaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: str
    category: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    namespace: str | None = None


class Dictionary(BaseModel):
    name: str
    entries: list[DictionaryEntry] = Field(default_factory=list)


class AttributeConflictCandidate(BaseModel):
    """A single rule's claim for a contested attribute value."""

    rule_id: str
    value: Any
    priority: int
    override: bool = False
    namespace: str | None = None


class AttributeConflict(BaseModel):
    """Recorded when multiple candidates of equal top priority disagree.

    `resolved_value` is the value that ended up on the result; `resolved_by`
    is the rule_id that contributed it. The conflict is informational —
    normalization always picks a value.
    """

    field: str
    candidates: list[AttributeConflictCandidate] = Field(default_factory=list)
    resolved_value: Any = None
    resolved_by: str | None = None


class PipelineConfig(BaseModel):
    dictionaries: dict[str, Dictionary] = Field(default_factory=dict)
    rules: RuleSet = Field(default_factory=RuleSet)
    options: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)


class NormalizeInput(BaseModel):
    text: str
    domain: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class NormalizeResult(BaseModel):
    original_text: str
    normalized_text: str
    canonical_name: str | None = None
    category: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tokens: list[Token] = Field(default_factory=list)
    matches: list[Match] = Field(default_factory=list)
    matched_rules: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    explanations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    attribute_conflicts: list[AttributeConflict] = Field(default_factory=list)
