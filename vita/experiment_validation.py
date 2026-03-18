"""Validation gates for experiment brief and interpretation artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from vita.experiment_manifest import ExperimentManifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLACEHOLDERS = {
    "",
    "n/a",
    "na",
    "none",
    "unknown",
    "tbd",
    "todo",
    "-",
    "...",
    "same",
    "same as above",
}


def _substantive(text: str | None, min_chars: int = 24) -> bool:
    """Return True when *text* is non-trivial narrative content."""
    if text is None:
        return False
    norm = " ".join(text.strip().lower().split())
    return len(norm) >= min_chars and norm not in _PLACEHOLDERS


def _format_timestamp(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    schema_version: str = "vita-experiment-validation/v1"
    artifact_kind: str = ""
    artifact_file: str = ""
    checked_at: str = ""
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "artifact_kind": self.artifact_kind,
            "artifact_file": self.artifact_file,
            "checked_at": self.checked_at,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "coverage": dict(self.coverage),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")


# ---------------------------------------------------------------------------
# Brief validation
# ---------------------------------------------------------------------------


def validate_brief(
    brief: dict,
    manifest: ExperimentManifest,
) -> ValidationResult:
    """Validate a planning brief against its experiment manifest."""
    result = ValidationResult(
        artifact_kind="brief",
        checked_at=_format_timestamp(datetime.now(UTC)),
    )

    # 1. Schema version
    if brief.get("schema_version") != "vita-experiment-brief/v1":
        result.errors.append(
            f"schema_version must be 'vita-experiment-brief/v1', "
            f"got {brief.get('schema_version')!r}"
        )

    # 2. Experiment ID
    if brief.get("experiment_id") != manifest.id:
        result.errors.append(
            f"experiment_id {brief.get('experiment_id')!r} does not match "
            f"manifest id {manifest.id!r}"
        )

    # 3. Variant coverage
    expected_variant_ids = {v.id for v in manifest.variants}
    documented_variant_ids = {
        v["variant_id"] for v in brief.get("variants", [])
    }
    missing_variants = expected_variant_ids - documented_variant_ids
    extra_variants = documented_variant_ids - expected_variant_ids

    if missing_variants:
        result.errors.append(
            f"Missing variant(s) from manifest: {sorted(missing_variants)}"
        )
    if extra_variants:
        result.warnings.append(
            f"Extra variant(s) not in manifest: {sorted(extra_variants)}"
        )

    # 4. Comparison coverage
    expected_comp_ids = {c.id for c in manifest.comparisons}
    documented_comp_ids = {
        cp["comparison_id"] for cp in brief.get("comparison_plan", [])
    }
    missing_comps = expected_comp_ids - documented_comp_ids
    extra_comps = documented_comp_ids - expected_comp_ids

    if missing_comps:
        result.errors.append(
            f"Missing comparison(s) from manifest: {sorted(missing_comps)}"
        )
    if extra_comps:
        result.warnings.append(
            f"Extra comparison(s) not in manifest: {sorted(extra_comps)}"
        )

    # 5. Cross-reference resolution
    for cp in brief.get("comparison_plan", []):
        cid = cp.get("comparison_id", "")
        if cid not in expected_comp_ids and cid not in extra_comps:
            result.errors.append(
                f"comparison_plan references unknown comparison_id {cid!r}"
            )

    # 6. Duplicate IDs
    _check_duplicate_ids(
        brief, "mechanism_chains", "variants[].hypothesis.mechanism_chains", result
    )
    _check_duplicate_ids(
        brief,
        "confirmation_criteria",
        "variants[].hypothesis.confirmation_criteria",
        result,
    )
    _check_duplicate_ids(
        brief,
        "refutation_criteria",
        "variants[].hypothesis.refutation_criteria",
        result,
    )

    design_step_ids: list[str] = []
    for step in brief.get("design_reasoning_steps", []):
        design_step_ids.append(step.get("id", ""))
    dupes = _find_duplicates(design_step_ids)
    if dupes:
        result.errors.append(
            f"Duplicate design_reasoning_steps IDs: {sorted(dupes)}"
        )

    # 7. Substance checks
    _check_substance(
        brief, "research.scope",
        _get_nested(brief, "research", "scope"), result,
    )
    _check_substance(
        brief, "design_summary.approach",
        _get_nested(brief, "design_summary", "approach"), result,
    )

    for i, v in enumerate(brief.get("variants", [])):
        vid = v.get("variant_id", f"[{i}]")
        _check_substance(
            brief, f"variants[{vid}].change_summary",
            v.get("change_summary"), result,
        )
        _check_substance(
            brief, f"variants[{vid}].why_this_variant",
            v.get("why_this_variant"), result,
        )

        hyp = v.get("hypothesis", {})
        _check_substance(
            brief, f"variants[{vid}].hypothesis.statement",
            hyp.get("statement"), result,
        )

        for mc in hyp.get("mechanism_chains", []):
            mcid = mc.get("id", "?")
            pfx = f"variants[{vid}].mechanism_chains[{mcid}]"
            _check_substance(
                brief, f"{pfx}.cause",
                mc.get("cause"), result,
            )
            _check_substance(
                brief, f"{pfx}.effect",
                mc.get("effect"), result,
            )
            _check_substance(
                brief, f"{pfx}.because",
                mc.get("because"), result,
            )

    for cp in brief.get("comparison_plan", []):
        cpid = cp.get("comparison_id", "?")
        _check_substance(
            brief, f"comparison_plan[{cpid}].purpose",
            cp.get("purpose"), result,
        )

    for step in brief.get("design_reasoning_steps", []):
        sid = step.get("id", "?")
        _check_substance(
            brief, f"design_reasoning_steps[{sid}].statement",
            step.get("statement"), result,
        )

    # 8. Non-empty mechanism_chains and confirmation_criteria
    for i, v in enumerate(brief.get("variants", [])):
        vid = v.get("variant_id", f"[{i}]")
        hyp = v.get("hypothesis", {})
        if not hyp.get("mechanism_chains"):
            result.errors.append(
                f"variants[{vid}].hypothesis.mechanism_chains must not be empty"
            )
        if not hyp.get("confirmation_criteria"):
            result.errors.append(
                f"variants[{vid}].hypothesis.confirmation_criteria must not be empty"
            )

    # Coverage summary
    result.coverage = {
        "expected_variant_ids": sorted(expected_variant_ids),
        "documented_variant_ids": sorted(documented_variant_ids),
        "missing_variant_ids": sorted(missing_variants),
        "expected_comparison_ids": sorted(expected_comp_ids),
        "documented_comparison_ids": sorted(documented_comp_ids),
        "missing_comparison_ids": sorted(missing_comps),
    }

    result.valid = len(result.errors) == 0
    return result


# ---------------------------------------------------------------------------
# Interpretation validation
# ---------------------------------------------------------------------------


def validate_interpretation(
    interpretation: dict,
    manifest: ExperimentManifest,
    summary: dict,
) -> ValidationResult:
    """Validate an interpretation artifact against manifest and summary."""
    result = ValidationResult(
        artifact_kind="interpretation",
        checked_at=_format_timestamp(datetime.now(UTC)),
    )

    # 1. Schema version
    if interpretation.get("schema_version") != "vita-experiment-interpretation/v1":
        result.errors.append(
            f"schema_version must be 'vita-experiment-interpretation/v1', "
            f"got {interpretation.get('schema_version')!r}"
        )

    # 2. Experiment ID
    if interpretation.get("experiment_id") != manifest.id:
        result.errors.append(
            f"experiment_id {interpretation.get('experiment_id')!r} does not "
            f"match manifest id {manifest.id!r}"
        )

    # 3. Comparison coverage
    expected_comp_ids = {c.id for c in manifest.comparisons}
    documented_comp_ids = {
        ci["comparison_id"]
        for ci in interpretation.get("comparison_interpretations", [])
    }
    missing_comps = expected_comp_ids - documented_comp_ids
    if missing_comps:
        result.errors.append(
            f"Missing comparison interpretation(s): {sorted(missing_comps)}"
        )

    # 4. Question coverage
    expected_question_ids: set[str] = {"Q"}
    for ext in manifest.extensions:
        expected_question_ids.add(ext.id)
    for analysis in manifest.analyses:
        expected_question_ids.add(analysis.id)

    documented_question_ids = {
        qa["question_id"]
        for qa in interpretation.get("question_answers", [])
    }
    missing_questions = expected_question_ids - documented_question_ids
    if missing_questions:
        result.errors.append(
            f"Missing question answer(s): {sorted(missing_questions)}"
        )

    # 5. Unique evidence IDs
    evidence_ids: list[str] = [
        e["id"] for e in interpretation.get("evidence_index", [])
    ]
    evidence_id_set = set(evidence_ids)
    dupes = _find_duplicates(evidence_ids)
    if dupes:
        result.errors.append(f"Duplicate evidence_index IDs: {sorted(dupes)}")

    # 6. Evidence refs resolution
    # Collect all evidence_refs across executive_summary, question_answers,
    # comparison_interpretations
    exec_summary = interpretation.get("executive_summary", {})
    for ref in exec_summary.get("evidence_refs", []):
        if ref not in evidence_id_set:
            result.errors.append(
                f"executive_summary.evidence_refs references unknown evidence {ref!r}"
            )

    for qa in interpretation.get("question_answers", []):
        qid = qa.get("question_id", "?")
        for ref in qa.get("evidence_refs", []):
            if ref not in evidence_id_set:
                result.errors.append(
                    f"question_answers[{qid}].evidence_refs references "
                    f"unknown evidence {ref!r}"
                )

    for ci in interpretation.get("comparison_interpretations", []):
        cid = ci.get("comparison_id", "?")
        for ref in ci.get("key_evidence_refs", []):
            if ref not in evidence_id_set:
                result.errors.append(
                    f"comparison_interpretations[{cid}].key_evidence_refs "
                    f"references unknown evidence {ref!r}"
                )
        for step in ci.get("reasoning_steps", []):
            sid = step.get("id", "?")
            for ref in step.get("evidence_refs", []):
                if ref not in evidence_id_set:
                    result.errors.append(
                        f"reasoning_steps[{sid}].evidence_refs references "
                        f"unknown evidence {ref!r}"
                    )

    # 7. Supporting step IDs resolution
    all_step_ids = _collect_all_step_ids(interpretation)

    for ref in exec_summary.get("supporting_step_ids", []):
        if ref not in all_step_ids:
            result.errors.append(
                f"executive_summary.supporting_step_ids references "
                f"unknown step {ref!r}"
            )

    for qa in interpretation.get("question_answers", []):
        qid = qa.get("question_id", "?")
        for ref in qa.get("supporting_step_ids", []):
            if ref not in all_step_ids:
                result.errors.append(
                    f"question_answers[{qid}].supporting_step_ids "
                    f"references unknown step {ref!r}"
                )

    # 8. depends_on within each comparison
    for ci in interpretation.get("comparison_interpretations", []):
        cid = ci.get("comparison_id", "?")
        local_step_ids = {s["id"] for s in ci.get("reasoning_steps", [])}
        for step in ci.get("reasoning_steps", []):
            sid = step.get("id", "?")
            for dep in step.get("depends_on", []):
                if dep not in local_step_ids:
                    result.errors.append(
                        f"comparison_interpretations[{cid}].reasoning_steps"
                        f"[{sid}].depends_on references unknown step {dep!r}"
                    )

    # 9. Observation and conclusion requirements
    for ci in interpretation.get("comparison_interpretations", []):
        cid = ci.get("comparison_id", "?")
        steps = ci.get("reasoning_steps", [])
        kinds = [s.get("kind") for s in steps]

        if "observation" not in kinds:
            result.errors.append(
                f"comparison_interpretations[{cid}]: "
                f"must have at least one observation step"
            )
        if "conclusion" not in kinds:
            result.errors.append(
                f"comparison_interpretations[{cid}]: "
                f"must have at least one conclusion step"
            )

    # 10. Conclusion reachable from observation via depends_on
    for ci in interpretation.get("comparison_interpretations", []):
        cid = ci.get("comparison_id", "?")
        steps = ci.get("reasoning_steps", [])
        _check_conclusion_reachability(cid, steps, result)

    # 11. Substance checks
    _check_substance(
        interpretation, "executive_summary.short_answer",
        exec_summary.get("short_answer"), result, min_chars=32,
    )
    _check_substance(
        interpretation, "executive_summary.answer",
        exec_summary.get("answer"), result, min_chars=32,
    )

    for qa in interpretation.get("question_answers", []):
        qid = qa.get("question_id", "?")
        _check_substance(
            interpretation, f"question_answers[{qid}].short_answer",
            qa.get("short_answer"), result, min_chars=32,
        )
        _check_substance(
            interpretation, f"question_answers[{qid}].answer",
            qa.get("answer"), result, min_chars=32,
        )

    for ci in interpretation.get("comparison_interpretations", []):
        cid = ci.get("comparison_id", "?")
        _check_substance(
            interpretation, f"comparison_interpretations[{cid}].takeaway",
            ci.get("takeaway"), result, min_chars=32,
        )
        ha = ci.get("hypothesis_assessment", {})
        _check_substance(
            interpretation,
            f"comparison_interpretations[{cid}].hypothesis_assessment.rationale",
            ha.get("rationale"), result, min_chars=32,
        )
        _check_substance(
            interpretation,
            f"comparison_interpretations[{cid}].primary_mechanism",
            ci.get("primary_mechanism"), result, min_chars=32,
        )
        for step in ci.get("reasoning_steps", []):
            sid = step.get("id", "?")
            _check_substance(
                interpretation,
                f"reasoning_steps[{sid}].statement",
                step.get("statement"), result, min_chars=32,
            )

    # Coverage summary
    result.coverage = {
        "expected_comparison_ids": sorted(expected_comp_ids),
        "documented_comparison_ids": sorted(documented_comp_ids),
        "missing_comparison_ids": sorted(missing_comps),
        "expected_question_ids": sorted(expected_question_ids),
        "documented_question_ids": sorted(documented_question_ids),
        "missing_question_ids": sorted(missing_questions),
    }

    result.valid = len(result.errors) == 0
    return result


# ---------------------------------------------------------------------------
# Markdown renderers
# ---------------------------------------------------------------------------


def render_brief_md(brief: dict) -> str:
    """Render brief.json as a readable Markdown document."""
    lines: list[str] = []

    lines.append(f"# Experiment Brief: {brief.get('experiment_id', '?')}")
    lines.append("")

    # Research Question
    research = brief.get("research", {})
    lines.append("## Research Question")
    lines.append("")
    lines.append(research.get("question", ""))
    lines.append("")
    if research.get("scope"):
        lines.append(f"**Scope:** {research['scope']}")
        lines.append("")

    # Design Approach
    design = brief.get("design_summary", {})
    lines.append("## Design Approach")
    lines.append("")
    lines.append(design.get("approach", ""))
    lines.append("")

    # Variants
    variants = brief.get("variants", [])
    if variants:
        lines.append("## Variants")
        lines.append("")
        for v in variants:
            vid = v.get("variant_id", "?")
            lines.append(f"### {vid}")
            lines.append("")
            lines.append(f"**Change:** {v.get('change_summary', '')}")
            lines.append("")
            lines.append(f"**Why:** {v.get('why_this_variant', '')}")
            lines.append("")

            hyp = v.get("hypothesis", {})
            lines.append(f"**Hypothesis:** {hyp.get('statement', '')}")
            lines.append("")
            lines.append(
                f"**Expected direction:** {hyp.get('expected_direction', '')}"
            )
            lines.append("")

            mcs = hyp.get("mechanism_chains", [])
            if mcs:
                lines.append("**Mechanism chains:**")
                lines.append("")
                for mc in mcs:
                    lines.append(
                        f"- **{mc.get('id', '?')}:** {mc.get('cause', '')} "
                        f"→ {mc.get('effect', '')} "
                        f"(because: {mc.get('because', '')})"
                    )
                lines.append("")

            ccs = hyp.get("confirmation_criteria", [])
            if ccs:
                lines.append("**Confirmation criteria:**")
                lines.append("")
                for cc in ccs:
                    cc_id = cc.get('id', '?')
                    cc_desc = cc.get('description', '')
                    lines.append(f"- **{cc_id}:** {cc_desc}")
                lines.append("")

            rcs = hyp.get("refutation_criteria", [])
            if rcs:
                lines.append("**Refutation criteria:**")
                lines.append("")
                for rc in rcs:
                    rc_id = rc.get('id', '?')
                    rc_desc = rc.get('description', '')
                    lines.append(f"- **{rc_id}:** {rc_desc}")
                lines.append("")

    # Comparison Plan
    comp_plan = brief.get("comparison_plan", [])
    if comp_plan:
        lines.append("## Comparison Plan")
        lines.append("")
        for cp in comp_plan:
            cpid = cp.get("comparison_id", "?")
            lines.append(f"### {cpid}")
            lines.append("")
            lines.append(f"**Purpose:** {cp.get('purpose', '')}")
            lines.append("")
            metrics = cp.get("metrics_of_interest", [])
            if metrics:
                lines.append("**Metrics of interest:**")
                lines.append("")
                for m in metrics:
                    lines.append(
                        f"- {m.get('metric', '?')} "
                        f"({m.get('priority', '?')}): "
                        f"{m.get('why_it_matters', '')}"
                    )
                lines.append("")

    # Design Reasoning
    steps = brief.get("design_reasoning_steps", [])
    if steps:
        lines.append("## Design Reasoning")
        lines.append("")
        for i, step in enumerate(steps, 1):
            sid = step.get("id", f"P{i}")
            kind = step.get("kind", "")
            lines.append(f"{i}. **[{sid}] ({kind}):** {step.get('statement', '')}")
        lines.append("")

    return "\n".join(lines)


def render_interpretation_md(interpretation: dict) -> str:
    """Render interpretation.json as a readable Markdown document."""
    lines: list[str] = []

    lines.append(
        f"# Experiment Interpretation: "
        f"{interpretation.get('experiment_id', '?')}"
    )
    lines.append("")

    # Executive Summary
    exec_sum = interpretation.get("executive_summary", {})
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Short answer:** {exec_sum.get('short_answer', '')}")
    lines.append("")
    lines.append(f"**Confidence:** {exec_sum.get('confidence', '')}")
    lines.append("")
    lines.append(exec_sum.get("answer", ""))
    lines.append("")

    # Comparison Interpretations
    comp_interps = interpretation.get("comparison_interpretations", [])
    if comp_interps:
        lines.append("## Comparison Interpretations")
        lines.append("")
        for ci in comp_interps:
            cid = ci.get("comparison_id", "?")
            lines.append(f"### {cid}")
            lines.append("")
            lines.append(f"**Takeaway:** {ci.get('takeaway', '')}")
            lines.append("")

            ha = ci.get("hypothesis_assessment", {})
            lines.append(
                f"**Hypothesis assessment:** {ha.get('status', '')} — "
                f"{ha.get('rationale', '')}"
            )
            lines.append("")

            steps = ci.get("reasoning_steps", [])
            if steps:
                lines.append("**Reasoning chain:**")
                lines.append("")
                for i, step in enumerate(steps, 1):
                    sid = step.get("id", f"R{i}")
                    kind = step.get("kind", "")
                    lines.append(
                        f"{i}. **[{sid}] ({kind}):** "
                        f"{step.get('statement', '')}"
                    )
                lines.append("")

            lines.append(
                f"**Primary mechanism:** {ci.get('primary_mechanism', '')}"
            )
            lines.append("")
            lines.append(f"**Confidence:** {ci.get('confidence', '')}")
            lines.append("")

            surprises = ci.get("surprises", [])
            if surprises:
                lines.append("**Surprises:**")
                lines.append("")
                for s in surprises:
                    lines.append(f"- {s.get('description', '')}")
                lines.append("")

    # Question Answers
    qa_list = interpretation.get("question_answers", [])
    if qa_list:
        lines.append("## Question Answers")
        lines.append("")
        for qa in qa_list:
            qid = qa.get("question_id", "?")
            lines.append(f"### {qid}: {qa.get('question', '')}")
            lines.append("")
            lines.append(f"**Short answer:** {qa.get('short_answer', '')}")
            lines.append("")
            lines.append(qa.get("answer", ""))
            lines.append("")
            lines.append(f"**Confidence:** {qa.get('confidence', '')}")
            lines.append("")

    # Cross-Comparison Synthesis
    synthesis = interpretation.get("cross_comparison_synthesis", {})
    if synthesis:
        lines.append("## Cross-Comparison Synthesis")
        lines.append("")
        if synthesis.get("overall_pattern"):
            lines.append(
                f"**Overall pattern:** {synthesis['overall_pattern']}"
            )
            lines.append("")
        oqs = synthesis.get("open_questions", [])
        if oqs:
            lines.append("**Open questions:**")
            lines.append("")
            for oq in oqs:
                lines.append(f"- {oq}")
            lines.append("")
        limits = synthesis.get("limits", [])
        if limits:
            lines.append("**Limits:**")
            lines.append("")
            for lim in limits:
                lines.append(f"- {lim}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_nested(d: dict, *keys: str) -> str | None:
    """Safely traverse nested dicts."""
    current: object = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


def _check_substance(
    _root: dict,
    field_path: str,
    value: str | None,
    result: ValidationResult,
    *,
    min_chars: int = 24,
) -> None:
    """Add an error if *value* is not substantive."""
    if not _substantive(value, min_chars=min_chars):
        result.errors.append(
            f"Field '{field_path}' is not substantive "
            f"(requires ≥{min_chars} chars, non-placeholder)"
        )


def _check_duplicate_ids(
    brief: dict,
    list_key: str,
    context: str,
    result: ValidationResult,
) -> None:
    """Check for duplicate IDs across all variants' hypothesis sub-lists."""
    ids: list[str] = []
    for v in brief.get("variants", []):
        hyp = v.get("hypothesis", {})
        for item in hyp.get(list_key, []):
            ids.append(item.get("id", ""))
    dupes = _find_duplicates(ids)
    if dupes:
        result.errors.append(f"Duplicate {context} IDs: {sorted(dupes)}")


