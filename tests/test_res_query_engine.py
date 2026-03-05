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


def test_facility_source_mode_granularity_exposes_mode_nodes():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_facilities.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "mode",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] == "ok"
    assert response["graph"]["nodes"]
    mode_nodes = [n for n in response["graph"]["nodes"] if n["type"] == "mode"]
    assert mode_nodes
    first_mode_id = mode_nodes[0]["id"]
    detail = response["details"]["nodes"][first_mode_id]
    assert detail["facility_id"]
    assert detail["mode_id"]


def test_facility_compiled_mode_granularity_includes_facility_metadata():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_facilities.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "mode",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": False, "allow_partial": True},
        }
    )

    assert response["status"] in {"ok", "partial"}
    mode_nodes = [n for n in response["graph"]["nodes"] if n["type"] == "mode"]
    assert mode_nodes
    first_mode_id = mode_nodes[0]["id"]
    detail = response["details"]["nodes"][first_mode_id]
    assert detail["facility_id"]
    assert detail["template_variant_id"]
    assert detail["mode_id"]


def test_mermaid_mode_granularity_includes_facility_mode_label():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_facilities.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "mode",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    mermaid = response_to_mermaid(response)
    assert "[Conversion]" in mermaid
    assert "retrofit_to_ng" in mermaid or "coal" in mermaid


def test_compiled_commodity_view_collapse_scope_merges_scoped_nodes():
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

    scoped_commodities = [
        n["label"]
        for n in scoped["graph"]["nodes"]
        if n["type"] == "commodity"
    ]
    collapsed_commodities = [
        n["label"]
        for n in collapsed["graph"]["nodes"]
        if n["type"] == "commodity"
    ]

    assert any("@" in label for label in scoped_commodities)
    assert all("@" not in label for label in collapsed_commodities)
