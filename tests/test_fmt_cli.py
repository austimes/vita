"""Unit tests for `vedalang fmt` command behavior."""

import argparse
import json
import subprocess

from vedalang import cli


def test_collect_fmt_targets_directory_filters_to_veda_yaml(tmp_path):
    root = tmp_path / "model_root"
    root.mkdir()
    (root / "ok.veda.yaml").write_text("a: 1\n", encoding="utf-8")
    (root / "ok.veda.yml").write_text("a: 1\n", encoding="utf-8")
    (root / "skip.yaml").write_text("a: 1\n", encoding="utf-8")

    nested = root / "nested"
    nested.mkdir()
    (nested / "nested_ok.veda.yaml").write_text("a: 1\n", encoding="utf-8")

    ignored = root / "node_modules"
    ignored.mkdir()
    (ignored / "ignored.veda.yaml").write_text("a: 1\n", encoding="utf-8")

    targets, missing = cli._collect_fmt_targets([root])
    assert missing == []
    assert sorted(p.name for p in targets) == [
        "nested_ok.veda.yaml",
        "ok.veda.yaml",
        "ok.veda.yml",
    ]


def test_cmd_fmt_json_reports_missing_path(tmp_path, capsys):
    missing = tmp_path / "missing.veda.yaml"
    args = argparse.Namespace(paths=[missing], check=False, json=True)

    exit_code = cli.cmd_fmt(args)
    captured = capsys.readouterr()

    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["success"] is False
    assert "Path not found" in payload["error"]


def test_cmd_fmt_check_mode_returns_1_on_drift(tmp_path, monkeypatch, capsys):
    src = tmp_path / "drift.veda.yaml"
    src.write_text("model: {name: Demo}\n", encoding="utf-8")

    monkeypatch.setattr(cli, "_resolve_prettier_command", lambda _: ["prettier"])

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["prettier"],
            returncode=1,
            stdout=f"[warn] {src}\n",
            stderr="",
        )

    monkeypatch.setattr(cli, "_run_prettier", fake_run)

    args = argparse.Namespace(paths=[src], check=True, json=True)
    exit_code = cli.cmd_fmt(args)
    captured = capsys.readouterr()

    assert exit_code == 1
    payload = json.loads(captured.out)
    assert payload["success"] is False
    assert payload["needs_formatting"] is True
    assert payload["changed"] is False


def test_cmd_fmt_write_mode_reports_success(tmp_path, monkeypatch, capsys):
    src = tmp_path / "format_me.veda.yaml"
    src.write_text("model: {name: Demo}\n", encoding="utf-8")

    monkeypatch.setattr(cli, "_resolve_prettier_command", lambda _: ["prettier"])

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["prettier"],
            returncode=0,
            stdout=str(src),
            stderr="",
        )

    monkeypatch.setattr(cli, "_run_prettier", fake_run)

    args = argparse.Namespace(paths=[src], check=False, json=True)
    exit_code = cli.cmd_fmt(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["changed"] is True
    assert payload["file_count"] == 1


def test_cmd_fmt_returns_2_when_prettier_unavailable(tmp_path, monkeypatch, capsys):
    src = tmp_path / "model.veda.yaml"
    src.write_text("model:\n  name: Demo\n", encoding="utf-8")

    monkeypatch.setattr(cli, "_resolve_prettier_command", lambda _: None)
    args = argparse.Namespace(paths=[src], check=False, json=True)

    exit_code = cli.cmd_fmt(args)
    captured = capsys.readouterr()

    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["success"] is False
    assert "Prettier not found" in payload["error"]


def test_cmd_fmt_no_matching_files_is_success(tmp_path, capsys):
    root = tmp_path / "empty_models"
    root.mkdir()
    (root / "notes.txt").write_text("no yaml", encoding="utf-8")

    args = argparse.Namespace(paths=[root], check=True, json=True)
    exit_code = cli.cmd_fmt(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["file_count"] == 0
