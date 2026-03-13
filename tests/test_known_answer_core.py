"""Core solver-backed known-answer tests (KA01-KA04)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.solver_assertions import (
    assert_activity_at_least,
    assert_activity_near_zero,
    assert_process_share_at_least,
)
from tests.helpers.solver_harness import (
    detect_solver_prerequisites,
    run_solver_pipeline_fixture,
)
from tools.veda_dev.times_results import TimesResults, extract_results

KNOWN_ANSWER_DIR = (
    Path(__file__).parent.parent / "vedalang" / "examples" / "known_answer"
)
KA01 = KNOWN_ANSWER_DIR / "ka01_gas_supply_base.veda.yaml"
KA02 = KNOWN_ANSWER_DIR / "ka02_gas_supply_double.veda.yaml"
KA03 = KNOWN_ANSWER_DIR / "ka03_emissions_factor.veda.yaml"
KA04 = KNOWN_ANSWER_DIR / "ka04_merit_order_dispatch.veda.yaml"


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


@pytest.mark.solver
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
    results = extract_results(run.primary_gdx, limit=0)
    process, level = _gas_supply_activity(results)

    assert_activity_at_least(results, process=process, min_level=3.0, year="2020")
    assert level == pytest.approx(3.1536, rel=1e-5, abs=1e-6)


@pytest.mark.solver
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
