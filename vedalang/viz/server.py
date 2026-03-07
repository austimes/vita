"""HTTP server for standalone RES viewer UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from vedalang.viz.query_engine import query_res_graph

STATIC_DIR = Path(__file__).parent / "static"
IGNORED_DIR_NAMES = {
    ".cache",
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "output",
    "tmp",
}


class VizApiState:
    """In-memory server state for the lightweight viewer."""

    def __init__(
        self,
        workspace_root: Path,
        initial_file: Path | None,
        initial_run: str | None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.initial_file = initial_file.resolve() if initial_file else None
        self.initial_run = initial_run


def _resolve_file(state: VizApiState, raw_path: str | None) -> Path | None:
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (state.workspace_root / candidate).resolve()
        return candidate
    return state.initial_file


def _assert_within_workspace(state: VizApiState, path: Path) -> None:
    try:
        path.relative_to(state.workspace_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Path outside workspace root: {path}",
        ) from exc


def _resolve_directory(state: VizApiState, raw_dir: str | None) -> Path:
    if raw_dir:
        candidate = Path(raw_dir).expanduser()
        if not candidate.is_absolute():
            candidate = state.workspace_root / candidate
        resolved = candidate.resolve()
    elif state.initial_file and state.initial_file.exists():
        resolved = state.initial_file.parent.resolve()
    else:
        resolved = state.workspace_root

    _assert_within_workspace(state, resolved)
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Directory does not exist: {resolved}",
        )
    return resolved


def _directory_entries(directory: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for child in directory.iterdir():
        if child.is_dir():
            if child.name.startswith(".") or child.name in IGNORED_DIR_NAMES:
                continue
            entries.append(
                {
                    "kind": "directory",
                    "name": child.name,
                    "path": str(child.resolve()),
                }
            )
            continue
        if child.is_file() and child.name.endswith(".veda.yaml"):
            entries.append(
                {"kind": "file", "name": child.name, "path": str(child.resolve())}
            )

    return sorted(entries, key=lambda item: (item["kind"] != "directory", item["name"]))


def create_app(
    *,
    workspace_root: Path,
    initial_file: Path | None = None,
    initial_run: str | None = None,
) -> FastAPI:
    """Create FastAPI app for the standalone viewer."""
    state = VizApiState(
        workspace_root=workspace_root,
        initial_file=initial_file,
        initial_run=initial_run,
    )
    app = FastAPI(title="VedaLang RES Visualizer")

    @app.get("/")
    async def index() -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(
            "<h1>VedaLang RES Visualizer</h1><p>Static files not found</p>"
        )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "workspace_root": str(state.workspace_root),
            "initial_file": str(state.initial_file) if state.initial_file else None,
            "initial_run": state.initial_run,
        }

    @app.get("/api/files")
    async def list_files(dir: str | None = None) -> dict[str, Any]:
        current_dir = _resolve_directory(state, dir)
        parent_dir: Path | None = None
        if current_dir != state.workspace_root:
            parent_dir = current_dir.parent
            _assert_within_workspace(state, parent_dir)

        return {
            "workspace_root": str(state.workspace_root),
            "current_dir": str(current_dir),
            "parent_dir": str(parent_dir) if parent_dir else None,
            "entries": _directory_entries(current_dir),
            "initial_file": str(state.initial_file) if state.initial_file else None,
            "initial_run": state.initial_run,
        }

    @app.post("/api/query")
    async def query(payload: dict[str, Any]) -> JSONResponse:
        request = dict(payload)
        selected = _resolve_file(state, request.get("file"))
        if selected is None:
            raise HTTPException(status_code=400, detail="No VedaLang file selected.")

        request["file"] = str(selected)
        request.setdefault("run", state.initial_run)
        response = query_res_graph(request)
        return JSONResponse(response)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
