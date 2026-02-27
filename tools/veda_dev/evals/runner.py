"""Eval runner for lint/llm-lint model/effort benchmarking."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from vedalang.compiler.compiler import load_vedalang, validate_vedalang
from vedalang.lint.code_categories import collect_structural_by_category
from vedalang.lint.diagnostics import with_meta
from vedalang.lint.llm_assessment import CHECK_ID as STRUCTURE_CHECK_ID
from vedalang.lint.llm_assessment import run_llm_assessment
from vedalang.lint.llm_unit_check import CHECK_ID as UNITS_CHECK_ID
from vedalang.lint.llm_unit_check import run_component_unit_check
from vedalang.lint.prompt_registry import resolve_prompt_versions

from .config import EvalWeights, build_candidate_matrix
from .dataset import EvalCase, cases_for_profile, load_dataset
from .judge import run_judge
from .scoring import (
    aggregate_quality_score,
    aggregate_rank_score,
    deterministic_score,
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
    grouped = collect_structural_by_category(source)
    return list(grouped.get(category, []))


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


def _summarize_candidate_rows(
    rows: list[dict[str, Any]], weights: EvalWeights
) -> dict[str, Any]:
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
            "ok_cases": 0,
            "skipped_cases": len([r for r in rows if r["status"] == "skipped"]),
            "error_cases": len([r for r in rows if r["status"] == "error"]),
        }

    deterministic_avg = mean(r["deterministic_score"] for r in valid_rows)
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
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    base_cases = cases_for_profile(dataset, profile)

    expanded_cases: list[ExpandedCase] = []
    for case in base_cases:
        versions = resolve_prompt_versions(case.check_id, prompt_version)
        for version in versions:
            expanded_cases.append(ExpandedCase(case=case, prompt_version=version))

    case_sources: dict[str, dict[str, Any]] = {}
    case_det_refs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for case in base_cases:
        source = load_vedalang(Path(case.source))
        validate_vedalang(source)
        case_sources[case.case_id] = source
        case_det_refs[(case.case_id, case.category)] = _deterministic_reference(
            source,
            case.category,
        )

    candidates = build_candidate_matrix()
    cache = _load_cache(cache_path)
    weights = EvalWeights()

    row_results: list[dict[str, Any]] = []

    for candidate in candidates:
        for expanded_case in expanded_cases:
            case = expanded_case.case
            evaluated = _evaluate_one(
                expanded_case=expanded_case,
                source=case_sources[case.case_id],
                model=candidate.model,
                effort=candidate.reasoning_effort,
                timeout_sec=timeout_sec,
                cache=cache,
                use_cache=use_cache,
            )

            det_reference = case_det_refs[(case.case_id, case.category)]

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

            if evaluated["status"] == "ok":
                det_score = deterministic_score(
                    diagnostics=evaluated["diagnostics"],
                    expected_category=case.category,
                    expected_engine=case.engine,
                    expected_check_id=case.check_id,
                    required_code_substrings=required,
                    forbidden_code_substrings=forbidden,
                    deterministic_diagnostics=det_reference,
                )

                telemetry = evaluated.get("telemetry") or []
                if telemetry:
                    in_tokens = sum((t.get("input_tokens") or 0) for t in telemetry)
                    out_tokens = sum((t.get("output_tokens") or 0) for t in telemetry)
                    est_cost = estimate_cost_usd(candidate.model, in_tokens, out_tokens)

                judge_result = None
                if not no_judge:
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
                    judge_score = judge_result.score_0_to_100

                quality_score = aggregate_quality_score(
                    deterministic=det_score,
                    judge=judge_score,
                    deterministic_weight=weights.deterministic_weight,
                    judge_weight=weights.judge_weight,
                )

                evaluated["judge"] = (
                    None
                    if (no_judge or judge_result is None)
                    else {
                        "score_0_to_100": judge_result.score_0_to_100,
                        "actionability_score": judge_result.actionability_score,
                        "hallucination_flag": judge_result.hallucination_flag,
                        "major_errors": judge_result.major_errors,
                        "rationale_short": judge_result.rationale_short,
                        "error": judge_result.error,
                        "telemetry": judge_result.telemetry,
                    }
                )

            row_results.append(
                {
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
                    "judge_score": judge_score,
                    "quality_score": quality_score,
                    "known_issues": case.expected.get("known_issues", []),
                    "judge": evaluated.get("judge"),
                }
            )

    _save_cache(cache_path, cache)

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
    return {
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
    }


def render_report(run: dict[str, Any]) -> str:
    lines = []
    lines.append(f"Run ID: {run.get('run_id')}")
    lines.append(f"Created: {run.get('created_at')}")
    lines.append(f"Profile: {run.get('profile')}")
    lines.append(f"Prompt version: {run.get('prompt_version')}")
    judge = run.get("judge", {})
    lines.append(
        f"Judge: {'enabled' if judge.get('enabled') else 'disabled'} "
        f"({judge.get('model')}:{judge.get('effort')})"
    )
    lines.append("")
    lines.append("Top candidates:")
    for idx, row in enumerate(run.get("leaderboard", [])[:10], start=1):
        lines.append(
            f"{idx:>2}. {row['candidate_id']} "
            f"rank={row['rank_score']:.2f} quality={row['quality_score']:.2f} "
            f"det={row['deterministic_score']:.2f} "
            f"latency_p50={row['p50_latency_sec']:.2f}s "
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
