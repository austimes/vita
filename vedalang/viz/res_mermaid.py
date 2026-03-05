"""Generate Mermaid diagram from VedaLang RES graph.

This module provides both programmatic API and CLI for generating
Mermaid flowcharts from VedaLang models.
"""

import argparse
import sys
from pathlib import Path

import yaml

from vedalang.conventions import stage_label, stage_order

DEFAULT_ACTIVITY_UNIT = "PJ"
DEFAULT_CAPACITY_UNIT = "GW"


def build_res_graph(parsed: dict, include_variants: bool = False) -> dict:
    """Build a Reference Energy System graph from a parsed VedaLang document.

    Args:
        parsed: The full parsed VedaLang document.
        include_variants: If True, include variants as nodes within roles.

    Returns:
        A dict with 'nodes' and 'edges' lists representing the RES graph.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    # Handle both nested (model: {...}) and flat structures
    model = parsed.get("model", parsed)

    # Extract commodities (support both 'id' and 'name' fields)
    for commodity in model.get("commodities", []) or []:
        cid = commodity.get("id") or commodity.get("name")
        if cid:
            nodes.append({
                "id": cid,
                "label": cid,
                "kind": "commodity",
                "type": commodity.get("kind") or commodity.get("type"),
                "unit": commodity.get("unit"),
                "stage": None,
            })

    # Build role -> variants mapping
    role_variants: dict[str, list[dict]] = {}
    for variant in parsed.get("variants", []) or []:
        role_id = variant.get("role")
        if role_id:
            role_variants.setdefault(role_id, []).append(variant)

    def _first_non_empty(items):
        for item in items:
            if item:
                return item
        return None

    # Extract roles (new P4 syntax) - these define the RES topology
    for role in parsed.get("roles", []) or []:
        rid = role.get("id") or role.get("name")
        if rid:
            role_activity_unit = role.get("activity_unit") or _first_non_empty(
                v.get("activity_unit") for v in role_variants.get(rid, [])
            )
            role_capacity_unit = role.get("capacity_unit") or _first_non_empty(
                v.get("capacity_unit") for v in role_variants.get(rid, [])
            )
            nodes.append({
                "id": rid,
                "label": rid,
                "kind": "process",
                "type": "role",
                "stage": role.get("stage"),
                "activity_unit": role_activity_unit,
                "capacity_unit": role_capacity_unit,
            })

            # Add variant nodes if requested
            if include_variants and rid in role_variants:
                for variant in role_variants[rid]:
                    vid = variant.get("id") or variant.get("name")
                    if vid:
                        nodes.append({
                            "id": vid,
                            "label": vid,
                            "kind": "process",
                            "type": "variant",
                            "stage": role.get("stage"),
                            "parentRole": rid,
                            "activity_unit": (
                                variant.get("activity_unit") or role_activity_unit
                            ),
                            "capacity_unit": (
                                variant.get("capacity_unit") or role_capacity_unit
                            ),
                        })

            # Helper to extract commodity IDs from flow lists
            def _commodity_ids(items):
                ids = []
                for item in items or []:
                    cid = item.get("commodity") if isinstance(item, dict) else item
                    if cid:
                        ids.append(cid)
                return ids

            # Role contract (required_inputs/required_outputs)
            role_req_inputs = set(_commodity_ids(role.get("required_inputs")))
            role_req_outputs = set(_commodity_ids(role.get("required_outputs")))

            if include_variants:
                # Variants view: each variant shows its own explicit I/O
                for variant in role_variants.get(rid, []):
                    vid = variant.get("id") or variant.get("name")
                    if vid:
                        for cid in _commodity_ids(variant.get("inputs")):
                            edges.append(
                                {
                                    "from": cid,
                                    "to": vid,
                                    "kind": "input",
                                    "commodityId": cid,
                                }
                            )
                        for cid in _commodity_ids(variant.get("outputs")):
                            edges.append(
                                {
                                    "from": vid,
                                    "to": cid,
                                    "kind": "output",
                                    "commodityId": cid,
                                }
                            )
            else:
                # Roles view: show contract (required_inputs/required_outputs)
                # plus union of variant I/O for a complete picture
                all_inputs = set(role_req_inputs)
                all_outputs = set(role_req_outputs)
                for variant in role_variants.get(rid, []):
                    all_inputs.update(_commodity_ids(variant.get("inputs")))
                    all_outputs.update(_commodity_ids(variant.get("outputs")))

                for cid in all_inputs:
                    edges.append(
                        {
                            "from": cid,
                            "to": rid,
                            "kind": "input",
                            "commodityId": cid,
                        }
                    )
                for cid in all_outputs:
                    edges.append(
                        {
                            "from": rid,
                            "to": cid,
                            "kind": "output",
                            "commodityId": cid,
                        }
                    )

    # Also support legacy 'processes' syntax for backward compatibility
    for process in model.get("processes", []) or []:
        name = process.get("name") or process.get("id")
        if name:
            nodes.append({
                "id": name,
                "label": name,
                "kind": "process",
                "type": process.get("type"),
                "stage": process.get("stage"),
                "activity_unit": process.get("activity_unit"),
                "capacity_unit": process.get("capacity_unit"),
            })

            inputs = process.get("inputs", []) or []
            if not inputs:
                single_input = process.get("input")
                if single_input:
                    inputs = [single_input]

            for inp in inputs:
                inp_id = inp.get("commodity") if isinstance(inp, dict) else inp
                if inp_id:
                    edges.append({
                        "from": inp_id,
                        "to": name,
                        "kind": "input",
                        "commodityId": inp_id,
                    })

            outputs = process.get("outputs", []) or []
            if not outputs:
                single_output = process.get("output")
                if single_output:
                    outputs = [single_output]

            for out in outputs:
                out_id = out.get("commodity") if isinstance(out, dict) else out
                if out_id:
                    edges.append({
                        "from": name,
                        "to": out_id,
                        "kind": "output",
                        "commodityId": out_id,
                    })

    return {"nodes": nodes, "edges": edges}


def sanitize_id(s: str) -> str:
    """Sanitize a string for use as a Mermaid node ID."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in s)


