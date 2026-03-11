"""Tests that canonical conventions propagate from schema enums."""

from pathlib import Path

from tools.sync_conventions import sync_generated_blocks
from vedalang.conventions import (
    commodity_namespace_enum,
    commodity_namespace_type_map,
    commodity_type_enum,
    format_enum_csv,
    namespaces_for_commodity_type,
    process_stage_enum,
)
from vedalang.lint.llm_assessment import assemble_prompt

MINIMAL_SOURCE = {
    "dsl_version": "0.3",
    "commodities": [
        {"id": "electricity", "type": "energy", "energy_form": "secondary"},
        {"id": "space_heat", "type": "service"},
    ],
    "technologies": [
        {
            "id": "heat_pump",
            "provides": "space_heat",
            "inputs": [{"commodity": "electricity"}],
            "outputs": [{"commodity": "space_heat"}],
        }
    ],
    "technology_roles": [
        {
            "id": "space_heat_supply",
            "primary_service": "space_heat",
            "technologies": ["heat_pump"],
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
    expected_namespace_line = (
        "- **Commodity namespace prefix** = one of: "
        f"{format_enum_csv(commodity_namespace_enum())}."
    )

    assert expected_stage_line in system_prompt
    assert expected_type_line in system_prompt
    assert expected_namespace_line in system_prompt


def test_generated_conventions_blocks_are_synced():
    repo_root = Path(__file__).resolve().parents[1]
    assert sync_generated_blocks(repo_root, check_only=True) == 0


def test_namespace_type_mapping_covers_all_schema_namespaces():
    mapping = commodity_namespace_type_map()
    assert set(mapping.keys()) == set(commodity_namespace_enum())

    assert mapping["primary"] == frozenset({"energy"})
    assert mapping["secondary"] == frozenset({"energy"})
    assert mapping["service"] == frozenset({"service"})
    assert mapping["emission"] == frozenset({"emission"})


def test_reverse_namespace_lookup_for_type():
    assert namespaces_for_commodity_type("energy") == (
        "primary",
        "secondary",
        "resource",
    )
    assert namespaces_for_commodity_type("service") == ("service",)
