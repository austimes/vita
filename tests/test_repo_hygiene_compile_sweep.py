"""Tests for run-aware example compile hygiene sweep."""

from pathlib import Path

import yaml

from tests.test_backend_bridge import _sample_source
from tools.repo_hygiene.check_examples_compile import evaluate_examples


def _write_source(path: Path, source: dict) -> None:
    path.write_text(yaml.safe_dump(source), encoding="utf-8")


def test_compile_sweep_records_expected_run_selection_e002_for_multi_run(tmp_path):
    source = _sample_source()
    source["runs"].append(
        {
            "id": "toy_states_alt",
            "veda_book_name": "TOYSTATESALT",
            "year_set": "pathway_2025_2035",
            "currency_year": 2024,
            "region_partition": "toy_states",
        }
    )
    model_path = tmp_path / "multi_run.veda.yaml"
    _write_source(model_path, source)

    report = evaluate_examples([model_path])

    assert report["success"] is True
    assert report["checked_files"] == 1
    assert report["checked_runs"] == 2
    assert report["expected_e002_files"] == [str(model_path)]
    assert report["failures"] == []


def test_compile_sweep_does_not_hide_non_selection_e002_failures(tmp_path):
    source = _sample_source()
    source["runs"][0]["region_partition"] = "missing_partition"
    model_path = tmp_path / "bad_run_ref.veda.yaml"
    _write_source(model_path, source)

    report = evaluate_examples([model_path])

    assert report["success"] is False
    assert report["expected_e002_files"] == []
    assert len(report["failures"]) == 1
    assert report["failures"][0]["code"] == "E002"
    assert "missing region_partition" in report["failures"][0]["message"]
