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
    "primary",
    "resource",
    "secondary",
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
_FALLBACK_NAMESPACE_TO_TYPES: dict[str, tuple[str, ...]] = {
    "secondary": ("energy",),
    "primary": ("fuel",),
    "resource": ("other", "energy"),
    "material": ("material",),
    "service": ("service",),
    "emission": ("emission",),
    "money": ("money",),
}
_FALLBACK_LEGACY_COMMODITY_NAMESPACES = frozenset({"C", "E", "S", "M", "D", "F"})


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


def commodity_namespace_type_map() -> dict[str, frozenset[str]]:
    """Canonical namespace->allowed commodity.type mapping."""
    return {
        namespace: frozenset(_FALLBACK_NAMESPACE_TO_TYPES.get(namespace, ()))
        for namespace in commodity_namespace_enum()
    }


def namespaces_for_commodity_type(commodity_type: str) -> tuple[str, ...]:
    """Canonical namespace prefixes that are valid for a commodity.type."""
    if not isinstance(commodity_type, str) or not commodity_type:
        return ()
    mapping = commodity_namespace_type_map()
    return tuple(
        namespace
        for namespace, allowed_types in mapping.items()
        if commodity_type in allowed_types
    )


def split_commodity_namespace(commodity_id: str) -> tuple[str | None, str]:
    """Split commodity id into (namespace, base_name)."""
    if not isinstance(commodity_id, str) or ":" not in commodity_id:
        return None, commodity_id if isinstance(commodity_id, str) else ""
    namespace, _, base = commodity_id.partition(":")
    return namespace, base


def is_legacy_commodity_namespace(namespace: str | None) -> bool:
    """True for legacy VEDA-style namespace prefixes (C:/E:/S:/...)."""
    return namespace in _FALLBACK_LEGACY_COMMODITY_NAMESPACES


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
