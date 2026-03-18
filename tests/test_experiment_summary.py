"""Tests for vita.experiment_summary module."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from vita.experiment_manifest import (
    load_experiment_manifest,
)
from vita.experiment_state import (
    create_experiment_state,
    load_experiment_state,
    save_experiment_state,
)
from vita.experiment_summary import (
    _build_comparison_summary,
    _build_key_findings,
    _build_run_summary,
    _detect_anomalies,
    _render_summary_md,
    generate_summary,
)
from vita.run_artifacts import RunManifest, write_run_manifest

# ---------------------------------------------------------------------------
# Fixtures — based on toy_industry structure
# ---------------------------------------------------------------------------

_FIXED_TS = datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC)
_FIXED_NOW = lambda: _FIXED_TS  # noqa: E731


_MINIMAL_MODEL = """\
vedalang: "0.5"
id: test_model
title: Test Model
regions: [SINGLE]
time_horizon: {start: 2025, periods: [{years: 2025}]}
commodities: []
technology_roles: []
"""

_MANIFEST_DICT = {
    "schema_version": 1,
    "id": "toy_industry",
    "title": "Toy Industry Experiment",
    "question": "How do different input assumptions affect system cost?",
    "extensions": [
        {"id": "A", "question": "What happens with a CO2 cap?"},
        {"id": "B", "question": "Which CAPEX variant has the largest cost impact?"},
    ],
    "baseline": {
        "id": "baseline",
        "model": "model.veda.yaml",
        "run": "single_2025",
    },
    "variants": [
        {
            "id": "co2_cap",
            "from": "baseline",
            "hypothesis": "CO2 cap may not change the result if non-binding",
        },
        {
            "id": "high_gas_capex",
            "from": "baseline",
            "hypothesis": "Higher gas CAPEX raises cost and changes technology mix",
        },
        {
            "id": "high_h2_capex",
            "from": "baseline",
            "hypothesis": "Higher H2 CAPEX increases cost",
        },
    ],
    "comparisons": [
        {
            "id": "baseline_vs_co2_cap",
            "baseline": "baseline",
            "variant": "co2_cap",
        },
        {
            "id": "baseline_vs_high_gas_capex",
            "baseline": "baseline",
            "variant": "high_gas_capex",
        },
        {
            "id": "baseline_vs_high_h2_capex",
            "baseline": "baseline",
            "variant": "high_h2_capex",
        },
    ],
    "analyses": [
        {
            "id": "A",
            "question": "What happens with a CO2 cap?",
            "comparisons": ["baseline_vs_co2_cap"],
        },
        {
            "id": "B",
            "question": "Which CAPEX variant has the largest cost impact?",
            "comparisons": ["baseline_vs_high_gas_capex", "baseline_vs_high_h2_capex"],
            "rank_by": "objective_delta",
        },
    ],
}


def _make_results(objective: float) -> dict:
    return {
        "objective": objective,
        "objective_breakdown": {"OBJINV": objective, "OBJFIX": 0.0},
        "var_act": [],
        "var_ncap": [],
        "var_cap": [],
        "var_flo": [],
    }


def _make_diff(
    *,
    baseline_obj: float,
    variant_obj: float,
    top_changes: list | None = None,
    process_deltas_ncap: list | None = None,
) -> dict:
    delta = variant_obj - baseline_obj
    pct = (delta / baseline_obj * 100.0) if baseline_obj != 0 else 0.0
    status = "unchanged" if delta == 0.0 else "changed"
    tables: dict = {
        "var_act": {
            "metric": "var_act",
            "key_fields": ["region", "year", "process", "timeslice"],
            "process_deltas": [],
            "rows": [],
            "totals": {"baseline": 0, "variant": 0, "delta": 0, "pct_delta": 0},
        },
        "var_ncap": {
            "metric": "var_ncap",
            "key_fields": ["region", "year", "process"],
            "process_deltas": process_deltas_ncap or [],
            "rows": [],
            "totals": {"baseline": 0, "variant": 0, "delta": 0, "pct_delta": 0},
        },
        "var_cap": {
            "metric": "var_cap",
            "key_fields": ["region", "year", "process"],
            "process_deltas": [],
            "rows": [],
            "totals": {"baseline": 0, "variant": 0, "delta": 0, "pct_delta": 0},
        },
        "var_flo": {
            "metric": "var_flo",
            "key_fields": ["region", "year", "process", "commodity", "timeslice"],
            "process_deltas": [],
            "rows": [],
            "totals": {"baseline": 0, "variant": 0, "delta": 0, "pct_delta": 0},
        },
    }
    return {
        "baseline": {
            "run_dir": "/tmp/baseline",
            "run_id": "single_2025",
            "case": "scenario",
            "timestamp": "2026-03-18T00:38:12Z",
            "solver_status": "optimal",
        },
        "variant": {
            "run_dir": "/tmp/variant",
            "run_id": "single_2025",
            "case": "scenario",
            "timestamp": "2026-03-18T00:38:37Z",
            "solver_status": "optimal",
        },
        "metrics": [
            "objective", "objective_breakdown",
            "var_act", "var_ncap", "var_cap", "var_flo",
        ],
        "focus_processes": [],
        "top_changes": top_changes or [],
        "objective": {
            "baseline": baseline_obj,
            "variant": variant_obj,
            "delta": delta,
            "pct_delta": pct,
            "status": status,
        },
        "tables": tables,
    }


@pytest.fixture()
def experiment_dir(tmp_path: Path) -> Path:
    """Create a complete experiment directory with runs/diffs populated."""
    exp_dir = tmp_path / "toy_industry"
    exp_dir.mkdir()

    # Model file
    model_path = tmp_path / "model.veda.yaml"
    model_path.write_text(_MINIMAL_MODEL)

    # Write manifest
    manifest_path = exp_dir / "manifest.yaml"
    manifest_path.write_text(yaml.dump(_MANIFEST_DICT))

    # Write run manifests and results
    cases = {
        "baseline": 195.59,
        "co2_cap": 195.59,
        "high_gas_capex": 452.95,
        "high_h2_capex": 241.92,
    }
    for case_id, objective in cases.items():
        run_dir = exp_dir / "runs" / case_id
        run_dir.mkdir(parents=True)
        rm = RunManifest(
            run_id="single_2025",
            source="model.veda.yaml",
            case="scenario",
            timestamp="2026-03-18T00:38:12Z",
            solver_status="optimal",
            objective=objective,
            pipeline_success=True,
        )
        write_run_manifest(rm, run_dir / "manifest.json")
        (run_dir / "results.json").write_text(
            json.dumps(_make_results(objective), indent=2) + "\n"
        )

    # Write diffs
    diffs = {
        "baseline_vs_co2_cap": _make_diff(baseline_obj=195.59, variant_obj=195.59),
        "baseline_vs_high_gas_capex": _make_diff(
            baseline_obj=195.59, variant_obj=452.95
        ),
        "baseline_vs_high_h2_capex": _make_diff(
            baseline_obj=195.59,
            variant_obj=241.92,
            top_changes=[{
                "metric": "var_ncap",
                "status": "changed",
                "key": {"region": "SINGLE", "year": "2025", "process": "H2_BOILER"},
                "baseline_level": 100.0,
                "variant_level": 280.0,
                "delta_level": 180.0,
                "pct_delta": 180.0,
            }],
            process_deltas_ncap=[{
                "process": "H2_BOILER",
                "baseline": 100.0,
                "variant": 280.0,
                "delta": 180.0,
                "pct_delta": 180.0,
            }],
        ),
    }
    for diff_id, diff_data in diffs.items():
        diff_dir = exp_dir / "diffs" / diff_id
        diff_dir.mkdir(parents=True)
        (diff_dir / "diff.json").write_text(
            json.dumps(diff_data, indent=2) + "\n"
        )

    # Create state.json with status=complete
    run_ids = ["baseline", "co2_cap", "high_gas_capex", "high_h2_capex"]
    comparison_ids = list(diffs.keys())
    state = create_experiment_state(
        experiment_dir=exp_dir,
        experiment_id="toy_industry",
        manifest_file="manifest.yaml",
        run_ids=run_ids,
        comparison_ids=comparison_ids,
        now_utc=_FIXED_NOW,
    )
    # Manually transition to complete
    state.status = "complete"
    state.completed_at = "2026-03-18T12:00:00Z"
    for rid in run_ids:
        state.run_statuses[rid] = "complete"
    for cid in comparison_ids:
        state.diff_statuses[cid] = "complete"
    state.progress.runs_complete = len(run_ids)
    state.progress.diffs_complete = len(comparison_ids)
    save_experiment_state(state, exp_dir)

    return exp_dir


# ---------------------------------------------------------------------------
# generate_summary (integration)
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    def test_generates_files(self, experiment_dir: Path):
        summary_path = generate_summary(
            experiment_dir, now_utc=_FIXED_NOW
        )
        assert summary_path.exists()
        assert (experiment_dir / "conclusions" / "summary.md").exists()

    def test_summary_json_structure(self, experiment_dir: Path):
        summary_path = generate_summary(
            experiment_dir, now_utc=_FIXED_NOW
        )
        summary = json.loads(summary_path.read_text())

        assert summary["schema_version"] == "vita-experiment-summary/v1"
        assert summary["experiment_id"] == "toy_industry"
        assert summary["status"] == "summarized"
        assert "methodology" in summary
        assert "runs" in summary
        assert "comparisons" in summary
        assert "key_findings" in summary
        assert "candidate_anomalies" in summary
        assert "limitations" in summary
        assert "artifacts" in summary
        # Interpretive fields must NOT be present
        assert "answers" not in summary
        assert "hypothesis_outcomes" not in summary
        assert "surprises" not in summary

    def test_all_runs_present(self, experiment_dir: Path):
        summary_path = generate_summary(
            experiment_dir, now_utc=_FIXED_NOW
        )
        summary = json.loads(summary_path.read_text())

        run_ids = {r["id"] for r in summary["runs"]}
        assert run_ids == {"baseline", "co2_cap", "high_gas_capex", "high_h2_capex"}

    def test_updates_state_artifacts(self, experiment_dir: Path):
        generate_summary(experiment_dir, now_utc=_FIXED_NOW)
        state = load_experiment_state(experiment_dir)
        assert state.artifacts["summary_json"] == "conclusions/summary.json"
        assert state.artifacts["summary_md"] == "conclusions/summary.md"

    def test_rejects_non_complete_state(self, experiment_dir: Path):
        state = load_experiment_state(experiment_dir)
        state.status = "running"
        save_experiment_state(state, experiment_dir)

        with pytest.raises(Exception, match="status is 'running'"):
            generate_summary(experiment_dir, now_utc=_FIXED_NOW)

    def test_summarized_at_field(self, experiment_dir: Path):
        summary_path = generate_summary(
            experiment_dir, now_utc=_FIXED_NOW
        )
        summary = json.loads(summary_path.read_text())
        assert "summarized_at" in summary
        assert "concluded_at" not in summary


# ---------------------------------------------------------------------------
# _build_run_summary
# ---------------------------------------------------------------------------


class TestBuildRunSummary:
    def test_with_objective(self):
        result = _build_run_summary("baseline", {"objective": 195.59})
        assert result["id"] == "baseline"
        assert result["objective"] == 195.59
        assert result["run_dir"] == "runs/baseline"

    def test_empty_results(self):
        result = _build_run_summary("missing", {})
        assert result["id"] == "missing"
        assert result["objective"] is None


# ---------------------------------------------------------------------------
# _build_comparison_summary
# ---------------------------------------------------------------------------


class TestBuildComparisonSummary:
    def test_zero_delta(self):
        diff = _make_diff(baseline_obj=100.0, variant_obj=100.0)
        result = _build_comparison_summary("test_cmp", diff)
        assert result["objective_delta"] == 0.0
        assert "No material difference" in result["headline"]

    def test_positive_delta(self):
        diff = _make_diff(baseline_obj=100.0, variant_obj=150.0)
        result = _build_comparison_summary("test_cmp", diff)
        assert result["objective_delta"] == 50.0
        assert "increased" in result["headline"]

    def test_negative_delta(self):
        diff = _make_diff(baseline_obj=100.0, variant_obj=80.0)
        result = _build_comparison_summary("test_cmp", diff)
        assert result["objective_delta"] == -20.0
        assert "decreased" in result["headline"]

    def test_capacity_deltas_extracted(self):
        diff = _make_diff(
            baseline_obj=100.0,
            variant_obj=150.0,
            process_deltas_ncap=[{
                "process": "PLANT_A",
                "baseline": 50.0,
                "variant": 100.0,
                "delta": 50.0,
                "pct_delta": 100.0,
            }],
        )
        result = _build_comparison_summary("test_cmp", diff)
        assert len(result["capacity_deltas"]) == 1
        assert result["capacity_deltas"][0]["process"] == "PLANT_A"


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


class TestAnomalyDetection:
    def _make_manifest(self, hypothesis: str) -> dict:
        """Build a minimal manifest with one variant having the given hypothesis."""
        d = dict(_MANIFEST_DICT)
        d["variants"] = [{
            "id": "test_var",
            "from": "baseline",
            "hypothesis": hypothesis,
        }]
        d["comparisons"] = [{
            "id": "baseline_vs_test_var",
            "baseline": "baseline",
            "variant": "test_var",
        }]
        d["analyses"] = []
        return d  # return raw dict for later parsing

    def test_unexpected_change_when_non_binding(self, tmp_path: Path):
        manifest_dict = self._make_manifest("may not change the result")
        model_path = tmp_path / "model.veda.yaml"
        model_path.write_text(_MINIMAL_MODEL)
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest_dict))
        manifest = load_experiment_manifest(manifest_path)

        comps = {
            "baseline_vs_test_var": _build_comparison_summary(
                "baseline_vs_test_var", _make_diff(baseline_obj=100, variant_obj=120)
            ),
        }
        anomalies = _detect_anomalies(comps, manifest)
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "unexpected_change"

    def test_no_anomaly_when_expected(self, tmp_path: Path):
        manifest_dict = self._make_manifest("may not change the result")
        model_path = tmp_path / "model.veda.yaml"
        model_path.write_text(_MINIMAL_MODEL)
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest_dict))
        manifest = load_experiment_manifest(manifest_path)

        comps = {
            "baseline_vs_test_var": _build_comparison_summary(
                "baseline_vs_test_var", _make_diff(baseline_obj=100, variant_obj=100)
            ),
        }
        anomalies = _detect_anomalies(comps, manifest)
        assert len(anomalies) == 0

    def test_unexpected_zero(self, tmp_path: Path):
        manifest_dict = self._make_manifest("Higher cost increases objective")
        model_path = tmp_path / "model.veda.yaml"
        model_path.write_text(_MINIMAL_MODEL)
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest_dict))
        manifest = load_experiment_manifest(manifest_path)

        comps = {
            "baseline_vs_test_var": _build_comparison_summary(
                "baseline_vs_test_var", _make_diff(baseline_obj=100, variant_obj=100)
            ),
        }
        anomalies = _detect_anomalies(comps, manifest)
        assert any(a["type"] == "unexpected_zero" for a in anomalies)


# ---------------------------------------------------------------------------
# Key findings
# ---------------------------------------------------------------------------


class TestKeyFindings:
    def test_zero_delta_finding(self):
        diff = _make_diff(baseline_obj=100, variant_obj=100)
        comps = {
            "cmp1": _build_comparison_summary("cmp1", diff),
        }
        findings = _build_key_findings(comps)
        assert len(findings) == 1
        assert "No material difference" in findings[0]["statement"]

    def test_nonzero_delta_finding(self):
        diff = _make_diff(baseline_obj=100, variant_obj=150)
        comps = {
            "cmp1": _build_comparison_summary("cmp1", diff),
        }
        findings = _build_key_findings(comps)
        assert any("increased" in f["statement"] for f in findings)

    def test_capacity_delta_finding(self):
        diff = _make_diff(
            baseline_obj=100,
            variant_obj=150,
            process_deltas_ncap=[{
                "process": "PLANT_X",
                "baseline": 50, "variant": 100, "delta": 50, "pct_delta": 100,
            }],
        )
        comps = {"cmp1": _build_comparison_summary("cmp1", diff)}
        findings = _build_key_findings(comps)
        assert any("PLANT_X" in f["statement"] for f in findings)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


class TestRenderSummaryMd:
    def test_contains_key_sections(self, experiment_dir: Path):
        summary_path = generate_summary(
            experiment_dir, now_utc=_FIXED_NOW
        )
        summary = json.loads(summary_path.read_text())
        md = _render_summary_md(summary)

        assert "# Experiment:" in md
        assert "## Methodology" in md
        assert "## Results" in md
        assert "## Comparisons" in md
        assert "## Key Findings" in md
        assert "## Limitations" in md
        # Interpretive sections must NOT be present
        assert "## Answers" not in md
        assert "## Hypothesis Outcomes" not in md
        assert "## Surprises" not in md

    def test_runs_table(self, experiment_dir: Path):
        summary_path = generate_summary(
            experiment_dir, now_utc=_FIXED_NOW
        )
        summary = json.loads(summary_path.read_text())
        md = _render_summary_md(summary)

        assert "| baseline |" in md
        assert "| co2_cap |" in md
        assert "195.59" in md

    def test_empty_summary_renders(self):
        minimal_summary = {
            "experiment_id": "test",
            "runs": [],
            "comparisons": [],
            "key_findings": [],
            "candidate_anomalies": [],
            "limitations": [],
        }
        md = _render_summary_md(minimal_summary)
        assert "# Experiment: test" in md
