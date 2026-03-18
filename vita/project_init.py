"""Project initialization for Vita."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates" / "starter"


def init_project(
    target_dir: Path,
    *,
    times_src: Path | None = None,
    gams_binary: str | None = None,
    smoke_test: bool = False,
    with_bd: bool = False,
) -> dict:
    """Bootstrap a new Vita project directory.

    Returns a dict with:
    - project_dir: Path to created project
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

    _write_template(
        TEMPLATES_DIR / "AGENTS.md.template",
        target / "AGENTS.md",
    )
    _write_template(
        TEMPLATES_DIR / "README.md.template",
        target / "README.md",
        project_name=project_name,
        gams_status=gams_status,
        times_status=times_status,
    )
    _write_template(
        TEMPLATES_DIR / "gitignore.template",
        target / ".gitignore",
    )
    _write_template(
        TEMPLATES_DIR / "questions.md.template",
        target / "notes" / "questions.md",
    )

    # Copy the example model
    example_src = TEMPLATES_DIR / "example.veda.yaml"
    example_dst = target / "models" / "example.veda.yaml"
    if not example_dst.exists():
        shutil.copy2(example_src, example_dst)

    # Write .env
    _write_env(target / ".env", gams_path=gams_path, times_path=times_path)

    # Smoke test
    smoke_test_passed = None
    if smoke_test and gams_path and times_path:
        smoke_test_passed = _run_smoke_test(target / "models" / "example.veda.yaml")

    result = {
        "project_dir": target,
        "gams_detected": gams_path is not None,
        "times_src_detected": times_path is not None,
        "smoke_test_passed": smoke_test_passed,
    }

    # Initialize beads (bd) for task tracking
    if with_bd:
        if _init_beads(target):
            result["bd_initialized"] = True
            _append_bd_template(target / "AGENTS.md")
        else:
            result["bd_initialized"] = False
            result["bd_failed"] = True

    return result


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


def _init_beads(target: Path) -> bool:
    """Run ``bd init`` in the target directory.

    Returns True on success, False on failure.
    """
    try:
        subprocess.run(
            ["bd", "init"],
            cwd=str(target),
            capture_output=True,
            timeout=30,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False
    return True


def _append_bd_template(agents_md_path: Path) -> None:
    """Append the bd workflow template to an existing AGENTS.md."""
    bd_template_path = TEMPLATES_DIR.parent / "AGENTS.bd.md.template"
    bd_content = bd_template_path.read_text(encoding="utf-8")
    with agents_md_path.open("a", encoding="utf-8") as f:
        f.write(bd_content)


def _run_smoke_test(model_path: Path) -> bool:
    """Run vedalang validate on the example model as a smoke test."""
    try:
        subprocess.run(
            ["vedalang", "validate", str(model_path), "--run", "demo_2025"],
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
