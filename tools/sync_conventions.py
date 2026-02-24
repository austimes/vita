"""Sync generated canonical convention snippets in docs from schema enums.

Usage:
  uv run python tools/sync_conventions.py
  uv run python tools/sync_conventions.py --check
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from vedalang.conventions import (
    commodity_type_enum,
    format_enum_pipe,
    process_stage_enum,
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


def _specs(repo_root: Path) -> list[BlockSpec]:
    stages = process_stage_enum()
    commodity_types = commodity_type_enum()

    canonical_enums_md = (
        f"- `stage` = one of `{format_enum_pipe(stages)}`\n"
        f"- `commodity.type` = one of `{format_enum_pipe(commodity_types)}`"
    )
    canonical_stages_md = "Valid stages: " + ", ".join(
        f"`{stage}`" for stage in stages
    ) + "."

    return [
        BlockSpec(
            path=repo_root / "docs" / "vedalang-user" / "modeling-conventions.md",
            marker="canonical-enums",
            body=canonical_enums_md,
        ),
        BlockSpec(
            path=repo_root / "docs" / "migration_guide_toy_refactor.md",
            marker="canonical-stages",
            body=canonical_stages_md,
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
