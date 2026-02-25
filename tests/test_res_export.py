"""Snapshot tests for RES graph export (vedalang-0pt.5).

Verifies deterministic JSON and Mermaid output from the lint-phase
RES graph export.
"""

import json
import subprocess
from pathlib import Path

import pytest

from vedalang.compiler.compiler import load_vedalang
from vedalang.lint.res_export import export_res_graph, res_graph_to_mermaid

EXAMPLES_DIR = Path(__file__).parent.parent / "vedalang" / "examples"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def toy_buildings_source():
    return load_vedalang(EXAMPLES_DIR / "toy_buildings.veda.yaml")


@pytest.fixture
def toy_buildings_graph(toy_buildings_source):
    return export_res_graph(toy_buildings_source)


@pytest.fixture
def toy_electricity_source():
    return load_vedalang(EXAMPLES_DIR / "toy_electricity_2ts.veda.yaml")


@pytest.fixture
def toy_electricity_graph(toy_electricity_source):
    return export_res_graph(toy_electricity_source)


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


class TestExportResGraphStructure:
    def test_top_level_keys(self, toy_buildings_graph):
        assert set(toy_buildings_graph.keys()) == {
            "version", "model", "commodities", "roles", "variants", "edges",
        }

    def test_version_is_string(self, toy_buildings_graph):
        assert toy_buildings_graph["version"] == "1.0"

    def test_model_metadata(self, toy_buildings_graph):
        model = toy_buildings_graph["model"]
        assert model["name"] == "ToyBuildings"
        assert "SINGLE" in model["regions"]
        assert isinstance(model["milestone_years"], list)
        assert len(model["milestone_years"]) > 0

    def test_commodities_have_required_fields(self, toy_buildings_graph):
        for comm in toy_buildings_graph["commodities"]:
            assert "id" in comm
            assert "type" in comm
            assert comm["type"] in (
                "fuel", "energy", "service", "material", "emission", "money", "other"
            )

    def test_roles_have_required_fields(self, toy_buildings_graph):
        for role in toy_buildings_graph["roles"]:
            assert "id" in role
            assert "stage" in role
            assert "required_inputs" in role
            assert "required_outputs" in role
            assert "derived_kind" in role
            assert "variant_count" in role
            assert "has_variant_level_inputs" in role

    def test_variants_have_required_fields(self, toy_buildings_graph):
        for variant in toy_buildings_graph["variants"]:
            assert "id" in variant
            assert "role" in variant
            assert "kind" in variant
            assert "kind_source" in variant
            assert variant["kind_source"] in ("explicit", "derived")

    def test_edges_have_required_fields(self, toy_buildings_graph):
        for edge in toy_buildings_graph["edges"]:
            assert "from" in edge
            assert "to" in edge
            assert "direction" in edge
            assert "commodity" in edge
            assert edge["direction"] in ("input", "output", "emission")


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_json_deterministic(self, toy_buildings_source):
        g1 = export_res_graph(toy_buildings_source)
        g2 = export_res_graph(toy_buildings_source)
        assert json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True)

    def test_mermaid_deterministic(self, toy_buildings_source):
        g1 = export_res_graph(toy_buildings_source)
        g2 = export_res_graph(toy_buildings_source)
        assert res_graph_to_mermaid(g1) == res_graph_to_mermaid(g2)

    def test_commodities_sorted(self, toy_buildings_graph):
        ids = [c["id"] for c in toy_buildings_graph["commodities"]]
        assert ids == sorted(ids)

    def test_roles_sorted(self, toy_buildings_graph):
        ids = [r["id"] for r in toy_buildings_graph["roles"]]
        assert ids == sorted(ids)

    def test_variants_sorted(self, toy_buildings_graph):
        ids = [v["id"] for v in toy_buildings_graph["variants"]]
        assert ids == sorted(ids)

    def test_edges_sorted(self, toy_buildings_graph):
        keys = [
            (e["from"], e["to"], e["direction"])
            for e in toy_buildings_graph["edges"]
        ]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Semantic tests (toy_buildings)
