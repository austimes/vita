"""Reusable solver-backed pipeline harness for end-to-end tests."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.veda_dev.pipeline import PipelineResult, format_result_table, run_pipeline
from tools.veda_run_times.runner import find_times_source

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOLVER_ARTIFACTS_ENV = "VEDALANG_SOLVER_ARTIFACTS_DIR"
SMOKE_FIXTURE = (
    PROJECT_ROOT
    / "vedalang"
    / "examples"
    / "quickstart"
    / "mini_plant.veda.yaml"
)


@dataclass(frozen=True)
class SolverPrerequisites:
    """Environment checks required for solver-backed tests."""

    ready: bool
    times_src: Path | None
    gams_binary: str
    missing: tuple[str, ...] = ()

    def skip_reason(self) -> str:
        """Reason string for skipping solver-backed tests."""
        if self.ready:
            return ""
        return "; ".join(self.missing)


@dataclass
class SolverPipelineArtifacts:
    """Discovered artifacts from a full `run_pipeline` execution."""

    fixture_path: Path
    pipeline_result: PipelineResult
    work_dir: Path
    times_work_dir: Path | None
    gdx_files: list[Path] = field(default_factory=list)
    diagnostics_file: Path | None = None
    diagnostics: dict[str, Any] | None = None
    artifact_bundle_dir: Path | None = None

    @property
    def primary_gdx(self) -> Path | None:
        """Primary GDX path for result extraction/known-answer checks."""
        if not self.gdx_files:
            return None
        return sorted(self.gdx_files, key=_gdx_preference_key)[0]

    @property
    def debug_artifact_hint(self) -> str:
        """One-line summary of useful diagnostics artifact paths."""
        hints: list[str] = [f"work_dir={self.work_dir}"]
        if self.times_work_dir is not None:
            hints.append(f"times_work_dir={self.times_work_dir}")
        if self.primary_gdx is not None:
            hints.append(f"primary_gdx={self.primary_gdx}")
        if self.diagnostics_file is not None:
            hints.append(f"diagnostics_json={self.diagnostics_file}")
        if self.artifact_bundle_dir is not None:
            hints.append(f"artifact_bundle_dir={self.artifact_bundle_dir}")
        return "; ".join(hints)


def detect_solver_prerequisites(gams_binary: str = "gams") -> SolverPrerequisites:
    """Check whether this machine can run end-to-end solver tests."""
    missing: list[str] = []

    times_src = find_times_source()
    if times_src is None:
        missing.append(
            "TIMES source not found (set TIMES_SRC or install ~/TIMES_model)"
        )

    resolved_gams = gams_binary
    binary_path = shutil.which(gams_binary)
    if binary_path:
        resolved_gams = binary_path
    elif not Path(gams_binary).exists():
        missing.append(f"GAMS binary not found: {gams_binary}")

    return SolverPrerequisites(
        ready=not missing,
        times_src=times_src,
        gams_binary=resolved_gams,
        missing=tuple(missing),
    )


def run_solver_pipeline_fixture(
    fixture_path: Path,
    *,
    run_id: str | None = None,
    case: str = "scenario",
    times_src: Path | None = None,
    gams_binary: str = "gams",
    solver: str = "CPLEX",
    work_dir: Path | None = None,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
    require_success: bool = True,
    verbose: bool = False,
) -> SolverPipelineArtifacts:
    """Run a fixture through the full solver pipeline and discover key artifacts."""
    fixture = Path(fixture_path)
    if not fixture.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture}")

    effective_times_src = times_src or find_times_source()
    if effective_times_src is None:
        raise RuntimeError("TIMES source not found. Set TIMES_SRC or pass times_src")

    result = run_pipeline(
        input_path=fixture,
        input_kind="vedalang",
        run_id=run_id,
        case=case,
        times_src=effective_times_src,
        gams_binary=gams_binary,
        solver=solver,
        work_dir=work_dir,
        keep_workdir=True,
        no_solver=False,
        no_sankey=True,
        measure_weights=measure_weights,
        custom_weights=custom_weights,
        verbose=verbose,
    )

    discovered = discover_solver_artifacts(result, fixture_path=fixture)
    discovered.artifact_bundle_dir = _capture_solver_artifacts(
        discovered,
        case=case,
        run_id=run_id,
    )

    if require_success and not result.success:
        raise AssertionError(format_result_table(result))

    return discovered


def discover_solver_artifacts(
    result: PipelineResult,
    *,
    fixture_path: Path,
) -> SolverPipelineArtifacts:
    """Discover stable artifact paths from a pipeline run result."""
    if result.work_dir == "(cleaned up)":
        raise ValueError(
            "Pipeline work directory was cleaned up; rerun with keep_workdir"
        )

    work_dir = Path(result.work_dir)
    if not work_dir.exists():
        raise ValueError(f"Pipeline work directory does not exist: {work_dir}")

    run_times_step = result.steps.get("run_times")
    if run_times_step is None or run_times_step.skipped:
        raise ValueError("Pipeline result has no run_times step artifacts")

    times_work_dir = _path_from_artifact(run_times_step.artifacts.get("times_work_dir"))
    if times_work_dir is None:
        candidate = work_dir / "gams"
        if candidate.exists():
            times_work_dir = candidate

    gdx_files: list[Path] = []
    for value in run_times_step.artifacts.get("gdx_files", []):
        path = Path(value)
        if path.exists() and path not in gdx_files:
            gdx_files.append(path)

    if not gdx_files and times_work_dir and times_work_dir.exists():
        gdx_files = sorted(times_work_dir.glob("*.gdx"))

    if gdx_files:
        gdx_files = sorted(gdx_files, key=_gdx_preference_key)

    diagnostics_file = _path_from_artifact(
        run_times_step.artifacts.get("gams_diagnostics_file")
    )

    diagnostics = run_times_step.artifacts.get("gams_diagnostics")
    if diagnostics is None and diagnostics_file and diagnostics_file.exists():
        diagnostics = json.loads(diagnostics_file.read_text())

    return SolverPipelineArtifacts(
        fixture_path=fixture_path,
        pipeline_result=result,
        work_dir=work_dir,
        times_work_dir=times_work_dir,
        gdx_files=gdx_files,
        diagnostics_file=diagnostics_file,
        diagnostics=diagnostics,
    )


def _path_from_artifact(value: Any) -> Path | None:
    """Convert a JSON-like artifact value to an existing Path when possible."""
    if not value:
        return None
    path = Path(str(value))
    return path if path.exists() else None


def _gdx_preference_key(path: Path) -> tuple[bool, str]:
    """Prefer solution GDX files over `~Data` intermediates."""
    name = path.name.upper()
    return ("~DATA" in name, str(path))


def _capture_solver_artifacts(
    artifacts: SolverPipelineArtifacts,
    *,
    case: str,
    run_id: str | None,
) -> Path | None:
    """Persist a copy of solver artifacts when CI artifact capture is enabled."""
    artifact_root = os.environ.get(SOLVER_ARTIFACTS_ENV)
    if not artifact_root:
        return None

    root_dir = Path(artifact_root).expanduser().resolve()
    root_dir.mkdir(parents=True, exist_ok=True)

    slug_parts = [artifacts.fixture_path.stem, case]
    if run_id:
        slug_parts.append(run_id)
    base_dir = root_dir / _slugify("__".join(slug_parts))
    bundle_dir = _unique_bundle_dir(base_dir)
    bundle_dir.mkdir(parents=True, exist_ok=False)

    copied_work_dir = bundle_dir / "pipeline_work_dir"
    shutil.copytree(artifacts.work_dir, copied_work_dir)

    payload = {
        "fixture_path": str(artifacts.fixture_path),
        "case": case,
        "run_id": run_id,
        "pipeline_success": artifacts.pipeline_result.success,
        "work_dir": str(artifacts.work_dir),
        "times_work_dir": (
            str(artifacts.times_work_dir) if artifacts.times_work_dir else None
        ),
        "diagnostics_file": (
            str(artifacts.diagnostics_file) if artifacts.diagnostics_file else None
        ),
        "primary_gdx": str(artifacts.primary_gdx) if artifacts.primary_gdx else None,
        "gdx_files": [str(path) for path in artifacts.gdx_files],
        "copied_work_dir": str(copied_work_dir),
    }
    (bundle_dir / "summary.json").write_text(json.dumps(payload, indent=2))
    (bundle_dir / "pipeline_result.json").write_text(
        json.dumps(artifacts.pipeline_result.to_dict(), indent=2)
    )
    return bundle_dir


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return normalized or "solver-run"


def _unique_bundle_dir(base_dir: Path) -> Path:
    """Return a unique artifact bundle directory path."""
    if not base_dir.exists():
        return base_dir

    index = 2
    while True:
        candidate = base_dir.parent / f"{base_dir.name}-{index}"
        if not candidate.exists():
            return candidate
        index += 1
