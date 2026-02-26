"""Canonical lint taxonomy and check registry for VedaLang."""

from __future__ import annotations

from dataclasses import dataclass

CATEGORY_ORDER = [
    "core",
    "identity",
    "structure",
    "units",
    "emissions",
    "feasibility",
]

CATEGORY_DESCRIPTIONS = {
    "core": "Parse/schema/cross-reference integrity checks.",
    "identity": "ID grammar, role/tech code validity, naming conventions.",
    "structure": "RES architecture/stage/role-variant topology correctness.",
    "units": "Units, basis consistency, and coefficient plausibility checks.",
    "emissions": "Emission namespace/type/factor integrity checks.",
    "feasibility": "Pre-solve heuristic risk checks.",
}

PROFILE_FAST = "fast"
PROFILE_THOROUGH = "thorough"
PROFILE_LLM = "llm"

FAST_CATEGORIES = {"core", "identity", "feasibility"}
THOROUGH_CATEGORIES = set(CATEGORY_ORDER)


@dataclass(frozen=True)
class LintCheck:
    check_id: str
    category: str
    engine: str  # "code" | "llm"
    profile: str  # "fast" | "thorough" | "llm"
    scope: str  # "model" | "component"
    runner: str
    supported: bool = True


CODE_CHECKS = [
    LintCheck(
        check_id="code.core.schema_xref",
        category="core",
        engine="code",
        profile=PROFILE_FAST,
        scope="model",
        runner="run_core_checks",
    ),
    LintCheck(
        check_id="code.identity.naming",
        category="identity",
        engine="code",
        profile=PROFILE_FAST,
        scope="model",
        runner="run_identity_checks",
    ),
    LintCheck(
        check_id="code.feasibility.heuristics",
        category="feasibility",
        engine="code",
        profile=PROFILE_FAST,
        scope="model",
        runner="run_feasibility_checks",
    ),
    LintCheck(
        check_id="code.structure.compiler_semantics",
        category="structure",
        engine="code",
        profile=PROFILE_THOROUGH,
        scope="model",
        runner="run_compiler_semantic_checks",
    ),
    LintCheck(
        check_id="code.units.compiler_semantics",
        category="units",
        engine="code",
        profile=PROFILE_THOROUGH,
        scope="model",
        runner="run_compiler_semantic_checks",
    ),
    LintCheck(
        check_id="code.emissions.compiler_semantics",
        category="emissions",
        engine="code",
        profile=PROFILE_THOROUGH,
        scope="model",
        runner="run_compiler_semantic_checks",
    ),
]

LLM_CHECKS = [
    LintCheck(
        check_id="llm.structure.res_assessment",
        category="structure",
        engine="llm",
        profile=PROFILE_LLM,
        scope="model",
        runner="run_llm_structure_assessment",
    ),
    LintCheck(
        check_id="llm.units.component_quorum",
        category="units",
        engine="llm",
        profile=PROFILE_LLM,
        scope="component",
        runner="run_llm_unit_quorum",
    ),
    LintCheck(
        check_id="llm.core.placeholder",
        category="core",
        engine="llm",
        profile=PROFILE_LLM,
        scope="model",
        runner="not_implemented",
        supported=False,
    ),
    LintCheck(
        check_id="llm.identity.placeholder",
        category="identity",
        engine="llm",
        profile=PROFILE_LLM,
        scope="model",
        runner="not_implemented",
        supported=False,
    ),
    LintCheck(
        check_id="llm.emissions.placeholder",
        category="emissions",
        engine="llm",
        profile=PROFILE_LLM,
        scope="model",
        runner="not_implemented",
        supported=False,
    ),
    LintCheck(
        check_id="llm.feasibility.placeholder",
        category="feasibility",
        engine="llm",
        profile=PROFILE_LLM,
        scope="model",
        runner="not_implemented",
        supported=False,
    ),
]


def normalize_categories(requested: list[str] | None) -> list[str]:
    """Return requested categories in canonical order (or all categories)."""
    if not requested:
        return list(CATEGORY_ORDER)
    unknown = sorted(set(requested) - set(CATEGORY_ORDER))
    if unknown:
        allowed = ", ".join(CATEGORY_ORDER)
        raise ValueError(
            f"Unknown category(s): {', '.join(unknown)}. "
            f"Valid categories: {allowed}"
        )
    requested_set = set(requested)
    return [c for c in CATEGORY_ORDER if c in requested_set]


def categories_for_profile(profile: str) -> set[str]:
    if profile == PROFILE_FAST:
        return set(FAST_CATEGORIES)
    if profile == PROFILE_THOROUGH:
        return set(THOROUGH_CATEGORIES)
    return set()


def checks_for_engine(engine: str) -> list[LintCheck]:
    if engine == "code":
        return list(CODE_CHECKS)
    if engine == "llm":
        return list(LLM_CHECKS)
    return []
