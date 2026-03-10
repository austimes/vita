"""Shared source-location helpers for YAML-backed diagnostics."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, SequenceNode

_LOCATION_SEGMENT_RE = re.compile(r"^(?P<key>[^\[\]]+)(?P<idx>(?:\[[^\]]+\])*)$")
_LOCATION_INDEX_RE = re.compile(r"\[([^\]]+)\]")
_LIST_ID_KEYS = (
    "id",
    "name",
    "commodity",
    "process",
    "role",
    "variant",
    "case",
    "parameter",
    "attribute",
    "region",
    "code",
)


def split_location_segments(location: str) -> list[str]:
    """Split dotted location path while preserving bracket contents."""
    out: list[str] = []
    depth = 0
    token_chars: list[str] = []
    for ch in location.strip():
        if ch == "." and depth == 0:
            if token_chars:
                out.append("".join(token_chars))
                token_chars = []
            continue
        if ch == "[":
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
        token_chars.append(ch)
    if token_chars:
        out.append("".join(token_chars))
    return out


def parse_location_steps(location: str) -> list[tuple[str, str | int]]:
    """Parse location text into key/index traversal steps."""
    if not location or location == "root":
        return []
    steps: list[tuple[str, str | int]] = []
    for segment in split_location_segments(location):
        match = _LOCATION_SEGMENT_RE.match(segment)
        if match is None:
            return []
        key = match.group("key")
        if key:
            steps.append(("key", key))
        for raw_idx in _LOCATION_INDEX_RE.findall(match.group("idx") or ""):
            idx = raw_idx.strip().strip("'\"")
            if idx.isdigit():
                steps.append(("index", int(idx)))
            elif idx:
                steps.append(("index", idx))
    return steps


def format_location_path(path_tokens: list[str | int]) -> str:
    """Convert jsonschema path tokens to dotted+indexed location format."""
    if not path_tokens:
        return "root"
    parts: list[str] = []
    for token in path_tokens:
        if isinstance(token, int):
            if not parts:
                parts.append(f"[{token}]")
            else:
                parts[-1] = f"{parts[-1]}[{token}]"
            continue
        parts.append(token)
    return ".".join(parts)


def find_list_item_index(items: list[Any], label: str) -> int | None:
    """Find list index for string labels used in location bracket notation."""
    if label.isdigit():
        idx = int(label)
        return idx if 0 <= idx < len(items) else None
    for idx, item in enumerate(items):
        if isinstance(item, dict):
            for key in _LIST_ID_KEYS:
                value = item.get(key)
                if value is not None and str(value) == label:
                    return idx
        elif str(item) == label:
            return idx
    return None


def resolve_location_to_runtime_path(
    source: dict[str, Any],
    location: str,
) -> list[str | int] | None:
    """Resolve a location string to a concrete dict/list traversal path."""
    steps = parse_location_steps(location)
    if not steps and location not in {"", "root"}:
        return None
    current: object = source
    runtime_path: list[str | int] = []
    for kind, token in steps:
        if kind == "key":
            if not isinstance(current, dict) or token not in current:
                return None
            runtime_path.append(token)
            current = current[token]
            continue

        if isinstance(token, int):
            if not isinstance(current, list) or token < 0 or token >= len(current):
                return None
            runtime_path.append(token)
            current = current[token]
            continue

        if isinstance(current, list):
            idx = find_list_item_index(current, token)
            if idx is None:
                return None
            runtime_path.append(idx)
            current = current[idx]
            continue

        if isinstance(current, dict) and token in current:
            runtime_path.append(token)
            current = current[token]
            continue

        return None
    return runtime_path


def yaml_node_for_path(root: Node, path: list[str | int]) -> Node | None:
    """Traverse a YAML AST node by a runtime path."""
    node: Node | None = root
    for token in path:
        if isinstance(token, str):
            if not isinstance(node, MappingNode):
                return None
            matched: Node | None = None
            for key_node, value_node in node.value:
                if key_node.value == token:
                    matched = value_node
                    break
            if matched is None:
                return None
            node = matched
            continue

        if not isinstance(node, SequenceNode):
            return None
        if token < 0 or token >= len(node.value):
            return None
        node = node.value[token]
    return node


def build_source_excerpt(
    source_lines: list[str],
    *,
    line: int,
    end_line: int,
    column: int,
    max_lines: int = 5,
) -> dict[str, Any] | None:
    """Build a compact source excerpt for a diagnostic."""
    if not source_lines:
        return None

    start_line = max(1, line - 1)
    finish_line = min(len(source_lines), end_line + 1)
    if finish_line - start_line + 1 > max_lines:
        finish_line = start_line + max_lines - 1

    lines: list[dict[str, Any]] = []
    for ln in range(start_line, finish_line + 1):
        lines.append({"line": ln, "text": source_lines[ln - 1]})

    return {
        "start_line": start_line,
        "end_line": finish_line,
        "caret_line": line,
        "caret_column": max(1, column),
        "lines": lines,
    }


def build_source_block(
    source_lines: list[str],
    *,
    start_line: int,
    end_line_exclusive: int,
) -> dict[str, Any] | None:
    """Build an exact YAML source block with per-line numbers."""
    if not source_lines:
        return None

    first_line = max(1, start_line)
    exclusive_line = max(first_line + 1, end_line_exclusive)
    block_lines = source_lines[first_line - 1 : max(first_line - 1, exclusive_line - 1)]
    while block_lines and not block_lines[-1].strip():
        block_lines.pop()
    if not block_lines:
        return None

    lines: list[dict[str, Any]] = []
    for offset, text in enumerate(block_lines):
        lines.append({"line": first_line + offset, "text": text})

    return {
        "start_line": first_line,
        "end_line": first_line + len(block_lines) - 1,
        "lines": lines,
    }


def attach_source_positions(
    diagnostics: list[dict[str, Any]],
    *,
    source: dict[str, Any],
    source_text: str,
) -> None:
    """Attach line/column/source excerpt metadata when location paths exist."""
    if not diagnostics or not isinstance(source, dict) or not source_text:
        return

    try:
        root = yaml.compose(source_text)
    except yaml.YAMLError:
        return
    if root is None:
        return

    source_lines = source_text.splitlines()
    for diag in diagnostics:
        raw_location = diag.get("location") or diag.get("path")
        if not isinstance(raw_location, str) or not raw_location:
            continue

        runtime_path = resolve_location_to_runtime_path(source, raw_location)
        if runtime_path is None:
            continue
        node = yaml_node_for_path(root, runtime_path)
        if node is None:
            continue

        line = node.start_mark.line + 1
        column = node.start_mark.column + 1
        end_line = max(line, node.end_mark.line + 1)
        end_column = max(1, node.end_mark.column + 1)

        diag["line"] = line
        diag["column"] = column
        diag["end_line"] = end_line
        diag["end_column"] = end_column
        diag["source_excerpt"] = build_source_excerpt(
            source_lines,
            line=line,
            end_line=end_line,
            column=column,
        )
        if "location" not in diag and "path" in diag:
            diag["location"] = diag["path"]


def attach_source_positions_from_file(
    diagnostics: list[dict[str, Any]],
    *,
    source: dict[str, Any],
    file_path: Path,
) -> None:
    """Attach source positions by reading the YAML text from a file."""
    try:
        source_text = file_path.read_text(encoding="utf-8")
    except Exception:
        return
    attach_source_positions(diagnostics, source=source, source_text=source_text)
