"""Parity checks for the v0.3 backend bridge."""

import json
import subprocess
from pathlib import Path

import yaml

from tests.test_v0_2_backend import _v0_2_backend_source
from tools.veda_check import run_check

PROJECT_ROOT = Path(__file__).parent.parent
V0_2_FIXTURE = (
    PROJECT_ROOT / "vedalang" / "examples" / "v0_2" / "toy_heat_network.veda.yaml"
)


def test_v0_2_fixture_reaches_xl2times_successfully():
    """The flagship v0.3 fixture should pass compile + xl2times validation."""
    result = run_check(
        V0_2_FIXTURE,
        from_vedalang=True,
        selected_run="toy_states_2025",
    )

    assert result.success
    assert result.errors == 0
    assert result.warnings == 0


def test_v0_2_fixture_pipeline_no_solver_succeeds():
    """vedalang-dev pipeline should succeed through xl2times for the fixture."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "vedalang-dev",
            "pipeline",
            str(V0_2_FIXTURE),
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


def test_v0_2_emission_source_reaches_xl2times_successfully(tmp_path):
    """Emission-bearing v0.3 sources should survive the xl2times path."""
    src = tmp_path / "toy_heat_emissions.veda.yaml"
    src.write_text(
        yaml.safe_dump(_v0_2_backend_source(include_emissions=True)),
        encoding="utf-8",
    )

    result = run_check(
        src,
        from_vedalang=True,
        selected_run="toy_states_2025",
    )

    assert result.success
    assert result.errors == 0
