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
            "activity_unit": "PJ",
            "capacity_unit": "GW",
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

SOURCE_WITH_MONETARY = {
    "model": {
        "name": "UnitCheckMonetary",
        "regions": ["R1"],
        "monetary": {
            "canonical": "MAUD24",
            "fx_table": "rules/monetary/fx_aud_usd_world_bank_pa_nus_fcrf.yaml",
        },
        "commodities": [
            {"id": "secondary:electricity", "type": "energy", "unit": "PJ"},
        ],
    },
    "process_roles": [
        {
            "id": "supply_power",
            "activity_unit": "PJ",
            "capacity_unit": "PJ/yr",
            "required_inputs": [],
            "required_outputs": [{"commodity": "secondary:electricity"}],
        }
    ],
    "process_variants": [
        {
            "id": "grid_import",
            "role": "supply_power",
            "inputs": [],
            "outputs": [{"commodity": "secondary:electricity"}],
            "variable_om_cost": "6.944444 MUSD24/PJ",
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


def test_parse_unit_check_response_preserves_fix_guidance_fields():
    raw = json.dumps({
        "status": "needs_review",
        "findings": [
            {
                "severity": "critical",
                "message": "Input coefficient appears off by 3.6x",
                "suggestion": "Use PJ for process activity and convert from TWh.",
                "expected_process_units": {
                    "activity_unit": "PJ",
                    "capacity_unit": "GW",
                },
                "expected_commodity_units": {
                    "primary:natural_gas": "PJ",
                    "secondary:electricity": "TWh",
                },
                "observed_units": {
                    "activity_unit": "TWh",
                    "capacity_unit": "GW",
                },
                "model_expectation": "Thermal generator should use PJ activity.",
            }
        ],
    })
    status, findings = llm_unit_check.parse_unit_check_response(raw)
    assert status == "needs_review"
    assert len(findings) == 1
    assert findings[0]["suggestion"]
    assert findings[0]["expected_process_units"]["activity_unit"] == "PJ"
    assert findings[0]["expected_commodity_units"]["secondary:electricity"] == "TWh"


def test_assemble_unit_prompt_includes_unit_enums_and_policy():
    system_prompt, user_prompt = llm_unit_check.assemble_unit_prompt(SOURCE, "ccgt")
    assert "status" in system_prompt
    assert "Allowed unit enums from schema" in user_prompt
    assert "Model unit policy" in user_prompt
    assert "energy_unit" in user_prompt


def test_assemble_unit_prompt_includes_monetary_literal_guidance():
    system_prompt, user_prompt = llm_unit_check.assemble_unit_prompt(
        SOURCE_WITH_MONETARY,
        "grid_import",
    )
    assert "currency-year tokens" in system_prompt
    assert "Monetary literal syntax and policy" in user_prompt
    assert "MAUD24" in user_prompt
    assert "cost_rate_literal_pattern" in user_prompt
    assert "Model monetary policy" in user_prompt
    assert '"canonical": "MAUD24"' in user_prompt
    assert '"activity_unit": "PJ"' in user_prompt


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


def test_run_component_unit_check_emits_progress_events():
    events = []

    def mock_llm(system: str, user: str, model: str) -> str:
        del system, user, model
        return json.dumps({"status": "pass", "findings": []})

    result = llm_unit_check.run_component_unit_check(
        source=SOURCE,
        component="ccgt",
        models=["m1", "m2"],
        llm_callable=mock_llm,
        progress_callback=events.append,
    )
    assert result.status == "certified"
    assert [e["event"] for e in events] == [
        "model_start",
        "model_done",
        "model_start",
        "model_done",
    ]


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

    def fake_run_component_unit_check(
        source: dict,
        component: str,
        models=None,
        progress_callback=None,
    ):
        del models
        if progress_callback:
            progress_callback(
                {
                    "event": "model_start",
                    "component": component,
                    "model": "m1",
                    "index": 1,
                    "total_models": 2,
                }
            )
            progress_callback(
                {
                    "event": "model_done",
                    "component": component,
                    "model": "m1",
                    "index": 1,
                    "total_models": 2,
                    "status": "pass",
                    "findings_count": 0,
                }
            )
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

    def fake_run_component_unit_check(
        source: dict,
        component: str,
        models=None,
        progress_callback=None,
    ):
        del models
        if progress_callback:
            progress_callback(
                {
                    "event": "model_start",
                    "component": component,
                    "model": "m1",
                    "index": 1,
                    "total_models": 2,
                }
            )
            progress_callback(
                {
                    "event": "model_done",
                    "component": component,
                    "model": "m1",
                    "index": 1,
                    "total_models": 2,
                    "status": "fail",
                    "findings_count": 1,
                }
            )
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


def test_cmd_llm_check_units_text_prints_fix_suggestions(
    tmp_path, monkeypatch, capsys
):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")

    def fake_run_component_unit_check(
        source: dict,
        component: str,
        models=None,
        progress_callback=None,
    ):
        del models
        if progress_callback:
            progress_callback(
                {
                    "event": "model_start",
                    "component": component,
                    "model": "m1",
                    "index": 1,
                    "total_models": 2,
                }
            )
            progress_callback(
                {
                    "event": "model_done",
                    "component": component,
                    "model": "m1",
                    "index": 1,
                    "total_models": 2,
                    "status": "fail",
                    "findings_count": 1,
                }
            )
        votes = [
            llm_unit_check.VoteResult(
                model="m1",
                status="fail",
                findings=[
                    {
                        "severity": "critical",
                        "message": (
                            "Mismatch between process activity and "
                            "commodity units."
                        ),
                        "suggestion": (
                            "Set activity_unit=PJ and recompute coefficients."
                        ),
                    }
                ],
            ),
            llm_unit_check.VoteResult(model="m2", status="pass", findings=[]),
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
        json=False,
        component=None,
        all=False,
        force=False,
        model=None,
        store=None,
    )
    exit_code = cli.cmd_llm_check_units(args)
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "[1/1] Checking ccgt" in out
    assert "Set activity_unit=PJ and recompute coefficients." in out
    assert "Summary:" in out
