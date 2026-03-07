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
from vedalang.versioning import looks_like_v0_2_source

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
    if looks_like_v0_2_source(source):
        return _export_v0_2_res_graph(source)

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
    roles = source.get("roles") or []
    role_nodes = []
    edges = []

    # Build variant-per-role counts
    variant_by_role: dict[str, list[dict]] = {}
    for variant in source.get("variants") or []:
        role_id = variant.get("role")
        if role_id:
            variant_by_role.setdefault(role_id, []).append(variant)

    def _first_non_empty(items):
        for item in items:
            if item:
                return item
        return None

    for raw_role in roles:
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
            edges.append(
                {
                    "from": inp_id,
                    "to": role_id,
                    "direction": "input",
                    "commodity": inp_id,
                    "scope": "role",
                }
            )
        for out_id in required_outputs:
            comm = commodities_by_id.get(out_id, {})
            edge_kind = "emission" if comm.get("type") == "emission" else "output"
            edges.append(
                {
                    "from": role_id,
                    "to": out_id,
                    "direction": edge_kind,
                    "commodity": out_id,
                    "scope": "role",
                }
            )

    # Build variant nodes and collect variant-level edges
    variant_nodes = []
    # Track which (role, commodity, direction) edges already exist from roles
    existing_edges = {(e["from"], e["to"], e["direction"]) for e in edges}

    # Track variant-level outputs per role (for role metadata)
    variant_output_by_role: dict[str, set[str]] = {}

    for variant in source.get("variants") or []:
        vid = variant.get("id")
        role_id = variant.get("role")
        if not vid or not role_id:
            continue

        # Find the role to derive kind
        role_raw = next((r for r in roles if r.get("id") == role_id), None)
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
                edges.append(
                    {
                        "from": inp_id,
                        "to": role_id,
                        "direction": "input",
                        "commodity": inp_id,
                        "scope": "variant",
                        "source_variants": [vid],
                    }
                )
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
                edges.append(
                    {
                        "from": role_id,
                        "to": em_id,
                        "direction": "emission",
                        "commodity": em_id,
                        "scope": "variant",
                        "source_variants": [vid],
                    }
                )
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


def _commodity_type_from_kind(kind: str | None) -> str:
    mapping = {
        "primary": "fuel",
        "secondary": "energy",
        "service": "service",
        "emission": "emission",
        "material": "material",
        "certificate": "other",
    }
    return mapping.get(str(kind or ""), "other")


def _infer_v0_2_stage(
    role_id: str,
    primary_service: str,
    technologies: list[dict],
) -> str:
    if role_id.endswith("_supply"):
        return "supply"
    if all(not tech.get("inputs") for tech in technologies):
        return "supply"
    if primary_service.startswith("service:"):
        explicit_outputs = any(tech.get("outputs") for tech in technologies)
        if explicit_outputs:
            return "conversion"
        return "end_use"
    return "conversion"


def _derive_v0_2_kind(
    stage: str,
    primary_service: str,
    technologies: list[dict],
) -> str:
    if stage == "supply":
        return "source"
    if stage == "end_use":
        return "device"
    output_ids: set[str] = set()
    for tech in technologies:
        for flow in tech.get("outputs") or []:
            if isinstance(flow, dict) and flow.get("commodity"):
                output_ids.add(str(flow["commodity"]))
    if primary_service.startswith("service:"):
        output_ids.add(primary_service)
    if any(output.startswith("secondary:") for output in output_ids):
        return "generator"
    return "process"


def _variant_outputs_for_v0_2(
    tech: dict,
    primary_service: str,
) -> list[str]:
    outputs = [
        str(flow["commodity"])
        for flow in tech.get("outputs") or []
        if isinstance(flow, dict) and flow.get("commodity")
    ]
    if primary_service.startswith("service:") and primary_service not in outputs:
        outputs.append(primary_service)
    return sorted(set(outputs))


