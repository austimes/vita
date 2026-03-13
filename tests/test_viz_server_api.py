from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from tests.test_backend_bridge import _sample_source
from vedalang.viz.server import create_app

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def test_viz_server_health_and_query():
    initial = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"
    app = create_app(workspace_root=Path.cwd(), initial_file=initial)
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    files = client.get("/api/files")
    assert files.status_code == 200
    payload = files.json()
    assert payload["initial_file"] == str(initial)

    query = client.post(
        "/api/query",
        json={
            "version": "1",
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        },
    )
    assert query.status_code == 200
    response = query.json()
    assert response["status"] in {"ok", "partial"}
    assert response["graph"]["nodes"]
    assert all("@SINGLE" not in node["label"] for node in response["graph"]["nodes"])

    filtered_query = client.post(
        "/api/query",
        json={
            "version": "1",
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {
                "regions": ["SINGLE"],
                "case": None,
                "sectors": [],
                "scopes": [],
            },
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        },
    )
    assert filtered_query.status_code == 200
    filtered = filtered_query.json()
    role_node = next(
        node for node in filtered["graph"]["nodes"] if node["type"] == "role"
    )
    assert (
        filtered["details"]["nodes"][role_node["id"]]["scopes"]["regions"]
        == ["SINGLE"]
    )

    trade_file = EXAMPLES_DIR / "feature_demos/example_with_trade.veda.yaml"
    trade_query = client.post(
        "/api/query",
        json={
            "version": "1",
            "file": str(trade_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "trade",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        },
    )
    assert trade_query.status_code == 200
    trade_response = trade_query.json()
    assert any(edge["type"] == "trade" for edge in trade_response["graph"]["edges"])
    assert all(node["type"] == "region" for node in trade_response["graph"]["nodes"])

    pruned_trade_query = client.post(
        "/api/query",
        json={
            "version": "1",
            "file": str(trade_file),
            "mode": "compiled",
            "granularity": "instance",
            "lens": "trade",
            "filters": {"regions": ["REG1"], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        },
    )
    assert pruned_trade_query.status_code == 200
    pruned_trade = pruned_trade_query.json()
    assert pruned_trade["graph"]["nodes"] == [
        {"id": "region:REG1", "label": "REG1", "type": "region"}
    ]
    assert pruned_trade["graph"]["edges"] == []


def test_viz_server_multi_run_query_uses_selected_run(tmp_path):
    source = _sample_source()
    source["runs"].append(
        {
            "id": "toy_states_alt",
            "base_year": 2025,
            "currency_year": 2024,
            "region_partition": "toy_states",
        }
    )
    initial = tmp_path / "multi_run.veda.yaml"
    initial.write_text(yaml.safe_dump(source), encoding="utf-8")

    app = create_app(
        workspace_root=tmp_path,
        initial_file=initial,
        initial_run="toy_states_alt",
    )
    client = TestClient(app)

    files = client.get("/api/files")
    assert files.status_code == 200
    payload = files.json()
    assert payload["initial_run"] == "toy_states_alt"

    query = client.post(
        "/api/query",
        json={
            "version": "1",
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        },
    )
    assert query.status_code == 200
    response = query.json()
    assert response["status"] == "ok"
    assert response["artifacts"]["run_id"] == "toy_states_alt"
    assert response["facets"]["runs"] == ["toy_states_2025", "toy_states_alt"]
