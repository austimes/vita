"""
Schema Compatibility Tests

These tests verify the VedaLang schema structure.

Note: As of January 2026, VedaLang underwent a breaking change to introduce
roles/variants/scoping syntax. The old process/process_template constructs
were removed. See docs/reference/vedalang-syntax.prd.txt for details.
"""

import json
from pathlib import Path

import pytest

SCHEMA_PATH = (
    Path(__file__).parent.parent / "vedalang" / "schema" / "vedalang.schema.json"
)


def load_schema() -> dict:
    """Load the current VedaLang schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


# =============================================================================
# Current Schema Definitions (January 2026 roles/variants/scoping syntax)
# =============================================================================

REQUIRED_ROOT_FIELDS = ["model"]

REQUIRED_MODEL_FIELDS = ["name", "regions", "commodities"]

# Commodity now uses 'id' (preferred) or 'name' (legacy), plus 'type'
REQUIRED_COMMODITY_FIELDS = ["type"]

REQUIRED_FLOW_FIELDS = ["commodity"]

REQUIRED_SCENARIO_FIELDS = ["name", "type"]

# New: process_role and process_variant replace the old 'process' definition
REQUIRED_PROCESS_ROLE_FIELDS = ["id"]
REQUIRED_PROCESS_VARIANT_FIELDS = ["id", "role"]

# Commodity types: canonical type enum values
BASELINE_COMMODITY_TYPES = [
    "fuel", "energy", "service", "material", "emission", "money", "other",
]

BASELINE_SCENARIO_TYPES = ["commodity_price", "demand_projection"]


# =============================================================================
# Required Field Tests
# =============================================================================


class TestRequiredFieldsPreserved:
    """Verify that all required fields exist in the schema."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_root_required_fields(self, schema: dict):
        """Root level must require 'model'."""
        current_required = schema.get("required", [])
        for field in REQUIRED_ROOT_FIELDS:
            assert field in current_required, (
                f"Required root field '{field}' was removed!"
            )

    def test_model_required_fields(self, schema: dict):
        """Model object must require baseline fields."""
        model_props = schema.get("properties", {}).get("model", {})
        current_required = model_props.get("required", [])
        for field in REQUIRED_MODEL_FIELDS:
            assert field in current_required, (
                f"Required model field '{field}' was removed!"
            )

    def test_commodity_required_fields(self, schema: dict):
        """Commodity definition must require baseline fields."""
        commodity_def = schema.get("$defs", {}).get("commodity", {})
        current_required = commodity_def.get("required", [])
        for field in REQUIRED_COMMODITY_FIELDS:
            assert field in current_required, (
                f"Required commodity field '{field}' was removed!"
            )

    def test_process_role_required_fields(self, schema: dict):
        """Process role definition must require baseline fields."""
        role_def = schema.get("$defs", {}).get("process_role", {})
        current_required = role_def.get("required", [])
        for field in REQUIRED_PROCESS_ROLE_FIELDS:
            assert field in current_required, (
                f"Required process_role field '{field}' was removed!"
            )

    def test_process_variant_required_fields(self, schema: dict):
        """Process variant definition must require baseline fields."""
        variant_def = schema.get("$defs", {}).get("process_variant", {})
        current_required = variant_def.get("required", [])
        for field in REQUIRED_PROCESS_VARIANT_FIELDS:
            assert field in current_required, (
                f"Required process_variant field '{field}' was removed!"
            )

    def test_flow_required_fields(self, schema: dict):
        """Flow definition must require baseline fields."""
        flow_def = schema.get("$defs", {}).get("flow", {})
        current_required = flow_def.get("required", [])
        for field in REQUIRED_FLOW_FIELDS:
            assert field in current_required, (
                f"Required flow field '{field}' was removed!"
            )

    def test_scenario_required_fields(self, schema: dict):
        """Scenario parameter definition must require baseline fields."""
        scenario_def = schema.get("$defs", {}).get("scenario_parameter", {})
        current_required = scenario_def.get("required", [])
        for field in REQUIRED_SCENARIO_FIELDS:
            assert field in current_required, (
                f"Required scenario_parameter field '{field}' was removed!"
            )


# =============================================================================
# Enum Value Tests
# =============================================================================


