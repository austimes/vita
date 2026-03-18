"""Tests for vita/experiment_presentation.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vita.experiment_presentation import generate_presentation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _run(rid: str, obj: float) -> dict:
    return {
        "id": rid,
        "run_dir": f"runs/{rid}",
        "objective": obj,
        "solver_status": "optimal",
    }


FULL_SUMMARY: dict = {
    "schema_version": "vita-experiment-summary/v1",
    "experiment_id": "toy_industry_core",
    "status": "concluded",
    "completed_at": "2026-03-18T12:25:00Z",
    "concluded_at": "2026-03-18T12:31:00Z",
    "methodology": {
        "baseline_run_id": "baseline",
        "variant_run_ids": ["co2_cap", "high_gas_capex"],
        "comparison_ids": [
            "baseline_vs_co2_cap",
            "baseline_vs_high_gas_capex",
        ],
    },
    "runs": [
        _run("baseline", 195.59),
        _run("co2_cap", 195.59),
        _run("high_gas_capex", 210.12),
    ],
    "comparisons": [
        {
            "id": "baseline_vs_co2_cap",
            "baseline_run_id": "baseline",
            "variant_run_id": "co2_cap",
            "objective_delta": 0.0,
            "pct_objective_delta": 0.0,
            "headline": (
                "No material difference; "
                "CO\u2082 cap is non-binding"
            ),
            "top_changes": ["Minor activity shifts"],
            "capacity_deltas": [],
        },
        {
            "id": "baseline_vs_high_gas_capex",
            "baseline_run_id": "baseline",
            "variant_run_id": "high_gas_capex",
            "objective_delta": 14.53,
            "pct_objective_delta": 7.4,
            "headline": (
                "Higher gas capex increases total system cost"
            ),
            "top_changes": [
                "Gas plant capacity reduced",
                "Coal plant capacity increased",
            ],
            "capacity_deltas": [
                {
                    "process": "PP_CCGT",
                    "baseline": 2.0,
                    "variant": 1.0,
                    "delta": -1.0,
                },
                {
                    "process": "PP_COAL",
                    "baseline": 1.0,
                    "variant": 2.0,
                    "delta": 1.0,
                },
            ],
        },
    ],
    "answers": [
        {
            "question_id": "Q",
            "kind": "primary",
            "question": (
                "How does gas capex affect the "
                "technology mix?"
            ),
            "status": "answered",
            "short_answer": (
                "Higher gas capex shifts investment to coal"
            ),
            "answer": (
                "When gas capital costs increase by 50%, "
                "the model substitutes coal capacity."
            ),
            "evidence_refs": [
                "baseline_vs_high_gas_capex",
            ],
            "limitations": [],
        },
        {
            "question_id": "E1",
            "kind": "extension",
            "question": "Is the CO2 cap binding?",
            "status": "answered",
            "short_answer": (
                "No, the cap is non-binding in the baseline"
            ),
            "answer": (
                "The CO2 cap does not change the objective."
            ),
            "evidence_refs": ["baseline_vs_co2_cap"],
            "limitations": [],
        },
    ],
    "key_findings": [
        {
            "id": "F1",
            "statement": (
                "Gas capex is a key driver of "
                "technology mix"
            ),
            "evidence_refs": [
                "baseline_vs_high_gas_capex",
            ],
        },
        {
            "id": "F2",
            "statement": (
                "CO2 cap is non-binding in the toy model"
            ),
            "evidence_refs": ["baseline_vs_co2_cap"],
        },
    ],
    "hypothesis_outcomes": [
        {
            "variant_id": "co2_cap",
            "hypothesis": "CO2 cap will raise system cost",
            "outcome": "refuted",
        },
        {
            "variant_id": "high_gas_capex",
            "hypothesis": (
                "Higher gas capex shifts to coal"
            ),
            "outcome": "confirmed",
        },
    ],
    "surprises": [
        {
            "statement": (
                "CO2 cap had zero impact on the solution"
            ),
            "evidence_refs": ["baseline_vs_co2_cap"],
            "follow_up": "Test with a tighter cap",
        },
    ],
    "limitations": [
        "Toy model with single period",
        "No renewable options",
    ],
}

MINIMAL_SUMMARY: dict = {
    "schema_version": "vita-experiment-summary/v1",
    "experiment_id": "minimal",
    "status": "concluded",
    "completed_at": "2026-03-18T12:00:00Z",
    "concluded_at": "2026-03-18T12:05:00Z",
    "methodology": {
        "baseline_run_id": "baseline",
        "variant_run_ids": [],
        "comparison_ids": [],
    },
    "runs": [_run("baseline", 100.0)],
    "comparisons": [],
    "answers": [],
    "key_findings": [],
    "hypothesis_outcomes": [],
    "surprises": [],
    "limitations": [],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHTMLGeneration:
    def test_generates_valid_html_from_dict(self, tmp_path: Path) -> None:
        result = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        assert result.exists()
        assert result.name == "index.html"
        html = result.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_writes_to_presentation_dir(self, tmp_path: Path) -> None:
        result = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        assert result == tmp_path / "presentation" / "index.html"
        assert result.parent.is_dir()

    def test_loads_from_summary_json(self, tmp_path: Path) -> None:
        conclusions_dir = tmp_path / "conclusions"
        conclusions_dir.mkdir()
        (conclusions_dir / "summary.json").write_text(
            json.dumps(FULL_SUMMARY), encoding="utf-8"
        )
        result = generate_presentation(tmp_path)
        assert result.exists()
        html = result.read_text(encoding="utf-8")
        assert "toy_industry_core" in html


class TestSectionsPresent:
    @pytest.fixture()
    def full_html(self, tmp_path: Path) -> str:
        path = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        return path.read_text(encoding="utf-8")

    def test_header(self, full_html: str) -> None:
        assert "toy_industry_core" in full_html
        assert "concluded" in full_html

    def test_research_question(self, full_html: str) -> None:
        assert "Research Question" in full_html
        assert "How does gas capex affect the technology mix?" in full_html

    def test_extensions_listed(self, full_html: str) -> None:
        assert "Is the CO2 cap binding?" in full_html

    def test_methodology(self, full_html: str) -> None:
        assert "Methodology" in full_html
        assert "baseline" in full_html
        assert "co2_cap" in full_html

    def test_results_overview(self, full_html: str) -> None:
        assert "Results Overview" in full_html
        assert "195.59" in full_html
        assert "210.12" in full_html

    def test_comparison_details(self, full_html: str) -> None:
        assert "Comparison Details" in full_html
        assert "baseline_vs_co2_cap" in full_html
        assert "baseline_vs_high_gas_capex" in full_html

    def test_capacity_deltas(self, full_html: str) -> None:
        assert "Capacity Changes" in full_html
        assert "PP_CCGT" in full_html
        assert "PP_COAL" in full_html

    def test_answers(self, full_html: str) -> None:
        assert "Answers" in full_html
        assert "Higher gas capex shifts investment to coal" in full_html

    def test_findings(self, full_html: str) -> None:
        assert "Key Findings" in full_html
        assert "F1" in full_html
        assert "Gas capex is a key driver" in full_html

    def test_hypothesis_outcomes(self, full_html: str) -> None:
        assert "Hypothesis Outcomes" in full_html
        assert "confirmed" in full_html
        assert "refuted" in full_html

    def test_surprises(self, full_html: str) -> None:
        assert "Surprises" in full_html
        assert "CO2 cap had zero impact" in full_html
        assert "Test with a tighter cap" in full_html

    def test_limitations(self, full_html: str) -> None:
        assert "Limitations" in full_html
        assert "Toy model with single period" in full_html


class TestEmptySectionsOmitted:
    @pytest.fixture()
    def minimal_html(self, tmp_path: Path) -> str:
        path = generate_presentation(tmp_path, summary=MINIMAL_SUMMARY)
        return path.read_text(encoding="utf-8")

    def test_no_comparisons(self, minimal_html: str) -> None:
        assert "Comparison Details" not in minimal_html

    def test_no_answers(self, minimal_html: str) -> None:
        assert "Answers" not in minimal_html

    def test_no_findings(self, minimal_html: str) -> None:
        assert "Key Findings" not in minimal_html

    def test_no_hypothesis_outcomes(self, minimal_html: str) -> None:
        assert "Hypothesis Outcomes" not in minimal_html

    def test_no_surprises(self, minimal_html: str) -> None:
        assert "Surprises" not in minimal_html

    def test_no_limitations(self, minimal_html: str) -> None:
        assert "Limitations" not in minimal_html

    def test_no_research_question(self, minimal_html: str) -> None:
        assert "Research Question" not in minimal_html

    def test_still_has_header(self, minimal_html: str) -> None:
        assert "minimal" in minimal_html
        assert "<!DOCTYPE html>" in minimal_html

    def test_still_has_results(self, minimal_html: str) -> None:
        assert "Results Overview" in minimal_html
        assert "100.0" in minimal_html


class TestDeltaFormatting:
    def test_positive_delta_in_results(self, tmp_path: Path) -> None:
        path = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        html = path.read_text(encoding="utf-8")
        assert "delta-pos" in html
        assert "+14.53" in html

    def test_zero_delta_in_comparisons(self, tmp_path: Path) -> None:
        path = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        html = path.read_text(encoding="utf-8")
        assert "delta-zero" in html

    def test_negative_capacity_delta(self, tmp_path: Path) -> None:
        path = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        html = path.read_text(encoding="utf-8")
        assert "delta-neg" in html
        assert "-1.0" in html


# ---------------------------------------------------------------------------
# Interpretation / Brief test fixtures
# ---------------------------------------------------------------------------

SAMPLE_INTERPRETATION: dict = {
    "executive_summary": "Gas capex is the primary cost driver",
    "overall_confidence": "high",
    "comparisons": [
        {
            "id": "baseline_vs_co2_cap",
            "takeaway": "CO2 cap is non-binding",
            "hypothesis_assessment": "refuted",
            "reasoning_chain": [
                {"type": "observation", "text": "Objective unchanged"},
                {"type": "mechanism", "text": "Cap exceeds baseline emissions"},
                {"type": "conclusion", "text": "Cap is slack"},
            ],
            "primary_mechanism": "Slack constraint",
            "surprises": ["Zero shadow price"],
        },
        {
            "id": "baseline_vs_high_gas_capex",
            "takeaway": "Coal substitutes for gas",
            "hypothesis_assessment": "supports",
            "reasoning_chain": [
                {"type": "observation", "text": "Gas capacity halved"},
                {"type": "mechanism", "text": "Higher capex raises LCOE"},
                {"type": "conclusion", "text": "Coal becomes cheaper"},
            ],
            "primary_mechanism": "LCOE crossover",
            "surprises": [],
        },
    ],
    "synthesis": "The model is capex-sensitive for gas.",
    "question_answers": [
        {
            "question": "How does gas capex affect the technology mix?",
            "short_answer": "Coal replaces gas",
            "answer": "Higher gas capex causes a shift to coal.",
            "confidence": "high",
            "evidence_refs": ["baseline_vs_high_gas_capex"],
        },
    ],
}

SAMPLE_BRIEF: dict = {
    "design_approach": "Single-variable sensitivity on gas capex",
    "variants": [
        {
            "id": "high_gas_capex",
            "change_summary": "Gas capex +50%",
            "hypothesis": "Coal will substitute for gas",
            "expected_mechanisms": [
                "Higher LCOE for gas",
                "Coal becomes least-cost",
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Tests: interpretation + brief rendering
# ---------------------------------------------------------------------------


class TestInterpretationRendering:
    def test_renders_with_interpretation(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            interpretation=SAMPLE_INTERPRETATION,
        )
        html = path.read_text(encoding="utf-8")
        assert "Agent Interpretation" in html
        assert "interpretation-card" in html

    def test_renders_without_interpretation(self, tmp_path: Path) -> None:
        path = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        html = path.read_text(encoding="utf-8")
        assert "Agent Interpretation" not in html
        assert "Answers" in html

    def test_reasoning_chain_steps(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            interpretation=SAMPLE_INTERPRETATION,
        )
        html = path.read_text(encoding="utf-8")
        assert "reasoning-step observation" in html
        assert "reasoning-step mechanism" in html
        assert "reasoning-step conclusion" in html
        assert "Objective unchanged" in html
        assert "Cap exceeds baseline emissions" in html

    def test_confidence_badges(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            interpretation=SAMPLE_INTERPRETATION,
        )
        html = path.read_text(encoding="utf-8")
        assert "badge-green" in html
        assert ">high<" in html

    def test_hypothesis_assessment_badges(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            interpretation=SAMPLE_INTERPRETATION,
        )
        html = path.read_text(encoding="utf-8")
        assert "badge-red" in html
        assert ">refuted<" in html
        assert ">supports<" in html

    def test_question_answers_section(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            interpretation=SAMPLE_INTERPRETATION,
        )
        html = path.read_text(encoding="utf-8")
        assert "Research Answers" in html
        assert "Coal replaces gas" in html

    def test_synthesis_rendered(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            interpretation=SAMPLE_INTERPRETATION,
        )
        html = path.read_text(encoding="utf-8")
        assert "Synthesis" in html
        assert "capex-sensitive" in html

    def test_executive_summary_in_question(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            interpretation=SAMPLE_INTERPRETATION,
        )
        html = path.read_text(encoding="utf-8")
        assert "Gas capex is the primary cost driver" in html


class TestBriefRendering:
    def test_renders_with_brief(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            brief=SAMPLE_BRIEF,
        )
        html = path.read_text(encoding="utf-8")
        assert "Experiment Design" in html
        assert "brief-card" in html

    def test_brief_shows_design_approach(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            brief=SAMPLE_BRIEF,
        )
        html = path.read_text(encoding="utf-8")
        assert "Single-variable sensitivity on gas capex" in html

    def test_brief_shows_variant_details(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            brief=SAMPLE_BRIEF,
        )
        html = path.read_text(encoding="utf-8")
        assert "Gas capex +50%" in html
        assert "Coal will substitute for gas" in html
        assert "Higher LCOE for gas" in html

    def test_no_brief_section_when_absent(self, tmp_path: Path) -> None:
        path = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        html = path.read_text(encoding="utf-8")
        assert "Experiment Design" not in html


class TestFileLoading:
    def test_loads_interpretation_from_disk(self, tmp_path: Path) -> None:
        conclusions = tmp_path / "conclusions"
        conclusions.mkdir()
        (conclusions / "summary.json").write_text(
            json.dumps(FULL_SUMMARY), encoding="utf-8"
        )
        (conclusions / "interpretation.json").write_text(
            json.dumps(SAMPLE_INTERPRETATION), encoding="utf-8"
        )
        path = generate_presentation(tmp_path)
        html = path.read_text(encoding="utf-8")
        assert "Agent Interpretation" in html

    def test_loads_brief_from_disk(self, tmp_path: Path) -> None:
        conclusions = tmp_path / "conclusions"
        conclusions.mkdir()
        (conclusions / "summary.json").write_text(
            json.dumps(FULL_SUMMARY), encoding="utf-8"
        )
        planning = tmp_path / "planning"
        planning.mkdir()
        (planning / "brief.json").write_text(
            json.dumps(SAMPLE_BRIEF), encoding="utf-8"
        )
        path = generate_presentation(tmp_path)
        html = path.read_text(encoding="utf-8")
        assert "Experiment Design" in html

    def test_graceful_without_interpretation_file(self, tmp_path: Path) -> None:
        conclusions = tmp_path / "conclusions"
        conclusions.mkdir()
        (conclusions / "summary.json").write_text(
            json.dumps(FULL_SUMMARY), encoding="utf-8"
        )
        path = generate_presentation(tmp_path)
        html = path.read_text(encoding="utf-8")
        assert "Agent Interpretation" not in html
        assert "<!DOCTYPE html>" in html


class TestCandidateAnomalies:
    def test_candidate_anomalies_fallback(self, tmp_path: Path) -> None:
        summary = {
            k: v for k, v in MINIMAL_SUMMARY.items() if k != "surprises"
        }
        summary["candidate_anomalies"] = [
            {"statement": "Unexpected result", "evidence_refs": [], "follow_up": ""},
        ]
        path = generate_presentation(tmp_path, summary=summary)
        html = path.read_text(encoding="utf-8")
        assert "Surprises" in html
        assert "Unexpected result" in html


class TestOverwrite:
    def test_overwrites_existing(self, tmp_path: Path) -> None:
        generate_presentation(tmp_path, summary=MINIMAL_SUMMARY)
        result = generate_presentation(tmp_path, summary=FULL_SUMMARY)
        html = result.read_text(encoding="utf-8")
        assert "toy_industry_core" in html
