"""Eval configuration for lint/llm-lint model benchmarking."""

from __future__ import annotations

from dataclasses import dataclass

from vedalang.lint.llm_runtime import canonical_model_name

MODEL_FAMILIES = ["gpt-5-nano", "gpt-5-mini", "gpt-5.2"]
REASONING_LEVELS = ["none", "low", "medium", "high", "xhigh"]
MODEL_REASONING_SUPPORT = {
    "gpt-5.2": set(REASONING_LEVELS),
    "gpt-5-mini": {"low", "medium", "high", "xhigh"},
    "gpt-5-nano": {"low", "medium", "high", "xhigh"},
}

# Rough estimates used only for relative leaderboard dimensions.
MODEL_PRICING_PER_1M = {
    "gpt-5.2": {"input": 5.0, "output": 15.0},
    "gpt-5-mini": {"input": 1.0, "output": 3.0},
    "gpt-5-nano": {"input": 0.2, "output": 0.8},
}

JUDGE_MODEL = "gpt-5.2"
JUDGE_EFFORT = "xhigh"


@dataclass(frozen=True)
class CandidateSpec:
    model: str
    reasoning_effort: str

    @property
    def candidate_id(self) -> str:
        return f"{self.model}:{self.reasoning_effort}"


@dataclass(frozen=True)
class EvalWeights:
    deterministic_weight: float = 0.7
    judge_weight: float = 0.3
    quality_weight: float = 0.8
    efficiency_weight: float = 0.2


def build_candidate_matrix() -> list[CandidateSpec]:
    candidates: list[CandidateSpec] = []
    for family in MODEL_FAMILIES:
        for effort in REASONING_LEVELS:
            canonical_model = canonical_model_name(family)
            if not model_supports_reasoning_effort(canonical_model, effort):
                continue
            candidates.append(
                CandidateSpec(
                    model=canonical_model,
                    reasoning_effort=effort,
                )
            )
    return candidates


def model_supports_reasoning_effort(model: str, reasoning_effort: str) -> bool:
    canonical_model = canonical_model_name(model)
    supported = MODEL_REASONING_SUPPORT.get(canonical_model, set(REASONING_LEVELS))
    return reasoning_effort in supported
