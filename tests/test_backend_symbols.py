from __future__ import annotations

from copy import deepcopy

import jsonschema
import pytest

from vedalang.compiler.artifacts import ResolvedArtifacts, build_run_artifacts
from vedalang.compiler.ast import parse_source
from vedalang.compiler.backend_symbols import validate_backend_aliases
from vedalang.compiler.compiler import compile_vedalang_bundle, validate_vedalang
from vedalang.compiler.resolution import ResolutionError, resolve_imports, resolve_run


def _base_source() -> dict:
    return {
        "dsl_version": "0.3",
        "commodities": [
            {"id": "electricity", "type": "energy", "energy_form": "secondary"},
            {"id": "space_heat", "type": "service"},
        ],
        "technologies": [
            {
                "id": "heater",
                "description": "Heater fixture technology.",
                "provides": "space_heat",
                "inputs": [{"commodity": "electricity"}],
                "performance": {"kind": "efficiency", "value": 0.95},
            }
        ],
        "technology_roles": [
            {
                "id": "heat_supply",
                "description": "Heat supply fixture role.",
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
                "id": "toy_partition",
                "layer": "geo_demo",
                "members": ["REG1"],
                "mapping": {"kind": "constant", "value": "REG1"},
            }
        ],
        "sites": [
            {
                "id": "home",
                "location": {"point": {"lat": -27.4, "lon": 153.0}},
                "membership_overrides": {
                    "region_partitions": {"toy_partition": "REG1"}
                },
            }
        ],
        "facilities": [
            {
                "id": "home_heat",
                "description": "Home heat facility fixture.",
                "site": "home",
                "technology_role": "heat_supply",
                "stock": {
                    "items": [
                        {
                            "technology": "heater",
                            "metric": "installed_capacity",
                            "observed": {"value": "10 MW", "year": 2025},
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


def test_compile_emits_verbatim_backend_aliases():
    bundle = compile_vedalang_bundle(_base_source(), selected_run="toy_run")

    fi_comm_rows = []
    fi_process_rows = []
    book_regions_rows = []
    for file_spec in bundle.tableir["files"]:
        for sheet in file_spec["sheets"]:
            for table in sheet["tables"]:
                if table["tag"] == "~FI_COMM":
                    fi_comm_rows.extend(table["rows"])
                elif table["tag"] == "~FI_PROCESS":
                    fi_process_rows.extend(table["rows"])
                elif table["tag"] == "~BOOKREGIONS_MAP":
                    book_regions_rows.extend(table["rows"])

    assert {row["commodity"] for row in fi_comm_rows} == {
        "COM_electricity",
        "COM_space_heat",
    }
    assert {row["process"] for row in fi_process_rows} == {
        "PRC_FAC_home_heat_heater"
    }
    assert book_regions_rows == [{"bookname": "RUN_toy_run", "region": "REG1"}]


def test_schema_rejects_dotted_public_ids():
    source = _base_source()
    source["spatial_layers"][0]["id"] = "geo.demo"

    with pytest.raises(jsonschema.ValidationError, match="geo.demo"):
        validate_vedalang(source)


def test_compile_fails_on_overlong_process_alias():
    source = _base_source()
    source["technologies"][0]["id"] = "extremely_long_heating_technology"
    source["technology_roles"][0]["technologies"] = [
        "extremely_long_heating_technology"
    ]
    source["facilities"][0]["stock"]["items"][0]["technology"] = (
        "extremely_long_heating_technology"
    )
    source["facilities"][0]["id"] = "very_long_residential_heat_service_facility"

    with pytest.raises(ResolutionError, match="E021"):
        compile_vedalang_bundle(source, selected_run="toy_run")


def test_backend_alias_validator_flags_same_region_collision():
    source = _base_source()
    parsed = parse_source(source)
    graph = resolve_imports(parsed, {})
    run = resolve_run(graph, "toy_run")
    artifacts = build_run_artifacts(graph, run)

    duplicated_cpir = deepcopy(artifacts.cpir)
    duplicated_process = dict(duplicated_cpir["processes"][0])
    duplicated_process["id"] = "P::collision::copy"
    duplicated_cpir["processes"].append(duplicated_process)
    duplicated_artifacts = ResolvedArtifacts(
        csir=artifacts.csir,
        cpir=duplicated_cpir,
        explain=artifacts.explain,
    )

    diagnostics = validate_backend_aliases(graph, duplicated_artifacts)

    assert any(diag["code"] == "E026" for diag in diagnostics)
