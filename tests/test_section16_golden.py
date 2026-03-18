import json

from vedalang.compiler import parse_source
from vedalang.compiler.artifacts import build_run_artifacts
from vedalang.compiler.resolution import resolve_imports, resolve_run


def _section16_packages_and_model():
    regions = parse_source(
        {
            "dsl_version": "0.3",
            "spatial_layers": [
                {
                    "id": "geo_regions_sa2_2021",
                    "kind": "polygon",
                    "key": "sa2_code",
                    "geometry_file": "data/sa2.geojson",
                }
            ],
            "region_partitions": [
                {
                    "id": "toy_states_3",
                    "layer": "geo_regions_sa2_2021",
                    "members": ["NSW", "VIC", "QLD"],
                    "mapping": {
                        "kind": "file",
                        "file": "data/sa2_to_state.csv",
                        "source_key": "sa2_code",
                        "target_key": "state_id",
                    },
                }
            ],
        }
    )
    demo = parse_source(
        {
            "dsl_version": "0.3",
            "spatial_layers": [
                {
                    "id": "geo_demo_sa2_2021",
                    "kind": "polygon",
                    "key": "sa2_code",
                    "geometry_file": "data/sa2.geojson",
                }
            ],
            "spatial_measure_sets": [
                {
                    "id": "abs_demography",
                    "layer": "geo_demo_sa2_2021",
                    "measures": [
                        {
                            "id": "dwelling_stock",
                            "observed_year": 2023,
                            "unit": "dwellings",
                            "file": "data/abs.parquet",
                            "column": "dwelling_stock",
                        }
                    ],
                }
            ],
            "temporal_index_series": [
                {
                    "id": "national_dwelling_stock_index",
                    "unit": "index",
                    "values": {"2023": 1.0, "2024": 1.02, "2025": 1.04},
                }
            ],
        }
    )
    heat = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "natural_gas", "type": "energy", "energy_form": "primary"},
                {"id": "electricity", "type": "energy", "energy_form": "secondary"},
                {"id": "space_heat", "type": "service"},
                {"id": "steam", "type": "service"},
                {"id": "co2", "type": "emission"},
            ],
            "technologies": [
                {
                    "id": "gas_heater",
                    "provides": "space_heat",
                    "inputs": [{"commodity": "natural_gas", "basis": "HHV"}],
                    "performance": {"kind": "efficiency", "value": 0.9},
                    "emissions": [
                        {"commodity": "co2", "factor": "0.056 t/GJ_fuel"}
                    ],
                    "stock_characterization": "res_gas_heater_default",
                },
                {
                    "id": "heat_pump",
                    "provides": "space_heat",
                    "inputs": [{"commodity": "electricity"}],
                    "performance": {"kind": "cop", "value": 3.2},
                },
                {
                    "id": "gas_boiler",
                    "provides": "steam",
                    "inputs": [{"commodity": "natural_gas", "basis": "HHV"}],
                    "performance": {"kind": "efficiency", "value": 0.85},
                    "emissions": [
                        {"commodity": "co2", "factor": "0.056 t/GJ_fuel"}
                    ],
                },
                {
                    "id": "electric_boiler",
                    "provides": "steam",
                    "inputs": [{"commodity": "electricity"}],
                    "performance": {"kind": "efficiency", "value": 0.98},
                },
            ],
            "technology_roles": [
                {
                    "id": "residential_space_heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["gas_heater", "heat_pump"],
                    "transitions": [
                        {
                            "from": "gas_heater",
                            "to": "heat_pump",
                            "kind": "retrofit",
                            "cost": "25 AUD2024/kW",
                        }
                    ],
                },
                {
                    "id": "industrial_steam_supply",
                    "primary_service": "steam",
                    "technologies": ["gas_boiler", "electric_boiler"],
                    "transitions": [
                        {
                            "from": "gas_boiler",
                            "to": "electric_boiler",
                            "kind": "retrofit",
                            "cost": "70 AUD2024/kW",
                        }
                    ],
                },
            ],
            "stock_characterizations": [
                {
                    "id": "res_gas_heater_default",
                    "applies_to": ["gas_heater"],
                    "counted_asset_label": "heater_system",
                    "conversions": [
                        {
                            "from_metric": "asset_count",
                            "to_metric": "installed_capacity",
                            "factor": "8 kWth/assets",
                        },
                        {
                            "from_metric": "asset_count",
                            "to_metric": "annual_activity",
                            "factor": "10 MWh_heat/assets/year",
                        },
                    ],
                }
            ],
        }
    )
    model = parse_source(
        {
            "dsl_version": "0.3",
            "imports": [
                {
                    "package": "vedalang.au.regions@1",
                    "as": "regions",
                    "only": {"region_partitions": ["toy_states_3"]},
                },
                {
                    "package": "vedalang.au.demography@1",
                    "as": "demo",
                    "only": {
                        "spatial_measure_sets": ["abs_demography"],
                        "temporal_index_series": ["national_dwelling_stock_index"],
                    },
                },
                {
                    "package": "vedalang.std.heat@1",
                    "as": "heat",
                    "only": {
                        "technology_roles": [
                            "residential_space_heat_supply",
                            "industrial_steam_supply",
                        ],
                        "technologies": [
                            "gas_heater",
                            "heat_pump",
                            "gas_boiler",
                            "electric_boiler",
                        ],
                        "stock_characterizations": ["res_gas_heater_default"],
                    },
                },
            ],
            "sites": [
                {
                    "id": "gladstone_refinery",
                    "location": {"point": {"lat": -23.842, "lon": 151.248}},
                }
            ],
            "facilities": [
                {
                    "id": "gladstone_steam",
                    "site": "gladstone_refinery",
                    "technology_role": "heat.industrial_steam_supply",
                    "available_technologies": [
                        "heat.gas_boiler",
                        "heat.electric_boiler",
                    ],
                    "stock": {
                        "adjust_to_base_year": {
                            "using": {"kind": "annual_growth", "rate": "0.5 %/year"}
                        },
                        "items": [
                            {
                                "technology": "heat.gas_boiler",
                                "metric": "installed_capacity",
                                "observed": {"value": "600 MWth", "year": 2023},
                            }
                        ],
                    },
                }
            ],
            "fleets": [
                {
                    "id": "residential_space_heat",
                    "technology_role": "heat.residential_space_heat_supply",
                    "stock": {
                        "adjust_to_base_year": {
                            "using": "demo.national_dwelling_stock_index",
                            "elasticity": 1.0,
                        },
                        "items": [
                            {
                                "technology": "heat.gas_heater",
                                "metric": "asset_count",
                                "observed": {"value": "1200000 assets", "year": 2023},
                            }
                        ],
                    },
                    "distribution": {
                        "method": "proportional",
                        "weight_by": "demo.abs_demography.dwelling_stock",
                    },
                }
            ],
            "runs": [
                {
                    "id": "toy_states_2025",
                    "base_year": 2025,
                    "currency_year": 2024,
                    "region_partition": "regions.toy_states_3",
                }
            ],
        }
    )
    return {
        "vedalang.au.regions@1": regions,
        "vedalang.au.demography@1": demo,
        "vedalang.std.heat@1": heat,
    }, model


