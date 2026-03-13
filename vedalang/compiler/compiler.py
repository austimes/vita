"""VedaLang to TableIR compiler."""

import json
import re
from functools import lru_cache
from pathlib import Path

import jsonschema
import yaml
from pint import UnitRegistry
from pint.errors import DimensionalityError, UndefinedUnitError

from vedalang.versioning import with_dsl_version

from .backend import CompileBundle, compile_source_bundle
from .registry import VedaLangError, get_registry

SCHEMA_DIR = Path(__file__).parent.parent / "schema"

# Unit categories for semantic validation
ENERGY_UNITS = {"PJ", "TJ", "GJ", "MWh", "GWh", "TWh", "MTOE", "KTOE"}
POWER_UNITS = {"GW", "MW", "kW", "TW"}
MASS_UNITS = {"Mt", "kt", "t", "Gt"}
CURRENCY_UNITS = {"USD", "kUSD", "MUSD", "BUSD"}
SERVICE_UNITS = {"Bvkm"}
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
        # Preserve scalar shorthand as a single row when no year expansion is needed
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


def load_vedalang_schema() -> dict:
    """Load the VedaLang JSON schema."""
    with open(SCHEMA_DIR / "vedalang.schema.json") as f:
        return json.load(f)


def load_tableir_schema() -> dict:
    """Load the TableIR JSON schema."""
    with open(SCHEMA_DIR / "tableir.schema.json") as f:
        return json.load(f)


def validate_vedalang(source: dict) -> None:
    """Validate VedaLang source against the active public schema."""
    jsonschema.validate(source, load_vedalang_schema())


def compile_vedalang_bundle(
    source: dict,
    validate: bool = True,
    selected_cases: list[str] | None = None,
    selected_run: str | None = None,
    packages: dict | None = None,
    site_region_memberships: dict[str, str | list[str]] | None = None,
    site_zone_memberships: dict[str, dict[str, str | list[str]]] | None = None,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
) -> CompileBundle:
    """Compile a public source into a normalized bundle."""
    del selected_cases
    bundle = compile_source_bundle(
        source,
        validate_source=validate_vedalang if validate else None,
        selected_run=selected_run,
        packages=packages,
        site_region_memberships=site_region_memberships,
        site_zone_memberships=site_zone_memberships,
        measure_weights=measure_weights,
        custom_weights=custom_weights,
    )
    if validate:
        _validate_compiled_tableir(bundle.tableir)
    return bundle


def _validate_compiled_tableir(tableir: dict) -> None:
    """Validate a compiled TableIR artifact against schema and table contracts."""
    tableir_schema = load_tableir_schema()
    jsonschema.validate(tableir, tableir_schema)

    from .table_schemas import TableValidationError, validate_tableir

    table_errors = validate_tableir(tableir)
    if table_errors:
        raise TableValidationError(table_errors)


def compile_vedalang_to_tableir(
    source: dict,
    validate: bool = True,
    selected_cases: list[str] | None = None,
    selected_run: str | None = None,
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
    del selected_cases
    bundle = compile_source_bundle(
        source,
        validate_source=validate_vedalang if validate else None,
        selected_run=selected_run,
    )
    if validate:
        _validate_compiled_tableir(bundle.tableir)
    return bundle.tableir


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
                # Scalar bound without milestone_years: emit a single row
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


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        source = yaml.safe_load(f)
    if not isinstance(source, dict):
        return source
    return with_dsl_version(source)
