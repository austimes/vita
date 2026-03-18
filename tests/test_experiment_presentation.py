"""Tests for the narrative experiment presentation renderer."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

from vita.experiment_presentation import generate_presentation


def _run(run_id: str, objective: float) -> dict:
    return {
        "id": run_id,
        "run_dir": f"runs/{run_id}",
        "objective": objective,
        "solver_status": "optimal",
    }


FULL_SUMMARY: dict = {
    "schema_version": "vita-experiment-summary/v1",
    "experiment_id": "toy_industry_core",
    "status": "summarized",
    "completed_at": "2026-03-18T12:25:00Z",
    "summarized_at": "2026-03-18T12:31:00Z",
    "methodology": {
        "baseline_run_id": "baseline",
        "variant_run_ids": ["co2_cap", "high_gas_capex"],
        "comparison_ids": [
            "baseline_vs_co2_cap",
            "baseline_vs_high_gas_capex",
        ],
    },
    "runs": [
        _run("baseline", 195.5915),
        _run("co2_cap", 195.5915),
        _run("high_gas_capex", 452.9488),
    ],
    "comparisons": [
        {
            "id": "baseline_vs_co2_cap",
            "baseline_run_id": "baseline",
            "variant_run_id": "co2_cap",
            "diff_file": "diffs/baseline_vs_co2_cap/diff.json",
            "objective_delta": 0.0,
            "pct_objective_delta": 0.0,
            "headline": "The cap does not materially change the result.",
            "top_changes": ["No meaningful row-level shifts"],
            "capacity_deltas": [],
        },
        {
            "id": "baseline_vs_high_gas_capex",
            "baseline_run_id": "baseline",
            "variant_run_id": "high_gas_capex",
            "diff_file": "diffs/baseline_vs_high_gas_capex/diff.json",
            "objective_delta": 257.3573,
            "pct_objective_delta": 131.58,
            "headline": "Higher gas capex produces a large cost increase.",
            "top_changes": [
                "Gas boiler expansion becomes more expensive",
                "Alternative heat supply grows",
            ],
            "capacity_deltas": [
                {
                    "metric": "var_ncap",
                    "process": "PRC_GAS_BOILER",
                    "baseline": 100.0,
                    "variant": 280.0,
                    "delta": 180.0,
                    "pct_delta": 180.0,
                },
            ],
        },
    ],
    "key_findings": [
        {
            "id": "F1",
            "statement": "Gas capex is the dominant cost lever in this toy study.",
            "evidence_refs": ["E1"],
        },
    ],
    "candidate_anomalies": [
        {
            "statement": "The CO2 cap appears non-binding in the baseline configuration.",
            "evidence_refs": ["E3"],
            "follow_up": "Test a tighter cap to force a response.",
        },
    ],
    "limitations": [
        "Single-period toy model.",
        "Only a small technology set is represented.",
    ],
}


MINIMAL_SUMMARY: dict = {
    "schema_version": "vita-experiment-summary/v1",
    "experiment_id": "minimal",
    "status": "summarized",
    "completed_at": "2026-03-18T12:00:00Z",
    "summarized_at": "2026-03-18T12:05:00Z",
    "methodology": {
        "baseline_run_id": "baseline",
        "variant_run_ids": [],
        "comparison_ids": [],
    },
    "runs": [_run("baseline", 100.0)],
    "comparisons": [],
    "key_findings": [],
    "candidate_anomalies": [],
    "limitations": [],
}


FULL_BRIEF: dict = {
    "schema_version": "vita-experiment-brief/v1",
    "experiment_id": "toy_industry_core",
    "manifest_file": "manifest.yaml",
    "created_at": "2026-03-18T10:00:00Z",
    "research": {
        "question": "How does gas capex affect the heat supply mix?",
        "scope": "This experiment tests whether a gas-capex shock changes system cost and technology choice in the toy industry model.",
    },
    "design_summary": {
        "approach": "Use one control variant and one cost shock variant so the answer can separate non-binding policy effects from real cost-driven shifts.",
        "variant_ids": ["co2_cap", "high_gas_capex"],
        "comparison_ids": [
            "baseline_vs_co2_cap",
            "baseline_vs_high_gas_capex",
        ],
    },
    "variants": [
        {
            "variant_id": "co2_cap",
            "change_summary": "Apply a CO2 cap that may or may not bind.",
            "why_this_variant": "This is the control case for checking whether emissions policy is active in the baseline setup.",
            "hypothesis": {
                "statement": "The CO2 cap will have little effect because the baseline already satisfies it.",
                "expected_direction": "no_change",
                "mechanism_chains": [
                    {
                        "id": "M1",
                        "cause": "The cap is loose relative to baseline emissions.",
                        "effect": "Objective and capacity remain largely unchanged.",
                        "because": "A slack policy constraint does not force a new investment pattern.",
                    },
                ],
                "confirmation_criteria": [
                    {
                        "id": "C1",
                        "description": "Objective remains flat and major process tables show no meaningful deltas.",
                        "signals": [
                            {
                                "metric": "objective",
                                "expected_direction": "no_change",
                            },
                        ],
                    },
                ],
                "refutation_criteria": [
                    {
                        "id": "R1",
                        "description": "Objective rises materially or low-carbon capacity expands.",
                    },
                ],
            },
        },
        {
            "variant_id": "high_gas_capex",
            "change_summary": "Increase gas capital costs sharply.",
            "why_this_variant": "This isolates whether gas capex is the main driver of the heat supply choice.",
            "hypothesis": {
                "statement": "Higher gas capex will increase total cost and reallocate capacity.",
                "expected_direction": "increase",
                "mechanism_chains": [
                    {
                        "id": "M2",
                        "cause": "Gas investment becomes more expensive.",
                        "effect": "Total system cost increases and alternative assets become more attractive.",
                        "because": "The model re-optimizes toward cheaper long-run capacity choices.",
                    },
                ],
                "confirmation_criteria": [
                    {
                        "id": "C2",
                        "description": "Objective rises and gas-linked capacity shifts materially.",
                        "signals": [
                            {
                                "metric": "objective",
                                "expected_direction": "increase",
                            },
                            {
                                "metric": "var_ncap",
                                "expected_direction": "increase",
                            },
                        ],
                    },
                ],
                "refutation_criteria": [
                    {
                        "id": "R2",
                        "description": "Objective stays flat and the process mix is unchanged.",
                    },
                ],
            },
        },
    ],
    "comparison_plan": [
        {
            "comparison_id": "baseline_vs_high_gas_capex",
            "purpose": "Measure the cost and capacity response to the gas capex shock.",
            "metrics_of_interest": [
                {
                    "metric": "objective",
                    "priority": "primary",
                    "why_it_matters": "This is the top-line cost signal.",
                },
            ],
        },
    ],
    "design_reasoning_steps": [
        {
            "id": "P1",
            "kind": "question_framing",
            "statement": "The experiment needs both a control and a capex shock so policy slack can be distinguished from cost-driven technology shifts.",
        },
    ],
}


FULL_INTERPRETATION: dict = {
    "schema_version": "vita-experiment-interpretation/v1",
    "experiment_id": "toy_industry_core",
    "summary_file": "conclusions/summary.json",
    "created_at": "2026-03-18T13:00:00Z",
    "research_question": "How does gas capex affect the heat supply mix?",
    "executive_summary": {
        "short_answer": "Gas capex is the main cost driver in this toy experiment.",
        "answer": "The gas-capex shock produces the only large objective movement and coincides with the strongest capacity response, so the answer is driven by cost sensitivity rather than policy binding effects.",
        "confidence": "high",
        "evidence_refs": ["E1", "E2"],
        "supporting_step_ids": ["baseline_vs_high_gas_capex_r3"],
    },
    "evidence_index": [
        {
            "id": "E1",
            "kind": "comparison_metric",
            "comparison_id": "baseline_vs_high_gas_capex",
            "metric": "objective",
            "source_file": "diffs/baseline_vs_high_gas_capex/diff.json",
        },
        {
            "id": "E2",
            "kind": "process_delta",
            "comparison_id": "baseline_vs_high_gas_capex",
            "metric": "var_ncap",
            "source_file": "diffs/baseline_vs_high_gas_capex/diff.json",
        },
        {
            "id": "E3",
            "kind": "comparison_metric",
            "comparison_id": "baseline_vs_co2_cap",
            "metric": "objective",
            "source_file": "diffs/baseline_vs_co2_cap/diff.json",
        },
    ],
    "question_answers": [
        {
            "question_id": "Q",
            "question": "How does gas capex affect the heat supply mix?",
            "comparison_ids": ["baseline_vs_high_gas_capex"],
            "short_answer": "It raises cost and changes the favored supply assets.",
            "answer": "The high-gas-capex case is the only one with a large objective delta and a meaningful capacity shift, which indicates the answer is being determined by investment cost sensitivity.",
            "confidence": "high",
            "uncertainty": "This remains a toy model, so the exact scale of response is not portable.",
            "evidence_refs": ["E1", "E2"],
            "supporting_step_ids": ["baseline_vs_high_gas_capex_r3"],
        },
    ],
    "comparison_interpretations": [
        {
            "comparison_id": "baseline_vs_co2_cap",
            "takeaway": "The CO2 cap behaves like a slack control in this configuration.",
            "hypothesis_assessment": {
                "status": "supports",
                "rationale": "No objective movement or capacity delta was observed, which matches the expectation of a non-binding cap.",
            },
            "key_evidence_refs": ["E3"],
            "reasoning_steps": [
                {
                    "id": "baseline_vs_co2_cap_r1",
                    "kind": "observation",
                    "statement": "Objective delta is zero and no major capacity shifts appear.",
                    "evidence_refs": ["E3"],
                    "depends_on": [],
                },
                {
                    "id": "baseline_vs_co2_cap_r2",
                    "kind": "conclusion",
                    "statement": "The policy change does not explain the final answer because it never binds strongly enough to move the solution.",
                    "evidence_refs": ["E3"],
                    "depends_on": ["baseline_vs_co2_cap_r1"],
                },
            ],
            "primary_mechanism": "Slack policy constraint",
            "alternative_mechanisms": [],
            "confidence": "medium",
            "surprises": [],
        },
        {
            "comparison_id": "baseline_vs_high_gas_capex",
            "takeaway": "The gas-capex shock drives the answer because it moves both cost and capacity.",
            "hypothesis_assessment": {
                "status": "supports",
                "rationale": "The largest objective delta and the clearest capacity response both occur in the gas-capex comparison.",
            },
            "key_evidence_refs": ["E1", "E2"],
            "reasoning_steps": [
                {
                    "id": "baseline_vs_high_gas_capex_r1",
                    "kind": "observation",
                    "statement": "Objective rises sharply in the gas-capex comparison.",
                    "evidence_refs": ["E1"],
                    "depends_on": [],
                },
                {
                    "id": "baseline_vs_high_gas_capex_r2",
                    "kind": "mechanism",
                    "statement": "The capacity delta shows the model re-optimizing around the more expensive gas option.",
                    "evidence_refs": ["E2"],
                    "depends_on": ["baseline_vs_high_gas_capex_r1"],
                },
                {
                    "id": "baseline_vs_high_gas_capex_r3",
                    "kind": "conclusion",
                    "statement": "Taken together, the cost signal and capacity movement identify gas capex as the main answer-bearing mechanism.",
                    "evidence_refs": ["E1", "E2"],
                    "depends_on": ["baseline_vs_high_gas_capex_r2"],
                },
            ],
            "primary_mechanism": "Cost-driven capacity re-optimization",
            "alternative_mechanisms": [],
            "confidence": "high",
            "surprises": [],
        },
    ],
    "cross_comparison_synthesis": {
        "overall_pattern": "Only the gas-capex shock meaningfully changes the result, so the answer is rooted in investment-cost sensitivity rather than policy binding.",
        "open_questions": [
            "Would the same ranking hold in a multi-period system?",
        ],
        "limits": [
            "This evidence comes from a toy model.",
        ],
    },
}


def _read_html(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestNarrativePresentation:
    def test_generates_html_document(self, tmp_path: Path) -> None:
        path = generate_presentation(
            tmp_path,
            summary=FULL_SUMMARY,
            brief=FULL_BRIEF,
            interpretation=FULL_INTERPRETATION,
        )
        html = _read_html(path)
        assert "<!DOCTYPE html>" in html
        assert "<main>" in html
        assert "</html>" in html

    def test_story_sections_render_in_order(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
                interpretation=FULL_INTERPRETATION,
            )
        )
        headings = [
            "What Is the Answer?",
            "Why This Experiment Was Designed",
            "Mechanisms We Expected",
            "What Happened",
            "How We Reached the Answer",
            "Question-by-Question Answers",
            "Cross-Comparison Synthesis",
            "Evidence Appendix",
        ]
        positions = [html.index(heading) for heading in headings]
        assert positions == sorted(positions)

    def test_uses_current_schema_fields_only(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
                interpretation=FULL_INTERPRETATION,
            )
        )
        assert "Gas capex is the main cost driver in this toy experiment." in html
        assert "The gas-capex shock drives the answer because it moves both cost and capacity." in html
        assert "baseline_vs_high_gas_capex_r2" in html
        assert "Comparison Details" not in html
        assert "Agent Interpretation" not in html

    def test_visual_contract_smoke_checks(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
                interpretation=FULL_INTERPRETATION,
            )
        )
        assert "fonts.googleapis.com" in html
        assert "--font-display" in html
        assert "scroll-snap-type:y mandatory" in html
        assert "Instrument Serif" in html

    def test_renders_evidence_index_and_appendix_tables(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
                interpretation=FULL_INTERPRETATION,
            )
        )
        assert "Evidence Index" in html
        assert "diffs/baseline_vs_high_gas_capex/diff.json" in html
        assert "Run Summary" in html
        assert "Comparison Summary" in html

    def test_renders_capacity_delta_appendix_only_when_present(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
                interpretation=FULL_INTERPRETATION,
            )
        )
        assert "Capacity Deltas: baseline_vs_high_gas_capex" in html
        assert "PRC_GAS_BOILER" in html

    def test_renders_reasoning_timeline_from_reasoning_steps(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
                interpretation=FULL_INTERPRETATION,
            )
        )
        assert "step observation" in html
        assert "step mechanism" in html
        assert "step conclusion" in html
        assert "Cost-driven capacity re-optimization" in html


class TestOptionalArtifacts:
    def test_summary_only_omits_brief_and_interpretation_sections(self, tmp_path: Path) -> None:
        html = _read_html(generate_presentation(tmp_path, summary=MINIMAL_SUMMARY))
        assert "What Happened" in html
        assert "Evidence Appendix" in html
        assert "Why This Experiment Was Designed" not in html
        assert "What Is the Answer?" not in html
        assert "How We Reached the Answer" not in html

    def test_summary_and_interpretation_without_brief(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                interpretation=FULL_INTERPRETATION,
            )
        )
        assert "What Is the Answer?" in html
        assert "How We Reached the Answer" in html
        assert "Why This Experiment Was Designed" not in html

    def test_summary_and_brief_without_interpretation(self, tmp_path: Path) -> None:
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
            )
        )
        assert "Why This Experiment Was Designed" in html
        assert "Mechanisms We Expected" in html
        assert "What Is the Answer?" not in html
        assert "Question-by-Question Answers" not in html

    def test_does_not_fallback_to_legacy_summary_answers(self, tmp_path: Path) -> None:
        summary = dict(FULL_SUMMARY)
        summary["answers"] = [
            {
                "question": "Legacy question",
                "short_answer": "Legacy answer should stay hidden.",
            },
        ]
        html = _read_html(generate_presentation(tmp_path, summary=summary))
        assert "Legacy answer should stay hidden." not in html
        assert "Question-by-Question Answers" not in html

    def test_omits_capacity_section_when_no_capacity_deltas_exist(self, tmp_path: Path) -> None:
        summary = dict(MINIMAL_SUMMARY)
        summary["comparisons"] = [
            {
                "id": "baseline_vs_variant",
                "baseline_run_id": "baseline",
                "variant_run_id": "variant",
                "diff_file": "diffs/baseline_vs_variant/diff.json",
                "objective_delta": 1.5,
                "pct_objective_delta": 1.5,
                "headline": "Small change only.",
                "top_changes": [],
                "capacity_deltas": [],
            },
        ]
        html = _read_html(generate_presentation(tmp_path, summary=summary))
        assert "Capacity Deltas:" not in html


class TestFileLoadingAndOverwrite:
    def test_loads_brief_and_interpretation_from_disk(self, tmp_path: Path) -> None:
        conclusions = tmp_path / "conclusions"
        conclusions.mkdir()
        planning = tmp_path / "planning"
        planning.mkdir()
        (conclusions / "summary.json").write_text(
            json.dumps(FULL_SUMMARY), encoding="utf-8"
        )
        (conclusions / "interpretation.json").write_text(
            json.dumps(FULL_INTERPRETATION), encoding="utf-8"
        )
        (planning / "brief.json").write_text(
            json.dumps(FULL_BRIEF), encoding="utf-8"
        )

        html = _read_html(generate_presentation(tmp_path))
        assert "How does gas capex affect the heat supply mix?" in html
        assert "Why This Experiment Was Designed" in html
        assert "How We Reached the Answer" in html

    def test_overwrites_existing_html(self, tmp_path: Path) -> None:
        generate_presentation(tmp_path, summary=MINIMAL_SUMMARY)
        html = _read_html(
            generate_presentation(
                tmp_path,
                summary=FULL_SUMMARY,
                brief=FULL_BRIEF,
                interpretation=FULL_INTERPRETATION,
            )
        )
        assert "toy_industry_core" in html
        assert "Gas capex is the main cost driver in this toy experiment." in html
