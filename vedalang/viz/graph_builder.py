"""Build visualization graph from VedaLang AST.

Converts a VedaLang model into a graph structure suitable for
Cytoscape.js visualization.
"""

from __future__ import annotations

from typing import Any

DEFAULT_ACTIVITY_UNIT = "PJ"
DEFAULT_CAPACITY_UNIT = "GW"
DEFAULT_COMMODITY_UNITS = {
    "fuel": "PJ",
    "energy": "PJ",
    "service": "PJ",
    "material": "Mt",
    "emission": "Mt",
    "money": "MUSD",
    "other": "PJ",
}


def build_graph(source: dict[str, Any]) -> dict[str, Any]:
    """Convert VedaLang source to visualization graph.

    Args:
        source: Parsed VedaLang source (with 'model' key or direct model dict)

    Returns:
        Graph dict with 'nodes' and 'edges' arrays for Cytoscape.js
    """
    model = source.get("model", source)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    commodity_nodes = _build_commodity_nodes(model)
    process_nodes = _build_process_nodes(model)
    nodes.extend(commodity_nodes)
    nodes.extend(process_nodes)

    process_edges = _build_process_edges(model)
    trade_edges = _build_trade_edges(model)
    edges.extend(process_edges)
    edges.extend(trade_edges)

    return {
        "modelName": model.get("name", "Unnamed Model"),
        "regions": model.get("regions", []),
        "nodes": nodes,
        "edges": edges,
    }


def _build_commodity_nodes(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Build commodity nodes."""
    nodes = []
    commodities = model.get("commodities", [])

    for comm in commodities:
        name = comm.get("name") or comm.get("id", "")
        ctype = comm.get("type", "energy")
        unit = comm.get("unit") or DEFAULT_COMMODITY_UNITS.get(ctype, "PJ")
        nodes.append({
            "data": {
                "id": f"C:{name}",
                "label": f"{name}\n({unit})",
                "type": "commodity",
                "commodityType": ctype,
                "unit": unit,
                "description": comm.get("description", ""),
            }
        })

    return nodes


def _build_process_nodes(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Build process nodes."""
    nodes = []
    processes = model.get("processes", [])

    for proc in processes:
        name = proc.get("name", "")
        sets = proc.get("sets", [])
        capacity_unit = proc.get("capacity_unit", DEFAULT_CAPACITY_UNIT)
        activity_unit = proc.get("activity_unit", DEFAULT_ACTIVITY_UNIT)

        process_class = _classify_process(sets)

        nodes.append({
            "data": {
                "id": f"P:{name}",
                "label": f"{name}\ncap: {capacity_unit} | act: {activity_unit}",
                "type": "process",
                "processClass": process_class,
                "sets": sets,
                "primaryCommodityGroup": proc.get("primary_commodity_group", ""),
                "description": proc.get("description", ""),
                "efficiency": proc.get("efficiency"),
                "invcost": proc.get("invcost"),
                "life": proc.get("life"),
                "stock": proc.get("stock"),
                "capacityUnit": capacity_unit,
                "activityUnit": activity_unit,
            }
        })

    return nodes


def _classify_process(sets: list[str]) -> str:
    """Classify process by its sets for styling."""
    sets_upper = [s.upper() for s in sets]

    if "IMP" in sets_upper or "IMPORT" in sets_upper:
        return "import"
    if "EXP" in sets_upper or "EXPORT" in sets_upper:
        return "export"
    if "ELE" in sets_upper:
        return "generation"
    if "DMD" in sets_upper:
        return "demand"
    if "STG" in sets_upper or "STS" in sets_upper:
        return "storage"
    if "IRE" in sets_upper:
        return "trade"

    return "conversion"


def _build_process_edges(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Build edges from process inputs/outputs."""
    edges = []
    processes = model.get("processes", [])

    for proc in processes:
        proc_name = proc.get("name", "")
        proc_id = f"P:{proc_name}"

        inputs = _normalize_flows(proc.get("input"), proc.get("inputs", []))
        for flow in inputs:
            comm_name = flow.get("commodity", "")
            edges.append({
                "data": {
                    "id": f"E:{comm_name}->{proc_name}",
                    "source": f"C:{comm_name}",
                    "target": proc_id,
                    "kind": "input",
                    "commodity": comm_name,
                }
            })

        outputs = _normalize_flows(proc.get("output"), proc.get("outputs", []))
        for flow in outputs:
            comm_name = flow.get("commodity", "")
            is_emission = flow.get("emission_factor") is not None

            edges.append({
                "data": {
                    "id": f"E:{proc_name}->{comm_name}",
                    "source": proc_id,
                    "target": f"C:{comm_name}",
                    "kind": "emission" if is_emission else "output",
                    "commodity": comm_name,
                    "emissionFactor": flow.get("emission_factor"),
                    "share": flow.get("share"),
                }
            })

    return edges


def _normalize_flows(
    single: str | dict | None, multiple: list[dict]
) -> list[dict[str, Any]]:
    """Normalize input/output to list of flow dicts."""
    if multiple:
        return multiple

    if single is None:
        return []

    if isinstance(single, str):
        return [{"commodity": single}]

    if isinstance(single, dict):
        return [single]

    return []


def _build_trade_edges(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Build edges from trade links."""
    edges = []
    trade_links = model.get("trade_links", [])

    for link in trade_links:
        origin = link.get("origin", "")
        dest = link.get("destination", "")
        comm = link.get("commodity", "")
        bidirectional = link.get("bidirectional", False)

        edge_id = f"T:{comm}:{origin}->{dest}"
        edges.append({
            "data": {
                "id": edge_id,
                "source": f"C:{comm}",
                "target": f"C:{comm}",
                "kind": "trade",
                "commodity": comm,
                "origin": origin,
                "destination": dest,
                "bidirectional": bidirectional,
                "efficiency": link.get("efficiency"),
            }
        })

    return edges
