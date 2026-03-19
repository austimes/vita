"""Solver-backed CLI proof for run-scoped VAL_FLO reporting control."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.helpers.solver_harness import detect_solver_prerequisites
from tools.veda_dev.gdx_utils import dump_symbol_csv, find_gdxdump

pytestmark = [pytest.mark.solver, pytest.mark.solver_full]

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURE = (
    PROJECT_ROOT
    / "vedalang"
    / "examples"
    / "known_answer"
    / "ka15_value_flow_reporting_toggle.veda.yaml"
)


def _run_vita_solver(
    fixture: Path,
    *,
    run_id: str,
    out_dir: Path,
    times_src: Path,
    gams_binary: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "vita",
            "run",
            str(fixture),
            "--run",
            run_id,
            "--times-src",
            str(times_src),
            "--gams-binary",
            gams_binary,
            "--solver",
            "CPLEX",
            "--no-sankey",
            "--out",
            str(out_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def _rpt_opt_rows(gdx_path: Path) -> list[str]:
    csv_text = dump_symbol_csv(gdx_path, "RPT_OPT", find_gdxdump() or "")
    if not csv_text:
        return []
    return csv_text.splitlines()[1:]


@pytest.mark.solver_fast
def test_vita_run_respects_value_flow_reporting_toggle(tmp_path: Path) -> None:
    prereqs = detect_solver_prerequisites(gams_binary="gams")
    if not prereqs.ready:
        pytest.skip(prereqs.skip_reason())

    default_out = tmp_path / "default_on"
    disabled_out = tmp_path / "reporting_off"

    default_run = _run_vita_solver(
        FIXTURE,
        run_id="reg1_2020_default",
        out_dir=default_out,
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
    )
    disabled_run = _run_vita_solver(
        FIXTURE,
        run_id="reg1_2020_reporting_off",
        out_dir=disabled_out,
        times_src=prereqs.times_src,
        gams_binary=prereqs.gams_binary,
    )

    assert default_run.returncode == 0, default_run.stderr or default_run.stdout
    assert disabled_run.returncode == 0, disabled_run.stderr or disabled_run.stdout

    default_payload = json.loads(
        (default_out / "results.json").read_text(encoding="utf-8")
    )
    disabled_payload = json.loads(
        (disabled_out / "results.json").read_text(encoding="utf-8")
    )
    default_gdx = default_out / "solver" / "scenario.gdx"
    disabled_gdx = disabled_out / "solver" / "scenario.gdx"

    assert default_payload["var_flo"]
    assert disabled_payload["var_flo"]

    default_rpt_opt = _rpt_opt_rows(default_gdx)
    disabled_rpt_opt = _rpt_opt_rows(disabled_gdx)

    assert any('"FLO","1",1' in row for row in default_rpt_opt)
    assert any('"FLO","3",1' in row for row in default_rpt_opt)
    assert disabled_rpt_opt == []
