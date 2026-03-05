"""Process IR structures for VedaLang compiler.

This module provides the intermediate representation (IR) for processes:
- Role: abstract transformation (topology)
- Variant: concrete technology implementing a role
- InstanceKey: unique identifier for (variant, region, segment)
- ProcessInstance: fully resolved process instance with merged attributes

The IR pipeline:
1. build_roles() - parse roles, validate commodity refs
2. build_variants() - parse variants, resolve role refs
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
    """Abstract process contract (minimum required I/O).

    Roles define the service contract that any implementing variant must
    satisfy. Multiple variants can implement the same role.

    Attributes:
        id: Role identifier (verb_phrase, e.g., "deliver_lighting")
        required_inputs: Minimum required input commodity IDs
        required_outputs: Minimum required output commodity IDs
        stage: Optional stage classification (supply, conversion, end_use, etc.)
        activity_unit: Activity unit for all variants implementing this role
        capacity_unit: Capacity unit for all variants implementing this role
    """

    id: str
    required_inputs: list[str]
    required_outputs: list[str]
    stage: str | None = None
    activity_unit: str = "PJ"
    capacity_unit: str = "GW"


@dataclass
class Variant:
    """Concrete technology implementing a process role.

    Variants carry numeric parameters (efficiency, costs, lifetime, emissions)
    and declare their full explicit I/O topology. No inheritance from the role —
    variants must list all inputs and outputs they actually consume/produce.

    Attributes:
        id: Variant identifier (snake_case technology name)
        role: The Role this variant implements
        attrs: Dict of variant attributes (efficiency, lifetime, costs, etc.)
        inputs: Full list of input commodity IDs consumed by this variant
        outputs: Full list of output commodity IDs produced by this variant
    """

    id: str
    role: Role
    attrs: dict = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    modes: dict[str, "Mode"] = field(default_factory=dict)
    default_mode: str | None = None


@dataclass
class Mode:
    """Concrete operating state nested under a variant."""

    id: str
    attrs: dict = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)


@dataclass
class ProviderOffering:
    """Provider-level selection of variant + allowed modes."""

    variant_id: str
    modes: list[str] = field(default_factory=list)


@dataclass
class Provider:
    """Concrete reporting object hosting role implementations."""

    id: str
    kind: str
    role: str
    region: str
    scopes: list[str | None] = field(default_factory=list)
    offerings: list[ProviderOffering] = field(default_factory=list)


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
    provider_id: str | None = None
    mode_id: str | None = None
    provider_kind: str | None = None
    role_id: str | None = None


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
    mode: Mode | None = None
    provider: Provider | None = None
    attrs: dict = field(default_factory=dict)


class IRError(Exception):
    """Error during IR construction."""

    pass


def build_roles(
    model: dict,
    commodities: dict[str, dict],
) -> dict[str, Role]:
    """Build Role objects from roles, validating commodity refs.

    Args:
        model: Model dict with 'roles' key
        commodities: Dict mapping commodity id to normalized commodity dict

    Returns:
        Dict mapping role id to Role object

    Raises:
        IRError: If duplicate role id or invalid commodity reference
    """
    roles_by_id: dict[str, Role] = {}
    role_entries = model.get("roles") or []

    for raw in role_entries:
        role_id = raw["id"]

        if role_id in roles_by_id:
            raise IRError(f"Duplicate role id: {role_id}")

        required_inputs = []
        for inp in raw.get("required_inputs") or []:
            comm_id = inp["commodity"]
            if comm_id not in commodities:
                raise IRError(
                    f"Role '{role_id}' references unknown input commodity: {comm_id}"
                )
            required_inputs.append(comm_id)

        required_outputs = []
        for out in raw.get("required_outputs") or []:
            comm_id = out["commodity"]
            if comm_id not in commodities:
                raise IRError(
                    f"Role '{role_id}' references unknown output commodity: {comm_id}"
                )
            required_outputs.append(comm_id)

        roles_by_id[role_id] = Role(
            id=role_id,
            required_inputs=required_inputs,
            required_outputs=required_outputs,
            stage=raw.get("stage"),
            activity_unit=raw["activity_unit"],
            capacity_unit=raw["capacity_unit"],
        )

    return roles_by_id


def build_variants(
    model: dict,
    roles: dict[str, Role],
    commodities: dict[str, dict] | None = None,
) -> dict[str, Variant]:
    """Build Variant objects from variants, resolving role refs.

    Validates that each variant explicitly declares inputs and outputs,
    and that the variant's I/O satisfies the role's service contract.

    Args:
        model: Model dict with 'variants' key
        roles: Dict mapping role id to Role object
        commodities: Optional commodity dict for validating commodity references

    Returns:
        Dict mapping variant id to Variant object

    Raises:
        IRError: If duplicate variant id, invalid role/commodity reference,
            or variant doesn't satisfy role contract
    """
    variants_by_id: dict[str, Variant] = {}
    variant_entries = model.get("variants") or []

    attr_keys = {
        "kind",
        "efficiency",
        "performance_metric",
        "lifetime",
        "investment_cost",
        "fixed_om_cost",
        "variable_om_cost",
        "emission_factors",
    }

    def _parse_flows(
        variant_id: str,
        mode_id: str,
        raw_mode: dict,
        field: str,
    ) -> list[str]:
        values: list[str] = []
        for flow in raw_mode.get(field) or []:
            comm_id = flow["commodity"]
            if commodities is not None and comm_id not in commodities:
                raise IRError(
                    f"Variant '{variant_id}' mode '{mode_id}' references unknown "
                    f"{field[:-1]} commodity: {comm_id}"
                )
            values.append(comm_id)
        return values

    def _parse_attrs(raw_obj: dict) -> dict:
        attrs = {}
        for key in attr_keys:
            if key in raw_obj:
                attrs[key] = raw_obj[key]
        return attrs

    for raw in variant_entries:
        variant_id = raw["id"]
        role_id = raw["role"]

        if variant_id in variants_by_id:
            raise IRError(f"Duplicate variant id: {variant_id}")

        if role_id not in roles:
            raise IRError(
                f"Variant '{variant_id}' references unknown role: {role_id}"
            )

        role = roles[role_id]
        variant_attrs = _parse_attrs(raw)

        modes_by_id: dict[str, Mode] = {}
        mode_entries = raw.get("modes") or []

        # Backward-compatible fallback: single implicit mode from variant I/O.
        if not mode_entries:
            mode_entries = [
                {
                    "id": "default",
                    "inputs": raw.get("inputs") or [],
                    "outputs": raw.get("outputs") or [],
                }
            ]

        for raw_mode in mode_entries:
            mode_id = raw_mode["id"]
            if mode_id in modes_by_id:
                raise IRError(
                    f"Variant '{variant_id}' has duplicate mode id: {mode_id}"
                )
            mode_inputs = _parse_flows(variant_id, mode_id, raw_mode, "inputs")
            mode_outputs = _parse_flows(variant_id, mode_id, raw_mode, "outputs")

            missing_inputs = set(role.required_inputs) - set(mode_inputs)
            if missing_inputs:
                raise IRError(
                    f"Variant '{variant_id}' mode '{mode_id}' missing required "
                    f"inputs from role '{role_id}': {sorted(missing_inputs)}"
                )
            missing_outputs = set(role.required_outputs) - set(mode_outputs)
            if missing_outputs:
                raise IRError(
                    f"Variant '{variant_id}' mode '{mode_id}' missing required "
                    f"outputs from role '{role_id}': {sorted(missing_outputs)}"
                )

            mode_attrs = _parse_attrs(raw_mode)
            modes_by_id[mode_id] = Mode(
                id=mode_id,
                attrs={**variant_attrs, **mode_attrs},
                inputs=mode_inputs,
                outputs=mode_outputs,
            )

        default_mode = None
        if "default_mode" in raw:
            default_mode = raw["default_mode"]
            if default_mode not in modes_by_id:
                raise IRError(
                    f"Variant '{variant_id}' default_mode '{default_mode}' "
                    "is not a declared mode"
                )
        elif modes_by_id:
            default_mode = sorted(modes_by_id.keys())[0]

        # Keep variant-level inputs/outputs for legacy pathways that are
        # not yet provider-mode aware.
        default_mode_obj = modes_by_id.get(default_mode) if default_mode else None
        variant_inputs = default_mode_obj.inputs if default_mode_obj else []
        variant_outputs = default_mode_obj.outputs if default_mode_obj else []

        variants_by_id[variant_id] = Variant(
            id=variant_id,
            role=role,
            attrs=variant_attrs,
            inputs=variant_inputs,
            outputs=variant_outputs,
            modes=modes_by_id,
            default_mode=default_mode,
        )

    return variants_by_id


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
    - If availability.scopes specified: use those exact segment keys
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

    seg_cfg = model.get("scoping") or {}
    has_end_uses = bool(seg_cfg.get("end_uses"))

    for entry in availability:
        variant_id = entry["variant"]

        if variant_id not in variants:
            raise IRError(
                f"Availability references unknown variant: {variant_id}"
            )

        variant = variants[variant_id]
        regions = entry["regions"]

        if "scopes" in entry and entry["scopes"]:
            segments_to_use = entry["scopes"]
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
                    mode = (
                        variant.modes.get(variant.default_mode)
                        if variant.default_mode
                        else None
                    )
                    instances[key] = ProcessInstance(
                        key=key,
                        role=variant.role,
                        variant=variant,
                        mode=mode,
                        attrs=dict(mode.attrs if mode else variant.attrs),
                    )

    return instances


def build_providers(
    model: dict,
    roles: dict[str, Role],
    variants: dict[str, Variant],
) -> dict[str, Provider]:
    """Build Provider objects from providers, validating role/variant/mode refs."""
    providers_by_id: dict[str, Provider] = {}
    provider_entries = model.get("providers") or []

    for raw in provider_entries:
        provider_id = raw["id"]
        if provider_id in providers_by_id:
            raise IRError(f"Duplicate provider id: {provider_id}")

        role_id = raw["role"]
        if role_id not in roles:
            raise IRError(
                f"Provider '{provider_id}' references unknown role: {role_id}"
            )

        offerings: list[ProviderOffering] = []
        for offering in raw.get("offerings") or []:
            variant_id = offering["variant"]
            if variant_id not in variants:
                raise IRError(
                    f"Provider '{provider_id}' references unknown variant: {variant_id}"
                )
            variant = variants[variant_id]
            if variant.role.id != role_id:
                raise IRError(
                    f"Provider '{provider_id}' role '{role_id}' does not match "
                    f"variant '{variant_id}' role '{variant.role.id}'"
                )

            mode_ids = list(offering.get("modes") or [])
            if not mode_ids:
                mode_ids = sorted(variant.modes.keys())
            if not mode_ids:
                raise IRError(
                    f"Provider '{provider_id}' variant '{variant_id}' has no modes"
                )
            for mode_id in mode_ids:
                if mode_id not in variant.modes:
                    raise IRError(
                        f"Provider '{provider_id}' variant '{variant_id}' references "
                        f"unknown mode '{mode_id}'"
                    )

            offerings.append(ProviderOffering(variant_id=variant_id, modes=mode_ids))

        if not offerings:
            raise IRError(
                f"Provider '{provider_id}' must declare at least one offering"
            )

        scopes = list(raw.get("scopes") or [])
        if not scopes:
            scopes = [None]

        providers_by_id[provider_id] = Provider(
            id=provider_id,
            kind=raw["kind"],
            role=role_id,
            region=raw["region"],
            scopes=scopes,
            offerings=offerings,
        )

    return providers_by_id


def expand_provider_instances(
    providers: dict[str, Provider],
    variants: dict[str, Variant],
) -> dict[InstanceKey, ProcessInstance]:
    """Expand provider offerings to concrete provider×variant×mode×scope instances."""
    instances: dict[InstanceKey, ProcessInstance] = {}

    for provider in providers.values():
        for offering in provider.offerings:
            variant = variants[offering.variant_id]
            for mode_id in offering.modes:
                mode = variant.modes[mode_id]
                for segment in provider.scopes:
                    key = InstanceKey(
                        offering.variant_id,
                        provider.region,
                        segment,
                        provider_id=provider.id,
                        mode_id=mode_id,
                        provider_kind=provider.kind,
                        role_id=provider.role,
                    )
                    if key in instances:
                        continue
                    instances[key] = ProcessInstance(
                        key=key,
                        role=variant.role,
                        variant=variant,
                        mode=mode,
                        provider=provider,
                        attrs=dict(mode.attrs),
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
    - If selector.scope: exact match with key.segment
    - If selector.sector: match any segment starting with that sector

    Args:
        selector: Parameter selector dict (variant, region, sector?, scope?)
        key: InstanceKey to check
        segment_keys: List of segment keys for context

    Returns:
        True if selector matches the key
    """
    if selector["variant"] != key.variant_id:
        return False
    if selector["region"] != key.region:
        return False

    if "scope" in selector:
        return selector["scope"] == key.segment

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


