import pytest

from vedalang.compiler import parse_source
from vedalang.compiler.resolution import (
    ResolutionError,
    allocate_fleet_stock,
    resolve_asset_stock,
    resolve_imports,
    resolve_run,
    resolve_sites,
    resolve_zone_opportunities,
)


def _packages_and_model():
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
            "zone_overlays": [
                {
                    "id": "aemo_rez_2024",
                    "layer": "geo_regions_sa2_2021",
                    "key": "rez_id",
                    "geometry_file": "data/rez.geojson",
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
                    "values": {"2023": 1.0, "2025": 1.04},
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
            ],
            "technologies": [
                {
                    "id": "gas_heater",
                    "provides": "space_heat",
                    "inputs": [{"commodity": "natural_gas", "basis": "HHV"}],
                    "performance": {"kind": "efficiency", "value": 0.9},
                    "stock_characterization": "res_gas_heater_default",
                },
                {
                    "id": "heat_pump",
                    "provides": "space_heat",
                    "inputs": [{"commodity": "electricity"}],
                    "performance": {"kind": "cop", "value": 3.2},
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
    model = parse_source(
        {
            "dsl_version": "0.3",
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
            "zone_opportunities": [
                {
                    "id": "qld_central_rez_heat",
                    "technology_role": "heat.residential_space_heat_supply",
                    "technology": "heat.heat_pump",
                    "zone": "regions.aemo_rez_2024.qld_central_rez",
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
                            "commodity": "heat.electricity",
                        }
                    ],
                }
            ],
            "runs": [
                {
                    "id": "toy_states_2025",
                    "veda_book_name": "TOYSTATES2025",

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
    assert "heat.space_heat" in graph.commodities
    assert "heat.res_gas_heater_default" in graph.stock_characterizations
    assert "demo.abs_demography" in graph.spatial_measure_sets
    assert "demo.geo_demo_sa2_2021" in graph.spatial_layers
    assert "regions.toy_states_3" in graph.region_partitions


def test_resolve_imports_detects_missing_object_and_cycle():
    packages, model = _packages_and_model()
    broken = parse_source(
        {
            "dsl_version": "0.3",
            "imports": [
                {
                    "package": "vedalang.std.heat@1",
                    "as": "heat",
                    "only": {"technology_roles": ["missing_role"]},
                }
            ],
        }
    )
    with pytest.raises(ResolutionError, match="E003"):
        resolve_imports(broken, packages)

    packages["cycle.a@1"] = parse_source(
        {
            "dsl_version": "0.3",
            "imports": [
                {"package": "cycle.b@1", "as": "b", "only": {"commodities": ["x"]}}
            ],
            "commodities": [{"id": "x", "type": "service"}],
        }
    )
    packages["cycle.b@1"] = parse_source(
        {
            "dsl_version": "0.3",
            "imports": [
                {"package": "cycle.a@1", "as": "a", "only": {"commodities": ["x"]}}
            ],
            "commodities": [{"id": "x", "type": "service"}],
        }
    )
    cyclical = parse_source(
        {
            "dsl_version": "0.3",
            "imports": [
                {"package": "cycle.a@1", "as": "a", "only": {"commodities": ["x"]}}
            ],
        }
    )
    with pytest.raises(ResolutionError, match="import cycle detected"):
        resolve_imports(cyclical, packages)

    conflicting = parse_source(
        {
            "dsl_version": "0.3",
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
                    "primary_service": "space_heat",
                    "technologies": [],
                }
            ],
        }
    )
    with pytest.raises(ResolutionError, match="E001"):
        resolve_imports(conflicting, packages)


def test_resolve_run_sites_and_zone_opportunities():
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
    opportunities = resolve_zone_opportunities(graph, run, sites)

    assert run.model_regions == ("NSW", "VIC", "QLD")
    assert sites["gladstone_refinery"].model_region == "QLD"
    assert sites["manual_override_site"].model_region == "VIC"
    assert opportunities["qld_central_rez_heat"].model_region == "QLD"
    assert opportunities["qld_central_rez_heat"].technology_role == (
        "heat.residential_space_heat_supply"
    )

    with pytest.raises(ResolutionError, match="E008"):
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
    broken_fleet = parse_source(
        {
            "dsl_version": "0.3",
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

    with pytest.raises(ResolutionError, match="E011"):
        resolve_asset_stock(broken_graph.fleets["broken"], graph=broken_graph, run=run)


def test_item_level_adjustment_overrides_stock_block_rule():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    facility = parse_source(
        {
            "dsl_version": "0.3",
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

    with pytest.raises(ResolutionError, match="E009"):
        allocate_fleet_stock(graph, run, fleet, adjusted, measure_weights={})

    with pytest.raises(ResolutionError, match="E010"):
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
    with pytest.raises(ResolutionError, match="E012"):
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


def test_resolve_run_fails_for_unknown_policy_references():
    source = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "co2", "type": "emission"},
                {"id": "space_heat", "type": "service"},
            ],
            "technologies": [
                {
                    "id": "heater",
                    "provides": "space_heat",
                    "emissions": [{"commodity": "co2", "factor": "0.1 t/GJ"}],
                }
            ],
            "technology_roles": [
                {
                    "id": "heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heater"],
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
                    "id": "single_region",
                    "layer": "geo_demo",
                    "members": ["SINGLE"],
                    "mapping": {"kind": "constant", "value": "SINGLE"},
                }
            ],
            "sites": [
                {
                    "id": "site_a",
                    "location": {"point": {"lat": -27.0, "lon": 153.0}},
                }
            ],
            "facilities": [
                {
                    "id": "fac_a",
                    "site": "site_a",
                    "technology_role": "heat_supply",
                    "policies": ["missing_policy"],
                    "description": "Facility policy reference fixture.",
                }
            ],
            "runs": [
                {
                    "id": "single_2025",
                    "veda_book_name": "SINGLE2025",

                    "base_year": 2025,

                    "currency_year": 2024,

                    "region_partition": "single_region",
                    "enable_policies": ["missing_policy"],
                }
            ],
        }
    )
    graph = resolve_imports(source, {})

    with pytest.raises(ResolutionError, match="E027"):
        resolve_run(graph, "single_2025")


def test_resolve_run_fails_when_emissions_budget_targets_non_emission_commodity():
    source = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "electricity", "type": "energy", "energy_form": "secondary"},
                {"id": "space_heat", "type": "service"},
            ],
            "technologies": [
                {
                    "id": "heater",
                    "provides": "space_heat",
                    "inputs": [{"commodity": "electricity"}],
                }
            ],
            "technology_roles": [
                {
                    "id": "heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heater"],
                }
            ],
            "policies": [
                {
                    "id": "co2_cap",
                    "kind": "emissions_budget",
                    "emission_commodity": "electricity",
                    "budgets": [{"year": 2025, "value": "1 Mt"}],
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
                    "id": "single_region",
                    "layer": "geo_demo",
                    "members": ["SINGLE"],
                    "mapping": {"kind": "constant", "value": "SINGLE"},
                }
            ],
            "runs": [
                {
                    "id": "single_2025",
                    "veda_book_name": "SINGLE2025",

                    "base_year": 2025,

                    "currency_year": 2024,

                    "region_partition": "single_region",
                    "enable_policies": ["co2_cap"],
                }
            ],
        }
    )
    graph = resolve_imports(source, {})

    with pytest.raises(ResolutionError, match="E028"):
        resolve_run(graph, "single_2025")


