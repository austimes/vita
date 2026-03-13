"""Core solver-backed known-answer tests (KA01/KA02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.solver_assertions import assert_activity_at_least
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


def _gas_supply_activity(results: TimesResults) -> tuple[str, float]:
    for row in results.var_act:
        process = str(row.get("process", ""))
        if "GAS_SUPPLY" in process:
            return process, float(row.get("level", 0.0))
    raise AssertionError("Expected a GAS_SUPPLY process in VAR_ACT output")


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
