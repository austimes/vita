"""VedaLang to TableIR compiler."""

import json
from difflib import get_close_matches
from pathlib import Path

import jsonschema
import yaml

from .registry import VedaLangError, get_registry

SCHEMA_DIR = Path(__file__).parent.parent / "schema"

# Unit categories for semantic validation
ENERGY_UNITS = {"PJ", "TJ", "GJ", "MWh", "GWh", "TWh", "MTOE", "KTOE"}
POWER_UNITS = {"GW", "MW", "kW", "TW"}
MASS_UNITS = {"Mt", "kt", "t", "Gt"}

# Default units by commodity type
DEFAULT_UNITS = {
    "energy": "PJ",
    "demand": "PJ",
    "emission": "Mt",
    "material": "Mt",
}

# Capacity-to-activity conversion factors (PRC_CAPACT)
# When capacity is in power units (GW) and activity is in energy units (PJ),
# we need to specify how much activity 1 unit of capacity can produce per year.
# Formula: 1 GW × 8760 hours × 3600 seconds / 1e15 J/PJ = 31.536 PJ/GW/year
CAP2ACT_CONVERSIONS = {
    # (capacity_unit, activity_unit): conversion_factor
    ("GW", "PJ"): 31.536,
    ("GW", "TWh"): 8.76,
    ("MW", "GWh"): 8.76,
    ("MW", "PJ"): 0.031536,
    ("TW", "PJ"): 31536.0,
}

