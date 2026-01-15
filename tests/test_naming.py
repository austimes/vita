"""Tests for NamingRegistry deterministic symbol generation.

Tests the P3 implementation of vedalang-awg: deterministic naming.
"""

from vedalang.compiler.naming import NamingRegistry


class TestNamingRegistryCommodities:
    """Tests for commodity symbol generation."""

    def test_simple_commodity(self):
        """Simple commodity without segment."""
        reg = NamingRegistry()
        result = reg.get_commodity_symbol("electricity")
        assert result == "electricity"

    def test_commodity_with_none_segment(self):
        """Commodity with explicit None segment."""
        reg = NamingRegistry()
        result = reg.get_commodity_symbol("electricity", None)
        assert result == "electricity"

    def test_commodity_with_segment(self):
        """Commodity with segment is scoped."""
        reg = NamingRegistry()
        result = reg.get_commodity_symbol("lighting", "RES")
        assert result == "lighting@RES"

    def test_commodity_with_fine_segment(self):
        """Commodity with sector.end_use segment."""
        reg = NamingRegistry()
        result = reg.get_commodity_symbol("lighting", "RES.lighting")
        assert result == "lighting@RES.lighting"

    def test_commodity_caching(self):
        """Same commodity returns same symbol on repeated calls."""
        reg = NamingRegistry()
        first = reg.get_commodity_symbol("lighting", "RES")
        second = reg.get_commodity_symbol("lighting", "RES")
        assert first == second
        assert first is second  # Same object (cached)

    def test_different_segments_different_symbols(self):
        """Same commodity with different segments gets different symbols."""
        reg = NamingRegistry()
        res = reg.get_commodity_symbol("lighting", "RES")
        com = reg.get_commodity_symbol("lighting", "COM")
        assert res == "lighting@RES"
        assert com == "lighting@COM"
        assert res != com

    def test_get_all_commodities(self):
        """get_all_commodities returns all registered symbols."""
        reg = NamingRegistry()
        reg.get_commodity_symbol("electricity")
        reg.get_commodity_symbol("lighting", "RES")
        reg.get_commodity_symbol("lighting", "COM")

        all_comms = reg.get_all_commodities()
        assert len(all_comms) == 3
        assert ("electricity", None) in all_comms
        assert ("lighting", "RES") in all_comms
        assert ("lighting", "COM") in all_comms


class TestNamingRegistryProcesses:
    """Tests for process symbol generation."""

    def test_simple_process(self):
        """Process without segment."""
        reg = NamingRegistry()
        result = reg.get_process_symbol("generator", "SINGLE")
        assert result == "generator_SINGLE"

    def test_process_with_none_segment(self):
        """Process with explicit None segment."""
        reg = NamingRegistry()
        result = reg.get_process_symbol("generator", "R1", None)
        assert result == "generator_R1"

    def test_process_with_segment(self):
        """Process with segment."""
        reg = NamingRegistry()
        result = reg.get_process_symbol("led_lighting", "SINGLE", "RES")
        assert result == "led_lighting_SINGLE_RES"

    def test_process_with_fine_segment(self):
        """Process with sector.end_use segment replaces dot with underscore."""
        reg = NamingRegistry()
        result = reg.get_process_symbol("led", "R1", "RES.lighting")
        assert result == "led_R1_RES_lighting"

    def test_process_caching(self):
        """Same process returns same symbol on repeated calls."""
        reg = NamingRegistry()
        first = reg.get_process_symbol("led", "R1", "RES")
        second = reg.get_process_symbol("led", "R1", "RES")
        assert first == second
        assert first is second  # Same object (cached)

    def test_different_regions_different_symbols(self):
        """Same variant in different regions gets different symbols."""
        reg = NamingRegistry()
        r1 = reg.get_process_symbol("led", "R1", "RES")
        r2 = reg.get_process_symbol("led", "R2", "RES")
        assert r1 == "led_R1_RES"
        assert r2 == "led_R2_RES"
        assert r1 != r2

    def test_get_all_processes(self):
        """get_all_processes returns all registered symbols."""
        reg = NamingRegistry()
        reg.get_process_symbol("generator", "R1")
        reg.get_process_symbol("led", "R1", "RES")
        reg.get_process_symbol("led", "R2", "RES")

        all_procs = reg.get_all_processes()
        assert len(all_procs) == 3
        assert ("generator", "R1", None) in all_procs
        assert ("led", "R1", "RES") in all_procs
        assert ("led", "R2", "RES") in all_procs


