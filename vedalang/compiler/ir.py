"""Process IR structures for VedaLang compiler.

This module provides the intermediate representation (IR) for processes:
- Role: abstract transformation (topology)
- Variant: concrete technology implementing a role
- InstanceKey: unique identifier for (variant, region, segment)
- ProcessInstance: fully resolved process instance with merged attributes

The IR pipeline:
1. build_roles() - parse process_roles, validate commodity refs
2. build_variants() - parse process_variants, resolve role refs
3. expand_availability() - expand availability entries into instance keys
4. apply_process_parameters() - apply selector-matched overrides
5. lower_instances_to_tableir() - convert to TableIR process rows
"""

from dataclasses import dataclass, field
from typing import NamedTuple

from .naming import NamingRegistry
from .segments import (
    build_segments,
    get_scoped_commodity_id,
    normalize_commodity,
)


@dataclass
class Role:
    """Abstract process transformation (topology definition).

    Roles define what transformations exist without specifying costs or
    efficiencies. Multiple variants can implement the same role.

    Attributes:
        id: Role identifier (verb_phrase, e.g., "deliver_lighting")
        inputs: List of input commodity IDs
        outputs: List of output commodity IDs
        stage: Optional stage classification (supply, conversion, end_use, etc.)
    """

    id: str
    inputs: list[str]
    outputs: list[str]
    stage: str | None = None


@dataclass
class Variant:
    """Concrete technology implementing a process role.

    Variants carry numeric parameters (efficiency, costs, lifetime, emissions).
    Multiple variants can implement the same role, competing in optimization.

    Attributes:
        id: Variant identifier (snake_case technology name)
        role: The Role this variant implements
        attrs: Dict of variant attributes (efficiency, lifetime, costs, etc.)
    """

    id: str
    role: Role
    attrs: dict = field(default_factory=dict)


class InstanceKey(NamedTuple):
    """Unique identifier for a process instance.

    Each (variant, region, segment) combination creates a distinct TIMES process.

    Attributes:
        variant_id: Reference to Variant.id
        region: Region code
        segment: Segment key (e.g., "RES", "RES.lighting") or None for supply-side
    """

    variant_id: str
    region: str
    segment: str | None


@dataclass
class ProcessInstance:
    """Fully resolved process instance.

    Represents a concrete TIMES process with all attributes merged from
    variant defaults and process_parameters overrides.

    Attributes:
        key: InstanceKey identifying this instance
        role: The Role from the variant
        variant: The Variant this instance derives from
        attrs: Merged attributes (variant attrs + process_parameters overrides)
    """

    key: InstanceKey
    role: Role
    variant: Variant
    attrs: dict = field(default_factory=dict)


class IRError(Exception):
    """Error during IR construction."""

    pass


def build_roles(
    model: dict,
    commodities: dict[str, dict],
) -> dict[str, Role]:
    """Build Role objects from process_roles, validating commodity refs.

    Args:
        model: Model dict with 'process_roles' key
        commodities: Dict mapping commodity id to normalized commodity dict

    Returns:
        Dict mapping role id to Role object

    Raises:
        IRError: If duplicate role id or invalid commodity reference
    """
    roles: dict[str, Role] = {}
    process_roles = model.get("process_roles") or []

    for raw in process_roles:
        role_id = raw["id"]

        if role_id in roles:
            raise IRError(f"Duplicate role id: {role_id}")

        inputs = []
        for inp in raw.get("inputs") or []:
            comm_id = inp["commodity"]
            if comm_id not in commodities:
                raise IRError(
                    f"Role '{role_id}' references unknown input commodity: {comm_id}"
                )
            inputs.append(comm_id)

        outputs = []
        for out in raw.get("outputs") or []:
            comm_id = out["commodity"]
            if comm_id not in commodities:
                raise IRError(
                    f"Role '{role_id}' references unknown output commodity: {comm_id}"
                )
            outputs.append(comm_id)

        roles[role_id] = Role(
            id=role_id,
            inputs=inputs,
            outputs=outputs,
            stage=raw.get("stage"),
        )

    return roles


