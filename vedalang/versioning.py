"""Shared version constants and source-shape helpers for VedaLang."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DSL_VERSION = "0.2"
TABLEIR_ARTIFACT_VERSION = "1.0.0"
CHECK_OUTPUT_VERSION = "1.0.0"
PIPELINE_OUTPUT_VERSION = "1.0.0"

V0_2_TOP_LEVEL_KEYS = frozenset(
    {
        "imports",
        "commodities",
        "technologies",
        "technology_roles",
        "stock_characterizations",
        "spatial_layers",
        "spatial_measure_sets",
        "temporal_index_series",
        "region_partitions",
        "zone_overlays",
        "sites",
        "facilities",
        "fleets",
        "opportunities",
        "networks",
        "runs",
    }
)
LEGACY_TOP_LEVEL_KEYS = frozenset(
    {
        "model",
        "scoping",
        "roles",
        "variants",
        "availability",
        "process_parameters",
        "demands",
        "diagnostics",
        "commodity_groups",
        "facility_templates",
        "facility_selection",
        "spatial_mappings",
        "providers",
        "provider_parameters",
    }
)


def looks_like_v0_2_source(source: dict[str, Any] | None) -> bool:
    """Return True when a source payload uses the v0.2 public object model."""
    if not isinstance(source, dict):
        return False
    if LEGACY_TOP_LEVEL_KEYS.intersection(source):
        return False
    declared_version = source.get("dsl_version")
    if isinstance(declared_version, str) and declared_version == DSL_VERSION:
        return True
    return bool(V0_2_TOP_LEVEL_KEYS.intersection(source))


def looks_like_legacy_source(source: dict[str, Any] | None) -> bool:
    """Return True when a source payload uses the pre-v0.2 authoring surface."""
    if not isinstance(source, dict):
        return False
    return bool(LEGACY_TOP_LEVEL_KEYS.intersection(source))


def with_dsl_version(source: dict[str, Any]) -> dict[str, Any]:
    """Return a source dict annotated with the current DSL version."""
    if not isinstance(source, dict):
        return source
    normalized = deepcopy(source)
    if looks_like_v0_2_source(normalized):
        normalized.setdefault("dsl_version", DSL_VERSION)
    return normalized


def dsl_version_for_source(source: dict[str, Any] | None) -> str:
    """Resolve the declared DSL version for a source payload."""
    if isinstance(source, dict):
        value = source.get("dsl_version")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return DSL_VERSION


def annotate_tableir(
    tableir: dict[str, Any],
    *,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach stable version metadata to a TableIR artifact."""
    tableir["dsl_version"] = dsl_version_for_source(source)
    tableir["artifact_version"] = TABLEIR_ARTIFACT_VERSION
    tableir["artifact_kind"] = "tableir"
    return tableir
