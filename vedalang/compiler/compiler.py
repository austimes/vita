"""VedaLang to TableIR compiler."""

import json
import re
from copy import deepcopy
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

import jsonschema
import yaml
from pint import UnitRegistry
from pint.errors import DimensionalityError, UndefinedUnitError

from vedalang.conventions import (
    commodity_namespace_enum,
    commodity_type_enum,
    process_stage_enum,
)

from .demands import compile_demands
from .ir import (
    apply_process_parameters,
    build_roles,
    build_variants,
    expand_availability,
    lower_instances_to_tableir,
)
from .naming import NamingRegistry
from .registry import VedaLangError, get_registry
from .segments import build_segments, normalize_commodity

SCHEMA_DIR = Path(__file__).parent.parent / "schema"

# Unit categories for semantic validation
ENERGY_UNITS = {"PJ", "TJ", "GJ", "MWh", "GWh", "TWh", "MTOE", "KTOE"}
POWER_UNITS = {"GW", "MW", "kW", "TW"}
MASS_UNITS = {"Mt", "kt", "t", "Gt"}
CURRENCY_UNITS = {"USD", "kUSD", "MUSD", "BUSD"}
SUPPORTED_MONETARY_CURRENCIES = {"AUD", "USD"}
MONETARY_SCALE_FACTORS = {
    "": 1.0,
    "k": 1e3,
    "M": 1e6,
    "B": 1e9,
}
MONETARY_TOKEN_RE = re.compile(r"^\s*([kMB]?)([A-Z]{3})(\d{2}|\d{4})\s*$")
COST_RATE_LITERAL_RE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+([kMB]?)([A-Z]{3})(\d{2}|\d{4})/([A-Za-z][A-Za-z0-9]*(?:/[A-Za-z][A-Za-z0-9]*)?)(?:/(yr))?\s*$"
)
SERVICE_UNITS = {"Bvkm"}
ENERGY_BASES = {"HHV", "LHV"}
PROCESS_UNIT_EXPR_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9]*)(?:/([A-Za-z][A-Za-z0-9]*))?$"
)
SUPPORTED_RATE_DENOMINATORS = {"yr"}
MODEL_TIME_BASIS = "model_year"

UNIT_DIMENSIONS = {
    **{u: "energy" for u in ENERGY_UNITS},
    **{u: "power" for u in POWER_UNITS},
    **{u: "mass" for u in MASS_UNITS},
    **{u: "currency" for u in CURRENCY_UNITS},
    **{u: "service" for u in SERVICE_UNITS},
}

ENERGY_UNIT_TO_PJ = {
    "PJ": 1.0,
    "TJ": 1e-3,
    "GJ": 1e-6,
    "MWh": 3.6e-6,
    "GWh": 3.6e-3,
    "TWh": 3.6,
    "MTOE": 41.868,
    "KTOE": 0.041868,
}

POWER_UNIT_TO_GW = {
    "GW": 1.0,
    "MW": 1e-3,
    "kW": 1e-6,
    "TW": 1e3,
}

# Default units by canonical commodity type
DEFAULT_UNITS = {
    # Canonical commodity types
    "fuel": "PJ",
    "energy": "PJ",
    "service": "PJ",
    "material": "Mt",
    "emission": "Mt",
    "money": "MUSD",
    "other": "PJ",
}

# Capacity-to-activity conversion constant:
# 1 GW used for a full year = 31.536 PJ/year.
GW_YEAR_TO_PJ = 31.536


@lru_cache(maxsize=1)
def _unit_registry() -> UnitRegistry:
    """Build shared unit registry for explicit unit expression conversion."""
    ureg = UnitRegistry(case_sensitive=True)

    def define_if_missing(symbol: str, definition: str) -> None:
        try:
            ureg.parse_units(symbol)
            return
        except UndefinedUnitError:
            pass
        ureg.define(definition)

    define_if_missing(MODEL_TIME_BASIS, f"{MODEL_TIME_BASIS} = 365 * day")
    define_if_missing("toe", "toe = 41.868e9 * joule")
    define_if_missing("MTOE", "MTOE = 1e6 * toe")
    define_if_missing("KTOE", "KTOE = 1e3 * toe")
    define_if_missing("Bvkm", "Bvkm = 1e9 * kilometer")
    define_if_missing("kt", "kt = 1e3 * tonne")
    define_if_missing("Mt", "Mt = 1e6 * tonne")
    define_if_missing("Gt", "Gt = 1e9 * tonne")
    return ureg


def _parse_process_unit_expression(unit_expr: str) -> tuple[str, str | None] | None:
    """Parse '<base>' or '<base>/yr' process unit expressions."""
    if not isinstance(unit_expr, str):
        return None
    match = PROCESS_UNIT_EXPR_RE.fullmatch(unit_expr.strip())
    if not match:
        return None
    base, denominator = match.groups()
    return base, denominator


def _to_pint_unit_expression(unit_expr: str) -> str | None:
    """Map process unit expression to pint syntax with model time basis."""
    parsed = _parse_process_unit_expression(unit_expr)
    if parsed is None:
        return None
    base, denominator = parsed
    if denominator is None:
        return base
    if denominator not in SUPPORTED_RATE_DENOMINATORS:
        return None
    return f"{base}/{MODEL_TIME_BASIS}"

# Process attributes that support time-varying values
TIME_VARYING_ATTRS = {
    "efficiency", "investment_cost", "fixed_om_cost", "variable_om_cost",
    "import_price", "lifetime", "availability_factor",
    # emission_factors values also support time-varying
}

# Attributes that MUST be expanded to all milestone years (even for scalars)
# These are attributes where TIMES implicit interpolation can cause surprises
# See AGENTS.md: "Avoid Implicit TIMES Interpolation"
#
# Per AGENTS.md, the key parameters with surprising interpolation are:
# - PRC_RESID (stock) - decays linearly over TLIFE by default
# - Bounds (ACT_BND, CAP_BND, NCAP_BND) - handled separately
# - COM_PROJ (demand projections) - already expanded in scenario compilation
#
# For now, we only force expansion on 'stock' (PRC_RESID) since it has the most
# surprising default behavior (linear decay). Costs and efficiency are left as
# scalars when specified as scalars - TIMES applies them uniformly which is expected.
EXPAND_TO_ALL_YEARS_ATTRS = {
    "stock",  # PRC_RESID - decays linearly by default, must be explicit
}

# Bound attributes that must be expanded to all years
# Bounds are period-indexed and need explicit values per milestone year
EXPAND_TO_ALL_YEARS_BOUNDS = {
    "activity_bound",  # ACT_BND
    "cap_bound",       # CAP_BND
    "ncap_bound",      # NCAP_BND
}

# Map VedaLang attribute names to their TableIR/VEDA column names
# These must map to CANONICAL VEDA attribute column headers only
# (from attribute-master.json "column_header" field, NOT aliases)
ATTR_TO_COLUMN = {
    "efficiency": "eff",                # ACT_EFF
    "investment_cost": "ncap_cost",     # NCAP_COST - capital cost per capacity
    "fixed_om_cost": "ncap_fom",        # NCAP_FOM - fixed O&M per capacity/year
    "variable_om_cost": "act_cost",     # ACT_COST - variable cost per activity
    "import_price": "ire_price",        # IRE_PRICE - import/export commodity price
    "lifetime": "ncap_tlife",           # NCAP_TLIFE - technical lifetime
    "availability_factor": "ncap_af",   # NCAP_AF - capacity factor
    "stock": "prc_resid",               # PRC_RESID - residual/existing capacity
    "existing_capacity": "ncap_pasti",  # NCAP_PASTI - past investment with vintage
}

# Interpolation mode to VEDA code mapping
INTERPOLATION_CODES = {
    "none": -1,
    "interp_only": 1,
    "interp_extrap_eps": 2,
    "interp_extrap": 3,
    "interp_extrap_back": 4,
    "interp_extrap_forward": 5,
}

# Map VedaLang semantic attribute names to canonical TIMES attribute names
# Used for registry validation (registry uses TIMES names like NCAP_COST)
SEMANTIC_TO_TIMES = {
    "efficiency": "ACT_EFF",
    "investment_cost": "NCAP_COST",
    "fixed_om_cost": "NCAP_FOM",
    "variable_om_cost": "ACT_COST",
    "import_price": "IRE_PRICE",
    "lifetime": "NCAP_TLIFE",
    "availability_factor": "NCAP_AF",
    "stock": "PRC_RESID",
    "existing_capacity": "NCAP_PASTI",
}

# Default category inference from scenario parameter type
DEFAULT_CATEGORY_FROM_TYPE = {
    "commodity_price": "prices",
    "demand_projection": "demands",
}

# Valid scenario categories
VALID_CATEGORIES = {
    "demands",
    "prices",
    "policies",
    "technology_assumptions",
    "resource_availability",
    "global_settings",
}

VALID_PROCESS_STAGES = process_stage_enum()
VALID_COMMODITY_TYPES = commodity_type_enum()
VALID_COMMODITY_NAMESPACES = set(commodity_namespace_enum())

NAMESPACE_TO_TYPES = {
    "secondary": {"energy"},
    "primary": {"fuel"},
    "resource": {"other", "energy"},
    "material": {"material"},
    "service": {"service"},
    "emission": {"emission"},
    "money": {"money"},
}

AMBIGUOUS_EMISSION_SPECIES = {"co2", "co2e", "ch4", "n2o"}
LEGACY_NAMESPACES = {"C", "E", "S", "M", "D", "F"}

ROLE_FUEL_PATHWAY_PATTERN = re.compile(
    r"(?:^|_)(?:from|with|using|via)_(?:[a-z0-9_]+)$"
)


def _split_namespace(commodity_ref: str) -> tuple[str | None, str]:
    """Return namespace + base name for a commodity reference."""
    if ":" not in commodity_ref:
        return None, commodity_ref
    namespace, _, base = commodity_ref.partition(":")
    return namespace, base


def _is_emission_namespace_ref(commodity_ref: str) -> bool:
    """True when commodity reference is explicitly namespaced as emission:*."""
    namespace, _ = _split_namespace(commodity_ref)
    return namespace == "emission"


def _is_legacy_namespace(namespace: str | None) -> bool:
    """Legacy VEDA-style commodity namespaces like C:/E:/S: remain valid."""
    if namespace is None:
        return False
    return namespace in LEGACY_NAMESPACES


def _is_ambiguous_unnamespaced_emission(commodity_ref: str) -> bool:
    """True when commodity reference looks like bare emission species name."""
    namespace, base = _split_namespace(commodity_ref)
    if namespace is not None:
        return False
    return base.lower() in AMBIGUOUS_EMISSION_SPECIES


def _warn_ambiguous_commodity_ref(
    warnings: list[str],
    location: str,
    commodity_ref: str,
) -> None:
    """Emit L5-style migration aid warning for ambiguous bare emission names."""
    if not _is_ambiguous_unnamespaced_emission(commodity_ref):
        return
    warnings.append(
        f"{location} uses ambiguous un-namespaced commodity '{commodity_ref}'. "
        f"Did you mean 'emission:{commodity_ref.lower()}' or "
        f"'material:{commodity_ref.lower()}'?"
    )


def _combustion_metadata_issues(comm_id: str, comm: dict) -> list[str]:
    """Return deterministic commodity combustibility metadata issues."""
    issues: list[str] = []
    comm_type = comm.get("type", "energy")
    unit = comm.get("unit") or _get_default_unit(comm_type)
    dimension = UNIT_DIMENSIONS.get(unit)
    combustible = comm.get("combustible")
    has_lhv = "lhv_mj_per_unit" in comm
    has_hhv = "hhv_mj_per_unit" in comm

    # For now we require explicit combustibility on all energy-domain carriers.
    requires_combustible_flag = (
        comm_type in {"fuel", "energy"} and dimension == "energy"
    )
    if requires_combustible_flag and combustible is None:
        issues.append(
            f"Commodity '{comm_id}' (type '{comm_type}', unit '{unit}') must set "
            "'combustible: true|false' explicitly."
        )
        return issues

    if combustible is None:
        if has_lhv or has_hhv:
            issues.append(
                f"Commodity '{comm_id}' defines heating values but is missing "
                "'combustible: true|false'."
            )
        return issues

    if combustible:
        if dimension != "energy":
            issues.append(
                f"Commodity '{comm_id}' is marked combustible but unit '{unit}' is not "
                "an energy-domain unit."
            )
        if not has_lhv or not has_hhv:
            issues.append(
                f"Commodity '{comm_id}' with combustible=true must include both "
                "'lhv_mj_per_unit' and 'hhv_mj_per_unit'."
            )
            return issues
        lhv = comm.get("lhv_mj_per_unit")
        hhv = comm.get("hhv_mj_per_unit")
        if not isinstance(lhv, (int, float)) or float(lhv) <= 0:
            issues.append(
                f"Commodity '{comm_id}' has invalid lhv_mj_per_unit '{lhv}'. "
                "Expected a positive number."
            )
        if not isinstance(hhv, (int, float)) or float(hhv) <= 0:
            issues.append(
                f"Commodity '{comm_id}' has invalid hhv_mj_per_unit '{hhv}'. "
                "Expected a positive number."
            )
        if (
            isinstance(lhv, (int, float))
            and isinstance(hhv, (int, float))
            and hhv < lhv
        ):
            issues.append(
                f"Commodity '{comm_id}' has hhv_mj_per_unit ({hhv}) lower than "
                f"lhv_mj_per_unit ({lhv}); expected HHV >= LHV."
            )
    else:
        if has_lhv or has_hhv:
            issues.append(
                f"Commodity '{comm_id}' has combustible=false but defines heating "
                "values. "
                "Remove lhv_mj_per_unit/hhv_mj_per_unit or set combustible=true."
            )
        basis = comm.get("basis")
        if basis in ENERGY_BASES:
            issues.append(
                f"Commodity '{comm_id}' has combustible=false but basis='{basis}'. "
                "Remove basis or mark commodity combustible."
            )

    return issues


def _format_structural_errors(errors: list[dict[str, str]]) -> str:
    """Format structural invariant errors as deterministic diagnostics."""
    ordered = sorted(
        errors,
        key=lambda err: (err["code"], err["location"], err["message"]),
    )
    lines = [f"{len(ordered)} structural invariant violation(s):"]
    for err in ordered:
        lines.append(
            f"  - [{err['code']}] {err['location']}: {err['message']}"
        )
    return "\n".join(lines)


def _normalize_commodities_for_new_syntax(
    raw_commodities: list[dict],
) -> dict[str, dict]:
    """Normalize commodities with deterministic structural diagnostics."""
    normalized: dict[str, dict] = {}
    errors: list[dict[str, str]] = []

    for idx, raw in enumerate(raw_commodities):
        comm_id = raw.get("id") or raw.get("name") or f"<commodity#{idx}>"
        comm_type = raw.get("type")
        if comm_type not in VALID_COMMODITY_TYPES:
            allowed = ", ".join(VALID_COMMODITY_TYPES)
            errors.append(
                {
                    "code": "E_COMMODITY_TYPE_ENUM",
                    "location": f"model.commodities[{comm_id}]",
                    "message": (
                        "Commodity type must be one of "
                        f"[{allowed}], got '{comm_type}'."
                    ),
                }
            )
            continue

        try:
            norm = normalize_commodity(raw)
        except ValueError as exc:
            errors.append(
                {
                    "code": "E_COMMODITY_TYPE_ENUM",
                    "location": f"model.commodities[{comm_id}]",
                    "message": str(exc),
                }
            )
            continue

        # Override normalize_commodity's generic PJ default with
        # canonical type-based defaults used by the compiler.
        if "unit" not in raw:
            norm["unit"] = _get_default_unit(comm_type)
        if "basis" in raw:
            norm["basis"] = raw["basis"]
        for field in ("combustible", "lhv_mj_per_unit", "hhv_mj_per_unit"):
            if field in raw:
                norm[field] = raw[field]

        normalized[norm["id"]] = norm

    if errors:
        raise VedaLangError(_format_structural_errors(errors))

    return normalized


