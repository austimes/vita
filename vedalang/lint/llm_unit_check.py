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

from vedalang.lint.llm_runtime import (
    ReasoningEffort,
    call_openai_json,
    canonical_model_name,
)
from vedalang.lint.prompt_registry import load_prompt_template

CHECK_ID = "llm.units.component_quorum"
DEFAULT_PROMPT_VERSION = "v2"
DEFAULT_MODELS = ("gpt-5.2", "gpt-5-mini")


def _schema_unit_reference() -> dict[str, list[str]]:
    """Load canonical unit enums from schema for prompt grounding."""
    schema_path = (
        Path(__file__).resolve().parents[1] / "schema" / "vedalang.schema.json"
    )
    try:
        with open(schema_path, encoding="utf-8") as f:
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

    def read_union_units(key: str) -> list[str]:
        value = defs.get(key, {})
        units: list[str] = []
        seen: set[str] = set()
        for option in value.get("oneOf", []):
            if not isinstance(option, dict):
                continue
            ref = option.get("$ref")
            if not isinstance(ref, str):
                continue
            if not ref.startswith("#/$defs/"):
                continue
            ref_key = ref.split("/")[-1]
            for unit in read_enum(ref_key):
                if unit in seen:
                    continue
                seen.add(unit)
                units.append(unit)
        return units

    monetary_token = defs.get("monetary_unit_token", {})
    cost_rate_literal = defs.get("cost_rate_literal", {})

    return {
        "unit_symbol": read_enum("unit_symbol"),
        "energy_unit": read_enum("energy_unit"),
        "power_unit": read_enum("power_unit"),
        "mass_unit": read_enum("mass_unit"),
        "currency_unit": read_enum("currency_unit"),
        "currency_code": read_enum("currency_code"),
        "service_unit": read_enum("service_unit"),
        "process_activity_unit": read_union_units("process_activity_unit"),
        "process_capacity_unit": read_union_units("process_capacity_unit"),
        "monetary_unit_token_pattern": [str(monetary_token.get("pattern", ""))],
        "cost_rate_literal_pattern": [str(cost_rate_literal.get("pattern", ""))],
    }


@dataclass
class VoteResult:
    model: str
    status: str
    findings: list[dict[str, Any]]
    raw_response: str | None = None
    telemetry: dict[str, Any] | None = None

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
    prompt_version: str = DEFAULT_PROMPT_VERSION

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
        return {"version": 2, "components": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"version": 2, "components": {}}
    data.setdefault("version", 2)
    data.setdefault("components", {})
    return data


def save_store(path: Path, store: dict[str, Any]) -> None:
    """Persist certification metadata store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
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
    roles = {r.get("id"): r for r in source.get("process_roles", []) if "id" in r}
    payload: dict[str, Any] = {
        "model": model.get("name"),
        "unit_policy": model.get("unit_policy", {}),
        "monetary_policy": model.get("monetary", {}),
        "cost_basis": {
            "investment_cost": "currency per capacity_unit",
            "fixed_om_cost": "currency per capacity_unit per year",
            "variable_om_cost": "currency per activity_unit",
        },
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
        role = roles.get(variant.get("role"))
        if role is not None:
            payload["role"] = role
            payload["process_units"] = {
                "activity_unit": role.get("activity_unit"),
                "capacity_unit": role.get("capacity_unit"),
            }
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
    store: dict[str, Any],
    component: str,
    fingerprint: str,
    *,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> bool:
    """True when certification exists and matches fingerprint + prompt version."""
    rec = store.get("components", {}).get(component)
    if not isinstance(rec, dict):
        return False
    rec_prompt_version = str(rec.get("prompt_version") or DEFAULT_PROMPT_VERSION)
    return (
        rec.get("status") == "certified"
        and rec.get("fingerprint") == fingerprint
        and rec_prompt_version == prompt_version
    )


def select_components(
    *,
    source: dict,
    store: dict[str, Any],
    selected: list[str] | None,
    run_all: bool,
    force: bool,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
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
        if (
            not force
            and not selected
            and is_certified_current(
                store,
                component,
                fp,
                prompt_version=prompt_version,
            )
        ):
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
        classification = item.get("classification")
        if not isinstance(classification, dict):
            classification = {}
        error_code = (
            item.get("error_code")
            or classification.get("error_code")
            or item.get("classification_code")
        )
        error_family = item.get("error_family") or classification.get("error_family")
        difficulty = item.get("difficulty") or classification.get("difficulty")
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
                "error_code": (
                    str(error_code).strip()
                    if isinstance(error_code, str) and str(error_code).strip()
                    else None
                ),
                "error_family": (
                    str(error_family).strip()
                    if isinstance(error_family, str) and str(error_family).strip()
                    else None
                ),
                "difficulty": (
                    str(difficulty).strip()
                    if isinstance(difficulty, str) and str(difficulty).strip()
                    else None
                ),
            }
        )
    return status, normalized


def assemble_unit_prompt(
    source: dict,
    component: str,
    *,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> tuple[str, str]:
    """Assemble system and user prompts for one component."""
    payload = _component_payload(source, component)
    model = source.get("model", {})
    unit_policy = model.get("unit_policy", {})
    monetary_policy = model.get("monetary", {})
    unit_reference = _schema_unit_reference()

    system_prompt = load_prompt_template(CHECK_ID, prompt_version, "system.txt")
    user_template = load_prompt_template(CHECK_ID, prompt_version, "user_prefix.txt")
    user_prompt = (
        user_template.replace(
            "__UNIT_REFERENCE__", json.dumps(unit_reference, indent=2)
        )
        .replace("__UNIT_POLICY__", json.dumps(unit_policy, indent=2))
        .replace("__MONETARY_POLICY__", json.dumps(monetary_policy, indent=2))
        .replace("__COMPONENT_ID__", component)
        .replace("__PAYLOAD_JSON__", json.dumps(payload, indent=2))
    )
    return system_prompt, user_prompt


def run_component_unit_check(
    *,
    source: dict,
    component: str,
    models: list[str] | None = None,
    llm_callable: Any | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    reasoning_effort: ReasoningEffort = "medium",
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    timeout_sec: int | None = None,
) -> ComponentUnitCheckResult:
    """Run quorum LLM checks for a component."""
    system_prompt, user_prompt = assemble_unit_prompt(
        source,
        component,
        prompt_version=prompt_version,
    )
    chosen_models = [canonical_model_name(m) for m in (models or list(DEFAULT_MODELS))]
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
        telemetry: dict[str, Any] | None = None
        if llm_callable is not None:
            raw = llm_callable(system_prompt, user_prompt, model)
        else:
            call = call_openai_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
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
                telemetry=telemetry,
            )
        )
    return ComponentUnitCheckResult(
        component=component,
        fingerprint=component_fingerprint(source, component),
        votes=votes,
        prompt_version=prompt_version,
    )


def update_store_with_result(
    store: dict[str, Any],
    result: ComponentUnitCheckResult,
    *,
    prompt_version: str | None = None,
) -> None:
    """Update certification store with one component result."""
    components = store.setdefault("components", {})
    effective_prompt_version = prompt_version or result.prompt_version
    components[result.component] = {
        "status": result.status,
        "fingerprint": result.fingerprint,
        "prompt_version": effective_prompt_version,
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
