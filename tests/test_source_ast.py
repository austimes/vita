from vedalang.compiler import SourceDocument, parse_source


def valid_public_source() -> dict:
    return {
        "dsl_version": "0.3",
        "imports": [
            {
                "package": "vedalang.std.heat@1",
                "as": "heat",
                "only": {
                    "technology_roles": ["residential_space_heat_supply"],
                    "technologies": ["gas_heater", "heat_pump"],
                },
            }
        ],
        "commodities": [
            {"id": "natural_gas", "type": "energy", "energy_form": "primary"},
            {"id": "electricity", "type": "energy", "energy_form": "secondary"},
            {"id": "space_heat", "type": "service"},
            {"id": "co2", "type": "emission"},
        ],
        "technologies": [
            {
                "id": "heat_gas_heater",
                "provides": "space_heat",
                "inputs": [
                    {
                        "commodity": "natural_gas",
                        "basis": "HHV",
                    }
                ],
                "performance": {"kind": "efficiency", "value": 0.9},
            }
        ],
        "technology_roles": [
            {
                "id": "heat_residential_space_heat_supply",
                "primary_service": "space_heat",
                "technologies": ["heat_gas_heater"],
                "transitions": [
                    {
                        "from": "heat_gas_heater",
                        "to": "heat_gas_heater",
                        "kind": "retrofit",
                    }
                ],
            }
        ],
        "stock_characterizations": [
            {
                "id": "heat_res_gas_heater_default",
                "applies_to": ["heat_gas_heater"],
                "conversions": [
                    {
                        "from_metric": "asset_count",
                        "to_metric": "installed_capacity",
                        "factor": "8 kWth/assets",
                    }
                ],
            }
        ],
        "spatial_layers": [
            {
                "id": "geo_sa2_2021",
                "kind": "polygon",
                "key": "sa2_code",
                "geometry_file": "data/sa2_2021.geojson",
            }
        ],
        "spatial_measure_sets": [
            {
                "id": "demo_abs_demography",
                "layer": "geo_sa2_2021",
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
                "id": "demo_national_dwelling_stock_index",
                "unit": "index",
                "values": {"2023": 1.0, "2025": 1.04},
            }
        ],
        "year_sets": [
            {
                "id": "pathway_2025_2035",
                "start_year": 2025,
                "milestone_years": [2025, 2035],
            }
        ],
        "policies": [
            {
                "id": "co2_cap",
                "kind": "emissions_budget",
                "emission_commodity": "co2",
                "cases": [
                    {
                        "id": "co2_cap_case",
                        "budgets": [
                            {"year": 2025, "value": "0.5 Mt"},
                            {"year": 2030, "value": "0.4 Mt"},
                        ],
                    }
                ],
            }
        ],
        "region_partitions": [
            {
                "id": "regions_toy_states_3",
                "layer": "geo_sa2_2021",
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
                "id": "regions_aemo_rez_2024",
                "layer": "geo_sa2_2021",
                "key": "rez_id",
                "geometry_file": "data/rez.geojson",
            }
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
                "technology_role": "heat_residential_space_heat_supply",
                "new_build_limits": [
                    {
                        "technology": "heat_heat_pump",
                        "max_new_capacity": "150 MW",
                    }
                ],
                "stock": {
                    "items": [
                        {
                            "technology": "heat_gas_heater",
                            "metric": "installed_capacity",
                            "observed": {"value": "600 MWth", "year": 2023},
                        }
                    ]
                },
            }
        ],
        "fleets": [
            {
                "id": "residential_space_heat",
                "technology_role": "heat_residential_space_heat_supply",
                "distribution": {
                    "method": "proportional",
                    "weight_by": "demo_abs_demography.dwelling_stock",
                },
            }
        ],
        "zone_opportunities": [
            {
                "id": "qld_central_rez_wind_class_1",
                "technology_role": "heat_residential_space_heat_supply",
                "technology": "heat_gas_heater",
                "zone": "regions_aemo_rez_2024.qld_central_rez",
                "max_new_capacity": "1500 MW",
            }
        ],
        "networks": [
            {
                "id": "east_coast_transmission",
                "kind": "transmission",
                "node_basis": {
                    "kind": "region_partition",
                    "ref": "regions_toy_states_3",
                },
                "links": [
                    {
                        "id": "qld_nsw",
                        "from": "QLD",
                        "to": "NSW",
                        "commodity": "electricity",
                    }
                ],
            }
        ],
        "runs": [
            {
                "id": "toy_states_2025",
                "veda_book_name": "TOYSTATES2025",
                "year_set": "pathway_2025_2035",
                "currency_year": 2024,
                "region_partition": "regions_toy_states_3",
            }
        ],
    }


def test_parse_public_source_returns_typed_document() -> None:
    ast = parse_source(valid_public_source())

    assert isinstance(ast, SourceDocument)
    assert ast.dsl_version == "0.3"
    assert ast.imports[0].alias == "heat"
    assert ast.commodities[0].id == "natural_gas"
    assert ast.technologies[0].performance.kind == "efficiency"
    assert ast.technology_roles[0].transitions[0].kind == "retrofit"
    assert (
        ast.stock_characterizations[0].conversions[0].to_metric
        == "installed_capacity"
    )
    assert ast.sites[0].location.point == {"lat": -23.842, "lon": 151.248}
    assert ast.policies[0].id == "co2_cap"
    assert ast.policies[0].cases[0].id == "co2_cap_case"
    assert ast.policies[0].cases[0].budgets[1].year == 2030
    assert ast.facilities[0].stock.items[0].metric == "installed_capacity"
    assert ast.facilities[0].new_build_limits[0].technology == "heat_heat_pump"
    assert ast.fleets[0].distribution.weight_by == "demo_abs_demography.dwelling_stock"
    assert ast.fleets[0].distribution.target_regions == ()
    assert (
        ast.zone_opportunities[0].technology_role
        == "heat_residential_space_heat_supply"
    )
    assert ast.zone_opportunities[0].zone == "regions_aemo_rez_2024.qld_central_rez"
    assert ast.networks[0].links[0].from_node == "QLD"
    assert ast.year_sets[0].start_year == 2025
    assert ast.runs[0].region_partition == "regions_toy_states_3"


def test_parse_public_source_keeps_structural_source_paths() -> None:
    ast = parse_source(valid_public_source())

    assert ast.imports[0].source_ref.path == "imports[0]"
    assert ast.technologies[0].inputs[0].source_ref.path == "technologies[0].inputs[0]"
    assert (
        ast.facilities[0].stock.items[0].source_ref.path
        == "facilities[0].stock.items[0]"
    )
    assert (
        ast.facilities[0].new_build_limits[0].source_ref.path
        == "facilities[0].new_build_limits[0]"
    )
    assert ast.policies[0].source_ref.path == "policies[0]"
    assert ast.policies[0].cases[0].source_ref.path == "policies[0].cases[0]"
    assert (
        ast.policies[0].cases[0].budgets[1].source_ref.path
        == "policies[0].cases[0].budgets[1]"
    )
    assert ast.fleets[0].distribution.source_ref.path == "fleets[0].distribution"
    assert ast.networks[0].links[0].source_ref.path == "networks[0].links[0]"
