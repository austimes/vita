"""Tests for template_resolver module."""

import pytest

from vedalang.compiler.template_resolver import ResolvedProcess, TemplateResolver


@pytest.fixture
def ccgt_template():
    """Sample CCGT generator template."""
    return {
        "name": "CCGT_GEN",
        "technology": "CCG",
        "role": "GEN",
        "sets": ["ELE"],
        "primary_commodity_group": "NRGO",
        "inputs": [{"commodity": "NG"}],
        "outputs": [{"commodity": "ELC"}],
        "efficiency": 0.55,
        "investment_cost": 800,
        "fixed_om_cost": 20,
        "variable_om_cost": 2,
        "lifetime": 40,
        "sankey_stage": "GEN",
        "tags": {"fuel": "gas", "category": "thermal"},
    }


@pytest.fixture
def demand_template():
    """Sample end-use service template (requires segment)."""
    return {
        "name": "RES_HEATING",
        "technology": "RHT",
        "role": "EUS",
        "sets": ["DMD"],
        "primary_commodity_group": "DEMO",
        "inputs": [{"commodity": "NG"}],
        "outputs": [{"commodity": "RSD"}],
        "efficiency": 0.9,
        "lifetime": 20,
    }


@pytest.fixture
def regions():
    """Sample regions list."""
    return ["NEM_EAST", "NEM_SOUTH", "WA"]


