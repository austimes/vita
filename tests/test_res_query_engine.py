from pathlib import Path

from vedalang.viz.query_engine import query_res_graph, response_to_mermaid

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def test_source_query_returns_graph():
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
    assert response["graph"]["nodes"]
    assert response["facets"]["regions"] == ["SINGLE"]
    role_details = [
        detail
        for node_id, detail in response["details"]["nodes"].items()
        if node_id.startswith("role:")
    ]
    assert any(isinstance(detail.get("stage"), str) for detail in role_details)


def test_compiled_instance_query_has_segment_scoped_entities():
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
                "sectors": ["RES"],
                "scopes": [],
            },
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] in {"ok", "partial"}
    assert response["graph"]["nodes"]
    process_labels = [
        n["label"] for n in response["graph"]["nodes"] if n["type"] == "instance"
    ]
    assert any("_RES" in label for label in process_labels)
    instance_details = [
        detail
        for node_id, detail in response["details"]["nodes"].items()
        if node_id.startswith("instance:")
    ]
    assert any(isinstance(detail.get("stage"), str) for detail in instance_details)


def test_mermaid_includes_stage_in_process_labels():
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

    mermaid = response_to_mermaid(response)
    assert "[Supply]" in mermaid or "[End Use]" in mermaid


def test_compiled_trade_query_exposes_trade_edges_and_details():
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
                "case": "baseline",
                "sectors": [],
                "scopes": [],
            },
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] in {"ok", "partial"}
    trade_edges = [e for e in response["graph"]["edges"] if e["type"] == "trade"]
    assert trade_edges
    first_edge_id = trade_edges[0]["id"]
    assert "ire_processes" in response["details"]["edges"][first_edge_id]
