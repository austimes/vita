"""Facility primitive lowering for VedaLang P4 syntax.

This module translates top-level facility/template declarations into existing
compiler constructs (scoping, demands, availability, process parameters) and
emits additional policy artifacts (TFM bounds and UC rows).
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .ir import Variant
from .registry import VedaLangError


def _sanitize_scope_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", value.lower())
    token = token.strip("_")
    return token or "facility"


def _series_values(series: dict) -> dict[str, float]:
    values = series.get("values", {}) if isinstance(series, dict) else {}
    return {str(k): float(v) for k, v in values.items()}


def _scale_series(values: dict[str, float], factor: float) -> dict[str, float]:
    if factor == 1.0:
        return dict(values)
    return {str(y): float(v) * factor for y, v in values.items()}


def _value_for_year(values: dict[str, float], year: int) -> float:
    if not values:
        return 0.0
    key = str(year)
    if key in values:
        return float(values[key])
    years = sorted(int(y) for y in values)
    prev = [y for y in years if y <= year]
    if prev:
        return float(values[str(prev[-1])])
    return float(values[str(years[0])])


def _topological_order(nodes: list[str], edges: list[dict[str, str]]) -> list[str]:
    if not edges:
        return list(nodes)

    indegree = {n: 0 for n in nodes}
    outgoing: dict[str, list[str]] = {n: [] for n in nodes}
    for edge in edges:
        src = edge["from"]
        dst = edge["to"]
        if src not in indegree or dst not in indegree:
            raise VedaLangError(
                "facility template transition_graph must reference "
                "candidate_variants only"
            )
        outgoing[src].append(dst)
        indegree[dst] += 1

    queue = sorted([n for n, d in indegree.items() if d == 0])
    order: list[str] = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in sorted(outgoing[cur]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(nodes):
        raise VedaLangError("facility template transition_graph must be acyclic")

    return order


def _validate_transition_graph_chain(
    nodes: list[str],
    edges: list[dict[str, str]],
) -> None:
    """Validate transition graph is a single directed chain when declared.

    The no-backswitch prefix formulation assumes an ordered state ladder
    v1 -> v2 -> ... -> vk. For v1 we enforce chain-shaped transitions to
    avoid ambiguous partial-order semantics.
    """
    if not edges:
        return

    if len(nodes) <= 1:
        return

    incoming = {n: 0 for n in nodes}
    outgoing = {n: 0 for n in nodes}
    seen_pairs: set[tuple[str, str]] = set()

    for edge in edges:
        src = edge["from"]
        dst = edge["to"]
        if src == dst:
            raise VedaLangError(
                "facility template transition_graph cannot contain self-loops"
            )
        pair = (src, dst)
        if pair in seen_pairs:
            raise VedaLangError(
                "facility template transition_graph contains duplicate edges"
            )
        seen_pairs.add(pair)
        incoming[dst] += 1
        outgoing[src] += 1

    if len(edges) != len(nodes) - 1:
        raise VedaLangError(
            "facility template transition_graph must define a single chain "
            "(exactly N-1 edges for N candidate_variants)"
        )

    for node in nodes:
        if incoming[node] > 1 or outgoing[node] > 1:
            raise VedaLangError(
                "facility template transition_graph must be chain-shaped "
                "(max one predecessor and one successor per variant)"
            )

    roots = [n for n in nodes if incoming[n] == 0]
    leaves = [n for n in nodes if outgoing[n] == 0]
    if len(roots) != 1 or len(leaves) != 1:
        raise VedaLangError(
            "facility template transition_graph must have one start and one end variant"
        )


def _validated_share_map(
    shares: dict[str, Any],
    *,
    label: str,
    allowed_members: set[str],
) -> dict[str, float]:
    if not shares:
        raise VedaLangError(f"{label} must define at least one share value")

    result: dict[str, float] = {}
    for member, raw_value in shares.items():
        if member not in allowed_members:
            raise VedaLangError(
                f"{label} references commodity '{member}' not present "
                "in the group members"
            )
        result[member] = float(raw_value)

    total = sum(result.values())
    if abs(total - 1.0) > 1e-6:
        raise VedaLangError(f"{label} must sum to 1.0 (got {total})")
    return result


def _resolve_spatial_mapping(
    source: dict, location_ref: str
) -> list[tuple[str, float]]:
    model = source.get("model", {})
    regions = model.get("regions", [])
    region_scheme = model.get("region_scheme")

    if location_ref in regions:
        return [(location_ref, 1.0)]

    mappings = source.get("spatial_mappings", []) or []
    if not region_scheme:
        raise VedaLangError(
            f"Facility location_ref '{location_ref}' requires "
            "model.region_scheme or direct region name"
        )

    for mapping in mappings:
        if mapping.get("scheme") != region_scheme:
            continue
        if mapping.get("from") not in (None, "facility_location_ref"):
            continue
        entries = (mapping.get("map") or {}).get(location_ref)
        if not entries:
            continue
        resolved: list[tuple[str, float]] = []
        total = 0.0
        for entry in entries:
            region = entry["region"]
            share = float(entry.get("share", 1.0))
            if region not in regions:
                raise VedaLangError(
                    f"Spatial mapping for '{location_ref}' references "
                    f"unknown region '{region}'"
                )
            resolved.append((region, share))
            total += share
        if abs(total - 1.0) > 1e-6:
            raise VedaLangError(
                f"Spatial mapping shares for '{location_ref}' must sum to "
                f"1.0 (got {total})"
            )
        return resolved

    raise VedaLangError(
        f"No spatial mapping found for location_ref '{location_ref}' "
        f"under scheme '{region_scheme}'"
    )


@dataclass
class FacilityEntity:
    """Internal resolved facility entity after selection and regional splitting."""

    facility_id: str
    class_name: str
    template_id: str
    scope: str
    region: str
    representation: str
    output_series: dict[str, float]
    output_interpolation: str
    installed_state: dict[str, Any]
    candidate_variants: list[str]
    variant_order: list[str]
    variant_policies: list[dict[str, Any]]
    primary_output_commodity: str
    input_mix: list[dict[str, Any]]
    input_groups: list[dict[str, Any]]
    safeguard: dict[str, Any] | None
    ranking_metric: float


def _merge_existing_capacity(entries: list[dict]) -> list[dict]:
    merged: dict[int, float] = {}
    for item in entries:
        year = int(item["vintage"])
        merged[year] = merged.get(year, 0.0) + float(item["capacity"])
    return [{"vintage": y, "capacity": c} for y, c in sorted(merged.items())]


def _merge_variant_policies(policies: list[list[dict]]) -> list[dict]:
    by_variant: dict[str, dict[str, Any]] = {}
    for policy_list in policies:
        for p in policy_list:
            variant = p["variant"]
            rec = by_variant.setdefault(
                variant,
                {
                    "variant": variant,
                    "from_year": int(p["from_year"]),
                    "to_year": p.get("to_year"),
                    "max_new_capacity_per_period": p.get("max_new_capacity_per_period"),
                },
            )
            rec["from_year"] = max(rec["from_year"], int(p["from_year"]))
            to_year = p.get("to_year")
            if to_year is not None:
                rec["to_year"] = (
                    to_year
                    if rec.get("to_year") is None
                    else min(rec["to_year"], to_year)
                )
            cap = p.get("max_new_capacity_per_period")
            if cap is not None:
                rec_cap = rec.get("max_new_capacity_per_period")
                rec["max_new_capacity_per_period"] = (
                    cap if rec_cap is None else min(rec_cap, cap)
                )
    return [by_variant[k] for k in sorted(by_variant)]


def _merge_input_mix(mixes: list[list[dict]], weights: list[float]) -> list[dict]:
    if not mixes:
        return []
    by_group: dict[str, dict[str, Any]] = {}
    for idx, mix_list in enumerate(mixes):
        w = weights[idx]
        for mix in mix_list:
            group = mix["group"]
            rec = by_group.setdefault(
                group, {"group": group, "baseline_shares": {}, "targets": []}
            )
            for comm, share in (mix.get("baseline_shares") or {}).items():
                rec["baseline_shares"][comm] = rec["baseline_shares"].get(
                    comm, 0.0
                ) + w * float(share)
    for rec in by_group.values():
        total = sum(rec["baseline_shares"].values())
        if total > 0:
            rec["baseline_shares"] = {
                comm: val / total
                for comm, val in sorted(rec["baseline_shares"].items())
            }
    return [by_group[g] for g in sorted(by_group)]


def _entity_aggregation_key(entity: FacilityEntity, keys: list[str]) -> tuple:
    installed_variant = entity.installed_state.get("variant", "")
    values: list[Any] = []
    for key in keys:
        if key == "template":
            values.append(entity.template_id)
        elif key == "class":
            values.append(entity.class_name)
        elif key == "region":
            values.append(entity.region)
        elif key == "primary_output_commodity":
            values.append(entity.primary_output_commodity)
        elif key == "installed_variant":
            values.append(installed_variant)
        else:
            raise VedaLangError(
                f"Unsupported facility_selection.aggregation_key '{key}'"
            )
    return tuple(values)


def _aggregate_entities(
    entities: list[FacilityEntity], aggregation_keys: list[str]
) -> list[FacilityEntity]:
    grouped: dict[tuple[Any, ...], list[FacilityEntity]] = {}
    for entity in entities:
        key = _entity_aggregation_key(entity, aggregation_keys)
        grouped.setdefault(key, []).append(entity)

    result: list[FacilityEntity] = []
    for idx, (_, group) in enumerate(sorted(grouped.items())):
        base = group[0]
        output_values: dict[str, float] = {}
        for entity in group:
            for y, v in entity.output_series.items():
                output_values[y] = output_values.get(y, 0.0) + float(v)

        merged_installed = {
            "variant": base.installed_state.get("variant"),
        }
        stock_total = sum(float(e.installed_state.get("stock", 0.0)) for e in group)
        if stock_total:
            merged_installed["stock"] = stock_total

        all_pasti = []
        for entity in group:
            all_pasti.extend(entity.installed_state.get("existing_capacity", []))
        if all_pasti:
            merged_installed["existing_capacity"] = _merge_existing_capacity(all_pasti)

        weights = [sum(float(v) for v in e.output_series.values()) for e in group]
        if sum(weights) == 0:
            weights = [1.0 for _ in group]
        norm = sum(weights)
        weights = [w / norm for w in weights]

        safeguard = None
        if base.safeguard:
            baseline_year = int(base.safeguard["baseline_year"])
            weighted_intensity = 0.0
            denom = 0.0
            for entity in group:
                y_val = _value_for_year(entity.output_series, baseline_year)
                weighted_intensity += (
                    float(entity.safeguard["baseline_intensity"]) * y_val
                )
                denom += y_val
            agg_intensity = (
                weighted_intensity / denom
                if denom > 0
                else float(base.safeguard["baseline_intensity"])
            )
            safeguard = deepcopy(base.safeguard)
            safeguard["baseline_intensity"] = agg_intensity

        result.append(
            FacilityEntity(
                facility_id=f"agg_{base.template_id}_{base.region}_{idx + 1}",
                class_name=base.class_name,
                template_id=base.template_id,
                scope=f"{base.scope}_agg{idx + 1}",
                region=base.region,
                representation="archetype",
                output_series=output_values,
                output_interpolation=base.output_interpolation,
                installed_state=merged_installed,
                candidate_variants=list(base.candidate_variants),
                variant_order=list(base.variant_order),
                variant_policies=_merge_variant_policies(
                    [e.variant_policies for e in group]
                ),
                primary_output_commodity=base.primary_output_commodity,
                input_mix=_merge_input_mix([e.input_mix for e in group], weights),
                input_groups=deepcopy(base.input_groups),
                safeguard=safeguard,
                ranking_metric=sum(e.ranking_metric for e in group),
            )
        )

    return result


def prepare_facilities(
    source: dict,
    commodities: dict[str, dict],
    variants: dict[str, Variant],
    model_years: list[int],
) -> tuple[dict, dict]:
    """Materialize facilities into source-level demands/availability/parameters.

    Returns transformed source and facility context used for post-instance artifact
    generation.
    """
    if not source.get("facilities"):
        return source, {"entities": [], "template_map": {}, "commodity_groups": {}}

    transformed = deepcopy(source)

    template_map = {t["id"]: t for t in transformed.get("facility_templates", [])}
    if not template_map:
        raise VedaLangError("facilities requires facility_templates")

    commodity_groups = {g["id"]: g for g in transformed.get("commodity_groups", [])}

    raw_variant_map = {v["id"]: v for v in transformed.get("process_variants", [])}

    entities: list[FacilityEntity] = []

    for facility in transformed.get("facilities", []):
        facility_id = facility["id"]
        template_id = facility["template"]
        template = template_map.get(template_id)
        if not template:
            raise VedaLangError(
                f"Facility '{facility_id}' references unknown template '{template_id}'"
            )

        class_name = facility["class"]
        if template.get("class") != class_name:
            raise VedaLangError(
                f"Facility '{facility_id}' class '{class_name}' does not "
                f"match template class '{template.get('class')}'"
            )

        role_id = template["role"]
        primary_output = template["primary_output_commodity"]
        comm = commodities.get(primary_output)
        if not comm or comm.get("type") != "service":
            raise VedaLangError(
                f"Facility template '{template_id}' "
                f"primary_output_commodity '{primary_output}' must be "
                "a service commodity"
            )

        candidate_variants = list(template.get("candidate_variants", []))
        if not candidate_variants:
            raise VedaLangError(
                f"Facility template '{template_id}' must define candidate_variants"
            )
        for variant_id in candidate_variants:
            variant = variants.get(variant_id)
            if not variant:
                raise VedaLangError(
                    f"Facility template '{template_id}' references "
                    f"unknown variant '{variant_id}'"
                )
            if variant.role.id != role_id:
                raise VedaLangError(
                    f"Facility template '{template_id}' variant "
                    f"'{variant_id}' role mismatch (expected '{role_id}')"
                )

        transition_graph = template.get("transition_graph") or []
        _validate_transition_graph_chain(candidate_variants, transition_graph)
        variant_order = _topological_order(candidate_variants, transition_graph)
        input_groups = deepcopy(template.get("input_groups", []))
        for group in input_groups:
            if group["commodity_group"] not in commodity_groups:
                raise VedaLangError(
                    f"Facility template '{template_id}' references "
                    "unknown commodity_group "
                    f"'{group['commodity_group']}'"
                )

        for variant_id in candidate_variants:
            raw_variant = raw_variant_map.get(variant_id, {})
            output_commodities = [
                o.get("commodity") for o in (raw_variant.get("outputs") or [])
            ]
            if primary_output not in output_commodities:
                raise VedaLangError(
                    f"Facility template '{template_id}' variant '{variant_id}' "
                    f"must produce primary_output_commodity '{primary_output}'"
                )
            service_outputs = [
                out_id
                for out_id in output_commodities
                if commodities.get(out_id, {}).get("type") == "service"
            ]
            if service_outputs != [primary_output]:
                raise VedaLangError(
                    f"Facility template '{template_id}' variant "
                    f"'{variant_id}' must have "
                    "exactly one service output equal to primary_output_commodity"
                )

        installed_state = deepcopy(facility.get("installed_state") or {})
        installed_variant = installed_state.get("variant")
        if installed_variant not in candidate_variants:
            raise VedaLangError(
                f"Facility '{facility_id}' installed_state.variant "
                f"'{installed_variant}' must be one of "
                "template candidate_variants"
            )

        output_series = facility.get("output_series") or {}
        output_values = _series_values(output_series)
        output_interp = output_series.get("interpolation", "interp_extrap")
        variant_policies = deepcopy(facility.get("variant_policies", []))
        for policy in variant_policies:
            if policy["variant"] not in candidate_variants:
                raise VedaLangError(
                    f"Facility '{facility_id}' variant_policies entry references "
                    f"unknown template variant '{policy['variant']}'"
                )
            from_year = int(policy["from_year"])
            to_year = policy.get("to_year")
            if to_year is not None and int(to_year) < from_year:
                raise VedaLangError(
                    f"Facility '{facility_id}' variant_policies for variant "
                    f"'{policy['variant']}' has to_year earlier than from_year"
                )
        input_mix = deepcopy(facility.get("input_mix", []))
        template_group_ids = {group["id"] for group in input_groups}
        group_to_members: dict[str, set[str]] = {}
        for group in input_groups:
            group_id = group["id"]
            commodity_group_id = group["commodity_group"]
            group_to_members[group_id] = set(
                commodity_groups[commodity_group_id]["members"]
            )
        for mix in input_mix:
            group_id = mix["group"]
            if group_id not in template_group_ids:
                raise VedaLangError(
                    f"Facility '{facility_id}' input_mix group '{mix['group']}' "
                    "must exist in facility_template.input_groups"
                )
            allowed_members = group_to_members[group_id]
            mix["baseline_shares"] = _validated_share_map(
                mix.get("baseline_shares") or {},
                label=(
                    f"Facility '{facility_id}' input_mix baseline_shares "
                    f"for group '{group_id}'"
                ),
                allowed_members=allowed_members,
            )
            validated_targets = []
            for target in mix.get("targets", []):
                validated_target = dict(target)
                validated_target["shares"] = _validated_share_map(
                    target.get("shares") or {},
                    label=(
                        f"Facility '{facility_id}' input_mix target shares for "
                        f"group '{group_id}' year {target.get('year')}"
                    ),
                    allowed_members=allowed_members,
                )
                validated_targets.append(validated_target)
            mix["targets"] = validated_targets

        safeguard = (
            deepcopy(facility.get("safeguard")) if class_name == "safeguard" else None
        )
        baseline_metric = 0.0
        if safeguard:
            baseline_year = int(safeguard["baseline_year"])
            baseline_intensity = float(safeguard["baseline_intensity"])
            baseline_output = _value_for_year(output_values, baseline_year)
            baseline_metric = baseline_intensity * baseline_output

        for region, share in _resolve_spatial_mapping(
            transformed, facility["location_ref"]
        ):
            suffix = f"_{region.lower()}" if share != 1.0 else ""
            piece_id = f"{facility_id}{suffix}"
            scope_token = _sanitize_scope_token(piece_id)
            scope = f"{template['sector']}.{scope_token}"

            scaled_installed = deepcopy(installed_state)
            if "stock" in scaled_installed:
                scaled_installed["stock"] = float(scaled_installed["stock"]) * share
            if "existing_capacity" in scaled_installed:
                scaled_installed["existing_capacity"] = [
                    {
                        "vintage": int(item["vintage"]),
                        "capacity": float(item["capacity"]) * share,
                    }
                    for item in scaled_installed["existing_capacity"]
                ]

            entities.append(
                FacilityEntity(
                    facility_id=piece_id,
                    class_name=class_name,
                    template_id=template_id,
                    scope=scope,
                    region=region,
                    representation=facility.get("representation", "individual"),
                    output_series=_scale_series(output_values, share),
                    output_interpolation=output_interp,
                    installed_state=scaled_installed,
                    candidate_variants=candidate_variants,
                    variant_order=variant_order,
                    variant_policies=variant_policies,
                    primary_output_commodity=primary_output,
                    input_mix=input_mix,
                    input_groups=input_groups,
                    safeguard=safeguard,
                    ranking_metric=baseline_metric * share,
                )
            )

    selection = transformed.get("facility_selection") or {}
    mode = selection.get("mode", "top_n_by_baseline_emissions")
    if mode != "top_n_by_baseline_emissions":
        raise VedaLangError(f"Unsupported facility_selection.mode '{mode}'")
    ranking_metric = selection.get("ranking_metric", "baseline_emissions")
    if ranking_metric != "baseline_emissions":
        raise VedaLangError(
            f"Unsupported facility_selection.ranking_metric '{ranking_metric}'"
        )
    n_individual = selection.get("n_individual")
    aggregation_keys = selection.get("aggregation_keys") or [
        "template",
        "class",
        "region",
        "primary_output_commodity",
        "installed_variant",
    ]
    mandatory_keys = {"template", "primary_output_commodity"}
    if not mandatory_keys.issubset(set(aggregation_keys)):
        raise VedaLangError(
            "facility_selection.aggregation_keys must include at least "
            "'template' and 'primary_output_commodity'"
        )

    explicit_archetypes = [e for e in entities if e.representation == "archetype"]
    individuals = [e for e in entities if e.representation != "archetype"]

    if n_individual is None:
        n_individual = len(individuals)

    individuals_sorted = sorted(
        individuals,
        key=lambda e: (-e.ranking_metric, e.facility_id),
    )
    selected_individual = individuals_sorted[:n_individual]
    to_aggregate = individuals_sorted[n_individual:]
    selected_entities = list(explicit_archetypes) + list(selected_individual)

    if to_aggregate:
        selected_entities.extend(_aggregate_entities(to_aggregate, aggregation_keys))

    # Mutate source with generated constructs used by existing compiler pipeline.
    demands = list(transformed.get("demands") or [])
    availability = list(transformed.get("availability") or [])
    process_parameters = list(transformed.get("process_parameters") or [])

    seen_availability: set[tuple[str, str, str]] = set()

    for entity in selected_entities:
        demands.append(
            {
                "commodity": entity.primary_output_commodity,
                "region": entity.region,
                "scope": entity.scope,
                "values": dict(entity.output_series),
                "interpolation": entity.output_interpolation,
            }
        )

        for variant_id in entity.candidate_variants:
            key = (variant_id, entity.region, entity.scope)
            if key in seen_availability:
                continue
            seen_availability.add(key)
            availability.append(
                {
                    "variant": variant_id,
                    "regions": [entity.region],
                    "scopes": [entity.scope],
                }
            )

        installed_variant = entity.installed_state.get("variant")
        param = {
            "selector": {
                "variant": installed_variant,
                "region": entity.region,
                "scope": entity.scope,
            },
        }
        if "existing_capacity" in entity.installed_state:
            param["existing_capacity"] = entity.installed_state["existing_capacity"]
        if "stock" in entity.installed_state:
            param["stock"] = entity.installed_state["stock"]
        process_parameters.append(param)

    transformed["demands"] = demands
    transformed["availability"] = availability
    transformed["process_parameters"] = process_parameters

    context = {
        "entities": [
            {
                "facility_id": e.facility_id,
                "class_name": e.class_name,
                "template_id": e.template_id,
                "scope": e.scope,
                "region": e.region,
                "candidate_variants": e.candidate_variants,
                "variant_order": e.variant_order,
                "variant_policies": e.variant_policies,
                "primary_output_commodity": e.primary_output_commodity,
                "input_mix": e.input_mix,
                "input_groups": e.input_groups,
                "safeguard": e.safeguard,
                "output_series": e.output_series,
            }
            for e in selected_entities
        ],
        "template_map": template_map,
        "commodity_groups": commodity_groups,
        "raw_variant_map": raw_variant_map,
        "model_years": list(model_years),
    }

    return transformed, context


def _intensity_path(
    safeguard: dict,
    model_years: list[int],
) -> dict[int, float]:
    baseline_year = int(safeguard["baseline_year"])
    baseline_intensity = float(safeguard["baseline_intensity"])
    blocks = safeguard.get("intensity_decline_blocks") or []
    overrides = {
        int(y): float(v)
        for y, v in (safeguard.get("explicit_intensity_overrides") or {}).items()
    }

    def rate_for_year(year: int) -> float:
        for block in blocks:
            if int(block["from_year"]) <= year <= int(block["to_year"]):
                return float(block["annual_decline_pct"]) / 100.0
        return 0.0

    years = sorted(int(y) for y in model_years)
    path: dict[int, float] = {}
    current = baseline_intensity
    last_year = baseline_year
    for year in years:
        if year < baseline_year:
            path[year] = baseline_intensity
            continue
        for step_year in range(last_year + 1, year + 1):
            current = current * (1.0 - rate_for_year(step_year))
        path[year] = current
        last_year = year

    path[baseline_year] = baseline_intensity
    for year, value in overrides.items():
        if year in path:
            path[year] = value

    return path


def _variant_output_coefficient(
    raw_variant: dict,
    output_commodity: str,
) -> float:
    for out in raw_variant.get("outputs") or []:
        if out.get("commodity") == output_commodity:
            coeff = out.get("coefficient")
            return float(coeff) if coeff is not None else 1.0
    return 1.0


def _variant_emission_factor(
    variant: Variant,
    emission_commodity: str,
) -> float:
    factors = variant.attrs.get("emission_factors") or {}
    value = factors.get(emission_commodity)
    if value is None and emission_commodity.endswith(":co2"):
        # Backward-compat fallback for sparse models still using bare key.
        value = factors.get("co2")
    if value is None:
        return 0.0
    if isinstance(value, dict):
        values = value.get("values") or {}
        if not values:
            return 0.0
        first_year = sorted(values.keys())[0]
        return float(values[first_year])
    return float(value)


def _variants_for_member(
    member: str,
    candidate_variants: list[str],
    raw_variant_map: dict[str, dict],
) -> set[str]:
    result: set[str] = set()
    for variant_id in candidate_variants:
        raw = raw_variant_map.get(variant_id, {})
        for inp in raw.get("inputs") or []:
            if inp.get("commodity") == member:
                result.add(variant_id)
                break
    return result


def generate_facility_artifacts(
    context: dict,
    variants: dict[str, Variant],
    process_symbol_map: dict[tuple[str, str, str | None], str],
) -> tuple[list[dict], list[dict]]:
    """Generate extra TFM_INS rows and internal UC constraints for facilities."""
    entities = context.get("entities", [])
    model_years = [int(y) for y in context.get("model_years", [])]
    commodity_groups = context.get("commodity_groups", {})
    raw_variant_map = context.get("raw_variant_map", {})

    tfm_rows: list[dict] = []
    constraints: list[dict] = []

    for entity in entities:
        facility_id = entity["facility_id"]
        region = entity["region"]
        scope = entity["scope"]
        candidate_variants = entity["candidate_variants"]
        variant_order = entity["variant_order"]

        # Timing windows and optional max new capacity.
        for policy in entity.get("variant_policies", []):
            variant_id = policy["variant"]
            symbol = process_symbol_map.get((variant_id, region, scope))
            if not symbol:
                continue
            from_year = int(policy["from_year"])
            to_year = (
                int(policy.get("to_year"))
                if policy.get("to_year") is not None
                else None
            )
            cap_limit = policy.get("max_new_capacity_per_period")

            for year in model_years:
                if year < from_year or (to_year is not None and year > to_year):
                    for attr in ("NCAP_BND", "ACT_BND"):
                        tfm_rows.append(
                            {
                                "region": region,
                                "process": symbol,
                                "year": year,
                                "attribute": attr,
                                "limtype": "FX",
                                "value": 0,
                            }
                        )
                elif cap_limit is not None:
                    tfm_rows.append(
                        {
                            "region": region,
                            "process": symbol,
                            "year": year,
                            "attribute": "NCAP_BND",
                            "limtype": "UP",
                            "value": float(cap_limit),
                        }
                    )

        # LP-safe no-backswitch prefix constraints.
        if len(variant_order) > 1:
            for idx in range(1, len(model_years)):
                prev_year = model_years[idx - 1]
                year = model_years[idx]
                for prefix_idx in range(1, len(variant_order)):
                    prefix = variant_order[:prefix_idx]
                    uc_name = f"FAC_NB_{facility_id}_{prefix_idx}_{year}"
                    rows = []
                    for variant_id in prefix:
                        current_symbol = process_symbol_map.get(
                            (variant_id, region, scope)
                        )
                        if not current_symbol:
                            continue
                    rows.append(
                        {
                            "uc_n": uc_name,
                            "description": (
                                f"No-backswitch prefix {prefix_idx} "
                                f"for {facility_id}"
                            ),
                            "region": region,
                            "year": year,
                            "process": current_symbol,
                                "commodity": "",
                                "side": "LHS",
                                "uc_act": 1,
                            }
                        )
                    rows.append(
                        {
                            "uc_n": uc_name,
                            "description": (
                                f"No-backswitch prefix {prefix_idx} "
                                f"for {facility_id}"
                            ),
                            "region": region,
                            "year": prev_year,
                            "process": current_symbol,
                                "commodity": "",
                                "side": "LHS",
                                "uc_act": -1,
                            }
                        )

                    if not rows:
                        continue
                    rows.append(
                        {
                            "uc_n": uc_name,
                            "description": (
                                f"No-backswitch prefix {prefix_idx} "
                                f"for {facility_id}"
                            ),
                            "region": region,
                            "process": "",
                            "commodity": "",
                            "limtype": "UP",
                            "uc_rhs": 0,
                        }
                    )
                    constraints.append(
                        {
                            "name": uc_name,
                            "type": "__uc_rows__",
                            "category": "policies",
                            "rows": rows,
                        }
                    )

        # Safeguard intensity constraints.
        safeguard = entity.get("safeguard")
        if safeguard:
            intensity_path = _intensity_path(safeguard, model_years)
            output_commodity = entity["primary_output_commodity"]
            emission_commodity = safeguard.get("emission_commodity", "emission:co2")

            for year in model_years:
                target_intensity = float(
                    intensity_path.get(year, intensity_path[max(intensity_path)])
                )
                uc_name = f"FAC_INT_{facility_id}_{year}"
                rows = []
                for variant_id in candidate_variants:
                    symbol = process_symbol_map.get((variant_id, region, scope))
                    if not symbol:
                        continue
                    variant = variants.get(variant_id)
                    if not variant:
                        continue
                    raw_variant = raw_variant_map.get(variant_id, {})
                    ef = _variant_emission_factor(variant, emission_commodity)
                    out_coeff = _variant_output_coefficient(
                        raw_variant, output_commodity
                    )
                    coef = ef - target_intensity * out_coeff
                    if abs(coef) < 1e-12:
                        continue
                    rows.append(
                        {
                            "uc_n": uc_name,
                            "description": f"Safeguard intensity for {facility_id}",
                            "region": region,
                            "year": year,
                            "process": symbol,
                            "commodity": "",
                            "side": "LHS",
                            "uc_act": coef,
                        }
                    )
                if not rows:
                    continue
                rows.append(
                    {
                        "uc_n": uc_name,
                        "description": f"Safeguard intensity for {facility_id}",
                        "region": region,
                        "year": year,
                        "process": "",
                        "commodity": "",
                        "limtype": "UP",
                        "uc_rhsrt": 0,
                    }
                )
                constraints.append(
                    {
                        "name": uc_name,
                        "type": "__uc_rows__",
                        "category": "policies",
                        "rows": rows,
                    }
                )

        # Fuel mix constraints (base-year hard + optional bounded targets).
        baseline_year = (
            model_years[0] if not safeguard else int(safeguard["baseline_year"])
        )
        baseline_year = min(model_years, key=lambda y: abs(y - baseline_year))

        for mix in entity.get("input_mix", []):
            group_id = mix.get("group")
            group = next(
                (g for g in entity.get("input_groups", []) if g.get("id") == group_id),
                None,
            )
            if not group:
                continue
            commodity_group = commodity_groups.get(group.get("commodity_group"))
            if not commodity_group:
                continue

            members = commodity_group.get("members", [])
            variants_total = set()
            variants_by_member: dict[str, set[str]] = {}
            for member in members:
                member_variants = _variants_for_member(
                    member, candidate_variants, raw_variant_map
                )
                variants_by_member[member] = member_variants
                variants_total.update(member_variants)

            if not variants_total:
                continue

            member_signatures = {
                tuple(sorted(variants_by_member.get(member, set())))
                for member in members
            }
            if len(members) > 1 and len(member_signatures) <= 1:
                raise VedaLangError(
                    "Facility input_mix requires fuel-distinguishable variants. "
                    "All commodity_group members map to the same variant set, "
                    "so share/no-backslide constraints are not identifiable. "
                    "Define separate process_variants per alternate fuel."
                )

            def add_mix_constraint(
                member: str, share: float, year: int, limtype: str, suffix: str
            ) -> None:
                uc_name = f"FAC_MIX_{facility_id}_{group_id}_{member}_{year}_{suffix}"
                rows = []
                for variant_id in sorted(variants_total):
                    symbol = process_symbol_map.get((variant_id, region, scope))
                    if not symbol:
                        continue
                    coef = (
                        (1.0 - share)
                        if variant_id in variants_by_member.get(member, set())
                        else -share
                    )
                    rows.append(
                        {
                            "uc_n": uc_name,
                            "description": f"Facility mix for {facility_id} ({member})",
                            "region": region,
                            "year": year,
                            "process": symbol,
                            "commodity": "",
                            "side": "LHS",
                            "uc_act": coef,
                        }
                    )
                if not rows:
                    return
                rows.append(
                    {
                        "uc_n": uc_name,
                        "description": f"Facility mix for {facility_id} ({member})",
                        "region": region,
                        "year": year,
                        "process": "",
                        "commodity": "",
                        "limtype": limtype,
                        "uc_rhsrt": 0,
                    }
                )
                constraints.append(
                    {
                        "name": uc_name,
                        "type": "__uc_rows__",
                        "category": "policies",
                        "rows": rows,
                    }
                )

            for member, share in (mix.get("baseline_shares") or {}).items():
                share_value = float(share)
                add_mix_constraint(member, share_value, baseline_year, "LO", "BASE_LO")
                add_mix_constraint(member, share_value, baseline_year, "UP", "BASE_UP")

            for target in mix.get("targets", []):
                year = int(target["year"])
                if year not in model_years:
                    continue
                hard = bool(target.get("hard", False))
                tol = float(target.get("tolerance", 0.05))
                for member, share in (target.get("shares") or {}).items():
                    share_value = float(share)
                    if hard or tol <= 0:
                        add_mix_constraint(member, share_value, year, "LO", "TGT_LO")
                        add_mix_constraint(member, share_value, year, "UP", "TGT_UP")
                    else:
                        lo = max(0.0, share_value - tol)
                        up = min(1.0, share_value + tol)
                        add_mix_constraint(member, lo, year, "LO", "TGT_BAND_LO")
                        add_mix_constraint(member, up, year, "UP", "TGT_BAND_UP")

    return tfm_rows, constraints
