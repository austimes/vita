"""Tests for legacy graph_builder runtime helpers."""

from vedalang.viz.graph_builder import build_graph


def test_graph_builder_uses_canonical_runtime_node_ids():
    source = {
        "model": {
            "name": "GraphBuilderTest",
            "regions": ["R1", "R2"],
            "commodities": [
                {"id": "secondary:electricity", "type": "energy", "unit": "PJ"},
                {"id": "primary:natural_gas", "type": "fuel", "unit": "PJ"},
            ],
            "processes": [
                {
                    "name": "pp_ccgt",
                    "sets": ["ELE"],
                    "inputs": [{"commodity": "primary:natural_gas"}],
                    "outputs": [{"commodity": "secondary:electricity"}],
                }
            ],
            "trade_links": [
                {
                    "origin": "R1",
                    "destination": "R2",
                    "commodity": "secondary:electricity",
                }
            ],
        }
    }

    graph = build_graph(source)
    node_ids = [n["data"]["id"] for n in graph["nodes"]]
    edge_ids = [e["data"]["id"] for e in graph["edges"]]

    assert "commodity:secondary:electricity" in node_ids
    assert "commodity:primary:natural_gas" in node_ids
    assert "process:pp_ccgt" in node_ids
    assert any(edge_id.startswith("edge:") for edge_id in edge_ids)
    assert any(edge_id.startswith("trade:") for edge_id in edge_ids)

