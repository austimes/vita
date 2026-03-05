"""Tests for RES graph builder and Mermaid renderer."""

from vedalang.viz.res_mermaid import build_res_graph, graph_to_mermaid


def _make_model_with_emissions():
    """Model where one role has emission output, another doesn't."""
    return {
        "model": {
            "name": "Test",
            "regions": ["R1"],
            "milestone_years": [2020, 2030],
            "commodities": [
                {"id": "gas", "kind": "carrier", "unit": "PJ"},
                {"id": "elc", "kind": "carrier", "unit": "PJ"},
                {"id": "co2", "kind": "emission", "unit": "Mt"},
            ],
        },
        "roles": [
            {
                "id": "generate_elc",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "conversion",
                "required_inputs": [{"commodity": "gas"}],
                "required_outputs": [{"commodity": "elc"}, {"commodity": "co2"}],
            },
            {
                "id": "generate_elc_renewable",
                "activity_unit": "PJ",
                "capacity_unit": "GW",
                "stage": "conversion",
                "required_inputs": [],
                "required_outputs": [{"commodity": "elc"}],
            },
        ],
        "variants": [
            {
                "id": "ccgt",
                "role": "generate_elc",
                "efficiency": 0.55,
                "emission_factors": {"co2": 0.05},
            },
            {
                "id": "wind",
                "role": "generate_elc_renewable",
                "efficiency": 1.0,
            },
        ],
    }


class TestBuildResGraph:
    def test_emission_output_creates_edge(self):
        """Emission commodity in role outputs creates a regular output edge."""
        graph = build_res_graph(_make_model_with_emissions())

        co2_edges = [e for e in graph["edges"] if e["commodityId"] == "co2"]
        assert len(co2_edges) == 1
        assert co2_edges[0]["from"] == "generate_elc"
        assert co2_edges[0]["to"] == "co2"
        assert co2_edges[0]["kind"] == "output"

    def test_non_emitting_role_no_co2_edge(self):
        """Role without emission output has no co2 edge."""
        graph = build_res_graph(_make_model_with_emissions())

        renewable_co2_edges = [
            e for e in graph["edges"]
            if e["from"] == "generate_elc_renewable" and e["commodityId"] == "co2"
        ]
        assert len(renewable_co2_edges) == 0

    def test_co2_node_connected(self):
        """CO2 commodity node has at least one edge."""
        graph = build_res_graph(_make_model_with_emissions())

        co2_edges = [
            e for e in graph["edges"]
            if e.get("commodityId") == "co2"
        ]
        assert len(co2_edges) >= 1


class TestGraphToMermaid:
    def test_emission_output_rendered(self):
        """Emission output edge appears in Mermaid output."""
        graph = build_res_graph(_make_model_with_emissions())
        mermaid = graph_to_mermaid(graph)

        assert "--> C_co2" in mermaid

    def test_core_edges_rendered(self):
        """Core I/O edges appear in Mermaid output."""
        graph = build_res_graph(_make_model_with_emissions())
        mermaid = graph_to_mermaid(graph)

        assert "--> C_elc" in mermaid
        assert "--> P_generate_elc" in mermaid

    def test_commodity_units_rendered(self):
        """Commodity nodes include unit labels."""
        graph = build_res_graph(_make_model_with_emissions())
        mermaid = graph_to_mermaid(graph)

        assert "gas<br/>(PJ)" in mermaid
        assert "co2<br/>(Mt)" in mermaid

    def test_process_units_rendered(self):
        """Process nodes include capacity/activity units."""
        graph = build_res_graph(_make_model_with_emissions())
        mermaid = graph_to_mermaid(graph)

        assert "cap: GW | act: PJ" in mermaid
