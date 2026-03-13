"""Core logic for running TIMES models through GAMS."""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Regex patterns for GAMS listing file parsing
# GAMS output uses formats like:
#   **** MODEL STATUS      1 OPTIMAL
#   **** SOLVER STATUS     1 NORMAL COMPLETION
#   **** OBJECTIVE VALUE    123.456
MODEL_STATUS_RE = re.compile(
    r"^\s*\*{4}\s+MODEL STATUS\s+(\d+)\s*([A-Za-z][A-Za-z _-]*)?\s*$", re.MULTILINE
)
SOLVER_STATUS_RE = re.compile(
    r"^\s*\*{4}\s+SOLVER STATUS\s+(\d+)\s*([A-Za-z][A-Za-z _-]*)?\s*$", re.MULTILINE
)
OBJECTIVE_VALUE_RE = re.compile(
    r"^\s*\*{4}\s+OBJECTIVE VALUE\s+([+-]?\d+(?:\.\d*)?(?:[eEdD][+-]?\d+)?)",
    re.MULTILINE,
)
ERROR_LINE_RE = re.compile(r"^\s*\*{4}\s+(ERROR[^\n]*?)\s*$", re.MULTILINE)
NUMERIC_ERROR_RE = re.compile(r"^\s*\*{4}\s+(\d+)\s+([^\n]+?)\s*$", re.MULTILINE)
WARNING_LINE_RE = re.compile(r"^\s*\*{3}\s+(WARNING[^\n]*?)\s*$", re.MULTILINE)
SYNTAX_ERROR_RE = re.compile(r"SYNTAX ERROR", re.IGNORECASE)
DOMAIN_VIOLATION_RE = re.compile(r"DOMAIN VIOLATION", re.IGNORECASE)
# Match infeasibility/unbounded indicators (simple patterns)
INFEASIBLE_RE = re.compile(r"\bINFEASIB(?:LE|ILITY)\b", re.IGNORECASE)
UNBOUNDED_RE = re.compile(r"\bUNBOUNDED\b", re.IGNORECASE)
# Report summary lines that indicate zero issues (should not trigger flags)
ZERO_INFEASIBLE_RE = re.compile(r"^\s*0\s+INFEASIBLE\s*$", re.MULTILINE)
ZERO_UNBOUNDED_RE = re.compile(r"^\s*0\s+UNBOUNDED\s*$", re.MULTILINE)
INTEGER_INFEASIBLE_RE = re.compile(r"INTEGER\s+INFEASIB", re.IGNORECASE)
LICENSING_RE = re.compile(r"LICENS(?:E|ING)\s+(?:ERROR|PROBLEM|LIMIT)", re.IGNORECASE)
UNKNOWN_SYMBOL_RE = re.compile(r"UNKNOWN\s+SYMBOL", re.IGNORECASE)
SOLVER_NAME_RE = re.compile(r"^\s+SOLVER\s+(\w+)\s*$", re.MULTILINE)

# IIS/Conflict Refiner patterns (CPLEX)
CONFLICT_STATUS_RE = re.compile(r"Conflict Refiner status", re.IGNORECASE)
IIS_EQUATIONS_RE = re.compile(
    r"Number of equations in conflict:\s+(\d+)", re.IGNORECASE
)
IIS_VARIABLES_RE = re.compile(
    r"Number of variables in conflict:\s+(\d+)", re.IGNORECASE
)
IIS_INDICATOR_RE = re.compile(
    r"Number of indicator constraints in conflict:\s+(\d+)", re.IGNORECASE
)
IIS_SOS_RE = re.compile(r"Number of SOS sets in conflict:\s+(\d+)", re.IGNORECASE)
IIS_MEMBER_RE = re.compile(
    r"^\s*(upper|lower|equality|free|fixed|rng|sos|indic)\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
OBJECTIVE_NAME_RE = re.compile(
    r"^\s*OBJECTIVE\s+(\w+)\s+(MINIMIZE|MAXIMIZE)?", re.MULTILINE | re.IGNORECASE
)

# Model status codes -> category
MODEL_STATUS_CATEGORIES = {
    1: "optimal",  # Optimal
    2: "optimal",  # Locally Optimal
    3: "unbounded",  # Unbounded
    4: "infeasible",  # Infeasible
    5: "unbounded",  # Locally Infeasible (often means unbounded in practice)
    6: "infeasible",  # Intermediate Infeasible
    7: "intermediate",  # Intermediate Nonoptimal
    8: "optimal",  # Integer Solution
    9: "intermediate",  # Intermediate Non-Integer
    10: "infeasible",  # Integer Infeasible
    11: "licensing",  # Licensing Problem
    12: "error",  # Error Unknown
    13: "error",  # Error No Solution
    14: "no_solution",  # No Solution Returned
    15: "solved_unique",  # Solved Unique
    16: "solved",  # Solved
    17: "solved_singular",  # Solved Singular
    18: "unbounded",  # Unbounded - No Solution
    19: "infeasible",  # Infeasible - No Solution
}

# Solver status codes -> category
SOLVER_STATUS_CATEGORIES = {
    1: "ok",  # Normal Completion
    2: "iteration_limit",  # Iteration Interrupt
    3: "resource_limit",  # Resource Interrupt
    4: "terminated",  # Terminated by Solver
    5: "evaluation_limit",  # Evaluation Interrupt
    6: "capability",  # Capability Problems
    7: "licensing",  # Licensing Problems
    8: "user_interrupt",  # User Interrupt
    9: "setup_failure",  # Error Setup Failure
    10: "solver_failure",  # Error Solver Failure
    11: "solver_failure",  # Error Internal Solver Error
    12: "solve_skipped",  # Solve Processing Skipped
    13: "system_failure",  # Error System Failure
}


@dataclass
class RunResult:
    """Result of a TIMES model run."""

    success: bool
    case: str
    work_dir: Path
    gams_command: list[str]
    return_code: int
    lst_file: Path | None = None
    gdx_files: list[Path] = field(default_factory=list)
    model_status: str | None = None
    solve_status: str | None = None
    objective: float | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] | None = None
    stdout: str = ""
    stderr: str = ""


