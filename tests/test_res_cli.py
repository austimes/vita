import argparse
import json
from pathlib import Path

import vedalang.cli as cli

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def _viz_args(**overrides):
    base = {
        "file": None,
        "port": 8765,
        "no_browser": True,
        "mermaid": False,
        "variants": False,
        "debug": False,
        "stop": False,
        "status": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cmd_res_query_json_output(capsys):
    args = argparse.Namespace(
        file=EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml",
        mode="source",
        granularity="role",
        lens="system",
        region=[],
        case=None,
        sector=[],
        scope=[],
        no_cache=True,
        strict_compiled=False,
        json=True,
    )

    exit_code = cli.cmd_res_query(args)
    assert exit_code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "1"
    assert payload["status"] == "ok"


def test_cmd_res_mermaid_outputs_flowchart(capsys):
    args = argparse.Namespace(
        file=EXAMPLES_DIR / "toy_sectors/toy_buildings.veda.yaml",
        mode="source",
        granularity="variant",
        lens="system",
        region=[],
        case=None,
        sector=[],
        scope=[],
        no_cache=True,
        strict_compiled=False,
        json=False,
    )

    exit_code = cli.cmd_res_mermaid(args)
    assert exit_code == 0

    output = capsys.readouterr().out
    assert output.startswith("flowchart LR")


def test_cmd_viz_stop_removes_stale_pid_file(tmp_path, monkeypatch, capsys):
    pid_file = tmp_path / "vedalang-viz-8765.pid"
    pid_file.write_text("12345\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_viz_pid_file", lambda _: pid_file)
    monkeypatch.setattr(cli, "_pid_is_running", lambda _: False)
    monkeypatch.setattr(cli, "_find_listener_pid", lambda _: None)

    exit_code = cli.cmd_viz(_viz_args(stop=True))

    assert exit_code == 0
    assert "No viz server is running on port 8765." in capsys.readouterr().out
    assert not pid_file.exists()


def test_cmd_viz_start_errors_when_tracked_server_running(monkeypatch, capsys):
    pid_file = Path("/tmp/vedalang-viz-test.pid")
    monkeypatch.setattr(cli, "_viz_pid_file", lambda _: pid_file)
    monkeypatch.setattr(cli, "_read_viz_pid", lambda _: 4321)
    monkeypatch.setattr(cli, "_pid_is_running", lambda _: True)

    exit_code = cli.cmd_viz(_viz_args())

    assert exit_code == 2
    stderr = capsys.readouterr().err
    assert "already running on port 8765" in stderr
    assert "vedalang viz --stop --port 8765" in stderr


def test_cmd_viz_stop_falls_back_to_viz_like_listener(monkeypatch, capsys):
    pid_file = Path("/tmp/vedalang-viz-missing.pid")
    monkeypatch.setattr(cli, "_viz_pid_file", lambda _: pid_file)
    monkeypatch.setattr(cli, "_read_viz_pid", lambda _: None)
    monkeypatch.setattr(cli, "_find_listener_pid", lambda _: 2222)
    monkeypatch.setattr(cli, "_pid_looks_like_viz", lambda _: True)
    monkeypatch.setattr(cli, "_terminate_pid", lambda _: True)

    exit_code = cli.cmd_viz(_viz_args(stop=True))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Stopped viz-like process on port 8765 (pid 2222)." in output
