"""Tests for the VedaLang abbreviation registry."""


import pytest

from vedalang.identity.registry import (
    AbbreviationRegistry,
    CommodityAbbrev,
    CommodityKind,
    RoleAbbrev,
    TechAbbrev,
)


class TestRegistryLoading:
    """Test that all registry files load correctly."""

    def test_registry_loads_without_error(self):
        """Registry should load all YAML files without raising."""
        registry = AbbreviationRegistry()
        assert registry is not None

    def test_commodities_loaded(self):
        """All expected commodities should be loaded."""
        registry = AbbreviationRegistry()

        tradable = [
            "electricity", "thermal_coal", "natural_gas",
            "hydrogen", "steam", "limestone",
            "carbon_dioxide_captured",
        ]
        for key in tradable:
            abbrev = registry.find_commodity_by_key(key)
            assert abbrev is not None, f"Missing tradable commodity: {key}"
            assert abbrev.kind == CommodityKind.TRADABLE

        services = [
            "lighting", "space_heating", "space_cooling",
            "passenger_kilometres",
            "residential_final_energy", "commercial_final_energy",
            "industrial_final_energy", "transport_final_energy",
        ]
        for key in services:
            abbrev = registry.find_commodity_by_key(key)
            assert abbrev is not None, f"Missing service commodity: {key}"
            assert abbrev.kind == CommodityKind.SERVICE

        emissions = ["carbon_dioxide", "methane", "nitrous_oxide"]
        for key in emissions:
            abbrev = registry.find_commodity_by_key(key)
            assert abbrev is not None, f"Missing emission commodity: {key}"
            assert abbrev.kind == CommodityKind.EMISSION

    def test_technologies_loaded(self):
        """All expected technologies should be loaded."""
        registry = AbbreviationRegistry()

        techs = [
            "coal_steam_turbine", "combined_cycle_gas", "photovoltaic",
            "led_lighting", "refinery_crude_distillation", "post_combustion_capture",
            "steam_methane_reforming", "electrolysis_h2", "onshore_wind",
            "generic_demand_device", "import_supply"
        ]
        for key in techs:
            abbrev = registry.find_tech_by_key(key)
            assert abbrev is not None, f"Missing technology: {key}"

    def test_roles_loaded(self):
        """All expected roles should be loaded."""
        registry = AbbreviationRegistry()

        roles = ["generation", "end_use_service", "conversion", "extraction",
                 "trade", "storage", "capture", "sequestration"]
        for key in roles:
            abbrev = registry.find_role_by_key(key)
            assert abbrev is not None, f"Missing role: {key}"


class TestLookupByKey:
    """Test lookup by semantic key."""

    def test_commodity_lookup_by_key(self):
        """Should find commodity by key."""
        registry = AbbreviationRegistry()
        abbrev = registry.find_commodity_by_key("electricity")
        assert abbrev is not None
        assert abbrev.code == "ELC"
        assert abbrev.kind == CommodityKind.TRADABLE

    def test_tech_lookup_by_key(self):
        """Should find technology by key."""
        registry = AbbreviationRegistry()
        abbrev = registry.find_tech_by_key("combined_cycle_gas")
        assert abbrev is not None
        assert abbrev.code == "CCG"

    def test_role_lookup_by_key(self):
        """Should find role by key."""
        registry = AbbreviationRegistry()
        abbrev = registry.find_role_by_key("generation")
        assert abbrev is not None
        assert abbrev.code == "GEN"

    def test_missing_key_returns_none(self):
        """Unknown keys should return None, not raise."""
        registry = AbbreviationRegistry()
        assert registry.find_commodity_by_key("nonexistent") is None
        assert registry.find_tech_by_key("nonexistent") is None
        assert registry.find_role_by_key("nonexistent") is None


