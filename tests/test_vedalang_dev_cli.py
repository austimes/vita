"""Tests for vedalang-dev CLI (design agent)."""

import json
import subprocess
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "vedalang" / "examples"
MINI_PLANT = EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml"
TABLEIR_MINIMAL = EXAMPLES_DIR / "tableir/tableir_minimal.yaml"


def run_vedalang_dev(*args: str) -> subprocess.CompletedProcess:
    """Run vedalang-dev CLI with given arguments."""
    return subprocess.run(
        ["uv", "run", "vedalang-dev", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )


class TestHelp:
    def test_vedalang_dev_help(self):
        """Main --help works."""
        result = run_vedalang_dev("--help")
        assert result.returncode == 0
        assert "vedalang-dev" in result.stdout.lower()
        assert "pipeline" in result.stdout

    def test_vedalang_dev_pipeline_help(self):
        """Pipeline subcommand --help works."""
        result = run_vedalang_dev("pipeline", "--help")
        assert result.returncode == 0
        assert "pipeline" in result.stdout.lower()
        assert "--no-solver" in result.stdout
        assert "--json" in result.stdout

    def test_vedalang_dev_check_help(self):
        """Check subcommand --help works."""
        result = run_vedalang_dev("check", "--help")
        assert result.returncode == 0
        assert "--from-vedalang" in result.stdout

    def test_vedalang_dev_emit_excel_help(self):
        """Emit-excel subcommand --help works."""
        result = run_vedalang_dev("emit-excel", "--help")
        assert result.returncode == 0
        assert "--out" in result.stdout

    def test_vedalang_dev_run_times_help(self):
        """Run-times subcommand --help works."""
        result = run_vedalang_dev("run-times", "--help")
        assert result.returncode == 0
        assert "--times-src" in result.stdout

    def test_vedalang_dev_pattern_help(self):
        """Pattern subcommand --help works."""
        result = run_vedalang_dev("pattern", "--help")
        assert result.returncode == 0

    def test_vedalang_dev_sankey_help(self):
        """Sankey subcommand --help works."""
        result = run_vedalang_dev("sankey", "--help")
        assert result.returncode == 0
        assert "--gdx" in result.stdout
        assert "--year" in result.stdout
        assert "--format" in result.stdout


class TestEmitExcel:
    def test_vedalang_dev_emit_excel(self, tmp_path):
        """Emit-excel creates Excel from TableIR fixture."""
        out_dir = tmp_path / "excel_out"
        result = run_vedalang_dev(
            "emit-excel", str(TABLEIR_MINIMAL), "--out", str(out_dir)
        )
        assert result.returncode == 0
        assert out_dir.exists()
        assert "Created" in result.stdout

        xlsx_files = list(out_dir.glob("**/*.xlsx"))
        assert len(xlsx_files) > 0, "Expected at least one Excel file"

    def test_vedalang_dev_emit_excel_file_not_found(self, tmp_path):
        """Emit-excel returns error for missing file."""
        out_dir = tmp_path / "excel_out"
        result = run_vedalang_dev(
            "emit-excel", "nonexistent.yaml", "--out", str(out_dir)
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()


class TestCheck:
    def test_vedalang_dev_check_vedalang(self):
        """Check validates VedaLang source."""
        result = run_vedalang_dev(
            "check", str(MINI_PLANT), "--from-vedalang"
        )
        assert result.returncode in (0, 1, 2)
        assert "tables" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_vedalang_dev_check_json(self):
        """Check with --json outputs valid JSON."""
        result = run_vedalang_dev(
            "check", str(MINI_PLANT), "--from-vedalang", "--json"
        )

        data = json.loads(result.stdout)
        assert data["dsl_version"] == "0.2"
        assert data["artifact_version"] == "1.0.0"
        assert "success" in data
        assert "tables" in data
        assert "errors" in data


class TestPipeline:
    def test_vedalang_dev_pipeline_no_solver(self):
        """Pipeline runs with --no-solver."""
        result = run_vedalang_dev(
            "pipeline", str(MINI_PLANT), "--no-solver"
        )
        assert result.returncode in (0, 2)
        stdout = result.stdout
        assert "PASS" in stdout or "FAIL" in stdout or "pipeline" in stdout.lower()

    def test_vedalang_dev_pipeline_json(self):
        """Pipeline with --json outputs valid JSON."""
        result = run_vedalang_dev(
            "pipeline", str(MINI_PLANT), "--no-solver", "--json"
        )

        data = json.loads(result.stdout)
        assert data["dsl_version"] == "0.2"
        assert data["artifact_version"] == "1.0.0"
        assert "success" in data
        assert "steps" in data

    def test_vedalang_dev_pipeline_file_not_found(self):
        """Pipeline returns error for missing file."""
        result = run_vedalang_dev("pipeline", "nonexistent.veda.yaml", "--no-solver")
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()


class TestPattern:
    def test_vedalang_dev_pattern_list(self):
        """Pattern list shows available patterns."""
        result = run_vedalang_dev("pattern", "list")
        if "not available" in result.stderr:
            pytest.skip("veda_patterns module not available")
        assert result.returncode == 0
        assert "pattern" in result.stdout.lower()

    def test_vedalang_dev_pattern_list_json(self):
        """Pattern list with --json outputs valid JSON array."""
        result = run_vedalang_dev("pattern", "list", "--json")
        if "not available" in result.stderr:
            pytest.skip("veda_patterns module not available")
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert isinstance(data, list)
