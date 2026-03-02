"""Tests for naming convention lint rules."""

from pathlib import Path

import yaml

from vedalang.identity.lint_rules import (
    N001_CommodityIDGrammar,
    N002_ProcessIDGrammar,
    N003_UnknownTechnologyCode,
    N004_UnknownRoleCode,
    N005_GeoNotInRegions,
    N006_EUSRequiresSegment,
    N007_EUSMustOutputService,
    N008_RoleSankeyMismatch,
    N009_ServiceInTradeLink,
    N010_ContextKindMismatch,
    lint_naming_conventions,
)


def make_model(**kwargs) -> dict:
    """Helper to create a model dict with defaults."""
    model_data = {
        "regions": ["NEM_EAST"],
        "commodities": [],
        "processes": [],
        "trade_links": [],
    }
    model_data.update(kwargs)
    return {"model": model_data}


class TestN001_CommodityIDGrammar:
    """Tests for commodity ID grammar rule."""

    def test_valid_tradable_commodity(self):
        model = make_model(
            commodities=[
                {
                    "name": "secondary:electricity",
                    "type": "energy",
                    "kind": "TRADABLE",
                }
            ]
        )
        rule = N001_CommodityIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_valid_tradable_commodity_with_id_field(self):
        model = make_model(
            commodities=[{"id": "secondary:electricity", "type": "energy"}]
        )
        rule = N001_CommodityIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_valid_service_commodity(self):
        model = make_model(
            commodities=[
                {
                    "name": "service:space_heat",
                    "type": "service",
                }
            ]
        )
        rule = N001_CommodityIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_valid_emission_commodity(self):
        model = make_model(
            commodities=[{"name": "emission:co2", "type": "emission"}]
        )
        rule = N001_CommodityIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_legacy_prefix_triggers_n001(self):
        model = make_model(
            commodities=[{"name": "C:ELC", "type": "energy"}]
        )
        rule = N001_CommodityIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N001"
        assert diagnostics[0].severity == "error"
        assert "Legacy commodity prefix" in diagnostics[0].message

    def test_legacy_prefix_with_id_field_points_to_id_path(self):
        model = make_model(
            commodities=[{"id": "E:CO2", "type": "emission"}]
        )
        rule = N001_CommodityIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N001"
        assert diagnostics[0].path == "model.commodities[0].id"

    def test_namespace_type_mismatch_triggers_n001(self):
        model = make_model(
            commodities=[{"name": "service:space_heat", "type": "energy"}]
        )
        rule = N001_CommodityIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N001"


class TestN002_ProcessIDGrammar:
    """Tests for process ID grammar rule."""

    def test_valid_process_id(self):
        model = make_model(
            processes=[{"name": "P:CCG:GEN:NEM_EAST", "outputs": []}]
        )
        rule = N002_ProcessIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_invalid_process_id_triggers_n002(self):
        model = make_model(processes=[{"name": "P:CCG", "outputs": []}])
        rule = N002_ProcessIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N002"
        assert diagnostics[0].severity == "error"

    def test_non_p_prefixed_skipped(self):
        model = make_model(processes=[{"name": "PP_CCGT", "outputs": []}])
        rule = N002_ProcessIDGrammar()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0


class TestN003_UnknownTechnologyCode:
    """Tests for unknown technology code rule."""

    def test_known_tech_code_passes(self):
        model = make_model(
            processes=[{"name": "P:CCG:GEN:NEM_EAST", "outputs": []}]
        )
        rule = N003_UnknownTechnologyCode()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_unknown_tech_code_triggers_n003(self):
        model = make_model(
            processes=[{"name": "P:XYZ:GEN:NEM_EAST", "outputs": []}]
        )
        rule = N003_UnknownTechnologyCode()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N003"
        assert "Unknown technology code: XYZ" in diagnostics[0].message


class TestN004_UnknownRoleCode:
    """Tests for unknown role code rule."""

    def test_valid_role_passes(self):
        model = make_model(
            processes=[{"name": "P:CCG:GEN:NEM_EAST", "outputs": []}]
        )
        rule = N004_UnknownRoleCode()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_unknown_role_triggers_n004(self):
        model = make_model(
            processes=[{"name": "P:CCG:XXX:NEM_EAST", "outputs": []}]
        )
        rule = N004_UnknownRoleCode()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N004"
        assert "Unknown role code: XXX" in diagnostics[0].message


class TestN005_GeoNotInRegions:
    """Tests for geo not in regions rule."""

    def test_valid_geo_passes(self):
        model = make_model(
            regions=["NEM_EAST", "NSW"],
            processes=[{"name": "P:CCG:GEN:NEM_EAST", "outputs": []}],
        )
        rule = N005_GeoNotInRegions()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_unknown_geo_triggers_n005(self):
        model = make_model(
            regions=["NEM_EAST"],
            processes=[{"name": "P:CCG:GEN:NSW", "outputs": []}],
        )
        rule = N005_GeoNotInRegions()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N005"
        assert "GEO 'NSW' not in model regions" in diagnostics[0].message