def test_resolve_run_fails_on_duplicate_policy_budget_years():
    source = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "co2", "type": "emission"},
                {"id": "space_heat", "type": "service"},
            ],
            "technologies": [
                {
                    "id": "heater",
                    "provides": "space_heat",
                    "emissions": [{"commodity": "co2", "factor": "0.1 t/GJ"}],
                }
            ],
            "technology_roles": [
                {
                    "id": "heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heater"],
                }
            ],
            "policies": [
                {
                    "id": "co2_cap",
                    "kind": "emissions_budget",
                    "emission_commodity": "co2",
                    "budgets": [
                        {"year": 2025, "value": "1 Mt"},
                        {"year": 2025, "value": "0.8 Mt"},
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
                    "id": "single_region",
                    "layer": "geo_demo",
                    "members": ["SINGLE"],
                    "mapping": {"kind": "constant", "value": "SINGLE"},
                }
            ],
            "runs": [
                {
                    "id": "single_2025",
                    "veda_book_name": "SINGLE2025",

                    "base_year": 2025,

                    "currency_year": 2024,

                    "region_partition": "single_region",
                    "enable_policies": ["co2_cap"],
                }
            ],
        }
    )
    graph = resolve_imports(source, {})

    with pytest.raises(ResolutionError, match="E030"):
        resolve_run(graph, "single_2025")


