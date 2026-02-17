"""Tests for process IR structures.

Tests the P2 implementation of vedalang-f8j:
roles/variants/availability → process instances.
"""

import pytest

from vedalang.compiler.ir import (
    InstanceKey,
    IRError,
    ProcessInstance,
    Role,
    Variant,
    apply_process_parameters,
    build_commodities_dict,
    build_roles,
    build_variants,
    expand_availability,
    lower_instances_to_tableir,
    validate_demand_feasibility,
)


class TestRole:
    """Tests for Role dataclass."""

    def test_role_creation(self):
        """Role can be created with required fields."""
        role = Role(id="generate_electricity", inputs=[], outputs=["electricity"])
        assert role.id == "generate_electricity"
        assert role.inputs == []
        assert role.outputs == ["electricity"]
        assert role.stage is None

    def test_role_with_stage(self):
        """Role can have optional stage."""
        role = Role(
            id="deliver_lighting",
            inputs=["electricity"],
            outputs=["lighting"],
            stage="end_use",
        )
        assert role.stage == "end_use"


class TestVariant:
    """Tests for Variant dataclass."""

    def test_variant_creation(self):
        """Variant can be created with role reference."""
        role = Role(id="generate_electricity", inputs=[], outputs=["electricity"])
        variant = Variant(id="simple_generator", role=role)
        assert variant.id == "simple_generator"
        assert variant.role is role
        assert variant.attrs == {}

    def test_variant_with_attrs(self):
        """Variant can have attributes."""
        role = Role(id="deliver_lighting", inputs=["electricity"], outputs=["lighting"])
        variant = Variant(
            id="led_lighting",
            role=role,
            attrs={"efficiency": 0.4, "lifetime": 15},
        )
        assert variant.attrs["efficiency"] == 0.4
        assert variant.attrs["lifetime"] == 15


class TestInstanceKey:
    """Tests for InstanceKey named tuple."""

    def test_instance_key_creation(self):
        """InstanceKey can be created."""
        key = InstanceKey(variant_id="led_lighting", region="SINGLE", segment="RES")
        assert key.variant_id == "led_lighting"
        assert key.region == "SINGLE"
        assert key.segment == "RES"

    def test_instance_key_no_segment(self):
        """InstanceKey can have None segment (supply-side)."""
        key = InstanceKey(variant_id="generator", region="SINGLE", segment=None)
        assert key.segment is None

    def test_instance_key_hashable(self):
        """InstanceKey is hashable for dict keys."""
        key1 = InstanceKey("var", "REG", "SEG")
        key2 = InstanceKey("var", "REG", "SEG")
        assert hash(key1) == hash(key2)
        d = {key1: "value"}
        assert d[key2] == "value"


class TestProcessInstance:
    """Tests for ProcessInstance dataclass."""

    def test_process_instance_creation(self):
        """ProcessInstance can be created."""
        role = Role(id="test_role", inputs=[], outputs=["out"])
        variant = Variant(id="test_variant", role=role, attrs={"efficiency": 0.5})
        key = InstanceKey("test_variant", "REG", "SEG")
        instance = ProcessInstance(
            key=key,
            role=role,
            variant=variant,
            attrs={"efficiency": 0.5},
        )
        assert instance.key == key
        assert instance.role is role
        assert instance.variant is variant
        assert instance.attrs["efficiency"] == 0.5


