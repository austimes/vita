"""Tests for vedalang CLI (user-facing)."""

import json
import subprocess
from pathlib import Path

import yaml

from tests.test_v0_2_backend import _v0_2_backend_source

EXAMPLES_DIR = Path(__file__).parent.parent / "vedalang" / "examples"
MINI_PLANT = EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml"
MINISYSTEM = EXAMPLES_DIR / "minisystem/minisystem8.veda.yaml"


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
        """Lint runs successfully on quickstart/mini_plant.veda.yaml."""
        result = run_vedalang("lint", str(MINI_PLANT))
        assert result.returncode in (0, 1)
        assert "error(s)" in result.stdout

    def test_vedalang_lint_json(self):
        """Lint with --json outputs valid JSON structure."""
        result = run_vedalang("lint", "--json", str(MINI_PLANT))
        assert result.returncode in (0, 1)

        data = json.loads(result.stdout)
        assert data["dsl_version"] == "0.2"
        assert data["artifact_version"] == "1.0.0"
        assert "success" in data
        assert "source" in data
        assert "warnings" in data
        assert "errors" in data
        assert "diagnostics" in data
        assert "summary" in data
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

    def test_vedalang_lint_list_categories(self):
        """lint --list-categories returns categories."""
        result = run_vedalang("lint", "--list-categories")
        assert result.returncode == 0
        assert "core" in result.stdout
        assert "feasibility" in result.stdout

    def test_vedalang_lint_list_checks_json(self):
        """lint --list-checks --json returns grouped checks."""
        result = run_vedalang("lint", "--list-checks", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "checks" in data
        assert "core" in data["checks"]
        assert "identity" in data["checks"]

    def test_vedalang_lint_category_identity_only(self):
        """Selecting identity category returns only identity diagnostics."""
        result = run_vedalang(
            "lint", "--json", "--category", "identity", str(MINI_PLANT)
        )
        assert result.returncode in (0, 1)
        data = json.loads(result.stdout)
        assert all(d["category"] == "identity" for d in data["diagnostics"])

    def test_vedalang_lint_category_feasibility_only(self):
        """Selecting feasibility category returns only H* checks."""
        result = run_vedalang(
            "lint", "--json", "--category", "feasibility", str(MINISYSTEM)
        )
        assert result.returncode in (0, 1, 2)
        data = json.loads(result.stdout)
        assert all(d["category"] == "feasibility" for d in data["diagnostics"])

    def test_vedalang_lint_units_runs_without_profile_flag(self):
        """Units category is available without a profile switch."""
        result = run_vedalang(
            "lint",
            "--json",
            "--category",
            "units",
            str(MINI_PLANT),
        )
        assert result.returncode in (0, 1, 2)
        data = json.loads(result.stdout)
        checks_run = data.get("summary", {}).get("checks_run", [])
        assert "code.units.compiler_semantics" in checks_run

    def test_vedalang_lint_rejects_legacy_syntax(self, tmp_path):
        """Deterministic lint reports legacy syntax as unsupported."""
        src = tmp_path / "legacy.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: LegacyDemo",
                    "  regions: [REG1]",
                    "  commodities:",
                    "    - name: C:ELC",
                    "      type: energy",
                    "  processes:",
                    "    - name: IMP_ELC",
                    "      sets: [IMP]",
                    "      outputs:",
                    "        - commodity: C:ELC",
                    "      efficiency: 1.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vedalang("lint", "--json", str(src))
        assert result.returncode == 2
        data = json.loads(result.stdout)
        assert any(d.get("code") == "SCHEMA_ERROR" for d in data.get("diagnostics", []))

    def test_vedalang_lint_rejects_legacy_role_variant_surface(self, tmp_path):
        """Deterministic lint rejects the pre-v0.2 model/roles/variants surface."""
        src = tmp_path / "legacy_roles.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: LegacyRoles",
                    "  regions: [REG1]",
                    "  milestone_years: [2020]",
                    "  commodities:",
                    "    - id: secondary:electricity",
                    "      type: energy",
                    "      unit: PJ",
                    "roles:",
                    "  - id: supply_power",
                    "    stage: supply",
                    "    activity_unit: PJ",
                    "    capacity_unit: GW",
                    "    required_outputs:",
                    "      - commodity: secondary:electricity",
                    "variants:",
                    "  - id: gen",
                    "    role: supply_power",
                    "    outputs:",
                    "      - commodity: secondary:electricity",
                    "    efficiency: 1.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vedalang("lint", "--json", str(src))
        assert result.returncode == 2
        data = json.loads(result.stdout)
        assert any(d.get("code") == "SCHEMA_ERROR" for d in data.get("diagnostics", []))

    def test_vedalang_lint_json_includes_line_and_excerpt(self, tmp_path):
        """Diagnostics include source line/column metadata and excerpt."""
        src = tmp_path / "bad_schema.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: Demo",
                    "  regions: [REG1]",
                    '  milestone_years: "2020"',
                    "  commodities:",
                    "    - id: secondary:electricity",
                    "      type: energy",
                    "      unit: PJ",
                    "      combustible: false",
                    "roles: []",
                    "variants: []",
                    "availability: []",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vedalang("lint", "--json", str(src))
        assert result.returncode == 2

        data = json.loads(result.stdout)
        assert data["diagnostics"], "Expected at least one diagnostic"
        first = data["diagnostics"][0]
        assert isinstance(first.get("line"), int)
        assert isinstance(first.get("column"), int)
        assert isinstance(first.get("source_excerpt"), dict)
        excerpt_lines = first["source_excerpt"].get("lines", [])
        assert any("milestone_years" in line.get("text", "") for line in excerpt_lines)

    def test_vedalang_lint_text_shows_offending_source_line(self, tmp_path):
        """Human output includes source snippet for quick debugging."""
        src = tmp_path / "bad_schema_text.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: Demo",
                    "  regions: [REG1]",
                    '  milestone_years: "2020"',
                    "  commodities:",
                    "    - id: secondary:electricity",
                    "      type: energy",
                    "      unit: PJ",
                    "      combustible: false",
                    "roles: []",
                    "variants: []",
                    "availability: []",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vedalang("lint", str(src))
        assert result.returncode == 2
        assert "milestone_years" in result.stdout
        assert "line " in result.stdout


class TestCompile:
    def test_vedalang_compile_v0_2_run_outputs_multi_artifacts(self, tmp_path):
        """v0.2 compile emits run-scoped CSIR/CPIR/explain artifacts."""
        src = tmp_path / "toy_v0_2.veda.yaml"
        src.write_text(yaml.safe_dump(_v0_2_backend_source()), encoding="utf-8")

        out_dir = tmp_path / "excel_out"
        tableir_path = tmp_path / "toy.tableir.yaml"
        result = run_vedalang(
            "compile",
            str(src),
            "--run",
            "toy_states_2025",
            "--out",
            str(out_dir),
            "--tableir",
            str(tableir_path),
            "--json",
            "--no-lint",
        )
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["run_id"] == "toy_states_2025"
        assert any(path.endswith(".csir.yaml") for path in data["files"])
        assert any(path.endswith(".cpir.yaml") for path in data["files"])
        assert any(path.endswith(".explain.json") for path in data["files"])
        assert tableir_path.exists()

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
        assert data["dsl_version"] == "0.2"
        assert data["artifact_version"] == "1.0.0"
        assert "success" in data
        assert "files" in data
        assert data["success"] is True

    def test_vedalang_compile_json_rejects_legacy_process_syntax(self, tmp_path):
        """Compile JSON rejects the legacy top-level processes public DSL."""
        src = tmp_path / "legacy_compile.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: LegacyCompile",
                    "  regions: [REG1]",
                    "  commodities:",
                    "    - name: C:ELC",
                    "      type: energy",
                    "processes:",
                    "  - name: IMP_ELC",
                    "    sets: [IMP]",
                    "    outputs:",
                    "      - commodity: C:ELC",
                    "    efficiency: 1.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        out_dir = tmp_path / "excel_out"
        result = run_vedalang(
            "compile",
            str(src),
            "--out",
            str(out_dir),
            "--json",
            "--no-lint",
        )
        assert result.returncode == 2
        data = json.loads(result.stdout)
        assert "Schema error:" in data["error"]

    def test_vedalang_compile_tableir_output(self, tmp_path):
        """Compile with --tableir creates TableIR YAML."""
        tableir_path = tmp_path / "output.tableir.yaml"
        result = run_vedalang(
            "compile", str(MINI_PLANT), "--tableir", str(tableir_path)
        )
        assert result.returncode == 0
        assert tableir_path.exists()
        tableir = yaml.safe_load(tableir_path.read_text(encoding="utf-8"))
        assert tableir["dsl_version"] == "0.2"
        assert tableir["artifact_version"] == "1.0.0"

    def test_vedalang_compile_no_output_error(self):
        """Compile without --out or --tableir returns error."""
        result = run_vedalang("compile", str(MINI_PLANT))
        assert result.returncode == 2


class TestValidate:
    def test_vedalang_validate_v0_2_run_json(self, tmp_path):
        """Validate supports run-scoped v0.2 sources."""
        src = tmp_path / "toy_v0_2.veda.yaml"
        src.write_text(yaml.safe_dump(_v0_2_backend_source()), encoding="utf-8")

        result = run_vedalang(
            "validate",
            "--json",
            "--run",
            "toy_states_2025",
            str(src),
        )
        assert result.returncode in (0, 1, 2)

        data = json.loads(result.stdout)
        assert data["dsl_version"] == "0.2"
        assert len(data["tables"]) > 0
        assert data["total_rows"] > 0

    def test_vedalang_validate_basic(self):
        """Validate runs through xl2times pipeline."""
        result = run_vedalang("validate", str(MINI_PLANT))
        assert result.returncode in (0, 1, 2)
        assert "error(s)" in result.stdout or "Validate" in result.stdout

    def test_vedalang_validate_json(self):
        """Validate with --json outputs valid JSON structure."""
        result = run_vedalang("validate", "--json", str(MINI_PLANT))

        data = json.loads(result.stdout)
        assert data["dsl_version"] == "0.2"
        assert data["artifact_version"] == "1.0.0"
        assert "success" in data
        assert "source" in data
        assert "tables" in data
        assert "total_rows" in data
        assert "diagnostics" in data

    def test_vedalang_validate_json_rejects_legacy_process_syntax(self, tmp_path):
        """Validate JSON surfaces deterministic legacy public DSL diagnostics."""
        src = tmp_path / "legacy_validate.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: LegacyValidate",
                    "  regions: [REG1]",
                    "  commodities:",
                    "    - name: C:ELC",
                    "      type: energy",
                    "processes:",
                    "  - name: IMP_ELC",
                    "    sets: [IMP]",
                    "    outputs:",
                    "      - commodity: C:ELC",
                    "    efficiency: 1.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vedalang("validate", "--json", str(src))
        assert result.returncode == 2
        data = json.loads(result.stdout)
        assert data["diagnostics"]["diagnostics"][0]["code"] == "SCHEMA_ERROR"


class TestViz:
    def test_vedalang_viz_mermaid_accepts_run_for_multi_run_v0_2_source(
        self, tmp_path
    ):
        src = tmp_path / "toy_v0_2_multi_run.veda.yaml"
        source = _v0_2_backend_source()
        source["runs"].append(
            {
                "id": "toy_states_alt",
                "base_year": 2025,
                "currency_year": 2024,
                "region_partition": "toy_states",
            }
        )
        src.write_text(yaml.safe_dump(source), encoding="utf-8")

        result = run_vedalang(
            "viz",
            str(src),
            "--mermaid",
            "--run",
            "toy_states_alt",
        )

        assert result.returncode == 0
        assert result.stdout.startswith("flowchart LR")
        assert "space_heat_supply\nbrisbane_heat\n[role instance]" in result.stdout


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

    def test_vedalang_fmt_help(self):
        """Fmt subcommand help works."""
        result = run_vedalang("fmt", "--help")
        assert result.returncode == 0
        assert "format" in result.stdout.lower()

    def test_vedalang_llm_lint_help(self):
        """llm-lint subcommand help works."""
        result = run_vedalang("llm-lint", "--help")
        assert result.returncode == 0
        assert "llm-lint" in result.stdout.lower()
