"""MiniSystem Golden Test.

Comprehensive golden test for the MiniSystem stress-test model.
This validates that a real-world-like model with all VedaLang features
compiles and produces the expected TableIR structure.

Issue: vedalang-4t8
"""

from pathlib import Path

import pytest
import yaml

from tools.veda_check import run_check
from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"
MINISYSTEM_PATH = EXAMPLES_DIR / "minisystem.veda.yaml"
GOLDEN_TABLEIR_PATH = EXAMPLES_DIR / "minisystem_golden.tableir.yaml"


class TestMiniSystemCompilation:
    """Test MiniSystem compiles to valid TableIR."""

    @pytest.fixture
    def source(self):
        """Load the MiniSystem source."""
        return load_vedalang(MINISYSTEM_PATH)

    @pytest.fixture
    def tableir(self, source):
        """Compile MiniSystem to TableIR."""
        return compile_vedalang_to_tableir(source)

    def test_minisystem_exists(self):
        """MiniSystem fixture must exist."""
        assert MINISYSTEM_PATH.exists(), "minisystem.veda.yaml is the stress-test model"

    def test_compiles_without_error(self, tableir):
        """MiniSystem should compile without errors."""
        assert "files" in tableir
        assert len(tableir["files"]) >= 1

    def test_has_multiple_files(self, tableir):
        """MiniSystem should produce multiple output files."""
        file_paths = [f["path"] for f in tableir["files"]]
        # Should have at least: base, SysSettings, scenarios, constraints
        assert len(file_paths) >= 3

    def test_has_syssettings(self, tableir):
        """Should have syssettings file with timeslices and regions."""
        syssettings_files = [
            f for f in tableir["files"] if "syssettings" in f["path"].lower()
        ]
        assert len(syssettings_files) == 1

        # Check for essential tables
        sysset = syssettings_files[0]
        table_tags = []
        for sheet in sysset["sheets"]:
            for table in sheet["tables"]:
                table_tags.append(table["tag"])

        assert "~BOOKREGIONS_MAP" in table_tags, "Should have region mapping"
        assert "~TIMESLICES" in table_tags, "Should have timeslice definitions"


class TestMiniSystemFeatureCoverage:
    """Test MiniSystem exercises all VedaLang features."""

    @pytest.fixture
    def source(self):
        """Load the MiniSystem source."""
        return load_vedalang(MINISYSTEM_PATH)

    @pytest.fixture
    def tableir(self, source):
        """Compile MiniSystem to TableIR."""
        return compile_vedalang_to_tableir(source)

    def test_has_multiple_regions(self, source):
        """MiniSystem should have multiple regions."""
        regions = source["model"]["regions"]
        assert len(regions) >= 2
        assert "NORTH" in regions
        assert "SOUTH" in regions

    def test_has_all_commodity_types(self, source):
        """MiniSystem should have all commodity types."""
        commodities = source["model"]["commodities"]
        types = {c["type"] for c in commodities}
        assert types == {"energy", "emission", "demand", "material"}

    def test_has_timeslices(self, source):
        """MiniSystem should have timeslice definitions."""
        ts = source["model"]["timeslices"]
        assert "season" in ts
        assert "daynite" in ts
        assert "fractions" in ts
        assert len(ts["season"]) >= 2
        assert len(ts["daynite"]) >= 2

    def test_has_trade_links(self, source):
        """MiniSystem should have trade links."""
        trade_links = source["model"]["trade_links"]
        assert len(trade_links) >= 1

    def test_has_scenarios(self, source):
        """MiniSystem should have scenarios."""
        scenarios = source["model"]["scenarios"]
        assert len(scenarios) >= 2
        types = {s["type"] for s in scenarios}
        assert "commodity_price" in types
        assert "demand_projection" in types

    def test_has_constraints(self, source):
        """MiniSystem should have user constraints."""
        constraints = source["model"]["constraints"]
        assert len(constraints) >= 1
        types = {c["type"] for c in constraints}
        assert "emission_cap" in types or "activity_share" in types

    def test_has_bounds(self, source):
        """MiniSystem should have processes with bounds."""
        processes = source["model"]["processes"]
        bounds_found = {
            "activity_bound": False,
            "cap_bound": False,
            "ncap_bound": False,
        }
        for proc in processes:
            for bound_type in bounds_found:
                if bound_type in proc:
                    bounds_found[bound_type] = True

        assert any(bounds_found.values()), "Should have at least one bound type"


