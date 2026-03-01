from pathlib import Path

from fastapi.testclient import TestClient

from vedalang.viz.server import create_app

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def test_viz_server_health_and_files_and_query():
    initial = EXAMPLES_DIR / "toy_buildings.veda.yaml"
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
                "segments": [],
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
