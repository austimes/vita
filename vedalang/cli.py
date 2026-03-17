"""User-facing CLI for VedaLang model authors.

This CLI provides intuitive commands for:
- Linting VedaLang source files
- Compiling VedaLang to Excel
- Validating with xl2times
"""

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from yaml.nodes import MappingNode, Node, SequenceNode

from vedalang.compiler.compiler import (
    SemanticValidationError,
    compile_vedalang_bundle,
    load_vedalang,
    validate_vedalang,
)
from vedalang.compiler.resolution import ResolutionError
from vedalang.compiler.schema_diagnostics import required_description_diagnostic
from vedalang.lint.code_categories import (
    CATEGORY_RUNNERS as CODE_CATEGORY_RUNNERS,
)
from vedalang.lint.code_categories import (
    collect_structural_by_category,
)
from vedalang.lint.diagnostics import build_summary, severity_counts, with_meta
from vedalang.lint.llm_categories import CATEGORY_RUNNERS as LLM_CATEGORY_RUNNERS
from vedalang.lint.llm_runtime import LLMRuntimeConfig, canonical_model_name
from vedalang.lint.registry import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_ORDER,
    CODE_CHECKS,
    checks_for_engine,
    normalize_categories,
)
from vedalang.versioning import CHECK_OUTPUT_VERSION, DSL_VERSION

FMT_DIR_IGNORES = {
    ".beads",
    ".dolt",
    ".git",
    ".venv",
    "node_modules",
    "output",
    "output_invalid",
    "tmp",
}


def main():
    parser = argparse.ArgumentParser(
        prog="vedalang",
        description="VedaLang CLI - author and validate energy system models",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_lint_parser(subparsers)
    _add_llm_lint_parser(subparsers)
    _add_fmt_parser(subparsers)
    _add_compile_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_res_parser(subparsers)
    _add_viz_parser(subparsers)

    args = parser.parse_args()

    if args.command == "lint":
        sys.exit(cmd_lint(args))
    elif args.command == "llm-lint":
        sys.exit(cmd_llm_lint(args))
    elif args.command == "fmt":
        sys.exit(cmd_fmt(args))
    elif args.command == "compile":
        sys.exit(cmd_compile(args))
    elif args.command == "validate":
        sys.exit(cmd_validate(args))
    elif args.command == "res":
        if args.res_command == "query":
            sys.exit(cmd_res_query(args))
        elif args.res_command == "mermaid":
            sys.exit(cmd_res_mermaid(args))
        _error("Unknown res subcommand", as_json=True, source="res")
        sys.exit(2)
    elif args.command == "viz":
        sys.exit(cmd_viz(args))


def _add_lint_parser(subparsers):
    p = subparsers.add_parser(
        "lint",
        help="Lint a VedaLang source file",
        description="Run deterministic lint checks with category selection.",
    )
    p.add_argument(
        "file",
        type=Path,
        nargs="?",
        help="Path to VedaLang source (.veda.yaml)",
    )
    p.add_argument(
        "--category",
        action="append",
        help=(
            "Lint category to run (repeatable): "
            "core, identity, structure, units, emissions, feasibility"
        ),
    )
    p.add_argument(
        "--list-categories",
        action="store_true",
        help="List available lint categories",
    )
    p.add_argument(
        "--list-checks",
        action="store_true",
        help="List deterministic checks grouped by category",
    )
    p.add_argument("--json", action="store_true", help="Output JSON format")
    p.add_argument(
        "--res-json",
        type=Path,
        metavar="PATH",
        help="Export normalized RES graph as JSON to the given path",
    )
    p.add_argument(
        "--res-mermaid",
        type=Path,
        metavar="PATH",
        help="Export RES graph as Mermaid diagram to the given path",
    )


def _add_llm_lint_parser(subparsers):
    p = subparsers.add_parser(
        "llm-lint",
        help="Run advisory LLM lint checks by category",
        description=(
            "Run LLM-backed lint checks using the shared lint taxonomy. "
            "Unsupported categories are reported as skipped."
        ),
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument(
        "--category",
        action="append",
        help=(
            "Lint category to run (repeatable): "
            "core, identity, structure, units, emissions, feasibility"
        ),
    )
    p.add_argument(
        "--component",
        action="append",
        help="Specific component to check for component-scoped categories",
    )
    p.add_argument(
        "--model",
        action="append",
        help=(
            "LLM model selection (repeatable for quorum-capable checks; "
            "default is gpt-5-nano)."
        ),
    )
    p.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh"],
        default="low",
        help="Reasoning effort for LLM calls (default: low).",
    )
    p.add_argument(
        "--prompt-version",
        default=None,
        help=(
            "Prompt version to use for supported checks (or 'all'). "
            "Default: latest available version per check."
        ),
    )
    p.add_argument(
        "--request-timeout-sec",
        type=int,
        default=120,
        help="Request timeout in seconds for each LLM call (default: 120).",
    )
    p.add_argument(
        "--store",
        type=Path,
        help="Path to sidecar certification store (default: <source>.unit_checks.json)",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="For units category: check all components, not only pending/current",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="For units category: re-check even certified components",
    )
    p.add_argument(
        "--advisory",
        action="store_true",
        help="Do not fail with exit code 2 when critical findings are present",
    )
    p.add_argument("--json", action="store_true", help="Output JSON format")


def _add_compile_parser(subparsers):
    p = subparsers.add_parser(
        "compile",
        help="Compile VedaLang to Excel",
        description="Compile VedaLang source to TableIR and emit Excel files.",
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument("--out", type=Path, help="Output directory for Excel files")
    p.add_argument("--tableir", type=Path, help="Also output TableIR YAML file")
    p.add_argument(
        "--case",
        action="append",
        help="Compile only the specified case (repeatable)",
    )
    p.add_argument(
        "--run",
        help="Compile the specified run",
    )
    p.add_argument("--no-lint", action="store_true", help="Skip linting before compile")
    p.add_argument("--json", action="store_true", help="Output JSON format")


def _add_fmt_parser(subparsers):
    p = subparsers.add_parser(
        "fmt",
        help="Format VedaLang YAML source files",
        description=(
            "Format .veda.yaml files using Prettier. "
            "Use --check for non-mutating CI checks."
        ),
    )
    p.add_argument(
        "paths",
        type=Path,
        nargs="+",
        help="File(s) or directory path(s) containing .veda.yaml source files",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Check formatting without modifying files",
    )
    p.add_argument("--json", action="store_true", help="Output JSON format")


def _add_validate_parser(subparsers):
    p = subparsers.add_parser(
        "validate",
        help="Compile and validate with xl2times",
        description="Compile and run xl2times validation for the selected run.",
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument(
        "--case",
        action="append",
        help="Validate only the specified case (repeatable)",
    )
    p.add_argument(
        "--run",
        help="Validate the specified run",
    )
    p.add_argument("--json", action="store_true", help="Output JSON format")
    p.add_argument(
        "--keep-workdir", action="store_true", help="Keep temp directory for debugging"
    )
def _add_res_parser(subparsers):
    p = subparsers.add_parser(
        "res",
        help="Query RES graph views (agent-first JSON API)",
        description=(
            "Unified RES query interface for source/compiled graph projections."
        ),
    )
    res_subparsers = p.add_subparsers(dest="res_command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    common.add_argument(
        "--mode",
        choices=["source", "compiled"],
        default="compiled",
        help="Graph source mode (default: compiled)",
    )
    common.add_argument(
        "--granularity",
        choices=["role", "instance"],
        default="role",
        help="Node granularity (default: role)",
    )
    common.add_argument(
        "--commodity-view",
        choices=["scoped", "collapse_scope"],
        default=None,
        help=(
            "Commodity rendering mode (default: collapse_scope except "
            "instance= scoped)"
        ),
    )
    common.add_argument(
        "--lens",
        choices=["system", "trade"],
        default="system",
        help="Graph lens (default: system)",
    )
    common.add_argument(
        "--run",
        default=None,
        help="Optional run selection for multi-run sources",
    )
    common.add_argument(
        "--region",
        action="append",
        default=[],
        help="Region filter (repeatable); default is all model regions",
    )
    common.add_argument("--case", default=None, help="Optional case filter")
    common.add_argument(
        "--sector",
        action="append",
        default=[],
        help="Sector filter (repeatable)",
    )
    common.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Scope filter (repeatable)",
    )
    common.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable compiled artifact cache",
    )
    common.add_argument(
        "--strict-compiled",
        action="store_true",
        help="Disable source fallback when compiled artifacts are unavailable",
    )

    query = res_subparsers.add_parser(
        "query",
        parents=[common],
        help="Return RES query JSON response",
    )
    query.add_argument("--json", action="store_true", help="Output JSON format")

    mermaid = res_subparsers.add_parser(
        "mermaid",
        parents=[common],
        help="Return Mermaid projection of RES query response",
    )
    mermaid.add_argument("--json", action="store_true", help="Output JSON format")


def _add_viz_parser(subparsers):
    p = subparsers.add_parser(
        "viz",
        help="Visualize the Reference Energy System",
        description="Open a real-time browser visualization of the RES.",
    )
    p.add_argument(
        "file",
        type=Path,
        nargs="?",
        help="Optional path to VedaLang source (.veda.yaml)",
    )
    p.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    p.add_argument(
        "--no-browser", action="store_true", help="Don't auto-open browser"
    )
    p.add_argument(
        "--run",
        default=None,
        help="Initial run selection for multi-run sources",
    )
    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mermaid", action="store_true", help="Output Mermaid syntax instead of web UI"
    )
    mode_group.add_argument(
        "--stop",
        action="store_true",
        help="Stop a running viz server on the selected port and exit",
    )
    mode_group.add_argument(
        "--status",
        action="store_true",
        help="Print viz server status for the selected port and exit",
    )
    p.add_argument(
        "--variants", action="store_true", help="Include process variants in diagram"
    )
    p.add_argument(
        "--granularity",
        choices=["role", "instance"],
        default=None,
        help="Node granularity for --mermaid output (default: role)",
    )
    p.add_argument(
        "--commodity-view",
        choices=["scoped", "collapse_scope"],
        default=None,
        help="Commodity rendering mode for --mermaid",
    )
    p.add_argument(
        "--debug", action="store_true", help="Print debug info about nodes and edges"
    )