class TestMiniSystemTableIRStructure:
    """Test MiniSystem TableIR has expected structure."""

    @pytest.fixture
    def tableir(self):
        """Compile MiniSystem to TableIR."""
        source = load_vedalang(MINISYSTEM_PATH)
        return compile_vedalang_to_tableir(source)

    def _find_table_rows(self, tableir, tag: str) -> list[dict]:
        """Find all rows for a given table tag."""
        rows = []
        for f in tableir["files"]:
            for s in f["sheets"]:
                for t in s["tables"]:
                    if t["tag"] == tag:
                        rows.extend(t["rows"])
        return rows

    def test_has_commodities(self, tableir):
        """Should have ~FI_COMM table with core commodities."""
        comm_rows = self._find_table_rows(tableir, "~FI_COMM")
        assert len(comm_rows) >= 4  # NG, ELC, CO2, RSD minimum
        names = {r.get("commodity") for r in comm_rows}
        assert {"NG", "ELC", "CO2", "RSD"}.issubset(names)

    def test_has_processes(self, tableir):
        """Should have ~FI_PROCESS table with core processes."""
        proc_rows = self._find_table_rows(tableir, "~FI_PROCESS")
        # 4 core processes: IMP_NG, PP_CCGT, PP_WIND, DMD_RSD
        assert len(proc_rows) >= 4
        names = {r.get("process") for r in proc_rows}
        expected = {
            "IMP_NG", "PP_CCGT", "PP_WIND", "DMD_RSD",
        }
        assert expected.issubset(names)

    def test_has_topology(self, tableir):
        """Should have ~FI_T table with process topology."""
        fit_rows = self._find_table_rows(tableir, "~FI_T")
        assert len(fit_rows) >= 6  # Multiple rows per process

    def test_has_timeslices(self, tableir):
        """Should have ~TIMESLICES table with ragged columns (independent levels)."""
        ts_rows = self._find_table_rows(tableir, "~TIMESLICES")
        # Ragged table: max(len(seasons), len(daynites)) rows
        # With 2 seasons and 2 daynites, we get 2 rows
        # xl2times extracts unique values per column and creates cross-product itself
        assert len(ts_rows) == 2
        # Verify season codes are present
        seasons = {r.get("season") for r in ts_rows if r.get("season")}
        assert seasons == {"S", "W"}
        # Verify daynite level codes (D, N - not leaf names SD/SN/WD/WN)
        daynites = {r.get("daynite") for r in ts_rows if r.get("daynite")}
        assert daynites == {"D", "N"}

    def test_has_tradelinks(self, tableir):
        """Trade links should emit ~TRADELINKS tables (processes auto-generated).

        Bilateral trade requires BOTH directions in matrix, so each bidirectional
        link produces 2 rows (NORTH→SOUTH and SOUTH→NORTH).
        MiniSystem has 1 bidirectional trade link (ELC) = 2 rows total.
        """
        tradelinks_rows = self._find_table_rows(tableir, "~TRADELINKS")
        # 1 commodity × 2 directions = 2 rows minimum
        assert len(tradelinks_rows) >= 2

        # Verify auto-naming (cells contain 1)
        for row in tradelinks_rows:
            for key, val in row.items():
                # Skip the commodity column (contains region name)
                if key not in ("ELC", "NG"):
                    assert val == 1

    def test_has_user_constraints(self, tableir):
        """Should have ~UC_T table for constraints."""
        uc_rows = self._find_table_rows(tableir, "~UC_T")
        assert len(uc_rows) >= 1


class TestMiniSystemPipeline:
    """Test MiniSystem through full veda_check pipeline."""

    def test_veda_check_succeeds(self):
        """veda_check should succeed for MiniSystem."""
        result = run_check(MINISYSTEM_PATH, from_vedalang=True)

        assert len(result.tables) > 0, "Should emit tables"
        assert result.total_rows > 0, "Should emit rows"
        assert result.errors == 0, (
            f"MiniSystem had {result.errors} errors:\n"
            + "\n".join(f"  - {msg}" for msg in result.error_messages)
        )


class TestMiniSystemGoldenOutput:
    """Test MiniSystem against golden TableIR output (if exists)."""

    @pytest.fixture
    def tableir(self):
        """Compile MiniSystem to TableIR."""
        source = load_vedalang(MINISYSTEM_PATH)
        return compile_vedalang_to_tableir(source)

    def test_golden_output_matches(self, tableir):
        """Compare against golden TableIR output if it exists."""
        if not GOLDEN_TABLEIR_PATH.exists():
            pytest.skip("Golden TableIR fixture not yet created")

        with open(GOLDEN_TABLEIR_PATH) as f:
            golden = yaml.safe_load(f)

        # Compare file structure
        current_paths = sorted(f["path"] for f in tableir["files"])
        golden_paths = sorted(f["path"] for f in golden["files"])
        assert current_paths == golden_paths, "File structure changed"

        # Compare table counts per file
        for curr_file, gold_file in zip(
            sorted(tableir["files"], key=lambda x: x["path"]),
            sorted(golden["files"], key=lambda x: x["path"]),
        ):
            curr_tables = sum(len(s["tables"]) for s in curr_file["sheets"])
            gold_tables = sum(len(s["tables"]) for s in gold_file["sheets"])
            assert curr_tables == gold_tables, (
                f"Table count changed in {curr_file['path']}: "
                f"{curr_tables} vs {gold_tables}"
            )
