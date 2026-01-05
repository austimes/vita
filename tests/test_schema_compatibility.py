"""
Schema Compatibility Tests

These tests ensure backward compatibility of vedalang.schema.json.
They catch accidental breaking changes by verifying that:
1. Required fields from the baseline are preserved
2. Enum values are not removed (only added)
3. Property types remain unchanged

If these tests fail, you've likely made a breaking schema change.
See docs/schema_evolution.md for the evolution policy.
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
# Baseline Definitions (LOCKED - do not remove items from these lists)
# =============================================================================

REQUIRED_ROOT_FIELDS = ["model"]

REQUIRED_MODEL_FIELDS = ["name", "regions", "commodities", "processes"]

REQUIRED_COMMODITY_FIELDS = ["name", "type"]

REQUIRED_PROCESS_FIELDS = ["name", "sets"]

REQUIRED_FLOW_FIELDS = ["commodity"]

REQUIRED_SCENARIO_FIELDS = ["name", "type"]

BASELINE_COMMODITY_TYPES = ["energy", "material", "emission", "demand"]

BASELINE_SCENARIO_TYPES = ["commodity_price", "demand_projection"]


# =============================================================================
# Required Field Tests
# =============================================================================


class TestRequiredFieldsPreserved:
    """Verify that all baseline required fields still exist in the schema."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_root_required_fields(self, schema: dict):
        """Root level must require 'model'."""
        current_required = schema.get("required", [])
        for field in REQUIRED_ROOT_FIELDS:
            assert field in current_required, (
                f"Required root field '{field}' was removed! "
                "This is a breaking change. See docs/schema_evolution.md"
            )

    def test_model_required_fields(self, schema: dict):
        """Model object must require baseline fields."""
        model_props = schema.get("properties", {}).get("model", {})
        current_required = model_props.get("required", [])
        for field in REQUIRED_MODEL_FIELDS:
            assert field in current_required, (
                f"Required model field '{field}' was removed! "
                "This is a breaking change. See docs/schema_evolution.md"
            )

    def test_commodity_required_fields(self, schema: dict):
        """Commodity definition must require baseline fields."""
        commodity_def = schema.get("$defs", {}).get("commodity", {})
        current_required = commodity_def.get("required", [])
        for field in REQUIRED_COMMODITY_FIELDS:
            assert field in current_required, (
                f"Required commodity field '{field}' was removed! "
                "This is a breaking change. See docs/schema_evolution.md"
            )

    def test_process_required_fields(self, schema: dict):
        """Process definition must require baseline fields."""
        process_def = schema.get("$defs", {}).get("process", {})
        current_required = process_def.get("required", [])
        for field in REQUIRED_PROCESS_FIELDS:
            assert field in current_required, (
                f"Required process field '{field}' was removed! "
                "This is a breaking change. See docs/schema_evolution.md"
            )

    def test_flow_required_fields(self, schema: dict):
        """Flow definition must require baseline fields."""
        flow_def = schema.get("$defs", {}).get("flow", {})
        current_required = flow_def.get("required", [])
        for field in REQUIRED_FLOW_FIELDS:
            assert field in current_required, (
                f"Required flow field '{field}' was removed! "
                "This is a breaking change. See docs/schema_evolution.md"
            )

    def test_scenario_required_fields(self, schema: dict):
        """Scenario parameter definition must require baseline fields.

        Note: 'scenario' was renamed to 'scenario_parameter' in the schema,
        with 'scenarios' kept as a deprecated alias for backward compatibility.
        """
        # Use the new 'scenario_parameter' definition
        scenario_def = schema.get("$defs", {}).get("scenario_parameter", {})
        current_required = scenario_def.get("required", [])
        for field in REQUIRED_SCENARIO_FIELDS:
            assert field in current_required, (
                f"Required scenario_parameter field '{field}' was removed! "
                "This is a breaking change. See docs/schema_evolution.md"
            )


# =============================================================================
# Enum Value Tests
# =============================================================================


class TestEnumValuesPreserved:
    """Verify that baseline enum values haven't been removed."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_commodity_type_enum_values(self, schema: dict):
        """Commodity type enum must include all baseline values."""
        commodity_def = schema.get("$defs", {}).get("commodity", {})
        type_prop = commodity_def.get("properties", {}).get("type", {})
        current_enum = type_prop.get("enum", [])

        for value in BASELINE_COMMODITY_TYPES:
            assert value in current_enum, (
                f"Commodity type '{value}' was removed from enum! "
                "This is a breaking change. See docs/schema_evolution.md"
            )

    def test_scenario_type_enum_values(self, schema: dict):
        """Scenario parameter type enum must include all baseline values.

        Note: 'scenario' was renamed to 'scenario_parameter' in the schema.
        """
        scenario_def = schema.get("$defs", {}).get("scenario_parameter", {})
        type_prop = scenario_def.get("properties", {}).get("type", {})
        current_enum = type_prop.get("enum", [])

        for value in BASELINE_SCENARIO_TYPES:
            assert value in current_enum, (
                f"Scenario parameter type '{value}' was removed from enum! "
                "This is a breaking change. See docs/schema_evolution.md"
            )


# =============================================================================
# Type Preservation Tests
# =============================================================================


class TestPropertyTypesPreserved:
    """Verify that property types haven't changed."""

    @pytest.fixture
    def schema(self) -> dict:
        return load_schema()

    def test_model_name_is_string(self, schema: dict):
        """model.name must remain a string type."""
        model_props = schema.get("properties", {}).get("model", {})
        name_prop = model_props.get("properties", {}).get("name", {})
        assert name_prop.get("type") == "string", (
            "model.name type was changed! This is a breaking change."
        )

    def test_model_regions_is_array(self, schema: dict):
        """model.regions must remain an array type."""
        model_props = schema.get("properties", {}).get("model", {})
        regions_prop = model_props.get("properties", {}).get("regions", {})
        assert regions_prop.get("type") == "array", (
            "model.regions type was changed! This is a breaking change."
        )

    def test_process_efficiency_accepts_number(self, schema: dict):
        """process.efficiency must accept number type (scalar or in oneOf)."""
        process_def = schema.get("$defs", {}).get("process", {})
        eff_prop = process_def.get("properties", {}).get("efficiency", {})
        # Can be direct type or oneOf (for time-varying support)
        if "oneOf" in eff_prop:
            # Check that at least one option accepts number
            number_options = [
                opt for opt in eff_prop["oneOf"]
                if opt.get("type") == "number"
            ]
            assert len(number_options) >= 1, (
                "process.efficiency oneOf must include a number option"
            )
        else:
            assert eff_prop.get("type") == "number", (
                "process.efficiency type was changed! This is a breaking change."
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

    def test_process_def_exists(self, schema: dict):
        """Process definition must exist."""
        assert "process" in schema.get("$defs", {}), (
            "Process type definition was removed!"
        )

    def test_flow_def_exists(self, schema: dict):
        """Flow definition must exist."""
        assert "flow" in schema.get("$defs", {}), (
            "Flow type definition was removed!"
        )

    def test_scenario_def_exists(self, schema: dict):
        """Scenario parameter definition must exist.

        Note: 'scenario' was renamed to 'scenario_parameter' in the schema,
        with 'scenarios' kept as a deprecated alias for backward compatibility.
        """
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
