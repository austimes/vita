import json

from lsprotocol import types

from tests.test_lsp import MockTextDocument
from tests.test_vedalang_cli import run_vedalang
from tools.vedalang_lsp.server.server import server, validate_document
from vedalang.compiler.source_maps import attach_source_positions
from vedalang.compiler.v0_2_diagnostics import collect_v0_2_diagnostics


def test_v0_2_compile_json_includes_section14_location_metadata(tmp_path):
    src = tmp_path / "bad_service_role.veda.yaml"
    src.write_text(
        "\n".join(
            [
                'dsl_version: "0.2"',
                "commodities:",
                "  - id: secondary:electricity",
                "    kind: secondary",
                "technologies:",
                "  - id: gas_heater",
                "    provides: secondary:electricity",
                "technology_roles:",
                "  - id: gas_boiler_role",
                "    primary_service: secondary:electricity",
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


def test_collect_v0_2_diagnostics_emits_prd_warning_codes():
    source = {
        "dsl_version": "0.2",
        "commodities": [
            {"id": "primary:natural_gas", "kind": "primary"},
            {"id": "service:space_heat", "kind": "service"},
        ],
        "technologies": [
            {
                "id": "gas_heater",
                "provides": "service:space_heat",
                "inputs": [{"commodity": "primary:natural_gas", "basis": "HHV"}],
                "performance": {"kind": "efficiency", "value": 0.9},
                "stock_characterization": "heater_stock",
            },
            {
                "id": "heat_pump",
                "provides": "service:space_heat",
                "performance": {"kind": "cop", "value": 3.0},
            },
        ],
        "technology_roles": [
            {
                "id": "gas_heat_pump",
                "primary_service": "service:space_heat",
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

    diagnostics = collect_v0_2_diagnostics(
        source,
        selected_run="toy_run",
        custom_weights={"weights.csv": {"QLD": 1.0}},
    )
    source_text = json.dumps(source)
    attach_source_positions(diagnostics, source=source, source_text=source_text)
    codes = {diag["code"] for diag in diagnostics}

    assert {"W001", "W002", "W003", "W006", "W007", "W009", "W010", "W011"} <= codes


def test_lsp_validate_document_uses_v0_2_diagnostics():
    doc = MockTextDocument(
        "\n".join(
            [
                'dsl_version: "0.2"',
                "commodities:",
                "  - id: secondary:electricity",
                "    kind: secondary",
                "technologies:",
                "  - id: gas_heater",
                "    provides: secondary:electricity",
                "technology_roles:",
                "  - id: gas_heater",
                "    primary_service: secondary:electricity",
                "    technologies: [gas_heater]",
            ]
        )
        + "\n"
    )

    diagnostics = validate_document(server, doc)
    errors = [d for d in diagnostics if d.severity == types.DiagnosticSeverity.Error]
    assert any(d.code == "E004" for d in errors)
    assert all("Missing required 'model' key" not in d.message for d in diagnostics)
