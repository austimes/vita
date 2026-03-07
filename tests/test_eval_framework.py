"""Tests for eval framework scaffold."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from tools.veda_dev.evals.config import (
    CandidateSpec,
    build_candidate_matrix,
    model_supports_reasoning_effort,
)
from tools.veda_dev.evals.dataset import cases_for_profile, load_dataset
from tools.veda_dev.evals.judge import parse_judge_response
from tools.veda_dev.evals.runner import (
    _deterministic_reference,
    compare_runs,
    run_eval,
)
from tools.veda_dev.evals.scoring import (
    deterministic_breakdown,
    label_metrics,
    parity_score,
)


def test_candidate_matrix_has_9_entries():
    candidates = build_candidate_matrix()
    assert len(candidates) == 9


def test_candidate_matrix_orders_fast_to_slow():
    candidate_ids = [c.candidate_id for c in build_candidate_matrix()]
    assert candidate_ids[:3] == [
        "gpt-5-nano:low",
        "gpt-5-nano:medium",
        "gpt-5-nano:high",
    ]
    assert candidate_ids[3:6] == [
        "gpt-5-mini:low",
        "gpt-5-mini:medium",
        "gpt-5-mini:high",
    ]
    assert candidate_ids[6:] == [
        "gpt-5.2:low",
        "gpt-5.2:medium",
        "gpt-5.2:high",
    ]


def test_model_reasoning_support_matrix():
    assert not model_supports_reasoning_effort("gpt-5.2", "none")
    assert not model_supports_reasoning_effort("gpt-5.2", "xhigh")
    assert not model_supports_reasoning_effort("gpt-5-mini", "none")
    assert not model_supports_reasoning_effort("gpt-5-mini", "xhigh")
    assert not model_supports_reasoning_effort("gpt-5-nano", "none")
    assert not model_supports_reasoning_effort("gpt-5-nano", "xhigh")
    assert model_supports_reasoning_effort("gpt-5-mini", "low")
    assert model_supports_reasoning_effort("gpt-5-nano", "medium")


def test_dataset_profile_counts():
    dataset = load_dataset()
    assert len(cases_for_profile(dataset, "smoke")) == 5
    assert len(cases_for_profile(dataset, "ci")) == 10
    assert len(cases_for_profile(dataset, "deep")) == 30


def test_judge_parser_requires_json_object():
    parsed = parse_judge_response(
        '{"score_0_to_100": 77, "actionability_score": 80, '
        '"hallucination_flag": false, "major_errors": [], '
        '"rationale_short": "ok"}'
    )
    assert parsed.score_0_to_100 == 77


def test_run_eval_marks_skips_without_crashing(monkeypatch, tmp_path):
    def fake_evaluate_one(**kwargs):
        effort = kwargs["effort"]
        if effort == "high":
            return {
                "status": "skipped",
                "diagnostics": [],
                "telemetry": [],
                "error": "unsupported combo",
                "cached": False,
            }
        return {
            "status": "ok",
            "diagnostics": [
                {
                    "code": "LLM_UNIT_CHECK",
                    "severity": "warning",
                    "category": kwargs["expanded_case"].case.category,
                    "engine": kwargs["expanded_case"].case.engine,
                    "check_id": kwargs["expanded_case"].case.check_id,
                }
            ],
            "telemetry": [
                {
                    "model": kwargs["model"],
                    "latency_sec": 0.2,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "reasoning_tokens": 2,
                    "reasoning_effort": kwargs["effort"],
                }
            ],
            "error": None,
            "cached": False,
        }

    monkeypatch.setattr("tools.veda_dev.evals.runner._evaluate_one", fake_evaluate_one)
    monkeypatch.setattr("tools.veda_dev.evals.runner.load_vedalang", lambda _p: {})
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.validate_vedalang",
        lambda _s, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c, **_k: []
    )

    run = run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=tmp_path / "cache.json",
        use_cache=False,
        timeout_sec=10,
        no_judge=True,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
    )

    assert run["run_id"].startswith("eval-")
    assert len(run["candidates"]) == 9
    assert len(run["results"]) == 9 * 5  # profile smoke expands to 5 cases at v1
    assert any(r["status"] == "skipped" for r in run["results"])
    assert all("telemetry" in r for r in run["results"])
    assert all("row_elapsed_sec" in r for r in run["results"])
    assert all("deterministic_breakdown" in r for r in run["results"])
    assert "timing" in run
    assert run["timing"]["completed_runs"] == len(run["results"])


def test_compare_runs_returns_deltas():
    old = {
        "run_id": "old",
        "leaderboard": [
            {"candidate_id": "a", "rank_score": 10.0, "quality_score": 20.0},
            {"candidate_id": "b", "rank_score": 5.0, "quality_score": 10.0},
        ],
    }
    new = {
        "run_id": "new",
        "leaderboard": [
            {"candidate_id": "a", "rank_score": 12.0, "quality_score": 21.0},
            {"candidate_id": "b", "rank_score": 3.0, "quality_score": 8.0},
        ],
    }
    diff = compare_runs(old, new)
    assert diff["old_run_id"] == "old"
    assert diff["new_run_id"] == "new"
    assert len(diff["deltas"]) == 2


def test_run_eval_emits_progress_events(monkeypatch, tmp_path):
    events: list[dict[str, object]] = []

    def fake_evaluate_one(**_kwargs):
        return {
            "status": "ok",
            "diagnostics": [],
            "telemetry": [],
            "error": None,
            "cached": False,
        }

    monkeypatch.setattr("tools.veda_dev.evals.runner._evaluate_one", fake_evaluate_one)
    monkeypatch.setattr("tools.veda_dev.evals.runner.load_vedalang", lambda _p: {})
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.validate_vedalang",
        lambda _s, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c, **_k: []
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.build_candidate_matrix",
        lambda: [CandidateSpec(model="gpt-5.2", reasoning_effort="low")],
    )

    run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=tmp_path / "cache.json",
        use_cache=False,
        timeout_sec=10,
        no_judge=True,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
        progress_callback=events.append,
    )

    assert events[0]["event"] == "start"
    assert any(e["event"] == "start" for e in events)
    assert events[0]["max_concurrency"] == 1
    assert any(e["event"] == "source_loaded" for e in events)
    assert any(e["event"] == "candidate_start" for e in events)
    row_events = [e for e in events if e["event"] == "row_complete"]
    assert row_events
    first_row = row_events[0]
    assert "deterministic_score" in first_row
    assert "label_match" in first_row
    assert "control_match" in first_row
    assert "additional_issues_count" in first_row
    assert "label_f1" in first_row
    assert "judge_score" in first_row
    assert "quality_score" in first_row
    assert "estimated_cost_usd" in first_row
    assert "row_elapsed_sec" in first_row
    candidate_done_events = [e for e in events if e["event"] == "candidate_complete"]
    assert candidate_done_events
    assert "rank_score" in candidate_done_events[0]
    assert "label_match" in candidate_done_events[0]
    assert "control_match" in candidate_done_events[0]
    assert "additional_issues_count" in candidate_done_events[0]
    assert "label_f1" in candidate_done_events[0]
    assert "avg_row_elapsed_sec" in candidate_done_events[0]
    assert "candidate_elapsed_sec" in candidate_done_events[0]
    assert events[-1]["event"] == "complete"
    assert "run_elapsed_sec" in events[-1]


def test_run_eval_pre_skips_known_unsupported_combos(monkeypatch, tmp_path):
    def should_not_be_called(**_kwargs):
        raise AssertionError("_evaluate_one should not run for unsupported combos")

    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._evaluate_one",
        should_not_be_called,
    )
    monkeypatch.setattr("tools.veda_dev.evals.runner.load_vedalang", lambda _p: {})
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.validate_vedalang",
        lambda _s, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c, **_k: []
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.build_candidate_matrix",
        lambda: [CandidateSpec(model="gpt-5-mini", reasoning_effort="high")],
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.model_supports_reasoning_effort",
        lambda _model, _effort: False,
    )

    run = run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=tmp_path / "cache.json",
        use_cache=False,
        timeout_sec=10,
        no_judge=True,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
    )

    assert len(run["results"]) == 5
    assert all(r["status"] == "skipped" for r in run["results"])
    assert all(
        "Unsupported model/effort combination" in str(r.get("error"))
        for r in run["results"]
    )


def test_label_metrics_reads_classification_fields():
    diagnostics = [
        {
            "code": "LLM_UNIT_CHECK",
            "context": {
                "error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH",
                "error_family": "cost_denominator",
                "difficulty": "easy",
            },
        }
    ]
    expected = {
        "labels": [
            {
                "error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH",
                "error_family": "cost_denominator",
                "difficulty": "easy",
                "expected_presence": "present",
            }
        ]
    }
    metrics = label_metrics(diagnostics, expected=expected)
    assert metrics["enabled"] is True
    assert metrics["presence_hits"] == 1
    assert metrics["intentional_hits"] == 1
    assert metrics["intentional_total"] == 1
    assert metrics["intentional_match"] == "[1/1]"
    assert metrics["control_match"] == "[0/0]"
    assert metrics["additional_issue_count"] == 0
    assert metrics["f1"] == 100.0
    assert metrics["presence_accuracy"] == 100.0
    assert metrics["difficulty_accuracy"] == 100.0
    assert metrics["family_accuracy"] == 100.0


def test_label_metrics_counts_additional_unknown_issue_codes():
    diagnostics = [
        {
            "code": "LLM_UNIT_CHECK",
            "context": {
                "error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH",
                "error_family": "cost_denominator",
                "difficulty": "easy",
            },
        },
        {
            "code": "LLM_UNIT_CHECK",
            "context": {
                "error_code": "UNIT_UNKNOWN_NEW",
                "error_family": "other",
                "difficulty": "hard",
            },
        },
    ]
    expected = {
        "labels": [
            {
                "error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH",
                "error_family": "cost_denominator",
                "difficulty": "easy",
                "expected_presence": "present",
            }
        ]
    }
    metrics = label_metrics(diagnostics, expected=expected)
    assert metrics["intentional_match"] == "[1/1]"
    assert metrics["control_match"] == "[0/0]"
    assert metrics["additional_issue_count"] == 1
    assert metrics["additional_issue_codes"] == ["UNIT_UNKNOWN_NEW"]


def test_label_metrics_intentional_match_ignores_absent_controls():
    diagnostics = []
    expected = {
        "labels": [
            {
                "error_code": "STR_ZERO_INPUT_DEVICE",
                "error_family": "structural_topology",
                "difficulty": "easy",
                "expected_presence": "absent",
            },
            {
                "error_code": "STR_STAGE_MISMATCH",
                "error_family": "stage_semantics",
                "difficulty": "medium",
                "expected_presence": "absent",
            },
        ]
    }
    metrics = label_metrics(diagnostics, expected=expected)
    assert metrics["intentional_total"] == 0
    assert metrics["intentional_match"] == "[0/0]"
    assert metrics["control_match"] == "[2/2]"


def test_deterministic_breakdown_is_bounded_to_100():
    diagnostics = [
        {
            "code": "LLM_UNIT_CHECK",
            "category": "units",
            "engine": "llm",
            "check_id": "llm.units.component_quorum",
            "context": {
                "error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH",
                "error_family": "cost_denominator",
                "difficulty": "easy",
            },
        }
    ]
    expected = {
        "labels": [
            {
                "error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH",
                "error_family": "cost_denominator",
                "difficulty": "easy",
                "expected_presence": "present",
            }
        ]
    }
    breakdown = deterministic_breakdown(
        diagnostics=diagnostics,
        expected_category="units",
        expected_engine="llm",
        expected_check_id="llm.units.component_quorum",
        expected=expected,
        required_code_substrings=[],
        forbidden_code_substrings=[],
        deterministic_diagnostics=[],
    )
    assert breakdown["score"] <= 100.0


def test_parity_score_is_neutral_when_reference_missing():
    assert parity_score([{"code": "LLM_UNIT_CHECK"}], None) == 100.0

    breakdown = deterministic_breakdown(
        diagnostics=[{"code": "LLM_UNIT_CHECK"}],
        expected_category="units",
        expected_engine="llm",
        expected_check_id="llm.units.component_quorum",
        expected={},
        required_code_substrings=[],
        forbidden_code_substrings=[],
        deterministic_diagnostics=None,
    )
    assert breakdown["parity_score"] == 100.0


def test_parity_score_uses_error_code_overlap_when_available():
    diagnostics = [
        {
            "code": "LLM_UNIT_CHECK",
            "context": {"error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH"},
        }
    ]
    deterministic = [
        {
            "code": "E_UNIT_VARIABLE_COST_DENOM_MISMATCH",
            "context": {"error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH"},
        },
        {
            "code": "W_ENERGY_MASS_BASIS_REQUIRED",
            "context": {"error_code": "UNIT_BASIS_MISSING"},
        },
    ]
    score = parity_score(diagnostics, deterministic)
    assert 60.0 <= score <= 70.0


def test_deterministic_reference_units_handles_v0_2_component_cases():
    dataset = load_dataset()
    case = dataset.cases["u02"]
    source_path = case.source
    from vedalang.compiler.compiler import load_vedalang

    source = load_vedalang(Path(source_path))
    reference = _deterministic_reference(
        source,
        "units",
        check_id=case.check_id,
        component=case.component,
    )
    assert reference is not None
    assert isinstance(reference, list)


def test_run_eval_parallelizes_rows(monkeypatch, tmp_path):
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_evaluate_one(**_kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return {
            "status": "ok",
            "diagnostics": [],
            "telemetry": [],
            "error": None,
            "cached": False,
        }

    monkeypatch.setattr("tools.veda_dev.evals.runner._evaluate_one", fake_evaluate_one)
    monkeypatch.setattr("tools.veda_dev.evals.runner.load_vedalang", lambda _p: {})
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.validate_vedalang",
        lambda _s, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c, **_k: []
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.build_candidate_matrix",
        lambda: [
            CandidateSpec(model="gpt-5-nano", reasoning_effort="low"),
            CandidateSpec(model="gpt-5-mini", reasoning_effort="low"),
            CandidateSpec(model="gpt-5.2", reasoning_effort="low"),
        ],
    )

    run = run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=tmp_path / "cache.json",
        use_cache=False,
        timeout_sec=10,
        max_concurrency=4,
        no_judge=True,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
    )

    assert len(run["results"]) == 15
    assert run["timing"]["max_concurrency"] == 4
    assert max_active >= 2


def test_run_eval_survives_deterministic_reference_errors(monkeypatch, tmp_path):
    def fake_evaluate_one(**_kwargs):
        return {
            "status": "ok",
            "diagnostics": [],
            "telemetry": [],
            "error": None,
            "cached": False,
        }

    def broken_collect(_source):
        raise RuntimeError(
            "1 structural invariant violation(s):\n"
            "  - [E_COMMODITY_TYPE_ENUM] x: bad commodity type"
        )

    monkeypatch.setattr("tools.veda_dev.evals.runner._evaluate_one", fake_evaluate_one)
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.collect_structural_by_category",
        broken_collect,
    )
    monkeypatch.setattr("tools.veda_dev.evals.runner.load_vedalang", lambda _p: {})
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.validate_vedalang",
        lambda _s, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.build_candidate_matrix",
        lambda: [CandidateSpec(model="gpt-5.2", reasoning_effort="low")],
    )

    run = run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=tmp_path / "cache.json",
        use_cache=False,
        timeout_sec=10,
        no_judge=True,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
        max_concurrency=1,
    )

    assert len(run["results"]) == 5
    assert any(r["status"] == "ok" for r in run["results"])
    assert run["timing"]["completed_runs"] == 5


def test_run_eval_orders_results_by_case_effort_model(monkeypatch, tmp_path):
    def fake_evaluate_one(**_kwargs):
        return {
            "status": "ok",
            "diagnostics": [],
            "telemetry": [],
            "error": None,
            "cached": False,
        }

    monkeypatch.setattr("tools.veda_dev.evals.runner._evaluate_one", fake_evaluate_one)
    monkeypatch.setattr("tools.veda_dev.evals.runner.load_vedalang", lambda _p: {})
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.validate_vedalang",
        lambda _s, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c, **_k: []
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.build_candidate_matrix",
        lambda: [
            CandidateSpec(model="gpt-5-mini", reasoning_effort="low"),
            CandidateSpec(model="gpt-5-nano", reasoning_effort="low"),
            CandidateSpec(model="gpt-5.2", reasoning_effort="low"),
            CandidateSpec(model="gpt-5.2", reasoning_effort="medium"),
        ],
    )

    run = run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=tmp_path / "cache.json",
        use_cache=False,
        timeout_sec=10,
        no_judge=True,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
        max_concurrency=1,
    )

    first_group = run["results"][:3]
    assert [r["candidate_id"] for r in first_group] == [
        "gpt-5-nano:low",
        "gpt-5-mini:low",
        "gpt-5.2:low",
    ]
    assert all(r["case_id"] == "s01@v1" for r in first_group)
    assert all(r["reasoning_effort"] == "low" for r in first_group)
    assert run["results"][3]["candidate_id"] == "gpt-5.2:medium"
    assert run["results"][3]["case_id"] == "s01@v1"
    assert run["results"][4]["candidate_id"] == "gpt-5-nano:low"
    assert run["results"][4]["case_id"] == "s02@v1"


def test_run_eval_cache_reuses_judge_results(monkeypatch, tmp_path):
    judge_calls = 0

    def fake_evaluate_one(**_kwargs):
        return {
            "status": "ok",
            "diagnostics": [{"code": "LLM_UNIT_CHECK"}],
            "telemetry": [],
            "error": None,
            "cached": False,
        }

    def fake_run_judge(**_kwargs):
        nonlocal judge_calls
        judge_calls += 1

        class FakeJudge:
            score_0_to_100 = 70.0
            actionability_score = 80.0
            hallucination_flag = False
            major_errors = []
            rationale_short = "ok"
            error = None
            telemetry = {"latency_sec": 0.1}

        return FakeJudge()

    monkeypatch.setattr("tools.veda_dev.evals.runner._evaluate_one", fake_evaluate_one)
    monkeypatch.setattr("tools.veda_dev.evals.runner.run_judge", fake_run_judge)
    monkeypatch.setattr("tools.veda_dev.evals.runner.load_vedalang", lambda _p: {})
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.validate_vedalang",
        lambda _s, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c, **_k: []
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.build_candidate_matrix",
        lambda: [CandidateSpec(model="gpt-5.2", reasoning_effort="low")],
    )

    cache_path = tmp_path / "cache.json"
    run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=cache_path,
        use_cache=True,
        timeout_sec=10,
        no_judge=False,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
        max_concurrency=1,
    )
    first_calls = judge_calls
    assert first_calls == 5

    run_eval(
        profile="smoke",
        prompt_version="v1",
        dataset_path=None,
        cache_path=cache_path,
        use_cache=True,
        timeout_sec=10,
        no_judge=False,
        judge_model="gpt-5.2",
        judge_effort="xhigh",
        max_concurrency=1,
    )
    assert judge_calls == first_calls
