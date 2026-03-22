import json
from pathlib import Path

import jsonschema

from tests.test_resolution import _packages_and_model
from vedalang.compiler import parse_source
from vedalang.compiler.artifacts import build_run_artifacts
from vedalang.compiler.resolution import resolve_imports, resolve_run

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"


def _load_schema(name: str) -> dict:
    with open(SCHEMA_DIR / name) as f:
        return json.load(f)


def test_build_public_artifacts_validate_against_schemas():
    packages, model = _packages_and_model()
    graph = resolve_imports(model, packages)
    run = resolve_run(graph, "toy_states_2025")

    artifacts = build_run_artifacts(
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

    first = build_run_artifacts(graph, run, **kwargs)
    second = build_run_artifacts(graph, run, **kwargs)

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

    artifacts = build_run_artifacts(
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


def test_emissions_budget_policy_activation_lowers_to_cpir_user_constraint():
    source = {
        "dsl_version": "0.3",
        "commodities": [
            {"id": "co2", "type": "emission"},
            {"id": "ng", "type": "energy", "energy_form": "primary"},
            {"id": "heat", "type": "service"},
        ],
        "technologies": [
            {
                "id": "gas_boil",
                "provides": "heat",
                "inputs": [{"commodity": "ng", "basis": "HHV"}],
                "emissions": [{"commodity": "co2", "factor": "0.056 t/GJ"}],
            }
        ],
        "technology_roles": [
            {
                "id": "heat_sup",
                "primary_service": "heat",
                "technologies": ["gas_boil"],
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
        "year_sets": [
            {
                "id": "pathway_2025_2030",
                "start_year": 2025,
                "milestone_years": [2025, 2030],
            }
        ],
        "fleets": [
            {
                "id": "heat_sup_fleet",
                "technology_role": "heat_sup",
                "distribution": {"method": "direct"},
                "policies": ["co2_cap"],
                "description": "Policy-linked fleet fixture.",
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
        "runs": [
            {
                "id": "s25_co2_cap",
                "veda_book_name": "S25CO2CAP",
                "year_set": "pathway_2025_2030",
                "currency_year": 2024,
                "region_partition": "single_region",
                "enable_policies": ["co2_cap"],
                "include_cases": ["co2_cap_case"],
            }
        ],
    }

    graph = resolve_imports(parse_source(source), {})
    run = resolve_run(graph, "s25_co2_cap")
    artifacts = build_run_artifacts(graph, run)

    assert artifacts.csir["policy_activations"]
    activation = artifacts.csir["policy_activations"][0]
    assert activation["policy_id"] == "co2_cap"
    assert activation["selected_case"] == "co2_cap_case"
    assert activation["budgets"] == [
        {"year": 2025, "amount": 0.5, "unit": "Mt"},
        {"year": 2030, "amount": 0.4, "unit": "Mt"},
    ]

    emissions_ucs = [
        uc
        for uc in artifacts.cpir["user_constraints"]
        if uc.get("kind") == "emissions_budget"
    ]
    assert len(emissions_ucs) == 1
    uc = emissions_ucs[0]
    assert uc["source_policy"] == "co2_cap"
    assert uc["selected_case"] == "co2_cap_case"
    assert uc["emission_commodity"] == "co2"
    assert any(row.get("uc_comprd") == 1.0 for row in uc["rows"])
    rhs_rows = [row for row in uc["rows"] if row.get("uc_rhsrt") is not None]
    assert rhs_rows == [
        {"region": "SINGLE", "year": 2025, "limtype": "UP", "uc_rhsrt": 0.5},
        {"region": "SINGLE", "year": 2030, "limtype": "UP", "uc_rhsrt": 0.4},
    ]
