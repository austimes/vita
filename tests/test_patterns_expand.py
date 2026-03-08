"""Tests for the archived pattern-expansion helpers."""

import pytest
import yaml

from tools.veda_patterns import (
    PatternError,
    expand_pattern,
    get_pattern_info,
    list_patterns,
)

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
    def test_vedalang_templates_are_archive_only(self):
        """vedalang output is intentionally blocked until patterns are ported."""
        with pytest.raises(
            PatternError,
            match="archived pre-v0.2 public DSL",
        ):
            expand_pattern(
                "add_power_plant",
                {
                    "plant_name": "PP_TEST",
                    "fuel_commodity": "COAL",
                    "output_commodity": "ELC",
                },
                output_format="vedalang",
            )

    def test_missing_required_param_raises(self):
        """Missing required parameter should raise PatternError."""
        with pytest.raises(PatternError, match="Missing required parameter"):
            expand_pattern(
                "co2_price_trajectory",
                {"region": "REG1"},
                output_format="tableir",
            )

    def test_unknown_pattern_raises(self):
        """Unknown pattern should raise PatternError."""
        with pytest.raises(PatternError, match="Unknown pattern"):
            expand_pattern("nonexistent_pattern", {})

    def test_expand_co2_price_trajectory_tableir(self):
        """Expand co2_price_trajectory pattern (tableir format)."""
        result = expand_pattern(
            "co2_price_trajectory",
            {"prices": {2025: 50, 2030: 100}, "region": "REG1"},
            output_format="tableir",
        )

        parsed = yaml.safe_load(result)
        assert parsed["tag"] == "~TFM_INS-TS"
        assert len(parsed["rows"]) == 2
        assert parsed["rows"][0]["YEAR"] == 2025
        assert parsed["rows"][0]["COST"] == 50

    def test_co2_price_trajectory_vedalang_is_also_archive_only(self):
        with pytest.raises(PatternError, match="archived pre-v0.2 public DSL"):
            expand_pattern(
                "co2_price_trajectory",
                {"prices": {2025: 50}},
                output_format="vedalang",
            )

    def test_invalid_output_format_raises(self):
        """Invalid output format should raise PatternError."""
        with pytest.raises(PatternError, match="Invalid output_format"):
            expand_pattern("add_power_plant", {}, output_format="invalid")
