"""Tests for vedalang-dev authoring and Vita run/analyze CLIs."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.test_backend_bridge import _sample_source

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


def run_vita(*args: str) -> subprocess.CompletedProcess:
    """Run vita CLI with given arguments."""
    return subprocess.run(
        ["uv", "run", "vita", *args],
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
        assert "check" in result.stdout
        assert "emit-excel" in result.stdout
        assert "pattern" in result.stdout
        assert "eval" in result.stdout
        assert "pipeline" not in result.stdout
        assert "run-times" not in result.stdout
        assert "times-results" not in result.stdout
        assert "sankey" not in result.stdout

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

    def test_vedalang_dev_pattern_help(self):
        """Pattern subcommand --help works."""
        result = run_vedalang_dev("pattern", "--help")
        assert result.returncode == 0

    @pytest.mark.parametrize(
        "command",
        ["pipeline", "run-times", "times-results", "sankey"],
    )
    def test_vedalang_dev_removed_commands_fail(self, command: str):
        """Removed backward-compat commands are no longer accepted."""
        result = run_vedalang_dev(command, "--help")
        assert result.returncode == 2
        assert "invalid choice" in result.stderr.lower()
        assert command in result.stderr


class TestVitaHelp:
    def test_vita_help(self):
        """Main --help works."""
        result = run_vita("--help")
        assert result.returncode == 0
        assert "vita" in result.stdout.lower()
        assert "run" in result.stdout
        assert "results" in result.stdout
        assert "sankey" in result.stdout
        assert "diff" in result.stdout
        assert "update" in result.stdout

    def test_vita_run_help(self):
        """Run subcommand --help works."""
        result = run_vita("run", "--help")
        assert result.returncode == 0
        assert "--no-solver" in result.stdout
        assert "--from" in result.stdout
        assert "--out" in result.stdout

    def test_vita_run_help_agent_mode(self):
        """Run subcommand accepts --agent-mode and stays unboxed."""
        result = run_vita("run", "--agent-mode", "--help")
        assert result.returncode == 0
        assert "--agent-mode" in result.stdout
        assert "╭" not in result.stdout

    def test_vita_results_help(self):
        """Results subcommand --help works."""
        result = run_vita("results", "--help")
        assert result.returncode == 0
        assert "--run" in result.stdout
        assert "--gdx" in result.stdout
        assert "--process" in result.stdout

    def test_vita_sankey_help(self):
        """Sankey subcommand --help works."""
        result = run_vita("sankey", "--help")
        assert result.returncode == 0
        assert "--run" in result.stdout
        assert "--gdx" in result.stdout
        assert "--format" in result.stdout

    def test_vita_diff_help(self):
        """Diff subcommand --help works."""
        result = run_vita("diff", "--help")
        assert result.returncode == 0
        assert "--focus-processes" in result.stdout
        assert "--metric" in result.stdout
        assert "--json" in result.stdout

    def test_vita_update_help(self):
        """Update subcommand --help works."""
        result = run_vita("update", "--help")
        assert result.returncode == 0
        assert "github main" in result.stdout.lower()
        assert "when main is newer" in result.stdout.lower()

    def test_vita_experiment_run_help_agent_mode(self):
        """Experiment subcommands accept --agent-mode."""
        result = run_vita("experiment", "run", "--agent-mode", "--help")
        assert result.returncode == 0
        assert "--agent-mode" in result.stdout
        assert "╭" not in result.stdout


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
        result = run_vedalang_dev("check", str(MINI_PLANT), "--from-vedalang")
        assert result.returncode in (0, 1, 2)
        assert "tables" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_vedalang_dev_check_json(self):
        """Check with --json outputs valid JSON."""
        result = run_vedalang_dev("check", str(MINI_PLANT), "--from-vedalang", "--json")

        data = json.loads(result.stdout)
        assert data["dsl_version"] == "0.3"
        assert data["artifact_version"] == "1.0.0"
        assert "success" in data
        assert "tables" in data
        assert "errors" in data


class TestVitaRun:
    def test_vita_run_public_run_json(self, tmp_path):
        """Vita run exposes run-scoped artifact files for v0.3 input."""
        src = tmp_path / "toy_public.veda.yaml"
        src.write_text(yaml.safe_dump(_sample_source()), encoding="utf-8")

        result = run_vita(
            "run",
            str(src),
            "--run",
            "toy_states_2025",
            "--no-solver",
            "--json",
        )
        assert result.returncode in (0, 2)

        data = json.loads(result.stdout)
        artifacts = data["artifacts"]
        assert artifacts["run_id"] == "toy_states_2025"
        assert artifacts["csir_file"].endswith(".csir.yaml")
        assert artifacts["cpir_file"].endswith(".cpir.yaml")
        assert artifacts["explain_file"].endswith(".explain.json")

    def test_vita_run_no_solver(self):
        """Vita run works with --no-solver."""
        result = run_vita("run", str(MINI_PLANT), "--no-solver")
        assert result.returncode in (0, 2)
        stdout = result.stdout
        assert "PASS" in stdout or "FAIL" in stdout or "pipeline" in stdout.lower()
        assert "╭" not in stdout

    def test_vita_run_no_solver_agent_mode(self):
        """Agent mode produces plain run output."""
        result = run_vita("run", str(MINI_PLANT), "--no-solver", "--agent-mode")
        assert result.returncode in (0, 2)
        stdout = result.stdout
        assert "PASS: Pipeline Summary" in stdout or "FAIL: Pipeline Summary" in stdout
        assert "╭" not in stdout

    def test_vita_run_pipeline_json(self):
        """Vita run with --json outputs valid JSON."""
        result = run_vita("run", str(MINI_PLANT), "--no-solver", "--json")

        assert result.returncode in (0, 2)
        data = json.loads(result.stdout)
        assert data["dsl_version"] == "0.3"
        assert data["artifact_version"] == "1.0.0"
        assert "success" in data
        assert "steps" in data

    def test_vita_run_pipeline_agent_mode_json(self):
        """Agent mode preserves the vita run JSON payload."""
        result = run_vita(
            "run", str(MINI_PLANT), "--no-solver", "--agent-mode", "--json"
        )
        assert result.returncode in (0, 2)
        data = json.loads(result.stdout)
        assert "success" in data
        assert "steps" in data

    def test_vita_run_file_not_found(self):
        """Vita run returns error for missing input file."""
        result = run_vita("run", "nonexistent.veda.yaml", "--no-solver")
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()

    def test_vita_run_out_writes_run_artifacts(self, tmp_path):
        """Vita run --out writes manifest and source snapshot artifacts."""
        src = tmp_path / "toy_public.veda.yaml"
        src.write_text(yaml.safe_dump(_sample_source()), encoding="utf-8")
        out_dir = tmp_path / "runs" / "baseline"

        result = run_vita(
            "run",
            str(src),
            "--run",
            "toy_states_2025",
            "--no-solver",
            "--out",
            str(out_dir),
            "--json",
        )

        assert result.returncode in (0, 2)
        data = json.loads(result.stdout)
        assert Path(data["artifacts"]["run_dir"]).resolve() == out_dir.resolve()

        manifest_path = out_dir / "manifest.json"
        model_source_path = out_dir / "model.veda.yaml"
        solver_dir = out_dir / "solver"

        assert manifest_path.exists()
        assert model_source_path.exists()
        assert solver_dir.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["run_id"] == "toy_states_2025"
        assert manifest["source"].endswith("toy_public.veda.yaml")
        assert manifest["case"] == "scenario"
        assert manifest["solver_status"] in {"skipped", "not_run"}

    def test_vita_results_run_missing_solver_artifacts(self, tmp_path):
        """vita results --run errors clearly when solver artifacts are missing."""
        run_dir = tmp_path / "runs" / "missing_solver"
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": "missing_solver",
                    "source": "model.veda.yaml",
                    "case": "scenario",
                    "timestamp": "2026-03-17T00:00:00Z",
                    "solver_status": "skipped",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "model.veda.yaml").write_text("model: {}\n", encoding="utf-8")

        result = run_vita("results", "--run", str(run_dir), "--json")
        assert result.returncode == 2
        assert "Missing required directory" in result.stderr

    def test_vita_sankey_run_missing_solver_artifacts(self, tmp_path):
        """vita sankey --run errors clearly when solver artifacts are missing."""
        run_dir = tmp_path / "runs" / "missing_solver"
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": "missing_solver",
                    "source": "model.veda.yaml",
                    "case": "scenario",
                    "timestamp": "2026-03-17T00:00:00Z",
                    "solver_status": "skipped",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "model.veda.yaml").write_text("model: {}\n", encoding="utf-8")

        result = run_vita("sankey", "--run", str(run_dir), "--format", "json")
        assert result.returncode == 2
        assert "Missing required directory" in result.stderr

    def test_vita_diff_json(self, tmp_path):
        """vita diff emits structured JSON for two run directories."""
        baseline_dir = tmp_path / "runs" / "baseline"
        variant_dir = tmp_path / "runs" / "variant"
        baseline_dir.mkdir(parents=True)
        variant_dir.mkdir(parents=True)

        manifest = {
            "run_id": "demo",
            "source": "model.veda.yaml",
            "case": "scenario",
            "timestamp": "2026-03-17T00:00:00Z",
            "solver_status": "optimal",
        }
        for run_dir in (baseline_dir, variant_dir):
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest) + "\n",
                encoding="utf-8",
            )
            (run_dir / "model.veda.yaml").write_text("model: {}\n", encoding="utf-8")

        (baseline_dir / "results.json").write_text(
            json.dumps(
                {
                    "objective": 100.0,
                    "var_act": [
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "gas_boiler",
                            "timeslice": "ANNUAL",
                            "level": 10.0,
                        },
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "h2_boiler",
                            "timeslice": "ANNUAL",
                            "level": 4.0,
                        }
                    ],
                    "var_cap": [],
                    "var_ncap": [],
                    "var_flo": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (variant_dir / "results.json").write_text(
            json.dumps(
                {
                    "objective": 120.0,
                    "var_act": [
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "gas_boiler",
                            "timeslice": "ANNUAL",
                            "level": 2.0,
                        },
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "electric_heater",
                            "timeslice": "ANNUAL",
                            "level": 12.0,
                        },
                    ],
                    "var_cap": [],
                    "var_ncap": [],
                    "var_flo": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vita("diff", str(baseline_dir), str(variant_dir), "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["objective"]["delta"] == 20.0
        assert payload["top_changes"]

        rows = payload["tables"]["var_act"]["rows"]
        statuses = {row["key"]["process"]: row["status"] for row in rows}
        assert statuses["gas_boiler"] == "changed"
        assert statuses["electric_heater"] == "added"
        assert statuses["h2_boiler"] == "removed"

        agent_result = run_vita(
            "diff", str(baseline_dir), str(variant_dir), "--agent-mode", "--json"
        )
        assert agent_result.returncode == 0
        agent_payload = json.loads(agent_result.stdout)
        assert agent_payload["objective"]["delta"] == 20.0

    def test_vita_diff_focus_and_metric_filters(self, tmp_path):
        """vita diff applies process focus and metric filtering."""
        baseline_dir = tmp_path / "runs" / "baseline"
        variant_dir = tmp_path / "runs" / "variant"
        baseline_dir.mkdir(parents=True)
        variant_dir.mkdir(parents=True)

        manifest = {
            "run_id": "demo",
            "source": "model.veda.yaml",
            "case": "scenario",
            "timestamp": "2026-03-17T00:00:00Z",
            "solver_status": "optimal",
        }
        for run_dir in (baseline_dir, variant_dir):
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest) + "\n",
                encoding="utf-8",
            )
            (run_dir / "model.veda.yaml").write_text("model: {}\n", encoding="utf-8")

        (baseline_dir / "results.json").write_text(
            json.dumps(
                {
                    "objective": 100.0,
                    "var_act": [
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "gas_boiler",
                            "timeslice": "ANNUAL",
                            "level": 8.0,
                        },
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "electric_heater",
                            "timeslice": "ANNUAL",
                            "level": 2.0,
                        },
                    ],
                    "var_cap": [],
                    "var_ncap": [],
                    "var_flo": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (variant_dir / "results.json").write_text(
            json.dumps(
                {
                    "objective": 98.0,
                    "var_act": [
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "gas_boiler",
                            "timeslice": "ANNUAL",
                            "level": 5.0,
                        },
                        {
                            "region": "R1",
                            "year": "2025",
                            "process": "electric_heater",
                            "timeslice": "ANNUAL",
                            "level": 5.0,
                        },
                    ],
                    "var_cap": [],
                    "var_ncap": [],
                    "var_flo": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_vita(
            "diff",
            str(baseline_dir),
            str(variant_dir),
            "--metric",
            "var_act",
            "--focus-processes",
            "gas_boiler",
            "--json",
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "objective" not in payload
        assert set(payload["tables"]) == {"var_act"}
        rows = payload["tables"]["var_act"]["rows"]
        assert len(rows) == 1
        assert rows[0]["key"]["process"] == "gas_boiler"

    def test_vita_diff_requires_results_files(self, tmp_path):
        """vita diff fails clearly when run artifacts are incomplete."""
        baseline_dir = tmp_path / "runs" / "baseline"
        variant_dir = tmp_path / "runs" / "variant"
        baseline_dir.mkdir(parents=True)
        variant_dir.mkdir(parents=True)

        manifest = {
            "run_id": "demo",
            "source": "model.veda.yaml",
            "case": "scenario",
            "timestamp": "2026-03-17T00:00:00Z",
            "solver_status": "optimal",
        }
        for run_dir in (baseline_dir, variant_dir):
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest) + "\n",
                encoding="utf-8",
            )
            (run_dir / "model.veda.yaml").write_text("model: {}\n", encoding="utf-8")

        result = run_vita("diff", str(baseline_dir), str(variant_dir), "--json")
        assert result.returncode == 2
        assert "Missing required file" in result.stderr


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
