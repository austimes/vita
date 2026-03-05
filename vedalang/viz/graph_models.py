"""Graph model builders for RES query engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from vedalang.compiler.compiler import _normalize_commodities_for_new_syntax
from vedalang.compiler.facilities import (
    build_facility_variant_metadata,
    prepare_facilities,
)
from vedalang.compiler.ir import (
    apply_process_parameters,
    build_roles,
    build_variants,
    expand_availability,
)
from vedalang.compiler.naming import NamingRegistry
from vedalang.compiler.segments import build_segments


@dataclass
class FilterSpec:
    regions: set[str]
    sectors: set[str]
    scopes: set[str]


def _is_truthy_trade_cell(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned not in {"", "0", "false", "no", "n"}
    return True


def _sector_of(segment: str | None) -> str | None:
    if not segment:
        return None
    return segment.split(".")[0]


def _include_scope(segment: str | None, filters: FilterSpec) -> bool:
    if filters.scopes and segment not in filters.scopes:
        return False
    if filters.sectors:
        sector = _sector_of(segment)
        if sector not in filters.sectors:
            return False
    return True


def _include_region(region: str | None, filters: FilterSpec) -> bool:
    if not filters.regions:
        return True
    return region in filters.regions


def _node(node_id: str, label: str, node_type: str) -> dict[str, str]:
    return {"id": node_id, "label": label, "type": node_type}


def _edge(edge_id: str, source: str, target: str, edge_type: str) -> dict[str, str]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": edge_type,
    }


def _commodity_type(symbol: str, commodity_types: dict[str, str]) -> str:
    base = symbol.split("@", 1)[0]
    return commodity_types.get(base, "energy")


def _ensure_node(
    nodes: list[dict[str, str]],
    node_map: dict[str, dict[str, str]],
    node_id: str,
    label: str,
    node_type: str,
) -> None:
    if node_id in node_map:
        return
    new_node = _node(node_id, label, node_type)
    nodes.append(new_node)
    node_map[node_id] = new_node


def _build_facets(source: dict, segment_keys: list[str]) -> dict[str, list[str]]:
    model = source.get("model", {})
    seg_cfg = source.get("scoping") or {}
    return {
        "regions": sorted(model.get("regions", [])),
        "cases": sorted(c["name"] for c in model.get("cases", []) if "name" in c),
        "sectors": sorted(seg_cfg.get("sectors", [])),
        "scopes": sorted(segment_keys),
        "granularities": [
            "role",
            "provider",
            "provider_variant",
            "provider_variant_mode",
            "instance",
            "variant",
            "mode",
            "facility",
        ],
        "lenses": ["system", "trade"],
    }


def _prepare_source_for_graph(
    source: dict,
    commodities: dict[str, dict],
) -> tuple[dict, dict[str, dict[str, Any]]]:
    """Expand facility primitives for source-mode graph building."""
    if not source.get("facilities"):
        return source, {}
    model_years = list(source.get("model", {}).get("milestone_years", []) or [])
    transformed, facility_context = prepare_facilities(
        deepcopy(source),
        commodities,
        model_years,
    )
    return transformed, build_facility_variant_metadata(facility_context)


def _group_for_granularity(
    *,
    granularity: str,
    process_symbol: str,
    variant_id: str,
    role_id: str,
    provider_id: str | None,
    mode_id: str | None,
    facility_meta: dict[str, Any] | None,
) -> tuple[str, str, str]:
    requested = granularity
    if granularity == "variant":
        granularity = "provider_variant"
    elif granularity == "mode":
        granularity = "provider_variant_mode"
    elif granularity == "facility":
        granularity = "provider"

    if granularity == "instance":
        return f"instance:{process_symbol}", process_symbol, "instance"
    if granularity == "provider":
        node_type = "facility" if requested == "facility" else "provider"
        if provider_id:
            return f"provider:{provider_id}", provider_id, node_type
        if facility_meta:
            facility_id = str(facility_meta.get("facility_id", "facility"))
            return f"provider:{facility_id}", facility_id, node_type
        return f"provider:role:{role_id}", role_id, node_type
    if granularity == "provider_variant":
        node_type = "variant" if requested == "variant" else "provider_variant"
        if provider_id:
            label = f"{provider_id}::{variant_id}"
            return f"provider_variant:{provider_id}:{variant_id}", label, node_type
        return f"provider_variant:{variant_id}", variant_id, node_type
    if granularity == "provider_variant_mode":
        node_type = "mode" if requested == "mode" else "provider_variant_mode"
        resolved_mode = mode_id
        if not resolved_mode and facility_meta:
            resolved_mode = str(facility_meta.get("mode_id", "mode"))
        if provider_id and resolved_mode:
            label = f"{provider_id}::{variant_id}::{resolved_mode}"
            return (
                f"provider_variant_mode:{provider_id}:{variant_id}:{resolved_mode}",
                label,
                node_type,
            )
        if provider_id:
            label = f"{provider_id}::{variant_id}"
            return f"provider_variant_mode:{provider_id}:{variant_id}", label, node_type
        return f"provider_variant_mode:{variant_id}", variant_id, node_type
    return f"role:{role_id}", role_id, "role"


def _init_group_detail(
    *,
    group_id: str,
    label: str,
    node_type: str,
) -> dict[str, Any]:
    return {
        "id": group_id,
        "label": label,
        "type": node_type,
        "processes": set(),
        "regions": set(),
        "scopes": set(),
        "sectors": set(),
        "variants": set(),
        "roles": set(),
        "provider_ids": set(),
        "provider_kinds": set(),
        "sets": set(),
        "stages": set(),
        "facility_ids": set(),
        "template_ids": set(),
        "facility_classes": set(),
        "template_variants": set(),
        "mode_ids": set(),
        "baseline_modes": set(),
        "mode_ladders": set(),
        "mode_ladder_indexes": set(),
        "is_baseline_mode_flags": set(),
        "capacity_couplings": set(),
        "no_backsliding_flags": set(),
        "cap_bases": set(),
        "cap_units": set(),
        "ramp_rates": set(),
    }


def _sorted_non_null(values: set[Any]) -> list[Any]:
    return sorted(v for v in values if v is not None)


def _single_or_none(values: list[Any]) -> Any | None:
    if len(values) == 1:
        return values[0]
    return None


def _finalize_group_detail(detail: dict[str, Any]) -> dict[str, Any]:
    stages = _sorted_non_null(detail["stages"])
    facilities = _sorted_non_null(detail["facility_ids"])
    provider_ids = _sorted_non_null(detail["provider_ids"])
    provider_kinds = _sorted_non_null(detail["provider_kinds"])
    template_variants = _sorted_non_null(detail["template_variants"])
    modes = _sorted_non_null(detail["mode_ids"])
    baseline_modes = _sorted_non_null(detail["baseline_modes"])
    capacity_couplings = _sorted_non_null(detail["capacity_couplings"])
    cap_units = _sorted_non_null(detail["cap_units"])
    ramp_rates = _sorted_non_null(detail["ramp_rates"])

    mode_ladders = sorted(
        [list(ladder) for ladder in detail["mode_ladders"]],
        key=lambda ladder: tuple(ladder),
    )
    mode_ladder_indexes = _sorted_non_null(detail["mode_ladder_indexes"])
    baseline_flags = sorted(detail["is_baseline_mode_flags"])
    no_backsliding_flags = sorted(detail["no_backsliding_flags"])
    cap_bases = _sorted_non_null(detail["cap_bases"])

    return {
        "processes": sorted(detail["processes"]),
        "regions": sorted(detail["regions"]),
        "scopes": sorted(detail["scopes"]),
        "sectors": sorted(detail["sectors"]),
        "variants": sorted(detail["variants"]),
        "roles": sorted(detail["roles"]),
        "provider_ids": provider_ids,
        "provider_id": _single_or_none(provider_ids),
        "provider_kinds": provider_kinds,
        "provider_kind": _single_or_none(provider_kinds),
        "sets": sorted(detail["sets"]),
        "stages": stages,
        "stage": stages[0] if len(stages) == 1 else None,
        "facility_ids": facilities,
        "facility_id": _single_or_none(facilities),
        "template_ids": sorted(detail["template_ids"]),
        "facility_classes": sorted(detail["facility_classes"]),
        "template_variants": template_variants,
        "template_variant_id": _single_or_none(template_variants),
        "mode_ids": modes,
        "mode_id": _single_or_none(modes),
        "baseline_modes": baseline_modes,
        "baseline_mode": _single_or_none(baseline_modes),
        "mode_ladders": mode_ladders,
        "mode_ladder": _single_or_none(mode_ladders),
        "mode_ladder_indexes": mode_ladder_indexes,
        "mode_ladder_index": _single_or_none(mode_ladder_indexes),
        "is_baseline_mode": (
            baseline_flags[0] if len(baseline_flags) == 1 else None
        ),
        "capacity_couplings": capacity_couplings,
        "capacity_coupling": _single_or_none(capacity_couplings),
        "no_backsliding": (
            no_backsliding_flags[0] if len(no_backsliding_flags) == 1 else None
        ),
        "cap_bases": cap_bases,
        "cap_base": _single_or_none(cap_bases),
        "cap_units": cap_units,
        "cap_unit": _single_or_none(cap_units),
        "ramp_rates": ramp_rates,
        "ramp_rate": _single_or_none(ramp_rates),
    }


def build_source_system_graph(
    source: dict,
    *,
    granularity: str,
    filters: FilterSpec,
) -> dict[str, Any]:
    """Build source-mode graph using role/variant/availability expansion."""
    model = source.get("model", {})
    segment_keys = build_segments({"scoping": source.get("scoping") or {}})
    commodities = _normalize_commodities_for_new_syntax(model.get("commodities", []))
    prepared_source, facility_variant_meta = _prepare_source_for_graph(
        source, commodities
    )
    commodity_types = {k: v.get("type", "energy") for k, v in commodities.items()}

    roles = build_roles(prepared_source, commodities)
    variants = build_variants(prepared_source, roles, commodities)
    instances = expand_availability(prepared_source, variants, segment_keys)
    apply_process_parameters(instances, prepared_source)

    registry = NamingRegistry()
    variant_to_role = {
        variant.get("id"): variant.get("role")
        for variant in prepared_source.get("variants", [])
        if variant.get("id") and variant.get("role")
    }

    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    node_map: dict[str, dict[str, str]] = {}
    process_group_detail: dict[str, dict[str, Any]] = {}
    details_nodes: dict[str, dict[str, Any]] = {}
    details_edges: dict[str, dict[str, Any]] = {}
    seen_edges: set[tuple[str, str, str]] = set()

    for key, instance in sorted(instances.items()):
        if not _include_region(key.region, filters):
            continue
        if not _include_scope(key.segment, filters):
            continue

        process_symbol = registry.get_process_symbol(
            key.variant_id,
            key.region,
            key.segment,
            provider_kind=key.provider_kind,
            provider_id=key.provider_id,
            role_id=key.role_id,
            mode_id=key.mode_id,
        )
        facility_meta = facility_variant_meta.get(key.variant_id)
        role_id = variant_to_role.get(key.variant_id, instance.role.id)
        mode_id = key.mode_id
        provider_id = key.provider_id
        provider_kind = key.provider_kind

        current_node_id, current_label, current_type = _group_for_granularity(
            granularity=granularity,
            process_symbol=process_symbol,
            variant_id=key.variant_id,
            role_id=role_id,
            provider_id=provider_id,
            mode_id=mode_id,
            facility_meta=facility_meta,
        )

        if current_node_id not in process_group_detail:
            process_group_detail[current_node_id] = _init_group_detail(
                group_id=current_node_id,
                label=current_label,
                node_type=current_type,
            )
        group = process_group_detail[current_node_id]
        group["processes"].add(process_symbol)
        group["regions"].add(key.region)
        if key.segment:
            group["scopes"].add(key.segment)
        sector = _sector_of(key.segment)
        if sector:
            group["sectors"].add(sector)
        group["variants"].add(key.variant_id)
        group["roles"].add(role_id)
        if provider_id:
            group["provider_ids"].add(provider_id)
        if provider_kind:
            group["provider_kinds"].add(provider_kind)
        if mode_id:
            group["mode_ids"].add(mode_id)
        if instance.role.stage:
            group["stages"].add(instance.role.stage)

        if facility_meta:
            group["facility_ids"].add(facility_meta.get("facility_id"))
            group["template_ids"].add(facility_meta.get("template_id"))
            group["facility_classes"].add(facility_meta.get("class_name"))
            group["template_variants"].add(
                facility_meta.get("template_variant_id")
            )
            group["mode_ids"].add(facility_meta.get("mode_id"))
            group["baseline_modes"].add(facility_meta.get("baseline_mode"))
            mode_ladder = tuple(facility_meta.get("mode_ladder", []))
            if mode_ladder:
                group["mode_ladders"].add(mode_ladder)
            mode_ladder_index = facility_meta.get("mode_ladder_index")
            if mode_ladder_index is not None:
                group["mode_ladder_indexes"].add(mode_ladder_index)
            group["is_baseline_mode_flags"].add(
                bool(facility_meta.get("is_baseline_mode", False))
            )
            group["capacity_couplings"].add(
                facility_meta.get("capacity_coupling")
            )
            group["no_backsliding_flags"].add(
                bool(facility_meta.get("no_backsliding", True))
            )
            cap_base = facility_meta.get("cap_base")
            if cap_base is not None:
                group["cap_bases"].add(float(cap_base))
            group["cap_units"].add(facility_meta.get("cap_unit"))
            ramp_rate = facility_meta.get("ramp_rate")
            if ramp_rate is not None:
                group["ramp_rates"].add(float(ramp_rate))

        for inp in instance.variant.inputs:
            comm_node_id = f"commodity:{inp}"
            _ensure_node(nodes, node_map, comm_node_id, inp, "commodity")
            details_nodes.setdefault(
                comm_node_id,
                {
                    "commodity": inp,
                    "type": commodity_types.get(inp, "energy"),
                },
            )
            edge_key = (comm_node_id, current_node_id, "input")
            edge_id = f"edge:{comm_node_id}->{current_node_id}:input"
            if edge_key not in seen_edges:
                edges.append(_edge(edge_id, comm_node_id, current_node_id, "input"))
                details_edges[edge_id] = {
                    "commodity": inp,
                    "direction": "input",
                    "processes": set(),
                    "regions": set(),
                    "scopes": set(),
                }
                seen_edges.add(edge_key)
            details_edges[edge_id]["processes"].add(process_symbol)
            details_edges[edge_id]["regions"].add(key.region)
            if key.segment:
                details_edges[edge_id]["scopes"].add(key.segment)

        for out in instance.variant.outputs:
            comm_node_id = f"commodity:{out}"
            _ensure_node(nodes, node_map, comm_node_id, out, "commodity")
            ctype = commodity_types.get(out, "energy")
            details_nodes.setdefault(comm_node_id, {"commodity": out, "type": ctype})
            edge_type = "emission" if ctype == "emission" else "output"
            edge_key = (current_node_id, comm_node_id, edge_type)
            edge_id = f"edge:{current_node_id}->{comm_node_id}:{edge_type}"
            if edge_key not in seen_edges:
                edges.append(_edge(edge_id, current_node_id, comm_node_id, edge_type))
                details_edges[edge_id] = {
                    "commodity": out,
                    "direction": edge_type,
                    "processes": set(),
                    "regions": set(),
                    "scopes": set(),
                }
                seen_edges.add(edge_key)
            details_edges[edge_id]["processes"].add(process_symbol)
            details_edges[edge_id]["regions"].add(key.region)
            if key.segment:
                details_edges[edge_id]["scopes"].add(key.segment)

    for group_id in sorted(process_group_detail):
        group = process_group_detail[group_id]
        _ensure_node(nodes, node_map, group_id, group["label"], group["type"])
        details_nodes[group_id] = _finalize_group_detail(group)

    for edge_id, detail in details_edges.items():
        if isinstance(detail.get("processes"), set):
            detail["processes"] = sorted(detail["processes"])
        if isinstance(detail.get("regions"), set):
            detail["regions"] = sorted(detail["regions"])
            detail["region"] = (
                detail["regions"][0] if len(detail["regions"]) == 1 else None
            )
        if isinstance(detail.get("scopes"), set):
            detail["scopes"] = sorted(detail["scopes"])
            detail["scope"] = (
                detail["scopes"][0] if len(detail["scopes"]) == 1 else None
            )

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": _build_facets(prepared_source, segment_keys),
    }


def _iter_table_rows(tableir: dict, tag: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_spec in tableir.get("files", []):
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == tag:
                    for row in table.get("rows", []):
                        merged = dict(row)
                        merged["__file__"] = file_spec.get("path", "")
                        merged["__sheet__"] = sheet.get("name", "")
                        rows.append(merged)
    return rows


def build_compiled_system_graph(
    source: dict,
    tableir: dict,
    manifest: dict[str, Any] | None,
    *,
    granularity: str,
    filters: FilterSpec,
) -> dict[str, Any]:
    """Build compiled-mode system graph from FI_* tables and metadata."""
    model = source.get("model", {})
    segment_keys = build_segments({"scoping": source.get("scoping") or {}})
    commodities = _normalize_commodities_for_new_syntax(model.get("commodities", []))
    prepared_source, _ = _prepare_source_for_graph(source, commodities)
    commodity_types = {
        c.get("id") or c.get("name"): c.get("type", "energy")
        for c in model.get("commodities", [])
        if c.get("id") or c.get("name")
    }
    variant_to_role = {
        variant.get("id"): variant.get("role")
        for variant in prepared_source.get("variants", [])
        if variant.get("id") and variant.get("role")
    }

    metadata_map = tableir.get("metadata_map", {}).get("processes", {})
    fi_process_rows = _iter_table_rows(tableir, "~FI_PROCESS")
    fi_t_rows = _iter_table_rows(tableir, "~FI_T")

    manifest_sets: dict[str, list[str]] = {}
    if manifest:
        for proc in manifest.get("symbols", {}).get("processes", []):
            name = proc.get("name")
            sets = proc.get("sets", [])
            if isinstance(name, str):
                manifest_sets[name] = [str(s) for s in sets]

    process_region: dict[str, str | None] = {}
    selected_processes: set[str] = set()
    process_node_to_group: dict[str, str] = {}
    process_group_detail: dict[str, dict[str, Any]] = {}
    process_stage: dict[str, str | None] = {}
    process_scope: dict[str, str | None] = {}

    for row in fi_process_rows:
        process = row.get("process")
        region = row.get("region")
        if not process:
            continue

        meta = metadata_map.get(process, {}) if isinstance(metadata_map, dict) else {}
        segment = meta.get("scope")
        facility_meta = meta.get("facility")
        if not isinstance(facility_meta, dict):
            facility_meta = None
        if not _include_region(region, filters):
            continue
        if not _include_scope(segment, filters):
            continue

        selected_processes.add(process)
        process_region[process] = region
        process_stage[process] = meta.get("stage")
        process_scope[process] = segment
        variant_name = str(meta.get("variant") or process)
        provider_id = meta.get("provider")
        provider_kind = meta.get("provider_kind")
        mode_id = meta.get("mode")
        role_name = (
            variant_to_role.get(variant_name)
            or str(meta.get("role") or meta.get("stage") or "role")
        )

        group_id, group_label, group_type = _group_for_granularity(
            granularity=granularity,
            process_symbol=str(process),
            variant_id=variant_name,
            role_id=role_name,
            provider_id=provider_id,
            mode_id=mode_id,
            facility_meta=facility_meta,
        )

        process_node_to_group[process] = group_id
        if group_id not in process_group_detail:
            process_group_detail[group_id] = _init_group_detail(
                group_id=group_id,
                label=group_label,
                node_type=group_type,
            )
        detail = process_group_detail[group_id]
        detail["processes"].add(process)
        stage_name = meta.get("stage")
        if isinstance(stage_name, str) and stage_name:
            detail["stages"].add(stage_name)
        if region:
            detail["regions"].add(region)
        if segment:
            detail["scopes"].add(segment)
            sector = _sector_of(segment)
            if sector:
                detail["sectors"].add(sector)
        if provider_id:
            detail["provider_ids"].add(provider_id)
        if provider_kind:
            detail["provider_kinds"].add(provider_kind)
        if mode_id:
            detail["mode_ids"].add(mode_id)
        variant_name = meta.get("variant")
        if variant_name:
            detail["variants"].add(variant_name)
            mapped_role = variant_to_role.get(str(variant_name))
            if mapped_role:
                detail["roles"].add(mapped_role)
        if role_name:
            detail["roles"].add(role_name)

        if facility_meta:
            detail["facility_ids"].add(facility_meta.get("facility_id"))
            detail["template_ids"].add(facility_meta.get("template_id"))
            detail["facility_classes"].add(facility_meta.get("class_name"))
            detail["template_variants"].add(facility_meta.get("template_variant_id"))
            detail["mode_ids"].add(facility_meta.get("mode_id"))
            detail["baseline_modes"].add(facility_meta.get("baseline_mode"))
            mode_ladder = tuple(facility_meta.get("mode_ladder", []))
            if mode_ladder:
                detail["mode_ladders"].add(mode_ladder)
            mode_ladder_index = facility_meta.get("mode_ladder_index")
            if mode_ladder_index is not None:
                detail["mode_ladder_indexes"].add(mode_ladder_index)
            detail["is_baseline_mode_flags"].add(
                bool(facility_meta.get("is_baseline_mode", False))
            )
            detail["capacity_couplings"].add(facility_meta.get("capacity_coupling"))
            detail["no_backsliding_flags"].add(
                bool(facility_meta.get("no_backsliding", True))
            )
            cap_base = facility_meta.get("cap_base")
            if cap_base is not None:
                detail["cap_bases"].add(float(cap_base))
            detail["cap_units"].add(facility_meta.get("cap_unit"))
            ramp_rate = facility_meta.get("ramp_rate")
            if ramp_rate is not None:
                detail["ramp_rates"].add(float(ramp_rate))

        for set_name in manifest_sets.get(process, []):
            detail["sets"].add(set_name)
        if isinstance(row.get("sets"), str):
            for set_name in row.get("sets", "").split(","):
                set_name = set_name.strip()
                if set_name:
                    detail["sets"].add(set_name)

    nodes: list[dict[str, str]] = []
    node_map: dict[str, dict[str, str]] = {}
    details_nodes: dict[str, dict[str, Any]] = {}

    for group_id in sorted(process_group_detail.keys()):
        detail = process_group_detail[group_id]
        node = _node(group_id, detail["label"], detail["type"])
        nodes.append(node)
        node_map[group_id] = node
        details_nodes[group_id] = _finalize_group_detail(detail)

    edges: list[dict[str, str]] = []
    details_edges: dict[str, dict[str, Any]] = {}
    seen_edges: set[tuple[str, str, str]] = set()

    for row in fi_t_rows:
        process = row.get("process")
        if process not in selected_processes:
            continue
        group_id = process_node_to_group.get(process)
        if not group_id:
            continue

        commodity_in = row.get("commodity-in")
        if commodity_in:
            comm_node_id = f"commodity:{commodity_in}"
            if comm_node_id not in node_map:
                ctype = _commodity_type(str(commodity_in), commodity_types)
                _ensure_node(
                    nodes,
                    node_map,
                    comm_node_id,
                    str(commodity_in),
                    "commodity",
                )
                details_nodes[comm_node_id] = {"commodity": commodity_in, "type": ctype}
            edge_key = (comm_node_id, group_id, "input")
            if edge_key not in seen_edges:
                edge_id = f"edge:{comm_node_id}->{group_id}:input"
                edges.append(_edge(edge_id, comm_node_id, group_id, "input"))
                details_edges[edge_id] = {
                    "commodity": commodity_in,
                    "direction": "input",
                    "processes": set(),
                    "regions": set(),
                    "scopes": set(),
                }
                seen_edges.add(edge_key)
            edge_id = f"edge:{comm_node_id}->{group_id}:input"
            details_edges[edge_id]["processes"].add(process)
            details_edges[edge_id]["regions"].add(process_region.get(process))
            details_edges[edge_id]["scopes"].add(process_scope.get(process))

        commodity_out = row.get("commodity-out")
        if commodity_out:
            comm_node_id = f"commodity:{commodity_out}"
            if comm_node_id not in node_map:
                ctype = _commodity_type(str(commodity_out), commodity_types)
                _ensure_node(
                    nodes,
                    node_map,
                    comm_node_id,
                    str(commodity_out),
                    "commodity",
                )
                details_nodes[comm_node_id] = {
                    "commodity": commodity_out,
                    "type": ctype,
                }
            ctype = _commodity_type(str(commodity_out), commodity_types)
            edge_type = "emission" if ctype == "emission" else "output"
            edge_key = (group_id, comm_node_id, edge_type)
            if edge_key not in seen_edges:
                edge_id = f"edge:{group_id}->{comm_node_id}:{edge_type}"
                edges.append(_edge(edge_id, group_id, comm_node_id, edge_type))
                details_edges[edge_id] = {
                    "commodity": commodity_out,
                    "direction": edge_type,
                    "processes": set(),
                    "regions": set(),
                    "scopes": set(),
                }
                seen_edges.add(edge_key)
            edge_id = f"edge:{group_id}->{comm_node_id}:{edge_type}"
            details_edges[edge_id]["processes"].add(process)
            details_edges[edge_id]["regions"].add(process_region.get(process))
            details_edges[edge_id]["scopes"].add(process_scope.get(process))

    for edge_id, detail in details_edges.items():
        if isinstance(detail.get("processes"), set):
            detail["processes"] = sorted(detail["processes"])
        if isinstance(detail.get("regions"), set):
            regions = sorted(r for r in detail["regions"] if r is not None)
            detail["regions"] = regions
            detail["region"] = regions[0] if len(regions) == 1 else None
        if isinstance(detail.get("scopes"), set):
            scopes = sorted(s for s in detail["scopes"] if s is not None)
            detail["scopes"] = scopes
            detail["scope"] = scopes[0] if len(scopes) == 1 else None

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": _build_facets(prepared_source, segment_keys),
    }


def _trade_rows_from_tableir(tableir: dict) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for row in _iter_table_rows(tableir, "~TRADELINKS"):
        region_cols = [k for k in row.keys() if k not in {"__file__", "__sheet__"}]
        if not region_cols:
            continue
        commodity_col = region_cols[0]
        origin = row.get(commodity_col)
        if not isinstance(origin, str) or not origin:
            continue
        for destination in region_cols[1:]:
            if _is_truthy_trade_cell(row.get(destination)):
                links.append({
                    "commodity": commodity_col,
                    "origin": origin,
                    "destination": destination,
                    "sheet": row.get("__sheet__", ""),
                    "file": row.get("__file__", ""),
                })
    return links


def build_trade_graph(
    source: dict,
    *,
    filters: FilterSpec,
    trade_links: list[dict[str, Any]],
    ire_processes: list[dict[str, Any]] | None = None,
    trade_attrs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build commodity-region trade lens graph."""
    model = source.get("model", {})
    segment_keys = build_segments({"scoping": source.get("scoping") or {}})

    nodes: list[dict[str, str]] = []
    node_map: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    details_nodes: dict[str, dict[str, Any]] = {}
    details_edges: dict[str, dict[str, Any]] = {}

    ire_processes = ire_processes or []
    trade_attrs = trade_attrs or []

    for link in trade_links:
        origin = link.get("origin")
        destination = link.get("destination")
        commodity = link.get("commodity")
        if not (origin and destination and commodity):
            continue
        if filters.regions and (
            origin not in filters.regions or destination not in filters.regions
        ):
            continue

        source_id = f"trade:{commodity}:{origin}"
        target_id = f"trade:{commodity}:{destination}"
        _ensure_node(
            nodes,
            node_map,
            source_id,
            f"{commodity}@{origin}",
            "trade_commodity",
        )
        _ensure_node(
            nodes,
            node_map,
            target_id,
            f"{commodity}@{destination}",
            "trade_commodity",
        )
        details_nodes[source_id] = {"commodity": commodity, "region": origin}
        details_nodes[target_id] = {"commodity": commodity, "region": destination}

        edge_id = f"trade:{commodity}:{origin}->{destination}"
        edges.append(_edge(edge_id, source_id, target_id, "trade"))

        matching_ire = []
        commodity_upper = str(commodity).upper()
        for proc in ire_processes:
            name = str(proc.get("name", ""))
            if commodity_upper not in name:
                continue
            if origin not in name and destination not in name:
                continue
            matching_ire.append(proc)

        matching_attrs = []
        for row in trade_attrs:
            selector = str(row.get("pset_pn", "")).upper()
            if commodity_upper in selector:
                matching_attrs.append(row)

        details_edges[edge_id] = {
            "commodity": commodity,
            "origin": origin,
            "destination": destination,
            "sheet": link.get("sheet"),
            "ire_processes": matching_ire,
            "trade_attributes": matching_attrs,
        }

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": {
            **_build_facets(source, segment_keys),
            "regions": sorted(model.get("regions", [])),
        },
    }


