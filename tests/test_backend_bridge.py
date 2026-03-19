import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import yaml

from tools.veda_check import run_check
from vedalang.compiler import compile_vedalang_bundle
from vedalang.compiler.artifacts import ResolvedArtifacts, build_run_artifacts
from vedalang.compiler.ast import parse_source
from vedalang.compiler.backend import lower_bundle_to_tableir
from vedalang.compiler.compiler import load_tableir_schema
from vedalang.compiler.resolution import resolve_imports, resolve_run

SCHEMA_DIR = Path(__file__).parent.parent / "vedalang" / "schema"


def _load_schema(name: str) -> dict:
    with open(SCHEMA_DIR / name) as f:
        return json.load(f)


def _sample_source(
    include_fleet: bool = False,
    include_emissions: bool = True,
) -> dict:
    source = {
        "dsl_version": "0.3",
        "commodities": [
            {"id": "natural_gas", "type": "energy", "energy_form": "primary"},
            {"id": "electricity", "type": "energy", "energy_form": "secondary"},
            {"id": "space_heat", "type": "service"},
        ],
        "technologies": [
            {
                "id": "gas_heater",
                "description": "Gas-heater converting gas to heat.",
                "provides": "space_heat",
                "inputs": [
                    {
                        "commodity": "natural_gas",
                        "basis": "HHV",
                    }
                ],
                "performance": {"kind": "efficiency", "value": 0.9},
                "emissions": [],
                "investment_cost": "220 AUD2024/kW",
                "fixed_om": "8 AUD2024/kW/year",
                "lifetime": "25 year",
                "stock_characterization": "heater_defaults",
            },
            {
                "id": "heat_pump",
                "description": "Heat-pump supplying heat from electricity.",
                "provides": "space_heat",
                "inputs": [{"commodity": "electricity"}],
                "performance": {"kind": "cop", "value": 3.2},
                "investment_cost": "400 AUD2024/kW",
                "fixed_om": "12 AUD2024/kW/year",
                "lifetime": "15 year",
            },
        ],
        "technology_roles": [
            {
                "id": "space_heat_supply",
                "description": "Space-heat supply role fixture.",
                "primary_service": "space_heat",
                "technologies": ["gas_heater", "heat_pump"],
                "transitions": [
                    {
                        "from": "gas_heater",
                        "to": "heat_pump",
                        "kind": "retrofit",
                        "cost": "70 AUD2024/kW",
                    }
                ],
            }
        ],
        "stock_characterizations": [
            {
                "id": "heater_defaults",
                "applies_to": ["gas_heater"],
                "counted_asset_label": "heater_system",
                "conversions": [
                    {
                        "from_metric": "asset_count",
                        "to_metric": "installed_capacity",
                        "factor": "8 kW/assets",
                    },
                    {
                        "from_metric": "asset_count",
                        "to_metric": "annual_activity",
                        "factor": "10 MWh/assets/year",
                    },
                ],
            }
        ],
        "spatial_layers": [
            {
                "id": "geo_demo",
                "kind": "polygon",
                "key": "region_id",
                "geometry_file": "data/regions.geojson",
            }
        ],
        "region_partitions": [
            {
                "id": "toy_states",
                "layer": "geo_demo",
                "members": ["NSW", "QLD"],
                "mapping": {"kind": "constant", "value": "NSW"},
            }
        ],
        "sites": [
            {
                "id": "brisbane_site",
                "location": {"point": {"lat": -27.47, "lon": 153.02}},
                "membership_overrides": {
                    "region_partitions": {"toy_states": "QLD"}
                },
            }
        ],
        "facilities": [
            {
                "id": "brisbane_heat",
                "description": "Brisbane heat facility fixture.",
                "site": "brisbane_site",
                "technology_role": "space_heat_supply",
                "available_technologies": ["gas_heater", "heat_pump"],
                "new_build_limits": [
                    {"technology": "heat_pump", "max_new_capacity": "500 MW"}
                ],
                "stock": {
                    "items": [
                        {
                            "technology": "gas_heater",
                            "metric": "installed_capacity",
                            "observed": {"value": "600 MW", "year": 2025},
                        }
                    ]
                },
            }
        ],
        "networks": [
            {
                "id": "east_coast_power",
                "kind": "transmission",
                "node_basis": {"kind": "region_partition", "ref": "toy_states"},
                "links": [
                    {
                        "id": "qld_nsw_power",
                        "from": "QLD",
                        "to": "NSW",
                        "commodity": "electricity",
                        "existing_transfer_capacity": "1200 MW",
                    }
                ],
            }
        ],
        "runs": [
            {
                "id": "toy_states_2025",
                "base_year": 2025,
                "currency_year": 2024,
                "region_partition": "toy_states",
            }
        ],
    }
    if include_emissions:
        source["commodities"].append({"id": "co2", "type": "emission"})
        source["technologies"][0]["emissions"] = [
            {"commodity": "co2", "factor": "0.056 t/GJ"}
        ]
    if include_fleet:
        source["fleets"] = [
            {
                "id": "residential_heat",
                "description": "Residential heat fleet fixture.",
                "technology_role": "space_heat_supply",
                "stock": {
                    "items": [
                        {
                            "technology": "gas_heater",
                            "metric": "asset_count",
                            "observed": {"value": "100 assets", "year": 2025},
                        }
                    ]
                },
                "distribution": {
                    "method": "custom",
                    "custom_weights_file": "weights/custom_heat.csv",
                },
            }
        ]
    return source


