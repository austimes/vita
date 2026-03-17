"""Compare two Vita run artifacts and compute deterministic deltas."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vita.run_artifacts import (
    RunArtifactError,
    RunManifest,
    load_run_manifest,
    resolve_run_artifacts,
)

TABLE_METRIC_SPECS: dict[str, tuple[str, ...]] = {
    "var_act": ("region", "year", "process", "timeslice"),
    "var_ncap": ("region", "year", "process"),
    "var_cap": ("region", "year", "process"),
    "var_flo": ("region", "year", "process", "commodity", "timeslice"),
}

SUPPORTED_METRICS = (
    "objective",
    "objective_breakdown",
    *TABLE_METRIC_SPECS.keys(),
)


class RunDiffError(ValueError):
    """Raised when diff inputs are invalid or cannot be compared."""


@dataclass(frozen=True)
class LoadedRunArtifacts:
    """Resolved run artifact payload needed for diffing."""

    run_dir: Path
    manifest: RunManifest
    results_payload: Mapping[str, Any]
    results_path: Path


def compare_run_artifacts(
    baseline_run_dir: Path,
    variant_run_dir: Path,
    *,
    metrics: Iterable[str] | None = None,
    focus_processes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Compare two Vita run artifact directories and return a JSON-safe payload."""
    selected_metrics = _normalize_metrics(metrics)
    focus = _normalize_process_focus(focus_processes)

    baseline = _load_run_artifacts(baseline_run_dir)
    variant = _load_run_artifacts(variant_run_dir)

    payload: dict[str, Any] = {
        "baseline": _run_identity_payload(baseline),
        "variant": _run_identity_payload(variant),
        "metrics": selected_metrics,
        "focus_processes": sorted(focus),
        "tables": {},
        "top_changes": [],
    }

    if "objective" in selected_metrics:
        baseline_obj = _extract_objective(baseline)
        variant_obj = _extract_objective(variant)
        payload["objective"] = _build_scalar_delta(baseline_obj, variant_obj)

    if "objective_breakdown" in selected_metrics:
        payload["objective_breakdown"] = _build_objective_breakdown_delta(
            baseline.results_payload,
            variant.results_payload,
        )

    top_changes: list[dict[str, Any]] = []
    for metric, key_fields in TABLE_METRIC_SPECS.items():
        if metric not in selected_metrics:
            continue
        table_delta = _build_table_delta(
            metric=metric,
            key_fields=key_fields,
            baseline_rows=baseline.results_payload.get(metric),
            variant_rows=variant.results_payload.get(metric),
            focus_processes=focus,
        )
        payload["tables"][metric] = table_delta
        for row in table_delta["rows"]:
            top_changes.append(
                {
                    "metric": metric,
                    "status": row["status"],
                    "key": row["key"],
                    "baseline_level": row["baseline_level"],
                    "variant_level": row["variant_level"],
                    "delta_level": row["delta_level"],
                    "pct_delta": row["pct_delta"],
                }
            )

    top_changes.sort(
        key=lambda row: (-abs(float(row["delta_level"])), _stable_key_tuple(row["key"]))
    )
    payload["top_changes"] = top_changes
    return payload


