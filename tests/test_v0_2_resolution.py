import pytest

from vedalang.compiler import parse_v0_2_source
from vedalang.compiler.v0_2_resolution import (
    V0_2ResolutionError,
    allocate_fleet_stock,
    resolve_asset_stock,
    resolve_imports,
    resolve_opportunities,
    resolve_run,
    resolve_sites,
)


def _packages_and_model():
    regions = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "spatial_layers": [
                {
                    "id": "geo_regions.sa2_2021",
                    "kind": "polygon",
                    "key": "sa2_code",
                    "geometry_file": "data/sa2.geojson",
                }
            ],
            "region_partitions": [
                {
                    "id": "toy_states_3",
                    "layer": "geo_regions.sa2_2021",
                    "members": ["NSW", "VIC", "QLD"],
                    "mapping": {
                        "kind": "file",
                        "file": "data/sa2_to_state.csv",
                        "source_key": "sa2_code",
                        "target_key": "state_id",
                    },
                }
            ],
            "zone_overlays": [
                {
                    "id": "aemo_rez_2024",
                    "layer": "geo_regions.sa2_2021",
                    "key": "rez_id",
                    "geometry_file": "data/rez.geojson",
                }
            ],
        }
    )
    demo = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "spatial_layers": [
                {
                    "id": "geo_demo.sa2_2021",
                    "kind": "polygon",
                    "key": "sa2_code",
                    "geometry_file": "data/sa2.geojson",
                }
            ],
            "spatial_measure_sets": [
                {
                    "id": "abs_demography",
                    "layer": "geo_demo.sa2_2021",
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
                    "values": {"2023": 1.0, "2025": 1.04},
                }
            ],
        }
    )
    heat = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "commodities": [
                {"id": "primary:natural_gas", "kind": "primary"},
                {"id": "secondary:electricity", "kind": "secondary"},
                {"id": "service:space_heat", "kind": "service"},
            ],
            "technologies": [
                {
                    "id": "gas_heater",
                    "provides": "service:space_heat",
                    "inputs": [{"commodity": "primary:natural_gas", "basis": "HHV"}],
                    "performance": {"kind": "efficiency", "value": 0.9},
                    "stock_characterization": "res_gas_heater_default",
                },
                {
                    "id": "heat_pump",
                    "provides": "service:space_heat",
                    "inputs": [{"commodity": "secondary:electricity"}],
                    "performance": {"kind": "cop", "value": 3.2},
                },
            ],
            "technology_roles": [
                {
                    "id": "residential_space_heat_supply",
                    "primary_service": "service:space_heat",
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
                    "id": "res_gas_heater_default",
                    "applies_to": ["gas_heater"],
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
    model = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {
                    "package": "vedalang.au.regions@1",
                    "as": "regions",
                    "only": {
                        "region_partitions": ["toy_states_3"],
                        "zone_overlays": ["aemo_rez_2024"],
                    },
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
                    "only": {"technology_roles": ["residential_space_heat_supply"]},
                },
            ],
            "sites": [
                {
                    "id": "gladstone_refinery",
                    "location": {"point": {"lat": -23.842, "lon": 151.248}},
                },
                {
                    "id": "manual_override_site",
                    "location": {"point": {"lat": -33.9, "lon": 151.2}},
                    "membership_overrides": {
                        "region_partitions": {"regions.toy_states_3": "VIC"}
                    },
                },
            ],
            "facilities": [
                {
                    "id": "gladstone_steam",
                    "site": "gladstone_refinery",
                    "technology_role": "heat.residential_space_heat_supply",
                    "available_technologies": ["heat.gas_heater", "heat.heat_pump"],
                    "stock": {
                        "adjust_to_base_year": {
                            "using": {"kind": "annual_growth", "rate": "0.5 %/year"}
                        },
                        "items": [
                            {
                                "technology": "heat.gas_heater",
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
            "opportunities": [
                {
                    "id": "qld_central_rez_heat",
                    "technology": "heat.heat_pump",
                    "siting": {"zone": "regions.aemo_rez_2024.qld_central_rez"},
                    "max_new_capacity": "1500 MW",
                }
            ],
            "networks": [
                {
                    "id": "east_coast_transmission",
                    "kind": "transmission",
                    "node_basis": {
                        "kind": "region_partition",
                        "ref": "regions.toy_states_3",
                    },
                    "links": [
                        {
                            "id": "qld_nsw",
                            "from": "QLD",
                            "to": "NSW",
                            "commodity": "heat.secondary:electricity",
                        }
                    ],
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
    packages = {
        "vedalang.au.regions@1": regions,
        "vedalang.au.demography@1": demo,
        "vedalang.std.heat@1": heat,
    }
    return packages, model


def test_resolve_imports_qualifies_aliases_and_dependency_closure():
    packages, model = _packages_and_model()

    graph = resolve_imports(model, packages)

    assert "heat.residential_space_heat_supply" in graph.technology_roles
    assert "heat.gas_heater" in graph.technologies
    assert "heat.heat_pump" in graph.technologies
    assert "heat.service:space_heat" in graph.commodities
    assert "heat.res_gas_heater_default" in graph.stock_characterizations
    assert "demo.abs_demography" in graph.spatial_measure_sets
    assert "demo.geo_demo.sa2_2021" in graph.spatial_layers
    assert "regions.toy_states_3" in graph.region_partitions


def test_resolve_imports_detects_missing_object_and_cycle():
    packages, model = _packages_and_model()
    broken = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {
                    "package": "vedalang.std.heat@1",
                    "as": "heat",
                    "only": {"technology_roles": ["missing_role"]},
                }
            ],
        }
    )
    with pytest.raises(V0_2ResolutionError, match="E003"):
        resolve_imports(broken, packages)

    packages["cycle.a@1"] = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {"package": "cycle.b@1", "as": "b", "only": {"commodities": ["x"]}}
            ],
            "commodities": [{"id": "x", "kind": "service"}],
        }
    )
    packages["cycle.b@1"] = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {"package": "cycle.a@1", "as": "a", "only": {"commodities": ["x"]}}
            ],
            "commodities": [{"id": "x", "kind": "service"}],
        }
    )
    cyclical = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {"package": "cycle.a@1", "as": "a", "only": {"commodities": ["x"]}}
            ],
        }
    )
    with pytest.raises(V0_2ResolutionError, match="import cycle detected"):
        resolve_imports(cyclical, packages)

    conflicting = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {
                    "package": "vedalang.std.heat@1",
                    "as": "heat",
                    "only": {"technology_roles": ["residential_space_heat_supply"]},
                },
                {
                    "package": "vedalang.au.demography@1",
                    "as": "demo",
                    "only": {
                        "temporal_index_series": ["national_dwelling_stock_index"]
                    },
                },
            ],
            "technology_roles": [
                {
                    "id": "heat.residential_space_heat_supply",
                    "primary_service": "service:space_heat",
                    "technologies": [],
                }
            ],
        }
    )
    with pytest.raises(V0_2ResolutionError, match="E001"):
        resolve_imports(conflicting, packages)