class TestBuildRoles:
    """Tests for build_roles()."""

    def test_empty_process_roles(self):
        """Empty process_roles returns empty dict."""
        commodities = {"electricity": {"id": "electricity", "kind": "carrier"}}
        assert build_roles({}, commodities) == {}
        assert build_roles({"process_roles": []}, commodities) == {}

    def test_single_role(self):
        """Single role is built correctly."""
        model = {
            "process_roles": [
                {
                    "id": "generate_electricity",
                    "stage": "conversion",
                    "inputs": [],
                    "outputs": [{"commodity": "electricity"}],
                }
            ]
        }
        commodities = {"electricity": {"id": "electricity", "kind": "carrier"}}
        roles = build_roles(model, commodities)

        assert "generate_electricity" in roles
        role = roles["generate_electricity"]
        assert role.id == "generate_electricity"
        assert role.inputs == []
        assert role.outputs == ["electricity"]
        assert role.stage == "conversion"

    def test_role_with_inputs_and_outputs(self):
        """Role with both inputs and outputs."""
        model = {
            "process_roles": [
                {
                    "id": "deliver_lighting",
                    "inputs": [{"commodity": "electricity"}],
                    "outputs": [{"commodity": "lighting"}],
                }
            ]
        }
        commodities = {
            "electricity": {"id": "electricity", "kind": "carrier"},
            "lighting": {"id": "lighting", "kind": "service"},
        }
        roles = build_roles(model, commodities)

        role = roles["deliver_lighting"]
        assert role.inputs == ["electricity"]
        assert role.outputs == ["lighting"]

    def test_duplicate_role_id_raises(self):
        """Duplicate role id raises IRError."""
        model = {
            "process_roles": [
                {"id": "dup_role", "outputs": [{"commodity": "elec"}]},
                {"id": "dup_role", "outputs": [{"commodity": "elec"}]},
            ]
        }
        commodities = {"elec": {"id": "elec", "kind": "carrier"}}
        with pytest.raises(IRError, match="Duplicate role id: dup_role"):
            build_roles(model, commodities)

    def test_unknown_input_commodity_raises(self):
        """Unknown input commodity raises IRError."""
        model = {
            "process_roles": [
                {
                    "id": "test_role",
                    "inputs": [{"commodity": "unknown"}],
                    "outputs": [],
                }
            ]
        }
        with pytest.raises(IRError, match="unknown input commodity: unknown"):
            build_roles(model, {})

    def test_unknown_output_commodity_raises(self):
        """Unknown output commodity raises IRError."""
        model = {
            "process_roles": [
                {
                    "id": "test_role",
                    "inputs": [],
                    "outputs": [{"commodity": "unknown"}],
                }
            ]
        }
        with pytest.raises(IRError, match="unknown output commodity: unknown"):
            build_roles(model, {})


class TestBuildVariants:
    """Tests for build_variants()."""

    def test_empty_process_variants(self):
        """Empty process_variants returns empty dict."""
        roles = {"role1": Role(id="role1", inputs=[], outputs=[])}
        assert build_variants({}, roles) == {}
        assert build_variants({"process_variants": []}, roles) == {}

    def test_single_variant(self):
        """Single variant is built correctly."""
        roles = {
            "generate_electricity": Role(
                id="generate_electricity", inputs=[], outputs=["electricity"]
            )
        }
        model = {
            "process_variants": [
                {
                    "id": "simple_generator",
                    "role": "generate_electricity",
                    "efficiency": 1.0,
                    "lifetime": 40,
                }
            ]
        }
        variants = build_variants(model, roles)

        assert "simple_generator" in variants
        variant = variants["simple_generator"]
        assert variant.id == "simple_generator"
        assert variant.role is roles["generate_electricity"]
        assert variant.attrs["efficiency"] == 1.0
        assert variant.attrs["lifetime"] == 40

    def test_variant_with_all_attrs(self):
        """Variant with all supported attributes."""
        roles = {"role1": Role(id="role1", inputs=[], outputs=[])}
        model = {
            "process_variants": [
                {
                    "id": "full_variant",
                    "role": "role1",
                    "efficiency": 0.5,
                    "lifetime": 20,
                    "investment_cost": 1000,
                    "fixed_om_cost": 50,
                    "variable_om_cost": 10,
                    "emission_factors": {"co2": 0.1},
                }
            ]
        }
        variants = build_variants(model, roles)
        attrs = variants["full_variant"].attrs

        assert attrs["efficiency"] == 0.5
        assert attrs["lifetime"] == 20
        assert attrs["investment_cost"] == 1000
        assert attrs["fixed_om_cost"] == 50
        assert attrs["variable_om_cost"] == 10
        assert attrs["emission_factors"] == {"co2": 0.1}

    def test_duplicate_variant_id_raises(self):
        """Duplicate variant id raises IRError."""
        roles = {"role1": Role(id="role1", inputs=[], outputs=[])}
        model = {
            "process_variants": [
                {"id": "dup", "role": "role1"},
                {"id": "dup", "role": "role1"},
            ]
        }
        with pytest.raises(IRError, match="Duplicate variant id: dup"):
            build_variants(model, roles)

    def test_unknown_role_raises(self):
        """Unknown role reference raises IRError."""
        model = {
            "process_variants": [{"id": "var1", "role": "unknown_role"}]
        }
        with pytest.raises(IRError, match="unknown role: unknown_role"):
            build_variants(model, {})


