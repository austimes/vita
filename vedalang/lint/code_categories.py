"""Deterministic lint category runners."""

from __future__ import annotations

from vedalang.compiler.diagnostics import (
    category_for_code,
    collect_diagnostics,
)
from vedalang.heuristics.linter import run_heuristics
from vedalang.identity.lint_rules import lint_naming_conventions
from vedalang.lint.diagnostics import with_meta
from vedalang.versioning import looks_like_supported_source


def run_core(source: dict) -> list[dict]:
    """Run cross-reference checks for the core category."""
    del source
    return []


def run_identity(source: dict) -> list[dict]:
    """Run naming/identity checks."""
    diagnostics: list[dict] = []
    for diag in lint_naming_conventions(source):
        diagnostics.append(
            with_meta(
                diag.to_dict(),
                category="identity",
                engine="code",
                check_id="code.identity.naming",
            )
        )
    if looks_like_supported_source(source):
        for diag in collect_diagnostics(source):
            if category_for_code(diag["code"]) != "identity":
                continue
            diagnostics.append(
                with_meta(
                    diag,
                    category="identity",
                    engine="code",
                    check_id="code.identity.prd_section_14",
                )
            )
    return diagnostics


def run_feasibility(source: dict) -> list[dict]:
    """Run heuristic feasibility checks."""
    diagnostics: list[dict] = []
    for issue in run_heuristics(source):
        diagnostics.append(
            with_meta(
                issue.to_dict(),
                category="feasibility",
                engine="code",
                check_id="code.feasibility.heuristics",
            )
        )
    return diagnostics


def collect_structural_by_category(source: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {
        "structure": [],
        "units": [],
        "emissions": [],
        "identity": [],
    }
    if not looks_like_supported_source(source):
        return grouped
    for diag in collect_diagnostics(source):
        category = category_for_code(diag["code"])
        grouped.setdefault(category, []).append(
            with_meta(
                diag,
                category=category,
                engine="code",
                check_id=f"code.{category}.prd_section_14",
            )
        )
    return grouped


def run_structure(
    source: dict,
    *,
    structural_cache: dict[str, list[dict]] | None,
) -> list[dict]:
    if structural_cache is None:
        structural_cache = collect_structural_by_category(source)
    return list(structural_cache.get("structure", []))


def run_units(
    source: dict,
    *,
    structural_cache: dict[str, list[dict]] | None,
) -> list[dict]:
    if structural_cache is None:
        structural_cache = collect_structural_by_category(source)
    return list(structural_cache.get("units", []))


def run_emissions(
    source: dict, *, structural_cache: dict[str, list[dict]] | None
) -> list[dict]:
    if structural_cache is None:
        structural_cache = collect_structural_by_category(source)
    return list(structural_cache.get("emissions", []))


CATEGORY_RUNNERS = {
    "core": run_core,
    "identity": run_identity,
    "structure": run_structure,
    "units": run_units,
    "emissions": run_emissions,
    "feasibility": run_feasibility,
}
