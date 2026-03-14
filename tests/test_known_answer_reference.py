"""Reference smoke test for the known-answer solver harness contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.solver_assertions import assert_activity_near_zero
from tests.helpers.solver_harness import (
    SMOKE_FIXTURE,
    detect_solver_prerequisites,
    run_solver_pipeline_fixture,
)
from tools.veda_dev.times_results import extract_results

pytestmark = [pytest.mark.solver, pytest.mark.solver_full]


@pytest.mark.solver_fast
def test_known_answer_reference_smoke(tmp_path: Path) -> None:
    """Demonstrate harness -> GDX extraction -> semantic assertion flow."""
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        SMOKE_FIXTURE,
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "known_answer_reference",
        case="known_answer_reference",
    )
    assert run.primary_gdx is not None

    extracted = extract_results(run.primary_gdx, include_flows=True, limit=0)
    assert not extracted.errors

    # This fixture currently has no demand; this assertion documents
    # how known-answer tests can express near-zero behavioral expectations.
    assert_activity_near_zero(
        extracted,
        process="nonexistent_reference_process",
        year="2030",
    )
