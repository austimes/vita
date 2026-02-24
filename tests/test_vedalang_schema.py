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
            "commodities": [{"name": "C:X", "type": "INVALID_TYPE"}],
            "processes": [],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_efficiency_range():
    """Efficiency must be between 0 and 1 for process_variants."""
    schema = load_schema()
    data = {
        "model": {
            "name": "Test",
            "regions": ["R1"],
            "commodities": [],
        },
        "process_roles": [
            {"id": "generate_power", "required_inputs": [], "required_outputs": [{"commodity": "electricity"}]}
        ],
        "process_variants": [
            {
                "id": "bad_plant",
                "role": "generate_power",
                "inputs": [],
                "outputs": [{"commodity": "electricity"}],
                "efficiency": 1.5,  # Invalid: > 1
            }
        ],
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
            "commodities": [{"name": "C:ELC", "type": "energy"}],
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
            "commodities": [{"name": "C:ELC", "type": "energy"}],
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
            "commodities": [{"name": "C:ELC", "type": "energy"}],
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
    """Trade links structure validates."""
    schema = load_schema()
    data = {
        "model": {
            "name": "TwoRegionTrade",
            "regions": ["REG1", "REG2"],
            "commodities": [
                {"id": "electricity", "type": "energy", "unit": "PJ"},
                {"id": "natural_gas", "type": "fuel", "unit": "PJ"},
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "electricity",
                    "bidirectional": True,
                    "efficiency": 0.98,
                },
            ],
        }
    }
    jsonschema.validate(data, schema)


def test_trade_link_missing_required_fields():
    """Trade link missing required fields should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadTrade",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
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
            "commodities": [{"name": "E:CO2", "type": "emission"}],
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
            "commodities": [{"name": "C:ELC", "type": "energy"}],
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
            "commodities": [{"name": "E:CO2", "type": "emission"}],
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
            "commodities": [{"name": "C:ELC", "type": "energy"}],
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


# Tests for new schema constructs (roles/variants/segments)


def test_segments_validates():
    """Segments block should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "SegmentTest",
            "regions": ["R1"],
            "commodities": [{"id": "electricity", "type": "energy"}],
        },
        "segments": {
            "sectors": ["RES", "COM"],
            "end_uses": ["lighting", "heating"],
        },
    }
    jsonschema.validate(data, schema)