def _find_duplicates(items: list[str]) -> set[str]:
    """Return the set of items that appear more than once."""
    seen: set[str] = set()
    dupes: set[str] = set()
    for item in items:
        if item in seen:
            dupes.add(item)
        seen.add(item)
    return dupes


def _collect_all_step_ids(interpretation: dict) -> set[str]:
    """Collect all reasoning step IDs across all comparison interpretations."""
    ids: set[str] = set()
    for ci in interpretation.get("comparison_interpretations", []):
        for step in ci.get("reasoning_steps", []):
            ids.add(step.get("id", ""))
    return ids


def _check_conclusion_reachability(
    comparison_id: str,
    steps: list[dict],
    result: ValidationResult,
) -> None:
    """Check that every conclusion step is reachable from an observation."""
    if not steps:
        return

    observation_ids = {
        s["id"] for s in steps if s.get("kind") == "observation"
    }
    conclusion_ids = {
        s["id"] for s in steps if s.get("kind") == "conclusion"
    }

    if not observation_ids or not conclusion_ids:
        return

    # Build reverse adjacency: for each step, what can it reach?
    # We do a forward reachability from observations.
    # Build adjacency: step -> set of steps that depend on it
    children: dict[str, set[str]] = {s["id"]: set() for s in steps if "id" in s}
    for s in steps:
        sid = s.get("id")
        if sid is None:
            continue
        for dep in s.get("depends_on", []):
            if dep in children:
                children[dep].add(sid)

    # BFS from all observations
    reachable: set[str] = set()
    frontier = list(observation_ids)
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        for child in children.get(current, set()):
            if child not in reachable:
                frontier.append(child)

    unreachable_conclusions = conclusion_ids - reachable
    for cid in sorted(unreachable_conclusions):
        result.errors.append(
            f"comparison_interpretations[{comparison_id}]: "
            f"conclusion step {cid!r} is not reachable from any observation"
        )
