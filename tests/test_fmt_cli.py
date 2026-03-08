"""Unit tests for `vedalang fmt` command behavior."""

import argparse
import json
import subprocess
import textwrap

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
    src.write_text(
        "commodities: [{id: service:heat, kind: service}]\n",
        encoding="utf-8",
    )

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
    src.write_text(
        "commodities: [{id: service:heat, kind: service}]\n",
        encoding="utf-8",
    )

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
    src.write_text(
        "commodities:\n  - id: service:heat\n    kind: service\n",
        encoding="utf-8",
    )

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


def test_canonicalize_yaml_text_sorts_and_adds_blank_lines():
    source = textwrap.dedent(
        """\
        runs:
          - region_partition: national
            id: run_z
          - id: run_a
            region_partition: national
        technology_roles:
          - role: conversion
            id: role_b
          - id: role_a
            role: conversion
        commodities:
          - kind: service
            id: service:z
          - id: service:a
            kind: service
        """
    )

    formatted = cli._canonicalize_yaml_text(source)
    assert formatted is not None
    assert formatted.startswith("commodities:\n")
    assert "\n\ntechnology_roles:\n" in formatted
    assert "\n\nruns:\n" in formatted
    assert formatted.index("id: service:a") < formatted.index("id: service:z")
    assert formatted.index("id: role_a") < formatted.index("id: role_b")
    assert formatted.index("id: run_a") < formatted.index("id: run_z")
    assert "\n\n- id: service:z\n" in formatted


def test_cmd_fmt_check_mode_returns_1_on_canonical_drift(tmp_path, monkeypatch, capsys):
    src = tmp_path / "canonical_drift.veda.yaml"
    src.write_text(
        "technology_roles:\n"
        "  - role: conversion\n"
        "    id: role_b\n"
        "commodities:\n"
        "  - kind: service\n"
        "    id: service:heat\n",
        encoding="utf-8",
    )
    original = src.read_text(encoding="utf-8")

    monkeypatch.setattr(cli, "_resolve_prettier_command", lambda _: ["prettier"])

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["prettier"],
            returncode=0,
            stdout="",
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
    assert payload["canonical_drift_count"] == 1
    assert src.read_text(encoding="utf-8") == original


def test_cmd_fmt_write_mode_applies_canonicalization(tmp_path, monkeypatch, capsys):
    src = tmp_path / "canonicalize_me.veda.yaml"
    src.write_text(
        "technology_roles:\n"
        "  - role: conversion\n"
        "    id: role_b\n"
        "  - role: conversion\n"
        "    id: role_a\n"
        "runs:\n"
        "  - region_partition: national\n"
        "    id: run_z\n"
        "  - region_partition: national\n"
        "    id: run_a\n"
        "commodities:\n"
        "  - kind: service\n"
        "    id: service:z\n"
        "  - kind: service\n"
        "    id: service:a\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_resolve_prettier_command", lambda _: ["prettier"])

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["prettier"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(cli, "_run_prettier", fake_run)

    args = argparse.Namespace(paths=[src], check=False, json=True)
    exit_code = cli.cmd_fmt(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["canonical_drift_count"] == 1

    updated = src.read_text(encoding="utf-8")
    assert updated.startswith("commodities:\n")
    assert "\n\ntechnology_roles:\n" in updated
    assert "\n\nruns:\n" in updated
    assert updated.index("id: service:a") < updated.index("id: service:z")
    assert updated.index("id: role_a") < updated.index("id: role_b")
    assert updated.index("id: run_a") < updated.index("id: run_z")
