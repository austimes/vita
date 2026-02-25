"""Optional LLM-based unit/coefficient certification workflow.

This module is advisory only. Deterministic compiler/lint checks remain the
primary enforcement layer; this adds a secondary review signal with model
quorum and fingerprint-based invalidation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vedalang.lint.llm_assessment import _call_openai

DEFAULT_MODELS = ("gpt-5.2", "gpt-5")


def _schema_unit_reference() -> dict[str, list[str]]:
    """Load canonical unit enums from schema for prompt grounding."""
    schema_path = (
        Path(__file__).resolve().parents[1] / "schema" / "vedalang.schema.json"
    )
    try:
        with open(schema_path) as f:
            schema = json.load(f)
    except Exception:
        return {}

    defs = schema.get("$defs", {})

    def read_enum(key: str) -> list[str]:
        value = defs.get(key, {})
        enum = value.get("enum", [])
        if not isinstance(enum, list):
            return []
        return [str(v) for v in enum]

    return {
        "unit_symbol": read_enum("unit_symbol"),
        "energy_unit": read_enum("energy_unit"),
        "power_unit": read_enum("power_unit"),
        "mass_unit": read_enum("mass_unit"),
        "currency_unit": read_enum("currency_unit"),
        "service_unit": read_enum("service_unit"),
    }


@dataclass
class VoteResult:
    model: str
    status: str
    findings: list[dict[str, Any]]
    raw_response: str | None = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.get("severity") == "critical")

    @property
    def is_pass(self) -> bool:
        return self.status == "pass" and self.critical_count == 0


@dataclass
class ComponentUnitCheckResult:
    component: str
    fingerprint: str
    votes: list[VoteResult]

    @property
    def pass_count(self) -> int:
        return sum(1 for v in self.votes if v.is_pass)

    @property
    def quorum(self) -> str:
        return f"{self.pass_count}/{len(self.votes)}"

    @property
    def status(self) -> str:
        return "certified" if self.pass_count == len(self.votes) else "needs_review"


def default_store_path(source_path: Path) -> Path:
    """Return sidecar path for persisted certification metadata."""
    return Path(f"{source_path}.unit_checks.json")


def load_store(path: Path) -> dict[str, Any]:
    """Load certification store or return an empty store."""
    if not path.exists():
        return {"version": 1, "components": {}}
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"version": 1, "components": {}}
    data.setdefault("version", 1)
    data.setdefault("components", {})
    return data


def save_store(path: Path, store: dict[str, Any]) -> None:
    """Persist certification metadata store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(store, f, indent=2, sort_keys=True)
        f.write("\n")


def list_components(source: dict) -> list[str]:
    """List component IDs for certification (P4 variants or legacy processes)."""
    variants = source.get("process_variants") or []
    if variants:
        return [v["id"] for v in variants if "id" in v]
    model = source.get("model", {})
    return [p["name"] for p in model.get("processes", []) if "name" in p]


def _component_payload(source: dict, component: str) -> dict[str, Any]:
    """Build canonical payload used for fingerprinting and LLM review."""
    model = source.get("model", {})
    commodities = {
        (c.get("id") or c.get("name")): c for c in model.get("commodities", [])
    }
    payload: dict[str, Any] = {
        "model": model.get("name"),
        "unit_policy": model.get("unit_policy", {}),
    }

    for variant in source.get("process_variants", []):
        if variant.get("id") != component:
            continue
        comm_refs = [
            f["commodity"] for f in (variant.get("inputs") or []) if "commodity" in f
        ]
        comm_refs.extend(
            f["commodity"] for f in (variant.get("outputs") or []) if "commodity" in f
        )
        payload["component"] = variant
        payload["commodities"] = {
            cid: commodities[cid]
            for cid in sorted(set(comm_refs))
            if cid in commodities
        }
        return payload

    for process in model.get("processes", []):
        if process.get("name") != component:
            continue
        comm_refs = [
            f["commodity"] for f in (process.get("inputs") or []) if "commodity" in f
        ]
        comm_refs.extend(
            f["commodity"] for f in (process.get("outputs") or []) if "commodity" in f
        )
        payload["component"] = process
        payload["commodities"] = {
            cid: commodities[cid]
            for cid in sorted(set(comm_refs))
            if cid in commodities
        }
        return payload

    raise ValueError(f"Unknown component '{component}'")


def component_fingerprint(source: dict, component: str) -> str:
    """Compute stable fingerprint for invalidation checks."""
    payload = _component_payload(source, component)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_certified_current(
    store: dict[str, Any], component: str, fingerprint: str
) -> bool:
    """True when certification exists and matches current fingerprint."""
    rec = store.get("components", {}).get(component)
    if not isinstance(rec, dict):
        return False
    return rec.get("status") == "certified" and rec.get("fingerprint") == fingerprint


