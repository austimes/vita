"""Shared OpenAI runtime helpers for LLM lint engines and evals."""

from __future__ import annotations

import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh"]


@dataclass(frozen=True)
class LLMRuntimeConfig:
    """Runtime configuration shared across LLM lint category runners."""

    model: str | None = None
    models: list[str] | None = None
    reasoning_effort: ReasoningEffort = "medium"
    prompt_version: str = "v2"
    timeout_sec: int | None = None


@dataclass
class LLMCallTelemetry:
    model: str
    reasoning_effort: str
    latency_sec: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    error: str | None = None


@dataclass
class LLMCallResult:
    output_text: str
    model: str
    telemetry: LLMCallTelemetry


def canonical_model_name(model: str) -> str:
    """Normalize common typos/aliases for model names."""
    normalized = (model or "").strip()
    if normalized == "git-5-mini":
        return "gpt-5-mini"
    return normalized


def _maybe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_usage(response: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    if usage is None:
        return None, None, None

    input_tokens = _maybe_int(getattr(usage, "input_tokens", None))
    if input_tokens is None and isinstance(usage, dict):
        input_tokens = _maybe_int(usage.get("input_tokens"))

    output_tokens = _maybe_int(getattr(usage, "output_tokens", None))
    if output_tokens is None and isinstance(usage, dict):
        output_tokens = _maybe_int(usage.get("output_tokens"))

    reasoning_tokens = None
    details = getattr(usage, "output_tokens_details", None)
    if details is not None:
        reasoning_tokens = _maybe_int(getattr(details, "reasoning_tokens", None))
    if reasoning_tokens is None and isinstance(usage, dict):
        details_dict = usage.get("output_tokens_details")
        if isinstance(details_dict, dict):
            reasoning_tokens = _maybe_int(details_dict.get("reasoning_tokens"))

    if reasoning_tokens is None:
        reasoning_tokens = _maybe_int(getattr(usage, "reasoning_tokens", None))
    if reasoning_tokens is None and isinstance(usage, dict):
        reasoning_tokens = _maybe_int(usage.get("reasoning_tokens"))

    return input_tokens, output_tokens, reasoning_tokens


def call_openai_json(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    reasoning_effort: ReasoningEffort = "medium",
    timeout_sec: int | None = None,
) -> LLMCallResult:
    """Call OpenAI Responses API and request JSON object output."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. "
            "Set it in your environment or .env file to use LLM lint."
        )

    try:
        import openai
    except ImportError as exc:
        raise RuntimeError(
            "openai package not installed. Install with: uv add openai"
        ) from exc

    resolved_model = canonical_model_name(model)
    client = openai.OpenAI(api_key=api_key)

    call_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "instructions": system_prompt,
        "input": user_prompt,
        "text": {"format": {"type": "json_object"}},
        "reasoning": {"effort": reasoning_effort},
    }
    if timeout_sec is not None:
        call_kwargs["timeout"] = timeout_sec

    start = perf_counter()
    try:
        response = client.responses.create(**call_kwargs)
    except Exception as exc:
        latency = perf_counter() - start
        telemetry = LLMCallTelemetry(
            model=resolved_model,
            reasoning_effort=reasoning_effort,
            latency_sec=latency,
            error=str(exc),
        )
        raise RuntimeError(
            "OpenAI call failed for "
            f"model={resolved_model}, effort={reasoning_effort}: {exc}"
        ) from exc

    latency = perf_counter() - start
    input_tokens, output_tokens, reasoning_tokens = _extract_usage(response)

    telemetry = LLMCallTelemetry(
        model=resolved_model,
        reasoning_effort=reasoning_effort,
        latency_sec=latency,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )

    return LLMCallResult(
        output_text=getattr(response, "output_text", None) or "{}",
        model=resolved_model,
        telemetry=telemetry,
    )
