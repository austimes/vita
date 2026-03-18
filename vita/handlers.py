"""Handler functions for Vita CLI commands."""

import importlib.metadata
import json
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from rich.console import Group

from tools.cli_ui import message_panel, print_message, print_renderable, status_panel

UPDATE_TOOL_SOURCE = "git+https://github.com/austimes/vita@main"
UPDATED_TOOL_COMMANDS = ("vita", "vedalang", "vedalang-dev")
UPDATE_TOOL_PACKAGE = "VITA"
UPDATE_VERSION_URL = (
    "https://raw.githubusercontent.com/austimes/vita/main/pyproject.toml"
)
_TEXT_INPUT_SUFFIXES = frozenset({".yaml", ".yml", ".json"})
_TABLEIR_SUFFIXES = (
    ".tableir.yaml",
    ".tableir.yml",
    ".tableir.json",
)


def _print_error(message: str) -> None:
    print_message("Error", [message], level="error", stream="stderr")


def _print_warning(message: str) -> None:
    print_message("Warning", [message], level="warning", stream="stderr")


def _print_status(
    title: str,
    rows: list[tuple[str, str]],
    *,
    level: str = "info",
    status: tuple[str, str] | None = None,
) -> None:
    print_renderable(status_panel(title, rows, level=level, status=status))


def _is_vedalang_source(path: Path) -> bool:
    """Return True for canonical VedaLang source file names."""
    name = path.name.lower()
    return name.endswith(".veda.yaml") or name.endswith(".veda.yml")


def _is_tableir_like_source(path: Path) -> bool:
    """Return True for file names that look like TableIR sources."""
    name = path.name.lower()
    if name.endswith(_TABLEIR_SUFFIXES):
        return True
    return path.suffix.lower() in _TEXT_INPUT_SUFFIXES and "tableir" in name


def _run_input_guardrail_error(input_path: Path, input_kind: str | None) -> str | None:
    """Return an actionable guardrail error message for invalid user-facing inputs."""
    if input_kind == "tableir":
        return (
            "TableIR input is dev-only for vita run. Use a .veda.yaml model in normal "
            "vita workflows, or use vedalang-dev tools for TableIR workflows."
        )

    if not input_path.is_file():
        return None

    if _is_tableir_like_source(input_path):
        return (
            "TableIR-style input is not supported in normal vita run mode: "
            f"{input_path}. "
            "Use a .veda.yaml model, or convert/check TableIR via vedalang-dev."
        )

    suffix = input_path.suffix.lower()
    if (
        input_kind is None
        and suffix in _TEXT_INPUT_SUFFIXES
        and not _is_vedalang_source(input_path)
    ):
        return (
            f"Unrecognized model source for vita run: {input_path}. "
            "Use a VedaLang file ending in .veda.yaml (or .veda.yml), "
            "or pass --from excel / --from dd for compiled artifacts."
        )

    return None


