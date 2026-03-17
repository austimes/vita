"""Run artifact contract utilities for Vita run directories."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "manifest.json"
SOURCE_SNAPSHOT_FILENAME = "model.veda.yaml"
RESULTS_FILENAME = "results.json"
SOLVER_DIRNAME = "solver"

RUN_MANIFEST_REQUIRED_FIELDS = (
    "run_id",
    "source",
    "case",
    "timestamp",
    "solver_status",
)

RUN_MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "VitaRunManifest",
    "type": "object",
    "required": list(RUN_MANIFEST_REQUIRED_FIELDS),
    "properties": {
        "run_id": {"type": "string", "minLength": 1},
        "source": {"type": "string", "minLength": 1},
        "case": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "format": "date-time"},
        "solver_status": {"type": "string", "minLength": 1},
        "objective": {"type": ["number", "null"]},
        "model_status": {"type": ["integer", "null"]},
        "solve_status": {"type": ["integer", "null"]},
        "input_kind": {"type": ["string", "null"]},
        "pipeline_success": {"type": ["boolean", "null"]},
    },
    "additionalProperties": True,
}


class RunArtifactError(ValueError):
    """Raised when a run artifact directory is invalid or incomplete."""


@dataclass(frozen=True)
class RunArtifactPaths:
    """Canonical paths for a single Vita run directory."""

    run_dir: Path
    case: str
    manifest_path: Path
    source_snapshot_path: Path
    results_path: Path
    solver_dir: Path
    gdx_path: Path
    lst_path: Path

    def to_dict(self) -> dict[str, str]:
        """Return JSON-serializable absolute paths."""
        return {
            "run_dir": str(self.run_dir.resolve()),
            "manifest_file": str(self.manifest_path.resolve()),
            "source_snapshot_file": str(self.source_snapshot_path.resolve()),
            "results_file": str(self.results_path.resolve()),
            "solver_dir": str(self.solver_dir.resolve()),
            "gdx_file": str(self.gdx_path.resolve()),
            "lst_file": str(self.lst_path.resolve()),
        }

    @property
    def manifest_file(self) -> Path:
        """Compatibility alias for manifest path."""
        return self.manifest_path

    @property
    def model_source_file(self) -> Path:
        """Compatibility alias for source snapshot path."""
        return self.source_snapshot_path

    @property
    def results_file(self) -> Path:
        """Compatibility alias for results path."""
        return self.results_path

    @property
    def gdx_file(self) -> Path:
        """Compatibility alias for solver GDX path."""
        return self.gdx_path

    @property
    def lst_file(self) -> Path:
        """Compatibility alias for solver LST path."""
        return self.lst_path


@dataclass(frozen=True)
class RunManifest:
    """Typed representation of `manifest.json` for a Vita run."""

    run_id: str
    source: str
    case: str
    timestamp: str
    solver_status: str
    objective: float | None = None
    model_status: int | None = None
    solve_status: int | None = None
    input_kind: str | None = None
    pipeline_success: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this manifest to a plain dict."""
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "source": self.source,
            "case": self.case,
            "timestamp": self.timestamp,
            "solver_status": self.solver_status,
            "objective": self.objective,
            "model_status": self.model_status,
            "solve_status": self.solve_status,
            "input_kind": self.input_kind,
            "pipeline_success": self.pipeline_success,
        }
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RunManifest:
        """Deserialize and minimally validate a run manifest payload."""
        missing = [key for key in RUN_MANIFEST_REQUIRED_FIELDS if key not in payload]
        if missing:
            raise RunArtifactError(
                f"Invalid run manifest: missing required field(s): {', '.join(missing)}"
            )

        run_id = _require_non_empty_str(payload, "run_id")
        source = _require_non_empty_str(payload, "source")
        case = _require_non_empty_str(payload, "case")
        timestamp = _require_non_empty_str(payload, "timestamp")
        solver_status = _require_non_empty_str(payload, "solver_status")

        objective = _optional_float(payload.get("objective"), field_name="objective")
        model_status = _optional_int(
            payload.get("model_status"), field_name="model_status"
        )
        solve_status = _optional_int(
            payload.get("solve_status"), field_name="solve_status"
        )
        input_kind = _optional_str(payload.get("input_kind"), field_name="input_kind")
        pipeline_success = _optional_bool(
            payload.get("pipeline_success"),
            field_name="pipeline_success",
        )

        return cls(
            run_id=run_id,
            source=source,
            case=case,
            timestamp=timestamp,
            solver_status=solver_status,
            objective=objective,
            model_status=model_status,
            solve_status=solve_status,
            input_kind=input_kind,
            pipeline_success=pipeline_success,
        )


