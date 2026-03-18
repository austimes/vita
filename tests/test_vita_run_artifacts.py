"""Unit tests for Vita run artifact helpers."""

import json
from pathlib import Path

import pytest

from vita.run_artifacts import (
    RunArtifactError,
    RunManifest,
    build_run_artifact_paths,
    emit_run_artifacts,
    load_run_manifest,
    resolve_run_artifacts,
    write_run_manifest,
)


class _FakeResults:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_dict(self) -> dict:
        return self._payload


def _toy_industry_symbol_csv(*, high_h2_capex: bool = False) -> dict[str, str]:
    """Representative toy-industry payload with switching rows in PAR_* symbols."""
    ncap_h2 = 280 if high_h2_capex else 100
    return {
        "OBJZ": '"Val"\n195.5915\n',
        "VAR_OBJ": (
            '"R","OBV","CUR","Val"\n'
            '"SINGLE","OBJINV","USD",195.5915\n'
        ),
        # Current extraction reads VAR_* first, but toy-industry VAR_* rows are empty.
        "VAR_ACT": (
            '"R","ALLYEAR","ALLYEAR","P","S","Val"\n'
            '"SINGLE","2025","2025","PRC_ROLE_ELC","ANNUAL",0\n'
            '"SINGLE","2025","2025","PRC_ROLE_H2","ANNUAL",0\n'
        ),
        "VAR_CAP": '"R","ALLYEAR","P","Val"\n',
        "VAR_NCAP": (
            '"R","ALLYEAR","P","Val"\n'
            '"SINGLE","2025","PRC_HEAT_E","0"\n'
            '"SINGLE","2025","PRC_HEAT_H2","0"\n'
        ),
        "VAR_FLO": '"R","ALLYEAR","ALLYEAR","P","C","S","Val"\n',
        "PAR_FLO": '"R","ALLYEAR","ALLYEAR","P","C","S","Val"\n',
        # Switching signals currently live in fallback PAR_* symbols for this toy model.
        "PAR_ACTM": (
            '"R","LL","LL","P","S","Val"\n'
            '"SINGLE","2025","2025","PRC_ROLE_ELC","ANNUAL",25\n'
            '"SINGLE","2025","2025","PRC_ROLE_H2","ANNUAL",18\n'
            '"SINGLE","2025","2025","PRC_ROLE_NG","ANNUAL",8\n'
        ),
        "PAR_NCAPM": (
            '"R","ALLYEAR","P","Val"\n'
            '"SINGLE","2025","PRC_HEAT_E",80\n'
            f'"SINGLE","2025","PRC_HEAT_H2",{ncap_h2}\n'
        ),
        "PAR_FLOM": (
            '"R","ALLYEAR","ALLYEAR","P","C","S","Val"\n'
            '"SINGLE","2025","2025","PRC_ROLE_ELC","COM_ELC","ANNUAL",202.7\n'
            '"SINGLE","2025","2025","PRC_ROLE_H2","COM_H2","ANNUAL",145.9\n'
        ),
    }


def test_resolve_run_artifacts_uses_case_from_manifest(tmp_path: Path) -> None:
    """Resolver should derive canonical solver filenames from manifest case."""
    run_dir = tmp_path / "runs" / "baseline"
    run_dir.mkdir(parents=True)
    manifest = RunManifest(
        run_id="baseline",
        source="toy.veda.yaml",
        case="custom",
        timestamp="2026-03-17T00:00:00Z",
        solver_status="optimal",
    )
    write_run_manifest(manifest, run_dir / "manifest.json")
    (run_dir / "model.veda.yaml").write_text("model: {}\n", encoding="utf-8")

    custom_paths = build_run_artifact_paths(run_dir, case="custom")
    custom_paths.results_path.write_text("{}\n", encoding="utf-8")
    custom_paths.solver_dir.mkdir(parents=True, exist_ok=True)
    custom_paths.gdx_path.write_text("gdx", encoding="utf-8")
    custom_paths.lst_path.write_text("lst", encoding="utf-8")

    resolved = resolve_run_artifacts(
        run_dir,
        require_results=True,
        require_solver=True,
    )
    assert resolved.case == "custom"
    assert resolved.gdx_path == custom_paths.gdx_path
    assert resolved.lst_path == custom_paths.lst_path


