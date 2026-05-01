"""Directory-aware rule loader.

`load_rules("rules/")` walks the directory tree, parses every YAML file,
and stitches the per-file `rules` and `dictionaries` into a single
`PipelineConfig`. The path of each file determines its namespace:

  rules/ingredients/meat.yaml      → namespace="ingredients.meat"
  rules/common/amount.yaml         → namespace="common.amount"

A file may override its namespace explicitly with a top-level
`namespace:` key; an individual rule or dictionary entry may further
override it on the rule. Resolution order is rule > entry > file > path.

Multiple files may declare the same dictionary name — their entries are
appended in load order. Each entry retains its own (possibly different)
namespace, so namespace filtering operates entry-by-entry.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError
from .models import (
    Dictionary,
    DictionaryEntry,
    PipelineConfig,
    Rule,
    RuleSet,
)


def load_rules(directory: str | Path) -> PipelineConfig:
    """Load every *.yaml / *.yml file under `directory` into one PipelineConfig.

    Namespaces are derived from each file's path relative to `directory`.
    Loading is deterministic: files are visited in sorted path order so
    later "first declared wins" tie-breaking remains stable across runs.
    """
    root = Path(directory)
    if not root.exists():
        raise ConfigError(f"rules directory not found: {root}")
    if not root.is_dir():
        raise ConfigError(f"not a directory: {root}")

    yaml_files = sorted(
        {*root.rglob("*.yaml"), *root.rglob("*.yml")},
        key=lambda p: p.as_posix(),
    )

    all_rules: list[Rule] = []
    all_dicts: dict[str, Dictionary] = {}
    options: dict[str, Any] = {}
    defaults: dict[str, Any] = {}

    for yaml_path in yaml_files:
        ns = _path_namespace(yaml_path, root)
        try:
            with yaml_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"failed to parse YAML at {yaml_path}: {e}") from e

        if not isinstance(data, dict):
            raise ConfigError(f"YAML root must be a mapping: {yaml_path}")

        file_ns = data.get("namespace") or ns

        for raw in data.get("rules") or []:
            all_rules.append(_parse_rule(raw, file_ns, yaml_path))

        for d_name, raw_entries in (data.get("dictionaries") or {}).items():
            if not isinstance(raw_entries, list):
                raise ConfigError(
                    f"dictionary '{d_name}' in {yaml_path} must be a list"
                )
            entries = [
                _parse_entry(d_name, e, file_ns, yaml_path) for e in raw_entries
            ]
            existing = all_dicts.get(d_name)
            if existing is None:
                all_dicts[d_name] = Dictionary(name=d_name, entries=entries)
            else:
                all_dicts[d_name] = Dictionary(
                    name=d_name, entries=[*existing.entries, *entries]
                )

        for k, v in (data.get("options") or {}).items():
            options[k] = v
        for k, v in (data.get("defaults") or {}).items():
            defaults[k] = v

    return PipelineConfig(
        dictionaries=all_dicts,
        rules=RuleSet(rules=all_rules),
        options=options,
        defaults=defaults,
    )


def _path_namespace(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = [p for p in rel.parts if p]
    return ".".join(parts) if parts else ""


def _parse_rule(raw: Any, file_ns: str, source: Path) -> Rule:
    if not isinstance(raw, dict):
        raise ConfigError(f"rule must be a mapping in {source}: {raw!r}")
    body = dict(raw)
    body.setdefault("namespace", file_ns)
    try:
        return Rule(**body)
    except Exception as ex:
        raise ConfigError(f"invalid rule in {source}: {ex}") from ex


def _parse_entry(
    dict_name: str, raw: Any, file_ns: str, source: Path
) -> DictionaryEntry:
    if not isinstance(raw, dict):
        raise ConfigError(
            f"entry in dictionary '{dict_name}' ({source}) must be a mapping: {raw!r}"
        )
    body = dict(raw)
    body.setdefault("namespace", file_ns)
    try:
        return DictionaryEntry(**body)
    except Exception as ex:
        raise ConfigError(
            f"invalid entry in dictionary '{dict_name}' ({source}): {ex}"
        ) from ex


__all__ = ["load_rules"]