def _print_lint_categories(output_json: bool) -> None:
    data = [
        {
            "category": cat,
            "description": CATEGORY_DESCRIPTIONS[cat],
        }
        for cat in CATEGORY_ORDER
    ]
    if output_json:
        print(json.dumps({"categories": data}, indent=2))
        return
    print("Lint categories:")
    for item in data:
        print(f"  - {item['category']}: {item['description']}")


def _print_lint_checks(output_json: bool) -> None:
    grouped: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_ORDER}
    for check in CODE_CHECKS:
        grouped[check.category].append(
            {
                "check_id": check.check_id,
                "scope": check.scope,
            }
        )
    if output_json:
        print(json.dumps({"checks": grouped}, indent=2))
        return
    print("Deterministic lint checks:")
    for category in CATEGORY_ORDER:
        checks = grouped.get(category, [])
        if not checks:
            continue
        print(f"  {category}:")
        for c in checks:
            print(f"    - {c['check_id']} (scope={c['scope']})")


def cmd_lint(args) -> int:
    """Run deterministic lint checks with category selection."""
    output_json: bool = args.json
    requested_categories = getattr(args, "category", None)
    list_categories: bool = getattr(args, "list_categories", False)
    list_checks: bool = getattr(args, "list_checks", False)
    res_json_path: Path | None = getattr(args, "res_json", None)
    res_mermaid_path: Path | None = getattr(args, "res_mermaid", None)

    if list_categories:
        _print_lint_categories(output_json)
        return 0
    if list_checks:
        _print_lint_checks(output_json)
        return 0

    file_path: Path | None = getattr(args, "file", None)
    if file_path is None:
        _error("Missing required argument: file", output_json, "<none>")
        return 2
    if not file_path.exists():
        _error(f"File not found: {file_path}", output_json, str(file_path))
        return 2

    if requested_categories:
        try:
            selected_categories = normalize_categories(requested_categories)
        except ValueError as e:
            _error(str(e), output_json, str(file_path))
            return 2
    else:
        selected_categories = []

    run_categories = (
        selected_categories if requested_categories else list(CATEGORY_ORDER)
    )
    run_category_set = set(run_categories)
    checks_run = [
        c.check_id
        for c in checks_for_engine("code")
        if c.category in run_category_set
    ]

    diagnostics: list[dict] = []
    skipped_categories: list[str] = []

    try:
        source = load_vedalang(file_path)
    except Exception as e:
        diagnostics.append(
            with_meta(
                {
                    "code": "PARSE_ERROR",
                    "severity": "error",
                    "message": f"Failed to parse YAML: {e}",
                },
                category="core",
                engine="code",
                check_id="code.core.schema_xref",
            )
        )
        errors, warnings, _ = severity_counts(diagnostics)
        summary = build_summary(
            diagnostics,
            checks_run=checks_run,
            skipped_categories=skipped_categories,
        )
        return _output_lint_result(
            file_path,
            diagnostics,
            errors,
            warnings,
            output_json,
            summary=summary,
        )

    try:
        validate_vedalang(source)
    except jsonschema.ValidationError as e:
        normalized = required_description_diagnostic(e)
        if normalized is None:
            normalized = {
                "code": "SCHEMA_ERROR",
                "severity": "error",
                "message": e.message,
                "location": _format_location_path(list(e.absolute_path)),
            }
        diagnostics.append(
            with_meta(
                normalized,
                category="core",
                engine="code",
                check_id="code.core.schema_xref",
            )
        )
        _attach_source_positions(diagnostics, source=source, file_path=file_path)
        errors, warnings, _ = severity_counts(diagnostics)
        summary = build_summary(
            diagnostics,
            checks_run=checks_run,
            skipped_categories=skipped_categories,
        )
        return _output_lint_result(
            file_path,
            diagnostics,
            errors,
            warnings,
            output_json,
            summary=summary,
        )

    structural_cache: dict[str, list[dict]] | None = None
    if run_category_set.intersection({"structure", "units", "emissions"}):
        try:
            structural_cache = collect_structural_by_category(source)
        except Exception as e:
            diagnostics.append(
                with_meta(
                    {
                        "code": "SEMANTIC_CHECK_ERROR",
                        "severity": "error",
                        "message": f"Failed to run compiler semantic checks: {e}",
                    },
                    category="structure",
                    engine="code",
                    check_id="code.structure.compiler_semantics",
                )
            )

    for category in run_categories:
        runner = CODE_CATEGORY_RUNNERS.get(category)
        if runner is None:
            continue
        if category in {"structure", "units", "emissions"}:
            diagnostics.extend(runner(source, structural_cache=structural_cache))
        else:
            diagnostics.extend(runner(source))

    # Export RES graph artifacts if requested
    if res_json_path or res_mermaid_path:
        from vedalang.lint.res_export import export_res_graph, res_graph_to_mermaid

        graph = export_res_graph(source)

        if res_json_path:
            res_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(res_json_path, "w") as f:
                json.dump(graph, f, indent=2)
                f.write("\n")
            if not output_json:
                print(f"RES graph JSON: {res_json_path}")

        if res_mermaid_path:
            mermaid = res_graph_to_mermaid(graph)
            res_mermaid_path.parent.mkdir(parents=True, exist_ok=True)
            with open(res_mermaid_path, "w") as f:
                f.write(mermaid)
                f.write("\n")
            if not output_json:
                print(f"RES Mermaid diagram: {res_mermaid_path}")

    _attach_source_positions(diagnostics, source=source, file_path=file_path)
    errors, warnings, _ = severity_counts(diagnostics)
    summary = build_summary(
        diagnostics,
        checks_run=checks_run,
        skipped_categories=skipped_categories,
    )
    return _output_lint_result(
        file_path,
        diagnostics,
        errors,
        warnings,
        output_json,
        summary=summary,
    )


