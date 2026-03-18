"""Tests for styled CLI help and parser errors."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.text import Text

from tools.cli_ui import render_to_text, strip_ansi
from vedalang import cli as vedalang_cli
from vedalang.version import VEDALANG_CLI_VERSION
from vita import cli as vita_cli
from vita.version import VITA_CLI_VERSION

ROOT = Path(__file__).resolve().parent.parent


def _run_cli(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["uv", "run", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=merged_env,
    )


def test_vita_build_parser_help_has_styled_sections() -> None:
    help_text = strip_ansi(vita_cli.build_parser().format_help())
    assert "Vita (VEDA Insight & TIMES Analysis) CLI" in help_text
    assert "Usage" in help_text
    assert "Commands" in help_text
    assert "Options" in help_text
    assert "run" in help_text
    assert "init" in help_text


def test_vedalang_build_parser_help_has_styled_sections() -> None:
    help_text = strip_ansi(vedalang_cli.build_parser().format_help())
    assert "VedaLang CLI - author and validate energy system models" in help_text
    assert "Usage" in help_text
    assert "Commands" in help_text
    assert "Options" in help_text
    assert "validate" in help_text


def test_vita_invalid_command_shows_suggestion() -> None:
    result = _run_cli("vita", "updat")
    stderr = strip_ansi(result.stderr)
    assert result.returncode == 2
    assert "invalid choice" in stderr
    assert "Did you mean `update`?" in stderr


def test_vita_no_args_shows_help() -> None:
    result = _run_cli("vita")
    stdout = strip_ansi(result.stdout)
    assert result.returncode == 0
    assert "Vita (VEDA Insight & TIMES Analysis) CLI" in stdout
    assert "Commands" in stdout


def test_vedalang_no_args_shows_help() -> None:
    result = _run_cli("vedalang")
    stdout = strip_ansi(result.stdout)
    assert result.returncode == 0
    assert "VedaLang CLI - author and validate energy system models" in stdout
    assert "Commands" in stdout


def test_vita_version_flag() -> None:
    result = _run_cli("vita", "--version")
    assert result.returncode == 0
    assert strip_ansi(result.stdout).strip() == f"vita {VITA_CLI_VERSION}"


def test_vedalang_version_flag() -> None:
    result = _run_cli("vedalang", "--version")
    assert result.returncode == 0
    assert strip_ansi(result.stdout).strip() == f"vedalang {VEDALANG_CLI_VERSION}"


def test_no_color_disables_ansi_sequences(monkeypatch) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    rendered = str(render_to_text(Text("hello", style="bold red")))
    assert "\x1b[" not in rendered


def test_force_color_enables_ansi_sequences(monkeypatch) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    monkeypatch.setenv("NO_COLOR", "")
    rendered = str(render_to_text(Text("hello", style="bold red")))
    assert "\x1b[" in rendered


def test_vita_init_parser_accepts_starter_profile() -> None:
    parser = vita_cli.build_parser()
    args = parser.parse_args(
        ["init", "demo-workspace", "--starter-profile", "minimal"]
    )
    assert args.command == "init"
    assert args.target == Path("demo-workspace")
    assert args.starter_profile == "minimal"