def run_pipeline_command(args):
    """Run the pipeline command."""
    from tools.veda_dev.pipeline import format_result_table, run_pipeline
    from tools.veda_dev.times_results import extract_results, format_results_console
    from vita.run_artifacts import emit_run_artifacts

    # Handle --process-results-only mode
    if args.process_results_only:
        work_dir = args.work_dir or Path("tmp")
        gdx_path = work_dir / "gams" / f"{args.case}.gdx"

        if not gdx_path.exists():
            _print_error(f"GDX file not found: {gdx_path}")
            sys.exit(2)

        results = extract_results(gdx_path=gdx_path)

        if args.json_output:
            print(json.dumps(results.to_dict(), indent=2))
        else:
            print(format_results_console(results))

        sys.exit(0 if not results.errors else 2)

    if not args.input.exists():
        _print_error(f"Input not found: {args.input}")
        sys.exit(2)

    guardrail_error = _run_input_guardrail_error(args.input, args.input_kind)
    if guardrail_error:
        _print_error(guardrail_error)
        sys.exit(2)

    # Suppress verbose output when JSON is requested (to keep stdout clean)
    verbose = args.verbose and not args.json_output
    out_dir = getattr(args, "out", None)
    keep_workdir = args.keep_workdir or out_dir is not None

    result = run_pipeline(
        input_path=args.input,
        input_kind=args.input_kind,
        run_id=args.run,
        case=args.case,
        times_src=args.times_src,
        gams_binary=args.gams_binary,
        solver=args.solver,
        work_dir=args.work_dir,
        keep_workdir=keep_workdir,
        no_solver=args.no_solver,
        no_sankey=args.no_sankey,
        verbose=verbose,
    )

    if out_dir is not None:
        try:
            run_times_step = result.steps.get("run_times")
            emission = emit_run_artifacts(
                run_dir=out_dir,
                input_path=args.input,
                input_kind=args.input_kind or result.input_kind,
                case=args.case,
                selected_run_id=args.run,
                pipeline_success=result.success,
                pipeline_artifacts=result.artifacts,
                run_times_artifacts=(
                    run_times_step.artifacts if run_times_step is not None else {}
                ),
                run_times_success=(
                    run_times_step.success if run_times_step is not None else False
                ),
                run_times_skipped=(
                    run_times_step.skipped if run_times_step is not None else True
                ),
                extract_results=extract_results,
                now_utc=lambda: datetime.now(UTC),
            )

            result.artifacts["run_artifacts"] = emission.paths.to_dict()
            result.artifacts["run_dir"] = str(emission.paths.run_dir)
            result.artifacts["manifest_file"] = str(emission.paths.manifest_path)
            result.artifacts["model_source_file"] = str(
                emission.paths.source_snapshot_path
            )
            if emission.results_written:
                result.artifacts["results_file"] = str(emission.paths.results_path)
            if emission.paths.gdx_path.exists():
                result.artifacts["run_gdx_file"] = str(emission.paths.gdx_path)
            if emission.paths.lst_path.exists():
                result.artifacts["run_lst_file"] = str(emission.paths.lst_path)

            if (
                result.success
                and not args.keep_workdir
                and result.work_dir != "(cleaned up)"
            ):
                work_dir_path = Path(result.work_dir)
                if work_dir_path.exists():
                    shutil.rmtree(work_dir_path)
                result.work_dir = "(cleaned up)"
                result.artifacts["work_dir"] = result.work_dir
        except Exception as exc:
            result.success = False
            result.artifacts["run_artifact_error"] = str(exc)

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_result_table(result))

    sys.exit(0 if result.success else 2)


def run_times_results_command(args):
    """Run times-results command."""
    from tools.veda_dev.times_results import (
        extract_results,
        format_results_console,
        save_results,
    )
    from vita.run_artifacts import RunArtifactError, resolve_run_artifacts

    if args.run_dir and args.gdx != Path("tmp/gams/scenario.gdx"):
        _print_error("Use either --run or --gdx, not both")
        sys.exit(2)

    gdx_path = args.gdx
    if args.run_dir:
        try:
            run_paths = resolve_run_artifacts(args.run_dir, require_solver=True)
            gdx_path = run_paths.gdx_path
        except RunArtifactError as exc:
            _print_error(str(exc))
            sys.exit(2)

    year_filter = None
    if args.year_filter:
        year_filter = [y.strip() for y in args.year_filter.split(",")]

    results = extract_results(
        gdx_path=gdx_path,
        process_filter=args.process_filter,
        year_filter=year_filter,
        include_flows=args.flows,
        limit=args.limit,
    )

    if results.errors:
        for err in results.errors:
            _print_error(err)
        sys.exit(2)

    if args.save:
        created = save_results(results, args.save)
        if not args.quiet:
            _print_status(
                "Results Saved",
                [("Paths", ", ".join(str(p) for p in created))],
                level="success",
                status=("saved", "success"),
            )

    if not args.quiet:
        if args.json_output:
            print(json.dumps(results.to_dict(), indent=2))
        else:
            print(format_results_console(results, limit=args.limit))

    sys.exit(0)


def run_diff_command(args):
    """Run the Vita run-artifact diff command."""
    from vita.diff import RunDiffError, compare_run_artifacts, format_run_diff_console

    metrics = _parse_multi_csv_args(getattr(args, "metric", None))
    focus_processes = _parse_multi_csv_args(getattr(args, "focus_processes", None))
    limit = max(int(getattr(args, "limit", 20)), 0)

    try:
        diff_payload = compare_run_artifacts(
            baseline_run_dir=args.baseline_run,
            variant_run_dir=args.variant_run,
            metrics=metrics or None,
            focus_processes=focus_processes or None,
        )
    except (RunDiffError, ValueError) as exc:
        _print_error(str(exc))
        sys.exit(2)

    if args.json_output:
        print(json.dumps(diff_payload, indent=2))
    else:
        print(format_run_diff_console(diff_payload, limit=limit))

    sys.exit(0)


