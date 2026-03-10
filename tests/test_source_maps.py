from pathlib import Path

import yaml

from vedalang.compiler.source_maps import (
    build_source_block,
    resolve_location_to_runtime_path,
    yaml_node_for_path,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples"


def test_build_source_block_returns_exact_yaml_list_item():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_agriculture.veda.yaml"
    source_text = source_file.read_text(encoding="utf-8")
    source = yaml.safe_load(source_text)
    root = yaml.compose(source_text)
    runtime_path = resolve_location_to_runtime_path(source, "technology_roles[2]")
    assert runtime_path is not None
    node = yaml_node_for_path(root, runtime_path)
    assert node is not None

    block = build_source_block(
        source_text.splitlines(),
        start_line=node.start_mark.line + 1,
        end_line_exclusive=node.end_mark.line + 1,
    )

    assert block == {
        "start_line": 138,
        "end_line": 141,
        "lines": [
            {"line": 138, "text": "  - id: farm_input_supply"},
            {
                "line": 139,
                "text": "    primary_service: service:farm_input_supply",
            },
            {"line": 140, "text": "    technologies:"},
            {"line": 141, "text": "      - farm_input_import"},
        ],
    }


def test_build_source_block_trims_trailing_blank_and_excludes_next_sibling():
    source_file = EXAMPLES_DIR / "toy_sectors/toy_agriculture.veda.yaml"
    source_text = source_file.read_text(encoding="utf-8")
    source = yaml.safe_load(source_text)
    root = yaml.compose(source_text)
    runtime_path = resolve_location_to_runtime_path(source, "technologies[0]")
    assert runtime_path is not None
    node = yaml_node_for_path(root, runtime_path)
    assert node is not None

    block = build_source_block(
        source_text.splitlines(),
        start_line=node.start_mark.line + 1,
        end_line_exclusive=node.end_mark.line + 1,
    )

    assert block is not None
    assert block["lines"][0]["text"] == "  - id: farm_input_import"
    assert block["lines"][-1]["text"] == "    provides: service:farm_input_supply"
    assert all(line["text"] != "  - id: land_endowment" for line in block["lines"])
    assert all(line["text"] != "" for line in block["lines"])
