"""Generate experiment summary from completed run and diff artifacts."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from vita.experiment_manifest import (
    ExperimentManifest,
    load_experiment_manifest,
)
from vita.experiment_state import (
    ExperimentStateError,
    load_experiment_state,
    save_experiment_state,
)

SUMMARY_SCHEMA_VERSION = "vita-experiment-summary/v1"


def _format_timestamp(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_factory(now_utc: Callable[[], datetime] | None) -> Callable[[], datetime]:
    return now_utc or (lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_summary(
    experiment_dir: Path,
    *,
    now_utc: Callable[[], datetime] | None = None,
) -> Path:
    """Generate conclusions/summary.json and conclusions/summary.md.

    Returns path to summary.json.
    """
    experiment_dir = experiment_dir.expanduser().resolve()
    manifest = load_experiment_manifest(experiment_dir / "manifest.yaml")
    state = load_experiment_state(experiment_dir)

    if state.status not in ("complete", "concluded"):
        raise ExperimentStateError(
            f"Cannot generate summary: experiment status is {state.status!r}, "
            "expected 'complete' or 'concluded'"
        )

    # Read run results
    run_results: dict[str, dict] = {}
    for case in manifest.all_cases():
        results_path = experiment_dir / "runs" / case.id / "results.json"
        if results_path.exists():
            run_results[case.id] = json.loads(
                results_path.read_text(encoding="utf-8")
            )

    # Read diff results
    diff_results: dict[str, dict] = {}
    for comp in manifest.comparisons:
        diff_path = experiment_dir / "diffs" / comp.id / "diff.json"
        if diff_path.exists():
            diff_results[comp.id] = json.loads(
                diff_path.read_text(encoding="utf-8")
            )

    summarized_at = _format_timestamp(_now_factory(now_utc)())
    completed_at = state.completed_at or summarized_at

    summary = _build_summary(
        manifest=manifest,
        run_results=run_results,
        diff_results=diff_results,
        completed_at=completed_at,
        summarized_at=summarized_at,
    )

    # Write outputs
    conclusions_dir = experiment_dir / "conclusions"
    conclusions_dir.mkdir(parents=True, exist_ok=True)

    summary_json_path = conclusions_dir / "summary.json"
    summary_json_path.write_text(json.dumps(summary, indent=2) + "\n")

    summary_md_path = conclusions_dir / "summary.md"
    summary_md_path.write_text(_render_summary_md(summary))

    # Update state artifacts
    state.artifacts["summary_json"] = "conclusions/summary.json"
    state.artifacts["summary_md"] = "conclusions/summary.md"
    save_experiment_state(state, experiment_dir)

    return summary_json_path


# ---------------------------------------------------------------------------
# Summary construction
# ---------------------------------------------------------------------------


def _build_summary(
    manifest: ExperimentManifest,
    run_results: dict[str, dict],
    diff_results: dict[str, dict],
    completed_at: str,
    summarized_at: str,
) -> dict:
    """Build the full summary.json structure."""
    run_summaries = [
        _build_run_summary(case.id, run_results.get(case.id, {}))
        for case in manifest.all_cases()
    ]

    comparison_summaries: dict[str, dict] = {}
    for comp in manifest.comparisons:
        comparison_summaries[comp.id] = _build_comparison_summary(
            comp.id, diff_results.get(comp.id, {})
        )

    key_findings = _build_key_findings(comparison_summaries)
    candidate_anomalies = _detect_anomalies(comparison_summaries, manifest)

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "experiment_id": manifest.id,
        "manifest_file": "manifest.yaml",
        "status": "summarized",
        "completed_at": completed_at,
        "summarized_at": summarized_at,
        "methodology": {
            "baseline_run_id": manifest.baseline.id,
            "variant_run_ids": [v.id for v in manifest.variants],
            "comparison_ids": [c.id for c in manifest.comparisons],
        },
        "runs": run_summaries,
        "comparisons": list(comparison_summaries.values()),
        "key_findings": key_findings,
        "candidate_anomalies": candidate_anomalies,
        "limitations": _build_limitations(manifest),
        "artifacts": {
            "summary_md": "conclusions/summary.md",
            "presentation_html": "presentation/index.html",
        },
    }


def _build_run_summary(case_id: str, results: dict) -> dict:
    """Extract headline metrics from a run's results.json."""
    objective = results.get("objective")
    solver_status = "optimal"  # default assumption for completed runs

    # Try to get solver_status from results if present
    if "solver_status" in results:
        solver_status = results["solver_status"]

    return {
        "id": case_id,
        "run_dir": f"runs/{case_id}",
        "objective": objective,
        "solver_status": solver_status,
    }


