"""Export normalized RES graph from validated VedaLang source.

Produces a deterministic JSON graph and optional Mermaid diagram
for downstream analysis (LLM-based structural assessment, lint rules).

This operates on the parsed VedaLang source *before* compilation —
no compile/solve phase is needed.
"""

from __future__ import annotations

from vedalang.compiler.compiler import (
    VALID_COMMODITY_TYPES,
    _derive_kind_from_structure,
)
from vedalang.compiler.ir import Role


def export_res_graph(source: dict) -> dict:
    """Build a normalized RES graph from a parsed VedaLang source.

    The output is a deterministic, machine-readable representation of the
    Reference Energy System suitable for downstream analyzers.

    Args:
        source: Parsed VedaLang source dict (from load_vedalang).

    Returns:
        Normalized RES graph dict with keys:
        - version: Schema version string
        - model: Model metadata
        - commodities: List of commodity descriptors
        - roles: List of role descriptors with derived metadata
        - variants: List of variant descriptors
        - edges: List of directed edges between commodities and roles
    """
    model = source.get("model", {})

    # Build commodity lookup
    commodities_raw = model.get("commodities") or []
    commodities_by_id = {}
    commodity_nodes = []

    for raw in commodities_raw:
        cid = raw.get("id") or raw.get("name")
        if not cid:
            continue
        ctype = raw.get("type", "energy")
        unit = raw.get("unit")
        entry = {
            "id": cid,
            "type": ctype if ctype in VALID_COMMODITY_TYPES else "other",
            "kind": raw.get("kind") or ctype,
        }
        if unit:
            entry["unit"] = unit
        commodities_by_id[cid] = entry
        commodity_nodes.append(entry)

    # Build roles and edges
    process_roles = source.get("process_roles") or []
    role_nodes = []
    edges = []

    # Build variant-per-role counts
    variant_by_role: dict[str, list[dict]] = {}
    for variant in source.get("process_variants") or []:
        role_id = variant.get("role")
        if role_id:
            variant_by_role.setdefault(role_id, []).append(variant)

    for raw_role in process_roles:
        role_id = raw_role.get("id")
        if not role_id:
            continue

        stage = raw_role.get("stage")
        inputs = [
            inp["commodity"] if isinstance(inp, dict) else inp
            for inp in raw_role.get("inputs") or []
        ]
        outputs = [
            out["commodity"] if isinstance(out, dict) else out
            for out in raw_role.get("outputs") or []
        ]

        # Build a Role object for kind derivation
        role_obj = Role(id=role_id, inputs=inputs, outputs=outputs, stage=stage)
        derived_kind = _derive_kind_from_structure(
            role_obj, commodities_by_id, outputs
        )

        # Determine primary output (first non-emission output)
        primary_output = None
        for out_id in outputs:
            comm = commodities_by_id.get(out_id, {})
            if comm.get("type") != "emission":
                primary_output = out_id
                break

        role_entry = {
            "id": role_id,
            "stage": stage,
            "inputs": sorted(inputs),
            "outputs": sorted(outputs),
            "derived_kind": derived_kind,
            "variant_count": len(variant_by_role.get(role_id, [])),
        }
        if primary_output:
            role_entry["primary_output"] = primary_output

        role_nodes.append(role_entry)

        # Build edges
        for inp_id in inputs:
            edges.append({
                "from": inp_id,
                "to": role_id,
                "direction": "input",
                "commodity": inp_id,
            })
        for out_id in outputs:
            comm = commodities_by_id.get(out_id, {})
            edge_kind = "emission" if comm.get("type") == "emission" else "output"
            edges.append({
                "from": role_id,
                "to": out_id,
                "direction": edge_kind,
                "commodity": out_id,
            })

    # Build variant nodes
    variant_nodes = []
    for variant in source.get("process_variants") or []:
        vid = variant.get("id")
        role_id = variant.get("role")
        if not vid or not role_id:
            continue

        # Find the role to derive kind
        role_raw = next(
            (r for r in process_roles if r.get("id") == role_id), None
        )
        kind = variant.get("kind")
        kind_source = "explicit" if kind else "derived"
        if not kind and role_raw:
            outputs = [
                out["commodity"] if isinstance(out, dict) else out
                for out in role_raw.get("outputs") or []
            ]
            role_obj = Role(
                id=role_id,
                inputs=[
                    inp["commodity"] if isinstance(inp, dict) else inp
                    for inp in role_raw.get("inputs") or []
                ],
                outputs=outputs,
                stage=role_raw.get("stage"),
            )
            kind = _derive_kind_from_structure(role_obj, commodities_by_id, outputs)

        variant_nodes.append({
            "id": vid,
            "role": role_id,
            "kind": kind or "process",
            "kind_source": kind_source,
        })

    # Sort everything for deterministic output
    commodity_nodes.sort(key=lambda c: c["id"])
    role_nodes.sort(key=lambda r: r["id"])
    variant_nodes.sort(key=lambda v: v["id"])
    edges.sort(key=lambda e: (e["from"], e["to"], e["direction"]))

    return {
        "version": "1.0",
        "model": {
            "name": model.get("name", ""),
            "regions": sorted(model.get("regions") or []),
            "milestone_years": model.get("milestone_years") or [],
        },
        "commodities": commodity_nodes,
        "roles": role_nodes,
        "variants": variant_nodes,
        "edges": edges,
    }