def test_resolve_run_artifacts_reports_missing_required_files(tmp_path: Path) -> None:
    """Validator should list missing required files with clear messaging."""
    run_dir = tmp_path / "missing"
    run_dir.mkdir(parents=True)

    with pytest.raises(RunArtifactError) as excinfo:
        resolve_run_artifacts(run_dir)

    msg = str(excinfo.value)
    assert "manifest.json" in msg
    assert "model.veda.yaml" in msg


def test_manifest_round_trip(tmp_path: Path) -> None:
    """Manifest serializer should preserve required metadata."""
    manifest = RunManifest(
        run_id="baseline",
        source="toy.veda.yaml",
        case="scenario",
        timestamp="2026-03-17T00:00:00Z",
        solver_status="skipped",
        pipeline_success=True,
        input_kind="vedalang",
    )
    manifest_path = tmp_path / "manifest.json"
    write_run_manifest(manifest, manifest_path)
    loaded = load_run_manifest(manifest_path)
    assert loaded == manifest


def test_emit_run_artifacts_no_solver_writes_manifest_and_snapshot(
    tmp_path: Path,
) -> None:
    """No-solver runs should still emit deterministic manifest/source artifacts."""
    src = tmp_path / "model.veda.yaml"
    src.write_text("dsl_version: '0.3'\n", encoding="utf-8")

    emission = emit_run_artifacts(
        run_dir=tmp_path / "runs" / "baseline",
        input_path=src,
        input_kind="vedalang",
        case="scenario",
        selected_run_id="baseline",
        pipeline_success=True,
        pipeline_artifacts={"run_id": "baseline"},
        run_times_artifacts={},
        run_times_success=False,
        run_times_skipped=True,
    )

    assert emission.paths.manifest_path.exists()
    assert emission.paths.source_snapshot_path.exists()
    assert not emission.paths.results_path.exists()
    assert emission.manifest.solver_status == "skipped"


def test_emit_run_artifacts_solver_case_writes_results_and_solver_files(
    tmp_path: Path,
) -> None:
    """Solver-backed runs should copy solver outputs and emit results.json."""
    src = tmp_path / "model.veda.yaml"
    src.write_text("dsl_version: '0.3'\n", encoding="utf-8")

    gdx_src = tmp_path / "scenario.gdx"
    lst_src = tmp_path / "scenario.lst"
    gdx_src.write_text("gdx", encoding="utf-8")
    lst_src.write_text("lst", encoding="utf-8")

    def _fake_extract_results(
        *,
        gdx_path: Path,
        include_flows: bool,
        limit: int,
    ) -> _FakeResults:
        assert gdx_path.exists()
        assert include_flows is True
        assert limit == 0
        return _FakeResults({"gdx_path": str(gdx_path), "errors": []})

    emission = emit_run_artifacts(
        run_dir=tmp_path / "runs" / "solver",
        input_path=src,
        input_kind="vedalang",
        case="scenario",
        selected_run_id="solver",
        pipeline_success=True,
        pipeline_artifacts={"run_id": "solver"},
        run_times_artifacts={
            "gdx_files": [str(gdx_src)],
            "lst_file": str(lst_src),
            "objective": 123.4,
            "gams_diagnostics": {
                "summary": {"ok": True},
                "execution": {
                    "model_status": {"code": 1},
                    "solve_status": {"code": 1},
                },
            },
        },
        run_times_success=True,
        run_times_skipped=False,
        extract_results=_fake_extract_results,
    )

    assert emission.results_written is True
    assert emission.paths.gdx_path.exists()
    assert emission.paths.lst_path.exists()
    assert emission.paths.results_path.exists()

    payload = json.loads(emission.paths.results_path.read_text(encoding="utf-8"))
    assert payload["errors"] == []

    resolved = resolve_run_artifacts(
        emission.paths.run_dir,
        require_results=True,
        require_solver=True,
    )
    assert resolved.manifest_path.exists()


