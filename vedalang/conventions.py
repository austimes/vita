"""Canonical modeling conventions derived from the VedaLang schema.

This module is the single runtime source for canonical enum values used by:
- compiler validation
- lint/LLM prompt assembly
- docs synchronization scripts
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "vedalang.schema.json"

_FALLBACK_PROCESS_STAGES = (
    "supply",
    "conversion",
    "distribution",
    "storage",
    "end_use",
    "sink",
)
_FALLBACK_COMMODITY_TYPES = (
    "fuel",
    "energy",
    "service",
    "material",
    "emission",
    "money",
    "other",
)
_FALLBACK_COMMODITY_NAMESPACES = (
    "fuel",
    "resource",
    "energy",
    "service",
    "material",
    "emission",
    "money",
)
_FALLBACK_SCENARIO_CATEGORIES = (
    "demands",
    "prices",
    "policies",
    "technology_assumptions",
    "resource_availability",
    "global_settings",
)


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    with _SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def process_stage_enum() -> tuple[str, ...]:
    """Canonical process stage enum from schema."""
    enum = (
        _load_schema()
        .get("$defs", {})
        .get("process_role", {})
        .get("properties", {})
        .get("stage", {})
        .get("enum")
    )
    if isinstance(enum, list) and enum and all(isinstance(x, str) for x in enum):
        return tuple(enum)
    return _FALLBACK_PROCESS_STAGES


def commodity_type_enum() -> tuple[str, ...]:
    """Canonical commodity.type enum from schema."""
    enum = (
        _load_schema()
        .get("$defs", {})
        .get("commodity", {})
        .get("properties", {})
        .get("type", {})
        .get("enum")
    )
    if isinstance(enum, list) and enum and all(isinstance(x, str) for x in enum):
        return tuple(enum)
    return _FALLBACK_COMMODITY_TYPES


def commodity_namespace_enum() -> tuple[str, ...]:
    """Canonical commodity namespace prefixes from schema."""
    enum = _load_schema().get("$defs", {}).get("commodity_namespace", {}).get("enum")
    if isinstance(enum, list) and enum and all(isinstance(x, str) for x in enum):
        return tuple(enum)
    return _FALLBACK_COMMODITY_NAMESPACES


def scenario_category_enum() -> tuple[str, ...]:
    """Canonical scenario category enum from schema."""
    enum = _load_schema().get("$defs", {}).get("category", {}).get("enum")
    if isinstance(enum, list) and enum and all(isinstance(x, str) for x in enum):
        return tuple(enum)
    return _FALLBACK_SCENARIO_CATEGORIES


def format_enum_pipe(values: tuple[str, ...] | list[str]) -> str:
    return " | ".join(values)


def format_enum_csv(values: tuple[str, ...] | list[str]) -> str:
    return ", ".join(values)


def stage_order(include_demand: bool = False) -> dict[str, int]:
    """Stage rank map for deterministic left-to-right graph layout."""
    ordered = list(process_stage_enum())
    if include_demand:
        ordered.append("demand")
    return {stage: idx for idx, stage in enumerate(ordered)}


def stage_label(stage: str) -> str:
    if stage == "end_use":
        return "End Use"
    return stage.replace("_", " ").title()
