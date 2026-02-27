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
    validate_vedalang,
)
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
    PROFILE_FAST,
    PROFILE_THOROUGH,
    categories_for_profile,
    checks_for_engine,
    normalize_categories,
)


def main():
    parser = argparse.ArgumentParser(
        prog="vedalang",
        description="VedaLang CLI - author and validate energy system models",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_lint_parser(subparsers)
    _add_llm_lint_parser(subparsers)
    _add_compile_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_viz_parser(subparsers)

    args = parser.parse_args()

    if args.command == "lint":
        sys.exit(cmd_lint(args))
    elif args.command == "llm-lint":
        sys.exit(cmd_llm_lint(args))
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
        description="Run deterministic lint checks with category/profile selection.",
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
        "--profile",
        choices=[PROFILE_FAST, PROFILE_THOROUGH],
        default=PROFILE_FAST,
        help="Lint profile: fast (default) or thorough",
    )
    p.add_argument(
        "--list-categories",
        action="store_true",
        help="List available lint categories and profile support",
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
        help="LLM model for quorum vote (repeatable, default is two models).",
    )
    p.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh"],
        default="medium",
        help="Reasoning effort for LLM calls (default: medium).",
    )
    p.add_argument(
        "--prompt-version",
        default="v1",
        help="Prompt version to use for supported checks (or 'all').",
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
    p.add_argument("--no-lint", action="store_true", help="Skip linting before compile")
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


def _print_lint_categories(output_json: bool) -> None:
    data = [
        {
            "category": cat,
            "description": CATEGORY_DESCRIPTIONS[cat],
            "profiles": (
                [PROFILE_FAST, PROFILE_THOROUGH]
                if cat in categories_for_profile(PROFILE_FAST)
                else [PROFILE_THOROUGH]
            ),
        }
        for cat in CATEGORY_ORDER
    ]
    if output_json:
        print(json.dumps({"categories": data}, indent=2))
        return
    print("Lint categories:")
    for item in data:
        profiles = ", ".join(item["profiles"])
        print(f"  - {item['category']}: {item['description']} (profiles: {profiles})")


def _print_lint_checks(output_json: bool) -> None:
    grouped: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_ORDER}
    for check in CODE_CHECKS:
        grouped[check.category].append(
            {
                "check_id": check.check_id,
                "profile": check.profile,
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
            print(
                f"    - {c['check_id']} "
                f"(profile={c['profile']}, scope={c['scope']})"
            )


def cmd_lint(args) -> int:
    """Run deterministic lint checks with category/profile support."""
    output_json: bool = args.json
    profile: str = getattr(args, "profile", PROFILE_FAST)
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

    allowed_categories = categories_for_profile(profile)
    invalid_for_profile = [
        c for c in selected_categories if c not in allowed_categories
    ]
    if invalid_for_profile:
        _error(
            "Selected category requires --profile thorough: "
            + ", ".join(invalid_for_profile),
            output_json,
            str(file_path),
        )
        return 2

    run_categories = (
        selected_categories
        if requested_categories
        else [c for c in CATEGORY_ORDER if c in allowed_categories]
    )
    run_category_set = set(run_categories)
    checks_run = [
        c.check_id
        for c in checks_for_engine("code")
        if (
            c.category in run_category_set
            and c.profile in {PROFILE_FAST, PROFILE_THOROUGH}
        )
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
        path_str = (
            " -> ".join(str(p) for p in e.absolute_path)
            if e.absolute_path
            else "root"
        )
        diagnostics.append(
            with_meta(
                {
                    "code": "SCHEMA_ERROR",
                    "severity": "error",
                    "message": f"{e.message} (at {path_str})",
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
        prompt_version=getattr(args, "prompt_version", "v1"),
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
                "prompt_version": runtime_config.prompt_version,
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
    summary: dict | None = None,
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