def _collect_new_syntax_structural_invariants(
    source: dict,
    roles: dict,
    commodities: dict[str, dict],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Collect compiler-enforced structural invariant diagnostics for new syntax."""
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    unit_policy = _resolve_unit_policy(source.get("model", {}))

    def append_unit_issue(
        *,
        location: str,
        message: str,
        error_code: str,
        warning_code: str,
    ) -> None:
        issue = {
            "code": error_code if _is_strict_unit_mode(unit_policy) else warning_code,
            "location": location,
            "message": message,
        }
        if _is_strict_unit_mode(unit_policy):
            errors.append(issue)
        else:
            warnings.append(issue)

    for comm_id, comm in sorted(commodities.items()):
        comm_type = comm.get("type", "energy")
        unit = comm.get("unit") or _get_default_unit(comm_type)
        dimension = UNIT_DIMENSIONS.get(unit)
        if dimension is None:
            append_unit_issue(
                location=f"model.commodities[{comm_id}]",
                message=(
                    f"Commodity '{comm_id}' has unsupported unit '{unit}'. "
                    "Use a unit from the schema enum."
                ),
                error_code="E_UNIT_UNSUPPORTED",
                warning_code="W_UNIT_UNSUPPORTED",
            )
            continue

        if unit not in unit_policy["allowed_units"].get(dimension, set()):
            append_unit_issue(
                location=f"model.commodities[{comm_id}]",
                message=(
                    f"Commodity '{comm_id}' uses unit '{unit}' which is not allowed by "
                    "model.unit_policy.allowed_units."
                ),
                error_code="E_UNIT_POLICY_DISALLOWED",
                warning_code="W_UNIT_POLICY_DISALLOWED",
            )

        basis = comm.get("basis")
        if basis is not None and basis not in ENERGY_BASES:
            append_unit_issue(
                location=f"model.commodities[{comm_id}]",
                message=(
                    f"Commodity '{comm_id}' has invalid basis '{basis}'. "
                    "Expected HHV or LHV."
                ),
                error_code="E_BASIS_ENUM",
                warning_code="W_BASIS_ENUM",
            )
        if _is_strict_unit_mode(unit_policy):
            for issue in _combustion_metadata_issues(comm_id, comm):
                errors.append(
                    {
                        "code": "E_COMBUSTIBLE_METADATA",
                        "location": f"model.commodities[{comm_id}]",
                        "message": issue,
                    }
                )

    for role_id, role in sorted(roles.items()):
        if role.stage not in VALID_PROCESS_STAGES:
            errors.append(
                {
                    "code": "E_STAGE_ENUM",
                    "location": f"process_roles[{role_id}]",
                    "message": (
                        "Stage must be one of "
                        f"{list(VALID_PROCESS_STAGES)}, got '{role.stage}'."
                    ),
                }
            )

        for idx, commodity_ref in enumerate(role.required_inputs):
            if _is_emission_namespace_ref(commodity_ref):
                errors.append(
                    {
                        "code": "E_EMISSION_NAMESPACE_FLOW",
                        "location": (
                            f"process_roles[{role_id}].required_inputs[{idx}].commodity"
                        ),
                        "message": (
                            "L1 violation: emission:* commodities must not appear in "
                            "role required_inputs."
                        ),
                    }
                )

        for idx, commodity_ref in enumerate(role.required_outputs):
            if _is_emission_namespace_ref(commodity_ref):
                errors.append(
                    {
                        "code": "E_EMISSION_NAMESPACE_FLOW",
                        "location": (
                            f"process_roles[{role_id}].required_outputs[{idx}].commodity"
                        ),
                        "message": (
                            "L1/L4 violation: emission:* commodities "
                            "must not appear in "
                            "role required_outputs."
                        ),
                    }
                )

    for role_id, issue in _validate_role_primary_outputs(roles, commodities):
        errors.append(
            {
                "code": "E_ROLE_PRIMARY_OUTPUT",
                "location": f"process_roles[{role_id}]",
                "message": issue,
            }
        )

    dup_errors, dup_warnings = _detect_service_role_duplication(roles, commodities)
    errors.extend(dup_errors)
    warnings.extend(dup_warnings)

    for variant in source.get("process_variants") or []:
        variant_id = variant.get("id", "<variant>")
        role = roles.get(variant.get("role"))

        for idx, inp in enumerate(variant.get("inputs") or []):
            commodity_ref = inp.get("commodity")
            if commodity_ref and _is_emission_namespace_ref(commodity_ref):
                errors.append(
                    {
                        "code": "E_EMISSION_NAMESPACE_FLOW",
                        "location": (
                            f"process_variants[{variant_id}].inputs[{idx}].commodity"
                        ),
                        "message": (
                            "L1 violation: emission:* commodities must not appear in "
                            "variant inputs. Use emission_factors instead."
                        ),
                    }
                )

        for idx, out in enumerate(variant.get("outputs") or []):
            commodity_ref = out.get("commodity")
            if commodity_ref and _is_emission_namespace_ref(commodity_ref):
                errors.append(
                    {
                        "code": "E_EMISSION_NAMESPACE_FLOW",
                        "location": (
                            f"process_variants[{variant_id}].outputs[{idx}].commodity"
                        ),
                        "message": (
                            "L1/L4 violation: emission:* commodities "
                            "must not appear in "
                            "variant outputs. Use emission_factors instead."
                        ),
                    }
                )

        if role is None or role.stage != "end_use":
            continue

        # Variant inputs are explicit (required)
        variant_inputs = [
            inp["commodity"] for inp in variant.get("inputs") or []
        ]

        physical_inputs = [
            inp
            for inp in variant_inputs
            if _commodity_kind(commodities.get(inp, {})) not in {"service", "emission"}
        ]
        if physical_inputs:
            continue

        errors.append(
            {
                "code": "E_END_USE_PHYSICAL_INPUT",
                "location": f"process_variants[{variant_id}]",
                "message": (
                    "End-use variants must have at least one physical input "
                    "(fuel/energy/material)."
                ),
            }
        )

    for demand in source.get("demands") or []:
        commodity = demand.get("commodity")
        comm = commodities.get(commodity)
        if not comm:
            continue
        if comm.get("type") != "service":
            errors.append(
                {
                    "code": "E_DEMAND_COMMODITY_TYPE",
                    "location": f"demands[{commodity}]",
                    "message": (
                        "Demand commodity must be type='service', "
                        f"got type='{comm.get('type')}'."
                    ),
                }
            )

    for variant in source.get("process_variants") or []:
        variant_id = variant.get("id", "<variant>")
        role = roles.get(variant.get("role"))
        emission_factors = variant.get("emission_factors") or {}
        activity_unit = role.activity_unit if role is not None else "PJ"
        capacity_unit = role.capacity_unit if role is not None else "GW"
        performance_metric = variant.get("performance_metric", "efficiency")

        variant_unit_errors: list[str] = []
        variant_unit_warnings: list[str] = []
        _validate_process_unit_pair(
            process_label=f"process_variants[{variant_id}]",
            activity_unit=activity_unit,
            capacity_unit=capacity_unit,
            policy=unit_policy,
            errors=variant_unit_errors,
            warnings=variant_unit_warnings,
        )
        has_flow_anchors = any(
            "coefficient" in flow
            for flow in (variant.get("inputs", []) + variant.get("outputs", []))
        )
        if "efficiency" in variant:
            _validate_efficiency_metric(
                process_label=f"process_variants[{variant_id}]",
                efficiency_value=variant.get("efficiency"),
                performance_metric=performance_metric,
                policy=unit_policy,
                errors=variant_unit_errors,
                warnings=variant_unit_warnings,
            )
        if has_flow_anchors:
            if "efficiency" not in variant:
                _record_unit_diagnostic(
                    variant_unit_errors,
                    variant_unit_warnings,
                    unit_policy,
                    (
                        "process_variants"
                        f"[{variant_id}] defines coefficient anchors but has no "
                        "efficiency value; cannot run anchor magnitude checks."
                    ),
                )
            else:
                _validate_flow_coefficient_anchors(
                    process_label=f"process_variants[{variant_id}]",
                    inputs=variant.get("inputs", []),
                    outputs=variant.get("outputs", []),
                    efficiency_value=variant.get("efficiency"),
                    performance_metric=performance_metric,
                    commodities=commodities,
                    policy=unit_policy,
                    errors=variant_unit_errors,
                    warnings=variant_unit_warnings,
                )
        for msg in variant_unit_errors:
            errors.append(
                {
                    "code": "E_PROCESS_UNITS",
                    "location": f"process_variants[{variant_id}]",
                    "message": msg,
                }
            )
        for msg in variant_unit_warnings:
            warnings.append(
                {
                    "code": "W_PROCESS_UNITS",
                    "location": f"process_variants[{variant_id}]",
                    "message": msg,
                }
            )

        flow_commodities = [i["commodity"] for i in variant.get("inputs") or []]
        flow_commodities.extend(o["commodity"] for o in variant.get("outputs") or [])
        flow_units = {
            comm_id: (commodities.get(comm_id, {}).get("unit") or "")
            for comm_id in flow_commodities
            if comm_id in commodities
        }
        flow_dims = {
            UNIT_DIMENSIONS.get(unit)
            for unit in flow_units.values()
            if UNIT_DIMENSIONS.get(unit) in {"energy", "mass"}
        }
        if {"energy", "mass"}.issubset(flow_dims):
            policy_basis = unit_policy.get("energy_basis")
            for comm_id, unit in sorted(flow_units.items()):
                dim = UNIT_DIMENSIONS.get(unit)
                if dim not in {"energy", "mass"}:
                    continue
                basis = commodities.get(comm_id, {}).get("basis")
                if not basis:
                    append_unit_issue(
                        location=f"process_variants[{variant_id}]",
                        message=(
                            "Energy/mass conversion requires basis metadata: "
                            f"commodity '{comm_id}' (unit '{unit}') has no basis."
                        ),
                        error_code="E_ENERGY_MASS_BASIS_REQUIRED",
                        warning_code="W_ENERGY_MASS_BASIS_REQUIRED",
                    )
                    continue
                if policy_basis and basis != policy_basis:
                    append_unit_issue(
                        location=f"process_variants[{variant_id}]",
                        message=(
                            f"Commodity '{comm_id}' basis '{basis}' conflicts with "
                            f"model.unit_policy.energy_basis '{policy_basis}'."
                        ),
                        error_code="E_ENERGY_MASS_BASIS_MISMATCH",
                        warning_code="W_ENERGY_MASS_BASIS_MISMATCH",
                    )

        if (
            unit_policy.get("forbid_unit_transform_processes", False)
            and _detect_fake_unit_transform_process(
                inputs=[inp["commodity"] for inp in variant.get("inputs", [])],
                outputs=[out["commodity"] for out in variant.get("outputs", [])],
                attrs=variant,
                kind=variant.get("kind"),
            )
        ):
            errors.append(
                {
                    "code": "E_UNIT_TRANSFORM_PROCESS",
                    "location": f"process_variants[{variant_id}]",
                    "message": (
                        "Variant appears to be a unit-only pass-through "
                        "(same commodity in/out without physical transformation)."
                    ),
                }
            )

        has_negative = False
        for emission_comm in sorted(emission_factors.keys()):
            if ":" in emission_comm and not _is_emission_namespace_ref(emission_comm):
                errors.append(
                    {
                        "code": "E_EMISSION_FACTOR_NAMESPACE",
                        "location": (
                            f"process_variants[{variant_id}]."
                            f"emission_factors[{emission_comm}]"
                        ),
                        "message": (
                            "L2 violation: emission_factors keys must be namespaced "
                            "as emission:*."
                        ),
                    }
                )

            value = emission_factors.get(emission_comm)
            if isinstance(value, (int, float)) and value < 0:
                has_negative = True
            elif isinstance(value, dict):
                series = value.get("values") or {}
                if any(v < 0 for v in series.values()):
                    has_negative = True

            comm = commodities.get(emission_comm)
            if not comm:
                continue
            if comm.get("type") != "emission":
                errors.append(
                    {
                        "code": "E_EMISSION_COMMODITY_TYPE",
                        "location": (
                            f"process_variants[{variant_id}]."
                            f"emission_factors[{emission_comm}]"
                        ),
                        "message": (
                            "Emission commodity must be type='emission', "
                            f"got type='{comm.get('type')}'."
                        ),
                    }
                )

        if has_negative and not (
            (variant.get("description") or "").strip()
            or (variant.get("notes") or "").strip()
        ):
            warnings.append(
                {
                    "code": "W_NEGATIVE_EMISSION_DOC",
                    "location": f"process_variants[{variant_id}]",
                    "message": (
                        "L3 guidance: negative emission_factors are allowed, but add "
                        "description/notes for auditability."
                    ),
                }
            )

    for constraint in source.get("model", {}).get("constraints", []):
        if constraint.get("type") != "emission_cap":
            continue
        commodity = constraint.get("commodity")
        comm = commodities.get(commodity)
        if not comm:
            continue
        if comm.get("type") != "emission":
            constraint_name = constraint.get("name", "<constraint>")
            errors.append(
                {
                    "code": "E_EMISSION_COMMODITY_TYPE",
                    "location": f"model.constraints[{constraint_name}]",
                    "message": (
                        "Emission cap commodity must be type='emission', "
                        f"got type='{comm.get('type')}'."
                    ),
                }
            )

    return (
        sorted(
            errors,
            key=lambda err: (err["code"], err["location"], err["message"]),
        ),
        sorted(
            warnings,
            key=lambda warn: (warn["code"], warn["location"], warn["message"]),
        ),
    )


def _validate_new_syntax_structural_invariants(
    source: dict,
    roles: dict,
    commodities: dict[str, dict],
) -> list[dict[str, str]]:
    """Validate compiler-enforced structural invariants for new syntax."""
    errors, warnings = _collect_new_syntax_structural_invariants(
        source,
        roles,
        commodities,
    )
    if errors:
        raise VedaLangError(_format_structural_errors(errors))
    return warnings


def collect_new_syntax_structural_diagnostics(
    source: dict,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return structured structural/unit/emission diagnostics for new syntax models."""
    if not source.get("process_roles"):
        return [], []

    normalized_source, _ = _normalize_new_syntax_monetary_costs(source)
    model = normalized_source["model"]
    commodities = _normalize_commodities_for_new_syntax(model.get("commodities", []))
    roles = build_roles(normalized_source, commodities)
    return _collect_new_syntax_structural_invariants(
        normalized_source,
        roles,
        commodities,
    )


def _is_time_varying(value) -> bool:
    """Check if a value is a time-varying specification (dict with 'values' key)."""
    return isinstance(value, dict) and "values" in value


def _normalize_process_flows(process: dict) -> dict:
    """
    Normalize process input/output shorthand to standard array format.

    Converts:
      input: "NG" → inputs: [{commodity: "NG"}]
      output: "ELC" → outputs: [{commodity: "ELC"}]

    Args:
        process: Process definition (may have shorthand or standard format)

    Returns:
        Process with normalized inputs/outputs arrays
    """
    result = process.copy()

    # Normalize single input string to array
    if "input" in result and "inputs" not in result:
        result["inputs"] = [{"commodity": result["input"]}]
        del result["input"]

    # Normalize single output string to array
    if "output" in result and "outputs" not in result:
        result["outputs"] = [{"commodity": result["output"]}]
        del result["output"]

    return result


def _get_default_unit(commodity_type: str) -> str:
    """Get default unit for a commodity type."""
    return DEFAULT_UNITS.get(commodity_type, "PJ")


def _resolve_unit_policy(model: dict) -> dict:
    """Resolve unit policy with defaults."""
    raw = model.get("unit_policy") or {}
    return {
        "mode": raw.get("mode", "permissive"),
        "energy_basis": raw.get("energy_basis"),
        "forbid_unit_transform_processes": raw.get(
            "forbid_unit_transform_processes", False
        ),
        "allowed_units": {
            "energy": set(raw.get("allowed_units", {}).get("energy", ENERGY_UNITS)),
            "power": set(raw.get("allowed_units", {}).get("power", POWER_UNITS)),
            "mass": set(raw.get("allowed_units", {}).get("mass", MASS_UNITS)),
            "currency": set(
                raw.get("allowed_units", {}).get("currency", CURRENCY_UNITS)
            ),
            "service": set(
                raw.get("allowed_units", {}).get("service", SERVICE_UNITS)
            ),
        },
    }


def _is_strict_unit_mode(policy: dict) -> bool:
    """Return True when unit policy should fail on violations."""
    return policy.get("mode") == "strict"


def _parse_money_year(year_token: str) -> int:
    """Parse 2-digit or 4-digit money year token into YYYY."""
    if len(year_token) == 2:
        return 2000 + int(year_token)
    return int(year_token)


def _parse_monetary_token(token: str, *, field_path: str) -> tuple[str, str, int]:
    """Parse shorthand token like MUSD24 into (scale, currency, year)."""
    match = MONETARY_TOKEN_RE.match(token)
    if not match:
        raise SemanticValidationError(
            [
                f"{field_path} must use shorthand like MAUD24 or USD23; "
                f"got '{token}'."
            ]
        )
    scale, currency, year_token = match.groups()
    if currency not in SUPPORTED_MONETARY_CURRENCIES:
        allowed = ", ".join(sorted(SUPPORTED_MONETARY_CURRENCIES))
        raise SemanticValidationError(
            [
                f"{field_path} uses unsupported currency '{currency}'. "
                f"Supported currencies: {allowed}."
            ]
        )
    return scale, currency, _parse_money_year(year_token)


def _load_yaml_file(path: Path) -> dict:
    """Load YAML file as dict."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SemanticValidationError([f"YAML file '{path}' must contain an object"])
    return data


def _load_fx_table(path: Path) -> dict[int, dict[str, float]]:
    """Load FX table in rules/monetary fx format."""
    data = _load_yaml_file(path)
    rates = data.get("rates")
    if not isinstance(rates, dict):
        raise SemanticValidationError(
            [f"FX table '{path}' must contain top-level 'rates' mapping."]
        )

    result: dict[int, dict[str, float]] = {}
    for year_key, row in rates.items():
        if not isinstance(row, dict):
            continue
        try:
            year = int(year_key)
        except (TypeError, ValueError):
            continue
        if "aud_per_usd" in row and "usd_per_aud" in row:
            result[year] = {
                "aud_per_usd": float(row["aud_per_usd"]),
                "usd_per_aud": float(row["usd_per_aud"]),
            }
    if not result:
        raise SemanticValidationError(
            [f"FX table '{path}' does not contain usable yearly AUD/USD rates."]
        )
    return result


def _load_cpi_table(path: Path) -> dict[int, float]:
    """Load CPI table with top-level index map: {year: value}."""
    data = _load_yaml_file(path)
    index = data.get("index")
    if not isinstance(index, dict):
        raise SemanticValidationError(
            [f"CPI table '{path}' must contain top-level 'index' mapping."]
        )
    result: dict[int, float] = {}
    for year_key, value in index.items():
        try:
            year = int(year_key)
            result[year] = float(value)
        except (TypeError, ValueError):
            continue
    if not result:
        raise SemanticValidationError(
            [f"CPI table '{path}' does not contain usable year/value entries."]
        )
    return result


def _resolve_monetary_policy(model: dict) -> dict:
    """Resolve model.monetary policy and load referenced conversion tables."""
    raw = model.get("monetary") or {}
    if not raw:
        return {"enabled": False}

    canonical = raw.get("canonical")
    if not isinstance(canonical, str):
        raise SemanticValidationError(
            ["model.monetary.canonical is required when model.monetary is set."]
        )

    canon_scale, canon_currency, canon_year = _parse_monetary_token(
        canonical,
        field_path="model.monetary.canonical",
    )

    fx_rows: dict[int, dict[str, float]] = {}
    fx_table = raw.get("fx_table")
    if fx_table is not None:
        fx_rows = _load_fx_table(Path(fx_table))

    cpi_series: dict[str, dict[int, float]] = {}
    for currency, path in (raw.get("cpi_tables") or {}).items():
        if currency not in SUPPORTED_MONETARY_CURRENCIES:
            allowed = ", ".join(sorted(SUPPORTED_MONETARY_CURRENCIES))
            raise SemanticValidationError(
                [
                    f"model.monetary.cpi_tables uses unsupported currency "
                    f"'{currency}'. Supported currencies: {allowed}."
                ]
            )
        cpi_series[currency] = _load_cpi_table(Path(path))

    return {
        "enabled": True,
        "canonical_token": canonical,
        "canonical_scale": canon_scale,
        "canonical_scale_factor": MONETARY_SCALE_FACTORS[canon_scale],
        "canonical_currency": canon_currency,
        "canonical_year": canon_year,
        "fx_rates": fx_rows,
        "cpi_series": cpi_series,
    }


def _fx_conversion_factor(
    *,
    src_currency: str,
    dst_currency: str,
    year: int,
    fx_rates: dict[int, dict[str, float]],
) -> float:
    """Return multiplicative FX factor to convert src->dst for given year."""
    if src_currency == dst_currency:
        return 1.0
    if year not in fx_rates:
        raise SemanticValidationError(
            [f"Missing FX data for year {year} for {src_currency}->{dst_currency}."]
        )
    row = fx_rates[year]
    if src_currency == "USD" and dst_currency == "AUD":
        return row["aud_per_usd"]
    if src_currency == "AUD" and dst_currency == "USD":
        return row["usd_per_aud"]
    raise SemanticValidationError(
        [
            "Unsupported FX conversion pair "
            f"{src_currency}->{dst_currency}. Only AUD<->USD is configured."
        ]
    )


def _inflate_by_cpi(
    *,
    amount: float,
    currency: str,
    src_year: int,
    dst_year: int,
    cpi_series: dict[str, dict[int, float]],
    field_path: str,
) -> float:
    """Inflate amount in same currency from src_year to dst_year using CPI index."""
    if src_year == dst_year:
        return amount
    series = cpi_series.get(currency)
    if not series:
        raise SemanticValidationError(
            [
                f"{field_path} requires CPI for {currency} to convert "
                f"{src_year}->{dst_year}, but model.monetary.cpi_tables.{currency} "
                "is not configured."
            ]
        )
    if src_year not in series or dst_year not in series:
        raise SemanticValidationError(
            [
                f"{field_path} requires CPI entries for {currency} years "
                f"{src_year} and {dst_year}."
            ]
        )
    return amount * (series[dst_year] / series[src_year])


def _parse_cost_rate_literal(
    literal: str,
    *,
    field_path: str,
    expected_denominator: str,
    require_per_year: bool,
) -> tuple[float, str, str, int]:
    """Parse '<value> MUSD23/PJ' style literal and validate denominator semantics."""
    match = COST_RATE_LITERAL_RE.match(literal)
    if not match:
        raise SemanticValidationError(
            [
                f"{field_path} must use '<value> <moneyYY>/<unit>' format "
                f"(e.g., '15 MUSD23/PJ'), got '{literal}'."
            ]
        )

    value_token, scale, currency, year_token, denominator, per_year = match.groups()
    value = float(value_token)
    if value < 0:
        raise SemanticValidationError(
            [f"{field_path} must be non-negative, got {value}."]
        )
    if currency not in SUPPORTED_MONETARY_CURRENCIES:
        allowed = ", ".join(sorted(SUPPORTED_MONETARY_CURRENCIES))
        raise SemanticValidationError(
            [
                f"{field_path} uses unsupported currency '{currency}'. "
                f"Supported currencies: {allowed}."
            ]
        )
    if denominator != expected_denominator:
        raise SemanticValidationError(
            [
                f"{field_path} denominator must be '{expected_denominator}' "
                f"to match process units, got '{denominator}'."
            ]
        )

    has_per_year = per_year == "yr"
    if require_per_year and not has_per_year:
        raise SemanticValidationError(
            [f"{field_path} must include '/yr' for fixed O&M cost basis."]
        )
    if (not require_per_year) and has_per_year:
        raise SemanticValidationError(
            [f"{field_path} must not include '/yr'."]
        )

    return value, scale, currency, _parse_money_year(year_token)


def _normalize_rate_to_canonical(
    *,
    value: float,
    scale: str,
    currency: str,
    year: int,
    policy: dict,
    field_path: str,
) -> float:
    """Normalize one monetary rate to model canonical currency-year-scale."""
    amount = value * MONETARY_SCALE_FACTORS[scale]
    amount = _inflate_by_cpi(
        amount=amount,
        currency=currency,
        src_year=year,
        dst_year=policy["canonical_year"],
        cpi_series=policy["cpi_series"],
        field_path=field_path,
    )
    fx = _fx_conversion_factor(
        src_currency=currency,
        dst_currency=policy["canonical_currency"],
        year=policy["canonical_year"],
        fx_rates=policy["fx_rates"],
    )
    canonical_amount = amount * fx
    return canonical_amount / policy["canonical_scale_factor"]


def _normalize_cost_value(
    *,
    raw_value,
    field_path: str,
    expected_denominator: str,
    require_per_year: bool,
    policy: dict,
):
    """Normalize scalar or time-varying cost values to canonical coefficients."""
    if _is_time_varying(raw_value):
        sparse = raw_value.get("values", {})
        normalized_values: dict[str, float] = {}
        for year, literal in sparse.items():
            if not isinstance(literal, str):
                raise SemanticValidationError(
                    [
                        f"{field_path}.values['{year}'] must be a string literal "
                        "like '15 MUSD23/PJ'."
                    ]
                )
            value, scale, currency, money_year = _parse_cost_rate_literal(
                literal,
                field_path=f"{field_path}.values['{year}']",
                expected_denominator=expected_denominator,
                require_per_year=require_per_year,
            )
            normalized_values[str(year)] = _normalize_rate_to_canonical(
                value=value,
                scale=scale,
                currency=currency,
                year=money_year,
                policy=policy,
                field_path=f"{field_path}.values['{year}']",
            )
        normalized = deepcopy(raw_value)
        normalized["values"] = normalized_values
        return normalized

    if not isinstance(raw_value, str):
        raise SemanticValidationError(
            [
                f"{field_path} must be explicit cost literal string "
                "(e.g., '15 MUSD23/PJ')."
            ]
        )

    value, scale, currency, money_year = _parse_cost_rate_literal(
        raw_value,
        field_path=field_path,
        expected_denominator=expected_denominator,
        require_per_year=require_per_year,
    )
    return _normalize_rate_to_canonical(
        value=value,
        scale=scale,
        currency=currency,
        year=money_year,
        policy=policy,
        field_path=field_path,
    )


def _model_output_currency(model: dict) -> str:
    """Get output currency code for ~CURRENCIES and G_DRATE rows."""
    policy = _resolve_monetary_policy(model)
    if policy.get("enabled"):
        return policy["canonical_currency"]
    return "USD"


def _normalize_new_syntax_monetary_costs(source: dict) -> tuple[dict, dict]:
    """Normalize new-syntax process and case cost fields to canonical currency-year."""
    normalized = deepcopy(source)
    model = normalized.get("model", {})
    policy = _resolve_monetary_policy(model)
    if not policy.get("enabled"):
        return normalized, policy

    roles_by_id = {
        r.get("id"): r for r in (normalized.get("process_roles") or []) if r.get("id")
    }
    variants = normalized.get("process_variants") or []
    units_by_variant: dict[str, tuple[str, str]] = {}
    for variant in variants:
        variant_id = variant.get("id", "<variant>")
        role_id = variant.get("role")
        role = roles_by_id.get(role_id, {})
        activity_unit = role.get("activity_unit")
        capacity_unit = role.get("capacity_unit")
        if not activity_unit or not capacity_unit:
            raise SemanticValidationError(
                [
                    f"process_roles[{role_id}] must declare both activity_unit and "
                    "capacity_unit when model.monetary is used."
                ]
            )
        units_by_variant[variant_id] = (activity_unit, capacity_unit)

        cost_specs = (
            ("variable_om_cost", activity_unit, False),
            ("investment_cost", capacity_unit, False),
            ("fixed_om_cost", capacity_unit, True),
        )
        for field_name, denominator, require_per_year in cost_specs:
            if field_name not in variant:
                continue
            variant[field_name] = _normalize_cost_value(
                raw_value=variant[field_name],
                field_path=f"process_variants[{variant_id}].{field_name}",
                expected_denominator=denominator,
                require_per_year=require_per_year,
                policy=policy,
            )

    for case in model.get("cases", []) or []:
        case_name = case.get("name", "<case>")
        for idx, override in enumerate(case.get("variant_overrides", []) or []):
            variant_id = override.get("variant")
            if variant_id not in units_by_variant:
                continue
            activity_unit, capacity_unit = units_by_variant[variant_id]
            cost_specs = (
                ("variable_om_cost", activity_unit, False),
                ("investment_cost", capacity_unit, False),
                ("fixed_om_cost", capacity_unit, True),
            )
            for field_name, denominator, require_per_year in cost_specs:
                if field_name not in override:
                    continue
                override[field_name] = _normalize_cost_value(
                    raw_value=override[field_name],
                    field_path=(
                        "model.cases["
                        f"{case_name}].variant_overrides[{idx}].{field_name}"
                    ),
                    expected_denominator=denominator,
                    require_per_year=require_per_year,
                    policy=policy,
                )

    return normalized, policy


def _compute_cap2act(capacity_unit: str, activity_unit: str) -> float | None:
    """Compute PRC_CAPACT for a (capacity_unit, activity_unit) pair."""
    capacity_expr = _to_pint_unit_expression(capacity_unit)
    activity_expr = _to_pint_unit_expression(activity_unit)
    if capacity_expr is None or activity_expr is None:
        return None
    try:
        ureg = _unit_registry()
        cap_unit = ureg.parse_units(capacity_expr)
        act_unit = ureg.parse_units(activity_expr)
        converted = (1 * cap_unit * ureg.parse_units(MODEL_TIME_BASIS)).to(act_unit)
    except (UndefinedUnitError, DimensionalityError):
        return None
    return round(float(converted.magnitude), 12)


def _record_unit_diagnostic(
    errors: list[str],
    warnings: list[str],
    policy: dict,
    message: str,
) -> None:
    """Record as error in strict mode, warning otherwise."""
    if _is_strict_unit_mode(policy):
        errors.append(message)
    else:
        warnings.append(message)


def _detect_fake_unit_transform_process(
    *,
    inputs: list[str],
    outputs: list[str],
    attrs: dict,
    kind: str | None = None,
) -> bool:
    """Detect suspicious pass-through process likely used only for unit scaling."""
    if len(inputs) != 1 or len(outputs) != 1:
        return False
    if inputs[0] != outputs[0]:
        return False
    if kind == "network":
        return False

    efficiency = attrs.get("efficiency")
    if efficiency is not None and efficiency != 1.0:
        return False

    # Treat any additional technical/economic attribute as physical intent.
    nontrivial_keys = {
        "investment_cost",
        "fixed_om_cost",
        "variable_om_cost",
        "lifetime",
        "stock",
        "existing_capacity",
        "cap_bound",
        "ncap_bound",
        "activity_bound",
        "emission_factors",
    }
    if any(k in attrs for k in nontrivial_keys):
        return False
    return True


def _validate_process_unit_pair(
    *,
    process_label: str,
    activity_unit: str,
    capacity_unit: str,
    policy: dict,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate explicit process activity/capacity unit semantics."""
    parsed_activity = _parse_process_unit_expression(activity_unit)
    if parsed_activity is None:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has unsupported activity_unit '{activity_unit}'. "
                "Use '<unit>' with an allowed energy/service/mass base."
            ),
        )
        return

    activity_valid_for_pair = True
    activity_base, activity_denominator = parsed_activity
    activity_dimension = UNIT_DIMENSIONS.get(activity_base)
    if activity_dimension not in {"energy", "service", "mass"}:
        activity_valid_for_pair = False
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has unsupported activity_unit '{activity_unit}'. "
                "Activity must use an energy, service, or mass base unit."
            ),
        )
    elif activity_base not in policy["allowed_units"][activity_dimension]:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} uses activity_unit '{activity_unit}' which is not "
                "allowed by model.unit_policy.allowed_units."
            ),
        )
    if activity_denominator is not None:
        activity_valid_for_pair = False
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} uses activity_unit '{activity_unit}' "
                "with denominator "
                f"'{activity_denominator}'. Activity must be an annual extensive unit "
                "(no '/yr')."
            ),
        )

    parsed_capacity = _parse_process_unit_expression(capacity_unit)
    if parsed_capacity is None:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has unsupported capacity_unit '{capacity_unit}'. "
                "Use a power unit (e.g., GW) or explicit annual rate '<unit>/yr'."
            ),
        )
        return

    capacity_valid_for_pair = True
    capacity_base, capacity_denominator = parsed_capacity
    capacity_dimension = UNIT_DIMENSIONS.get(capacity_base)
    if capacity_dimension not in {"power", "energy", "service", "mass"}:
        capacity_valid_for_pair = False
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has unsupported capacity_unit '{capacity_unit}'. "
                "Capacity must use a power base unit or annual rate "
                "of energy/service/mass."
            ),
        )
    elif capacity_base not in policy["allowed_units"][capacity_dimension]:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} uses capacity_unit '{capacity_unit}' which is not "
                "allowed by model.unit_policy.allowed_units."
            ),
        )

    if capacity_dimension == "power":
        if capacity_denominator is not None:
            capacity_valid_for_pair = False
            _record_unit_diagnostic(
                errors,
                warnings,
                policy,
                (
                    f"{process_label} uses capacity_unit '{capacity_unit}'. Power "
                    "capacity should not include a denominator (use GW/MW/TW/kW)."
                ),
            )
    elif capacity_dimension in {"energy", "service", "mass"}:
        if capacity_denominator is None:
            capacity_valid_for_pair = False
            _record_unit_diagnostic(
                errors,
                warnings,
                policy,
                (
                    f"{process_label} uses capacity_unit '{capacity_unit}' without "
                    "explicit time basis. Use '<unit>/yr' for non-power capacities."
                ),
            )
        elif capacity_denominator not in SUPPORTED_RATE_DENOMINATORS:
            allowed = ", ".join(sorted(SUPPORTED_RATE_DENOMINATORS))
            capacity_valid_for_pair = False
            _record_unit_diagnostic(
                errors,
                warnings,
                policy,
                (
                    f"{process_label} uses capacity_unit '{capacity_unit}' with "
                    f"unsupported denominator '{capacity_denominator}'. "
                    f"Supported rate denominators: {allowed}."
                ),
            )

    if not activity_valid_for_pair or not capacity_valid_for_pair:
        return

    cap2act = _compute_cap2act(capacity_unit, activity_unit)
    if cap2act is None:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has incompatible capacity/activity unit pair "
                f"({capacity_unit}, {activity_unit}); cannot derive PRC_CAPACT "
                f"using a 1-{next(iter(SUPPORTED_RATE_DENOMINATORS))} basis."
            ),
        )


