"""Tests for vita.experiment_validation module."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from vita.experiment_manifest import load_experiment_manifest
from vita.experiment_validation import (
    ValidationResult,
    render_brief_md,
    render_interpretation_md,
    validate_brief,
    validate_interpretation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    "id": "test_experiment",
    "title": "Test Experiment",
    "question": "What happens when we change X?",
    "extensions": [{"id": "A", "question": "Sub-question A?"}],
    "baseline": {"id": "baseline", "model": "model.veda.yaml", "run": "run1"},
    "variants": [
        {
            "id": "variant_a",
            "from": "baseline",
            "hypothesis": "X increases cost",
        },
    ],
    "comparisons": [
        {
            "id": "baseline_vs_variant_a",
            "baseline": "baseline",
            "variant": "variant_a",
        },
    ],
    "analyses": [
        {
            "id": "A",
            "question": "Sub-question A?",
            "comparisons": ["baseline_vs_variant_a"],
        },
    ],
}

_LONG_TEXT = "This is a sufficiently long substantive text for validation checks."
_LONG_TEXT_32 = "This text is long enough for thirty-two character minimum checks easily."


def _make_manifest(tmp_path: Path) -> "ExperimentManifest":
    """Write manifest + model to tmp_path and load."""
    model_path = tmp_path / "model.veda.yaml"
    model_path.write_text(_MINIMAL_MODEL)
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.dump(_MANIFEST_DICT))
    return load_experiment_manifest(manifest_path)


def _make_valid_brief() -> dict:
    """Build a minimal valid brief dict matching _MANIFEST_DICT."""
    return {
        "schema_version": "vita-experiment-brief/v1",
        "experiment_id": "test_experiment",
        "manifest_file": "manifest.yaml",
        "created_at": "2026-03-18T12:00:00Z",
        "research": {
            "question": "What happens when we change X?",
            "scope": _LONG_TEXT,
        },
        "design_summary": {
            "approach": _LONG_TEXT,
            "variant_ids": ["variant_a"],
            "comparison_ids": ["baseline_vs_variant_a"],
        },
        "variants": [
            {
                "variant_id": "variant_a",
                "change_summary": _LONG_TEXT,
                "why_this_variant": _LONG_TEXT,
                "hypothesis": {
                    "statement": _LONG_TEXT,
                    "expected_direction": "increase",
                    "mechanism_chains": [
                        {
                            "id": "M1",
                            "cause": _LONG_TEXT,
                            "effect": _LONG_TEXT,
                            "because": _LONG_TEXT,
                        },
                    ],
                    "confirmation_criteria": [
                        {
                            "id": "C1",
                            "description": "Cost increases by more than 5%",
                            "signals": [
                                {
                                    "metric": "objective",
                                    "expected_direction": "increase",
                                },
                            ],
                        },
                    ],
                    "refutation_criteria": [
                        {
                            "id": "R1",
                            "description": "Cost stays flat or decreases",
                        },
                    ],
                },
            },
        ],
        "comparison_plan": [
            {
                "comparison_id": "baseline_vs_variant_a",
                "purpose": _LONG_TEXT,
                "metrics_of_interest": [
                    {
                        "metric": "objective",
                        "priority": "primary",
                        "why_it_matters": "Main cost indicator",
                    },
                ],
            },
        ],
        "design_reasoning_steps": [
            {
                "id": "P1",
                "kind": "question_framing",
                "statement": _LONG_TEXT,
            },
        ],
    }


def _make_valid_interpretation() -> dict:
    """Build a minimal valid interpretation dict matching _MANIFEST_DICT."""
    return {
        "schema_version": "vita-experiment-interpretation/v1",
        "experiment_id": "test_experiment",
        "summary_file": "conclusions/summary.json",
        "created_at": "2026-03-18T13:00:00Z",
        "research_question": "What happens when we change X?",
        "executive_summary": {
            "short_answer": _LONG_TEXT_32,
            "answer": _LONG_TEXT_32,
            "confidence": "high",
            "evidence_refs": ["E1"],
            "supporting_step_ids": ["baseline_vs_variant_a.R1"],
        },
        "evidence_index": [
            {
                "id": "E1",
                "kind": "comparison_metric",
                "comparison_id": "baseline_vs_variant_a",
                "metric": "objective",
                "source_file": "diffs/baseline_vs_variant_a/diff.json",
            },
            {
                "id": "E2",
                "kind": "run_metric",
                "metric": "objective",
                "source_file": "runs/baseline/results.json",
            },
        ],
        "question_answers": [
            {
                "question_id": "Q",
                "question": "What happens when we change X?",
                "comparison_ids": ["baseline_vs_variant_a"],
                "short_answer": _LONG_TEXT_32,
                "answer": _LONG_TEXT_32,
                "confidence": "high",
                "uncertainty": "None significant",
                "evidence_refs": ["E1"],
                "supporting_step_ids": ["baseline_vs_variant_a.R3"],
            },
            {
                "question_id": "A",
                "question": "Sub-question A?",
                "comparison_ids": ["baseline_vs_variant_a"],
                "short_answer": _LONG_TEXT_32,
                "answer": _LONG_TEXT_32,
                "confidence": "medium",
                "uncertainty": "Some uncertainty remains",
                "evidence_refs": ["E2"],
                "supporting_step_ids": ["baseline_vs_variant_a.R3"],
            },
        ],
        "comparison_interpretations": [
            {
                "comparison_id": "baseline_vs_variant_a",
                "takeaway": _LONG_TEXT_32,
                "hypothesis_assessment": {
                    "status": "supports",
                    "rationale": _LONG_TEXT_32,
                },
                "key_evidence_refs": ["E1", "E2"],
                "reasoning_steps": [
                    {
                        "id": "baseline_vs_variant_a.R1",
                        "kind": "observation",
                        "statement": _LONG_TEXT_32,
                        "evidence_refs": ["E1"],
                        "depends_on": [],
                    },
                    {
                        "id": "baseline_vs_variant_a.R2",
                        "kind": "mechanism",
                        "statement": _LONG_TEXT_32,
                        "evidence_refs": ["E2"],
                        "depends_on": ["baseline_vs_variant_a.R1"],
                    },
                    {
                        "id": "baseline_vs_variant_a.R3",
                        "kind": "conclusion",
                        "statement": _LONG_TEXT_32,
                        "evidence_refs": ["E1", "E2"],
                        "depends_on": ["baseline_vs_variant_a.R2"],
                    },
                ],
                "primary_mechanism": _LONG_TEXT_32,
                "alternative_mechanisms": [],
                "confidence": "high",
                "surprises": [],
            },
        ],
        "cross_comparison_synthesis": {
            "overall_pattern": "Cost increases as expected",
            "open_questions": [],
            "limits": ["Single-period model"],
        },
    }


def _make_summary() -> dict:
    """Minimal summary.json for interpretation validation."""
    return {
        "schema_version": "vita-experiment-summary/v1",
        "experiment_id": "test_experiment",
    }


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_to_dict(self):
        vr = ValidationResult(artifact_kind="brief", valid=True)
        d = vr.to_dict()
        assert d["schema_version"] == "vita-experiment-validation/v1"
        assert d["artifact_kind"] == "brief"
        assert d["valid"] is True

    def test_save(self, tmp_path: Path):
        vr = ValidationResult(artifact_kind="brief", valid=False, errors=["e1"])
        out = tmp_path / "result.json"
        vr.save(out)
        assert out.exists()
        import json

        data = json.loads(out.read_text())
        assert data["valid"] is False
        assert data["errors"] == ["e1"]


# ---------------------------------------------------------------------------
# Brief validation
# ---------------------------------------------------------------------------


class TestBriefValidation:
    def test_valid_brief_passes(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        result = validate_brief(brief, manifest)
        assert result.valid, f"Expected valid, got errors: {result.errors}"
        assert result.errors == []

    def test_wrong_schema_version(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["schema_version"] = "wrong/v2"
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("schema_version" in e for e in result.errors)

    def test_experiment_id_mismatch(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["experiment_id"] = "wrong_id"
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("experiment_id" in e for e in result.errors)

    def test_missing_variant(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["variants"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("Missing variant" in e for e in result.errors)
        assert "variant_a" in result.coverage["missing_variant_ids"]

    def test_extra_variant(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        extra = copy.deepcopy(brief["variants"][0])
        extra["variant_id"] = "extra_variant"
        brief["variants"].append(extra)
        result = validate_brief(brief, manifest)
        assert any("Extra variant" in w for w in result.warnings)

    def test_missing_comparison(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["comparison_plan"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("Missing comparison" in e for e in result.errors)

    def test_duplicate_mechanism_ids(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        # Add a second mechanism chain with same ID
        mc_dup = copy.deepcopy(
            brief["variants"][0]["hypothesis"]["mechanism_chains"][0]
        )
        brief["variants"][0]["hypothesis"]["mechanism_chains"].append(mc_dup)
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("Duplicate" in e and "mechanism_chains" in e for e in result.errors)

    def test_non_substantive_fields(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["research"]["scope"] = "tbd"
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("research.scope" in e for e in result.errors)

    def test_empty_mechanism_chains(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["variants"][0]["hypothesis"]["mechanism_chains"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("mechanism_chains must not be empty" in e for e in result.errors)

    def test_empty_confirmation_criteria(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["variants"][0]["hypothesis"]["confirmation_criteria"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("confirmation_criteria must not be empty" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Interpretation validation
# ---------------------------------------------------------------------------


class TestInterpretationValidation:
    def test_valid_interpretation_passes(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert result.valid, f"Expected valid, got errors: {result.errors}"
        assert result.errors == []

    def test_missing_comparison_interpretation(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        interp["comparison_interpretations"] = []
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("Missing comparison interpretation" in e for e in result.errors)

    def test_missing_question_answer(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        # Remove question A
        interp["question_answers"] = [
            qa for qa in interp["question_answers"] if qa["question_id"] != "A"
        ]
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("Missing question answer" in e for e in result.errors)

    def test_duplicate_evidence_ids(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        dup = copy.deepcopy(interp["evidence_index"][0])
        interp["evidence_index"].append(dup)
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("Duplicate evidence_index" in e for e in result.errors)

    def test_dangling_evidence_ref(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        interp["executive_summary"]["evidence_refs"] = ["ENONEXISTENT"]
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("ENONEXISTENT" in e for e in result.errors)

    def test_dangling_step_ref(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        ci = interp["comparison_interpretations"][0]
        ci["reasoning_steps"][2]["depends_on"] = ["NONEXISTENT_STEP"]
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("NONEXISTENT_STEP" in e for e in result.errors)

    def test_no_observation_step(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        ci = interp["comparison_interpretations"][0]
        # Remove observation, keep only mechanism and conclusion
        ci["reasoning_steps"] = [
            s for s in ci["reasoning_steps"] if s["kind"] != "observation"
        ]
        # Fix depends_on so mechanism doesn't reference removed step
        ci["reasoning_steps"][0]["depends_on"] = []
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("observation step" in e for e in result.errors)

    def test_no_conclusion_step(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        ci = interp["comparison_interpretations"][0]
        ci["reasoning_steps"] = [
            s for s in ci["reasoning_steps"] if s["kind"] != "conclusion"
        ]
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("conclusion step" in e for e in result.errors)

    def test_unreachable_conclusion(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        ci = interp["comparison_interpretations"][0]
        # Make conclusion depend on nothing (and not reachable from observation)
        ci["reasoning_steps"] = [
            {
                "id": "baseline_vs_variant_a.R1",
                "kind": "observation",
                "statement": _LONG_TEXT_32,
                "evidence_refs": ["E1"],
                "depends_on": [],
            },
            {
                "id": "baseline_vs_variant_a.R3",
                "kind": "conclusion",
                "statement": _LONG_TEXT_32,
                "evidence_refs": ["E1"],
                "depends_on": [],
            },
        ]
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("not reachable from any observation" in e for e in result.errors)

    def test_non_substantive_interpretation(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        interp = _make_valid_interpretation()
        interp["executive_summary"]["short_answer"] = "tbd"
        summary = _make_summary()
        result = validate_interpretation(interp, manifest, summary)
        assert not result.valid
        assert any("executive_summary.short_answer" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderBriefMd:
    def test_brief_md_has_key_sections(self):
        brief = _make_valid_brief()
        md = render_brief_md(brief)
        assert "# Experiment Brief:" in md
        assert "## Research Question" in md
        assert "## Design Approach" in md
        assert "## Variants" in md
        assert "## Comparison Plan" in md
        assert "## Design Reasoning" in md


class TestRenderInterpretationMd:
    def test_interpretation_md_has_key_sections(self):
        interp = _make_valid_interpretation()
        md = render_interpretation_md(interp)
        assert "# Experiment Interpretation:" in md
        assert "## Executive Summary" in md
        assert "## Comparison Interpretations" in md
        assert "## Question Answers" in md
        assert "## Cross-Comparison Synthesis" in md
