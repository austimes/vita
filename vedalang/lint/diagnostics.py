"""Shared diagnostic helpers for deterministic and LLM lint engines."""

from __future__ import annotations

from typing import Any


def with_meta(
    diag: dict[str, Any],
    *,
    category: str,
    engine: str,
    check_id: str,
) -> dict[str, Any]:
    """Attach lint taxonomy metadata to a diagnostic payload."""
    out = dict(diag)
    out["category"] = category
    out["engine"] = engine
    out["check_id"] = check_id
    if "path" in out and "location" not in out:
        out["location"] = out.pop("path")
    return out


def severity_counts(diagnostics: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Return (errors, warnings, critical)."""
    errors = 0
    warnings = 0
    critical = 0
    for d in diagnostics:
        sev = str(d.get("severity", "warning")).lower().strip()
        if sev == "critical":
            critical += 1
        elif sev == "warning":
            warnings += 1
        elif sev == "error":
            errors += 1
    return errors, warnings, critical


def build_summary(
    diagnostics: list[dict[str, Any]],
    *,
    checks_run: list[str],
    skipped_categories: list[str],
) -> dict[str, Any]:
    """Build normalized lint summary blocks for JSON output."""
    by_category: dict[str, dict[str, int]] = {}
    by_severity: dict[str, int] = {}
    for d in diagnostics:
        category = str(d.get("category") or "uncategorized")
        sev = str(d.get("severity") or "warning").lower().strip()
        cat_entry = by_category.setdefault(
            category,
            {"total": 0, "error": 0, "warning": 0, "critical": 0, "suggestion": 0},
        )
        cat_entry["total"] += 1
        cat_entry[sev] = cat_entry.get(sev, 0) + 1
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "by_category": by_category,
        "by_severity": by_severity,
        "skipped_categories": skipped_categories,
        "checks_run": checks_run,
    }
