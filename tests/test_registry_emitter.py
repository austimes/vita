"""Tests for the registry emitter."""

import json

import pytest

from vedalang.compiler.registry_emitter import (
    RegistryEmitter,
)
from vedalang.compiler.template_resolver import ResolvedProcess
from vedalang.identity.registry import AbbreviationRegistry


@pytest.fixture
def registry():
    """Abbreviation registry fixture."""
    return AbbreviationRegistry()


@pytest.fixture
def emitter(registry):
    """Registry emitter fixture."""
    return RegistryEmitter(registry)


class TestCommodityEmission:
    """Tests for commodity registry entry emission."""

    def test_emit_energy_commodity_with_key_lookup(self, emitter, registry):
        """Test emitting a canonical carrier commodity with key lookup."""
        commodity = {
            "name": "ELC",
            "type": "energy",
            "unit": "PJ",
            "description": "Electricity",
        }

        entry = emitter.emit_commodity(commodity)

        assert entry.id == "secondary:ELC"
        assert entry.kind == "carrier"
        assert entry.code == "ELC"
        assert entry.context is None
        assert entry.unit == "PJ"
        assert entry.description == "Electricity"

        abbrev = registry.find_commodity_by_code("ELC")
        if abbrev:
            assert entry.key == abbrev.key
        else:
            assert entry.key is None

    def test_emit_service_commodity_with_context(self, emitter):
        """Test emitting a canonical service commodity with context."""
        commodity = {
            "name": "RSD",
            "type": "demand",
            "context": "RES.ALL",
            "unit": "PJ",
            "description": "Residential demand",
        }

        entry = emitter.emit_commodity(commodity)

        assert entry.id == "service:RSD"
        assert entry.kind == "service"
        assert entry.code == "RSD"
        assert entry.context == "RES.ALL"
        assert entry.unit == "PJ"

    def test_emit_emission_commodity(self, emitter):
        """Test emitting a canonical emission commodity."""
        commodity = {
            "name": "CO2",
            "type": "emission",
            "unit": "Mt",
            "description": "Carbon dioxide emissions",
        }

        entry = emitter.emit_commodity(commodity)

        assert entry.id == "emission:CO2"
        assert entry.kind == "emission"
        assert entry.code == "CO2"
        assert entry.context is None
        assert entry.unit == "Mt"


class TestProcessEmission:
    """Tests for process registry entry emission."""

    def test_emit_canonical_provider_process(self, emitter):
        """Canonical provider symbols should parse without legacy parser paths."""
        process = {
            "name": (
                "FAC::port_kembla_steel::ROLE::steel_primary_production::"
                "VAR::bf_bof::MODE::coal"
            ),
            "region": "NSW",
            "description": "Blast furnace route",
        }

        entry = emitter.emit_process(process)

        assert entry.id.startswith("FAC::")
        assert entry.parsed["provider_kind"] == "FAC"
        assert entry.parsed["provider_id"] == "port_kembla_steel"
        assert entry.parsed["role"] == "steel_primary_production"
        assert entry.parsed["variant"] == "bf_bof"
        assert entry.parsed["mode"] == "coal"
        assert entry.region == "NSW"

    def test_emit_inline_process_parsed_from_id(self, emitter):
        """Test emitting an inline process with full VEDA ID."""
        process = {
            "name": "P:CCG:GEN:NEM_EAST",
            "description": "Combined cycle gas turbine",
            "sets": ["ELE"],
            "sankey_stage": "GEN",
            "tags": {"fuel": "gas"},
        }

        entry = emitter.emit_process(process)

        assert entry.id == "P:CCG:GEN:NEM_EAST"
        assert entry.template is None
        assert entry.parsed["technology"] == "CCG"
        assert entry.parsed["role"] == "GEN"
        assert entry.parsed["geo"] == "NEM_EAST"
        assert entry.region == "NEM_EAST"
        assert entry.technology == "CCG"
        assert entry.role == "GEN"
        assert entry.sankey_stage == "GEN"
        assert entry.description == "Combined cycle gas turbine"
        assert entry.tags == {"fuel": "gas"}

    def test_emit_inline_process_with_segment(self, emitter):
        """Test emitting an EUS process with segment."""
        process = {
            "name": "P:DEM:EUS:NEM_EAST:RES.ALL",
            "description": "Residential demand device",
            "sets": ["DMD"],
        }

        entry = emitter.emit_process(process)

        assert entry.id == "P:DEM:EUS:NEM_EAST:RES.ALL"
        assert entry.parsed["role"] == "EUS"
        assert entry.parsed["segment"] == "RES.ALL"
        assert entry.segment == "RES.ALL"

    def test_emit_resolved_process_from_template(self, emitter):
        """Test emitting a process from ResolvedProcess."""
        resolved = ResolvedProcess(
            veda_id="P:CCG:GEN:NEM_EAST",
            instance_name="ccgt_east",
            template_name="CCGT_GEN",
            region="NEM_EAST",
            technology="CCG",
            role="GEN",
            segment=None,
            variant=None,
            vintage=None,
            sankey_stage="GEN",
            tags={"fuel": "gas"},
        )

        entry = emitter.emit_resolved_process(resolved)

        assert entry.id == "P:CCG:GEN:NEM_EAST"
        assert entry.template == "CCGT_GEN"
        assert entry.parsed["technology"] == "CCG"
        assert entry.parsed["role"] == "GEN"
        assert entry.parsed["geo"] == "NEM_EAST"
        assert entry.region == "NEM_EAST"
        assert entry.technology == "CCG"
        assert entry.role == "GEN"
        assert entry.sankey_stage == "GEN"
        assert entry.tags == {"fuel": "gas"}