# ---------------------------------------------------------------------------


class TestToyBuildingsSemantics:
    def test_service_commodity_present(self, toy_buildings_graph):
        services = [
            c for c in toy_buildings_graph["commodities"] if c["type"] == "service"
        ]
        assert len(services) >= 1
        assert any(c["id"] == "service:space_heat" for c in services)

    def test_emission_commodity_present(self, toy_buildings_graph):
        emissions = [
            c for c in toy_buildings_graph["commodities"] if c["type"] == "emission"
        ]
        assert len(emissions) >= 1
        assert any(c["id"] == "emission:co2" for c in emissions)

    def test_end_use_role_derived_as_device(self, toy_buildings_graph):
        end_use_roles = [
            r for r in toy_buildings_graph["roles"] if r["stage"] == "end_use"
        ]
        for role in end_use_roles:
            assert role["derived_kind"] == "device"

    def test_supply_roles_present(self, toy_buildings_graph):
        supply_roles = [
            r for r in toy_buildings_graph["roles"] if r["stage"] == "supply"
        ]
        assert len(supply_roles) >= 1

    def test_variant_counts_match(self, toy_buildings_graph):
        for role in toy_buildings_graph["roles"]:
            variant_count = sum(
                1 for v in toy_buildings_graph["variants"] if v["role"] == role["id"]
            )
            assert role["variant_count"] == variant_count

    def test_emission_edges_use_emission_direction(self, toy_buildings_graph):
        co2_output_edges = [
            e for e in toy_buildings_graph["edges"]
            if e["commodity"] == "emission:co2" and e["direction"] != "input"
        ]
        for edge in co2_output_edges:
            assert edge["direction"] == "emission"

    def test_variant_nodes_include_io(self, toy_buildings_graph):
        """Variant nodes include inputs, outputs, and emission_factors."""
        gas = next(
            v for v in toy_buildings_graph["variants"] if v["id"] == "gas_heater"
        )
        assert gas["inputs"] == ["primary:natural_gas"]
        assert gas["outputs"] == ["service:space_heat"]
        assert gas["emission_factors"] == {"emission:co2": 0.056}

        hp = next(
            v for v in toy_buildings_graph["variants"] if v["id"] == "heat_pump"
        )
        assert hp["inputs"] == ["secondary:electricity"]
        assert hp["outputs"] == ["service:space_heat"]
        assert "emission_factors" not in hp

    def test_co2_emission_edge_is_variant_scoped(self, toy_buildings_graph):
        """CO2 emission edge should be variant-scoped, not role-scoped."""
        co2_edges = [
            e for e in toy_buildings_graph["edges"]
            if e["commodity"] == "emission:co2" and e["direction"] == "emission"
        ]
        assert len(co2_edges) == 1
        edge = co2_edges[0]
        assert edge["scope"] == "variant"
        assert edge["source_variants"] == ["gas_heater"]

    def test_role_has_variant_level_outputs(self, toy_buildings_graph):
        """provide_space_heat role should not use emission commodities as outputs."""
        role = next(
            r for r in toy_buildings_graph["roles"]
            if r["id"] == "provide_space_heat"
        )
        assert role["has_variant_level_outputs"] is False

    def test_role_level_edges_have_scope_role(self, toy_buildings_graph):
        """Role-level required_output edges should have scope=role."""
        space_heat_edges = [
            e for e in toy_buildings_graph["edges"]
            if e["commodity"] == "service:space_heat" and e["direction"] == "output"
        ]
        assert len(space_heat_edges) == 1
        assert space_heat_edges[0]["scope"] == "role"

    def test_all_edge_endpoints_exist(self, toy_buildings_graph):
        all_ids = set()
        for c in toy_buildings_graph["commodities"]:
            all_ids.add(c["id"])
        for r in toy_buildings_graph["roles"]:
            all_ids.add(r["id"])
        for edge in toy_buildings_graph["edges"]:
            assert edge["from"] in all_ids, f"Edge 'from' {edge['from']} not found"
            assert edge["to"] in all_ids, f"Edge 'to' {edge['to']} not found"