class TestExpandAvailability:
    """Tests for expand_availability()."""

    def test_empty_availability(self):
        """Empty availability returns empty dict."""
        variants = {"var1": Variant(id="var1", role=Role("r", [], []))}
        assert expand_availability({}, variants, []) == {}
        assert expand_availability({"availability": []}, variants, []) == {}

    def test_simple_availability_no_segment(self):
        """Availability without sectors/segments creates None segment."""
        role = Role(id="generate", inputs=[], outputs=["elec"])
        variants = {"gen": Variant(id="gen", role=role)}
        model = {"availability": [{"variant": "gen", "regions": ["REG1"]}]}

        instances = expand_availability(model, variants, [])

        assert len(instances) == 1
        key = InstanceKey("gen", "REG1", None)
        assert key in instances
        assert instances[key].variant is variants["gen"]

    def test_availability_with_sectors_coarse(self):
        """Availability with sectors (no end_uses) expands to sectors."""
        role = Role(id="deliver", inputs=["elec"], outputs=["heat"])
        variants = {"heat_pump": Variant(id="heat_pump", role=role)}
        model = {
            "segments": {"sectors": ["RES", "COM"]},
            "availability": [
                {"variant": "heat_pump", "regions": ["REG"], "sectors": ["RES", "COM"]}
            ],
        }
        segment_keys = ["RES", "COM"]

        instances = expand_availability(model, variants, segment_keys)

        assert len(instances) == 2
        assert InstanceKey("heat_pump", "REG", "RES") in instances
        assert InstanceKey("heat_pump", "REG", "COM") in instances

    def test_availability_with_sectors_fine_granularity(self):
        """Availability with sectors expands to sector.end_use when end_uses defined."""
        role = Role(id="deliver", inputs=[], outputs=[])
        variants = {"var": Variant(id="var", role=role)}
        model = {
            "segments": {
                "sectors": ["RES", "COM"],
                "end_uses": ["lighting", "heating"],
            },
            "availability": [{"variant": "var", "regions": ["R1"], "sectors": ["RES"]}],
        }
        segment_keys = ["RES.lighting", "RES.heating", "COM.lighting", "COM.heating"]

        instances = expand_availability(model, variants, segment_keys)

        assert len(instances) == 2
        assert InstanceKey("var", "R1", "RES.lighting") in instances
        assert InstanceKey("var", "R1", "RES.heating") in instances
        assert InstanceKey("var", "R1", "COM.lighting") not in instances

    def test_availability_with_explicit_segments(self):
        """Availability with explicit segments uses those exactly."""
        role = Role(id="deliver", inputs=[], outputs=[])
        variants = {"var": Variant(id="var", role=role)}
        model = {
            "segments": {
                "sectors": ["RES", "COM"],
                "end_uses": ["lighting", "heating"],
            },
            "availability": [
                {
                    "variant": "var",
                    "regions": ["R1"],
                    "segments": ["RES.lighting", "COM.heating"],
                }
            ],
        }
        segment_keys = ["RES.lighting", "RES.heating", "COM.lighting", "COM.heating"]

        instances = expand_availability(model, variants, segment_keys)

        assert len(instances) == 2
        assert InstanceKey("var", "R1", "RES.lighting") in instances
        assert InstanceKey("var", "R1", "COM.heating") in instances

    def test_availability_multiple_regions(self):
        """Availability expands across multiple regions."""
        role = Role(id="gen", inputs=[], outputs=[])
        variants = {"gen": Variant(id="gen", role=role)}
        model = {
            "availability": [{"variant": "gen", "regions": ["R1", "R2", "R3"]}]
        }

        instances = expand_availability(model, variants, [])

        assert len(instances) == 3
        assert InstanceKey("gen", "R1", None) in instances
        assert InstanceKey("gen", "R2", None) in instances
        assert InstanceKey("gen", "R3", None) in instances

    def test_unknown_variant_raises(self):
        """Unknown variant in availability raises IRError."""
        model = {"availability": [{"variant": "unknown", "regions": ["R1"]}]}
        with pytest.raises(IRError, match="unknown variant: unknown"):
            expand_availability(model, {}, [])

    def test_instance_inherits_variant_attrs(self):
        """ProcessInstance inherits variant attrs."""
        role = Role(id="gen", inputs=[], outputs=[])
        variant = Variant(
            id="gen", role=role, attrs={"efficiency": 0.5, "lifetime": 30}
        )
        variants = {"gen": variant}
        model = {"availability": [{"variant": "gen", "regions": ["R1"]}]}

        instances = expand_availability(model, variants, [])

        instance = instances[InstanceKey("gen", "R1", None)]
        assert instance.attrs["efficiency"] == 0.5
        assert instance.attrs["lifetime"] == 30


