"""Shared version constants for VedaLang source and emitted artifacts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DSL_VERSION = "0.2"
TABLEIR_ARTIFACT_VERSION = "1.0.0"
CHECK_OUTPUT_VERSION = "1.0.0"
PIPELINE_OUTPUT_VERSION = "1.0.0"


def with_dsl_version(source: dict[str, Any]) -> dict[str, Any]:
    """Return a source dict annotated with the current DSL version."""
    if not isinstance(source, dict):
        return source
    normalized = deepcopy(source)
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
