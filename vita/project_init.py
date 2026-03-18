"""Project initialization for Vita."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from vita.starter_catalog import (
    CURATED_STARTER_DEMOS,
    MINIMAL_STARTER_MODEL,
    MINIMAL_STARTER_RUN,
    featured_starter_demo,
)

TEMPLATES_DIR = Path(__file__).parent / "templates" / "starter"


def init_project(
    target_dir: Path,
    *,
    times_src: Path | None = None,
    gams_binary: str | None = None,
    smoke_test: bool = False,
    starter_profile: str = "curated",
    with_bd: bool = False,
) -> dict:
    """Bootstrap a new Vita project directory.

    Returns a dict with:
    - project_dir: Path to created project
    - starter_profile: str
    - gams_detected: bool
    - times_src_detected: bool
    - smoke_test_passed: bool | None
    - bd_initialized: bool (only when with_bd=True)
    - bd_failed: bool (only when with_bd=True)
    """
    target = target_dir.resolve()

    # Detect GAMS
    gams_path = _detect_gams(gams_binary)

    # Detect TIMES source
    times_path = _detect_times_src(times_src)

    # Create directory structure
    for subdir in ["models", "experiments", "runs", "notes"]:
        (target / subdir).mkdir(parents=True, exist_ok=True)

    # Write template files
    gams_status = f"detected ({gams_path})" if gams_path else "not found"
    times_status = f"detected ({times_path})" if times_path else "not found"
    project_name = target.name
    template_context = _build_template_context(
        starter_profile=starter_profile,
        project_name=project_name,
        gams_status=gams_status,
        times_status=times_status,
    )

    _write_template(
        TEMPLATES_DIR / "AGENTS.md.template",
        target / "AGENTS.md",
        **template_context,
    )
    _write_template(
        TEMPLATES_DIR / "README.md.template",
        target / "README.md",
        **template_context,
    )
    _write_template(
        TEMPLATES_DIR / "gitignore.template",
        target / ".gitignore",
    )
    _write_template(
        TEMPLATES_DIR / "questions.md.template",
        target / "notes" / "questions.md",
        **template_context,
    )

    starter_model_path, starter_run_id = _seed_starter(
        target,
        starter_profile=starter_profile,
    )

    # Write .env
    _write_env(target / ".env", gams_path=gams_path, times_path=times_path)

    # Smoke test
    smoke_test_passed = None
    if smoke_test and gams_path and times_path:
        smoke_test_passed = _run_smoke_test(
            model_path=starter_model_path,
            run_id=starter_run_id,
        )

    featured_demo = featured_starter_demo()

    result = {
        "project_dir": target,
        "starter_profile": starter_profile,
        "gams_detected": gams_path is not None,
        "times_src_detected": times_path is not None,
        "smoke_test_passed": smoke_test_passed,
        "featured_model": (
            str(featured_demo.target_relpath)
            if starter_profile == "curated"
            else str(MINIMAL_STARTER_MODEL)
        ),
        "featured_run": (
            featured_demo.default_run
            if starter_profile == "curated"
            else MINIMAL_STARTER_RUN
        ),
    }

    # Initialize beads (bd) for task tracking
    if with_bd:
        bd_result = _init_beads(target)
        result["bd_initialized"] = bd_result["initialized"]
        if bd_result["initialized"]:
            _append_bd_template(target / "AGENTS.md")
        else:
            result["bd_failed"] = True
            result["bd_error"] = bd_result["message"]

    return result


def _seed_starter(target: Path, *, starter_profile: str) -> tuple[Path, str]:
    """Seed starter assets for the selected profile."""
    if starter_profile == "curated":
        return _seed_curated_starter(target)
    if starter_profile == "minimal":
        return _seed_minimal_starter(target)
    raise ValueError(f"Unsupported starter profile: {starter_profile!r}")


def _seed_curated_starter(target: Path) -> tuple[Path, str]:
    """Copy curated demo assets into the workspace."""
    featured_demo = featured_starter_demo()
    for demo in CURATED_STARTER_DEMOS:
        src = TEMPLATES_DIR / demo.asset_filename
        dst = target / demo.target_relpath
        _copy_if_missing(src, dst)

        if demo.experiment_asset_filename:
            exp_src = TEMPLATES_DIR / demo.experiment_asset_filename
            exp_dst = (
                target
                / "experiments"
                / "demos"
                / "toy_industry_core.experiment.yaml"
            )
            _copy_if_missing(exp_src, exp_dst)

    return target / featured_demo.target_relpath, featured_demo.default_run


def _seed_minimal_starter(target: Path) -> tuple[Path, str]:
    """Copy the legacy single-file starter into the workspace."""
    example_src = TEMPLATES_DIR / "example.veda.yaml"
    example_dst = target / MINIMAL_STARTER_MODEL
    _copy_if_missing(example_src, example_dst)
    return example_dst, MINIMAL_STARTER_RUN


def _copy_if_missing(src: Path, dst: Path) -> None:
    """Copy a file into the workspace without overwriting existing content."""
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _build_template_context(
    *,
    starter_profile: str,
    project_name: str,
    gams_status: str,
    times_status: str,
) -> dict[str, str]:
    """Return placeholder replacements for starter templates."""
    if starter_profile == "curated":
        return _curated_template_context(
            project_name=project_name,
            gams_status=gams_status,
            times_status=times_status,
        )
    if starter_profile == "minimal":
        return _minimal_template_context(
            project_name=project_name,
            gams_status=gams_status,
            times_status=times_status,
        )
    raise ValueError(f"Unsupported starter profile: {starter_profile!r}")


def _curated_template_context(
    *,
    project_name: str,
    gams_status: str,
    times_status: str,
) -> dict[str, str]:
    """Template replacements for the curated starter profile."""
    featured_demo = featured_starter_demo()
    demo_catalog_lines = [
        (
            f"- `{demo.target_relpath.as_posix()}` — run `{demo.default_run}` — "
            f"{demo.question}"
        )
        for demo in CURATED_STARTER_DEMOS
    ]
    return {
        "project_name": project_name,
        "gams_status": gams_status,
        "times_status": times_status,
        "starter_intro_prompt": (
            "Run the seeded toy industry model at `single_2025` and explain "
            "which technology is selected"
        ),
        "starter_validate_command": (
            "vedalang validate "
            f"{featured_demo.target_relpath.as_posix()} "
            f"--run {featured_demo.default_run}"
        ),
        "starter_run_command": (
            "vita run "
            f"{featured_demo.target_relpath.as_posix()} "
            f"--run {featured_demo.default_run} "
            "--out runs/toy_industry/baseline --json"
        ),
        "starter_run_semantics": (
            "In this starter workspace, the seeded single run is "
            "`models/demos/toy_industry.veda.yaml --run single_2025`."
        ),
        "starter_run_note": (
            "This runs one existing seeded model/run directly and writes a "
            "single run directory at `runs/toy_industry/baseline`."
        ),
        "starter_experiment_command": (
            "vita experiment experiments/demos/toy_industry_core.experiment.yaml "
            "--out experiments/ --json"
        ),
        "starter_experiment_semantics": (
            "The seeded experiment is "
            "`experiments/demos/toy_industry_core.experiment.yaml`: it compares "
            "the same seeded toy industry model at baseline run `single_2025` "
            "against variant run `s25_co2_cap`."
        ),
        "starter_experiment_note": (
            "This experiment is a coordinated set of run variations over the "
            "seeded toy industry model, not a separate model family."
        ),
        "starter_experiment_section": (
            "```bash\n"
            "# Run the seeded industry experiment\n"
            "vita experiment experiments/demos/toy_industry_core.experiment.yaml "
            "--out experiments/ --json\n"
            "```"
        ),
        "starter_demo_catalog": "\n".join(demo_catalog_lines),
        "starter_project_layout_note": (
            "- `models/` — user-authored VedaLang models plus optional curated demos "
            "under `models/demos/`\n"
            "- `experiments/` — experiment manifests and outputs; seeded demos land "
            "under `experiments/demos/`\n"
            "- `runs/` — individual run artifacts from any model in this workspace\n"
            "- `notes/` — research questions and planning notes"
        ),
        "starter_using_your_own_model": """\
