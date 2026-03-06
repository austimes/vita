"""Deterministic and aggregate scoring for eval runs."""

from __future__ import annotations

from dataclasses import dataclass
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
    deterministic_diagnostics: list[dict[str, Any]] | None,
) -> float:
    if deterministic_diagnostics is None:
        return 100.0
    llm_codes = _diagnostic_error_codes(diagnostics)
    det_codes = _diagnostic_error_codes(deterministic_diagnostics)
    if llm_codes or det_codes:
        if not llm_codes and not det_codes:
            return 100.0
        if not llm_codes or not det_codes:
            return 0.0
        tp = len(llm_codes & det_codes)
        if tp == 0:
            return 0.0
        fp = len(llm_codes - det_codes)
        fn = len(det_codes - llm_codes)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0:
            return 0.0
        return 100.0 * ((2.0 * precision * recall) / (precision + recall))
    llm_present = len(diagnostics) > 0
    det_present = len(deterministic_diagnostics) > 0
    return 100.0 if llm_present == det_present else 0.0


def _diagnostic_error_codes(diagnostics: list[dict[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for diag in diagnostics:
        context = diag.get("context")
        if isinstance(context, dict):
            error_code = context.get("error_code")
            if isinstance(error_code, str) and error_code:
                codes.add(error_code)
        code = diag.get("code")
        if isinstance(code, str) and code.startswith("UNIT_"):
            codes.add(code)
    return codes


@dataclass(frozen=True)
class ExpectedLabel:
    error_code: str
    error_family: str
    difficulty: str
    expected_presence: str


def _normalize_expected_labels(expected: dict[str, Any]) -> list[ExpectedLabel]:
    labels = expected.get("labels")
    if not isinstance(labels, list):
        return []
    normalized: list[ExpectedLabel] = []
    for item in labels:
        if not isinstance(item, dict):
            continue
        code = str(item.get("error_code", "")).strip()
        if not code:
            continue
        family = str(item.get("error_family", "unknown")).strip() or "unknown"
        difficulty = str(item.get("difficulty", "medium")).strip() or "medium"
        presence = str(item.get("expected_presence", "present")).strip().lower()
        if presence not in {"present", "absent"}:
            presence = "present"
        normalized.append(
            ExpectedLabel(
                error_code=code,
                error_family=family,
                difficulty=difficulty,
                expected_presence=presence,
            )
        )
    return normalized


def _predicted_labels(diagnostics: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    by_code: dict[str, dict[str, str]] = {}
    for d in diagnostics:
        context = d.get("context")
        if not isinstance(context, dict):
            context = {}
        code = str(
            context.get("error_code")
            or context.get("classification_code")
            or d.get("error_code")
            or ""
        ).strip()
        if not code:
            continue
        family = str(
            context.get("error_family")
            or context.get("family")
            or d.get("error_family")
            or d.get("category")
            or "unknown"
        ).strip() or "unknown"
        difficulty = str(
            context.get("difficulty")
            or context.get("difficulty_level")
            or d.get("difficulty")
            or "unspecified"
        ).strip() or "unspecified"
        by_code[code] = {
            "error_code": code,
            "error_family": family,
            "difficulty": difficulty,
        }
    return by_code


def _safe_ratio(numerator: float, denominator: float, default: float = 100.0) -> float:
    if denominator <= 0:
        return default
    return 100.0 * numerator / denominator


def label_metrics(
    diagnostics: list[dict[str, Any]],
    *,
    expected: dict[str, Any],
) -> dict[str, Any]:
    expected_labels = _normalize_expected_labels(expected)
    if not expected_labels:
        return {
            "enabled": False,
            "precision": None,
            "recall": None,
            "f1": None,
            "presence_accuracy": None,
            "difficulty_accuracy": None,
            "family_accuracy": None,
            "presence_hits": None,
            "intentional_hits": None,
            "intentional_total": None,
            "intentional_match": None,
            "control_hits": None,
            "control_total": None,
            "control_match": None,
            "known_false_positive_count": None,
            "additional_issue_count": None,
            "additional_issue_codes": [],
            "tp": None,
            "fp": None,
            "fn": None,
            "expected_count": 0,
            "predicted_count": 0,
            "by_difficulty": {},
            "by_family": {},
        }

    predicted = _predicted_labels(diagnostics)
    expected_present = [x for x in expected_labels if x.expected_presence == "present"]
    expected_absent = [x for x in expected_labels if x.expected_presence == "absent"]

    expected_present_codes = {x.error_code for x in expected_present}
    expected_all_codes = {x.error_code for x in expected_labels}
    expected_absent_codes = {x.error_code for x in expected_absent}
    predicted_codes = set(predicted.keys())

    tp = len(expected_present_codes & predicted_codes)
    fp = len(predicted_codes - expected_present_codes)
    fn = len(expected_present_codes - predicted_codes)

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = (2.0 * precision * recall) / (precision + recall)

    presence_hits = 0
    intentional_hits = 0
    for label in expected_present:
        if label.error_code in predicted_codes:
            intentional_hits += 1
            presence_hits += 1
    control_hits = 0
    for label in expected_absent:
        if label.error_code not in predicted_codes:
            control_hits += 1
            presence_hits += 1
    presence_accuracy = _safe_ratio(presence_hits, len(expected_labels))
    intentional_total = len(expected_present)
    intentional_match = f"[{intentional_hits}/{intentional_total}]"
    control_total = len(expected_absent)
    control_match = f"[{control_hits}/{control_total}]"
    known_false_positive_count = len(predicted_codes & expected_absent_codes)
    additional_issue_codes = sorted(predicted_codes - expected_all_codes)
    additional_issue_count = len(additional_issue_codes)

    difficulty_checks = 0
    difficulty_hits = 0
    by_difficulty_counts: dict[str, dict[str, int]] = {}
    for label in expected_present:
        level = label.difficulty
        bucket = by_difficulty_counts.setdefault(level, {"expected": 0, "matched": 0})
        bucket["expected"] += 1
        pred = predicted.get(label.error_code)
        if pred is None:
            continue
        difficulty_checks += 1
        if pred.get("difficulty") == label.difficulty:
            difficulty_hits += 1
            bucket["matched"] += 1
    difficulty_accuracy = _safe_ratio(
        difficulty_hits,
        difficulty_checks,
        default=100.0,
    )

    family_checks = 0
    family_hits = 0
    by_family_counts: dict[str, dict[str, int]] = {}
    for label in expected_present:
        family = label.error_family
        bucket = by_family_counts.setdefault(
            family,
            {"expected": 0, "predicted": 0, "tp": 0, "fp": 0, "fn": 0},
        )
        bucket["expected"] += 1
        pred = predicted.get(label.error_code)
        if pred is None:
            bucket["fn"] += 1
            continue
        bucket["predicted"] += 1
        family_checks += 1
        if pred.get("error_family") == label.error_family:
            family_hits += 1
            bucket["tp"] += 1
        else:
            bucket["fp"] += 1
            bucket["fn"] += 1
    family_accuracy = _safe_ratio(
        family_hits,
        family_checks,
        default=100.0,
    )

    by_difficulty = {
        level: {
            "expected": counts["expected"],
            "matched": counts["matched"],
            "accuracy": _safe_ratio(
                counts["matched"],
                counts["expected"],
                default=0.0 if counts["expected"] == 0 else 100.0,
            ),
        }
        for level, counts in sorted(by_difficulty_counts.items())
    }
    by_family = {
        family: {
            **counts,
            "precision": _safe_ratio(
                counts["tp"],
                counts["tp"] + counts["fp"],
                default=0.0 if (counts["tp"] + counts["fp"]) == 0 else 100.0,
            ),
            "recall": _safe_ratio(
                counts["tp"],
                counts["tp"] + counts["fn"],
                default=0.0 if (counts["tp"] + counts["fn"]) == 0 else 100.0,
            ),
        }
        for family, counts in sorted(by_family_counts.items())
    }

    return {
        "enabled": True,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "presence_accuracy": presence_accuracy,
        "presence_hits": presence_hits,
        "intentional_hits": intentional_hits,
        "intentional_total": intentional_total,
        "intentional_match": intentional_match,
        "control_hits": control_hits,
        "control_total": control_total,
        "control_match": control_match,
        "known_false_positive_count": known_false_positive_count,
        "additional_issue_count": additional_issue_count,
        "additional_issue_codes": additional_issue_codes,
        "difficulty_accuracy": difficulty_accuracy,
        "family_accuracy": family_accuracy,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "expected_count": len(expected_labels),
        "predicted_count": len(predicted_codes),
        "by_difficulty": by_difficulty,
        "by_family": by_family,
    }


def deterministic_breakdown(
    *,
    diagnostics: list[dict[str, Any]],
    expected_category: str,
    expected_engine: str,
    expected_check_id: str,
    expected: dict[str, Any],
    required_code_substrings: list[str],
    forbidden_code_substrings: list[str],
    deterministic_diagnostics: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    taxonomy = taxonomy_score(
        diagnostics,
        expected_category=expected_category,
        expected_engine=expected_engine,
        expected_check_id=expected_check_id,
    )
    signal = expected_signal_score(
        diagnostics,
        required_code_substrings=required_code_substrings,
        forbidden_code_substrings=forbidden_code_substrings,
    )
    parity = parity_score(diagnostics, deterministic_diagnostics)
    labels = label_metrics(diagnostics, expected=expected)

    if labels["enabled"]:
        label_quality = (
            (labels["f1"] or 0.0)
            + (labels["presence_accuracy"] or 0.0)
            + (labels["difficulty_accuracy"] or 0.0)
            + (labels["family_accuracy"] or 0.0)
        ) / 4.0
        score = (
            100.0  # schema validity
            + taxonomy
            + signal
            + parity
            + label_quality
        ) / 5.0
    else:
        score = (100.0 + taxonomy + signal + parity) / 4.0

    return {
        "score": score,
        "taxonomy_score": taxonomy,
        "expected_signal_score": signal,
        "parity_score": parity,
        "label_metrics": labels,
    }


def deterministic_score(
    *,
    diagnostics: list[dict[str, Any]],
    expected_category: str,
    expected_engine: str,
    expected_check_id: str,
    expected: dict[str, Any] | None = None,
    required_code_substrings: list[str],
    forbidden_code_substrings: list[str],
    deterministic_diagnostics: list[dict[str, Any]],
) -> float:
    return deterministic_breakdown(
        diagnostics=diagnostics,
        expected_category=expected_category,
        expected_engine=expected_engine,
        expected_check_id=expected_check_id,
        expected=expected or {},
        required_code_substrings=required_code_substrings,
        forbidden_code_substrings=forbidden_code_substrings,
        deterministic_diagnostics=deterministic_diagnostics,
    )["score"]


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
