"""Load a PipelineConfig from a YAML file or dict."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..errors import ConfigError
from ..models import (
    Dictionary,
    DictionaryEntry,
    PipelineConfig,
    Rule,
    RuleSet,
)


def load_pipeline_config(path: str | Path) -> PipelineConfig:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"YAML file not found: {p}")
    try:
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"failed to parse YAML at {p}: {e}") from e
    return parse_pipeline_config(data)


def parse_pipeline_config(data: Any) -> PipelineConfig:
    if not isinstance(data, dict):
        raise ConfigError("YAML root must be a mapping")

    raw_dicts = data.get("dictionaries") or {}
    if not isinstance(raw_dicts, dict):
        raise ConfigError("'dictionaries' must be a mapping of name -> entries")

    dictionaries: dict[str, Dictionary] = {}
    for name, entries in raw_dicts.items():
        if not isinstance(entries, list):
            raise ConfigError(
                f"dictionary '{name}' must be a list of entries"
            )
        parsed = [_parse_entry(name, e) for e in entries]
        dictionaries[name] = Dictionary(name=name, entries=parsed)

    raw_rules = data.get("rules") or []
    if not isinstance(raw_rules, list):
        raise ConfigError("'rules' must be a list")
    rules = [_parse_rule(r) for r in raw_rules]

    options = data.get("options") or {}
    if not isinstance(options, dict):
        raise ConfigError("'options' must be a mapping")

    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ConfigError("'defaults' must be a mapping")

    return PipelineConfig(
        dictionaries=dictionaries,
        rules=RuleSet(rules=rules),
        options=options,
        defaults=defaults,
    )


def _parse_entry(dict_name: str, e: Any) -> DictionaryEntry:
    if not isinstance(e, dict):
        raise ConfigError(
            f"entry in dictionary '{dict_name}' must be a mapping: {e!r}"
        )
    try:
        return DictionaryEntry(**e)
    except Exception as ex:
        raise ConfigError(
            f"invalid entry in dictionary '{dict_name}': {ex}"
        ) from ex


def _parse_rule(r: Any) -> Rule:
    if not isinstance(r, dict):
        raise ConfigError(f"rule must be a mapping: {r!r}")
    try:
        return Rule(**r)
    except Exception as ex:
        raise ConfigError(f"invalid rule: {ex}") from ex
