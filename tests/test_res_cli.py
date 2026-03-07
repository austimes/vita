import argparse
import json
from pathlib import Path

import vedalang.cli as cli

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


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
    assert payload["graph"]["nodes"]


def test_cmd_res_mermaid_outputs_flowchart(capsys):
    args = argparse.Namespace(
        file=EXAMPLES_DIR / "feature_demos/example_with_facilities.veda.yaml",
        mode="source",
        granularity="role",
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
    assert "alumina_calcination" in output
