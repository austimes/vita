from pathlib import Path

import yaml

from tests.test_v0_2_backend import _v0_2_backend_source
from vedalang.viz.query_engine import query_res_graph, response_to_mermaid

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def _write_multi_run_source(path: Path) -> None:
    source = _v0_2_backend_source()
    source["runs"].append(
        {
            "id": "toy_states_alt",
            "base_year": 2025,
            "currency_year": 2024,
            "region_partition": "toy_states",
        }
    )
    path.write_text(yaml.safe_dump(source), encoding="utf-8")


def test_source_query_returns_v0_2_role_graph():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] == "ok"
    assert response["mode_used"] == "source"
    assert response["facets"]["regions"] == ["SINGLE"]
    assert any(node["type"] == "role" for node in response["graph"]["nodes"])
    assert any(
        detail.get("technology_role") == "space_heat_supply"
        for detail in response["details"]["nodes"].values()
    )


def test_compiled_instance_query_returns_process_nodes():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "filters": {
                "regions": ["SINGLE"],
                "case": None,
                "sectors": [],
                "scopes": [],
            },
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] in {"ok", "partial"}
    assert any(node["type"] == "instance" for node in response["graph"]["nodes"])
    assert any(
        detail.get("technology") == "heat_pump"
        for detail in response["details"]["nodes"].values()
    )


def test_trade_query_exposes_network_edges():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_trade.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "trade",
            "filters": {
                "regions": ["REG1", "REG2"],
                "case": None,
                "sectors": [],
                "scopes": [],
            },
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] in {"ok", "partial"}
    trade_edges = [
        edge for edge in response["graph"]["edges"] if edge["type"] == "trade"
    ]
    assert len(trade_edges) == 2
    first_edge_detail = response["details"]["edges"][trade_edges[0]["id"]]
    assert "source_network" in first_edge_detail


def test_trade_lens_returns_empty_graph_when_no_networks_defined():
    source_file = EXAMPLES_DIR / "design_challenges/dc5_two_regions.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "role",
            "lens": "trade",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] == "ok"
    assert response["graph"]["edges"] == []
    assert response["graph"]["nodes"] == [
        {"id": "region:REG1", "label": "REG1", "type": "region"},
        {"id": "region:REG2", "label": "REG2", "type": "region"},
    ]


def test_mermaid_output_contains_flowchart():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_facilities.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    mermaid = response_to_mermaid(response)
    assert mermaid.startswith("flowchart LR")
    assert "alumina_calcination" in mermaid


def test_compiled_commodity_view_collapse_scope_merges_namespaces():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"

    scoped = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "commodity_view": "scoped",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )
    collapsed = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "commodity_view": "collapse_scope",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    scoped_labels = [
        node["label"]
        for node in scoped["graph"]["nodes"]
        if node["type"] == "commodity"
    ]
    collapsed_labels = [
        node["label"]
        for node in collapsed["graph"]["nodes"]
        if node["type"] == "commodity"
    ]
    assert scoped_labels
    assert collapsed_labels
    assert len(collapsed_labels) <= len(scoped_labels)


def test_role_granularity_exposes_opportunity_provenance_in_labels():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_agriculture.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    role_nodes = [
        node for node in response["graph"]["nodes"] if node["type"] == "role"
    ]
    labels = [node["label"] for node in role_nodes]

    assert len(labels) == len(set(labels))
    assert (
        "farm_carbon_management@SINGLE [opportunity:reforestation_rollout]"
        in labels
    )
    assert "farm_carbon_management@SINGLE [opportunity:soil_carbon_rollout]" in labels

    reforestation_node = next(
        node
        for node in role_nodes
        if node["label"]
        == "farm_carbon_management@SINGLE [opportunity:reforestation_rollout]"
    )
    assert (
        response["details"]["nodes"][reforestation_node["id"]]["group_origin"]
        == "opportunity"
    )


def test_multi_run_v0_2_query_requires_explicit_run_and_exposes_facets(tmp_path):
    source_file = tmp_path / "multi_run.veda.yaml"
    _write_multi_run_source(source_file)

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] == "error"
    assert response["diagnostics"][0]["code"] == "RUN_SELECTION_REQUIRED"
    assert response["facets"]["runs"] == ["toy_states_2025", "toy_states_alt"]


def test_multi_run_v0_2_query_succeeds_with_selected_run(tmp_path):
    source_file = tmp_path / "multi_run.veda.yaml"
    _write_multi_run_source(source_file)

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "run": "toy_states_alt",
            "granularity": "instance",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] in {"ok", "partial"}
    assert response["artifacts"]["run_id"] == "toy_states_alt"
    assert response["facets"]["runs"] == ["toy_states_2025", "toy_states_alt"]


def test_query_rejects_legacy_public_dsl_surface(tmp_path):
    source_file = tmp_path / "legacy_roles.veda.yaml"
    source_file.write_text(
        "\n".join(
            [
                "model:",
                "  name: LegacyQuery",
                "  regions: [R1]",
                "  milestone_years: [2020]",
                "  commodities: []",
                "roles: []",
                "variants: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] == "error"
    assert response["diagnostics"][0]["code"] == "SCHEMA_ERROR"