def test_resolve_run_sites_and_opportunities():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    sites = resolve_sites(
        graph,
        run,
        site_region_memberships={"gladstone_refinery": "QLD"},
        site_zone_memberships={
            "gladstone_refinery": {"regions.aemo_rez_2024": "qld_central_rez"}
        },
    )
    opportunities = resolve_opportunities(graph, run, sites)

    assert run.model_regions == ("NSW", "VIC", "QLD")
    assert sites["gladstone_refinery"].model_region == "QLD"
    assert sites["manual_override_site"].model_region == "VIC"
    assert opportunities["qld_central_rez_heat"].model_region == "QLD"

    with pytest.raises(V0_2ResolutionError, match="E008"):
        resolve_sites(
            graph,
            run,
            site_region_memberships={"gladstone_refinery": ["NSW", "QLD"]},
        )


def test_adjust_stock_and_allocate_fleet_derives_stock_views():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    fleet = graph.fleets["residential_space_heat"]

    adjusted = resolve_asset_stock(fleet, graph=graph, run=run)
    assert adjusted[0].adjusted.value == pytest.approx(1_248_000.0)

    allocations = allocate_fleet_stock(
        graph,
        run,
        fleet,
        adjusted,
        measure_weights={
            "demo.abs_demography.dwelling_stock": {
                "NSW": 0.40,
                "VIC": 0.35,
                "QLD": 0.25,
            }
        },
    )
    by_region = {allocation.model_region: allocation for allocation in allocations}

    assert by_region["NSW"].initial_stock[0].adjusted.value == pytest.approx(499_200.0)
    assert by_region["NSW"].derived_stock_views["heat.gas_heater"][
        "installed_capacity"
    ].value == pytest.approx(3_993_600.0)
    assert by_region["QLD"].derived_stock_views["heat.gas_heater"][
        "annual_activity"
    ].value == pytest.approx(3_120_000.0)


