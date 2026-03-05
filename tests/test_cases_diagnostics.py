"""Tests for cases overlay and diagnostics metadata export."""

import pytest

from vedalang.compiler.compiler import compile_vedalang_to_tableir
from vedalang.compiler.registry import VedaLangError


def _minimal_new_syntax_source() -> dict:
    return {
        "model": {
            "name": "CasesMini",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030],
            "commodities": [
                {"id": "electricity", "type": "energy"},
                {"id": "heat_service", "type": "service"},
                {"id": "co2", "type": "emission"},
            ],
            "scenario_parameters": [
                {
                    "name": "base_price",
                    "type": "commodity_price",
                    "commodity": "electricity",
                    "interpolation": "interp_extrap",
                    "values": {"2020": 10, "2030": 12},
                }
            ],
            "constraints": [
                {
                    "name": "co2_cap",
                    "type": "emission_cap",
                    "commodity": "co2",
                    "limtype": "up",
                    "years": {"2020": 100, "2030": 80},
                }
            ],
            "cases": [
                {"name": "baseline", "is_baseline": True},
                {
                    "name": "policy",
                    "demand_overrides": [
                        {
                            "commodity": "heat_service",
                            "region": "REG1",
                            "values": {"2020": 999, "2030": 999},
                        }
                    ],
                    "fuel_price_overrides": [
                        {
                            "commodity": "electricity",
                            "values": {"2020": 77, "2030": 88},
                        }
                    ],
                    "constraint_overrides": [
                        {"name": "co2_cap", "enabled": False}
                    ],
                    "provider_overrides": [
                        {
                            "selector": {"variant": "heat_pump"},
                            "enabled": False,
                            "investment_cost": 123,
                        }
                    ],
                },
            ],
        },
        "scoping": {"sectors": ["RES"]},
        "roles": [
            {
                "id": "deliver_heat",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "end_use",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "heat_service"}],
            }
        ],
        "variants": [
            {
                "id": "heat_pump",
                "role": "deliver_heat",
                "inputs": [{"commodity": "electricity"}],
                "outputs": [{"commodity": "heat_service"}],
                "efficiency": 0.9,
            }
        ],
        "availability": [
            {"variant": "heat_pump", "regions": ["REG1"], "sectors": ["RES"]}
        ],
        "demands": [
            {
                "commodity": "heat_service",
                "region": "REG1",
                "sector": "RES",
                "interpolation": "interp_extrap",
                "values": {"2020": 100, "2030": 110},
            }
        ],
        "diagnostics": {
            "boundaries": [
                {
                    "id": "heat_end_use",
                    "measure": "end_use_inputs",
                    "selectors": {
                        "stage_in": ["end_use"],
                        "service_in": ["heat_service"],
                    },
                }
            ],
            "metrics": [
                {
                    "id": "heat_switch",
                    "type": "fuel_switch",
                    "boundary": "heat_end_use",
                    "from_case": "baseline",
                    "to_case": "policy",
                }
            ],
        },
    }


def _process_kind_source(explicit_kind: str | None = None) -> dict:
    demand_variant = {"id": "heat_pump", "role": "deliver_heat",
                      "inputs": [{"commodity": "electricity"}],
                      "outputs": [{"commodity": "heat_service"}],
                      "efficiency": 0.9}
    if explicit_kind is not None:
        demand_variant["kind"] = explicit_kind

    return {
        "model": {
            "name": "KindDerivation",
            "regions": ["REG1"],
            "milestone_years": [2020],
            "commodities": [
                {"id": "gas", "type": "fuel"},
                {"id": "electricity", "type": "energy"},
                {"id": "heat_service", "type": "service"},
            ],
        },
        "roles": [
            {
                "id": "generate_power",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "conversion",
                "required_inputs": [{"commodity": "gas"}],
                "required_outputs": [{"commodity": "electricity"}],
            },
            {
                "id": "deliver_heat",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "end_use",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "heat_service"}],
            },
            {
                "id": "store_power",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "storage",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "electricity"}],
            },
        ],
        "variants": [
            {
                "id": "ccgt",
                "role": "generate_power",
                "inputs": [{"commodity": "gas"}],
                "outputs": [{"commodity": "electricity"}],
                "efficiency": 0.55,
            },
            demand_variant,
            {
                "id": "battery",
                "role": "store_power",
                "inputs": [{"commodity": "electricity"}],
                "outputs": [{"commodity": "electricity"}],
                "efficiency": 0.9,
            },
        ],
        "availability": [
            {"variant": "ccgt", "regions": ["REG1"]},
            {"variant": "heat_pump", "regions": ["REG1"]},
            {"variant": "battery", "regions": ["REG1"]},
        ],
    }


