"""Export a normalized RES graph from the active VedaLang source model."""

from __future__ import annotations

from vedalang.conventions import stage_label, stage_order
from vedalang.versioning import looks_like_v0_2_source

DEFAULT_ACTIVITY_UNIT = "PJ"
DEFAULT_CAPACITY_UNIT = "GW"
DEFAULT_COMMODITY_UNITS = {
    "energy": "PJ",
    "service": "PJ",
    "material": "Mt",
    "emission": "Mt",
    "money": "MUSD",
    "certificate": "PJ",
}


def export_res_graph(source: dict) -> dict:
    """Build a deterministic RES graph from a v0.2 VedaLang source."""
    if not looks_like_v0_2_source(source):
        raise ValueError(
            "RES export now supports only the v0.2 object model "
            "(commodities/technologies/technology_roles/... )."
        )

    commodities_by_id: dict[str, dict] = {}
    commodity_nodes: list[dict] = []
    for raw in source.get("commodities") or []:
        commodity_id = raw.get("id")
        if not commodity_id:
            continue
        entry = {
            "id": commodity_id,
            "type": str(raw.get("type") or ""),
            "energy_form": raw.get("energy_form"),
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

        stage = _infer_stage(
            str(role_id),
            primary_service,
            role_techs,
            commodities_by_id,
        )
        derived_kind = _derive_kind(
            stage,
            primary_service,
            role_techs,
            commodities_by_id,
        )
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

        output_edge_key = (str(role_id), primary_service, "output")
        edges.append(
            {
                "from": str(role_id),
                "to": primary_service,
                "direction": "output",
                "commodity": primary_service,
                "scope": "role",
            }
        )
        existing_edges.add(output_edge_key)

        variant_outputs_extra: set[str] = set()
        for tech in role_techs:
            tech_id = str(tech["id"])
            v_inputs = sorted(
                str(flow["commodity"])
                for flow in tech.get("inputs") or []
                if isinstance(flow, dict) and flow.get("commodity")
            )
            v_outputs = _variant_outputs(tech, primary_service)
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
                if edge_key in existing_edges:
                    _append_source_variant(edges, edge_key, tech_id)
                    continue
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
                if edge_key in existing_edges:
                    _append_source_variant(edges, edge_key, tech_id)
                    continue
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
                if edge_key in existing_edges:
                    _append_source_variant(edges, edge_key, tech_id)
                    continue
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

    regions: list[str] = []
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


def _append_source_variant(
    edges: list[dict],
    edge_key: tuple[str, str, str],
    technology_id: str,
) -> None:
    for edge in edges:
        if (edge["from"], edge["to"], edge["direction"]) != edge_key:
            continue
        source_variants = edge.setdefault("source_variants", [])
        if technology_id not in source_variants:
            source_variants.append(technology_id)
        edge["scope"] = "variant"
        return


def _infer_stage(
    role_id: str,
    primary_service: str,
    technologies: list[dict],
    commodities_by_id: dict[str, dict],
) -> str:
    if role_id.endswith("_supply"):
        return "supply"
    if all(not tech.get("inputs") for tech in technologies):
        return "supply"
    if commodities_by_id.get(primary_service, {}).get("type") == "service":
        explicit_outputs = any(tech.get("outputs") for tech in technologies)
        if explicit_outputs:
            return "conversion"
        return "end_use"
    return "conversion"


def _derive_kind(
    stage: str,
    primary_service: str,
    technologies: list[dict],
    commodities_by_id: dict[str, dict],
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
    if commodities_by_id.get(primary_service, {}).get("type") == "service":
        output_ids.add(primary_service)
    if any(
        commodities_by_id.get(output, {}).get("energy_form") == "secondary"
        for output in output_ids
    ):
        return "generator"
    return "process"


def _variant_outputs(tech: dict, primary_service: str) -> list[str]:
    outputs = [
        str(flow["commodity"])
        for flow in tech.get("outputs") or []
        if isinstance(flow, dict) and flow.get("commodity")
    ]
    if primary_service not in outputs:
        outputs.append(primary_service)
    return sorted(set(outputs))


def res_graph_to_mermaid(graph: dict) -> str:
    """Convert a normalized RES graph to Mermaid flowchart syntax."""
    lines = ["flowchart LR"]
    stage_rank = stage_order(include_demand=True)

    roles_by_stage: dict[str, list[dict]] = {}
    for role in graph.get("roles", []):
        stage = role.get("stage") or "conversion"
        roles_by_stage.setdefault(stage, []).append(role)

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

    lines.append("")
    lines.append("    %% Commodities")
    for commodity in graph.get("commodities", []):
        safe_id = _sanitize(commodity["id"])
        label = _format_commodity_label(commodity)
        lines.append(f'    C_{safe_id}(("{label}"))')

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

    lines.append("")
    lines.append("    %% Styles")
    lines.append("    classDef fuel fill:#d9a84a,stroke:#876a2e,color:#fff")
    lines.append("    classDef energy fill:#4a90d9,stroke:#2e5a87,color:#fff")
    lines.append("    classDef service fill:#4ad94a,stroke:#2e872e,color:#fff")
    lines.append("    classDef emission fill:#d94a4a,stroke:#872e2e,color:#fff")
    lines.append("    classDef material fill:#a0522d,stroke:#5a2e1a,color:#fff")
    lines.append("    classDef role fill:#9b59b6,stroke:#6c3483,color:#fff")

    for commodity in graph.get("commodities", []):
        safe_id = _sanitize(commodity["id"])
        commodity_type = commodity.get("type", "energy")
        if commodity_type in ("fuel", "energy", "service", "emission", "material"):
            lines.append(f"    class C_{safe_id} {commodity_type}")

    for role in graph.get("roles", []):
        safe_id = _sanitize(role["id"])
        lines.append(f"    class R_{safe_id} role")

    return "\n".join(lines)


def _sanitize(value: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in value)


def _escape_label(value: str) -> str:
    return value.replace('"', '\\"')


def _format_commodity_label(commodity: dict) -> str:
    unit = commodity.get("unit") or DEFAULT_COMMODITY_UNITS.get(
        commodity.get("type"),
        "PJ",
    )
    return _escape_label(f"{commodity['id']}<br/>({unit})")


def _format_role_label(role: dict) -> str:
    derived_kind = role.get("derived_kind")
    kind_label = f" [{derived_kind}]" if derived_kind else ""
    capacity_unit = role.get("capacity_unit") or DEFAULT_CAPACITY_UNIT
    activity_unit = role.get("activity_unit") or DEFAULT_ACTIVITY_UNIT
    return _escape_label(
        f"{role['id']}{kind_label}<br/>cap: {capacity_unit} | act: {activity_unit}"
    )
