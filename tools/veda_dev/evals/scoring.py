"""Deterministic and aggregate scoring for eval runs."""

from __future__ import annotations

from typing import Any

from tools.veda_dev.evals.config import MODEL_PRICING_PER_1M


def _bounded(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def taxonomy_score(
    diagnostics: list[dict[str, Any]],
    *,
    expected_category: str,
    expected_engine: str,
    expected_check_id: str,
) -> float:
    if not diagnostics:
        return 100.0
    ok = 0
    for d in diagnostics:
        if (
            str(d.get("category")) == expected_category
            and str(d.get("engine")) == expected_engine
            and str(d.get("check_id")) == expected_check_id
        ):
            ok += 1
    return 100.0 * ok / len(diagnostics)


def expected_signal_score(
    diagnostics: list[dict[str, Any]],
    *,
    required_code_substrings: list[str],
    forbidden_code_substrings: list[str],
) -> float:
    codes = [str(d.get("code", "")) for d in diagnostics]
    score = 100.0
    for required in required_code_substrings:
        if not any(required in code for code in codes):
            score -= 20.0
    for forbidden in forbidden_code_substrings:
        if any(forbidden in code for code in codes):
            score -= 20.0
    return _bounded(score)


def parity_score(
    diagnostics: list[dict[str, Any]],
    deterministic_diagnostics: list[dict[str, Any]],
) -> float:
    llm_present = len(diagnostics) > 0
    det_present = len(deterministic_diagnostics) > 0
    return 100.0 if llm_present == det_present else 0.0


def deterministic_score(
    *,
    diagnostics: list[dict[str, Any]],
    expected_category: str,
    expected_engine: str,
    expected_check_id: str,
    required_code_substrings: list[str],
    forbidden_code_substrings: list[str],
    deterministic_diagnostics: list[dict[str, Any]],
) -> float:
    components = [
        100.0,  # JSON/schema validity (runner normalizes structure)
        taxonomy_score(
            diagnostics,
            expected_category=expected_category,
            expected_engine=expected_engine,
            expected_check_id=expected_check_id,
        ),
        expected_signal_score(
            diagnostics,
            required_code_substrings=required_code_substrings,
            forbidden_code_substrings=forbidden_code_substrings,
        ),
        parity_score(diagnostics, deterministic_diagnostics),
    ]
    return sum(components) / len(components)


def estimate_cost_usd(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    pricing = MODEL_PRICING_PER_1M.get(model)
    if pricing is None:
        return None
    return (input_tokens / 1_000_000.0) * pricing["input"] + (
        output_tokens / 1_000_000.0
    ) * pricing["output"]


def efficiency_score(
    *,
    p50_latency_sec: float,
    avg_cost_usd: float,
) -> float:
    latency_component = _bounded(100.0 - (p50_latency_sec * 10.0))
    cost_component = _bounded(100.0 - (avg_cost_usd * 500.0))
    return (latency_component + cost_component) / 2.0


def aggregate_quality_score(
    *,
    deterministic: float,
    judge: float | None,
    deterministic_weight: float,
    judge_weight: float,
) -> float:
    if judge is None:
        return deterministic
    return (deterministic_weight * deterministic) + (judge_weight * judge)


def aggregate_rank_score(
    *,
    quality_score: float,
    efficiency_score_value: float,
    quality_weight: float,
    efficiency_weight: float,
) -> float:
    return (quality_weight * quality_score) + (
        efficiency_weight * efficiency_score_value
    )
