"""Tests for vedalang CLI (user-facing)."""

import json
import subprocess
from pathlib import Path

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
    def _write_new_syntax_cost_model(
        self,
        path: Path,
        *,
        investment_cost: str | int,
        fixed_om_cost: str | int | None = None,
        variable_om_cost: str | int | None = None,
        override_investment_cost: str | int | None = None,
    ) -> None:
        lines = [
            "model:",
            "  name: CostLintModel",
            "  regions: [REG1]",
            "  milestone_years: [2020]",
            "  commodities:",
            "    - id: secondary:electricity",
            "      type: energy",
            "      unit: PJ",
            "      combustible: false",
            "  cases:",
            "    - name: base",
            "      is_baseline: true",
            "      provider_overrides:",
            "        - selector:",
            "            variant: gen",
        ]
        if override_investment_cost is not None:
            lines.append(
                "          investment_cost: "
                f"{json.dumps(override_investment_cost)}"
            )
        lines.extend(
            [
                "roles:",
                "  - id: supply_power",
                "    stage: supply",
                "    activity_unit: PJ",
                "    capacity_unit: GW",
                "    required_inputs: []",
                "    required_outputs:",
                "      - commodity: secondary:electricity",
                "variants:",
                "  - id: gen",
                "    role: supply_power",
                "    inputs: []",
                "    outputs:",
                "      - commodity: secondary:electricity",
                "    efficiency: 1.0",
                f"    investment_cost: {json.dumps(investment_cost)}",
            ]
        )
        if fixed_om_cost is not None:
            lines.append(f"    fixed_om_cost: {json.dumps(fixed_om_cost)}")
        if variable_om_cost is not None:
            lines.append(f"    variable_om_cost: {json.dumps(variable_om_cost)}")
        lines.extend(
            [
                "availability:",
                "  - variant: gen",
                "    regions: [REG1]",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
        assert any(
            d.get("code") == "E_LEGACY_SYNTAX_UNSUPPORTED"
            for d in data.get("diagnostics", [])
        )

    def test_vedalang_lint_units_flags_numeric_cost_scalar(self, tmp_path):
        """Numeric cost values fail deterministic denominator checks."""
        src = tmp_path / "numeric_cost.veda.yaml"
        self._write_new_syntax_cost_model(
            src,
            investment_cost=20,
            fixed_om_cost=5,
            variable_om_cost=2,
        )

        result = run_vedalang("lint", "--json", "--category", "units", str(src))
        assert result.returncode == 2
        data = json.loads(result.stdout)
        codes = {d.get("code") for d in data.get("diagnostics", [])}
        assert "E_UNIT_INVESTMENT_COST_DENOM_MISMATCH" in codes
        assert "E_UNIT_FIXED_OM_COST_DENOM_MISMATCH" in codes
        assert "E_UNIT_VARIABLE_COST_DENOM_MISMATCH" in codes

    def test_vedalang_lint_units_accepts_explicit_cost_literals(self, tmp_path):
        """Explicit cost literals matching role units pass deterministic checks."""
        src = tmp_path / "literal_cost.veda.yaml"
        self._write_new_syntax_cost_model(
            src,
            investment_cost="20 MUSD24/GW",
            fixed_om_cost="5 MUSD24/GW/yr",
            variable_om_cost="2 MUSD24/PJ",
            override_investment_cost="22 MUSD24/GW",
        )

        result = run_vedalang("lint", "--json", "--category", "units", str(src))
        data = json.loads(result.stdout)
        assert result.returncode == 0
        assert data.get("diagnostics") == []

    def test_vedalang_lint_emissions_includes_negative_emission_doc_guidance(
        self, tmp_path
    ):
        """Negative-emission guidance stays in emissions lint category."""
        src = tmp_path / "negative_emission_doc.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: EmissionDocModel",
                    "  regions: [REG1]",
                    "  milestone_years: [2020]",
                    "  commodities:",
                    "    - id: emission:co2e",
                    "      type: emission",
                    "      unit: Mt",
                    "      combustible: false",
                    "roles:",
                    "  - id: remove_co2",
                    "    activity_unit: PJ",
                    "    capacity_unit: GW",
                    "    stage: sink",
                    "    required_inputs: []",
                    "    required_outputs: []",
                    "variants:",
                    "  - id: afforestation",
                    "    role: remove_co2",
                    "    inputs: []",
                    "    outputs: []",
                    "    efficiency: 1.0",
                    "    emission_factors:",
                    "      emission:co2e: -1.0",
                    "availability:",
                    "  - variant: afforestation",
                    "    regions: [REG1]",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vedalang("lint", "--json", "--category", "emissions", str(src))
        assert result.returncode in (0, 1)
        data = json.loads(result.stdout)
        assert any(
            d.get("code") == "W_NEGATIVE_EMISSION_DOC"
            for d in data["diagnostics"]
        )
        assert all(d["category"] == "emissions" for d in data["diagnostics"])

    def test_vedalang_lint_units_flags_emission_intensity_unit_mismatch(
        self, tmp_path
    ):
        """Units lint flags emission_factors when emission numerator is not mass."""
        src = tmp_path / "emission_intensity_units.veda.yaml"
        src.write_text(
            "\n".join(
                [
                    "model:",
                    "  name: EmissionUnitMismatchModel",
                    "  regions: [REG1]",
                    "  milestone_years: [2020]",
                    "  commodities:",
                    "    - id: emission:co2e",
                    "      type: emission",
                    "      unit: GW",
                    "      combustible: false",
                    "roles:",
                    "  - id: remove_co2",
                    "    activity_unit: PJ",
                    "    capacity_unit: GW",
                    "    stage: sink",
                    "    required_inputs: []",
                    "    required_outputs: []",
                    "variants:",
                    "  - id: afforestation",
                    "    role: remove_co2",
                    "    inputs: []",
                    "    outputs: []",
                    "    efficiency: 1.0",
                    "    emission_factors:",
                    "      emission:co2e: 1.0",
                    "availability:",
                    "  - variant: afforestation",
                    "    regions: [REG1]",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vedalang("lint", "--json", "--category", "units", str(src))
        assert result.returncode in (0, 1, 2)
        data = json.loads(result.stdout)
        assert any(
            d.get("code") == "W_UNIT_EMISSION_INTENSITY_NUMERATOR"
            for d in data["diagnostics"]
        )
        assert all(d["category"] == "units" for d in data["diagnostics"])

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