class TestEnumValuesPreserved:
    """Verify that enum values exist in the schema."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_commodity_type_enum_values(self, schema: dict):
        """Commodity type enum must include all expected values."""
        commodity_def = schema.get("$defs", {}).get("commodity", {})
        type_prop = commodity_def.get("properties", {}).get("type", {})
        current_enum = type_prop.get("enum", [])

        for value in BASELINE_COMMODITY_TYPES:
            assert value in current_enum, (
                f"Commodity type '{value}' was removed from enum!"
            )

    def test_scenario_type_enum_values(self, schema: dict):
        """Scenario parameter type enum must include all expected values."""
        scenario_def = schema.get("$defs", {}).get("scenario_parameter", {})
        type_prop = scenario_def.get("properties", {}).get("type", {})
        current_enum = type_prop.get("enum", [])

        for value in BASELINE_SCENARIO_TYPES:
            assert value in current_enum, (
                f"Scenario parameter type '{value}' was removed from enum!"
            )


# =============================================================================
# Type Preservation Tests
# =============================================================================


class TestPropertyTypesPreserved:
    """Verify that property types are correct."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_model_name_is_string(self, schema: dict):
        """model.name must be a string type."""
        model_props = schema.get("properties", {}).get("model", {})
        name_prop = model_props.get("properties", {}).get("name", {})
        assert name_prop.get("type") == "string", (
            "model.name type was changed!"
        )

    def test_model_regions_is_array(self, schema: dict):
        """model.regions must be an array type."""
        model_props = schema.get("properties", {}).get("model", {})
        regions_prop = model_props.get("properties", {}).get("regions", {})
        assert regions_prop.get("type") == "array", (
            "model.regions type was changed!"
        )

    def test_process_variant_efficiency_accepts_number(self, schema: dict):
        """process_variant.efficiency must accept number type (scalar or in oneOf)."""
        variant_def = schema.get("$defs", {}).get("process_variant", {})
        eff_prop = variant_def.get("properties", {}).get("efficiency", {})
        # Can be direct type or oneOf (for time-varying support)
        if "oneOf" in eff_prop:
            number_options = [
                opt for opt in eff_prop["oneOf"]
                if opt.get("type") == "number"
            ]
            assert len(number_options) >= 1, (
                "process_variant.efficiency oneOf must include a number option"
            )
        else:
            assert eff_prop.get("type") == "number", (
                "process_variant.efficiency type was changed!"
            )


# =============================================================================
# Schema Structure Tests
# =============================================================================


class TestSchemaStructure:
    """Verify overall schema structure is maintained."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_defs_section_exists(self, schema: dict):
        """Schema must have $defs section for type definitions."""
        assert "$defs" in schema, "Schema $defs section is missing!"

    def test_commodity_def_exists(self, schema: dict):
        """Commodity definition must exist."""
        assert "commodity" in schema.get("$defs", {}), (
            "Commodity type definition was removed!"
        )

    def test_process_role_def_exists(self, schema: dict):
        """Process role definition must exist."""
        assert "process_role" in schema.get("$defs", {}), (
            "Process role type definition was removed!"
        )

    def test_process_variant_def_exists(self, schema: dict):
        """Process variant definition must exist."""
        assert "process_variant" in schema.get("$defs", {}), (
            "Process variant type definition was removed!"
        )

    def test_flow_def_exists(self, schema: dict):
        """Flow definition must exist."""
        assert "flow" in schema.get("$defs", {}), (
            "Flow type definition was removed!"
        )

    def test_scenario_def_exists(self, schema: dict):
        """Scenario parameter definition must exist."""
        assert "scenario_parameter" in schema.get("$defs", {}), (
            "Scenario parameter type definition was removed!"
        )

    def test_timeslices_def_exists(self, schema: dict):
        """Timeslices definition must exist."""
        assert "timeslices" in schema.get("$defs", {}), (
            "Timeslices type definition was removed!"
        )

    def test_timeslice_level_def_exists(self, schema: dict):
        """Timeslice level definition must exist."""
        assert "timeslice_level" in schema.get("$defs", {}), (
            "Timeslice level type definition was removed!"
        )


# =============================================================================
# New Schema Construct Tests
# =============================================================================


class TestNewSchemaConstructs:
    """Verify new roles/variants/scoping constructs exist."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_scoping_def_exists(self, schema: dict):
        """Scoping definition must exist."""
        assert "scoping" in schema.get("$defs", {}), (
            "Scoping type definition is missing!"
        )

    def test_availability_entry_def_exists(self, schema: dict):
        """Availability entry definition must exist."""
        assert "availability_entry" in schema.get("$defs", {}), (
            "Availability entry type definition is missing!"
        )

    def test_process_parameter_def_exists(self, schema: dict):
        """Process parameter definition must exist."""
        assert "process_parameter" in schema.get("$defs", {}), (
            "Process parameter type definition is missing!"
        )

    def test_demand_def_exists(self, schema: dict):
        """Demand definition must exist."""
        assert "demand" in schema.get("$defs", {}), (
            "Demand type definition is missing!"
        )

    def test_top_level_scoping_property_exists(self, schema: dict):
        """Top-level scoping property must exist."""
        assert "scoping" in schema.get("properties", {}), (
            "Top-level scoping property is missing!"
        )

    def test_top_level_roles_property_exists(self, schema: dict):
        """Top-level roles property must exist."""
        assert "roles" in schema.get("properties", {}), (
            "Top-level roles property is missing!"
        )

    def test_top_level_variants_property_exists(self, schema: dict):
        """Top-level variants property must exist."""
        assert "variants" in schema.get("properties", {}), (
            "Top-level variants property is missing!"
        )

    def test_top_level_availability_property_exists(self, schema: dict):
        """Top-level availability property must exist."""
        assert "availability" in schema.get("properties", {}), (
            "Top-level availability property is missing!"
        )

    def test_top_level_process_parameters_property_exists(self, schema: dict):
        """Top-level process_parameters property must exist."""
        assert "process_parameters" in schema.get("properties", {}), (
            "Top-level process_parameters property is missing!"
        )

    def test_top_level_demands_property_exists(self, schema: dict):
        """Top-level demands property must exist."""
        assert "demands" in schema.get("properties", {}), (
            "Top-level demands property is missing!"
        )