def build_variants(
    model: dict,
    roles: dict[str, Role],
) -> dict[str, Variant]:
    """Build Variant objects from process_variants, resolving role refs.

    Args:
        model: Model dict with 'process_variants' key
        roles: Dict mapping role id to Role object

    Returns:
        Dict mapping variant id to Variant object

    Raises:
        IRError: If duplicate variant id or invalid role reference
    """
    variants: dict[str, Variant] = {}
    process_variants = model.get("process_variants") or []

    attr_keys = {
        "efficiency",
        "lifetime",
        "investment_cost",
        "fixed_om_cost",
        "variable_om_cost",
        "emission_factors",
    }

    for raw in process_variants:
        variant_id = raw["id"]
        role_id = raw["role"]

        if variant_id in variants:
            raise IRError(f"Duplicate variant id: {variant_id}")

        if role_id not in roles:
            raise IRError(
                f"Variant '{variant_id}' references unknown role: {role_id}"
            )

        attrs = {}
        for key in attr_keys:
            if key in raw:
                attrs[key] = raw[key]

        variants[variant_id] = Variant(
            id=variant_id,
            role=roles[role_id],
            attrs=attrs,
        )

    return variants


def _expand_sectors_to_segments(
    sectors: list[str],
    segment_keys: list[str],
    has_end_uses: bool,
) -> list[str]:
    """Expand sector list to matching segment keys.

    If model has end_uses, expand each sector to all matching sector.end_use
    combinations. Otherwise, use sectors directly as segment keys.

    Args:
        sectors: List of sector codes (e.g., ["RES", "COM"])
        segment_keys: Full list of segment keys from build_segments()
        has_end_uses: Whether model has end_uses defined

    Returns:
        List of segment keys matching the sectors
    """
    if not has_end_uses:
        return list(sectors)

    expanded = []
    for seg in segment_keys:
        sector = seg.split(".")[0] if "." in seg else seg
        if sector in sectors:
            expanded.append(seg)
    return expanded


def expand_availability(
    model: dict,
    variants: dict[str, Variant],
    segment_keys: list[str],
) -> dict[InstanceKey, ProcessInstance]:
    """Expand availability entries into concrete process instances.

    Rules:
    - If availability.segments specified: use those exact segment keys
    - If availability.sectors specified:
      - If model has end_uses: expand to all matching sector.end_use combinations
      - Else: use sector as segment key
    - If neither: segment = None (supply-side/global)

    Args:
        model: Model dict with 'availability' key
        variants: Dict mapping variant id to Variant object
        segment_keys: List of segment keys from build_segments()

    Returns:
        Dict mapping InstanceKey to ProcessInstance

    Raises:
        IRError: If availability references unknown variant
    """
    instances: dict[InstanceKey, ProcessInstance] = {}
    availability = model.get("availability") or []

    seg_cfg = model.get("segments") or {}
    has_end_uses = bool(seg_cfg.get("end_uses"))

    for entry in availability:
        variant_id = entry["variant"]

        if variant_id not in variants:
            raise IRError(
                f"Availability references unknown variant: {variant_id}"
            )

        variant = variants[variant_id]
        regions = entry["regions"]

        if "segments" in entry and entry["segments"]:
            segments_to_use = entry["segments"]
        elif "sectors" in entry and entry["sectors"]:
            segments_to_use = _expand_sectors_to_segments(
                entry["sectors"], segment_keys, has_end_uses
            )
        else:
            segments_to_use = [None]

        for region in regions:
            for segment in segments_to_use:
                key = InstanceKey(variant_id, region, segment)
                if key not in instances:
                    instances[key] = ProcessInstance(
                        key=key,
                        role=variant.role,
                        variant=variant,
                        attrs=dict(variant.attrs),
                    )

    return instances


