"""CSIR/CPIR/explain emitters for the VedaLang public frontend."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from vedalang.conventions import canonicalize_commodity_id
from vedalang.versioning import DSL_VERSION

from .resolution import (
    ParsedQuantity,
    ResolvedDefinitionGraph,
    RunContext,
    allocate_fleet_stock,
    derive_stock_views,
    parse_quantity,
    resolve_asset_new_build_limits,
    resolve_asset_stock,
    resolve_policy_activations,
    resolve_sites,
    resolve_zone_opportunities,
)

ARTIFACT_VERSION = "1.0.0"


@dataclass(frozen=True)
class ResolvedArtifacts:
    csir: dict[str, Any]
    explain: dict[str, Any]
    cpir: dict[str, Any]


def _quantity_dict(quantity: ParsedQuantity) -> dict[str, Any]:
    return {"amount": quantity.value, "unit": quantity.unit}


def _sorted_dict(items: dict[str, Any]) -> dict[str, Any]:
    return {key: items[key] for key in sorted(items)}


def _default_model_years(base_year: int) -> list[int]:
    return sorted({base_year, base_year + 10})


def _sanitize_uc_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return token or "VALUE"


def _retrofit_uc_symbol(
    role_instance_id: str,
    from_technology: str,
    to_technology: str,
) -> str:
    return (
        f"UC_RET_{_sanitize_uc_token(role_instance_id)}"
        f"_{_sanitize_uc_token(from_technology)}"
        f"_{_sanitize_uc_token(to_technology)}"
    )


def _emissions_budget_uc_symbol(
    policy_id: str,
    model_region: str,
) -> str:
    return (
        f"UC_EMS_{_sanitize_uc_token(policy_id)}"
        f"_{_sanitize_uc_token(model_region)}"
    )


def emit_csir(
    graph: ResolvedDefinitionGraph,
    run: RunContext,
    *,
    site_region_memberships: dict[str, str | list[str]] | None = None,
    site_zone_memberships: dict[str, dict[str, str | list[str]]] | None = None,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit a deterministic CSIR artifact plus explain trace catalog."""
    resolved_sites = resolve_sites(
        graph,
        run,
        site_region_memberships=site_region_memberships,
        site_zone_memberships=site_zone_memberships,
    )
    resolved_zone_opportunities = resolve_zone_opportunities(graph, run, resolved_sites)
    policy_activations = resolve_policy_activations(graph, run)
    explain_objects: dict[str, Any] = {}
    explain_traces: dict[str, Any] = {}
    role_instances: list[dict[str, Any]] = []

    for site_id in sorted(resolved_sites):
        site = resolved_sites[site_id]
        trace_id = f"trace.site.{site_id}.region_resolution"
        explain_traces[trace_id] = {
            "kind": "site_to_region",
            "site": site_id,
            "model_region": site.model_region,
        }
    sites = [
        {
            "id": site_id,
            "resolved_model_region": resolved_sites[site_id].model_region,
            "trace_ids": [f"trace.site.{site_id}.region_resolution"],
        }
        for site_id in sorted(resolved_sites)
    ]

    for facility_id in sorted(graph.facilities):
        facility = graph.facilities[facility_id]
        adjusted = resolve_asset_stock(facility, graph=graph, run=run)
        new_build_limits = resolve_asset_new_build_limits(facility, graph=graph)
        site = resolved_sites[facility.site]
        role = graph.technology_roles[facility.technology_role]
        available = tuple(facility.available_technologies or role.technologies)
        stock_items = []
        for item in adjusted:
            norm_trace = f"trace.norm.{facility_id}.{item.technology}"
            stock_trace = (
                f"trace.stock_view.{facility_id}.{site.model_region}.{item.technology}"
            )
            explain_traces[norm_trace] = {
                "kind": "temporal_adjustment",
                "asset": facility_id,
                "technology": item.technology,
                **item.trace,
                "result": _quantity_dict(item.adjusted),
            }
            views = {
                metric: _quantity_dict(quantity)
                for metric, quantity in _sorted_dict(
                    derive_stock_views(graph, item)
                ).items()
            }
            explain_traces[stock_trace] = {
                "kind": "stock_characterization",
                "asset": facility_id,
                "technology": item.technology,
                "declared_metric": item.declared_metric,
                "stock_views": views,
            }
            stock_items.append(
                {
                    "technology": item.technology,
                    "declared_metric": item.declared_metric,
                    "stock_views": views,
                    "trace_ids": [norm_trace, stock_trace],
                }
            )
        role_instance_id = f"role_instance.{facility_id}@{site.model_region}"
        role_instances.append(
            {
                "id": role_instance_id,
                "source_asset": f"facilities.{facility_id}",
                "technology_role": facility.technology_role,
                "model_region": site.model_region,
                "available_technologies": list(sorted(available)),
                "new_build_limits": [
                    {
                        "technology": item.technology,
                        "max_new_capacity": _quantity_dict(item.max_new_capacity),
                    }
                    for item in sorted(
                        new_build_limits,
                        key=lambda item: item.technology,
                    )
                ],
                "initial_stock": sorted(
                    stock_items, key=lambda item: item["technology"]
                ),
                "trace_ids": [f"trace.site.{facility.site}.region_resolution"],
            }
        )
        explain_objects[role_instance_id] = {
            "public_origin": {
                "facility": facility_id,
                "technology_role": facility.technology_role,
            },
            "resolved_model_region": site.model_region,
            "trace_ids": [f"trace.site.{facility.site}.region_resolution"],
        }

    for fleet_id in sorted(graph.fleets):
        fleet = graph.fleets[fleet_id]
        adjusted = resolve_asset_stock(fleet, graph=graph, run=run)
        new_build_limits = resolve_asset_new_build_limits(fleet, graph=graph)
        allocations = allocate_fleet_stock(
            graph,
            run,
            fleet,
            adjusted,
            measure_weights=measure_weights,
            custom_weights=custom_weights,
        )
        role = graph.technology_roles[fleet.technology_role]
        available = tuple(fleet.available_technologies or role.technologies)
        total_trace = f"trace.norm.{fleet_id}.total"
        explain_traces[total_trace] = {
            "kind": "temporal_adjustment",
            "asset": fleet_id,
            "items": [
                {
                    "technology": item.technology,
                    "declared_metric": item.declared_metric,
                    "result": _quantity_dict(item.adjusted),
                    **item.trace,
                }
                for item in adjusted
            ],
        }
        for allocation in allocations:
            alloc_trace = f"trace.alloc.{fleet_id}.{allocation.model_region}"
            explain_traces[alloc_trace] = {
                "kind": (
                    "direct_region_binding"
                    if fleet.distribution.method == "direct"
                    else "spatial_allocation"
                ),
                "fleet": fleet_id,
                "model_region": allocation.model_region,
                "share": allocation.share,
                "weight_measure": fleet.distribution.weight_by,
                "target_regions": list(fleet.distribution.target_regions),
            }
            stock_items = []
            for item in allocation.initial_stock:
                stock_trace = (
                    "trace.stock_view."
                    f"{fleet_id}.{allocation.model_region}.{item.technology}"
                )
                views = {
                    metric: _quantity_dict(quantity)
                    for metric, quantity in _sorted_dict(
                        allocation.derived_stock_views[item.technology]
                    ).items()
                }
                explain_traces[stock_trace] = {
                    "kind": "stock_characterization",
                    "fleet": fleet_id,
                    "model_region": allocation.model_region,
                    "technology": item.technology,
                    "declared_metric": item.declared_metric,
                    "stock_views": views,
                }
                stock_items.append(
                    {
                        "technology": item.technology,
                        "declared_metric": item.declared_metric,
                        "stock_views": views,
                        "trace_ids": [total_trace, alloc_trace, stock_trace],
                    }
                )
            role_instance_id = f"role_instance.{fleet_id}@{allocation.model_region}"
            role_instances.append(
                {
                    "id": role_instance_id,
                    "source_asset": f"fleets.{fleet_id}",
                    "technology_role": fleet.technology_role,
                    "model_region": allocation.model_region,
                    "available_technologies": list(sorted(available)),
                    "new_build_limits": [
                        {
                            "technology": item.technology,
                            "max_new_capacity": _quantity_dict(item.max_new_capacity),
                        }
                        for item in sorted(
                            new_build_limits,
                            key=lambda item: item.technology,
                        )
                    ],
                    "initial_stock": sorted(
                        stock_items,
                        key=lambda item: item["technology"],
                    ),
                    "trace_ids": [total_trace, alloc_trace],
                }
            )
            explain_objects[role_instance_id] = {
                "public_origin": {
                    "fleet": fleet_id,
                    "technology_role": fleet.technology_role,
                },
                "resolved_model_region": allocation.model_region,
                "trace_ids": [total_trace, alloc_trace],
            }

    zone_opportunities = []
    for opportunity_id in sorted(resolved_zone_opportunities):
        opportunity = resolved_zone_opportunities[opportunity_id]
        trace_id = f"trace.zone_opportunity.{opportunity_id}.siting"
        explain_traces[trace_id] = {
            "kind": "zone_opportunity_siting",
            "zone_opportunity": opportunity_id,
            "model_region": opportunity.model_region,
            "zone": graph.zone_opportunities[opportunity_id].zone,
        }
        zone_opportunities.append(
            {
                "id": opportunity_id,
                "technology_role": opportunity.technology_role,
                "technology": opportunity.technology,
                "model_region": opportunity.model_region,
                "max_new_capacity": _quantity_dict(
                    parse_quantity(
                        graph.zone_opportunities[opportunity_id].max_new_capacity
                    )
                ),
                "trace_ids": [trace_id],
            }
        )

    networks = []
    for network_id in sorted(graph.networks):
        network = graph.networks[network_id]
        networks.append(
            {
                "id": network_id,
                "kind": network.kind,
                "node_basis": {
                    "kind": network.node_basis.kind,
                    "ref": network.node_basis.ref,
                },
                "links": [
                    {
                        "id": link.id,
                        "from": link.from_node,
                        "to": link.to_node,
                        "commodity": link.commodity,
                        "existing_transfer_capacity": (
                            _quantity_dict(
                                parse_quantity(link.existing_transfer_capacity)
                            )
                            if link.existing_transfer_capacity is not None
                            else None
                        ),
                        "max_new_capacity": (
                            _quantity_dict(parse_quantity(link.max_new_capacity))
                            if link.max_new_capacity is not None
                            else None
                        ),
                    }
                    for link in sorted(network.links, key=lambda link: link.id)
                ],
            }
        )

    csir = {
        "artifact_kind": "csir",
        "artifact_version": ARTIFACT_VERSION,
        "dsl_version": DSL_VERSION,
        "run_id": run.run_id,
        "base_year": run.base_year,
        "model_years": _default_model_years(run.base_year),
        "currency_year": run.currency_year,
        "region_partition": run.region_partition,
        "model_regions": list(run.model_regions),
        "commodities": [
            {
                "id": commodity.id,
                "canonical_id": canonicalize_commodity_id(
                    commodity.id,
                    type_=commodity.type,
                    energy_form=commodity.energy_form,
                ),
                "type": commodity.type,
                "energy_form": commodity.energy_form,
            }
            for commodity in sorted(
                graph.commodities.values(),
                key=lambda item: item.id,
            )
        ],
        "technology_roles": [
            {
                "id": role.id,
                "primary_service": role.primary_service,
                "technologies": list(role.technologies),
            }
            for role in sorted(
                graph.technology_roles.values(), key=lambda role: role.id
            )
        ],
        "sites": sites,
        "technology_role_instances": sorted(
            role_instances, key=lambda item: item["id"]
        ),
        "policy_activations": [
            {
                "policy_id": activation.policy_id,
                "kind": activation.kind,
                "selected_case": activation.selected_case,
                "emission_commodity": activation.emission_commodity,
                "budgets": [
                    {
                        "year": budget.year,
                        **_quantity_dict(budget.value),
                    }
                    for budget in activation.budgets
                ],
                "role_instances": sorted(
                    [
                        role_instance["id"]
                        for role_instance in role_instances
                        if role_instance["source_asset"].startswith("facilities.")
                        and activation.policy_id
                        in graph.facilities[
                            role_instance["source_asset"].split(".", 1)[1]
                        ].policies
                    ]
                    + [
                        role_instance["id"]
                        for role_instance in role_instances
                        if role_instance["source_asset"].startswith("fleets.")
                        and activation.policy_id
                        in graph.fleets[
                            role_instance["source_asset"].split(".", 1)[1]
                        ].policies
                    ]
                ),
            }
            for activation in policy_activations
        ],
        "zone_opportunities": zone_opportunities,
        "networks": networks,
    }
    explain = {
        "artifact_kind": "explain",
        "artifact_version": ARTIFACT_VERSION,
        "dsl_version": DSL_VERSION,
        "run_id": run.run_id,
        "objects": _sorted_dict(explain_objects),
        "traces": _sorted_dict(explain_traces),
    }
    return csir, explain


