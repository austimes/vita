"""Graph builders for v0.2 CSIR/CPIR artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FilterSpec:
    regions: set[str]
    sectors: set[str]
    scopes: set[str]


def infer_run_id(source: dict[str, Any]) -> str | None:
    """Infer a run id when the source defines exactly one run."""
    runs = source.get("runs")
    if not isinstance(runs, list) or len(runs) != 1:
        return None
    run_id = runs[0].get("id")
    return str(run_id) if run_id else None


def _commodity_node_id(symbol: str) -> str:
    return f"commodity:{symbol}"


def _group_key(
    granularity: str,
    process: dict[str, Any],
    *,
    technology_to_role: dict[str, str],
) -> tuple[str, str, str]:
    if granularity == "instance":
        process_id = str(process["id"])
        return (f"instance:{process_id}", process_id, "instance")
    role_instance = process.get("source_role_instance")
    if role_instance:
        role_instance = str(role_instance)
        region = str(process["model_region"])
        asset_name = role_instance.split(".", 1)[-1].split("@", 1)[0]
        return (f"role:{role_instance}", f"{asset_name}@{region}", "role")
    role_name = technology_to_role.get(
        str(process.get("technology", "")),
        str(process.get("technology", "")) or str(process.get("id", "")),
    )
    region = str(process["model_region"])
    source_opportunity = process.get("source_opportunity")
    if source_opportunity:
        return (
            f"role:opportunity:{source_opportunity}",
            f"{role_name}@{region} [opportunity:{source_opportunity}]",
            "role",
        )
    return (f"role:{role_name}@{region}", f"{role_name}@{region}", "role")


def _display_commodity(symbol: str, commodity_view: str) -> str:
    if commodity_view == "collapse_scope":
        return symbol.split("@", 1)[0]
    return symbol


def build_v0_2_system_graph(
    *,
    csir: dict[str, Any],
    cpir: dict[str, Any],
    granularity: str,
    commodity_view: str,
) -> dict[str, Any]:
    """Build a RES graph view from v0.2 compiled artifacts."""
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    node_map: dict[str, dict[str, str]] = {}
    details_nodes: dict[str, dict[str, Any]] = {}
    details_edges: dict[str, dict[str, Any]] = {}
    role_instances = {
        item["id"]: item for item in csir.get("technology_role_instances", [])
    }
    technology_roles = {item["id"]: item for item in csir.get("technology_roles", [])}
    technology_to_role = {
        str(technology): str(role["id"])
        for role in technology_roles.values()
        for technology in role.get("technologies", [])
    }
    opportunities = {item["id"]: item for item in csir.get("opportunities", [])}

    for process in cpir.get("processes", []):
        group_id, label, node_type = _group_key(
            granularity,
            process,
            technology_to_role=technology_to_role,
        )
        if group_id not in node_map:
            node = {"id": group_id, "label": label, "type": node_type}
            nodes.append(node)
            node_map[group_id] = node
            if node_type == "instance":
                details_nodes[group_id] = {
                    "technology": process.get("technology"),
                    "model_region": process.get("model_region"),
                    "model_stock_metric": process.get("model_stock_metric"),
                    "source_role_instance": process.get("source_role_instance"),
                    "source_opportunity": process.get("source_opportunity"),
                    "initial_stock": process.get("initial_stock"),
                }
            else:
                role_instance_id = process.get("source_role_instance", "")
                role_instance = role_instances.get(role_instance_id, {})
                role_name = technology_to_role.get(str(process.get("technology", "")))
                opportunity = (
                    opportunities.get(process.get("source_opportunity", "")) or {}
                )
                details_nodes[group_id] = {
                    "technology_role": role_instance.get("technology_role")
                    or role_name,
                    "model_region": process.get("model_region"),
                    "group_origin": (
                        "opportunity"
                        if process.get("source_opportunity")
                        else "role_instance"
                    ),
                    "source_role_instance": role_instance_id or None,
                    "source_asset": role_instance.get("source_asset"),
                    "source_opportunity": process.get("source_opportunity"),
                    "available_technologies": role_instance.get(
                        "available_technologies",
                        [process.get("technology")]
                        if process.get("technology")
                        else [],
                    ),
                    "max_new_capacity": opportunity.get("max_new_capacity"),
                }

        for flow in process.get("flows", []):
            commodity = str(flow.get("commodity", ""))
            commodity_label = _display_commodity(commodity, commodity_view)
            commodity_node_id = _commodity_node_id(commodity_label)
            if commodity_node_id not in node_map:
                commodity_kind = (
                    commodity.split(":", 1)[0] if ":" in commodity else "commodity"
                )
                node = {
                    "id": commodity_node_id,
                    "label": commodity_label,
                    "type": "commodity",
                }
                nodes.append(node)
                node_map[commodity_node_id] = node
                details_nodes[commodity_node_id] = {
                    "commodity": commodity,
                    "kind": commodity_kind,
                }
            direction = str(flow.get("direction", ""))
            if direction == "in":
                source_id, target_id, edge_type = commodity_node_id, group_id, "input"
            else:
                source_id, target_id, edge_type = group_id, commodity_node_id, direction
            edge_id = f"{source_id}->{target_id}:{commodity}:{direction}"
            if edge_id in details_edges:
                continue
            edges.append(
                {
                    "id": edge_id,
                    "source": source_id,
                    "target": target_id,
                    "type": edge_type,
                }
            )
            details_edges[edge_id] = {
                "commodity": commodity,
                "direction": direction,
                "coefficient": flow.get("coefficient"),
                "technology": process.get("technology"),
                "source_role_instance": process.get("source_role_instance"),
            }

    nodes.sort(key=lambda node: (node["type"], node["label"], node["id"]))
    edges.sort(
        key=lambda edge: (
            edge["type"],
            edge["source"],
            edge["target"],
            edge["id"],
        )
    )
    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": {
            "regions": sorted(csir.get("model_regions", []) or []),
            "cases": [],
            "sectors": [],
            "scopes": [],
            "granularities": ["role", "instance"],
            "commodity_views": ["scoped", "collapse_scope"],
            "lenses": ["system", "trade"],
        },
    }


def build_v0_2_trade_graph(
    *,
    csir: dict[str, Any] | None,
    cpir: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a trade lens from v0.2 CSIR/CPIR network data."""
    model_regions = list((csir or {}).get("model_regions", []) or [])
    nodes = [
        {"id": f"region:{region}", "label": region, "type": "region"}
        for region in sorted(model_regions)
    ]
    details_nodes = {node["id"]: {"region": node["label"]} for node in nodes}
    edges: list[dict[str, str]] = []
    details_edges: dict[str, dict[str, Any]] = {}

    for arc in (cpir or {}).get("network_arcs", []):
        source_id = f"region:{arc['from']}"
        target_id = f"region:{arc['to']}"
        edge_id = f"trade:{arc['id']}"
        edges.append(
            {
                "id": edge_id,
                "source": source_id,
                "target": target_id,
                "type": "trade",
            }
        )
        details_edges[edge_id] = {
            "commodity": arc.get("commodity"),
            "source_network": arc.get("source_network") or arc.get("network"),
            "source_link": arc.get("source_link") or arc.get("link_id"),
            "existing_transfer_capacity": arc.get("existing_transfer_capacity"),
            "max_new_capacity": arc.get("max_new_capacity"),
        }

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": {
            "regions": sorted(model_regions),
            "cases": [],
            "sectors": [],
            "scopes": [],
            "granularities": ["role", "instance"],
            "commodity_views": ["scoped", "collapse_scope"],
            "lenses": ["system", "trade"],
        },
    }
