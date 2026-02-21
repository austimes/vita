"""Optional LLM-based structural RES assessment for the lint pipeline.

Provides Layer 2 of the three-layer convention framework:
  Layer 1 — Skill guidance (advisory)
  Layer 2 — Lint + LLM structural assessment (testing)
  Layer 3 — Compiler hard enforcement (guarantee)

When enabled, this module:
1. Assembles a prompt from the modeling conventions doc + RES graph artifacts
2. Sends it to an LLM for structural assessment
3. Parses the structured JSON response into LintFindings

This is off by default — requires explicit opt-in via --llm-assess flag.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedalang.lint.res_export import export_res_graph, res_graph_to_mermaid

# Path to the modeling conventions skill document
_CONVENTIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "skills"
    / "vedalang-modeling-conventions"
    / "SKILL.md"
)

# Severity levels for LLM assessment findings
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
        """Convert to JSON-serializable dict."""
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
        """Convert to JSON-serializable dict."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "summary": {
                "critical": self.critical_count,
                "warning": self.warning_count,
                "suggestion": self.suggestion_count,
                "total": len(self.findings),
            },
        }


def load_conventions() -> str:
    """Load the modeling conventions document.

    Returns:
        Contents of the SKILL.md conventions document, or a fallback message.
    """
    if _CONVENTIONS_PATH.exists():
        return _CONVENTIONS_PATH.read_text()
    return (
        "Modeling conventions document not found. "
        "Assess based on general energy system modeling best practices."
    )


_SYSTEM_PROMPT = """\
You are a VedaLang structural assessment engine. Your task is to review the \
Reference Energy System (RES) graph of a VedaLang model and identify \
architectural inconsistencies.

You will receive:
1. Modeling conventions that define best practices
2. A normalized RES graph (JSON) describing commodities, roles, variants, \
and edges
3. A Mermaid diagram of the same graph (for visual reference)

Assess the RES for:
- Violations of service-level role abstraction (fuel-pathway roles)
- Suspicious zero-input end-use devices (fake supply)
- Over-fragmented roles that should be merged
- Inconsistent stage usage
- Commodity type mismatches
- Any other structural anti-patterns

Respond with ONLY a JSON object (no markdown fencing) matching this schema:

{
  "findings": [
    {
      "severity": "critical" | "warning" | "suggestion",
      "category": "string (e.g. fuel_pathway_roles, zero_input_device, \
stage_mismatch, commodity_type_mismatch, over_fragmented_roles, other)",
      "message": "string describing the issue",
      "location": "string identifying where in the model (optional)",
      "suggestion": "string with fix guidance (optional)"
    }
  ]
}

If no issues are found, return: {"findings": []}
"""


def assemble_prompt(source: dict) -> tuple[str, str]:
    """Assemble the system and user prompts for LLM assessment.

    Args:
        source: Parsed VedaLang source dict.

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    conventions = load_conventions()
    graph = export_res_graph(source)
    mermaid = res_graph_to_mermaid(graph)

    user_prompt = (
        "## Modeling Conventions\n\n"
        f"{conventions}\n\n"
        "## RES Graph (JSON)\n\n"
        f"```json\n{json.dumps(graph, indent=2)}\n```\n\n"
        "## RES Graph (Mermaid)\n\n"
        f"```mermaid\n{mermaid}\n```\n\n"
        "Assess this RES for structural issues."
    )

    return _SYSTEM_PROMPT, user_prompt


def parse_llm_response(raw: str) -> AssessmentResult:
    """Parse a raw LLM response into an AssessmentResult.

    Handles both clean JSON and markdown-fenced JSON responses.

    Args:
        raw: Raw text response from the LLM.

    Returns:
        Parsed AssessmentResult.

    Raises:
        ValueError: If the response cannot be parsed.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line (```)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response is not valid JSON: {e}") from e

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

        findings.append(
            LLMFinding(
                severity=severity,
                category=item.get("category", "other"),
                message=item.get("message", "No description provided"),
                location=item.get("location"),
                suggestion=item.get("suggestion"),
            )
        )

    return AssessmentResult(findings=findings, raw_response=raw)


def _call_openai(system_prompt: str, user_prompt: str) -> str:
    """Call OpenAI API for structural assessment.

    Uses OPENAI_API_KEY from environment. Raises RuntimeError if unavailable.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. "
            "Set it in your environment or .env file to use LLM assessment."
        )

    try:
        import openai
    except ImportError:
        raise RuntimeError(
            "openai package not installed. "
            "Install with: uv add openai"
        )

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.environ.get("VEDALANG_LLM_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or "{}"


def run_llm_assessment(
    source: dict,
    *,
    llm_callable: Any | None = None,
) -> AssessmentResult:
    """Run LLM-based structural assessment on a VedaLang source.

    Args:
        source: Parsed VedaLang source dict (from load_vedalang).
        llm_callable: Optional callable(system_prompt, user_prompt) -> str.
            If not provided, uses OpenAI API via OPENAI_API_KEY.

    Returns:
        AssessmentResult with findings.
    """
    system_prompt, user_prompt = assemble_prompt(source)

    if llm_callable is not None:
        raw = llm_callable(system_prompt, user_prompt)
    else:
        raw = _call_openai(system_prompt, user_prompt)

    return parse_llm_response(raw)