def test_emit_run_artifacts_copies_compiled_and_dd_artifacts(
    tmp_path: Path,
) -> None:
    """Pipeline intermediate artifacts (Excel, DD, diagnostics) should be preserved."""
    src = tmp_path / "model.veda.yaml"
    src.write_text("dsl_version: '0.3'\n", encoding="utf-8")

    # Simulate pipeline work directory with Excel and DD outputs
    work_dir = tmp_path / "work"
    excel_dir = work_dir / "excel"
    dd_dir = work_dir / "dd"
    excel_dir.mkdir(parents=True)
    dd_dir.mkdir(parents=True)

    # Create fake Excel files (including nested subdirectory)
    (excel_dir / "base").mkdir()
    (excel_dir / "base" / "base.xlsx").write_bytes(b"excel-base")
    (excel_dir / "scen_baseline.xlsx").write_bytes(b"excel-scen")

    # Create fake DD files
    (dd_dir / "scenario.dd").write_text("DD content", encoding="utf-8")
    (dd_dir / "syssettings.dd").write_text("SS content", encoding="utf-8")

    # Create xl2times diagnostics next to dd_dir
    diag = {"diagnostics": []}
    (work_dir / "xl2times_diagnostics.json").write_text(
        json.dumps(diag), encoding="utf-8"
    )

    emission = emit_run_artifacts(
        run_dir=tmp_path / "runs" / "baseline",
        input_path=src,
        input_kind="vedalang",
        case="scenario",
        selected_run_id="baseline",
        pipeline_success=True,
        pipeline_artifacts={
            "run_id": "baseline",
            "excel_dir": str(excel_dir),
            "dd_dir": str(dd_dir),
        },
        run_times_artifacts={},
        run_times_success=False,
        run_times_skipped=True,
    )

    # Verify compiled/ directory
    compiled = emission.paths.compiled_dir
    assert compiled.is_dir()
    assert (compiled / "base" / "base.xlsx").exists()
    assert (compiled / "scen_baseline.xlsx").exists()
    assert (compiled / "base" / "base.xlsx").read_bytes() == b"excel-base"

    # Verify dd/ directory
    dd = emission.paths.dd_dir
    assert dd.is_dir()
    assert (dd / "scenario.dd").exists()
    assert (dd / "syssettings.dd").exists()
    assert (dd / "diagnostics.json").exists()
    diag_loaded = json.loads((dd / "diagnostics.json").read_text(encoding="utf-8"))
    assert diag_loaded == {"diagnostics": []}


def test_emit_run_artifacts_toy_industry_switching_signal_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Toy-industry baseline/variant artifacts should expose switching tables."""
    from tools.veda_dev import times_results

    src = tmp_path / "toy_industry.veda.yaml"
    src.write_text("dsl_version: '0.3'\n", encoding="utf-8")

    gdx_baseline = tmp_path / "baseline.gdx"
    gdx_variant = tmp_path / "high_h2_capex.gdx"
    lst_baseline = tmp_path / "baseline.lst"
    lst_variant = tmp_path / "high_h2_capex.lst"
    gdx_baseline.write_text("gdx", encoding="utf-8")
    gdx_variant.write_text("gdx", encoding="utf-8")
    lst_baseline.write_text("lst", encoding="utf-8")
    lst_variant.write_text("lst", encoding="utf-8")

    symbol_csv_by_gdx = {
        gdx_baseline.resolve(): _toy_industry_symbol_csv(high_h2_capex=False),
        gdx_variant.resolve(): _toy_industry_symbol_csv(high_h2_capex=True),
    }

    def _mock_dump_symbol_csv(gdx_path: Path, symbol: str, _gdxdump: str) -> str | None:
        return symbol_csv_by_gdx.get(gdx_path.resolve(), {}).get(symbol)

    monkeypatch.setattr(times_results, "find_gdxdump", lambda: "/usr/bin/gdxdump")
    monkeypatch.setattr(times_results, "dump_symbol_csv", _mock_dump_symbol_csv)

    for run_id, gdx_src, lst_src in (
        ("baseline", gdx_baseline, lst_baseline),
        ("high_h2_capex", gdx_variant, lst_variant),
    ):
        emission = emit_run_artifacts(
            run_dir=tmp_path / "runs" / run_id,
            input_path=src,
            input_kind="vedalang",
            case="scenario",
            selected_run_id=run_id,
            pipeline_success=True,
            pipeline_artifacts={"run_id": run_id},
            run_times_artifacts={
                "gdx_files": [str(gdx_src)],
                "lst_file": str(lst_src),
                "objective": 200.0,
                "gams_diagnostics": {
                    "summary": {"ok": True},
                    "execution": {
                        "model_status": {"code": 1},
                        "solve_status": {"code": 1},
                    },
                },
            },
            run_times_success=True,
            run_times_skipped=False,
            extract_results=times_results.extract_results,
        )

        payload = json.loads(emission.paths.results_path.read_text(encoding="utf-8"))
        missing_tables = [
            metric
            for metric in ("var_act", "var_cap", "var_ncap", "var_flo")
            if not payload.get(metric)
        ]
        assert not missing_tables, (
            "Toy-industry switching tables were empty in emitted run artifacts: "
            f"{', '.join(missing_tables)}"
        )