def _validate_efficiency_metric(
    *,
    process_label: str,
    efficiency_value,
    performance_metric: str,
    policy: dict,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate efficiency value against declared performance metric."""
    if _is_time_varying(efficiency_value):
        return
    if not isinstance(efficiency_value, (int, float)):
        return
    if efficiency_value <= 0:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            f"{process_label} has non-positive efficiency value {efficiency_value}.",
        )
        return

    if performance_metric == "cop":
        return

    if efficiency_value > 1:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has efficiency={efficiency_value} > 1. "
                "Use performance_metric='cop' for heat-pump/COP-style components."
            ),
        )


def _validate_flow_coefficient_anchors(
    *,
    process_label: str,
    inputs: list[dict],
    outputs: list[dict],
    efficiency_value,
    performance_metric: str,
    commodities: dict[str, dict],
    policy: dict,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Check flow coefficient anchors against efficiency and unit conversions.

    Coefficients are validation-only anchors (commodity_unit/activity_unit).
    This check currently supports standard converter cases in the energy domain.
    """
    if performance_metric == "cop":
        return
    if _is_time_varying(efficiency_value):
        return
    if not isinstance(efficiency_value, (int, float)) or efficiency_value <= 0:
        return

    def flow_unit(flow: dict) -> str | None:
        comm = flow.get("commodity")
        if not comm:
            return None
        comm_info = commodities.get(comm)
        if not comm_info:
            return None
        comm_type = comm_info.get("type", "energy")
        return comm_info.get("unit") or _get_default_unit(comm_type)

    def is_energy_flow(flow: dict) -> bool:
        unit = flow_unit(flow)
        return unit in ENERGY_UNIT_TO_PJ

    def coeff(flow: dict) -> float | None:
        val = flow.get("coefficient")
        if val is None:
            return None
        if not isinstance(val, (int, float)) or val <= 0:
            _record_unit_diagnostic(
                errors,
                warnings,
                policy,
                (
                    f"{process_label} flow coefficient for commodity "
                    f"'{flow.get('commodity')}' must be > 0."
                ),
            )
            return None
        return float(val)

    any_coeff = any("coefficient" in f for f in inputs + outputs)
    if not any_coeff:
        return

    energy_inputs = [f for f in inputs if is_energy_flow(f)]
    energy_outputs = [f for f in outputs if is_energy_flow(f)]
    if not energy_inputs or not energy_outputs:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} defines coefficient anchors but no energy-domain "
                "input/output pair was found for anchor checks."
            ),
        )
        return

    explicit_output = [f for f in energy_outputs if f.get("coefficient") is not None]
    if len(explicit_output) > 1:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has multiple output coefficient anchors; "
                "anchor check expects a single anchored output."
            ),
        )
        return
    if explicit_output:
        output_anchor = explicit_output[0]
        output_coeff = coeff(output_anchor)
    elif len(energy_outputs) == 1:
        output_anchor = energy_outputs[0]
        output_coeff = 1.0
    else:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has no unique output anchor coefficient "
                "(set one output coefficient explicitly)."
            ),
        )
        return
    if output_coeff is None:
        return

    out_unit = flow_unit(output_anchor)
    assert out_unit is not None  # guarded by energy_outputs
    out_pj = ENERGY_UNIT_TO_PJ[out_unit]

    single_energy_input = len(energy_inputs) == 1
    tolerance = 0.02  # 2%
    checked = 0

    for inp in energy_inputs:
        observed = coeff(inp)
        if observed is None:
            if single_energy_input:
                observed = 1.0
            else:
                continue

        in_unit = flow_unit(inp)
        assert in_unit is not None  # guarded by energy_inputs
        in_pj = ENERGY_UNIT_TO_PJ[in_unit]
        expected = output_coeff * out_pj / (efficiency_value * in_pj)
        if expected <= 0:
            continue
        rel_err = abs(observed - expected) / expected
        if rel_err > tolerance:
            inversion_expected = output_coeff * out_pj * efficiency_value / in_pj
            inversion_hint = ""
            if inversion_expected > 0:
                inv_rel_err = abs(observed - inversion_expected) / inversion_expected
                if inv_rel_err <= tolerance:
                    inversion_hint = " Possible efficiency inversion detected."
            _record_unit_diagnostic(
                errors,
                warnings,
                policy,
                (
                    f"{process_label} coefficient mismatch for input "
                    f"'{inp.get('commodity')}': expected ~{expected:.6g} "
                    f"{in_unit}/{out_unit}_act from efficiency={efficiency_value}, "
                    f"got {observed:.6g}.{inversion_hint}"
                ),
            )
        checked += 1

    if checked == 0:
        _record_unit_diagnostic(
            errors,
            warnings,
            policy,
            (
                f"{process_label} has coefficient anchors but no checkable "
                "input anchor "
                "(set one input coefficient explicitly for multi-input processes)."
            ),
        )


def _get_scalar_value(value):
    """Get scalar value from scalar or time-varying spec (returns None for latter)."""
    if _is_time_varying(value):
        # Return None - caller should use _expand_time_varying_rows instead
        return None
    return value


def _expand_time_varying_attr(
    attr_name: str,
    value,
    base_row: dict,
) -> list[dict]:
    """
    Expand a time-varying attribute into multiple rows with YEAR column.

    Args:
        attr_name: The attribute name (e.g., 'invcost', 'efficiency')
        value: Either a scalar or a time-varying spec with 'values' dict
        base_row: Base row dict to copy for each year (region, techname, etc.)

    Returns:
        List of row dicts, one per year (or single row for scalar values)
    """
    column = ATTR_TO_COLUMN.get(attr_name, attr_name)

    if not _is_time_varying(value):
        # Scalar value - return single row
        row = base_row.copy()
        row[column] = value
        return [row]

    # Time-varying value - expand to multiple rows
    rows = []
    values = value["values"]
    interpolation = value.get("interpolation", "interp_extrap")
    interp_code = INTERPOLATION_CODES.get(interpolation, 3)

    # First, emit a year=0 row with interpolation code if not 'none'
    if interp_code != -1:
        interp_row = base_row.copy()
        interp_row["year"] = 0
        interp_row[column] = interp_code
        rows.append(interp_row)

    # Emit one row per year
    for year_str, val in sorted(values.items()):
        row = base_row.copy()
        row["year"] = int(year_str)
        row[column] = val
        rows.append(row)

    return rows


def _expand_scalar_to_all_years(
    attr_name: str,
    scalar_value: float | int,
    base_row: dict,
    milestone_years: list[int],
) -> list[dict]:
    """
    Expand a scalar attribute value to explicit rows for all milestone years.

    VedaLang design principle: Never rely on TIMES implicit interpolation.
    This function ensures scalar values are emitted explicitly for every year.

    Args:
        attr_name: The VedaLang attribute name (e.g., 'efficiency', 'stock')
        scalar_value: The scalar value to expand
        base_row: Base row dict to copy for each year
        milestone_years: List of model milestone years

    Returns:
        List of row dicts, one per milestone year
    """
    column = ATTR_TO_COLUMN.get(attr_name, attr_name)
    rows = []

    for year in milestone_years:
        row = base_row.copy()
        row["year"] = year
        row[column] = scalar_value
        rows.append(row)

    return rows


def _expand_attr_to_all_years(
    attr_name: str,
    value,
    base_row: dict,
    milestone_years: list[int],
    force_expand: bool = False,
) -> list[dict]:
    """
    Expand an attribute value to rows for all milestone years.

    For time-varying specs: uses interpolation to expand sparse values.
    For scalar values: expands to all years if force_expand is True.

    This is the preferred function for attributes that should always have
    explicit year-indexed values (as per VedaLang design principles).

    Args:
        attr_name: The VedaLang attribute name (e.g., 'efficiency', 'stock')
        value: Either a scalar or a time-varying spec with 'values' dict
        base_row: Base row dict to copy for each year
        milestone_years: List of model milestone years
        force_expand: If True, expand scalar values to all years

    Returns:
        List of row dicts, one per milestone year
    """
    if _is_time_varying(value):
        # Time-varying: use interpolation to fill all years
        sparse_values = value.get("values", {})
        interpolation = value.get("interpolation", "interp_extrap")
        dense_values = _expand_series_to_years(
            sparse_values, milestone_years, interpolation
        )

        column = ATTR_TO_COLUMN.get(attr_name, attr_name)
        rows = []
        for year, val in sorted(dense_values.items()):
            row = base_row.copy()
            row["year"] = year
            row[column] = val
            rows.append(row)
        return rows

    # Scalar value
    if force_expand:
        return _expand_scalar_to_all_years(
            attr_name, value, base_row, milestone_years
        )
    else:
        # Just return single row without year (legacy behavior)
        column = ATTR_TO_COLUMN.get(attr_name, attr_name)
        row = base_row.copy()
        row[column] = value
        return [row]


def _validate_attribute_for_emission(attr_name: str, tag_name: str) -> None:
    """
    Validate attribute can be emitted in the given tag.

    Args:
        attr_name: VedaLang semantic name (e.g., 'efficiency') or TIMES name
        tag_name: VEDA tag name without ~ prefix (e.g., 'FI_T', 'TFM_INS')

    Raises:
        VedaLangError: If attribute is unsupported or incompatible with tag
    """
    registry = get_registry()

    times_name = SEMANTIC_TO_TIMES.get(attr_name, attr_name.upper())

    if not registry.is_attribute_supported(times_name):
        unsupported = registry.get_unsupported_info(times_name)
        if unsupported:
            msg = f"Attribute '{attr_name}' is not supported by VedaLang. "
            msg += unsupported.reason
            if unsupported.suggested_alternative:
                msg += f" Use '{unsupported.suggested_alternative}' instead."
            raise VedaLangError(msg)
        else:
            msg = f"Attribute '{attr_name}' is not supported by VedaLang."
            raise VedaLangError(msg)

    # Skip tag compatibility for TFM_ tags (transformation tags are flexible)
    # TFM_DINS-AT, TFM_INS etc. inherit valid_fields from base_tag which
    # the registry doesn't resolve. The attribute support check is sufficient.
    if tag_name.upper().startswith("TFM_"):
        return

    if not registry.is_attribute_compatible_with_tag(times_name, tag_name):
        raise VedaLangError(
            f"Attribute '{attr_name}' cannot be set in tag '~{tag_name.upper()}'. "
            f"Required columns are not available in this tag."
        )


