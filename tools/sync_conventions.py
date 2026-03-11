"""Sync generated canonical convention snippets in docs.

Usage:
  uv run python tools/sync_conventions.py
  uv run python tools/sync_conventions.py --check
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from vedalang.conventions import (
    commodity_namespace_enum,
    commodity_type_enum,
    format_enum_pipe,
    process_stage_enum,
    scenario_category_enum,
)


@dataclass(frozen=True)
class BlockSpec:
    path: Path
    marker: str
    body: str


def _replace_generated_block(text: str, marker: str, body: str) -> str:
    start = f"<!-- GENERATED:{marker}:start -->"
    end = f"<!-- GENERATED:{marker}:end -->"
    if start not in text or end not in text:
        raise ValueError(
            f"Missing generated block markers '{start}'/'{end}'."
        )

    prefix, remainder = text.split(start, 1)
    _, suffix = remainder.split(end, 1)
    return f"{prefix}{start}\n{body.rstrip()}\n{end}{suffix}"


def _load_schema(repo_root: Path) -> dict:
    schema_path = repo_root / "vedalang" / "schema" / "vedalang.schema.json"
    with schema_path.open(encoding="utf-8") as f:
        return json.load(f)


def _schema_property_choices(
    schema: dict, def_name: str, property_name: str
) -> tuple[str, ...]:
    property_schema = (
        schema.get("$defs", {})
        .get(def_name, {})
        .get("properties", {})
        .get(property_name, {})
    )
    enum = property_schema.get("enum")
    if isinstance(enum, list) and enum and all(isinstance(x, str) for x in enum):
        return tuple(enum)

    const = property_schema.get("const")
    if isinstance(const, str) and const:
        return (const,)

    raise ValueError(
        f"Could not find enum/const for {def_name}.{property_name} in schema."
    )


def _schema_root_property_choices(schema: dict, property_name: str) -> tuple[str, ...]:
    property_schema = schema.get("properties", {}).get(property_name, {})
    enum = property_schema.get("enum")
    if isinstance(enum, list) and enum and all(isinstance(x, str) for x in enum):
        return tuple(enum)

    const = property_schema.get("const")
    if isinstance(const, str) and const:
        return (const,)

    raise ValueError(f"Could not find enum/const for root property {property_name}.")


def _schema_oneof_kind_choices(schema: dict, def_name: str) -> tuple[str, ...]:
    kinds: list[str] = []
    one_of = schema.get("$defs", {}).get(def_name, {}).get("oneOf", [])
    for variant in one_of:
        kind = (
            variant.get("properties", {}).get("kind", {}).get("const")
        )
        if isinstance(kind, str) and kind:
            kinds.append(kind)

    if kinds:
        return tuple(kinds)

    raise ValueError(f"Could not find oneOf kind consts for {def_name} in schema.")


def _specs(repo_root: Path) -> list[BlockSpec]:
    schema = _load_schema(repo_root)
    stages = process_stage_enum()
    commodity_types = commodity_type_enum()
    commodity_energy_forms = _schema_property_choices(
        schema, "commodity", "energy_form"
    )
    commodity_namespaces = commodity_namespace_enum()
    scenario_categories = scenario_category_enum()
    flow_bases = _schema_property_choices(schema, "flow_spec", "basis")
    performance_kinds = _schema_property_choices(schema, "performance_spec", "kind")
    spatial_layer_kinds = _schema_property_choices(schema, "spatial_layer", "kind")
    partition_mapping_kinds = _schema_oneof_kind_choices(schema, "partition_mapping")
    stock_metrics = _schema_property_choices(schema, "stock_observation", "metric")
    dsl_versions = _schema_root_property_choices(schema, "dsl_version")

    canonical_enums_md = (
        f"- `stage` = one of `{format_enum_pipe(stages)}`\n"
        f"- `commodity.type` = one of `{format_enum_pipe(commodity_types)}`\n"
        "- `commodity namespace prefix` = one of "
        f"`{format_enum_pipe(commodity_namespaces)}`"
    )
    canonical_scenario_categories_md = (
        "**Canonical scenario categories:** "
        + " | ".join(f"`{category}`" for category in scenario_categories)
    )
    minimal_example_enums_md = (
        "### Enum-backed Fields In This Example\n\n"
        f"- `dsl_version`: `{format_enum_pipe(dsl_versions)}`\n"
        f"- `commodities[*].type`: `{format_enum_pipe(commodity_types)}`\n"
        "- `commodities[*].energy_form`: "
        f"`{format_enum_pipe(commodity_energy_forms)}`\n"
        f"- `technologies[*].inputs[*].basis`: `{format_enum_pipe(flow_bases)}`\n"
        "- `technologies[*].performance.kind`: "
        f"`{format_enum_pipe(performance_kinds)}`\n"
        f"- `spatial_layers[*].kind`: `{format_enum_pipe(spatial_layer_kinds)}`\n"
        "- `region_partitions[*].mapping.kind`: "
        f"`{format_enum_pipe(partition_mapping_kinds)}`\n"
        "- `facilities[*].stock.items[*].metric`: "
        f"`{format_enum_pipe(stock_metrics)}`"
    )
    llms_canonical_enums_md = (
        "### Canonical Enums (Schema-Derived)\n\n"
        f"- `stage`: `{format_enum_pipe(stages)}`\n"
        f"- `commodity.type`: `{format_enum_pipe(commodity_types)}`\n"
        "- `commodity namespace prefix`: "
        f"`{format_enum_pipe(commodity_namespaces)}`\n"
        "- `scenario category`: "
        f"`{format_enum_pipe(scenario_categories)}`"
    )

    return [
        BlockSpec(
            path=repo_root / "docs" / "vedalang-user" / "modeling-conventions.md",
            marker="canonical-enums",
            body=canonical_enums_md,
        ),
        BlockSpec(
            path=repo_root
            / "skills"
            / "vedalang-dsl-cli"
            / "references"
            / "dsl-cli-pipeline.md",
            marker="dsl-cli-canonical-enums",
            body=llms_canonical_enums_md,
        ),
        BlockSpec(
            path=repo_root / "README.md",
            marker="scenario-categories",
            body=canonical_scenario_categories_md,
        ),
        BlockSpec(
            path=repo_root / "README.md",
            marker="minimal-example-enums",
            body=minimal_example_enums_md,
        ),
        BlockSpec(
            path=repo_root / "AGENTS.md",
            marker="scenario-categories",
            body=canonical_scenario_categories_md,
        ),
        BlockSpec(
            path=repo_root / "docs" / "vedalang-user" / "tutorial.md",
            marker="minimal-example-enums",
            body=minimal_example_enums_md,
        ),
    ]


def sync_generated_blocks(repo_root: Path, *, check_only: bool) -> int:
    changed_paths: list[Path] = []
    for spec in _specs(repo_root):
        original = spec.path.read_text(encoding="utf-8")
        updated = _replace_generated_block(original, spec.marker, spec.body)
        if updated != original:
            changed_paths.append(spec.path)
            if not check_only:
                spec.path.write_text(updated, encoding="utf-8")

    if changed_paths:
        rel = [str(p.relative_to(repo_root)) for p in changed_paths]
        if check_only:
            print("Generated convention blocks out of date:")
            for path in rel:
                print(f"  - {path}")
            print("Run: uv run python tools/sync_conventions.py")
            return 1

        print("Updated generated convention blocks:")
        for path in rel:
            print(f"  - {path}")
    else:
        print("Generated convention blocks already up to date.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if generated blocks need updates.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    return sync_generated_blocks(repo_root, check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
