"""Graph builders for v0.2 CSIR/CPIR artifacts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .ledger_emissions import (
    empty_ledger_emissions,
    ledger_state_from_value,
    summarize_ledger_emissions,
)


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


def _sorted_unique(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for value in values:
        if value in (None, ""):
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return sorted(out)


def _append_unique(target: list[Any], value: Any) -> None:
    if value in (None, ""):
        return
    if value not in target:
        target.append(value)


def _commodity_node_id(symbol: str) -> str:
    return f"commodity:{symbol}"


def _role_instance_asset_name(role_instance_id: str) -> str:
    return role_instance_id.split(".", 1)[-1].split("@", 1)[0]


def _role_name_for_process(
    process: dict[str, Any],
    *,
    role_instances: dict[str, dict[str, Any]],
    technology_to_role: dict[str, str],
) -> str:
    role_instance_id = str(process.get("source_role_instance", "") or "")
    role_instance = role_instances.get(role_instance_id, {})
    role_name = role_instance.get("technology_role")
    if role_name:
        return str(role_name)
    return technology_to_role.get(
        str(process.get("technology", "")),
        str(process.get("technology", "")) or str(process.get("id", "")),
    )


def _source_asset_for_process(
    process: dict[str, Any],
    *,
    role_instances: dict[str, dict[str, Any]],
) -> str | None:
    source_role_instance = str(process.get("source_role_instance", "") or "")
    if not source_role_instance:
        return None
    source_asset = role_instances.get(source_role_instance, {}).get("source_asset")
    if not source_asset:
        return None
    return str(source_asset)


def _asset_name_for_process(
    process: dict[str, Any],
    *,
    role_instances: dict[str, dict[str, Any]],
) -> str | None:
    source_role_instance = str(process.get("source_role_instance", "") or "")
    if source_role_instance:
        return _role_instance_asset_name(source_role_instance)
    source_asset = _source_asset_for_process(process, role_instances=role_instances)
    if not source_asset:
        return None
    return source_asset.split(".", 1)[-1]


def _asset_provenance_label(
    process: dict[str, Any],
    *,
    role_instances: dict[str, dict[str, Any]],
) -> str | None:
    source_asset = _source_asset_for_process(process, role_instances=role_instances)
    if not source_asset:
        return None
    if source_asset.startswith("facilities."):
        return "facility instance"
    if source_asset.startswith("fleets."):
        return "fleet instance"
    return "role instance"


def _asset_kind(source_asset: str | None) -> str | None:
    if not source_asset:
        return None
    if source_asset.startswith("facilities."):
        return "facility"
    if source_asset.startswith("fleets."):
        return "fleet"
    return None


def _group_origin(process: dict[str, Any]) -> str:
    if process.get("source_role_instance"):
        return "role_instance"
    if process.get("source_zone_opportunity"):
        return "zone_opportunity"
    return "group"


def _display_process_label(
    granularity: str,
    process: dict[str, Any],
    *,
    role_instances: dict[str, dict[str, Any]],
    technology_to_role: dict[str, str],
) -> str:
    role_name = _role_name_for_process(
        process,
        role_instances=role_instances,
        technology_to_role=technology_to_role,
    )
    source_zone_opportunity = str(process.get("source_zone_opportunity", "") or "")
    asset_name = _asset_name_for_process(process, role_instances=role_instances)
    asset_provenance = _asset_provenance_label(
        process,
        role_instances=role_instances,
    )

    if granularity == "instance":
        technology = str(process.get("technology", "") or process.get("id", ""))
        if asset_name:
            provenance = f"[{asset_name}, {asset_provenance}]"
        elif source_zone_opportunity:
            provenance = f"[{source_zone_opportunity}, zone opportunity]"
        else:
            provenance = "[group]"
        return "\n".join([technology, role_name, provenance])

    if asset_name:
        return "\n".join([role_name, asset_name, f"[{asset_provenance}]"])
    if source_zone_opportunity:
        return "\n".join([role_name, source_zone_opportunity, "[zone opportunity]"])
    return "\n".join([role_name, "[group]"])


def _group_key(
    granularity: str,
    process: dict[str, Any],
    *,
    role_instances: dict[str, dict[str, Any]],
    technology_to_role: dict[str, str],
) -> tuple[str, str, str]:
    role_name = _role_name_for_process(
        process,
        role_instances=role_instances,
        technology_to_role=technology_to_role,
    )
    source_asset = _source_asset_for_process(process, role_instances=role_instances)
    source_zone_opportunity = str(process.get("source_zone_opportunity", "") or "")
    technology = str(process.get("technology", "") or process.get("id", ""))

    if granularity == "instance":
        if source_asset:
            key = f"instance:asset:{technology}:{source_asset}"
        elif source_zone_opportunity:
            key = (
                f"instance:zone_opportunity:{technology}:{source_zone_opportunity}"
            )
        else:
            key = f"instance:group:{technology}:{role_name}"
        return (
            key,
            _display_process_label(
                granularity,
                process,
                role_instances=role_instances,
                technology_to_role=technology_to_role,
            ),
            "instance",
        )

    if source_asset:
        key = f"role:asset:{source_asset}"
    elif source_zone_opportunity:
        key = f"role:zone_opportunity:{source_zone_opportunity}"
    else:
        key = f"role:group:{role_name}"
    return (
        key,
        _display_process_label(
            granularity,
            process,
            role_instances=role_instances,
            technology_to_role=technology_to_role,
        ),
        "role",
    )


def _display_commodity(symbol: str, commodity_view: str) -> str:
    if commodity_view == "collapse_scope":
        return symbol.split("@", 1)[0]
    return symbol


def _quantity_signature(value: Any) -> tuple[Any, ...] | None:
    if not isinstance(value, dict):
        return None
    amount = value.get("amount")
    unit = value.get("unit")
    if amount is None and unit in (None, ""):
        return None
    return (amount, unit)


def _sum_quantities(values: list[dict[str, Any]]) -> dict[str, Any] | None:
    signatures = [_quantity_signature(value) for value in values]
    valid = [sig for sig in signatures if sig is not None]
    if not valid:
        return None
    units = {sig[1] for sig in valid}
    if len(units) != 1:
        return None
    total = 0.0
    for sig in valid:
        amount = sig[0]
        if amount is None:
            return None
        total += float(amount)
    return {"amount": total, "unit": valid[0][1]}


def _quantity_by_region(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        region = str(entry.get("region", "") or "")
        if not region:
            continue
        grouped[region].append(entry)

    rows: list[dict[str, Any]] = []
    for region in sorted(grouped):
        region_entries = grouped[region]
        quantities = [
            entry.get("quantity")
            for entry in region_entries
            if isinstance(entry.get("quantity"), dict)
        ]
        row: dict[str, Any] = {"region": region}
        total = _sum_quantities(quantities)
        if total is not None:
            row["total"] = total
        row["values"] = quantities
        row["member_ids"] = _sorted_unique(
            [entry.get("member_id") for entry in region_entries]
        )
        rows.append(row)
    return rows


def _coefficient_metrics(entries: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        entry.get("quantity")
        for entry in entries
        if isinstance(entry.get("quantity"), dict)
    ]
    signatures = [_quantity_signature(value) for value in values]
    unique_signatures = {sig for sig in signatures if sig is not None}
    metric: dict[str, Any] = {
        "by_region": _quantity_by_region(entries),
    }
    if len(unique_signatures) == 1 and values:
        metric["value"] = values[0]
    else:
        metric["value"] = None
    return metric


def _process_technology(process_id: str | None) -> str | None:
    if not process_id:
        return None
    technology = str(process_id).rsplit("::", 1)[-1]
    return technology or None


def _normalize_transition(transition: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(transition, dict):
        return None
    transition_id = str(transition.get("id", "") or "")
    if not transition_id:
        return None
    from_process = str(transition.get("from_process", "") or "")
    to_process = str(transition.get("to_process", "") or "")
    normalized = {
        "id": transition_id,
        "kind": str(transition.get("kind", "") or ""),
        "source_role_instance": str(transition.get("source_role_instance", "") or ""),
        "from_process": from_process,
        "to_process": to_process,
        "from_technology": _process_technology(from_process),
        "to_technology": _process_technology(to_process),
        "cost": transition.get("cost"),
    }
    return normalized


def _kind_basis(transitions: list[dict[str, Any]]) -> str | None:
    kinds = {
        str(transition.get("kind", "") or "")
        for transition in transitions
        if transition.get("kind")
    }
    if not kinds:
        return None
    if kinds == {"retrofit"}:
        return "retrofit"
    if kinds == {"switch"}:
        return "switch"
    return "transition"


def _transition_badge_label(
    *,
    node_type: str,
    participation: str,
    kind_basis: str | None,
) -> str | None:
    if participation == "none" or not kind_basis:
        return None
    if node_type == "role":
        if kind_basis == "retrofit":
            return "retrofit options"
        if kind_basis == "switch":
            return "switch options"
        return "transition options"
    if kind_basis == "retrofit":
        prefix = "retrofit"
    elif kind_basis == "switch":
        prefix = "switch"
    else:
        prefix = "transition"
    if participation == "source":
        return f"{prefix} source"
    if participation == "option":
        return f"{prefix} option"
    if participation == "source_and_option":
        return f"{prefix} source + option"
    return None


def _empty_transition_semantics() -> dict[str, Any]:
    return {
        "has_transitions": False,
        "badge_label": None,
        "participation": "none",
        "direction": "none",
        "kind_basis": None,
        "matched_transition_count": 0,
        "matched_transition_ids": [],
        "matched_transitions": [],
        "incoming_technologies": [],
        "outgoing_technologies": [],
    }


def _transition_semantics_for_role(
    transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not transitions:
        return _empty_transition_semantics()
    matched = sorted(
        transitions,
        key=lambda item: (
            str(item.get("kind", "") or ""),
            str(item.get("from_technology", "") or ""),
            str(item.get("to_technology", "") or ""),
            str(item.get("id", "") or ""),
        ),
    )
    kind_basis = _kind_basis(matched)
    return {
        "has_transitions": True,
        "badge_label": _transition_badge_label(
            node_type="role",
            participation="role",
            kind_basis=kind_basis,
        ),
        "participation": "role",
        "direction": "role",
        "kind_basis": kind_basis,
        "matched_transition_count": len(matched),
        "matched_transition_ids": [str(item["id"]) for item in matched],
        "matched_transitions": matched,
        "incoming_technologies": _sorted_unique(
            [item.get("from_technology") for item in matched]
        ),
        "outgoing_technologies": _sorted_unique(
            [item.get("to_technology") for item in matched]
        ),
    }


def _transition_semantics_for_instance(
    *,
    transitions: list[dict[str, Any]],
    member_process_ids: list[str],
) -> dict[str, Any]:
    if not transitions:
        return _empty_transition_semantics()
    process_ids = set(member_process_ids)
    matched = sorted(
        transitions,
        key=lambda item: (
            str(item.get("kind", "") or ""),
            str(item.get("from_technology", "") or ""),
            str(item.get("to_technology", "") or ""),
            str(item.get("id", "") or ""),
        ),
    )
    incoming = _sorted_unique(
        [
            item.get("from_technology")
            for item in matched
            if str(item.get("to_process", "") or "") in process_ids
        ]
    )
    outgoing = _sorted_unique(
        [
            item.get("to_technology")
            for item in matched
            if str(item.get("from_process", "") or "") in process_ids
        ]
    )
    has_incoming = bool(incoming)
    has_outgoing = bool(outgoing)
    if has_incoming and has_outgoing:
        participation = "source_and_option"
    elif has_outgoing:
        participation = "source"
    elif has_incoming:
        participation = "option"
    else:
        participation = "none"
    kind_basis = _kind_basis(matched)
    return {
        "has_transitions": participation != "none",
        "badge_label": _transition_badge_label(
            node_type="instance",
            participation=participation,
            kind_basis=kind_basis,
        ),
        "participation": participation,
        "direction": participation,
        "kind_basis": kind_basis,
        "matched_transition_count": len(matched),
        "matched_transition_ids": [str(item["id"]) for item in matched],
        "matched_transitions": matched,
        "incoming_technologies": incoming,
        "outgoing_technologies": outgoing,
    }


def _node_metric_summary(
    *,
    stock_entries: list[dict[str, Any]],
    capacity_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if stock_entries:
        stock_values = [
            entry["quantity"]
            for entry in stock_entries
            if isinstance(entry.get("quantity"), dict)
        ]
        metrics["stock"] = {
            "total": _sum_quantities(stock_values),
            "by_region": _quantity_by_region(stock_entries),
        }
    if capacity_entries:
        capacity_values = [
            entry["quantity"]
            for entry in capacity_entries
            if isinstance(entry.get("quantity"), dict)
        ]
        metrics["max_new_capacity"] = {
            "total": _sum_quantities(capacity_values),
            "by_region": _quantity_by_region(capacity_entries),
        }
    return metrics


def _scopes(regions: list[str]) -> dict[str, Any]:
    return {
        "regions": sorted(regions),
        "other": [],
    }


def _section(key: str, label: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "default_open": key in {"identity", "scopes"},
        "status": "ok",
        "items": [
            {
                "label": label,
                "kind": key,
                "id": None,
                "attributes": attributes,
                "source_location": None,
            }
        ],
    }


def _edge_inspector(
    *,
    title: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    metrics = detail.get("metrics", {})
    return {
        "title": title,
        "kind": "edge",
        "node_type": "edge",
        "summary": {
            "direction": detail.get("direction"),
            "region_count": len(detail.get("scopes", {}).get("regions", [])),
        },
        "sections": [
            _section("identity", "Identity", detail.get("identity", {})),
            _section("scopes", "Scopes", detail.get("scopes", {})),
            _section("aggregation", "Aggregation", detail.get("aggregation", {})),
            _section("metrics", "Metrics", metrics),
        ],
    }


def _build_system_node_detail(
    *,
    node_id: str,
    node_type: str,
    label: str,
    granularity: str,
    group_origin: str,
    role_name: str | None,
    technology: str | None,
    source_asset: str | None,
    source_role_instance: str | None,
    source_zone_opportunity: str | None,
    commodity: str | None = None,
    commodity_kind: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "identity": {
            "id": node_id,
            "label": label,
            "node_type": node_type,
            "granularity": granularity,
            "technology_role": role_name,
            "technology": technology,
            "commodity": commodity,
            "kind": commodity_kind,
        },
        "scopes": _scopes([]),
        "provenance": {
            "group_origin": group_origin,
            "source_asset": source_asset,
            "source_asset_kind": _asset_kind(source_asset),
            "source_role_instance": source_role_instance,
            "source_zone_opportunity": source_zone_opportunity,
        },
        "aggregation": {
            "is_aggregated": False,
            "member_count": 0,
            "member_regions": [],
            "member_ids": [],
        },
        "metrics": {},
        "ledger_emissions": empty_ledger_emissions(),
    }
    return detail


def build_v0_2_system_graph(
    *,
    csir: dict[str, Any],
    cpir: dict[str, Any],
    granularity: str,
    commodity_view: str,
    filters: FilterSpec,
) -> dict[str, Any]:
    """Build a RES graph view from v0.2 compiled artifacts."""
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    node_map: dict[str, dict[str, str]] = {}
    details_nodes: dict[str, dict[str, Any]] = {}
    details_edges: dict[str, dict[str, Any]] = {}
    role_instances = {
        str(item["id"]): item
        for item in csir.get("technology_role_instances", [])
        if isinstance(item, dict) and item.get("id")
    }
    technology_roles = {
        str(item["id"]): item
        for item in csir.get("technology_roles", [])
        if isinstance(item, dict) and item.get("id")
    }
    technology_to_role = {
        str(technology): str(role["id"])
        for role in technology_roles.values()
        for technology in role.get("technologies", [])
    }
    transitions_by_role_instance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    transitions_by_from_process: dict[str, list[dict[str, Any]]] = defaultdict(list)
    transitions_by_to_process: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_transition in cpir.get("transitions", []):
        transition = _normalize_transition(raw_transition)
        if transition is None:
            continue
        source_role_instance = str(transition.get("source_role_instance", "") or "")
        from_process = str(transition.get("from_process", "") or "")
        to_process = str(transition.get("to_process", "") or "")
        if source_role_instance:
            transitions_by_role_instance[source_role_instance].append(transition)
        if from_process:
            transitions_by_from_process[from_process].append(transition)
        if to_process:
            transitions_by_to_process[to_process].append(transition)
    commodity_metadata = {
        str(item["id"]): item
        for item in csir.get("commodities", [])
        if isinstance(item, dict) and item.get("id")
    }

    filtered_processes = [
        process
        for process in cpir.get("processes", [])
        if isinstance(process, dict)
        and str(process.get("model_region", "")) in filters.regions
    ]

    for process in filtered_processes:
        group_id, label, node_type = _group_key(
            granularity,
            process,
            role_instances=role_instances,
            technology_to_role=technology_to_role,
        )
        role_name = _role_name_for_process(
            process,
            role_instances=role_instances,
            technology_to_role=technology_to_role,
        )
        region = str(process.get("model_region", "") or "")
        source_asset = _source_asset_for_process(process, role_instances=role_instances)
        source_role_instance = (
            str(process.get("source_role_instance", "") or "") or None
        )
        source_zone_opportunity = (
            str(process.get("source_zone_opportunity", "") or "") or None
        )

        if group_id not in node_map:
            node = {"id": group_id, "label": label, "type": node_type}
            nodes.append(node)
            node_map[group_id] = node
            detail = _build_system_node_detail(
                node_id=group_id,
                node_type=node_type,
                label=label,
                granularity=granularity,
                group_origin=_group_origin(process),
                role_name=role_name,
                technology=(
                    str(process.get("technology", "") or "") or None
                    if node_type == "instance"
                    else None
                ),
                source_asset=source_asset,
                source_role_instance=source_role_instance,
                source_zone_opportunity=source_zone_opportunity,
            )
            detail.update(
                {
                    "process_id": process.get("id"),
                    "technology_role": role_name,
                    "technology": process.get("technology"),
                    "model_region": region or None,
                    "model_regions": [],
                    "model_stock_metric": process.get("model_stock_metric"),
                    "group_origin": _group_origin(process),
                    "source_role_instance": source_role_instance,
                    "source_asset": source_asset,
                    "source_zone_opportunity": source_zone_opportunity,
                    "initial_stock": process.get("initial_stock"),
                    "available_technologies": [],
                    "max_new_capacity": process.get("max_new_capacity"),
                    "member_process_ids": [],
                    "member_technologies": [],
                    "member_source_role_instances": [],
                    "member_source_zone_opportunities": [],
                    "member_source_assets": [],
                    "stock_entries": [],
                    "capacity_entries": [],
                    "ledger_emission_entries": [],
                    "transition_semantics": _empty_transition_semantics(),
                }
            )
            details_nodes[group_id] = detail

        group_details = details_nodes[group_id]
        _append_unique(group_details["model_regions"], region)
        _append_unique(group_details["member_process_ids"], process.get("id"))
        _append_unique(group_details["member_technologies"], process.get("technology"))
        _append_unique(
            group_details["member_source_role_instances"],
            source_role_instance,
        )
        _append_unique(
            group_details["member_source_zone_opportunities"],
            source_zone_opportunity,
        )
        _append_unique(group_details["member_source_assets"], source_asset)
        for technology_id in role_instances.get(source_role_instance or "", {}).get(
            "available_technologies",
            [],
        ):
            _append_unique(group_details["available_technologies"], technology_id)
        stock_entry = {
            "region": region,
            "quantity": process.get("initial_stock"),
            "member_id": process.get("id"),
        }
        if isinstance(process.get("initial_stock"), dict):
            group_details["stock_entries"].append(stock_entry)
        capacity_entry = {
            "region": region,
            "quantity": process.get("max_new_capacity"),
            "member_id": process.get("id"),
        }
        if isinstance(process.get("max_new_capacity"), dict):
            group_details["capacity_entries"].append(capacity_entry)

        for flow in process.get("flows", []):
            if not isinstance(flow, dict):
                continue
            direction = str(flow.get("direction", ""))
            if direction == "emission":
                emission_state = ledger_state_from_value(flow.get("coefficient"))
                if emission_state is not None:
                    group_details["ledger_emission_entries"].append(
                        {
                            "commodity_id": str(flow.get("commodity", "") or ""),
                            "member_id": str(process.get("id", "") or ""),
                            "state": emission_state,
                        }
                    )
                continue
            commodity = str(flow.get("commodity", ""))
            commodity_label = _display_commodity(commodity, commodity_view)
            commodity_node_id = _commodity_node_id(commodity_label)
            commodity_info = commodity_metadata.get(commodity, {})
            commodity_kind = str(commodity_info.get("type") or "commodity")
            commodity_energy_form = commodity_info.get("energy_form")
            if commodity_node_id not in node_map:
                node = {
                    "id": commodity_node_id,
                    "label": commodity_label,
                    "type": "commodity",
                }
                nodes.append(node)
                node_map[commodity_node_id] = node
                detail = _build_system_node_detail(
                    node_id=commodity_node_id,
                    node_type="commodity",
                    label=commodity_label,
                    granularity=granularity,
                    group_origin="group",
                    role_name=None,
                    technology=None,
                    source_asset=None,
                    source_role_instance=None,
                    source_zone_opportunity=None,
                    commodity=commodity,
                    commodity_kind=commodity_kind,
                )
                detail.update(
                    {
                        "commodity": commodity,
                        "kind": commodity_kind,
                        "energy_form": commodity_energy_form,
                        "model_region": None,
                        "model_regions": [],
                        "commodity_ids": [],
                        "kinds": [],
                        "energy_forms": [],
                        "member_process_ids": [],
                    }
                )
                details_nodes[commodity_node_id] = detail
            commodity_details = details_nodes[commodity_node_id]
            _append_unique(commodity_details["commodity_ids"], commodity)
            _append_unique(commodity_details["kinds"], commodity_kind)
            _append_unique(commodity_details["energy_forms"], commodity_energy_form)
            _append_unique(commodity_details["model_regions"], region)
            _append_unique(commodity_details["member_process_ids"], process.get("id"))

            if direction == "in":
                source_id, target_id, edge_type = commodity_node_id, group_id, "input"
            else:
                source_id, target_id, edge_type = group_id, commodity_node_id, direction
            edge_key = f"{source_id}->{target_id}:{commodity_node_id}:{direction}"
            if edge_key not in details_edges:
                edge_id = (
                    f"{source_id}->{target_id}:{direction}"
                    if commodity_view == "collapse_scope"
                    else f"{source_id}->{target_id}:{commodity}:{direction}"
                )
                edges.append(
                    {
                        "id": edge_id,
                        "source": source_id,
                        "target": target_id,
                        "type": edge_type,
                    }
                )
                details_edges[edge_key] = {
                    "id": edge_id,
                    "identity": {
                        "id": edge_id,
                        "source": source_id,
                        "target": target_id,
                        "type": edge_type,
                        "direction": direction,
                        "commodity": commodity_label,
                    },
                    "scopes": _scopes([]),
                    "aggregation": {
                        "is_aggregated": False,
                        "member_count": 0,
                        "member_regions": [],
                        "member_ids": [],
                    },
                    "metrics": {},
                    "commodity": commodity,
                    "commodities": [],
                    "direction": direction,
                    "coefficient": flow.get("coefficient"),
                    "technology": process.get("technology"),
                    "source_role_instance": source_role_instance,
                    "member_process_ids": [],
                    "coefficient_entries": [],
                }
            edge_detail = details_edges[edge_key]
            _append_unique(edge_detail["commodities"], commodity)
            _append_unique(edge_detail["member_process_ids"], process.get("id"))
            _append_unique(edge_detail["aggregation"]["member_regions"], region)
            _append_unique(edge_detail["aggregation"]["member_ids"], process.get("id"))
            _append_unique(edge_detail["scopes"]["regions"], region)
            if isinstance(flow.get("coefficient"), dict):
                edge_detail["coefficient_entries"].append(
                    {
                        "region": region,
                        "quantity": flow.get("coefficient"),
                        "member_id": process.get("id"),
                    }
                )

    final_edges: list[dict[str, str]] = []
    final_edge_details: dict[str, dict[str, Any]] = {}
    for edge_key, detail in details_edges.items():
        del edge_key
        detail["member_process_ids"] = _sorted_unique(detail["member_process_ids"])
        detail["aggregation"]["member_regions"] = sorted(
            detail["aggregation"]["member_regions"]
        )
        detail["aggregation"]["member_ids"] = sorted(
            detail["aggregation"]["member_ids"]
        )
        detail["aggregation"]["member_count"] = len(detail["aggregation"]["member_ids"])
        detail["aggregation"]["is_aggregated"] = detail["aggregation"][
            "member_count"
        ] > 1 or len(detail["aggregation"]["member_regions"]) > 1
        detail["commodities"] = _sorted_unique(detail["commodities"])
        detail["metrics"] = {
            "coefficient": _coefficient_metrics(detail["coefficient_entries"])
        }
        if (
            detail["coefficient_entries"]
            and detail["metrics"]["coefficient"]["value"] is not None
        ):
            detail["coefficient"] = detail["metrics"]["coefficient"]["value"]
        detail["inspector"] = _edge_inspector(
            title=str(detail["identity"]["commodity"]),
            detail=detail,
        )
        final_edges.append(
            {
                "id": str(detail["id"]),
                "source": str(detail["identity"]["source"]),
                "target": str(detail["identity"]["target"]),
                "type": str(detail["identity"]["type"]),
            }
        )
        final_edge_details[str(detail["id"])] = detail

    for detail in details_nodes.values():
        detail["model_regions"] = _sorted_unique(detail.get("model_regions", []))
        if len(detail["model_regions"]) != 1:
            detail["model_region"] = None
        detail["member_process_ids"] = _sorted_unique(
            detail.get("member_process_ids", [])
        )
        detail["member_technologies"] = _sorted_unique(
            detail.get("member_technologies", [])
        )
        detail["member_source_role_instances"] = _sorted_unique(
            detail.get("member_source_role_instances", [])
        )
        detail["member_source_zone_opportunities"] = _sorted_unique(
            detail.get("member_source_zone_opportunities", [])
        )
        detail["member_source_assets"] = _sorted_unique(
            detail.get("member_source_assets", [])
        )
        detail["available_technologies"] = _sorted_unique(
            detail.get("available_technologies", [])
        )
        if "commodity_ids" in detail:
            detail["commodity_ids"] = _sorted_unique(detail["commodity_ids"])
            detail["kinds"] = _sorted_unique(detail["kinds"])
        detail["scopes"] = _scopes(detail["model_regions"])
        detail["aggregation"] = {
            "is_aggregated": (
                len(detail["member_process_ids"]) > 1
                or len(detail["model_regions"]) > 1
            ),
            "member_count": len(detail["member_process_ids"])
            if detail["member_process_ids"]
            else len(detail.get("commodity_ids", [])),
            "member_regions": list(detail["model_regions"]),
            "member_ids": (
                list(detail["member_process_ids"])
                if detail["member_process_ids"]
                else list(detail.get("commodity_ids", []))
            ),
        }
        detail["metrics"] = _node_metric_summary(
            stock_entries=detail.pop("stock_entries", []),
            capacity_entries=detail.pop("capacity_entries", []),
        )
        detail["ledger_emissions"] = summarize_ledger_emissions(
            detail.pop("ledger_emission_entries", []),
            member_ids=detail.get("member_process_ids", []),
        )
        if detail["identity"]["node_type"] == "commodity":
            detail["identity"]["commodity_view_members"] = detail.get(
                "commodity_ids", []
            )
        elif detail["identity"]["node_type"] == "role":
            matched_by_id: dict[str, dict[str, Any]] = {}
            for role_instance_id in detail["member_source_role_instances"]:
                transitions = transitions_by_role_instance.get(role_instance_id, [])
                for transition in transitions:
                    matched_by_id[str(transition["id"])] = transition
            detail["transition_semantics"] = _transition_semantics_for_role(
                list(matched_by_id.values())
            )
        elif detail["identity"]["node_type"] == "instance":
            matched_by_id = {}
            for process_id in detail["member_process_ids"]:
                for transition in transitions_by_from_process.get(process_id, []):
                    matched_by_id[str(transition["id"])] = transition
                for transition in transitions_by_to_process.get(process_id, []):
                    matched_by_id[str(transition["id"])] = transition
            detail["transition_semantics"] = _transition_semantics_for_instance(
                transitions=list(matched_by_id.values()),
                member_process_ids=detail["member_process_ids"],
            )

    nodes.sort(key=lambda node: (node["type"], node["label"], node["id"]))
    final_edges.sort(
        key=lambda edge: (
            edge["type"],
            edge["source"],
            edge["target"],
            edge["id"],
        )
    )
    return {
        "graph": {"nodes": nodes, "edges": final_edges},
        "details": {"nodes": details_nodes, "edges": final_edge_details},
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
    filters: FilterSpec,
) -> dict[str, Any]:
    """Build a trade lens from v0.2 CSIR/CPIR network data."""
    model_regions = sorted(
        region
        for region in list((csir or {}).get("model_regions", []) or [])
        if region in filters.regions
    )
    nodes = [
        {"id": f"region:{region}", "label": region, "type": "region"}
        for region in model_regions
    ]
    details_nodes: dict[str, dict[str, Any]] = {}
    for node in nodes:
        detail = {
            "region": node["label"],
            "identity": {
                "id": node["id"],
                "label": node["label"],
                "node_type": "region",
            },
            "scopes": _scopes([node["label"]]),
            "aggregation": {
                "is_aggregated": False,
                "member_count": 1,
                "member_regions": [node["label"]],
                "member_ids": [node["id"]],
            },
            "metrics": {},
            "inspector": {
                "title": node["label"],
                "kind": "region",
                "node_type": "region",
                "summary": {"region": node["label"]},
                "sections": [
                    _section("identity", "Identity", {"region": node["label"]}),
                    _section("scopes", "Scopes", _scopes([node["label"]])),
                ],
            },
        }
        details_nodes[node["id"]] = detail

    edges: list[dict[str, str]] = []
    details_edges: dict[str, dict[str, Any]] = {}

    for arc in (cpir or {}).get("network_arcs", []):
        if not isinstance(arc, dict):
            continue
        from_region = str(arc.get("from", ""))
        to_region = str(arc.get("to", ""))
        if from_region not in filters.regions or to_region not in filters.regions:
            continue
        source_id = f"region:{from_region}"
        target_id = f"region:{to_region}"
        edge_id = f"trade:{arc['id']}"
        edges.append(
            {
                "id": edge_id,
                "source": source_id,
                "target": target_id,
                "type": "trade",
            }
        )
        detail = {
            "commodity": arc.get("commodity"),
            "source_network": arc.get("source_network") or arc.get("network"),
            "source_link": arc.get("source_link") or arc.get("link_id"),
            "existing_transfer_capacity": arc.get("existing_transfer_capacity"),
            "max_new_capacity": arc.get("max_new_capacity"),
            "identity": {
                "id": edge_id,
                "source": source_id,
                "target": target_id,
                "type": "trade",
                "commodity": arc.get("commodity"),
            },
            "scopes": _scopes([from_region, to_region]),
            "aggregation": {
                "is_aggregated": False,
                "member_count": 1,
                "member_regions": sorted([from_region, to_region]),
                "member_ids": [edge_id],
            },
            "metrics": {
                "existing_transfer_capacity": arc.get("existing_transfer_capacity"),
                "max_new_capacity": arc.get("max_new_capacity"),
            },
        }
        detail["inspector"] = _edge_inspector(
            title=str(arc.get("commodity", "trade")),
            detail=detail,
        )
        details_edges[edge_id] = detail

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "details": {"nodes": details_nodes, "edges": details_edges},
        "facets": {
            "regions": sorted((csir or {}).get("model_regions", []) or []),
            "cases": [],
            "sectors": [],
            "scopes": [],
            "granularities": ["role", "instance"],
            "commodity_views": ["scoped", "collapse_scope"],
            "lenses": ["system", "trade"],
        },
    }