def _table_rows(tableir: dict, tag: str) -> list[dict]:
    rows: list[dict] = []
    for file_spec in tableir.get("files", []):
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == tag:
                    rows.extend(table.get("rows", []))
    return rows


def _tables_for_tag(tableir: dict, tag: str) -> list[dict]:
    tables: list[dict] = []
    for file_spec in tableir.get("files", []):
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == tag:
                    tables.append(table)
    return tables


def test_compile_public_bundle_emits_artifacts_and_trade_links():
    bundle = compile_vedalang_bundle(
        _sample_source(),
        selected_run="toy_states_2025",
    )

    assert bundle.run_id == "toy_states_2025"
    assert bundle.csir is not None
    assert bundle.cpir is not None
    assert bundle.explain is not None
    jsonschema.validate(bundle.tableir, load_tableir_schema())
    jsonschema.validate(bundle.csir, _load_schema("csir.schema.json"))
    jsonschema.validate(bundle.cpir, _load_schema("cpir.schema.json"))
    assert bundle.csir["model_years"] == [2025, 2035]
    assert bundle.csir["policy_activations"] == []
    assert bundle.cpir["model_years"] == [2025, 2035]
    assert len(bundle.cpir["user_constraints"]) == 1

    fi_process_rows = _table_rows(bundle.tableir, "~FI_PROCESS")
    tfm_rows = _table_rows(bundle.tableir, "~TFM_INS")
    trade_rows = _table_rows(bundle.tableir, "~TRADELINKS")

    assert fi_process_rows
    assert any(row.get("attribute") == "PRC_RESID" for row in tfm_rows)
    assert any(row.get("attribute") == "NCAP_BND" for row in tfm_rows)
    assert len(trade_rows) == 1
    commodity_keys = [key for key in trade_rows[0] if key != "NSW"]
    assert len(commodity_keys) == 1
    assert commodity_keys[0] == "COM_electricity"
    assert trade_rows[0][commodity_keys[0]] == "QLD"
    assert trade_rows[0]["NSW"] == "TU_electricity_QLD_NSW"
    process_symbols = {row["process"] for row in fi_process_rows}
    assert process_symbols == {
        "PRC_FAC_brisbane_heat_gas_heater",
        "PRC_FAC_brisbane_heat_heat_pump",
    }
    trade_sheet_names = {
        sheet["name"]
        for file_spec in bundle.tableir["files"]
        for sheet in file_spec.get("sheets", [])
        if any(table.get("tag") == "~TRADELINKS" for table in sheet.get("tables", []))
    }
    assert trade_sheet_names == {"U_electricity"}


def test_compile_public_bundle_lowers_retrofit_transition_to_cpir_user_constraint():
    bundle = compile_vedalang_bundle(
        _sample_source(),
        selected_run="toy_states_2025",
    )

    user_constraints = bundle.cpir.get("user_constraints", [])
    assert len(user_constraints) == 1
    retrofit_uc = user_constraints[0]
    assert retrofit_uc["kind"] == "retrofit_transition"
    assert retrofit_uc["transition_id"] == (
        "T::role_instance.brisbane_heat@QLD::gas_heater->heat_pump"
    )
    assert retrofit_uc["uc_n"] == (
        "UC_RET_role_instance_brisbane_heat_QLD_gas_heater_heat_pump"
    )
    assert retrofit_uc["uc_sets"] == {"R_E": "AllRegions", "T_E": ""}
    assert retrofit_uc["cost"] == {"amount": 70.0, "unit": "AUD2024/kW"}
    assert retrofit_uc["rows"] == [
        {
            "region": "QLD",
            "process": "P::role_instance.brisbane_heat@QLD::gas_heater",
            "side": "IN",
            "uc_act": 1.0,
        },
        {
            "region": "QLD",
            "process": "P::role_instance.brisbane_heat@QLD::heat_pump",
            "side": "OUT",
            "uc_act": 1.0,
        },
        {
            "region": "QLD",
            "year": 2025,
            "limtype": "UP",
            "uc_rhsrt": 0.0,
        },
        {
            "region": "QLD",
            "year": 2035,
            "limtype": "UP",
            "uc_rhsrt": 0.0,
        },
    ]


def test_compile_public_bundle_allocates_fleet_stock_with_custom_weights():
    bundle = compile_vedalang_bundle(
        _sample_source(include_fleet=True),
        selected_run="toy_states_2025",
        custom_weights={
            "weights/custom_heat.csv": {"NSW": 0.6, "QLD": 0.4},
        },
    )

    tfm_rows = _table_rows(bundle.tableir, "~TFM_INS")
    prc_resid = [row for row in tfm_rows if row.get("attribute") == "PRC_RESID"]

    assert len(prc_resid) >= 3
    assert {row["region"] for row in prc_resid} >= {"NSW", "QLD"}
    assert any(row.get("value") == 320.0 for row in prc_resid)
    assert any(row.get("value") == 480.0 for row in prc_resid)


