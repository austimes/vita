"""Tests for vita.experiment_runner orchestration logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from vita.experiment_runner import (
    _build_run_matrix,
    _run_already_complete,
    plan_experiment,
    run_experiment,
)
from vita.experiment_state import load_experiment_state
from vita.run_artifacts import RunManifest, write_run_manifest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_MODEL = """\
vedalang: "0.5"
id: test_model
title: Test Model
regions: [REG1]
time_horizon: {start: 2020, periods: [{years: 2020}]}
commodities: []
technology_roles: []
"""

_MINIMAL_MANIFEST = {
    "schema_version": 1,
    "id": "test_exp",
    "title": "Test Experiment",
    "question": "Does it work?",
    "baseline": {
        "id": "baseline",
        "model": "model.veda.yaml",
        "run": "base_run",
    },
    "variants": [
        {
            "id": "variant_a",
            "model": "model.veda.yaml",
            "run": "variant_run",
        },
    ],
    "comparisons": [
        {
            "id": "baseline_vs_variant_a",
            "baseline": "baseline",
            "variant": "variant_a",
        },
    ],
    "analyses": [],
}


@pytest.fixture()
def manifest_dir(tmp_path: Path) -> Path:
    """Create a tmp directory with a manifest and model file."""
    model_path = tmp_path / "model.veda.yaml"
    model_path.write_text(_MINIMAL_MODEL)

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.dump(_MINIMAL_MANIFEST))

    return tmp_path


def _write_fake_run(run_dir: Path, *, case_id: str, success: bool = True) -> None:
    """Populate a run directory with a fake manifest and results."""
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = RunManifest(
        run_id=case_id,
        source="model.veda.yaml",
        case="scenario",
        timestamp="2026-01-01T00:00:00Z",
        solver_status="optimal" if success else "failed",
        objective=100.0 if success else None,
        pipeline_success=success,
    )
    write_run_manifest(manifest, run_dir / "manifest.json")

    results = {
        "objective": 100.0,
        "objective_breakdown": {"inv": 50.0, "fix": 30.0, "var": 20.0},
        "var_act": [],
        "var_ncap": [],
        "var_cap": [],
        "var_flo": [],
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")


# ---------------------------------------------------------------------------
# plan_experiment tests
# ---------------------------------------------------------------------------


class TestPlanExperiment:
    def test_creates_directory_structure(self, manifest_dir: Path, tmp_path: Path):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)

        exp_dir = out_dir / "test_exp"
        assert exp_dir.exists()
        assert (exp_dir / "manifest.yaml").exists()
        assert (exp_dir / "state.json").exists()
        assert (exp_dir / "inputs" / "models").is_dir()
        assert (exp_dir / "runs" / "baseline").is_dir()
        assert (exp_dir / "runs" / "variant_a").is_dir()
        assert (exp_dir / "diffs" / "baseline_vs_variant_a").is_dir()
        assert (exp_dir / "analyses").is_dir()

    def test_state_is_planned(self, manifest_dir: Path, tmp_path: Path):
        out_dir = tmp_path / "experiments"
        state = plan_experiment(manifest_dir / "manifest.yaml", out_dir)

        assert state.status == "planned"
        assert state.experiment_id == "test_exp"
        assert state.progress.runs_total == 2
        assert state.progress.diffs_total == 1
        assert state.run_statuses == {
            "baseline": "pending",
            "variant_a": "pending",
        }

    def test_copies_manifest_immutably(self, manifest_dir: Path, tmp_path: Path):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)

        original = (manifest_dir / "manifest.yaml").read_text()
        copied = (out_dir / "test_exp" / "manifest.yaml").read_text()
        assert original == copied

    def test_snapshots_model_files(self, manifest_dir: Path, tmp_path: Path):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)

        models_dir = out_dir / "test_exp" / "inputs" / "models"
        assert (models_dir / "model.veda.yaml").exists()

    def test_state_persisted_to_disk(self, manifest_dir: Path, tmp_path: Path):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)

        loaded = load_experiment_state(out_dir / "test_exp")
        assert loaded.status == "planned"
        assert loaded.experiment_id == "test_exp"


# ---------------------------------------------------------------------------
# resume logic tests
# ---------------------------------------------------------------------------


class TestResumeLogic:
    def test_run_already_complete_true(self, tmp_path: Path):
        run_dir = tmp_path / "runs" / "test"
        _write_fake_run(run_dir, case_id="test", success=True)
        assert _run_already_complete(run_dir) is True

    def test_run_already_complete_false_when_failed(self, tmp_path: Path):
        run_dir = tmp_path / "runs" / "test"
        _write_fake_run(run_dir, case_id="test", success=False)
        assert _run_already_complete(run_dir) is False

    def test_run_already_complete_false_when_missing(self, tmp_path: Path):
        run_dir = tmp_path / "runs" / "test"
        assert _run_already_complete(run_dir) is False

    @patch("vita.experiment_runner._run_single_case")
    @patch("vita.experiment_runner._run_single_diff")
    def test_resume_skips_complete_runs(
        self,
        mock_diff: MagicMock,
        mock_run: MagicMock,
        manifest_dir: Path,
        tmp_path: Path,
    ):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)
        exp_dir = out_dir / "test_exp"

        # Pre-populate baseline as complete
        _write_fake_run(exp_dir / "runs" / "baseline", case_id="baseline")

        # Mock variant run
        mock_run.return_value = {}
        # Also pre-populate variant so diff can proceed
        def run_side_effect(case, run_dir, *, no_sankey):
            _write_fake_run(run_dir, case_id=case.id)
            return {}

        mock_run.side_effect = run_side_effect
        mock_diff.return_value = {
            "objective": {
                "baseline": 100,
                "variant": 100,
                "delta": 0,
                "pct_delta": 0.0,
            },
        }

        run_experiment(exp_dir, resume=True)

        # Only variant should have been run (baseline skipped)
        assert mock_run.call_count == 1
        called_case = mock_run.call_args[0][0]
        assert called_case.id == "variant_a"

    @patch("vita.experiment_runner._run_single_case")
    def test_resume_skips_complete_diffs(
        self,
        mock_run: MagicMock,
        manifest_dir: Path,
        tmp_path: Path,
    ):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)
        exp_dir = out_dir / "test_exp"

        # Pre-populate both runs and diff
        _write_fake_run(exp_dir / "runs" / "baseline", case_id="baseline")
        _write_fake_run(exp_dir / "runs" / "variant_a", case_id="variant_a")

        diff_dir = exp_dir / "diffs" / "baseline_vs_variant_a"
        diff_dir.mkdir(parents=True, exist_ok=True)
        (diff_dir / "diff.json").write_text('{"objective": {}}')

        with patch("vita.experiment_runner._run_single_diff") as mock_diff:
            run_experiment(exp_dir, resume=True)
            mock_diff.assert_not_called()


# ---------------------------------------------------------------------------
# run_experiment integration (mocked pipeline)
# ---------------------------------------------------------------------------


class TestRunExperiment:
    @patch("vita.experiment_runner._run_single_case")
    @patch("vita.experiment_runner._run_single_diff")
    def test_full_run(
        self,
        mock_diff: MagicMock,
        mock_run: MagicMock,
        manifest_dir: Path,
        tmp_path: Path,
    ):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)
        exp_dir = out_dir / "test_exp"

        def run_side_effect(case, run_dir, *, no_sankey):
            _write_fake_run(run_dir, case_id=case.id)
            return {}

        mock_run.side_effect = run_side_effect
        mock_diff.return_value = {
            "objective": {
                "baseline": 100.0,
                "variant": 110.0,
                "delta": 10.0,
                "pct_delta": 10.0,
            },
        }

        result = run_experiment(exp_dir)

        assert result.success is True
        assert result.errors == []
        assert mock_run.call_count == 2
        assert mock_diff.call_count == 1

        # State should be complete
        state = load_experiment_state(exp_dir)
        assert state.status == "complete"
        assert state.progress.runs_complete == 2
        assert state.progress.diffs_complete == 1

        # run_matrix.json written
        matrix_path = exp_dir / "analyses" / "run_matrix.json"
        assert matrix_path.exists()
        matrix = json.loads(matrix_path.read_text())
        assert len(matrix["cases"]) == 2
        assert len(matrix["comparisons"]) == 1

    @patch("vita.experiment_runner._run_single_case")
    def test_run_failure_continues(
        self,
        mock_run: MagicMock,
        manifest_dir: Path,
        tmp_path: Path,
    ):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)
        exp_dir = out_dir / "test_exp"

        call_count = 0

        def run_side_effect(case, run_dir, *, no_sankey):
            nonlocal call_count
            call_count += 1
            if case.id == "baseline":
                raise RuntimeError("solver exploded")
            _write_fake_run(run_dir, case_id=case.id)
            return {}

        mock_run.side_effect = run_side_effect

        result = run_experiment(exp_dir)

        # Both runs attempted despite baseline failure
        assert call_count == 2
        assert result.success is False
        assert any("baseline" in e for e in result.errors)

        state = load_experiment_state(exp_dir)
        assert state.run_statuses["baseline"] == "failed"
        assert state.run_statuses["variant_a"] == "complete"

    @patch("vita.experiment_runner._run_single_case")
    def test_force_cleans_before_rerun(
        self,
        mock_run: MagicMock,
        manifest_dir: Path,
        tmp_path: Path,
    ):
        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)
        exp_dir = out_dir / "test_exp"

        # Pre-populate baseline
        _write_fake_run(exp_dir / "runs" / "baseline", case_id="baseline")

        def run_side_effect(case, run_dir, *, no_sankey):
            _write_fake_run(run_dir, case_id=case.id)
            return {}

        mock_run.side_effect = run_side_effect

        run_experiment(exp_dir, force=True)

        # Both runs should have been executed (force ignores existing)
        assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# run_matrix tests
# ---------------------------------------------------------------------------


class TestBuildRunMatrix:
    def test_build_run_matrix(self, manifest_dir: Path, tmp_path: Path):
        from vita.experiment_manifest import load_experiment_manifest

        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)
        exp_dir = out_dir / "test_exp"

        # Populate runs
        _write_fake_run(exp_dir / "runs" / "baseline", case_id="baseline")
        _write_fake_run(exp_dir / "runs" / "variant_a", case_id="variant_a")

        # Write a diff
        diff_dir = exp_dir / "diffs" / "baseline_vs_variant_a"
        diff_dir.mkdir(parents=True, exist_ok=True)
        (diff_dir / "diff.json").write_text(
            json.dumps(
                {
                    "objective": {
                        "baseline": 100.0,
                        "variant": 110.0,
                        "delta": 10.0,
                        "pct_delta": 10.0,
                    },
                }
            )
        )

        manifest = load_experiment_manifest(exp_dir / "manifest.yaml")
        matrix = _build_run_matrix(manifest, exp_dir)

        assert len(matrix["cases"]) == 2
        baseline_entry = matrix["cases"][0]
        assert baseline_entry["id"] == "baseline"
        assert baseline_entry["objective"] == 100.0
        assert baseline_entry["solver_status"] == "optimal"
        assert baseline_entry["pipeline_success"] is True

        assert len(matrix["comparisons"]) == 1
        comp_entry = matrix["comparisons"][0]
        assert comp_entry["id"] == "baseline_vs_variant_a"
        assert comp_entry["baseline_objective"] == 100.0
        assert comp_entry["delta_objective"] == 10.0

    def test_build_run_matrix_missing_runs(self, manifest_dir: Path, tmp_path: Path):
        from vita.experiment_manifest import load_experiment_manifest

        out_dir = tmp_path / "experiments"
        plan_experiment(manifest_dir / "manifest.yaml", out_dir)
        exp_dir = out_dir / "test_exp"

        manifest = load_experiment_manifest(exp_dir / "manifest.yaml")
        matrix = _build_run_matrix(manifest, exp_dir)

        # Should gracefully handle missing runs
        assert len(matrix["cases"]) == 2
        assert matrix["cases"][0]["objective"] is None
        assert matrix["cases"][0]["pipeline_success"] is None
