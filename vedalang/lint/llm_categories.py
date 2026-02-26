"""LLM lint category runners (mirrors deterministic category names)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vedalang.lint.diagnostics import with_meta


@dataclass
class LLMCategoryResult:
    diagnostics: list[dict]
    runtime_error: bool = False
    supported: bool = True
    extras: dict[str, Any] = field(default_factory=dict)


def run_core(*, source: dict, **_: Any) -> LLMCategoryResult:
    del source
    return LLMCategoryResult(diagnostics=[], supported=False)


def run_identity(*, source: dict, **_: Any) -> LLMCategoryResult:
    del source
    return LLMCategoryResult(diagnostics=[], supported=False)


def run_emissions(*, source: dict, **_: Any) -> LLMCategoryResult:
    del source
    return LLMCategoryResult(diagnostics=[], supported=False)


def run_feasibility(*, source: dict, **_: Any) -> LLMCategoryResult:
    del source
    return LLMCategoryResult(diagnostics=[], supported=False)


def run_structure(*, source: dict, **_: Any) -> LLMCategoryResult:
    from vedalang.lint.llm_assessment import run_llm_assessment

    diagnostics: list[dict] = []
    try:
        result = run_llm_assessment(source)
        for finding in result.findings:
            data = finding.to_dict()
            llm_subcategory = data.get("category")
            if llm_subcategory:
                context = data.get("context") or {}
                context["llm_subcategory"] = llm_subcategory
                data["context"] = context
            data["category"] = "structure"
            diagnostics.append(
                with_meta(
                    data,
                    category="structure",
                    engine="llm",
                    check_id="llm.structure.res_assessment",
                )
            )
    except Exception as e:
        diagnostics.append(
            with_meta(
                {
                    "code": "LLM_STRUCTURE_ERROR",
                    "severity": "error",
                    "message": f"LLM structure assessment failed: {e}",
                },
                category="structure",
                engine="llm",
                check_id="llm.structure.res_assessment",
            )
        )
        return LLMCategoryResult(diagnostics=diagnostics, runtime_error=True)

    return LLMCategoryResult(diagnostics=diagnostics)


def run_units(
    *,
    source: dict,
    file_path: Path,
    component: list[str] | None,
    run_all: bool,
    force: bool,
    models: list[str] | None,
    store_path: Path | None,
    **_: Any,
) -> LLMCategoryResult:
    from vedalang.lint.llm_unit_check import (
        default_store_path,
        load_store,
        run_component_unit_check,
        save_store,
        select_components,
        update_store_with_result,
    )

    diagnostics: list[dict] = []
    result_extras: dict[str, Any] = {
        "store_path": None,
        "unit_results": [],
        "unit_skipped_components": [],
    }
    runtime_error = False

    resolved_store = store_path or default_store_path(file_path)
    result_extras["store_path"] = resolved_store
    store = load_store(resolved_store)

    try:
        to_check, skipped_components = select_components(
            source=source,
            store=store,
            selected=component,
            run_all=run_all,
            force=force,
        )
        result_extras["unit_skipped_components"] = skipped_components
    except Exception as e:
        diagnostics.append(
            with_meta(
                {
                    "code": "LLM_UNIT_SELECTION_ERROR",
                    "severity": "error",
                    "message": str(e),
                },
                category="units",
                engine="llm",
                check_id="llm.units.component_quorum",
            )
        )
        return LLMCategoryResult(
            diagnostics=diagnostics,
            runtime_error=True,
            extras=result_extras,
        )

    for component_id in to_check:
        try:
            result = run_component_unit_check(
                source=source,
                component=component_id,
                models=models,
            )
            update_store_with_result(store, result)
            result_extras["unit_results"].append(
                {
                    "component": result.component,
                    "status": result.status,
                    "fingerprint": result.fingerprint,
                    "quorum": result.quorum,
                    "models": [v.model for v in result.votes],
                }
            )
            for vote in result.votes:
                if not vote.findings and vote.status != "pass":
                    diagnostics.append(
                        with_meta(
                            {
                                "code": "LLM_UNIT_CHECK",
                                "severity": "warning",
                                "location": f"{result.component} [{vote.model}]",
                                "message": (
                                    "LLM returned non-pass status but provided "
                                    "no findings."
                                ),
                            },
                            category="units",
                            engine="llm",
                            check_id="llm.units.component_quorum",
                        )
                    )
                    continue
                for finding in vote.findings:
                    location = f"{result.component} [{vote.model}]"
                    field = finding.get("field")
                    if field:
                        location = f"{location} :: {field}"
                    diagnostics.append(
                        with_meta(
                            {
                                "code": "LLM_UNIT_CHECK",
                                "severity": finding.get("severity", "warning"),
                                "location": location,
                                "message": str(
                                    finding.get("message", "No message provided.")
                                ),
                                "suggestion": finding.get("suggestion"),
                                "context": {
                                    "expected_process_units": finding.get(
                                        "expected_process_units"
                                    ),
                                    "expected_commodity_units": finding.get(
                                        "expected_commodity_units"
                                    ),
                                    "observed_units": finding.get("observed_units"),
                                    "model_expectation": finding.get(
                                        "model_expectation"
                                    ),
                                },
                            },
                            category="units",
                            engine="llm",
                            check_id="llm.units.component_quorum",
                        )
                    )
        except Exception as e:
            runtime_error = True
            diagnostics.append(
                with_meta(
                    {
                        "code": "LLM_UNIT_CHECK_ERROR",
                        "severity": "error",
                        "location": component_id,
                        "message": str(e),
                    },
                    category="units",
                    engine="llm",
                    check_id="llm.units.component_quorum",
                )
            )

    save_store(resolved_store, store)
    return LLMCategoryResult(
        diagnostics=diagnostics,
        runtime_error=runtime_error,
        extras=result_extras,
    )


CATEGORY_RUNNERS = {
    "core": run_core,
    "identity": run_identity,
    "structure": run_structure,
    "units": run_units,
    "emissions": run_emissions,
    "feasibility": run_feasibility,
}
