"""PRD Acceptance Criteria A1-A8 — regression matrix.

Maps each acceptance criterion from
docs/prds/vedalang_toy_refactor_prd_updated.txt (Part 8) to explicit,
independently-runnable tests.  If any of these fail, the corresponding
PRD invariant has regressed.

Criteria:
  A1  All toy_* models compile under new rules.
  A2  No fuel-pathway roles remain.
  A3  No zero-input end_use supply processes (unless demand_measure).
  A4  Cases overlay replaces duplicate toy files where appropriate.
  A5  Diagnostics remain independent of solve.
  A6  SKILL.md exists and documents conventions.
  A7  LLM lint step produces structured assessment output.
  A8  Compiler enforces structural invariants.
"""

import json
from pathlib import Path

import pytest

from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang
from vedalang.compiler.compiler import (
    _detect_service_role_duplication,
    _normalize_commodities_for_new_syntax,
)
from vedalang.compiler.ir import build_roles
from vedalang.lint.llm_assessment import (
    AssessmentResult,
    parse_llm_response,
    run_llm_assessment,
)
from vedalang.lint.res_export import export_res_graph, res_graph_to_mermaid

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"
SKILL_PATH = PROJECT_ROOT / ".agents" / "skills" / "vedalang-modeling-conventions" / "SKILL.md"

TOY_MODELS = sorted(EXAMPLES_DIR.glob("toy_*.veda.yaml"))

# Ensure the fixture list is non-empty so the parametrize never silently passes.
assert len(TOY_MODELS) >= 6, f"Expected ≥6 toy models, found {len(TOY_MODELS)}"


# ── A1: All toy_* models compile under new rules ─────────────────────────

class TestA1_AllToyModelsCompile:
    @pytest.mark.parametrize("model_path", TOY_MODELS, ids=lambda p: p.stem)
    def test_toy_model_compiles(self, model_path: Path):
        source = load_vedalang(model_path)
        tableir = compile_vedalang_to_tableir(source)
        assert "files" in tableir, f"{model_path.name} did not compile"


# ── A2: No fuel-pathway roles remain ─────────────────────────────────────

FUEL_PATHWAY_KEYWORDS = [
    "heat_from_gas", "heat_from_electricity", "heat_from_hydrogen",
    "haul_with_diesel", "haul_with_electricity", "haul_with_biodiesel",
    "convert_gas_to_industrial_heat", "convert_electricity_to_industrial_heat",
    "convert_petrol_to_mobility", "convert_electricity_to_mobility",
]


class TestA2_NoFuelPathwayRoles:
    @pytest.mark.parametrize("model_path", TOY_MODELS, ids=lambda p: p.stem)
    def test_no_fuel_pathway_roles(self, model_path: Path):
        source = load_vedalang(model_path)
        if "process_roles" not in source:
            pytest.skip("Legacy-syntax model (no process_roles)")
        role_ids = {role["id"] for role in source["process_roles"]}
        for bad in FUEL_PATHWAY_KEYWORDS:
            assert bad not in role_ids, (
                f"{model_path.name}: prohibited fuel-pathway role '{bad}' present"
            )

    @pytest.mark.parametrize("model_path", TOY_MODELS, ids=lambda p: p.stem)
    def test_compiler_rejects_duplicate_service_roles(self, model_path: Path):
        """If we were to re-add a fuel-pathway role, the compiler would catch it."""
        source = load_vedalang(model_path)
        if "process_roles" not in source:
            pytest.skip("Legacy-syntax model")
        commodities = _normalize_commodities_for_new_syntax(source["model"]["commodities"])
        roles = build_roles(source, commodities)
        errors, _warnings = _detect_service_role_duplication(roles, commodities)
        assert len(errors) == 0, (
            f"{model_path.name}: duplicate service-role errors:\n"
            + "\n".join(e["message"] for e in errors)
        )


# ── A3: No zero-input end_use supply (unless demand_measure) ─────────────

