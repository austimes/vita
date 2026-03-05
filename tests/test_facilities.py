"""Tests for facility primitive mode-based lowering."""

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
                {
                    "id": "primary:natural_gas",
                    "type": "fuel",
                    "combustible": False,
                },
                {"id": "primary:hydrogen", "type": "fuel", "combustible": False},
                {"id": "service:alumina_output", "type": "service", "unit": "PJ"},
                {"id": "emission:co2", "type": "emission", "unit": "Mt"},
            ],
            "cases": [{"name": "baseline", "is_baseline": True}],
        },
        "roles": [
            {
                "id": "produce_alumina",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "conversion",
                "required_inputs": [],
                "required_outputs": [{"commodity": "service:alumina_output"}],
            }
        ],
        "facility_templates": [
            {
                "id": "alumina_template",
                "class": "safeguard",
                "role": "produce_alumina",
                "sector": "IND",
                "primary_output_commodity": "service:alumina_output",
                "variants": [
                    {
                        "id": "calciner_standard",
                        "baseline_mode": "coal",
                        "mode_ladder": ["coal", "retrofit_to_ng", "retrofit_to_h2"],
                        "modes": [
                            {
                                "id": "coal",
                                "fuel_in": "primary:coal",
                                "capex": 0,
                                "existing": True,
                                "efficiency": 0.9,
                                "emission_factors": {"emission:co2": 0.12},
                                "ramp_rate": 0.0,
                            },
                            {
                                "id": "retrofit_to_ng",
                                "fuel_in": "primary:natural_gas",
                                "capex": 1200,
                                "existing": False,
                                "efficiency": 0.95,
                                "emission_factors": {"emission:co2": 0.08},
                                "ramp_rate": 0.5,
                            },
                            {
                                "id": "retrofit_to_h2",
                                "fuel_in": "primary:hydrogen",
                                "capex": 2500,
                                "existing": False,
                                "efficiency": 0.98,
                                "emission_factors": {"emission:co2": 0.02},
                                "ramp_rate": 0.2,
                            },
                        ],
                    }
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
                "cap_base": {"value": 8.0, "unit": "GW"},
                "capacity_coupling": "le",
                "no_backsliding": True,
                "output_series": {
                    "interpolation": "interp_extrap",
                    "values": {"2025": 100, "2030": 95, "2035": 90},
                },
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


def test_facility_lowering_generates_scoped_demand_and_mode_processes():
    tableir = compile_vedalang_to_tableir(_base_source())

    demand_rows = [r for r in _collect_rows(tableir, "~TFM_DINS-AT") if "com_proj" in r]
    assert demand_rows
    assert any(
        "service:alumina_output@IND.sgf_alumina_gladstone" == r["cset_cn"]
        for r in demand_rows
    )

    process_rows = _collect_rows(tableir, "~FI_PROCESS")
    process_names = {row["process"] for row in process_rows}
    assert any("mode_coal" in name for name in process_names)
    assert any("mode_retrofit_to_ng" in name for name in process_names)
    assert any("mode_retrofit_to_h2" in name for name in process_names)


def test_facility_generates_cap_coupling_no_backslide_and_ramp_constraints():
    tableir = compile_vedalang_to_tableir(_base_source())

    uc_rows = _collect_rows(tableir, "~UC_T")
    uc_names = {row["uc_n"] for row in uc_rows}

    assert any(
        name.startswith("FAC_CAP_COUPLE_sgf_alumina_gladstone")
        for name in uc_names
    )
    assert any(
        name.startswith("FAC_CAP_MONO_sgf_alumina_gladstone")
        for name in uc_names
    )
    assert any(
        name.startswith("FAC_CAP_RAMP_sgf_alumina_gladstone")
        for name in uc_names
    )
    assert any(name.startswith("FAC_INT_sgf_alumina_gladstone") for name in uc_names)

    assert not any(
        name.startswith("FAC_MIX_sgf_alumina_gladstone") for name in uc_names
    )
    assert not any(name.startswith("FAC_NB_sgf_alumina_gladstone") for name in uc_names)

    cap_rows = [r for r in uc_rows if str(r.get("uc_n", "")).startswith("FAC_CAP_")]
    assert any("uc_cap" in r for r in cap_rows)


def test_facility_top_n_aggregation_keeps_one_individual_plus_one_aggregate():
    source = _base_source()
    source["facilities"].append(
        {
            "id": "sgf_alumina_y",
            "template": "alumina_template",
            "class": "safeguard",
            "location_ref": "aus/qld/gladstone_lga",
            "representation": "individual",
            "cap_base": {"value": 1.5, "unit": "GW"},
            "output_series": {
                "interpolation": "interp_extrap",
                "values": {"2025": 20, "2030": 18, "2035": 17},
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
    assert len(scopes) == 2
    assert any("_agg" in scope for scope in scopes)


def test_facility_scopes_do_not_expand_existing_sector_availability():
    source = _base_source()
    source["scoping"] = {"sectors": ["IND"], "end_uses": ["existing_scope"]}
    source["variants"] = [
        {
            "id": "alumina_generic",
            "role": "produce_alumina",
            "inputs": [{"commodity": "primary:natural_gas"}],
            "outputs": [{"commodity": "service:alumina_output"}],
            "efficiency": 0.92,
            "emission_factors": {"emission:co2": 0.09},
        }
    ]
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


def test_facility_template_mode_ladder_must_cover_all_modes():
    source = _base_source()
    source["facility_templates"][0]["variants"][0]["mode_ladder"] = [
        "coal",
        "retrofit_to_ng",
    ]

    with pytest.raises(VedaLangError, match="mode_ladder"):
        compile_vedalang_to_tableir(source)


def test_facility_no_backsliding_false_disables_mono_constraints():
    source = _base_source()
    source["facilities"][0]["no_backsliding"] = False

    tableir = compile_vedalang_to_tableir(source)
    uc_rows = _collect_rows(tableir, "~UC_T")
    uc_names = {row["uc_n"] for row in uc_rows}

    assert not any(
        name.startswith("FAC_CAP_MONO_sgf_alumina_gladstone")
        for name in uc_names
    )


def test_facility_mode_lowering_uses_only_physical_commodities():
    tableir = compile_vedalang_to_tableir(_base_source())
    comm_rows = _collect_rows(tableir, "~FI_COMM")
    commodities = {row["commodity"] for row in comm_rows}
    assert not any("capability" in commodity for commodity in commodities)
