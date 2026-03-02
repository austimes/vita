"""Tests for demands lowering.

Tests the P3 implementation of vedalang-awg: demands → scenario parameters.
"""

import pytest

from vedalang.compiler.demands import DemandError, compile_demands
from vedalang.compiler.naming import NamingRegistry


class TestCompileDemandsBasic:
    """Basic tests for compile_demands()."""

    def test_empty_demands(self):
        """Empty demands returns empty list."""
        assert compile_demands({}, {}, []) == []
        assert compile_demands({"demands": []}, {}, []) == []
        assert compile_demands({"demands": None}, {}, []) == []

    def test_single_demand(self):
        """Single demand is compiled correctly."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "SINGLE",
                    "sector": "RES",
                    "values": {"2020": 10, "2030": 15},
                }
            ]
        }
        commodities = {
            "lighting": {"id": "lighting", "kind": "service", "tradable": False}
        }
        segment_keys = ["RES", "COM"]

        result = compile_demands(model, commodities, segment_keys)

        assert len(result) == 1
        param = result[0]
        assert param["name"] == "demand_lighting_SINGLE_RES"
        assert param["type"] == "demand_projection"
        assert param["commodity"] == "lighting@RES"
        assert param["region"] == "SINGLE"
        assert param["values"] == {"2020": 10, "2030": 15}
        assert param["interpolation"] == "interp_extrap"
        assert param["scope"] == "RES"

    def test_demand_with_segment_field(self):
        """Demand using 'segment' field (fine granularity)."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "scope": "RES.lighting",
                    "values": {"2020": 5},
                }
            ]
        }
        commodities = {
            "lighting": {"id": "lighting", "kind": "service", "tradable": False}
        }
        segment_keys = ["RES.lighting", "RES.heating"]

        result = compile_demands(model, commodities, segment_keys)

        param = result[0]
        assert param["name"] == "demand_lighting_R1_RES_lighting"
        assert param["commodity"] == "lighting@RES.lighting"
        assert param["scope"] == "RES.lighting"

    def test_demand_no_segment_flat_model(self):
        """Demand without segment in flat model (no segments)."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "SINGLE",
                    "values": {"2020": 10},
                }
            ]
        }
        commodities = {
            "lighting": {"id": "lighting", "kind": "service", "tradable": False}
        }
        segment_keys = []

        result = compile_demands(model, commodities, segment_keys)

        param = result[0]
        assert param["name"] == "demand_lighting_SINGLE_ALL"
        assert param["commodity"] == "lighting"
        assert "scope" not in param

    def test_custom_interpolation(self):
        """Demand with custom interpolation mode."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "sector": "RES",
                    "values": {"2020": 10},
                    "interpolation": "none",
                }
            ]
        }
        commodities = {"lighting": {"id": "lighting", "kind": "service"}}
        segment_keys = ["RES"]

        result = compile_demands(model, commodities, segment_keys)

        assert result[0]["interpolation"] == "none"

    def test_multiple_demands(self):
        """Multiple demands are compiled."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "sector": "RES",
                    "values": {"2020": 10},
                },
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "sector": "COM",
                    "values": {"2020": 20},
                },
                {
                    "commodity": "heating",
                    "region": "R1",
                    "sector": "RES",
                    "values": {"2020": 50},
                },
            ]
        }
        commodities = {
            "lighting": {"id": "lighting", "kind": "service"},
            "heating": {"id": "heating", "kind": "service"},
        }
        segment_keys = ["RES", "COM"]

        result = compile_demands(model, commodities, segment_keys)

        assert len(result) == 3
        names = {p["name"] for p in result}
        assert "demand_lighting_R1_RES" in names
        assert "demand_lighting_R1_COM" in names
        assert "demand_heating_R1_RES" in names


class TestCompileDemandsErrors:
    """Error handling tests for compile_demands()."""

    def test_unknown_commodity_raises(self):
        """Unknown commodity in demand raises DemandError."""
        model = {
            "demands": [
                {
                    "commodity": "unknown",
                    "region": "R1",
                    "values": {"2020": 10},
                }
            ]
        }

        with pytest.raises(DemandError, match="Unknown commodity in demand: unknown"):
            compile_demands(model, {}, [])

    def test_non_service_commodity_raises(self):
        """Non-service commodity in demand raises DemandError."""
        model = {
            "demands": [
                {
                    "commodity": "electricity",
                    "region": "R1",
                    "values": {"2020": 10},
                }
            ]
        }
        commodities = {"electricity": {"id": "electricity", "kind": "carrier"}}

        with pytest.raises(
            DemandError, match="Demands must reference service commodities"
        ):
            compile_demands(model, commodities, [])

    def test_error_includes_commodity_kind(self):
        """Error message includes the actual commodity kind."""
        model = {
            "demands": [{"commodity": "gas", "region": "R1", "values": {"2020": 1}}]
        }
        commodities = {"gas": {"id": "gas", "kind": "carrier"}}

        with pytest.raises(DemandError, match=r"kind=carrier"):
            compile_demands(model, commodities, [])


class TestCompileDemandsWithRegistry:
    """Tests for compile_demands() with NamingRegistry."""

    def test_registry_used_for_commodity_symbol(self):
        """Registry is used for commodity symbol generation."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "sector": "RES",
                    "values": {"2020": 10},
                }
            ]
        }
        commodities = {"lighting": {"id": "lighting", "kind": "service"}}
        segment_keys = ["RES"]
        registry = NamingRegistry()

        result = compile_demands(model, commodities, segment_keys, registry)

        param = result[0]
        assert param["commodity"] == "lighting@RES"

        all_comms = registry.get_all_commodities()
        assert ("lighting", "RES") in all_comms

    def test_registry_caches_symbols(self):
        """Registry caches symbols across calls."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "sector": "RES",
                    "values": {"2020": 10},
                },
                {
                    "commodity": "lighting",
                    "region": "R2",
                    "sector": "RES",
                    "values": {"2020": 20},
                },
            ]
        }
        commodities = {"lighting": {"id": "lighting", "kind": "service"}}
        segment_keys = ["RES"]
        registry = NamingRegistry()

        result = compile_demands(model, commodities, segment_keys, registry)

        assert result[0]["commodity"] == result[1]["commodity"]
        all_comms = registry.get_all_commodities()
        assert len(all_comms) == 1


class TestCompileDemandsSegmentScoping:
    """Tests for segment scoping in demands."""

    def test_sector_vs_segment_field(self):
        """'sector' and 'segment' fields both work for scoping."""
        commodities = {"lighting": {"id": "lighting", "kind": "service"}}

        model_sector = {
            "demands": [
                {"commodity": "lighting", "region": "R1", "sector": "RES", "values": {}}
            ]
        }
        model_segment = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "scope": "RES",
                    "values": {},
                }
            ]
        }

        result_sector = compile_demands(model_sector, commodities, ["RES"])
        result_segment = compile_demands(model_segment, commodities, ["RES"])

        assert result_sector[0]["commodity"] == result_segment[0]["commodity"]

    def test_segment_takes_precedence(self):
        """If both sector and segment present, segment wins."""
        model = {
            "demands": [
                {
                    "commodity": "lighting",
                    "region": "R1",
                    "sector": "RES",
                    "scope": "RES.lighting",
                    "values": {},
                }
            ]
        }
        commodities = {"lighting": {"id": "lighting", "kind": "service"}}
        segment_keys = ["RES.lighting"]

        result = compile_demands(model, commodities, segment_keys)

        assert result[0]["commodity"] == "lighting@RES.lighting"
        assert result[0]["scope"] == "RES.lighting"