def test_resolve_run_fails_when_multiple_cases_selected_for_policy():
    source = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "co2", "type": "emission"},
                {"id": "space_heat", "type": "service"},
            ],
            "technologies": [
                {
                    "id": "heater",
                    "provides": "space_heat",
                    "emissions": [{"commodity": "co2", "factor": "0.1 t/GJ"}],
                }
            ],
            "technology_roles": [
                {
                    "id": "heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heater"],
                }
            ],
            "policies": [
                {
                    "id": "co2_cap",
                    "kind": "emissions_budget",
                    "emission_commodity": "co2",
                    "cases": [
                        {
                            "id": "cap_a",
                            "budgets": [{"year": 2025, "value": "1 Mt"}],
                        },
                        {
                            "id": "cap_b",
                            "budgets": [{"year": 2025, "value": "0.8 Mt"}],
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
                    "id": "single_region",
                    "layer": "geo_demo",
                    "members": ["SINGLE"],
                    "mapping": {"kind": "constant", "value": "SINGLE"},
                }
            ],
            "runs": [
                {
                    "id": "single_2025",
                    "veda_book_name": "SINGLE2025",

                    "base_year": 2025,

                    "currency_year": 2024,

                    "region_partition": "single_region",
                    "enable_policies": ["co2_cap"],
                    "include_cases": ["cap_a", "cap_b"],
                }
            ],
        }
    )
    graph = resolve_imports(source, {})

    with pytest.raises(ResolutionError, match="E029"):
        resolve_run(graph, "single_2025")


def test_resolve_run_fails_when_case_based_policy_not_selected():
    source = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "co2", "type": "emission"},
                {"id": "space_heat", "type": "service"},
            ],
            "technologies": [
                {
                    "id": "heater",
                    "provides": "space_heat",
                    "emissions": [{"commodity": "co2", "factor": "0.1 t/GJ"}],
                }
            ],
            "technology_roles": [
                {
                    "id": "heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heater"],
                }
            ],
            "policies": [
                {
                    "id": "co2_cap",
                    "kind": "emissions_budget",
                    "emission_commodity": "co2",
                    "cases": [
                        {
                            "id": "cap_a",
                            "budgets": [{"year": 2025, "value": "1 Mt"}],
                        }
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
                    "id": "single_region",
                    "layer": "geo_demo",
                    "members": ["SINGLE"],
                    "mapping": {"kind": "constant", "value": "SINGLE"},
                }
            ],
            "runs": [
                {
                    "id": "single_2025",
                    "veda_book_name": "SINGLE2025",

                    "base_year": 2025,

                    "currency_year": 2024,

                    "region_partition": "single_region",
                    "enable_policies": ["co2_cap"],
                    "include_cases": ["dem_base"],
                }
            ],
        }
    )
    graph = resolve_imports(source, {})

    with pytest.raises(ResolutionError, match="E031"):
        resolve_run(graph, "single_2025")


