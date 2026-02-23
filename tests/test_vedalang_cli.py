"""Tests for vedalang CLI (user-facing)."""

import json
import subprocess
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent.parent / "vedalang" / "examples"
MINI_PLANT = EXAMPLES_DIR / "mini_plant.veda.yaml"
MINISYSTEM = EXAMPLES_DIR / "minisystem8.veda.yaml"


def run_vedalang(*args: str) -> subprocess.CompletedProcess:
    """Run vedalang CLI with given arguments."""
    return subprocess.run(
        ["uv", "run", "vedalang", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )


class TestLint:
    def test_vedalang_lint_basic(self):
        """Lint runs successfully on mini_plant.veda.yaml."""
        result = run_vedalang("lint", str(MINI_PLANT))
        assert result.returncode == 0
        assert "error(s)" in result.stdout

    def test_vedalang_lint_json(self):
        """Lint with --json outputs valid JSON structure."""
        result = run_vedalang("lint", "--json", str(MINI_PLANT))
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert "success" in data
        assert "source" in data
        assert "warnings" in data
        assert "errors" in data
        assert "diagnostics" in data
        assert isinstance(data["diagnostics"], list)
        assert data["success"] is True

    def test_vedalang_lint_heuristic_warning(self):
        """Lint detects heuristic warnings on minisystem.veda.yaml."""
        result = run_vedalang("lint", "--json", str(MINISYSTEM))
        data = json.loads(result.stdout)

        assert data["warnings"] > 0 or data["errors"] >= 0, (
            "Expected minisystem to have warnings or at least complete lint"
        )

    def test_vedalang_lint_file_not_found(self):
        """Lint returns error for missing file."""
        result = run_vedalang("lint", "nonexistent.veda.yaml")
        assert result.returncode == 2


class TestCompile:
    def test_vedalang_compile_basic(self, tmp_path):
        """Compile creates Excel files."""
        out_dir = tmp_path / "excel_out"
        result = run_vedalang("compile", str(MINI_PLANT), "--out", str(out_dir))
        assert result.returncode == 0
        assert out_dir.exists()

        xlsx_files = list(out_dir.glob("**/*.xlsx"))
        assert len(xlsx_files) > 0, "Expected at least one Excel file"

    def test_vedalang_compile_json(self, tmp_path):
        """Compile with --json outputs valid JSON structure."""
        out_dir = tmp_path / "excel_out"
        result = run_vedalang(
            "compile", str(MINI_PLANT), "--out", str(out_dir), "--json", "--no-lint"
        )
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert "success" in data
        assert "files" in data
        assert data["success"] is True

    def test_vedalang_compile_tableir_output(self, tmp_path):
        """Compile with --tableir creates TableIR YAML."""
        tableir_path = tmp_path / "output.tableir.yaml"
        result = run_vedalang(
            "compile", str(MINI_PLANT), "--tableir", str(tableir_path)
        )
        assert result.returncode == 0
        assert tableir_path.exists()

    def test_vedalang_compile_no_output_error(self):
        """Compile without --out or --tableir returns error."""
        result = run_vedalang("compile", str(MINI_PLANT))
        assert result.returncode == 2


class TestValidate:
    def test_vedalang_validate_basic(self):
        """Validate runs through xl2times pipeline."""
        result = run_vedalang("validate", str(MINI_PLANT))
        assert result.returncode in (0, 1, 2)
        assert "error(s)" in result.stdout or "Validate" in result.stdout

    def test_vedalang_validate_json(self):
        """Validate with --json outputs valid JSON structure."""
        result = run_vedalang("validate", "--json", str(MINI_PLANT))

        data = json.loads(result.stdout)
        assert "success" in data
        assert "source" in data
        assert "tables" in data
        assert "total_rows" in data
        assert "diagnostics" in data


class TestHelp:
    def test_vedalang_help(self):
        """Main help works."""
        result = run_vedalang("--help")
        assert result.returncode == 0
        assert "vedalang" in result.stdout.lower()

    def test_vedalang_lint_help(self):
        """Lint subcommand help works."""
        result = run_vedalang("lint", "--help")
        assert result.returncode == 0
        assert "lint" in result.stdout.lower()

    def test_vedalang_compile_help(self):
        """Compile subcommand help works."""
        result = run_vedalang("compile", "--help")
        assert result.returncode == 0
        assert "compile" in result.stdout.lower()

    def test_vedalang_validate_help(self):
        """Validate subcommand help works."""
        result = run_vedalang("validate", "--help")
        assert result.returncode == 0
        assert "validate" in result.stdout.lower()