def _build_comparison_summary(comparison_id: str, diff: dict) -> dict:
    """Extract headline metrics from a diff.json."""
    obj = diff.get("objective", {})
    objective_delta = obj.get("delta", 0.0)
    pct_objective_delta = obj.get("pct_delta", 0.0)

    top_changes = diff.get("top_changes", [])

    # Extract capacity deltas from var_cap or var_ncap tables
    capacity_deltas: list[dict] = []
    tables = diff.get("tables", {})
    for table_name in ("var_ncap", "var_cap"):
        table = tables.get(table_name, {})
        for pd in table.get("process_deltas", []):
            capacity_deltas.append({
                "metric": table_name,
                "process": pd.get("process", ""),
                "baseline": pd.get("baseline", 0.0),
                "variant": pd.get("variant", 0.0),
                "delta": pd.get("delta", 0.0),
                "pct_delta": pd.get("pct_delta", 0.0),
            })

    # Build headline
    if objective_delta == 0.0 and not top_changes and not capacity_deltas:
        headline = "No material difference"
    elif objective_delta == 0.0:
        headline = "No objective change but capacity/activity shifts observed"
    else:
        direction = "increased" if objective_delta > 0 else "decreased"
        headline = (
            f"Objective {direction} by {abs(objective_delta):.2f} "
            f"({abs(pct_objective_delta):.1f}%)"
        )

    return {
        "id": comparison_id,
        "baseline_run_id": diff.get("baseline", {}).get("run_id", ""),
        "variant_run_id": diff.get("variant", {}).get("run_id", ""),
        "diff_file": f"diffs/{comparison_id}/diff.json",
        "objective_delta": objective_delta,
        "pct_objective_delta": pct_objective_delta,
        "headline": headline,
        "top_changes": top_changes,
        "capacity_deltas": capacity_deltas,
    }


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


def _detect_anomalies(
    comparison_summaries: dict[str, dict],
    manifest: ExperimentManifest,
) -> list[dict]:
    """Detect counterintuitive or unexpected results as candidate anomaly flags."""
    anomalies: list[dict] = []

    for variant in manifest.variants:
        if not variant.hypothesis:
            continue

        h_lower = variant.hypothesis.lower()

        # Find relevant comparisons for this variant
        relevant = [
            comparison_summaries[comp.id]
            for comp in manifest.comparisons
            if comp.variant == variant.id and comp.id in comparison_summaries
        ]

        for comp in relevant:
            delta = comp["objective_delta"]
            has_capacity = bool(comp.get("capacity_deltas"))

            # Hypothesis says "may not change" but there IS a large delta
            non_binding = (
                "may not change" in h_lower or "non-binding" in h_lower
            )
            if non_binding and delta != 0.0:
                anomalies.append({
                    "variant_id": variant.id,
                    "comparison_id": comp["id"],
                    "type": "unexpected_change",
                    "description": (
                        f"Hypothesis suggested no change, but objective "
                        f"delta is {delta:.2f} ({comp['pct_objective_delta']:.1f}%)"
                    ),
                })

            # Hypothesis says "changes cost" but technology mix also changes
            if "cost" in h_lower and has_capacity:
                cap_procs = [cd["process"] for cd in comp.get("capacity_deltas", [])]
                if cap_procs:
                    anomalies.append({
                        "variant_id": variant.id,
                        "comparison_id": comp["id"],
                        "type": "technology_switch",
                        "description": (
                            f"Cost change accompanied by technology mix change: "
                            f"{', '.join(cap_procs[:3])}"
                        ),
                    })

            # Zero delta when non-zero expected
            if (
                "increase" in h_lower or "decrease" in h_lower or "raises" in h_lower
            ) and delta == 0.0:
                anomalies.append({
                    "variant_id": variant.id,
                    "comparison_id": comp["id"],
                    "type": "unexpected_zero",
                    "description": (
                        "Hypothesis expected a change, but no objective delta observed"
                    ),
                })

    return anomalies


# ---------------------------------------------------------------------------
# Key findings
# ---------------------------------------------------------------------------