Place new model files under `models/`. Keep or delete `models/demos/` whenever you
like; Vita does not auto-delete or auto-refresh them. A single Vita workspace can
mix many models, experiments, and run directories at once, and there is no single
active model setting.""",
        "starter_first_prompt": (
            "Run the seeded toy industry model at `single_2025` and explain "
            "what technology mix it selects"
        ),
        "starter_experiment_prompt": (
            "Run the seeded toy industry experiment and explain how "
            "`s25_co2_cap` changes the result relative to `single_2025`"
        ),
        "starter_second_prompt": (
            "Show me the demo catalog and tell me whether I should start with "
            "a single seeded run or a seeded experiment"
        ),
        "starter_questions_examples": (
            "- Which of the curated demos is the best starting point for my "
            "question?\n"
            "- For the toy industry demo, what changes when I switch from "
            "`single_2025` to `s25_co2_cap`?\n"
            "- How do I add my own model next to the curated demos without "
            "replacing them?"
        ),
    }


def _minimal_template_context(
    *,
    project_name: str,
    gams_status: str,
    times_status: str,
) -> dict[str, str]:
    """Template replacements for the legacy minimal starter profile."""
    return {
        "project_name": project_name,
        "gams_status": gams_status,
        "times_status": times_status,
        "starter_intro_prompt": (
            "Run the example model and explain what technologies are selected"
        ),
        "starter_validate_command": (
            "vedalang validate models/example.veda.yaml --run demo_2025"
        ),
        "starter_run_command": (
            "vita run models/example.veda.yaml --run demo_2025 --out "
            "runs/example --json"
        ),
        "starter_run_semantics": (
            "In this starter workspace, the seeded single run is "
            "`models/example.veda.yaml --run demo_2025`."
        ),
        "starter_run_note": (
            "This runs the one seeded starter model directly and writes a "
            "single run directory at `runs/example`."
        ),
        "starter_experiment_command": "# No seeded experiment in the minimal profile",
        "starter_experiment_semantics": (
            "The minimal profile does not seed an experiment manifest; add one "
            "under `experiments/` when you want baseline/variant comparisons."
        ),
        "starter_experiment_note": (
            "An experiment in Vita is a set of coordinated run variations over "
            "one question, but you need to author the manifest yourself in the "
            "minimal profile."
        ),
        "starter_experiment_section": (
            "The minimal profile does not seed an experiment manifest. Add one under "
            "`experiments/` when you are ready to compare cases."
        ),
        "starter_demo_catalog": (
            "- `models/example.veda.yaml` — run `demo_2025` — Minimal starter model "
            "for validating the pipeline."
        ),
        "starter_project_layout_note": """\