class SemanticValidationError(Exception):
    """Raised when semantic validation fails."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} semantic error(s):")
            for e in self.errors:
                parts.append(f"  - {e}")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s):")
            for w in self.warnings:
                parts.append(f"  - {w}")
        return "\n".join(parts)


def validate_cross_references(
    model: dict, source: dict | None = None,
) -> tuple[list[str], list[str]]:
    """
    Validate semantic cross-references in the model.

    Checks that all referenced commodities, processes, and regions exist,
    and that scenario types target appropriate commodity types.

    Args:
        model: The model dictionary from VedaLang source
        source: Optional full source dict (for P4 syntax with process_variants)

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    unit_policy = _resolve_unit_policy(model)

    # Build lookup sets - support both new syntax ('id') and old syntax ('name')
    commodities = {}
    for i, c in enumerate(model.get("commodities", [])):
        comm_id = c.get("id") or c.get("name")
        if comm_id:
            namespace, _ = _split_namespace(comm_id)
            if namespace is not None and not _is_legacy_namespace(namespace):
                actual_type = c.get("type")
                if namespace not in VALID_COMMODITY_NAMESPACES:
                    errors.append(
                        f"Commodity '{comm_id}' in model.commodities[{i}] uses unknown "
                        f"namespace '{namespace}'."
                    )
                else:
                    expected_types = NAMESPACE_TO_TYPES.get(namespace)
                    if expected_types is None:
                        errors.append(
                            "Commodity "
                            f"'{comm_id}' uses namespace '{namespace}' but no "
                            "compiler type mapping is defined for it."
                        )
                    elif actual_type not in expected_types:
                        errors.append(
                            f"Commodity '{comm_id}' namespace '{namespace}' "
                            f"implies type in {sorted(expected_types)} but "
                            f"commodity type is '{actual_type}'."
                        )
            _warn_ambiguous_commodity_ref(
                warnings, f"model.commodities[{i}]", comm_id
            )
            comm_type = c.get("type", "energy")
            comm_unit = c.get("unit") or _get_default_unit(comm_type)
            comm_dimension = UNIT_DIMENSIONS.get(comm_unit)
            if comm_dimension is None:
                _record_unit_diagnostic(
                    errors,
                    warnings,
                    unit_policy,
                    (
                        f"Commodity '{comm_id}' has unsupported unit '{comm_unit}'. "
                        "Use a unit from the schema enum."
                    ),
                )
            else:
                allowed_units = unit_policy["allowed_units"].get(comm_dimension, set())
                if comm_unit not in allowed_units:
                    _record_unit_diagnostic(
                        errors,
                        warnings,
                        unit_policy,
                        (
                            f"Commodity '{comm_id}' uses unit '{comm_unit}' which is "
                            "not allowed by model.unit_policy.allowed_units."
                        ),
                    )
            comm_basis = c.get("basis")
            if comm_basis is not None and comm_basis not in ENERGY_BASES:
                _record_unit_diagnostic(
                    errors,
                    warnings,
                    unit_policy,
                    (
                        f"Commodity '{comm_id}' has invalid basis '{comm_basis}'. "
                        "Expected one of: HHV, LHV."
                    ),
                )
            if _is_strict_unit_mode(unit_policy):
                for issue in _combustion_metadata_issues(comm_id, c):
                    errors.append(issue)
            commodities[comm_id] = c
    commodity_names = set(commodities.keys())
    processes = set()
    for p in model.get("processes", []):
        proc_name = p.get("name") or p.get("id")
        if proc_name:
            processes.add(proc_name)
    # P4 syntax: include process_variants from top-level source
    if source:
        for v in source.get("process_variants", []):
            variant_id = v.get("id")
            if variant_id:
                processes.add(variant_id)
    regions = set(model.get("regions", []))

    def suggest_commodity(name: str) -> str:
        matches = get_close_matches(name, commodity_names, n=1, cutoff=0.6)
        if matches:
            return f" Did you mean '{matches[0]}'?"
        return ""

    def suggest_process(name: str) -> str:
        matches = get_close_matches(name, processes, n=1, cutoff=0.6)
        if matches:
            return f" Did you mean '{matches[0]}'?"
        return ""

    def suggest_region(name: str) -> str:
        matches = get_close_matches(name, regions, n=1, cutoff=0.6)
        if matches:
            return f" Did you mean '{matches[0]}'?"
        return ""

    def check_energy_mass_basis(flow_comms: list[str], process_label: str) -> None:
        # Only enforce basis consistency when crossing between energy and mass domains.
        units_by_comm: dict[str, str] = {}
        dims: set[str] = set()
        for comm in set(flow_comms):
            comm_info = commodities.get(comm)
            if not comm_info:
                continue
            comm_type = comm_info.get("type", "energy")
            unit = comm_info.get("unit") or _get_default_unit(comm_type)
            dimension = UNIT_DIMENSIONS.get(unit)
            units_by_comm[comm] = unit
            if dimension in {"energy", "mass"}:
                dims.add(dimension)
        if not {"energy", "mass"}.issubset(dims):
            return

        policy_basis = unit_policy.get("energy_basis")
        for comm, unit in sorted(units_by_comm.items()):
            dimension = UNIT_DIMENSIONS.get(unit)
            if dimension not in {"energy", "mass"}:
                continue
            comm_basis = commodities.get(comm, {}).get("basis")
            if not comm_basis:
                _record_unit_diagnostic(
                    errors,
                    warnings,
                    unit_policy,
                    (
                        f"{process_label} crosses energy<->mass units but commodity "
                        f"'{comm}' (unit '{unit}') has no basis. Add basis: HHV/LHV."
                    ),
                )
                continue
            if policy_basis and comm_basis != policy_basis:
                _record_unit_diagnostic(
                    errors,
                    warnings,
                    unit_policy,
                    (
                        f"{process_label} uses commodity '{comm}' with basis "
                        f"'{comm_basis}', which conflicts with model.unit_policy "
                        f"energy_basis '{policy_basis}'."
                    ),
                )

    # Validate process references (only for legacy processes array)
    for raw_process in model.get("processes", []):
        # Normalize shorthand syntax before validation
        process = _normalize_process_flows(raw_process)
        proc_name = process.get("name") or process.get("id", "unknown")

        # Check input commodity references
        for i, inp in enumerate(process.get("inputs", [])):
            comm = inp["commodity"]
            _warn_ambiguous_commodity_ref(
                warnings,
                f"process '{proc_name}' inputs[{i}]",
                comm,
            )
            if _is_emission_namespace_ref(comm):
                errors.append(
                    f"L1 violation in process '{proc_name}' inputs[{i}]: emission:* "
                    "commodities must not appear in flow topology."
                )
            if comm not in commodity_names:
                hint = suggest_commodity(comm)
                errors.append(
                    f"Unknown commodity '{comm}' in process "
                    f"'{proc_name}' inputs[{i}].{hint}"
                )

        # Check output commodity references
        for i, out in enumerate(process.get("outputs", [])):
            comm = out["commodity"]
            _warn_ambiguous_commodity_ref(
                warnings,
                f"process '{proc_name}' outputs[{i}]",
                comm,
            )
            if _is_emission_namespace_ref(comm):
                errors.append(
                    f"L1/L4 violation in process '{proc_name}' outputs[{i}]: "
                    "emission:* "
                    "commodities must not appear in flow topology."
                )
            if comm not in commodity_names:
                hint = suggest_commodity(comm)
                errors.append(
                    f"Unknown commodity '{comm}' in process "
                    f"'{proc_name}' outputs[{i}].{hint}"
                )

        activity_unit = process.get("activity_unit", "PJ")
        capacity_unit = process.get("capacity_unit", "GW")
        performance_metric = process.get("performance_metric", "efficiency")
        _validate_process_unit_pair(
            process_label=f"Process '{proc_name}'",
            activity_unit=activity_unit,
            capacity_unit=capacity_unit,
            policy=unit_policy,
            errors=errors,
            warnings=warnings,
        )
        has_flow_anchors = any(
            "coefficient" in flow
            for flow in (process.get("inputs", []) + process.get("outputs", []))
        )
        if "efficiency" in process:
            _validate_efficiency_metric(
                process_label=f"Process '{proc_name}'",
                efficiency_value=process.get("efficiency"),
                performance_metric=performance_metric,
                policy=unit_policy,
                errors=errors,
                warnings=warnings,
            )
        if has_flow_anchors:
            if "efficiency" not in process:
                _record_unit_diagnostic(
                    errors,
                    warnings,
                    unit_policy,
                    (
                        f"Process '{proc_name}' defines coefficient anchors but has no "
                        "efficiency value; cannot run anchor magnitude checks."
                    ),
                )
            else:
                _validate_flow_coefficient_anchors(
                    process_label=f"Process '{proc_name}'",
                    inputs=process.get("inputs", []),
                    outputs=process.get("outputs", []),
                    efficiency_value=process.get("efficiency"),
                    performance_metric=performance_metric,
                    commodities=commodities,
                    policy=unit_policy,
                    errors=errors,
                    warnings=warnings,
                )

        all_flow_commodities = [
            inp["commodity"] for inp in process.get("inputs", [])
        ] + [
            out["commodity"] for out in process.get("outputs", [])
        ]
        check_energy_mass_basis(all_flow_commodities, f"Process '{proc_name}'")

        if (
            unit_policy.get("forbid_unit_transform_processes", False)
            and _detect_fake_unit_transform_process(
                inputs=[inp["commodity"] for inp in process.get("inputs", [])],
                outputs=[out["commodity"] for out in process.get("outputs", [])],
                attrs=process,
            )
        ):
            errors.append(
                f"Process '{proc_name}' appears to be a unit-only transformation "
                "pass-through (same commodity in/out without physical conversion)."
            )

    # Validate constraint references
    for constraint in model.get("constraints", []):
        constraint_name = constraint["name"]

        # Check commodity reference
        commodity = constraint.get("commodity")
        if commodity and commodity not in commodity_names:
            hint = suggest_commodity(commodity)
            errors.append(
                f"Unknown commodity '{commodity}' in constraint "
                f"'{constraint_name}'.{hint}"
            )

        # Check process references (for activity_share constraints)
        for proc in constraint.get("processes", []):
            if proc not in processes:
                hint = suggest_process(proc)
                errors.append(
                    f"Unknown process '{proc}' in constraint '{constraint_name}'.{hint}"
                )

    # Validate trade link references
    for i, link in enumerate(model.get("trade_links", [])):
        origin = link["origin"]
        destination = link["destination"]
        commodity = link["commodity"]

        if origin not in regions:
            hint = suggest_region(origin)
            errors.append(
                f"Unknown region '{origin}' in trade_links[{i}] origin.{hint}"
            )

        if destination not in regions:
            hint = suggest_region(destination)
            errors.append(
                f"Unknown region '{destination}' in trade_links[{i}] destination.{hint}"
            )

        if commodity not in commodity_names:
            hint = suggest_commodity(commodity)
            errors.append(
                f"Unknown commodity '{commodity}' in trade_links[{i}].{hint}"
            )

    # Validate scenario references
    for scenario in model.get("scenarios", []):
        scenario_name = scenario["name"]
        scenario_type = scenario.get("type")
        commodity = scenario.get("commodity")

        if commodity:
            _warn_ambiguous_commodity_ref(
                warnings,
                f"scenario '{scenario_name}'",
                commodity,
            )
            if commodity not in commodity_names:
                hint = suggest_commodity(commodity)
                errors.append(
                    f"Unknown commodity '{commodity}' in scenario "
                    f"'{scenario_name}'.{hint}"
                )
            else:
                # Check commodity kind matches scenario type
                # New naming convention uses 'kind': TRADABLE/SERVICE/EMISSION
                comm_info = commodities[commodity]
                comm_type = comm_info.get("type", "energy")

                if scenario_type == "demand_projection":
                    # demand_projection targets service commodities
                    if comm_type != "service":
                        errors.append(
                            f"demand_projection scenario '{scenario_name}' targets "
                            f"commodity '{commodity}' (type '{comm_type}'), "
                            "expected 'service'"
                        )

                elif scenario_type == "commodity_price":
                    # commodity_price targets non-service commodities
                    if comm_type == "service":
                        errors.append(
                            f"commodity_price scenario '{scenario_name}' targets "
                            f"commodity '{commodity}' (type 'service'), "
                            "expected non-service type"
                        )

    # Validate case overlay references and conflict-prone selectors
    case_names_seen: set[str] = set()
    baseline_cases: list[str] = []
    constraints_by_name = {c["name"] for c in model.get("constraints", [])}
    scenario_param_names = {
        p["name"] for p in model.get("scenario_parameters", []) if "name" in p
    }
    for scenario in model.get("scenarios", []):
        if "name" in scenario:
            scenario_param_names.add(scenario["name"])

    for case in model.get("cases", []):
        case_name = case["name"]
        if case_name in case_names_seen:
            errors.append(f"Duplicate case name '{case_name}'")
        case_names_seen.add(case_name)

        if case.get("is_baseline"):
            baseline_cases.append(case_name)

        includes = set(case.get("includes", []))
        excludes = set(case.get("excludes", []))
        overlap = sorted(includes.intersection(excludes))
        if overlap:
            errors.append(
                f"Case '{case_name}' has names in both includes and excludes:"
                f" {', '.join(overlap)}"
            )

        unknown_includes = sorted(
            name
            for name in includes
            if name not in scenario_param_names and name not in constraints_by_name
        )
        if unknown_includes:
            errors.append(
                f"Case '{case_name}' includes unknown names:"
                f" {', '.join(unknown_includes)}"
            )

        unknown_excludes = sorted(
            name
            for name in excludes
            if name not in scenario_param_names and name not in constraints_by_name
        )
        if unknown_excludes:
            errors.append(
                f"Case '{case_name}' excludes unknown names:"
                f" {', '.join(unknown_excludes)}"
            )

        demand_selectors_seen: set[tuple[str, str, str]] = set()
        for idx, override in enumerate(case.get("demand_overrides", [])):
            commodity = override["commodity"]
            _warn_ambiguous_commodity_ref(
                warnings,
                f"case '{case_name}' demand_overrides[{idx}]",
                commodity,
            )
            if commodity not in commodity_names:
                hint = suggest_commodity(commodity)
                errors.append(
                    f"Unknown commodity '{commodity}' in case '{case_name}'"
                    f" demand_overrides[{idx}].{hint}"
                )

            region = override.get("region")
            if region and region not in regions:
                hint = suggest_region(region)
                errors.append(
                    f"Unknown region '{region}' in case '{case_name}'"
                    f" demand_overrides[{idx}].{hint}"
                )

            selector = (
                commodity,
                region or "",
                override.get("segment") or override.get("sector") or "",
            )
            if selector in demand_selectors_seen:
                errors.append(
                    f"Case '{case_name}' has duplicate demand_overrides selectors"
                    f" {selector}"
                )
            demand_selectors_seen.add(selector)

        price_commodities_seen: set[str] = set()
        for idx, override in enumerate(case.get("fuel_price_overrides", [])):
            commodity = override["commodity"]
            _warn_ambiguous_commodity_ref(
                warnings,
                f"case '{case_name}' fuel_price_overrides[{idx}]",
                commodity,
            )
            if commodity not in commodity_names:
                hint = suggest_commodity(commodity)
                errors.append(
                    f"Unknown commodity '{commodity}' in case '{case_name}'"
                    f" fuel_price_overrides[{idx}].{hint}"
                )
            if commodity in price_commodities_seen:
                errors.append(
                    f"Case '{case_name}' has duplicate fuel_price_overrides"
                    f" for commodity '{commodity}'"
                )
            price_commodities_seen.add(commodity)

        constraint_override_names: set[str] = set()
        for idx, override in enumerate(case.get("constraint_overrides", [])):
            name = override["name"]
            if name in constraint_override_names:
                errors.append(
                    f"Case '{case_name}' has duplicate constraint_overrides"
                    f" for '{name}'"
                )
            constraint_override_names.add(name)
            if name not in constraints_by_name:
                errors.append(
                    f"Case '{case_name}' constraint_overrides[{idx}] references"
                    f" unknown constraint '{name}'"
                )

        variant_override_names: set[str] = set()
        for override in case.get("variant_overrides", []):
            variant = override["variant"]
            if variant in variant_override_names:
                errors.append(
                    f"Case '{case_name}' has duplicate variant_overrides"
                    f" for variant '{variant}'"
                )
            variant_override_names.add(variant)

    if source:
        role_units = {
            role.get("id"): (
                role.get("activity_unit", "PJ"),
                role.get("capacity_unit", "GW"),
            )
            for role in source.get("process_roles", [])
            if role.get("id")
        }
        for variant in source.get("process_variants", []):
            variant_id = variant.get("id", "<variant>")
            for idx, inp in enumerate(variant.get("inputs") or []):
                comm = inp.get("commodity")
                if not comm:
                    continue
                _warn_ambiguous_commodity_ref(
                    warnings,
                    f"process_variants[{variant_id}].inputs[{idx}]",
                    comm,
                )
                if _is_emission_namespace_ref(comm):
                    errors.append(
                        "L1 violation in process_variants"
                        f"[{variant_id}].inputs[{idx}]: emission:* commodities "
                        "must not appear in inputs/outputs."
                    )

            for idx, out in enumerate(variant.get("outputs") or []):
                comm = out.get("commodity")
                if not comm:
                    continue
                _warn_ambiguous_commodity_ref(
                    warnings,
                    f"process_variants[{variant_id}].outputs[{idx}]",
                    comm,
                )
                if _is_emission_namespace_ref(comm):
                    errors.append(
                        "L1/L4 violation in process_variants"
                        f"[{variant_id}].outputs[{idx}]: emission:* commodities "
                        "must not appear in inputs/outputs."
                    )

            emission_factors = variant.get("emission_factors") or {}
            for em_key in emission_factors:
                if ":" in em_key and not _is_emission_namespace_ref(em_key):
                    errors.append(
                        "L2 violation in process_variants"
                        f"[{variant_id}].emission_factors: key '{em_key}' must "
                        "be namespaced as emission:*."
                    )

            role_id = variant.get("role")
            activity_unit, capacity_unit = role_units.get(role_id, ("PJ", "GW"))
            performance_metric = variant.get("performance_metric", "efficiency")
            _validate_process_unit_pair(
                process_label=f"process_variants[{variant_id}]",
                activity_unit=activity_unit,
                capacity_unit=capacity_unit,
                policy=unit_policy,
                errors=errors,
                warnings=warnings,
            )
            has_flow_anchors = any(
                "coefficient" in flow
                for flow in (variant.get("inputs", []) + variant.get("outputs", []))
            )
            if "efficiency" in variant:
                _validate_efficiency_metric(
                    process_label=f"process_variants[{variant_id}]",
                    efficiency_value=variant.get("efficiency"),
                    performance_metric=performance_metric,
                    policy=unit_policy,
                    errors=errors,
                    warnings=warnings,
                )
            if has_flow_anchors:
                if "efficiency" not in variant:
                    _record_unit_diagnostic(
                        errors,
                        warnings,
                        unit_policy,
                        (
                            "process_variants"
                            f"[{variant_id}] defines coefficient anchors but has no "
                            "efficiency value; cannot run anchor magnitude checks."
                        ),
                    )
                else:
                    _validate_flow_coefficient_anchors(
                        process_label=f"process_variants[{variant_id}]",
                        inputs=variant.get("inputs", []),
                        outputs=variant.get("outputs", []),
                        efficiency_value=variant.get("efficiency"),
                        performance_metric=performance_metric,
                        commodities=commodities,
                        policy=unit_policy,
                        errors=errors,
                        warnings=warnings,
                    )

            variant_flow_commodities = [
                inp["commodity"] for inp in variant.get("inputs", [])
            ] + [
                out["commodity"] for out in variant.get("outputs", [])
            ]
            check_energy_mass_basis(
                variant_flow_commodities,
                f"process_variants[{variant_id}]",
            )

            if (
                unit_policy.get("forbid_unit_transform_processes", False)
                and _detect_fake_unit_transform_process(
                    inputs=[inp["commodity"] for inp in variant.get("inputs", [])],
                    outputs=[out["commodity"] for out in variant.get("outputs", [])],
                    attrs=variant,
                    kind=variant.get("kind"),
                )
            ):
                errors.append(
                    "UNIT_TRANSFORM_PROCESS_FORBIDDEN in process_variants"
                    f"[{variant_id}]: appears to be a unit-only pass-through "
                    "without physical transformation."
                )

    if len(baseline_cases) > 1:
        errors.append(
            "Only one case may be marked is_baseline=true. Found: "
            + ", ".join(sorted(baseline_cases))
        )

    return errors, warnings


def load_vedalang_schema() -> dict:
    """Load the VedaLang JSON schema."""
    with open(SCHEMA_DIR / "vedalang.schema.json") as f:
        return json.load(f)


def load_tableir_schema() -> dict:
    """Load the TableIR JSON schema."""
    with open(SCHEMA_DIR / "tableir.schema.json") as f:
        return json.load(f)


def validate_vedalang(source: dict) -> None:
    """Validate VedaLang source against schema."""
    schema = load_vedalang_schema()
    jsonschema.validate(source, schema)