def find_times_source() -> Path | None:
    """Locate TIMES source directory.

    Checks common locations:
    1. TIMES_SRC environment variable
    2. ~/TIMES_model (common user install)
    3. Subdirectory in workspace
    """
    if env_path := os.environ.get("TIMES_SRC"):
        p = Path(env_path)
        if p.exists():
            return p

    home_times = Path.home() / "TIMES_model"
    if home_times.exists():
        return home_times

    return None


def get_scaffold_dir() -> Path:
    """Get path to the GAMS scaffold directory."""
    return Path(__file__).parent.parent.parent / "xl2times" / "gams_scaffold"


def setup_work_dir(
    dd_dir: Path,
    case: str,
    work_dir: Path | None = None,
    times_src: Path | None = None,
) -> Path:
    """Set up the GAMS working directory with all required files.

    Creates:
      work_dir/
        source/ -> symlink to TIMES source
        model/  -> DD files
        scenarios/ -> (empty, for compatibility)
        runmodel.gms
        scenario.run
        gams.opt
    """
    if work_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        work_dir = Path(tempfile.mkdtemp(prefix=f"veda_run_{case}_{timestamp}_"))
    else:
        work_dir.mkdir(parents=True, exist_ok=True)

    scaffold = get_scaffold_dir()

    source_dir = work_dir / "source"
    if times_src:
        if source_dir.exists():
            source_dir.unlink()
        source_dir.symlink_to(times_src.resolve())
    else:
        source_dir.mkdir(exist_ok=True)

    model_dir = work_dir / "model"
    model_dir.mkdir(exist_ok=True)

    for dd_file in dd_dir.glob("*.dd"):
        shutil.copy(dd_file, model_dir / dd_file.name)

    scenarios_dir = work_dir / "scenarios"
    scenarios_dir.mkdir(exist_ok=True)

    for scaffold_file in ["runmodel.gms", "scenario.run", "gams.opt"]:
        src = scaffold / scaffold_file
        if src.exists():
            shutil.copy(src, work_dir / scaffold_file)

    return work_dir