class TestApplyProcessParameters:
    """Tests for apply_process_parameters()."""

    def test_no_parameters(self):
        """No process_parameters leaves instances unchanged."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="v", role=role, attrs={"efficiency": 0.5})
        key = InstanceKey("v", "R1", None)
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }

        apply_process_parameters(instances, {})

        assert instances[key].attrs == {}

    def test_exact_match_applies(self):
        """Selector with exact variant+region match applies."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="gen", role=role)
        key = InstanceKey("gen", "REG", None)
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }

        model = {
            "process_parameters": [
                {
                    "selector": {"variant": "gen", "region": "REG"},
                    "cap_bound": {"up": 100},
                }
            ]
        }
        apply_process_parameters(instances, model)

        assert instances[key].attrs["cap_bound"] == {"up": 100}

    def test_segment_exact_match(self):
        """Selector with segment matches exactly."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="v", role=role)
        key1 = InstanceKey("v", "R1", "RES")
        key2 = InstanceKey("v", "R1", "COM")
        instances = {
            key1: ProcessInstance(key=key1, role=role, variant=variant, attrs={}),
            key2: ProcessInstance(key=key2, role=role, variant=variant, attrs={}),
        }

        model = {
            "process_parameters": [
                {
                    "selector": {"variant": "v", "region": "R1", "segment": "RES"},
                    "stock": 50,
                }
            ]
        }
        apply_process_parameters(instances, model)

        assert instances[key1].attrs["stock"] == 50
        assert "stock" not in instances[key2].attrs

    def test_sector_matches_segment_prefix(self):
        """Selector with sector matches segments starting with that sector."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="v", role=role)
        key1 = InstanceKey("v", "R1", "RES.lighting")
        key2 = InstanceKey("v", "R1", "RES.heating")
        key3 = InstanceKey("v", "R1", "COM.lighting")
        instances = {
            key1: ProcessInstance(key=key1, role=role, variant=variant, attrs={}),
            key2: ProcessInstance(key=key2, role=role, variant=variant, attrs={}),
            key3: ProcessInstance(key=key3, role=role, variant=variant, attrs={}),
        }

        model = {
            "segments": {
                "sectors": ["RES", "COM"],
                "end_uses": ["lighting", "heating"],
            },
            "process_parameters": [
                {
                    "selector": {"variant": "v", "region": "R1", "sector": "RES"},
                    "activity_bound": {"up": 1000},
                }
            ],
        }
        apply_process_parameters(instances, model)

        assert instances[key1].attrs["activity_bound"] == {"up": 1000}
        assert instances[key2].attrs["activity_bound"] == {"up": 1000}
        assert "activity_bound" not in instances[key3].attrs

    def test_multiple_parameters_merge(self):
        """Multiple matching parameter blocks merge."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="v", role=role)
        key = InstanceKey("v", "R1", None)
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }

        model = {
            "process_parameters": [
                {
                    "selector": {"variant": "v", "region": "R1"},
                    "cap_bound": {"up": 100},
                },
                {
                    "selector": {"variant": "v", "region": "R1"},
                    "ncap_bound": {"lo": 10},
                },
            ]
        }
        apply_process_parameters(instances, model)

        assert instances[key].attrs["cap_bound"] == {"up": 100}
        assert instances[key].attrs["ncap_bound"] == {"lo": 10}

    def test_later_parameter_overrides(self):
        """Later parameter block overrides earlier for same key."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="v", role=role)
        key = InstanceKey("v", "R1", None)
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }

        model = {
            "process_parameters": [
                {"selector": {"variant": "v", "region": "R1"}, "stock": 100},
                {"selector": {"variant": "v", "region": "R1"}, "stock": 200},
            ]
        }
        apply_process_parameters(instances, model)

        assert instances[key].attrs["stock"] == 200


