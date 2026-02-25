"""Tests for advisory LLM unit/coefficient certification workflow."""

import argparse
import json

import yaml

from vedalang import cli
from vedalang.lint import llm_unit_check

SOURCE = {
    "model": {
        "name": "UnitCheckTest",
        "regions": ["R1"],
        "commodities": [
            {"id": "primary:natural_gas", "type": "fuel", "unit": "PJ"},
            {"id": "secondary:electricity", "type": "energy", "unit": "TWh"},
        ],
    },
    "process_roles": [
        {
            "id": "generate_electricity",
            "required_inputs": [{"commodity": "primary:natural_gas"}],
            "required_outputs": [{"commodity": "secondary:electricity"}],
        }
    ],
    "process_variants": [
        {
            "id": "ccgt",
            "role": "generate_electricity",
            "inputs": [{"commodity": "primary:natural_gas", "coefficient": 6.4}],
            "outputs": [{"commodity": "secondary:electricity", "coefficient": 1.0}],
            "efficiency": 0.55,
        }
    ],
}


def _certified_result(
    source: dict, component: str
) -> llm_unit_check.ComponentUnitCheckResult:
    votes = [
        llm_unit_check.VoteResult(model="m1", status="pass", findings=[]),
        llm_unit_check.VoteResult(model="m2", status="pass", findings=[]),
    ]
    return llm_unit_check.ComponentUnitCheckResult(
        component=component,
        fingerprint=llm_unit_check.component_fingerprint(source, component),
        votes=votes,
    )


def test_component_fingerprint_changes_on_component_edit():
    fp1 = llm_unit_check.component_fingerprint(SOURCE, "ccgt")
    mutated = json.loads(json.dumps(SOURCE))
    mutated["process_variants"][0]["efficiency"] = 0.6
    fp2 = llm_unit_check.component_fingerprint(mutated, "ccgt")
    assert fp1 != fp2


def test_select_components_skips_certified_current_by_default():
    fp = llm_unit_check.component_fingerprint(SOURCE, "ccgt")
    store = {
        "version": 1,
        "components": {"ccgt": {"status": "certified", "fingerprint": fp}},
    }
    to_check, skipped = llm_unit_check.select_components(
        source=SOURCE,
        store=store,
        selected=None,
        run_all=False,
        force=False,
    )
    assert to_check == []
    assert skipped == ["ccgt"]


def test_select_components_force_rechecks_certified_components():
    fp = llm_unit_check.component_fingerprint(SOURCE, "ccgt")
    store = {
        "version": 1,
        "components": {"ccgt": {"status": "certified", "fingerprint": fp}},
    }
    to_check, skipped = llm_unit_check.select_components(
        source=SOURCE,
        store=store,
        selected=None,
        run_all=False,
        force=True,
    )
    assert to_check == ["ccgt"]
    assert skipped == []


def test_parse_unit_check_response_handles_fenced_json():
    raw = """```json
{"status":"pass","findings":[{"severity":"warning","message":"ok"}]}
```"""
    status, findings = llm_unit_check.parse_unit_check_response(raw)
    assert status == "pass"
    assert findings[0]["severity"] == "warning"


def test_run_component_unit_check_needs_review_on_split_votes():
    def mock_llm(system: str, user: str, model: str) -> str:
        del system, user
        if model == "m1":
            return json.dumps({"status": "pass", "findings": []})
        return json.dumps({
            "status": "fail",
            "findings": [{"severity": "critical", "message": "bad conversion"}],
        })

    result = llm_unit_check.run_component_unit_check(
        source=SOURCE,
        component="ccgt",
        models=["m1", "m2"],
        llm_callable=mock_llm,
    )
    assert result.status == "needs_review"
    assert result.quorum == "1/2"


def test_update_store_with_result_persists_component_record():
    store = {"version": 1, "components": {}}
    result = _certified_result(SOURCE, "ccgt")
    llm_unit_check.update_store_with_result(store, result)
    rec = store["components"]["ccgt"]
    assert rec["status"] == "certified"
    assert rec["quorum"] == "2/2"
    assert rec["fingerprint"].startswith("sha256:")


def test_cmd_llm_check_units_json_success(tmp_path, monkeypatch, capsys):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")
    store_file = tmp_path / "checks.json"

    def fake_run_component_unit_check(source: dict, component: str, models=None):
        del models
        return _certified_result(source, component)

    monkeypatch.setattr(
        llm_unit_check,
        "run_component_unit_check",
        fake_run_component_unit_check,
    )

    args = argparse.Namespace(
        file=model_file,
        json=True,
        component=None,
        all=False,
        force=False,
        model=None,
        store=store_file,
    )
    exit_code = cli.cmd_llm_check_units(args)
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert out["success"] is True
    assert out["certified"] == 1
    assert out["needs_review"] == 0
    assert store_file.exists()


def test_cmd_llm_check_units_needs_review_exit_code(tmp_path, monkeypatch, capsys):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")

    def fake_run_component_unit_check(source: dict, component: str, models=None):
        del models
        votes = [
            llm_unit_check.VoteResult(model="m1", status="pass", findings=[]),
            llm_unit_check.VoteResult(
                model="m2",
                status="fail",
                findings=[{"severity": "critical", "message": "bad units"}],
            ),
        ]
        return llm_unit_check.ComponentUnitCheckResult(
            component=component,
            fingerprint=llm_unit_check.component_fingerprint(source, component),
            votes=votes,
        )

    monkeypatch.setattr(
        llm_unit_check,
        "run_component_unit_check",
        fake_run_component_unit_check,
    )

    args = argparse.Namespace(
        file=model_file,
        json=True,
        component=None,
        all=False,
        force=False,
        model=None,
        store=None,
    )
    exit_code = cli.cmd_llm_check_units(args)
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert out["needs_review"] == 1


def test_cmd_llm_check_units_unknown_component_returns_error(tmp_path, capsys):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")

    args = argparse.Namespace(
        file=model_file,
        json=True,
        component=["missing_component"],
        all=False,
        force=False,
        model=None,
        store=None,
    )
    exit_code = cli.cmd_llm_check_units(args)
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert out["success"] is False
    assert "Unknown component" in out["error"]