def parse_gams_listing(content: str) -> dict[str, Any]:
    """Parse GAMS listing file content into structured diagnostics.

    Returns comprehensive diagnostic structure for AI agent consumption.
    """
    # Initialize the full diagnostic structure
    diag: dict[str, Any] = {
        "compilation": {"ok": True, "errors": [], "warnings": []},
        "execution": {
            "ran_solver": False,
            "model_status": {"code": None, "text": None, "category": None},
            "solve_status": {"code": None, "text": None, "category": None},
            "objective": {"value": None, "name": None, "sense": None},
            "solver": None,
        },
        "flags": {
            "syntax_error": False,
            "domain_violation": False,
            "infeasible": False,
            "unbounded": False,
            "integer_infeasible": False,
            "solver_failure": False,
            "licensing_problem": False,
            "unknown_symbol": False,
        },
        "summary": {"ok": True, "problem_type": None, "message": ""},
        "messages": {"errors": [], "warnings": [], "info": []},
        "raw": {
            "model_status_line": None,
            "solve_status_line": None,
            "objective_line": None,
        },
        "iis": {
            "available": False,
            "counts": {
                "equations": None,
                "variables": None,
                "indicator_constraints": None,
                "sos_sets": None,
            },
            "members": [],
            "raw_section": None,
        },
    }

    # Parse compilation errors
    error_matches = ERROR_LINE_RE.findall(content)
    numeric_errors: list[str] = []
    for code, message in NUMERIC_ERROR_RE.findall(content):
        normalized = message.strip()
        if normalized.upper().startswith("LINE "):
            continue
        numeric_errors.append(f"{code} {normalized}")

    all_errors = [*error_matches, *numeric_errors]
    if all_errors:
        diag["compilation"]["ok"] = False
        diag["compilation"]["errors"] = all_errors[:20]
        diag["messages"]["errors"].extend(all_errors[:20])

    # Parse warnings
    warning_matches = WARNING_LINE_RE.findall(content)
    if warning_matches:
        diag["compilation"]["warnings"] = warning_matches[:20]
        diag["messages"]["warnings"].extend(warning_matches[:20])

    # Detect problem flags from content
    diag["flags"]["syntax_error"] = bool(SYNTAX_ERROR_RE.search(content))
    diag["flags"]["domain_violation"] = bool(DOMAIN_VIOLATION_RE.search(content))
    # Check for infeasible/unbounded, but exclude "0 INFEASIBLE" summary lines
    has_infeasible = bool(INFEASIBLE_RE.search(content))
    has_zero_infeasible = bool(ZERO_INFEASIBLE_RE.search(content))
    diag["flags"]["infeasible"] = has_infeasible and not has_zero_infeasible
    has_unbounded = bool(UNBOUNDED_RE.search(content))
    has_zero_unbounded = bool(ZERO_UNBOUNDED_RE.search(content))
    diag["flags"]["unbounded"] = has_unbounded and not has_zero_unbounded
    diag["flags"]["integer_infeasible"] = bool(INTEGER_INFEASIBLE_RE.search(content))
    diag["flags"]["licensing_problem"] = bool(LICENSING_RE.search(content))
    diag["flags"]["unknown_symbol"] = bool(UNKNOWN_SYMBOL_RE.search(content))

    if diag["flags"]["syntax_error"]:
        diag["compilation"]["ok"] = False

    # Parse model status
    model_match = MODEL_STATUS_RE.search(content)
    if model_match:
        diag["raw"]["model_status_line"] = model_match.group(0).strip()
        code = int(model_match.group(1))
        text = model_match.group(2).strip() if model_match.group(2) else None
        diag["execution"]["model_status"] = {
            "code": code,
            "text": text,
            "category": MODEL_STATUS_CATEGORIES.get(code, "unknown"),
        }
        diag["execution"]["ran_solver"] = True

    # Parse solver status
    solver_match = SOLVER_STATUS_RE.search(content)
    if solver_match:
        diag["raw"]["solve_status_line"] = solver_match.group(0).strip()
        code = int(solver_match.group(1))
        text = solver_match.group(2).strip() if solver_match.group(2) else None
        diag["execution"]["solve_status"] = {
            "code": code,
            "text": text,
            "category": SOLVER_STATUS_CATEGORIES.get(code, "unknown"),
        }
        # Check for solver failure
        if SOLVER_STATUS_CATEGORIES.get(code) in ("solver_failure", "system_failure"):
            diag["flags"]["solver_failure"] = True

    # Parse objective value
    obj_match = OBJECTIVE_VALUE_RE.search(content)
    if obj_match:
        diag["raw"]["objective_line"] = obj_match.group(0).strip()
        try:
            # Handle Fortran-style 'D' exponent notation
            val_str = obj_match.group(1).replace("d", "e").replace("D", "e")
            diag["execution"]["objective"]["value"] = float(val_str)
        except ValueError:
            pass

    # Parse objective name and sense
    obj_name_match = OBJECTIVE_NAME_RE.search(content)
    if obj_name_match:
        diag["execution"]["objective"]["name"] = obj_name_match.group(1)
        if obj_name_match.group(2):
            diag["execution"]["objective"]["sense"] = obj_name_match.group(2).upper()

    # Parse solver name
    solver_name_match = SOLVER_NAME_RE.search(content)
    if solver_name_match:
        diag["execution"]["solver"] = solver_name_match.group(1)

    # Build summary
    model_cat = diag["execution"]["model_status"]["category"]
    solver_cat = diag["execution"]["solve_status"]["category"]
    ran_solver = bool(diag["execution"].get("ran_solver"))

    # Determine overall OK status
    is_ok = (
        diag["compilation"]["ok"]
        and ran_solver
        and model_cat in ("optimal", "solved", "solved_unique", None)
        and solver_cat in ("ok", None)
        and not any(
            [
                diag["flags"]["syntax_error"],
                diag["flags"]["domain_violation"],
                diag["flags"]["infeasible"],
                diag["flags"]["unbounded"],
                diag["flags"]["solver_failure"],
                diag["flags"]["licensing_problem"],
            ]
        )
    )
    diag["summary"]["ok"] = is_ok

    # Determine problem type
    if diag["flags"]["syntax_error"]:
        diag["summary"]["problem_type"] = "syntax_error"
        diag["summary"]["message"] = "GAMS compilation failed due to syntax error"
    elif diag["flags"]["licensing_problem"] or model_cat == "licensing":
        diag["summary"]["problem_type"] = "licensing"
        diag["summary"]["message"] = "GAMS licensing problem encountered"
    elif diag["flags"]["infeasible"] or model_cat == "infeasible":
        diag["summary"]["problem_type"] = "infeasible"
        diag["summary"]["message"] = "Model is infeasible - no solution exists"
    elif diag["flags"]["unbounded"] or model_cat == "unbounded":
        diag["summary"]["problem_type"] = "unbounded"
        diag["summary"]["message"] = "Model is unbounded"
    elif diag["flags"]["solver_failure"]:
        diag["summary"]["problem_type"] = "solver_failure"
        diag["summary"]["message"] = "Solver failed during execution"
    elif diag["flags"]["domain_violation"]:
        diag["summary"]["problem_type"] = "domain_violation"
        diag["summary"]["message"] = "Domain violation in model"
    elif not diag["compilation"]["ok"]:
        diag["summary"]["problem_type"] = "compilation_error"
        diag["summary"]["message"] = "GAMS compilation failed"
    elif not ran_solver:
        diag["summary"]["problem_type"] = "solver_not_run"
        diag["summary"]["message"] = (
            "Solver status lines not found in listing; solver may not have run"
        )
    elif is_ok:
        diag["summary"]["problem_type"] = None
        obj_val = diag["execution"]["objective"]["value"]
        if obj_val is not None:
            diag["summary"]["message"] = f"Solved successfully, objective = {obj_val}"
        else:
            diag["summary"]["message"] = "Solved successfully"
    else:
        diag["summary"]["problem_type"] = "unknown"
        diag["summary"]["message"] = f"Unknown issue: model={model_cat}, solver={solver_cat}"  # noqa: E501

    # --- IIS / Conflict Refiner parsing (CPLEX) ---
    if CONFLICT_STATUS_RE.search(content):
        conflict_start = content.find("Conflict Refiner status")
        if conflict_start != -1:
            tail = content[conflict_start:]
            # Find end of conflict section: look for double blank line or major
            # section markers (e.g., "****", "---", or start of new GAMS output)
            section_end = re.search(r"\n\s*\n\s*\n|\n\*{4}|\n-{3,}", tail)
            section = tail[: section_end.start()] if section_end else tail
            section = section.strip()

            diag["iis"]["available"] = True
            diag["iis"]["raw_section"] = section

            # Extract counts
            eq_m = IIS_EQUATIONS_RE.search(section)
            var_m = IIS_VARIABLES_RE.search(section)
            ind_m = IIS_INDICATOR_RE.search(section)
            sos_m = IIS_SOS_RE.search(section)

            if eq_m:
                diag["iis"]["counts"]["equations"] = int(eq_m.group(1))
            if var_m:
                diag["iis"]["counts"]["variables"] = int(var_m.group(1))
            if ind_m:
                diag["iis"]["counts"]["indicator_constraints"] = int(ind_m.group(1))
            if sos_m:
                diag["iis"]["counts"]["sos_sets"] = int(sos_m.group(1))

            # Extract individual conflicting members
            for role, rest in IIS_MEMBER_RE.findall(section):
                rest = rest.strip()
                parts = rest.split(None, 1)
                symbol = parts[0] if parts else rest
                detail = parts[1] if len(parts) > 1 else ""
                diag["iis"]["members"].append(
                    {
                        "role": role.lower(),
                        "symbol": symbol,
                        "detail": detail,
                    }
                )

    return diag


