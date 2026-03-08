"""Pipeline orchestrator for full VedaLang -> TIMES cycle."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vedalang.versioning import DSL_VERSION, PIPELINE_OUTPUT_VERSION


@dataclass
class StepResult:
    """Result from a single pipeline step."""

    skipped: bool = False
    success: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Full pipeline execution result."""

    success: bool = False
    input_path: str = ""
    input_kind: str = ""
    work_dir: str = ""
    steps: dict[str, StepResult] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        # Build summary of key diagnostics for quick access
        summary = self._build_summary()

        return {
            "dsl_version": DSL_VERSION,
            "artifact_version": PIPELINE_OUTPUT_VERSION,
            "success": self.success,
            "summary": summary,
            "input": {"path": self.input_path, "kind": self.input_kind},
            "work_dir": self.work_dir,
            "artifacts": self.artifacts,
            "steps": {
                name: {
                    "skipped": step.skipped,
                    "success": step.success,
                    "errors": step.errors,
                    "warnings": step.warnings,
                    **step.artifacts,
                }
                for name, step in self.steps.items()
            },
        }

    def _build_summary(self) -> dict:
        """Build a quick-access summary of pipeline status."""
        summary: dict[str, Any] = {
            "all_steps_ok": self.success,
            "failed_step": None,
            "gams": None,
        }

        # Find first failed step
        for name, step in self.steps.items():
            if not step.skipped and not step.success:
                summary["failed_step"] = name
                break

        # Extract GAMS diagnostics summary if available
        run_times_step = self.steps.get("run_times")
        if run_times_step and not run_times_step.skipped:
            gams_diag = run_times_step.artifacts.get("gams_diagnostics")
            if gams_diag:
                gams_summary = gams_diag.get("summary", {})
                execution = gams_diag.get("execution", {})
                summary["gams"] = {
                    "ok": gams_summary.get("ok", False),
                    "problem_type": gams_summary.get("problem_type"),
                    "message": gams_summary.get("message", ""),
                    "ran_solver": execution.get("ran_solver", False),
                    "model_status_code": execution.get("model_status", {}).get("code"),
                    "model_status": execution.get("model_status", {}).get("category"),
                    "model_status_text": execution.get("model_status", {}).get("text"),
                    "solve_status_code": execution.get("solve_status", {}).get("code"),
                    "solve_status": execution.get("solve_status", {}).get("category"),
                    "solve_status_text": execution.get("solve_status", {}).get("text"),
                    "objective": execution.get("objective", {}).get("value"),
                }

        return summary


def detect_input_kind(path: Path) -> str:
    """Auto-detect input type based on file extension/content."""
    if path.suffix == ".yaml" and ".veda" in path.name:
        return "vedalang"
    if path.suffix in (".yaml", ".json"):
        return "tableir"
    if path.suffix == ".xlsx":
        return "excel"
    if path.is_dir():
        if list(path.glob("*.dd")):
            return "dd"
        if list(path.glob("*.xlsx")):
            return "excel"
    return "unknown"


def _tail_text(text: str, *, max_lines: int = 20, max_chars: int = 2000) -> str:
    """Return a bounded tail excerpt for logs/std streams."""
    lines = text.splitlines()
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail


def _update_result_artifacts(
    result: PipelineResult,
    *,
    work_dir: Path,
    tableir_file: Path | None,
    excel_dir: Path | None,
    dd_dir: Path | None,
) -> None:
    """Refresh top-level pipeline artifact pointers from step outputs."""
    result.artifacts["work_dir"] = str(work_dir)
    if tableir_file:
        result.artifacts["tableir_file"] = str(tableir_file)
    compile_step = result.steps.get("compile")
    if compile_step:
        for key in ("run_id", "csir_file", "cpir_file", "explain_file"):
            if key in compile_step.artifacts:
                result.artifacts[key] = compile_step.artifacts[key]
    if excel_dir:
        result.artifacts["excel_dir"] = str(excel_dir)
    if dd_dir:
        result.artifacts["dd_dir"] = str(dd_dir)


def _extract_licensing_excerpt(lst_file: Path, *, max_lines: int = 6) -> list[str]:
    """Extract key licensing lines from a GAMS listing file."""
    if not lst_file.exists():
        return []

    excerpt: list[str] = []
    pattern = re.compile(r"licens|demo|gamslice", re.IGNORECASE)
    try:
        for raw_line in lst_file.read_text(errors="replace").splitlines():
            if pattern.search(raw_line):
                excerpt.append(raw_line.strip())
                if len(excerpt) >= max_lines:
                    break
    except OSError:
        return []

    return excerpt