def test_compile_public_bundle_attaches_asset_new_build_limits_to_role_processes():
    source = _sample_source(include_fleet=True)
    source["fleets"][0]["distribution"] = {
        "method": "direct",
        "target_regions": ["QLD"],
    }
    source["fleets"][0]["new_build_limits"] = [
        {"technology": "heat_pump", "max_new_capacity": "500 MW"}
    ]
    bundle = compile_vedalang_bundle(
        source,
        selected_run="toy_states_2025",
    )

    tfm_rows = _table_rows(bundle.tableir, "~TFM_INS")
    assert any(
        row.get("attribute") == "NCAP_BND"
        and row.get("region") == "QLD"
        and row.get("value") == 500.0
        for row in tfm_rows
    )
    assert not any(
        process.get("source_zone_opportunity")
        for process in bundle.cpir.get("processes", [])
    )


def test_compile_public_bundle_lowers_activity_bound_to_act_bnd():
    source = _sample_source()
    source["technologies"][0]["activity_bound"] = {
        "limtype": "UP",
        "value": "0.06 PJ",
    }

    bundle = compile_vedalang_bundle(
        source,
        selected_run="toy_states_2025",
    )

    fi_t_rows = _table_rows(bundle.tableir, "~FI_T")
    assert any(
        row.get("process") == "PRC_FAC_brisbane_heat_gas_heater"
        and row.get("limtype") == "UP"
        and row.get("year") == 2025
        and row.get("act_bnd") == 0.06
        for row in fi_t_rows
    )


def _tableir_with_injected_user_constraints() -> dict:
    source = _sample_source()
    parsed = parse_source(source)
    graph = resolve_imports(parsed, {})
    run = resolve_run(graph, "toy_states_2025")
    artifacts = build_run_artifacts(graph, run)

    cpir = deepcopy(artifacts.cpir)
    cpir["model_years"] = [2025, 2030, 2035]
    gas_process = next(
        process
        for process in cpir["processes"]
        if process["technology"] == "gas_heater"
    )
    cpir["user_constraints"] = [
        {
            "id": "UC::RETROFIT::toy",
            "uc_n": "UC_RETROFIT_TOY",
            "description": "Synthetic retrofit link for backend UC emission tests",
            "uc_sets": {"R_E": "QLD", "T_E": ""},
            "rows": [
                {
                    "region": gas_process["model_region"],
                    "process": gas_process["id"],
                    "side": "IN",
                    "uc_act": 1.0,
                },
                {
                    "region": gas_process["model_region"],
                    "commodity": "co2",
                    "side": "OUT",
                    "attribute": "uc_comprd",
                    "value": 1.0,
                },
                {
                    "region": gas_process["model_region"],
                    "limtype": "UP",
                    "uc_rhsrt": 0.4,
                },
            ],
        }
    ]
    rewritten_artifacts = ResolvedArtifacts(
        csir=artifacts.csir,
        cpir=cpir,
        explain=artifacts.explain,
    )
    return lower_bundle_to_tableir(
        source=source,
        graph=graph,
        artifacts=rewritten_artifacts,
    )


def test_lower_bundle_emits_uc_tables_from_cpir_user_constraints():
    tableir = _tableir_with_injected_user_constraints()

    uc_tables = _tables_for_tag(tableir, "~UC_T")
    assert len(uc_tables) == 1
    assert uc_tables[0].get("uc_sets") == {"R_E": "QLD", "T_E": ""}

    uc_rows = uc_tables[0]["rows"]
    assert uc_rows
    assert all("value" not in row for row in uc_rows)
    assert any(row.get("uc_comprd") == 1.0 for row in uc_rows)
    assert any(
        row.get("process") == "PRC_FAC_brisbane_heat_gas_heater"
        for row in uc_rows
    )
    assert any(row.get("commodity") == "COM_co2" for row in uc_rows)
    assert any(row.get("side") == "LHS" for row in uc_rows)
    assert any(row.get("side") == "RHS" for row in uc_rows)
    assert all(row.get("side") not in {"IN", "OUT"} for row in uc_rows)

    rhs_years = sorted(
        row["year"]
        for row in uc_rows
        if row.get("uc_rhsrt") is not None
    )
    assert rhs_years == [2025, 2030, 2035]

    milestone_rows = _table_rows(tableir, "~MILESTONEYEARS")
    assert any(row == {"type": "Endyear", "year": 2035} for row in milestone_rows)
    assert {
        row["year"] for row in milestone_rows if row.get("type") == "milestoneyear"
    } == {2025, 2030, 2035}


def test_injected_uc_tableir_passes_run_check(tmp_path):
    tableir = _tableir_with_injected_user_constraints()
    path = tmp_path / "uc_backend_fixture.tableir.yaml"
    path.write_text(yaml.safe_dump(tableir, sort_keys=False), encoding="utf-8")

    result = run_check(path, from_tableir=True)
    assert result.success
    assert result.errors == 0
