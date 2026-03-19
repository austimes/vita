"""Tests for TIMES runner scaffold setup."""

from pathlib import Path

from tools.veda_run_times.runner import setup_work_dir


def test_setup_work_dir_injects_run_option_include(tmp_path: Path) -> None:
    dd_dir = tmp_path / "dd"
    dd_dir.mkdir()
    (dd_dir / "ts.dd").write_text("* timeslices\n", encoding="utf-8")
    (dd_dir / "output.dd").write_text("* outputs\n", encoding="utf-8")
    (dd_dir / "milestonyr.dd").write_text("* milestone years\n", encoding="utf-8")

    times_src = tmp_path / "times_src"
    times_src.mkdir()

    work_dir = setup_work_dir(
        dd_dir=dd_dir,
        case="scenario",
        work_dir=tmp_path / "work",
        times_src=times_src,
        run_option_lines=["RPT_OPT('FLO','3') = 1;"],
    )

    scenario_text = (work_dir / "scenario.run").read_text(encoding="utf-8")
    include_text = (work_dir / "vita_run_options.inc").read_text(encoding="utf-8")

    assert "$INCLUDE vita_run_options.inc" in scenario_text
    assert "RPT_OPT('FLO','3') = 1;" in include_text


def test_setup_work_dir_skips_include_when_no_run_options(tmp_path: Path) -> None:
    dd_dir = tmp_path / "dd"
    dd_dir.mkdir()
    (dd_dir / "ts.dd").write_text("* timeslices\n", encoding="utf-8")
    (dd_dir / "output.dd").write_text("* outputs\n", encoding="utf-8")
    (dd_dir / "milestonyr.dd").write_text("* milestone years\n", encoding="utf-8")

    times_src = tmp_path / "times_src"
    times_src.mkdir()

    work_dir = setup_work_dir(
        dd_dir=dd_dir,
        case="scenario",
        work_dir=tmp_path / "work",
        times_src=times_src,
        run_option_lines=[],
    )

    scenario_text = (work_dir / "scenario.run").read_text(encoding="utf-8")

    assert "$INCLUDE vita_run_options.inc" not in scenario_text
    assert not (work_dir / "vita_run_options.inc").exists()
