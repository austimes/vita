"""Tests for segments and commodity semantics in IR.

Tests the P1 implementation of vedalang-38r: segments and commodity semantics.
"""

import pytest

from vedalang.compiler.segments import (
    ScopedCommodity,
    build_scoped_commodity_registry,
    build_segments,
    commodity_kind_to_com_type,
    get_scoped_commodity_id,
    normalize_commodity,
)


class TestBuildSegments:
    """Tests for build_segments()."""

    def test_no_segments_defined(self):
        """Empty model returns empty list."""
        assert build_segments({}) == []
        assert build_segments({"segments": None}) == []
        assert build_segments({"segments": {}}) == []

    def test_empty_sectors(self):
        """Empty sectors list returns empty list."""
        assert build_segments({"segments": {"sectors": []}}) == []

    def test_coarse_sectors_only(self):
        """Sectors without end_uses returns sector keys."""
        model = {"segments": {"sectors": ["RES", "COM"]}}
        assert build_segments(model) == ["RES", "COM"]

    def test_single_sector(self):
        """Single sector returns single key."""
        model = {"segments": {"sectors": ["RES"]}}
        assert build_segments(model) == ["RES"]

    def test_fine_with_end_uses(self):
        """Sectors + end_uses returns sector.end_use keys."""
        model = {
            "segments": {
                "sectors": ["RES", "COM"],
                "end_uses": ["lighting", "heating"],
            }
        }
        expected = [
            "RES.lighting",
            "RES.heating",
            "COM.lighting",
            "COM.heating",
        ]
        assert build_segments(model) == expected

    def test_many_sectors_many_end_uses(self):
        """Cross product of many sectors and end_uses."""
        model = {
            "segments": {
                "sectors": ["RES", "COM", "IND"],
                "end_uses": ["lighting", "heating", "cooling"],
            }
        }
        result = build_segments(model)
        # Should have 3 sectors × 3 end_uses = 9 keys
        assert len(result) == 9
        assert "RES.lighting" in result
        assert "IND.cooling" in result

    def test_empty_end_uses_treated_as_none(self):
        """Empty end_uses list treated as coarse mode."""
        model = {"segments": {"sectors": ["RES", "COM"], "end_uses": []}}
        # Empty list is falsy, so should return sectors only
        assert build_segments(model) == ["RES", "COM"]


class TestCommodityKindToComType:
    """Tests for commodity_kind_to_com_type()."""

    def test_service_to_dem(self):
        """Service commodities map to DEM."""
        assert commodity_kind_to_com_type("service") == "DEM"

    def test_carrier_to_nrg(self):
        """Carrier commodities map to NRG."""
        assert commodity_kind_to_com_type("carrier") == "NRG"

    def test_material_to_mat(self):
        """Material commodities map to MAT."""
        assert commodity_kind_to_com_type("material") == "MAT"

    def test_emission_to_env(self):
        """Emission commodities map to ENV."""
        assert commodity_kind_to_com_type("emission") == "ENV"

    def test_legacy_uppercase_service(self):
        """Legacy SERVICE maps to DEM."""
        assert commodity_kind_to_com_type("SERVICE") == "DEM"

    def test_legacy_tradable(self):
        """Legacy TRADABLE maps to NRG."""
        assert commodity_kind_to_com_type("TRADABLE") == "NRG"

    def test_legacy_emission(self):
        """Legacy EMISSION maps to ENV."""
        assert commodity_kind_to_com_type("EMISSION") == "ENV"

    def test_deprecated_energy(self):
        """Deprecated 'energy' maps to NRG."""
        assert commodity_kind_to_com_type("energy") == "NRG"

    def test_deprecated_demand(self):
        """Deprecated 'demand' maps to DEM."""
        assert commodity_kind_to_com_type("demand") == "DEM"

    def test_unknown_defaults_to_nrg(self):
        """Unknown kinds default to NRG."""
        assert commodity_kind_to_com_type("unknown") == "NRG"
        assert commodity_kind_to_com_type("") == "NRG"


