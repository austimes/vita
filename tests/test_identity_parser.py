"""Tests for VedaLang naming grammar parser and validator."""

import pytest

from vedalang.identity.parser import (
    VALID_ROLES,
    generate_process_id,
    parse_process_id,
    validate_commodity_id,
)


class TestCommodityIDValidation:
    """Tests for validate_commodity_id function."""

    def test_valid_tradable_commodities(self):
        """Valid TRADABLE commodity IDs."""
        for name in ["C:ELC", "C:GAS", "C:H2", "C:COA", "C:OIL"]:
            result = validate_commodity_id(name, "TRADABLE")
            assert result.valid, f"Expected {name} to be valid: {result.error}"
            assert result.kind == "TRADABLE"
            assert result.code == name.split(":")[1]
            assert result.context is None
            assert result.error is None

    def test_valid_service_commodities(self):
        """Valid SERVICE commodity IDs."""
        test_cases = [
            ("S:RSD:RES.ALL", "RSD", "RES.ALL"),
            ("S:COM:COM.OFFICE", "COM", "COM.OFFICE"),
            ("S:TRN:TRN.ROAD.LDV", "TRN", "TRN.ROAD.LDV"),
        ]
        for name, expected_code, expected_ctx in test_cases:
            result = validate_commodity_id(name, "SERVICE")
            assert result.valid, f"Expected {name} to be valid: {result.error}"
            assert result.kind == "SERVICE"
            assert result.code == expected_code
            assert result.context == expected_ctx
            assert result.error is None

    def test_valid_emission_commodities(self):
        """Valid EMISSION commodity IDs."""
        for name in ["E:CO2", "E:CH4", "E:N2O", "E:NOX"]:
            result = validate_commodity_id(name, "EMISSION")
            assert result.valid, f"Expected {name} to be valid: {result.error}"
            assert result.kind == "EMISSION"
            assert result.code == name.split(":")[1]
            assert result.context is None
            assert result.error is None

    def test_wrong_prefix_tradable(self):
        """TRADABLE commodity with wrong prefix."""
        result = validate_commodity_id("E:ELC", "TRADABLE")
        assert not result.valid
        assert "Wrong prefix" in result.error

    def test_wrong_prefix_service(self):
        """SERVICE commodity with wrong prefix."""
        result = validate_commodity_id("C:RSD:RES.ALL", "SERVICE")
        assert not result.valid
        assert "Wrong prefix" in result.error

    def test_wrong_prefix_emission(self):
        """EMISSION commodity with wrong prefix."""
        result = validate_commodity_id("C:CO2", "EMISSION")
        assert not result.valid
        assert "Wrong prefix" in result.error

    def test_missing_parts_tradable(self):
        """TRADABLE commodity missing parts."""
        result = validate_commodity_id("C", "TRADABLE")
        assert not result.valid
        assert "Invalid commodity ID format" in result.error

    def test_service_missing_context(self):
        """SERVICE commodity missing context."""
        result = validate_commodity_id("S:RSD", "SERVICE")
        assert not result.valid
        assert "requires format" in result.error

    def test_service_invalid_context_format(self):
        """SERVICE commodity with invalid context format."""
        result = validate_commodity_id("S:RSD:INVALID", "SERVICE")
        assert not result.valid
        assert "Invalid SERVICE context format" in result.error

    def test_service_context_mismatch(self):
        """SERVICE commodity context doesn't match expected."""
        result = validate_commodity_id("S:RSD:RES.ALL", "SERVICE", context="COM.OFFICE")
        assert not result.valid
        assert "Context mismatch" in result.error

    def test_unknown_kind(self):
        """Unknown commodity kind."""
        result = validate_commodity_id("X:FOO", "UNKNOWN")
        assert not result.valid
        assert "Unknown commodity kind" in result.error

    def test_tradable_extra_parts(self):
        """TRADABLE commodity with too many parts."""
        result = validate_commodity_id("C:ELC:EXTRA", "TRADABLE")
        assert not result.valid
        assert "requires format" in result.error

    def test_invalid_code_format(self):
        """TRADABLE commodity with invalid code format."""
        result = validate_commodity_id("C:elc", "TRADABLE")
        assert not result.valid
        assert "Must be uppercase" in result.error