def cmd_llm_lint(args) -> int:
    """Run LLM lint checks using the shared lint taxonomy."""
    file_path: Path = args.file
    output_json: bool = args.json
    requested_categories = getattr(args, "category", None)
    advisory: bool = getattr(args, "advisory", False)

    if not file_path.exists():
        _error(f"File not found: {file_path}", output_json, str(file_path))
        return 2

    try:
        selected_categories = normalize_categories(requested_categories)
    except ValueError as e:
        _error(str(e), output_json, str(file_path))
        return 2

    diagnostics: list[dict] = []
    skipped_categories: list[str] = []
    checks_run: list[str] = []
    runtime_errors = False
    unit_store_path: Path | None = None
    unit_results: list[dict] = []
    unit_skipped_components: list[str] = []
    llm_runs: list[dict] = []

    raw_models = [canonical_model_name(m) for m in (getattr(args, "model", None) or [])]
    runtime_config = LLMRuntimeConfig(
        model=raw_models[0] if raw_models else None,
        models=raw_models or None,
        reasoning_effort=getattr(args, "reasoning_effort", "medium"),
        prompt_version=getattr(args, "prompt_version", None),
        timeout_sec=getattr(args, "request_timeout_sec", 120),
    )

    try:
        source = load_vedalang(file_path)
        validate_vedalang(source)
    except Exception as e:
        _error(f"Failed to load/validate source: {e}", output_json, str(file_path))
        return 2

    for category in selected_categories:
        check = next(
            (c for c in checks_for_engine("llm") if c.category == category),
            None,
        )
        if check is None:
            skipped_categories.append(category)
            continue
        runner = LLM_CATEGORY_RUNNERS[category]
        result = runner(
            source=source,
            file_path=file_path,
            component=getattr(args, "component", None),
            run_all=getattr(args, "all", False),
            force=getattr(args, "force", False),
            store_path=getattr(args, "store", None),
            runtime_config=runtime_config,
        )
        if not result.supported:
            skipped_categories.append(category)
            continue
        checks_run.append(check.check_id)
        runtime_errors = runtime_errors or result.runtime_error
        diagnostics.extend(result.diagnostics)
        if "store_path" in result.extras and result.extras["store_path"] is not None:
            unit_store_path = result.extras["store_path"]
        unit_results.extend(result.extras.get("unit_results", []))
        unit_skipped_components.extend(
            result.extras.get("unit_skipped_components", [])
        )
        llm_runs.extend(result.extras.get("llm_runs", []))

    _attach_source_positions(diagnostics, source=source, file_path=file_path)
    errors, warnings, critical = severity_counts(diagnostics)
    summary = build_summary(
        diagnostics,
        checks_run=checks_run,
        skipped_categories=skipped_categories,
    )

    display_errors = errors + (critical if not advisory else 0)
    display_warnings = warnings + (critical if advisory else 0)

    if runtime_errors or errors > 0:
        exit_code = 2
    elif critical > 0 and not advisory:
        exit_code = 2
    elif warnings > 0 or critical > 0:
        exit_code = 1
    else:
        exit_code = 0

    if output_json:
        payload = {
            "dsl_version": DSL_VERSION,
            "artifact_version": CHECK_OUTPUT_VERSION,
            "success": exit_code == 0,
            "source": str(file_path),
            "warnings": display_warnings,
            "errors": display_errors,
            "critical": critical,
            "diagnostics": diagnostics,
            "summary": summary,
            "store": str(unit_store_path) if unit_store_path else None,
            "unit_results": unit_results,
            "skipped_certified_components": unit_skipped_components,
            "advisory": advisory,
            "runtime": {
                "model": runtime_config.model,
                "models": runtime_config.models,
                "reasoning_effort": runtime_config.reasoning_effort,
                "prompt_version": runtime_config.prompt_version or "latest",
                "request_timeout_sec": runtime_config.timeout_sec,
            },
            "llm_runs": llm_runs,
        }
        print(json.dumps(payload, indent=2))
    else:
        _output_lint_result(
            file_path,
            diagnostics,
            display_errors,
            display_warnings,
            output_json=False,
            summary=summary,
        )

    return exit_code


_LOCATION_SEGMENT_RE = re.compile(r"^(?P<key>[^\[\]]+)(?P<idx>(?:\[[^\]]+\])*)$")
_LOCATION_INDEX_RE = re.compile(r"\[([^\]]+)\]")
_LIST_ID_KEYS = (
    "id",
    "name",
    "commodity",
    "process",
    "role",
    "variant",
    "case",
    "parameter",
    "attribute",
    "region",
    "code",
)


def _split_location_segments(location: str) -> list[str]:
    """Split dotted location path while preserving bracket contents."""
    out: list[str] = []
    depth = 0
    token_chars: list[str] = []
    for ch in location.strip():
        if ch == "." and depth == 0:
            if token_chars:
                out.append("".join(token_chars))
                token_chars = []
            continue
        if ch == "[":
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
        token_chars.append(ch)
    if token_chars:
        out.append("".join(token_chars))
    return out


def _parse_location_steps(location: str) -> list[tuple[str, str | int]]:
    """Parse location text into key/index traversal steps."""
    if not location or location == "root":
        return []
    steps: list[tuple[str, str | int]] = []
    for segment in _split_location_segments(location):
        match = _LOCATION_SEGMENT_RE.match(segment)
        if match is None:
            return []
        key = match.group("key")
        if key:
            steps.append(("key", key))
        for raw_idx in _LOCATION_INDEX_RE.findall(match.group("idx") or ""):
            idx = raw_idx.strip().strip("'\"")
            if idx.isdigit():
                steps.append(("index", int(idx)))
            elif idx:
                steps.append(("index", idx))
    return steps


def _format_location_path(path_tokens: list[str | int]) -> str:
    """Convert jsonschema path tokens to location format."""
    if not path_tokens:
        return "root"
    parts: list[str] = []
    for token in path_tokens:
        if isinstance(token, int):
            if not parts:
                parts.append(f"[{token}]")
            else:
                parts[-1] = f"{parts[-1]}[{token}]"
            continue
        parts.append(token)
    return ".".join(parts)


def _find_list_item_index(items: list, label: str) -> int | None:
    """Find list index for string labels used in location bracket notation."""
    if label.isdigit():
        idx = int(label)
        return idx if 0 <= idx < len(items) else None
    for idx, item in enumerate(items):
        if isinstance(item, dict):
            for key in _LIST_ID_KEYS:
                value = item.get(key)
                if value is not None and str(value) == label:
                    return idx
        elif str(item) == label:
            return idx
    return None