class TestGetScopedCommodityId:
    """Tests for get_scoped_commodity_id()."""

    def test_tradable_no_scope(self):
        """Tradable commodities are never scoped."""
        result = get_scoped_commodity_id("electricity", "RES", True, "carrier")
        assert result == "electricity"
        result = get_scoped_commodity_id("gas", "COM.heating", True, "carrier")
        assert result == "gas"

    def test_carrier_kind_no_scope(self):
        """Carrier kind is never scoped regardless of tradable flag."""
        assert get_scoped_commodity_id("elec", "RES", False, "carrier") == "elec"

    def test_material_kind_no_scope(self):
        """Material kind is never scoped regardless of tradable flag."""
        assert get_scoped_commodity_id("steel", "IND", False, "material") == "steel"

    def test_service_with_segment_scoped(self):
        """Non-tradable service with segment is scoped."""
        result = get_scoped_commodity_id("lighting", "RES", False, "service")
        assert result == "lighting@RES"

    def test_service_fine_segment_scoped(self):
        """Non-tradable service with fine segment is scoped."""
        result = get_scoped_commodity_id("lighting", "RES.lighting", False, "service")
        assert result == "lighting@RES.lighting"

    def test_service_no_segment_unscoped(self):
        """Non-tradable service without segment is unscoped (flat model)."""
        result = get_scoped_commodity_id("lighting", None, False, "service")
        assert result == "lighting"

    def test_emission_with_segment_scoped(self):
        """Non-tradable emission with segment is scoped."""
        result = get_scoped_commodity_id("co2", "IND", False, "emission")
        assert result == "co2@IND"


class TestNormalizeCommodity:
    """Tests for normalize_commodity()."""

    def test_minimal_carrier(self):
        """Minimal carrier commodity normalization."""
        result = normalize_commodity({"id": "electricity"})
        assert result["id"] == "electricity"
        assert result["kind"] == "carrier"
        assert result["tradable"] is True
        assert result["unit"] == "PJ"
        assert result["com_type"] == "NRG"

    def test_explicit_service(self):
        """Explicit service commodity normalization."""
        result = normalize_commodity({"id": "lighting", "kind": "service"})
        assert result["id"] == "lighting"
        assert result["kind"] == "service"
        assert result["tradable"] is False  # inferred from kind
        assert result["com_type"] == "DEM"

    def test_explicit_emission(self):
        """Emission commodity normalization."""
        result = normalize_commodity({"id": "co2", "kind": "emission", "unit": "Mt"})
        assert result["id"] == "co2"
        assert result["kind"] == "emission"
        assert result["tradable"] is False
        assert result["unit"] == "Mt"
        assert result["com_type"] == "ENV"

    def test_legacy_name_field(self):
        """'name' field maps to 'id'."""
        result = normalize_commodity({"name": "gas", "kind": "carrier"})
        assert result["id"] == "gas"

    def test_id_takes_precedence_over_name(self):
        """'id' field takes precedence over 'name'."""
        result = normalize_commodity({"id": "elec", "name": "electricity"})
        assert result["id"] == "elec"

    def test_legacy_tradable_kind(self):
        """Legacy TRADABLE kind normalizes to carrier."""
        result = normalize_commodity({"id": "gas", "kind": "TRADABLE"})
        assert result["kind"] == "carrier"
        assert result["tradable"] is True
        assert result["com_type"] == "NRG"

    def test_legacy_service_kind(self):
        """Legacy SERVICE kind normalizes to service."""
        result = normalize_commodity({"id": "heat", "kind": "SERVICE"})
        assert result["kind"] == "service"
        assert result["tradable"] is False
        assert result["com_type"] == "DEM"

    def test_legacy_emission_kind(self):
        """Legacy EMISSION kind normalizes to emission."""
        result = normalize_commodity({"id": "co2", "kind": "EMISSION"})
        assert result["kind"] == "emission"
        assert result["tradable"] is False
        assert result["com_type"] == "ENV"

    def test_explicit_tradable_override(self):
        """Explicit tradable flag overrides default."""
        # Service that is explicitly tradable (unusual but allowed)
        raw = {"id": "heat", "kind": "service", "tradable": True}
        result = normalize_commodity(raw)
        assert result["tradable"] is True

        # Carrier that is explicitly not tradable
        raw = {"id": "local_gas", "kind": "carrier", "tradable": False}
        result = normalize_commodity(raw)
        assert result["tradable"] is False

    def test_missing_id_and_name_raises(self):
        """Missing both id and name raises ValueError."""
        with pytest.raises(ValueError, match="must have 'id' or 'name'"):
            normalize_commodity({"kind": "carrier"})

    def test_deprecated_energy_kind(self):
        """Deprecated 'energy' kind normalizes to carrier."""
        result = normalize_commodity({"id": "elec", "kind": "energy"})
        assert result["kind"] == "carrier"

    def test_deprecated_demand_kind(self):
        """Deprecated 'demand' kind normalizes to service."""
        result = normalize_commodity({"id": "heat", "kind": "demand"})
        assert result["kind"] == "service"

    def test_material_tradable_by_default(self):
        """Material commodities are tradable by default."""
        result = normalize_commodity({"id": "steel", "kind": "material"})
        assert result["tradable"] is True
        assert result["com_type"] == "MAT"