class TestA3_NoZeroInputEndUse:
    @pytest.mark.parametrize("model_path", TOY_MODELS, ids=lambda p: p.stem)
    def test_no_zero_input_end_use_without_demand_measure(self, model_path: Path):
        source = load_vedalang(model_path)
        if "process_roles" not in source:
            pytest.skip("Legacy-syntax model")
        roles = {r["id"]: r for r in source["process_roles"]}
        variants = source.get("process_variants", [])
        for role_id, role in roles.items():
            if role.get("stage") != "end_use":
                continue
            role_inputs = role.get("inputs", [])
            variant_inputs_exist = any(
                v.get("inputs") for v in variants if v.get("role") == role_id
            )
            if role_inputs or variant_inputs_exist:
                continue
            # Zero-input end_use: every variant must be demand_measure
            for v in variants:
                if v.get("role") != role_id:
                    continue
                assert v.get("kind") == "demand_measure", (
                    f"{model_path.name}: end_use role '{role_id}' variant "
                    f"'{v['id']}' has no inputs and is not kind=demand_measure"
                )

    def test_compiler_hard_error_on_zero_input_end_use(self):
        """Compiler raises E_END_USE_PHYSICAL_INPUT for violations."""
        source = {
            "model": {
                "name": "A3_Test",
                "regions": ["R1"],
                "milestone_years": [2020, 2030],
                "commodities": [
                    {"id": "electricity", "type": "energy"},
                    {"id": "space_heat", "type": "service"},
                ],
                "constraints": [],
            },
            "segments": {"sectors": ["RES"]},
            "process_roles": [
                {
                    "id": "provide_space_heat",
                    "stage": "end_use",
                    "inputs": [],
                    "outputs": [{"commodity": "space_heat"}],
                },
            ],
            "process_variants": [
                {"id": "fake_device", "role": "provide_space_heat", "efficiency": 1.0},
            ],
            "availability": [
                {"variant": "fake_device", "regions": ["R1"], "sectors": ["RES"]},
            ],
            "demands": [
                {"commodity": "space_heat", "region": "R1", "sector": "RES",
                 "values": {"2020": 100}},
            ],
        }
        with pytest.raises(Exception, match=r"\[E_END_USE_PHYSICAL_INPUT\]"):
            compile_vedalang_to_tableir(source)


# ── A4: Cases overlay replaces duplicate toy files ────────────────────────

class TestA4_CasesOverlay:
    def test_toy_resources_single_file_with_three_cases(self):
        source = load_vedalang(EXAMPLES_DIR / "toy_resources.veda.yaml")
        cases = source["model"]["cases"]
        case_names = sorted(c["name"] for c in cases)
        assert case_names == ["co2cap", "force_shift", "ref"]

    def test_toy_resources_compiles_to_tableir_with_cases(self):
        source = load_vedalang(EXAMPLES_DIR / "toy_resources.veda.yaml")
        tableir = compile_vedalang_to_tableir(source)
        assert "cases" in tableir
        compiled_names = sorted(c["name"] for c in tableir["cases"])
        assert compiled_names == ["co2cap", "force_shift", "ref"]

    def test_no_duplicate_toy_resources_files(self):
        """Exactly one toy_resources file, not co2cap/forceshift splits."""
        resource_files = list(EXAMPLES_DIR.glob("toy_resources*.veda.yaml"))
        assert len(resource_files) == 1


# ── A5: Diagnostics independent of solve ──────────────────────────────────

class TestA5_DiagnosticsIndependentOfSolve:
    def test_res_export_is_deterministic_without_solver(self):
        source = load_vedalang(EXAMPLES_DIR / "toy_buildings.veda.yaml")
        g1 = export_res_graph(source)
        g2 = export_res_graph(source)
        assert json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True)

    def test_mermaid_export_is_deterministic_without_solver(self):
        source = load_vedalang(EXAMPLES_DIR / "toy_buildings.veda.yaml")
        g = export_res_graph(source)
        m1 = res_graph_to_mermaid(g)
        m2 = res_graph_to_mermaid(g)
        assert m1 == m2

    def test_diagnostics_metadata_flag_present(self):
        source = load_vedalang(EXAMPLES_DIR / "toy_buildings.veda.yaml")
        tableir = compile_vedalang_to_tableir(source)
        diag_export = tableir.get("diagnostics_export", {})
        assert diag_export.get("contract") == "diagnostics_are_solve_independent"


# ── A6: SKILL.md exists and documents conventions ─────────────────────────

class TestA6_SkillMDExists:
    def test_skill_md_file_exists(self):
        assert SKILL_PATH.exists(), f"SKILL.md not found at {SKILL_PATH}"

    def test_skill_md_documents_core_principles(self):
        content = SKILL_PATH.read_text()
        for phrase in [
            "service",
            "variant",
            "physical",
            "stage",
            "commodity",
            "demand_measure",
            "cases",
            "diagnostics",
        ]:
            assert phrase.lower() in content.lower(), (
                f"SKILL.md missing expected topic: '{phrase}'"
            )

    def test_skill_md_has_frontmatter(self):
        content = SKILL_PATH.read_text()
        assert content.startswith("---"), "SKILL.md should have YAML frontmatter"


# ── A7: LLM lint produces structured assessment ──────────────────────────