def test_segments_requires_sectors():
    """Segments block requires sectors."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadSegment",
            "regions": ["R1"],
            "commodities": [],
        },
        "segments": {
            "end_uses": ["lighting"],  # Missing required sectors
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_segments_invalid_sector_rejected():
    """Invalid sector enum value should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadSector",
            "regions": ["R1"],
            "commodities": [],
        },
        "segments": {
            "sectors": ["INVALID"],  # Not in enum
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_process_roles_validates():
    """Process roles block should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "RoleTest",
            "regions": ["R1"],
            "commodities": [
                {"id": "electricity", "type": "energy"},
                {"id": "lighting", "type": "service"},
            ],
        },
        "process_roles": [
            {
                "id": "generate_electricity",
                "stage": "conversion",
                "required_inputs": [],
                "required_outputs": [{"commodity": "electricity"}],
            },
            {
                "id": "deliver_lighting",
                "stage": "end_use",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "lighting"}],
            },
        ],
    }
    jsonschema.validate(data, schema)


def test_process_roles_invalid_stage_rejected():
    """Invalid stage enum value should be rejected."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadRole",
            "regions": ["R1"],
            "commodities": [],
        },
        "process_roles": [
            {
                "id": "bad_role",
                "stage": "invalid_stage",  # Not in enum
            },
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_process_variants_validates():
    """Process variants block should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "VariantTest",
            "regions": ["R1"],
            "commodities": [{"id": "electricity", "type": "energy"}],
        },
        "process_roles": [
            {"id": "generate_power", "required_inputs": [], "required_outputs": [{"commodity": "electricity"}]},
        ],
        "process_variants": [
            {
                "id": "coal_plant",
                "role": "generate_power",
                "inputs": [],
                "outputs": [{"commodity": "electricity"}],
                "efficiency": 0.4,
                "lifetime": 40,
                "investment_cost": 1500,
                "fixed_om_cost": 30,
                "variable_om_cost": 5,
                "emission_factors": {"co2": 0.09},
            },
        ],
    }
    jsonschema.validate(data, schema)


def test_process_variants_requires_role():
    """Process variant requires role reference."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadVariant",
            "regions": ["R1"],
            "commodities": [],
        },
        "process_variants": [
            {
                "id": "orphan_plant",
                # Missing required 'role'
            },
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_availability_validates():
    """Availability block should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "AvailTest",
            "regions": ["REG1", "REG2"],
            "commodities": [],
        },
        "availability": [
            {
                "variant": "coal_plant",
                "regions": ["REG1", "REG2"],
                "sectors": ["IND"],
            },
        ],
    }
    jsonschema.validate(data, schema)


def test_availability_requires_variant_and_regions():
    """Availability requires variant and regions."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadAvail",
            "regions": ["R1"],
            "commodities": [],
        },
        "availability": [
            {"regions": ["R1"]},  # Missing variant
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_process_parameters_validates():
    """Process parameters block should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "ParamTest",
            "regions": ["R1"],
            "commodities": [],
        },
        "process_parameters": [
            {
                "selector": {
                    "variant": "coal_plant",
                    "region": "R1",
                },
                "existing_capacity": [
                    {"vintage": 2010, "capacity": 100},
                ],
                "cap_bound": {"up": 500},
                "ncap_bound": {"lo": 0, "up": 100},
            },
        ],
    }
    jsonschema.validate(data, schema)


def test_demands_validates():
    """Demands block should validate against schema."""
    schema = load_schema()
    data = {
        "model": {
            "name": "DemandTest",
            "regions": ["R1"],
            "commodities": [{"id": "lighting", "type": "service"}],
        },
        "demands": [
            {
                "commodity": "lighting",
                "region": "R1",
                "sector": "RES",
                "values": {"2020": 50, "2030": 60},
                "interpolation": "interp_extrap",
            },
        ],
    }
    jsonschema.validate(data, schema)


def test_demands_requires_commodity_region_values():
    """Demands require commodity, region, and values."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadDemand",
            "regions": ["R1"],
            "commodities": [],
        },
        "demands": [
            {"commodity": "lighting"},  # Missing region and values
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_commodity_with_id_validates():
    """Commodity using 'id' (preferred) should validate."""
    schema = load_schema()
    data = {
        "model": {
            "name": "IdTest",
            "regions": ["R1"],
            "commodities": [
                {
                    "id": "electricity",
                    "type": "energy",
                    "unit": "PJ",
                    "tradable": True,
                },
                {
                    "id": "lighting",
                    "type": "service",
                    "unit": "PJ",
                    "tradable": False,
                },
            ],
        },
    }
    jsonschema.validate(data, schema)


def test_namespaced_commodity_id_validates():
    """Commodity id may use human-readable namespace syntax."""
    schema = load_schema()
    data = {
        "model": {
            "name": "NamespacedIdTest",
            "regions": ["R1"],
            "commodities": [
                {"id": "energy:electricity", "type": "energy"},
                {"id": "fuel:natural_gas", "type": "fuel"},
                {"id": "resource:wind_resource", "type": "other"},
                {"id": "service:space_heat", "type": "service"},
                {"id": "emission:co2", "type": "emission"},
            ],
        },
    }
    jsonschema.validate(data, schema)


def test_unknown_commodity_namespace_rejected_by_schema():
    """Commodity id namespace prefix must be from canonical schema enum."""
    schema = load_schema()
    data = {
        "model": {
            "name": "BadNamespace",
            "regions": ["R1"],
            "commodities": [
                {"id": "unknown:electricity", "type": "energy"},
            ],
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_negative_emission_factor_validates():
    """Negative emission factors are allowed for removals (DAC/LULUCF)."""
    schema = load_schema()
    data = {
        "model": {
            "name": "NegativeEmissionFactor",
            "regions": ["R1"],
            "commodities": [
                {"id": "energy:electricity", "type": "energy"},
                {"id": "service:co2_removal", "type": "service"},
                {"id": "emission:co2", "type": "emission"},
            ],
        },
        "process_roles": [
            {
                "id": "remove_co2",
                "required_inputs": [{"commodity": "energy:electricity"}],
                "required_outputs": [{"commodity": "service:co2_removal"}],
            }
        ],
        "process_variants": [
            {
                "id": "dac",
                "role": "remove_co2",
                "inputs": [{"commodity": "energy:electricity"}],
                "outputs": [{"commodity": "service:co2_removal"}],
                "emission_factors": {"emission:co2": -1.0},
            }
        ],
    }
    jsonschema.validate(data, schema)


def test_full_roles_variants_model_validates():
    """Full model with all new constructs should validate."""
    schema = load_schema()
    data = {
        "model": {
            "name": "MiniSystem_v2",
            "regions": ["SINGLE"],
            "milestone_years": [2020, 2030],
            "commodities": [
                {"id": "electricity", "type": "energy", "unit": "PJ"},
                {"id": "lighting", "type": "service", "unit": "PJ"},
            ],
        },
        "segments": {
            "sectors": ["RES", "COM"],
        },
        "process_roles": [
            {
                "id": "generate_electricity",
                "stage": "conversion",
                "required_inputs": [],
                "required_outputs": [{"commodity": "electricity"}],
            },
            {
                "id": "deliver_lighting",
                "stage": "end_use",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "lighting"}],
            },
        ],
        "process_variants": [
            {
                "id": "simple_generator",
                "role": "generate_electricity",
                "inputs": [],
                "outputs": [{"commodity": "electricity"}],
                "efficiency": 1.0,
                "variable_om_cost": 10,
                "lifetime": 40,
            },
            {
                "id": "led_lighting_device",
                "role": "deliver_lighting",
                "inputs": [{"commodity": "electricity"}],
                "outputs": [{"commodity": "lighting"}],
                "efficiency": 0.4,
                "lifetime": 15,
                "investment_cost": 100,
            },
        ],
        "availability": [
            {"variant": "simple_generator", "regions": ["SINGLE"]},
            {
                "variant": "led_lighting_device",
                "regions": ["SINGLE"],
                "sectors": ["RES", "COM"],
            },
        ],
        "process_parameters": [
            {
                "selector": {"variant": "simple_generator", "region": "SINGLE"},
                "existing_capacity": [{"vintage": 2010, "capacity": 100}],
                "cap_bound": {"up": 1000},
            },
        ],
        "demands": [
            {
                "commodity": "lighting", "region": "SINGLE",
                "sector": "RES", "values": {"2020": 50},
            },
            {
                "commodity": "lighting", "region": "SINGLE",
                "sector": "COM", "values": {"2020": 30},
            },
        ],
    }
    jsonschema.validate(data, schema)
