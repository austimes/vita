"""LLM-based structural RES assessment used by `vedalang llm-lint`.

Provides Layer 2 of the three-layer convention framework:
  Layer 1 - Skill guidance (advisory)
  Layer 2 - Lint + LLM structural assessment (testing)
  Layer 3 - Compiler hard enforcement (guarantee)

This runs when `vedalang llm-lint --category structure` is selected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedalang.conventions import (
    commodity_namespace_enum,
    commodity_type_enum,
    format_enum_csv,
    process_stage_enum,
)
from vedalang.lint.llm_runtime import (
    ReasoningEffort,
    call_openai_json,
    canonical_model_name,
)
from vedalang.lint.prompt_registry import load_prompt_template
from vedalang.lint.res_export import export_res_graph, res_graph_to_mermaid

CHECK_ID = "llm.structure.res_assessment"
DEFAULT_MODEL = "gpt-5.2"
DEFAULT_PROMPT_VERSION = "v2"

# Path to the canonical modeling conventions document (single source of truth)
_CONVENTIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "vedalang-user"
    / "modeling-conventions.md"
)

Severity = Literal["critical", "warning", "suggestion"]
VALID_SEVERITIES: set[str] = {"critical", "warning", "suggestion"}


@dataclass
class LLMFinding:
    """A single finding from the LLM structural assessment."""

    severity: Severity
    category: str
    message: str
    location: str | None = None
    suggestion: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": f"LLM_{self.category.upper()}",
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
        }
        if self.location:
            d["location"] = self.location
        if self.suggestion:
            d["suggestion"] = self.suggestion
        if self.context:
            d["context"] = self.context
        return d


@dataclass
class AssessmentResult:
    """Result of the LLM structural assessment."""

    findings: list[LLMFinding]
    raw_response: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    telemetry: dict[str, Any] | None = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def suggestion_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "suggestion")

    @property
    def has_critical(self) -> bool:
        return self.critical_count > 0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "findings": [f.to_dict() for f in self.findings],
            "summary": {
                "critical": self.critical_count,
                "warning": self.warning_count,
                "suggestion": self.suggestion_count,
                "total": len(self.findings),
            },
        }
        if self.model:
            payload["model"] = self.model
        if self.prompt_version:
            payload["prompt_version"] = self.prompt_version
        if self.telemetry is not None:
            payload["telemetry"] = self.telemetry
        return payload


def load_conventions() -> str:
    if _CONVENTIONS_PATH.exists():
        return _CONVENTIONS_PATH.read_text(encoding="utf-8")
    return (
        "Modeling conventions document not found. "
        "Assess based on general energy system modeling best practices."
    )


def _build_system_prompt(prompt_version: str = DEFAULT_PROMPT_VERSION) -> str:
    system_template = load_prompt_template(CHECK_ID, prompt_version, "system.txt")
    canonical_enum_lines = (
        f"- **Stage** = one of: {format_enum_csv(process_stage_enum())}.\n"
        f"- **Commodity type** = one of: {format_enum_csv(commodity_type_enum())}.\n"
        "- **Commodity namespace prefix** = one of: "
        f"{format_enum_csv(commodity_namespace_enum())}."
    )
    return system_template.replace("__CANONICAL_ENUMS__", canonical_enum_lines)


def _build_user_prompt(
    conventions: str,
    graph: dict,
    mermaid: str,
    *,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> str:
    user_template = load_prompt_template(CHECK_ID, prompt_version, "user_prefix.txt")
    return (
        user_template.replace("__MODELING_CONVENTIONS__", conventions)
        .replace("__RES_GRAPH_JSON__", json.dumps(graph, indent=2))
        .replace("__RES_GRAPH_MERMAID__", mermaid)
    )


def assemble_prompt(
    source: dict,
    *,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> tuple[str, str]:
    conventions = load_conventions()
    graph = export_res_graph(source)
    mermaid = res_graph_to_mermaid(graph)
    user_prompt = _build_user_prompt(
        conventions,
        graph,
        mermaid,
        prompt_version=prompt_version,
    )
    return _build_system_prompt(prompt_version=prompt_version), user_prompt


def parse_llm_response(raw: str) -> AssessmentResult:
    text = raw.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"LLM response must be a JSON object, got {type(data).__name__}"
        )

    raw_findings = data.get("findings")
    if raw_findings is None:
        raise ValueError("LLM response missing 'findings' key")

    if not isinstance(raw_findings, list):
        raise ValueError(
            f"'findings' must be a list, got {type(raw_findings).__name__}"
        )

    findings: list[LLMFinding] = []
    for i, item in enumerate(raw_findings):
        if not isinstance(item, dict):
            raise ValueError(
                f"Finding {i} must be an object, got {type(item).__name__}"
            )

        severity = item.get("severity", "suggestion")
        if severity not in VALID_SEVERITIES:
            severity = "suggestion"

        classification = item.get("classification")
        if not isinstance(classification, dict):
            classification = {}
        context: dict[str, Any] = {}
        error_code = (
            item.get("error_code")
            or classification.get("error_code")
            or item.get("classification_code")
        )
        if isinstance(error_code, str) and error_code.strip():
            context["error_code"] = error_code.strip()
        error_family = item.get("error_family") or classification.get("error_family")
        if isinstance(error_family, str) and error_family.strip():
            context["error_family"] = error_family.strip()
        difficulty = item.get("difficulty") or classification.get("difficulty")
        if isinstance(difficulty, str) and difficulty.strip():
            context["difficulty"] = difficulty.strip()

        findings.append(
            LLMFinding(
                severity=severity,
                category=item.get("category", "other"),
                message=item.get("message", "No description provided"),
                location=item.get("location"),
                suggestion=item.get("suggestion"),
                context=context,
            )
        )

    return AssessmentResult(findings=findings, raw_response=raw)


def run_llm_assessment(
    source: dict,
    *,
    llm_callable: Any | None = None,
    model: str = DEFAULT_MODEL,
    reasoning_effort: ReasoningEffort = "medium",
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    timeout_sec: int | None = None,
) -> AssessmentResult:
    system_prompt, user_prompt = assemble_prompt(source, prompt_version=prompt_version)

    resolved_model = canonical_model_name(model)
    telemetry: dict[str, Any] | None = None

    if llm_callable is not None:
        raw = llm_callable(system_prompt, user_prompt)
    else:
        call = call_openai_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=resolved_model,
            reasoning_effort=reasoning_effort,
            timeout_sec=timeout_sec,
        )
        raw = call.output_text
        telemetry = {
            "latency_sec": call.telemetry.latency_sec,
            "input_tokens": call.telemetry.input_tokens,
            "output_tokens": call.telemetry.output_tokens,
            "reasoning_tokens": call.telemetry.reasoning_tokens,
            "reasoning_effort": call.telemetry.reasoning_effort,
        }

    result = parse_llm_response(raw)
    result.model = resolved_model
    result.prompt_version = prompt_version
    result.telemetry = telemetry
    return result
