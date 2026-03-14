"""Smoke tests for the reusable solver-backed pipeline harness."""

import os
from pathlib import Path

import pytest

from tests.helpers.solver_harness import (
    SMOKE_FIXTURE,
    SOLVER_ARTIFACTS_ENV,
    detect_solver_prerequisites,
    run_solver_pipeline_fixture,
)

pytestmark = [pytest.mark.solver, pytest.mark.solver_full]


@pytest.mark.solver_fast
def test_solver_harness_discovers_pipeline_artifacts(tmp_path: Path) -> None:
    """Harness returns stable paths to key solver artifacts after a full run."""
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    run = run_solver_pipeline_fixture(
        SMOKE_FIXTURE,
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
        solver="CPLEX",
        work_dir=tmp_path / "solver_harness_smoke",
    )

    assert run.pipeline_result.success is True
    assert run.work_dir.exists()
    assert run.times_work_dir is not None and run.times_work_dir.exists()

    assert run.primary_gdx is not None and run.primary_gdx.exists()
    assert run.gdx_files

    assert run.diagnostics_file is not None and run.diagnostics_file.exists()
    assert run.diagnostics is not None
    assert run.diagnostics["execution"]["ran_solver"] is True
    assert run.diagnostics["summary"]["ok"] is True
    assert "work_dir=" in run.debug_artifact_hint

    if os.environ.get(SOLVER_ARTIFACTS_ENV):
        assert run.artifact_bundle_dir is not None
        assert run.artifact_bundle_dir.exists()
    else:
        assert run.artifact_bundle_dir is None