def test_section16_worked_example_matches_normative_stock_rollup():
    packages, model = _section16_packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")

    artifacts = build_run_artifacts(
        graph,
        run,
        site_region_memberships={"gladstone_refinery": "QLD"},
        measure_weights={
            "demo.abs_demography.dwelling_stock": {
                "NSW": 0.40,
                "VIC": 0.35,
                "QLD": 0.25,
            }
        },
    )

    csir_by_id = {
        item["id"]: item for item in artifacts.csir["technology_role_instances"]
    }
    assert round(
        csir_by_id["role_instance.gladstone_steam@QLD"]["initial_stock"][0]["stock_views"]["installed_capacity"]["amount"],
        1,
    ) == 606.0
    assert round(
        csir_by_id["role_instance.residential_space_heat@NSW"]["initial_stock"][0]["stock_views"]["installed_capacity"]["amount"],
        1,
    ) == 3993600.0
    assert round(
        csir_by_id["role_instance.residential_space_heat@VIC"]["initial_stock"][0]["stock_views"]["annual_activity"]["amount"],
        3,
    ) == 4368000.0
    assert round(
        csir_by_id["role_instance.residential_space_heat@QLD"]["initial_stock"][0]["stock_views"]["asset_count"]["amount"],
        0,
    ) == 312000.0

    assert len(artifacts.cpir["processes"]) == 8
    assert len(artifacts.cpir["transitions"]) == 4


def test_section16_artifacts_are_byte_stable():
    packages, model = _section16_packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    kwargs = {
        "site_region_memberships": {"gladstone_refinery": "QLD"},
        "measure_weights": {
            "demo.abs_demography.dwelling_stock": {
                "NSW": 0.40,
                "VIC": 0.35,
                "QLD": 0.25,
            }
        },
    }
    first = build_run_artifacts(graph, run, **kwargs)
    second = build_run_artifacts(graph, run, **kwargs)

    assert json.dumps(first.csir, sort_keys=True) == json.dumps(
        second.csir,
        sort_keys=True,
    )
    assert json.dumps(first.cpir, sort_keys=True) == json.dumps(
        second.cpir,
        sort_keys=True,
    )
    assert json.dumps(first.explain, sort_keys=True) == json.dumps(
        second.explain,
        sort_keys=True,
    )
