"""Tests for llm category runner runtime wiring."""

from vedalang.lint import llm_categories
from vedalang.lint.llm_assessment import AssessmentResult
from vedalang.lint.llm_runtime import LLMRuntimeConfig


def test_run_structure_uses_first_model_and_runtime_flags(monkeypatch):
    captured = {}

    def fake_run_llm_assessment(
        source,
        *,
        llm_callable=None,
        model,
        reasoning_effort,
        prompt_version,
        timeout_sec,
    ):
        del source, llm_callable
        captured["model"] = model
        captured["reasoning_effort"] = reasoning_effort
        captured["prompt_version"] = prompt_version
        captured["timeout_sec"] = timeout_sec
        return AssessmentResult(findings=[], model=model, prompt_version=prompt_version)

    monkeypatch.setattr(
        "vedalang.lint.llm_assessment.run_llm_assessment",
        fake_run_llm_assessment,
    )

    result = llm_categories.run_structure(
        source={"model": {"name": "X", "regions": [], "commodities": []}},
        runtime_config=LLMRuntimeConfig(
            model=None,
            models=["gpt-5-mini", "gpt-5-nano"],
            reasoning_effort="low",
            prompt_version="v1",
            timeout_sec=17,
        ),
    )

    assert result.runtime_error is False
    assert result.supported is True
    assert captured["model"] == "gpt-5-mini"
    assert captured["reasoning_effort"] == "low"
    assert captured["prompt_version"] == "v1"
    assert captured["timeout_sec"] == 17
