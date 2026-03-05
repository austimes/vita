from pathlib import Path

from fastapi.testclient import TestClient

from vedalang.viz.server import create_app

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def test_viz_server_health_and_files_and_query():
    initial = EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml"
    app = create_app(workspace_root=Path.cwd(), initial_file=initial)
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    files = client.get("/api/files")
    assert files.status_code == 200
    payload = files.json()
    assert payload["workspace_root"] == str(Path.cwd())
    assert payload["current_dir"] == str(initial.parent)
    assert payload["initial_file"] == str(initial)
    assert any(
        entry["kind"] == "file" and entry["path"] == str(initial)
        for entry in payload["entries"]
    )

    parent = payload["parent_dir"]
    if parent:
        parent_resp = client.get("/api/files", params={"dir": parent})
        assert parent_resp.status_code == 200
        assert parent_resp.json()["current_dir"] == parent

    query = client.post(
        "/api/query",
        json={
            "version": "1",
            "mode": "source",
            "granularity": "role",
            "lens": "system",
            "filters": {
                "regions": [],
                "case": None,
                "sectors": [],
                "scopes": [],
            },
            "compiled": {
                "truth": "auto",
                "cache": True,
                "allow_partial": True,
            },
        },
    )
    assert query.status_code == 200
    response = query.json()
    assert response["version"] == "1"
    assert response["status"] in {"ok", "partial"}
    assert response["graph"]["nodes"]

    facility_file = EXAMPLES_DIR / "feature_demos/example_with_facilities.veda.yaml"
    mode_query = client.post(
        "/api/query",
        json={
            "version": "1",
            "file": str(facility_file),
            "mode": "source",
            "granularity": "mode",
            "lens": "system",
            "filters": {
                "regions": [],
                "case": None,
                "sectors": [],
                "scopes": [],
            },
            "compiled": {
                "truth": "auto",
                "cache": True,
                "allow_partial": True,
            },
        },
    )
    assert mode_query.status_code == 200
    mode_response = mode_query.json()
    assert mode_response["graph"]["nodes"]
    assert any(node["type"] == "mode" for node in mode_response["graph"]["nodes"])
