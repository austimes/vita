"""Graph model builders for RES query engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vedalang.compiler.compiler import _normalize_commodities_for_new_syntax
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
        "granularities": ["role", "variant", "instance"],
        "lenses": ["system", "trade"],
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
    commodity_types = {k: v.get("type", "energy") for k, v in commodities.items()}

    roles = build_roles(source, commodities)
    variants = build_variants(source, roles, commodities)
    instances = expand_availability(source, variants, segment_keys)
    apply_process_parameters(instances, source)

    registry = NamingRegistry()
    variant_to_role = {
        variant.get("id"): variant.get("role")
        for variant in source.get("process_variants", [])
        if variant.get("id") and variant.get("role")
    }

    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    node_map: dict[str, dict[str, str]] = {}
    details_nodes: dict[str, dict[str, Any]] = {}
    details_edges: dict[str, dict[str, Any]] = {}
    seen_edges: set[tuple[str, str, str]] = set()

    for key, instance in sorted(instances.items()):
        if not _include_region(key.region, filters):
            continue
        if not _include_scope(key.segment, filters):
            continue

        process_symbol = registry.get_process_symbol(
            key.variant_id, key.region, key.segment
        )
        process_node_id = f"instance:{process_symbol}"
        variant_node_id = f"variant:{key.variant_id}"
        role_id = variant_to_role.get(key.variant_id, instance.role.id)
        role_node_id = f"role:{role_id}"

        current_node_id = role_node_id
        current_label = role_id
        current_type = "role"

        if granularity == "variant":
            current_node_id = variant_node_id
            current_label = key.variant_id
            current_type = "variant"
        elif granularity == "instance":
            current_node_id = process_node_id
            current_label = process_symbol
            current_type = "instance"

        _ensure_node(nodes, node_map, current_node_id, current_label, current_type)
        details_nodes.setdefault(
            current_node_id,
            {
                "variant": key.variant_id,
                "role": role_id,
                "region": key.region,
                "scope": key.segment,
                "sector": _sector_of(key.segment),
                "stage": instance.role.stage,
                "processes": set(),
            },
        )
        details_nodes[current_node_id]["processes"].add(process_symbol)

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
            if edge_key not in seen_edges:
                edge_id = f"edge:{comm_node_id}->{current_node_id}:input"
                edges.append(_edge(edge_id, comm_node_id, current_node_id, "input"))
                details_edges[edge_id] = {
                    "commodity": inp,
                    "direction": "input",
                    "process": process_symbol,
                    "region": key.region,
                    "scope": key.segment,
                }
                seen_edges.add(edge_key)

        for out in instance.variant.outputs:
            comm_node_id = f"commodity:{out}"
            _ensure_node(nodes, node_map, comm_node_id, out, "commodity")
            ctype = commodity_types.get(out, "energy")
            details_nodes.setdefault(comm_node_id, {"commodity": out, "type": ctype})
            edge_type = "emission" if ctype == "emission" else "output"
            edge_key = (current_node_id, comm_node_id, edge_type)
            if edge_key not in seen_edges:
                edge_id = f"edge:{current_node_id}->{comm_node_id}:{edge_type}"
                edges.append(_edge(edge_id, current_node_id, comm_node_id, edge_type))
                details_edges[edge_id] = {
                    "commodity": out,
                    "direction": edge_type,
                    "process": process_symbol,
                    "region": key.region,
                    "scope": key.segment,
                }
                seen_edges.add(edge_key)

    for node_id, node_detail in details_nodes.items():
        processes = node_detail.get("processes")
        if isinstance(processes, set):
            node_detail["processes"] = sorted(processes)

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": _build_facets(source, segment_keys),
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
    commodity_types = {
        c.get("id") or c.get("name"): c.get("type", "energy")
        for c in model.get("commodities", [])
        if c.get("id") or c.get("name")
    }
    variant_to_role = {
        variant.get("id"): variant.get("role")
        for variant in source.get("process_variants", [])
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

    for row in fi_process_rows:
        process = row.get("process")
        region = row.get("region")
        if not process:
            continue

        meta = metadata_map.get(process, {}) if isinstance(metadata_map, dict) else {}
        segment = meta.get("scope")
        if not _include_region(region, filters):
            continue
        if not _include_scope(segment, filters):
            continue

        selected_processes.add(process)
        process_region[process] = region

        if granularity == "instance":
            group_id = f"instance:{process}"
            group_label = process
            group_type = "instance"
        elif granularity == "variant":
            variant = str(meta.get("variant") or process)
            group_id = f"variant:{variant}"
            group_label = variant
            group_type = "variant"
        else:
            variant = str(meta.get("variant") or "")
            role = variant_to_role.get(variant) or str(meta.get("stage") or "role")
            group_id = f"role:{role}"
            group_label = role
            group_type = "role"

        process_node_to_group[process] = group_id
        if group_id not in process_group_detail:
            process_group_detail[group_id] = {
                "id": group_id,
                "label": group_label,
                "type": group_type,
                "processes": set(),
                "regions": set(),
                "scopes": set(),
                "variants": set(),
                "roles": set(),
                "sets": set(),
                "stages": set(),
            }
        detail = process_group_detail[group_id]
        detail["processes"].add(process)
        stage_name = meta.get("stage")
        if isinstance(stage_name, str) and stage_name:
            detail["stages"].add(stage_name)
        if region:
            detail["regions"].add(region)
        if segment:
            detail["scopes"].add(segment)
        variant_name = meta.get("variant")
        if variant_name:
            detail["variants"].add(variant_name)
            mapped_role = variant_to_role.get(str(variant_name))
            if mapped_role:
                detail["roles"].add(mapped_role)
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
        stages_sorted = sorted(detail["stages"])
        node = _node(group_id, detail["label"], detail["type"])
        nodes.append(node)
        node_map[group_id] = node
        details_nodes[group_id] = {
            "processes": sorted(detail["processes"]),
            "regions": sorted(detail["regions"]),
            "scopes": sorted(detail["scopes"]),
            "variants": sorted(detail["variants"]),
            "roles": sorted(detail["roles"]),
            "sets": sorted(detail["sets"]),
            "stages": stages_sorted,
            "stage": stages_sorted[0] if len(stages_sorted) == 1 else None,
        }

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
                    "process": process,
                    "region": process_region.get(process),
                }
                seen_edges.add(edge_key)

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
                    "process": process,
                    "region": process_region.get(process),
                }
                seen_edges.add(edge_key)

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": _build_facets(source, segment_keys),
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