def res_graph_to_mermaid(graph: dict) -> str:
    """Convert a normalized RES graph to Mermaid flowchart syntax.

    Args:
        graph: Normalized RES graph from export_res_graph().

    Returns:
        Mermaid flowchart code as a string.
    """
    lines = ["flowchart LR"]

    stage_order = {
        "supply": 0,
        "conversion": 1,
        "storage": 2,
        "end_use": 3,
        "sink": 4,
    }

    # Group roles by stage
    roles_by_stage: dict[str, list[dict]] = {}
    for role in graph.get("roles", []):
        stage = role.get("stage") or "conversion"
        roles_by_stage.setdefault(stage, []).append(role)

    # Render roles grouped by stage
    for stage in sorted(roles_by_stage.keys(), key=lambda s: stage_order.get(s, 99)):
        lines.append("")
        lines.append(f"    %% Stage: {stage}")
        for role in roles_by_stage[stage]:
            safe_id = _sanitize(role["id"])
            dk = role.get("derived_kind")
            kind_label = f" [{dk}]" if dk else ""
            lines.append(f"    R_{safe_id}[{role['id']}{kind_label}]")

    # Render commodity nodes
    lines.append("")
    lines.append("    %% Commodities")
    for comm in graph.get("commodities", []):
        safe_id = _sanitize(comm["id"])
        lines.append(f"    C_{safe_id}(({comm['id']}))")

    # Render edges
    lines.append("")
    lines.append("    %% Edges")
    for edge in graph.get("edges", []):
        from_id = _sanitize(edge["from"])
        to_id = _sanitize(edge["to"])
        if edge["direction"] == "input":
            lines.append(f"    C_{from_id} --> R_{to_id}")
        elif edge["direction"] == "emission":
            lines.append(f"    R_{from_id} -.-> C_{to_id}")
        else:
            lines.append(f"    R_{from_id} --> C_{to_id}")

    # Style definitions
    lines.append("")
    lines.append("    %% Styles")
    lines.append("    classDef fuel fill:#d9a84a,stroke:#876a2e,color:#fff")
    lines.append("    classDef energy fill:#4a90d9,stroke:#2e5a87,color:#fff")
    lines.append("    classDef service fill:#4ad94a,stroke:#2e872e,color:#fff")
    lines.append("    classDef emission fill:#d94a4a,stroke:#872e2e,color:#fff")
    lines.append("    classDef material fill:#a0522d,stroke:#5a2e1a,color:#fff")
    lines.append("    classDef role fill:#9b59b6,stroke:#6c3483,color:#fff")

    # Apply commodity styles
    for comm in graph.get("commodities", []):
        safe_id = _sanitize(comm["id"])
        ctype = comm.get("type", "energy")
        if ctype in ("fuel", "energy", "service", "emission", "material"):
            lines.append(f"    class C_{safe_id} {ctype}")

    # Apply role styles
    for role in graph.get("roles", []):
        safe_id = _sanitize(role["id"])
        lines.append(f"    class R_{safe_id} role")

    return "\n".join(lines)


def _sanitize(s: str) -> str:
    """Sanitize a string for use as a Mermaid node ID."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in s)