def select_components(
    *,
    source: dict,
    store: dict[str, Any],
    selected: list[str] | None,
    run_all: bool,
    force: bool,
) -> tuple[list[str], list[str]]:
    """Select components to check and list skipped components."""
    all_components = list_components(source)
    if selected:
        unknown = sorted(set(selected) - set(all_components))
        if unknown:
            raise ValueError(f"Unknown component(s): {', '.join(unknown)}")
        targets = list(dict.fromkeys(selected))
    elif run_all:
        targets = list(all_components)
    else:
        targets = list(all_components)

    to_check: list[str] = []
    skipped: list[str] = []
    for component in targets:
        fp = component_fingerprint(source, component)
        if not force and not selected and is_certified_current(store, component, fp):
            skipped.append(component)
            continue
        to_check.append(component)
    return to_check, skipped


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_unit_check_response(raw: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse model response into (status, findings)."""
    cleaned = _strip_markdown_fence(raw)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("LLM unit check response must be a JSON object")
    status = data.get("status", "needs_review")
    if status not in {"pass", "fail", "needs_review"}:
        status = "needs_review"
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    normalized = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "warning")).lower()
        if sev not in {"critical", "warning", "suggestion"}:
            sev = "warning"
        normalized.append(
            {
                "severity": sev,
                "message": str(item.get("message", "")),
                "field": item.get("field"),
                "suggestion": item.get("suggestion"),
                "expected_process_units": item.get("expected_process_units"),
                "expected_commodity_units": item.get("expected_commodity_units"),
                "observed_units": item.get("observed_units"),
                "model_expectation": item.get("model_expectation"),
            }
        )
    return status, normalized


def assemble_unit_prompt(source: dict, component: str) -> tuple[str, str]:
    """Assemble system and user prompts for one component."""
    payload = _component_payload(source, component)
    model = source.get("model", {})
    unit_policy = model.get("unit_policy", {})
    unit_reference = _schema_unit_reference()
    system_prompt = (
        "You are a strict unit/coefficient reviewer for energy system DSL models. "
        "Return JSON only with keys: status, findings. "
        "status must be one of pass|fail|needs_review. "
        "Each finding must include severity (critical|warning|suggestion) and message. "
        "For findings that are not suggestion-only, include concrete remediation in "
        "'suggestion', plus unit expectations where possible: "
        "'expected_process_units' (activity_unit/capacity_unit), "
        "'expected_commodity_units' (commodity->unit), "
        "'observed_units', and 'model_expectation'. "
        "Be explicit and actionable; do not be vague."
    )
    user_prompt = (
        "Assess unit/coefficient consistency for this component. "
        "Focus on unit conversions, efficiency-vs-coefficient plausibility, "
        "basis mismatches (HHV/LHV), and likely inversion/factor mistakes. "
        "When raising a concern, propose a fix and expected units based on "
        "process/commodity names, role intent, and model context.\n\n"
        "Allowed unit enums from schema:\n"
        f"{json.dumps(unit_reference, indent=2)}\n\n"
        "Model unit policy:\n"
        f"{json.dumps(unit_policy, indent=2)}\n\n"
        f"Component ID: {component}\n"
        "Payload JSON:\n"
        f"{json.dumps(payload, indent=2)}"
    )
    return system_prompt, user_prompt


def run_component_unit_check(
    *,
    source: dict,
    component: str,
    models: list[str] | None = None,
    llm_callable: Any | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ComponentUnitCheckResult:
    """Run quorum LLM checks for a component."""
    system_prompt, user_prompt = assemble_unit_prompt(source, component)
    chosen_models = models or list(DEFAULT_MODELS)
    votes: list[VoteResult] = []
    for index, model in enumerate(chosen_models, start=1):
        if progress_callback:
            progress_callback(
                {
                    "event": "model_start",
                    "component": component,
                    "model": model,
                    "index": index,
                    "total_models": len(chosen_models),
                }
            )
        if llm_callable is not None:
            raw = llm_callable(system_prompt, user_prompt, model)
        else:
            raw, _ = _call_openai(system_prompt, user_prompt, model=model)
        status, findings = parse_unit_check_response(raw)
        if progress_callback:
            progress_callback(
                {
                    "event": "model_done",
                    "component": component,
                    "model": model,
                    "index": index,
                    "total_models": len(chosen_models),
                    "status": status,
                    "findings_count": len(findings),
                }
            )
        votes.append(
            VoteResult(
                model=model,
                status=status,
                findings=findings,
                raw_response=raw,
            )
        )
    return ComponentUnitCheckResult(
        component=component,
        fingerprint=component_fingerprint(source, component),
        votes=votes,
    )


def update_store_with_result(
    store: dict[str, Any], result: ComponentUnitCheckResult
) -> None:
    """Update certification store with one component result."""
    components = store.setdefault("components", {})
    components[result.component] = {
        "status": result.status,
        "fingerprint": result.fingerprint,
        "checked_at": datetime.now(UTC).isoformat(),
        "models": [vote.model for vote in result.votes],
        "quorum": result.quorum,
        "votes": [
            {
                "model": vote.model,
                "status": vote.status,
                "critical_count": vote.critical_count,
                "findings": vote.findings,
            }
            for vote in result.votes
        ],
    }
