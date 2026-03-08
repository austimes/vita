"""Tests for pattern expansion."""
from pathlib import Path

import pytest
import yaml

from tools.veda_patterns import (
    PatternError,
    expand_pattern,
    get_pattern_info,
    list_patterns,
)

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"

EXPECTED_PATTERNS = [
    "add_power_plant",
    "add_renewable_plant",
    "add_energy_commodity",
    "add_emission_commodity",
    "co2_price_trajectory",
]


class TestListPatterns:
    def test_list_returns_patterns(self):
        """Should return list of available patterns."""
        patterns = list_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) >= 5

    def test_all_expected_patterns_exist(self):
        """All documented patterns should exist."""
        patterns = list_patterns()
        for expected in EXPECTED_PATTERNS:
            assert expected in patterns, f"Missing pattern: {expected}"

    def test_get_pattern_info(self):
        """Should return pattern details."""
        info = get_pattern_info("add_power_plant")
        assert "description" in info
        assert "parameters" in info

    def test_get_pattern_info_unknown_raises(self):
        """Unknown pattern should raise PatternError."""
        with pytest.raises(PatternError, match="Unknown pattern"):
            get_pattern_info("nonexistent_pattern")


class TestExpandPattern:
    def test_expand_power_plant(self):
        """Expand add_power_plant pattern."""
        result = expand_pattern(
            "add_power_plant",
            {
                "plant_name": "PP_TEST",
                "fuel_commodity": "COAL",
                "output_commodity": "ELC",
            },
            output_format="vedalang"
        )

        # Should be valid YAML
        parsed = yaml.safe_load(result)
        assert "processes" in parsed
        assert parsed["processes"][0]["name"] == "PP_TEST"

    def test_expand_with_defaults(self):
        """Default values should be applied."""
        result = expand_pattern(
            "add_power_plant",
            {
                "plant_name": "PP_DEFAULT",
                "fuel_commodity": "NG",
                "output_commodity": "ELC",
                # efficiency not specified, should use default
            },
            output_format="vedalang"
        )

        parsed = yaml.safe_load(result)
        # Should have efficiency from default (0.40)
        assert parsed["processes"][0]["efficiency"] == 0.40

    def test_missing_required_param_raises(self):
        """Missing required parameter should raise PatternError."""
        with pytest.raises(PatternError, match="Missing required parameter"):
            expand_pattern(
                "add_power_plant",
                {"fuel_commodity": "NG"},  # Missing plant_name
                output_format="vedalang"
            )

    def test_unknown_pattern_raises(self):
        """Unknown pattern should raise PatternError."""
        with pytest.raises(PatternError, match="Unknown pattern"):
            expand_pattern("nonexistent_pattern", {})

    def test_expand_renewable_plant(self):
        """Expand add_renewable_plant pattern."""
        result = expand_pattern(
            "add_renewable_plant",
            {
                "plant_name": "PP_WIND",
                "output_commodity": "ELC",
                "technology_type": "wind_onshore",
            },
            output_format="vedalang"
        )

        parsed = yaml.safe_load(result)
        assert "processes" in parsed
        assert parsed["processes"][0]["name"] == "PP_WIND"
        assert "RNEW" in parsed["processes"][0]["sets"]

    def test_expand_energy_commodity(self):
        """Expand add_energy_commodity pattern."""
        result = expand_pattern(
            "add_energy_commodity",
            {"name": "NG", "unit": "PJ", "description": "Natural Gas"},
            output_format="vedalang"
        )

        parsed = yaml.safe_load(result)
        assert "commodities" in parsed
        assert parsed["commodities"][0]["name"] == "secondary:NG"
        assert parsed["commodities"][0]["type"] == "energy"

    def test_expand_emission_commodity(self):
        """Expand add_emission_commodity pattern."""
        result = expand_pattern(
            "add_emission_commodity",
            {"name": "CO2"},
            output_format="vedalang"
        )

        parsed = yaml.safe_load(result)
        assert "commodities" in parsed
        assert parsed["commodities"][0]["name"] == "emission:CO2"
        assert parsed["commodities"][0]["type"] == "emission"
        assert parsed["commodities"][0]["unit"] == "Mt"

    def test_expand_co2_price_trajectory_tableir(self):
        """Expand co2_price_trajectory pattern (tableir format)."""
        result = expand_pattern(
            "co2_price_trajectory",
            {"prices": {2025: 50, 2030: 100}, "region": "REG1"},
            output_format="tableir"
        )

        parsed = yaml.safe_load(result)
        assert parsed["tag"] == "~TFM_INS-TS"
        assert len(parsed["rows"]) == 2
        assert parsed["rows"][0]["YEAR"] == 2025
        assert parsed["rows"][0]["COST"] == 50

    def test_co2_price_trajectory_no_vedalang_template(self):
        """co2_price_trajectory should not have a vedalang template."""
        with pytest.raises(PatternError, match="does not have a vedalang template"):
            expand_pattern(
                "co2_price_trajectory",
                {"prices": {2025: 50}},
                output_format="vedalang"
            )

    def test_invalid_output_format_raises(self):
        """Invalid output format should raise PatternError."""
        with pytest.raises(PatternError, match="Invalid output_format"):
            expand_pattern("add_power_plant", {}, output_format="invalid")


class TestFullPipeline:
    def test_expand_compile_rejects_legacy_pattern_output(self):
        """Legacy pattern output should be rejected by the v0.2-only compiler."""

        from vedalang.compiler import (
            PublicDSLContractError,
            compile_vedalang_to_tableir,
        )

        # Expand pattern - use namespace naming convention
        process_yaml = expand_pattern(
            "add_power_plant",
            {
                "plant_name": "PP_CCGT",
                "fuel_commodity": "primary:natural_gas",
                "output_commodity": "secondary:electricity",
                "efficiency": 0.55,
            }
        )
        process_data = yaml.safe_load(process_yaml)

        # Also expand commodities - pattern adds secondary: prefix
        elc_yaml = expand_pattern(
            "add_energy_commodity",
            {"name": "electricity", "unit": "PJ"}
        )
        elc_data = yaml.safe_load(elc_yaml)
        # Primary fuels are modeled with primary:* namespace and type=fuel.
        ng_data = {
            "commodities": [
                {"name": "primary:natural_gas", "type": "fuel", "unit": "PJ"}
            ]
        }

        # Build full VedaLang model
        model = {
            "model": {
                "name": "PatternTest",
                "regions": ["REG1"],
                "commodities": elc_data["commodities"] + ng_data["commodities"],
                "processes": process_data["processes"],
            }
        }

        with pytest.raises(
            PublicDSLContractError,
            match="Legacy pre-v0.2 public DSL blocks are no longer supported",
        ):
            compile_vedalang_to_tableir(model)
