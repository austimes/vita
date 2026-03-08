"""Regression tests for the removal of legacy facility/provider lowering."""

from __future__ import annotations

import pytest

from vedalang.compiler.compiler import (
    PublicDSLContractError,
    compile_vedalang_to_tableir,
)


def _legacy_facility_source() -> dict:
    return {
        "model": {
            "name": "FacilityMini",
            "regions": ["AUS"],
            "milestone_years": [2025, 2030],
            "commodities": [
                {"id": "primary:natural_gas", "type": "fuel", "combustible": True},
                {"id": "service:space_heat", "type": "service", "unit": "PJ"},
            ],
            "constraints": [],
        },
        "roles": [
            {
                "id": "provide_space_heat",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "end_use",
                "required_inputs": [{"commodity": "primary:natural_gas"}],
                "required_outputs": [{"commodity": "service:space_heat"}],
            }
        ],
        "facility_templates": [
            {
                "id": "legacy_template",
                "class": "generic",
                "role": "provide_space_heat",
                "sector": "RES",
                "primary_output_commodity": "service:space_heat",
                "variants": [
                    {
                        "id": "gas_boiler",
                        "baseline_mode": "ng",
                        "mode_ladder": ["ng"],
                        "modes": [
                            {
                                "id": "ng",
                                "fuel_in": "primary:natural_gas",
                                "capex": 0,
                                "existing": True,
                            }
                        ],
                    }
                ],
            }
        ],
        "facilities": [
            {
                "id": "legacy_facility",
                "template": "legacy_template",
                "location_ref": "AUS",
                "representation": "individual",
                "cap_base": {"value": 1.0, "unit": "GW"},
                "output_series": {
                    "interpolation": "interp_extrap",
                    "values": {"2025": 1},
                },
            }
        ],
    }


def test_compile_rejects_legacy_facility_template_lowering():
    with pytest.raises(
        PublicDSLContractError,
        match="Legacy pre-v0.2 public DSL blocks are no longer supported",
    ):
        compile_vedalang_to_tableir(_legacy_facility_source(), validate=False)


def test_compile_rejects_legacy_provider_parameter_surfaces():
    source = _legacy_facility_source()
    source["providers"] = [
        {
            "id": "fleet.space_heat.AUS.residential",
            "kind": "fleet",
            "role": "provide_space_heat",
            "region": "AUS",
            "scopes": ["RES"],
            "offerings": [{"variant": "gas_boiler", "modes": ["ng"]}],
        }
    ]

    with pytest.raises(
        PublicDSLContractError,
        match="Legacy pre-v0.2 public DSL blocks are no longer supported",
    ):
        compile_vedalang_to_tableir(source, validate=False)
