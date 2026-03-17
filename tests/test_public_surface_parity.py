"""Parity checks for the v0.3 backend bridge."""

import json
import subprocess
from pathlib import Path

import yaml

from tests.test_backend_bridge import _sample_source
from tools.veda_check import run_check

PROJECT_ROOT = Path(__file__).parent.parent
PUBLIC_FIXTURE = (
    PROJECT_ROOT
    / "vedalang"
    / "examples"
    / "feature_demos"
    / "toy_heat_network.veda.yaml"
)


def test_public_fixture_reaches_xl2times_successfully():
    """The flagship v0.3 fixture should pass compile + xl2times validation."""
    result = run_check(
        PUBLIC_FIXTURE,
        from_vedalang=True,
        selected_run="toy_states_2025",
    )

    assert result.success
    assert result.errors == 0
    assert result.warnings == 0


def test_public_fixture_vita_run_no_solver_succeeds():
    """vita run --no-solver succeeds through xl2times on the flagship fixture."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "vita",
            "run",
            str(PUBLIC_FIXTURE),
            "--run",
            "toy_states_2025",
            "--no-solver",
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["success"] is True
    assert data["artifacts"]["run_id"] == "toy_states_2025"


def test_public_emission_source_reaches_xl2times_successfully(tmp_path):
    """Emission-bearing v0.3 sources should survive the xl2times path."""
    src = tmp_path / "toy_heat_emissions.veda.yaml"
    src.write_text(
        yaml.safe_dump(_sample_source(include_emissions=True)),
        encoding="utf-8",
    )

    result = run_check(
        src,
        from_vedalang=True,
        selected_run="toy_states_2025",
    )

    assert result.success
    assert result.errors == 0
