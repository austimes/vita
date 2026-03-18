"""Tests for Vita project initialization."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from vita.experiment_manifest import load_experiment_manifest
from vita.project_init import init_project
from vita.starter_catalog import CURATED_STARTER_DEMOS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROOT_README = PROJECT_ROOT / "README.md"
CURATED_DEMO_PATHS = [demo.target_relpath for demo in CURATED_STARTER_DEMOS]
FEATURED_DEMO = Path("models/demos/toy_industry.veda.yaml")
FEATURED_EXPERIMENT = Path("experiments/demos/toy_industry_core.experiment.yaml")


class TestInitProject:
    """Tests for init_project()."""

    def test_basic_init_creates_directories(self, tmp_path: Path) -> None:
        result = init_project(tmp_path)
        for subdir in ["models", "experiments", "runs", "notes"]:
            assert (tmp_path / subdir).is_dir()
        assert result["project_dir"] == tmp_path
        assert result["starter_profile"] == "curated"

    def test_default_init_seeds_curated_demos(self, tmp_path: Path) -> None:
        result = init_project(tmp_path)
        assert result["featured_model"] == str(FEATURED_DEMO)
        assert result["featured_run"] == "single_2025"
        for relpath in CURATED_DEMO_PATHS:
            assert (tmp_path / relpath).exists()
        assert (tmp_path / FEATURED_EXPERIMENT).exists()
        assert not (tmp_path / "models" / "example.veda.yaml").exists()

    def test_minimal_profile_preserves_legacy_starter(self, tmp_path: Path) -> None:
        result = init_project(tmp_path, starter_profile="minimal")
        assert result["starter_profile"] == "minimal"
        assert (tmp_path / "models" / "example.veda.yaml").exists()
        assert not (tmp_path / "models" / "demos").exists()
        assert not (tmp_path / FEATURED_EXPERIMENT).exists()

    def test_creates_agents_md(self, tmp_path: Path) -> None:
        init_project(tmp_path)
        agents = tmp_path / "AGENTS.md"
        assert agents.exists()
        assert "vita:bd:start" not in agents.read_text()

    def test_curated_readme_contains_featured_demo_commands(
        self, tmp_path: Path
    ) -> None:
        init_project(tmp_path)
        readme = (tmp_path / "README.md").read_text()
        assert "models/demos/toy_industry.veda.yaml" in readme
        assert "single_2025" in readme
        assert "Demo Catalog" in readme
        assert "Using Your Own Model" in readme
        assert "there is no single\nactive model setting" in readme
        assert (
            "vita experiment "
            "experiments/demos/toy_industry_core.experiment.yaml"
        ) in readme

    def test_curated_agents_contains_featured_demo_guidance(
        self, tmp_path: Path
    ) -> None:
        init_project(tmp_path)
        agents = (tmp_path / "AGENTS.md").read_text()
        assert (
            "vedalang validate models/demos/toy_industry.veda.yaml "
            "--run single_2025"
        ) in agents
        assert (
            "Show me the demo catalog and recommend which starter model fits "
            "my question"
        ) in agents
        assert "Run the example model and explain the results" not in agents

    def test_seeded_experiment_manifest_resolves_demo_model(
        self, tmp_path: Path
    ) -> None:
        init_project(tmp_path)
        manifest = load_experiment_manifest(tmp_path / FEATURED_EXPERIMENT)
        assert manifest.baseline.model == (tmp_path / FEATURED_DEMO).resolve()
        assert manifest.variants[0].model == (tmp_path / FEATURED_DEMO).resolve()

    def test_agents_md_contains_skill_bootstrap(self, tmp_path: Path) -> None:
        init_project(tmp_path)
        agents = tmp_path / "AGENTS.md"
        content = agents.read_text()
        assert "<!-- vita:skill-bootstrap:start -->" in content
        assert "<!-- vita:skill-bootstrap:end -->" in content
        assert (
            "https://github.com/austimes/vita/tree/main/skills/"
            "vedalang-dsl-cli" in content
        )
        assert (
            "https://github.com/austimes/vita/tree/main/skills/"
            "vita-experiment-loop" in content
        )
        assert (
            "https://github.com/austimes/vita/tree/main/skills/"
            "vedalang-modeling-conventions" in content
        )
        assert "project-locally" in content
        assert "amp skill add" in content
        assert "amp skill remove" in content
        assert "remove this entire `vita:skill-bootstrap` block" in content

    def test_smoke_test_uses_curated_featured_demo(self, tmp_path: Path) -> None:
        with patch("vita.project_init.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[
                    "vedalang",
                    "validate",
                    str(tmp_path / FEATURED_DEMO),
                    "--run",
                    "single_2025",
                ],
                returncode=0,
            )
            init_project(
                tmp_path,
                smoke_test=True,
                gams_binary="gams",
                times_src=tmp_path,
            )
        call_args = mock_run.call_args
        assert call_args[0][0] == [
            "vedalang",
            "validate",
            str(tmp_path / FEATURED_DEMO),
            "--run",
            "single_2025",
        ]

    def test_smoke_test_uses_minimal_starter_when_requested(
        self, tmp_path: Path
    ) -> None:
        with patch("vita.project_init.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[
                    "vedalang",
                    "validate",
                    str(tmp_path / "models" / "example.veda.yaml"),
                    "--run",
                    "demo_2025",
                ],
                returncode=0,
            )
            init_project(
                tmp_path,
                smoke_test=True,
                starter_profile="minimal",
                gams_binary="gams",
                times_src=tmp_path,
            )
        call_args = mock_run.call_args
        assert call_args[0][0] == [
            "vedalang",
            "validate",
            str(tmp_path / "models" / "example.veda.yaml"),
            "--run",
            "demo_2025",
        ]

    def test_reinit_does_not_overwrite_existing_models(self, tmp_path: Path) -> None:
        init_project(tmp_path)
        featured_path = tmp_path / FEATURED_DEMO
        featured_path.write_text("# user customized demo\n", encoding="utf-8")
        custom_model = tmp_path / "models" / "custom.veda.yaml"
        custom_model.write_text("dsl_version: \"0.3\"\n", encoding="utf-8")

        init_project(tmp_path)

        assert featured_path.read_text(encoding="utf-8") == "# user customized demo\n"
        assert custom_model.exists()

    def test_with_bd_runs_bd_init(self, tmp_path: Path) -> None:
        with patch("vita.project_init.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bd", "init", "--quiet"], returncode=0
            )
            result = init_project(tmp_path, with_bd=True)
        assert result["bd_initialized"] is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["bd", "init", "--quiet"]
        assert call_args[1]["capture_output"] is True
        assert call_args[1]["text"] is True

    def test_with_bd_appends_agents_template(self, tmp_path: Path) -> None:
        with patch("vita.project_init.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bd", "init", "--quiet"], returncode=0
            )
            init_project(tmp_path, with_bd=True)
        agents = tmp_path / "AGENTS.md"
        content = agents.read_text()
        assert "<!-- vita:bd:start -->" in content
        assert "<!-- vita:bd:end -->" in content
        assert "Experiment Task Tracking" in content

    def test_with_bd_handles_missing_bd(self, tmp_path: Path) -> None:
        with patch(
            "vita.project_init.subprocess.run",
            side_effect=FileNotFoundError("bd not found"),
        ):
            result = init_project(tmp_path, with_bd=True)
        assert result["bd_initialized"] is False
        assert result["bd_failed"] is True
        assert (
            result["bd_error"]
            == "bd not found on PATH; install beads to use task tracking"
        )
        # AGENTS.md should exist but without bd section
        agents = tmp_path / "AGENTS.md"
        assert agents.exists()
        assert "vita:bd:start" not in agents.read_text()

    def test_with_bd_handles_bd_failure(self, tmp_path: Path) -> None:
        with patch(
            "vita.project_init.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                1, ["bd", "init", "--quiet"], stderr="bd backend failed"
            ),
        ):
            result = init_project(tmp_path, with_bd=True)
        assert result["bd_initialized"] is False
        assert result["bd_failed"] is True
        assert result["bd_error"] == "bd backend failed"

    def test_with_bd_handles_timeout(self, tmp_path: Path) -> None:
        with patch(
            "vita.project_init.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["bd", "init", "--quiet"], 30),
        ):
            result = init_project(tmp_path, with_bd=True)
        assert result["bd_initialized"] is False
        assert result["bd_failed"] is True
        assert result["bd_error"] == "bd init timed out after 30s"

    def test_without_bd_no_bd_keys_in_result(self, tmp_path: Path) -> None:
        result = init_project(tmp_path)
        assert "bd_initialized" not in result
        assert "bd_failed" not in result


def test_root_readme_quick_start_uses_curated_demo() -> None:
    content = ROOT_README.read_text(encoding="utf-8")
    assert (
        "vedalang validate models/demos/toy_industry.veda.yaml "
        "--run single_2025"
    ) in content
    assert (
        "vita run models/demos/toy_industry.veda.yaml "
        "--run single_2025 --no-solver --json"
    ) in content
    assert (
        "vita experiment experiments/demos/toy_industry_core.experiment.yaml "
        "--out experiments/ --json"
    ) in content