def extract_trade_links_from_source(source: dict) -> list[dict[str, Any]]:
    links = []
    for link in source.get("model", {}).get("trade_links", []):
        origin = link.get("origin")
        destination = link.get("destination")
        commodity = link.get("commodity")
        if not (origin and destination and commodity):
            continue
        links.append({
            "commodity": commodity,
            "origin": origin,
            "destination": destination,
            "bidirectional": bool(link.get("bidirectional", True)),
            "efficiency": link.get("efficiency"),
        })
        if link.get("bidirectional", True):
            links.append({
                "commodity": commodity,
                "origin": destination,
                "destination": origin,
                "bidirectional": True,
                "efficiency": link.get("efficiency"),
            })
    return links


def extract_trade_links_from_compiled(tableir: dict) -> list[dict[str, Any]]:
    return _trade_rows_from_tableir(tableir)


def extract_trade_attrs_from_compiled(tableir: dict) -> list[dict[str, Any]]:
    attrs: list[dict[str, Any]] = []
    for row in _iter_table_rows(tableir, "~TFM_INS"):
        if "pset_pn" in row:
            attrs.append(row)
    return attrs


def extract_ire_symbols(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest:
        return []
    ire_rows: list[dict[str, Any]] = []
    for proc in manifest.get("symbols", {}).get("processes", []):
        sets = [str(s).upper() for s in proc.get("sets", [])]
        if "IRE" in sets:
            ire_rows.append(proc)
    return ire_rows
