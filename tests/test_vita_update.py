import argparse
import subprocess

import pytest

from vita import handlers


def test_run_update_command_invokes_uv_tool_install(monkeypatch, capsys):
    calls: list[list[str]] = []

    def fake_run(command, check):
        calls.append(command)
        assert check is False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(handlers.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        handlers.run_update_command(argparse.Namespace())

    assert excinfo.value.code == 0
    assert calls == [
        [
            "uv",
            "tool",
            "install",
            "--force",
            "git+https://github.com/austimes/vita@main",
        ]
    ]
    stdout = capsys.readouterr().out
    assert "Refreshing CLI tools from GitHub main" in stdout
    assert "Refreshed commands: vita, vedalang, vedalang-dev" in stdout


def test_run_update_command_propagates_uv_failure(monkeypatch):
    def fake_run(command, check):
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(handlers.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        handlers.run_update_command(argparse.Namespace())

    assert excinfo.value.code == 1


def test_run_update_command_handles_missing_uv(monkeypatch, capsys):
    def fake_run(command, check):
        raise FileNotFoundError

    monkeypatch.setattr(handlers.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        handlers.run_update_command(argparse.Namespace())

    assert excinfo.value.code == 2
    assert "uv was not found on PATH" in capsys.readouterr().err