def _escape_label(s: str) -> str:
    """Escape Mermaid label text."""
    return s.replace('"', '\\"')


def _format_commodity_label(node: dict) -> str:
    """Build commodity label with unit suffix."""
    label = str(node.get("label", node["id"]))
    unit = node.get("unit")
    if unit:
        return _escape_label(f"{label}<br/>({unit})")
    return _escape_label(label)


def _format_process_label(node: dict) -> str:
    """Build process label with capacity/activity units."""
    label = str(node.get("label", node["id"]))
    cap_unit = node.get("capacity_unit") or DEFAULT_CAPACITY_UNIT
    act_unit = node.get("activity_unit") or DEFAULT_ACTIVITY_UNIT
    return _escape_label(f"{label}<br/>cap: {cap_unit} | act: {act_unit}")


def graph_to_mermaid(graph: dict) -> str:
    """Convert a RES graph to Mermaid flowchart syntax.

    Args:
        graph: Dict with 'nodes' and 'edges' lists.

    Returns:
        Mermaid flowchart code as a string.
    """
    lines = ["flowchart LR"]

    # Define stage order for left-to-right layout
    stage_rank = stage_order(include_demand=True)

    # Separate nodes by type
    commodity_nodes = []
    role_nodes = []
    variant_nodes = []

    for node in graph.get("nodes", []):
        if node["kind"] == "commodity":
            commodity_nodes.append(node)
        elif node.get("type") == "variant":
            variant_nodes.append(node)
        else:
            role_nodes.append(node)

    # Check if we have variants (determines rendering mode)
    has_variants = len(variant_nodes) > 0

    # Build role -> variants mapping for subgraphs
    role_to_variants: dict[str, list[dict]] = {}
    for v in variant_nodes:
        parent = v.get("parentRole")
        if parent:
            role_to_variants.setdefault(parent, []).append(v)

    # Group role nodes by stage
    nodes_by_stage: dict[str, list[dict]] = {}
    for node in role_nodes:
        stage = node.get("stage") or "conversion"
        nodes_by_stage.setdefault(stage, []).append(node)

    # Infer commodity stages based on connected processes
    commodity_stages = {}
    for edge in graph.get("edges", []):
        if edge["kind"] == "output":
            proc_node = next(
                (n for n in graph["nodes"] if n["id"] == edge["from"]),
                None,
            )
            if proc_node:
                proc_stage = proc_node.get("stage") or "conversion"
                proc_rank = stage_rank.get(proc_stage, 1)
                commodity_stages[edge["to"]] = max(
                    commodity_stages.get(edge["to"], 0),
                    proc_rank + 0.5
                )
        elif edge["kind"] == "input":
            proc_node = next(
                (n for n in graph["nodes"] if n["id"] == edge["to"]),
                None,
            )
            if proc_node:
                proc_stage = proc_node.get("stage") or "conversion"
                proc_rank = stage_rank.get(proc_stage, 1)
                commodity_stages[edge["from"]] = min(
                    commodity_stages.get(edge["from"], 10),
                    proc_rank - 0.5
                )

    # Render nodes - processes first, grouped by stage subgraphs
    lines.append("")
    lines.append("    %% Process nodes grouped by stage")
    for stage in sorted(nodes_by_stage.keys(), key=lambda s: stage_rank.get(s, 99)):
        role_stage_label = stage_label(stage)
        safe_stage = sanitize_id(stage)
        lines.append(f"    subgraph stage_{safe_stage}[\"{role_stage_label}\"]")
        for node in nodes_by_stage[stage]:
            safe_id = sanitize_id(node["id"])
            safe_label = _format_process_label(node)

            if has_variants and node["id"] in role_to_variants:
                # Render as subgraph containing variants
                lines.append(f"        subgraph {safe_id}[\"{safe_label}\"]")
                for variant in role_to_variants[node["id"]]:
                    v_safe_id = sanitize_id(variant["id"])
                    v_safe_label = _format_process_label(variant)
                    lines.append(f"            V_{v_safe_id}[\"{v_safe_label}\"]")
                lines.append("        end")
            else:
                # Render as simple node
                lines.append(f"        P_{safe_id}[\"{safe_label}\"]")
        lines.append("    end")

    lines.append("")
    lines.append("    %% Commodity nodes")
    for node in commodity_nodes:
        safe_id = sanitize_id(node["id"])
        safe_label = _format_commodity_label(node)
        lines.append(f"    C_{safe_id}((\"{safe_label}\"))")

    # Build set of role IDs that have subgraphs (for edge targeting)
    roles_with_subgraphs = set(role_to_variants.keys()) if has_variants else set()

    # Build set of variant IDs for edge prefix resolution
    variant_ids = {v["id"] for v in variant_nodes}

    # Render edges
    lines.append("")
    lines.append("    %% Edges")
    for edge in graph.get("edges", []):
        from_id = sanitize_id(edge["from"])
        to_id = sanitize_id(edge["to"])

        if edge["kind"] == "input":
            # Commodity → Process/Variant/Subgraph
            if edge["to"] in roles_with_subgraphs:
                target = to_id
            elif edge["to"] in variant_ids:
                target = f"V_{to_id}"
            else:
                target = f"P_{to_id}"
            lines.append(f"    C_{from_id} --> {target}")
        else:
            # Process/Variant/Subgraph → Commodity
            if edge["from"] in roles_with_subgraphs:
                source = from_id
            elif edge["from"] in variant_ids:
                source = f"V_{from_id}"
            else:
                source = f"P_{from_id}"
            lines.append(f"    {source} --> C_{to_id}")

    # Style definitions
    lines.append("")
    lines.append("    %% Styles")
    lines.append("    classDef carrier fill:#4a90d9,stroke:#2e5a87,color:#fff")
    lines.append("    classDef service fill:#4ad94a,stroke:#2e872e,color:#fff")
    lines.append("    classDef emission fill:#d94a4a,stroke:#872e2e,color:#fff")
    lines.append("    classDef material fill:#d9a84a,stroke:#876a2e,color:#fff")
    lines.append("    classDef process fill:#9b59b6,stroke:#6c3483,color:#fff")
    lines.append("    classDef variant fill:#8e44ad,stroke:#5b2c6f,color:#fff")

    # Apply styles to nodes
    for node in graph.get("nodes", []):
        safe_id = sanitize_id(node["id"])
        if node["kind"] == "commodity":
            comm_type = (node.get("type") or "carrier").lower()
            if comm_type in ("emission", "environment", "env"):
                lines.append(f"    class C_{safe_id} emission")
            elif comm_type in ("service", "demand", "dem"):
                lines.append(f"    class C_{safe_id} service")
            elif comm_type in ("material", "mat"):
                lines.append(f"    class C_{safe_id} material")
            else:
                lines.append(f"    class C_{safe_id} carrier")
        elif node.get("type") == "variant":
            lines.append(f"    class V_{safe_id} variant")
        elif node["id"] not in roles_with_subgraphs:
            lines.append(f"    class P_{safe_id} process")

    return "\n".join(lines)