def _resolve_location_to_runtime_path(
    source: dict,
    location: str,
) -> list[str | int] | None:
    """Resolve a location string to concrete dict/list traversal path."""
    steps = _parse_location_steps(location)
    if not steps and location not in {"", "root"}:
        return None
    current: object = source
    runtime_path: list[str | int] = []
    for kind, token in steps:
        if kind == "key":
            if not isinstance(current, dict) or token not in current:
                return None
            runtime_path.append(token)
            current = current[token]
            continue

        # kind == "index"
        if isinstance(token, int):
            if not isinstance(current, list) or token < 0 or token >= len(current):
                return None
            runtime_path.append(token)
            current = current[token]
            continue

        if isinstance(current, list):
            idx = _find_list_item_index(current, token)
            if idx is None:
                return None
            runtime_path.append(idx)
            current = current[idx]
            continue

        if isinstance(current, dict) and token in current:
            runtime_path.append(token)
            current = current[token]
            continue

        return None
    return runtime_path


def _yaml_node_for_path(root: Node, path: list[str | int]) -> Node | None:
    """Traverse YAML AST node by runtime path."""
    node: Node | None = root
    for token in path:
        if isinstance(token, str):
            if not isinstance(node, MappingNode):
                return None
            matched: Node | None = None
            for key_node, value_node in node.value:
                if key_node.value == token:
                    matched = value_node
                    break
            if matched is None:
                return None
            node = matched
            continue

        if not isinstance(node, SequenceNode):
            return None
        if token < 0 or token >= len(node.value):
            return None
        node = node.value[token]
    return node


def _build_source_excerpt(
    source_lines: list[str],
    *,
    line: int,
    end_line: int,
    column: int,
    max_lines: int = 5,
) -> dict | None:
    """Build compact source excerpt for diagnostics."""
    if not source_lines:
        return None

    start_line = max(1, line - 1)
    finish_line = min(len(source_lines), end_line + 1)
    if finish_line - start_line + 1 > max_lines:
        finish_line = start_line + max_lines - 1

    lines: list[dict] = []
    for ln in range(start_line, finish_line + 1):
        lines.append({"line": ln, "text": source_lines[ln - 1]})

    return {
        "start_line": start_line,
        "end_line": finish_line,
        "caret_line": line,
        "caret_column": max(1, column),
        "lines": lines,
    }


def _attach_source_positions(
    diagnostics: list[dict],
    *,
    source: dict,
    file_path: Path,
) -> None:
    """Attach line/column/source excerpt metadata to diagnostics when possible."""
    if not diagnostics:
        return

    try:
        source_text = file_path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — file unreadable; skip position enrichment
        return

    try:
        root = yaml.compose(source_text)
    except yaml.YAMLError:
        return
    if root is None:
        return

    source_lines = source_text.splitlines()
    for diag in diagnostics:
        raw_location = diag.get("location") or diag.get("path")
        if not isinstance(raw_location, str) or not raw_location:
            continue

        runtime_path = _resolve_location_to_runtime_path(source, raw_location)
        if runtime_path is None:
            continue
        node = _yaml_node_for_path(root, runtime_path)
        if node is None:
            continue

        line = node.start_mark.line + 1
        column = node.start_mark.column + 1
        end_line = max(line, node.end_mark.line + 1)
        end_column = max(1, node.end_mark.column + 1)

        diag["line"] = line
        diag["column"] = column
        diag["end_line"] = end_line
        diag["end_column"] = end_column
        diag["source_excerpt"] = _build_source_excerpt(
            source_lines,
            line=line,
            end_line=end_line,
            column=column,
        )
        if "location" not in diag and "path" in diag:
            diag["location"] = diag["path"]