def test_exports_metadata_and_resolved_diagnostics():
    source = _minimal_new_syntax_source()
    tableir = compile_vedalang_to_tableir(source)

    assert "metadata_map" in tableir
    processes = tableir["metadata_map"]["processes"]
    assert len(processes) == 1

    only_meta = next(iter(processes.values()))
    assert only_meta["stage"] == "end_use"
    assert only_meta["service"] == "heat_service"
    assert only_meta["kind"] == "device"
    assert only_meta["exclude_from_fuel_switch"] is False

    exported = tableir["diagnostics_export"]
    assert exported["contract"] == "diagnostics_are_solve_independent"
    assert exported["boundaries"][0]["id"] == "heat_end_use"
    assert exported["boundaries"][0]["default_exclusions"] == []
    assert len(exported["boundaries"][0]["processes"]) == 1

def test_end_use_diagnostics_include_all_end_use_variants_by_default():
    source = _minimal_new_syntax_source()
    source["model"]["commodities"].append({"id": "aux_heat_service", "type": "service"})
    source["diagnostics"]["boundaries"][0]["selectors"] = {"stage_in": ["end_use"]}
    source["roles"].append(
        {
            "id": "deliver_aux_heat",
            "activity_unit": "PJ",
            "capacity_unit": "GW",
            "stage": "end_use",
            "required_inputs": [{"commodity": "electricity"}],
            "required_outputs": [{"commodity": "aux_heat_service"}],
        }
    )
    source["variants"].append(
        {
            "id": "resistive_heater",
            "role": "deliver_aux_heat",
            "inputs": [{"commodity": "electricity"}],
            "outputs": [{"commodity": "aux_heat_service"}],
        }
    )
    source["availability"].append(
        {
            "variant": "resistive_heater",
            "regions": ["REG1"],
            "sectors": ["RES"],
        }
    )

    tableir = compile_vedalang_to_tableir(source)
    by_variant = {
        meta["variant"]: meta
        for meta in tableir["metadata_map"]["processes"].values()
    }
    assert by_variant["heat_pump"]["exclude_from_fuel_switch"] is False
    assert by_variant["resistive_heater"]["exclude_from_fuel_switch"] is False

    boundary = tableir["diagnostics_export"]["boundaries"][0]
    assert boundary["default_exclusions"] == []
    assert len(boundary["processes"]) == 2


def test_metadata_map_includes_derived_process_kinds():
    tableir = compile_vedalang_to_tableir(_process_kind_source())

    by_variant = {
        meta["variant"]: meta
        for meta in tableir["metadata_map"]["processes"].values()
    }

    assert by_variant["heat_pump"]["stage"] == "end_use"
    assert by_variant["heat_pump"]["kind"] == "device"
    assert by_variant["heat_pump"]["derived_kind"] == "device"
    assert by_variant["heat_pump"]["kind_source"] == "derived"

    assert by_variant["ccgt"]["stage"] == "conversion"
    assert by_variant["ccgt"]["kind"] == "generator"
    assert by_variant["ccgt"]["derived_kind"] == "generator"
    assert by_variant["ccgt"]["kind_source"] == "derived"

    assert by_variant["battery"]["stage"] == "storage"
    assert by_variant["battery"]["kind"] == "storage"
    assert by_variant["battery"]["derived_kind"] == "storage"
    assert by_variant["battery"]["kind_source"] == "derived"


def test_explicit_kind_is_preserved_and_derived_kind_is_exposed():
    tableir = compile_vedalang_to_tableir(
        _process_kind_source(explicit_kind="network")
    )

    by_variant = {
        meta["variant"]: meta
        for meta in tableir["metadata_map"]["processes"].values()
    }

    demand_meta = by_variant["heat_pump"]
    assert demand_meta["kind"] == "network"
    assert demand_meta["derived_kind"] == "device"
    assert demand_meta["kind_source"] == "explicit"
    assert demand_meta["exclude_from_fuel_switch"] is False


def test_explicit_or_derived_kind_does_not_change_compiled_topology():
    tableir_derived = compile_vedalang_to_tableir(_process_kind_source())
    tableir_explicit = compile_vedalang_to_tableir(
        _process_kind_source(explicit_kind="network")
    )

    assert tableir_derived["files"] == tableir_explicit["files"]


def test_case_overrides_emit_policy_scenario_rows():
    source = _minimal_new_syntax_source()
    tableir = compile_vedalang_to_tableir(source)

    policy_demand_rows = []
    policy_price_rows = []
    policy_variant_rows = []
    policy_has_policies_file = False
    policy_has_tech_file = False

    for file_spec in tableir["files"]:
        path = file_spec["path"].lower()
        if "scen_policy_demands" in path:
            for sheet in file_spec["sheets"]:
                for table in sheet["tables"]:
                    if table["tag"] == "~TFM_DINS-AT":
                        policy_demand_rows.extend(table["rows"])
        if "scen_policy_prices" in path:
            for sheet in file_spec["sheets"]:
                for table in sheet["tables"]:
                    if table["tag"] == "~TFM_DINS-AT":
                        policy_price_rows.extend(table["rows"])
        if "scen_policy_policies" in path:
            policy_has_policies_file = True
        if "scen_policy_technology_assumptions" in path:
            policy_has_tech_file = True
            for sheet in file_spec["sheets"]:
                for table in sheet["tables"]:
                    if table["tag"] == "~TFM_INS":
                        policy_variant_rows.extend(table["rows"])

    assert any(row.get("com_proj") == 999 for row in policy_demand_rows)
    assert any(row.get("com_cstnet") == 77 for row in policy_price_rows)
    assert policy_has_policies_file is False
    assert policy_has_tech_file is True
    assert any(
        row.get("attribute") == "ACT_BND" and row.get("value") == 0
        for row in policy_variant_rows
    )
    assert any(
        row.get("attribute") == "NCAP_BND" and row.get("value") == 0
        for row in policy_variant_rows
    )
    assert any(
        row.get("attribute") == "NCAP_COST" and row.get("value") == 123
        for row in policy_variant_rows
    )

