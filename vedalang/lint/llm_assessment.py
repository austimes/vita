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

# Path to the canonical modeling conventions document (single source of truth)
_CONVENTIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "vedalang-user"
    / "modeling-conventions.md"
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
    model: str | None = None

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

## VedaLang Key Concepts

Understanding these precisely is critical to avoid false positives:

- **Role** = a service/transformation provided (e.g. "provide-space-heat"). \
Defined in `process_roles` with stage, inputs, and outputs.
- **Variant** = a specific technology pathway that fulfils a role \
(e.g. "gas-boiler", "heat-pump"). Defined in `process_variants` with \
`role:` reference, efficiency, lifetime, costs.
- **Stage** = one of: supply, conversion, storage, end_use, sink.
- **Commodity type** = one of: fuel, energy, service, material, emission, money, other.

### Critical distinctions (avoid these mistakes):

1. **Multiple variants under one role is GOOD, not fragmented.** \
The whole point of the role/variant pattern is that one service role \
(e.g. "provide-ag-output") can have many technology variants \
(e.g. "traditional-baseline", "traditional-with-feed-additives", \
"traditional-with-improved-manure"). \
This is correct design. "Over-fragmented roles" means having too many \
ROLES that serve the same purpose — NOT too many variants under one role.

4. **Variant names should indicate complete replacement pathways**, not \
bolt-on modifiers. When variants represent improved versions of a \
baseline practice, use bundle naming like "traditional-with-feed-additives" \
(not just "feed-additives") to make clear each variant is a complete \
end-to-end replacement for the baseline, not an add-on. Flag variant \
names that sound like standalone measures or bolt-on modifiers when they \
share a role with a baseline variant.

2. **Zero-input processes are only valid at stage: supply.** \
A process at end_use or conversion that has no inputs in its role \
definition AND no variant-level inputs is suspicious (fake supply). \
However, VedaLang supports **variant-level inputs**: when different \
variants under a role consume different fuels (e.g. gas_heater→natural_gas, \
heat_pump→electricity), the role correctly has empty `required_inputs` \
while each variant declares its own inputs. Check the role's \
`has_variant_level_inputs` field and `variant_inputs` list in the JSON — \
if `has_variant_level_inputs` is true, the role is NOT a zero-input device. \
Also check the edges section for commodity→role input edges. \
Do NOT flag roles that have variant-level inputs as zero-input devices.

3. **Commodity type mismatches** must explain: what type the commodity \
currently has, what type would be expected in this context (and why), \
and what diagnostic confusion might result. For example, if xl2times \
expects a "fuel" type for process inputs but finds "material", explain \
that xl2times may misclassify the flow in its diagnostics.

## You will receive:
1. Modeling conventions that define best practices
2. A normalized RES graph (JSON) describing commodities, roles, variants, \
and edges
3. A Mermaid diagram of the same graph (for visual reference — role-level \
only; variant-specific flows are in the JSON)

## Interpreting edge scope (CRITICAL — read carefully)

Edges in the JSON have a `scope` field:
- `"scope": "role"` — declared in `process_roles.required_inputs/outputs`. \
Applies to ALL variants under this role.
- `"scope": "variant"` — declared only by specific variant(s). The \
`source_variants` list shows WHICH variant(s) produce this edge.

**Variant-level emissions**: If an emission edge has `"scope": "variant"` \
and `"source_variants": ["gas_heater"]`, it means ONLY `gas_heater` emits \
that commodity — NOT the role as a whole, and NOT other variants like \
`heat_pump`. Do NOT generalise variant-scoped edges to the role.

Similarly, each variant node now includes its own `inputs`, `outputs`, \
and `emission_factors` so you can verify exactly which variants have \
which topology.

## What to assess:
- Violations of service-level role abstraction (fuel-pathway roles)
- Suspicious zero-input end-use devices (processes at non-supply stage \
with no inputs declared in their role)
- Over-fragmented ROLES (multiple roles serving the same service that \
should be merged — NOT multiple variants under one role)
- Inconsistent stage usage
- Commodity type mismatches (with specific xl2times/VEDA expectations)
- **Ambiguous variant naming**: variants that sound like bolt-on modifiers \
(e.g. "feed-additives") when they should use bundle naming to indicate \
complete replacement pathways (e.g. "traditional-with-feed-additives"). \
Flag variants whose names suggest they are add-on measures rather than \
complete end-to-end replacements for a baseline variant.
- Any other structural anti-patterns

## Response format

Respond with ONLY a JSON object (no markdown fencing) matching this schema:

{
  "findings": [
    {
      "severity": "critical" | "warning" | "suggestion",
      "category": "string (e.g. fuel_pathway_roles, zero_input_device, \
stage_mismatch, commodity_type_mismatch, over_fragmented_roles, \
ambiguous_variant_naming, other)",
      "message": "Detailed description of the issue: what is wrong, why \
it is a problem, and what the model expects vs what it found.",
      "location": "string identifying where in the model (role/variant id)",
      "suggestion": "Concrete guidance on how to fix the issue, including \
a VedaLang YAML snippet showing the corrected structure."
    }
  ]
}

IMPORTANT:
- Every finding MUST include a non-empty "suggestion" with a concrete fix.
- "message" must explain the root cause and downstream consequences.
- Do NOT flag multiple variants under one role as "over-fragmented".
- Do NOT flag a process as "zero-input" if its role declares inputs OR \
if `has_variant_level_inputs` is true (variants provide the inputs).
- If no genuine issues are found, return: {"findings": []}
- Prefer fewer, high-quality findings over many low-quality ones.
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


_MODEL = "gpt-5.2"


def _call_openai(system_prompt: str, user_prompt: str) -> tuple[str, str]:
    """Call OpenAI Responses API for structural assessment.

    Uses OPENAI_API_KEY from environment. Raises RuntimeError if unavailable.

    Returns:
        Tuple of (response_text, model_name).
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

    response = client.responses.create(
        model=_MODEL,
        instructions=system_prompt,
        input=user_prompt,
        text={"format": {"type": "json_object"}},
        reasoning={"effort": "medium"},
    )

    return response.output_text or "{}", _MODEL


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

    model: str | None = None
    if llm_callable is not None:
        raw = llm_callable(system_prompt, user_prompt)
    else:
        raw, model = _call_openai(system_prompt, user_prompt)

    result = parse_llm_response(raw)
    result.model = model
    return result
