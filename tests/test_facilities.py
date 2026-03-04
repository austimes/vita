"""Tests for facility primitive v1 lowering."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from vedalang.compiler.compiler import compile_vedalang_to_tableir
from vedalang.compiler.registry import VedaLangError

SCHEMA_PATH = (
    Path(__file__).parent.parent / "vedalang" / "schema" / "vedalang.schema.json"
)


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _base_source() -> dict:
    return {
        "model": {
            "name": "FacilityMini",
            "regions": ["AUS"],
            "region_scheme": "au_state_v1",
            "milestone_years": [2025, 2030, 2035],
            "commodities": [
                {"id": "primary:coal", "type": "fuel", "combustible": False},
                {"id": "primary:natural_gas", "type": "fuel", "combustible": False},
                {"id": "service:alumina_output", "type": "service", "unit": "PJ"},
                {"id": "emission:co2", "type": "emission", "unit": "Mt"},
            ],
            "cases": [{"name": "baseline", "is_baseline": True}],
        },
        "process_roles": [
            {
                "id": "produce_alumina",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "conversion",
                "required_inputs": [],
                "required_outputs": [{"commodity": "service:alumina_output"}],
            }
        ],
        "process_variants": [
            {
                "id": "alumina_coal",
                "role": "produce_alumina",
                "inputs": [{"commodity": "primary:coal"}],
                "outputs": [{"commodity": "service:alumina_output"}],
                "efficiency": 0.9,
                "emission_factors": {"emission:co2": 0.12},
            },
            {
                "id": "alumina_gas",
                "role": "produce_alumina",
                "inputs": [{"commodity": "primary:natural_gas"}],
                "outputs": [{"commodity": "service:alumina_output"}],
                "efficiency": 0.95,
                "emission_factors": {"emission:co2": 0.08},
            },
        ],
        "commodity_groups": [
            {
                "id": "high_temp_heat",
                "members": ["primary:coal", "primary:natural_gas"],
                "unit": "PJ",
                "dimension": "energy",
            }
        ],
        "facility_templates": [
            {
                "id": "alumina_template",
                "class": "safeguard",
                "role": "produce_alumina",
                "sector": "IND",
                "primary_output_commodity": "service:alumina_output",
                "candidate_variants": ["alumina_coal", "alumina_gas"],
                "transition_graph": [{"from": "alumina_coal", "to": "alumina_gas"}],
                "input_groups": [
                    {"id": "heat_input", "commodity_group": "high_temp_heat"}
                ],
            }
        ],
        "facility_selection": {
            "mode": "top_n_by_baseline_emissions",
            "n_individual": 1,
        },
        "spatial_mappings": [
            {
                "scheme": "au_state_v1",
                "from": "facility_location_ref",
                "map": {"aus/qld/gladstone_lga": [{"region": "AUS", "share": 1.0}]},
            }
        ],
        "facilities": [
            {
                "id": "sgf_alumina_gladstone",
                "template": "alumina_template",
                "class": "safeguard",
                "location_ref": "aus/qld/gladstone_lga",
                "representation": "individual",
                "output_series": {
                    "interpolation": "interp_extrap",
                    "values": {"2025": 100, "2030": 95, "2035": 90},
                },
                "installed_state": {
                    "variant": "alumina_coal",
                    "existing_capacity": [{"vintage": 2018, "capacity": 8.0}],
                },
                "variant_policies": [
                    {
                        "variant": "alumina_gas",
                        "from_year": 2030,
                        "max_new_capacity_per_period": 2.0,
                    }
                ],
                "input_mix": [
                    {
                        "group": "heat_input",
                        "baseline_shares": {
                            "primary:coal": 0.8,
                            "primary:natural_gas": 0.2,
                        },
                        "targets": [
                            {
                                "year": 2035,
                                "shares": {
                                    "primary:coal": 0.2,
                                    "primary:natural_gas": 0.8,
                                },
                                "hard": False,
                                "tolerance": 0.1,
                            }
                        ],
                    }
                ],
                "safeguard": {
                    "baseline_intensity": 0.1,
                    "baseline_year": 2025,
                    "intensity_decline_blocks": [
                        {"from_year": 2025, "to_year": 2030, "annual_decline_pct": 4.9},
                        {"from_year": 2031, "to_year": 2040, "annual_decline_pct": 3.0},
                    ],
                },
            }
        ],
    }


def _collect_rows(tableir: dict, tag: str) -> list[dict]:
    rows: list[dict] = []
    for file_spec in tableir["files"]:
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == tag:
                    rows.extend(table.get("rows", []))
    return rows


def test_facility_schema_requires_safeguard_block():
    schema = _load_schema()
    data = _base_source()
    data["facilities"][0].pop("safeguard")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_facility_lowering_generates_scoped_demand_and_availability():
    tableir = compile_vedalang_to_tableir(_base_source())

    demand_rows = [r for r in _collect_rows(tableir, "~TFM_DINS-AT") if "com_proj" in r]
    assert demand_rows
    assert any(
        "service:alumina_output@IND.sgf_alumina_gladstone" == r["cset_cn"]
        for r in demand_rows
    )

    process_rows = _collect_rows(tableir, "~FI_PROCESS")
    process_names = {row["process"] for row in process_rows}
    assert any(
        "alumina_coal_AUS_IND_sgf_alumina_gladstone" in name for name in process_names
    )
    assert any(
        "alumina_gas_AUS_IND_sgf_alumina_gladstone" in name for name in process_names
    )


def test_facility_generates_policy_bounds_and_constraints():
    tableir = compile_vedalang_to_tableir(_base_source())

    tfm_rows = _collect_rows(tableir, "~TFM_INS")
    gas_bounds = [
        r
        for r in tfm_rows
        if "alumina_gas_AUS_IND_sgf_alumina_gladstone" in str(r.get("process", ""))
        and r.get("attribute") in {"NCAP_BND", "ACT_BND"}
    ]
    assert any(r.get("year") == 2025 and r.get("limtype") == "FX" for r in gas_bounds)

    uc_rows = _collect_rows(tableir, "~UC_T")
    uc_names = {row["uc_n"] for row in uc_rows}
    assert any(name.startswith("FAC_INT_sgf_alumina_gladstone") for name in uc_names)
    assert any(name.startswith("FAC_NB_sgf_alumina_gladstone") for name in uc_names)
    assert any(name.startswith("FAC_MIX_sgf_alumina_gladstone") for name in uc_names)


def test_facility_top_n_aggregation_keeps_one_individual_plus_one_aggregate():
    source = _base_source()
    source["facilities"].append(
        {
            "id": "sgf_alumina_y",
            "template": "alumina_template",
            "class": "safeguard",
            "location_ref": "aus/qld/gladstone_lga",
            "representation": "individual",
            "output_series": {
                "interpolation": "interp_extrap",
                "values": {"2025": 20, "2030": 18, "2035": 17},
            },
            "installed_state": {
                "variant": "alumina_coal",
                "existing_capacity": [{"vintage": 2010, "capacity": 1.0}],
            },
            "safeguard": {
                "baseline_intensity": 0.1,
                "baseline_year": 2025,
                "intensity_decline_blocks": [
                    {"from_year": 2025, "to_year": 2030, "annual_decline_pct": 4.9}
                ],
            },
        }
    )

    tableir = compile_vedalang_to_tableir(source)
    demand_rows = [
        r
        for r in _collect_rows(tableir, "~TFM_DINS-AT")
        if "com_proj" in r and r.get("year") == 2025
    ]
    scopes = {r["cset_cn"] for r in demand_rows if "@IND." in r.get("cset_cn", "")}
    # One selected individual + one aggregated long-tail facility entity.
    assert len(scopes) == 2
    assert any("_agg" in scope for scope in scopes)


def test_facility_input_mix_shares_must_sum_to_one():
    source = _base_source()
    source["facilities"][0]["input_mix"][0]["baseline_shares"] = {"primary:coal": 0.7}

    with pytest.raises(VedaLangError, match="must sum to 1.0"):
        compile_vedalang_to_tableir(source)


def test_facility_transition_graph_must_be_chain():
    source = _base_source()
    source["process_variants"].append(
        {
            "id": "alumina_h2",
            "role": "produce_alumina",
            "inputs": [{"commodity": "primary:natural_gas"}],
            "outputs": [{"commodity": "service:alumina_output"}],
            "efficiency": 0.97,
            "emission_factors": {"emission:co2": 0.02},
        }
    )
    source["facility_templates"][0]["candidate_variants"] = [
        "alumina_coal",
        "alumina_gas",
        "alumina_h2",
    ]
    source["facility_templates"][0]["transition_graph"] = [
        {"from": "alumina_coal", "to": "alumina_gas"},
        {"from": "alumina_coal", "to": "alumina_h2"},
    ]

    with pytest.raises(VedaLangError, match="chain-shaped"):
        compile_vedalang_to_tableir(source)


def test_facility_scopes_do_not_expand_existing_sector_availability():
    source = _base_source()
    source["scoping"] = {"sectors": ["IND"], "end_uses": ["existing_scope"]}
    source["process_variants"].append(
        {
            "id": "alumina_generic",
            "role": "produce_alumina",
            "inputs": [{"commodity": "primary:natural_gas"}],
            "outputs": [{"commodity": "service:alumina_output"}],
            "efficiency": 0.92,
            "emission_factors": {"emission:co2": 0.09},
        }
    )
    source["availability"] = [
        {
            "variant": "alumina_generic",
            "regions": ["AUS"],
            "sectors": ["IND"],
        }
    ]

    tableir = compile_vedalang_to_tableir(source)
    process_rows = _collect_rows(tableir, "~FI_PROCESS")
    generic_processes = [
        row["process"]
        for row in process_rows
        if row["process"].startswith("alumina_generic_AUS_")
    ]
    assert generic_processes == ["alumina_generic_AUS_IND_existing_scope"]
