"""Tests for MiniSystem incremental model fixtures.

Each MiniSystem fixture (1-8) tests progressively more complex VedaLang features.
These tests verify:
1. Compilation succeeds (VedaLang → TableIR)
2. TableIR validates against schema
3. xl2times validation passes (Excel → DD)
4. Expected model structure is present

Expected solutions (objective values) require GAMS/TIMES which may not be available.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from tools.veda_emit_excel import emit_excel
from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"


# Expected features per increment
# NOTE: New P4 syntax uses snake_case commodity/variant IDs, not legacy C:/S: prefixes
MINISYSTEM_FEATURES = {
    1: {
        "description": "Minimal solvable model",
        "commodities": {"electricity", "residential_demand"},
        "processes": {"simple_generator_SINGLE", "residential_device_SINGLE_RES"},
        "features": ["basic RES", "demand projection"],
    },
    2: {
        "description": "Fuel chain",
        "commodities": {"gas", "electricity", "residential_demand"},
        "processes": {"gas_import_SINGLE", "ccgt_SINGLE", "residential_device_SINGLE_RES"},
        "features": ["input-output chains", "fuel supply"],
    },
    3: {
        "description": "Investment decisions",
        "commodities": {"gas", "electricity", "residential_demand"},
        "processes": {"gas_import_SINGLE", "ccgt_SINGLE", "residential_device_SINGLE_RES"},
        "features": ["investment_cost", "fixed_om_cost", "variable_om_cost", "lifetime"],
    },
    4: {
        "description": "Emissions",
        "commodities": {"gas", "electricity", "residential_demand", "co2"},
        "processes": {"gas_import_SINGLE", "ccgt_SINGLE", "residential_device_SINGLE_RES"},
        "features": ["emission tracking", "ENV_ACT"],
    },
    5: {
        "description": "Multiple generators",
        "commodities": {"gas", "electricity", "residential_demand", "co2"},
        "processes": {"gas_import_SINGLE", "ccgt_SINGLE", "wind_SINGLE", "residential_device_SINGLE_RES"},
        "features": ["renewable generation", "technology choice"],
    },
    6: {
        "description": "Scenario parameters",
        "commodities": {"gas", "electricity", "residential_demand", "co2"},
        "processes": {"gas_import_SINGLE", "ccgt_SINGLE", "wind_SINGLE", "residential_device_SINGLE_RES"},
        "features": ["CO2 price", "scenario files"],
    },
    7: {
        "description": "Multi-region",
        "commodities": {"gas", "electricity", "residential_demand", "co2"},
        # Process names include region, so we check for NORTH variants
        "processes": {"gas_import_NORTH", "ccgt_NORTH", "wind_NORTH", "residential_device_NORTH_RES"},
        "features": ["multiple regions", "trade links"],
    },
    8: {
        "description": "Australian baseline scaffold",
        "commodities": {"gas", "coal", "electricity", "hydrogen", "co2",
                        "residential_demand", "commercial_demand", "industrial_demand", "transport_demand"},
        # Check NEM_EAST region processes
        "processes": {
            "gas_import_NEM_EAST", "coal_import_NEM_EAST", "coal_plant_NEM_EAST",
            "ccgt_NEM_EAST", "wind_NEM_EAST", "solar_NEM_EAST",
            "smr_NEM_EAST", "electrolyzer_NEM_EAST",
        },
        "features": ["multi-sector", "hydrogen", "4 demand sectors"],
    },
}


@pytest.fixture
def get_minisystem_path():
    """Get path to a minisystem fixture by number."""
    def _get(n: int) -> Path:
        path = EXAMPLES_DIR / f"minisystem{n}.veda.yaml"
        if not path.exists():
            pytest.skip(f"minisystem{n}.veda.yaml not found")
        return path
    return _get


class TestMiniSystemCompilation:
    """Test that each minisystem fixture compiles successfully."""

    @pytest.mark.parametrize("n", range(1, 9))
    def test_minisystem_compiles(self, n, get_minisystem_path):
        """Each minisystem fixture should compile without errors."""
        path = get_minisystem_path(n)
        source = load_vedalang(path)
        tableir = compile_vedalang_to_tableir(source)

        # Basic structure checks
        assert "files" in tableir
        assert len(tableir["files"]) >= 1

        # Should have expected commodities
        expected = MINISYSTEM_FEATURES.get(n, {})
        if "commodities" in expected:
            comm_names = set()
            for f in tableir["files"]:
                for s in f["sheets"]:
                    for t in s["tables"]:
                        if t["tag"] == "~FI_COMM":
                            comm_names.update(r.get("commodity") for r in t["rows"])
            missing = expected["commodities"] - comm_names
            assert not missing, f"Missing commodities: {missing}"

        # Should have expected processes
        if "processes" in expected:
            proc_names = set()
            for f in tableir["files"]:
                for s in f["sheets"]:
                    for t in s["tables"]:
                        if t["tag"] == "~FI_PROCESS":
                            proc_names.update(r.get("process") for r in t["rows"])
            missing = expected["processes"] - proc_names
            assert not missing, f"Missing processes: {missing}"


class TestMiniSystemXl2times:
    """Test that each minisystem fixture passes xl2times validation."""

    @pytest.mark.parametrize("n", range(1, 9))
    def test_minisystem_xl2times_validation(self, n, get_minisystem_path):
        """Each minisystem should pass xl2times validation."""
        path = get_minisystem_path(n)
        source = load_vedalang(path)
        tableir = compile_vedalang_to_tableir(source)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            emit_excel(tableir, tmpdir)

            # Run xl2times
            result = subprocess.run(
                [
                    "uv", "run", "python", "-m", "xl2times",
                    str(tmpdir),
                    "--diagnostics-json", str(tmpdir / "diag.json"),
                ],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )

            # Should succeed
            assert result.returncode == 0, (
                f"xl2times failed for minisystem{n}:\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )


class TestMiniSystem1ExpectedSolution:
    """Test expected solution for MiniSystem1.

    MiniSystem1 is the simplest possible model:
    - Single region, single period (2020, 10 years)
    - PP_SIMPLE: generator with cost=10, stock=100, outputs ELC
    - DMD_RSD: demand device with stock=100, inputs ELC, outputs RSD
    - Demand: 50 PJ in 2020

    Expected solution:
    - PP_SIMPLE activity: 50 PJ (to meet demand)
    - DMD_RSD activity: 50 PJ (pass-through)
    - Objective: 50 PJ × 10 = 500 (activity cost)

    Note: This ignores TIMES period-length scaling. With 10-year period,
    TIMES would compute 50 PJ/yr × 10 years × 10 cost/PJ = 5000.
    """

    def test_minisystem1_has_activity_cost(self, get_minisystem_path):
        """MiniSystem1 simple_generator should have act_cost (new P4 syntax)."""
        path = get_minisystem_path(1)
        source = load_vedalang(path)
        tableir = compile_vedalang_to_tableir(source)

        # Find simple_generator cost row (process name is simple_generator_SINGLE)
        for f in tableir["files"]:
            for s in f["sheets"]:
                for t in s["tables"]:
                    if t["tag"] == "~FI_T":
                        for row in t["rows"]:
                            if "simple_generator" in row.get("process", "") and "act_cost" in row:
                                assert row["act_cost"] == 10
                                return

        pytest.fail("simple_generator should have act_cost=10")

    def test_minisystem1_has_demand_projection(self, get_minisystem_path):
        """MiniSystem1 should have a demand projection for residential_demand."""
        path = get_minisystem_path(1)
        source = load_vedalang(path)
        tableir = compile_vedalang_to_tableir(source)

        # Find demand projection in scenario file
        for f in tableir["files"]:
            if "scen_" in f["path"].lower():
                for s in f["sheets"]:
                    for t in s["tables"]:
                        if t["tag"] == "~TFM_DINS-AT":
                            for row in t["rows"]:
                                # New P4 syntax uses residential_demand@RES for scoped demand
                                if "residential_demand" in str(row.get("cset_cn", "")):
                                    assert row.get("com_proj") == 50
                                    return

        pytest.fail("Should have demand projection for residential_demand with value 50")


class TestMiniSystem2FuelChain:
    """Test MiniSystem2 fuel chain features (new P4 syntax)."""

    def test_minisystem2_has_fuel_import(self, get_minisystem_path):
        """MiniSystem2 gas_import should output gas commodity."""
        path = get_minisystem_path(2)
        source = load_vedalang(path)
        tableir = compile_vedalang_to_tableir(source)

        # Find gas_import output row
        for f in tableir["files"]:
            for s in f["sheets"]:
                for t in s["tables"]:
                    if t["tag"] == "~FI_T":
                        for row in t["rows"]:
                            if "gas_import" in row.get("process", "") and "commodity-out" in row:
                                assert row["commodity-out"] == "gas"
                                return

        pytest.fail("gas_import should have gas output")

    def test_minisystem2_has_ccgt_topology(self, get_minisystem_path):
        """MiniSystem2 ccgt should have gas input and electricity output."""
        path = get_minisystem_path(2)
        source = load_vedalang(path)
        tableir = compile_vedalang_to_tableir(source)

        has_input = False
        has_output = False

        for f in tableir["files"]:
            for s in f["sheets"]:
                for t in s["tables"]:
                    if t["tag"] == "~FI_T":
                        for row in t["rows"]:
                            if "ccgt" in row.get("process", ""):
                                if row.get("commodity-in") == "gas":
                                    has_input = True
                                if row.get("commodity-out") == "electricity":
                                    has_output = True

        assert has_input, "ccgt should have gas input"
        assert has_output, "ccgt should have electricity output"