def test_adjust_stock_requires_rule_when_year_differs():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    broken_fleet = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {
                    "package": "vedalang.std.heat@1",
                    "as": "heat",
                    "only": {"technology_roles": ["residential_space_heat_supply"]},
                }
            ],
            "fleets": [
                {
                    "id": "broken",
                    "technology_role": "heat.residential_space_heat_supply",
                    "stock": {
                        "items": [
                            {
                                "technology": "heat.gas_heater",
                                "metric": "asset_count",
                                "observed": {"value": "10 assets", "year": 2023},
                            }
                        ]
                    },
                    "distribution": {
                        "method": "custom",
                        "custom_weights_file": "w.csv",
                    },
                }
            ],
        }
    )
    broken_graph = resolve_imports(broken_fleet, packages)

    with pytest.raises(V0_2ResolutionError, match="E011"):
        resolve_asset_stock(broken_graph.fleets["broken"], graph=broken_graph, run=run)


def test_item_level_adjustment_overrides_stock_block_rule():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    facility = parse_v0_2_source(
        {
            "dsl_version": "0.2",
            "imports": [
                {
                    "package": "vedalang.std.heat@1",
                    "as": "heat",
                    "only": {"technology_roles": ["residential_space_heat_supply"]},
                },
                {
                    "package": "vedalang.au.demography@1",
                    "as": "demo",
                    "only": {
                        "temporal_index_series": ["national_dwelling_stock_index"]
                    },
                },
            ],
            "facilities": [
                {
                    "id": "override_demo",
                    "site": "gladstone_refinery",
                    "technology_role": "heat.residential_space_heat_supply",
                    "stock": {
                        "adjust_to_base_year": {
                            "using": {"kind": "annual_growth", "rate": "0.5 %/year"}
                        },
                        "items": [
                            {
                                "technology": "heat.gas_heater",
                                "metric": "asset_count",
                                "observed": {"value": "100 assets", "year": 2023},
                                "adjust_to_base_year": {
                                    "using": "demo.national_dwelling_stock_index"
                                },
                            }
                        ],
                    },
                }
            ],
        }
    )
    override_graph = resolve_imports(facility, packages)

    adjusted = resolve_asset_stock(
        override_graph.facilities["override_demo"],
        graph=override_graph,
        run=run,
    )

    assert adjusted[0].adjusted.value == pytest.approx(104.0)


def test_allocate_fleet_requires_weights_and_stock_characterization():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    fleet = graph.fleets["residential_space_heat"]
    adjusted = resolve_asset_stock(fleet, graph=graph, run=run)

    with pytest.raises(V0_2ResolutionError, match="E009"):
        allocate_fleet_stock(graph, run, fleet, adjusted, measure_weights={})

    with pytest.raises(V0_2ResolutionError, match="E010"):
        allocate_fleet_stock(
            graph,
            run,
            fleet,
            adjusted,
            measure_weights={
                "demo.abs_demography.dwelling_stock": {
                    "NSW": 0.0,
                    "VIC": 0.0,
                    "QLD": 0.0,
                }
            },
        )

    graph_without_stock_char = graph.__class__(
        **{**graph.__dict__, "stock_characterizations": {}}
    )
    with pytest.raises(V0_2ResolutionError, match="E012"):
        allocate_fleet_stock(
            graph_without_stock_char,
            run,
            fleet,
            adjusted,
            measure_weights={
                "demo.abs_demography.dwelling_stock": {
                    "NSW": 0.40,
                    "VIC": 0.35,
                    "QLD": 0.25,
                }
            },
        )