class TestTemplateResolver:
    """Tests for TemplateResolver class."""

    def test_simple_resolution(self, ccgt_template, regions):
        """Test basic template + instance resolution."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "CCGT_East",
            "template": "CCGT_GEN",
            "region": "NEM_EAST",
        }

        result = resolver.resolve(instance)

        assert isinstance(result, ResolvedProcess)
        assert result.veda_id == "P:CCG:GEN:NEM_EAST"
        assert result.instance_name == "CCGT_East"
        assert result.template_name == "CCGT_GEN"
        assert result.region == "NEM_EAST"
        assert result.technology == "CCG"
        assert result.role == "GEN"
        assert result.sets == ["ELE"]
        assert result.efficiency == 0.55
        assert result.investment_cost == 800
        assert result.lifetime == 40

    def test_multiple_instances_same_template(self, ccgt_template, regions):
        """Test multiple instances from same template in different regions."""
        resolver = TemplateResolver([ccgt_template], regions)

        instances = [
            {"name": "CCGT_East", "template": "CCGT_GEN", "region": "NEM_EAST"},
            {"name": "CCGT_South", "template": "CCGT_GEN", "region": "NEM_SOUTH"},
            {"name": "CCGT_West", "template": "CCGT_GEN", "region": "WA"},
        ]

        results = resolver.resolve_all(instances)

        assert len(results) == 3
        assert results[0].veda_id == "P:CCG:GEN:NEM_EAST"
        assert results[1].veda_id == "P:CCG:GEN:NEM_SOUTH"
        assert results[2].veda_id == "P:CCG:GEN:WA"

    def test_instance_cost_override(self, ccgt_template, regions):
        """Test instance overrides template cost values."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "CCGT_Expensive",
            "template": "CCGT_GEN",
            "region": "NEM_EAST",
            "investment_cost": 1200,
            "fixed_om_cost": 30,
        }

        result = resolver.resolve(instance)

        assert result.investment_cost == 1200
        assert result.fixed_om_cost == 30
        assert result.variable_om_cost == 2

    def test_eus_requires_segment(self, demand_template, regions):
        """Test EUS role requires segment - error if missing."""
        resolver = TemplateResolver([demand_template], regions)

        instance = {
            "name": "Heater_NoSegment",
            "template": "RES_HEATING",
            "region": "NEM_EAST",
        }

        with pytest.raises(ValueError, match="requires a segment"):
            resolver.resolve(instance)

    def test_eus_with_segment(self, demand_template, regions):
        """Test EUS role works with segment provided."""
        resolver = TemplateResolver([demand_template], regions)

        instance = {
            "name": "Heater_Residential",
            "template": "RES_HEATING",
            "region": "NEM_EAST",
            "segment": "RES.ALL",
        }

        result = resolver.resolve(instance)

        assert result.veda_id == "P:RHT:EUS:NEM_EAST:RES.ALL"
        assert result.segment == "RES.ALL"

    def test_unknown_template_error(self, ccgt_template, regions):
        """Test error when template not found."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "Unknown",
            "template": "NONEXISTENT",
            "region": "NEM_EAST",
        }

        with pytest.raises(ValueError, match="Unknown template: 'NONEXISTENT'"):
            resolver.resolve(instance)

    def test_unknown_region_error(self, ccgt_template, regions):
        """Test error when region not in model.regions."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "CCGT_Invalid",
            "template": "CCGT_GEN",
            "region": "INVALID_REGION",
        }

        with pytest.raises(ValueError, match="Unknown region: 'INVALID_REGION'"):
            resolver.resolve(instance)

    def test_tag_merging(self, ccgt_template, regions):
        """Test tags are merged with instance overriding template."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "CCGT_Tagged",
            "template": "CCGT_GEN",
            "region": "NEM_EAST",
            "tags": {"fuel": "natural_gas", "owner": "utility"},
        }

        result = resolver.resolve(instance)

        assert result.tags["fuel"] == "natural_gas"
        assert result.tags["category"] == "thermal"
        assert result.tags["owner"] == "utility"

    def test_variant_in_id(self, ccgt_template, regions):
        """Test variant is included in generated VEDA ID."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "CCGT_CCS",
            "template": "CCGT_GEN",
            "region": "NEM_EAST",
            "variant": "CCS90",
        }

        result = resolver.resolve(instance)

        assert result.veda_id == "P:CCG:GEN:NEM_EAST:CCS90"
        assert result.variant == "CCS90"

    def test_vintage_in_id(self, ccgt_template, regions):
        """Test vintage is included in generated VEDA ID."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "CCGT_Existing",
            "template": "CCGT_GEN",
            "region": "NEM_EAST",
            "vintage": "EXIST",
        }

        result = resolver.resolve(instance)

        assert result.veda_id == "P:CCG:GEN:NEM_EAST:EXIST"
        assert result.vintage == "EXIST"

    def test_instance_bounds(self, ccgt_template, regions):
        """Test instance-only attributes like bounds."""
        resolver = TemplateResolver([ccgt_template], regions)

        instance = {
            "name": "CCGT_Bounded",
            "template": "CCGT_GEN",
            "region": "NEM_EAST",
            "cap_bound": {"up": 10},
            "ncap_bound": {"up": 2},
            "existing_capacity": [{"vintage": 2015, "capacity": 1.5}],
        }

        result = resolver.resolve(instance)

        assert result.cap_bound == {"up": 10}
        assert result.ncap_bound == {"up": 2}
        assert result.existing_capacity == [{"vintage": 2015, "capacity": 1.5}]

    def test_resolve_all_collects_errors(self, ccgt_template, regions):
        """Test resolve_all collects all errors."""
        resolver = TemplateResolver([ccgt_template], regions)

        instances = [
            {"name": "Bad1", "template": "NONEXISTENT", "region": "NEM_EAST"},
            {"name": "Bad2", "template": "CCGT_GEN", "region": "INVALID"},
        ]

        with pytest.raises(ValueError) as exc_info:
            resolver.resolve_all(instances)

        error_msg = str(exc_info.value)
        assert "Bad1" in error_msg
        assert "Bad2" in error_msg
        assert "Unknown template" in error_msg
        assert "Unknown region" in error_msg

    def test_shorthand_input_output(self, regions):
        """Test template with shorthand input/output (single string)."""
        template = {
            "name": "SIMPLE",
            "technology": "SIM",
            "role": "GEN",
            "input": "NG",
            "output": "ELC",
            "efficiency": 0.5,
        }
        resolver = TemplateResolver([template], regions)

        instance = {
            "name": "Simple_East",
            "template": "SIMPLE",
            "region": "NEM_EAST",
        }

        result = resolver.resolve(instance)

        assert result.inputs == [{"commodity": "NG"}]
        assert result.outputs == [{"commodity": "ELC"}]
