"""Eval runner for lint/llm-lint model/effort benchmarking."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from threading import Lock
from time import perf_counter
from typing import Any

from vedalang.compiler.compiler import load_vedalang, validate_vedalang
from vedalang.lint.code_categories import collect_structural_by_category
from vedalang.lint.diagnostics import with_meta
from vedalang.lint.llm_assessment import CHECK_ID as STRUCTURE_CHECK_ID
from vedalang.lint.llm_assessment import run_llm_assessment
from vedalang.lint.llm_runtime import canonical_model_name
from vedalang.lint.llm_unit_check import CHECK_ID as UNITS_CHECK_ID
from vedalang.lint.llm_unit_check import run_component_unit_check
from vedalang.lint.prompt_registry import resolve_prompt_versions

from .config import (
    MODEL_FAMILIES,
    REASONING_LEVELS,
    EvalWeights,
    build_candidate_matrix,
    model_supports_reasoning_effort,
)
from .dataset import EvalCase, cases_for_profile, load_dataset
from .judge import run_judge
from .scoring import (
    aggregate_quality_score,
    aggregate_rank_score,
    deterministic_breakdown,
    efficiency_score,
    estimate_cost_usd,
)


@dataclass
class ExpandedCase:
    case: EvalCase
    prompt_version: str

    @property
    def expanded_case_id(self) -> str:
        return f"{self.case.case_id}@{self.prompt_version}"


ProgressCallback = Callable[[dict[str, Any]], None]


def _emit_progress(
    progress_callback: ProgressCallback | None,
    event: str,
    **payload: Any,
) -> None:
    if progress_callback is None:
        return
    progress_callback({"event": event, **payload})


def _is_unsupported_combo_error(message: str) -> bool:
    lowered = message.lower()
    markers = [
        "unsupported",
        "does not support",
        "invalid value",
        "not available for",
    ]
    return any(marker in lowered for marker in markers)


def _cache_key(
    *, case_id: str, check_id: str, model: str, effort: str, prompt_version: str
) -> str:
    raw = json.dumps(
        {
            "case_id": case_id,
            "check_id": check_id,
            "model": model,
            "effort": effort,
            "prompt_version": prompt_version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _judge_cache_key(
    *,
    case_id: str,
    candidate_id: str,
    judge_model: str,
    judge_effort: str,
    diagnostics: list[dict[str, Any]],
    deterministic_score_value: float,
) -> str:
    raw = json.dumps(
        {
            "kind": "judge",
            "case_id": case_id,
            "candidate_id": candidate_id,
            "judge_model": judge_model,
            "judge_effort": judge_effort,
            "diagnostics": diagnostics,
            "deterministic_score": deterministic_score_value,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _cache_get(
    cache: dict[str, Any], key: str, lock: Lock | None
) -> dict[str, Any] | None:
    if lock is None:
        value = cache.get(key)
    else:
        with lock:
            value = cache.get(key)
    if value is None:
        return None
    return dict(value)


def _cache_set(
    cache: dict[str, Any], key: str, value: dict[str, Any], lock: Lock | None
) -> None:
    if lock is None:
        cache[key] = value
        return
    with lock:
        cache[key] = value


def _normalize_structure_diagnostics(
    result: Any, prompt_version: str
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for finding in result.findings:
        data = finding.to_dict()
        llm_subcategory = data.get("category")
        context = data.get("context") or {}
        if llm_subcategory:
            context["llm_subcategory"] = llm_subcategory
        context["prompt_version"] = prompt_version
        context["llm_model"] = result.model
        data["context"] = context
        data["category"] = "structure"
        diagnostics.append(
            with_meta(
                data,
                category="structure",
                engine="llm",
                check_id=STRUCTURE_CHECK_ID,
            )
        )
    return diagnostics


def _normalize_units_diagnostics(
    result: Any, prompt_version: str
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for vote in result.votes:
        if not vote.findings and vote.status != "pass":
            diagnostics.append(
                with_meta(
                    {
                        "code": "LLM_UNIT_CHECK",
                        "severity": "warning",
                        "location": f"{result.component} [{vote.model}]",
                        "message": (
                            "LLM returned non-pass status but provided no findings."
                        ),
                        "context": {"prompt_version": prompt_version},
                    },
                    category="units",
                    engine="llm",
                    check_id=UNITS_CHECK_ID,
                )
            )
            continue
        for finding in vote.findings:
            location = f"{result.component} [{vote.model}]"
            if finding.get("field"):
                location = f"{location} :: {finding.get('field')}"
            diagnostics.append(
                with_meta(
                    {
                        "code": "LLM_UNIT_CHECK",
                        "severity": finding.get("severity", "warning"),
                        "location": location,
                        "message": str(finding.get("message", "No message provided.")),
                        "suggestion": finding.get("suggestion"),
                        "context": {
                            "expected_process_units": finding.get(
                                "expected_process_units"
                            ),
                            "expected_commodity_units": finding.get(
                                "expected_commodity_units"
                            ),
                            "observed_units": finding.get("observed_units"),
                            "model_expectation": finding.get("model_expectation"),
                            "error_code": finding.get("error_code"),
                            "error_family": finding.get("error_family"),
                            "difficulty": finding.get("difficulty"),
                            "prompt_version": prompt_version,
                        },
                    },
                    category="units",
                    engine="llm",
                    check_id=UNITS_CHECK_ID,
                )
            )
    return diagnostics


def _deterministic_reference(source: dict, category: str) -> list[dict[str, Any]]:
    if category not in {"structure", "units"}:
        return []
    try:
        grouped = collect_structural_by_category(source)
        return list(grouped.get(category, []))
    except Exception as exc:
        text = str(exc)
        parsed: list[dict[str, Any]] = []
        for line in text.splitlines():
            match = re.search(r"\[(?P<code>[EW]_[A-Z0-9_]+)\]", line)
            if not match:
                continue
            code = match.group("code")
            message = line.split("]", 1)[-1].strip()
            if message.startswith("-"):
                message = message[1:].strip()
            severity = "warning" if code.startswith("W_") else "error"
            parsed.append(
                with_meta(
                    {
                        "code": code,
                        "severity": severity,
                        "message": message,
                    },
                    category=category,
                    engine="code",
                    check_id=f"code.{category}.compiler_semantics",
                )
            )
        if parsed:
            return parsed
        return [
            with_meta(
                {
                    "code": "E_DETERMINISTIC_REFERENCE",
                    "severity": "error",
                    "message": (
                        "Failed to build deterministic reference diagnostics: "
                        f"{exc}"
                    ),
                },
                category=category,
                engine="code",
                check_id=f"code.{category}.compiler_semantics",
            )
        ]


def _evaluate_one(
    *,
    expanded_case: ExpandedCase,
    source: dict[str, Any],
    model: str,
    effort: str,
    timeout_sec: int,
    cache: dict[str, Any],
    use_cache: bool,
) -> dict[str, Any]:
    case = expanded_case.case
    cache_key = _cache_key(
        case_id=case.case_id,
        check_id=case.check_id,
        model=model,
        effort=effort,
        prompt_version=expanded_case.prompt_version,
    )

    if use_cache and cache_key in cache:
        cached = dict(cache[cache_key])
        cached["cached"] = True
        return cached

    diagnostics: list[dict[str, Any]] = []
    telemetry_rows: list[dict[str, Any]] = []

    try:
        if case.check_id == STRUCTURE_CHECK_ID:
            assessment = run_llm_assessment(
                source,
                model=model,
                reasoning_effort=effort,
                prompt_version=expanded_case.prompt_version,
                timeout_sec=timeout_sec,
            )
            diagnostics = _normalize_structure_diagnostics(
                assessment,
                expanded_case.prompt_version,
            )
            if assessment.telemetry:
                telemetry_rows.append(
                    {
                        "model": assessment.model,
                        **assessment.telemetry,
                    }
                )
        elif case.check_id == UNITS_CHECK_ID:
            if not case.component:
                raise ValueError(f"Units case '{case.case_id}' missing component")
            check = run_component_unit_check(
                source=source,
                component=case.component,
                models=[model],
                reasoning_effort=effort,
                prompt_version=expanded_case.prompt_version,
                timeout_sec=timeout_sec,
            )
            diagnostics = _normalize_units_diagnostics(
                check, expanded_case.prompt_version
            )
            for vote in check.votes:
                if vote.telemetry:
                    telemetry_rows.append(
                        {
                            "model": vote.model,
                            **vote.telemetry,
                        }
                    )
        else:
            raise ValueError(f"Unsupported check_id in dataset: {case.check_id}")

        payload = {
            "status": "ok",
            "diagnostics": diagnostics,
            "telemetry": telemetry_rows,
            "error": None,
            "cached": False,
        }
    except Exception as e:
        message = str(e)
        payload = {
            "status": "skipped" if _is_unsupported_combo_error(message) else "error",
            "diagnostics": [],
            "telemetry": [],
            "error": message,
            "cached": False,
        }

    cache[cache_key] = payload
    return payload


def _evaluate_one_cached_threadsafe(
    *,
    expanded_case: ExpandedCase,
    source: dict[str, Any],
    model: str,
    effort: str,
    timeout_sec: int,
    cache: dict[str, Any],
    use_cache: bool,
    cache_lock: Lock | None,
) -> dict[str, Any]:
    """Thread-safe cache wrapper around `_evaluate_one`."""
    case = expanded_case.case
    cache_key = _cache_key(
        case_id=case.case_id,
        check_id=case.check_id,
        model=model,
        effort=effort,
        prompt_version=expanded_case.prompt_version,
    )

    if use_cache:
        cached_payload = _cache_get(cache, cache_key, cache_lock)
        if cached_payload is not None:
            cached = cached_payload
            cached["cached"] = True
            return cached

    # Avoid concurrent writes to shared cache by using a local scratch cache.
    evaluated = _evaluate_one(
        expanded_case=expanded_case,
        source=source,
        model=model,
        effort=effort,
        timeout_sec=timeout_sec,
        cache={},
        use_cache=False,
    )

    _cache_set(cache, cache_key, evaluated, cache_lock)
    return evaluated


def _evaluate_row(
    *,
    candidate: Any,
    candidate_index: int,
    expanded_case: ExpandedCase,
    expanded_case_index: int,
    case_source: dict[str, Any],
    det_reference: list[dict[str, Any]],
    timeout_sec: int,
    cache: dict[str, Any],
    use_cache: bool,
    cache_lock: Lock | None,
    no_judge: bool,
    judge_model: str,
    judge_effort: str,
    weights: EvalWeights,
) -> dict[str, Any]:
    """Evaluate one (candidate, expanded-case) row and compute scores."""
    row_started = perf_counter()
    case = expanded_case.case

    try:
        if not model_supports_reasoning_effort(
            candidate.model, candidate.reasoning_effort
        ):
            evaluated = {
                "status": "skipped",
                "diagnostics": [],
                "telemetry": [],
                "error": (
                    "Unsupported model/effort combination: "
                    f"{candidate.model}:{candidate.reasoning_effort}"
                ),
                "cached": False,
            }
        else:
            evaluated = _evaluate_one_cached_threadsafe(
                expanded_case=expanded_case,
                source=case_source,
                model=candidate.model,
                effort=candidate.reasoning_effort,
                timeout_sec=timeout_sec,
                cache=cache,
                use_cache=use_cache,
                cache_lock=cache_lock,
            )

        required = [
            str(x) for x in (case.expected.get("required_code_substrings") or [])
        ]
        forbidden = [
            str(x) for x in (case.expected.get("forbidden_code_substrings") or [])
        ]

        det_score = 0.0
        judge_score = None
        quality_score = 0.0
        est_cost = None
        label_match_hits: int | None = None
        label_match_total: int | None = None
        label_match: str | None = None
        additional_issues_count: int | None = None
        additional_issue_codes: list[str] = []

        if evaluated["status"] == "ok":
            det_breakdown = deterministic_breakdown(
                diagnostics=evaluated["diagnostics"],
                expected_category=case.category,
                expected_engine=case.engine,
                expected_check_id=case.check_id,
                expected=case.expected,
                required_code_substrings=required,
                forbidden_code_substrings=forbidden,
                deterministic_diagnostics=det_reference,
            )
            det_score = float(det_breakdown["score"])
            label_metrics = (
                det_breakdown.get("label_metrics", {})
                if isinstance(det_breakdown, dict)
                else {}
            )
            if isinstance(label_metrics, dict) and label_metrics.get("enabled"):
                hits = label_metrics.get("intentional_hits")
                total = label_metrics.get("intentional_total")
                if isinstance(hits, int) and isinstance(total, int):
                    label_match_hits = hits
                    label_match_total = total
                    label_match = f"[{hits}/{total}]" if total > 0 else None
                extra_count = label_metrics.get("additional_issue_count")
                if isinstance(extra_count, int):
                    additional_issues_count = extra_count
                extra_codes = label_metrics.get("additional_issue_codes")
                if isinstance(extra_codes, list):
                    additional_issue_codes = [str(c) for c in extra_codes]

            telemetry = evaluated.get("telemetry") or []
            if telemetry:
                in_tokens = sum((t.get("input_tokens") or 0) for t in telemetry)
                out_tokens = sum((t.get("output_tokens") or 0) for t in telemetry)
                est_cost = estimate_cost_usd(candidate.model, in_tokens, out_tokens)

            judge_result = None
            judge_payload: dict[str, Any] | None = None
            if not no_judge:
                judge_key = _judge_cache_key(
                    case_id=expanded_case.expanded_case_id,
                    candidate_id=candidate.candidate_id,
                    judge_model=judge_model,
                    judge_effort=judge_effort,
                    diagnostics=evaluated["diagnostics"],
                    deterministic_score_value=det_score,
                )
                if use_cache:
                    judge_payload = _cache_get(cache, judge_key, cache_lock)

                if judge_payload is None:
                    judge_result = run_judge(
                        sample={
                            "case_id": expanded_case.expanded_case_id,
                            "check_id": case.check_id,
                            "candidate": candidate.candidate_id,
                            "expected": case.expected,
                            "diagnostics": evaluated["diagnostics"],
                            "deterministic_score": det_score,
                        },
                        judge_model=judge_model,
                        judge_effort=judge_effort,
                        timeout_sec=timeout_sec,
                    )
                    judge_payload = {
                        "score_0_to_100": judge_result.score_0_to_100,
                        "actionability_score": judge_result.actionability_score,
                        "hallucination_flag": judge_result.hallucination_flag,
                        "major_errors": judge_result.major_errors,
                        "rationale_short": judge_result.rationale_short,
                        "error": judge_result.error,
                        "telemetry": judge_result.telemetry,
                    }
                    _cache_set(cache, judge_key, judge_payload, cache_lock)

                judge_score = judge_payload.get("score_0_to_100")

            quality_score = aggregate_quality_score(
                deterministic=det_score,
                judge=judge_score,
                deterministic_weight=weights.deterministic_weight,
                judge_weight=weights.judge_weight,
            )

            evaluated["judge"] = None if no_judge else judge_payload

        row = {
            "_candidate_index": candidate_index,
            "_case_index": expanded_case_index,
            "case_id": expanded_case.expanded_case_id,
            "base_case_id": case.case_id,
            "candidate_id": candidate.candidate_id,
            "model": candidate.model,
            "reasoning_effort": candidate.reasoning_effort,
            "prompt_version": expanded_case.prompt_version,
            "check_id": case.check_id,
            "category": case.category,
            "engine": case.engine,
            "status": evaluated["status"],
            "cached": evaluated.get("cached", False),
            "error": evaluated.get("error"),
            "diagnostics": evaluated.get("diagnostics", []),
            "telemetry": evaluated.get("telemetry", []),
            "estimated_cost_usd": est_cost,
            "deterministic_score": det_score,
            "deterministic_breakdown": (
                det_breakdown if evaluated["status"] == "ok" else None
            ),
            "judge_score": judge_score,
            "quality_score": quality_score,
            "known_issues": case.expected.get("known_issues", []),
            "judge": evaluated.get("judge"),
            "label_match_hits": label_match_hits,
            "label_match_total": label_match_total,
            "label_match": label_match,
            "additional_issues_count": additional_issues_count,
            "additional_issue_codes": additional_issue_codes,
        }
    except Exception as e:
        row = {
            "_candidate_index": candidate_index,
            "_case_index": expanded_case_index,
            "case_id": expanded_case.expanded_case_id,
            "base_case_id": case.case_id,
            "candidate_id": candidate.candidate_id,
            "model": candidate.model,
            "reasoning_effort": candidate.reasoning_effort,
            "prompt_version": expanded_case.prompt_version,
            "check_id": case.check_id,
            "category": case.category,
            "engine": case.engine,
            "status": "error",
            "cached": False,
            "error": str(e),
            "diagnostics": [],
            "telemetry": [],
            "estimated_cost_usd": None,
            "deterministic_score": 0.0,
            "deterministic_breakdown": None,
            "judge_score": None,
            "quality_score": 0.0,
            "known_issues": case.expected.get("known_issues", []),
            "judge": None,
            "label_match_hits": None,
            "label_match_total": None,
            "label_match": None,
            "additional_issues_count": None,
            "additional_issue_codes": [],
        }

    row["row_elapsed_sec"] = perf_counter() - row_started
    return row


def _summarize_candidate_rows(
    rows: list[dict[str, Any]], weights: EvalWeights
) -> dict[str, Any]:
    row_elapsed_values = sorted(
        [
            float(r.get("row_elapsed_sec", 0.0) or 0.0)
            for r in rows
            if r.get("row_elapsed_sec") is not None
        ]
    )
    if row_elapsed_values:
        p50_row_elapsed = row_elapsed_values[len(row_elapsed_values) // 2]
        p95_row_elapsed = row_elapsed_values[
            min(len(row_elapsed_values) - 1, int(len(row_elapsed_values) * 0.95))
        ]
        avg_row_elapsed = mean(row_elapsed_values)
        total_row_elapsed = sum(row_elapsed_values)
    else:
        p50_row_elapsed = 0.0
        p95_row_elapsed = 0.0
        avg_row_elapsed = 0.0
        total_row_elapsed = 0.0

    valid_rows = [r for r in rows if r["status"] == "ok"]
    if not valid_rows:
        return {
            "deterministic_score": 0.0,
            "judge_score": None,
            "quality_score": 0.0,
            "efficiency_score": 0.0,
            "rank_score": 0.0,
            "p50_latency_sec": 0.0,
            "p95_latency_sec": 0.0,
            "avg_cost_usd": 0.0,
            "label_match_hits": 0,
            "label_match_total": 0,
            "label_match": "n/a",
            "additional_issues_count": 0,
            "label_precision": None,
            "label_recall": None,
            "label_f1": None,
            "label_presence_accuracy": None,
            "label_difficulty_accuracy": None,
            "label_family_accuracy": None,
            "avg_row_elapsed_sec": avg_row_elapsed,
            "p50_row_elapsed_sec": p50_row_elapsed,
            "p95_row_elapsed_sec": p95_row_elapsed,
            "total_row_elapsed_sec": total_row_elapsed,
            "ok_cases": 0,
            "skipped_cases": len([r for r in rows if r["status"] == "skipped"]),
            "error_cases": len([r for r in rows if r["status"] == "error"]),
        }

    deterministic_avg = mean(r["deterministic_score"] for r in valid_rows)
    label_metric_rows = [
        r.get("deterministic_breakdown", {}).get("label_metrics", {})
        for r in valid_rows
        if isinstance(r.get("deterministic_breakdown"), dict)
        and isinstance(
            r.get("deterministic_breakdown", {}).get("label_metrics"),
            dict,
        )
        and r.get("deterministic_breakdown", {})
        .get("label_metrics", {})
        .get("enabled")
    ]
    label_match_hits_sum = 0
    label_match_total_sum = 0
    for m in label_metric_rows:
        hits = m.get("intentional_hits")
        total = m.get("intentional_total")
        if isinstance(hits, int) and isinstance(total, int):
            label_match_hits_sum += hits
            label_match_total_sum += total
    label_match = (
        f"[{label_match_hits_sum}/{label_match_total_sum}]"
        if label_match_total_sum > 0
        else "n/a"
    )
    additional_issues_total = 0
    for m in label_metric_rows:
        extra_count = m.get("additional_issue_count")
        if isinstance(extra_count, int):
            additional_issues_total += extra_count

    label_precision = (
        mean(
            float(m.get("precision", 0.0))
            for m in label_metric_rows
            if m.get("precision") is not None
        )
        if label_metric_rows
        else None
    )
    label_recall = (
        mean(
            float(m.get("recall", 0.0))
            for m in label_metric_rows
            if m.get("recall") is not None
        )
        if label_metric_rows
        else None
    )
    label_f1 = (
        mean(
            float(m.get("f1", 0.0))
            for m in label_metric_rows
            if m.get("f1") is not None
        )
        if label_metric_rows
        else None
    )
    label_presence_accuracy = (
        mean(
            float(m.get("presence_accuracy", 0.0))
            for m in label_metric_rows
            if m.get("presence_accuracy") is not None
        )
        if label_metric_rows
        else None
    )
    label_difficulty_accuracy = (
        mean(
            float(m.get("difficulty_accuracy", 0.0))
            for m in label_metric_rows
            if m.get("difficulty_accuracy") is not None
        )
        if label_metric_rows
        else None
    )
    label_family_accuracy = (
        mean(
            float(m.get("family_accuracy", 0.0))
            for m in label_metric_rows
            if m.get("family_accuracy") is not None
        )
        if label_metric_rows
        else None
    )
    judge_values = [
        r["judge_score"] for r in valid_rows if r["judge_score"] is not None
    ]
    judge_avg = mean(judge_values) if judge_values else None
    quality_avg = mean(r["quality_score"] for r in valid_rows)

    latencies = sorted(
        [
            t["latency_sec"]
            for r in valid_rows
            for t in r.get("telemetry", [])
            if t.get("latency_sec") is not None
        ]
    )
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    else:
        p50 = 0.0
        p95 = 0.0

    costs = [
        r["estimated_cost_usd"]
        for r in valid_rows
        if r["estimated_cost_usd"] is not None
    ]
    avg_cost = mean(costs) if costs else 0.0

    eff_score = efficiency_score(
        p50_latency_sec=p50,
        avg_cost_usd=avg_cost,
    )
    rank_score = aggregate_rank_score(
        quality_score=quality_avg,
        efficiency_score_value=eff_score,
        quality_weight=weights.quality_weight,
        efficiency_weight=weights.efficiency_weight,
    )
    return {
        "deterministic_score": deterministic_avg,
        "judge_score": judge_avg,
        "quality_score": quality_avg,
        "efficiency_score": eff_score,
        "rank_score": rank_score,
        "p50_latency_sec": p50,
        "p95_latency_sec": p95,
        "avg_cost_usd": avg_cost,
        "label_match_hits": label_match_hits_sum,
        "label_match_total": label_match_total_sum,
        "label_match": label_match,
        "additional_issues_count": additional_issues_total,
        "label_precision": label_precision,
        "label_recall": label_recall,
        "label_f1": label_f1,
        "label_presence_accuracy": label_presence_accuracy,
        "label_difficulty_accuracy": label_difficulty_accuracy,
        "label_family_accuracy": label_family_accuracy,
        "avg_row_elapsed_sec": avg_row_elapsed,
        "p50_row_elapsed_sec": p50_row_elapsed,
        "p95_row_elapsed_sec": p95_row_elapsed,
        "total_row_elapsed_sec": total_row_elapsed,
        "ok_cases": len(valid_rows),
        "skipped_cases": len([r for r in rows if r["status"] == "skipped"]),
        "error_cases": len([r for r in rows if r["status"] == "error"]),
    }


def run_eval(
    *,
    profile: str,
    prompt_version: str,
    dataset_path: Path | None,
    cache_path: Path,
    use_cache: bool,
    timeout_sec: int,
    no_judge: bool,
    judge_model: str,
    judge_effort: str,
    max_concurrency: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    run_started = perf_counter()
    dataset = load_dataset(dataset_path)
    base_cases = cases_for_profile(dataset, profile)

    expanded_cases: list[ExpandedCase] = []
    for case in base_cases:
        versions = resolve_prompt_versions(case.check_id, prompt_version)
        for version in versions:
            expanded_cases.append(ExpandedCase(case=case, prompt_version=version))

    candidates = build_candidate_matrix()
    total_runs = len(candidates) * len(expanded_cases)
    _emit_progress(
        progress_callback,
        "start",
        profile=profile,
        base_cases=len(base_cases),
        expanded_cases=len(expanded_cases),
        candidates=len(candidates),
        total_runs=total_runs,
        max_concurrency=max(1, int(max_concurrency)),
    )

    case_sources: dict[str, dict[str, Any]] = {}
    case_det_refs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for case_index, case in enumerate(base_cases, start=1):
        source = load_vedalang(Path(case.source))
        validate_vedalang(source)
        case_sources[case.case_id] = source
        case_det_refs[(case.case_id, case.category)] = _deterministic_reference(
            source,
            case.category,
        )
        _emit_progress(
            progress_callback,
            "source_loaded",
            case_index=case_index,
            case_total=len(base_cases),
            case_id=case.case_id,
            source=case.source,
        )

    cache = _load_cache(cache_path)
    weights = EvalWeights()
    cache_lock = Lock() if max(1, int(max_concurrency)) > 1 else None

    row_results: list[dict[str, Any]] = []
    completed_runs = 0
    candidate_index_by_id = {
        c.candidate_id: idx for idx, c in enumerate(candidates, start=1)
    }
    candidate_rows_by_id = {c.candidate_id: [] for c in candidates}
    candidate_started_at = {c.candidate_id: perf_counter() for c in candidates}
    emitted_candidate_complete: set[str] = set()
    expected_rows_per_candidate = len(expanded_cases)

    for candidate in candidates:
        _emit_progress(
            progress_callback,
            "candidate_start",
            candidate_index=candidate_index_by_id[candidate.candidate_id],
            candidate_total=len(candidates),
            candidate_id=candidate.candidate_id,
        )

    effort_order = [
        e for e in REASONING_LEVELS if any(c.reasoning_effort == e for c in candidates)
    ]
    model_order = [
        canonical_model_name(m)
        for m in MODEL_FAMILIES
        if any(c.model == canonical_model_name(m) for c in candidates)
    ]
    candidate_lookup = {(c.reasoning_effort, c.model): c for c in candidates}
    worker_count = max(1, int(max_concurrency))
    executor = (
        ThreadPoolExecutor(max_workers=worker_count)
        if worker_count > 1
        else None
    )

    try:
        for expanded_case_index, expanded_case in enumerate(expanded_cases, start=1):
            for effort_index, effort in enumerate(effort_order, start=1):
                specs: list[dict[str, Any]] = []
                for model_index, model in enumerate(model_order, start=1):
                    candidate = candidate_lookup.get((effort, model))
                    if candidate is None:
                        continue
                    case = expanded_case.case
                    specs.append(
                        {
                            "candidate": candidate,
                            "candidate_index": candidate_index_by_id[
                                candidate.candidate_id
                            ],
                            "expanded_case": expanded_case,
                            "expanded_case_index": expanded_case_index,
                            "effort_index": effort_index,
                            "model_index": model_index,
                            "case_source": case_sources[case.case_id],
                            "det_reference": case_det_refs[
                                (case.case_id, case.category)
                            ],
                        }
                    )

                if not specs:
                    continue

                group_rows: list[dict[str, Any]] = []
                if executor is None or len(specs) == 1:
                    for spec in specs:
                        row = _evaluate_row(
                            candidate=spec["candidate"],
                            candidate_index=spec["candidate_index"],
                            expanded_case=spec["expanded_case"],
                            expanded_case_index=spec["expanded_case_index"],
                            case_source=spec["case_source"],
                            det_reference=spec["det_reference"],
                            timeout_sec=timeout_sec,
                            cache=cache,
                            use_cache=use_cache,
                            cache_lock=cache_lock,
                            no_judge=no_judge,
                            judge_model=judge_model,
                            judge_effort=judge_effort,
                            weights=weights,
                        )
                        row["_effort_index"] = spec["effort_index"]
                        row["_model_order"] = spec["model_index"]
                        group_rows.append(row)
                else:
                    futures = {
                        executor.submit(
                            _evaluate_row,
                            candidate=spec["candidate"],
                            candidate_index=spec["candidate_index"],
                            expanded_case=spec["expanded_case"],
                            expanded_case_index=spec["expanded_case_index"],
                            case_source=spec["case_source"],
                            det_reference=spec["det_reference"],
                            timeout_sec=timeout_sec,
                            cache=cache,
                            use_cache=use_cache,
                            cache_lock=cache_lock,
                            no_judge=no_judge,
                            judge_model=judge_model,
                            judge_effort=judge_effort,
                            weights=weights,
                        ): spec
                        for spec in specs
                    }
                    for future in as_completed(futures):
                        spec = futures[future]
                        row = future.result()
                        row["_effort_index"] = spec["effort_index"]
                        row["_model_order"] = spec["model_index"]
                        group_rows.append(row)

                group_rows.sort(key=lambda r: int(r["_model_order"]))
                for row in group_rows:
                    row_results.append(row)
                    candidate_id = str(row["candidate_id"])
                    candidate_rows_by_id[candidate_id].append(row)

                    completed_runs += 1
                    _emit_progress(
                        progress_callback,
                        "row_complete",
                        completed_runs=completed_runs,
                        total_runs=total_runs,
                        candidate_index=row["_candidate_index"],
                        candidate_total=len(candidates),
                        candidate_id=candidate_id,
                        case_index=row["_case_index"],
                        case_total=len(expanded_cases),
                        case_id=row["case_id"],
                        status=row["status"],
                        cached=row.get("cached", False),
                        deterministic_score=row["deterministic_score"],
                        label_match=row["label_match"],
                        additional_issues_count=row["additional_issues_count"],
                        label_f1=(
                            row.get("deterministic_breakdown", {})
                            .get("label_metrics", {})
                            .get("f1")
                            if isinstance(row.get("deterministic_breakdown"), dict)
                            else None
                        ),
                        judge_score=row["judge_score"],
                        quality_score=row["quality_score"],
                        estimated_cost_usd=row["estimated_cost_usd"],
                        row_elapsed_sec=row["row_elapsed_sec"],
                    )

                    if (
                        candidate_id not in emitted_candidate_complete
                        and len(candidate_rows_by_id[candidate_id])
                        >= expected_rows_per_candidate
                    ):
                        candidate_rows = candidate_rows_by_id[candidate_id]
                        candidate_summary = _summarize_candidate_rows(
                            candidate_rows,
                            weights,
                        )
                        _emit_progress(
                            progress_callback,
                            "candidate_complete",
                            candidate_index=candidate_index_by_id[candidate_id],
                            candidate_total=len(candidates),
                            candidate_id=candidate_id,
                            ok_cases=len(
                                [r for r in candidate_rows if r["status"] == "ok"]
                            ),
                            skipped_cases=len(
                                [
                                    r
                                    for r in candidate_rows
                                    if r["status"] == "skipped"
                                ]
                            ),
                            error_cases=len(
                                [r for r in candidate_rows if r["status"] == "error"]
                            ),
                            deterministic_score=candidate_summary[
                                "deterministic_score"
                            ],
                            label_match=candidate_summary["label_match"],
                            additional_issues_count=candidate_summary[
                                "additional_issues_count"
                            ],
                            label_f1=candidate_summary["label_f1"],
                            label_presence_accuracy=candidate_summary[
                                "label_presence_accuracy"
                            ],
                            label_difficulty_accuracy=candidate_summary[
                                "label_difficulty_accuracy"
                            ],
                            label_family_accuracy=candidate_summary[
                                "label_family_accuracy"
                            ],
                            judge_score=candidate_summary["judge_score"],
                            quality_score=candidate_summary["quality_score"],
                            rank_score=candidate_summary["rank_score"],
                            avg_row_elapsed_sec=candidate_summary[
                                "avg_row_elapsed_sec"
                            ],
                            total_row_elapsed_sec=candidate_summary[
                                "total_row_elapsed_sec"
                            ],
                            candidate_elapsed_sec=(
                                perf_counter() - candidate_started_at[candidate_id]
                            ),
                        )
                        emitted_candidate_complete.add(candidate_id)
    finally:
        if executor is not None:
            executor.shutdown(wait=True)

    _save_cache(cache_path, cache)

    row_results.sort(
        key=lambda r: (
            int(r["_case_index"]),
            int(r.get("_effort_index", 0)),
            int(r.get("_model_order", 0)),
        )
    )
    for row in row_results:
        row.pop("_candidate_index", None)
        row.pop("_case_index", None)
        row.pop("_effort_index", None)
        row.pop("_model_order", None)

    leaderboard: list[dict[str, Any]] = []
    for candidate in candidates:
        rows = [r for r in row_results if r["candidate_id"] == candidate.candidate_id]
        summary = _summarize_candidate_rows(rows, weights)
        leaderboard.append(
            {
                "candidate_id": candidate.candidate_id,
                "model": candidate.model,
                "reasoning_effort": candidate.reasoning_effort,
                **summary,
            }
        )

    leaderboard.sort(key=lambda r: r["rank_score"], reverse=True)

    run_id = datetime.now(UTC).strftime("eval-%Y%m%dT%H%M%SZ")
    run = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "profile": profile,
        "prompt_version": prompt_version,
        "dataset_version": dataset.version,
        "weights": {
            "deterministic_weight": weights.deterministic_weight,
            "judge_weight": weights.judge_weight,
            "quality_weight": weights.quality_weight,
            "efficiency_weight": weights.efficiency_weight,
        },
        "judge": {
            "enabled": not no_judge,
            "model": judge_model,
            "effort": judge_effort,
        },
        "cases": [
            {
                "case_id": c.case_id,
                "check_id": c.check_id,
                "category": c.category,
                "engine": c.engine,
                "source": c.source,
                "component": c.component,
                "expected": c.expected,
            }
            for c in base_cases
        ],
        "expanded_cases": [
            {
                "case_id": c.expanded_case_id,
                "base_case_id": c.case.case_id,
                "check_id": c.case.check_id,
                "prompt_version": c.prompt_version,
            }
            for c in expanded_cases
        ],
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "model": c.model,
                "reasoning_effort": c.reasoning_effort,
            }
            for c in candidates
        ],
        "results": row_results,
        "leaderboard": leaderboard,
        "cache_path": str(cache_path),
        "timing": {
            "run_elapsed_sec": perf_counter() - run_started,
            "max_concurrency": max(1, int(max_concurrency)),
            "total_runs": total_runs,
            "completed_runs": completed_runs,
            "ok_runs": len([r for r in row_results if r["status"] == "ok"]),
            "skipped_runs": len([r for r in row_results if r["status"] == "skipped"]),
            "error_runs": len([r for r in row_results if r["status"] == "error"]),
            "total_row_elapsed_sec": sum(
                float(r.get("row_elapsed_sec", 0.0) or 0.0) for r in row_results
            ),
        },
    }

    _emit_progress(
        progress_callback,
        "complete",
        run_id=run_id,
        leaderboard_top=(
            run["leaderboard"][0]["candidate_id"] if run["leaderboard"] else None
        ),
        run_elapsed_sec=run["timing"]["run_elapsed_sec"],
    )
    return run


def render_report(run: dict[str, Any]) -> str:
    lines = []
    lines.append(f"Run ID: {run.get('run_id')}")
    lines.append(f"Created: {run.get('created_at')}")
    lines.append(f"Profile: {run.get('profile')}")
    lines.append(f"Prompt version: {run.get('prompt_version')}")
    timing = run.get("timing", {})
    if timing:
        lines.append(
            "Timing: "
            f"run_elapsed={timing.get('run_elapsed_sec', 0.0):.2f}s "
            f"ok={timing.get('ok_runs')} "
            f"skipped={timing.get('skipped_runs')} "
            f"errors={timing.get('error_runs')}"
        )
    judge = run.get("judge", {})
    lines.append(
        f"Judge: {'enabled' if judge.get('enabled') else 'disabled'} "
        f"({judge.get('model')}:{judge.get('effort')})"
    )
    lines.append("")
    lines.append("Top candidates:")
    for idx, row in enumerate(run.get("leaderboard", [])[:10], start=1):
        label_f1 = row.get("label_f1")
        label_f1_text = "n/a" if label_f1 is None else f"{label_f1:.2f}"
        lines.append(
            f"{idx:>2}. {row['candidate_id']} "
            f"rank={row['rank_score']:.2f} quality={row['quality_score']:.2f} "
            f"det={row['deterministic_score']:.2f} "
            f"label_match={row.get('label_match', 'n/a')} "
            f"extra={row.get('additional_issues_count', 0)} "
            f"label_f1={label_f1_text} "
            f"latency_p50={row['p50_latency_sec']:.2f}s "
            f"row_p50={row.get('p50_row_elapsed_sec', 0.0):.2f}s "
            f"cost_avg=${row['avg_cost_usd']:.4f}"
        )
    return "\n".join(lines)


def compare_runs(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_by_id = {r["candidate_id"]: r for r in old.get("leaderboard", [])}
    new_by_id = {r["candidate_id"]: r for r in new.get("leaderboard", [])}

    deltas: list[dict[str, Any]] = []
    for candidate_id in sorted(set(old_by_id) | set(new_by_id)):
        before = old_by_id.get(candidate_id)
        after = new_by_id.get(candidate_id)
        deltas.append(
            {
                "candidate_id": candidate_id,
                "old_rank_score": None if before is None else before.get("rank_score"),
                "new_rank_score": None if after is None else after.get("rank_score"),
                "delta_rank_score": (
                    None
                    if (before is None or after is None)
                    else after.get("rank_score", 0.0) - before.get("rank_score", 0.0)
                ),
                "old_quality_score": None
                if before is None
                else before.get("quality_score"),
                "new_quality_score": None
                if after is None
                else after.get("quality_score"),
                "delta_quality_score": (
                    None
                    if (before is None or after is None)
                    else after.get("quality_score", 0.0)
                    - before.get("quality_score", 0.0)
                ),
            }
        )

    deltas.sort(key=lambda r: (r["delta_rank_score"] or 0.0), reverse=True)

    return {
        "old_run_id": old.get("run_id"),
        "new_run_id": new.get("run_id"),
        "deltas": deltas,
    }
