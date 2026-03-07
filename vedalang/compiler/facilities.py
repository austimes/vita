"""Quarantined legacy facility/provider lowering hooks.

The public DSL is now v0.2-only. Legacy facility/template/provider primitives
must fail deterministically instead of lowering into generated providers and
provider-parameter artifacts.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .registry import VedaLangError

_LEGACY_FACILITY_KEYS = (
    "facility_templates",
    "facility_selection",
    "providers",
    "provider_parameters",
)


def _uses_legacy_facility_lowering(source: dict[str, Any]) -> bool:
    if any(source.get(key) for key in _LEGACY_FACILITY_KEYS):
        return True
    if source.get("dsl_version") == "0.2":
        return False
    facilities = source.get("facilities")
    if not isinstance(facilities, list):
        return False
    return any(isinstance(item, dict) and item.get("template") for item in facilities)


def prepare_facilities(
    source: dict[str, Any],
    commodities: dict[str, dict[str, Any]],
    milestone_years: list[int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reject pre-v0.2 facility lowering and pass through v0.2 sources unchanged."""
    del commodities, milestone_years
    if _uses_legacy_facility_lowering(source):
        raise VedaLangError(
            "Legacy facility/template/provider lowering has been removed. "
            "Author facilities, fleets, opportunities, networks, and runs with the "
            "v0.2 object model instead."
        )
    return deepcopy(source), {"entities": [], "template_map": {}, "model_years": []}


def build_facility_variant_metadata(
    facility_context: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return no legacy facility metadata for the v0.2-only runtime."""
    del facility_context
    return {}


def generate_facility_artifacts(
    facility_context: dict[str, Any],
    variants: dict[str, Any],
    process_symbol_map: dict[tuple[str, str, str | None], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Legacy facility-generated TFM/constraint artifacts are no longer emitted."""
    del facility_context, variants, process_symbol_map
    return [], []