def run_pipeline(
    input_path: Path,
    *,
    input_kind: str | None = None,
    run_id: str | None = None,
    case: str = "scenario",
    times_src: Path | None = None,
    gams_binary: str = "gams",
    solver: str = "CBC",
    work_dir: Path | None = None,
    keep_workdir: bool = False,
    no_solver: bool = False,
    no_sankey: bool = False,
    verbose: bool = False,
) -> PipelineResult:
    """Run the full VedaLang -> TIMES pipeline.

    Stages:
    1. compile: VedaLang -> TableIR (if vedalang input)
    2. emit_excel: TableIR -> Excel (if vedalang/tableir input)
    3. xl2times: Excel -> DD files
    4. run_times: DD -> TIMES solution (unless no_solver)
    """
    result = PipelineResult()
    result.input_path = str(input_path)

    # Auto-detect input kind
    if input_kind is None:
        input_kind = detect_input_kind(input_path)
    result.input_kind = input_kind

    # Set up work directory
    if work_dir is None:
        work_dir = Path(
            tempfile.mkdtemp(prefix=f"veda-dev-{datetime.now():%Y%m%d-%H%M%S}-")
        )
    else:
        work_dir.mkdir(parents=True, exist_ok=True)
    result.work_dir = str(work_dir)

    try:
        tableir_file: Path | None = None
        excel_dir: Path | None = None
        dd_dir: Path | None = None
        vedalang_source: dict | None = None

        # Step 0: Heuristics (VedaLang only)
        heuristics_result = StepResult()
        if input_kind == "vedalang":
            try:
                from vedalang.compiler import load_vedalang
                from vedalang.heuristics.linter import run_heuristics

                if verbose:
                    print(f"[heuristics] Checking {input_path}")

                vedalang_source = load_vedalang(input_path)
                issues = run_heuristics(vedalang_source)

                heuristics_result.artifacts["issues"] = [i.to_dict() for i in issues]
                heuristics_result.artifacts["issue_count"] = len(issues)

                for issue in issues:
                    if issue.severity == "error":
                        heuristics_result.errors.append(issue.message)
                    else:
                        heuristics_result.warnings.append(issue.message)

                if verbose and issues:
                    print(f"[heuristics] Found {len(issues)} issue(s)")
            except Exception as e:
                heuristics_result.success = False
                heuristics_result.errors.append(str(e))
        else:
            heuristics_result.skipped = True
        result.steps["heuristics"] = heuristics_result

        # Step 1: Compile VedaLang -> TableIR
        compile_result = StepResult()
        if input_kind == "vedalang":
            try:
                from vedalang.compiler import (
                    V0_2ResolutionError,
                    compile_vedalang_bundle,
                    load_vedalang,
                )

                if verbose:
                    print(f"[compile] Compiling {input_path}")

                # Reuse source if already loaded, otherwise load fresh
                source = (
                    vedalang_source if vedalang_source
                    else load_vedalang(input_path)
                )
                bundle = compile_vedalang_bundle(
                    source,
                    validate=True,
                    selected_run=run_id,
                )
                tableir = bundle.tableir

                tableir_file = work_dir / "model.tableir.yaml"
                import yaml

                with open(tableir_file, "w") as f:
                    yaml.dump(tableir, f, default_flow_style=False, sort_keys=False)

                compile_result.artifacts["tableir_file"] = str(tableir_file)
                compile_result.artifacts["file_count"] = len(tableir.get("files", []))
                if bundle.run_id and bundle.csir and bundle.cpir and bundle.explain:
                    csir_file = work_dir / f"{bundle.run_id}.csir.yaml"
                    cpir_file = work_dir / f"{bundle.run_id}.cpir.yaml"
                    explain_file = work_dir / f"{bundle.run_id}.explain.json"
                    csir_file.write_text(
                        yaml.safe_dump(bundle.csir, sort_keys=False),
                        encoding="utf-8",
                    )
                    cpir_file.write_text(
                        yaml.safe_dump(bundle.cpir, sort_keys=False),
                        encoding="utf-8",
                    )
                    explain_file.write_text(
                        json.dumps(bundle.explain, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    compile_result.artifacts["run_id"] = bundle.run_id
                    compile_result.artifacts["csir_file"] = str(csir_file)
                    compile_result.artifacts["cpir_file"] = str(cpir_file)
                    compile_result.artifacts["explain_file"] = str(explain_file)
                if verbose:
                    count = compile_result.artifacts["file_count"]
                    print(f"[compile] Created TableIR with {count} files")
            except V0_2ResolutionError as e:
                compile_result.success = False
                compile_result.errors.append(f"{e.code}: {e.message}")
            except Exception as e:
                compile_result.success = False
                compile_result.errors.append(str(e))
        else:
            compile_result.skipped = True
            if input_kind == "tableir":
                tableir_file = input_path
        result.steps["compile"] = compile_result

        if not compile_result.success:
            _update_result_artifacts(
                result,
                work_dir=work_dir,
                tableir_file=tableir_file,
                excel_dir=excel_dir,
                dd_dir=dd_dir,
            )
            return result

        # Step 2: Emit Excel
        emit_result = StepResult()
        if input_kind in ("vedalang", "tableir") and tableir_file:
            try:
                from tools.veda_emit_excel import emit_excel, load_tableir

                if verbose:
                    print(f"[emit_excel] Emitting from {tableir_file}")

                tableir = load_tableir(tableir_file)
                excel_dir = work_dir / "excel"
                created = emit_excel(tableir, excel_dir, validate=False)

                emit_result.artifacts["excel_dir"] = str(excel_dir)
                emit_result.artifacts["excel_files"] = [str(p) for p in created]
                emit_result.artifacts["file_count"] = len(created)
                if verbose:
                    print(f"[emit_excel] Created {len(created)} Excel file(s)")
            except Exception as e:
                emit_result.success = False
                emit_result.errors.append(str(e))
        else:
            emit_result.skipped = True
            if input_kind == "excel":
                excel_dir = input_path if input_path.is_dir() else input_path.parent
        result.steps["emit_excel"] = emit_result

        if not emit_result.success:
            _update_result_artifacts(
                result,
                work_dir=work_dir,
                tableir_file=tableir_file,
                excel_dir=excel_dir,
                dd_dir=dd_dir,
            )
            return result

        # Step 3: xl2times (Excel -> DD)
        xl2times_result = StepResult()
        if input_kind in ("vedalang", "tableir", "excel") and excel_dir:
            try:
                dd_dir = work_dir / "dd"
                dd_dir.mkdir(parents=True, exist_ok=True)
                diag_file = work_dir / "xl2times_diagnostics.json"
                manifest_file = work_dir / "xl2times_manifest.json"

                # Extract regions from the VedaLang source or TableIR
                regions = None
                if vedalang_source:
                    model_regions = vedalang_source.get("model", {}).get("regions", [])
                    if model_regions:
                        regions = ",".join(model_regions)
                if not regions and tableir_file and tableir_file.exists():
                    # Try to extract from TableIR - look for BOOKREGIONS_MAP
                    import yaml
                    with open(tableir_file) as f:
                        tir = yaml.safe_load(f)
                    for file_spec in tir.get("files", []):
                        for sheet in file_spec.get("sheets", []):
                            for table in sheet.get("tables", []):
                                if table.get("tag") == "~BOOKREGIONS_MAP":
                                    rows = table.get("rows", [])
                                    region_set = {
                                        r.get("region") for r in rows
                                        if r.get("region")
                                    }
                                    regions = ",".join(sorted(region_set))
                                    break

                if not regions:
                    regions = "REG1"  # Fallback default

                cmd = [
                    sys.executable,
                    "-m",
                    "xl2times",
                    str(excel_dir.resolve()),
                    "--dd",
                    "--output_dir",
                    str(dd_dir.resolve()),
                    "--regions",
                    regions,
                    "--diagnostics-json",
                    str(diag_file.resolve()),
                    "--manifest-json",
                    str(manifest_file.resolve()),
                ]

                if verbose:
                    print(f"[xl2times] Running: {' '.join(cmd)}")

                proc = subprocess.run(
                    cmd, capture_output=True, text=True
                )

                xl2times_result.artifacts["dd_dir"] = str(dd_dir)
                xl2times_result.artifacts["command"] = " ".join(cmd)
                xl2times_result.artifacts["return_code"] = proc.returncode

                if diag_file.exists():
                    with open(diag_file) as f:
                        diag_data = json.load(f)
                    xl2times_result.artifacts["diagnostics"] = diag_data
                    for d in diag_data.get("diagnostics", []):
                        if d.get("severity") == "error":
                            xl2times_result.errors.append(d.get("message", ""))
                        elif d.get("severity") == "warning":
                            xl2times_result.warnings.append(d.get("message", ""))

                if manifest_file.exists():
                    xl2times_result.artifacts["manifest_file"] = str(manifest_file)

                if proc.returncode != 0:
                    xl2times_result.success = False
                    if proc.stderr:
                        xl2times_result.errors.append(proc.stderr[-500:])
                elif verbose:
                    print(f"[xl2times] DD files written to {dd_dir}")
            except Exception as e:
                xl2times_result.success = False
                xl2times_result.errors.append(str(e))
        else:
            xl2times_result.skipped = True
            if input_kind == "dd":
                dd_dir = input_path
        result.steps["xl2times"] = xl2times_result

        if not xl2times_result.success:
            _update_result_artifacts(
                result,
                work_dir=work_dir,
                tableir_file=tableir_file,
                excel_dir=excel_dir,
                dd_dir=dd_dir,
            )
            return result

        # Step 4: Run TIMES solver
        run_times_result = StepResult()
        if no_solver:
            run_times_result.skipped = True
        elif dd_dir:
            try:
                from tools.veda_run_times.runner import find_times_source, run_times

                effective_times_src = times_src
                if effective_times_src is None:
                    effective_times_src = find_times_source()

                if effective_times_src is None:
                    run_times_result.success = False
                    run_times_result.errors.append(
                        "TIMES source not found. Set TIMES_SRC env or use --times-src"
                    )
                else:
                    if verbose:
                        print(f"[run_times] Using TIMES source: {effective_times_src}")

                    # Run GAMS in a subdirectory of our work_dir
                    gams_work_dir = work_dir / "gams"
                    times_result = run_times(
                        dd_dir=dd_dir,
                        case=case,
                        times_src=effective_times_src,
                        gams_binary=gams_binary,
                        solver=solver,
                        work_dir=gams_work_dir,
                        keep_workdir=True,  # We manage cleanup ourselves
                        verbose=verbose,
                    )

                    run_times_result.success = times_result.success
                    run_times_result.artifacts["case"] = times_result.case
                    run_times_result.artifacts["times_work_dir"] = str(
                        times_result.work_dir
                    )
                    run_times_result.artifacts["gams_return_code"] = (
                        times_result.return_code
                    )
                    run_times_result.artifacts["model_status"] = (
                        times_result.model_status
                    )
                    run_times_result.artifacts["solve_status"] = (
                        times_result.solve_status
                    )
                    run_times_result.artifacts["objective"] = times_result.objective
                    run_times_result.artifacts["gams_command"] = " ".join(
                        times_result.gams_command
                    )
                    if times_result.stdout:
                        run_times_result.artifacts["gams_stdout_tail"] = _tail_text(
                            times_result.stdout
                        )
                    if times_result.stderr:
                        run_times_result.artifacts["gams_stderr_tail"] = _tail_text(
                            times_result.stderr
                        )

                    if times_result.lst_file:
                        run_times_result.artifacts["lst_file"] = str(
                            times_result.lst_file
                        )
                        if times_result.diagnostics:
                            problem_type = times_result.diagnostics.get(
                                "summary", {}
                            ).get("problem_type")
                            if problem_type == "licensing":
                                excerpt = _extract_licensing_excerpt(
                                    times_result.lst_file
                                )
                                if excerpt:
                                    run_times_result.artifacts[
                                        "lst_license_excerpt"
                                    ] = excerpt
                    if times_result.gdx_files:
                        run_times_result.artifacts["gdx_files"] = [
                            str(f) for f in times_result.gdx_files
                        ]
                    run_times_result.errors.extend(times_result.errors)
                    run_times_result.warnings.extend(times_result.warnings)

                    # Add GAMS diagnostics artifact
                    if times_result.diagnostics:
                        run_times_result.artifacts["gams_diagnostics"] = (
                            times_result.diagnostics
                        )
                        # Write diagnostics file
                        diag_file = work_dir / f"{case}_gams_diagnostics.json"
                        with open(diag_file, "w") as f:
                            json.dump(times_result.diagnostics, f, indent=2)
                        run_times_result.artifacts["gams_diagnostics_file"] = str(
                            diag_file
                        )
            except Exception as e:
                run_times_result.success = False
                run_times_result.errors.append(str(e))
        else:
            run_times_result.skipped = True
        result.steps["run_times"] = run_times_result

        # Step 5: Generate Sankey diagram
        sankey_result = StepResult()
        gdx_file = None

        if no_sankey or no_solver:
            sankey_result.skipped = True
        elif run_times_result.success and run_times_result.artifacts.get("gdx_files"):
            try:
                from .sankey import extract_sankey_multi

                gdx_files = run_times_result.artifacts["gdx_files"]
                gdx_file = Path(gdx_files[0]) if gdx_files else None

                if gdx_file and gdx_file.exists():
                    if verbose:
                        print(f"[sankey] Generating from {gdx_file}")

                    sankey = extract_sankey_multi(gdx_path=gdx_file)

                    if sankey.errors:
                        sankey_result.success = False
                        sankey_result.errors.extend(sankey.errors)
                    elif not sankey.years or not sankey.regions:
                        sankey_result.success = False
                        sankey_result.errors.append("No flow data found in GDX file")
                    else:
                        output_html = sankey.to_html_interactive()
                        sankey_file = work_dir / "sankey.html"
                        sankey_file.write_text(output_html)

                        sankey_result.artifacts["sankey_file"] = str(sankey_file)
                        sankey_result.artifacts["years"] = len(sankey.years)
                        sankey_result.artifacts["regions"] = len(sankey.regions)

                        if verbose:
                            print(f"[sankey] Created {sankey_file}")
                else:
                    sankey_result.skipped = True
                    sankey_result.warnings.append("GDX file not found")
            except Exception as e:
                sankey_result.success = False
                sankey_result.errors.append(str(e))
        else:
            sankey_result.skipped = True
        result.steps["sankey"] = sankey_result

        # Aggregate success
        result.success = all(
            step.success or step.skipped for step in result.steps.values()
        )

        # Collect top-level artifacts
        _update_result_artifacts(
            result,
            work_dir=work_dir,
            tableir_file=tableir_file,
            excel_dir=excel_dir,
            dd_dir=dd_dir,
        )
        if sankey_result.artifacts.get("sankey_file"):
            result.artifacts["sankey_file"] = sankey_result.artifacts["sankey_file"]

    finally:
        # Clean up work dir on success if not keeping
        if not keep_workdir and result.success:
            try:
                shutil.rmtree(work_dir)
                result.work_dir = "(cleaned up)"
            except Exception:
                pass

    return result


def _format_step_detail(name: str, step: StepResult) -> str:
    """Format additional detail for a step based on its artifacts."""
    details = []

    if name == "heuristics" and not step.skipped:
        issue_count = step.artifacts.get("issue_count", 0)
        if issue_count > 0:
            err_count = len(step.errors)
            warn_count = len(step.warnings)
            if err_count > 0:
                details.append(f"{err_count} error(s)")
            if warn_count > 0:
                details.append(f"{warn_count} warning(s)")
        else:
            details.append("clean")

    elif name == "compile" and not step.skipped:
        if "file_count" in step.artifacts:
            details.append(f"{step.artifacts['file_count']} files")

    elif name == "emit_excel" and not step.skipped:
        if "file_count" in step.artifacts:
            details.append(f"{step.artifacts['file_count']} xlsx")

    elif name == "xl2times" and not step.skipped:
        if "return_code" in step.artifacts:
            rc = step.artifacts["return_code"]
            if rc != 0:
                details.append(f"rc={rc}")

    elif name == "run_times" and not step.skipped:
        # Show GAMS diagnostics summary
        diag = step.artifacts.get("gams_diagnostics")
        if diag:
            summary = diag.get("summary", {})
            execution = diag.get("execution", {})
            if summary.get("ok"):
                obj = execution.get("objective", {}).get("value")
                if obj is not None:
                    details.append(f"obj={obj:.2f}")
                else:
                    details.append("solved")
            else:
                prob = summary.get("problem_type", "error")
                details.append(prob)
                model_code = execution.get("model_status", {}).get("code")
                solve_code = execution.get("solve_status", {}).get("code")
                if model_code is not None:
                    details.append(f"m={model_code}")
                if solve_code is not None:
                    details.append(f"s={solve_code}")
                rc = step.artifacts.get("gams_return_code")
                if rc is not None and rc != 0:
                    details.append(f"rc={rc}")

            # Show if solver didn't run
            if not execution.get("ran_solver"):
                details.append("no-solve")
        else:
            # Fall back to compatibility fields
            if step.artifacts.get("model_status"):
                details.append(step.artifacts["model_status"])
            rc = step.artifacts.get("gams_return_code")
            if rc is not None and rc != 0:
                details.append(f"rc={rc}")

    elif name == "sankey" and not step.skipped:
        years = step.artifacts.get("years")
        regions = step.artifacts.get("regions")
        if years and regions:
            details.append(f"{years}y/{regions}r")

    return ", ".join(details) if details else ""


def _format_exec_status(status: dict[str, Any] | None) -> str | None:
    """Format model/solver status from structured diagnostics."""
    if not status:
        return None

    code = status.get("code")
    text = status.get("text")
    category = status.get("category")

    parts = []
    if code is not None:
        parts.append(str(code))
    if text:
        parts.append(str(text))

    if not parts and not category:
        return None

    base = " ".join(parts) if parts else "unknown"
    if category:
        return f"{base} [{category}]"
    return base


def _format_run_times_failure(step: StepResult) -> list[str]:
    """Build verbose failure lines for the run_times step."""
    lines: list[str] = ["Run-times diagnostics:"]

    gams_rc = step.artifacts.get("gams_return_code")
    if gams_rc is not None:
        lines.append(f"  - GAMS return code: {gams_rc}")

    diag = step.artifacts.get("gams_diagnostics")
    if diag:
        summary = diag.get("summary", {})
        execution = diag.get("execution", {})

        problem = summary.get("problem_type")
        if problem:
            lines.append(f"  - Problem: {problem}")

        message = summary.get("message")
        if message:
            lines.append(f"  - Message: {message}")

        model_status = _format_exec_status(execution.get("model_status"))
        if model_status:
            lines.append(f"  - Model status: {model_status}")

        solve_status = _format_exec_status(execution.get("solve_status"))
        if solve_status:
            lines.append(f"  - Solve status: {solve_status}")

        ran_solver = execution.get("ran_solver")
        if isinstance(ran_solver, bool):
            lines.append(f"  - Ran solver: {'yes' if ran_solver else 'no'}")

    command = step.artifacts.get("gams_command")
    if command:
        lines.append(f"  - Command: {command}")

    lst_file = step.artifacts.get("lst_file")
    if lst_file:
        lines.append(f"  - LST file: {lst_file}")

    diag_file = step.artifacts.get("gams_diagnostics_file")
    if diag_file:
        lines.append(f"  - Diagnostics JSON: {diag_file}")

    lst_license_excerpt = step.artifacts.get("lst_license_excerpt")
    if lst_license_excerpt:
        lines.append("  - Licensing excerpt (from .lst):")
        for line in lst_license_excerpt[:6]:
            lines.append(f"      {line[:120]}")

    stderr_tail = step.artifacts.get("gams_stderr_tail")
    if stderr_tail:
        lines.append("  - GAMS stderr tail:")
        for line in stderr_tail.splitlines()[-8:]:
            if line.strip():
                lines.append(f"      {line[:120]}")

    return lines


def format_result_table(result: PipelineResult) -> str:
    """Format pipeline result as a human-readable table."""
    status = "✓ PASS" if result.success else "✗ FAIL"

    lines = [
        f"Work dir: {result.work_dir}",
        "",
        "┌" + "─" * 65 + "┐",
        "│ veda-dev pipeline results" + " " * 39 + "│",
        "├" + "─" * 65 + "┤",
        f"│ Input: {result.input_path[:55]}".ljust(66) + "│",
        f"│ Kind: {result.input_kind}".ljust(66) + "│",
        "├" + "─" * 65 + "┤",
    ]

    for name, step in result.steps.items():
        if step.skipped:
            step_status = "⊘ skip"
        elif step.success:
            step_status = "✓ ok"
        else:
            step_status = "✗ fail"

        # Add step-specific details
        detail = _format_step_detail(name, step)
        if detail:
            step_line = f"│ {name:15} {step_status:8} ({detail})"
        else:
            step_line = f"│ {name:15} {step_status}"
        lines.append(step_line[:65].ljust(66) + "│")

    lines.append("├" + "─" * 65 + "┤")
    lines.append(f"│ Overall: {status}".ljust(66) + "│")
    lines.append("└" + "─" * 65 + "┘")

    # Show errors
    all_errors = []
    for name, step in result.steps.items():
        for err in step.errors:
            all_errors.append(f"[{name}] {err}")

    if all_errors:
        lines.append("")
        lines.append("Errors:")
        for err in all_errors[:10]:
            lines.append(f"  - {err[:70]}")

    run_times_step = result.steps.get("run_times")
    if run_times_step and not run_times_step.skipped and not run_times_step.success:
        lines.append("")
        lines.extend(_format_run_times_failure(run_times_step))

    return "\n".join(lines)