def _build_key_findings(comparison_summaries: dict[str, dict]) -> list[dict]:
    """Extract key findings from comparison results."""
    findings: list[dict] = []
    finding_num = 0

    for comp_id, comp in comparison_summaries.items():
        delta = comp["objective_delta"]

        if delta == 0.0 and not comp["top_changes"] and not comp["capacity_deltas"]:
            finding_num += 1
            findings.append({
                "id": f"F{finding_num}",
                "statement": f"{comp_id}: No material difference from baseline",
                "evidence_refs": [comp_id],
            })
        else:
            if delta != 0.0:
                finding_num += 1
                direction = "increased" if delta > 0 else "decreased"
                findings.append({
                    "id": f"F{finding_num}",
                    "statement": (
                        f"{comp_id}: Objective {direction} by "
                        f"{abs(delta):.2f} ({abs(comp['pct_objective_delta']):.1f}%)"
                    ),
                    "evidence_refs": [comp_id],
                })

            for cd in comp.get("capacity_deltas", []):
                if cd["delta"] != 0.0:
                    finding_num += 1
                    findings.append({
                        "id": f"F{finding_num}",
                        "statement": (
                            f"{comp_id}: {cd['process']} capacity changed "
                            f"from {cd['baseline']:.1f} to {cd['variant']:.1f}"
                        ),
                        "evidence_refs": [comp_id],
                    })

    return findings


# ---------------------------------------------------------------------------
# Limitations
# ---------------------------------------------------------------------------


def _build_limitations(manifest: ExperimentManifest) -> list[str]:
    """Build list of standard limitations."""
    limitations: list[str] = []

    # Check for single-period models
    case_notes = [
        c.notes for c in manifest.all_cases() if c.notes
    ]
    if any("single" in n.lower() for n in case_notes):
        limitations.append("Single-period model — no temporal dynamics")

    # Generic limitations
    limitations.append("Results are specific to this model configuration")
    limitations.append(
        "Deterministic answers derived from solver output; "
        "no uncertainty quantification"
    )

    return limitations


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _render_summary_md(summary: dict) -> str:
    """Render summary.json as a readable Markdown document."""
    lines: list[str] = []

    lines.append(f"# Experiment: {summary['experiment_id']}")
    lines.append("")

    # Methodology
    meth = summary.get("methodology", {})
    lines.append("## Methodology")
    lines.append("")
    lines.append(f"- **Baseline:** {meth.get('baseline_run_id', 'N/A')}")
    variant_ids = meth.get("variant_run_ids", [])
    lines.append(f"- **Variants:** {', '.join(variant_ids) if variant_ids else 'none'}")
    comp_ids = meth.get("comparison_ids", [])
    lines.append(f"- **Comparisons:** {', '.join(comp_ids) if comp_ids else 'none'}")
    lines.append("")

    # Results table
    runs = summary.get("runs", [])
    if runs:
        lines.append("## Results")
        lines.append("")
        lines.append("| Run | Objective | Solver Status |")
        lines.append("|-----|-----------|---------------|")
        for run in runs:
            obj = run.get("objective")
            obj_str = f"{obj:.2f}" if obj is not None else "N/A"
            lines.append(
                f"| {run['id']} | {obj_str} | {run.get('solver_status', 'N/A')} |"
            )
        lines.append("")

    # Comparisons
    comparisons = summary.get("comparisons", [])
    if comparisons:
        lines.append("## Comparisons")
        lines.append("")
        for comp in comparisons:
            lines.append(f"### {comp['id']}")
            delta = comp.get("objective_delta", 0.0)
            pct = comp.get("pct_objective_delta", 0.0)
            lines.append(f"- **Headline:** {comp.get('headline', 'N/A')}")
            lines.append(f"- **Objective delta:** {delta:.2f} ({pct:.1f}%)")
            if comp.get("capacity_deltas"):
                lines.append("- **Capacity changes:**")
                for cd in comp["capacity_deltas"]:
                    lines.append(
                        f"  - {cd['process']}: "
                        f"{cd['baseline']:.1f} → {cd['variant']:.1f} "
                        f"(Δ{cd['delta']:.1f})"
                    )
            lines.append("")

    # Key findings
    findings = summary.get("key_findings", [])
    if findings:
        lines.append("## Key Findings")
        lines.append("")
        for f in findings:
            lines.append(f"{f['id']}. {f['statement']}")
        lines.append("")

    # Candidate anomalies
    anomalies = summary.get("candidate_anomalies", [])
    if anomalies:
        lines.append("## Candidate Anomalies")
        lines.append("")
        for a in anomalies:
            lines.append(f"- {a['description']}")
        lines.append("")

    # Limitations
    limitations = summary.get("limitations", [])
    if limitations:
        lines.append("## Limitations")
        lines.append("")
        for lim in limitations:
            lines.append(f"- {lim}")
        lines.append("")

    return "\n".join(lines)