class TestA7_LLMLintStructuredAssessment:
    def test_parse_clean_response(self):
        result = parse_llm_response('{"findings": []}')
        assert isinstance(result, AssessmentResult)
        assert len(result.findings) == 0
        assert not result.has_critical

    def test_parse_multi_severity_findings(self):
        raw = json.dumps({
            "findings": [
                {"severity": "critical", "category": "fuel_pathway_roles",
                 "message": "Duplicate roles detected"},
                {"severity": "warning", "category": "zero_input_device",
                 "message": "Zero-input device at end_use"},
                {"severity": "suggestion", "category": "other",
                 "message": "Consider explicit types"},
            ]
        })
        result = parse_llm_response(raw)
        assert result.critical_count == 1
        assert result.warning_count == 1
        assert result.suggestion_count == 1

    def test_to_dict_has_structured_schema(self):
        raw = json.dumps({
            "findings": [
                {"severity": "critical", "category": "fuel_pathway_roles",
                 "message": "test"},
            ]
        })
        result = parse_llm_response(raw)
        d = result.to_dict()
        assert "summary" in d
        assert "findings" in d
        assert d["summary"]["total"] == 1
        finding = d["findings"][0]
        assert finding["code"].startswith("LLM_")
        assert finding["severity"] == "critical"

    def test_run_llm_assessment_with_mock(self):
        mock_response = '{"findings": []}'

        def mock_llm(system, user):
            return mock_response

        source = load_vedalang(EXAMPLES_DIR / "toy_buildings.veda.yaml")
        result = run_llm_assessment(source, llm_callable=mock_llm)
        assert isinstance(result, AssessmentResult)
        assert not result.has_critical


# ── A8: Compiler enforces structural invariants ──────────────────────────

class TestA8_CompilerStructuralInvariants:
    def _base_source(self):
        return {
            "model": {
                "name": "A8_Test",
                "regions": ["R1"],
                "milestone_years": [2020, 2030],
                "commodities": [
                    {"id": "electricity", "type": "energy"},
                    {"id": "space_heat", "type": "service"},
                    {"id": "co2", "type": "emission"},
                ],
                "constraints": [
                    {"name": "CO2_CAP", "type": "emission_cap",
                     "commodity": "co2", "limit": 100, "limtype": "up"},
                ],
            },
            "segments": {"sectors": ["RES"]},
            "process_roles": [
                {
                    "id": "provide_space_heat",
                    "stage": "end_use",
                    "inputs": [{"commodity": "electricity"}],
                    "outputs": [{"commodity": "space_heat"}],
                },
            ],
            "process_variants": [
                {"id": "heat_pump", "role": "provide_space_heat",
                 "kind": "device", "efficiency": 0.95},
            ],
            "availability": [
                {"variant": "heat_pump", "regions": ["R1"], "sectors": ["RES"]},
            ],
            "demands": [
                {"commodity": "space_heat", "region": "R1", "sector": "RES",
                 "values": {"2020": 100}},
            ],
        }

    def test_e_stage_enum(self):
        src = self._base_source()
        src["process_roles"][0]["stage"] = "distribution"
        with pytest.raises(Exception, match=r"\[E_STAGE_ENUM\]"):
            compile_vedalang_to_tableir(src, validate=False)

    def test_e_commodity_type_enum(self):
        src = self._base_source()
        src["model"]["commodities"][0]["type"] = "bogus"
        with pytest.raises(Exception, match=r"\[E_COMMODITY_TYPE_ENUM\]"):
            compile_vedalang_to_tableir(src, validate=False)

    def test_e_demand_commodity_type(self):
        src = self._base_source()
        src["demands"][0]["commodity"] = "electricity"
        with pytest.raises(Exception, match=r"\[E_DEMAND_COMMODITY_TYPE\]"):
            compile_vedalang_to_tableir(src)

    def test_e_emission_commodity_type(self):
        src = self._base_source()
        src["model"]["constraints"][0]["commodity"] = "electricity"
        with pytest.raises(Exception, match=r"\[E_EMISSION_COMMODITY_TYPE\]"):
            compile_vedalang_to_tableir(src)

    def test_e_role_primary_output(self):
        src = self._base_source()
        src["process_roles"][0]["outputs"] = [
            {"commodity": "space_heat"},
            {"commodity": "electricity"},
        ]
        with pytest.raises(Exception, match=r"\[E_ROLE_PRIMARY_OUTPUT\]"):
            compile_vedalang_to_tableir(src)

    def test_e1_duplicate_service_roles(self):
        src = self._base_source()
        src["model"]["commodities"].append({"id": "gas", "type": "fuel"})
        src["process_roles"].append(
            {"id": "heat_from_gas", "stage": "end_use",
             "inputs": [{"commodity": "gas"}],
             "outputs": [{"commodity": "space_heat"}]},
        )
        src["process_variants"].append(
            {"id": "gas_heater", "role": "heat_from_gas",
             "kind": "device", "efficiency": 0.9},
        )
        src["availability"].append(
            {"variant": "gas_heater", "regions": ["R1"], "sectors": ["RES"]},
        )
        with pytest.raises(Exception, match=r"\[E1_DUPLICATE_SERVICE_ROLES\]"):
            compile_vedalang_to_tableir(src)

    def test_e_end_use_physical_input(self):
        src = self._base_source()
        src["process_roles"][0]["inputs"] = []
        src["process_variants"][0].pop("kind", None)
        with pytest.raises(Exception, match=r"\[E_END_USE_PHYSICAL_INPUT\]"):
            compile_vedalang_to_tableir(src)
