"""Deterministic lint category runners."""

from __future__ import annotations

from vedalang.compiler.compiler import (
    collect_new_syntax_structural_diagnostics,
    validate_cross_references,
)
from vedalang.heuristics.linter import run_heuristics
from vedalang.identity.lint_rules import lint_naming_conventions
from vedalang.lint.diagnostics import with_meta


def _category_for_structural_code(code: str) -> str:
    if (
        code.startswith("E_UNIT_")
        or code.startswith("W_UNIT_")
        or code.startswith("E_BASIS_")
        or code.startswith("W_BASIS_")
        or code in {"E_PROCESS_UNITS", "W_PROCESS_UNITS", "E_UNIT_TRANSFORM_PROCESS"}
        or code.startswith("E_ENERGY_MASS_BASIS_")
        or code.startswith("W_ENERGY_MASS_BASIS_")
    ):
        return "units"
    if "EMISSION" in code or code == "W_NEGATIVE_EMISSION_DOC":
        return "emissions"
    return "structure"


def run_core(source: dict) -> list[dict]:
    """Run cross-reference checks for the core category."""
    diagnostics: list[dict] = []
    model = source.get("model", source)
    xref_errors, xref_warnings = validate_cross_references(model, source=source)
    for msg in xref_errors:
        diagnostics.append(
            with_meta(
                {
                    "code": "XREF_ERROR",
                    "severity": "error",
                    "message": msg,
                },
                category="core",
                engine="code",
                check_id="code.core.schema_xref",
            )
        )
    for msg in xref_warnings:
        diagnostics.append(
            with_meta(
                {
                    "code": "XREF_WARNING",
                    "severity": "warning",
                    "message": msg,
                },
                category="core",
                engine="code",
                check_id="code.core.schema_xref",
            )
        )
    return diagnostics


def run_identity(source: dict) -> list[dict]:
    """Run naming/identity checks."""
    diagnostics: list[dict] = []
    for diag in lint_naming_conventions(source):
        data = diag.to_dict()
        # Keep identity checks advisory for existing examples.
        if data.get("severity") == "error":
            data["severity"] = "warning"
        diagnostics.append(
            with_meta(
                data,
                category="identity",
                engine="code",
                check_id="code.identity.naming",
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
    }
    semantic_errors, semantic_warnings = (
        collect_new_syntax_structural_diagnostics(source)
    )
    for d in semantic_errors:
        category = _category_for_structural_code(d["code"])
        grouped.setdefault(category, []).append(
            with_meta(
                {
                    "code": d["code"],
                    "severity": "error",
                    "message": d["message"],
                    "location": d["location"],
                },
                category=category,
                engine="code",
                check_id=f"code.{category}.compiler_semantics",
            )
        )
    for d in semantic_warnings:
        category = _category_for_structural_code(d["code"])
        grouped.setdefault(category, []).append(
            with_meta(
                {
                    "code": d["code"],
                    "severity": "warning",
                    "message": d["message"],
                    "location": d["location"],
                },
                category=category,
                engine="code",
                check_id=f"code.{category}.compiler_semantics",
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