- `models/` — VedaLang model files (.veda.yaml)
- `experiments/` — Experiment outputs (manifests, runs, diffs, conclusions)
- `runs/` — Individual run artifacts
- `notes/` — Research questions and planning notes""",
        "starter_using_your_own_model": """\
Place new model files under `models/`. This minimal starter seeds one example file,
but the workspace can still hold many models, experiments, and runs at once.""",
        "starter_first_prompt": (
            "What technology mix does the solver select for the example model, and why?"
        ),
        "starter_experiment_prompt": (
            "Design an experiment to test what happens if we double gas prices"
        ),
        "starter_second_prompt": "Run the example model and explain the results",
        "starter_questions_examples": """\
- What is the least-cost technology mix for meeting industrial heat demand?
- How does a CO₂ constraint change the optimal technology selection?
- What is the cost sensitivity to gas vs hydrogen boiler capital costs?""",
    }


def _detect_gams(explicit: str | None) -> str | None:
    """Detect GAMS binary path."""
    if explicit:
        return explicit

    env_val = os.environ.get("GAMS_BINARY")
    if env_val:
        return env_val

    which_gams = shutil.which("gams")
    if which_gams:
        return which_gams

    return None


def _detect_times_src(explicit: Path | None) -> Path | None:
    """Detect TIMES source directory."""
    if explicit and explicit.is_dir():
        return explicit.resolve()

    env_val = os.environ.get("TIMES_SRC")
    if env_val:
        env_path = Path(env_val)
        if env_path.is_dir():
            return env_path.resolve()

    default = Path.home() / "TIMES_model"
    if default.is_dir():
        return default.resolve()

    return None


def _write_template(
    src: Path,
    dst: Path,
    **replacements: str,
) -> None:
    """Read a template, apply replacements, and write if target doesn't exist."""
    if dst.exists():
        return
    content = src.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{key}}}", value)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")


def _write_env(
    path: Path,
    *,
    gams_path: str | None,
    times_path: Path | None,
) -> None:
    """Write .env file with detected or placeholder values."""
    if path.exists():
        return
    lines = [
        "# Vita project environment",
        f"GAMS_BINARY={gams_path or '# /path/to/gams'}",
        f"TIMES_SRC={times_path or '# /path/to/TIMES_model'}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _init_beads(target: Path) -> dict[str, str | bool]:
    """Run ``bd init`` in the target directory.

    Returns structured status to distinguish missing commands from runtime failures.
    """
    try:
        subprocess.run(
            ["bd", "init", "--quiet"],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except FileNotFoundError:
        return {
            "initialized": False,
            "message": "bd not found on PATH; install beads to use task tracking",
        }
    except subprocess.TimeoutExpired:
        return {
            "initialized": False,
            "message": "bd init timed out after 30s",
        }
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        if not detail:
            detail = f"bd init exited with status {exc.returncode}"
        return {
            "initialized": False,
            "message": detail,
        }
    return {"initialized": True, "message": ""}


def _append_bd_template(agents_md_path: Path) -> None:
    """Append the bd workflow template to an existing AGENTS.md."""
    bd_template_path = TEMPLATES_DIR.parent / "AGENTS.bd.md.template"
    bd_content = bd_template_path.read_text(encoding="utf-8")
    with agents_md_path.open("a", encoding="utf-8") as f:
        f.write(bd_content)


def _run_smoke_test(*, model_path: Path, run_id: str) -> bool:
    """Run vedalang validate on the example model as a smoke test."""
    try:
        subprocess.run(
            ["vedalang", "validate", str(model_path), "--run", run_id],
            capture_output=True,
            timeout=60,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False
    return True