class TestLookupByCode:
    """Test lookup by short code."""

    def test_commodity_lookup_by_code(self):
        """Should find commodity by code."""
        registry = AbbreviationRegistry()
        abbrev = registry.find_commodity_by_code("H2")
        assert abbrev is not None
        assert abbrev.key == "hydrogen"
        assert abbrev.kind == CommodityKind.TRADABLE

    def test_tech_lookup_by_code(self):
        """Should find technology by code."""
        registry = AbbreviationRegistry()
        abbrev = registry.find_tech_by_code("PV")
        assert abbrev is not None
        assert abbrev.key == "photovoltaic"

    def test_role_lookup_by_code(self):
        """Should find role by code."""
        registry = AbbreviationRegistry()
        abbrev = registry.find_role_by_code("EUS")
        assert abbrev is not None
        assert abbrev.key == "end_use_service"

    def test_missing_code_returns_none(self):
        """Unknown codes should return None, not raise."""
        registry = AbbreviationRegistry()
        assert registry.find_commodity_by_code("XXX") is None
        assert registry.find_tech_by_code("XXX") is None
        assert registry.find_role_by_code("XXX") is None


class TestRoundTrip:
    """Test that key -> code -> key round-trips correctly."""

    def test_commodity_round_trip(self):
        """All commodities should round-trip correctly."""
        registry = AbbreviationRegistry()
        for abbrev in registry.all_commodities():
            by_key = registry.find_commodity_by_key(abbrev.key)
            by_code = registry.find_commodity_by_code(abbrev.code)
            assert by_key == by_code == abbrev

    def test_tech_round_trip(self):
        """All technologies should round-trip correctly."""
        registry = AbbreviationRegistry()
        for abbrev in registry.all_technologies():
            by_key = registry.find_tech_by_key(abbrev.key)
            by_code = registry.find_tech_by_code(abbrev.code)
            assert by_key == by_code == abbrev

    def test_role_round_trip(self):
        """All roles should round-trip correctly."""
        registry = AbbreviationRegistry()
        for abbrev in registry.all_roles():
            by_key = registry.find_role_by_key(abbrev.key)
            by_code = registry.find_role_by_code(abbrev.code)
            assert by_key == by_code == abbrev


class TestDuplicateDetection:
    """Test that duplicate codes are detected and rejected."""

    def test_no_duplicate_codes_in_commodities(self):
        """Commodity codes should be unique across all kinds."""
        registry = AbbreviationRegistry()
        codes = [c.code for c in registry.all_commodities()]
        assert len(codes) == len(set(codes)), "Duplicate commodity codes found"

    def test_no_duplicate_codes_in_technologies(self):
        """Technology codes should be unique."""
        registry = AbbreviationRegistry()
        codes = [t.code for t in registry.all_technologies()]
        assert len(codes) == len(set(codes)), "Duplicate technology codes found"

    def test_no_duplicate_codes_in_roles(self):
        """Role codes should be unique."""
        registry = AbbreviationRegistry()
        codes = [r.code for r in registry.all_roles()]
        assert len(codes) == len(set(codes)), "Duplicate role codes found"


class TestSpecificAbbreviations:
    """Test specific abbreviations from the PRD."""

    def test_trade_role_uses_trd_not_trn(self):
        """Trade role should use TRD, not TRN (reserved for transport sector)."""
        registry = AbbreviationRegistry()
        trade = registry.find_role_by_key("trade")
        assert trade is not None
        assert trade.code == "TRD"

    def test_transport_final_energy_uses_trn(self):
        """Transport final energy service commodity uses TRN."""
        registry = AbbreviationRegistry()
        transport = registry.find_commodity_by_key("transport_final_energy")
        assert transport is not None
        assert transport.code == "TRN"

    def test_electrolysis_code(self):
        """Electrolysis technology should use ELEC_H2."""
        registry = AbbreviationRegistry()
        elec = registry.find_tech_by_key("electrolysis_h2")
        assert elec is not None
        assert elec.code == "ELEC_H2"


class TestDataclassProperties:
    """Test that dataclasses are properly frozen/immutable."""

    def test_commodity_abbrev_frozen(self):
        """CommodityAbbrev should be frozen."""
        abbrev = CommodityAbbrev(key="test", code="TST", kind=CommodityKind.TRADABLE)
        with pytest.raises(Exception):
            abbrev.key = "modified"  # type: ignore

    def test_tech_abbrev_frozen(self):
        """TechAbbrev should be frozen."""
        abbrev = TechAbbrev(key="test", code="TST")
        with pytest.raises(Exception):
            abbrev.key = "modified"  # type: ignore

    def test_role_abbrev_frozen(self):
        """RoleAbbrev should be frozen."""
        abbrev = RoleAbbrev(key="test", code="TST")
        with pytest.raises(Exception):
            abbrev.key = "modified"  # type: ignore