def run_sankey_command(args):
    """Run the sankey command."""
    from tools.veda_dev.sankey import (
        extract_sankey,
        extract_sankey_multi,
        get_available_regions,
        get_available_years,
    )
    from vita.run_artifacts import RunArtifactError, resolve_run_artifacts

    if args.run_dir and args.gdx != Path("tmp/gams/scenario.gdx"):
        _print_error("Use either --run or --gdx, not both")
        sys.exit(2)

    gdx_path = args.gdx
    if args.run_dir:
        try:
            run_paths = resolve_run_artifacts(args.run_dir, require_solver=True)
            gdx_path = run_paths.gdx_path
        except RunArtifactError as exc:
            _print_error(str(exc))
            sys.exit(2)

    if not gdx_path.exists():
        _print_error(f"GDX file not found: {gdx_path}")
        sys.exit(2)

    # Handle list options
    if args.list_years:
        years = get_available_years(gdx_path)
        if years:
            _print_status(
                "Available Years",
                [("Years", ", ".join(years))],
                status=("listed", "success"),
            )
        else:
            print_message("Sankey", ["No flow data found in GDX file"], level="warning")
        sys.exit(0)

    if args.list_regions:
        regions = get_available_regions(gdx_path)
        if regions:
            _print_status(
                "Available Regions",
                [("Regions", ", ".join(regions))],
                status=("listed", "success"),
            )
        else:
            print_message("Sankey", ["No flow data found in GDX file"], level="warning")
        sys.exit(0)

    # For HTML format, use interactive mode by default (unless --static)
    use_interactive = args.format == "html" and not args.static

    if use_interactive:
        # Extract all years/regions for interactive visualization
        sankey = extract_sankey_multi(
            gdx_path=gdx_path,
            min_flow=args.min_flow,
        )

        if sankey.errors:
            for err in sankey.errors:
                _print_error(err)
            sys.exit(2)

        if not sankey.years or not sankey.regions:
            _print_warning("No flow data found in GDX file")
            sys.exit(1)

        output = sankey.to_html_interactive()
        output_path = args.output or Path("sankey.html")
        output_path.write_text(output)
        _print_status(
            "Interactive Sankey Saved",
            [
                ("Path", str(output_path)),
                (
                    "Years",
                    f"{len(sankey.years)} ({sankey.years[0]} - {sankey.years[-1]})",
                ),
                ("Regions", f"{len(sankey.regions)} ({', '.join(sankey.regions)})"),
                ("Open", f"file://{output_path.absolute()}"),
            ],
            level="success",
            status=("saved", "success"),
        )
        sys.exit(0)

    # Static mode: single year/region
    sankey = extract_sankey(
        gdx_path=gdx_path,
        year=args.year,
        region=args.region,
        min_flow=args.min_flow,
    )

    if sankey.errors:
        for err in sankey.errors:
            _print_error(err)
        sys.exit(2)

    if not sankey.links:
        _print_warning("No flow data found for specified year/region")
        sys.exit(1)

    # Generate output
    if args.format == "json":
        output = json.dumps(sankey.to_dict(), indent=2)
        if args.output:
            args.output.write_text(output)
            _print_status(
                "Sankey JSON Saved",
                [("Path", str(args.output))],
                level="success",
                status=("saved", "success"),
            )
        else:
            print(output)

    elif args.format == "mermaid":
        output = sankey.to_mermaid()
        if args.output:
            args.output.write_text(output)
            _print_status(
                "Sankey Mermaid Saved",
                [("Path", str(args.output))],
                level="success",
                status=("saved", "success"),
            )
        else:
            print(output)

    elif args.format == "html":
        output = sankey.to_html()
        output_path = args.output or Path("sankey.html")
        output_path.write_text(output)
        _print_status(
            "Static Sankey Saved",
            [
                ("Path", str(output_path)),
                ("Open", f"file://{output_path.absolute()}"),
            ],
            level="success",
            status=("saved", "success"),
        )

    sys.exit(0)


def run_experiment_plan_command(args):
    """Handle 'vita experiment plan'."""
    from vita.experiment_manifest import ExperimentManifestError
    from vita.experiment_runner import plan_experiment

    try:
        state = plan_experiment(args.manifest, args.out)
    except ExperimentManifestError as exc:
        _print_error(str(exc))
        sys.exit(2)

    _print_status(
        "Experiment Staged",
        [
            ("Experiment", state.experiment_id),
            ("Status", state.status),
            ("Runs", str(state.progress.runs_total)),
            ("Comparisons", str(state.progress.diffs_total)),
        ],
        level="success",
        status=("staged", "success"),
    )