def _export_v0_2_res_graph(source: dict) -> dict:
    commodities_by_id: dict[str, dict] = {}
    commodity_nodes: list[dict] = []
    for raw in source.get("commodities") or []:
        commodity_id = raw.get("id")
        if not commodity_id:
            continue
        entry = {
            "id": commodity_id,
            "type": _commodity_type_from_kind(raw.get("kind")),
            "kind": raw.get("kind") or _commodity_type_from_kind(raw.get("kind")),
        }
        commodities_by_id[str(commodity_id)] = entry
        commodity_nodes.append(entry)

    technologies = {
        str(item["id"]): item
        for item in source.get("technologies") or []
        if item.get("id")
    }
    role_nodes: list[dict] = []
    variant_nodes: list[dict] = []
    edges: list[dict] = []
    existing_edges: set[tuple[str, str, str]] = set()

    for raw_role in source.get("technology_roles") or []:
        role_id = raw_role.get("id")
        primary_service = str(raw_role.get("primary_service", ""))
        tech_ids = [str(item) for item in raw_role.get("technologies") or []]
        role_techs = [
            technologies[tech_id] for tech_id in tech_ids if tech_id in technologies
        ]
        if not role_id or not primary_service:
            continue

        stage = _infer_v0_2_stage(str(role_id), primary_service, role_techs)
        derived_kind = _derive_v0_2_kind(stage, primary_service, role_techs)
        role_inputs = sorted(
            {
                str(flow["commodity"])
                for tech in role_techs
                for flow in tech.get("inputs") or []
                if isinstance(flow, dict) and flow.get("commodity")
            }
        )
        role_entry = {
            "id": str(role_id),
            "stage": stage,
            "required_inputs": [],
            "required_outputs": [{"commodity": primary_service}],
            "derived_kind": derived_kind,
            "variant_count": len(role_techs),
            "has_variant_level_inputs": bool(role_inputs),
            "primary_output": primary_service,
            "has_variant_level_outputs": False,
        }
        if role_inputs:
            role_entry["variant_inputs"] = role_inputs
        role_nodes.append(role_entry)

        edge_key = (str(role_id), primary_service, "output")
        edges.append(
            {
                "from": str(role_id),
                "to": primary_service,
                "direction": "output",
                "commodity": primary_service,
                "scope": "role",
            }
        )
        existing_edges.add(edge_key)

        variant_outputs_extra: set[str] = set()
        for tech in role_techs:
            tech_id = str(tech["id"])
            v_inputs = sorted(
                str(flow["commodity"])
                for flow in tech.get("inputs") or []
                if isinstance(flow, dict) and flow.get("commodity")
            )
            v_outputs = _variant_outputs_for_v0_2(tech, primary_service)
            variant_entry = {
                "id": tech_id,
                "role": str(role_id),
                "kind": derived_kind,
                "kind_source": "derived",
                "inputs": v_inputs,
                "outputs": v_outputs,
            }
            emissions = {
                str(flow["commodity"]): str(flow["factor"])
                for flow in tech.get("emissions") or []
                if isinstance(flow, dict) and flow.get("commodity")
            }
            if emissions:
                variant_entry["emission_factors"] = emissions
            variant_nodes.append(variant_entry)

            for commodity_id in v_inputs:
                edge_key = (commodity_id, str(role_id), "input")
                if edge_key not in existing_edges:
                    edges.append(
                        {
                            "from": commodity_id,
                            "to": str(role_id),
                            "direction": "input",
                            "commodity": commodity_id,
                            "scope": "variant",
                            "source_variants": [tech_id],
                        }
                    )
                    existing_edges.add(edge_key)
            for commodity_id in v_outputs:
                if commodity_id == primary_service:
                    continue
                variant_outputs_extra.add(commodity_id)
                direction = (
                    "emission"
                    if commodities_by_id.get(commodity_id, {}).get("type") == "emission"
                    else "output"
                )
                edge_key = (str(role_id), commodity_id, direction)
                if edge_key not in existing_edges:
                    edges.append(
                        {
                            "from": str(role_id),
                            "to": commodity_id,
                            "direction": direction,
                            "commodity": commodity_id,
                            "scope": "variant",
                            "source_variants": [tech_id],
                        }
                    )
                    existing_edges.add(edge_key)
            for emission_id in emissions:
                edge_key = (str(role_id), emission_id, "emission")
                if edge_key not in existing_edges:
                    edges.append(
                        {
                            "from": str(role_id),
                            "to": emission_id,
                            "direction": "emission",
                            "commodity": emission_id,
                            "scope": "variant",
                            "source_variants": [tech_id],
                        }
                    )
                    existing_edges.add(edge_key)
        if variant_outputs_extra:
            role_entry["has_variant_level_outputs"] = True
            role_entry["variant_outputs"] = sorted(variant_outputs_extra)

    commodity_nodes.sort(key=lambda c: c["id"])
    role_nodes.sort(key=lambda r: r["id"])
    variant_nodes.sort(key=lambda v: v["id"])
    edges.sort(key=lambda e: (e["from"], e["to"], e["direction"]))

    regions = []
    run_id = ""
    if source.get("runs"):
        run = source["runs"][0]
        run_id = str(run.get("id", ""))
        partition_ref = run.get("region_partition")
        for partition in source.get("region_partitions") or []:
            if partition.get("id") == partition_ref:
                regions = sorted(partition.get("members") or [])
                break

    return {
        "version": "1.0",
        "model": {
            "name": run_id,
            "regions": regions,
            "milestone_years": [],
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
        lines.append(f'    subgraph stage_{safe_stage}["{role_stage_label}"]')
        for role in roles_by_stage[stage]:
            safe_id = _sanitize(role["id"])
            label = _format_role_label(role)
            lines.append(f'        R_{safe_id}["{label}"]')
        lines.append("    end")

    # Render commodity nodes
    lines.append("")
    lines.append("    %% Commodities")
    for comm in graph.get("commodities", []):
        safe_id = _sanitize(comm["id"])
        label = _format_commodity_label(comm)
        lines.append(f'    C_{safe_id}(("{label}"))')

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