def _provider_selector_matches(selector: dict, key: InstanceKey) -> bool:
    """Check if provider_parameter selector matches an instance key."""
    provider_id = selector.get("provider")
    if provider_id and provider_id != key.provider_id:
        return False

    variant_id = selector.get("variant")
    if variant_id and variant_id != key.variant_id:
        return False

    mode_id = selector.get("mode")
    if mode_id and mode_id != key.mode_id:
        return False

    role_id = selector.get("role")
    if role_id and role_id != key.role_id:
        return False

    region = selector.get("region")
    if region and region != key.region:
        return False

    scope = selector.get("scope")
    if scope is not None and scope != key.segment:
        return False

    return True


def apply_provider_parameters(
    instances: dict[InstanceKey, ProcessInstance],
    model: dict,
) -> None:
    """Apply provider_parameters blocks to matching provider-mode instances."""
    provider_params = model.get("provider_parameters") or []

    override_keys = {
        "existing_capacity",
        "cap_bound",
        "ncap_bound",
        "activity_bound",
        "stock",
    }
    merge_keys = {"emission_factors"}

    for param_block in provider_params:
        selector = param_block["selector"]
        for key, instance in instances.items():
            if not _provider_selector_matches(selector, key):
                continue
            for attr_key in override_keys:
                if attr_key in param_block:
                    instance.attrs[attr_key] = param_block[attr_key]
            for attr_key in merge_keys:
                if attr_key in param_block:
                    existing = instance.attrs.get(attr_key, {})
                    instance.attrs[attr_key] = {**existing, **param_block[attr_key]}


