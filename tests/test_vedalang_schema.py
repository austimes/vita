import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = PROJECT_ROOT / "vedalang" / "schema" / "vedalang.schema.json"


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


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
                    "stock_characterizations": ["res_gas_heater_default"],
                },
            }
        ],
        "commodities": [
            {"id": "primary:natural_gas", "kind": "primary"},
            {"id": "secondary:electricity", "kind": "secondary"},
            {"id": "service:space_heat", "kind": "service"},
            {"id": "emission:co2", "kind": "emission"},
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
                "emissions": [
                    {
                        "commodity": "emission:co2",
                        "factor": "0.056 t/GJ",
                    }
                ],
                "investment_cost": "220 AUD2024/kW",
                "lifetime": "25 year",
            },
            {
                "id": "heat.heat_pump",
                "provides": "service:space_heat",
                "inputs": [{"commodity": "secondary:electricity"}],
                "performance": {"kind": "cop", "value": 3.2},
                "investment_cost": "400 AUD2024/kW",
                "lifetime": "15 year",
            },
        ],
        "technology_roles": [
            {
                "id": "heat.residential_space_heat_supply",
                "primary_service": "service:space_heat",
                "technologies": ["heat.gas_heater", "heat.heat_pump"],
                "transitions": [
                    {
                        "from": "heat.gas_heater",
                        "to": "heat.heat_pump",
                        "kind": "retrofit",
                        "cost": "70 AUD2024/kW",
                    }
                ],
            }
        ],
        "stock_characterizations": [
            {
                "id": "heat.res_gas_heater_default",
                "applies_to": ["heat.gas_heater"],
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
                "base_year": 2023,
                "values": {"2023": 1.0, "2024": 1.02, "2025": 1.04},
            }
        ],
        "region_partitions": [
            {
                "id": "regions.toy_states_3",
                "layer": "geo.sa2_2021",
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
                            "observed": {
                                "value": "1200000 assets",
                                "year": 2023,
                            },
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
                "id": "qld_central_rez_wind_class_1",
                "technology": "heat.heat_pump",
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
                "region_partition": "regions.toy_states_3",
            }
        ],
    }


def test_v0_2_source_validates() -> None:
    jsonschema.validate(valid_v0_2_source(), load_schema())


def test_missing_all_object_families_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"dsl_version": "0.2"}, load_schema())


def test_invalid_commodity_kind_rejected() -> None:
    data = valid_v0_2_source()
    data["commodities"][0]["kind"] = "fuel"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_invalid_performance_kind_rejected() -> None:
    data = valid_v0_2_source()
    data["technologies"][0]["performance"]["kind"] = "ratio"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_import_only_requires_supported_object_families() -> None:
    data = valid_v0_2_source()
    data["imports"][0]["only"] = {"facilities": ["x"]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_distribution_requires_matching_method_field() -> None:
    data = valid_v0_2_source()
    data["fleets"][0]["distribution"] = {"method": "custom"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_distribution_direct_accepts_target_regions() -> None:
    data = valid_v0_2_source()
    data["fleets"][0]["distribution"] = {
        "method": "direct",
        "target_regions": ["QLD"],
    }
    jsonschema.validate(data, load_schema())


def test_site_location_requires_point_or_feature_ref() -> None:
    data = valid_v0_2_source()
    data["sites"][0]["location"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_opportunity_siting_allows_exactly_one_mode() -> None:
    data = valid_v0_2_source()
    data["opportunities"][0]["siting"] = {
        "site": "gladstone_refinery",
        "zone": "regions.aemo_rez_2024",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_network_node_basis_requires_partition_ref() -> None:
    data = valid_v0_2_source()
    data["networks"][0]["node_basis"] = {"kind": "region_partition"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_temporal_index_series_requires_index_unit() -> None:
    data = valid_v0_2_source()
    data["temporal_index_series"][0]["unit"] = "ratio"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_stock_characterization_requires_conversions() -> None:
    data = valid_v0_2_source()
    data["stock_characterizations"][0]["conversions"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_asset_new_build_limits_require_technology_and_capacity() -> None:
    data = valid_v0_2_source()
    data["facilities"][0]["new_build_limits"] = [{"technology": "heat.gas_heater"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, load_schema())


def test_minimal_reference_package_validates() -> None:
    data = {
        "dsl_version": "0.2",
        "spatial_layers": deepcopy(valid_v0_2_source()["spatial_layers"]),
        "region_partitions": deepcopy(valid_v0_2_source()["region_partitions"]),
    }
    jsonschema.validate(data, load_schema())
