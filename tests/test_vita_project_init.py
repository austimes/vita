"""Tests for Vita project initialization."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from vita.project_init import init_project


class TestInitProject:
    """Tests for init_project()."""

    def test_basic_init_creates_directories(self, tmp_path: Path) -> None:
        result = init_project(tmp_path)
        for subdir in ["models", "experiments", "runs", "notes"]:
            assert (tmp_path / subdir).is_dir()
        assert result["project_dir"] == tmp_path

    def test_creates_agents_md(self, tmp_path: Path) -> None:
        init_project(tmp_path)
        agents = tmp_path / "AGENTS.md"
        assert agents.exists()
        assert "vita:bd:start" not in agents.read_text()

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
        assert "remove this entire `vita:skill-bootstrap` block" in content

    def test_with_bd_runs_bd_init(self, tmp_path: Path) -> None:
        with patch("vita.project_init.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bd", "init"], returncode=0
            )
            result = init_project(tmp_path, with_bd=True)
        assert result["bd_initialized"] is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["bd", "init"]

    def test_with_bd_appends_agents_template(self, tmp_path: Path) -> None:
        with patch("vita.project_init.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bd", "init"], returncode=0
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
        # AGENTS.md should exist but without bd section
        agents = tmp_path / "AGENTS.md"
        assert agents.exists()
        assert "vita:bd:start" not in agents.read_text()

    def test_with_bd_handles_bd_failure(self, tmp_path: Path) -> None:
        with patch(
            "vita.project_init.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "bd init"),
        ):
            result = init_project(tmp_path, with_bd=True)
        assert result["bd_initialized"] is False
        assert result["bd_failed"] is True

    def test_without_bd_no_bd_keys_in_result(self, tmp_path: Path) -> None:
        result = init_project(tmp_path)
        assert "bd_initialized" not in result
        assert "bd_failed" not in result
