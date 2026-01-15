"""Phase 0 Baseline Tests - Validate toolchain works before schema evolution.

These tests confirm the VedaLang → TableIR → Excel pipeline works
without Python exceptions. xl2times validation is expected to fail
because minimal examples lack system tables.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from tools.veda_check import run_check
from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"


class TestMiniPlantCompilation:
    """Tests for mini_plant.veda.yaml compilation."""

    @pytest.fixture
    def mini_plant_source(self):
        return load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")

    @pytest.fixture
    def mini_plant_tableir(self, mini_plant_source):
        return compile_vedalang_to_tableir(mini_plant_source)

    def test_compiles_without_exceptions(self, mini_plant_source):
        """Compilation should not raise exceptions."""
        tableir = compile_vedalang_to_tableir(mini_plant_source)
        assert tableir is not None

    def test_output_has_files(self, mini_plant_tableir):
        """TableIR must have 'files' key."""
        assert "files" in mini_plant_tableir
        assert len(mini_plant_tableir["files"]) >= 1

    def test_output_validates_against_schema(self, mini_plant_tableir):
        """Compiler output must be valid TableIR."""
        with open(SCHEMA_DIR / "tableir.schema.json") as f:
            schema = json.load(f)
        jsonschema.validate(mini_plant_tableir, schema)

    def test_has_fi_comm_table(self, mini_plant_tableir):
        """Should generate ~FI_COMM table."""
        tags = self._get_all_tags(mini_plant_tableir)
        assert "~FI_COMM" in tags

    def test_has_fi_process_table(self, mini_plant_tableir):
        """Should generate ~FI_PROCESS table."""
        tags = self._get_all_tags(mini_plant_tableir)
        assert "~FI_PROCESS" in tags

    def test_has_fi_t_table(self, mini_plant_tableir):
        """Should generate ~FI_T table."""
        tags = self._get_all_tags(mini_plant_tableir)
        assert "~FI_T" in tags

    def test_commodity_rows_correct(self, mini_plant_tableir):
        """Commodities electricity and gas should appear in ~FI_COMM (new P4 syntax)."""
        rows = self._get_table_rows(mini_plant_tableir, "~FI_COMM")
        comm_names = [r.get("commodity") for r in rows]
        assert "electricity" in comm_names
        assert "gas" in comm_names

    def test_process_row_correct(self, mini_plant_tableir):
        """Process ccgt_REG1 should appear in ~FI_PROCESS (new P4 syntax)."""
        rows = self._get_table_rows(mini_plant_tableir, "~FI_PROCESS")
        tech_names = [r.get("process") for r in rows]
        assert "ccgt_REG1" in tech_names

    def test_process_has_sets(self, mini_plant_tableir):
        """Process should have sets (may be empty for conversion process)."""
        rows = self._get_table_rows(mini_plant_tableir, "~FI_PROCESS")
        ccgt = next(r for r in rows if "ccgt" in r.get("process", "").lower())
        # Conversion processes don't automatically get ELE sets in new syntax
        assert "sets" in ccgt

    def test_fi_t_has_efficiency(self, mini_plant_tableir):
        """~FI_T should contain efficiency row."""
        rows = self._get_table_rows(mini_plant_tableir, "~FI_T")
        eff_rows = [r for r in rows if "eff" in r]
        assert len(eff_rows) >= 1
        assert eff_rows[0]["eff"] == 0.55

    def _get_all_tags(self, tableir):
        """Extract all table tags from TableIR."""
        tags = []
        for f in tableir.get("files", []):
            for s in f.get("sheets", []):
                for t in s.get("tables", []):
                    tags.append(t.get("tag"))
        return tags

    def _get_table_rows(self, tableir, tag):
        """Get rows from a specific table tag."""
        for f in tableir.get("files", []):
            for s in f.get("sheets", []):
                for t in s.get("tables", []):
                    if t.get("tag") == tag:
                        return t.get("rows", [])
        return []


class TestVedaCheckPipeline:
    """Tests for veda_check orchestration."""

    def test_veda_check_no_python_exceptions(self):
        """veda_check should run without Python exceptions."""
        result = run_check(
            EXAMPLES_DIR / "mini_plant.veda.yaml",
            from_vedalang=True,
        )
        assert result is not None

    def test_veda_check_reports_tables(self):
        """veda_check should report generated tables."""
        result = run_check(
            EXAMPLES_DIR / "mini_plant.veda.yaml",
            from_vedalang=True,
        )
        assert len(result.tables) >= 3
        assert "~FI_COMM" in result.tables
        assert "~FI_PROCESS" in result.tables
        assert "~FI_T" in result.tables

    def test_veda_check_reports_row_count(self):
        """veda_check should report total row count."""
        result = run_check(
            EXAMPLES_DIR / "mini_plant.veda.yaml",
            from_vedalang=True,
        )
        assert result.total_rows >= 6

    def test_veda_check_no_schema_errors(self):
        """Should have no schema validation errors."""
        result = run_check(
            EXAMPLES_DIR / "mini_plant.veda.yaml",
            from_vedalang=True,
        )
        schema_errors = [e for e in result.error_messages if "Schema" in e]
        assert len(schema_errors) == 0


class TestBaselineCapabilities:
    """Document what the toolchain can currently express (using new P4 syntax)."""

    def test_can_express_energy_commodities(self):
        """Can define carrier-type commodities."""
        source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
        # New P4 syntax uses 'kind' not 'type'
        assert any(c.get("kind") == "carrier" for c in source["model"]["commodities"])

    def test_can_express_process_with_efficiency(self):
        """Can define a variant with efficiency."""
        source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
        # New P4 syntax uses process_variants, not processes
        variant = source["process_variants"][0]
        assert "efficiency" in variant
        assert 0 < variant["efficiency"] < 1

    def test_can_express_input_output_topology(self):
        """Can define role inputs and outputs."""
        source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
        # New P4 syntax uses process_roles for topology
        role = source["process_roles"][0]
        # This role has inputs and outputs
        assert "inputs" in role or "outputs" in role

    def test_can_express_regions(self):
        """Can define model regions."""
        source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
        assert len(source["model"]["regions"]) >= 1
