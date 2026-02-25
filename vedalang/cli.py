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
    _add_llm_units_parser(subparsers)
    _add_compile_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_viz_parser(subparsers)

    args = parser.parse_args()

    if args.command == "lint":
        sys.exit(cmd_lint(args))
    elif args.command == "llm-check-units":
        sys.exit(cmd_llm_check_units(args))
    elif args.command == "compile":
        sys.exit(cmd_compile(args))
    elif args.command == "validate":
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
    p.add_argument(
        "--llm-assess",
        action="store_true",
        help="Enable optional LLM-based structural RES assessment",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail with exit code 2 on critical LLM assessment findings",
    )


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
    p.add_argument("--no-lint", action="store_true", help="Skip linting before compile")
    p.add_argument("--json", action="store_true", help="Output JSON format")


def _add_llm_units_parser(subparsers):
    p = subparsers.add_parser(
        "llm-check-units",
        help="Advisory LLM unit/coefficient certification",
        description=(
            "Run optional LLM unit/coefficient checks on model components with "
            "fingerprint-based certification metadata."
        ),
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument(
        "--component",
        action="append",
        help="Specific component to check (repeatable). Defaults to all pending.",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Check all components that are not already certified/current.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-check even certified components.",
    )
    p.add_argument(
        "--model",
        action="append",
        help="LLM model for quorum vote (repeatable, default is two models).",
    )
    p.add_argument(
        "--store",
        type=Path,
        help="Path to sidecar certification store (default: <source>.unit_checks.json)",
    )
    p.add_argument("--json", action="store_true", help="Output JSON format")


def _add_validate_parser(subparsers):
    p = subparsers.add_parser(
        "validate",
        help="Validate through full pipeline",
        description="Compile and run through xl2times for complete validation.",
    )
    p.add_argument("file", type=Path, help="Path to VedaLang source (.veda.yaml)")
    p.add_argument(
        "--case",
        action="append",
        help="Validate only the specified case (repeatable)",
    )
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
    """Run lint command: schema + cross-refs + heuristics + optional LLM assessment."""
    file_path: Path = args.file
    output_json: bool = args.json
    res_json_path: Path | None = getattr(args, "res_json", None)
    res_mermaid_path: Path | None = getattr(args, "res_mermaid", None)
    llm_assess: bool = getattr(args, "llm_assess", False)
    strict_mode: bool = getattr(args, "strict", False)

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

    # Optional LLM-based structural assessment
    llm_result = None
    llm_model = None
    if llm_assess:
        from vedalang.lint.llm_assessment import _MODEL, run_llm_assessment

        if not output_json:
            print(
                f"Sending model to LLM review agent"
                f" ({_MODEL}, reasoning effort=medium)..."
            )
            sys.stdout.flush()

        try:
            llm_result = run_llm_assessment(source)
            llm_model = llm_result.model
            for finding in llm_result.findings:
                diagnostics.append(finding.to_dict())
                if finding.severity == "critical":
                    if strict_mode:
                        errors += 1
                    else:
                        warnings += 1
                elif finding.severity == "warning":
                    warnings += 1
                # suggestions don't affect counts
        except Exception as e:
            diagnostics.append({
                "code": "LLM_ASSESS_ERROR",
                "severity": "warning",
                "message": f"LLM assessment failed: {e}",
            })
            warnings += 1

    return _output_lint_result(
        file_path, diagnostics, errors, warnings, output_json,
        llm_model=llm_model,
    )


def cmd_llm_check_units(args) -> int:
    """Run optional LLM unit/coefficient certification workflow."""
    file_path: Path = args.file
    output_json: bool = args.json
    selected_components: list[str] | None = args.component
    run_all: bool = args.all
    force: bool = args.force
    models: list[str] | None = args.model

    if not file_path.exists():
        _error(f"File not found: {file_path}", output_json, str(file_path))
        return 2

    try:
        source = load_vedalang(file_path)
        validate_vedalang(source)
    except Exception as e:
        _error(f"Failed to load/validate source: {e}", output_json, str(file_path))
        return 2

    from vedalang.lint.llm_unit_check import (
        default_store_path,
        load_store,
        run_component_unit_check,
        save_store,
        select_components,
        update_store_with_result,
    )

    store_path = args.store or default_store_path(file_path)
    store = load_store(store_path)

    try:
        to_check, skipped = select_components(
            source=source,
            store=store,
            selected=selected_components,
            run_all=run_all,
            force=force,
        )
    except Exception as e:
        _error(str(e), output_json, str(file_path))
        return 2

    results = []
    run_errors = []
    for component in to_check:
        try:
            result = run_component_unit_check(
                source=source,
                component=component,
                models=models,
            )
            update_store_with_result(store, result)
            results.append(result)
        except Exception as e:
            run_errors.append({"component": component, "error": str(e)})

    save_store(store_path, store)

    reviewed = len(results)
    certified = sum(1 for r in results if r.status == "certified")
    needs_review = reviewed - certified

    def summarize_vote(vote):
        critical = sum(1 for f in vote.findings if f.get("severity") == "critical")
        warning = sum(1 for f in vote.findings if f.get("severity") == "warning")
        suggestion = sum(1 for f in vote.findings if f.get("severity") == "suggestion")
        top_findings = []
        top_suggestions = []
        for item in vote.findings[:3]:
            msg = str(item.get("message", "")).strip()
            if msg:
                top_findings.append(msg)
            fix = str(item.get("suggestion", "")).strip()
            if fix:
                top_suggestions.append(fix)
        return {
            "model": vote.model,
            "status": vote.status,
            "critical": critical,
            "warning": warning,
            "suggestion": suggestion,
            "top_findings": top_findings,
            "top_suggestions": top_suggestions,
            "findings": vote.findings,
        }

    if output_json:
        payload = {
            "success": len(run_errors) == 0 and needs_review == 0,
            "source": str(file_path),
            "store": str(store_path),
            "checked": reviewed,
            "certified": certified,
            "needs_review": needs_review,
            "skipped_certified": skipped,
            "results": [
                {
                    "component": r.component,
                    "status": r.status,
                    "fingerprint": r.fingerprint,
                    "quorum": r.quorum,
                    "models": [v.model for v in r.votes],
                    "votes": [summarize_vote(v) for v in r.votes],
                }
                for r in results
            ],
            "errors": run_errors,
        }
        print(json.dumps(payload, indent=2))
    else:
        _output_llm_unit_check_result(
            file_path=file_path,
            store_path=store_path,
            results=results,
            skipped=skipped,
            run_errors=run_errors,
            certified=certified,
            needs_review=needs_review,
            summarize_vote=summarize_vote,
        )

    if run_errors:
        return 2
    if needs_review > 0:
        return 1
    return 0


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


def _output_llm_unit_check_result(
    *,
    file_path: Path,
    store_path: Path,
    results: list,
    skipped: list[str],
    run_errors: list[dict],
    certified: int,
    needs_review: int,
    summarize_vote,
) -> None:
    """Render llm-check-units output in the same style as lint --llm-assess."""

    diagnostics: list[dict] = []
    for result in results:
        for vote in result.votes:
            vote_summary = summarize_vote(vote)
            if not vote.findings and vote.status != "pass":
                diagnostics.append(
                    {
                        "code": "LLM_UNIT_CHECK",
                        "severity": "warning",
                        "category": "unit_coefficient",
                        "location": f"{result.component} [{vote.model}]",
                        "message": (
                            "LLM returned non-pass status but provided no findings."
                        ),
                    }
                )
                continue

            for finding in vote.findings:
                message = (
                    str(finding.get("message", "")).strip()
                    or "No message provided."
                )
                context_parts: list[str] = []

                expected_process_units = finding.get("expected_process_units")
                if expected_process_units:
                    context_parts.append(
                        "Expected process units: "
                        f"{json.dumps(expected_process_units, sort_keys=True)}"
                    )

                expected_commodity_units = finding.get("expected_commodity_units")
                if expected_commodity_units:
                    context_parts.append(
                        "Expected commodity units: "
                        f"{json.dumps(expected_commodity_units, sort_keys=True)}"
                    )

                observed_units = finding.get("observed_units")
                if observed_units:
                    context_parts.append(
                        f"Observed units: {json.dumps(observed_units, sort_keys=True)}"
                    )

                model_expectation = finding.get("model_expectation")
                if model_expectation:
                    context_parts.append(
                        f"Model expectation: {str(model_expectation).strip()}"
                    )

                if context_parts:
                    message = message + "\n\n" + "\n".join(context_parts)

                field = finding.get("field")
                location = f"{result.component} [{vote.model}]"
                if field:
                    location = f"{location} :: {field}"

                diagnostics.append(
                    {
                        "code": "LLM_UNIT_CHECK",
                        "severity": finding.get("severity", "warning"),
                        "category": "unit_coefficient",
                        "location": location,
                        "message": message,
                        "suggestion": finding.get("suggestion"),
                    }
                )

            if vote_summary["status"] != "pass" and not vote_summary["top_findings"]:
                diagnostics.append(
                    {
                        "code": "LLM_UNIT_CHECK",
                        "severity": "warning",
                        "category": "unit_coefficient",
                        "location": f"{result.component} [{vote.model}]",
                        "message": (
                            "Needs review but no actionable findings were "
                            "returned."
                        ),
                    }
                )

    for err in run_errors:
        diagnostics.append(
            {
                "code": "LLM_UNIT_CHECK_ERROR",
                "severity": "error",
                "category": "unit_coefficient",
                "location": err.get("component", ""),
                "message": str(err.get("error", "Unknown error")),
            }
        )

    try:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console()

        header_tbl = Table.grid(expand=True)
        header_tbl.add_column("left", ratio=1)
        header_tbl.add_column("right", justify="right")
        header_tbl.add_row(
            Text("VedaLang LLM Unit Check", style="bold"),
            Text(str(file_path), style="dim"),
        )
        header_tbl.add_row(
            Text("Store", style="dim"),
            Text(str(store_path), style="dim"),
        )
        if skipped:
            header_tbl.add_row(
                Text("Skipped certified/current", style="dim"),
                Text(", ".join(skipped), style="dim"),
            )

        console.print(
            Panel(
                header_tbl,
                box=box.ROUNDED,
                border_style="blue",
                padding=(1, 1),
            )
        )

        status_tbl = Table(show_header=True, header_style="bold")
        status_tbl.add_column("Component")
        status_tbl.add_column("Status")
        status_tbl.add_column("Quorum")
        status_tbl.add_column("Models")
        for result in results:
            status_style = "green" if result.status == "certified" else "yellow"
            status_tbl.add_row(
                result.component,
                f"[{status_style}]{result.status}[/{status_style}]",
                result.quorum,
                ",".join(v.model for v in result.votes),
            )
        if results:
            console.print(
                Panel(status_tbl, box=box.ROUNDED, border_style="cyan", padding=(0, 1))
            )

        if diagnostics:
            total = len(diagnostics)
            for i, d in enumerate(diagnostics, start=1):
                console.print(_format_finding_rich(d, i, total))
                console.print()

        summary = Table.grid(expand=True)
        summary.add_column("left", ratio=1)
        summary.add_column("right", justify="right")
        left = Text.assemble(
            ("Summary: ", "bold"),
            (f"{certified} certified", "bold green" if certified else "dim"),
            ("  ", ""),
            (f"{needs_review} needs_review", "bold yellow" if needs_review else "dim"),
            ("  ", ""),
            (
                f"{len(run_errors)} errors",
                "bold red" if run_errors else "dim",
            ),
        )
        right = (
            Text("✓ OK", style="bold green")
            if not run_errors and needs_review == 0
            else Text("✗ Needs attention", style="bold red")
        )
        summary.add_row(left, right)
        console.print(
            Panel(
                summary,
                box=box.ROUNDED,
                border_style="green" if not run_errors and needs_review == 0 else "red",
                padding=(1, 1),
            )
        )
    except ImportError:
        print(f"LLM unit check: {file_path}")
        print(f"Store: {store_path}")
        if skipped:
            print(f"Skipped certified/current: {', '.join(skipped)}")
        for result in results:
            print(
                f"  - {result.component}: {result.status} "
                "(quorum "
                f"{result.quorum}, models={','.join(v.model for v in result.votes)})"
            )
        for d in diagnostics:
            severity = str(d.get("severity", "warning")).upper()
            code = d.get("code", "LLM_UNIT_CHECK")
            location = d.get("location", "")
            location_str = f" ({location})" if location else ""
            print(f"{severity} [{code}]{location_str}: {d.get('message', '')}")
            suggestion = d.get("suggestion")
            if suggestion:
                print(f"  ↳ Fix: {suggestion}")
        print()
        print(
            "Summary: "
            f"{certified} certified, {needs_review} needs_review, "
            f"{len(run_errors)} errors"
        )


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
        body_items.append(Text(f"Location: {location}", style="dim"))

    body_items.append(Rule(style="dim"))

    # Message — render markdown for inline `code` formatting
    body_items.append(Markdown(message.strip() or " ", code_theme="monokai"))

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
        if llm_model:
            result["llm_model"] = llm_model
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
            summary = Table.grid(expand=True)
            summary.add_column("left", ratio=1)
            summary.add_column("right", justify="right")

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
            summary.add_row(left, right)

            console.print(Panel(
                summary,
                box=box.ROUNDED,
                border_style="green" if success else "red",
                padding=(1, 1),
            ))

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
            if llm_model:
                print(f"LLM model: {llm_model}")
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
    selected_cases: list[str] | None = args.case
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
        tableir = compile_vedalang_to_tableir(
            source,
            validate=True,
            selected_cases=selected_cases,
        )
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
    selected_cases: list[str] | None = args.case

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
    )

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