def run_experiment_run_command(args):
    """Handle 'vita experiment run'."""
    from vita.experiment_manifest import ExperimentManifestError
    from vita.experiment_runner import run_experiment

    try:
        result = run_experiment(
            args.experiment_dir,
            resume=args.resume,
            force=args.force,
            json_output=getattr(args, "json_output", False),
        )
    except ExperimentManifestError as exc:
        _print_error(str(exc))
        sys.exit(2)

    if args.json_output:
        print(
            json.dumps(
                {
                    "experiment_dir": str(result.experiment_dir),
                    "status": result.state.status,
                    "success": result.success,
                    "progress": result.state.progress.__dict__,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
    else:
        p = result.state.progress
        _print_status(
            "Experiment Run",
            [
                ("Experiment", result.state.experiment_id),
                ("Status", result.state.status),
                ("Runs", f"{p.runs_complete}/{p.runs_total} complete"),
                ("Diffs", f"{p.diffs_complete}/{p.diffs_total} complete"),
            ],
            level="success" if result.success else "warning",
            status=("complete", "success") if result.success else ("issues", "warning"),
        )
    sys.exit(0 if result.success else 2)


def run_experiment_summarize_command(args):
    """Handle 'vita experiment summarize'."""
    from vita.experiment_summary import generate_summary

    summary_path = generate_summary(args.experiment_dir)

    if getattr(args, "json_output", False):
        import json as json_mod

        print(json_mod.dumps({"summary_json": str(summary_path)}, indent=2))
    else:
        _print_status(
            "Summary Generated",
            [("Summary", str(summary_path))],
            level="success",
            status=("saved", "success"),
        )


def run_experiment_validate_brief_command(args):
    """Handle 'vita experiment validate-brief'."""
    from vita.experiment_manifest import (
        ExperimentManifestError,
        load_experiment_manifest,
    )
    from vita.experiment_validation import validate_brief

    experiment_dir = args.experiment_dir.expanduser().resolve()
    try:
        manifest = load_experiment_manifest(experiment_dir / "manifest.yaml")
    except ExperimentManifestError as exc:
        _print_error(str(exc))
        sys.exit(2)

    brief_path = experiment_dir / "planning" / "brief.json"
    if not brief_path.exists():
        _print_error(f"brief.json not found: {brief_path}")
        sys.exit(2)

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    result = validate_brief(brief, manifest)

    # Save validation result
    val_path = experiment_dir / "planning" / "brief.validation.json"
    result.save(val_path)

    if getattr(args, "json_output", False):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        rows = [
            ("Errors", str(len(result.errors))),
            ("Warnings", str(len(result.warnings))),
        ]
        panel_level = "success" if result.valid else "error"
        panel_status = ("passed", "success") if result.valid else ("failed", "error")
        extras = [f"ERROR: {err}" for err in result.errors] + [
            f"WARNING: {warn}" for warn in result.warnings
        ]
        print_renderable(
            Group(
                status_panel(
                    "Brief Validation",
                    rows,
                    level=panel_level,
                    status=panel_status,
                ),
                message_panel(
                    "Diagnostics",
                    extras or ["No diagnostics"],
                    level="warning" if extras else "muted",
                ),
            )
        )

    sys.exit(0 if result.valid else 2)


def run_experiment_validate_interpretation_command(args):
    """Handle 'vita experiment validate-interpretation'."""
    from vita.experiment_manifest import (
        ExperimentManifestError,
        load_experiment_manifest,
    )
    from vita.experiment_validation import validate_interpretation

    experiment_dir = args.experiment_dir.expanduser().resolve()
    try:
        manifest = load_experiment_manifest(experiment_dir / "manifest.yaml")
    except ExperimentManifestError as exc:
        _print_error(str(exc))
        sys.exit(2)

    interpretation_path = experiment_dir / "conclusions" / "interpretation.json"
    if not interpretation_path.exists():
        _print_error(f"interpretation.json not found: {interpretation_path}")
        sys.exit(2)

    interpretation = json.loads(interpretation_path.read_text(encoding="utf-8"))
    result = validate_interpretation(interpretation, manifest)

    val_path = experiment_dir / "conclusions" / "interpretation.validation.json"
    result.save(val_path)

    if getattr(args, "json_output", False):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        rows = [
            ("Errors", str(len(result.errors))),
            ("Warnings", str(len(result.warnings))),
        ]
        panel_level = "success" if result.valid else "error"
        panel_status = ("passed", "success") if result.valid else ("failed", "error")
        extras = [f"ERROR: {err}" for err in result.errors] + [
            f"WARNING: {warn}" for warn in result.warnings
        ]
        print_renderable(
            Group(
                status_panel(
                    "Interpretation Validation",
                    rows,
                    level=panel_level,
                    status=panel_status,
                ),
                message_panel(
                    "Diagnostics",
                    extras or ["No diagnostics"],
                    level="warning" if extras else "muted",
                ),
            )
        )

    sys.exit(0 if result.valid else 2)


def run_experiment_status_command(args):
    """Handle 'vita experiment status'."""
    from vita.experiment_state import load_experiment_state

    state = load_experiment_state(args.experiment_dir)
    if getattr(args, "json_output", False):
        print(json.dumps(state.to_dict(), indent=2))
    else:
        p = state.progress
        rows = [
            ("Experiment", state.experiment_id),
            ("Status", state.status),
            (
                "Runs",
                f"{p.runs_complete}/{p.runs_total} complete, {p.runs_failed} failed",
            ),
            ("Diffs", f"{p.diffs_complete}/{p.diffs_total} complete"),
        ]
        if state.completed_at:
            rows.append(("Completed", str(state.completed_at)))
        if state.concluded_at:
            rows.append(("Concluded", str(state.concluded_at)))
        _print_status("Experiment Status", rows, status=("status", "info"))


def run_experiment_full_command(args):
    """Handle convenience 'vita experiment <manifest.yaml>' (stage+run+summarize)."""
    from vita.experiment_manifest import ExperimentManifestError
    from vita.experiment_runner import plan_experiment, run_experiment
    from vita.experiment_summary import generate_summary

    try:
        state = plan_experiment(args.manifest, args.out)
    except ExperimentManifestError as exc:
        _print_error(str(exc))
        sys.exit(2)

    _print_status(
        "Experiment Staged",
        [
            ("Experiment", state.experiment_id),
            ("Runs", str(state.progress.runs_total)),
            ("Comparisons", str(state.progress.diffs_total)),
        ],
        level="success",
        status=("staged", "success"),
    )

    experiment_dir = args.out / state.experiment_id
    try:
        result = run_experiment(
            experiment_dir,
            resume=False,
            force=False,
            json_output=getattr(args, "json_output", False),
        )
    except ExperimentManifestError as exc:
        _print_error(str(exc))
        sys.exit(2)

    if getattr(args, "json_output", False):
        print(
            json.dumps(
                {
                    "experiment_dir": str(result.experiment_dir),
                    "status": result.state.status,
                    "success": result.success,
                    "progress": result.state.progress.__dict__,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
    else:
        p = result.state.progress
        _print_status(
            "Experiment Run",
            [
                ("Experiment", result.state.experiment_id),
                ("Status", result.state.status),
                ("Runs", f"{p.runs_complete}/{p.runs_total} complete"),
                ("Diffs", f"{p.diffs_complete}/{p.diffs_total} complete"),
            ],
            level="success" if result.success else "warning",
            status=("complete", "success") if result.success else ("issues", "warning"),
        )

    if not result.success:
        sys.exit(2)

    summary_path = generate_summary(result.experiment_dir)
    # DO NOT auto-present or auto-conclude — those require agentic artifacts
    if not getattr(args, "json_output", False):
        _print_status(
            "Experiment Summary",
            [("Summary", str(summary_path))],
            level="success",
            status=("saved", "success"),
        )

    sys.exit(0)


def run_init_command(args):
    """Handle 'vita init'."""
    from vita.project_init import init_project

    result = init_project(
        target_dir=args.target,
        times_src=getattr(args, "times_src", None),
        gams_binary=getattr(args, "gams_binary", None),
        smoke_test=getattr(args, "smoke_test", False),
        starter_profile=getattr(args, "starter_profile", "curated"),
        with_bd=getattr(args, "with_bd", False),
    )
    rows = [
        ("Project", str(result["project_dir"])),
        ("Starter", result["starter_profile"]),
        (
            "GAMS",
            "detected"
            if result["gams_detected"]
            else "not found (set GAMS_BINARY in .env)",
        ),
        (
            "TIMES source",
            "detected"
            if result["times_src_detected"]
            else "not found (set TIMES_SRC in .env)",
        ),
    ]
    if result.get("smoke_test_passed") is True:
        rows.append(("Smoke test", "passed"))
    elif result.get("smoke_test_passed") is False:
        rows.append(("Smoke test", "failed"))
    if result.get("bd_initialized"):
        rows.append(("Beads (bd)", "initialized"))
    elif result.get("bd_failed"):
        bd_error = result.get("bd_error") or "bd initialization failed"
        rows.append(("Beads (bd)", f"failed ({bd_error})"))

    if result.get("featured_model") and result.get("featured_run"):
        rows.append(("Featured demo", result["featured_model"]))
        rows.append(("Featured run", result["featured_run"]))

    if result["starter_profile"] == "curated":
        next_steps = [
            "1. Open this directory in your AI agent (Amp, Codex, Claude)",
            '2. Ask: "Run the toy industry demo and explain the results"',
            '3. Ask: "Show me the demo catalog and recommend a starter model"',
        ]
    else:
        next_steps = [
            "1. Open this directory in your AI agent (Amp, Codex, Claude)",
            "2. The agent will read AGENTS.md and understand the workflow",
            '3. Ask: "Run the example model and explain the results"',
        ]

    print_renderable(
        Group(
            status_panel(
                "Vita Project Initialized",
                rows,
                level="success",
                status=("ready", "success"),
            ),
            message_panel(
                "Next Steps",
                next_steps,
                level="info",
            ),
        )
    )


def run_update_command(_args):
    """Refresh the installed Vita tool package from GitHub main."""
    installed_version = _get_installed_tool_version()
    latest_version = _fetch_latest_tool_version()

    if installed_version is not None and latest_version is not None:
        print_message(
            "CLI Tools",
            [
                "Refreshing vita tool package from GitHub main "
                f"({installed_version} -> {latest_version})."
            ],
            level="info",
        )
    elif installed_version is not None:
        print_message(
            "CLI Tools",
            [
                f"Installed version: {installed_version}. "
                "Could not determine latest GitHub main version; refreshing anyway."
            ],
            level="info",
        )
    else:
        print_message(
            "CLI Tools",
            ["Refreshing vita tool package from GitHub main."],
            level="info",
        )

    command = ["uv", "tool", "install", "--force", UPDATE_TOOL_SOURCE]
    print_renderable(
        Group(
            message_panel(
                "CLI Tools",
                ["Refreshing CLI tools from GitHub main:"],
                level="info",
            ),
            status_panel(
                "Refresh Command",
                [("Command", " ".join(command))],
                level="info",
                status=("run", "info"),
            ),
        )
    )

    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError:
        _print_error("uv was not found on PATH.")
        sys.exit(2)

    if result.returncode != 0:
        sys.exit(result.returncode)

    print_message(
        "CLI Tools Refreshed",
        [
            "Refreshed commands: "
            + ", ".join(UPDATED_TOOL_COMMANDS)
            + " (vita and vedalang come from the same tool package)."
        ],
        level="success",
    )
    sys.exit(0)


def _get_installed_tool_version() -> str | None:
    """Return the installed VITA package version, if available."""
    try:
        return importlib.metadata.version(UPDATE_TOOL_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return None


def _fetch_latest_tool_version() -> str | None:
    """Fetch the latest package version declared on GitHub main."""
    try:
        with urlopen(UPDATE_VERSION_URL, timeout=5) as response:
            payload = response.read().decode("utf-8")
    except (OSError, URLError):
        return None

    try:
        data = tomllib.loads(payload)
        return str(data["project"]["version"])
    except (tomllib.TOMLDecodeError, KeyError, TypeError):
        return None


def _compare_versions(lhs: str, rhs: str) -> int:
    """Compare dotted numeric versions."""
    lhs_parts = _parse_version(lhs)
    rhs_parts = _parse_version(rhs)
    width = max(len(lhs_parts), len(rhs_parts))
    lhs_norm = lhs_parts + (0,) * (width - len(lhs_parts))
    rhs_norm = rhs_parts + (0,) * (width - len(rhs_parts))
    if lhs_norm < rhs_norm:
        return -1
    if lhs_norm > rhs_norm:
        return 1
    return 0


def _parse_version(value: str) -> tuple[int, ...]:
    """Parse a dotted numeric version string."""
    parts = tuple(int(part) for part in value.split("."))
    if not parts:
        raise ValueError("version must not be empty")
    return parts


def _parse_multi_csv_args(values: list[str] | None) -> list[str]:
    """Parse repeated/CSV CLI values into a de-duplicated ordered list."""
    if values is None:
        return []

    parsed: list[str] = []
    for raw in values:
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            if value not in parsed:
                parsed.append(value)
    return parsed
