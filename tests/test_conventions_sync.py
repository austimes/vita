"""Tests that canonical conventions propagate from schema enums."""

from pathlib import Path

from tools.sync_conventions import sync_generated_blocks
from vedalang.conventions import (
    commodity_type_enum,
    format_enum_csv,
    process_stage_enum,
)
from vedalang.lint.llm_assessment import assemble_prompt

MINIMAL_SOURCE = {
    "model": {
        "name": "conventions_sync_test",
        "regions": ["R1"],
        "commodities": [
            {"id": "energy:electricity", "type": "energy"},
            {"id": "service:space_heat", "type": "service"},
        ],
    },
    "process_roles": [
        {
            "id": "provide_space_heat",
            "stage": "end_use",
            "required_inputs": [{"commodity": "energy:electricity"}],
            "required_outputs": [{"commodity": "service:space_heat"}],
        }
    ],
    "process_variants": [
        {
            "id": "heat_pump",
            "role": "provide_space_heat",
            "inputs": [{"commodity": "energy:electricity"}],
            "outputs": [{"commodity": "service:space_heat"}],
        }
    ],
}


def test_llm_system_prompt_uses_schema_enums():
    system_prompt, _ = assemble_prompt(MINIMAL_SOURCE)

    expected_stage_line = (
        f"- **Stage** = one of: {format_enum_csv(process_stage_enum())}."
    )
    expected_type_line = (
        f"- **Commodity type** = one of: {format_enum_csv(commodity_type_enum())}."
    )

    assert expected_stage_line in system_prompt
    assert expected_type_line in system_prompt


def test_generated_conventions_blocks_are_synced():
    repo_root = Path(__file__).resolve().parents[1]
    assert sync_generated_blocks(repo_root, check_only=True) == 0