# ---------------------------------------------------------------------------
# Mermaid output tests
# ---------------------------------------------------------------------------


class TestMermaidOutput:
    def test_starts_with_flowchart(self, toy_buildings_graph):
        mermaid = res_graph_to_mermaid(toy_buildings_graph)
        assert mermaid.startswith("flowchart LR")

    def test_contains_stage_subgraphs(self, toy_buildings_graph):
        mermaid = res_graph_to_mermaid(toy_buildings_graph)
        assert 'subgraph stage_supply["Supply"]' in mermaid
        assert 'subgraph stage_end_use["End Use"]' in mermaid

    def test_commodity_nodes_use_round_parens(self, toy_buildings_graph):
        mermaid = res_graph_to_mermaid(toy_buildings_graph)
        assert 'C_service_space_heat(("service:space_heat<br/>(PJ)"))' in mermaid

    def test_role_nodes_include_kind(self, toy_buildings_graph):
        mermaid = res_graph_to_mermaid(toy_buildings_graph)
        assert "[device]" in mermaid
        assert "cap: GW | act: PJ" in mermaid

    def test_emission_edges_use_dotted_arrow(self, toy_buildings_graph):
        mermaid = res_graph_to_mermaid(toy_buildings_graph)
        assert "-.-> C_emission_co2" in mermaid

    def test_style_definitions_present(self, toy_buildings_graph):
        mermaid = res_graph_to_mermaid(toy_buildings_graph)
        assert "classDef fuel" in mermaid
        assert "classDef service" in mermaid
        assert "classDef emission" in mermaid
        assert "classDef role" in mermaid


# ---------------------------------------------------------------------------
# Cross-model tests
# ---------------------------------------------------------------------------


class TestCrossModel:
    def test_electricity_model_has_generator(self, toy_electricity_graph):
        generators = [
            r for r in toy_electricity_graph["roles"]
            if r["derived_kind"] == "generator"
        ]
        assert len(generators) >= 1

    def test_different_models_different_graphs(
        self, toy_buildings_graph, toy_electricity_graph
    ):
        bld_name = toy_buildings_graph["model"]["name"]
        elc_name = toy_electricity_graph["model"]["name"]
        assert bld_name != elc_name


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_lint_res_json_flag(self, tmp_path):
        json_path = tmp_path / "res.json"
        subprocess.run(
            [
                "uv", "run", "vedalang", "lint",
                str(EXAMPLES_DIR / "toy_buildings.veda.yaml"),
                "--res-json", str(json_path),
            ],
            capture_output=True,
            text=True,
        )
        assert json_path.exists()
        graph = json.loads(json_path.read_text())
        assert graph["version"] == "1.0"
        assert "commodities" in graph
        assert "roles" in graph
        assert "edges" in graph

    def test_lint_res_mermaid_flag(self, tmp_path):
        mermaid_path = tmp_path / "res.mmd"
        subprocess.run(
            [
                "uv", "run", "vedalang", "lint",
                str(EXAMPLES_DIR / "toy_buildings.veda.yaml"),
                "--res-mermaid", str(mermaid_path),
            ],
            capture_output=True,
            text=True,
        )
        assert mermaid_path.exists()
        content = mermaid_path.read_text()
        assert content.startswith("flowchart LR")

    def test_lint_both_flags(self, tmp_path):
        json_path = tmp_path / "res.json"
        mermaid_path = tmp_path / "res.mmd"
        subprocess.run(
            [
                "uv", "run", "vedalang", "lint",
                str(EXAMPLES_DIR / "toy_buildings.veda.yaml"),
                "--res-json", str(json_path),
                "--res-mermaid", str(mermaid_path),
            ],
            capture_output=True,
            text=True,
        )
        assert json_path.exists()
        assert mermaid_path.exists()