def _selector_matches(
    selector: dict,
    key: InstanceKey,
    segment_keys: list[str],
) -> bool:
    """Check if a parameter selector matches an instance key.

    Matching rules:
    - Must match variant and region exactly
    - If selector.segment: exact match with key.segment
    - If selector.sector: match any segment starting with that sector

    Args:
        selector: Parameter selector dict (variant, region, sector?, segment?)
        key: InstanceKey to check
        segment_keys: List of segment keys for context

    Returns:
        True if selector matches the key
    """
    if selector["variant"] != key.variant_id:
        return False
    if selector["region"] != key.region:
        return False

    if "segment" in selector:
        return selector["segment"] == key.segment

    if "sector" in selector:
        if key.segment is None:
            return False
        sector_prefix = key.segment.split(".")[0] if "." in key.segment else key.segment
        return sector_prefix == selector["sector"]

    return True


def apply_process_parameters(
    instances: dict[InstanceKey, ProcessInstance],
    model: dict,
) -> None:
    """Apply process_parameters blocks to matching instances.

    Mutates instances in-place, merging parameter values into attrs.

    Args:
        instances: Dict of instances to update
        model: Model dict with 'process_parameters' key
    """
    process_params = model.get("process_parameters") or []
    segment_keys = build_segments(model)

    override_keys = {
        "existing_capacity",
        "cap_bound",
        "ncap_bound",
        "activity_bound",
        "stock",
    }

    # Dict-valued keys use merge semantics (update, not replace)
    merge_keys = {
        "emission_factors",
    }

    for param_block in process_params:
        selector = param_block["selector"]

        for key, instance in instances.items():
            if _selector_matches(selector, key, segment_keys):
                for attr_key in override_keys:
                    if attr_key in param_block:
                        instance.attrs[attr_key] = param_block[attr_key]
                for attr_key in merge_keys:
                    if attr_key in param_block:
                        existing = instance.attrs.get(attr_key, {})
                        instance.attrs[attr_key] = {**existing, **param_block[attr_key]}


def _produces_service(role: Role, commodities: dict[str, dict]) -> bool:
    """Check if a role produces a service commodity."""
    for out_id in role.outputs:
        if out_id in commodities:
            comm = commodities[out_id]
            if comm.get("kind") == "service":
                return True
    return False


def _generate_process_name(
    key: InstanceKey, registry: NamingRegistry | None = None
) -> str:
    """Generate deterministic process name from instance key.

    If a NamingRegistry is provided, uses it for consistent symbol generation.
    Otherwise, generates inline: {variant_id}_{region}_{segment} or
    {variant_id}_{region} if no segment.

    Args:
        key: InstanceKey to generate name for
        registry: Optional NamingRegistry for consistent naming

    Returns:
        Deterministic process name
    """
    if registry:
        return registry.get_process_symbol(key.variant_id, key.region, key.segment)
    parts = [key.variant_id, key.region]
    if key.segment:
        parts.append(key.segment.replace(".", "_"))
    return "_".join(parts)