# Process attributes that support time-varying values
TIME_VARYING_ATTRS = {
    "efficiency", "investment_cost", "fixed_om_cost", "variable_om_cost",
    "import_price", "lifetime", "availability_factor",
    # Note: emission_factor also supports time-varying but is handled separately
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


def validate_cross_references(model: dict) -> tuple[list[str], list[str]]:
    """
    Validate semantic cross-references in the model.

    Checks that all referenced commodities, processes, and regions exist,
    and that scenario types target appropriate commodity types.

    Args:
        model: The model dictionary from VedaLang source

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Build lookup sets
    commodities = {c["name"]: c for c in model.get("commodities", [])}
    commodity_names = set(commodities.keys())
    processes = {p["name"] for p in model.get("processes", [])}
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

    # Validate process references
    for raw_process in model.get("processes", []):
        # Normalize shorthand syntax before validation
        process = _normalize_process_flows(raw_process)
        proc_name = process["name"]

        # Check input commodity references
        for i, inp in enumerate(process.get("inputs", [])):
            comm = inp["commodity"]
            if comm not in commodity_names:
                hint = suggest_commodity(comm)
                errors.append(
                    f"Unknown commodity '{comm}' in process "
                    f"'{proc_name}' inputs[{i}].{hint}"
                )

        # Check output commodity references
        for i, out in enumerate(process.get("outputs", [])):
            comm = out["commodity"]
            if comm not in commodity_names:
                hint = suggest_commodity(comm)
                errors.append(
                    f"Unknown commodity '{comm}' in process "
                    f"'{proc_name}' outputs[{i}].{hint}"
                )

        # Check unit compatibility (warnings only)
        activity_unit = process.get("activity_unit")
        if activity_unit and activity_unit not in ENERGY_UNITS:
            warnings.append(
                f"Process '{proc_name}' has activity_unit '{activity_unit}' "
                f"which is not a recognized energy unit. "
                f"Expected one of: {', '.join(sorted(ENERGY_UNITS))}"
            )

        capacity_unit = process.get("capacity_unit")
        if capacity_unit and capacity_unit not in POWER_UNITS:
            warnings.append(
                f"Process '{proc_name}' has capacity_unit '{capacity_unit}' "
                f"which is not a recognized power unit. "
                f"Expected one of: {', '.join(sorted(POWER_UNITS))}"
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
            if commodity not in commodity_names:
                hint = suggest_commodity(commodity)
                errors.append(
                    f"Unknown commodity '{commodity}' in scenario "
                    f"'{scenario_name}'.{hint}"
                )
            else:
                # Check commodity type matches scenario type
                comm_info = commodities[commodity]
                comm_type = comm_info.get("type", "energy")

                if scenario_type == "demand_projection":
                    if comm_type != "demand":
                        errors.append(
                            f"demand_projection scenario '{scenario_name}' targets "
                            f"commodity '{commodity}' (type '{comm_type}'), "
                            "expected 'demand'"
                        )

                elif scenario_type == "commodity_price":
                    if comm_type == "demand":
                        errors.append(
                            f"commodity_price scenario '{scenario_name}' targets "
                            f"commodity '{commodity}' (type 'demand'), "
                            "expected non-demand type"
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


def compile_vedalang_to_tableir(source: dict, validate: bool = True) -> dict:
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
        comm_type = commodity.get("type", "energy")
        # Use explicit unit or default based on commodity type
        unit = commodity.get("unit") or _get_default_unit(comm_type)
        comm_rows.append({
            "region": default_region,
            "csets": _commodity_type_to_csets(comm_type),
            "commodity": commodity["name"],
            "unit": unit,
        })

    # Build process table (~FI_PROCESS)
    # Use lowercase column names for xl2times compatibility
    # primary_commodity_group is REQUIRED in schema - use directly, no inference
    process_rows = []
    for raw_process in model.get("processes", []):
        # Normalize shorthand input/output syntax
        process = _normalize_process_flows(raw_process)
        process_rows.append({
            "region": default_region,
            "process": process["name"],
            "description": process.get("description", ""),
            "sets": ",".join(process.get("sets", [])),
            "tact": process.get("activity_unit", "PJ"),
            "tcap": process.get("capacity_unit", "GW"),
            "primarycg": process["primary_commodity_group"],
        })

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
        cap2act_key = (capacity_unit, activity_unit)
        if cap2act_key in CAP2ACT_CONVERSIONS:
            cost_params["prc_capact"] = CAP2ACT_CONVERSIONS[cap2act_key]

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
    currencies_rows = [{"currency": "USD"}]

    # G_DRATE - discount rate (required for TIMES to process costs)
    # Without G_DRATE, rdcur set is empty and all cost parameters are ignored
    # Default: 5% discount rate; can be overridden via model.discount_rate
    discount_rate = model.get("discount_rate", 0.05)
    gdrate_rows = [
        {
            "region": r,
            "attribute": "G_DRATE",
            "currency": "USD",
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

    # Build scenario files organized by case and category
    scenario_files, cases_json = _compile_scenario_files(
        scenario_params,
        model.get("constraints", []),
        cases,
        regions,
        model_years,
        default_region,
    )

    # Compile timeslices if defined
    timeslice_rows = []
    yrfr_rows = []
    if "timeslices" in model:
        timeslice_rows, yrfr_rows = _compile_timeslices(
            model["timeslices"], regions
        )

    # Build SysSets tables list
    # Note: ~MILESTONEYEARS is an alternative to ~ACTIVEPDEF + ~TIMEPERIODS
    # We use ~MILESTONEYEARS for explicit control over milestone years
    syssets_tables = [
        {"tag": "~BOOKREGIONS_MAP", "rows": bookregions_rows},
        {"tag": "~STARTYEAR", "rows": startyear_rows},
        {"tag": "~MILESTONEYEARS", "rows": milestoneyears_rows},
        {"tag": "~CURRENCIES", "rows": currencies_rows},
    ]

    # Add timeslice table if defined
    if timeslice_rows:
        syssets_tables.append({"tag": "~TIMESLICES", "rows": timeslice_rows})

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
    """Map VedaLang commodity type to VEDA Csets."""
    mapping = {
        "energy": "NRG",
        "material": "MAT",
        "emission": "ENV",
        "demand": "DEM",
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
    for region in regions:
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
    for region in regions:
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


def _compile_scenario_files(
    scenario_params: list[dict],
    constraints: list[dict],
    cases: list[dict],
    regions: list[str],
    model_years: list[int],
    default_region: str,
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

    for case in cases:
        case_name = case["name"]
        includes = set(case.get("includes", []))
        excludes = set(case.get("excludes", []))

        # Group parameters by category for this case
        params_by_category: dict[str, list[dict]] = defaultdict(list)

        for param in scenario_params:
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
        for constraint in constraints:
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

        # Build files for each category
        case_scenario_files = []
        for category, items in sorted(params_by_category.items()):
            if not items:
                continue

            # Build sheets - one sheet per category with all tables
            sheets = []

            # Group items by tag (TFM_DINS-AT vs UC_T)
            tfm_items = [i for i in items if i["tag"] == "~TFM_DINS-AT"]
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
        sheet_name = f"{direction}_{commodity}"

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
            "limtype": limtype,
            "uc_rhsrt": 0,
        })

    return rows


def load_vedalang(path: Path) -> dict:
    """Load VedaLang source from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
