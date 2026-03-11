"""Backend bridge for the VedaLang v0.2 frontend."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from vedalang.conventions import canonicalize_commodity_id
from vedalang.versioning import annotate_tableir

from .v0_2_ast import V0_2Source, parse_v0_2_source
from .v0_2_ir import ResolvedArtifacts, build_v0_2_artifacts
from .v0_2_resolution import (
    ResolvedDefinitionGraph,
    V0_2ResolutionError,
    parse_quantity,
    resolve_imports,
)
from .v0_2_resolution import resolve_run as resolve_selected_run

DEFAULT_UNITS = {
    "energy": "PJ",
    "service": "PJ",
    "material": "Mt",
    "emission": "Mt",
    "money": "MUSD",
    "certificate": "PJ",
}

UNIT_DIMENSION = {
    "PJ": "energy",
    "TJ": "energy",
    "GJ": "energy",
    "MWh": "energy",
    "GWh": "energy",
    "TWh": "energy",
    "GW": "power",
    "MW": "power",
    "kW": "power",
    "TW": "power",
    "Mt": "mass",
    "kt": "mass",
    "t": "mass",
    "assets": "count",
}


@dataclass(frozen=True)
class CompileBundle:
    """Compiled bundle for one VedaLang source."""

    tableir: dict[str, Any]
    run_id: str | None = None
    csir: dict[str, Any] | None = None
    cpir: dict[str, Any] | None = None
    explain: dict[str, Any] | None = None


def _artifact_symbol(prefix: str, raw: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_").upper() or prefix
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}_{token}_{digest}"[:64]


def _commodity_symbol(commodity_id: str) -> str:
    return _artifact_symbol("COM", commodity_id)


def _process_symbol(process_id: str) -> str:
    return _artifact_symbol("PRC", process_id)


def _trade_sheet_name(commodity_symbol: str) -> str:
    return f"Uni_{commodity_symbol}"[:31]


def _commodity_csets(type_: str) -> str:
    return {
        "energy": "NRG",
        "service": "DEM",
        "material": "MAT",
        "emission": "ENV",
        "money": "FIN",
        "certificate": "NRG",
    }.get(type_, "NRG")


def _default_unit(type_: str) -> str:
    return DEFAULT_UNITS.get(type_, "PJ")


def _canonical_commodity_id(commodity: Any) -> str:
    return canonicalize_commodity_id(
        commodity.id,
        type_=commodity.type,
        energy_form=commodity.energy_form,
    )


def _quantity_unit(quantity: dict[str, Any] | None) -> str:
    if not isinstance(quantity, dict):
        return ""
    unit = quantity.get("unit")
    return str(unit).strip() if unit is not None else ""


def _numeric_amount(value: str | int | float | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return parse_quantity(value).value


def _activity_unit(
    process: dict[str, Any],
    graph: ResolvedDefinitionGraph,
) -> str:
    for flow in process.get("flows", []):
        if flow.get("direction") != "out":
            continue
        commodity = graph.commodities.get(flow.get("commodity", ""))
        if commodity is not None and commodity.type != "emission":
            return _default_unit(commodity.type)
    for flow in process.get("flows", []):
        if flow.get("direction") != "in":
            continue
        commodity = graph.commodities.get(flow.get("commodity", ""))
        if commodity is not None:
            return _default_unit(commodity.type)
    return "PJ"


def _capacity_unit(process: dict[str, Any], activity_unit: str) -> str:
    for field in ("initial_stock", "max_new_capacity"):
        unit = _quantity_unit(process.get(field))
        if unit:
            return unit
    metric = str(process.get("model_stock_metric", ""))
    if metric == "asset_count":
        return "assets"
    return activity_unit


def _cap_to_act(capacity_unit: str, activity_unit: str) -> float | None:
    if capacity_unit == activity_unit:
        return 1.0
    cap_dim = UNIT_DIMENSION.get(capacity_unit)
    act_dim = UNIT_DIMENSION.get(activity_unit)
    if cap_dim == "power" and act_dim == "energy":
        factors_to_gw = {"GW": 1.0, "MW": 1e-3, "kW": 1e-6, "TW": 1e3}
        factors_from_pj = {
            "PJ": 1.0,
            "TJ": 1e3,
            "GJ": 1e6,
            "MWh": 1 / 3.6e-6,
            "GWh": 1 / 3.6e-3,
            "TWh": 1 / 3.6,
        }
        to_gw = factors_to_gw.get(capacity_unit)
        from_pj = factors_from_pj.get(activity_unit)
        if to_gw is not None and from_pj is not None:
            return 31.536 * to_gw * from_pj
    return None


def _efficiency(flows: list[dict[str, Any]]) -> float | None:
    first_input = next((flow for flow in flows if flow.get("direction") == "in"), None)
    first_output = next(
        (flow for flow in flows if flow.get("direction") == "out"),
        None,
    )
    if first_input is None and first_output is not None:
        return 1.0
    if first_input is None or first_output is None:
        return None
    in_coeff = float(first_input["coefficient"]["amount"])
    out_coeff = float(first_output["coefficient"]["amount"])
    if in_coeff == 0:
        return None
    return out_coeff / in_coeff


def _require_selected_run(
    graph: ResolvedDefinitionGraph,
    selected_run: str | None,
) -> str:
    if selected_run:
        return selected_run
    run_ids = sorted(graph.runs)
    if not run_ids:
        raise V0_2ResolutionError("E002", "runs", "source defines no runs")
    if len(run_ids) == 1:
        return run_ids[0]
    raise V0_2ResolutionError(
        "E002",
        "runs",
        "multiple runs defined; select one with --run",
    )


def _normalize_packages(
    packages: dict[str, V0_2Source | dict[str, Any]] | None,
) -> dict[str, V0_2Source]:
    normalized: dict[str, V0_2Source] = {}
    for name, package in (packages or {}).items():
        normalized[name] = (
            parse_v0_2_source(package) if isinstance(package, dict) else package
        )
    return normalized


def _trade_link_files(
    network_arcs: list[dict[str, Any]],
    commodity_symbols: dict[str, str],
    *,
    base_year: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    trade_attr_rows: list[dict[str, Any]] = []
    for arc in network_arcs:
        commodity = arc["commodity"]
        commodity_symbol = commodity_symbols[commodity]
        grouped.setdefault(commodity_symbol, []).append(arc)
        pattern = f"TB_{commodity_symbol}_*,TU_{commodity_symbol}_*"
        existing = arc.get("existing_transfer_capacity")
        if isinstance(existing, dict) and existing.get("amount") not in (None, 0):
            trade_attr_rows.append(
                {
                    "region": arc["from"],
                    "pset_pn": pattern,
                    "attribute": "PRC_RESID",
                    "value": existing["amount"],
                }
            )
        max_new = arc.get("max_new_capacity")
        if isinstance(max_new, dict) and max_new.get("amount") not in (None, 0):
            trade_attr_rows.append(
                {
                    "region": arc["from"],
                    "year": base_year,
                    "limtype": "UP",
                    "pset_pn": pattern,
                    "attribute": "NCAP_BND",
                    "value": max_new["amount"],
                }
            )

    sheets = []
    for commodity_symbol, arcs in sorted(grouped.items()):
        by_origin: dict[str, dict[str, int]] = {}
        for arc in arcs:
            row = by_origin.setdefault(arc["from"], {commodity_symbol: arc["from"]})
            row[arc["to"]] = 1
        sheets.append(
            {
                "name": _trade_sheet_name(commodity_symbol),
                "tables": [
                    {
                        "tag": "~TRADELINKS",
                        "rows": [by_origin[key] for key in sorted(by_origin)],
                    }
                ],
            }
        )

    files: list[dict[str, Any]] = []
    if sheets:
        files.append(
            {
                "path": "suppxls/trades/scentrade__trade_links.xlsx",
                "sheets": sheets,
            }
        )
    if trade_attr_rows:
        files.append(
            {
                "path": "suppxls/trades/scentrade__trade_attrs.xlsx",
                "sheets": [
                    {
                        "name": "Attributes",
                        "tables": [{"tag": "~TFM_INS", "rows": trade_attr_rows}],
                    }
                ],
            }
        )
    return files


def lower_v0_2_bundle_to_tableir(
    *,
    source: dict[str, Any],
    graph: ResolvedDefinitionGraph,
    artifacts: ResolvedArtifacts,
) -> dict[str, Any]:
    """Lower a resolved v0.2 bundle into the existing TableIR backend shape."""
    run_id = artifacts.csir["run_id"]
    model_regions = list(artifacts.csir["model_regions"])
    default_region = ",".join(model_regions)
    bookname = _artifact_symbol("RUN", run_id)
    commodity_symbols = {
        commodity_id: _commodity_symbol(_canonical_commodity_id(commodity))
        for commodity_id, commodity in sorted(graph.commodities.items())
    }
    process_symbols = {
        process["id"]: _process_symbol(process["id"])
        for process in artifacts.cpir.get("processes", [])
    }

    comm_rows = [
        {
            "region": default_region,
            "csets": _commodity_csets(commodity.type),
            "commodity": commodity_symbols[commodity_id],
            "unit": _default_unit(commodity.type),
        }
        for commodity_id, commodity in sorted(graph.commodities.items())
    ]

    process_rows: list[dict[str, Any]] = []
    fi_t_rows: list[dict[str, Any]] = []
    tfm_rows: list[dict[str, Any]] = []

    for process in artifacts.cpir.get("processes", []):
        technology = graph.technologies[process["technology"]]
        region = process["model_region"]
        process_symbol = process_symbols[process["id"]]
        activity_unit = _activity_unit(process, graph)
        capacity_unit = _capacity_unit(process, activity_unit)
        process_rows.append(
            {
                "region": region,
                "process": process_symbol,
                "description": process["id"],
                "sets": "",
                "tact": activity_unit,
                "tcap": capacity_unit,
            }
        )

        first_output_symbol: str | None = None
        emission_rows: list[dict[str, Any]] = []
        for flow in process.get("flows", []):
            commodity_symbol = commodity_symbols[flow["commodity"]]
            if flow["direction"] == "in":
                fi_t_rows.append(
                    {
                        "region": region,
                        "process": process_symbol,
                        "commodity-in": commodity_symbol,
                    }
                )
            elif flow["direction"] == "out":
                if first_output_symbol is None:
                    first_output_symbol = commodity_symbol
                fi_t_rows.append(
                    {
                        "region": region,
                        "process": process_symbol,
                        "commodity-out": commodity_symbol,
                    }
                )
            elif flow["direction"] == "emission":
                emission_rows.append(
                    {
                        "region": region,
                        "process": process_symbol,
                        "commodity": commodity_symbol,
                        "attribute": "ENV_ACT",
                        "value": flow["coefficient"]["amount"],
                    }
                )

        eff_row = {"region": region, "process": process_symbol}
        if first_output_symbol:
            eff_row["commodity-out"] = first_output_symbol
        eff = _efficiency(process.get("flows", []))
        if eff is not None:
            eff_row["eff"] = eff
        cap_to_act = _cap_to_act(capacity_unit, activity_unit)
        if cap_to_act is not None:
            eff_row["prc_capact"] = cap_to_act
        if technology.investment_cost is not None:
            eff_row["ncap_cost"] = _numeric_amount(technology.investment_cost)
        if technology.fixed_om is not None:
            eff_row["ncap_fom"] = _numeric_amount(technology.fixed_om)
        if technology.variable_om is not None:
            eff_row["act_cost"] = _numeric_amount(technology.variable_om)
        if technology.lifetime is not None:
            eff_row["ncap_tlife"] = _numeric_amount(technology.lifetime)
        if len(eff_row) > 2:
            fi_t_rows.append(eff_row)

        initial_stock = process.get("initial_stock")
        if (
            isinstance(initial_stock, dict)
            and initial_stock.get("amount") not in (None, 0)
        ):
            tfm_rows.append(
                {
                    "region": region,
                    "process": process_symbol,
                    "year": artifacts.csir["base_year"],
                    "attribute": "PRC_RESID",
                    "value": initial_stock["amount"],
                }
            )

        max_new_capacity = process.get("max_new_capacity")
        if (
            isinstance(max_new_capacity, dict)
            and max_new_capacity.get("amount") not in (None, 0)
        ):
            tfm_rows.append(
                {
                    "region": region,
                    "process": process_symbol,
                    "year": artifacts.csir["base_year"],
                    "limtype": "UP",
                    "attribute": "NCAP_BND",
                    "value": max_new_capacity["amount"],
                }
            )

        fi_t_rows.extend(emission_rows)

    start_year = artifacts.csir["base_year"]
    bookregions_rows = [
        {"bookname": bookname, "region": region} for region in model_regions
    ]
    startyear_rows = [{"value": start_year}]
    milestoneyears_rows = [{"type": "Endyear", "year": start_year + 10}]
    milestoneyears_rows.append({"type": "milestoneyear", "year": start_year})
    currencies_rows = [{"currency": "USD"}]
    gdrate_rows = [
        {"region": region, "attribute": "G_DRATE", "currency": "USD", "value": 0.05}
        for region in model_regions
    ]
    yrfr_rows = [
        {"region": region, "attribute": "YRFR", "timeslice": "AN", "value": 1.0}
        for region in model_regions
    ]

    tableir = {
        "files": [
            {
                "path": "syssettings.xlsx",
                "sheets": [
                    {
                        "name": "SysSets",
                        "tables": [
                            {"tag": "~BOOKREGIONS_MAP", "rows": bookregions_rows},
                            {"tag": "~STARTYEAR", "rows": startyear_rows},
                            {"tag": "~MILESTONEYEARS", "rows": milestoneyears_rows},
                            {"tag": "~CURRENCIES", "rows": currencies_rows},
                            {"tag": "~TIMESLICES", "rows": [{"season": "AN"}]},
                        ],
                    },
                    {
                        "name": "Commodities",
                        "tables": [{"tag": "~FI_COMM", "rows": comm_rows}],
                    },
                    {
                        "name": "constants",
                        "tables": [
                            {"tag": "~TFM_INS", "rows": gdrate_rows},
                            {"tag": "~TFM_INS", "rows": yrfr_rows},
                        ],
                    },
                ],
            },
            {
                "path": f"vt_{bookname.lower()}_{run_id.lower()}.xlsx",
                "sheets": [
                    {
                        "name": "Processes",
                        "tables": [
                            {"tag": "~FI_PROCESS", "rows": process_rows},
                            {"tag": "~FI_T", "rows": fi_t_rows},
                            {"tag": "~TFM_INS", "rows": tfm_rows},
                        ],
                    }
                ],
            },
            *_trade_link_files(
                artifacts.cpir.get("network_arcs", []),
                commodity_symbols,
                base_year=start_year,
            ),
        ]
    }
    annotate_tableir(tableir, source=source)
    return tableir


def compile_v0_2_bundle(
    source: dict[str, Any],
    *,
    validate_source: callable | None = None,
    selected_run: str | None = None,
    packages: dict[str, V0_2Source | dict[str, Any]] | None = None,
    site_region_memberships: dict[str, str | list[str]] | None = None,
    site_zone_memberships: dict[str, dict[str, str | list[str]]] | None = None,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
) -> CompileBundle:
    """Compile a v0.2 source into TableIR plus CSIR/CPIR/explain artifacts."""
    if validate_source is not None:
        validate_source(source)
    from .v0_2_diagnostics import collect_v0_2_diagnostics

    diagnostics = collect_v0_2_diagnostics(
        source,
        selected_run=selected_run,
        packages=packages,
        site_region_memberships=site_region_memberships,
        site_zone_memberships=site_zone_memberships,
        measure_weights=measure_weights,
        custom_weights=custom_weights,
    )
    first_error = next(
        (diag for diag in diagnostics if diag.get("severity") == "error"),
        None,
    )
    if first_error is not None:
        raise V0_2ResolutionError(
            str(first_error.get("code", "E002")),
            str(first_error.get("object_id", "<unknown>")),
            str(first_error.get("message", "v0.2 compilation failed")),
            location=(
                str(first_error["location"])
                if first_error.get("location") is not None
                else None
            ),
            suggestion=(
                str(first_error["suggestion"])
                if first_error.get("suggestion") is not None
                else None
            ),
        )
    parsed = parse_v0_2_source(source)
    graph = resolve_imports(parsed, _normalize_packages(packages))
    run = resolve_selected_run(graph, _require_selected_run(graph, selected_run))
    artifacts = build_v0_2_artifacts(
        graph,
        run,
        site_region_memberships=site_region_memberships,
        site_zone_memberships=site_zone_memberships,
        measure_weights=measure_weights,
        custom_weights=custom_weights,
    )
    tableir = lower_v0_2_bundle_to_tableir(
        source=source,
        graph=graph,
        artifacts=artifacts,
    )
    return CompileBundle(
        tableir=tableir,
        run_id=run.run_id,
        csir=artifacts.csir,
        cpir=artifacts.cpir,
        explain=artifacts.explain,
    )