def _produces_service(outputs: list[str], commodities: dict[str, dict]) -> bool:
    """Check if a list of output commodity IDs includes a service commodity."""
    for out_id in outputs:
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
        return registry.get_process_symbol(
            key.variant_id,
            key.region,
            key.segment,
            provider_kind=key.provider_kind,
            provider_id=key.provider_id,
            role_id=key.role_id,
            mode_id=key.mode_id,
        )
    parts = [key.variant_id, key.region]
    if key.provider_id:
        parts = [key.provider_id, key.role_id or "role", key.variant_id]
        if key.mode_id:
            parts.append(key.mode_id)
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
        variant = instance.variant
        mode = instance.mode
        attrs = instance.attrs

        prc_name = _generate_process_name(key, registry)

        inputs_scoped = []
        for inp_id in mode.inputs if mode else variant.inputs:
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
        for out_id in mode.outputs if mode else variant.outputs:
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
        if _produces_service(mode.outputs if mode else variant.outputs, commodities):
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
        outputs = instance.mode.outputs if instance.mode else instance.variant.outputs
        for out_id in outputs:
            map_key = (key.region, key.segment, out_id)
            if map_key not in producer_map:
                producer_map[map_key] = []
            producer_map[map_key].append(key.variant_id)

    for demand in demands:
        comm_id = demand["commodity"]
        region = demand["region"]
        segment = demand.get("scope") or demand.get("sector")

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
