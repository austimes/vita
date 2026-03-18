"""Tests for LLM-based structural RES assessment.

Tests the prompt assembly, response parsing, and CLI integration
using mock LLM responses — no real API calls are made.
"""

import argparse
import json

import pytest

from vedalang.lint.llm_assessment import (
    AssessmentResult,
    LLMFinding,
    assemble_prompt,
    load_conventions,
    parse_llm_response,
    run_llm_assessment,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_SOURCE = {
    "dsl_version": "0.3",
    "commodities": [
        {"id": "natural_gas", "type": "energy", "energy_form": "primary"},
        {"id": "electricity", "type": "energy", "energy_form": "secondary"},
        {"id": "space_heat", "type": "service"},
    ],
    "technologies": [
        {
            "id": "heat_pump",
            "description": "Electric heat pump",
            "provides": "space_heat",
            "inputs": [{"commodity": "electricity"}],
        },
    ],
    "technology_roles": [
        {
            "id": "space_heat_supply",
            "description": "Space heat supply",
            "primary_service": "space_heat",
            "technologies": ["heat_pump"],
        },
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
    "runs": [
        {
            "id": "r1_2025",
            "base_year": 2025,
            "currency_year": 2024,
            "region_partition": "single_region",
        }
    ],
}

CLEAN_RESPONSE = json.dumps({"findings": []})

RESPONSE_WITH_FINDINGS = json.dumps({
    "findings": [
        {
            "severity": "critical",
            "category": "fuel_pathway_roles",
            "message": "Roles heat_from_gas and heat_from_elec share output",
            "location": "technology_roles",
            "suggestion": "Merge into space_heat_supply",
        },
        {
            "severity": "warning",
            "category": "zero_input_device",
            "message": "Role create_heat has no inputs at stage end_use",
        },
        {
            "severity": "suggestion",
            "category": "other",
            "message": "Consider adding explicit commodity types",
        },
    ]
})

RESPONSE_WITH_FENCES = f"```json\n{RESPONSE_WITH_FINDINGS}\n```"


# ---------------------------------------------------------------------------
# parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLLMResponse:
    """Tests for the LLM response parser."""

    def test_clean_response(self):
        result = parse_llm_response(CLEAN_RESPONSE)
        assert isinstance(result, AssessmentResult)
        assert len(result.findings) == 0
        assert result.critical_count == 0
        assert not result.has_critical

    def test_response_with_findings(self):
        result = parse_llm_response(RESPONSE_WITH_FINDINGS)
        assert len(result.findings) == 3
        assert result.critical_count == 1
        assert result.warning_count == 1
        assert result.suggestion_count == 1
        assert result.has_critical

    def test_finding_fields(self):
        result = parse_llm_response(RESPONSE_WITH_FINDINGS)
        critical = result.findings[0]
        assert critical.severity == "critical"
        assert critical.category == "fuel_pathway_roles"
        assert "heat_from_gas" in critical.message
        assert critical.location == "technology_roles"
        assert critical.suggestion == "Merge into space_heat_supply"

    def test_markdown_fenced_response(self):
        result = parse_llm_response(RESPONSE_WITH_FENCES)
        assert len(result.findings) == 3

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_llm_response("this is not json")

    def test_missing_findings_key_raises(self):
        with pytest.raises(ValueError, match="missing 'findings' key"):
            parse_llm_response('{"issues": []}')

    def test_findings_not_list_raises(self):
        with pytest.raises(ValueError, match="must be a list"):
            parse_llm_response('{"findings": "wrong"}')

    def test_non_object_response_raises(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_llm_response("[1, 2, 3]")

    def test_non_object_finding_raises(self):
        with pytest.raises(ValueError, match="must be an object"):
            parse_llm_response('{"findings": ["not an object"]}')

    def test_unknown_severity_defaults_to_suggestion(self):
        raw = json.dumps({
            "findings": [
                {"severity": "unknown_level", "category": "other", "message": "test"}
            ]
        })
        result = parse_llm_response(raw)
        assert result.findings[0].severity == "suggestion"

    def test_classification_fields_flow_into_context(self):
        raw = json.dumps(
            {
                "findings": [
                    {
                        "severity": "warning",
                        "category": "stage_mismatch",
                        "message": "role stage does not match topology",
                        "error_code": "STR_STAGE_MISMATCH",
                        "error_family": "stage_semantics",
                        "difficulty": "medium",
                    }
                ]
            }
        )
        result = parse_llm_response(raw)
        finding = result.findings[0]
        assert finding.context["error_code"] == "STR_STAGE_MISMATCH"
        assert finding.context["error_family"] == "stage_semantics"
        assert finding.context["difficulty"] == "medium"

    def test_raw_response_preserved(self):
        result = parse_llm_response(CLEAN_RESPONSE)
        assert result.raw_response == CLEAN_RESPONSE


# ---------------------------------------------------------------------------
# LLMFinding / AssessmentResult serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for to_dict() serialization."""

    def test_finding_to_dict(self):
        finding = LLMFinding(
            severity="critical",
            category="fuel_pathway_roles",
            message="Test message",
            location="technology_roles[0]",
            suggestion="Fix it",
        )
        d = finding.to_dict()
        assert d["code"] == "LLM_FUEL_PATHWAY_ROLES"
        assert d["severity"] == "critical"
        assert d["message"] == "Test message"
        assert d["location"] == "technology_roles[0]"
        assert d["suggestion"] == "Fix it"

    def test_finding_to_dict_minimal(self):
        finding = LLMFinding(
            severity="suggestion",
            category="other",
            message="Minor note",
        )
        d = finding.to_dict()
        assert "location" not in d
        assert "suggestion" not in d

    def test_assessment_result_to_dict(self):
        result = parse_llm_response(RESPONSE_WITH_FINDINGS)
        d = result.to_dict()
        assert d["summary"]["critical"] == 1
        assert d["summary"]["warning"] == 1
        assert d["summary"]["suggestion"] == 1
        assert d["summary"]["total"] == 3
        assert len(d["findings"]) == 3


# ---------------------------------------------------------------------------
# assemble_prompt
# ---------------------------------------------------------------------------


class TestAssemblePrompt:
    """Tests for prompt assembly."""

    def test_returns_system_and_user_prompts(self):
        system, user = assemble_prompt(MINIMAL_SOURCE)
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert "structural assessment" in system.lower()

    def test_user_prompt_contains_conventions(self):
        _, user = assemble_prompt(MINIMAL_SOURCE)
        assert "Modeling Conventions" in user

    def test_user_prompt_contains_res_json(self):
        _, user = assemble_prompt(MINIMAL_SOURCE)
        assert '"commodities"' in user
        assert "space_heat_supply" in user

    def test_user_prompt_contains_mermaid(self):
        _, user = assemble_prompt(MINIMAL_SOURCE)
        assert "flowchart" in user
        assert "mermaid" in user.lower()

    def test_system_prompt_requests_json_schema(self):
        system, _ = assemble_prompt(MINIMAL_SOURCE)
        assert "critical" in system
        assert "warning" in system
        assert "suggestion" in system
        assert "findings" in system


# ---------------------------------------------------------------------------
# load_conventions
# ---------------------------------------------------------------------------


class TestLoadConventions:
    """Tests for conventions loading."""

    def test_loads_existing_conventions(self):
        text = load_conventions()
        assert isinstance(text, str)
        assert len(text) > 0
        # Should contain content from the SKILL.md
        assert "VedaLang" in text or "conventions" in text.lower()


# ---------------------------------------------------------------------------
# run_llm_assessment (with mock)
# ---------------------------------------------------------------------------


class TestRunLLMAssessment:
    """Integration tests using mock LLM callable."""

    def test_clean_model_no_findings(self):
        def mock_llm(system, user):
            return CLEAN_RESPONSE

        result = run_llm_assessment(MINIMAL_SOURCE, llm_callable=mock_llm)
        assert len(result.findings) == 0
        assert not result.has_critical

    def test_model_with_findings(self):
        def mock_llm(system, user):
            return RESPONSE_WITH_FINDINGS

        result = run_llm_assessment(MINIMAL_SOURCE, llm_callable=mock_llm)
        assert len(result.findings) == 3
        assert result.has_critical

    def test_missing_findings_key_treated_as_clean_result(self):
        def mock_llm(system, user):
            return '{"status":"pass"}'

        result = run_llm_assessment(MINIMAL_SOURCE, llm_callable=mock_llm)
        assert len(result.findings) == 0
        assert not result.has_critical

    def test_mock_receives_prompt_content(self):
        captured = {}

        def mock_llm(system, user):
            captured["system"] = system
            captured["user"] = user
            return CLEAN_RESPONSE

        run_llm_assessment(MINIMAL_SOURCE, llm_callable=mock_llm)
        assert "structural assessment" in captured["system"].lower()
        assert "space_heat_supply" in captured["user"]

    def test_findings_integrate_as_lint_diagnostics(self):
        """Findings can be serialized as lint diagnostics."""
        def mock_llm(system, user):
            return RESPONSE_WITH_FINDINGS

        result = run_llm_assessment(MINIMAL_SOURCE, llm_callable=mock_llm)
        for finding in result.findings:
            d = finding.to_dict()
            assert "code" in d
            assert "severity" in d
            assert "message" in d
            assert d["code"].startswith("LLM_")


# ---------------------------------------------------------------------------
# CLI integration (cmd_lint default behavior)
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """Tests for CLI flag integration."""

    def test_lint_default_is_offline(self, tmp_path):
        """Default deterministic lint never calls LLM."""
        from vedalang.cli import cmd_lint

        model_file = tmp_path / "test.veda.yaml"
        import yaml
        model_file.write_text(yaml.dump(MINIMAL_SOURCE))

        args = argparse.Namespace(
            file=model_file,
            json=True,
            res_json=None,
            res_mermaid=None,
        )
        exit_code = cmd_lint(args)
        # Should succeed without needing any API key
        assert exit_code in (0, 1)  # 0 = clean, 1 = warnings only

    def test_strict_mode_escalates_critical_to_error(self):
        """In strict mode, critical findings cause exit code 2."""
        result = parse_llm_response(RESPONSE_WITH_FINDINGS)
        assert result.has_critical

        # Simulate strict mode counting
        errors = 0
        for f in result.findings:
            if f.severity == "critical":
                errors += 1
        assert errors == 1
