from vedalang.compiler import V0_2Source, parse_v0_2_source


def valid_v0_2_source() -> dict:
    return {
        "dsl_version": "0.2",
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
            {"id": "primary:natural_gas", "kind": "primary"},
            {"id": "secondary:electricity", "kind": "secondary"},
            {"id": "service:space_heat", "kind": "service"},
        ],
        "technologies": [
            {
                "id": "heat.gas_heater",
                "provides": "service:space_heat",
                "inputs": [
                    {
                        "commodity": "primary:natural_gas",
                        "basis": "HHV",
                    }
                ],
                "performance": {"kind": "efficiency", "value": 0.9},
            }
        ],
        "technology_roles": [
            {
                "id": "heat.residential_space_heat_supply",
                "primary_service": "service:space_heat",
                "technologies": ["heat.gas_heater"],
                "transitions": [
                    {
                        "from": "heat.gas_heater",
                        "to": "heat.gas_heater",
                        "kind": "retrofit",
                    }
                ],
            }
        ],
        "stock_characterizations": [
            {
                "id": "heat.res_gas_heater_default",
                "applies_to": ["heat.gas_heater"],
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
                "id": "geo.sa2_2021",
                "kind": "polygon",
                "key": "sa2_code",
                "geometry_file": "data/sa2_2021.geojson",
            }
        ],
        "spatial_measure_sets": [
            {
                "id": "demo.abs_demography",
                "layer": "geo.sa2_2021",
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
                "id": "demo.national_dwelling_stock_index",
                "unit": "index",
                "values": {"2023": 1.0, "2025": 1.04},
            }
        ],
        "region_partitions": [
            {
                "id": "regions.toy_states_3",
                "layer": "geo.sa2_2021",
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
                "id": "regions.aemo_rez_2024",
                "layer": "geo.sa2_2021",
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
                "technology_role": "heat.residential_space_heat_supply",
                "stock": {
                    "items": [
                        {
                            "technology": "heat.gas_heater",
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
                "technology_role": "heat.residential_space_heat_supply",
                "distribution": {
                    "method": "proportional",
                    "weight_by": "demo.abs_demography.dwelling_stock",
                },
            }
        ],
        "opportunities": [
            {
                "id": "qld_central_rez_wind_class_1",
                "technology": "heat.gas_heater",
                "siting": {
                    "region_member": {
                        "partition": "regions.toy_states_3",
                        "member": "QLD",
                    }
                },
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
                        "commodity": "secondary:electricity",
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


def test_parse_v0_2_source_returns_typed_document() -> None:
    ast = parse_v0_2_source(valid_v0_2_source())

    assert isinstance(ast, V0_2Source)
    assert ast.dsl_version == "0.2"
    assert ast.imports[0].alias == "heat"
    assert ast.commodities[0].id == "primary:natural_gas"
    assert ast.technologies[0].performance.kind == "efficiency"
    assert ast.technology_roles[0].transitions[0].kind == "retrofit"
    assert (
        ast.stock_characterizations[0].conversions[0].to_metric
        == "installed_capacity"
    )
    assert ast.sites[0].location.point == {"lat": -23.842, "lon": 151.248}
    assert ast.facilities[0].stock.items[0].metric == "installed_capacity"
    assert ast.fleets[0].distribution.weight_by == "demo.abs_demography.dwelling_stock"
    assert ast.opportunities[0].siting.region_member == {
        "partition": "regions.toy_states_3",
        "member": "QLD",
    }
    assert ast.networks[0].links[0].from_node == "QLD"
    assert ast.runs[0].region_partition == "regions.toy_states_3"


def test_parse_v0_2_source_keeps_structural_source_paths() -> None:
    ast = parse_v0_2_source(valid_v0_2_source())

    assert ast.imports[0].source_ref.path == "imports[0]"
    assert ast.technologies[0].inputs[0].source_ref.path == "technologies[0].inputs[0]"
    assert (
        ast.facilities[0].stock.items[0].source_ref.path
        == "facilities[0].stock.items[0]"
    )
    assert ast.fleets[0].distribution.source_ref.path == "fleets[0].distribution"
    assert ast.networks[0].links[0].source_ref.path == "networks[0].links[0]"