def _compile_new_syntax(
    source: dict,
    validate: bool = True,
    selected_cases: list[str] | None = None,
) -> dict:
    """
    Compile VedaLang source using new P4 syntax (process_roles/variants/availability).

    This is the new compilation pipeline that uses:
    - process_roles: abstract transformations (topology)
    - process_variants: concrete technologies with parameters
    - availability: where variants exist (region/sector/segment)
    - process_parameters: selector-based parameter overrides
    - demands: service commodity demands

    Args:
        source: VedaLang source dict with new syntax
        validate: Whether to validate output

    Returns:
        TableIR dict
    """
    source, monetary_policy = _normalize_new_syntax_monetary_costs(source)
    model = source["model"]
    regions = model.get("regions", ["REG1"])
    default_region = ",".join(regions)
    milestone_years = model.get("milestone_years", [2020])
    output_currency = (
        monetary_policy["canonical_currency"]
        if monetary_policy.get("enabled")
        else "USD"
    )

    # Build normalized commodities dict
    commodities = _normalize_commodities_for_new_syntax(model.get("commodities", []))

    # Build segment keys
    seg_cfg = source.get("segments") or {}
    segment_keys = build_segments({"segments": seg_cfg})

    # Build roles from process_roles
    roles = build_roles(source, commodities)
    convention_warnings = _validate_new_syntax_structural_invariants(
        source,
        roles,
        commodities,
    )

    # Build variants from process_variants
    variants = build_variants(source, roles, commodities)

    # Expand availability to process instances
    instances = expand_availability(source, variants, segment_keys)

    # Apply process_parameters overrides
    apply_process_parameters(instances, source)

    # Create naming registry for deterministic symbols
    registry = NamingRegistry()

    # Build solve-independent metadata map for diagnostics resolution
    metadata_map = _build_metadata_map(instances, commodities, registry)
    variant_symbol_map: dict[str, list[dict[str, str]]] = {}
    for process_symbol, meta in metadata_map.items():
        variant_symbol_map.setdefault(meta["variant"], []).append(
            {
                "process": process_symbol,
                "region": meta["region"],
            }
        )
    diagnostics_export = _resolve_diagnostics_boundaries(
        source.get("diagnostics"), metadata_map
    )

    # Lowering is intentionally deferred to explicit FI_* row construction below.
    lower_instances_to_tableir(instances, commodities, segment_keys, registry)

    # Compile demands to scenario parameters
    demand_params = compile_demands(source, commodities, segment_keys, registry)

    # Build commodity rows for ~FI_COMM
    comm_rows = []
    for comm_id, comm in commodities.items():
        comm_rows.append({
            "region": default_region,
            "csets": _commodity_type_to_csets(comm.get("type", "energy")),
            "commodity": registry.get_commodity_symbol(comm_id, None),
            "unit": comm.get("unit", "PJ"),
        })
        # For non-tradable commodities with segments, emit scoped versions
        if not comm.get("tradable", True) and segment_keys:
            for seg in segment_keys:
                scoped_sym = registry.get_commodity_symbol(comm_id, seg)
                if scoped_sym != comm_id:  # Only add if different
                    comm_rows.append({
                        "region": default_region,
                        "csets": _commodity_type_to_csets(
                            comm.get("type", "energy")
                        ),
                        "commodity": scoped_sym,
                        "unit": comm.get("unit", "PJ"),
                    })

    # Build ~FI_PROCESS rows from instances
    fi_process_rows = []
    for key, instance in sorted(instances.items()):
        prc_name = registry.get_process_symbol(key.variant_id, key.region, key.segment)
        activity_unit = instance.role.activity_unit
        capacity_unit = instance.role.capacity_unit
        row = {
            "region": key.region,
            "process": prc_name,
            "sets": ",".join(
                ["DMD"]
                if _produces_service_comm(instance.variant.outputs, commodities)
                else []
            ),
            "tact": activity_unit,
            "tcap": capacity_unit,
        }
        fi_process_rows.append(row)

    # Build ~FI_T topology rows from instances
    fi_t_rows = []
    pasti_rows = []
    for key, instance in sorted(instances.items()):
        prc_name = registry.get_process_symbol(key.variant_id, key.region, key.segment)
        attrs = instance.attrs
        activity_unit = instance.role.activity_unit
        capacity_unit = instance.role.capacity_unit
        prc_capact = _compute_cap2act(capacity_unit, activity_unit)

        # Input commodities (from variant's explicit I/O)
        for inp_id in instance.variant.inputs:
            comm = commodities.get(inp_id, {})
            tradable = comm.get("tradable", True)
            if tradable:
                scoped_id = registry.get_commodity_symbol(inp_id, None)
            else:
                scoped_id = registry.get_commodity_symbol(inp_id, key.segment)
            fi_t_rows.append({
                "region": key.region,
                "process": prc_name,
                "commodity-in": scoped_id,
            })

        # Output commodities (from variant's explicit I/O)
        for out_id in instance.variant.outputs:
            comm = commodities.get(out_id, {})
            comm_kind = _commodity_kind(comm)
            tradable = comm.get("tradable", True)
            # Emission commodities are always region-wide (never segment-scoped)
            if comm_kind == "emission" or tradable:
                scoped_id = registry.get_commodity_symbol(out_id, None)
            else:
                scoped_id = registry.get_commodity_symbol(out_id, key.segment)
            fi_t_rows.append({
                "region": key.region,
                "process": prc_name,
                "commodity-out": scoped_id,
            })

        # Efficiency row with other attributes
        if "efficiency" in attrs:
            eff_row = {
                "region": key.region,
                "process": prc_name,
                "eff": attrs["efficiency"],
            }
            if prc_capact is not None:
                eff_row["prc_capact"] = prc_capact
            # Add scalar costs to FI_T row; time-varying costs go to TFM_INS
            cost_attrs = {
                "investment_cost": ("ncap_cost", "NCAP_COST"),
                "fixed_om_cost": ("ncap_fom", "NCAP_FOM"),
                "variable_om_cost": ("act_cost", "ACT_COST"),
                "lifetime": ("ncap_tlife", "NCAP_TLIFE"),
            }
            for attr_name, (col_name, times_name) in cost_attrs.items():
                if attr_name not in attrs:
                    continue
                val = attrs[attr_name]
                if _is_time_varying(val):
                    sparse = val.get("values", {})
                    interp = val.get("interpolation", "interp_extrap")
                    dense = _expand_series_to_years(sparse, milestone_years, interp)
                    for year, v in sorted(dense.items()):
                        pasti_rows.append({
                            "region": key.region,
                            "process": prc_name,
                            "year": year,
                            "attribute": times_name,
                            "value": v,
                        })
                else:
                    eff_row[col_name] = val
            fi_t_rows.append(eff_row)
        elif prc_capact is not None:
            # Emit standalone PRC_CAPACT row when no efficiency row exists.
            row = {
                "region": key.region,
                "process": prc_name,
                "prc_capact": prc_capact,
            }
            first_output = (
                instance.variant.outputs[0] if instance.variant.outputs else None
            )
            if first_output:
                comm = commodities.get(first_output, {})
                tradable = comm.get("tradable", True)
                if _commodity_kind(comm) == "emission" or tradable:
                    scoped_id = registry.get_commodity_symbol(first_output, None)
                else:
                    scoped_id = registry.get_commodity_symbol(first_output, key.segment)
                row["commodity-out"] = scoped_id
            fi_t_rows.append(row)

        # Stock (PRC_RESID) - use TFM_INS pattern to avoid commodity requirement
        if "stock" in attrs:
            for year in milestone_years:
                pasti_rows.append({
                    "region": key.region,
                    "process": prc_name,
                    "year": year,
                    "attribute": "PRC_RESID",
                    "value": attrs["stock"],
                })

        # Existing capacity (NCAP_PASTI) via ~TFM_INS
        if "existing_capacity" in attrs:
            for pasti in attrs["existing_capacity"]:
                pasti_rows.append({
                    "region": key.region,
                    "process": prc_name,
                    "year": pasti["vintage"],
                    "attribute": "NCAP_PASTI",
                    "value": pasti["capacity"],
                })

        # Bounds - use TFM_INS pattern to avoid commodity requirement
        # Maps to TIMES attributes: CAP_BND, NCAP_BND, ACT_BND
        bound_attr_map = {
            "cap_bound": "CAP_BND",
            "ncap_bound": "NCAP_BND",
            "activity_bound": "ACT_BND",
        }
        for bound_type in ["cap_bound", "ncap_bound", "activity_bound"]:
            if bound_type not in attrs:
                continue
            bound_spec = attrs[bound_type]
            attr_name = bound_attr_map[bound_type]
            for lim_key, lim_val in bound_spec.items():
                limtype = {"up": "UP", "lo": "LO", "fx": "FX"}.get(lim_key)
                if not limtype:
                    continue
                for year in milestone_years:
                    pasti_rows.append({
                        "region": key.region,
                        "process": prc_name,
                        "year": year,
                        "limtype": limtype,
                        "attribute": attr_name,
                        "value": lim_val,
                    })

        # Emission factors (ENV_ACT) via ~TFM_INS
        # Emission commodities are now regular role outputs; emission_factors
        # parameterizes the per-activity emission rate for each.
        if "emission_factors" in attrs:
            for em_comm, em_factor in attrs["emission_factors"].items():
                if em_factor == 0:
                    continue  # No ENV_ACT row needed for zero emission factor
                em_sym = registry.get_commodity_symbol(em_comm, None)
                pasti_rows.append({
                    "region": key.region,
                    "process": prc_name,
                    "commodity": em_sym,
                    "attribute": "ENV_ACT",
                    "value": em_factor,
                })

    # Build system settings
    model_name = model.get("name", "Model")
    bookname = model_name.upper()
    start_year = milestone_years[0] if milestone_years else 2020
    last_year = milestone_years[-1] if milestone_years else 2020

    bookregions_rows = [{"bookname": bookname, "region": r} for r in regions]
    startyear_rows = [{"value": start_year}]
    milestoneyears_rows = [{"type": "Endyear", "year": last_year + 10}]
    milestoneyears_rows += [
        {"type": "milestoneyear", "year": y} for y in milestone_years
    ]
    currencies_rows = [{"currency": output_currency}]

    discount_rate = model.get("discount_rate", 0.05)
    gdrate_rows = [
        {
            "region": r,
            "attribute": "G_DRATE",
            "currency": output_currency,
            "value": discount_rate,
        }
        for r in regions
    ]

    # Timeslice handling — always emit at least ANNUAL
    timeslice_rows = []
    yrfr_rows = []
    if "timeslices" in model:
        timeslice_rows, yrfr_rows = _compile_timeslices(model["timeslices"], regions)
    else:
        # Default: single ANNUAL timeslice (required by TIMES)
        timeslice_rows = [{"season": "AN"}]
        yrfr_rows = [
            {"region": r, "attribute": "YRFR", "timeslice": "AN", "value": 1.0}
            for r in regions
        ]

    syssets_tables = [
        {"tag": "~BOOKREGIONS_MAP", "rows": bookregions_rows},
        {"tag": "~STARTYEAR", "rows": startyear_rows},
        {"tag": "~MILESTONEYEARS", "rows": milestoneyears_rows},
        {"tag": "~CURRENCIES", "rows": currencies_rows},
        {"tag": "~TIMESLICES", "rows": timeslice_rows},
    ]

    syssettings_sheets = [
        {"name": "SysSets", "tables": syssets_tables},
        {"name": "Commodities", "tables": [{"tag": "~FI_COMM", "rows": comm_rows}]},
    ]

    constants_tables = [{"tag": "~TFM_INS", "rows": gdrate_rows}]
    if yrfr_rows:
        constants_tables.append({"tag": "~TFM_INS", "rows": yrfr_rows})
    syssettings_sheets.append({"name": "constants", "tables": constants_tables})

    # Process file
    process_file_path = f"vt_{bookname.lower()}_{model_name.lower()}.xlsx"
    process_tables = [
        {"tag": "~FI_PROCESS", "rows": fi_process_rows},
        {"tag": "~FI_T", "rows": fi_t_rows},
    ]
    if pasti_rows:
        process_tables.append({"tag": "~TFM_INS", "rows": pasti_rows})

    # Compile scenario files from demands + model scenario_parameters
    all_scenario_params = list(model.get("scenario_parameters", []))
    all_scenario_params.extend(demand_params)

    cases = model.get("cases", [])
    if not cases:
        cases = [{"name": "baseline", "is_baseline": True}]
    cases = _select_cases(cases, selected_cases)

    scenario_files, cases_json = _compile_scenario_files(
        all_scenario_params,
        model.get("constraints", []),
        cases,
        regions,
        milestone_years,
        default_region,
        variant_symbol_map=variant_symbol_map,
    )

    # Trade links
    trade_link_files, _ = _compile_trade_links(
        model.get("trade_links", []),
        model.get("commodities", []),
    )

    tableir = {
        "files": [
            {"path": "syssettings.xlsx", "sheets": syssettings_sheets},
            {
                "path": process_file_path,
                "sheets": [{"name": "Processes", "tables": process_tables}],
            },
            *scenario_files,
            *trade_link_files,
        ],
        "cases": cases_json,
        "metadata_map": {"processes": metadata_map},
        "diagnostics_export": diagnostics_export,
        "convention_diagnostics": {
            "contract": "res_conventions_v1",
            "warnings": convention_warnings,
        },
    }

    if validate:
        tableir_schema = load_tableir_schema()
        jsonschema.validate(tableir, tableir_schema)

        from .table_schemas import TableValidationError, validate_tableir
        table_errors = validate_tableir(tableir)
        if table_errors:
            raise TableValidationError(table_errors)

    return tableir


def _produces_service_comm(outputs: list[str], commodities: dict[str, dict]) -> bool:
    """Check if any output is a service commodity."""
    for out_id in outputs:
        if out_id in commodities:
            if _commodity_kind(commodities[out_id]) == "service":
                return True
    return False


def _commodity_kind(comm: dict) -> str:
    """Return canonical commodity kind."""
    ctype = comm.get("type")
    return {
        "fuel": "carrier",
        "energy": "carrier",
        "service": "service",
        "material": "material",
        "emission": "emission",
        "money": "money",
        "other": "carrier",
    }.get(ctype, "carrier")


def _primary_output_for_role(role, commodities: dict[str, dict]) -> str | None:
    """Select primary output as first non-emission required output.

    Fallback to first output if all outputs are emissions.
    """
    non_emission = [
        out
        for out in role.required_outputs
        if _commodity_kind(commodities.get(out, {})) != "emission"
    ]
    if non_emission:
        return non_emission[0]
    if role.required_outputs:
        return role.required_outputs[0]
    return None


def _validate_role_primary_outputs(
    roles: dict,
    commodities: dict[str, dict],
) -> list[tuple[str, str]]:
    """Enforce one primary non-emission required output for non-storage/sink roles."""
    errors: list[tuple[str, str]] = []
    for role in roles.values():
        if role.stage in {"storage", "sink"}:
            continue
        non_emission = [
            out
            for out in role.required_outputs
            if _commodity_kind(commodities.get(out, {})) != "emission"
        ]
        if len(non_emission) != 1:
            errors.append(
                (
                    role.id,
                    (
                        "Role must have exactly one primary non-emission "
                        "required output "
                        f"for stage '{role.stage}' (found {len(non_emission)})."
                    ),
                )
            )
    return errors


def _is_service_end_use_role(role, commodities: dict[str, dict]) -> bool:
    """Return True for end-use roles whose primary output is a service commodity."""
    if role.stage != "end_use":
        return False
    primary = _primary_output_for_role(role, commodities)
    if primary is None:
        return False
    return commodities.get(primary, {}).get("type") == "service"


def _suggest_merged_service_role_name(service_commodity: str) -> str:
    """Build deterministic merge suggestion from the shared service commodity."""
    return f"provide_{service_commodity}"


