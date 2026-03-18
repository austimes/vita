"""Core solver-backed known-answer tests (KA01-KA14) with KA05 traceability."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.helpers.solver_assertions import (
    activity_level,
    assert_activity_at_least,
    assert_activity_near_zero,
    assert_flow_activity_ratio_for_commodity_token,
    assert_new_capacity_near_zero,
    assert_process_share_at_least,
    flow_level_for_commodity_token,
    new_capacity_level,
)
from tests.helpers.solver_harness import (
    SolverPipelineArtifacts,
    detect_solver_prerequisites,
    run_solver_pipeline_fixture,
)
from tools.veda_dev.times_results import TimesResults, extract_results

pytestmark = pytest.mark.solver_full

KNOWN_ANSWER_DIR = (
    Path(__file__).parent.parent / "vedalang" / "examples" / "known_answer"
)
KA01 = KNOWN_ANSWER_DIR / "ka01_gas_supply_base.veda.yaml"
KA02 = KNOWN_ANSWER_DIR / "ka02_gas_supply_double.veda.yaml"
KA03 = KNOWN_ANSWER_DIR / "ka03_emissions_factor.veda.yaml"
KA04 = KNOWN_ANSWER_DIR / "ka04_merit_order_dispatch.veda.yaml"
KA06 = KNOWN_ANSWER_DIR / "ka06_stock_sufficient.veda.yaml"
KA07 = KNOWN_ANSWER_DIR / "ka07_demand_spike.veda.yaml"
KA10_OPEN = KNOWN_ANSWER_DIR / "ka10_network_transfer_open.veda.yaml"
KA10_CONSTRAINED = KNOWN_ANSWER_DIR / "ka10_network_transfer_constrained.veda.yaml"
KA08_TIGHT = KNOWN_ANSWER_DIR / "ka08_build_limit_tight.veda.yaml"
KA08_LOOSE = KNOWN_ANSWER_DIR / "ka08_build_limit_loose.veda.yaml"
KA09_TIGHT = KNOWN_ANSWER_DIR / "ka09_zone_opportunity_tight.veda.yaml"
KA09_LOOSE = KNOWN_ANSWER_DIR / "ka09_zone_opportunity_loose.veda.yaml"
KA11 = KNOWN_ANSWER_DIR / "ka11_fleet_distribution_base.veda.yaml"
KA11_STRESS = KNOWN_ANSWER_DIR / "ka11_fleet_distribution_stress.veda.yaml"
KA11_MEASURE_WEIGHTS = {"ka11_pop": {"NTH": 3.0, "STH": 1.0}}
KA12 = KNOWN_ANSWER_DIR / "ka12_temporal_growth_annual.veda.yaml"
KA14 = KNOWN_ANSWER_DIR / "ka14_run_selection_multi_run.veda.yaml"

BASE_ACTIVITY_2020 = 3.1536


def _activity_for_token(results: TimesResults, token: str) -> tuple[str, float]:
    token_upper = token.upper()
    for row in results.var_act:
        process = str(row.get("process", ""))
        if token_upper in process:
            return process, float(row.get("level", 0.0))

    # Zero-activity processes are absent from VAR_ACT. Fall back to PRC_RESID so
    # tests can still assert near-zero behavior against an explicit process.
    for row in results.par_resid:
        process = str(row.get("process", ""))
        if token_upper in process:
            return process, 0.0

    raise AssertionError(f"Expected a process containing '{token_upper}'")


def _gas_supply_activity(results: TimesResults) -> tuple[str, float]:
    return _activity_for_token(results, "GAS_SUPPLY")


def _process_for_token_and_region(
    results: TimesResults,
    token: str,
    region: str,
) -> str:
    token_upper = token.upper()
    region_upper = region.upper()

    for row in results.var_act:
        process = str(row.get("process", ""))
        row_region = str(row.get("region", "")).upper()
        if token_upper in process and row_region == region_upper:
            return process

    # Zero-activity processes are absent from VAR_ACT. Fall back to PRC_RESID so
    # tests can still assert directional behavior against explicit process names.
    for row in results.par_resid:
        process = str(row.get("process", ""))
        row_region = str(row.get("region", "")).upper()
        if token_upper in process and row_region == region_upper:
            return process

    raise AssertionError(
        f"Expected a process containing '{token_upper}' in region '{region_upper}'"
    )


def _token_activity_level(
    results: TimesResults,
    token: str,
    *,
    year: str | None = None,
    region: str | None = None,
) -> float:
    token_upper = token.upper()
    total = 0.0
    for row in results.var_act:
        process = str(row.get("process", ""))
        if token_upper not in process:
            continue
        if year is not None and str(row.get("year", "")) != year:
            continue
        if region is not None and str(row.get("region", "")) != region:
            continue
        total += float(row.get("level", 0.0))
    return total


def _residual_capacity_for_token(
    results: TimesResults,
    token: str,
    *,
    year: str,
    region: str | None = None,
) -> float:
    token_upper = token.upper()
    for row in results.par_resid:
        process = str(row.get("process", ""))
        if token_upper not in process:
            continue
        if str(row.get("year", "")) != year:
            continue
        if region is not None and str(row.get("region", "")) != region:
            continue
        return float(row.get("capacity", 0.0))
    return 0.0


def _tableir_env_act_factor(*, work_dir: Path, process_token: str) -> float:
    return _tableir_attribute_value(
        work_dir=work_dir,
        process_token=process_token,
        attribute="ENV_ACT",
    )


def _tableir_attribute_value(
    *,
    work_dir: Path,
    process_token: str,
    attribute: str,
) -> float:
    tableir_path = work_dir / "model.tableir.yaml"
    tableir = yaml.safe_load(tableir_path.read_text())
    token_upper = process_token.upper()

    for file_entry in tableir.get("files", []):
        for sheet in file_entry.get("sheets", []):
            for table in sheet.get("tables", []):
                for row in table.get("rows", []):
                    process = str(row.get("process", "")).upper()
                    if token_upper not in process:
                        continue
                    if row.get("attribute") != attribute:
                        continue
                    if "value" not in row:
                        continue
                    return float(row.get("value", 0.0))

    raise AssertionError(
        "Expected "
        f"{attribute} row for process token '{process_token}' "
        "in compiled TableIR"
    )


def _artifact_context(run: SolverPipelineArtifacts) -> str:
    return run.debug_artifact_hint


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka01_base_activity_is_stable(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        KA01,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka01",
        case="ka01",
    )

    assert run.primary_gdx is not None
    results = extract_results(run.primary_gdx, limit=0)
    process, level = _gas_supply_activity(results)

    assert_activity_at_least(results, process=process, min_level=3.0, year="2020")
    assert level == pytest.approx(3.1536, rel=1e-5, abs=1e-6)


@pytest.mark.solver
def test_ka02_double_capacity_doubles_supply_activity(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    base_run = run_solver_pipeline_fixture(
        KA01,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka02_base",
        case="ka02base",
    )
    double_run = run_solver_pipeline_fixture(
        KA02,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka02_double",
        case="ka02double",
    )

    assert base_run.primary_gdx is not None
    assert double_run.primary_gdx is not None

    base_results = extract_results(base_run.primary_gdx, limit=0)
    double_results = extract_results(double_run.primary_gdx, limit=0)

    _, base_level = _gas_supply_activity(base_results)
    _, double_level = _gas_supply_activity(double_results)

    assert base_level == pytest.approx(3.1536, rel=1e-5, abs=1e-6)
    assert double_level == pytest.approx(6.3072, rel=1e-5, abs=1e-6)
    assert (double_level / base_level) == pytest.approx(2.0, rel=1e-6, abs=1e-6)


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka03_emissions_fixture_preserves_supply_activity(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        KA03,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka03",
        case="ka03",
    )

    assert run.primary_gdx is not None
    results = extract_results(run.primary_gdx, include_flows=True, limit=0)
    process, level = _gas_supply_activity(results)

    assert_activity_at_least(results, process=process, min_level=3.0, year="2020")
    assert level == pytest.approx(3.1536, rel=1e-5, abs=1e-6)
    assert results.var_flo_source in {"VAR_FLO", "PAR_FLO"}, _artifact_context(run)
    assert_flow_activity_ratio_for_commodity_token(
        results,
        process=process,
        commodity_token="NATURAL_GAS",
        expected_ratio=1.0,
        year="2020",
    )

    expected_factor = 0.056
    env_act_factor = _tableir_env_act_factor(
        work_dir=run.work_dir,
        process_token="GAS_SUPPLY",
    )
    assert env_act_factor == pytest.approx(expected_factor, rel=1e-6, abs=1e-8)
    assert (env_act_factor / expected_factor) == pytest.approx(
        1.0,
        rel=1e-6,
        abs=1e-8,
    )
    solved_fuel_flow = flow_level_for_commodity_token(
        results,
        process=process,
        commodity_token="NATURAL_GAS",
        year="2020",
    )
    implied_emissions = solved_fuel_flow * env_act_factor
    assert implied_emissions == pytest.approx(
        level * expected_factor,
        rel=1e-6,
        abs=1e-8,
    )


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka04_merit_order_prefers_zero_cost_supply(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        KA04,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka04",
        case="ka04",
    )

    assert run.primary_gdx is not None
    results = extract_results(run.primary_gdx, limit=0)

    cheap_process, cheap_level = _activity_for_token(results, "GAS_CHEAP")
    expensive_process, _ = _activity_for_token(results, "GAS_EXP")

    assert_activity_at_least(results, process=cheap_process, min_level=3.0, year="2020")
    assert_activity_near_zero(results, process=expensive_process, year="2020")
    assert_process_share_at_least(
        results,
        process=cheap_process,
        process_pool=[cheap_process, expensive_process],
        min_share=0.99,
        year="2020",
    )
    assert cheap_level == pytest.approx(3.1536, rel=1e-5, abs=1e-6)


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka06_stock_sufficient_keeps_new_capacity_near_zero(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        KA06,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka06",
        case="ka06",
    )

    assert run.primary_gdx is not None
    results = extract_results(run.primary_gdx, limit=0)

    supply_process, supply_level = _activity_for_token(results, "FSUP")
    demand_process, demand_level = _activity_for_token(results, "FDEM")

    assert_activity_at_least(
        results,
        process=supply_process,
        min_level=0.79,
        year="2020",
    )
    assert_activity_at_least(
        results,
        process=demand_process,
        min_level=0.79,
        year="2020",
    )
    assert supply_level == pytest.approx(0.8, rel=1e-6, abs=1e-6)
    assert demand_level == pytest.approx(0.8, rel=1e-6, abs=1e-6)
    assert_new_capacity_near_zero(results, process=supply_process, year="2020")


@pytest.mark.solver
def test_ka07_demand_spike_triggers_positive_new_capacity(
    tmp_path: Path,
) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    base_run = run_solver_pipeline_fixture(
        KA06,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka07_base",
        case="ka07base",
    )
    spike_run = run_solver_pipeline_fixture(
        KA07,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka07_spike",
        case="ka07spike",
    )

    assert base_run.primary_gdx is not None
    assert spike_run.primary_gdx is not None

    base_results = extract_results(base_run.primary_gdx, limit=0)
    spike_results = extract_results(spike_run.primary_gdx, limit=0)

    base_supply_process, base_supply_level = _activity_for_token(base_results, "FSUP")
    spike_supply_process, spike_supply_level = _activity_for_token(
        spike_results,
        "FSUP",
    )
    _, base_demand_level = _activity_for_token(base_results, "FDEM")
    _, spike_demand_level = _activity_for_token(spike_results, "FDEM")

    assert base_supply_process == spike_supply_process
    assert base_supply_level == pytest.approx(0.8, rel=1e-6, abs=1e-6)
    assert base_demand_level == pytest.approx(0.8, rel=1e-6, abs=1e-6)
    assert spike_supply_level == pytest.approx(1.2, rel=1e-6, abs=1e-6)
    assert spike_demand_level == pytest.approx(1.2, rel=1e-6, abs=1e-6)
    assert (spike_supply_level / base_supply_level) == pytest.approx(
        1.5,
        rel=1e-6,
        abs=1e-6,
    )

    base_new_capacity = new_capacity_level(
        base_results,
        process=base_supply_process,
        year="2020",
    )
    spike_new_capacity = new_capacity_level(
        spike_results,
        process=spike_supply_process,
        year="2020",
    )

    assert base_new_capacity == pytest.approx(0.0, abs=1e-6)
    assert spike_new_capacity == pytest.approx(8.0517503805175, rel=1e-6, abs=1e-6)
    assert spike_new_capacity >= 8.0


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka08_build_limit_tight_suppresses_backup_build(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    loose_run = run_solver_pipeline_fixture(
        KA08_LOOSE,
        run_id="r2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka08_loose",
        case="ka08loose",
    )
    tight_run = run_solver_pipeline_fixture(
        KA08_TIGHT,
        run_id="r2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka08_tight",
        case="ka08tight",
    )

    assert loose_run.primary_gdx is not None
    assert tight_run.primary_gdx is not None

    loose_results = extract_results(loose_run.primary_gdx, limit=0)
    tight_results = extract_results(tight_run.primary_gdx, limit=0)

    loose_backup_process, loose_backup_level = _activity_for_token(loose_results, "IFB")
    tight_backup_process, _ = _activity_for_token(tight_results, "IFB")

    assert_activity_at_least(
        loose_results,
        process=loose_backup_process,
        min_level=7.9,
        year="2020",
    )
    assert_activity_near_zero(tight_results, process=tight_backup_process, year="2020")

    loose_new_capacity = new_capacity_level(
        loose_results,
        process=loose_backup_process,
        year="2020",
    )
    tight_new_capacity = new_capacity_level(
        tight_results,
        process=tight_backup_process,
        year="2020",
    )

    assert loose_backup_level == pytest.approx(8.0, rel=1e-6, abs=1e-6)
    assert loose_new_capacity == pytest.approx(153.678335870117, rel=1e-6, abs=1e-6)
    assert loose_new_capacity >= 150.0
    assert tight_new_capacity == pytest.approx(0.0, abs=1e-6)


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka13_constraint_edge_exposes_actionable_solver_diagnostics(
    tmp_path: Path,
) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        KA08_TIGHT,
        run_id="r2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka13_constraint_diag",
        case="ka13diag",
    )

    assert run.primary_gdx is not None, _artifact_context(run)
    assert run.diagnostics is not None, _artifact_context(run)
    assert run.diagnostics_file is not None and run.diagnostics_file.exists(), (
        _artifact_context(run)
    )

    run_times_step = run.pipeline_result.steps.get("run_times")
    assert run_times_step is not None and not run_times_step.skipped, (
        _artifact_context(run)
    )

    diagnostics = run.diagnostics
    summary = diagnostics.get("summary", {})
    execution = diagnostics.get("execution", {})
    model_status = execution.get("model_status", {})
    solve_status = execution.get("solve_status", {})

    assert summary.get("ok") is True, _artifact_context(run)
    assert model_status.get("code") == 1, _artifact_context(run)
    assert solve_status.get("code") == 1, _artifact_context(run)
    assert run_times_step.artifacts.get("gams_command"), _artifact_context(run)
    assert run_times_step.artifacts.get("lst_file"), _artifact_context(run)
    assert run_times_step.artifacts.get("gams_diagnostics_file"), _artifact_context(
        run
    )

    results = extract_results(run.primary_gdx, limit=0)
    backup_process, _ = _activity_for_token(results, "IFB")
    backup_residual = _residual_capacity_for_token(
        results,
        "IFB",
        year="2020",
        region="R1",
    )

    assert backup_residual == pytest.approx(100.0, rel=1e-9, abs=1e-9)
    assert_activity_near_zero(results, process=backup_process, year="2020")


@pytest.mark.solver
def test_ka09_zone_opportunity_shift_changes_active_process_class(
    tmp_path: Path,
) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    loose_run = run_solver_pipeline_fixture(
        KA09_LOOSE,
        run_id="r2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka09_loose",
        case="ka09loose",
    )
    tight_run = run_solver_pipeline_fixture(
        KA09_TIGHT,
        run_id="r2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka09_tight",
        case="ka09tight",
    )

    assert loose_run.primary_gdx is not None
    assert tight_run.primary_gdx is not None

    loose_results = extract_results(loose_run.primary_gdx, limit=0)
    tight_results = extract_results(tight_run.primary_gdx, limit=0)

    loose_zone_level = _token_activity_level(
        loose_results,
        "PRC_ZOP_ZO2_IFB",
        year="2020",
    )
    tight_zone_level = _token_activity_level(
        tight_results,
        "PRC_ZOP_ZO2_IFB",
        year="2020",
    )
    loose_role_level = _token_activity_level(
        loose_results,
        "PRC_FAC_FS_IFB",
        year="2020",
    )
    tight_role_level = _token_activity_level(
        tight_results,
        "PRC_FAC_FS_IFB",
        year="2020",
    )

    assert loose_zone_level == pytest.approx(8.0, rel=1e-6, abs=1e-6)
    assert tight_zone_level == pytest.approx(0.0, abs=1e-6)
    assert loose_role_level == pytest.approx(0.0, abs=1e-6)
    assert tight_role_level == pytest.approx(8.0, rel=1e-6, abs=1e-6)


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka10_network_transfer_flip_shifts_active_region(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    open_run = run_solver_pipeline_fixture(
        KA10_OPEN,
        run_id="ab_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka10_open",
        case="ka10open",
    )
    constrained_run = run_solver_pipeline_fixture(
        KA10_CONSTRAINED,
        run_id="ab_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka10_constrained",
        case="ka10cap",
    )

    assert open_run.primary_gdx is not None
    assert constrained_run.primary_gdx is not None

    open_results = extract_results(open_run.primary_gdx, limit=0)
    constrained_results = extract_results(constrained_run.primary_gdx, limit=0)

    open_a_process = _process_for_token_and_region(open_results, "PRC_FAC_A_G_GA", "A")
    open_b_process = _process_for_token_and_region(open_results, "PRC_FAC_B_G_GB", "B")
    constrained_a_process = _process_for_token_and_region(
        constrained_results,
        "PRC_FAC_A_G_GA",
        "A",
    )
    constrained_b_process = _process_for_token_and_region(
        constrained_results,
        "PRC_FAC_B_G_GB",
        "B",
    )

    assert_activity_near_zero(
        open_results,
        process=open_a_process,
        year="2020",
        region="A",
    )
    assert_activity_at_least(
        open_results,
        process=open_b_process,
        min_level=6.0,
        year="2020",
        region="B",
    )
    assert_activity_at_least(
        constrained_results,
        process=constrained_a_process,
        min_level=6.0,
        year="2020",
        region="A",
    )
    assert_activity_near_zero(
        constrained_results,
        process=constrained_b_process,
        year="2020",
        region="B",
    )

    open_transfer_capacity = _residual_capacity_for_token(
        open_results,
        "TU_NATURAL_GAS_B_A",
        year="2020",
        region="B",
    )
    constrained_transfer_capacity = _residual_capacity_for_token(
        constrained_results,
        "TU_NATURAL_GAS_A_B",
        year="2020",
        region="A",
    )

    assert open_transfer_capacity == pytest.approx(400.0, rel=1e-9, abs=1e-9)
    assert constrained_transfer_capacity == pytest.approx(400.0, rel=1e-9, abs=1e-9)


@pytest.mark.solver
def test_ka11_fleet_distribution_respects_weighted_allocation(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    base_run = run_solver_pipeline_fixture(
        KA11,
        run_id="ka11_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka11_base",
        case="ka11base",
        measure_weights=KA11_MEASURE_WEIGHTS,
    )
    stress_run = run_solver_pipeline_fixture(
        KA11_STRESS,
        run_id="ka11_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka11_stress",
        case="ka11stress",
        measure_weights=KA11_MEASURE_WEIGHTS,
    )

    assert base_run.primary_gdx is not None
    assert stress_run.primary_gdx is not None

    base_results = extract_results(base_run.primary_gdx, limit=0)
    stress_results = extract_results(stress_run.primary_gdx, limit=0)

    north_base_process = _process_for_token_and_region(base_results, "GAS_FLT", "NTH")
    south_base_process = _process_for_token_and_region(base_results, "GAS_FLT", "STH")
    north_stress_process = _process_for_token_and_region(
        stress_results,
        "GAS_FLT",
        "NTH",
    )
    south_stress_process = _process_for_token_and_region(
        stress_results,
        "GAS_FLT",
        "STH",
    )

    north_base_level = activity_level(
        base_results,
        process=north_base_process,
        year="2020",
        region="NTH",
    )
    south_base_level = activity_level(
        base_results,
        process=south_base_process,
        year="2020",
        region="STH",
    )
    north_stress_level = activity_level(
        stress_results,
        process=north_stress_process,
        year="2020",
        region="NTH",
    )
    south_stress_level = activity_level(
        stress_results,
        process=south_stress_process,
        year="2020",
        region="STH",
    )

    assert_activity_at_least(
        base_results,
        process=north_base_process,
        min_level=2.0,
        year="2020",
        region="NTH",
    )
    assert_activity_at_least(
        base_results,
        process=south_base_process,
        min_level=0.6,
        year="2020",
        region="STH",
    )
    assert_activity_at_least(
        stress_results,
        process=north_stress_process,
        min_level=4.0,
        year="2020",
        region="NTH",
    )
    assert_activity_at_least(
        stress_results,
        process=south_stress_process,
        min_level=1.2,
        year="2020",
        region="STH",
    )

    assert south_base_level > 0.0
    assert south_stress_level > 0.0
    assert (north_base_level / south_base_level) == pytest.approx(
        3.0,
        rel=2e-2,
        abs=1e-2,
    )
    assert (north_stress_level / south_stress_level) == pytest.approx(
        3.0,
        rel=2e-2,
        abs=1e-2,
    )

    assert north_base_level / (north_base_level + south_base_level) >= 0.74
    assert north_stress_level / (north_stress_level + south_stress_level) >= 0.74

    assert north_stress_level > north_base_level * 1.9
    assert south_stress_level > south_base_level * 1.9


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka12_temporal_growth_scales_supply_activity(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        KA12,
        run_id="reg1_2030",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka12",
        case="ka12",
    )

    assert run.primary_gdx is not None
    results = extract_results(run.primary_gdx, limit=0)
    process, level = _gas_supply_activity(results)

    growth_ratio = 1.1**10
    assert_activity_at_least(results, process=process, min_level=8.0, year="2030")
    assert level == pytest.approx(8.17962622217, rel=1e-6, abs=1e-6)
    assert (level / BASE_ACTIVITY_2020) == pytest.approx(
        growth_ratio,
        rel=1e-6,
        abs=1e-6,
    )


@pytest.mark.solver
@pytest.mark.solver_fast
def test_ka14_run_selection_changes_solved_activity(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run_2020 = run_solver_pipeline_fixture(
        KA14,
        run_id="reg1_2020",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka14_2020",
        case="ka14_2020",
    )
    run_2030 = run_solver_pipeline_fixture(
        KA14,
        run_id="reg1_2030",
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "ka14_2030",
        case="ka14_2030",
    )

    assert run_2020.primary_gdx is not None
    assert run_2030.primary_gdx is not None

    results_2020 = extract_results(run_2020.primary_gdx, limit=0)
    results_2030 = extract_results(run_2030.primary_gdx, limit=0)
    process_2020, level_2020 = _gas_supply_activity(results_2020)
    process_2030, level_2030 = _gas_supply_activity(results_2030)

    assert_activity_at_least(
        results_2020,
        process=process_2020,
        min_level=3.0,
        year="2020",
    )
    assert_activity_at_least(
        results_2030,
        process=process_2030,
        min_level=6.0,
        year="2030",
    )
    assert level_2020 == pytest.approx(BASE_ACTIVITY_2020, rel=1e-5, abs=1e-6)
    assert level_2030 == pytest.approx(6.3072, rel=1e-5, abs=1e-6)
    assert (level_2030 / level_2020) == pytest.approx(2.0, rel=1e-6, abs=1e-6)
