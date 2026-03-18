"""Experiment runner — orchestrates plan, run, diff, and analysis phases."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from vita.diff import compare_run_artifacts
from vita.experiment_manifest import (
    CaseSpec,
    ComparisonSpec,
    ExperimentManifest,
    load_experiment_manifest,
    validate_manifest,
)
from vita.experiment_state import (
    ExperimentState,
    create_experiment_state,
    load_experiment_state,
    mark_diff_complete,
    mark_run_complete,
    mark_run_failed,
    mark_run_started,
    save_experiment_state,
)
from vita.run_artifacts import emit_run_artifacts, load_run_manifest

logger = logging.getLogger(__name__)


@dataclass
class ExperimentRunResult:
    experiment_dir: Path
    state: ExperimentState
    success: bool
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 1: Plan
# ---------------------------------------------------------------------------


def plan_experiment(
    manifest_path: Path,
    out_dir: Path,
) -> ExperimentState:
    """Set up experiment directory and return initial state.

    1. Load and validate manifest
    2. Create output directory structure
    3. Copy manifest.yaml (immutable record)
    4. Snapshot model files into inputs/models/
    5. Create state.json with status=planned
    """
    manifest = load_experiment_manifest(manifest_path)
    warnings = validate_manifest(manifest)
    for w in warnings:
        logger.warning("manifest warning: %s", w)

    experiment_dir = out_dir / manifest.id
    experiment_dir.mkdir(parents=True, exist_ok=True)

    # Copy manifest (immutable)
    dest_manifest = experiment_dir / "manifest.yaml"
    shutil.copy2(manifest.manifest_path, dest_manifest)

    # Snapshot model files
    models_dir = experiment_dir / "inputs" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    seen_models: set[Path] = set()
    for case in manifest.all_cases():
        if case.model in seen_models:
            continue
        seen_models.add(case.model)
        if case.model.exists() and case.model.is_file():
            shutil.copy2(case.model, models_dir / case.model.name)

    # Pre-create run and diff directories
    for case in manifest.all_cases():
        (experiment_dir / "runs" / case.id).mkdir(parents=True, exist_ok=True)
    for comp in manifest.comparisons:
        (experiment_dir / "diffs" / comp.id).mkdir(parents=True, exist_ok=True)
    (experiment_dir / "analyses").mkdir(parents=True, exist_ok=True)

    # Create state
    run_ids = [c.id for c in manifest.all_cases()]
    comparison_ids = [c.id for c in manifest.comparisons]
    state = create_experiment_state(
        experiment_dir=experiment_dir,
        experiment_id=manifest.id,
        manifest_file="manifest.yaml",
        run_ids=run_ids,
        comparison_ids=comparison_ids,
    )
    return state


# ---------------------------------------------------------------------------
# Phase 2: Run experiment
# ---------------------------------------------------------------------------


def run_experiment(
    experiment_dir: Path,
    *,
    resume: bool = False,
    force: bool = False,
    json_output: bool = False,
) -> ExperimentRunResult:
    """Execute all runs and diffs for an experiment.

    1. Load manifest and state from experiment_dir
    2. Run each case (baseline first, then variants)
    3. Compute each comparison diff
    4. Build analyses (run_matrix.json)
    5. Return result
    """
    experiment_dir = experiment_dir.expanduser().resolve()
    manifest = load_experiment_manifest(experiment_dir / "manifest.yaml")
    state = load_experiment_state(experiment_dir)

    errors: list[str] = []
    no_sankey = manifest.defaults.no_sankey

    # --- Runs ---
    for case in manifest.all_cases():
        run_dir = experiment_dir / "runs" / case.id

        if force:
            _clean_run_dir(run_dir)
        elif resume and _run_already_complete(run_dir):
            logger.info("Skipping completed run: %s", case.id)
            continue

        mark_run_started(state, case.id)
        save_experiment_state(state, experiment_dir)

        try:
            _run_single_case(case, run_dir, no_sankey=no_sankey)
            mark_run_complete(state, case.id)
        except Exception as exc:
            msg = f"Run {case.id} failed: {exc}"
            logger.error(msg)
            errors.append(msg)
            mark_run_failed(state, case.id)

        save_experiment_state(state, experiment_dir)

    # --- Diffs ---
    for comp in manifest.comparisons:
        diff_dir = experiment_dir / "diffs" / comp.id
        diff_file = diff_dir / "diff.json"

        if force and diff_file.exists():
            diff_file.unlink()
        elif resume and diff_file.exists():
            logger.info("Skipping completed diff: %s", comp.id)
            continue

        # Only diff if both runs succeeded
        baseline_dir = experiment_dir / "runs" / comp.baseline
        variant_dir = experiment_dir / "runs" / comp.variant
        if not _run_already_complete(baseline_dir):
            msg = f"Diff {comp.id} skipped: baseline run {comp.baseline!r} not complete"
            logger.warning(msg)
            errors.append(msg)
            continue
        if not _run_already_complete(variant_dir):
            msg = f"Diff {comp.id} skipped: variant run {comp.variant!r} not complete"
            logger.warning(msg)
            errors.append(msg)
            continue

        try:
            diff_result = _run_single_diff(comp, experiment_dir)
            diff_dir.mkdir(parents=True, exist_ok=True)
            diff_file.write_text(json.dumps(diff_result, indent=2) + "\n")
            mark_diff_complete(state, comp.id)
        except Exception as exc:
            msg = f"Diff {comp.id} failed: {exc}"
            logger.error(msg)
            errors.append(msg)

        save_experiment_state(state, experiment_dir)

    # --- Analyses ---
    try:
        matrix = _build_run_matrix(manifest, experiment_dir)
        analyses_dir = experiment_dir / "analyses"
        analyses_dir.mkdir(parents=True, exist_ok=True)
        (analyses_dir / "run_matrix.json").write_text(
            json.dumps(matrix, indent=2) + "\n"
        )
    except Exception as exc:
        msg = f"Analysis build failed: {exc}"
        logger.error(msg)
        errors.append(msg)

    save_experiment_state(state, experiment_dir)

    success = len(errors) == 0
    return ExperimentRunResult(
        experiment_dir=experiment_dir,
        state=state,
        success=success,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_single_case(
    case: CaseSpec,
    run_dir: Path,
    *,
    no_sankey: bool,
) -> dict:
    """Run a single case through the pipeline. Returns pipeline result dict."""
    from tools.veda_dev.pipeline import run_pipeline
    from tools.veda_dev.times_results import extract_results

    result = run_pipeline(
        input_path=case.model,
        input_kind="vedalang",
        run_id=case.run,
        case=case.case,
        keep_workdir=True,
        no_solver=False,
        no_sankey=no_sankey,
        verbose=False,
    )

    run_times_step = result.steps.get("run_times")
    emit_run_artifacts(
        run_dir=run_dir,
        input_path=case.model,
        input_kind=result.input_kind or "vedalang",
        case=case.case,
        selected_run_id=case.run,
        pipeline_success=result.success,
        pipeline_artifacts=result.artifacts,
        run_times_artifacts=(
            run_times_step.artifacts if run_times_step is not None else {}
        ),
        run_times_success=(
            run_times_step.success if run_times_step is not None else False
        ),
        run_times_skipped=(
            run_times_step.skipped if run_times_step is not None else True
        ),
        extract_results=extract_results,
        now_utc=lambda: datetime.now(UTC),
    )

    # Clean up work_dir after artifact emission
    if result.success and result.work_dir and result.work_dir != "(cleaned up)":
        work_dir_path = Path(result.work_dir)
        if work_dir_path.exists():
            shutil.rmtree(work_dir_path)

    if not result.success:
        raise RuntimeError(
            f"Pipeline failed for case {case.id}: "
            + "; ".join(
                err
                for step in result.steps.values()
                for err in step.errors
            )
        )

    return result.to_dict()


def _run_single_diff(
    comparison: ComparisonSpec,
    experiment_dir: Path,
) -> dict:
    """Compute a single diff. Returns diff result dict."""
    baseline_dir = experiment_dir / "runs" / comparison.baseline
    variant_dir = experiment_dir / "runs" / comparison.variant
    return compare_run_artifacts(
        baseline_run_dir=baseline_dir,
        variant_run_dir=variant_dir,
        metrics=comparison.metrics,
        focus_processes=comparison.focus_processes,
    )


def _build_run_matrix(
    manifest: ExperimentManifest,
    experiment_dir: Path,
) -> dict:
    """Build analyses/run_matrix.json from completed run results."""
    cases_data: list[dict] = []
    for case in manifest.all_cases():
        run_dir = experiment_dir / "runs" / case.id
        manifest_path = run_dir / "manifest.json"
        entry: dict = {
            "id": case.id,
            "objective": None,
            "solver_status": None,
            "pipeline_success": None,
            "run_dir": f"runs/{case.id}",
        }
        if manifest_path.exists():
            rm = load_run_manifest(manifest_path)
            entry["objective"] = rm.objective
            entry["solver_status"] = rm.solver_status
            entry["pipeline_success"] = rm.pipeline_success
        cases_data.append(entry)

    comparisons_data: list[dict] = []
    for comp in manifest.comparisons:
        diff_file = experiment_dir / "diffs" / comp.id / "diff.json"
        entry = {
            "id": comp.id,
            "baseline_objective": None,
            "variant_objective": None,
            "delta_objective": None,
            "pct_delta_objective": None,
            "diff_file": f"diffs/{comp.id}/diff.json",
        }
        if diff_file.exists():
            diff_data = json.loads(diff_file.read_text(encoding="utf-8"))
            obj = diff_data.get("objective", {})
            entry["baseline_objective"] = obj.get("baseline")
            entry["variant_objective"] = obj.get("variant")
            entry["delta_objective"] = obj.get("delta")
            entry["pct_delta_objective"] = obj.get("pct_delta")
        comparisons_data.append(entry)

    return {
        "cases": cases_data,
        "comparisons": comparisons_data,
    }


def _run_already_complete(run_dir: Path) -> bool:
    """Check if a run has already completed successfully."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        rm = load_run_manifest(manifest_path)
        return rm.pipeline_success is True
    except Exception:
        return False


def _clean_run_dir(run_dir: Path) -> None:
    """Remove all contents of a run directory for force re-run."""
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
