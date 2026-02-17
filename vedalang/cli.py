"""User-facing CLI for VedaLang model authors.

This CLI provides intuitive commands for:
- Linting VedaLang source files
- Compiling VedaLang to Excel
- Validating with xl2times
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import jsonschema

from vedalang.compiler.compiler import (
    SemanticValidationError,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_cross_references,
    validate_vedalang,
)
from vedalang.heuristics.linter import run_heuristics


def main():
    parser = argparse.ArgumentParser(
        prog="vedalang",
        description="VedaLang CLI - author and validate energy system models",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_lint_parser(subparsers)
    _add_compile_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_check_parser(subparsers)
    _add_viz_parser(subparsers)

    args = parser.parse_args()

    if args.command == "lint":
        sys.exit(cmd_lint(args))
    elif args.command == "compile":
        sys.exit(cmd_compile(args))
    elif args.command in ("validate", "check"):
        sys.exit(cmd_validate(args))
    elif args.command == "viz":
        sys.exit(cmd_viz(args))


def _add_lint_parser(subparsers):
    p = subparsers.add_parser(
        "lint",
        help="Lint a VedaLang source file",
        description="Validate schema, check cross-references, and run heuristics.",
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
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
    p.add_argument("--no-lint", action="store_true", help="Skip linting before compile")
    p.add_argument("--json", action="store_true", help="Output JSON format")


def _add_validate_parser(subparsers):
    p = subparsers.add_parser(
        "validate",
        help="Validate through full pipeline",
        description="Compile and run through xl2times for complete validation.",
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument("--json", action="store_true", help="Output JSON format")
    p.add_argument(
        "--keep-workdir", action="store_true", help="Keep temp directory for debugging"
    )


def _add_check_parser(subparsers):
    p = subparsers.add_parser(
        "check",
        help="Alias for validate",
        description="Alias for 'validate' command.",
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument("--json", action="store_true", help="Output JSON format")
    p.add_argument(
        "--keep-workdir", action="store_true", help="Keep temp directory for debugging"
    )


def _add_viz_parser(subparsers):
    p = subparsers.add_parser(
        "viz",
        help="Visualize the Reference Energy System",
        description="Open a real-time browser visualization of the RES.",
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    p.add_argument(
        "--no-browser", action="store_true", help="Don't auto-open browser"
    )
    p.add_argument(
        "--mermaid", action="store_true", help="Output Mermaid syntax instead of web UI"
    )
    p.add_argument(
        "--variants", action="store_true", help="Include process variants in diagram"
    )
    p.add_argument(
        "--debug", action="store_true", help="Print debug info about nodes and edges"
    )


def cmd_lint(args) -> int:
    """Run lint command: schema + cross-refs + heuristics."""
    file_path: Path = args.file
    output_json: bool = args.json

    if not file_path.exists():
        _error(f"File not found: {file_path}", output_json, str(file_path))
        return 2

    diagnostics: list[dict] = []
    errors = 0
    warnings = 0

    try:
        source = load_vedalang(file_path)
    except Exception as e:
        diagnostics.append({
            "code": "PARSE_ERROR",
            "severity": "error",
            "message": f"Failed to parse YAML: {e}",
        })
        errors += 1
        return _output_lint_result(
            file_path, diagnostics, errors, warnings, output_json
        )

    try:
        validate_vedalang(source)
    except jsonschema.ValidationError as e:
        if e.absolute_path:
            path_str = " -> ".join(str(p) for p in e.absolute_path)
        else:
            path_str = "root"
        diagnostics.append({
            "code": "SCHEMA_ERROR",
            "severity": "error",
            "message": f"{e.message} (at {path_str})",
        })
        errors += 1
        return _output_lint_result(
            file_path, diagnostics, errors, warnings, output_json
        )

    model = source.get("model", source)
    xref_errors, xref_warnings = validate_cross_references(model, source=source)
    for msg in xref_errors:
        diagnostics.append({
            "code": "XREF_ERROR",
            "severity": "error",
            "message": msg,
        })
        errors += 1
    for msg in xref_warnings:
        diagnostics.append({
            "code": "XREF_WARNING",
            "severity": "warning",
            "message": msg,
        })
        warnings += 1

    issues = run_heuristics(source)
    for issue in issues:
        diagnostics.append(issue.to_dict())
        if issue.severity == "error":
            errors += 1
        else:
            warnings += 1

    return _output_lint_result(file_path, diagnostics, errors, warnings, output_json)


def _output_lint_result(
    file_path: Path,
    diagnostics: list[dict],
    errors: int,
    warnings: int,
    output_json: bool,
) -> int:
    """Output lint results and return exit code."""
    success = errors == 0

    if output_json:
        result = {
            "success": success,
            "source": str(file_path),
            "warnings": warnings,
            "errors": errors,
            "diagnostics": diagnostics,
        }
        print(json.dumps(result, indent=2))
    else:
        if diagnostics:
            for d in diagnostics:
                severity = d["severity"].upper()
                code = d["code"]
                msg = d["message"]
                loc = d.get("location", "")
                loc_str = f" ({loc})" if loc else ""
                print(f"{severity} [{code}]{loc_str}: {msg}")
            print()

        print(f"Lint: {errors} error(s), {warnings} warning(s)")
        if success:
            print(f"✓ {file_path}")

    if errors > 0:
        return 2
    elif warnings > 0:
        return 1
    return 0


def cmd_compile(args) -> int:
    """Run compile command: lint + compile to Excel."""
    file_path: Path = args.file
    out_dir: Path | None = args.out
    tableir_path: Path | None = args.tableir
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
        tableir = compile_vedalang_to_tableir(source, validate=True)
    except jsonschema.ValidationError as e:
        _error(f"Schema error: {e.message}", output_json, str(file_path))
        return 2
    except SemanticValidationError as e:
        _error(f"Semantic error: {e}", output_json, str(file_path))
        return 2
    except Exception as e:
        _error(f"Compile error: {e}", output_json, str(file_path))
        return 2

    created_files: list[str] = []

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
            "success": True,
            "source": str(file_path),
            "files": created_files,
        }, indent=2))
    else:
        print(f"Compiled {file_path}:")
        for f in created_files:
            print(f"  {f}")

    return 0


def cmd_validate(args) -> int:
    """Run validate command: full pipeline via veda_check."""
    file_path: Path = args.file
    output_json: bool = args.json
    keep_workdir: bool = args.keep_workdir

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

    result = run_check(file_path, from_vedalang=True)

    if output_json:
        output = {
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


def _error(message: str, as_json: bool, source: str):
    """Print error message."""
    if as_json:
        print(json.dumps({
            "success": False,
            "source": source,
            "error": message,
        }))
    else:
        print(f"Error: {message}", file=sys.stderr)


def cmd_viz(args) -> int:
    """Run viz command: real-time RES visualization."""
    file_path: Path = args.file

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 2

    # Mermaid mode: just output the diagram and exit
    if getattr(args, "mermaid", False):
        import yaml

        from vedalang.viz.res_mermaid import build_res_graph, graph_to_mermaid

        with open(file_path) as f:
            parsed = yaml.safe_load(f)

        include_variants = getattr(args, "variants", False)
        graph = build_res_graph(parsed, include_variants=include_variants)

        if getattr(args, "debug", False):
            print("=== Nodes ===", file=sys.stderr)
            for n in graph["nodes"]:
                kind, nid = n['kind'], n['id']
                ntype, stage = n.get('type'), n.get('stage')
                parent = n.get('parentRole', '')
                parent_str = f" (parent={parent})" if parent else ""
                msg = f"  {kind}: {nid} (type={ntype}, stage={stage}){parent_str}"
                print(msg, file=sys.stderr)
            print("=== Edges ===", file=sys.stderr)
            for e in graph["edges"]:
                print(f"  {e['from']} --{e['kind']}--> {e['to']}", file=sys.stderr)
            print("", file=sys.stderr)

        print(graph_to_mermaid(graph))
        return 0

    # Web server mode
    import asyncio
    import webbrowser

    import uvicorn

    from vedalang.viz.server import create_app

    port: int = args.port
    no_browser: bool = args.no_browser

    app, server = create_app(file_path)

    print("Starting VedaLang RES Visualizer...")
    print(f"  File: {file_path}")
    print(f"  URL:  http://localhost:{port}")
    print()
    print("Press Ctrl+C to stop")
    print()

    if not no_browser:
        webbrowser.open(f"http://localhost:{port}")

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    uvicorn_server = uvicorn.Server(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    server.start_watcher(loop)

    try:
        loop.run_until_complete(uvicorn_server.serve())
    except KeyboardInterrupt:
        pass
    finally:
        server.stop_watcher()

    return 0


if __name__ == "__main__":
    main()
