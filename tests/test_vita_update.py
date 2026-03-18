import argparse
import subprocess

import pytest

from vita import handlers


def test_compare_versions_orders_dotted_numbers():
    assert handlers._compare_versions("0.3.0", "0.4.2") == -1
    assert handlers._compare_versions("0.4.2", "0.4.2") == 0
    assert handlers._compare_versions("0.4.3", "0.4.2") == 1
    assert handlers._compare_versions("0.4", "0.4.0") == 0


def test_run_update_command_always_refreshes_even_when_current(monkeypatch, capsys):
    monkeypatch.setattr(handlers, "_get_installed_tool_version", lambda: "0.4.2")
    monkeypatch.setattr(handlers, "_fetch_latest_tool_version", lambda: "0.4.2")

    calls: list[list[str]] = []

    def fake_run(command, check):
        calls.append(command)
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
    assert "Refreshing" in stdout
    assert "Refreshed commands: vita, vedalang, vedalang-dev" in stdout


def test_run_update_command_invokes_uv_when_remote_is_newer(monkeypatch, capsys):
    monkeypatch.setattr(handlers, "_get_installed_tool_version", lambda: "0.3.0")
    monkeypatch.setattr(handlers, "_fetch_latest_tool_version", lambda: "0.4.2")

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
    assert "0.3.0" in stdout
    assert "0.4.2" in stdout
    assert "Refreshed commands: vita, vedalang, vedalang-dev" in stdout


def test_run_update_command_refreshes_when_latest_unknown(monkeypatch, capsys):
    monkeypatch.setattr(handlers, "_get_installed_tool_version", lambda: "0.4.2")
    monkeypatch.setattr(handlers, "_fetch_latest_tool_version", lambda: None)

    def fake_run(command, check):
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(handlers.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        handlers.run_update_command(argparse.Namespace())

    assert excinfo.value.code == 0
    stdout = capsys.readouterr().out
    assert "Could not determine latest GitHub main version" in stdout


def test_run_update_command_propagates_uv_failure(monkeypatch):
    monkeypatch.setattr(handlers, "_get_installed_tool_version", lambda: "0.3.0")
    monkeypatch.setattr(handlers, "_fetch_latest_tool_version", lambda: "0.4.2")

    def fake_run(command, check):
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(handlers.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        handlers.run_update_command(argparse.Namespace())

    assert excinfo.value.code == 1


def test_run_update_command_handles_missing_uv(monkeypatch, capsys):
    monkeypatch.setattr(handlers, "_get_installed_tool_version", lambda: "0.3.0")
    monkeypatch.setattr(handlers, "_fetch_latest_tool_version", lambda: "0.4.2")

    def fake_run(command, check):
        raise FileNotFoundError

    monkeypatch.setattr(handlers.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        handlers.run_update_command(argparse.Namespace())

    assert excinfo.value.code == 2
    assert "uv was not found on PATH" in capsys.readouterr().err
