"""Tests for v0.3 naming convention lint rules."""

from vedalang.identity.lint_rules import (
    N001_CommodityIDGrammar,
    N011_SnakeCasePreferred,
    lint_naming_conventions,
)


def make_source(**overrides) -> dict:
    source = {
        "dsl_version": "0.3",
        "commodities": [],
        "technologies": [],
        "technology_roles": [],
        "sites": [],
        "facilities": [],
        "runs": [],
    }
    source.update(overrides)
    return source


class TestN001CommodityIDGrammar:
    def test_valid_commodity_passes(self):
        source = make_source(
            commodities=[
                {
                    "id": "electricity",
                    "type": "energy",
                    "energy_form": "secondary",
                }
            ]
        )
        diagnostics = N001_CommodityIDGrammar().check(source)
        assert diagnostics == []

    def test_unsupported_prefix_triggers(self):
        source = make_source(
            commodities=[
                {
                    "id": "fuel:natural_gas",
                    "type": "energy",
                    "energy_form": "primary",
                }
            ]
        )
        diagnostics = N001_CommodityIDGrammar().check(source)
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "N001"
        assert "lowered namespace prefix" in diagnostics[0].message


class TestN011SnakeCasePreferred:
    def test_warns_on_dashed_top_level_ids(self):
        source = make_source(
            technologies=[{"id": "heat-pump", "provides": "space_heat"}],
            technology_roles=[
                {
                    "id": "space-heat-supply",
                    "primary_service": "space_heat",
                    "technologies": ["heat-pump"],
                }
            ],
        )
        diagnostics = N011_SnakeCasePreferred().check(source)
        assert len(diagnostics) == 2
        assert all(d.code == "N011" for d in diagnostics)

    def test_ignores_snake_case_ids(self):
        source = make_source(
            technologies=[{"id": "heat_pump", "provides": "space_heat"}],
            technology_roles=[
                {
                    "id": "space_heat_supply",
                    "primary_service": "space_heat",
                    "technologies": ["heat_pump"],
                }
            ],
        )
        diagnostics = N011_SnakeCasePreferred().check(source)
        assert diagnostics == []


class TestLintNamingConventions:
    def test_lints_public_source(self):
        source = make_source(
            commodities=[{"id": "fuel:natural_gas", "kind": "primary"}],
            technologies=[{"id": "heat-pump", "provides": "space_heat"}],
        )
        diagnostics = lint_naming_conventions(source)
        assert len(diagnostics) == 2
        assert [d.code for d in diagnostics] == ["N001", "N011"]

    def test_ignores_non_public_source(self):
        diagnostics = lint_naming_conventions({"model": {"commodities": []}})
        assert diagnostics == []
