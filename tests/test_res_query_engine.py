from pathlib import Path

from vedalang.viz.query_engine import query_res_graph, response_to_mermaid

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


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