def _detect_service_role_duplication(
    roles: dict,
    commodities: dict[str, dict],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Detect duplicated fuel-pathway service roles and emit E1/W1/W2 diagnostics."""
    grouped: dict[str, list] = {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    for role in roles.values():
        if not _is_service_end_use_role(role, commodities):
            continue
        primary = _primary_output_for_role(role, commodities)
        if primary is None:
            continue
        grouped.setdefault(primary, []).append(role)

        # W2: role names should describe the service, not fuel pathways.
        fuelish_inputs = [
            inp
            for inp in role.required_inputs
            if commodities.get(inp, {}).get("type") in {"fuel", "energy"}
        ]
        if fuelish_inputs and ROLE_FUEL_PATHWAY_PATTERN.search(role.id):
            warnings.append(
                {
                    "code": "W2_FUEL_PATHWAY_ROLE_NAME",
                    "location": f"process_roles[{role.id}]",
                    "message": (
                        "Role name appears to encode fuel pathway semantics. "
                        "Use service-level names on roles and move pathway "
                        "choices to variants."
                    ),
                }
            )

    for service, role_group in sorted(grouped.items()):
        sorted_roles = sorted(role_group, key=lambda role: role.id)
        if len(sorted_roles) < 2:
            continue

        merged_name = _suggest_merged_service_role_name(service)
        role_names = ", ".join(role.id for role in sorted_roles)
        errors.append(
            {
                "code": "E1_DUPLICATE_SERVICE_ROLES",
                "location": (
                    f"process_roles[{service}]"
                ),
                "message": (
                    "Fuel-pathway role duplication detected for service commodity "
                    f"'{service}' at stage 'end_use': {role_names}. "
                    "Merge into one service role "
                    f"(e.g., '{merged_name}') and express pathways as variants."
                ),
            }
        )

        signatures: dict[tuple[tuple[str, ...], tuple[str, ...]], list[str]] = {}
        for role in sorted_roles:
            signature = (
                tuple(sorted(role.required_inputs)),
                tuple(sorted(role.required_outputs)),
            )
            signatures.setdefault(signature, []).append(role.id)

        for signature_roles in signatures.values():
            if len(signature_roles) < 2:
                continue
            warnings.append(
                {
                    "code": "W1_SPLIT_IDENTICAL_IO_ROLES",
                    "location": f"process_roles[{service}]",
                    "message": (
                        "Multiple end-use roles share identical "
                        "input/output structure: "
                        f"{', '.join(sorted(signature_roles))}. "
                        "Consider merging into one service role with multiple variants."
                    ),
                }
            )

    return errors, warnings


def _derive_variant_kind(
    role,
    variant_attrs: dict,
    commodities: dict[str, dict],
    outputs: list[str],
) -> tuple[str, str]:
    """Return effective and derived process kind for diagnostics metadata."""
    derived_kind = _derive_kind_from_structure(role, commodities, outputs)

    explicit = variant_attrs.get("kind")
    if explicit:
        return explicit, derived_kind

    return derived_kind, derived_kind


def _derive_kind_from_structure(
    role,
    commodities: dict[str, dict],
    outputs: list[str],
) -> str:
    """Auto-derived kind from PRD stage/output conventions.

    Rules:
    - stage=storage => storage
    - stage=end_use with service output => device
    - stage=conversion with electricity output => generator
    """
    if role.stage == "storage":
        return "storage"

    if role.stage == "end_use" and _has_service_output(outputs, commodities):
        return "device"

    if role.stage == "conversion" and _has_electricity_output(outputs, commodities):
        return "generator"

    return "process"


def _has_service_output(outputs: list[str], commodities: dict[str, dict]) -> bool:
    """Return True when any output commodity is a service commodity."""
    return any(
        _commodity_kind(commodities.get(out, {})) == "service"
        for out in outputs
    )


def _has_electricity_output(outputs: list[str], commodities: dict[str, dict]) -> bool:
    """Return True when an output appears to be electricity commodity."""
    electricity_tokens = ("electricity", "elc", "elec")
    for out in outputs:
        commodity = commodities.get(out, {})
        if commodity.get("type") != "energy":
            continue
        normalized_out = out.lower()
        if any(token in normalized_out for token in electricity_tokens):
            return True
    return False


def _build_metadata_map(
    instances: dict,
    commodities: dict[str, dict],
    registry: NamingRegistry,
) -> dict[str, dict]:
    """Build solve-independent metadata map for diagnostics boundary resolution."""
    metadata: dict[str, dict] = {}
    for key, instance in sorted(instances.items()):
        symbol = registry.get_process_symbol(key.variant_id, key.region, key.segment)
        role = instance.role
        service = _primary_output_for_role(role, commodities)
        carriers = [
            inp
            for inp in instance.variant.inputs
            if _commodity_kind(commodities.get(inp, {})) != "emission"
        ]
        sector = None
        if key.segment:
            sector = key.segment.split(".")[0]
        semantic_kind, derived_kind = _derive_variant_kind(
            role,
            instance.attrs,
            commodities,
            instance.variant.outputs,
        )
        metadata[symbol] = {
            "variant": key.variant_id,
            "region": key.region,
            "segment": key.segment,
            "stage": role.stage,
            "sector": sector,
            "service": service,
            "carrier_in": carriers,
            "kind": semantic_kind,
            "derived_kind": derived_kind,
            "kind_source": "explicit" if "kind" in instance.attrs else "derived",
            "exclude_from_fuel_switch": False,
        }
    return metadata


def _resolve_diagnostics_boundaries(
    diagnostics: dict | None,
    metadata_map: dict[str, dict],
) -> dict:
    """Resolve diagnostics boundaries to concrete process symbols."""
    if not diagnostics:
        return {
            "contract": "diagnostics_are_solve_independent",
            "on_empty_boundary": "warn",
            "boundaries": [],
            "metrics": [],
            "warnings": [],
        }

    warnings = []
    on_empty = diagnostics.get("on_empty_boundary", "warn")
    resolved = []

    for boundary in diagnostics.get("boundaries", []):
        selectors = boundary.get("selectors", {})
        stage_in = set(selectors.get("stage_in", []))
        sector_in = set(selectors.get("sector_in", []))
        service_in = set(selectors.get("service_in", []))
        kind_in = set(selectors.get("kind_in", []))
        include_any = selectors.get("include_any", [])
        exclude_any = selectors.get("exclude_any", [])
        measure = boundary.get("measure")

        matches = []
        for symbol, meta in metadata_map.items():
            if stage_in and meta.get("stage") not in stage_in:
                continue
            if sector_in and meta.get("sector") not in sector_in:
                continue
            if service_in and meta.get("service") not in service_in:
                continue
            if kind_in and meta.get("kind") not in kind_in:
                continue
            if include_any and not any(token in symbol for token in include_any):
                continue
            if exclude_any and any(token in symbol for token in exclude_any):
                continue

            # Opinionated measure-specific filtering
            if measure == "generation_outputs" and meta.get("kind") != "generator":
                continue
            if measure == "end_use_inputs" and meta.get("exclude_from_fuel_switch"):
                continue

            matches.append(symbol)

        if not matches:
            msg = f"Boundary '{boundary['id']}' resolved to zero processes"
            if on_empty == "error":
                raise VedaLangError(msg)
            warnings.append(msg)

        resolved.append(
            {
                "id": boundary["id"],
                "measure": measure,
                "selectors": selectors,
                "default_exclusions": [],
                "processes": sorted(matches),
            }
        )

    return {
        "contract": "diagnostics_are_solve_independent",
        "on_empty_boundary": on_empty,
        "boundaries": resolved,
        "metrics": diagnostics.get("metrics", []),
        "warnings": warnings,
    }


def compile_vedalang_to_tableir(
    source: dict,
    validate: bool = True,
    selected_cases: list[str] | None = None,
) -> dict:
    """
    Transform VedaLang source to TableIR structure.

    Args:
        source: VedaLang dictionary (parsed from .veda.yaml)
        validate: Whether to validate input/output against schemas and semantics

    Returns:
        TableIR dictionary ready for veda_emit_excel

    Raises:
        jsonschema.ValidationError: If source doesn't match VedaLang schema
        SemanticValidationError: If cross-references are invalid
    """
    if validate:
        validate_vedalang(source)

    # Detect new syntax: process_roles is at top-level (not in model)
    if source.get("process_roles"):
        return _compile_new_syntax(source, validate, selected_cases)

    model = source["model"]

    # Semantic cross-reference validation (before any emission)
    if validate:
        errors, warnings = validate_cross_references(model)
        if errors:
            raise SemanticValidationError(errors, warnings)

    # Get regions from model
    regions = model.get("regions", ["REG1"])
    default_region = ",".join(regions)  # For multi-region models

    # Extract milestone years early - needed for year expansion
    # VedaLang principle: Always emit explicit values for all milestone years
    milestone_years = model.get("milestone_years", [2020])

    # Build commodity lookup for type checking during process compilation
    commodity_types = {
        c["name"]: c.get("type", "energy") for c in model.get("commodities", [])
    }

    # Build commodity table (~FI_COMM)
    # Use lowercase column names for xl2times compatibility
    comm_rows = []
    for commodity in model.get("commodities", []):
        # commodity.type is the canonical field
        comm_kind = commodity.get("type", "energy")
        # Use explicit unit or default based on commodity kind
        unit = commodity.get("unit") or _get_default_unit(comm_kind)
        comm_rows.append({
            "region": default_region,
            "csets": _commodity_type_to_csets(comm_kind),
            "commodity": commodity["name"],
            "unit": unit,
        })

    # Build process table (~FI_PROCESS)
    # Use lowercase column names for xl2times compatibility
    # primarycg is OPTIONAL - only emit when explicitly specified, else xl2times infers
    process_rows = []
    for raw_process in model.get("processes", []):
        # Normalize shorthand input/output syntax
        process = _normalize_process_flows(raw_process)
        row = {
            "region": default_region,
            "process": process["name"],
            "description": process.get("description", ""),
            "sets": ",".join(process.get("sets", [])),
            "tact": process.get("activity_unit", "PJ"),
            "tcap": process.get("capacity_unit", "GW"),
        }
        pcg_override = process.get("primary_commodity_group")
        if pcg_override is not None:
            row["primarycg"] = pcg_override
        process_rows.append(row)

    # Build topology table (~FI_T) for inputs/outputs
    # Use lowercase column names for xl2times compatibility
    topology_rows = []
    all_emission_factors = []  # Collected for separate ~TFM_INS table
    all_pasti_rows = []  # NCAP_PASTI rows for ~TFM_INS table
    for raw_process in model.get("processes", []):
        # Normalize shorthand input/output syntax
        process = _normalize_process_flows(raw_process)
        inputs = process.get("inputs", [])
        outputs = process.get("outputs", [])

        # Collect cost parameters - separate scalar from time-varying
        # Keys in cost_params use CANONICAL column names from ATTR_TO_COLUMN
        cost_params = {}  # Scalar values to merge into rows
        time_varying_attrs = []  # (attr_name, value) tuples for year-indexed rows
        year_expand_attrs = []  # (attr_name, value) scalars that expand to all years

        # All process attributes that can be emitted
        process_attrs = [
            "investment_cost", "fixed_om_cost", "variable_om_cost",
            "import_price", "lifetime", "stock",
        ]

        for attr in process_attrs:
            if attr not in process:
                continue

            _validate_attribute_for_emission(attr, "FI_T")
            val = process[attr]
            column = ATTR_TO_COLUMN.get(attr, attr)

            if _is_time_varying(val):
                # Always expand time-varying to all years
                time_varying_attrs.append((attr, val))
            elif attr in EXPAND_TO_ALL_YEARS_ATTRS:
                # Scalar but must expand to all milestone years
                year_expand_attrs.append((attr, val))
            else:
                # Scalar that doesn't need year expansion (e.g., lifetime)
                cost_params[column] = val

        # Add PRC_CAPACT (capacity-to-activity conversion) when units differ
        # This is critical: if capacity is in GW and activity is in PJ, TIMES needs
        # to know the conversion factor (31.536 PJ/GW/year for full-year operation)
        activity_unit = process.get("activity_unit", "PJ")
        capacity_unit = process.get("capacity_unit", "GW")
        cap2act = _compute_cap2act(capacity_unit, activity_unit)
        if cap2act is not None:
            cost_params["prc_capact"] = cap2act

        # Add input flows
        for inp in inputs:
            row = {
                "region": default_region,
                "process": process["name"],
                "commodity-in": inp["commodity"],
            }
            if "share" in inp:
                row["share-i"] = inp["share"]
            topology_rows.append(row)

        # Collect emission factors for separate rows (emitted via attribute column)
        emission_factors = []

        # Add output flows - merge cost params into first output row if no eff
        for i, out in enumerate(outputs):
            out_comm = out["commodity"]
            out_comm_type = commodity_types.get(out_comm, "energy")
            row = {
                "region": default_region,
                "process": process["name"],
                "commodity-out": out_comm,
            }

            # Handle emission outputs: use ENV_ACT attribute for emission coefficients
            # Reject 'share' on emission commodities (would become invalid FLO_SHAR)
            if out_comm_type == "emission":
                if "share" in out:
                    raise SemanticValidationError([
                        f"Process '{process['name']}': 'share' is not allowed on "
                        f"emission output '{out_comm}'. Use 'emission_factor' instead."
                    ])
                if "emission_factor" in out:
                    # Collect for separate attribute row
                    emission_factors.append({
                        "commodity": out_comm,
                        "value": out["emission_factor"],
                    })
            else:
                # Non-emission outputs: use share -> share-o
                if "share" in out:
                    row["share-o"] = out["share"]

            # Merge cost params into first output row if no efficiency specified
            if i == 0 and "efficiency" not in process and cost_params:
                row.update(cost_params)
                cost_params = {}  # Clear so we don't add again
            topology_rows.append(row)

        # Collect emission factors for VT process file ~TFM_INS table
        # We'll emit these as a separate table after ~FI_T
        for ef in emission_factors:
            all_emission_factors.append({
                "region": default_region,
                "process": process["name"],
                "commodity": ef["commodity"],
                "attribute": "ENV_ACT",
                "value": ef["value"],
            })

        # Collect bound parameters - expand to all milestone years
        bound_params = _collect_bound_params(process, milestone_years)

        # Add efficiency row with cost and bound parameters if specified
        if "efficiency" in process:
            _validate_attribute_for_emission("efficiency", "FI_T")
            eff_val = process["efficiency"]
            if _is_time_varying(eff_val):
                # Time-varying efficiency - add to time_varying_attrs
                time_varying_attrs.append(("efficiency", eff_val))
                # Still emit a base row with scalar cost params if any
                if cost_params:
                    row = {
                        "region": default_region,
                        "process": process["name"],
                    }
                    # xl2times requires rows to have a commodity or eff/value
                    # Add first output commodity for reference
                    first_output = outputs[0]["commodity"] if outputs else None
                    if first_output:
                        row["commodity-out"] = first_output
                    row.update(cost_params)
                    if bound_params:
                        first_bound = bound_params.pop(0)
                        row.update(first_bound)
                    topology_rows.append(row)
            else:
                # Scalar efficiency
                row = {
                    "region": default_region,
                    "process": process["name"],
                    "eff": eff_val,
                }
                row.update(cost_params)
                # Merge first bound into efficiency row if present
                if bound_params:
                    first_bound = bound_params.pop(0)
                    row.update(first_bound)
                topology_rows.append(row)

        # Emit remaining bounds merged with commodity-out references
        # xl2times requires rows to have Comm-IN, Comm-OUT, EFF, or Value
        for bound_param in bound_params:
            # Find first output commodity for this process
            first_output = outputs[0]["commodity"] if outputs else None
            row = {
                "region": default_region,
                "process": process["name"],
            }
            if first_output:
                row["commodity-out"] = first_output
            row.update(bound_param)
            topology_rows.append(row)

        # Emit time-varying attributes as separate year-indexed rows
        # xl2times requires at least one commodity reference per row
        first_output = outputs[0]["commodity"] if outputs else None
        for attr_name, attr_value in time_varying_attrs:
            base_row = {
                "region": default_region,
                "process": process["name"],
            }
            if first_output:
                base_row["commodity-out"] = first_output
            # Use original _expand_time_varying_attr which emits year=0 + data rows
            # This preserves backward compatibility for time-varying syntax
            expanded_rows = _expand_time_varying_attr(attr_name, attr_value, base_row)
            topology_rows.extend(expanded_rows)

        # Emit scalar attributes that need year expansion (VedaLang design principle)
        # These are attributes where TIMES interpolation could cause surprises
        for attr_name, scalar_value in year_expand_attrs:
            base_row = {
                "region": default_region,
                "process": process["name"],
            }
            if first_output:
                base_row["commodity-out"] = first_output
            expanded_rows = _expand_scalar_to_all_years(
                attr_name, scalar_value, base_row, milestone_years
            )
            topology_rows.extend(expanded_rows)

        # Handle existing_capacity (NCAP_PASTI) - past investments with vintage years
        # Unlike PRC_RESID, NCAP_PASTI uses pastyear (vintage) not datayear
        # Emitted via ~TFM_INS table using attribute/value pattern
        if "existing_capacity" in process:
            for pasti in process["existing_capacity"]:
                pasti_row = {
                    "region": default_region,
                    "process": process["name"],
                    "year": pasti["vintage"],
                    "attribute": "NCAP_PASTI",
                    "value": pasti["capacity"],
                }
                all_pasti_rows.append(pasti_row)

    # Build system settings tables
    regions = model.get("regions", ["REG1"])

    # ~BOOKREGIONS_MAP - maps book regions to internal regions
    # Use a single bookname for all regions to ensure all are treated as internal
    # The bookname must match the VT_{bookname}_* file pattern
    # IMPORTANT: Bookname must be uppercase for xl2times compatibility
    model_name = model.get("name", "Model")
    bookname = model_name.upper()  # Uppercase for xl2times BookRegions_Map matching
    bookregions_rows = [{"bookname": bookname, "region": r} for r in regions]

    # ~STARTYEAR - model start year (first milestone year)
    # NOTE: milestone_years already extracted at start of function
    start_year = milestone_years[0] if milestone_years else 2020
    startyear_rows = [{"value": start_year}]

    # ~MILESTONEYEARS - explicit milestone years (alternative to ~TIMEPERIODS)
    # Format: type column + year column (named after model)
    # This ensures VedaLang milestone_years appear directly in TIMES MILESTONYR
    last_year = milestone_years[-1] if milestone_years else 2020
    milestoneyears_rows = [{"type": "Endyear", "year": last_year + 10}]
    milestoneyears_rows += [
        {"type": "milestoneyear", "year": y} for y in milestone_years
    ]

    # ~CURRENCIES - default currency
    output_currency = _model_output_currency(model)
    currencies_rows = [{"currency": output_currency}]

    # G_DRATE - discount rate (required for TIMES to process costs)
    # Without G_DRATE, rdcur set is empty and all cost parameters are ignored
    # Default: 5% discount rate; can be overridden via model.discount_rate
    discount_rate = model.get("discount_rate", 0.05)
    gdrate_rows = [
        {
            "region": r,
            "attribute": "G_DRATE",
            "currency": output_currency,
            "value": discount_rate,
        }
        for r in regions
    ]

    # Use milestone_years for time-series expansion (already extracted above)
    model_years = milestone_years

    # Build scenario files (~TFM_DINS-AT tables)
    # ARCHITECTURE/SCENARIO SEPARATION:
    # - Scenario data (demand projections, commodity prices) goes to Scen_* files
    # - This prevents forward-fill contamination when mixed with process topology
    # - Uses ~TFM_DINS-AT for VedaOnline compatibility
    # FILE NAMING: Scen_{case}_{category}.xlsx
    # - Groups parameters by case and category
    # - Constraints are co-located with their category (default: policies)

    # Get scenario parameters (support new 'scenario_parameters' and legacy 'scenarios')
    scenario_params = (
        model.get("scenario_parameters", []) or model.get("scenarios", [])
    )

    # Get cases - if none defined, create a default 'baseline' case
    cases = model.get("cases", [])
    if not cases:
        # Default case includes all parameters
        cases = [{"name": "baseline", "is_baseline": True}]
    cases = _select_cases(cases, selected_cases)

    # Build scenario files organized by case and category
    scenario_files, cases_json = _compile_scenario_files(
        scenario_params,
        model.get("constraints", []),
        cases,
        regions,
        model_years,
        default_region,
        variant_symbol_map=None,
    )

    # Compile timeslices — always emit at least ANNUAL
    timeslice_rows = []
    yrfr_rows = []
    if "timeslices" in model:
        timeslice_rows, yrfr_rows = _compile_timeslices(
            model["timeslices"], regions
        )
    else:
        timeslice_rows = [{"season": "AN"}]
        yrfr_rows = [
            {"region": r, "attribute": "YRFR", "timeslice": "AN", "value": 1.0}
            for r in regions
        ]

    # Build SysSets tables list
    syssets_tables = [
        {"tag": "~BOOKREGIONS_MAP", "rows": bookregions_rows},
        {"tag": "~STARTYEAR", "rows": startyear_rows},
        {"tag": "~MILESTONEYEARS", "rows": milestoneyears_rows},
        {"tag": "~CURRENCIES", "rows": currencies_rows},
        {"tag": "~TIMESLICES", "rows": timeslice_rows},
    ]

    # Build SysSettings sheets list
    syssettings_sheets = [
        {"name": "SysSets", "tables": syssets_tables},
        {"name": "Commodities", "tables": [{"tag": "~FI_COMM", "rows": comm_rows}]},
    ]

    # Build constants tables - includes G_DRATE and optionally YRFR
    constants_tables = [{"tag": "~TFM_INS", "rows": gdrate_rows}]
    if yrfr_rows:
        constants_tables.append({"tag": "~TFM_INS", "rows": yrfr_rows})

    syssettings_sheets.append({
        "name": "constants",
        "tables": constants_tables,
    })

    # Build process file - use VT_{bookname}_ prefix for internal region recognition
    # All regions map to this single bookname via BOOKREGIONS_MAP
    # Use lowercase for consistent file naming (xl2times is case-insensitive)
    process_file_path = f"vt_{bookname.lower()}_{model_name.lower()}.xlsx"

    # Compile trade links if present - returns files only (no process/topology rows)
    # Trade processes are auto-generated by VEDA/xl2times from ~TRADELINKS tables
    trade_link_files, _ = _compile_trade_links(
        model.get("trade_links", []),
        model.get("commodities", []),
    )

    # Build TableIR structure
    # ARCHITECTURE ONLY: VT_* and SysSettings files contain model structure
    # Scenario data (demands, prices, policies) → Scen_{case}_{category}.xlsx
    tableir = {
        "files": [
            {
                "path": "syssettings.xlsx",
                "sheets": syssettings_sheets,
            },
            {
                "path": process_file_path,
                "sheets": [
                    {
                        "name": "Processes",
                        "tables": _build_process_tables(
                            process_rows, topology_rows,
                            all_emission_factors, all_pasti_rows
                        ),
                    },
                ],
            },
            *scenario_files,
            *trade_link_files,
        ],
        # Include cases.json metadata for VEDA integration
        "cases": cases_json,
    }

    if validate:
        tableir_schema = load_tableir_schema()
        jsonschema.validate(tableir, tableir_schema)

        # Validate against VEDA table schemas (canonical column names only)
        from .table_schemas import TableValidationError, validate_tableir

        table_errors = validate_tableir(tableir)
        if table_errors:
            raise TableValidationError(table_errors)

    return tableir


def _build_process_tables(
    process_rows: list[dict],
    topology_rows: list[dict],
    emission_factors: list[dict],
    pasti_rows: list[dict],
) -> list[dict]:
    """Build the tables list for the process sheet."""
    tables = [
        {"tag": "~FI_PROCESS", "rows": process_rows},
        {"tag": "~FI_T", "rows": topology_rows},
    ]
    if emission_factors:
        tables.append({"tag": "~TFM_INS", "rows": emission_factors})
    if pasti_rows:
        tables.append({"tag": "~TFM_INS", "rows": pasti_rows})
    return tables


def _collect_bound_params(
    process: dict,
    milestone_years: list[int] | None = None,
) -> list[dict]:
    """
    Collect bound parameters from process definition.

    Each bound type (activity_bound, cap_bound, ncap_bound) can have up to three
    limits (up, lo, fx), each returned as separate dicts with limtype and column.

    When milestone_years is provided, scalar bounds are expanded to all years
    per VedaLang design principle: Never rely on TIMES implicit interpolation.

    Args:
        process: Process definition from VedaLang source
        milestone_years: If provided, expand scalar bounds to all years

    Returns:
        List of dicts with {limtype, year (if expanded), <bound_column>: value}
    """
    params = []

    # Mapping: VedaLang field -> (VEDA column name, TIMES attribute name)
    bound_mapping = {
        "activity_bound": ("act_bnd", "ACT_BND"),
        "cap_bound": ("cap_bnd", "CAP_BND"),
        "ncap_bound": ("ncap_bnd", "NCAP_BND"),
    }

    # Mapping: VedaLang limtype key -> VEDA limtype value
    limtype_mapping = {
        "up": "UP",
        "lo": "LO",
        "fx": "FX",
    }

    for vedalang_field, (veda_column, times_attr) in bound_mapping.items():
        bound_spec = process.get(vedalang_field)
        if not bound_spec:
            continue

        _validate_attribute_for_emission(times_attr, "FI_T")

        for limit_key, limit_value in bound_spec.items():
            if limit_key not in limtype_mapping:
                continue

            limtype = limtype_mapping[limit_key]

            # Check if this is a time-varying bound
            if _is_time_varying(limit_value):
                # Time-varying bound: expand using interpolation
                sparse_values = limit_value.get("values", {})
                interpolation = limit_value.get("interpolation", "interp_extrap")
                years_to_use = milestone_years or [2020]
                dense_values = _expand_series_to_years(
                    sparse_values, years_to_use, interpolation
                )
                for year, val in sorted(dense_values.items()):
                    params.append({
                        "limtype": limtype,
                        "year": year,
                        veda_column: val,
                    })
            elif milestone_years:
                # Scalar bound with milestone_years: expand to all years
                for year in milestone_years:
                    params.append({
                        "limtype": limtype,
                        "year": year,
                        veda_column: limit_value,
                    })
            else:
                # Scalar bound without milestone_years: single row (legacy)
                params.append({
                    "limtype": limtype,
                    veda_column: limit_value,
                })

    return params


def _commodity_type_to_csets(ctype: str) -> str:
    """Map VedaLang commodity kind/type to VEDA Csets."""
    mapping = {
        # Canonical commodity types
        "fuel": "NRG",
        "energy": "NRG",
        "service": "DEM",
        "material": "MAT",
        "emission": "ENV",
        "money": "FIN",
        "other": "NRG",
        # Normalized internal commodity class used in compiler internals
        "carrier": "NRG",
    }
    return mapping.get(ctype, "NRG")


def _get_model_years(model: dict) -> list[int]:
    """
    Get the list of model milestone years.

    Args:
        model: The model dictionary from VedaLang source

    Returns:
        List of model years (e.g., [2020, 2030, 2040, 2050])
    """
    return model.get("milestone_years", [2020])


def _expand_series_to_years(
    sparse_values: dict[str, float],
    model_years: list[int],
    interpolation: str,
) -> dict[int, float]:
    """
    Expand sparse year->value mapping to dense values for all model years.

    Uses VEDA-compatible interpolation/extrapolation semantics but performs
    the expansion at compile time (no year=0 rows emitted).

    Args:
        sparse_values: Dictionary of year (as string) -> value
        model_years: List of model representative years
        interpolation: One of the VEDA-compatible modes:
            - none: No interpolation/extrapolation (only specified years)
            - interp_only: Interpolate between points, no extrapolation
            - interp_extrap_eps: Interpolate, extrapolate with EPS (tiny value)
            - interp_extrap: Full interpolation and extrapolation
            - interp_extrap_back: Interpolate, backward extrapolation only
            - interp_extrap_forward: Interpolate, forward extrapolation only

    Returns:
        Dictionary of year (as int) -> interpolated value
    """
    # Convert string keys to int and sort
    points = sorted([(int(y), v) for y, v in sparse_values.items()])

    if not points:
        return {}

    result = {}
    first_year, first_val = points[0]
    last_year, last_val = points[-1]

    # Determine extrapolation behavior based on mode
    extrap_backward = interpolation in ("interp_extrap", "interp_extrap_back")
    extrap_forward = interpolation in (
        "interp_extrap", "interp_extrap_forward", "interp_extrap_eps"
    )
    do_interpolate = interpolation != "none"

    for ym in model_years:
        # Check if exact match exists
        exact = next((v for y, v in points if y == ym), None)
        if exact is not None:
            result[ym] = exact
            continue

        # If no interpolation, skip non-specified years
        if not do_interpolate:
            continue

        # Find surrounding points
        before = [(y, v) for y, v in points if y < ym]
        after = [(y, v) for y, v in points if y > ym]

        if not before:
            # Before first point - backward extrapolation
            if extrap_backward:
                result[ym] = first_val
            # else: skip this year
        elif not after:
            # After last point - forward extrapolation
            if extrap_forward:
                result[ym] = last_val
            # else: skip this year
        else:
            # Between two points - linear interpolation
            y0, v0 = before[-1]
            y1, v1 = after[0]
            ratio = (ym - y0) / (y1 - y0)
            result[ym] = v0 + (v1 - v0) * ratio

    return result


def _compile_commodity_price_scenario(
    scenario: dict,
    regions: list[str],
    model_years: list[int],
) -> list[dict]:
    """
    Compile a commodity_price scenario to TableIR rows for ~TFM_DINS-AT.

    Uses ~TFM_DINS-AT tag (not ~TFM_INS) for VedaOnline compatibility.
    The attribute name becomes a column header, not a 'value' column.

    Expands sparse time-series to dense rows for all model years using
    VEDA-compatible interpolation semantics.

    Args:
        scenario: commodity_price scenario definition from VedaLang source
        regions: List of model regions (rows emitted for each)
        model_years: List of model representative years

    Returns:
        List of rows for the ~TFM_DINS-AT table (one row per region × year)
    """
    assert scenario.get("type") == "commodity_price"

    _validate_attribute_for_emission("COM_CSTNET", "TFM_DINS-AT")

    commodity = scenario["commodity"]
    sparse_values = scenario.get("values", {})
    interpolation = scenario.get("interpolation", "interp_extrap")

    # Expand to all model years using VEDA-compatible interpolation
    dense_values = _expand_series_to_years(
        sparse_values, model_years, interpolation
    )

    rows = []
    scenario_region = scenario.get("region")
    target_regions = [scenario_region] if scenario_region else regions

    for region in target_regions:
        for year, value in sorted(dense_values.items()):
            rows.append({
                "region": region,
                "cset_cn": commodity,
                "year": year,
                "com_cstnet": value,
            })

    return rows


def _compile_demand_projection_scenario(
    scenario: dict,
    regions: list[str],
    model_years: list[int],
) -> list[dict]:
    """
    Compile one demand_projection scenario to ~TFM_DINS-AT rows.

    Uses wide-in-attribute format where 'com_proj' is a column header
    in ~TFM_DINS-AT. This properly separates scenario data from model
    architecture, avoiding forward-fill contamination in xl2times.

    Args:
        scenario: A single demand_projection scenario definition
        regions: List of model regions (rows emitted for each)
        model_years: List of model representative years

    Returns:
        List of rows for ~TFM_DINS-AT table (one per region × year)
    """
    assert scenario.get("type") == "demand_projection"

    _validate_attribute_for_emission("COM_PROJ", "TFM_DINS-AT")

    commodity = scenario["commodity"]
    sparse_values = scenario.get("values", {})
    interpolation = scenario.get("interpolation", "interp_extrap")

    # Expand to all model years using VEDA-compatible interpolation
    dense_values = _expand_series_to_years(
        sparse_values, model_years, interpolation
    )

    rows = []
    scenario_region = scenario.get("region")
    target_regions = [scenario_region] if scenario_region else regions

    for region in target_regions:
        for year, value in sorted(dense_values.items()):
            rows.append({
                "region": region,
                "cset_cn": commodity,  # Commodity selector for TFM tables
                "year": year,
                "com_proj": value,  # Canonical attribute column
            })

    return rows


def _get_parameter_category(param: dict) -> str:
    """
    Get the category for a scenario parameter.

    Uses explicit 'category' if provided, otherwise infers from 'type'.
    """
    if "category" in param:
        return param["category"]
    param_type = param.get("type", "")
    return DEFAULT_CATEGORY_FROM_TYPE.get(param_type, "global_settings")


def _get_constraint_category(constraint: dict) -> str:
    """
    Get the category for a constraint.

    Constraints default to 'policies' unless explicitly categorized.
    """
    return constraint.get("category", "policies")


def _select_cases(cases: list[dict], selected_cases: list[str] | None) -> list[dict]:
    """Filter case definitions to selected names while preserving source order."""
    if not selected_cases:
        return cases

    selected = list(dict.fromkeys(selected_cases))
    available = {case["name"] for case in cases}
    missing = [name for name in selected if name not in available]
    if missing:
        available_str = ", ".join(sorted(available)) or "<none>"
        raise VedaLangError(
            "Unknown case(s) requested: "
            f"{', '.join(missing)}. Available cases: {available_str}"
        )

    selected_set = set(selected)
    return [case for case in cases if case["name"] in selected_set]

def _merge_case_series(
    base_values: dict[str, float],
    base_interpolation: str,
    override_values: dict[str, float] | None,
    override_interpolation: str,
    override_scale: float | None,
    model_years: list[int],
) -> dict[str, float]:
    """Merge a base time series with case overrides deterministically."""
    dense: dict[int, float] = {}

    if base_values:
        dense.update(
            _expand_series_to_years(base_values, model_years, base_interpolation)
        )

    if not dense and override_values:
        dense.update(
            _expand_series_to_years(
                override_values,
                model_years,
                override_interpolation,
            )
        )

    if override_scale is not None:
        dense = {year: value * override_scale for year, value in dense.items()}

    if override_values:
        if base_values:
            for year_str, value in override_values.items():
                dense[int(year_str)] = value
        else:
            dense.update(
                _expand_series_to_years(
                    override_values,
                    model_years,
                    override_interpolation,
                )
            )

    return {str(year): value for year, value in sorted(dense.items())}

def _apply_case_parameter_overrides(
    scenario_params: list[dict],
    case: dict,
    model_years: list[int],
) -> list[dict]:
    """Apply case-level demand and price overlays to scenario parameters."""
    merged_params: list[dict] = []
    for param in scenario_params:
        cloned = deepcopy(param)
        merged_params.append(cloned)

    case_name = case["name"]

    seen_demand_selectors: set[tuple[str, str, str]] = set()
    for idx, override in enumerate(case.get("demand_overrides", [])):
        selector_segment = override.get("segment") or override.get("sector") or ""
        selector_region = override.get("region", "")
        selector = (override["commodity"], selector_region, selector_segment)
        if selector in seen_demand_selectors:
            raise VedaLangError(
                "Conflicting demand_overrides in "
                f"case '{case_name}' for selector {selector}"
            )
        seen_demand_selectors.add(selector)

        matching_indices = []
        for param_idx, param in enumerate(merged_params):
            if param.get("type") != "demand_projection":
                continue
            param_commodity = str(param.get("commodity", ""))
            base_commodity = override["commodity"]
            if (
                param_commodity != base_commodity
                and not param_commodity.startswith(f"{base_commodity}@")
            ):
                continue
            if override.get("region") and param.get("region") != override["region"]:
                continue
            param_segment = param.get("segment") or param.get("sector")
            if selector_segment and param_segment != selector_segment:
                continue
            matching_indices.append(param_idx)

        if len(matching_indices) > 1:
            raise VedaLangError(
                "Ambiguous demand_overrides target in "
                f"case '{case_name}' for commodity '{override['commodity']}'"
            )

        override_values = override.get("values")
        override_scale = override.get("scale")
        if override_values is None and override_scale is None:
            raise VedaLangError(
                f"case '{case_name}' demand_overrides[{idx}] must set"
                " at least one of: values, scale"
            )

        if matching_indices:
            target = merged_params[matching_indices[0]]
            target_interpolation = target.get("interpolation", "interp_extrap")
            override_interpolation = override.get(
                "interpolation",
                target_interpolation,
            )
            merged_values = _merge_case_series(
                target.get("values", {}),
                target_interpolation,
                override_values,
                override_interpolation,
                override_scale,
                model_years,
            )
            target["values"] = merged_values
            target["interpolation"] = "none"
            continue

        if override_scale is not None and not override_values:
            raise VedaLangError(
                "demand_overrides with only 'scale' must target an existing base "
                "demand series "
                f"(case '{case_name}', commodity '{override['commodity']}')"
            )

        parts = [
            override.get("region"),
            override.get("sector"),
            override.get("segment"),
        ]
        scope = "_".join([p for p in parts if p])
        param_name = f"{case_name}_demand_override_{override['commodity']}_{idx}"
        if scope:
            param_name = f"{param_name}_{scope}"

        merged_values = _merge_case_series(
            {},
            "interp_extrap",
            override_values,
            override.get("interpolation", "interp_extrap"),
            override_scale,
            model_years,
        )
        new_param = {
            "name": param_name,
            "type": "demand_projection",
            "category": "demands",
            "commodity": (
                f"{override['commodity']}@{selector_segment}"
                if selector_segment and "@" not in override["commodity"]
                else override["commodity"]
            ),
            "values": merged_values,
            "interpolation": "none",
        }
        if override.get("region"):
            new_param["region"] = override["region"]
        if selector_segment:
            new_param["segment"] = selector_segment
        merged_params.append(new_param)

    seen_price_commodities: set[str] = set()
    for idx, override in enumerate(case.get("fuel_price_overrides", [])):
        commodity = override["commodity"]
        if commodity in seen_price_commodities:
            raise VedaLangError(
                f"Conflicting fuel_price_overrides in case '{case_name}'"
                f" for commodity '{commodity}'"
            )
        seen_price_commodities.add(commodity)

        matching_indices = [
            param_idx
            for param_idx, param in enumerate(merged_params)
            if param.get("type") == "commodity_price"
            and param.get("commodity") == commodity
        ]

        if len(matching_indices) > 1:
            raise VedaLangError(
                "Ambiguous fuel_price_overrides target in "
                f"case '{case_name}' for commodity '{commodity}'"
            )

        override_values = override.get("values")
        if override_values is None:
            raise VedaLangError(
                f"case '{case_name}' fuel_price_overrides[{idx}] is missing 'values'"
            )

        if matching_indices:
            target = merged_params[matching_indices[0]]
            target_interpolation = target.get("interpolation", "interp_extrap")
            override_interpolation = override.get(
                "interpolation",
                target_interpolation,
            )
            merged_values = _merge_case_series(
                target.get("values", {}),
                target_interpolation,
                override_values,
                override_interpolation,
                None,
                model_years,
            )
            target["values"] = merged_values
            target["interpolation"] = "none"
            continue

        merged_values = _merge_case_series(
            {},
            "interp_extrap",
            override_values,
            override.get("interpolation", "interp_extrap"),
            None,
            model_years,
        )
        merged_params.append(
            {
                "name": f"{case_name}_price_override_{commodity}_{idx}",
                "type": "commodity_price",
                "category": "prices",
                "commodity": commodity,
                "values": merged_values,
                "interpolation": "none",
            }
        )

    return merged_params

def _validate_case_overlay_configuration(
    scenario_params: list[dict],
    constraints: list[dict],
    cases: list[dict],
) -> None:
    """Validate case overlay references and conflicting selectors."""
    available_names = {
        param["name"] for param in scenario_params if "name" in param
    }
    available_names.update(
        constraint["name"] for constraint in constraints if "name" in constraint
    )

    baseline_cases = [case["name"] for case in cases if case.get("is_baseline")]
    if len(baseline_cases) > 1:
        raise VedaLangError(
            "Only one case may be marked is_baseline=true. Found: "
            + ", ".join(sorted(baseline_cases))
        )

    for case in cases:
        case_name = case["name"]
        includes = set(case.get("includes", []))
        excludes = set(case.get("excludes", []))
        overlap = sorted(includes.intersection(excludes))
        if overlap:
            raise VedaLangError(
                f"Case '{case_name}' has names in both includes and excludes:"
                f" {', '.join(overlap)}"
            )

        unknown_includes = sorted(
            name for name in includes if name not in available_names
        )
        if unknown_includes:
            raise VedaLangError(
                f"Case '{case_name}' includes unknown names:"
                f" {', '.join(unknown_includes)}"
            )

        unknown_excludes = sorted(
            name for name in excludes if name not in available_names
        )
        if unknown_excludes:
            raise VedaLangError(
                f"Case '{case_name}' excludes unknown names:"
                f" {', '.join(unknown_excludes)}"
            )

        constraint_override_names: set[str] = set()
        constraint_names = {constraint["name"] for constraint in constraints}
        for override in case.get("constraint_overrides", []):
            name = override["name"]
            if name in constraint_override_names:
                raise VedaLangError(
                    "Case "
                    f"'{case_name}' has duplicate constraint_overrides for '{name}'"
                )
            constraint_override_names.add(name)
            if name not in constraint_names:
                raise VedaLangError(
                    f"Case '{case_name}' has constraint_overrides for unknown"
                    f" constraint '{name}'"
                )

        variant_override_names: set[str] = set()
        for override in case.get("variant_overrides", []):
            variant = override["variant"]
            if variant in variant_override_names:
                raise VedaLangError(
                    f"Case '{case_name}' has duplicate variant_overrides"
                    f" for variant '{variant}'"
                )
            variant_override_names.add(variant)


def _constraints_for_case(base_constraints: list[dict], case: dict) -> list[dict]:
    """Apply case constraint overrides to base constraints."""
    overrides = {o["name"]: o for o in case.get("constraint_overrides", [])}
    resolved = []
    for constraint in base_constraints:
        override = overrides.get(constraint["name"])
        if override and override.get("enabled") is False:
            continue
        merged = dict(constraint)
        if override:
            for key in (
                "limit",
                "limtype",
                "minimum_share",
                "maximum_share",
                "years",
            ):
                if key in override:
                    merged[key] = override[key]
        resolved.append(merged)
    return resolved


def _variant_override_tfm_rows(
    case: dict,
    variant_symbol_map: dict[str, list[dict[str, str]]] | None,
    model_years: list[int],
) -> list[dict]:
    """Build ~TFM_INS rows for case-level variant overrides."""
    if not variant_symbol_map:
        return []

    attr_map = {
        "efficiency": "ACT_EFF",
        "investment_cost": "NCAP_COST",
        "fixed_om_cost": "NCAP_FOM",
        "variable_om_cost": "ACT_COST",
        "lifetime": "NCAP_TLIFE",
    }

    rows: list[dict] = []
    for override in case.get("variant_overrides", []):
        variant = override["variant"]
        entries = variant_symbol_map.get(variant, [])
        if not entries:
            raise VedaLangError(
                f"case '{case['name']}' references unknown"
                f" or unavailable variant '{variant}'"
            )

        if override.get("enabled", True) is False:
            for entry in entries:
                symbol = entry["process"]
                region = entry["region"]
                for year in model_years:
                    rows.append(
                        {
                            "region": region,
                            "process": symbol,
                            "year": year,
                            "attribute": "NCAP_BND",
                            "limtype": "FX",
                            "value": 0,
                        }
                    )
                    rows.append(
                        {
                            "region": region,
                            "process": symbol,
                            "year": year,
                            "attribute": "ACT_BND",
                            "limtype": "FX",
                            "value": 0,
                        }
                    )

        for attr_name, times_attr in attr_map.items():
            if attr_name not in override:
                continue

            value = override[attr_name]
            if _is_time_varying(value):
                sparse_values = value.get("values", {})
                interpolation = value.get("interpolation", "interp_extrap")
                dense_values = _expand_series_to_years(
                    sparse_values,
                    model_years,
                    interpolation,
                )
            else:
                dense_values = {year: value for year in model_years}

            for entry in entries:
                symbol = entry["process"]
                region = entry["region"]
                for year, attr_value in sorted(dense_values.items()):
                    rows.append(
                        {
                            "region": region,
                            "process": symbol,
                            "year": year,
                            "attribute": times_attr,
                            "value": attr_value,
                        }
                    )

    return rows


def _compile_scenario_files(
    scenario_params: list[dict],
    constraints: list[dict],
    cases: list[dict],
    regions: list[str],
    model_years: list[int],
    default_region: str,
    variant_symbol_map: dict[str, list[dict[str, str]]] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Compile scenario parameters and constraints into case-organized files.

    File naming: Scen_{case}_{category}.xlsx
    Each file contains all parameters of that category for that case.

    Args:
        scenario_params: List of scenario parameter definitions
        constraints: List of constraint definitions
        cases: List of case definitions
        regions: List of model regions
        model_years: List of model representative years
        default_region: Default region string (comma-separated if multi-region)

    Returns:
        Tuple of:
        - List of TableIR file definitions
        - List of case metadata for cases.json
    """
    from collections import defaultdict

    scenario_files = []
    cases_json = []

    _validate_case_overlay_configuration(scenario_params, constraints, cases)

    for case in cases:
        case_name = case["name"]
        includes = set(case.get("includes", []))
        excludes = set(case.get("excludes", []))
        case_scenario_params = _apply_case_parameter_overrides(
            scenario_params,
            case,
            model_years,
        )
        case_constraints = _constraints_for_case(constraints, case)
        variant_rows = _variant_override_tfm_rows(
            case,
            variant_symbol_map,
            model_years,
        )

        # Group parameters by category for this case
        params_by_category: dict[str, list[dict]] = defaultdict(list)

        for param in case_scenario_params:
            param_name = param["name"]

            # Check if parameter is included in this case
            if includes and param_name not in includes:
                continue
            if param_name in excludes:
                continue

            category = _get_parameter_category(param)
            param_type = param.get("type")

            # Compile parameter rows
            if param_type == "commodity_price":
                rows = _compile_commodity_price_scenario(param, regions, model_years)
            elif param_type == "demand_projection":
                rows = _compile_demand_projection_scenario(param, regions, model_years)
            else:
                continue

            if rows:
                params_by_category[category].append({
                    "name": param_name,
                    "description": param.get("description", ""),
                    "rows": rows,
                    "tag": "~TFM_DINS-AT",
                })

        # Group constraints by category for this case
        for constraint in case_constraints:
            constraint_name = constraint["name"]

            # Check if constraint is included in this case
            if includes and constraint_name not in includes:
                continue
            if constraint_name in excludes:
                continue

            category = _get_constraint_category(constraint)

            # Compile constraint rows (one ~UC_T per constraint)
            constraint_rows = _compile_single_constraint(
                constraint, default_region, model_years
            )

            if constraint_rows:
                params_by_category[category].append({
                    "name": constraint_name,
                    "description": constraint.get("description", ""),
                    "rows": constraint_rows,
                    "tag": "~UC_T",
                    "uc_sets": {"R_E": "AllRegions", "T_E": ""},
                })

        if variant_rows:
            params_by_category["technology_assumptions"].append(
                {
                    "name": f"{case_name}_variant_overrides",
                    "description": "Generated from case.variant_overrides",
                    "rows": variant_rows,
                    "tag": "~TFM_INS",
                }
            )

        # Build files for each category
        case_scenario_files = []
        for category, items in sorted(params_by_category.items()):
            if not items:
                continue

            # Build sheets - one sheet per category with all tables
            sheets = []

            # Group items by tag (TFM_DINS-AT vs UC_T)
            tfm_items = [i for i in items if i["tag"] == "~TFM_DINS-AT"]
            tfm_ins_items = [i for i in items if i["tag"] == "~TFM_INS"]
            uc_items = [i for i in items if i["tag"] == "~UC_T"]

            # Build TFM sheet with all scenario parameter rows
            if tfm_items:
                all_tfm_rows = []
                for item in tfm_items:
                    all_tfm_rows.extend(item["rows"])

                # Sheet name based on category
                sheet_name = _category_to_sheet_name(category)
                sheets.append({
                    "name": sheet_name,
                    "tables": [{"tag": "~TFM_DINS-AT", "rows": all_tfm_rows}],
                })

            if tfm_ins_items:
                all_tfm_ins_rows = []
                for item in tfm_ins_items:
                    all_tfm_ins_rows.extend(item["rows"])
                sheet_name = _category_to_sheet_name(category)
                if tfm_items:
                    sheet_name = f"{sheet_name}Attributes"
                sheets.append(
                    {
                        "name": sheet_name,
                        "tables": [{"tag": "~TFM_INS", "rows": all_tfm_ins_rows}],
                    }
                )

            # Build UC sheets - ONE ~UC_T per constraint (not merged)
            for uc_item in uc_items:
                sheets.append({
                    "name": uc_item["name"],
                    "tables": [{
                        "tag": "~UC_T",
                        "uc_sets": uc_item.get("uc_sets", {}),
                        "rows": uc_item["rows"],
                    }],
                })

            # Create file for this case+category (lowercase paths)
            file_path = f"suppxls/scen_{case_name.lower()}_{category.lower()}.xlsx"
            scenario_files.append({
                "path": file_path,
                "sheets": sheets,
            })
            case_scenario_files.append(file_path)

        # Build case metadata for cases.json
        cases_json.append({
            "name": case_name,
            "description": case.get("description", ""),
            "is_baseline": case.get("is_baseline", False),
            "scenario_files": case_scenario_files,
            "tags": case.get("tags", []),
        })

    return scenario_files, cases_json


def _category_to_sheet_name(category: str) -> str:
    """Convert category to human-readable sheet name."""
    mapping = {
        "demands": "Demands",
        "prices": "Prices",
        "policies": "Policies",
        "technology_assumptions": "TechAssumptions",
        "resource_availability": "Resources",
        "global_settings": "Settings",
    }
    return mapping.get(category, category.title())


def _compile_single_constraint(
    constraint: dict,
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile a single constraint to ~UC_T rows.

    Args:
        constraint: Constraint definition
        region: Default region
        model_years: List of model years

    Returns:
        List of ~UC_T rows for this constraint
    """
    constraint_type = constraint["type"]
    uc_name = constraint["name"]
    commodity = constraint.get("commodity")
    limtype = constraint.get("limtype", "up").upper()

    if constraint_type == "emission_cap":
        return _compile_emission_cap(
            uc_name, commodity, constraint, region, model_years, limtype
        )
    elif constraint_type == "activity_share":
        return _compile_activity_share(
            uc_name, commodity, constraint, region, model_years
        )

    return []


def _compile_trade_links(
    trade_links: list[dict],
    commodities: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Compile trade link definitions to TableIR structures.

    Emits ONLY ~TRADELINKS tables - VEDA/xl2times auto-generates trade processes
    (IRE) from these tables. This avoids PCG conflicts that occur when both
    ~TRADELINKS and explicit ~FI_PROCESS declarations exist for the same trades.

    Trade attributes (efficiency) are emitted via ~TFM_INS tables using long
    format (attribute + value columns) targeting the auto-generated process names.

    Matrix format:
    - Sheet name uses Bi_ or Uni_ prefix for compatibility (e.g., Bi_ELC, Uni_NG)
    - First column is commodity name, contains origin (FROM) region
    - Other columns are destination (TO) regions
    - Cell value is 1 for enabled trade (auto-naming), 0 or empty for no trade

    Bilateral trade representation:
    - Bidirectional trade requires BOTH directions in the matrix
    - For REG1↔REG2: one row with REG1→REG2, another with REG2→REG1
    - This explicitly represents both flows; we don't rely on sheet prefix alone

    Process auto-naming: VEDA/xl2times generates process names automatically
    from the matrix structure when cells contain 1.

    Args:
        trade_links: List of trade link definitions from VedaLang source
        commodities: List of commodity definitions (unused, kept for API compat)

    Returns:
        Tuple of:
        - List of TableIR file definitions (ScenTrade file with ~TRADELINKS)
        - List of TFM rows for trade attributes (efficiency, etc.)
    """
    if not trade_links:
        return [], []

    from collections import defaultdict

    def _safe_trade_sheet_name(direction: str, commodity_name: str) -> str:
        """Build an Excel-safe trade sheet name from direction and commodity."""
        raw = f"{direction}_{commodity_name}"
        safe = re.sub(r"[:\\/?*\[\]]", "_", raw)
        return safe[:31]

    # Group trade links by commodity and bidirectional flag
    grouped: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for link in trade_links:
        commodity = link["commodity"]
        bidirectional = link.get("bidirectional", True)
        grouped[(commodity, bidirectional)].append(link)

    # Build sheets for trade links (matrix format)
    tradelink_sheets = []
    tfm_rows = []  # TFM rows for trade attributes

    for (commodity, bidirectional), links in grouped.items():
        # Sheet name encodes direction and commodity (kept for compatibility)
        direction = "Bi" if bidirectional else "Uni"
        sheet_name = _safe_trade_sheet_name(direction, commodity)

        # Collect all unique regions for matrix columns
        all_regions: set[str] = set()
        for link in links:
            all_regions.add(link["origin"])
            all_regions.add(link["destination"])

        # Build directed edges - for bilateral, expand to both directions
        # This is the key change: bilateral creates BOTH A→B and B→A edges
        directed_edges: list[tuple[str, str, float | None]] = []
        for link in links:
            origin = link["origin"]
            dest = link["destination"]
            efficiency = link.get("efficiency")

            # Add forward direction
            directed_edges.append((origin, dest, efficiency))

            # For bilateral, also add reverse direction
            if bidirectional:
                directed_edges.append((dest, origin, efficiency))

        # Group edges by origin for matrix rows
        edges_by_origin: dict[str, list[tuple[str, float | None]]] = defaultdict(list)
        for origin, dest, eff in directed_edges:
            edges_by_origin[origin].append((dest, eff))

        # Build matrix rows - one row per origin region
        rows = []
        for origin in sorted(edges_by_origin.keys()):
            row: dict = {commodity: origin}
            for dest, efficiency in edges_by_origin[origin]:
                # Cell value: 1 for auto-naming (VEDA generates process names).
                row[dest] = 1

                # Emit EFF for trade processes with efficiency
                # xl2times transforms EFF on IRE processes to IRE_FLO
                if efficiency is not None:
                    _validate_attribute_for_emission("efficiency", "TFM_INS")
                    tfm_rows.append({
                        "region": origin,
                        "pset_pn": f"TB_{commodity}_*,TU_{commodity}_*",
                        "attribute": "EFF",
                        "value": efficiency,
                    })

            rows.append(row)

        tradelink_sheets.append({
            "name": sheet_name,
            "tables": [{"tag": "~TRADELINKS", "rows": rows}],
        })

    # Build files list
    files = []

    # Trade links file with ~TRADELINKS tables only
    if tradelink_sheets:
        files.append({
            "path": "suppxls/trades/scentrade__trade_links.xlsx",
            "sheets": tradelink_sheets,
        })

    # Trade attributes file with TFM_INS if we have any attributes
    if tfm_rows:
        files.append({
            "path": "suppxls/trades/scentrade__trade_attrs.xlsx",
            "sheets": [{
                "name": "Attributes",
                "tables": [{"tag": "~TFM_INS", "rows": tfm_rows}],
            }],
        })

    return files, tfm_rows


def _compile_timeslices(
    timeslices: dict,
    regions: list[str],
) -> tuple[list[dict], list[dict]]:
    """
    Compile timeslice definitions to TableIR tables.

    Generates:
    1. ~TIMESLICES table with season/weekly/daynite columns
    2. ~TFM_INS rows with attribute=YRFR for year fractions

    The ~TIMESLICES table format emits **independent columns** (a ragged table).
    xl2times extracts unique values from each column, then internally creates
    the cross-product and concatenates them to form leaf timeslice names.

    For example, with seasons [S, W] and daynites [D, N], we emit:
        Season | Weekly | DayNite
        S      |        | D
        W      |        | N

    xl2times will:
    1. Extract unique seasons: {S, W}
    2. Extract unique daynites: {D, N}
    3. Create cross-product: SD, SN, WD, WN

    Args:
        timeslices: Timeslice definition from VedaLang source
        regions: List of region codes

    Returns:
        Tuple of (timeslice_rows, yrfr_rows)

    Raises:
        ValueError: If user-provided fractions keys don't match expected leaves
    """
    season_codes = [s["code"] for s in timeslices.get("season", [])]
    weekly_codes = [w["code"] for w in timeslices.get("weekly", [])]
    daynite_codes = [d["code"] for d in timeslices.get("daynite", [])]

    # Validate fractions keys match expected leaf names
    fractions = timeslices.get("fractions", {})
    if fractions:
        expected_leaves = set(_generate_leaf_timeslices(
            season_codes, weekly_codes, daynite_codes
        ))
        user_leaves = set(fractions.keys())
        if user_leaves != expected_leaves:
            missing = expected_leaves - user_leaves
            extra = user_leaves - expected_leaves
            msg_parts = ["Timeslice fractions mismatch:"]
            if missing:
                msg_parts.append(f"  Missing: {sorted(missing)}")
            if extra:
                msg_parts.append(f"  Unknown: {sorted(extra)}")
            msg_parts.append(
                f"  Expected leaves from level codes: {sorted(expected_leaves)}"
            )
            raise ValueError("\n".join(msg_parts))

    # =========================================================================
    # WARNING: DO NOT "FIX" THIS TO EMIT A CROSS-PRODUCT!
    #
    # This emits a "ragged table" where each column independently lists its
    # level codes. This looks strange, but it's exactly what xl2times expects.
    #
    # xl2times extracts unique values from each column via pandas unique(),
    # then uses merge(..., how="cross") to create the cartesian product.
    # See: xl2times/transforms.py::process_time_slices() around line 3334.
    #
    # Example: seasons=[S,W], daynites=[D,N] emits 2 rows, NOT 4 rows:
    #     Season | DayNite     (NOT: Season | DayNite)
    #     S      | D                 (S      | D      )
    #     W      | N                 (S      | N      )
    #                                (W      | D      )
    #                                (W      | N      )
    #
    # This is a peculiarity of VEDA's table format. Trust the docstring.
    # =========================================================================
    timeslice_rows = []

    # Determine the maximum number of rows needed (ragged - columns vary)
    max_rows = max(len(season_codes), len(weekly_codes), len(daynite_codes), 1)

    for i in range(max_rows):
        row = {
            "season": season_codes[i] if i < len(season_codes) else "",
            "weekly": weekly_codes[i] if i < len(weekly_codes) else "",
            "daynite": daynite_codes[i] if i < len(daynite_codes) else "",
        }
        # Skip if all columns are empty
        if not row["season"] and not row["weekly"] and not row["daynite"]:
            continue
        timeslice_rows.append(row)

    # Build ~TFM_INS rows for year fractions
    yrfr_rows = []
    if fractions:
        _validate_attribute_for_emission("G_YRFR", "TFM_INS")
    for ts_name, fraction in fractions.items():
        # YRFR applies to all regions via allregions column
        yrfr_rows.append({
            "timeslice": ts_name,
            "attribute": "YRFR",
            "allregions": fraction,
        })

    return timeslice_rows, yrfr_rows


def _generate_leaf_timeslices(
    seasons: list[str],
    weeklies: list[str],
    daynites: list[str],
) -> list[str]:
    """
    Generate explicit leaf timeslice names by concatenating level codes.

    The leaf timeslice name is formed by concatenating codes from each level
    in order: season + weekly + daynite.

    Args:
        seasons: List of season codes (e.g., ["S", "W"])
        weeklies: List of weekly codes (e.g., [])
        daynites: List of daynite codes (e.g., ["D", "N"])

    Returns:
        List of leaf timeslice names (e.g., ["SD", "SN", "WD", "WN"])
    """
    import itertools

    # Use [""] as placeholder for empty levels to ensure product works
    s_list = seasons if seasons else [""]
    w_list = weeklies if weeklies else [""]
    d_list = daynites if daynites else [""]

    leaves = []
    for s, w, d in itertools.product(s_list, w_list, d_list):
        leaf = s + w + d
        if leaf:  # Only add non-empty leaf names
            leaves.append(leaf)

    return leaves


def _compile_constraints(
    constraints: list[dict],
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile constraint definitions to TableIR files with ~UC_T tables.

    Supports two constraint types:
    1. emission_cap: Bounds on commodity production (uses UC_COMPRD + UC_RHSRT)
    2. activity_share: Share constraints on process activity (uses UC_ACT + UC_RHSRT)

    Args:
        constraints: List of constraint definitions from VedaLang source
        region: Default region for the model
        model_years: List of model representative years

    Returns:
        List of TableIR file definitions containing ~UC_T tables
    """
    if not constraints:
        return []

    uc_rows = []

    for constraint in constraints:
        constraint_type = constraint["type"]
        uc_name = constraint["name"]
        commodity = constraint.get("commodity")
        limtype = constraint.get("limtype", "up").upper()

        if constraint_type == "emission_cap":
            uc_rows.extend(
                _compile_emission_cap(
                    uc_name, commodity, constraint, region, model_years, limtype
                )
            )
        elif constraint_type == "activity_share":
            uc_rows.extend(
                _compile_activity_share(
                    uc_name, commodity, constraint, region, model_years
                )
            )

    if not uc_rows:
        return []

    # Build UC file with uc_sets metadata
    # Default UC scope: R_E (each region), T_E (each period)
    # This tells xl2times how to expand the constraints
    return [
        {
            "path": "SuppXLS/Scen_UC_Constraints.xlsx",
            "sheets": [
                {
                    "name": "UC_Constraints",
                    "tables": [
                        {
                            "tag": "~UC_T",
                            "uc_sets": {
                                "R_E": "AllRegions",
                                "T_E": "",
                            },
                            "rows": uc_rows,
                        }
                    ],
                }
            ],
        }
    ]


def _compile_emission_cap(
    uc_name: str,
    commodity: str,
    constraint: dict,
    region: str,
    model_years: list[int],
    limtype: str,
) -> list[dict]:
    """
    Compile an emission_cap constraint to ~UC_T rows.

    VedaOnline compatibility: uses attribute name as column header (not 'value').
    UC_N is the row identifier, UC_RHS is the column header for RHS values.

    Emission cap uses:
    - UC_COMPRD with coefficient 1 (LHS side) to sum commodity production
    - UC_RHS with the limit value (RHS side)

    Args:
        uc_name: Constraint name
        commodity: Target commodity to cap
        constraint: Full constraint definition
        region: Model region
        model_years: List of model years
        limtype: Limit type (UP, LO, FX)

    Returns:
        List of ~UC_T rows
    """
    rows = []

    # Get RHS values - either single limit or year-specific
    if "years" in constraint:
        sparse_values = constraint["years"]
        interpolation = constraint.get("interpolation", "interp_extrap")
        dense_values = _expand_series_to_years(
            sparse_values, model_years, interpolation
        )
    elif "limit" in constraint:
        # Single limit applies to all years
        dense_values = {y: constraint["limit"] for y in model_years}
    else:
        # No limit specified - skip this constraint
        return []

    # Emit LHS coefficient row: UC_COMPRD for the commodity
    # Use uc_comprd as column header (lowercase for xl2times)
    description = f"Emission cap on {commodity}"
    for year in sorted(dense_values.keys()):
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "process": "",
            "commodity": commodity,
            "side": "LHS",
            "uc_comprd": 1,
        })

    # Use uc_rhsrt (region + year variant) for year-specific RHS values
    # UC_RHSRT indexes: [region, uc_n, year, limtype]
    for year in sorted(dense_values.keys()):
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "process": "",
            "commodity": "",
            "limtype": limtype,
            "uc_rhsrt": dense_values[year],
        })

    return rows


def _compile_activity_share(
    uc_name: str,
    commodity: str,
    constraint: dict,
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile an activity_share constraint to ~UC_T rows.

    Activity share uses:
    - UC_ACT with coefficient 1 for target processes (LHS)
    - UC_ACT with -share for all processes producing the commodity (LHS)
    - UC_RHSRT with 0 (constraint is: target >= share * total)

    For minimum_share: limtype=LO; for maximum_share: limtype=UP.

    Simplified approach: use commodity production as the denominator.

    Args:
        uc_name: Constraint name
        commodity: Reference commodity (e.g., ELC)
        constraint: Full constraint definition
        region: Model region
        model_years: List of model years

    Returns:
        List of ~UC_T rows
    """
    rows = []
    processes = constraint.get("processes", [])
    minimum_share = constraint.get("minimum_share")
    maximum_share = constraint.get("maximum_share")

    if not processes:
        return []

    # Generate rows for minimum share constraint
    if minimum_share is not None:
        rows.extend(
            _compile_share_constraint(
                uc_name + "_LO" if maximum_share is not None else uc_name,
                commodity,
                processes,
                minimum_share,
                "LO",
                region,
                model_years,
            )
        )

    # Generate rows for maximum share constraint
    if maximum_share is not None:
        rows.extend(
            _compile_share_constraint(
                uc_name + "_UP" if minimum_share is not None else uc_name,
                commodity,
                processes,
                maximum_share,
                "UP",
                region,
                model_years,
            )
        )

    return rows


def _compile_share_constraint(
    uc_name: str,
    commodity: str,
    processes: list[str],
    share: float,
    limtype: str,
    region: str,
    model_years: list[int],
) -> list[dict]:
    """
    Compile a single share constraint (either min or max).

    VedaOnline compatibility: uses attribute name as column header (not 'value').
    UC_ACT, UC_COMPRD, UC_RHS become column headers.

    The constraint is: sum(process_act) - share * commodity_prod {>= | <=} 0.

    Args:
        uc_name: Constraint name
        commodity: Reference commodity
        processes: Target processes
        share: Share value (0-1)
        limtype: LO for minimum, UP for maximum
        region: Model region
        model_years: List of model years

    Returns:
        List of ~UC_T rows
    """
    rows = []
    bound_type = "minimum" if limtype == "LO" else "maximum"
    description = f"Activity share ({bound_type} {share:.0%}) on {commodity}"

    for year in model_years:
        # LHS: Add target process activities with coefficient 1
        # Use uc_act as column header (lowercase for xl2times)
        for process in processes:
            rows.append({
                "uc_n": uc_name,
                "description": description,
                "region": region,
                "year": year,
                "process": process,
                "commodity": "",
                "side": "LHS",
                "uc_act": 1,
            })

        # LHS: Subtract share * commodity production
        # Use uc_comprd as column header (lowercase for xl2times)
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "process": "",
            "commodity": commodity,
            "side": "LHS",
            "uc_comprd": -share,
        })

        # RHS: The bound is 0
        # Use uc_rhsrt (region + year variant) since we have year-specific constraints
        rows.append({
            "uc_n": uc_name,
            "description": description,
            "region": region,
            "year": year,
            "process": "",
            "commodity": "",
            "limtype": limtype,
            "uc_rhsrt": 0,
        })

    return rows


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
