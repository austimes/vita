"""LLM-as-judge scoring for eval runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from vedalang.lint.llm_runtime import call_openai_json


@dataclass
class JudgeResult:
    score_0_to_100: float | None
    actionability_score: float | None
    hallucination_flag: bool
    major_errors: list[str]
    rationale_short: str
    raw_response: str
    telemetry: dict[str, Any] | None
    error: str | None = None


def _judge_system_prompt() -> str:
    return (
        "You are a strict evaluator for lint output quality. "
        "Return JSON only. Do not include markdown."
    )


def _judge_user_prompt(sample: dict[str, Any]) -> str:
    return (
        "Evaluate this candidate lint output against expected signals. "
        "Score quality from 0-100. Penalize hallucinations. "
        "Return JSON object with keys: "
        "score_0_to_100, actionability_score, hallucination_flag, "
        "major_errors, rationale_short.\n\n"
        f"Sample:\n{json.dumps(sample, indent=2)}"
    )


def parse_judge_response(raw: str) -> JudgeResult:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Judge response must be a JSON object")

    def f(value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    major_errors = data.get("major_errors")
    if not isinstance(major_errors, list):
        major_errors = []

    return JudgeResult(
        score_0_to_100=f(data.get("score_0_to_100")),
        actionability_score=f(data.get("actionability_score")),
        hallucination_flag=bool(data.get("hallucination_flag", False)),
        major_errors=[str(x) for x in major_errors],
        rationale_short=str(data.get("rationale_short", "")),
        raw_response=raw,
        telemetry=None,
    )


def run_judge(
    *,
    sample: dict[str, Any],
    judge_model: str,
    judge_effort: str,
    timeout_sec: int | None,
) -> JudgeResult:
    try:
        call = call_openai_json(
            system_prompt=_judge_system_prompt(),
            user_prompt=_judge_user_prompt(sample),
            model=judge_model,
            reasoning_effort=judge_effort,
            timeout_sec=timeout_sec,
        )
        parsed = parse_judge_response(call.output_text)
        parsed.telemetry = {
            "latency_sec": call.telemetry.latency_sec,
            "input_tokens": call.telemetry.input_tokens,
            "output_tokens": call.telemetry.output_tokens,
            "reasoning_tokens": call.telemetry.reasoning_tokens,
            "reasoning_effort": call.telemetry.reasoning_effort,
            "model": call.model,
        }
        return parsed
    except Exception as e:
        return JudgeResult(
            score_0_to_100=None,
            actionability_score=None,
            hallucination_flag=False,
            major_errors=[],
            rationale_short="",
            raw_response="",
            telemetry=None,
            error=str(e),
        )