class TestNamingRegistryClear:
    """Tests for clear functionality."""

    def test_clear_removes_all(self):
        """clear() removes all registered symbols."""
        reg = NamingRegistry()
        reg.get_commodity_symbol("electricity")
        reg.get_process_symbol("generator", "R1")

        assert len(reg.get_all_commodities()) == 1
        assert len(reg.get_all_processes()) == 1

        reg.clear()

        assert len(reg.get_all_commodities()) == 0
        assert len(reg.get_all_processes()) == 0


class TestNamingStability:
    """Tests for naming stability and determinism."""

    def test_stability_across_calls(self):
        """Same inputs always produce same outputs."""
        reg = NamingRegistry()

        for _ in range(3):
            assert reg.get_commodity_symbol("elec") == "elec"
            assert reg.get_commodity_symbol("light", "RES") == "light@RES"
            assert reg.get_process_symbol("gen", "R1") == "gen_R1"
            assert reg.get_process_symbol("led", "R1", "RES") == "led_R1_RES"

    def test_order_independence(self):
        """Registration order doesn't affect symbol values."""
        reg1 = NamingRegistry()
        reg1.get_commodity_symbol("a")
        reg1.get_commodity_symbol("b")
        reg1.get_commodity_symbol("c")

        reg2 = NamingRegistry()
        reg2.get_commodity_symbol("c")
        reg2.get_commodity_symbol("a")
        reg2.get_commodity_symbol("b")

        assert reg1.get_commodity_symbol("a") == reg2.get_commodity_symbol("a")
        assert reg1.get_commodity_symbol("b") == reg2.get_commodity_symbol("b")
        assert reg1.get_commodity_symbol("c") == reg2.get_commodity_symbol("c")

    def test_deterministic_model_compilation(self):
        """Simulated model compilation produces identical results."""
        def compile_model(reg: NamingRegistry) -> list[str]:
            symbols = []
            commodities = ["electricity", "gas", "lighting", "co2"]
            for c in sorted(commodities):
                symbols.append(reg.get_commodity_symbol(c))
            for region in sorted(["R1", "R2"]):
                for variant in sorted(["generator", "led", "boiler"]):
                    symbols.append(reg.get_process_symbol(variant, region))
            return symbols

        result1 = compile_model(NamingRegistry())
        result2 = compile_model(NamingRegistry())

        assert result1 == result2


class TestNamingStabilityIntegration:
    """Integration tests for naming stability with IR pipeline."""

    def test_compile_same_model_twice_identical_output(self):
        """Compile same model twice, assert identical symbol output.

        This tests FR17: emitted symbol stability across compilation runs.
        """
        from vedalang.compiler.ir import (
            InstanceKey,
            ProcessInstance,
            Role,
            Variant,
            lower_instances_to_tableir,
        )

        def compile_model() -> list[dict]:
            registry = NamingRegistry()
            role = Role(
                id="deliver_lighting",
                inputs=["electricity"],
                outputs=["lighting"],
            )
            variant = Variant(
                id="led_lighting",
                role=role,
                attrs={"efficiency": 0.4, "lifetime": 15},
            )
            instances = {
                InstanceKey("led_lighting", "R1", "RES"): ProcessInstance(
                    key=InstanceKey("led_lighting", "R1", "RES"),
                    role=role,
                    variant=variant,
                    attrs=dict(variant.attrs),
                ),
                InstanceKey("led_lighting", "R2", "RES"): ProcessInstance(
                    key=InstanceKey("led_lighting", "R2", "RES"),
                    role=role,
                    variant=variant,
                    attrs=dict(variant.attrs),
                ),
                InstanceKey("led_lighting", "R1", "COM"): ProcessInstance(
                    key=InstanceKey("led_lighting", "R1", "COM"),
                    role=role,
                    variant=variant,
                    attrs=dict(variant.attrs),
                ),
            }
            commodities = {
                "electricity": {
                    "id": "electricity",
                    "kind": "carrier",
                    "tradable": True,
                },
                "lighting": {
                    "id": "lighting",
                    "kind": "service",
                    "tradable": False,
                },
            }
            segment_keys = ["RES", "COM"]
            return lower_instances_to_tableir(
                instances, commodities, segment_keys, registry
            )

        result1 = compile_model()
        result2 = compile_model()

        assert result1 == result2
        assert len(result1) == 3
        prc_names = [r["prc"] for r in result1]
        assert prc_names == sorted(prc_names)