def format_run_diff_console(diff_payload: Mapping[str, Any], *, limit: int = 20) -> str:
    """Format a run-diff payload for terminal output."""
    baseline = diff_payload.get("baseline")
    variant = diff_payload.get("variant")
    if not isinstance(baseline, Mapping) or not isinstance(variant, Mapping):
        raise RunDiffError("Invalid diff payload: missing baseline/variant identity")

    lines = [
        (
            "Vita Run Diff: "
            f"{baseline.get('run_id', 'baseline')} ({baseline.get('run_dir')}) -> "
            f"{variant.get('run_id', 'variant')} ({variant.get('run_dir')})"
        ),
        "=" * 80,
    ]

    objective = diff_payload.get("objective")
    if isinstance(objective, Mapping):
        lines.append(
            "Objective: "
            f"baseline={_fmt_float(objective.get('baseline'))} "
            f"variant={_fmt_float(objective.get('variant'))} "
            f"delta={_fmt_signed(objective.get('delta'))} "
            f"pct={_fmt_pct(objective.get('pct_delta'))}"
        )

    objective_breakdown = diff_payload.get("objective_breakdown")
    if isinstance(objective_breakdown, Mapping):
        rows = objective_breakdown.get("rows")
        if isinstance(rows, list) and rows:
            lines.append("")
            lines.append("Objective Breakdown")
            lines.append("-------------------")
            for row in rows[:limit]:
                if not isinstance(row, Mapping):
                    continue
                component = row.get("component", "(unknown)")
                delta = _fmt_signed(row.get("delta"))
                status = row.get("status")
                lines.append(f"{component}: {delta} ({status})")
            if len(rows) > limit:
                lines.append(f"... showing {limit} of {len(rows)} components")

    tables = diff_payload.get("tables")
    if isinstance(tables, Mapping):
        for metric in TABLE_METRIC_SPECS:
            table_delta = tables.get(metric)
            if not isinstance(table_delta, Mapping):
                continue
            lines.append("")
            lines.append(metric.upper())
            lines.append("-" * len(metric))

            totals = table_delta.get("totals")
            status_counts = table_delta.get("status_counts")
            if isinstance(totals, Mapping):
                lines.append(
                    "Totals: "
                    f"baseline={_fmt_float(totals.get('baseline'))} "
                    f"variant={_fmt_float(totals.get('variant'))} "
                    f"delta={_fmt_signed(totals.get('delta'))} "
                    f"pct={_fmt_pct(totals.get('pct_delta'))}"
                )
            if isinstance(status_counts, Mapping):
                lines.append(
                    "Rows: "
                    f"changed={status_counts.get('changed', 0)} "
                    f"added={status_counts.get('added', 0)} "
                    f"removed={status_counts.get('removed', 0)}"
                )

            rows = table_delta.get("rows")
            if not isinstance(rows, list) or not rows:
                lines.append("(no changed rows)")
                continue

            for row in rows[:limit]:
                if not isinstance(row, Mapping):
                    continue
                key = row.get("key")
                key_text = _format_row_key(key)
                lines.append(
                    f"{key_text}: delta={_fmt_signed(row.get('delta_level'))} "
                    f"pct={_fmt_pct(row.get('pct_delta'))} "
                    f"status={row.get('status')}"
                )
            if len(rows) > limit:
                lines.append(f"... showing {limit} of {len(rows)} changed rows")

    return "\n".join(lines)


