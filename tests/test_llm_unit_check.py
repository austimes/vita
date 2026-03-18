"""Tests for advisory LLM unit/coefficient certification workflow."""

import argparse
import json

import yaml

from vedalang import cli
from vedalang.lint import llm_unit_check

SOURCE = {
    "dsl_version": "0.3",
    "commodities": [
        {"id": "natural_gas", "type": "energy", "energy_form": "primary"},
        {"id": "electricity", "type": "energy", "energy_form": "secondary"},
    ],
    "technologies": [
        {
            "id": "ccgt",
            "description": "Combined cycle gas turbine",
            "provides": "electricity",
            "inputs": [
                {
                    "commodity": "natural_gas",
                    "coefficient": 6.4,
                    "basis": "HHV",
                }
            ],
            "outputs": [{"commodity": "electricity", "coefficient": 1.0}],
            "performance": {"kind": "efficiency", "value": 0.55},
        }
    ],
    "technology_roles": [
        {
            "id": "electricity_supply",
            "description": "Electricity supply",
            "primary_service": "electricity",
            "technologies": ["ccgt"],
        }
    ],
    "spatial_layers": [
        {
            "id": "geo_demo",
            "kind": "polygon",
            "key": "region_id",
            "geometry_file": "data/regions.geojson",
        }
    ],
    "region_partitions": [
        {
            "id": "single_region",
            "layer": "geo_demo",
            "members": ["R1"],
            "mapping": {"kind": "constant", "value": "R1"},
        }
    ],
    "sites": [
        {
            "id": "hub",
            "location": {"point": {"lat": 0.0, "lon": 0.0}},
            "membership_overrides": {"region_partitions": {"single_region": "R1"}},
        }
    ],
    "facilities": [
        {
            "id": "grid_supply",
            "description": "Grid supply facility",
            "site": "hub",
            "technology_role": "electricity_supply",
            "stock": {
                "items": [
                    {
                        "technology": "ccgt",
                        "metric": "installed_capacity",
                        "observed": {"value": "1 GW", "year": 2025},
                    }
                ]
            },
        }
    ],
    "runs": [
        {
            "id": "r1_2025",
            "base_year": 2025,
            "currency_year": 2024,
            "region_partition": "single_region",
        }
    ],
}

SOURCE_WITH_MONETARY = {
    "dsl_version": "0.3",
    "commodities": [
        {"id": "electricity", "type": "energy", "energy_form": "secondary"}
    ],
    "technologies": [
        {
            "id": "grid_import",
            "description": "Grid electricity import",
            "provides": "electricity",
            "outputs": [{"commodity": "electricity"}],
            "variable_om": "6.944444 MAUD24/MWh",
        }
    ],
    "technology_roles": [
        {
            "id": "power_supply",
            "description": "Power supply",
            "primary_service": "electricity",
            "technologies": ["grid_import"],
        }
    ],
    "runs": [
        {
            "id": "r1_2025",
            "base_year": 2025,
            "currency_year": 2024,
            "region_partition": "single_region",
        }
    ],
    "spatial_layers": [
        {
            "id": "geo_demo",
            "kind": "polygon",
            "key": "region_id",
            "geometry_file": "data/regions.geojson",
        }
    ],
    "region_partitions": [
        {
            "id": "single_region",
            "layer": "geo_demo",
            "members": ["R1"],
            "mapping": {"kind": "constant", "value": "R1"},
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
    mutated["technologies"][0]["performance"]["value"] = 0.6
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
    raw = json.dumps(
        {
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
                        "natural_gas": "PJ",
                        "electricity": "TWh",
                    },
                    "observed_units": {
                        "activity_unit": "TWh",
                        "capacity_unit": "GW",
                    },
                    "model_expectation": "Thermal generator should use PJ activity.",
                }
            ],
        }
    )
    status, findings = llm_unit_check.parse_unit_check_response(raw)
    assert status == "needs_review"
    assert len(findings) == 1
    assert findings[0]["suggestion"]
    assert findings[0]["expected_process_units"]["activity_unit"] == "PJ"
    assert findings[0]["expected_commodity_units"]["electricity"] == "TWh"