def test_resolve_run_fails_on_duplicate_policy_case_ids():
    source = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "co2", "type": "emission"},
                {"id": "space_heat", "type": "service"},
            ],
            "technologies": [
                {
                    "id": "heater",
                    "provides": "space_heat",
                    "emissions": [{"commodity": "co2", "factor": "0.1 t/GJ"}],
                }
            ],
            "technology_roles": [
                {
                    "id": "heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heater"],
                }
            ],
            "policies": [
                {
                    "id": "co2_cap",
                    "kind": "emissions_budget",
                    "emission_commodity": "co2",
                    "cases": [
                        {
                            "id": "cap_a",
                            "budgets": [{"year": 2025, "value": "1 Mt"}],
                        },
                        {
                            "id": "cap_a",
                            "budgets": [{"year": 2030, "value": "0.8 Mt"}],
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
                    "id": "single_region",
                    "layer": "geo_demo",
                    "members": ["SINGLE"],
                    "mapping": {"kind": "constant", "value": "SINGLE"},
                }
            ],
            "runs": [
                {
                    "id": "single_2025",
                    "veda_book_name": "SINGLE2025",

                    "base_year": 2025,

                    "currency_year": 2024,

                    "region_partition": "single_region",
                    "enable_policies": ["co2_cap"],
                    "include_cases": ["cap_a"],
                }
            ],
        }
    )
    graph = resolve_imports(source, {})

    with pytest.raises(ResolutionError, match="E032"):
        resolve_run(graph, "single_2025")


def test_allocate_direct_fleet_defaults_to_single_region_and_copies_stock():
    source = parse_source(
        {
            "dsl_version": "0.3",
            "commodities": [
                {"id": "electricity", "type": "energy", "energy_form": "secondary"},
                {"id": "space_heat", "type": "service"},
            ],
            "technologies": [
                {
                    "id": "heat_pump",
                    "provides": "space_heat",
                    "inputs": [{"commodity": "electricity"}],
                    "performance": {"kind": "cop", "value": 3.0},
                }
            ],
            "technology_roles": [
                {
                    "id": "space_heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heat_pump"],
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
                    "id": "single_region",
                    "layer": "geo_demo",
                    "members": ["QLD"],
                    "mapping": {"kind": "constant", "value": "QLD"},
                }
            ],
            "fleets": [
                {
                    "id": "residential_heat",
                    "technology_role": "space_heat_supply",
                    "stock": {
                        "items": [
                            {
                                "technology": "heat_pump",
                                "metric": "installed_capacity",
                                "observed": {"value": "10 MW", "year": 2025},
                            }
                        ]
                    },
                    "distribution": {"method": "direct"},
                }
            ],
            "runs": [
                {
                    "id": "single_2025",
                    "veda_book_name": "SINGLE2025",

                    "base_year": 2025,

                    "currency_year": 2024,

                    "region_partition": "single_region",
                }
            ],
        }
    )
    graph = resolve_imports(source, {})
    run = resolve_run(graph, "single_2025")
    fleet = graph.fleets["residential_heat"]
    adjusted = resolve_asset_stock(fleet, graph=graph, run=run)

    allocations = allocate_fleet_stock(graph, run, fleet, adjusted)

    assert len(allocations) == 1
    assert allocations[0].model_region == "QLD"
    assert allocations[0].initial_stock[0].adjusted.value == pytest.approx(10.0)


def test_allocate_direct_fleet_requires_targets_for_multi_region_run():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    direct_fleet = parse_source(
        {
            "dsl_version": "0.3",
            "imports": [
                {
                    "package": "vedalang.std.heat@1",
                    "as": "heat",
                    "only": {"technology_roles": ["residential_space_heat_supply"]},
                }
            ],
            "fleets": [
                {
                    "id": "residential_space_heat",
                    "technology_role": "heat.residential_space_heat_supply",
                    "stock": {
                        "items": [
                            {
                                "technology": "heat.gas_heater",
                                "metric": "asset_count",
                                "observed": {"value": "100 assets", "year": 2025},
                            }
                        ]
                    },
                    "distribution": {"method": "direct"},
                }
            ],
        }
    )
    broken_graph = resolve_imports(direct_fleet, packages)
    fleet = broken_graph.fleets["residential_space_heat"]
    adjusted = resolve_asset_stock(fleet, graph=broken_graph, run=run)

    with pytest.raises(ResolutionError, match="E020"):
        allocate_fleet_stock(broken_graph, run, fleet, adjusted)