@dataclass(frozen=True)
class RunArtifactEmission:
    """Result from emitting a run artifact directory."""

    paths: RunArtifactPaths
    manifest: RunManifest
    results_written: bool


def build_run_artifact_paths(
    run_dir: Path, *, case: str = "scenario"
) -> RunArtifactPaths:
    """Build canonical paths for a run directory without validating file existence."""
    normalized = run_dir.expanduser().resolve()
    solver_dir = normalized / SOLVER_DIRNAME
    return RunArtifactPaths(
        run_dir=normalized,
        case=case,
        manifest_path=normalized / MANIFEST_FILENAME,
        source_snapshot_path=normalized / SOURCE_SNAPSHOT_FILENAME,
        results_path=normalized / RESULTS_FILENAME,
        solver_dir=solver_dir,
        gdx_path=solver_dir / f"{case}.gdx",
        lst_path=solver_dir / f"{case}.lst",
    )


def write_run_manifest(manifest: RunManifest, manifest_path: Path) -> None:
    """Write a run manifest with deterministic JSON formatting."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n")


def load_run_manifest(manifest_path: Path) -> RunManifest:
    """Read and validate a run manifest from disk."""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunArtifactError(
            f"Invalid run manifest JSON: {manifest_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RunArtifactError(
            f"Invalid run manifest: expected JSON object in {manifest_path}"
        )
    return RunManifest.from_dict(payload)


def resolve_run_artifacts(
    run_dir: Path,
    *,
    case: str | None = None,
    require_results: bool = False,
    require_solver: bool = False,
) -> RunArtifactPaths:
    """Validate a run directory and return canonical paths."""
    normalized = run_dir.expanduser().resolve()
    baseline_paths = build_run_artifact_paths(normalized, case=case or "scenario")

    errors: list[str] = []
    if not normalized.exists():
        errors.append(f"Run directory not found: {normalized}")
    elif not normalized.is_dir():
        errors.append(f"Run directory is not a directory: {normalized}")

    if normalized.exists() and not baseline_paths.manifest_path.exists():
        errors.append(f"Missing required file: {baseline_paths.manifest_path}")

    effective_case = case
    manifest: RunManifest | None = None
    if baseline_paths.manifest_path.exists():
        manifest = load_run_manifest(baseline_paths.manifest_path)
        if effective_case is None:
            effective_case = manifest.case

    paths = build_run_artifact_paths(normalized, case=effective_case or "scenario")

    if not paths.source_snapshot_path.exists():
        errors.append(f"Missing required file: {paths.source_snapshot_path}")
    if require_results and not paths.results_path.exists():
        errors.append(f"Missing required file: {paths.results_path}")
    if require_solver:
        if not paths.solver_dir.exists():
            errors.append(f"Missing required directory: {paths.solver_dir}")
        if not paths.gdx_path.exists():
            errors.append(f"Missing required file: {paths.gdx_path}")
        if not paths.lst_path.exists():
            errors.append(f"Missing required file: {paths.lst_path}")

    if errors:
        raise RunArtifactError("\n".join(errors))

    if manifest and manifest.case != paths.case:
        raise RunArtifactError(
            "Run manifest case "
            f"({manifest.case}) does not match expected case ({paths.case})"
        )
    return paths


def resolve_run_artifact_paths(
    run_dir: Path, *, case: str = "scenario"
) -> RunArtifactPaths:
    """Compatibility helper returning canonical paths without validation."""
    return build_run_artifact_paths(run_dir, case=case)


def validate_run_artifacts(
    run_dir: Path,
    *,
    case: str = "scenario",
    require_results: bool = False,
    require_solver_files: bool = False,
) -> RunArtifactPaths:
    """Compatibility helper for validating run directories."""
    return resolve_run_artifacts(
        run_dir,
        case=case,
        require_results=require_results,
        require_solver=require_solver_files,
    )


def write_manifest(path: Path, manifest: RunManifest) -> None:
    """Compatibility helper for writing manifest JSON."""
    write_run_manifest(manifest, path)


def emit_run_artifacts(
    *,
    run_dir: Path,
    input_path: Path,
    input_kind: str,
    case: str,
    selected_run_id: str | None,
    pipeline_success: bool,
    pipeline_artifacts: Mapping[str, Any],
    run_times_artifacts: Mapping[str, Any],
    run_times_success: bool,
    run_times_skipped: bool,
    extract_results: Callable[..., Any] | None = None,
    now_utc: Callable[[], datetime] | None = None,
) -> RunArtifactEmission:
    """Emit a stable run artifact directory from pipeline outputs."""
    paths = build_run_artifact_paths(run_dir, case=case)
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    paths.solver_dir.mkdir(parents=True, exist_ok=True)

    _write_source_snapshot(
        source_path=input_path,
        input_kind=input_kind,
        destination=paths.source_snapshot_path,
    )
    _copy_solver_artifacts(paths, run_times_artifacts)
    gdx_candidates = _existing_paths(run_times_artifacts.get("gdx_files", []))
    preferred_gdx = _pick_preferred_gdx(gdx_candidates)
    extraction_gdx_path = preferred_gdx or paths.gdx_path

    timestamp_factory = now_utc or (lambda: datetime.now(UTC))
    manifest = RunManifest(
        run_id=_derive_run_id(
            selected_run_id=selected_run_id,
            pipeline_artifacts=pipeline_artifacts,
            run_dir=paths.run_dir,
        ),
        source=str(input_path),
        case=case,
        timestamp=timestamp_factory()
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        solver_status=_derive_solver_status(
            run_times_artifacts=run_times_artifacts,
            run_times_success=run_times_success,
            run_times_skipped=run_times_skipped,
        ),
        objective=_optional_float(
            run_times_artifacts.get("objective"),
            field_name="objective",
        ),
        model_status=_diagnostic_status_code(run_times_artifacts, "model_status"),
        solve_status=_diagnostic_status_code(run_times_artifacts, "solve_status"),
        input_kind=input_kind,
        pipeline_success=pipeline_success,
    )
    write_run_manifest(manifest, paths.manifest_path)

    results_written = False
    if extract_results is not None and extraction_gdx_path.exists():
        try:
            results_obj = extract_results(
                gdx_path=extraction_gdx_path,
                include_flows=True,
                limit=0,
            )
            payload = (
                results_obj.to_dict()
                if hasattr(results_obj, "to_dict")
                else results_obj
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            payload = {
                "gdx_path": str(extraction_gdx_path),
                "errors": [f"Failed to extract results: {exc}"],
            }
        paths.results_path.write_text(json.dumps(payload, indent=2) + "\n")
        results_written = True

    return RunArtifactEmission(
        paths=paths,
        manifest=manifest,
        results_written=results_written,
    )


def _derive_run_id(
    *,
    selected_run_id: str | None,
    pipeline_artifacts: Mapping[str, Any],
    run_dir: Path,
) -> str:
    if selected_run_id and selected_run_id.strip():
        return selected_run_id.strip()

    run_id = pipeline_artifacts.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return run_id.strip()

    if run_dir.name:
        return run_dir.name
    return "scenario"


def _write_source_snapshot(
    *,
    source_path: Path,
    input_kind: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_path.exists() and source_path.is_file():
        shutil.copy2(source_path, destination)
        return

    payload = {
        "source_path": str(source_path),
        "input_kind": input_kind,
    }
    destination.write_text(json.dumps(payload, indent=2) + "\n")


def _copy_solver_artifacts(
    paths: RunArtifactPaths,
    run_times_artifacts: Mapping[str, Any],
) -> None:
    gdx_candidates = _existing_paths(run_times_artifacts.get("gdx_files", []))
    preferred_gdx = _pick_preferred_gdx(gdx_candidates)
    for source in gdx_candidates:
        _copy_to_dir(source, paths.solver_dir)

    if preferred_gdx is not None:
        _copy_to_file(preferred_gdx, paths.gdx_path)

    lst_value = run_times_artifacts.get("lst_file")
    if isinstance(lst_value, str):
        lst_source = Path(lst_value)
        if lst_source.exists():
            _copy_to_file(lst_source, paths.lst_path)


def _pick_preferred_gdx(candidates: list[Path]) -> Path | None:
    if not candidates:
        return None
    non_data = [path for path in candidates if "~DATA" not in path.name.upper()]
    ranked = non_data or candidates
    return sorted(ranked, key=lambda path: path.name)[0]


def _copy_to_dir(source: Path, destination_dir: Path) -> None:
    destination = destination_dir / source.name
    _copy_to_file(source, destination)


def _copy_to_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_resolved = source.resolve()
    destination_resolved = destination.resolve() if destination.exists() else None
    if destination_resolved is not None and source_resolved == destination_resolved:
        return
    shutil.copy2(source, destination)


def _derive_solver_status(
    *,
    run_times_artifacts: Mapping[str, Any],
    run_times_success: bool,
    run_times_skipped: bool,
) -> str:
    if run_times_skipped:
        return "skipped"

    diagnostics = run_times_artifacts.get("gams_diagnostics")
    if isinstance(diagnostics, Mapping):
        summary = diagnostics.get("summary")
        if isinstance(summary, Mapping):
            if summary.get("ok") is True:
                return "optimal"
            problem_type = summary.get("problem_type")
            if isinstance(problem_type, str) and problem_type.strip():
                return problem_type.strip()

    if run_times_success:
        return "ok"
    if run_times_artifacts:
        return "failed"
    return "not_run"


def _diagnostic_status_code(
    run_times_artifacts: Mapping[str, Any],
    field_name: str,
) -> int | None:
    diagnostics = run_times_artifacts.get("gams_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return None
    execution = diagnostics.get("execution")
    if not isinstance(execution, Mapping):
        return None
    status = execution.get(field_name)
    if not isinstance(status, Mapping):
        return None
    return _optional_int(status.get("code"), field_name=field_name)


def _existing_paths(values: Any) -> list[Path]:
    if not isinstance(values, list):
        return []

    paths: list[Path] = []
    for value in values:
        if isinstance(value, str):
            path = Path(value)
            if path.exists():
                paths.append(path)
    return paths


def _require_non_empty_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RunArtifactError(
            f"Invalid run manifest: {key!r} must be a non-empty string"
        )
    return value.strip()


def _optional_str(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RunArtifactError(f"Invalid run manifest: {field_name!r} must be a string")
    text = value.strip()
    return text or None


def _optional_bool(value: Any, *, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise RunArtifactError(
            f"Invalid run manifest: {field_name!r} must be a boolean"
        )
    return value


def _optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RunArtifactError(
            f"Invalid run manifest: {field_name!r} must be an integer"
        )
    return value


def _optional_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RunArtifactError(f"Invalid run manifest: {field_name!r} must be numeric")
    return float(value)
