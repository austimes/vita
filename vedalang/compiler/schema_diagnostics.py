"""Helpers for deterministic diagnostics derived from schema validation errors."""

from __future__ import annotations

from typing import Any

from jsonschema import ValidationError

from .source_maps import format_location_path

_DESCRIPTION_REQUIRED_FAMILIES: dict[str, str] = {
    "technologies": "technology",
    "technology_roles": "technology_role",
    "facilities": "facility",
    "fleets": "fleet",
    "zone_opportunities": "zone_opportunity",
}


def required_description_diagnostic(
    error: ValidationError,
) -> dict[str, Any] | None:
    """Return a deterministic diagnostic for missing required authored descriptions."""
    if error.validator != "required":
        return None

    required_fields = error.validator_value
    if not isinstance(required_fields, list) or "description" not in required_fields:
        return None

    path_tokens = list(error.absolute_path)
    if not path_tokens:
        return None
    top_level = path_tokens[0]
    if not isinstance(top_level, str):
        return None

    object_kind = _DESCRIPTION_REQUIRED_FAMILIES.get(top_level)
    if object_kind is None:
        return None

    object_id = "<unknown>"
    if isinstance(error.instance, dict):
        raw_id = error.instance.get("id")
        if raw_id is not None and str(raw_id).strip():
            object_id = str(raw_id)

    return {
        "code": "E020",
        "severity": "error",
        "message": (
            f"{object_kind} requires an authored `description` for RES explorer output"
        ),
        "object_id": object_id,
        "location": format_location_path(path_tokens),
        "suggestion": "Add a non-empty `description` field.",
    }