def test_parse_unit_check_response_reads_classification_fields():
    raw = json.dumps(
        {
            "status": "needs_review",
            "findings": [
                {
                    "severity": "warning",
                    "message": "Variable O&M denominator should match activity unit.",
                    "error_code": "UNIT_VARIABLE_COST_DENOM_MISMATCH",
                    "error_family": "cost_denominator",
                    "difficulty": "easy",
                }
            ],
        }
    )
    status, findings = llm_unit_check.parse_unit_check_response(raw)
    assert status == "needs_review"
    assert findings[0]["error_code"] == "UNIT_VARIABLE_COST_DENOM_MISMATCH"
    assert findings[0]["error_family"] == "cost_denominator"
    assert findings[0]["difficulty"] == "easy"


def test_parse_unit_check_response_filters_speculative_unit_other():
    raw = json.dumps(
        {
            "status": "needs_review",
            "findings": [
                {
                    "severity": "warning",
                    "error_code": "UNIT_OTHER",
                    "error_family": "other",
                    "difficulty": "medium",
                    "message": "Possible HHV/LHV issue; consider sanity-checking.",
                }
            ],
        }
    )
    status, findings = llm_unit_check.parse_unit_check_response(raw)
    assert status == "needs_review"
    assert findings == []


def test_parse_unit_check_response_keeps_concrete_unit_other():
    raw = json.dumps(
        {
            "status": "needs_review",
            "findings": [
                {
                    "severity": "critical",
                    "error_code": "UNIT_OTHER",
                    "error_family": "other",
                    "difficulty": "hard",
                    "message": (
                        "Missing explicit coefficient linking electricity PJ "
                        "input to mobility Bvkm activity."
                    ),
                    "suggestion": "Add input coefficient in PJ/Bvkm on the technology.",
                }
            ],
        }
    )
    status, findings = llm_unit_check.parse_unit_check_response(raw)
    assert status == "needs_review"
    assert len(findings) == 1
    assert findings[0]["error_code"] == "UNIT_OTHER"


def test_assemble_unit_prompt_includes_unit_enums_and_policy():
    system_prompt, user_prompt = llm_unit_check.assemble_unit_prompt(SOURCE, "ccgt")
    assert "status" in system_prompt
    assert "unit checks apply to v0.3 `technologies`" in system_prompt
    assert "Allowed unit enums from schema" in user_prompt
    assert "investment_cost -> stock or capacity denominator" in user_prompt
    assert "Model unit policy" in user_prompt
    assert "energy_unit" in user_prompt


def test_assemble_unit_prompt_includes_monetary_literal_guidance():
    system_prompt, user_prompt = llm_unit_check.assemble_unit_prompt(
        SOURCE_WITH_MONETARY,
        "grid_import",
    )
    assert "currency-year literals" in system_prompt
    assert "Monetary literal syntax and policy" in user_prompt
    assert "MAUD24" in user_prompt
    assert "cost_rate_literal_pattern" in user_prompt
    assert "Model monetary policy" in user_prompt
    assert '"currency_years": [' in user_prompt
    assert '"basis_policy": "explicit_at_flow_site"' in user_prompt


def test_run_component_unit_check_needs_review_on_split_votes():
    def mock_llm(system: str, user: str, model: str) -> str:
        del system, user
        if model == "m1":
            return json.dumps({"status": "pass", "findings": []})
        return json.dumps(
            {
                "status": "fail",
                "findings": [{"severity": "critical", "message": "bad conversion"}],
            }
        )

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


def test_run_component_unit_check_applies_default_max_output_tokens(monkeypatch):
    captured: dict = {}

    class FakeTelemetry:
        latency_sec = 0.1
        input_tokens = 1
        output_tokens = 1
        reasoning_tokens = 1
        reasoning_effort = "low"

    class FakeCall:
        output_text = json.dumps({"status": "pass", "findings": []})
        telemetry = FakeTelemetry()

    def fake_call_openai_json(**kwargs):
        captured.update(kwargs)
        return FakeCall()

    monkeypatch.setattr(llm_unit_check, "call_openai_json", fake_call_openai_json)

    result = llm_unit_check.run_component_unit_check(
        source=SOURCE,
        component="ccgt",
        models=["gpt-5-mini"],
        reasoning_effort="low",
    )
    assert result.status == "certified"
    assert (
        captured["max_output_tokens"] == llm_unit_check.DEFAULT_MAX_OUTPUT_TOKENS
    )


