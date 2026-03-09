"""Unified RES query engine for CLI, LSP, and web clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema

from vedalang.compiler.compiler import (
    compile_vedalang_bundle,
    load_vedalang,
    validate_vedalang,
)
from vedalang.compiler.v0_2_ast import parse_v0_2_source
from vedalang.compiler.v0_2_resolution import resolve_imports, resolve_run
from vedalang.conventions import stage_label
from vedalang.versioning import looks_like_v0_2_source

from .compiled_artifacts import resolve_compiled_artifacts
from .inspector import InspectorContext, build_system_node_inspectors
from .v0_2_graph import (
    FilterSpec,
    build_v0_2_system_graph,
    build_v0_2_trade_graph,
    infer_run_id,
)

VALID_MODES = {"source", "compiled"}
VALID_GRANULARITIES = {"role", "instance"}
VALID_LENSES = {"system", "trade"}
VALID_COMMODITY_VIEWS = {"scoped", "collapse_scope"}


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


def _sanitize_commodity_view(value: str | None, granularity: str) -> str:
    if value in VALID_COMMODITY_VIEWS:
        return str(value)
    if granularity == "instance":
        return "scoped"
    return "collapse_scope"


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
    granularity = _sanitize_granularity(request.get("granularity"))
    return {
        "version": str(request.get("version", "1")),
        "file": request.get("file", ""),
        "run": request.get("run"),
        "mode": _sanitize_mode(request.get("mode")),
        "granularity": granularity,
        "lens": _sanitize_lens(request.get("lens")),
        "commodity_view": _sanitize_commodity_view(
            request.get("commodity_view"),
            granularity,
        ),
        "filters": {
            "regions": list(filters.get("regions", []) or []),
            "case": filters.get("case"),
            "sectors": list(filters.get("sectors", []) or []),
            "scopes": list(filters.get("scopes", []) or []),
        },
        "compiled": {
            "truth": str(compiled.get("truth", "auto")),
            "cache": bool(compiled.get("cache", True)),
            "allow_partial": bool(compiled.get("allow_partial", True)),
        },
    }


def _default_facets() -> dict[str, list[str]]:
    return {
        "regions": [],
        "cases": [],
        "runs": [],
        "sectors": [],
        "scopes": [],
        "granularities": ["role", "instance"],
        "commodity_views": ["scoped", "collapse_scope"],
        "lenses": ["system", "trade"],
    }


def _v0_2_runs(source: dict[str, Any]) -> list[str]:
    runs = source.get("runs")
    if not isinstance(runs, list):
        return []
    return [
        str(run.get("id"))
        for run in runs
        if isinstance(run, dict) and run.get("id")
    ]


def _v0_2_model_regions(
    source: dict[str, Any],
    *,
    run_id: str | None = None,
) -> set[str]:
    partitions = {
        str(partition.get("id")): partition
        for partition in source.get("region_partitions", []) or []
        if isinstance(partition, dict) and partition.get("id")
    }
    runs = {
        str(run.get("id")): run
        for run in source.get("runs", []) or []
        if isinstance(run, dict) and run.get("id")
    }

    if run_id and run_id in runs:
        partition_ref = runs[run_id].get("region_partition")
        partition = partitions.get(str(partition_ref))
        if partition:
            return set(partition.get("members", []) or [])

    members: set[str] = set()
    for run in runs.values():
        partition_ref = run.get("region_partition")
        partition = partitions.get(str(partition_ref))
        if partition:
            members.update(partition.get("members", []) or [])
    return members


def _facets_for_source(
    source: dict[str, Any],
    *,
    run_id: str | None = None,
) -> dict[str, list[str]]:
    facets = _default_facets()
    if looks_like_v0_2_source(source):
        facets["runs"] = sorted(_v0_2_runs(source))
        facets["regions"] = sorted(_v0_2_model_regions(source, run_id=run_id))
    return facets


def _filters_from_request(
    req: dict[str, Any],
    source: dict,
    *,
    run_id: str | None = None,
) -> tuple[FilterSpec, list[dict[str, str]]]:
    diagnostics: list[dict[str, str]] = []
    model_regions = _v0_2_model_regions(source, run_id=run_id)
    requested_regions = set(req["filters"]["regions"])
    regions = requested_regions or model_regions
    unknown_regions = sorted(regions - model_regions) if model_regions else []
    if unknown_regions:
        diagnostics.append(
            _diagnostic(
                "UNKNOWN_REGION_FILTER",
                "warning",
                f"Ignoring unknown regions: {', '.join(unknown_regions)}",
            )
        )
        regions = regions - set(unknown_regions)
    return (
        FilterSpec(
            regions=regions,
            sectors=set(req["filters"]["sectors"]),
            scopes=set(req["filters"]["scopes"]),
        ),
        diagnostics,
    )


def _empty_response(
    mode: str,
    diagnostics: list[dict[str, str]],
    *,
    facets: dict[str, list[str]] | None = None,
    artifacts: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "version": "1",
        "status": "error",
        "mode_used": mode,
        "artifacts": artifacts or {},
        "graph": {"nodes": [], "edges": []},
        "facets": facets or _default_facets(),
        "diagnostics": diagnostics,
        "details": {"nodes": {}, "edges": {}},
    }


def _networks_configured(source: dict[str, Any]) -> bool:
    networks = source.get("networks", [])
    if not isinstance(networks, list):
        return False
    return any(
        isinstance(network, dict)
        and isinstance(network.get("links"), list)
        and bool(network.get("links"))
        for network in networks
    )


def _attach_system_inspectors(
    built: dict[str, Any],
    *,
    source: dict[str, Any],
    file_path: Path,
    run_id: str,
    csir: dict[str, Any] | None,
    cpir: dict[str, Any] | None,
    explain: dict[str, Any] | None,
    tableir: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
) -> None:
    if csir is None or cpir is None:
        return
    details = built.get("details")
    graph = built.get("graph")
    if not isinstance(details, dict) or not isinstance(graph, dict):
        return
    detail_nodes = details.get("nodes")
    graph_nodes = graph.get("nodes")
    if not isinstance(detail_nodes, dict) or not isinstance(graph_nodes, list):
        return

    parsed_source = parse_v0_2_source(source)
    resolved_graph = resolve_imports(parsed_source, {})
    run_context = resolve_run(resolved_graph, run_id)
    inspectors = build_system_node_inspectors(
        graph_nodes=graph_nodes,
        details_nodes=detail_nodes,
        context=InspectorContext(
            source=source,
            source_file=file_path,
            parsed_source=parsed_source,
            graph=resolved_graph,
            run_context=run_context,
            csir=csir,
            cpir=cpir,
            explain=explain,
            tableir=tableir,
            manifest=manifest,
        ),
    )
    for node_id, inspector in inspectors.items():
        detail = detail_nodes.get(node_id)
        if isinstance(detail, dict):
            detail["inspector"] = inspector


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

    mode_used = req["mode"]
    artifacts: dict[str, str] = {}
    run_id: str | None = None
    facets = _facets_for_source(source)

    if not looks_like_v0_2_source(source):
        try:
            validate_vedalang(source)
        except jsonschema.ValidationError as exc:
            diagnostics.append(_diagnostic("SCHEMA_ERROR", "error", exc.message))
        else:  # pragma: no cover - defensive
            diagnostics.append(
                _diagnostic(
                    "SOURCE_UNSUPPORTED",
                    "error",
                    "Source shape is unsupported for RES query and viz tooling.",
                )
            )
        return _empty_response(req["mode"], diagnostics, facets=facets)

    available_runs = _v0_2_runs(source)
    requested_run = req.get("run")
    if requested_run is not None:
        requested_run = str(requested_run)
        if requested_run not in available_runs:
            diagnostics.append(
                _diagnostic(
                    "UNKNOWN_RUN_FILTER",
                    "error",
                    f"Run '{requested_run}' not found in source.",
                )
            )
            return _empty_response(
                req["mode"],
                diagnostics,
                facets=facets,
            )
        run_id = requested_run
    else:
        run_id = infer_run_id(source)

    if run_id is None:
        diagnostics.append(
            _diagnostic(
                "RUN_SELECTION_REQUIRED",
                "error",
                "v0.2 graph queries require an explicit run when the source "
                "defines multiple runs.",
            )
        )
        return _empty_response(req["mode"], diagnostics, facets=facets)

    artifacts["run_id"] = run_id
    facets = _facets_for_source(source, run_id=run_id)
    filters, filter_diags = _filters_from_request(req, source, run_id=run_id)
    diagnostics.extend(filter_diags)

    if req["mode"] == "source":
        try:
            bundle = compile_vedalang_bundle(
                source,
                validate=True,
                selected_run=run_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            diagnostics.append(
                _diagnostic(
                    "SOURCE_GRAPH_BUILD_FAILED",
                    "error",
                    f"Failed to compile v0.2 source graph: {exc}",
                )
            )
            return _empty_response(req["mode"], diagnostics, facets=facets)
        if bundle.csir and bundle.cpir:
            if req["lens"] == "trade":
                built = build_v0_2_trade_graph(
                    csir=bundle.csir,
                    cpir=bundle.cpir,
                    filters=filters,
                )
            else:
                built = build_v0_2_system_graph(
                    csir=bundle.csir,
                    cpir=bundle.cpir,
                    granularity=req["granularity"],
                    commodity_view=req["commodity_view"],
                    filters=filters,
                )
                _attach_system_inspectors(
                    built,
                    source=source,
                    file_path=file_path,
                    run_id=run_id,
                    csir=bundle.csir,
                    cpir=bundle.cpir,
                    explain=bundle.explain,
                    tableir=bundle.tableir,
                    manifest=None,
                )
            return {
                "version": "1",
                "status": "ok",
                "mode_used": mode_used,
                "artifacts": artifacts,
                "graph": built["graph"],
                "facets": {**built["facets"], "runs": facets["runs"]},
                "diagnostics": diagnostics,
                "details": built["details"],
            }
        diagnostics.append(
            _diagnostic(
                "V0_2_ARTIFACTS_UNAVAILABLE",
                "error",
                "v0.2 source compilation did not produce CSIR/CPIR artifacts.",
            )
        )
        return _empty_response(req["mode"], diagnostics, facets=facets)

    compiled = resolve_compiled_artifacts(
        file_path=file_path,
        workspace_root=file_path.parent,
        case_name=req["filters"].get("case"),
        run_id=run_id,
        truth=req["compiled"].get("truth", "auto"),
        use_cache=req["compiled"].get("cache", True),
    )
    diagnostics.extend(compiled.diagnostics)
    artifacts.update(compiled.artifacts)
    if compiled.csir is not None and compiled.cpir is not None:
        if req["lens"] == "trade":
            built = build_v0_2_trade_graph(
                csir=compiled.csir,
                cpir=compiled.cpir,
                filters=filters,
            )
        else:
            built = build_v0_2_system_graph(
                csir=compiled.csir,
                cpir=compiled.cpir,
                granularity=req["granularity"],
                commodity_view=req["commodity_view"],
                filters=filters,
            )
            _attach_system_inspectors(
                built,
                source=source,
                file_path=file_path,
                run_id=run_id,
                csir=compiled.csir,
                cpir=compiled.cpir,
                explain=compiled.explain,
                tableir=compiled.tableir,
                manifest=compiled.manifest,
            )
        status = compiled.status
    elif req["compiled"].get("allow_partial", True):
        mode_used = "source"
        try:
            bundle = compile_vedalang_bundle(
                source,
                validate=True,
                selected_run=run_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            diagnostics.append(
                _diagnostic(
                    "COMPILED_GRAPH_UNAVAILABLE",
                    "error",
                    f"Compiled graph unavailable and source fallback failed: {exc}",
                )
            )
            return _empty_response(mode_used, diagnostics, facets=facets)
        built = (
            build_v0_2_trade_graph(
                csir=bundle.csir,
                cpir=bundle.cpir,
                filters=filters,
            )
            if req["lens"] == "trade"
            else build_v0_2_system_graph(
                csir=bundle.csir or {},
                cpir=bundle.cpir or {},
                granularity=req["granularity"],
                commodity_view=req["commodity_view"],
                filters=filters,
            )
        )
        if req["lens"] != "trade":
            _attach_system_inspectors(
                built,
                source=source,
                file_path=file_path,
                run_id=run_id,
                csir=bundle.csir,
                cpir=bundle.cpir,
                explain=bundle.explain,
                tableir=bundle.tableir,
                manifest=None,
            )
        status = "partial"
        diagnostics.append(
            _diagnostic(
                "COMPILED_SOURCE_FALLBACK",
                "warning",
                "Compiled artifacts unavailable; returned v0.2 source-mode "
                "graph fallback.",
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
        return _empty_response(mode_used, diagnostics, facets=facets)

    if req["lens"] == "trade":
        graph = built.get("graph", {})
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges = graph.get("edges", []) if isinstance(graph, dict) else []
        if not nodes and not edges and not _networks_configured(source):
            diagnostics.append(
                _diagnostic(
                    "NO_NETWORKS",
                    "warning",
                    "Trade lens is empty because the v0.2 source defines no "
                    "networks with links.",
                )
            )

    return {
        "version": "1",
        "status": status,
        "mode_used": mode_used,
        "artifacts": artifacts,
        "graph": built["graph"],
        "facets": {**built["facets"], "runs": facets["runs"]},
        "diagnostics": diagnostics,
        "details": built["details"],
    }


def _sanitize_mermaid_id(node_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in node_id)


def response_to_mermaid(response: dict[str, Any]) -> str:
    """Render a query response graph as Mermaid flowchart syntax."""
    lines = ["flowchart LR"]
    details_nodes = response.get("details", {}).get("nodes", {})

    for node in response.get("graph", {}).get("nodes", []):
        node_raw_id = str(node.get("id", ""))
        node_id = _sanitize_mermaid_id(str(node.get("id", "")))
        node_type = str(node.get("type", ""))
        label = str(node.get("label", node.get("id", "")))
        detail = (
            details_nodes.get(node_raw_id, {})
            if isinstance(details_nodes, dict)
            else {}
        )
        stage = detail.get("stage") if isinstance(detail, dict) else None
        if node_type in {"role", "instance"} and isinstance(stage, str) and stage:
            label = f"{label}\\n[{stage_label(stage)}]"
        label = label.replace('"', "\\\"")
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
