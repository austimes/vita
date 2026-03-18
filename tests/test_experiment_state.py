"""Tests for vita/experiment_state.py — experiment lifecycle state management."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vita.experiment_state import (
    STATE_FILENAME,
    ExperimentStateError,
    check_completion,
    create_experiment_state,
    load_experiment_state,
    mark_diff_complete,
    mark_narrated,
    mark_run_complete,
    mark_run_failed,
    mark_run_started,
    save_experiment_state,
)

FIXED_TIME = datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC)
FIXED_TIME_2 = datetime(2026, 3, 18, 13, 0, 0, tzinfo=UTC)
FIXED_TIME_3 = datetime(2026, 3, 18, 14, 0, 0, tzinfo=UTC)
FIXED_TIME_4 = datetime(2026, 3, 18, 15, 0, 0, tzinfo=UTC)


def _clock(dt: datetime):
    return lambda: dt


class TestCreateExperimentState:
    def test_creates_initial_state(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="test_exp",
            manifest_file="manifest.yaml",
            run_ids=["baseline", "variant_a"],
            comparison_ids=["baseline_vs_variant_a"],
            now_utc=_clock(FIXED_TIME),
        )
        assert state.schema_version == "vita-experiment-state/v1"
        assert state.experiment_id == "test_exp"
        assert state.manifest_file == "manifest.yaml"
        assert state.status == "planned"
        assert state.created_at == "2026-03-18T12:00:00Z"
        assert state.updated_at == "2026-03-18T12:00:00Z"
        assert state.completed_at is None
        assert state.narrated_at is None
        assert state.progress.runs_total == 2
        assert state.progress.runs_complete == 0
        assert state.progress.runs_failed == 0
        assert state.progress.diffs_total == 1
        assert state.progress.diffs_complete == 0
        assert state.run_statuses == {"baseline": "pending", "variant_a": "pending"}
        assert state.diff_statuses == {"baseline_vs_variant_a": "pending"}
        assert state.artifacts["summary_json"] is None
        assert state.artifacts["report_html"] is None

    def test_writes_state_file(self, tmp_path: Path) -> None:
        create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="test_exp",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        state_path = tmp_path / STATE_FILENAME
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert data["status"] == "planned"
        assert data["schema_version"] == "vita-experiment-state/v1"


class TestSerializationRoundTrip:
    def test_round_trip(self, tmp_path: Path) -> None:
        original = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="round_trip",
            manifest_file="manifest.yaml",
            run_ids=["baseline", "co2_cap"],
            comparison_ids=["baseline_vs_co2_cap"],
            now_utc=_clock(FIXED_TIME),
        )
        loaded = load_experiment_state(tmp_path)
        assert loaded.to_dict() == original.to_dict()

    def test_save_and_reload(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="save_reload",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        save_experiment_state(state, tmp_path)
        reloaded = load_experiment_state(tmp_path)
        assert reloaded.status == "running"
        assert reloaded.run_statuses["baseline"] == "running"


class TestLifecycleTransitions:
    def test_full_lifecycle(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="lifecycle",
            manifest_file="manifest.yaml",
            run_ids=["baseline", "variant"],
            comparison_ids=["baseline_vs_variant"],
            now_utc=_clock(FIXED_TIME),
        )
        assert state.status == "planned"

        # planned → running
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        assert state.status == "running"

        mark_run_started(state, "variant", now_utc=_clock(FIXED_TIME_2))
        assert state.status == "running"

        # complete runs
        mark_run_complete(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        assert state.status == "running"
        assert state.progress.runs_complete == 1

        mark_run_complete(state, "variant", now_utc=_clock(FIXED_TIME_2))
        assert state.status == "running"  # diff still pending
        assert state.progress.runs_complete == 2

        # complete diff → auto-transition to complete
        mark_diff_complete(state, "baseline_vs_variant", now_utc=_clock(FIXED_TIME_3))
        assert state.status == "complete"
        assert state.completed_at == "2026-03-18T14:00:00Z"

        # complete → narrated
        state.artifacts["summary_json"] = "conclusions/summary.json"
        state.artifacts["report_html"] = "report/index.html"
        mark_narrated(state, now_utc=_clock(FIXED_TIME_3))
        assert state.status == "narrated"
        assert state.narrated_at == "2026-03-18T14:00:00Z"

    def test_no_diffs_auto_completes(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="no_diffs",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        mark_run_complete(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        assert state.status == "complete"


class TestInvalidTransitions:
    def test_cannot_narrate_from_planned(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="bad",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        state.artifacts["summary_json"] = "x"
        state.artifacts["report_html"] = "y"
        with pytest.raises(ExperimentStateError, match="Invalid transition"):
            mark_narrated(state)

    def test_cannot_narrate_from_running(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="bad",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        state.artifacts["summary_json"] = "x"
        state.artifacts["report_html"] = "y"
        with pytest.raises(ExperimentStateError, match="Invalid transition"):
            mark_narrated(state)

    def test_unknown_run_id_raises(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="bad",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        with pytest.raises(ExperimentStateError, match="Unknown run_id"):
            mark_run_started(state, "nonexistent")

    def test_unknown_diff_id_raises(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="bad",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        with pytest.raises(ExperimentStateError, match="Unknown diff_id"):
            mark_diff_complete(state, "nonexistent")


class TestCannotNarrateWithoutArtifacts:
    def test_missing_summary_json(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="no_artifacts",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        mark_run_complete(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        with pytest.raises(ExperimentStateError, match="summary_json"):
            mark_narrated(state)

    def test_missing_report_html(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="no_report",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        mark_run_complete(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        state.artifacts["summary_json"] = "conclusions/summary.json"
        with pytest.raises(ExperimentStateError, match="report_html"):
            mark_narrated(state)


class TestRunFailed:
    def test_failed_run_counts(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="fail",
            manifest_file="manifest.yaml",
            run_ids=["baseline", "variant"],
            comparison_ids=["baseline_vs_variant"],
            now_utc=_clock(FIXED_TIME),
        )
        mark_run_started(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        mark_run_started(state, "variant", now_utc=_clock(FIXED_TIME_2))
        mark_run_complete(state, "baseline", now_utc=_clock(FIXED_TIME_2))
        mark_run_failed(state, "variant", now_utc=_clock(FIXED_TIME_2))
        assert state.progress.runs_complete == 1
        assert state.progress.runs_failed == 1
        assert state.run_statuses["variant"] == "failed"


class TestCheckCompletion:
    def test_does_not_transition_if_not_running(self, tmp_path: Path) -> None:
        state = create_experiment_state(
            experiment_dir=tmp_path,
            experiment_id="noop",
            manifest_file="manifest.yaml",
            run_ids=["baseline"],
            comparison_ids=[],
            now_utc=_clock(FIXED_TIME),
        )
        result = check_completion(state)
        assert result.status == "planned"
