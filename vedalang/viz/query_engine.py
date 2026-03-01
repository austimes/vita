"""Unified RES query engine for CLI, LSP, and web clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vedalang.compiler.compiler import load_vedalang

from .compiled_artifacts import resolve_compiled_artifacts
from .graph_models import (
    FilterSpec,
    build_compiled_system_graph,
    build_source_system_graph,
)
from .trade_view import build_compiled_trade_view, build_source_trade_view

VALID_MODES = {"source", "compiled"}
VALID_GRANULARITIES = {"role", "variant", "instance"}
VALID_LENSES = {"system", "trade"}


def _diagnostic(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _sanitize_mode(value: str | None) -> str:
    if value in VALID_MODES:
        return value
    return "compiled"


def _sanitize_granularity(value: str | None) -> str:
    if value in VALID_GRANULARITIES:
        return value
    return "role"


def _sanitize_lens(value: str | None) -> str:
    if value in VALID_LENSES:
        return value
    return "system"


def _normalize_request(request: dict[str, Any]) -> dict[str, Any]:
    filters = (
        request.get("filters")
        if isinstance(request.get("filters"), dict)
        else {}
    )
    compiled = (
        request.get("compiled")
        if isinstance(request.get("compiled"), dict)
        else {}
    )
    return {
        "version": str(request.get("version", "1")),
        "file": request.get("file", ""),
        "mode": _sanitize_mode(request.get("mode")),
        "granularity": _sanitize_granularity(request.get("granularity")),
        "lens": _sanitize_lens(request.get("lens")),
        "filters": {
            "regions": list(filters.get("regions", []) or []),
            "case": filters.get("case"),
            "sectors": list(filters.get("sectors", []) or []),
            "segments": list(filters.get("segments", []) or []),
        },
        "compiled": {
            "truth": str(compiled.get("truth", "auto")),
            "cache": bool(compiled.get("cache", True)),
            "allow_partial": bool(compiled.get("allow_partial", True)),
        },
    }


def _filters_from_request(
    req: dict[str, Any],
    source: dict,
) -> tuple[FilterSpec, list[dict[str, str]]]:
    diagnostics: list[dict[str, str]] = []
    model_regions = set(source.get("model", {}).get("regions", []))
    requested_regions = set(req["filters"]["regions"])
    regions = requested_regions or model_regions
    unknown_regions = sorted(regions - model_regions)
    if unknown_regions:
        diagnostics.append(
            _diagnostic(
                "UNKNOWN_REGION_FILTER",
                "warning",
                f"Ignoring unknown regions: {', '.join(unknown_regions)}",
            )
        )
        regions = regions - set(unknown_regions)

    sectors = set(req["filters"]["sectors"])
    segments = set(req["filters"]["segments"])

    case_name = req["filters"].get("case")
    if case_name:
        known_cases = {
            c.get("name") for c in source.get("model", {}).get("cases", [])
        }
        if case_name not in known_cases:
            diagnostics.append(
                _diagnostic(
                    "UNKNOWN_CASE_FILTER",
                    "warning",
                    (
                        f"Case '{case_name}' not found; using baseline/default "
                        "graph state."
                    ),
                )
            )

    return FilterSpec(regions=regions, sectors=sectors, segments=segments), diagnostics


def _empty_response(mode: str, diagnostics: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "version": "1",
        "status": "error",
        "mode_used": mode,
        "artifacts": {},
        "graph": {"nodes": [], "edges": []},
        "facets": {
            "regions": [],
            "cases": [],
            "sectors": [],
            "segments": [],
            "granularities": ["role", "variant", "instance"],
            "lenses": ["system", "trade"],
        },
        "diagnostics": diagnostics,
        "details": {"nodes": {}, "edges": {}},
    }


def query_res_graph(request: dict[str, Any]) -> dict[str, Any]:
    """Run a graph query and return a stable JSON response contract."""
    req = _normalize_request(request)
    diagnostics: list[dict[str, str]] = []

    file_raw = req["file"]
    if not file_raw:
        diagnostics.append(
            _diagnostic("MISSING_FILE", "error", "Request missing 'file'.")
        )
        return _empty_response(req["mode"], diagnostics)

    file_path = Path(file_raw).expanduser().resolve()
    if not file_path.exists():
        diagnostics.append(
            _diagnostic(
                "FILE_NOT_FOUND",
                "error",
                f"VedaLang source not found: {file_path}",
            )
        )
        return _empty_response(req["mode"], diagnostics)

    try:
        source = load_vedalang(file_path)
    except Exception as exc:  # pragma: no cover - defensive
        diagnostics.append(
            _diagnostic("SOURCE_LOAD_FAILED", "error", f"Failed to load source: {exc}")
        )
        return _empty_response(req["mode"], diagnostics)

    filters, filter_diags = _filters_from_request(req, source)
    diagnostics.extend(filter_diags)

    mode_used = req["mode"]
    artifacts: dict[str, str] = {}

    def build_source_graph() -> dict[str, Any]:
        if req["lens"] == "trade":
            return build_source_trade_view(source, filters=filters)
        return build_source_system_graph(
            source,
            granularity=req["granularity"],
            filters=filters,
        )

    if req["mode"] == "source":
        built = build_source_graph()
        status = "ok"
    else:
        compiled = resolve_compiled_artifacts(
            file_path=file_path,
            workspace_root=file_path.parent,
            case_name=req["filters"].get("case"),
            truth=req["compiled"].get("truth", "auto"),
            use_cache=req["compiled"].get("cache", True),
        )
        diagnostics.extend(compiled.diagnostics)
        artifacts.update(compiled.artifacts)

        built = None
        status = compiled.status
        if compiled.tableir is not None:
            if req["lens"] == "trade":
                built = build_compiled_trade_view(
                    source,
                    filters=filters,
                    tableir=compiled.tableir,
                    manifest=compiled.manifest,
                )
            else:
                built = build_compiled_system_graph(
                    source,
                    compiled.tableir,
                    compiled.manifest,
                    granularity=req["granularity"],
                    filters=filters,
                )
        elif req["compiled"].get("allow_partial", True):
            mode_used = "source"
            built = build_source_graph()
            status = "partial"
            diagnostics.append(
                _diagnostic(
                    "COMPILED_SOURCE_FALLBACK",
                    "warning",
                    (
                        "Compiled artifacts unavailable; returned source-mode "
                        "graph fallback."
                    ),
                )
            )
        else:
            diagnostics.append(
                _diagnostic(
                    "COMPILED_GRAPH_UNAVAILABLE",
                    "error",
                    "Compiled graph unavailable and source fallback disabled.",
                )
            )
            return _empty_response(mode_used, diagnostics)

    if built is None:
        diagnostics.append(
            _diagnostic("GRAPH_BUILD_FAILED", "error", "No graph was produced.")
        )
        return _empty_response(mode_used, diagnostics)

    return {
        "version": "1",
        "status": status,
        "mode_used": mode_used,
        "artifacts": artifacts,
        "graph": built["graph"],
        "facets": built["facets"],
        "diagnostics": diagnostics,
        "details": built["details"],
    }


def _sanitize_mermaid_id(node_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in node_id)


def response_to_mermaid(response: dict[str, Any]) -> str:
    """Render a query response graph as Mermaid flowchart syntax."""
    lines = ["flowchart LR"]

    for node in response.get("graph", {}).get("nodes", []):
        node_id = _sanitize_mermaid_id(str(node.get("id", "")))
        label = str(node.get("label", node.get("id", ""))).replace('"', "\\\"")
        node_type = str(node.get("type", ""))
        if node_type.startswith("commodity") or node_type == "trade_commodity":
            lines.append(f"    N_{node_id}((\"{label}\"))")
        else:
            lines.append(f"    N_{node_id}[\"{label}\"]")

    for edge in response.get("graph", {}).get("edges", []):
        source = _sanitize_mermaid_id(str(edge.get("source", "")))
        target = _sanitize_mermaid_id(str(edge.get("target", "")))
        edge_type = str(edge.get("type", ""))
        if edge_type == "emission":
            lines.append(f"    N_{source} -.-> N_{target}")
        elif edge_type == "trade":
            lines.append(f"    N_{source} ==> N_{target}")
        else:
            lines.append(f"    N_{source} --> N_{target}")

    return "\n".join(lines)


def list_workspace_veda_files(root: Path) -> list[str]:
    """Return all .veda.yaml files under root, excluding cache/venv dirs."""
    ignore_parts = {".git", ".venv", "node_modules", ".cache", "output", "tmp"}
    root = root.resolve()
    files: list[str] = []
    for path in root.rglob("*.veda.yaml"):
        if any(part in ignore_parts for part in path.parts):
            continue
        files.append(str(path))
    return sorted(files)
