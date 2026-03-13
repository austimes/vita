"""Snapshot tests for deterministic RES graph export."""

import json
import subprocess
from pathlib import Path

import pytest

from vedalang.compiler.compiler import load_vedalang
from vedalang.lint.res_export import export_res_graph, res_graph_to_mermaid

EXAMPLES_DIR = Path(__file__).parent.parent / "vedalang" / "examples"


@pytest.fixture
def toy_buildings_source():
    return load_vedalang(EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml")


@pytest.fixture
def toy_buildings_graph(toy_buildings_source):
    return export_res_graph(toy_buildings_source)


@pytest.fixture
def toy_electricity_graph():
    source = load_vedalang(EXAMPLES_DIR / "toy_sectors/toy_electricity_2ts.veda.yaml")
    return export_res_graph(source)


def test_export_graph_has_expected_top_level_keys(toy_buildings_graph):
    assert set(toy_buildings_graph) == {
        "version",
        "model",
        "commodities",
        "roles",
        "variants",
        "edges",
    }
    assert toy_buildings_graph["version"] == "1.0"


def test_export_graph_is_deterministic(toy_buildings_source):
    g1 = export_res_graph(toy_buildings_source)
    g2 = export_res_graph(toy_buildings_source)
    assert json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True)
    assert res_graph_to_mermaid(g1) == res_graph_to_mermaid(g2)


def test_toy_buildings_graph_exposes_public_roles_and_emissions(toy_buildings_graph):
    role_ids = {role["id"] for role in toy_buildings_graph["roles"]}
    assert role_ids == {"electricity_supply", "gas_supply", "space_heat_supply"}

    variants = {variant["id"]: variant for variant in toy_buildings_graph["variants"]}
    assert variants["gas_heater"]["inputs"] == ["natural_gas"]
    assert variants["gas_heater"]["outputs"] == ["space_heat"]
    assert "co2" in variants["gas_heater"]["emission_factors"]
    assert variants["gas_heater"]["ledger_emissions"]["state"] == "emit"
    assert variants["heat_pump"]["inputs"] == ["electricity"]

    assert all(edge["direction"] != "emission" for edge in toy_buildings_graph["edges"])
    commodity_ids = {
        commodity["id"] for commodity in toy_buildings_graph["commodities"]
    }
    assert "co2" not in commodity_ids
    role = next(
        role
        for role in toy_buildings_graph["roles"]
        if role["id"] == "space_heat_supply"
    )
    assert (
        role["ledger_emissions"]["coverage"] == "some_members"
    )


def test_toy_electricity_graph_has_multiple_regions_and_trade_ready_shape(
    toy_electricity_graph,
):
    assert toy_electricity_graph["model"]["regions"] == ["D", "N"]
    assert any(
        role["id"] == "electricity_generation"
        for role in toy_electricity_graph["roles"]
    )
    assert any(variant["id"] == "ccgt" for variant in toy_electricity_graph["variants"])


def test_mermaid_output_contains_stage_and_commodity_nodes(toy_buildings_graph):
    mermaid = res_graph_to_mermaid(toy_buildings_graph)
    assert mermaid.startswith("flowchart LR")
    assert 'subgraph stage_supply["Supply"]' in mermaid
    assert "C_space_heat" in mermaid
    assert "classDef role" in mermaid
    assert "classDef ledger_emit" in mermaid
    assert "Ledger emissions are process coefficients, not commodity flows." in mermaid
    assert "-.->" not in mermaid
    assert "CO2" in mermaid


def test_lint_res_export_flags_write_files(tmp_path):
    json_path = tmp_path / "res.json"
    mermaid_path = tmp_path / "res.mmd"
    result = subprocess.run(
        [
            "uv",
            "run",
            "vedalang",
            "lint",
            str(EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"),
            "--res-json",
            str(json_path),
            "--res-mermaid",
            str(mermaid_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode in {0, 1}
    assert json_path.exists()
    assert mermaid_path.exists()
    assert json.loads(json_path.read_text())["version"] == "1.0"
    assert mermaid_path.read_text().startswith("flowchart LR")
