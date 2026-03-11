from pathlib import Path

import yaml

from tests.test_v0_2_backend import _v0_2_backend_source
from vedalang.compiler import compile_vedalang_bundle
from vedalang.viz.query_engine import query_res_graph, response_to_mermaid
from vedalang.viz.v0_2_graph import FilterSpec, build_v0_2_system_graph

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def _section_by_key(inspector: dict, key: str) -> dict:
    return next(section for section in inspector["sections"] if section["key"] == key)


def _flatten_dsl_items(items: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for item in items:
        flattened.append(item)
        flattened.extend(_flatten_dsl_items(item.get("children", [])))
    return flattened


def _assert_table_row_ref_contract(row_ref: dict) -> None:
    assert "table_index" in row_ref
    assert isinstance(row_ref["table_index"], int)
    assert "table_key" in row_ref
    assert row_ref["table_key"] == (
        f'{row_ref["file"]}::{row_ref["sheet"]}::{row_ref["table_index"]}::{row_ref["tag"]}'
    )


ROLE_CARBON_LABEL = (
    "farm_carbon_management\n"
    "farm_carbon_management\n"
    "[fleet instance]"
)
ROLE_PROD_LABEL = (
    "agricultural_production\n"
    "farm_production\n"
    "[fleet instance]"
)
ROLE_ZONE_WIND_LABEL = (
    "electricity_generation\n"
    "reg1_new_wind\n"
    "[zone opportunity]"
)
INSTANCE_BASELINE_LABEL = (
    "traditional_baseline\n"
    "agricultural_production\n"
    "[farm_production, fleet instance]"
)
INSTANCE_FEED_ADDITIVES_LABEL = (
    "traditional_with_feed_additives\n"
    "agricultural_production\n"
    "[farm_production, fleet instance]"
)
INSTANCE_IMPROVED_MANURE_LABEL = (
    "traditional_with_improved_manure\n"
    "agricultural_production\n"
    "[farm_production, fleet instance]"
)
INSTANCE_SOIL_LABEL = (
    "soil_carbon\n"
    "farm_carbon_management\n"
    "[farm_carbon_management, fleet instance]"
)
INSTANCE_ZONE_WIND_LABEL = (
    "onshore_wind_turbine\n"
    "electricity_generation\n"
    "[reg1_new_wind, zone opportunity]"
)


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

    instance_node = next(
        node for node in response["graph"]["nodes"] if node["type"] == "instance"
    )
    details = response["details"]["nodes"][instance_node["id"]]
    inspector = details["inspector"]
    expected_sections = [
        "identity",
        "scopes",
        "provenance",
        "aggregation",
        "metrics",
        "dsl",
        "semantic",
    ]
    if details["transition_semantics"]["has_transitions"]:
        expected_sections.append("transitions")
    expected_sections.extend(["lowered", "veda"])
    assert [section["key"] for section in inspector["sections"]] == expected_sections
    assert inspector["kind"] == "process"
    assert inspector["node_type"] == "instance"
    assert _section_by_key(inspector, "identity")["default_open"] is True
    assert _section_by_key(inspector, "dsl")["label"] == "Object explorer"
    assert details["scopes"]["regions"] == ["SINGLE"]
    assert details["aggregation"]["is_aggregated"] is False
    assert details["metrics"]["stock"]["total"]["unit"] == "MW"
    assert _section_by_key(inspector, "lowered")["items"][0]["kind"] == "cpir_process"
    dsl_item = _section_by_key(inspector, "dsl")["items"][0]
    assert "excerpt" not in (dsl_item["source_location"] or {})
    assert "start_line" in (dsl_item["source_location"] or {})
    assert "end_line" in (dsl_item["source_location"] or {})
    assert "lines" in (dsl_item["source_location"] or {})
    veda = _section_by_key(inspector, "veda")
    assert (
        veda["items"][0]["attributes"]["manifest_entry"] is not None
    )
    process_rows = veda["items"][0]["attributes"]["fi_process_rows"]
    fi_t_rows = veda["items"][0]["attributes"]["fi_t_rows"]
    assert process_rows
    assert fi_t_rows
    _assert_table_row_ref_contract(process_rows[0])
    _assert_table_row_ref_contract(fi_t_rows[0])
    assert all(row["table_key"] == process_rows[0]["table_key"] for row in process_rows)


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
    assert first_edge_detail["scopes"]["regions"] == ["REG1", "REG2"]


def test_trade_query_region_filter_prunes_nodes_and_edges():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_trade.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "trade",
            "filters": {
                "regions": ["REG1"],
                "case": None,
                "sectors": [],
                "scopes": [],
            },
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert response["status"] in {"ok", "partial"}
    assert response["graph"]["nodes"] == [
        {"id": "region:REG1", "label": "REG1", "type": "region"}
    ]
    assert response["graph"]["edges"] == []


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


def test_role_granularity_keeps_toy_agriculture_fleet_first():
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
    assert ROLE_CARBON_LABEL in labels
    assert ROLE_PROD_LABEL in labels

    carbon_node = next(
        node
        for node in role_nodes
        if node["label"] == ROLE_CARBON_LABEL
    )
    assert (
        response["details"]["nodes"][carbon_node["id"]]["group_origin"]
        == "role_instance"
    )
    assert (
        response["details"]["nodes"][carbon_node["id"]]["scopes"]["regions"]
        == ["SINGLE"]
    )


def test_role_granularity_exposes_zone_opportunity_provenance_in_labels():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_bounds.veda.yaml"

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

    assert ROLE_ZONE_WIND_LABEL in labels
    wind_node = next(
        node for node in role_nodes if node["label"] == ROLE_ZONE_WIND_LABEL
    )
    assert (
        response["details"]["nodes"][wind_node["id"]]["group_origin"]
        == "zone_opportunity"
    )


def test_system_graph_aggregates_multi_region_fleet_role_nodes():
    bundle = compile_vedalang_bundle(
        _v0_2_backend_source(include_fleet=True),
        selected_run="toy_states_2025",
        custom_weights={"weights/custom_heat.csv": {"NSW": 0.6, "QLD": 0.4}},
    )

    built = build_v0_2_system_graph(
        csir=bundle.csir or {},
        cpir=bundle.cpir or {},
        granularity="role",
        commodity_view="collapse_scope",
        filters=FilterSpec(regions={"NSW", "QLD"}, sectors=set(), scopes=set()),
    )

    fleet_role = next(
        node
        for node in built["graph"]["nodes"]
        if node["id"] == "role:asset:fleets.residential_heat"
    )
    assert (
        fleet_role["label"]
        == "space_heat_supply\nresidential_heat\n[fleet instance]"
    )
    detail = built["details"]["nodes"][fleet_role["id"]]
    assert detail["scopes"]["regions"] == ["NSW", "QLD"]
    assert detail["aggregation"]["is_aggregated"] is True
    assert detail["aggregation"]["member_regions"] == ["NSW", "QLD"]
    assert detail["metrics"]["stock"]["total"]["unit"] == "kW"
    assert len(detail["metrics"]["stock"]["by_region"]) == 2


def test_region_filter_excludes_other_system_regions(tmp_path):
    source_file = tmp_path / "two_region.veda.yaml"
    source_file.write_text(yaml.safe_dump(_v0_2_backend_source()), encoding="utf-8")

    qld = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "run": "toy_states_2025",
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": ["QLD"], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )
    nsw = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "run": "toy_states_2025",
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": ["NSW"], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    assert qld["status"] == "ok"
    assert any(node["type"] == "role" for node in qld["graph"]["nodes"])
    assert nsw["status"] == "ok"
    assert [node for node in nsw["graph"]["nodes"] if node["type"] == "role"] == []


def test_role_query_inspector_aggregates_member_processes():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"

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

    role_node = next(
        node
        for node in response["graph"]["nodes"]
        if node["type"] == "role"
        and len(response["details"]["nodes"][node["id"]]["member_process_ids"]) > 1
    )
    inspector = response["details"]["nodes"][role_node["id"]]["inspector"]
    assert _section_by_key(inspector, "aggregation")["items"][0]["attributes"][
        "member_count"
    ] == len(response["details"]["nodes"][role_node["id"]]["member_process_ids"])
    lowered = _section_by_key(inspector, "lowered")
    dsl = _section_by_key(inspector, "dsl")
    assert dsl["label"] == "Object explorer"
    assert len(lowered["items"]) > 1
    assert (
        sum(
            1
            for item in _flatten_dsl_items(dsl["items"])
            if item["kind"] == "technology"
        )
        > 1
    )


def test_commodity_inspector_reports_usage_lists():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    commodity_node = next(
        node
        for node in response["graph"]["nodes"]
        if node["type"] == "commodity" and node["label"] == "space_heat"
    )
    inspector = response["details"]["nodes"][commodity_node["id"]]["inspector"]
    assert _section_by_key(inspector, "dsl")["label"] == "Object explorer"
    lowered = _section_by_key(inspector, "lowered")
    usage = lowered["items"][0]["attributes"]
    assert usage["produced_by"]
    assert usage["consumed_by"] == []
    veda = _section_by_key(inspector, "veda")
    assert veda["items"][0]["attributes"]["manifest_entry"] is not None
    fi_comm_rows = veda["items"][0]["attributes"]["times_summary"]["fi_comm_rows"]
    fi_t_rows = veda["items"][0]["attributes"]["times_summary"]["fi_t_rows"]
    assert fi_comm_rows
    assert fi_t_rows
    _assert_table_row_ref_contract(fi_comm_rows[0])
    _assert_table_row_ref_contract(fi_t_rows[0])
    assert all(row["table_key"] == fi_comm_rows[0]["table_key"] for row in fi_comm_rows)


def test_source_mode_inspector_marks_veda_section_partial_without_manifest():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "source",
            "granularity": "instance",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    instance_node = next(
        node for node in response["graph"]["nodes"] if node["type"] == "instance"
    )
    inspector = response["details"]["nodes"][instance_node["id"]]["inspector"]
    veda = _section_by_key(inspector, "veda")
    assert veda["status"] == "partial"
    assert veda["items"]
    assert veda["items"][0]["attributes"]["fi_process_rows"]
    _assert_table_row_ref_contract(veda["items"][0]["attributes"]["fi_process_rows"][0])


def test_collapse_scope_inspector_tracks_all_underlying_commodities(tmp_path):
    source = {
        "dsl_version": "0.3",
        "commodities": [
            {"id": "electricity", "type": "energy", "energy_form": "secondary"},
            {"id": "space_heat@RES", "type": "service"},
            {"id": "space_heat@COM", "type": "service"},
        ],
        "technologies": [
            {
                "id": "res_hp",
                "provides": "space_heat@RES",
                "inputs": [{"commodity": "electricity"}],
                "performance": {"kind": "cop", "value": 3.0},
                "emissions": [],
            },
            {
                "id": "com_hp",
                "provides": "space_heat@COM",
                "inputs": [{"commodity": "electricity"}],
                "performance": {"kind": "cop", "value": 3.0},
                "emissions": [],
            },
        ],
        "technology_roles": [
            {
                "id": "res_space_heat",
                "primary_service": "space_heat@RES",
                "technologies": ["res_hp"],
            },
            {
                "id": "com_space_heat",
                "primary_service": "space_heat@COM",
                "technologies": ["com_hp"],
            },
        ],
        "spatial_layers": [
            {
                "id": "geo.demo",
                "kind": "polygon",
                "key": "region_id",
                "geometry_file": "data/regions.geojson",
            }
        ],
        "region_partitions": [
            {
                "id": "single_partition",
                "layer": "geo.demo",
                "members": ["SINGLE"],
                "mapping": {"kind": "constant", "value": "SINGLE"},
            }
        ],
        "sites": [
            {
                "id": "single_site",
                "location": {"point": {"lat": 0.0, "lon": 0.0}},
                "membership_overrides": {
                    "region_partitions": {"single_partition": "SINGLE"}
                },
            }
        ],
        "facilities": [
            {
                "id": "res_heat",
                "site": "single_site",
                "technology_role": "res_space_heat",
                "available_technologies": ["res_hp"],
                "stock": {
                    "items": [
                        {
                            "technology": "res_hp",
                            "metric": "installed_capacity",
                            "observed": {"value": "10 MW", "year": 2025},
                        }
                    ]
                },
            },
            {
                "id": "com_heat",
                "site": "single_site",
                "technology_role": "com_space_heat",
                "available_technologies": ["com_hp"],
                "stock": {
                    "items": [
                        {
                            "technology": "com_hp",
                            "metric": "installed_capacity",
                            "observed": {"value": "12 MW", "year": 2025},
                        }
                    ]
                },
            },
        ],
        "runs": [
            {
                "id": "single_run",
                "base_year": 2025,
                "currency_year": 2024,
                "region_partition": "single_partition",
            }
        ],
    }
    source_file = tmp_path / "scoped.veda.yaml"
    source_file.write_text(yaml.safe_dump(source), encoding="utf-8")

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "run": "single_run",
            "mode": "source",
            "granularity": "instance",
            "lens": "system",
            "commodity_view": "collapse_scope",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    commodity_node = next(
        node
        for node in response["graph"]["nodes"]
        if node["type"] == "commodity" and node["label"] == "space_heat"
    )
    details = response["details"]["nodes"][commodity_node["id"]]
    assert details["commodity_ids"] == [
        "space_heat@COM",
        "space_heat@RES",
    ]
    inspector = details["inspector"]
    assert inspector["summary"]["commodity_view_members"] == [
        "space_heat@COM",
        "space_heat@RES",
    ]
    assert details["scopes"]["regions"] == ["SINGLE"]
    lowered = _section_by_key(inspector, "lowered")
    produced = sorted(
        item["attributes"]["produced_by"][0] for item in lowered["items"]
    )
    assert produced == [
        "P::role_instance.com_heat@SINGLE::com_hp",
        "P::role_instance.res_heat@SINGLE::res_hp",
    ]


def test_instance_granularity_uses_stacked_technology_role_and_provenance_labels():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_agriculture.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    instance_nodes = [
        node for node in response["graph"]["nodes"] if node["type"] == "instance"
    ]
    labels = [node["label"] for node in instance_nodes]

    assert INSTANCE_BASELINE_LABEL in labels
    assert INSTANCE_SOIL_LABEL in labels

    baseline_node = next(
        node
        for node in instance_nodes
        if node["label"] == INSTANCE_BASELINE_LABEL
    )
    assert (
        response["details"]["nodes"][baseline_node["id"]]["group_origin"]
        == "role_instance"
    )
    assert (
        response["details"]["nodes"][baseline_node["id"]]["technology_role"]
        == "agricultural_production"
    )


def test_toy_agriculture_transition_semantics_ignore_new_build_limits() -> None:
    source_file = EXAMPLES_DIR / "toy_sectors/toy_agriculture.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    instance_details = response["details"]["nodes"]
    instance_nodes = [
        node for node in response["graph"]["nodes"] if node["type"] == "instance"
    ]

    baseline_node = next(
        node for node in instance_nodes if node["label"] == INSTANCE_BASELINE_LABEL
    )
    baseline_semantics = instance_details[baseline_node["id"]]["transition_semantics"]
    assert baseline_semantics["has_transitions"] is True
    assert baseline_semantics["participation"] == "source"
    assert baseline_semantics["direction"] == "source"
    assert baseline_semantics["kind_basis"] == "retrofit"
    assert baseline_semantics["badge_label"] == "retrofit source"
    assert baseline_semantics["incoming_technologies"] == []
    assert baseline_semantics["outgoing_technologies"] == [
        "traditional_with_feed_additives",
        "traditional_with_improved_manure",
    ]

    feed_node = next(
        node
        for node in instance_nodes
        if node["label"] == INSTANCE_FEED_ADDITIVES_LABEL
    )
    feed_semantics = instance_details[feed_node["id"]]["transition_semantics"]
    assert feed_semantics["has_transitions"] is True
    assert feed_semantics["participation"] == "option"
    assert feed_semantics["direction"] == "option"
    assert feed_semantics["badge_label"] == "retrofit option"
    assert feed_semantics["incoming_technologies"] == ["traditional_baseline"]
    assert feed_semantics["outgoing_technologies"] == []

    manure_node = next(
        node
        for node in instance_nodes
        if node["label"] == INSTANCE_IMPROVED_MANURE_LABEL
    )
    manure_semantics = instance_details[manure_node["id"]]["transition_semantics"]
    assert manure_semantics["has_transitions"] is True
    assert manure_semantics["participation"] == "option"
    assert manure_semantics["direction"] == "option"
    assert manure_semantics["badge_label"] == "retrofit option"
    assert manure_semantics["incoming_technologies"] == ["traditional_baseline"]
    assert manure_semantics["outgoing_technologies"] == []

    soil_node = next(
        node for node in instance_nodes if node["label"] == INSTANCE_SOIL_LABEL
    )
    soil_semantics = instance_details[soil_node["id"]]["transition_semantics"]
    assert soil_semantics["has_transitions"] is False
    assert soil_semantics["badge_label"] is None


def test_toy_agriculture_role_transition_semantics_expose_retrofit_options():
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

    role_nodes = [node for node in response["graph"]["nodes"] if node["type"] == "role"]
    prod_node = next(node for node in role_nodes if node["label"] == ROLE_PROD_LABEL)
    prod_semantics = response["details"]["nodes"][prod_node["id"]][
        "transition_semantics"
    ]
    assert prod_semantics["has_transitions"] is True
    assert prod_semantics["participation"] == "role"
    assert prod_semantics["direction"] == "role"
    assert prod_semantics["kind_basis"] == "retrofit"
    assert prod_semantics["badge_label"] == "retrofit options"
    assert prod_semantics["matched_transition_count"] == 2
    assert prod_semantics["incoming_technologies"] == ["traditional_baseline"]
    assert prod_semantics["outgoing_technologies"] == [
        "traditional_with_feed_additives",
        "traditional_with_improved_manure",
    ]

    carbon_node = next(
        node for node in role_nodes if node["label"] == ROLE_CARBON_LABEL
    )
    carbon_semantics = response["details"]["nodes"][carbon_node["id"]][
        "transition_semantics"
    ]
    assert carbon_semantics["has_transitions"] is False
    assert carbon_semantics["badge_label"] is None


def test_zone_opportunity_nodes_without_role_transitions_are_not_marked_as_retrofits():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_bounds.veda.yaml"

    role_response = query_res_graph(
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
    role_node = next(
        node
        for node in role_response["graph"]["nodes"]
        if node["type"] == "role" and node["label"] == ROLE_ZONE_WIND_LABEL
    )
    role_details = role_response["details"]["nodes"][role_node["id"]]
    assert role_details["group_origin"] == "zone_opportunity"
    assert role_details["transition_semantics"]["has_transitions"] is False

    instance_response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "filters": {"regions": ["REG1"], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )
    instance_node = next(
        node
        for node in instance_response["graph"]["nodes"]
        if node["type"] == "instance" and node["label"] == INSTANCE_ZONE_WIND_LABEL
    )
    instance_details = instance_response["details"]["nodes"][instance_node["id"]]
    assert instance_details["group_origin"] == "zone_opportunity"
    assert instance_details["transition_semantics"]["has_transitions"] is False


def test_asset_backed_role_object_explorer_nests_facility_role_technology():
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

    node_id = "role:asset:fleets.farm_input_supply"
    inspector = response["details"]["nodes"][node_id]["inspector"]
    dsl = _section_by_key(inspector, "dsl")
    assert dsl["label"] == "Object explorer"
    assert dsl["status"] == "ok"
    assert len(dsl["items"]) == 1
    fleet = dsl["items"][0]
    assert fleet["kind"] == "fleet"
    assert fleet["id"] == "farm_input_supply"
    assert [child["kind"] for child in fleet["children"]] == ["technology_role"]
    role = fleet["children"][0]
    assert role["id"] == "farm_input_supply"
    assert [child["kind"] for child in role["children"]] == ["technology"]
    assert [child["id"] for child in role["children"]] == ["farm_input_import"]


def test_object_explorer_source_blocks_use_exact_yaml_item_lines():
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

    node_id = "role:asset:fleets.farm_input_supply"
    inspector = response["details"]["nodes"][node_id]["inspector"]
    dsl_items = _flatten_dsl_items(_section_by_key(inspector, "dsl")["items"])
    role_item = next(item for item in dsl_items if item["kind"] == "technology_role")
    tech_item = next(item for item in dsl_items if item["kind"] == "technology")

    assert role_item["source_location"]["start_line"] == 117
    assert role_item["source_location"]["end_line"] == 120
    assert (
        role_item["source_location"]["lines"][0]["text"]
        == "  - id: farm_input_supply"
    )
    assert all(
        line["text"] != "technology_roles:"
        for line in role_item["source_location"]["lines"]
    )
    assert "excerpt" not in role_item["source_location"]

    assert tech_item["source_location"]["start_line"] == 18
    assert (
        tech_item["source_location"]["lines"][0]["text"]
        == "  - id: farm_input_import"
    )
    assert all(
        line["text"] != "technologies:"
        for line in tech_item["source_location"]["lines"]
    )


def test_object_explorer_includes_role_transitions_as_nested_items():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_agriculture.veda.yaml"

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

    node_id = "instance:asset:traditional_baseline:fleets.farm_production"
    inspector = response["details"]["nodes"][node_id]["inspector"]
    fleet = _section_by_key(inspector, "dsl")["items"][0]
    role = fleet["children"][0]

    assert [child["kind"] for child in role["children"]] == [
        "technology",
        "transition",
        "transition",
    ]
    assert role["children"][1]["attributes"]["kind"] == "retrofit"
    assert role["children"][2]["attributes"]["kind"] == "retrofit"


def test_retrofit_linked_nodes_include_transitions_inspector_section():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_agriculture.veda.yaml"

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

    node_id = "instance:asset:traditional_baseline:fleets.farm_production"
    inspector = response["details"]["nodes"][node_id]["inspector"]
    transitions = _section_by_key(inspector, "transitions")
    assert transitions["label"] == "Transitions"
    assert transitions["default_open"] is True
    assert transitions["items"][0]["kind"] == "transition_summary"
    assert transitions["items"][0]["attributes"]["badge_label"] == "retrofit source"
    assert [item["kind"] for item in transitions["items"][1:]] == [
        "transition",
        "transition",
    ]


def test_object_explorer_zone_opportunity_nests_role_then_technology():
    source_file = EXAMPLES_DIR / "feature_demos/example_with_bounds.veda.yaml"

    response = query_res_graph(
        {
            "version": "1",
            "file": str(source_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "system",
            "filters": {
                "regions": ["REG1"],
                "case": None,
                "sectors": [],
                "scopes": [],
            },
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
    )

    node_id = next(
        node["id"]
        for node in response["graph"]["nodes"]
        if node["type"] == "instance" and node["label"] == INSTANCE_ZONE_WIND_LABEL
    )
    inspector = response["details"]["nodes"][node_id]["inspector"]
    dsl = _section_by_key(inspector, "dsl")
    assert dsl["status"] == "ok"
    assert len(dsl["items"]) == 1
    opportunity = dsl["items"][0]
    assert opportunity["kind"] == "zone_opportunity"
    assert opportunity["id"] == "reg1_new_wind"
    assert [child["kind"] for child in opportunity["children"]] == ["technology_role"]
    role = opportunity["children"][0]
    assert role["id"] == "electricity_generation"
    assert [child["kind"] for child in role["children"]] == ["technology"]
    assert role["children"][0]["id"] == "onshore_wind_turbine"


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
