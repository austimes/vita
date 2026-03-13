import json

from lsprotocol import types

from tests.test_lsp import MockTextDocument
from tests.test_vedalang_cli import run_vedalang
from tools.vedalang_lsp.server.server import server, validate_document
from vedalang.compiler.diagnostics import collect_diagnostics
from vedalang.compiler.source_maps import attach_source_positions
from vedalang.lint.code_categories import run_core


def test_public_compile_json_includes_section14_location_metadata(tmp_path):
    src = tmp_path / "bad_service_role.veda.yaml"
    src.write_text(
        "\n".join(
            [
                'dsl_version: "0.3"',
                "commodities:",
                "  - id: electricity",
                "    type: energy",
                "    energy_form: secondary",
                "technologies:",
                "  - id: gas_heater",
                "    provides: electricity",
                "technology_roles:",
                "  - id: gas_boiler_role",
                "    primary_service: electricity",
                "    technologies: [gas_heater]",
                "runs:",
                "  - id: toy_run",
                "    base_year: 2025",
                "    currency_year: 2024",
                "    region_partition: toy_partition",
                "spatial_layers:",
                "  - id: geo.demo",
                "    kind: polygon",
                "    key: region_id",
                "    geometry_file: data/regions.geojson",
                "region_partitions:",
                "  - id: toy_partition",
                "    layer: geo.demo",
                "    members: [QLD]",
                "    mapping:",
                "      kind: constant",
                "      value: QLD",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_vedalang(
        "compile",
        str(src),
        "--run",
        "toy_run",
        "--out",
        str(tmp_path / "out"),
        "--json",
        "--no-lint",
    )
    assert result.returncode == 2

    payload = json.loads(result.stdout)
    assert payload["code"] == "E004"
    assert payload["object_id"] == "gas_boiler_role"
    assert payload["location"] == "technology_roles[0]"
    assert isinstance(payload.get("line"), int)
    assert isinstance(payload.get("column"), int)
    assert isinstance(payload.get("source_excerpt"), dict)


def test_collect_public_diagnostics_emits_prd_warning_codes():
    source = {
        "dsl_version": "0.3",
        "commodities": [
            {"id": "natural_gas", "type": "energy", "energy_form": "primary"},
            {"id": "space_heat", "type": "service"},
        ],
        "technologies": [
            {
                "id": "gas_heater",
                "provides": "space_heat",
                "inputs": [{"commodity": "natural_gas", "basis": "HHV"}],
                "performance": {"kind": "efficiency", "value": 0.9},
                "stock_characterization": "heater_stock",
            },
            {
                "id": "heat_pump",
                "provides": "space_heat",
                "performance": {"kind": "cop", "value": 3.0},
            },
        ],
        "technology_roles": [
            {
                "id": "gas_heat_pump",
                "primary_service": "space_heat",
                "technologies": ["gas_heater", "heat_pump"],
            }
        ],
        "stock_characterizations": [
            {
                "id": "heater_stock",
                "applies_to": ["gas_heater"],
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
                "id": "geo.demo",
                "kind": "polygon",
                "key": "region_id",
                "geometry_file": "data/regions.geojson",
            }
        ],
        "spatial_measure_sets": [
            {
                "id": "weights",
                "layer": "geo.demo",
                "measures": [
                    {
                        "id": "dwelling_stock",
                        "observed_year": 2018,
                        "unit": "assets",
                        "file": "data/weights.csv",
                        "column": "dwelling_stock",
                    }
                ],
            }
        ],
        "temporal_index_series": [
            {
                "id": "dwelling_index",
                "unit": "index",
                "values": {"2020": 1.0, "2025": 1.1},
            }
        ],
        "region_partitions": [
            {
                "id": "toy_partition",
                "layer": "geo.demo",
                "members": ["QLD"],
                "mapping": {"kind": "constant", "value": "QLD"},
            }
        ],
        "sites": [
            {
                "id": "home",
                "location": {"point": {"lat": -27.4, "lon": 153.0}},
                "membership_overrides": {
                    "region_partitions": {"toy_partition": "QLD"}
                },
            }
        ],
        "fleets": [
            {
                "id": "heat_fleet",
                "technology_role": "gas_heat_pump",
                "stock": {
                    "adjust_to_base_year": {
                        "using": {"kind": "annual_growth", "rate": "1 %/year"}
                    },
                    "items": [
                        {
                            "technology": "gas_heater",
                            "metric": "asset_count",
                            "observed": {"value": "100 assets", "year": 2020},
                        }
                    ],
                },
                "distribution": {
                    "method": "custom_file",
                    "custom_weights_file": "weights.csv",
                },
            }
        ],
        "runs": [
            {
                "id": "toy_run",
                "base_year": 2025,
                "currency_year": 2024,
                "region_partition": "toy_partition",
            }
        ],
    }

    diagnostics = collect_diagnostics(
        source,
        selected_run="toy_run",
        custom_weights={"weights.csv": {"QLD": 1.0}},
    )
    source_text = json.dumps(source)
    attach_source_positions(diagnostics, source=source, source_text=source_text)
    codes = {diag["code"] for diag in diagnostics}

    assert {"W001", "W002", "W003", "W006", "W007", "W009", "W010", "W011"} <= codes


def test_collect_public_diagnostics_flags_duplicate_rollout_patterns():
    source = {
        "dsl_version": "0.3",
        "commodities": [
            {"id": "electricity", "type": "energy", "energy_form": "secondary"},
            {"id": "space_heat", "type": "service"},
        ],
        "technologies": [
            {
                "id": "gas_heater",
                "provides": "space_heat",
                "performance": {"kind": "efficiency", "value": 0.9},
            },
            {
                "id": "heat_pump",
                "provides": "space_heat",
                "inputs": [{"commodity": "electricity"}],
                "performance": {"kind": "cop", "value": 3.0},
            },
        ],
        "technology_roles": [
            {
                "id": "space_heat_supply",
                "primary_service": "space_heat",
                "technologies": ["gas_heater", "heat_pump"],
                "transitions": [
                    {
                        "from": "gas_heater",
                        "to": "heat_pump",
                        "kind": "retrofit",
                    }
                ],
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
        "region_partitions": [
            {
                "id": "single_region",
                "layer": "geo.demo",
                "members": ["SINGLE"],
                "mapping": {"kind": "constant", "value": "SINGLE"},
            }
        ],
        "sites": [
            {
                "id": "single_site",
                "location": {"point": {"lat": -33.9, "lon": 151.2}},
                "membership_overrides": {
                    "region_partitions": {"single_region": "SINGLE"}
                },
            }
        ],
        "facilities": [
            {
                "id": "residential_heat",
                "site": "single_site",
                "technology_role": "space_heat_supply",
                "available_technologies": ["gas_heater", "heat_pump"],
                "new_build_limits": [
                    {"technology": "heat_pump", "max_new_capacity": "60 MW"}
                ],
                "stock": {
                    "items": [
                        {
                            "technology": "gas_heater",
                            "metric": "installed_capacity",
                            "observed": {"value": "80 MW", "year": 2025},
                        }
                    ]
                },
            }
        ],
        "runs": [
            {
                "id": "single_2025",
                "base_year": 2025,
                "currency_year": 2024,
                "region_partition": "single_region",
            }
        ],
    }

    diagnostics = collect_diagnostics(source, selected_run="single_2025")
    codes = {diag["code"] for diag in diagnostics}

    assert {"W013"} <= codes


def test_lsp_validate_document_uses_diagnostics():
    doc = MockTextDocument(
        "\n".join(
            [
                'dsl_version: "0.3"',
                "commodities:",
                "  - id: electricity",
                "    type: energy",
                "    energy_form: secondary",
                "technologies:",
                "  - id: gas_heater",
                "    provides: electricity",
                "technology_roles:",
                "  - id: gas_heater",
                "    primary_service: electricity",
                "    technologies: [gas_heater]",
            ]
        )
        + "\n"
    )

    diagnostics = validate_document(server, doc)
    errors = [d for d in diagnostics if d.severity == types.DiagnosticSeverity.Error]
    assert any(d.code == "E004" for d in errors)
    assert all("Missing required 'model' key" not in d.message for d in diagnostics)


def test_run_core_skips_legacy_xref_checks_for_public_source():
    source = {
        "dsl_version": "0.3",
        "commodities": [
            {"id": "natural_gas", "type": "energy", "energy_form": "primary"},
            {"id": "space_heat", "type": "service"},
        ],
        "technologies": [
            {
                "id": "gas_heater",
                "provides": "space_heat",
                "inputs": [{"commodity": "natural_gas", "basis": "HHV"}],
                "performance": {"kind": "efficiency", "value": 0.9},
            }
        ],
        "technology_roles": [
            {
                "id": "space_heat_supply",
                "primary_service": "space_heat",
                "technologies": ["gas_heater"],
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
        "region_partitions": [
            {
                "id": "toy_partition",
                "layer": "geo.demo",
                "members": ["QLD"],
                "mapping": {"kind": "constant", "value": "QLD"},
            }
        ],
        "sites": [
            {
                "id": "home",
                "location": {"point": {"lat": -27.4, "lon": 153.0}},
                "membership_overrides": {
                    "region_partitions": {"toy_partition": "QLD"}
                },
            }
        ],
        "facilities": [
            {
                "id": "home_heat",
                "site": "home",
                "technology_role": "space_heat_supply",
                "stock": {
                    "items": [
                        {
                            "technology": "gas_heater",
                            "metric": "installed_capacity",
                            "observed": {"value": "12 kW", "year": 2025},
                        }
                    ]
                },
            }
        ],
        "runs": [
            {
                "id": "toy_run",
                "base_year": 2025,
                "currency_year": 2024,
                "region_partition": "toy_partition",
            }
        ],
    }

    diagnostics = run_core(source)
    assert diagnostics == []