class TestProcessIDParser:
    """Tests for parse_process_id function."""

    def test_basic_process_id(self):
        """Parse basic process ID with required parts only."""
        result = parse_process_id("P:CCG:GEN:NEM_EAST")
        assert result.valid
        assert result.parsed.technology == "CCG"
        assert result.parsed.role == "GEN"
        assert result.parsed.geo == "NEM_EAST"
        assert result.parsed.segment is None
        assert result.parsed.variant is None
        assert result.parsed.vintage is None

    def test_process_id_with_segment(self):
        """Parse process ID with segment (EUS role)."""
        result = parse_process_id("P:DEM:EUS:NEM_EAST:RES.ALL")
        assert result.valid
        assert result.parsed.technology == "DEM"
        assert result.parsed.role == "EUS"
        assert result.parsed.geo == "NEM_EAST"
        assert result.parsed.segment == "RES.ALL"

    def test_process_id_with_variant(self):
        """Parse process ID with variant."""
        result = parse_process_id("P:PCC:CAP:NSW.NCC:CCS90")
        assert result.valid
        assert result.parsed.technology == "PCC"
        assert result.parsed.role == "CAP"
        assert result.parsed.geo == "NSW.NCC"
        assert result.parsed.variant == "CCS90"

    def test_process_id_with_vintage(self):
        """Parse process ID with vintage."""
        result = parse_process_id("P:CCG:GEN:NEM_EAST:EXIST")
        assert result.valid
        assert result.parsed.vintage == "EXIST"

    def test_process_id_with_new_vintage(self):
        """Parse process ID with NEW vintage."""
        result = parse_process_id("P:CCG:GEN:NEM_EAST:NEW")
        assert result.valid
        assert result.parsed.vintage == "NEW"

    def test_process_id_full(self):
        """Parse process ID with all optional parts."""
        result = parse_process_id("P:DEM:EUS:NEM_EAST:RES.ALL:V2:EXIST")
        assert result.valid
        assert result.parsed.segment == "RES.ALL"
        assert result.parsed.variant == "V2"
        assert result.parsed.vintage == "EXIST"

    def test_all_valid_roles(self):
        """All valid roles are accepted."""
        for role in VALID_ROLES:
            if role == "EUS":
                result = parse_process_id(f"P:XXX:{role}:REGION:SEG.A")
            else:
                result = parse_process_id(f"P:XXX:{role}:REGION")
            assert result.valid, f"Role {role} should be valid: {result.error}"

    def test_wrong_prefix(self):
        """Process ID with wrong prefix."""
        result = parse_process_id("X:CCG:GEN:NEM_EAST")
        assert not result.valid
        assert "must start with 'P:'" in result.error

    def test_unknown_role(self):
        """Process ID with unknown role."""
        result = parse_process_id("P:CCG:XXX:NEM_EAST")
        assert not result.valid
        assert "Unknown role" in result.error

    def test_missing_geo(self):
        """Process ID missing geographic region."""
        result = parse_process_id("P:CCG:GEN")
        assert not result.valid
        assert "at least 4 parts" in result.error

    def test_eus_requires_segment(self):
        """EUS role requires segment."""
        result = parse_process_id("P:DEM:EUS:NEM_EAST")
        assert not result.valid
        assert "requires a segment" in result.error


class TestProcessIDGenerator:
    """Tests for generate_process_id function."""

    def test_basic_generation(self):
        """Generate basic process ID."""
        pid = generate_process_id("CCG", "GEN", "NEM_EAST")
        assert pid == "P:CCG:GEN:NEM_EAST"

    def test_generation_with_segment(self):
        """Generate process ID with segment."""
        pid = generate_process_id("DEM", "EUS", "NEM_EAST", segment="RES.ALL")
        assert pid == "P:DEM:EUS:NEM_EAST:RES.ALL"

    def test_generation_with_variant(self):
        """Generate process ID with variant."""
        pid = generate_process_id("PCC", "CAP", "NSW.NCC", variant="CCS90")
        assert pid == "P:PCC:CAP:NSW.NCC:CCS90"

    def test_generation_with_vintage(self):
        """Generate process ID with vintage."""
        pid = generate_process_id("CCG", "GEN", "NEM_EAST", vintage="EXIST")
        assert pid == "P:CCG:GEN:NEM_EAST:EXIST"

    def test_generation_full(self):
        """Generate process ID with all optional parts."""
        pid = generate_process_id(
            "DEM", "EUS", "NEM_EAST", segment="RES.ALL", variant="V2", vintage="NEW"
        )
        assert pid == "P:DEM:EUS:NEM_EAST:RES.ALL:V2:NEW"

    def test_unknown_role_raises(self):
        """Unknown role raises ValueError."""
        with pytest.raises(ValueError, match="Unknown role"):
            generate_process_id("CCG", "XXX", "NEM_EAST")

    def test_eus_without_segment_raises(self):
        """EUS role without segment raises ValueError."""
        with pytest.raises(ValueError, match="requires a segment"):
            generate_process_id("DEM", "EUS", "NEM_EAST")


class TestRoundTrip:
    """Test generate and parse round-trip."""

    def test_basic_roundtrip(self):
        """Basic round-trip generation and parsing."""
        original = generate_process_id("CCG", "GEN", "NEM_EAST")
        result = parse_process_id(original)
        assert result.valid
        assert result.parsed.technology == "CCG"
        assert result.parsed.role == "GEN"
        assert result.parsed.geo == "NEM_EAST"

    def test_full_roundtrip(self):
        """Full round-trip with all components."""
        original = generate_process_id(
            "DEM", "EUS", "NEM_EAST", segment="RES.ALL", variant="V2", vintage="EXIST"
        )
        result = parse_process_id(original)
        assert result.valid
        regenerated = generate_process_id(
            result.parsed.technology,
            result.parsed.role,
            result.parsed.geo,
            segment=result.parsed.segment,
            variant=result.parsed.variant,
            vintage=result.parsed.vintage,
        )
        assert original == regenerated

    def test_all_roles_roundtrip(self):
        """Round-trip for all valid roles."""
        for role in VALID_ROLES:
            if role == "EUS":
                pid = generate_process_id("XXX", role, "REGION", segment="SEG.A")
            else:
                pid = generate_process_id("XXX", role, "REGION")
            result = parse_process_id(pid)
            assert result.valid, f"Failed round-trip for role {role}"
            assert result.parsed.role == role
