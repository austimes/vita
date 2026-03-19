"""Status and acceptance tests for user-constraint lowering gaps."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tools.veda_check import run_check
from vedalang.compiler import compile_vedalang_bundle, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
TOY_SECTORS_DIR = PROJECT_ROOT / "vedalang" / "examples" / "toy_sectors"
TOY_INDUSTRY = TOY_SECTORS_DIR / "toy_industry.veda.yaml"
EMISSIONS_BUDGET_FIXTURES = [
    TOY_SECTORS_DIR / "toy_industry_co2_cap_loose.veda.yaml",
    TOY_SECTORS_DIR / "toy_industry_co2_cap_mid.veda.yaml",
    TOY_SECTORS_DIR / "toy_industry_co2_cap_tight.veda.yaml",
]


def _tables_for_tag(tableir: dict, tag: str) -> list[dict]:
    tables: list[dict] = []
    for file_spec in tableir.get("files", []):
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == tag:
                    tables.append(table)
    return tables


def _compile_fixture(path: Path, run_id: str) -> tuple[dict, object]:
    source = load_vedalang(path)
    bundle = compile_vedalang_bundle(source, validate=True, selected_run=run_id)
    return source, bundle


def _transition_snapshot(
    bundle: object,
) -> list[tuple[str, str, float | None, str | None]]:
    snapshot: list[tuple[str, str, float | None, str | None]] = []
    for transition in bundle.cpir.get("transitions", []):
        from_technology = str(transition.get("from_process", "")).rsplit("::", 1)[-1]
        to_technology = str(transition.get("to_process", "")).rsplit("::", 1)[-1]
        cost = transition.get("cost") or {}
        snapshot.append(
            (
                from_technology,
                to_technology,
                cost.get("amount"),
                cost.get("unit"),
            )
        )
    return sorted(snapshot)


def _retrofit_uc_snapshot(
    bundle: object,
) -> list[
    tuple[
        str,
        str,
        float | None,
        str | None,
        tuple[tuple[str, str, float], ...],
        tuple[int, ...],
    ]
]:
    snapshot: list[
        tuple[
            str,
            str,
            float | None,
            str | None,
            tuple[tuple[str, str, float], ...],
            tuple[int, ...],
        ]
    ] = []
    for user_constraint in bundle.cpir.get("user_constraints", []):
        if user_constraint.get("kind") != "retrofit_transition":
            continue
        cost = user_constraint.get("cost") or {}
        process_terms = tuple(
            sorted(
                (
                    str(row.get("process")),
                    str(row.get("side")),
                    float(row.get("uc_act", 0.0)),
                )
                for row in user_constraint.get("rows", [])
                if row.get("process") is not None
            )
        )
        rhs_years = tuple(
            sorted(
                int(row["year"])
                for row in user_constraint.get("rows", [])
                if row.get("uc_rhsrt") is not None and row.get("year") is not None
            )
        )
        snapshot.append(
            (
                str(user_constraint.get("transition_id")),
                str(user_constraint.get("uc_n")),
                cost.get("amount"),
                cost.get("unit"),
                process_terms,
                rhs_years,
            )
        )
    return sorted(snapshot)


def test_retrofit_transitions_have_known_answer_in_cpir_and_reach_xl2times():
    result = run_check(TOY_INDUSTRY, from_vedalang=True, selected_run="s25_co2_cap")
    assert result.success
    assert result.errors == 0

    _, bundle = _compile_fixture(TOY_INDUSTRY, run_id="s25_co2_cap")

    assert _transition_snapshot(bundle) == [
        ("gas_boil", "e_heat", 15.0, "AUD2024/kW"),
        ("gas_boil", "h2_boil", 25.0, "AUD2024/kW"),
    ]
    assert bundle.cpir["model_years"] == [2025, 2035]
    assert _retrofit_uc_snapshot(bundle) == [
        (
            "T::role_instance.heat_sup_fleet@SINGLE::gas_boil->e_heat",
            "UC_RET_role_instance_heat_sup_fleet_SINGLE_gas_boil_e_heat",
            15.0,
            "AUD2024/kW",
            (
                (
                    "P::role_instance.heat_sup_fleet@SINGLE::e_heat",
                    "OUT",
                    1.0,
                ),
                (
                    "P::role_instance.heat_sup_fleet@SINGLE::gas_boil",
                    "IN",
                    1.0,
                ),
            ),
            (2025, 2035),
        ),
        (
            "T::role_instance.heat_sup_fleet@SINGLE::gas_boil->h2_boil",
            "UC_RET_role_instance_heat_sup_fleet_SINGLE_gas_boil_h2_boil",
            25.0,
            "AUD2024/kW",
            (
                (
                    "P::role_instance.heat_sup_fleet@SINGLE::gas_boil",
                    "IN",
                    1.0,
                ),
                (
                    "P::role_instance.heat_sup_fleet@SINGLE::h2_boil",
                    "OUT",
                    1.0,
                ),
            ),
            (2025, 2035),
        ),
    ]
    uc_tables = _tables_for_tag(bundle.tableir, "~UC_T")
    assert len(uc_tables) == 2
    assert all(
        table.get("uc_sets") == {"R_E": "AllRegions", "T_E": ""}
        for table in uc_tables
    )

    uc_rows = [
        row
        for table in uc_tables
        for row in table.get("rows", [])
    ]
    assert any(row.get("uc_act") == 1.0 for row in uc_rows)
    assert any(row.get("uc_rhsrt") == 0.0 for row in uc_rows)
    assert any("gas_boil" in str(row.get("process", "")) for row in uc_rows)


def test_policy_case_hooks_are_currently_lowering_noops_for_toy_industry():
    source, with_hooks = _compile_fixture(TOY_INDUSTRY, run_id="s25_co2_cap")

    stripped = deepcopy(source)
    for fleet in stripped.get("fleets", []):
        fleet.pop("policies", None)
    for facility in stripped.get("facilities", []):
        facility.pop("policies", None)
    for run in stripped.get("runs", []):
        run.pop("enable_policies", None)
        run.pop("include_cases", None)

    without_hooks = compile_vedalang_bundle(
        stripped,
        validate=True,
        selected_run="s25_co2_cap",
    )

    assert with_hooks.csir == without_hooks.csir

    def _strip_retrofit_ucs(bundle: object) -> dict:
        cpir = deepcopy(bundle.cpir)
        cpir["user_constraints"] = [
            uc
            for uc in cpir.get("user_constraints", [])
            if uc.get("kind") != "retrofit_transition"
        ]
        return cpir

    assert _strip_retrofit_ucs(with_hooks) == _strip_retrofit_ucs(without_hooks)

    def _strip_uc_tables(tableir: dict) -> dict:
        stripped = deepcopy(tableir)
        for file_spec in stripped.get("files", []):
            for sheet in file_spec.get("sheets", []):
                sheet["tables"] = [
                    table
                    for table in sheet.get("tables", [])
                    if table.get("tag") != "~UC_T"
                ]
        return stripped

    assert _strip_uc_tables(with_hooks.tableir) == _strip_uc_tables(
        without_hooks.tableir
    )


@pytest.mark.parametrize("fixture_path", EMISSIONS_BUDGET_FIXTURES)
def test_emissions_budget_examples_run_end_to_end_but_do_not_emit_uc_yet(
    fixture_path: Path,
):
    result = run_check(fixture_path, from_vedalang=True, selected_run="s25_co2_cap")
    assert result.success
    assert result.errors == 0

    _, bundle = _compile_fixture(fixture_path, run_id="s25_co2_cap")
    uc_tables = _tables_for_tag(bundle.tableir, "~UC_T")
    assert len(uc_tables) == 2
    uc_rows = [
        row
        for table in uc_tables
        for row in table.get("rows", [])
    ]
    assert all(row.get("uc_rhs") is None for row in uc_rows)
    assert all(row.get("uc_comprd") is None for row in uc_rows)


@pytest.mark.xfail(
    strict=True,
    reason="Emissions budget constraints are not yet lowered to ~UC_T.",
)
def test_emissions_budget_should_lower_to_user_constraint_tables():
    _, bundle = _compile_fixture(
        TOY_SECTORS_DIR / "toy_industry_co2_cap_mid.veda.yaml",
        run_id="s25_co2_cap",
    )

    uc_tables = _tables_for_tag(bundle.tableir, "~UC_T")
    assert uc_tables
    assert any(
        row.get("uc_rhs") is not None
        for table in uc_tables
        for row in table.get("rows", [])
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Retrofit transitions should eventually include nonzero "
        "UC bounds from transition costs."
    ),
)
def test_retrofit_transitions_should_lower_to_user_constraint_tables():
    _, bundle = _compile_fixture(TOY_INDUSTRY, run_id="s25_co2_cap")

    uc_rows = [
        row
        for table in _tables_for_tag(bundle.tableir, "~UC_T")
        for row in table.get("rows", [])
    ]
    assert uc_rows
    assert any("gas_boil" in str(row.get("process", "")) for row in uc_rows)
    assert any((row.get("uc_rhsrt") or 0) > 0 for row in uc_rows)