def test_update_store_with_result_persists_component_record():
    store = {"version": 1, "components": {}}
    result = _certified_result(SOURCE, "ccgt")
    llm_unit_check.update_store_with_result(store, result)
    rec = store["components"]["ccgt"]
    assert rec["status"] == "certified"
    assert rec["quorum"] == "2/2"
    assert rec["fingerprint"].startswith("sha256:")


def test_cmd_llm_lint_units_json_success(tmp_path, monkeypatch, capsys):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")
    store_file = tmp_path / "checks.json"

    def fake_run_component_unit_check(
        source: dict,
        component: str,
        models=None,
        progress_callback=None,
        reasoning_effort="medium",
        prompt_version="v1",
        timeout_sec=None,
    ):
        del models, reasoning_effort, prompt_version, timeout_sec
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
    args.category = ["units"]
    args.advisory = False
    exit_code = cli.cmd_llm_lint(args)
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert out["success"] is True
    assert "llm.units.component_quorum" in out["summary"]["checks_run"]
    assert len(out["unit_results"]) == 1
    assert out["unit_results"][0]["status"] == "certified"
    assert store_file.exists()


def test_cmd_llm_lint_units_needs_review_exit_code(tmp_path, monkeypatch, capsys):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")

    def fake_run_component_unit_check(
        source: dict,
        component: str,
        models=None,
        progress_callback=None,
        reasoning_effort="medium",
        prompt_version="v1",
        timeout_sec=None,
    ):
        del models, reasoning_effort, prompt_version, timeout_sec
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
    args.category = ["units"]
    args.advisory = False
    exit_code = cli.cmd_llm_lint(args)
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert out["success"] is False
    assert out["critical"] >= 1


def test_cmd_llm_lint_units_unknown_component_returns_error(tmp_path, capsys):
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
    args.category = ["units"]
    args.advisory = False
    exit_code = cli.cmd_llm_lint(args)
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert out["success"] is False
    messages = [d["message"] for d in out["diagnostics"]]
    assert any("Unknown component" in m for m in messages)


def test_cmd_llm_lint_units_text_prints_fix_suggestions(tmp_path, monkeypatch, capsys):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")

    def fake_run_component_unit_check(
        source: dict,
        component: str,
        models=None,
        progress_callback=None,
        reasoning_effort="medium",
        prompt_version="v1",
        timeout_sec=None,
    ):
        del models, reasoning_effort, prompt_version, timeout_sec
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
                            "Mismatch between process activity and commodity units."
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
    args.category = ["units"]
    args.advisory = False
    exit_code = cli.cmd_llm_lint(args)
    out = capsys.readouterr().out

    assert exit_code == 2
    assert "Set activity_unit=PJ and recompute coefficients." in out
    assert "Summary:" in out


def test_cmd_llm_lint_units_propagates_runtime_flags(tmp_path, monkeypatch, capsys):
    model_file = tmp_path / "test.veda.yaml"
    model_file.write_text(yaml.safe_dump(SOURCE), encoding="utf-8")

    captured: dict = {}

    def fake_run_component_unit_check(
        source: dict,
        component: str,
        models=None,
        progress_callback=None,
        reasoning_effort="medium",
        prompt_version="v1",
        timeout_sec=None,
    ):
        del progress_callback
        captured["component"] = component
        captured["models"] = models
        captured["reasoning_effort"] = reasoning_effort
        captured["prompt_version"] = prompt_version
        captured["timeout_sec"] = timeout_sec
        return _certified_result(source, component)

    monkeypatch.setattr(
        llm_unit_check,
        "run_component_unit_check",
        fake_run_component_unit_check,
    )

    args = argparse.Namespace(
        file=model_file,
        json=True,
        component=["ccgt"],
        all=False,
        force=False,
        model=["gpt-5-mini"],
        store=None,
        reasoning_effort="low",
        prompt_version="v1",
        request_timeout_sec=33,
    )
    args.category = ["units"]
    args.advisory = False
    exit_code = cli.cmd_llm_lint(args)
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert out["runtime"]["reasoning_effort"] == "low"
    assert out["runtime"]["prompt_version"] == "v1"
    assert out["runtime"]["request_timeout_sec"] == 33
    assert captured["models"] == ["gpt-5-mini"]
    assert captured["reasoning_effort"] == "low"
    assert captured["prompt_version"] == "v1"
    assert captured["timeout_sec"] == 33