def _role_instance_metric(role_instance: dict[str, Any]) -> tuple[str, str]:
    metrics = {
        metric: views[metric]["unit"]
        for item in role_instance.get("initial_stock", [])
        for metric, views in [
            (metric, item["stock_views"]) for metric in item["stock_views"]
        ]
    }
    for candidate in ("installed_capacity", "annual_activity", "asset_count"):
        if candidate in metrics:
            return candidate, metrics[candidate]
    return "installed_capacity", ""


def _technology_flows(technology: Any) -> list[dict[str, Any]]:
    flows: list[dict[str, Any]] = []
    performance_value = technology.performance.value if technology.performance else 1.0
    for flow in technology.inputs:
        coefficient = (
            parse_quantity(flow.coefficient)
            if flow.coefficient is not None
            else ParsedQuantity(value=1.0 / performance_value, unit="")
        )
        flows.append(
            {
                "direction": "in",
                "commodity": flow.commodity,
                "coefficient": _quantity_dict(coefficient),
            }
        )
    outputs = technology.outputs or ()
    if outputs:
        for flow in outputs:
            coefficient = (
                parse_quantity(flow.coefficient)
                if flow.coefficient is not None
                else ParsedQuantity(value=1.0, unit="")
            )
            flows.append(
                {
                    "direction": "out",
                    "commodity": flow.commodity,
                    "coefficient": _quantity_dict(coefficient),
                }
            )
    else:
        flows.append(
            {
                "direction": "out",
                "commodity": technology.provides,
                "coefficient": _quantity_dict(ParsedQuantity(value=1.0, unit="")),
            }
        )
    for emission in technology.emissions:
        flows.append(
            {
                "direction": "emission",
                "commodity": emission.commodity,
                "coefficient": _quantity_dict(parse_quantity(emission.factor)),
            }
        )
    return flows