def _load_run_artifacts(run_dir: Path) -> LoadedRunArtifacts:
    try:
        paths = resolve_run_artifacts(run_dir, require_results=True)
    except RunArtifactError as exc:
        raise RunDiffError(str(exc)) from exc

    manifest = load_run_manifest(paths.manifest_path)
    try:
        payload = json.loads(paths.results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunDiffError(
            f"Invalid results JSON: {paths.results_path}: {exc}"
        ) from exc

    if not isinstance(payload, Mapping):
        raise RunDiffError(
            "Invalid results payload: "
            f"expected object in {paths.results_path}"
        )

    return LoadedRunArtifacts(
        run_dir=paths.run_dir,
        manifest=manifest,
        results_payload=payload,
        results_path=paths.results_path,
    )


def _run_identity_payload(run: LoadedRunArtifacts) -> dict[str, Any]:
    return {
        "run_dir": str(run.run_dir.resolve()),
        "run_id": run.manifest.run_id,
        "case": run.manifest.case,
        "timestamp": run.manifest.timestamp,
        "solver_status": run.manifest.solver_status,
        "results_file": str(run.results_path.resolve()),
    }


def _build_scalar_delta(
    baseline_value: float | None,
    variant_value: float | None,
) -> dict[str, float | None]:
    if baseline_value is None and variant_value is None:
        return {
            "baseline": None,
            "variant": None,
            "delta": None,
            "pct_delta": None,
            "status": "missing",
        }

    baseline = baseline_value or 0.0
    variant = variant_value or 0.0
    delta = variant - baseline
    status = "changed"
    if baseline_value is None:
        status = "added"
    elif variant_value is None:
        status = "removed"
    elif abs(delta) <= 1e-12:
        status = "unchanged"

    return {
        "baseline": baseline_value,
        "variant": variant_value,
        "delta": delta,
        "pct_delta": _pct_delta(baseline, variant),
        "status": status,
    }


def _build_objective_breakdown_delta(
    baseline_payload: Mapping[str, Any],
    variant_payload: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_breakdown = _extract_breakdown_map(baseline_payload)
    variant_breakdown = _extract_breakdown_map(variant_payload)

    components = sorted(set(baseline_breakdown) | set(variant_breakdown))
    rows: list[dict[str, Any]] = []
    status_counts = {"changed": 0, "added": 0, "removed": 0}

    for component in components:
        baseline = baseline_breakdown.get(component)
        variant = variant_breakdown.get(component)
        baseline_value = baseline if baseline is not None else 0.0
        variant_value = variant if variant is not None else 0.0
        delta = variant_value - baseline_value
        if abs(delta) <= 1e-12:
            continue

        status = "changed"
        if baseline is None:
            status = "added"
        elif variant is None:
            status = "removed"

        status_counts[status] += 1
        rows.append(
            {
                "component": component,
                "baseline": baseline,
                "variant": variant,
                "delta": delta,
                "pct_delta": _pct_delta(baseline_value, variant_value),
                "status": status,
            }
        )

    rows.sort(key=lambda row: (-abs(float(row["delta"])), str(row["component"])))
    baseline_total = sum(baseline_breakdown.values())
    variant_total = sum(variant_breakdown.values())
    return {
        "rows": rows,
        "status_counts": status_counts,
        "totals": {
            "baseline": baseline_total,
            "variant": variant_total,
            "delta": variant_total - baseline_total,
            "pct_delta": _pct_delta(baseline_total, variant_total),
        },
    }


def _build_table_delta(
    *,
    metric: str,
    key_fields: tuple[str, ...],
    baseline_rows: Any,
    variant_rows: Any,
    focus_processes: set[str],
) -> dict[str, Any]:
    baseline_index = _index_rows(
        baseline_rows,
        key_fields=key_fields,
        focus=focus_processes,
    )
    variant_index = _index_rows(
        variant_rows,
        key_fields=key_fields,
        focus=focus_processes,
    )

    all_keys = sorted(set(baseline_index) | set(variant_index))
    rows: list[dict[str, Any]] = []
    status_counts = {"changed": 0, "added": 0, "removed": 0}
    process_index: dict[str, dict[str, float]] = defaultdict(
        lambda: {"baseline": 0.0, "variant": 0.0, "delta": 0.0}
    )

    for key in all_keys:
        baseline = baseline_index.get(key)
        variant = variant_index.get(key)
        baseline_value = baseline if baseline is not None else 0.0
        variant_value = variant if variant is not None else 0.0
        delta_value = variant_value - baseline_value

        if abs(delta_value) <= 1e-12:
            continue

        status = "changed"
        if baseline is None:
            status = "added"
        elif variant is None:
            status = "removed"

        status_counts[status] += 1

        key_payload = {field: key[idx] for idx, field in enumerate(key_fields)}
        rows.append(
            {
                "key": key_payload,
                "baseline_level": baseline,
                "variant_level": variant,
                "delta_level": delta_value,
                "pct_delta": _pct_delta(baseline_value, variant_value),
                "status": status,
            }
        )

        process = str(key_payload.get("process") or "")
        if process:
            process_delta = process_index[process]
            process_delta["baseline"] += baseline_value
            process_delta["variant"] += variant_value
            process_delta["delta"] += delta_value

    rows.sort(
        key=lambda row: (-abs(float(row["delta_level"])), _stable_key_tuple(row["key"]))
    )

    process_deltas: list[dict[str, Any]] = []
    for process, aggregates in process_index.items():
        process_deltas.append(
            {
                "process": process,
                "baseline": aggregates["baseline"],
                "variant": aggregates["variant"],
                "delta": aggregates["delta"],
                "pct_delta": _pct_delta(aggregates["baseline"], aggregates["variant"]),
            }
        )
    process_deltas.sort(
        key=lambda row: (-abs(float(row["delta"])), str(row["process"]))
    )

    baseline_total = sum(baseline_index.values())
    variant_total = sum(variant_index.values())
    return {
        "metric": metric,
        "key_fields": list(key_fields),
        "baseline_row_count": len(baseline_index),
        "variant_row_count": len(variant_index),
        "changed_row_count": len(rows),
        "status_counts": status_counts,
        "totals": {
            "baseline": baseline_total,
            "variant": variant_total,
            "delta": variant_total - baseline_total,
            "pct_delta": _pct_delta(baseline_total, variant_total),
        },
        "process_deltas": process_deltas,
        "rows": rows,
    }


def _normalize_metrics(metrics: Iterable[str] | None) -> list[str]:
    if metrics is None:
        return list(SUPPORTED_METRICS)

    normalized: list[str] = []
    for metric in metrics:
        value = metric.strip()
        if not value:
            continue
        if value not in SUPPORTED_METRICS:
            supported = ", ".join(SUPPORTED_METRICS)
            raise RunDiffError(
                f"Unsupported metric {value!r}; expected one of: {supported}"
            )
        if value not in normalized:
            normalized.append(value)

    if not normalized:
        raise RunDiffError("At least one metric must be selected")
    return normalized


def _normalize_process_focus(processes: Iterable[str] | None) -> set[str]:
    if processes is None:
        return set()

    normalized: set[str] = set()
    for process in processes:
        value = process.strip().lower()
        if value:
            normalized.add(value)
    return normalized


def _extract_objective(run: LoadedRunArtifacts) -> float | None:
    payload_value = _as_float(run.results_payload.get("objective"))
    if payload_value is not None:
        return payload_value
    return run.manifest.objective


def _extract_breakdown_map(payload: Mapping[str, Any]) -> dict[str, float]:
    value = payload.get("objective_breakdown")
    if not isinstance(value, Mapping):
        return {}

    normalized: dict[str, float] = {}
    for key, component in value.items():
        numeric = _as_float(component)
        if numeric is None:
            continue
        normalized[str(key)] = numeric
    return normalized


def _index_rows(
    rows: Any,
    *,
    key_fields: tuple[str, ...],
    focus: set[str],
) -> dict[tuple[str, ...], float]:
    if not isinstance(rows, list):
        return {}

    indexed: dict[tuple[str, ...], float] = defaultdict(float)
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue

        process = _as_text(raw.get("process"))
        if focus and process.lower() not in focus:
            continue

        level = _as_float(raw.get("level"))
        if level is None:
            continue

        key = tuple(_as_text(raw.get(field)) for field in key_fields)
        indexed[key] += level
    return dict(indexed)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _pct_delta(baseline: float, variant: float) -> float | None:
    if abs(baseline) <= 1e-12:
        if abs(variant) <= 1e-12:
            return 0.0
        return None
    return ((variant - baseline) / abs(baseline)) * 100.0


def _stable_key_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(f"{key}:{value[key]}" for key in sorted(value))
    return (str(value),)


def _format_row_key(key: Any) -> str:
    if not isinstance(key, Mapping):
        return str(key)
    ordered = [f"{field}={key[field]}" for field in sorted(key)]
    return ", ".join(ordered)


def _fmt_float(value: Any) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.4f}"


def _fmt_signed(value: Any) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:+.4f}"


def _fmt_pct(value: Any) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:+.2f}%"