class TestBuildScopedCommodityRegistry:
    """Tests for build_scoped_commodity_registry()."""

    def test_empty_inputs(self):
        """Empty commodities returns empty registry."""
        assert build_scoped_commodity_registry([], []) == {}

    def test_tradable_commodity_single_entry(self):
        """Tradable commodity gets single unscoped entry."""
        commodities = [{"id": "electricity", "kind": "carrier"}]
        segments = ["RES", "COM"]

        registry = build_scoped_commodity_registry(commodities, segments)

        assert "electricity" in registry
        entries = registry["electricity"]
        assert len(entries) == 1
        assert entries[0].times_symbol == "electricity"
        assert entries[0].segment is None
        assert entries[0].tradable is True

    def test_service_commodity_scoped_per_segment(self):
        """Non-tradable service gets one entry per segment."""
        commodities = [{"id": "lighting", "kind": "service"}]
        segments = ["RES", "COM"]

        registry = build_scoped_commodity_registry(commodities, segments)

        entries = registry["lighting"]
        assert len(entries) == 2
        assert entries[0].times_symbol == "lighting@RES"
        assert entries[0].segment == "RES"
        assert entries[1].times_symbol == "lighting@COM"
        assert entries[1].segment == "COM"

    def test_service_no_segments_flat(self):
        """Non-tradable service with no segments gets single entry."""
        commodities = [{"id": "lighting", "kind": "service"}]
        segments = []  # flat model

        registry = build_scoped_commodity_registry(commodities, segments)

        entries = registry["lighting"]
        assert len(entries) == 1
        assert entries[0].times_symbol == "lighting"
        assert entries[0].segment is None

    def test_mixed_commodities(self):
        """Mixed tradable and non-tradable commodities."""
        commodities = [
            {"id": "electricity", "kind": "carrier"},
            {"id": "lighting", "kind": "service"},
            {"id": "co2", "kind": "emission"},
        ]
        segments = ["RES", "COM"]

        registry = build_scoped_commodity_registry(commodities, segments)

        # Carrier: single unscoped
        assert len(registry["electricity"]) == 1
        assert registry["electricity"][0].times_symbol == "electricity"

        # Service: scoped per segment
        assert len(registry["lighting"]) == 2
        symbols = {e.times_symbol for e in registry["lighting"]}
        assert symbols == {"lighting@RES", "lighting@COM"}

        # Emission: scoped per segment (non-tradable)
        assert len(registry["co2"]) == 2
        symbols = {e.times_symbol for e in registry["co2"]}
        assert symbols == {"co2@RES", "co2@COM"}

    def test_scoped_commodity_dataclass(self):
        """ScopedCommodity dataclass has expected fields."""
        commodities = [{"id": "heat", "kind": "service", "unit": "PJ"}]
        segments = ["RES"]

        registry = build_scoped_commodity_registry(commodities, segments)
        entry = registry["heat"][0]

        assert isinstance(entry, ScopedCommodity)
        assert entry.id == "heat"
        assert entry.segment == "RES"
        assert entry.kind == "service"
        assert entry.tradable is False
        assert entry.times_symbol == "heat@RES"
