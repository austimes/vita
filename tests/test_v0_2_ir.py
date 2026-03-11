import json
from pathlib import Path

import jsonschema

from tests.test_v0_2_resolution import _packages_and_model
from vedalang.compiler.v0_2_ir import build_v0_2_artifacts
from vedalang.compiler.v0_2_resolution import resolve_imports, resolve_run

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"


def _load_schema(name: str) -> dict:
    with open(SCHEMA_DIR / name) as f:
        return json.load(f)


def test_build_v0_2_artifacts_validate_against_schemas():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")

    artifacts = build_v0_2_artifacts(
        graph,
        run,
        site_region_memberships={"gladstone_refinery": "QLD"},
        site_zone_memberships={
            "gladstone_refinery": {"regions.aemo_rez_2024": "qld_central_rez"}
        },
        measure_weights={
            "demo.abs_demography.dwelling_stock": {
                "NSW": 0.40,
                "VIC": 0.35,
                "QLD": 0.25,
            }
        },
    )

    jsonschema.validate(artifacts.csir, _load_schema("csir.schema.json"))
    jsonschema.validate(artifacts.cpir, _load_schema("cpir.schema.json"))
    jsonschema.validate(artifacts.explain, _load_schema("explain.schema.json"))

    assert artifacts.csir["technology_role_instances"][0]["id"].startswith(
        "role_instance."
    )
    assert artifacts.cpir["processes"][0]["id"].startswith("P::")
    assert "trace.norm.residential_space_heat.total" in artifacts.explain["traces"]


def test_artifacts_are_deterministically_ordered():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")
    kwargs = {
        "site_region_memberships": {"gladstone_refinery": "QLD"},
        "site_zone_memberships": {
            "gladstone_refinery": {"regions.aemo_rez_2024": "qld_central_rez"}
        },
        "measure_weights": {
            "demo.abs_demography.dwelling_stock": {
                "NSW": 0.40,
                "VIC": 0.35,
                "QLD": 0.25,
            }
        },
    }

    first = build_v0_2_artifacts(graph, run, **kwargs)
    second = build_v0_2_artifacts(graph, run, **kwargs)

    assert json.dumps(first.csir, sort_keys=True) == json.dumps(
        second.csir, sort_keys=True
    )
    assert json.dumps(first.cpir, sort_keys=True) == json.dumps(
        second.cpir, sort_keys=True
    )
    assert json.dumps(first.explain, sort_keys=True) == json.dumps(
        second.explain, sort_keys=True
    )


def test_cpir_contains_transitions_and_network_arcs():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")

    artifacts = build_v0_2_artifacts(
        graph,
        run,
        site_region_memberships={"gladstone_refinery": "QLD"},
        site_zone_memberships={
            "gladstone_refinery": {"regions.aemo_rez_2024": "qld_central_rez"}
        },
        measure_weights={
            "demo.abs_demography.dwelling_stock": {
                "NSW": 0.40,
                "VIC": 0.35,
                "QLD": 0.25,
            }
        },
    )

    assert len(artifacts.cpir["transitions"]) == 4
    assert len(artifacts.cpir["network_arcs"]) == 1
    assert any(
        process.get("source_zone_opportunity") == "qld_central_rez_heat"
        for process in artifacts.cpir["processes"]
    )
    opportunity_process = next(
        process
        for process in artifacts.cpir["processes"]
        if process.get("source_zone_opportunity") == "qld_central_rez_heat"
    )
    assert opportunity_process["max_new_capacity"]["amount"] == 1500.0
