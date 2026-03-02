"""Tests for veda_dev pipeline result formatting and summaries."""

from tools.veda_dev.pipeline import (
    PipelineResult,
    StepResult,
    _format_step_detail,
    format_result_table,
)


def _licensing_diag() -> dict:
    return {
        "summary": {
            "ok": False,
            "problem_type": "licensing",
            "message": "GAMS licensing problem encountered",
        },
        "execution": {
            "ran_solver": False,
            "model_status": {
                "code": 11,
                "text": "LICENSING PROBLEM",
                "category": "licensing",
            },
            "solve_status": {
                "code": 7,
                "text": "LICENSING PROBLEM",
                "category": "licensing",
            },
            "objective": {"value": None},
        },
    }


def test_run_times_step_detail_includes_status_codes_and_no_solve() -> None:
    step = StepResult(
        skipped=False,
        success=False,
        artifacts={
            "gams_return_code": 0,
            "gams_diagnostics": _licensing_diag(),
        },
    )

    detail = _format_step_detail("run_times", step)

    assert "licensing" in detail
    assert "m=11" in detail
    assert "s=7" in detail
    assert "no-solve" in detail


def test_format_result_table_shows_verbose_run_times_failure_block() -> None:
    step = StepResult(
        skipped=False,
        success=False,
        artifacts={
            "gams_return_code": 0,
            "gams_command": "gams runmodel.gms --solve_with=CBC --run_name=scenario",
            "lst_file": "/tmp/run/scenario.lst",
            "gams_diagnostics_file": "/tmp/run/scenario_gams_diagnostics.json",
            "lst_license_excerpt": [
                "**** Terminated due to a licensing error",
                "**** License file: /opt/gams/gamslice.txt",
            ],
            "gams_stderr_tail": "line 1\nline 2\nLICENSE ERROR",
            "gams_diagnostics": _licensing_diag(),
        },
    )

    result = PipelineResult(
        success=False,
        input_path="vedalang/examples/toy_sectors/toy_agriculture.veda.yaml",
        input_kind="vedalang",
        work_dir="/tmp/run",
        steps={"run_times": step},
    )

    table = format_result_table(result)

    assert "Run-times diagnostics:" in table
    assert "Problem: licensing" in table
    assert "Message: GAMS licensing problem encountered" in table
    assert "Model status: 11 LICENSING PROBLEM [licensing]" in table
    assert "Solve status: 7 LICENSING PROBLEM [licensing]" in table
    assert "Ran solver: no" in table
    assert "Command: gams runmodel.gms --solve_with=CBC --run_name=scenario" in table
    assert "LST file: /tmp/run/scenario.lst" in table
    assert "Diagnostics JSON: /tmp/run/scenario_gams_diagnostics.json" in table
    assert "Licensing excerpt (from .lst):" in table
    assert "Terminated due to a licensing error" in table
    assert "GAMS stderr tail:" in table
    assert "LICENSE ERROR" in table


def test_pipeline_to_dict_summary_includes_gams_status_codes_and_text() -> None:
    step = StepResult(
        skipped=False,
        success=False,
        artifacts={
            "gams_diagnostics": _licensing_diag(),
        },
    )
    result = PipelineResult(
        success=False,
        input_path="in.veda.yaml",
        input_kind="vedalang",
        work_dir="/tmp/run",
        steps={"run_times": step},
    )

    as_dict = result.to_dict()
    gams_summary = as_dict["summary"]["gams"]

    assert gams_summary["problem_type"] == "licensing"
    assert gams_summary["model_status_code"] == 11
    assert gams_summary["model_status_text"] == "LICENSING PROBLEM"
    assert gams_summary["solve_status_code"] == 7
    assert gams_summary["solve_status_text"] == "LICENSING PROBLEM"
