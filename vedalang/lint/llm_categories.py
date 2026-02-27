"""LLM lint category runners (mirrors deterministic category names)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vedalang.lint.diagnostics import with_meta
from vedalang.lint.llm_runtime import LLMRuntimeConfig, canonical_model_name
from vedalang.lint.prompt_registry import resolve_prompt_versions


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


def run_structure(
    *,
    source: dict,
    runtime_config: LLMRuntimeConfig,
    **_: Any,
) -> LLMCategoryResult:
    from vedalang.lint.llm_assessment import CHECK_ID, DEFAULT_MODEL, run_llm_assessment

    diagnostics: list[dict] = []
    llm_runs: list[dict[str, Any]] = []

    model = runtime_config.model
    if not model and runtime_config.models:
        model = runtime_config.models[0]
    model = canonical_model_name(model or DEFAULT_MODEL)

    try:
        versions = resolve_prompt_versions(CHECK_ID, runtime_config.prompt_version)
    except Exception as e:
        diagnostics.append(
            with_meta(
                {
                    "code": "LLM_STRUCTURE_ERROR",
                    "severity": "error",
                    "message": f"Failed to resolve prompt version: {e}",
                },
                category="structure",
                engine="llm",
                check_id=CHECK_ID,
            )
        )
        return LLMCategoryResult(diagnostics=diagnostics, runtime_error=True)

    for version in versions:
        try:
            structure_kwargs: dict[str, Any] = {
                "model": model,
                "reasoning_effort": runtime_config.reasoning_effort,
                "prompt_version": version,
                "timeout_sec": runtime_config.timeout_sec,
            }
            if runtime_config.max_output_tokens is not None:
                structure_kwargs["max_output_tokens"] = (
                    runtime_config.max_output_tokens
                )
            result = run_llm_assessment(source, **structure_kwargs)
            llm_runs.append(
                {
                    "check_id": CHECK_ID,
                    "prompt_version": version,
                    "model": result.model,
                    "telemetry": result.telemetry,
                }
            )
            for finding in result.findings:
                data = finding.to_dict()
                llm_subcategory = data.get("category")
                context = data.get("context") or {}
                if llm_subcategory:
                    context["llm_subcategory"] = llm_subcategory
                context["prompt_version"] = version
                context["llm_model"] = result.model
                data["context"] = context
                data["category"] = "structure"
                diagnostics.append(
                    with_meta(
                        data,
                        category="structure",
                        engine="llm",
                        check_id=CHECK_ID,
                    )
                )
        except Exception as e:
            diagnostics.append(
                with_meta(
                    {
                        "code": "LLM_STRUCTURE_ERROR",
                        "severity": "error",
                        "message": (
                            f"LLM structure assessment failed for "
                            f"prompt_version={version}: {e}"
                        ),
                    },
                    category="structure",
                    engine="llm",
                    check_id=CHECK_ID,
                )
            )
            return LLMCategoryResult(
                diagnostics=diagnostics,
                runtime_error=True,
                extras={"llm_runs": llm_runs},
            )

    return LLMCategoryResult(diagnostics=diagnostics, extras={"llm_runs": llm_runs})


def run_units(
    *,
    source: dict,
    file_path: Path,
    component: list[str] | None,
    run_all: bool,
    force: bool,
    store_path: Path | None,
    runtime_config: LLMRuntimeConfig,
    **_: Any,
) -> LLMCategoryResult:
    from vedalang.lint.llm_unit_check import (
        CHECK_ID,
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
        "llm_runs": [],
    }
    runtime_error = False

    resolved_store = store_path or default_store_path(file_path)
    result_extras["store_path"] = resolved_store
    store = load_store(resolved_store)

    try:
        versions = resolve_prompt_versions(CHECK_ID, runtime_config.prompt_version)
    except Exception as e:
        diagnostics.append(
            with_meta(
                {
                    "code": "LLM_UNIT_SELECTION_ERROR",
                    "severity": "error",
                    "message": f"Failed to resolve prompt version: {e}",
                },
                category="units",
                engine="llm",
                check_id=CHECK_ID,
            )
        )
        return LLMCategoryResult(
            diagnostics=diagnostics,
            runtime_error=True,
            extras=result_extras,
        )

    models = runtime_config.models
    if not models and runtime_config.model:
        models = [runtime_config.model]

    for prompt_version in versions:
        try:
            to_check, skipped_components = select_components(
                source=source,
                store=store,
                selected=component,
                run_all=run_all,
                force=force,
                prompt_version=prompt_version,
            )
            result_extras["unit_skipped_components"].extend(skipped_components)
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
                    check_id=CHECK_ID,
                )
            )
            return LLMCategoryResult(
                diagnostics=diagnostics,
                runtime_error=True,
                extras=result_extras,
            )

        for component_id in to_check:
            try:
                unit_kwargs: dict[str, Any] = {
                    "source": source,
                    "component": component_id,
                    "models": models,
                    "reasoning_effort": runtime_config.reasoning_effort,
                    "prompt_version": prompt_version,
                    "timeout_sec": runtime_config.timeout_sec,
                }
                if runtime_config.max_output_tokens is not None:
                    unit_kwargs["max_output_tokens"] = runtime_config.max_output_tokens
                result = run_component_unit_check(**unit_kwargs)
                update_store_with_result(
                    store,
                    result,
                    prompt_version=prompt_version,
                )
                result_extras["unit_results"].append(
                    {
                        "component": result.component,
                        "status": result.status,
                        "fingerprint": result.fingerprint,
                        "quorum": result.quorum,
                        "models": [v.model for v in result.votes],
                        "prompt_version": prompt_version,
                    }
                )
                for vote in result.votes:
                    result_extras["llm_runs"].append(
                        {
                            "check_id": CHECK_ID,
                            "prompt_version": prompt_version,
                            "component": result.component,
                            "model": vote.model,
                            "telemetry": vote.telemetry,
                        }
                    )
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
                                    "context": {"prompt_version": prompt_version},
                                },
                                category="units",
                                engine="llm",
                                check_id=CHECK_ID,
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
                                        "error_code": finding.get("error_code"),
                                        "error_family": finding.get("error_family"),
                                        "difficulty": finding.get("difficulty"),
                                        "prompt_version": prompt_version,
                                    },
                                },
                                category="units",
                                engine="llm",
                                check_id=CHECK_ID,
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
                            "message": (
                                "Unit check failed for "
                                f"prompt_version={prompt_version}: {e}"
                            ),
                        },
                        category="units",
                        engine="llm",
                        check_id=CHECK_ID,
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
