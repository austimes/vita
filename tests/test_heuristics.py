"""Tests for the v0.3 heuristics linter."""

from vedalang.heuristics.linter import (
    H001_ServiceAssetWithoutStock,
    H002_AnnualActivityStockWithoutSupply,
    get_available_checks,
    run_heuristics,
    run_heuristics_detailed,
)


def make_source(**overrides) -> dict:
    source = {
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
                "lifetime": "18 year",
            }
        ],
        "technology_roles": [
            {
                "id": "space_heat_supply",
                "primary_service": "space_heat",
                "technologies": ["heat_pump"],
            }
        ],
        "sites": [
            {
                "id": "reg1_home",
                "location": {"point": {"lat": -33.86, "lon": 151.21}},
            }
        ],
        "facilities": [],
        "runs": [
            {
                "id": "reg1_2025",
                "base_year": 2025,
                "currency_year": 2024,
                "region_partition": "reg1_partition",
            }
        ],
        "region_partitions": [
            {
                "id": "reg1_partition",
                "layer": "geo.demo",
                "members": ["REG1"],
                "mapping": {"kind": "constant", "value": "REG1"},
            }
        ],
        "spatial_layers": [
            {
                "id": "geo.demo",
                "kind": "polygon",
                "key": "region_id",
                "geometry_file": "data/regions.geojson",
            }
        ],
    }
    source.update(overrides)
    return source


class TestH001ServiceAssetWithoutStock:
    def test_triggers_on_service_facility_without_stock(self):
        source = make_source(
            facilities=[
                {
                    "id": "reg1_heat",
                    "site": "reg1_home",
                    "technology_role": "space_heat_supply",
                }
            ]
        )

        issues = H001_ServiceAssetWithoutStock().apply(source)

        assert len(issues) == 1
        assert issues[0].code == "H001"
        assert "reg1_heat" in issues[0].message

    def test_ignores_service_facility_with_stock(self):
        source = make_source(
            facilities=[
                {
                    "id": "reg1_heat",
                    "site": "reg1_home",
                    "technology_role": "space_heat_supply",
                    "stock": {
                        "items": [
                            {
                                "technology": "heat_pump",
                                "metric": "installed_capacity",
                                "observed": {"value": "10 kW", "year": 2025},
                            }
                        ]
                    },
                }
            ]
        )

        issues = H001_ServiceAssetWithoutStock().apply(source)
        assert issues == []


class TestH002AnnualActivityStockWithoutSupply:
    def test_triggers_when_only_annual_activity_is_present(self):
        source = make_source(
            facilities=[
                {
                    "id": "reg1_heat",
                    "site": "reg1_home",
                    "technology_role": "space_heat_supply",
                    "stock": {
                        "items": [
                            {
                                "technology": "heat_pump",
                                "metric": "annual_activity",
                                "observed": {"value": "100 GWh/year", "year": 2025},
                            }
                        ]
                    },
                }
            ]
        )

        issues = H002_AnnualActivityStockWithoutSupply().apply(source)

        assert len(issues) == 1
        assert issues[0].code == "H002"
        assert "annual_activity stock" in issues[0].message

    def test_ignores_when_installed_capacity_exists(self):
        source = make_source(
            facilities=[
                {
                    "id": "reg1_heat",
                    "site": "reg1_home",
                    "technology_role": "space_heat_supply",
                    "stock": {
                        "items": [
                            {
                                "technology": "heat_pump",
                                "metric": "annual_activity",
                                "observed": {"value": "100 GWh/year", "year": 2025},
                            },
                            {
                                "technology": "heat_pump",
                                "metric": "installed_capacity",
                                "observed": {"value": "15 kW", "year": 2025},
                            },
                        ]
                    },
                }
            ]
        )

        issues = H002_AnnualActivityStockWithoutSupply().apply(source)
        assert issues == []


class TestHeuristicAPIs:
    def test_get_available_checks(self):
        checks = get_available_checks()
        assert checks == [
            {
                "code": "H001",
                "description": "Service asset without stock observations",
            },
            {
                "code": "H002",
                "description": (
                    "Annual-activity stock without matching installed-capacity "
                    "supply"
                ),
            },
        ]

    def test_run_heuristics(self):
        source = make_source(
            facilities=[
                {
                    "id": "reg1_heat",
                    "site": "reg1_home",
                    "technology_role": "space_heat_supply",
                }
            ]
        )

        issues = run_heuristics(source)
        assert len(issues) == 1
        assert issues[0].code == "H001"

    def test_run_heuristics_detailed(self):
        source = make_source(
            facilities=[
                {
                    "id": "reg1_heat",
                    "site": "reg1_home",
                    "technology_role": "space_heat_supply",
                }
            ]
        )

        result = run_heuristics_detailed(source)
        assert result.warning_count == 1
        assert result.error_count == 0
        assert len(result.issues) == 1
        assert result.to_dict()["summary"]["issue_count"] == 1