def lower_csir_to_cpir(
    csir: dict[str, Any],
    graph: ResolvedDefinitionGraph,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Lower CSIR semantic objects to deterministic CPIR process objects."""
    processes: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    user_constraints: list[dict[str, Any]] = []
    network_arcs: list[dict[str, Any]] = []
    explain_objects: dict[str, Any] = {}
    explain_traces: dict[str, Any] = {}
    model_years = sorted(
        {
            int(year)
            for year in (
                csir.get("model_years")
                or _default_model_years(int(csir.get("base_year", 0)))
            )
        }
    )

    for role_instance in csir.get("technology_role_instances", []):
        role = graph.technology_roles[role_instance["technology_role"]]
        metric, metric_unit = _role_instance_metric(role_instance)
        stock_by_technology = {
            item["technology"]: item["stock_views"]
            for item in role_instance.get("initial_stock", [])
        }
        new_build_by_technology = {
            item["technology"]: item["max_new_capacity"]
            for item in role_instance.get("new_build_limits", [])
            if isinstance(item, dict)
        }
        for technology_id in sorted(role_instance["available_technologies"]):
            process_id = f"P::{role_instance['id']}::{technology_id}"
            stock_view = stock_by_technology.get(technology_id, {})
            quantity = stock_view.get(metric) or {"amount": 0.0, "unit": metric_unit}
            process = {
                "id": process_id,
                "source_role_instance": role_instance["id"],
                "technology": technology_id,
                "model_region": role_instance["model_region"],
                "model_stock_metric": metric,
                "initial_stock": quantity,
                "flows": _technology_flows(graph.technologies[technology_id]),
            }
            max_new_capacity = new_build_by_technology.get(technology_id)
            if isinstance(max_new_capacity, dict):
                process["max_new_capacity"] = max_new_capacity
            processes.append(process)
            lower_trace = f"trace.lower.{process_id}"
            explain_traces[lower_trace] = {
                "kind": "role_instance_to_process",
                "role_instance": role_instance["id"],
                "technology": technology_id,
            }
            explain_objects[process_id] = {
                "generated_from": {"role_instance": role_instance["id"]},
                "trace_ids": [lower_trace],
            }
        allowed = set(role_instance["available_technologies"])
        for transition in role.transitions:
            if (
                transition.from_technology not in allowed
                or transition.to_technology not in allowed
            ):
                continue
            edge_id = (
                f"T::{role_instance['id']}::"
                f"{transition.from_technology}->{transition.to_technology}"
            )
            from_process = f"P::{role_instance['id']}::{transition.from_technology}"
            to_process = f"P::{role_instance['id']}::{transition.to_technology}"
            cost = (
                _quantity_dict(parse_quantity(transition.cost))
                if transition.cost is not None
                else None
            )
            transitions.append(
                {
                    "id": edge_id,
                    "source_role_instance": role_instance["id"],
                    "from_process": from_process,
                    "to_process": to_process,
                    "kind": transition.kind,
                    "cost": cost,
                }
            )
            if transition.kind == "retrofit":
                user_constraint_id = f"UC::{edge_id}"
                user_constraint = {
                    "id": user_constraint_id,
                    "kind": "retrofit_transition",
                    "uc_n": _retrofit_uc_symbol(
                        role_instance_id=role_instance["id"],
                        from_technology=transition.from_technology,
                        to_technology=transition.to_technology,
                    ),
                    "description": (
                        "Retrofit "
                        f"{transition.from_technology} -> {transition.to_technology}"
                    ),
                    "source_role_instance": role_instance["id"],
                    "transition_id": edge_id,
                    "uc_sets": {"R_E": "AllRegions", "T_E": ""},
                    "rows": [
                        {
                            "region": role_instance["model_region"],
                            "process": from_process,
                            "side": "IN",
                            "uc_act": 1.0,
                        },
                        {
                            "region": role_instance["model_region"],
                            "process": to_process,
                            "side": "OUT",
                            "uc_act": 1.0,
                        },
                        *[
                            {
                                "region": role_instance["model_region"],
                                "year": year,
                                "limtype": "UP",
                                "uc_rhsrt": 0.0,
                            }
                            for year in model_years
                        ],
                    ],
                }
                if cost is not None:
                    user_constraint["cost"] = cost
                user_constraints.append(user_constraint)
                trace_id = f"trace.lower.{user_constraint_id}"
                explain_objects[user_constraint_id] = {
                    "generated_from": {"transition": edge_id},
                    "trace_ids": [trace_id],
                }
                explain_traces[trace_id] = {
                    "kind": "retrofit_transition_to_user_constraint",
                    "transition": edge_id,
                    "user_constraint": user_constraint_id,
                }

    processes_by_id = {process["id"]: process for process in processes}
    for activation in csir.get("policy_activations", []):
        if not isinstance(activation, dict):
            continue
        if activation.get("kind") != "emissions_budget":
            continue
        emission_commodity = str(activation.get("emission_commodity", ""))
        budgets = [
            budget
            for budget in (activation.get("budgets") or [])
            if isinstance(budget, dict)
        ]
        if not budgets:
            continue

        role_instance_ids = {
            str(role_instance_id)
            for role_instance_id in (activation.get("role_instances") or [])
            if role_instance_id is not None
        }
        if not role_instance_ids:
            continue

        processes_by_region: dict[str, list[str]] = {}
        for process_id, process in processes_by_id.items():
            source_role_instance = process.get("source_role_instance")
            if source_role_instance not in role_instance_ids:
                continue
            if not any(
                flow.get("direction") == "emission"
                and flow.get("commodity") == emission_commodity
                for flow in process.get("flows", [])
            ):
                continue
            region = str(process.get("model_region"))
            processes_by_region.setdefault(region, []).append(process_id)

        for region, region_process_ids in sorted(processes_by_region.items()):
            uc_id = (
                f"UC::POLICY::{activation.get('policy_id')}::{region}"
            )
            uc_n = _emissions_budget_uc_symbol(
                str(activation.get("policy_id", "policy")),
                region,
            )
            rows: list[dict[str, Any]] = []
            for process_id in sorted(region_process_ids):
                rows.append(
                    {
                        "region": region,
                        "process": process_id,
                        "commodity": emission_commodity,
                        "side": "OUT",
                        "top_check": "O",
                        "uc_comprd": 1.0,
                    }
                )
            for budget in sorted(
                budgets,
                key=lambda item: int(item.get("year", 0)),
            ):
                year_value = budget.get("year")
                amount_value = budget.get("amount")
                if not isinstance(year_value, int):
                    continue
                if not isinstance(amount_value, (int, float)):
                    continue
                rows.append(
                    {
                        "region": region,
                        "year": year_value,
                        "limtype": "UP",
                        "uc_rhsrt": float(amount_value),
                    }
                )

            user_constraints.append(
                {
                    "id": uc_id,
                    "kind": "emissions_budget",
                    "uc_n": uc_n,
                    "description": (
                        "Emissions budget "
                        f"{activation.get('policy_id')} for {region}"
                    ),
                    "source_policy": activation.get("policy_id"),
                    "selected_case": activation.get("selected_case"),
                    "emission_commodity": emission_commodity,
                    "uc_sets": {"R_E": "AllRegions", "T_E": ""},
                    "rows": rows,
                }
            )
            trace_id = f"trace.lower.{uc_id}"
            explain_objects[uc_id] = {
                "generated_from": {
                    "policy": activation.get("policy_id"),
                    "model_region": region,
                },
                "trace_ids": [trace_id],
            }
            explain_traces[trace_id] = {
                "kind": "emissions_budget_to_user_constraint",
                "policy": activation.get("policy_id"),
                "model_region": region,
                "user_constraint": uc_id,
            }
    for opportunity in csir.get("zone_opportunities", []):
        process_id = (
            f"P::zone_opportunity::{opportunity['id']}::{opportunity['technology']}"
        )
        technology = graph.technologies[opportunity["technology"]]
        processes.append(
            {
                "id": process_id,
                "source_zone_opportunity": opportunity["id"],
                "technology": opportunity["technology"],
                "model_region": opportunity["model_region"],
                "model_stock_metric": "installed_capacity",
                "initial_stock": {"amount": 0.0, "unit": ""},
                "max_new_capacity": dict(opportunity.get("max_new_capacity") or {}),
                "flows": _technology_flows(technology),
            }
        )
        explain_objects[process_id] = {
            "generated_from": {"zone_opportunity": opportunity["id"]},
            "trace_ids": [f"trace.lower.{process_id}"],
        }
        explain_traces[f"trace.lower.{process_id}"] = {
            "kind": "zone_opportunity_to_process",
            "zone_opportunity": opportunity["id"],
            "technology": opportunity["technology"],
        }
    for network in csir.get("networks", []):
        node_basis = network["node_basis"]
        if (
            node_basis["kind"] == "region_partition"
            and node_basis.get("ref") != csir["region_partition"]
        ):
            raise ValueError(
                "E013 network node_basis region_partition mismatches "
                "selected run partition"
            )
        for link in network.get("links", []):
            arc_id = f"N::{network['id']}::{link['id']}"
            network_arcs.append(
                {
                    "id": arc_id,
                    "network": network["id"],
                    "link_id": link["id"],
                    "from": link["from"],
                    "to": link["to"],
                    "commodity": link["commodity"],
                    "existing_transfer_capacity": link.get(
                        "existing_transfer_capacity"
                    ),
                    "max_new_capacity": link.get("max_new_capacity"),
                }
            )
            explain_objects[arc_id] = {
                "generated_from": {"network": network["id"], "link": link["id"]},
                "trace_ids": [f"trace.lower.{arc_id}"],
            }
            explain_traces[f"trace.lower.{arc_id}"] = {
                "kind": "network_to_arc",
                "network": network["id"],
                "link": link["id"],
            }

    cpir = {
        "artifact_kind": "cpir",
        "artifact_version": ARTIFACT_VERSION,
        "dsl_version": DSL_VERSION,
        "run_id": csir["run_id"],
        "model_years": model_years,
        "model_regions": list(csir["model_regions"]),
        "processes": sorted(processes, key=lambda item: item["id"]),
        "transitions": sorted(transitions, key=lambda item: item["id"]),
        "user_constraints": sorted(user_constraints, key=lambda item: item["id"]),
        "network_arcs": sorted(network_arcs, key=lambda item: item["id"]),
    }
    explain = {
        "artifact_kind": "explain",
        "artifact_version": ARTIFACT_VERSION,
        "dsl_version": DSL_VERSION,
        "run_id": csir["run_id"],
        "objects": _sorted_dict(explain_objects),
        "traces": _sorted_dict(explain_traces),
    }
    return cpir, explain


def build_run_artifacts(
    graph: ResolvedDefinitionGraph,
    run: RunContext,
    *,
    site_region_memberships: dict[str, str | list[str]] | None = None,
    site_zone_memberships: dict[str, dict[str, str | list[str]]] | None = None,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
) -> ResolvedArtifacts:
    """Build CSIR, explain, and CPIR artifacts for a resolved public model."""
    csir, explain = emit_csir(
        graph,
        run,
        site_region_memberships=site_region_memberships,
        site_zone_memberships=site_zone_memberships,
        measure_weights=measure_weights,
        custom_weights=custom_weights,
    )
    cpir, lowering_explain = lower_csir_to_cpir(csir, graph)
    merged_explain = {
        **explain,
        "objects": _sorted_dict(
            {
                **explain["objects"],
                **lowering_explain["objects"],
            }
        ),
        "traces": _sorted_dict(
            {
                **explain["traces"],
                **lowering_explain["traces"],
            }
        ),
    }
    return ResolvedArtifacts(csir=csir, explain=merged_explain, cpir=cpir)