class TestN006_EUSRequiresSegment:
    """Tests for EUS requires segment rule."""

    def test_eus_with_segment_passes(self):
        model = make_model(
            processes=[{"name": "P:DEM:EUS:NEM_EAST:RES.ALL", "outputs": []}]
        )
        rule = N006_EUSRequiresSegment()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_eus_without_segment_triggers_n006(self):
        model = make_model(
            processes=[{"name": "P:DEM:EUS:NEM_EAST", "outputs": []}]
        )
        rule = N006_EUSRequiresSegment()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N006"


class TestN007_EUSMustOutputService:
    """Tests for EUS must output service rule."""

    def test_eus_with_service_output_passes(self):
        model = make_model(
            commodities=[{"name": "RSD", "type": "demand"}],
            processes=[
                {
                    "name": "P:DEM:EUS:NEM_EAST:RES.ALL",
                    "outputs": [{"commodity": "RSD"}],
                }
            ],
        )
        rule = N007_EUSMustOutputService()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_eus_without_service_output_triggers_n007(self):
        model = make_model(
            commodities=[{"name": "ELC", "type": "energy"}],
            processes=[
                {
                    "name": "P:DEM:EUS:NEM_EAST:RES.ALL",
                    "outputs": [{"commodity": "ELC"}],
                }
            ],
        )
        rule = N007_EUSMustOutputService()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N007"


class TestN008_RoleSankeyMismatch:
    """Tests for role sankey mismatch rule."""

    def test_matching_role_sankey_passes(self):
        model = make_model(
            processes=[
                {"name": "P:CCG:GEN:NEM_EAST", "sankey_stage": "GEN", "outputs": []}
            ]
        )
        rule = N008_RoleSankeyMismatch()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_mismatched_role_sankey_triggers_n008(self):
        model = make_model(
            processes=[
                {"name": "P:CCG:GEN:NEM_EAST", "sankey_stage": "END", "outputs": []}
            ]
        )
        rule = N008_RoleSankeyMismatch()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N008"
        assert diagnostics[0].severity == "warning"


class TestN009_ServiceInTradeLink:
    """Tests for service in trade link rule."""

    def test_tradable_in_trade_link_passes(self):
        model = make_model(
            commodities=[{"name": "ELC", "type": "energy"}],
            trade_links=[
                {"origin": "NEM_EAST", "destination": "NSW", "commodity": "ELC"}
            ],
        )
        rule = N009_ServiceInTradeLink()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_service_in_trade_link_triggers_n009(self):
        model = make_model(
            commodities=[{"name": "RSD", "type": "demand"}],
            trade_links=[
                {"origin": "NEM_EAST", "destination": "NSW", "commodity": "RSD"}
            ],
        )
        rule = N009_ServiceInTradeLink()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N009"
        assert "SERVICE commodity 'RSD'" in diagnostics[0].message


class TestN010_ContextKindMismatch:
    """Tests for context kind mismatch rule."""

    def test_tradable_without_context_passes(self):
        model = make_model(
            commodities=[{"name": "ELC", "type": "energy", "kind": "TRADABLE"}]
        )
        rule = N010_ContextKindMismatch()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 0

    def test_tradable_with_context_triggers_n010(self):
        model = make_model(
            commodities=[
                {
                    "name": "ELC",
                    "type": "energy",
                    "kind": "TRADABLE",
                    "context": "RES.ALL",
                }
            ]
        )
        rule = N010_ContextKindMismatch()
        diagnostics = rule.check(model)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N010"


class TestLintNamingConventions:
    """Integration tests for lint_naming_conventions function."""

    def test_valid_model_passes_all_rules(self):
        model = make_model(
            regions=["NEM_EAST"],
            commodities=[
                {"name": "secondary:electricity", "type": "energy"},
                {"name": "service:residential_service", "type": "service"},
            ],
            processes=[
                {
                    "name": "P:CCG:GEN:NEM_EAST",
                    "outputs": [{"commodity": "secondary:electricity"}],
                },
                {
                    "name": "P:DEM:EUS:NEM_EAST:RES.ALL",
                    "outputs": [{"commodity": "service:residential_service"}],
                },
            ],
        )
        diagnostics = lint_naming_conventions(model)
        assert len(diagnostics) == 0

    def test_multiple_errors_sorted_by_severity(self):
        model = make_model(
            regions=["NEM_EAST"],
            commodities=[
                {"name": "service:elc", "type": "energy"},  # N001 error
            ],
            processes=[
                {
                    "name": "P:CCG:GEN:NEM_EAST",
                    "sankey_stage": "END",
                    "outputs": [],
                },
            ],
        )
        diagnostics = lint_naming_conventions(model)
        assert len(diagnostics) == 2
        assert diagnostics[0].severity == "error"
        assert diagnostics[1].severity == "warning"

    def test_empty_model_passes(self):
        model = make_model()
        diagnostics = lint_naming_conventions(model)
        assert len(diagnostics) == 0

    def test_toy_agriculture_namespaced_ids_do_not_trigger_n001(self):
        source = yaml.safe_load(
            (
                Path(__file__).resolve().parents[1]
                / "vedalang"
                / "examples"
                / "toy_sectors/toy_agriculture.veda.yaml"
            ).read_text(encoding="utf-8")
        )
        diagnostics = lint_naming_conventions(source)
        assert not any(diag.code == "N001" for diag in diagnostics)