def parse_lst_file(lst_path: Path) -> dict:
    """Parse GAMS listing file for model/solve status.

    This is a backward-compatible wrapper that returns the old format
    plus a new "diagnostics" key with the full structure.
    """
    result = {
        "model_status": None,
        "solve_status": None,
        "objective": None,
        "errors": [],
        "warnings": [],
        "diagnostics": None,
    }

    if not lst_path.exists():
        return result

    content = lst_path.read_text(errors="replace")

    # Get full diagnostics
    diag = parse_gams_listing(content)
    result["diagnostics"] = diag

    # Extract summary fields from diagnostics
    model_status = diag["execution"]["model_status"]
    if model_status["text"]:
        result["model_status"] = model_status["text"]
    elif model_status["code"]:
        result["model_status"] = str(model_status["code"])

    solve_status = diag["execution"]["solve_status"]
    if solve_status["text"]:
        result["solve_status"] = solve_status["text"]
    elif solve_status["code"]:
        result["solve_status"] = str(solve_status["code"])

    result["objective"] = diag["execution"]["objective"]["value"]
    result["errors"] = diag["compilation"]["errors"][:10]
    result["warnings"] = diag["compilation"]["warnings"][:10]

    return result


def run_times(
    dd_dir: Path,
    case: str = "scenario",
    times_src: Path | None = None,
    gams_binary: str = "gams",
    work_dir: Path | None = None,
    solver: str = "CBC",
    keep_workdir: bool = False,
    verbose: bool = False,
) -> RunResult:
    """Run a TIMES model through GAMS.

    Args:
        dd_dir: Directory containing DD files from xl2times
        case: Case/scenario name (default: "scenario")
        times_src: Path to TIMES source code (defaults to auto-detect)
        gams_binary: GAMS executable (default: "gams")
        work_dir: Working directory (default: create temp dir)
        solver: LP solver to use (default: "CBC")
        keep_workdir: Keep working directory after run
        verbose: Print verbose output

    Returns:
        RunResult with execution details and status
    """
    if times_src is None:
        times_src = find_times_source()
        if times_src is None:
            return RunResult(
                success=False,
                case=case,
                work_dir=Path("."),
                gams_command=[],
                return_code=-1,
                errors=["TIMES source not found. Set TIMES_SRC env var or --times-src"],
            )

    work_path = setup_work_dir(dd_dir, case, work_dir, times_src)

    # Generate solver option file with IIS enabled for CPLEX
    if solver.upper() == "CPLEX":
        cplex_opt = work_path / "cplex.opt"
        if not cplex_opt.exists():
            cplex_opt.write_text(
                "\n".join(
                    [
                        "* Automatically generated by veda_run_times",
                        "* Enable conflict refiner / IIS when model is infeasible",
                        "iis 1",
                        "conflictdisplay 2",
                        "names 1",
                        "rerun auto",
                        "",
                    ]
                )
            )

    cmd = [
        gams_binary,
        "runmodel.gms",
        f"--solve_with={solver}",
        f"--run_name={case}",
    ]

    if verbose:
        print(f"Working directory: {work_path}")
        print(f"Running: {' '.join(cmd)}")

    proc = subprocess.run(
        cmd,
        cwd=work_path,
        capture_output=True,
        text=True,
    )

    lst_file = work_path / f"{case}.lst"
    if not lst_file.exists():
        lst_file = next(work_path.glob("*.lst"), None)

    gdx_files = list(work_path.glob("*.gdx"))

    lst_info = parse_lst_file(lst_file) if lst_file else {}
    diagnostics = lst_info.get("diagnostics")

    # Determine success from diagnostics if available, else fall back
    # to status-code checks.
    if diagnostics:
        success = proc.returncode == 0 and diagnostics["summary"]["ok"]
    else:
        success = proc.returncode == 0 and lst_info.get("model_status") in (
            None,
            "1",
            "OPTIMAL",
            "2",
            "LOCALLY OPTIMAL",
            "8",
            "INTEGER SOLUTION",
        )

    result = RunResult(
        success=success,
        case=case,
        work_dir=work_path,
        gams_command=cmd,
        return_code=proc.returncode,
        lst_file=lst_file,
        gdx_files=gdx_files,
        model_status=lst_info.get("model_status"),
        solve_status=lst_info.get("solve_status"),
        objective=lst_info.get("objective"),
        errors=lst_info.get("errors", []),
        warnings=lst_info.get("warnings", []),
        diagnostics=diagnostics,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )

    if not keep_workdir and success and work_dir is None:
        shutil.rmtree(work_path, ignore_errors=True)
        result.work_dir = Path("(cleaned up)")

    return result