def lower_instances_to_tableir(
    instances: dict[InstanceKey, ProcessInstance],
    commodities: dict[str, dict],
    segment_keys: list[str],
    registry: NamingRegistry | None = None,
) -> list[dict]:
    """Convert ProcessInstance objects to TableIR process rows.

    For each instance:
    1. Generate deterministic process name: {variant_id}_{region}_{segment}
    2. Build inputs/outputs using scoped commodity IDs
    3. Include all numeric attributes
    4. Infer sets (DMD for service-producing roles)

    Args:
        instances: Dict of ProcessInstance objects
        commodities: Dict mapping commodity id to normalized commodity dict
        segment_keys: List of segment keys
        registry: Optional NamingRegistry for deterministic symbol generation

    Returns:
        List of TableIR process row dicts
    """
    rows = []

    for key, instance in sorted(instances.items()):
        role = instance.role
        attrs = instance.attrs

        prc_name = _generate_process_name(key, registry)

        inputs_scoped = []
        for inp_id in role.inputs:
            comm = commodities.get(inp_id, {})
            tradable = comm.get("tradable", True)
            kind = comm.get("kind", "carrier")
            scoped_id = get_scoped_commodity_id(inp_id, key.segment, tradable, kind)
            if registry and not tradable and kind not in ("carrier", "material"):
                scoped_id = registry.get_commodity_symbol(inp_id, key.segment)
            elif registry:
                scoped_id = registry.get_commodity_symbol(inp_id, None)
            inputs_scoped.append(scoped_id)

        outputs_scoped = []
        for out_id in role.outputs:
            comm = commodities.get(out_id, {})
            tradable = comm.get("tradable", True)
            kind = comm.get("kind", "carrier")
            scoped_id = get_scoped_commodity_id(out_id, key.segment, tradable, kind)
            if registry and not tradable and kind not in ("carrier", "material"):
                scoped_id = registry.get_commodity_symbol(out_id, key.segment)
            elif registry:
                scoped_id = registry.get_commodity_symbol(out_id, None)
            outputs_scoped.append(scoped_id)

        sets = []
        if _produces_service(role, commodities):
            sets.append("DMD")

        row: dict = {
            "prc": prc_name,
            "region": key.region,
        }

        if inputs_scoped:
            row["com_in"] = ",".join(inputs_scoped)
        if outputs_scoped:
            row["com_out"] = ",".join(outputs_scoped)
        if sets:
            row["sets"] = ",".join(sets)

        attr_map = {
            "efficiency": "eff",
            "lifetime": "ncap_tlife",
            "investment_cost": "ncap_cost",
            "fixed_om_cost": "ncap_fom",
            "variable_om_cost": "act_cost",
        }
        for vedalang_attr, tableir_col in attr_map.items():
            if vedalang_attr in attrs:
                val = attrs[vedalang_attr]
                if isinstance(val, (int, float)):
                    row[tableir_col] = val

        rows.append(row)

    return rows


def validate_demand_feasibility(
    demands: list[dict],
    instances: dict[InstanceKey, ProcessInstance],
    commodities: dict[str, dict],
) -> list[str]:
    """Validate that each demand has at least one provider.

    For each (region, segment) demand of a service commodity, there must exist
    at least one available variant whose role can produce that commodity.

    Args:
        demands: List of demand definitions
        instances: Dict of ProcessInstance objects
        commodities: Dict mapping commodity id to normalized commodity dict

    Returns:
        List of error messages (empty if all demands are feasible)
    """
    errors = []

    producer_map: dict[tuple[str, str | None, str], list[str]] = {}
    for key, instance in instances.items():
        for out_id in instance.role.outputs:
            map_key = (key.region, key.segment, out_id)
            if map_key not in producer_map:
                producer_map[map_key] = []
            producer_map[map_key].append(key.variant_id)

    for demand in demands:
        comm_id = demand["commodity"]
        region = demand["region"]
        segment = demand.get("segment") or demand.get("sector")

        map_key = (region, segment, comm_id)
        if map_key not in producer_map:
            seg_str = f" segment '{segment}'" if segment else ""
            errors.append(
                f"Demand for '{comm_id}' in region '{region}'{seg_str} "
                f"has no available producer"
            )

    return errors


def build_commodities_dict(model: dict) -> dict[str, dict]:
    """Build normalized commodities dict from model.

    Args:
        model: Model dict with 'commodities' under 'model' key

    Returns:
        Dict mapping commodity id to normalized commodity dict
    """
    commodities_raw = model.get("model", {}).get("commodities") or []
    result = {}
    for raw in commodities_raw:
        norm = normalize_commodity(raw)
        result[norm["id"]] = norm
    return result
