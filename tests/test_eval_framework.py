"""Tests for eval framework scaffold."""

from __future__ import annotations

from tools.veda_dev.evals.config import CandidateSpec, build_candidate_matrix
from tools.veda_dev.evals.dataset import cases_for_profile, load_dataset
from tools.veda_dev.evals.judge import parse_judge_response
from tools.veda_dev.evals.runner import compare_runs, run_eval


def test_candidate_matrix_has_15_entries():
    candidates = build_candidate_matrix()
    assert len(candidates) == 15


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
        if effort == "xhigh":
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
        "tools.veda_dev.evals.runner.validate_vedalang", lambda _s: None
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c: []
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
    assert len(run["candidates"]) == 15
    assert len(run["results"]) == 15 * 5  # profile smoke expands to 5 cases at v1
    assert any(r["status"] == "skipped" for r in run["results"])
    assert all("telemetry" in r for r in run["results"])


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
        "tools.veda_dev.evals.runner.validate_vedalang", lambda _s: None
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner._deterministic_reference", lambda _s, _c: []
    )
    monkeypatch.setattr(
        "tools.veda_dev.evals.runner.build_candidate_matrix",
        lambda: [CandidateSpec(model="gpt-5.2", reasoning_effort="none")],
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
    assert any(e["event"] == "source_loaded" for e in events)
    assert any(e["event"] == "candidate_start" for e in events)
    row_events = [e for e in events if e["event"] == "row_complete"]
    assert row_events
    first_row = row_events[0]
    assert "deterministic_score" in first_row
    assert "judge_score" in first_row
    assert "quality_score" in first_row
    assert "estimated_cost_usd" in first_row
    candidate_done_events = [e for e in events if e["event"] == "candidate_complete"]
    assert candidate_done_events
    assert "rank_score" in candidate_done_events[0]
    assert events[-1]["event"] == "complete"
