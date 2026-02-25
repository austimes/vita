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
from vedalang.conventions import stage_label, stage_order

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

    def _first_non_empty(items):
        for item in items:
            if item:
                return item
        return None

    for raw_role in process_roles:
        role_id = raw_role.get("id")
        if not role_id:
            continue

        stage = raw_role.get("stage")
        required_inputs = [
            inp["commodity"] if isinstance(inp, dict) else inp
            for inp in raw_role.get("required_inputs") or []
        ]
        required_outputs = [
            out["commodity"] if isinstance(out, dict) else out
            for out in raw_role.get("required_outputs") or []
        ]

        # Build a Role object for kind derivation
        role_obj = Role(
            id=role_id,
            required_inputs=required_inputs,
            required_outputs=required_outputs,
            stage=stage,
        )
        derived_kind = _derive_kind_from_structure(
            role_obj, commodities_by_id, required_outputs
        )

        # Determine primary output (first non-emission required output)
        primary_output = None
        for out_id in required_outputs:
            comm = commodities_by_id.get(out_id, {})
            if comm.get("type") != "emission":
                primary_output = out_id
                break

        # Collect variant-level inputs not already in required_inputs
        variant_input_set: set[str] = set()
        for v in variant_by_role.get(role_id, []):
            for inp in v.get("inputs") or []:
                inp_id = inp["commodity"] if isinstance(inp, dict) else inp
                if inp_id not in required_inputs:
                    variant_input_set.add(inp_id)

        role_activity_unit = raw_role.get("activity_unit") or _first_non_empty(
            v.get("activity_unit") for v in variant_by_role.get(role_id, [])
        )
        role_capacity_unit = raw_role.get("capacity_unit") or _first_non_empty(
            v.get("capacity_unit") for v in variant_by_role.get(role_id, [])
        )

        role_entry = {
            "id": role_id,
            "stage": stage,
            "required_inputs": sorted(required_inputs),
            "required_outputs": sorted(required_outputs),
            "derived_kind": derived_kind,
            "variant_count": len(variant_by_role.get(role_id, [])),
            "has_variant_level_inputs": bool(variant_input_set),
        }
        if role_activity_unit:
            role_entry["activity_unit"] = role_activity_unit
        if role_capacity_unit:
            role_entry["capacity_unit"] = role_capacity_unit
        if variant_input_set:
            role_entry["variant_inputs"] = sorted(variant_input_set)
        if primary_output:
            role_entry["primary_output"] = primary_output

        role_nodes.append(role_entry)

        # Build edges
        for inp_id in required_inputs:
            edges.append({
                "from": inp_id,
                "to": role_id,
                "direction": "input",
                "commodity": inp_id,
                "scope": "role",
            })
        for out_id in required_outputs:
            comm = commodities_by_id.get(out_id, {})
            edge_kind = "emission" if comm.get("type") == "emission" else "output"
            edges.append({
                "from": role_id,
                "to": out_id,
                "direction": edge_kind,
                "commodity": out_id,
                "scope": "role",
            })

    # Build variant nodes and collect variant-level edges
    variant_nodes = []
    # Track which (role, commodity, direction) edges already exist from roles
    existing_edges = {(e["from"], e["to"], e["direction"]) for e in edges}

    # Track variant-level outputs per role (for role metadata)
    variant_output_by_role: dict[str, set[str]] = {}

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
            required_outputs = [
                out["commodity"] if isinstance(out, dict) else out
                for out in role_raw.get("required_outputs") or []
            ]
            role_obj = Role(
                id=role_id,
                required_inputs=[
                    inp["commodity"] if isinstance(inp, dict) else inp
                    for inp in role_raw.get("required_inputs") or []
                ],
                required_outputs=required_outputs,
                stage=role_raw.get("stage"),
            )
            kind = _derive_kind_from_structure(
                role_obj, commodities_by_id, required_outputs
            )

        # Collect variant I/O for the enriched variant node
        v_inputs = []
        for inp in variant.get("inputs") or []:
            v_inputs.append(inp["commodity"] if isinstance(inp, dict) else inp)
        v_outputs = []
        for out in variant.get("outputs") or []:
            v_outputs.append(out["commodity"] if isinstance(out, dict) else out)

        variant_entry: dict = {
            "id": vid,
            "role": role_id,
            "kind": kind or "process",
            "kind_source": kind_source,
            "inputs": sorted(v_inputs),
            "outputs": sorted(v_outputs),
        }
        if variant.get("activity_unit"):
            variant_entry["activity_unit"] = variant["activity_unit"]
        if variant.get("capacity_unit"):
            variant_entry["capacity_unit"] = variant["capacity_unit"]
        emission_factors = variant.get("emission_factors") or {}
        if emission_factors:
            variant_entry["emission_factors"] = emission_factors

        variant_nodes.append(variant_entry)

        # Determine which role-level required outputs this role has
        role_required_outputs: set[str] = set()
        if role_raw:
            for out in role_raw.get("required_outputs") or []:
                role_required_outputs.add(
                    out["commodity"] if isinstance(out, dict) else out
                )

        # Track variant-level outputs not in role required_outputs
        for out_id in v_outputs:
            if out_id not in role_required_outputs:
                variant_output_by_role.setdefault(role_id, set()).add(out_id)

        # Add edges for variant-level I/O not already covered by role
        for inp_id in v_inputs:
            edge_key = (inp_id, role_id, "input")
            if edge_key not in existing_edges:
                edges.append({
                    "from": inp_id,
                    "to": role_id,
                    "direction": "input",
                    "commodity": inp_id,
                    "scope": "variant",
                    "source_variants": [vid],
                })
                existing_edges.add(edge_key)
            else:
                # Tag existing edge with this variant source
                for e in edges:
                    if (e["from"], e["to"], e["direction"]) == edge_key:
                        if "source_variants" in e:
                            if vid not in e["source_variants"]:
                                e["source_variants"].append(vid)
                        break
        for out_id in v_outputs:
            comm = commodities_by_id.get(out_id, {})
            edge_kind = "emission" if comm.get("type") == "emission" else "output"
            edge_key = (role_id, out_id, edge_kind)
            # Determine scope: role if in required_outputs, else variant
            scope = "role" if out_id in role_required_outputs else "variant"
            if edge_key not in existing_edges:
                edge_entry: dict = {
                    "from": role_id,
                    "to": out_id,
                    "direction": edge_kind,
                    "commodity": out_id,
                    "scope": scope,
                }
                if scope == "variant":
                    edge_entry["source_variants"] = [vid]
                edges.append(edge_entry)
                existing_edges.add(edge_key)
            else:
                # Tag existing variant-scoped edge with this variant source
                if scope == "variant":
                    for e in edges:
                        if (e["from"], e["to"], e["direction"]) == edge_key:
                            if "source_variants" in e:
                                if vid not in e["source_variants"]:
                                    e["source_variants"].append(vid)
                            break

        for em_id in emission_factors.keys():
            edge_key = (role_id, em_id, "emission")
            if edge_key not in existing_edges:
                edges.append({
                    "from": role_id,
                    "to": em_id,
                    "direction": "emission",
                    "commodity": em_id,
                    "scope": "variant",
                    "source_variants": [vid],
                })
                existing_edges.add(edge_key)
            else:
                for e in edges:
                    if (e["from"], e["to"], e["direction"]) == edge_key:
                        if "source_variants" not in e:
                            e["source_variants"] = []
                        if vid not in e["source_variants"]:
                            e["source_variants"].append(vid)
                        e["scope"] = "variant"
                        break

    # Enrich role nodes with variant-level output metadata
    for role_entry in role_nodes:
        role_id = role_entry["id"]
        v_outputs = variant_output_by_role.get(role_id, set())
        role_entry["has_variant_level_outputs"] = bool(v_outputs)
        if v_outputs:
            role_entry["variant_outputs"] = sorted(v_outputs)

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

    stage_rank = stage_order(include_demand=True)

    # Group roles by stage
    roles_by_stage: dict[str, list[dict]] = {}
    for role in graph.get("roles", []):
        stage = role.get("stage") or "conversion"
        roles_by_stage.setdefault(stage, []).append(role)

    # Render roles grouped by stage subgraphs
    for stage in sorted(roles_by_stage.keys(), key=lambda s: stage_rank.get(s, 99)):
        role_stage_label = stage_label(stage)
        safe_stage = _sanitize(stage)
        lines.append("")
        lines.append(f"    subgraph stage_{safe_stage}[\"{role_stage_label}\"]")
        for role in roles_by_stage[stage]:
            safe_id = _sanitize(role["id"])
            label = _format_role_label(role)
            lines.append(f"        R_{safe_id}[\"{label}\"]")
        lines.append("    end")

    # Render commodity nodes
    lines.append("")
    lines.append("    %% Commodities")
    for comm in graph.get("commodities", []):
        safe_id = _sanitize(comm["id"])
        label = _format_commodity_label(comm)
        lines.append(f"    C_{safe_id}((\"{label}\"))")

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


def _escape_label(s: str) -> str:
    """Escape Mermaid label text."""
    return s.replace('"', '\\"')


def _format_commodity_label(comm: dict) -> str:
    """Build commodity label with volume unit."""
    unit = comm.get("unit") or DEFAULT_COMMODITY_UNITS.get(comm.get("type"), "PJ")
    return _escape_label(f"{comm['id']}<br/>({unit})")


def _format_role_label(role: dict) -> str:
    """Build role label with derived kind and process units."""
    dk = role.get("derived_kind")
    kind_label = f" [{dk}]" if dk else ""
    cap_unit = role.get("capacity_unit") or DEFAULT_CAPACITY_UNIT
    act_unit = role.get("activity_unit") or DEFAULT_ACTIVITY_UNIT
    return _escape_label(
        f"{role['id']}{kind_label}<br/>cap: {cap_unit} | act: {act_unit}"
    )