def test_case_overlay_merges_base_with_scale_and_values():
    source = _minimal_new_syntax_source()
    source["model"]["cases"][1]["demand_overrides"] = [
        {
            "commodity": "heat_service",
            "region": "REG1",
            "scale": 2,
            "values": {"2030": 500},
        }
    ]

    tableir = compile_vedalang_to_tableir(source)

    policy_rows = []
    for file_spec in tableir["files"]:
        if "scen_policy_demands" not in file_spec["path"].lower():
            continue
        for sheet in file_spec["sheets"]:
            for table in sheet["tables"]:
                if table["tag"] == "~TFM_DINS-AT":
                    policy_rows.extend(table["rows"])

    values_by_year = {
        row["year"]: row["com_proj"]
        for row in policy_rows
        if row["region"] == "REG1"
    }
    assert values_by_year == {2020: 200, 2030: 500}

def test_case_overlay_duplicate_selector_raises_error():
    source = _minimal_new_syntax_source()
    source["model"]["cases"][1]["demand_overrides"] = [
        {
            "commodity": "heat_service",
            "region": "REG1",
            "values": {"2020": 200},
        },
        {
            "commodity": "heat_service",
            "region": "REG1",
            "values": {"2030": 300},
        },
    ]

    with pytest.raises(VedaLangError, match="Conflicting demand_overrides"):
        compile_vedalang_to_tableir(source)

def test_case_overlay_ambiguous_price_target_raises_error():
    source = _minimal_new_syntax_source()
    source["model"]["scenario_parameters"] = [
        {
            "name": "price_a",
            "type": "commodity_price",
            "commodity": "electricity",
            "interpolation": "interp_extrap",
            "values": {"2020": 10, "2030": 11},
        },
        {
            "name": "price_b",
            "type": "commodity_price",
            "commodity": "electricity",
            "interpolation": "interp_extrap",
            "values": {"2020": 20, "2030": 21},
        },
    ]
    source["model"]["cases"][1]["fuel_price_overrides"] = [
        {
            "commodity": "electricity",
            "values": {"2030": 88},
        }
    ]

    with pytest.raises(VedaLangError, match="Ambiguous fuel_price_overrides"):
        compile_vedalang_to_tableir(source)

def test_case_selection_filters_compiled_outputs():
    source = _minimal_new_syntax_source()
    tableir = compile_vedalang_to_tableir(source, selected_cases=["policy"])

    assert [case["name"] for case in tableir["cases"]] == ["policy"]
    file_paths = [spec["path"] for spec in tableir["files"]]
    assert not any("scen_baseline_" in path for path in file_paths)
    assert any("scen_policy_" in path for path in file_paths)

def test_case_selection_unknown_case_raises_error():
    source = _minimal_new_syntax_source()

    with pytest.raises(VedaLangError, match=r"Unknown case\(s\) requested"):
        compile_vedalang_to_tableir(source, selected_cases=["missing_case"])

def test_case_include_exclude_overlap_raises_error():
    source = _minimal_new_syntax_source()
    source["model"]["cases"][1]["includes"] = ["base_price"]
    source["model"]["cases"][1]["excludes"] = ["base_price"]

    with pytest.raises(VedaLangError, match="includes and excludes"):
        compile_vedalang_to_tableir(source)


def test_provider_overrides_conflicting_targets_raise_error():
    source = _minimal_new_syntax_source()
    source["model"]["cases"][1]["provider_overrides"] = [
        {
            "selector": {"variant": "heat_pump"},
            "enabled": False,
        },
        {
            "selector": {"variant": "heat_pump", "region": "REG1"},
            "enabled": False,
        },
    ]

    with pytest.raises(VedaLangError, match="Conflicting provider_overrides targets"):
        compile_vedalang_to_tableir(source)


def test_provider_overrides_unmatched_selector_raises_error():
    source = _minimal_new_syntax_source()
    source["model"]["cases"][1]["provider_overrides"] = [
        {
            "selector": {"provider": "facility.missing"},
            "enabled": False,
        }
    ]

    with pytest.raises(VedaLangError, match="matched zero processes"):
        compile_vedalang_to_tableir(source)
