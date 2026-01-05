"""WebSocket server for real-time RES visualization.

Watches VedaLang files and pushes graph updates to connected clients.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from vedalang.compiler.compiler import load_vedalang, validate_vedalang
from vedalang.viz.graph_builder import build_graph

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class VizServer:
    """WebSocket server with file watching for RES visualization."""

    def __init__(self, file_path: Path, debounce_ms: int = 250):
        self.file_path = file_path.resolve()
        self.debounce_ms = debounce_ms
        self.app = FastAPI(title="VedaLang RES Visualizer")
        self.clients: set[WebSocket] = set()
        self.last_graph: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._debounce_task: asyncio.Task | None = None
        self._observer: Observer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/")
        async def index():
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            return HTMLResponse(
                "<h1>VedaLang RES Visualizer</h1><p>Static files not found</p>"
            )

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.clients.add(websocket)
            logger.info(f"Client connected. Total clients: {len(self.clients)}")

            if self.last_graph:
                await websocket.send_json({
                    "type": "graph",
                    "data": self.last_graph,
                })
            elif self.last_error:
                await websocket.send_json({
                    "type": "error",
                    "message": self.last_error,
                })

            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.clients.discard(websocket)
                logger.info(f"Client disconnected. Total clients: {len(self.clients)}")

        self.app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    async def broadcast(self, message: dict[str, Any]):
        """Send message to all connected clients."""
        if not self.clients:
            return

        disconnected = set()
        for client in self.clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.add(client)

        self.clients -= disconnected

    def _load_and_broadcast(self):
        """Load the file, build graph, and schedule broadcast."""
        if self._loop is None:
            return

        try:
            source = load_vedalang(self.file_path)
            validate_vedalang(source)
            graph = build_graph(source)
            self.last_graph = graph
            self.last_error = None

            asyncio.run_coroutine_threadsafe(
                self.broadcast({"type": "graph", "data": graph}),
                self._loop,
            )
            node_count = len(graph["nodes"])
            edge_count = len(graph["edges"])
            logger.info(f"Broadcasted graph: {node_count} nodes, {edge_count} edges")

        except Exception as e:
            error_msg = str(e)
            self.last_error = error_msg
            asyncio.run_coroutine_threadsafe(
                self.broadcast({"type": "error", "message": error_msg}),
                self._loop,
            )
            logger.warning(f"Parse error: {error_msg}")

    def _schedule_reload(self):
        """Schedule a debounced reload."""
        if self._loop is None:
            return

        async def debounced_reload():
            await asyncio.sleep(self.debounce_ms / 1000)
            self._load_and_broadcast()

        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        self._debounce_task = asyncio.run_coroutine_threadsafe(
            debounced_reload(), self._loop
        )

    def start_watcher(self, loop: asyncio.AbstractEventLoop):
        """Start file watcher in background thread."""
        self._loop = loop

        self._load_and_broadcast()

        class Handler(FileSystemEventHandler):
            def __init__(self, server: VizServer):
                self.server = server

            def on_modified(self, event):
                if event.is_directory:
                    return
                if Path(event.src_path).resolve() == self.server.file_path:
                    logger.debug(f"File modified: {event.src_path}")
                    self.server._schedule_reload()

        self._observer = Observer()
        self._observer.schedule(
            Handler(self),
            str(self.file_path.parent),
            recursive=False,
        )
        self._observer.start()
        logger.info(f"Watching: {self.file_path}")

    def stop_watcher(self):
        """Stop file watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None


def create_app(file_path: Path) -> tuple[FastAPI, VizServer]:
    """Create the FastAPI app and server instance."""
    server = VizServer(file_path)
    return server.app, server