class TestLowerInstancesToTableir:
    """Tests for lower_instances_to_tableir()."""

    def test_empty_instances(self):
        """Empty instances returns empty list."""
        assert lower_instances_to_tableir({}, {}, []) == []

    def test_simple_process(self):
        """Simple process is lowered correctly."""
        role = Role(id="generate", inputs=[], outputs=["electricity"])
        variant = Variant(id="gen", role=role)
        key = InstanceKey("gen", "REG", None)
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }
        commodities = {"electricity": {"id": "electricity", "kind": "carrier"}}

        rows = lower_instances_to_tableir(instances, commodities, [])

        assert len(rows) == 1
        row = rows[0]
        assert row["prc"] == "gen_REG"
        assert row["region"] == "REG"
        assert row["com_out"] == "electricity"
        assert "com_in" not in row

    def test_process_with_inputs_and_outputs(self):
        """Process with inputs and outputs."""
        role = Role(id="deliver", inputs=["electricity"], outputs=["lighting"])
        variant = Variant(id="led", role=role)
        key = InstanceKey("led", "R1", "RES")
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }
        commodities = {
            "electricity": {"id": "electricity", "kind": "carrier", "tradable": True},
            "lighting": {"id": "lighting", "kind": "service", "tradable": False},
        }

        rows = lower_instances_to_tableir(instances, commodities, ["RES"])

        row = rows[0]
        assert row["prc"] == "led_R1_RES"
        assert row["com_in"] == "electricity"
        assert row["com_out"] == "lighting@RES"
        assert row["sets"] == "DMD"

    def test_numeric_attrs_included(self):
        """Numeric attributes are included in row."""
        role = Role(id="gen", inputs=[], outputs=[])
        variant = Variant(id="gen", role=role)
        key = InstanceKey("gen", "R1", None)
        instances = {
            key: ProcessInstance(
                key=key,
                role=role,
                variant=variant,
                attrs={
                    "efficiency": 0.5,
                    "lifetime": 30,
                    "investment_cost": 1000,
                    "fixed_om_cost": 50,
                    "variable_om_cost": 10,
                },
            )
        }

        rows = lower_instances_to_tableir(instances, {}, [])

        row = rows[0]
        assert row["eff"] == 0.5
        assert row["ncap_tlife"] == 30
        assert row["ncap_cost"] == 1000
        assert row["ncap_fom"] == 50
        assert row["act_cost"] == 10

    def test_segment_in_process_name(self):
        """Segment is included in process name with underscore."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="v", role=role)
        key = InstanceKey("v", "R1", "RES.lighting")
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }

        rows = lower_instances_to_tableir(instances, {}, [])

        assert rows[0]["prc"] == "v_R1_RES_lighting"

    def test_sorted_by_key(self):
        """Output is sorted by instance key."""
        role = Role(id="r", inputs=[], outputs=[])
        variant = Variant(id="v", role=role)
        instances = {
            InstanceKey("v", "R2", None): ProcessInstance(
                InstanceKey("v", "R2", None), role, variant, {}
            ),
            InstanceKey("v", "R1", None): ProcessInstance(
                InstanceKey("v", "R1", None), role, variant, {}
            ),
        }

        rows = lower_instances_to_tableir(instances, {}, [])

        assert rows[0]["prc"] == "v_R1"
        assert rows[1]["prc"] == "v_R2"


class TestValidateDemandFeasibility:
    """Tests for validate_demand_feasibility()."""

    def test_no_demands(self):
        """No demands returns no errors."""
        assert validate_demand_feasibility([], {}, {}) == []

    def test_demand_with_producer(self):
        """Demand with matching producer has no error."""
        role = Role(id="deliver", inputs=[], outputs=["lighting"])
        variant = Variant(id="led", role=role)
        key = InstanceKey("led", "REG", "RES")
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }
        demands = [{"commodity": "lighting", "region": "REG", "sector": "RES"}]
        commodities = {"lighting": {"id": "lighting", "kind": "service"}}

        errors = validate_demand_feasibility(demands, instances, commodities)

        assert errors == []

    def test_demand_without_producer(self):
        """Demand without matching producer returns error."""
        instances = {}
        demands = [{"commodity": "lighting", "region": "REG", "sector": "RES"}]
        commodities = {"lighting": {"id": "lighting", "kind": "service"}}

        errors = validate_demand_feasibility(demands, instances, commodities)

        assert len(errors) == 1
        assert "lighting" in errors[0]
        assert "REG" in errors[0]
        assert "RES" in errors[0]
        assert "no available producer" in errors[0]

    def test_demand_with_segment_field(self):
        """Demand with 'segment' field is checked."""
        role = Role(id="deliver", inputs=[], outputs=["heat"])
        variant = Variant(id="hp", role=role)
        key = InstanceKey("hp", "R1", "RES.heating")
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }
        demands = [{"commodity": "heat", "region": "R1", "segment": "RES.heating"}]

        errors = validate_demand_feasibility(demands, instances, {})

        assert errors == []

    def test_demand_wrong_region(self):
        """Demand in different region than producer returns error."""
        role = Role(id="deliver", inputs=[], outputs=["lighting"])
        variant = Variant(id="led", role=role)
        key = InstanceKey("led", "REG1", "RES")
        instances = {
            key: ProcessInstance(key=key, role=role, variant=variant, attrs={})
        }
        demands = [{"commodity": "lighting", "region": "REG2", "sector": "RES"}]

        errors = validate_demand_feasibility(demands, instances, {})

        assert len(errors) == 1
        assert "REG2" in errors[0]


class TestBuildCommoditiesDict:
    """Tests for build_commodities_dict()."""

    def test_empty_model(self):
        """Empty model returns empty dict."""
        assert build_commodities_dict({}) == {}
        assert build_commodities_dict({"model": {}}) == {}
        assert build_commodities_dict({"model": {"commodities": []}}) == {}

    def test_single_commodity(self):
        """Single commodity is normalized."""
        model = {
            "model": {
                "commodities": [{"id": "electricity", "kind": "carrier", "unit": "PJ"}]
            }
        }
        result = build_commodities_dict(model)

        assert "electricity" in result
        assert result["electricity"]["kind"] == "carrier"
        assert result["electricity"]["tradable"] is True

    def test_multiple_commodities(self):
        """Multiple commodities are normalized."""
        model = {
            "model": {
                "commodities": [
                    {"id": "electricity", "kind": "carrier"},
                    {"id": "lighting", "kind": "service"},
                    {"id": "co2", "kind": "emission"},
                ]
            }
        }
        result = build_commodities_dict(model)

        assert len(result) == 3
        assert result["electricity"]["kind"] == "carrier"
        assert result["lighting"]["kind"] == "service"
        assert result["co2"]["kind"] == "emission"
