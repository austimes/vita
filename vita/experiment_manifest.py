"""Experiment manifest schema and parser for the Vita experiment system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class ExperimentManifestError(ValueError):
    """Raised when an experiment manifest is invalid."""


@dataclass(frozen=True)
class ExtensionSpec:
    id: str
    question: str


@dataclass(frozen=True)
class DefaultChecks:
    require_pipeline_success: bool
    require_solver_status: list[str]


@dataclass(frozen=True)
class ExperimentDefaults:
    case: str
    no_sankey: bool
    metrics: list[str]
    checks: DefaultChecks


@dataclass(frozen=True)
class CaseSpec:
    id: str
    model: Path
    run: str
    case: str
    notes: str | None = None
    hypothesis: str | None = None
    from_case: str | None = None


@dataclass(frozen=True)
class ComparisonSpec:
    id: str
    baseline: str
    variant: str
    metrics: list[str] | None = None
    focus_processes: list[str] | None = None


@dataclass(frozen=True)
class AnalysisSpec:
    id: str
    question: str
    comparisons: list[str]
    metrics_of_interest: list[str] | None = None
    rank_by: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ExperimentManifest:
    schema_version: int
    id: str
    title: str
    question: str
    extensions: list[ExtensionSpec]
    defaults: ExperimentDefaults
    baseline: CaseSpec
    variants: list[CaseSpec]
    comparisons: list[ComparisonSpec]
    analyses: list[AnalysisSpec]
    manifest_path: Path

    def all_cases(self) -> list[CaseSpec]:
        """Return baseline + all variants."""
        return [self.baseline, *self.variants]

    def get_case(self, case_id: str) -> CaseSpec:
        """Look up a case by ID. Raises ExperimentManifestError if not found."""
        for case in self.all_cases():
            if case.id == case_id:
                return case
        raise ExperimentManifestError(f"Unknown case ID: {case_id!r}")

    def get_comparison(self, comparison_id: str) -> ComparisonSpec:
        """Look up a comparison by ID. Raises ExperimentManifestError if not found."""
        for comp in self.comparisons:
            if comp.id == comparison_id:
                return comp
        raise ExperimentManifestError(f"Unknown comparison ID: {comparison_id!r}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

_REQUIRED_TOP_LEVEL = ("schema_version", "id", "title", "question", "baseline")


def load_experiment_manifest(manifest_path: Path) -> ExperimentManifest:
    """Load, validate, and resolve an experiment manifest from YAML."""
    manifest_path = manifest_path.expanduser().resolve()
    if not manifest_path.exists():
        raise ExperimentManifestError(
            f"Manifest file not found: {manifest_path}"
        )

    text = manifest_path.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExperimentManifestError(
            f"Invalid YAML in manifest: {manifest_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ExperimentManifestError(
            f"Expected a YAML mapping at top level in {manifest_path}"
        )

    # Required fields
    missing = [k for k in _REQUIRED_TOP_LEVEL if k not in raw]
    if missing:
        raise ExperimentManifestError(
            f"Missing required field(s): {', '.join(missing)}"
        )

    schema_version = raw["schema_version"]
    if schema_version != 1:
        raise ExperimentManifestError(
            f"Unsupported schema_version: {schema_version} (expected 1)"
        )

    manifest_dir = manifest_path.parent

    # Defaults
    defaults = _parse_defaults(raw.get("defaults", {}))

    # Extensions
    extensions = [
        _parse_extension(ext) for ext in raw.get("extensions", [])
    ]

    # Baseline
    baseline_raw = raw["baseline"]
    if not isinstance(baseline_raw, dict):
        raise ExperimentManifestError("'baseline' must be a mapping")
    baseline = _parse_case(baseline_raw, defaults=defaults, manifest_dir=manifest_dir)

    # Build a lookup of parsed cases for variant inheritance
    cases_by_id: dict[str, CaseSpec] = {baseline.id: baseline}

    # Variants
    variants: list[CaseSpec] = []
    for v_raw in raw.get("variants", []):
        if not isinstance(v_raw, dict):
            raise ExperimentManifestError("Each variant must be a mapping")
        variant = _parse_variant(
            v_raw,
            cases_by_id=cases_by_id,
            defaults=defaults,
            manifest_dir=manifest_dir,
        )
        if variant.id in cases_by_id:
            raise ExperimentManifestError(
                f"Duplicate case ID: {variant.id!r}"
            )
        cases_by_id[variant.id] = variant
        variants.append(variant)

    # Comparisons
    comparisons: list[ComparisonSpec] = []
    comparison_ids: set[str] = set()
    for c_raw in raw.get("comparisons", []):
        comp = _parse_comparison(c_raw)
        if comp.id in comparison_ids:
            raise ExperimentManifestError(
                f"Duplicate comparison ID: {comp.id!r}"
            )
        if comp.baseline not in cases_by_id:
            raise ExperimentManifestError(
                f"Comparison {comp.id!r} references unknown baseline case:"
                f" {comp.baseline!r}"
            )
        if comp.variant not in cases_by_id:
            raise ExperimentManifestError(
                f"Comparison {comp.id!r} references unknown variant case:"
                f" {comp.variant!r}"
            )
        comparison_ids.add(comp.id)
        comparisons.append(comp)

    # Analyses
    analyses: list[AnalysisSpec] = []
    for a_raw in raw.get("analyses", []):
        analysis = _parse_analysis(a_raw)
        for cref in analysis.comparisons:
            if cref not in comparison_ids:
                raise ExperimentManifestError(
                    f"Analysis {analysis.id!r} references unknown comparison: {cref!r}"
                )
        analyses.append(analysis)

    manifest = ExperimentManifest(
        schema_version=schema_version,
        id=raw["id"],
        title=raw["title"],
        question=raw["question"],
        extensions=extensions,
        defaults=defaults,
        baseline=baseline,
        variants=variants,
        comparisons=comparisons,
        analyses=analyses,
        manifest_path=manifest_path,
    )

    return manifest


def validate_manifest(manifest: ExperimentManifest) -> list[str]:
    """Return list of validation warnings (errors raise during load)."""
    warnings: list[str] = []
    for case in manifest.all_cases():
        if not case.model.exists():
            warnings.append(
                f"Model path does not exist for case {case.id!r}: {case.model}"
            )
    return warnings


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

_DEFAULT_METRICS = [
    "objective",
    "objective_breakdown",
    "var_act",
    "var_ncap",
    "var_cap",
    "var_flo",
]


def _parse_defaults(raw: object) -> ExperimentDefaults:
    if not isinstance(raw, dict):
        raw = {}
    checks_raw = raw.get("checks", {})
    if not isinstance(checks_raw, dict):
        checks_raw = {}
    checks = DefaultChecks(
        require_pipeline_success=checks_raw.get("require_pipeline_success", True),
        require_solver_status=checks_raw.get("require_solver_status", ["optimal"]),
    )
    return ExperimentDefaults(
        case=raw.get("case", "scenario"),
        no_sankey=raw.get("no_sankey", False),
        metrics=raw.get("metrics", list(_DEFAULT_METRICS)),
        checks=checks,
    )


def _parse_extension(raw: object) -> ExtensionSpec:
    if not isinstance(raw, dict):
        raise ExperimentManifestError("Each extension must be a mapping")
    _require_fields(raw, ("id", "question"), context="extension")
    return ExtensionSpec(id=raw["id"], question=raw["question"])


def _resolve_case_model_path(
    *,
    model_raw: str,
    manifest_dir: Path,
    context: str,
) -> Path:
    """Resolve and validate model path for user-facing experiment manifests."""
    model_path = (manifest_dir / model_raw).resolve()
    model_name = model_path.name.lower()
    is_tableir_like = model_name.endswith(
        (".tableir.yaml", ".tableir.yml", ".tableir.json")
    ) or (
        model_path.suffix.lower() in {".yaml", ".yml", ".json"}
        and "tableir" in model_name
    )
    if is_tableir_like:
        raise ExperimentManifestError(
            f"{context} model must be a VedaLang source (.veda.yaml/.veda.yml), "
            f"not TableIR: {model_raw}. TableIR workflows are dev-only and should use "
            "vedalang-dev tooling."
        )

    if not (
        model_name.endswith(".veda.yaml") or model_name.endswith(".veda.yml")
    ):
        raise ExperimentManifestError(
            f"{context} model must end with .veda.yaml or .veda.yml: {model_raw}"
        )

    return model_path


def _parse_case(
    raw: dict,
    *,
    defaults: ExperimentDefaults,
    manifest_dir: Path,
) -> CaseSpec:
    _require_fields(raw, ("id", "model", "run"), context=f"case {raw.get('id', '?')!r}")
    model_path = _resolve_case_model_path(
        model_raw=raw["model"],
        manifest_dir=manifest_dir,
        context=f"case {raw['id']!r}",
    )
    return CaseSpec(
        id=raw["id"],
        model=model_path,
        run=raw["run"],
        case=raw.get("case", defaults.case),
        notes=raw.get("notes"),
        hypothesis=raw.get("hypothesis"),
        from_case=None,
    )


def _parse_variant(
    raw: dict,
    *,
    cases_by_id: dict[str, CaseSpec],
    defaults: ExperimentDefaults,
    manifest_dir: Path,
) -> CaseSpec:
    _require_fields(raw, ("id",), context=f"variant {raw.get('id', '?')!r}")

    from_ref = raw.get("from")
    if from_ref is not None:
        if from_ref not in cases_by_id:
            raise ExperimentManifestError(
                f"Variant {raw['id']!r} references unknown 'from' case: {from_ref!r}"
            )
        parent = cases_by_id[from_ref]
        model_raw = raw.get("model")
        model_path = (
            _resolve_case_model_path(
                model_raw=model_raw,
                manifest_dir=manifest_dir,
                context=f"variant {raw['id']!r}",
            )
            if model_raw is not None
            else parent.model
        )
        return CaseSpec(
            id=raw["id"],
            model=model_path,
            run=raw.get("run", parent.run),
            case=raw.get("case", defaults.case),
            notes=raw.get("notes"),
            hypothesis=raw.get("hypothesis"),
            from_case=from_ref,
        )

    # No inheritance — require model and run
    _require_fields(raw, ("model", "run"), context=f"variant {raw['id']!r}")
    model_path = _resolve_case_model_path(
        model_raw=raw["model"],
        manifest_dir=manifest_dir,
        context=f"variant {raw['id']!r}",
    )
    return CaseSpec(
        id=raw["id"],
        model=model_path,
        run=raw["run"],
        case=raw.get("case", defaults.case),
        notes=raw.get("notes"),
        hypothesis=raw.get("hypothesis"),
        from_case=None,
    )


def _parse_comparison(raw: object) -> ComparisonSpec:
    if not isinstance(raw, dict):
        raise ExperimentManifestError("Each comparison must be a mapping")
    _require_fields(raw, ("id", "baseline", "variant"), context="comparison")
    return ComparisonSpec(
        id=raw["id"],
        baseline=raw["baseline"],
        variant=raw["variant"],
        metrics=raw.get("metrics"),
        focus_processes=raw.get("focus_processes"),
    )


def _parse_analysis(raw: object) -> AnalysisSpec:
    if not isinstance(raw, dict):
        raise ExperimentManifestError("Each analysis must be a mapping")
    _require_fields(raw, ("id", "question", "comparisons"), context="analysis")
    return AnalysisSpec(
        id=raw["id"],
        question=raw["question"],
        comparisons=raw["comparisons"],
        metrics_of_interest=raw.get("metrics_of_interest"),
        rank_by=raw.get("rank_by"),
        notes=raw.get("notes"),
    )


def _require_fields(raw: dict, fields: tuple[str, ...], *, context: str) -> None:
    missing = [f for f in fields if f not in raw]
    if missing:
        raise ExperimentManifestError(
            f"Missing required field(s) in {context}: {', '.join(missing)}"
        )
