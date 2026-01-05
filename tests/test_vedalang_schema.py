import json
from pathlib import Path

import jsonschema
import pytest
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = PROJECT_ROOT / "vedalang" / "schema" / "vedalang.schema.json"
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def test_mini_plant_validates():
    """The mini_plant example should pass validation."""
    schema = load_schema()
    with open(EXAMPLES_DIR / "mini_plant.veda.yaml") as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)


def test_missing_model_rejected():
    """Document without 'model' key should be rejected."""
    schema = load_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"foo": "bar"}, schema)


def test_missing_required_fields_rejected():
    """Model missing required fields should be rejected."""
    schema = load_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"model": {"name": "Test"}}, schema)


def test_invalid_commodity_type_rejected():
    """Invalid commodity type enum should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "Test",
            "regions": ["R1"],
            "commodities": [{"name": "X", "type": "invalid_type"}],
            "processes": [],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_efficiency_range():
    """Efficiency must be between 0 and 1."""
    schema = load_schema()
    data = {
        "model": {
            "name": "Test",
            "regions": ["R1"],
            "commodities": [],
            "processes": [
                {
                    "name": "P1",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.5,
                }
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_timeslices_validates():
    """Timeslice structure should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "TimesliceTest",
            "regions": ["R1"],
            "timeslices": {
                "season": [
                    {"code": "S", "name": "Summer"},
                    {"code": "W", "name": "Winter"},
                ],
                "daynite": [
                    {"code": "D", "name": "Day"},
                    {"code": "N", "name": "Night"},
                ],
                "fractions": {
                    "SD": 0.25,
                    "SN": 0.25,
                    "WD": 0.25,
                    "WN": 0.25,
                },
            },
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "P1", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0}
            ],
        }
    }
    jsonschema.validate(data, schema)


def test_timeslices_example_validates():
    """The example_with_timeslices.veda.yaml should pass validation."""
    schema = load_schema()
    with open(EXAMPLES_DIR / "example_with_timeslices.veda.yaml") as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)


def test_timeslice_code_pattern():
    """Timeslice code must be 1-3 uppercase letters."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadTimeslice",
            "regions": ["R1"],
            "timeslices": {
                "season": [{"code": "toolong"}],
            },
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "P1", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0}
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_trade_links_validates():
    """Trade links should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "TradeTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "P1", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0}
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "ELC",
                    "bidirectional": True,
                },
            ],
        }
    }
    jsonschema.validate(data, schema)


def test_trade_links_example_validates():
    """The example_with_trade.veda.yaml should pass validation."""
    schema = load_schema()
    with open(EXAMPLES_DIR / "example_with_trade.veda.yaml") as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)


def test_trade_link_missing_required_fields():
    """Trade link missing required fields should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadTrade",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "P1", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0}
            ],
            "trade_links": [
                {"origin": "REG1"},  # Missing destination and commodity
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_constraints_emission_cap_validates():
    """emission_cap constraint should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "ConstraintTest",
            "regions": ["REG1"],
            "commodities": [{"name": "CO2", "type": "emission"}],
            "processes": [
                {"name": "P1", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0}
            ],
            "constraints": [
                {
                    "name": "CO2_CAP",
                    "type": "emission_cap",
                    "commodity": "CO2",
                    "limit": 100,
                    "limtype": "up",
                },
            ],
        }
    }
    jsonschema.validate(data, schema)


def test_constraints_activity_share_validates():
    """activity_share constraint should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "ConstraintTest",
            "regions": ["REG1"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP_WIND", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0},
                {"name": "PP_CCGT", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 0.55},
            ],
            "constraints": [
                {
                    "name": "REN_TARGET",
                    "type": "activity_share",
                    "commodity": "ELC",
                    "processes": ["PP_WIND"],
                    "minimum_share": 0.30,
                },
            ],
        }
    }
    jsonschema.validate(data, schema)


def test_constraints_example_validates():
    """The example_with_constraints.veda.yaml should pass validation."""
    schema = load_schema()
    with open(EXAMPLES_DIR / "example_with_constraints.veda.yaml") as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)


def test_constraint_invalid_type_rejected():
    """Invalid constraint type should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadConstraint",
            "regions": ["REG1"],
            "commodities": [{"name": "CO2", "type": "emission"}],
            "processes": [
                {"name": "P1", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0}
            ],
            "constraints": [
                {
                    "name": "BAD",
                    "type": "invalid_type",
                    "commodity": "CO2",
                },
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_constraint_share_range():
    """Share values must be between 0 and 1."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadShare",
            "regions": ["REG1"],
            "commodities": [{"name": "ELC", "type": "energy"}],
            "processes": [
                {"name": "PP_WIND", "sets": ["ELE"], "primary_commodity_group": "NRGO", "efficiency": 1.0}
            ],
            "constraints": [
                {
                    "name": "BAD",
                    "type": "activity_share",
                    "commodity": "ELC",
                    "processes": ["PP_WIND"],
                    "minimum_share": 1.5,  # Invalid: > 1
                },
            ],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