class TestModelEmission:
    """Tests for full model registry emission."""

    def test_emit_full_model(self, emitter):
        """Test emitting a complete model registry."""
        model = {
            "model": {
                "name": "TestModel",
                "regions": ["NEM_EAST", "NEM_SOUTH"],
                "commodities": [
                    {"name": "ELC", "type": "energy", "unit": "PJ"},
                    {"name": "CO2", "type": "emission", "unit": "Mt"},
                ],
                "processes": [
                    {"name": "PP_CCGT", "sets": ["ELE"], "description": "CCGT"},
                ],
            }
        }

        registry = emitter.emit_model(model)

        assert registry.model_name == "TestModel"
        assert registry.regions == ["NEM_EAST", "NEM_SOUTH"]
        assert len(registry.commodities) == 2
        assert len(registry.processes) == 1

        assert registry.commodities[0].id == "secondary:ELC"
        assert registry.commodities[1].id == "emission:CO2"

    def test_emit_model_with_resolved_processes(self, emitter):
        """Test emitting model with resolved processes."""
        model = {
            "model": {
                "name": "TestModel",
                "regions": ["NEM_EAST"],
                "commodities": [
                    {"name": "ELC", "type": "energy", "unit": "PJ"},
                ],
                "processes": [],
            }
        }

        resolved_processes = [
            ResolvedProcess(
                veda_id="P:CCG:GEN:NEM_EAST",
                instance_name="ccgt_east",
                template_name="CCGT_GEN",
                region="NEM_EAST",
                technology="CCG",
                role="GEN",
            ),
        ]

        registry = emitter.emit_model(model, resolved_processes)

        assert len(registry.processes) == 1
        assert registry.processes[0].id == "P:CCG:GEN:NEM_EAST"
        assert registry.processes[0].template == "CCGT_GEN"


class TestJSONSerialization:
    """Tests for JSON serialization."""

    def test_json_serialization_roundtrip(self, emitter):
        """Test JSON serialization and deserialization."""
        model = {
            "model": {
                "name": "RoundtripTest",
                "regions": ["SINGLE"],
                "commodities": [
                    {
                        "name": "ELC",
                        "type": "energy",
                        "unit": "PJ",
                        "description": "Electricity",
                    },
                    {
                        "name": "RSD",
                        "type": "demand",
                        "context": "RES.ALL",
                        "unit": "PJ",
                    },
                ],
                "processes": [
                    {
                        "name": "P:CCG:GEN:SINGLE",
                        "description": "CCGT",
                        "sets": ["ELE"],
                    },
                ],
            }
        }

        registry = emitter.emit_model(model)
        json_str = emitter.to_json(registry)

        parsed = json.loads(json_str)

        assert parsed["model_name"] == "RoundtripTest"
        assert parsed["regions"] == ["SINGLE"]
        assert len(parsed["commodities"]) == 2
        assert len(parsed["processes"]) == 1

        assert parsed["commodities"][0]["id"] == "secondary:ELC"
        assert parsed["commodities"][0]["kind"] == "carrier"
        assert parsed["commodities"][1]["id"] == "service:RSD"
        assert parsed["commodities"][1]["kind"] == "service"

        assert parsed["processes"][0]["id"] == "P:CCG:GEN:SINGLE"
        assert parsed["processes"][0]["parsed"]["technology"] == "CCG"

    def test_json_includes_all_fields(self, emitter):
        """Test that JSON output includes all expected fields."""
        model = {
            "model": {
                "name": "FieldsTest",
                "regions": ["R1"],
                "commodities": [{"name": "X", "type": "energy", "unit": "PJ"}],
                "processes": [],
            }
        }

        registry = emitter.emit_model(model)
        json_str = emitter.to_json(registry)
        parsed = json.loads(json_str)

        commodity = parsed["commodities"][0]
        expected_fields = [
            "id", "kind", "code", "key", "context", "unit", "description", "tags"
        ]
        for field in expected_fields:
            assert field in commodity, f"Missing field: {field}"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_commodity_without_type_defaults_to_carrier(self, emitter):
        """Test that commodities without type default to carrier semantics."""
        commodity = {"name": "X", "unit": "PJ"}
        entry = emitter.emit_commodity(commodity)
        assert entry.id == "secondary:X"
        assert entry.kind == "carrier"

    def test_process_without_sets_infers_gen_role(self, emitter):
        """Test that processes without sets default to GEN role."""
        process = {"name": "SomeProcess"}
        entry = emitter.emit_process(process)
        assert entry.role == "GEN"

    def test_empty_model(self, emitter):
        """Test emitting an empty model."""
        model = {
            "model": {
                "name": "Empty",
                "regions": [],
                "commodities": [],
                "processes": [],
            }
        }

        registry = emitter.emit_model(model)

        assert registry.model_name == "Empty"
        assert registry.regions == []
        assert registry.commodities == []
        assert registry.processes == []