def generate_mermaid(veda_file: Path) -> str:
    """Generate Mermaid diagram from a VedaLang file.

    Args:
        veda_file: Path to a .veda.yaml file.

    Returns:
        Mermaid flowchart code.
    """
    with open(veda_file) as f:
        parsed = yaml.safe_load(f)

    graph = build_res_graph(parsed)
    return graph_to_mermaid(graph)


def main():
    """CLI entry point for vedalang res-mermaid command."""
    parser = argparse.ArgumentParser(
        description="Generate Mermaid RES diagram from VedaLang file"
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to .veda.yaml file"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output graph as JSON instead of Mermaid"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug info about nodes and edges"
    )

    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    with open(args.file) as f:
        parsed = yaml.safe_load(f)

    graph = build_res_graph(parsed)

    if args.debug:
        print("=== Nodes ===", file=sys.stderr)
        for n in graph["nodes"]:
            kind, nid = n['kind'], n['id']
            ntype, stage = n.get('type'), n.get('stage')
            print(f"  {kind}: {nid} (type={ntype}, stage={stage})", file=sys.stderr)
        print("=== Edges ===", file=sys.stderr)
        for e in graph["edges"]:
            print(f"  {e['from']} --{e['kind']}--> {e['to']}", file=sys.stderr)
        print("", file=sys.stderr)

    if args.json:
        import json
        print(json.dumps(graph, indent=2))
    else:
        print(graph_to_mermaid(graph))


if __name__ == "__main__":
    main()
