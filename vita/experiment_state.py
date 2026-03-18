"""Lifecycle state management for Vita experiments."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATE_FILENAME = "state.json"

SCHEMA_VERSION = "vita-experiment-state/v1"

VALID_STATUSES = ("planned", "running", "complete", "interpreted", "presented")
VALID_RUN_STATUSES = ("pending", "running", "complete", "failed")
VALID_DIFF_STATUSES = ("pending", "complete", "failed")

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"running"},
    "running": {"complete"},
    "complete": {"interpreted"},
    "interpreted": {"presented"},
    "presented": set(),
}


class ExperimentStateError(ValueError):
    """Raised on invalid state transitions or missing prerequisites."""


@dataclass
class ExperimentProgress:
    runs_total: int
    runs_complete: int
    runs_failed: int
    diffs_total: int
    diffs_complete: int

    def to_dict(self) -> dict[str, int]:
        return {
            "runs_total": self.runs_total,
            "runs_complete": self.runs_complete,
            "runs_failed": self.runs_failed,
            "diffs_total": self.diffs_total,
            "diffs_complete": self.diffs_complete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentProgress:
        return cls(
            runs_total=int(data["runs_total"]),
            runs_complete=int(data["runs_complete"]),
            runs_failed=int(data["runs_failed"]),
            diffs_total=int(data["diffs_total"]),
            diffs_complete=int(data["diffs_complete"]),
        )


@dataclass
class ExperimentState:
    schema_version: str
    experiment_id: str
    manifest_file: str
    status: str
    created_at: str
    updated_at: str
    completed_at: str | None
    interpreted_at: str | None
    presented_at: str | None
    progress: ExperimentProgress
    run_statuses: dict[str, str] = field(default_factory=dict)
    diff_statuses: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "manifest_file": self.manifest_file,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "interpreted_at": self.interpreted_at,
            "presented_at": self.presented_at,
            "progress": self.progress.to_dict(),
            "run_statuses": dict(self.run_statuses),
            "diff_statuses": dict(self.diff_statuses),
            "artifacts": dict(self.artifacts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentState:
        return cls(
            schema_version=data["schema_version"],
            experiment_id=data["experiment_id"],
            manifest_file=data["manifest_file"],
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            completed_at=data.get("completed_at"),
            interpreted_at=data.get("interpreted_at"),
            presented_at=data.get("presented_at"),
            progress=ExperimentProgress.from_dict(data["progress"]),
            run_statuses=dict(data.get("run_statuses", {})),
            diff_statuses=dict(data.get("diff_statuses", {})),
            artifacts=dict(data.get("artifacts", {})),
        )


def _format_timestamp(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_factory(now_utc: Callable[[], datetime] | None) -> Callable[[], datetime]:
    return now_utc or (lambda: datetime.now(UTC))


def _transition(state: ExperimentState, target: str) -> None:
    allowed = _VALID_TRANSITIONS.get(state.status, set())
    if target not in allowed:
        raise ExperimentStateError(
            f"Invalid transition: {state.status!r} → {target!r}"
        )
    state.status = target


def create_experiment_state(
    experiment_dir: Path,
    experiment_id: str,
    manifest_file: str,
    run_ids: list[str],
    comparison_ids: list[str],
    now_utc: Callable[[], datetime] | None = None,
) -> ExperimentState:
    """Create initial state.json with status=planned."""
    ts = _format_timestamp(_now_factory(now_utc)())
    state = ExperimentState(
        schema_version=SCHEMA_VERSION,
        experiment_id=experiment_id,
        manifest_file=manifest_file,
        status="planned",
        created_at=ts,
        updated_at=ts,
        completed_at=None,
        interpreted_at=None,
        presented_at=None,
        progress=ExperimentProgress(
            runs_total=len(run_ids),
            runs_complete=0,
            runs_failed=0,
            diffs_total=len(comparison_ids),
            diffs_complete=0,
        ),
        run_statuses={rid: "pending" for rid in run_ids},
        diff_statuses={cid: "pending" for cid in comparison_ids},
        artifacts={
            "brief_json": None,
            "brief_md": None,
            "brief_validation_json": None,
            "summary_json": None,
            "summary_md": None,
            "interpretation_json": None,
            "interpretation_md": None,
            "interpretation_validation_json": None,
            "presentation_html": None,
        },
    )
    save_experiment_state(state, experiment_dir)
    return state


def load_experiment_state(experiment_dir: Path) -> ExperimentState:
    """Load state from state.json."""
    state_path = experiment_dir / STATE_FILENAME
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExperimentStateError(
            f"Invalid state JSON: {state_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ExperimentStateError(
            f"Invalid state: expected JSON object in {state_path}"
        )
    return ExperimentState.from_dict(payload)


def save_experiment_state(state: ExperimentState, experiment_dir: Path) -> None:
    """Write state.json with deterministic formatting."""
    state_path = experiment_dir / STATE_FILENAME
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state.to_dict(), indent=2) + "\n")


def mark_run_started(
    state: ExperimentState,
    run_id: str,
    now_utc: Callable[[], datetime] | None = None,
) -> ExperimentState:
    """Mark a run as started, transition to 'running' if needed."""
    if run_id not in state.run_statuses:
        raise ExperimentStateError(f"Unknown run_id: {run_id!r}")
    if state.status == "planned":
        _transition(state, "running")
    state.run_statuses[run_id] = "running"
    state.updated_at = _format_timestamp(_now_factory(now_utc)())
    return state


def mark_run_complete(
    state: ExperimentState,
    run_id: str,
    now_utc: Callable[[], datetime] | None = None,
) -> ExperimentState:
    """Mark a run as complete, update progress counts."""
    if run_id not in state.run_statuses:
        raise ExperimentStateError(f"Unknown run_id: {run_id!r}")
    state.run_statuses[run_id] = "complete"
    state.progress.runs_complete = sum(
        1 for s in state.run_statuses.values() if s == "complete"
    )
    state.updated_at = _format_timestamp(_now_factory(now_utc)())
    return check_completion(state)


def mark_run_failed(
    state: ExperimentState,
    run_id: str,
    now_utc: Callable[[], datetime] | None = None,
) -> ExperimentState:
    """Mark a run as failed."""
    if run_id not in state.run_statuses:
        raise ExperimentStateError(f"Unknown run_id: {run_id!r}")
    state.run_statuses[run_id] = "failed"
    state.progress.runs_failed = sum(
        1 for s in state.run_statuses.values() if s == "failed"
    )
    state.updated_at = _format_timestamp(_now_factory(now_utc)())
    return state


def mark_diff_complete(
    state: ExperimentState,
    diff_id: str,
    now_utc: Callable[[], datetime] | None = None,
) -> ExperimentState:
    """Mark a diff as complete, check if all diffs done."""
    if diff_id not in state.diff_statuses:
        raise ExperimentStateError(f"Unknown diff_id: {diff_id!r}")
    state.diff_statuses[diff_id] = "complete"
    state.progress.diffs_complete = sum(
        1 for s in state.diff_statuses.values() if s == "complete"
    )
    state.updated_at = _format_timestamp(_now_factory(now_utc)())
    return check_completion(state)


def check_completion(state: ExperimentState) -> ExperimentState:
    """If all runs complete and all diffs complete, transition to 'complete'."""
    if state.status != "running":
        return state
    all_runs_done = all(
        s in ("complete", "failed") for s in state.run_statuses.values()
    )
    all_diffs_done = all(
        s in ("complete", "failed") for s in state.diff_statuses.values()
    )
    if all_runs_done and all_diffs_done:
        _transition(state, "complete")
        state.completed_at = state.updated_at
    return state


def mark_interpreted(
    state: ExperimentState,
    now_utc: Callable[[], datetime] | None = None,
) -> ExperimentState:
    """Transition to 'interpreted'.

    Raises if summary_json or interpretation_json missing.
    """
    if not state.artifacts.get("summary_json"):
        raise ExperimentStateError(
            "Cannot interpret: artifacts.summary_json is not set"
        )
    if not state.artifacts.get("interpretation_json"):
        raise ExperimentStateError(
            "Cannot interpret: artifacts.interpretation_json is not set"
        )
    _transition(state, "interpreted")
    ts = _format_timestamp(_now_factory(now_utc)())
    state.interpreted_at = ts
    state.updated_at = ts
    return state


def mark_presented(
    state: ExperimentState,
    now_utc: Callable[[], datetime] | None = None,
) -> ExperimentState:
    """Transition to 'presented'.

    Raises if presentation_html missing.
    """
    if not state.artifacts.get("presentation_html"):
        raise ExperimentStateError(
            "Cannot present: artifacts.presentation_html is not set"
        )
    _transition(state, "presented")
    ts = _format_timestamp(_now_factory(now_utc)())
    state.presented_at = ts
    state.updated_at = ts
    return state