def _split_fenced_code_blocks(text: str) -> list[dict]:
    """Split a markdown-ish string into alternating text/code segments."""
    import re

    if not text:
        return []

    fence_re = re.compile(
        r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<code>.*?)\n```", re.DOTALL
    )
    out: list[dict] = []
    pos = 0
    for m in fence_re.finditer(text):
        if m.start() > pos:
            chunk = text[pos : m.start()]
            if chunk.strip():
                out.append({"kind": "text", "text": chunk.strip("\n")})
        lang = (m.group("lang") or "").strip() or "text"
        code = (m.group("code") or "").rstrip("\n")
        out.append({"kind": "code", "lang": lang, "code": code})
        pos = m.end()

    tail = text[pos:]
    if tail.strip():
        out.append({"kind": "text", "text": tail.strip("\n")})

    return out


def _format_finding_rich(finding: dict, index: int, total: int):
    """Render a single lint/LLM finding as a Rich Panel."""
    from rich import box
    from rich.console import Group
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text

    severity_raw = (finding.get("severity") or "warning").lower().strip()
    code = finding.get("code") or "UNKNOWN"
    category = finding.get("category")
    message = finding.get("message") or ""
    location = finding.get("location")
    line = finding.get("line")
    column = finding.get("column")
    source_excerpt = finding.get("source_excerpt")
    suggestion = finding.get("suggestion")

    if severity_raw in ("critical", "error"):
        badge_text = severity_raw.upper()
        badge_style = "bold white on red"
        border_style = "red"
    elif severity_raw == "warning":
        badge_text = "WARNING"
        badge_style = "bold black on yellow"
        border_style = "yellow"
    else:
        badge_text = "SUGGESTION"
        badge_style = "bold black on cyan"
        border_style = "cyan"

    # Header row: badge + code + category | index
    header = Table.grid(padding=(0, 1))
    header.expand = True
    header.add_column("left", ratio=1)
    header.add_column("right", justify="right")

    left_bits = Text.assemble(
        (f" {badge_text} ", badge_style),
        ("  ", ""),
        (f"[{code}]", "bold"),
    )
    if category:
        left_bits.append(f"  ({category})", style="dim")

    header.add_row(left_bits, Text(f"{index}/{total}", style="dim"))

    body_items: list = [header]

    if location:
        if isinstance(line, int) and isinstance(column, int):
            body_items.append(
                Text(f"Location: {location} (line {line}:{column})", style="dim")
            )
        elif isinstance(line, int):
            body_items.append(Text(f"Location: {location} (line {line})", style="dim"))
        else:
            body_items.append(Text(f"Location: {location}", style="dim"))

    body_items.append(Rule(style="dim"))

    # Message — render markdown for inline `code` formatting
    body_items.append(Markdown(message.strip() or " ", code_theme="monokai"))

    if isinstance(source_excerpt, dict):
        excerpt_lines = source_excerpt.get("lines") or []
        if isinstance(excerpt_lines, list) and excerpt_lines:
            body_items.append(Rule("Source", style="dim"))
            block = Text()
            caret_line = source_excerpt.get("caret_line")
            caret_column = source_excerpt.get("caret_column")
            for row in excerpt_lines:
                line_no = row.get("line")
                line_text = row.get("text")
                if not isinstance(line_no, int) or not isinstance(line_text, str):
                    continue
                block.append(f"{line_no:>5} | ", style="dim")
                block.append(line_text)
                block.append("\n")
                if (
                    isinstance(caret_line, int)
                    and caret_line == line_no
                    and isinstance(caret_column, int)
                ):
                    block.append("      | ", style="dim")
                    block.append(" " * max(0, caret_column - 1))
                    block.append("^", style="bold red")
                    block.append("\n")
            if block:
                body_items.append(
                    Panel(
                        block,
                        border_style="dim",
                        box=box.ROUNDED,
                        padding=(0, 1),
                    )
                )

    # Fix / suggestion section
    if suggestion:
        body_items.append(Rule("Fix", style="green"))
        for part in _split_fenced_code_blocks(suggestion):
            if part["kind"] == "text":
                txt = part["text"].strip()
                if txt:
                    body_items.append(Markdown(txt, code_theme="monokai"))
            else:
                lang = part.get("lang") or "text"
                code_txt = part.get("code") or ""
                syn = Syntax(
                    code_txt, lang, theme="monokai",
                    line_numbers=False, word_wrap=False,
                )
                body_items.append(Panel(
                    syn,
                    title=lang,
                    border_style="dim",
                    box=box.ROUNDED,
                    padding=(0, 1),
                ))

    return Panel(
        Group(*body_items),
        border_style=border_style,
        box=box.ROUNDED,
        padding=(1, 1),
    )


def _output_lint_result(
    file_path: Path,
    diagnostics: list[dict],
    errors: int,
    warnings: int,
    output_json: bool,
    *,
    llm_model: str | None = None,
    summary: dict | None = None,
) -> int:
    """Output lint results and return exit code."""
    success = errors == 0

    if output_json:
        result = {
            "dsl_version": DSL_VERSION,
            "artifact_version": CHECK_OUTPUT_VERSION,
            "success": success,
            "source": str(file_path),
            "warnings": warnings,
            "errors": errors,
            "diagnostics": diagnostics,
        }
        if llm_model:
            result["llm_model"] = llm_model
        if summary is not None:
            result["summary"] = summary
        print(json.dumps(result, indent=2))
    else:
        try:
            from rich import box
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table
            from rich.text import Text

            console = Console()

            # Header panel
            header_tbl = Table.grid(expand=True)
            header_tbl.add_column("left", ratio=1)
            header_tbl.add_column("right", justify="right")
            header_tbl.add_row(
                Text("VedaLang Lint", style="bold"),
                Text(str(file_path), style="dim"),
            )
            if llm_model:
                header_tbl.add_row(
                    Text("LLM model", style="dim"),
                    Text(llm_model, style="dim"),
                )
            console.print(Panel(
                header_tbl,
                box=box.ROUNDED,
                border_style="blue",
                padding=(1, 1),
            ))

            # Findings
            if diagnostics:
                total = len(diagnostics)
                for i, d in enumerate(diagnostics, start=1):
                    console.print(_format_finding_rich(d, i, total))
                    console.print()

            # Summary bar
            summary_tbl = Table.grid(expand=True)
            summary_tbl.add_column("left", ratio=1)
            summary_tbl.add_column("right", justify="right")

            left = Text.assemble(
                ("Summary: ", "bold"),
                (
                    f"{errors} error(s)",
                    "bold red" if errors else "dim",
                ),
                ("  ", ""),
                (
                    f"{warnings} warning(s)",
                    "bold yellow" if warnings else "dim",
                ),
            )

            sev_counts: dict[str, int] = {}
            for d in diagnostics:
                sev = (d.get("severity") or "warning").lower().strip()
                sev_counts[sev] = sev_counts.get(sev, 0) + 1
            if sev_counts.get("critical"):
                left.append("  ")
                left.append(
                    f"{sev_counts['critical']} critical",
                    style="bold red",
                )
            if sev_counts.get("suggestion"):
                left.append("  ")
                left.append(
                    f"{sev_counts['suggestion']} suggestion(s)",
                    style="bold cyan",
                )

            right = (
                Text("✓ OK", style="bold green")
                if success
                else Text("✗ Issues found", style="bold red")
            )
            summary_tbl.add_row(left, right)

            console.print(Panel(
                summary_tbl,
                box=box.ROUNDED,
                border_style="green" if success else "red",
                padding=(1, 1),
            ))

            if summary is not None:
                skipped = summary.get("skipped_categories", [])
                if skipped:
                    console.print(f"Skipped categories: {', '.join(skipped)}")

        except ImportError:
            # Plain-text fallback
            if diagnostics:
                for d in diagnostics:
                    severity = d["severity"].upper()
                    code = d["code"]
                    msg = d["message"]
                    loc = d.get("location", "")
                    loc_str = f" ({loc})" if loc else ""
                    print(f"{severity} [{code}]{loc_str}: {msg}")
                    suggestion = d.get("suggestion")
                    if suggestion:
                        print(f"  ↳ Fix: {suggestion}")
                print()

            print(f"Lint: {errors} error(s), {warnings} warning(s)")
            if summary is not None and summary.get("skipped_categories"):
                print(
                    "Skipped categories: "
                    + ", ".join(summary.get("skipped_categories", []))
                )
            if llm_model:
                print(f"LLM model: {llm_model}")
            if success:
                print(f"✓ {file_path}")

    if errors > 0:
        return 2
    elif warnings > 0:
        return 1
    return 0


def _is_yaml_file(path: Path) -> bool:
    return path.suffix.lower() in {".yaml", ".yml"}


FMT_ROOT_KEY_ORDER = (
    "dsl_version",
    "imports",
    "commodities",
    "technologies",
    "technology_roles",
    "stock_characterizations",
    "spatial_layers",
    "spatial_measure_sets",
    "temporal_index_series",
    "region_partitions",
    "zone_overlays",
    "sites",
    "facilities",
    "fleets",
    "zone_opportunities",
    "networks",
    "runs",
)

FMT_GENERIC_KEY_ORDER = (
    "id",
    "name",
    "description",
    "type",
    "role",
    "variant",
    "commodity",
    "emission",
    "region",
    "origin",
    "destination",
    "unit",
    "activity_unit",
    "capacity_unit",
    "stage",
    "inputs",
    "outputs",
    "required_inputs",
    "required_outputs",
    "emission_factors",
    "timeslices",
    "years",
    "values",
)

FMT_PATH_KEY_ORDER: dict[tuple[str, ...], tuple[str, ...]] = {
    (): FMT_ROOT_KEY_ORDER,
}

FMT_LIST_SORT_KEYS = (
    "id",
    "name",
    "code",
    "variant",
    "role",
    "commodity",
    "emission",
    "region",
    "origin",
    "destination",
    "type",
    "selector",
    "year",
)

FMT_SCALAR_LIST_LAST_KEYS = {
    "regions",
    "milestone_years",
    "sectors",
    "end_uses",
    "required_inputs",
    "required_outputs",
    "processes",
    "cases",
    "includes",
    "excludes",
}

FMT_MAP_ITEM_RE = re.compile(r"^\s*-\s+[^#:\n][^:\n]*:\s*.*$")


def _is_int_like(value: Any) -> bool:
    if isinstance(value, int):
        return True
    if not isinstance(value, str):
        return False
    return value.isdigit() or (value.startswith("-") and value[1:].isdigit())


def _scalar_sort_key(value: Any) -> tuple[int, int | float | str]:
    if isinstance(value, bool):
        return (2, str(value).lower())
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, str) and _is_int_like(value):
        return (0, int(value))
    return (1, str(value))


def _mapping_key_rank(key: str, path: tuple[str, ...]) -> tuple[int, int | str]:
    specific = FMT_PATH_KEY_ORDER.get(path, ())
    if key in specific:
        return (0, specific.index(key))
    if key in FMT_GENERIC_KEY_ORDER:
        return (1, FMT_GENERIC_KEY_ORDER.index(key))
    return (2, key)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sort_mapping_keys(
    data: dict[str, Any], path: tuple[str, ...]
) -> list[tuple[str, Any]]:
    return sorted(data.items(), key=lambda kv: _mapping_key_rank(kv[0], path))


def _should_sort_scalar_list(path: tuple[str, ...], items: list[Any]) -> bool:
    if not items:
        return False
    if not all(not isinstance(item, (dict, list)) for item in items):
        return False
    return bool(path and path[-1] in FMT_SCALAR_LIST_LAST_KEYS)


def _sequence_mapping_sort_key(item: dict[str, Any]) -> tuple[int, tuple[Any, ...]]:
    for key in FMT_LIST_SORT_KEYS:
        if key in item:
            return (0, (_scalar_sort_key(item[key]), _canonical_json(item)))
    return (1, (_canonical_json(item),))


def _canonicalize_value(value: Any, path: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        canonical: dict[str, Any] = {}
        for key, raw_val in _sort_mapping_keys(value, path):
            canonical[key] = _canonicalize_value(raw_val, path + (key,))
        return canonical

    if isinstance(value, list):
        canonical_items = [_canonicalize_value(item, path + ("[]",)) for item in value]
        if not canonical_items:
            return canonical_items

        if _should_sort_scalar_list(path, canonical_items):
            return sorted(canonical_items, key=_scalar_sort_key)

        if all(isinstance(item, dict) for item in canonical_items):
            if any(
                any(k in item for k in FMT_LIST_SORT_KEYS)
                for item in canonical_items
            ):
                return sorted(canonical_items, key=_sequence_mapping_sort_key)

        return canonical_items

    return value


def _insert_readability_blank_lines(source: str) -> str:
    lines = source.splitlines()
    if not lines:
        return ""

    out: list[str] = []
    seen_top_level_key = False
    seen_mapping_items_by_indent: dict[int, bool] = {}

    for raw_line in lines:
        if not raw_line.strip():
            if out and out[-1] != "":
                out.append("")
            continue

        stripped = raw_line.lstrip(" ")
        indent = len(raw_line) - len(stripped)
        is_top_level_key = (
            indent == 0 and not stripped.startswith("-") and ":" in stripped
        )

        # Clear list-item tracking when indentation decreases.
        for known_indent in list(seen_mapping_items_by_indent):
            if known_indent > indent:
                seen_mapping_items_by_indent.pop(known_indent, None)

        if is_top_level_key:
            if seen_top_level_key and out and out[-1] != "":
                out.append("")
            seen_top_level_key = True

        is_mapping_item = bool(FMT_MAP_ITEM_RE.match(raw_line))
        if is_mapping_item:
            if (
                seen_mapping_items_by_indent.get(indent, False)
                and out
                and out[-1] != ""
            ):
                out.append("")
            seen_mapping_items_by_indent[indent] = True
        elif stripped.startswith("-"):
            # Scalar list item at this depth; do not add extra spacing.
            seen_mapping_items_by_indent.pop(indent, None)
        else:
            seen_mapping_items_by_indent.pop(indent, None)

        out.append(raw_line)

    normalized = "\n".join(out).strip()
    if not normalized:
        return ""
    return normalized + "\n"


def _canonicalize_yaml_text(source: str) -> str | None:
    try:
        parsed = yaml.safe_load(source)
    except yaml.YAMLError:
        return None

    canonical = _canonicalize_value(parsed, ())
    dumped = yaml.safe_dump(
        canonical,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    return _insert_readability_blank_lines(dumped)


def _apply_yaml_canonicalization(
    targets: list[Path],
    *,
    check_only: bool,
    prettier_command: list[str],
    repo_root: Path,
) -> list[Path]:
    drifted: list[Path] = []

    for target in targets:
        original = target.read_text(encoding="utf-8")
        canonical = _canonicalize_yaml_text(original)
        if canonical is None:
            continue
        formatted = _prettier_format_text(
            prettier_command,
            source=canonical,
            repo_root=repo_root,
            filepath_hint=target,
        )
        expected = formatted if formatted is not None else canonical
        if expected == original:
            continue
        drifted.append(target)
        if not check_only:
            target.write_text(expected, encoding="utf-8")

    return drifted


def _collect_fmt_targets(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    targets: list[Path] = []
    missing: list[Path] = []
    seen: set[str] = set()

    for raw_path in paths:
        path = raw_path.resolve()
        if not path.exists():
            missing.append(raw_path)
            continue

        if path.is_file():
            if not _is_yaml_file(path):
                continue
            key = str(path)
            if key not in seen:
                seen.add(key)
                targets.append(path)
            continue

        if path.is_dir():
            for file_path in sorted(path.rglob("*.veda.yaml")) + sorted(
                path.rglob("*.veda.yml")
            ):
                if any(part in FMT_DIR_IGNORES for part in file_path.parts):
                    continue
                key = str(file_path)
                if key not in seen:
                    seen.add(key)
                    targets.append(file_path)

    return targets, missing


def _resolve_prettier_command(repo_root: Path) -> list[str] | None:
    local_bin_name = "prettier.cmd" if sys.platform == "win32" else "prettier"
    local_bin = repo_root / "node_modules" / ".bin" / local_bin_name
    if local_bin.exists():
        return [str(local_bin)]

    if shutil.which("prettier"):
        return ["prettier"]

    return None


def _run_prettier(
    command: list[str],
    *,
    check_only: bool,
    targets: list[Path],
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    mode_flag = "--check" if check_only else "--write"
    args = [
        *command,
        "--parser",
        "yaml",
        "--log-level",
        "warn",
        mode_flag,
        *[str(t) for t in targets],
    ]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )


def _prettier_format_text(
    command: list[str], *, source: str, repo_root: Path, filepath_hint: Path
) -> str | None:
    result = subprocess.run(
        [
            *command,
            "--parser",
            "yaml",
            "--log-level",
            "warn",
            "--stdin-filepath",
            str(filepath_hint),
        ],
        input=source,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def cmd_fmt(args) -> int:
    """Run fmt command: canonicalize + format .veda.yaml files."""
    output_json: bool = args.json
    check_only: bool = args.check
    input_paths: list[Path] = args.paths
    repo_root = Path(__file__).resolve().parent.parent

    targets, missing = _collect_fmt_targets(input_paths)

    if missing:
        message = "Path not found: " + ", ".join(str(p) for p in missing)
        if output_json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "paths": [str(p) for p in input_paths],
                        "error": message,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 2

    if not targets:
        if output_json:
            print(
                json.dumps(
                    {
                        "success": True,
                        "mode": "check" if check_only else "write",
                        "paths": [str(p) for p in input_paths],
                        "file_count": 0,
                        "files": [],
                        "changed": False,
                    },
                    indent=2,
                )
            )
        else:
            print("No .veda.yaml files found.")
        return 0

    prettier_command = _resolve_prettier_command(repo_root)
    if prettier_command is None:
        message = (
            "Prettier not found. Install formatter tooling with "
            "`bun install` in the repository root."
        )
        if output_json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "mode": "check" if check_only else "write",
                        "paths": [str(p) for p in input_paths],
                        "files": [str(p) for p in targets],
                        "file_count": len(targets),
                        "error": message,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 2

    canonical_drift = _apply_yaml_canonicalization(
        targets,
        check_only=check_only,
        prettier_command=prettier_command,
        repo_root=repo_root,
    )

    result = _run_prettier(
        prettier_command,
        check_only=check_only,
        targets=targets,
        repo_root=repo_root,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    prettier_check_drift = check_only and result.returncode == 1
    canonical_check_drift = check_only and bool(canonical_drift)
    has_check_drift = prettier_check_drift or canonical_check_drift
    success = result.returncode == 0 and not has_check_drift
    changed = (not check_only) and (result.returncode == 0)

    if output_json:
        payload = {
            "success": success,
            "mode": "check" if check_only else "write",
            "paths": [str(p) for p in input_paths],
            "files": [str(p) for p in targets],
            "file_count": len(targets),
            "changed": changed,
            "needs_formatting": has_check_drift,
            "canonical_drift_count": len(canonical_drift),
            "canonical_drift_files": [str(p) for p in canonical_drift],
            "stdout": stdout,
            "stderr": stderr,
        }
        print(json.dumps(payload, indent=2))
    else:
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)

        if check_only:
            if not has_check_drift and result.returncode == 0:
                print(f"Formatting check passed for {len(targets)} file(s).")
            elif has_check_drift:
                print(
                    "Formatting drift detected. "
                    "Run `uv run vedalang fmt <path>` to apply fixes."
                )
        elif result.returncode == 0:
            print(f"Formatted {len(targets)} file(s).")

    if result.returncode == 0:
        if check_only and has_check_drift:
            return 1
        return 0
    if check_only and result.returncode == 1:
        return 1
    return 2


def cmd_compile(args) -> int:
    """Run compile command: lint + compile to Excel."""
    file_path: Path = args.file
    out_dir: Path | None = args.out
    tableir_path: Path | None = args.tableir
    selected_cases: list[str] | None = args.case
    selected_run: str | None = args.run
    skip_lint: bool = args.no_lint
    output_json: bool = args.json

    if not file_path.exists():
        _error(f"File not found: {file_path}", output_json, str(file_path))
        return 2

    if out_dir is None and tableir_path is None:
        _error("Must specify --out or --tableir", output_json, str(file_path))
        return 2

    if not skip_lint:
        lint_args = argparse.Namespace(file=file_path, json=False)
        lint_exit = cmd_lint(lint_args)
        if lint_exit == 2:
            if output_json:
                print(json.dumps({
                    "success": False,
                    "source": str(file_path),
                    "error": "Lint errors prevent compilation",
                }))
            return 2
        print()

    try:
        source = load_vedalang(file_path)
        bundle = compile_vedalang_bundle(
            source,
            validate=True,
            selected_cases=selected_cases,
            selected_run=selected_run,
        )
        tableir = bundle.tableir
    except jsonschema.ValidationError as e:
        _error(f"Schema error: {e.message}", output_json, str(file_path))
        return 2
    except SemanticValidationError as e:
        _error(f"Semantic error: {e}", output_json, str(file_path))
        return 2
    except ResolutionError as e:
        diagnostics = [e.as_diagnostic()]
        _attach_source_positions(diagnostics, source=source, file_path=file_path)
        diag = diagnostics[0]
        _error(
            f"{e.code}: {e.message}",
            output_json,
            str(file_path),
            code=e.code,
            object_id=diag.get("object_id"),
            location=diag.get("location"),
            line=diag.get("line"),
            column=diag.get("column"),
            source_excerpt=diag.get("source_excerpt"),
            suggestion=diag.get("suggestion"),
        )
        return 2
    except Exception as e:
        _error(f"Compile error: {e}", output_json, str(file_path))
        return 2

    created_files: list[str] = []
    artifact_dir = out_dir or (tableir_path.parent if tableir_path else None)

    if (
        artifact_dir
        and bundle.run_id
        and bundle.csir
        and bundle.cpir
        and bundle.explain
    ):
        import yaml

        artifact_dir.mkdir(parents=True, exist_ok=True)
        csir_path = artifact_dir / f"{bundle.run_id}.csir.yaml"
        cpir_path = artifact_dir / f"{bundle.run_id}.cpir.yaml"
        explain_path = artifact_dir / f"{bundle.run_id}.explain.json"
        csir_path.write_text(
            yaml.safe_dump(bundle.csir, sort_keys=False),
            encoding="utf-8",
        )
        cpir_path.write_text(
            yaml.safe_dump(bundle.cpir, sort_keys=False),
            encoding="utf-8",
        )
        explain_path.write_text(
            json.dumps(bundle.explain, indent=2) + "\n",
            encoding="utf-8",
        )
        created_files.extend([str(csir_path), str(cpir_path), str(explain_path)])

    if tableir_path:
        import yaml
        tableir_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tableir_path, "w") as f:
            yaml.dump(tableir, f, default_flow_style=False, sort_keys=False)
        created_files.append(str(tableir_path))

    if out_dir:
        from tools.veda_emit_excel import emit_excel
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = emit_excel(tableir, out_dir, validate=False)
        created_files.extend(str(p) for p in paths)

    if output_json:
        print(json.dumps({
            "dsl_version": source.get("dsl_version", DSL_VERSION),
            "artifact_version": CHECK_OUTPUT_VERSION,
            "success": True,
            "source": str(file_path),
            "run_id": bundle.run_id,
            "files": created_files,
        }, indent=2))
    else:
        print(f"Compiled {file_path}:")
        for f in created_files:
            print(f"  {f}")

    return 0


def cmd_validate(args) -> int:
    """Run validate command: compile + xl2times validation via veda_check."""
    file_path: Path = args.file
    output_json: bool = args.json
    keep_workdir: bool = args.keep_workdir
    selected_cases: list[str] | None = args.case
    selected_run: str | None = args.run

    if not file_path.exists():
        _error(f"File not found: {file_path}", output_json, str(file_path))
        return 2

    from tools.veda_check.checker import run_check

    if keep_workdir:
        workdir = Path(tempfile.mkdtemp(prefix="vedalang_"))
        if not output_json:
            print(f"Work directory: {workdir}")
    else:
        workdir = None

    result = run_check(
        file_path,
        from_vedalang=True,
        selected_cases=selected_cases,
        selected_run=selected_run,
    )

    if output_json:
        output = {
            "dsl_version": result.dsl_version,
            "artifact_version": result.artifact_version,
            "success": result.success,
            "source": str(file_path),
            "tables": result.tables,
            "total_rows": result.total_rows,
            "warnings": result.warnings,
            "errors": result.errors,
            "diagnostics": result.diagnostics,
        }
        if workdir:
            output["workdir"] = str(workdir)
        print(json.dumps(output, indent=2))
    else:
        if result.error_messages:
            for msg in result.error_messages:
                print(f"ERROR: {msg}")
            print()

        print(f"Validate: {result.errors} error(s), {result.warnings} warning(s)")
        if result.success:
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path}")

    if result.errors > 0:
        return 2
    elif result.warnings > 0:
        return 1
    return 0


def _res_request_from_args(args) -> dict[str, Any]:
    return {
        "version": "1",
        "file": str(args.file.resolve()),
        "mode": args.mode,
        "granularity": args.granularity,
        "lens": args.lens,
        "run": getattr(args, "run", None),
        "commodity_view": getattr(args, "commodity_view", None),
        "filters": {
            "regions": list(args.region or []),
            "case": args.case,
            "sectors": list(args.sector or []),
            "scopes": list(args.scope or []),
        },
        "compiled": {
            "truth": "auto",
            "cache": not bool(args.no_cache),
            "allow_partial": not bool(args.strict_compiled),
        },
    }


def cmd_res_query(args) -> int:
    """Run res query command and print stable JSON response."""
    from vedalang.viz.query_engine import query_res_graph

    request = _res_request_from_args(args)
    response = query_res_graph(request)

    if args.json:
        print(json.dumps(response, indent=2))
    else:
        print(json.dumps(response, indent=2))

    status = response.get("status", "error")
    if status == "ok":
        return 0
    if status == "partial":
        return 1
    return 2


def cmd_res_mermaid(args) -> int:
    """Run res mermaid command from query response."""
    from vedalang.viz.query_engine import query_res_graph, response_to_mermaid

    request = _res_request_from_args(args)
    response = query_res_graph(request)
    mermaid = response_to_mermaid(response)

    if args.json:
        payload = {"response": response, "mermaid": mermaid}
        print(json.dumps(payload, indent=2))
    else:
        print(mermaid)

    status = response.get("status", "error")
    if status == "ok":
        return 0
    if status == "partial":
        return 1
    return 2


def _error(
    message: str,
    as_json: bool,
    source: str,
    *,
    code: str | None = None,
    object_id: str | None = None,
    location: str | None = None,
    line: int | None = None,
    column: int | None = None,
    source_excerpt: dict[str, Any] | None = None,
    suggestion: str | None = None,
):
    """Print error message."""
    if as_json:
        payload = {
            "dsl_version": DSL_VERSION,
            "artifact_version": CHECK_OUTPUT_VERSION,
            "success": False,
            "source": source,
            "error": message,
        }
        if code is not None:
            payload["code"] = code
        if object_id is not None:
            payload["object_id"] = object_id
        if location is not None:
            payload["location"] = location
        if line is not None:
            payload["line"] = line
        if column is not None:
            payload["column"] = column
        if source_excerpt is not None:
            payload["source_excerpt"] = source_excerpt
        if suggestion is not None:
            payload["suggestion"] = suggestion
        print(json.dumps(payload))
    else:
        print(f"Error: {message}", file=sys.stderr)


def _viz_pid_file(port: int) -> Path:
    return Path(tempfile.gettempdir()) / f"vedalang-viz-{port}.pid"


def _read_viz_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
        pid = int(raw)
        if pid > 0:
            return pid
    except (OSError, ValueError):
        return None
    return None


def _write_viz_pid(pid_file: Path, pid: int) -> None:
    pid_file.write_text(f"{pid}\n", encoding="utf-8")


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_command(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    cmd = result.stdout.strip()
    return cmd or None


def _pid_looks_like_viz(pid: int) -> bool:
    cmd = (_pid_command(pid) or "").lower()
    return "vedalang" in cmd and "viz" in cmd


def _find_listener_pid(port: int) -> int | None:
    if shutil.which("lsof") is None:
        return None
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid > 0:
            return pid
    return None


def _terminate_pid(pid: int, timeout_seconds: float = 3.0) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            return True
        time.sleep(0.05)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    time.sleep(0.05)
    return not _pid_is_running(pid)


def _wait_for_viz_listener(
    host: str,
    port: int,
    *,
    timeout_seconds: float = 3.0,
    poll_seconds: float = 0.05,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=poll_seconds):
                return True
        except OSError:
            time.sleep(poll_seconds)
    return False


def _open_viz_browser_when_ready(port: int) -> None:
    import webbrowser

    if _wait_for_viz_listener("127.0.0.1", port):
        webbrowser.open(f"http://localhost:{port}")


def _cmd_viz_status(port: int) -> int:
    pid_file = _viz_pid_file(port)
    tracked_pid = _read_viz_pid(pid_file)
    listener_pid = _find_listener_pid(port)

    if tracked_pid and _pid_is_running(tracked_pid):
        print(f"viz server is running on port {port} (pid {tracked_pid}).")
        print(f"pid file: {pid_file}")
        return 0

    if tracked_pid and not _pid_is_running(tracked_pid):
        try:
            pid_file.unlink()
        except OSError:
            pass
        print(f"Removed stale viz pid file: {pid_file}")

    if listener_pid:
        if _pid_looks_like_viz(listener_pid):
            print(
                f"viz-like process is listening on port {port} (pid {listener_pid}),"
            )
            print("but no matching pid file is present.")
            return 1
        print(f"Port {port} is in use by pid {listener_pid} (not identified as viz).")
        return 2

    print(f"No viz server is running on port {port}.")
    return 0


def _cmd_viz_stop(port: int) -> int:
    pid_file = _viz_pid_file(port)
    tracked_pid = _read_viz_pid(pid_file)

    if tracked_pid and _pid_is_running(tracked_pid):
        if _terminate_pid(tracked_pid):
            try:
                pid_file.unlink()
            except OSError:
                pass
            print(f"Stopped viz server on port {port} (pid {tracked_pid}).")
            return 0
        print(f"Failed to stop viz server pid {tracked_pid}.", file=sys.stderr)
        return 2

    if tracked_pid and not _pid_is_running(tracked_pid):
        try:
            pid_file.unlink()
        except OSError:
            pass

    listener_pid = _find_listener_pid(port)
    if listener_pid is None:
        print(f"No viz server is running on port {port}.")
        return 0

    if not _pid_looks_like_viz(listener_pid):
        print(
            f"Refusing to stop pid {listener_pid} on port {port} "
            "(not identified as vedalang viz).",
            file=sys.stderr,
        )
        return 2

    if _terminate_pid(listener_pid):
        print(f"Stopped viz-like process on port {port} (pid {listener_pid}).")
        return 0

    print(f"Failed to stop viz-like process pid {listener_pid}.", file=sys.stderr)
    return 2


def cmd_viz(args) -> int:
    """Run viz command: standalone web UI backed by unified query engine."""
    port: int = args.port
    no_browser: bool = args.no_browser
    file_path: Path | None = args.file

    if getattr(args, "stop", False):
        return _cmd_viz_stop(port)

    if getattr(args, "status", False):
        return _cmd_viz_status(port)

    if file_path is not None and not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 2

    # Mermaid mode: output a projection from the unified query engine
    if getattr(args, "mermaid", False):
        from vedalang.viz.query_engine import query_res_graph, response_to_mermaid

        if file_path is None:
            print("Error: file is required when using --mermaid", file=sys.stderr)
            return 2
        granularity = getattr(args, "granularity", None) or "role"
        if getattr(args, "variants", False) and granularity == "role":
            granularity = "instance"
        request = {
            "version": "1",
            "file": str(file_path.resolve()),
            "mode": "source",
            "granularity": granularity,
            "lens": "system",
            "run": getattr(args, "run", None),
            "commodity_view": getattr(args, "commodity_view", None),
            "filters": {"regions": [], "case": None, "sectors": [], "scopes": []},
            "compiled": {"truth": "auto", "cache": True, "allow_partial": True},
        }
        response = query_res_graph(request)
        mermaid = response_to_mermaid(response)

        if getattr(args, "debug", False):
            print(json.dumps(response, indent=2), file=sys.stderr)

        print(mermaid)
        status = response.get("status", "error")
        if status == "ok":
            return 0
        if status == "partial":
            return 1
        return 2

    import uvicorn

    from vedalang.viz.server import create_app

    pid_file = _viz_pid_file(port)
    tracked_pid = _read_viz_pid(pid_file)
    if tracked_pid and _pid_is_running(tracked_pid):
        print(
            f"Error: viz server already running on port {port} (pid {tracked_pid}).",
            file=sys.stderr,
        )
        print(f"Stop it with: vedalang viz --stop --port {port}", file=sys.stderr)
        return 2
    if tracked_pid and not _pid_is_running(tracked_pid):
        try:
            pid_file.unlink()
        except OSError:
            pass

    listener_pid = _find_listener_pid(port)
    if listener_pid and listener_pid != tracked_pid:
        print(
            f"Error: port {port} is already in use by pid {listener_pid}.",
            file=sys.stderr,
        )
        if _pid_looks_like_viz(listener_pid):
            print(
                f"Try stopping it with: vedalang viz --stop --port {port}",
                file=sys.stderr,
            )
        return 2

    app = create_app(
        workspace_root=Path.cwd(),
        initial_file=file_path.resolve() if file_path else None,
        initial_run=getattr(args, "run", None),
    )

    print("Starting VedaLang RES Visualizer...")
    if file_path:
        print(f"  File: {file_path}")
    else:
        print("  File: (select from workspace in UI)")
    print(f"  URL:  http://localhost:{port}")
    print()
    print("Press Ctrl+C to stop")
    print()

    if not no_browser:
        browser_thread = threading.Thread(
            target=_open_viz_browser_when_ready,
            args=(port,),
            daemon=True,
        )
        browser_thread.start()

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    uvicorn_server = uvicorn.Server(config)

    _write_viz_pid(pid_file, os.getpid())

    try:
        uvicorn_server.run()
    except KeyboardInterrupt:
        pass
    finally:
        tracked_pid = _read_viz_pid(pid_file)
        if tracked_pid == os.getpid():
            try:
                pid_file.unlink()
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    main()
