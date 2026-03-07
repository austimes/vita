from pathlib import Path

from fastapi.testclient import TestClient

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
