"""Structured node inspector payloads for the RES viewer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from vedalang.compiler.source_maps import (
    build_source_excerpt,
    resolve_location_to_runtime_path,
    yaml_node_for_path,
)
from vedalang.compiler.v0_2_ast import V0_2Source
from vedalang.compiler.v0_2_backend import _commodity_symbol, _process_symbol
from vedalang.compiler.v0_2_resolution import ResolvedDefinitionGraph, RunContext


@dataclass(frozen=True)
class InspectorContext:
    source: dict[str, Any]
    source_file: Path
    parsed_source: V0_2Source
    graph: ResolvedDefinitionGraph
    run_context: RunContext
    csir: dict[str, Any]
    cpir: dict[str, Any]
    explain: dict[str, Any] | None
    tableir: dict[str, Any] | None
    manifest: dict[str, Any] | None


class SourceLocator:
    """Resolve structural source paths into file/line/excerpt metadata."""

    def __init__(self, source: dict[str, Any], source_file: Path) -> None:
        self._source = source
        self._source_file = source_file.resolve()
        try:
            source_text = self._source_file.read_text(encoding="utf-8")
        except OSError:
            source_text = ""
        self._source_lines = source_text.splitlines()
        self._root = None
        if source_text:
            try:
                self._root = yaml.compose(source_text)
            except yaml.YAMLError:
                self._root = None

    def locate(self, path: str | None) -> dict[str, Any] | None:
        if not path or self._root is None:
            return None
        runtime_path = resolve_location_to_runtime_path(self._source, path)
        if runtime_path is None:
            return None
        node = yaml_node_for_path(self._root, runtime_path)
        if node is None:
            return None
        line = node.start_mark.line + 1
        column = node.start_mark.column + 1
        end_line = max(line, node.end_mark.line + 1)
        excerpt = build_source_excerpt(
            self._source_lines,
            line=line,
            end_line=end_line,
            column=column,
        )
        return {
            "file": str(self._source_file),
            "path": path,
            "line": line,
            "column": column,
            "excerpt": excerpt,
        }


@dataclass(frozen=True)
class TableRowRef:
    file: str
    sheet: str
    table_index: int
    table_key: str
    tag: str
    row: dict[str, Any]


@dataclass(frozen=True)
class TableIndexes:
    process_rows: dict[str, dict[str, list[dict[str, Any]]]]
    commodity_rows: dict[str, dict[str, list[dict[str, Any]]]]


def _local_object_maps(parsed_source: V0_2Source) -> dict[str, dict[str, Any]]:
    return {
        "commodities": {item.id: item for item in parsed_source.commodities},
        "technologies": {item.id: item for item in parsed_source.technologies},
        "technology_roles": {
            item.id: item for item in parsed_source.technology_roles
        },
        "facilities": {item.id: item for item in parsed_source.facilities},
        "fleets": {item.id: item for item in parsed_source.fleets},
        "opportunities": {item.id: item for item in parsed_source.opportunities},
    }


def _normalize_json(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize_json(asdict(value))
    if isinstance(value, dict):
        return {
            str(key): _normalize_json(item)
            for key, item in value.items()
            if key != "source_ref"
        }
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _item(
    *,
    label: str,
    kind: str,
    object_id: str | None,
    attributes: Any,
    source_location: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "label": label,
        "kind": kind,
        "id": object_id,
        "attributes": _normalize_json(attributes),
        "source_location": source_location,
    }


def _section(
    *,
    key: str,
    label: str,
    default_open: bool,
    items: list[dict[str, Any]],
    partial: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "default_open": default_open,
        "status": "partial" if partial else "ok",
        "items": items,
    }


def _symbol_manifest_entries(
    manifest: dict[str, Any] | None,
    symbol_type: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(manifest, dict):
        return {}
    symbols = manifest.get("symbols", {})
    if not isinstance(symbols, dict):
        return {}
    entries = symbols.get(symbol_type, [])
    if not isinstance(entries, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name"):
            out[str(entry["name"])] = entry
    return out


def _table_indexes(tableir: dict[str, Any] | None) -> TableIndexes:
    process_rows = {
        "~FI_PROCESS": {},
        "~FI_T": {},
        "~TFM_INS": {},
    }
    commodity_rows = {
        "~FI_COMM": {},
        "~FI_T": {},
        "~TFM_INS": {},
    }
    if not isinstance(tableir, dict):
        return TableIndexes(process_rows=process_rows, commodity_rows=commodity_rows)

    for file_def in tableir.get("files", []):
        file_path = str(file_def.get("path", ""))
        for sheet in file_def.get("sheets", []):
            sheet_name = str(sheet.get("name", ""))
            for table_index, table in enumerate(sheet.get("tables", [])):
                tag = str(table.get("tag", ""))
                table_key = f"{file_path}::{sheet_name}::{table_index}::{tag}"
                rows = table.get("rows", [])
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    ref = _normalize_json(
                        asdict(
                            TableRowRef(
                                file=file_path,
                                sheet=sheet_name,
                                table_index=table_index,
                                table_key=table_key,
                                tag=tag,
                                row=row,
                            )
                        )
                    )
                    process_symbol = row.get("process")
                    if (
                        isinstance(process_symbol, str)
                        and process_symbol
                        and tag in process_rows
                    ):
                        process_rows[tag].setdefault(process_symbol, []).append(ref)
                    if tag == "~FI_COMM":
                        commodity_symbol = row.get("commodity")
                        if isinstance(commodity_symbol, str) and commodity_symbol:
                            commodity_rows[tag].setdefault(commodity_symbol, []).append(
                                ref
                            )
                    elif tag in {"~FI_T", "~TFM_INS"}:
                        referenced = {
                            value
                            for key, value in row.items()
                            if key in {"commodity", "commodity-in", "commodity-out"}
                            and isinstance(value, str)
                            and value
                        }
                        for commodity_symbol in referenced:
                            commodity_rows[tag].setdefault(commodity_symbol, []).append(
                                ref
                            )
    return TableIndexes(process_rows=process_rows, commodity_rows=commodity_rows)


def _process_times_summary(
    process_symbol: str,
    *,
    table_indexes: TableIndexes,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "process_symbol": process_symbol,
        "input_commodities": [],
        "output_commodities": [],
        "emission_attributes": [],
        "times_attributes": [],
    }
    input_symbols: set[str] = set()
    output_symbols: set[str] = set()
    fi_t_rows = table_indexes.process_rows["~FI_T"].get(process_symbol, [])
    for ref in fi_t_rows:
        row = ref["row"]
        commodity_in = row.get("commodity-in")
        commodity_out = row.get("commodity-out")
        if isinstance(commodity_in, str) and commodity_in:
            input_symbols.add(commodity_in)
        if isinstance(commodity_out, str) and commodity_out:
            output_symbols.add(commodity_out)
        if row.get("attribute"):
            summary["emission_attributes"].append(_normalize_json(ref))
        canonical_attrs = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "region",
                "process",
                "commodity-in",
                "commodity-out",
                "commodity",
                "attribute",
                "value",
            }
            and value not in (None, "", [])
        }
        if canonical_attrs:
            summary["times_attributes"].append(
                {
                    "file": ref["file"],
                    "sheet": ref["sheet"],
                    "tag": ref["tag"],
                    "attributes": canonical_attrs,
                }
            )
    summary["input_commodities"] = sorted(input_symbols)
    summary["output_commodities"] = sorted(output_symbols)
    summary["times_attributes"].extend(
        table_indexes.process_rows["~TFM_INS"].get(process_symbol, [])
    )
    return summary


def _commodity_times_summary(
    commodity_symbol: str,
    *,
    table_indexes: TableIndexes,
) -> dict[str, Any]:
    return {
        "commodity_symbol": commodity_symbol,
        "fi_comm_rows": table_indexes.commodity_rows["~FI_COMM"].get(
            commodity_symbol, []
        ),
        "fi_t_rows": table_indexes.commodity_rows["~FI_T"].get(commodity_symbol, []),
        "tfm_ins_rows": table_indexes.commodity_rows["~TFM_INS"].get(
            commodity_symbol, []
        ),
    }


def _asset_kind_and_id(source_asset: str | None) -> tuple[str | None, str | None]:
    if not source_asset:
        return None, None
    if source_asset.startswith("facilities."):
        return "facility", source_asset.split(".", 1)[1]
    if source_asset.startswith("fleets."):
        return "fleet", source_asset.split(".", 1)[1]
    return None, None


def _sorted_unique(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return sorted(out, key=lambda item: str(item))


def _technology_to_role_map(
    graph: ResolvedDefinitionGraph,
) -> dict[str, str]:
    return {
        str(technology): str(role.id)
        for role in graph.technology_roles.values()
        for technology in role.technologies
    }


def _local_or_resolved_item(
    *,
    local_maps: dict[str, dict[str, Any]],
    resolved_maps: dict[str, dict[str, Any]],
    map_key: str,
    object_id: str,
    label: str,
    kind: str,
    locator: SourceLocator,
) -> tuple[dict[str, Any] | None, bool]:
    local = local_maps.get(map_key, {}).get(object_id)
    if local is not None:
        source_path = getattr(getattr(local, "source_ref", None), "path", None)
        source_location = locator.locate(source_path)
        return (
            _item(
                label=label,
                kind=kind,
                object_id=object_id,
                attributes=local,
                source_location=source_location,
            ),
            source_location is None,
        )
    resolved = resolved_maps.get(map_key, {}).get(object_id)
    if resolved is None:
        return None, True
    return (
        _item(
            label=label,
            kind=kind,
            object_id=object_id,
            attributes=resolved,
            source_location=None,
        ),
        True,
    )


def _process_semantic_origin_item(
    process: dict[str, Any],
    *,
    role_instances: dict[str, dict[str, Any]],
    opportunities: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    source_role_instance = str(process.get("source_role_instance", "") or "")
    if source_role_instance:
        role_instance = role_instances.get(source_role_instance)
        if role_instance is not None:
            return _item(
                label="resolved role instance",
                kind="technology_role_instance",
                object_id=source_role_instance,
                attributes=role_instance,
                source_location=None,
            )
    source_opportunity = str(process.get("source_opportunity", "") or "")
    if source_opportunity:
        opportunity = opportunities.get(source_opportunity)
        if opportunity is not None:
            return _item(
                label="resolved opportunity",
                kind="opportunity",
                object_id=source_opportunity,
                attributes=opportunity,
                source_location=None,
            )
    return None


def _commodity_usage_item(
    commodity_id: str,
    *,
    cpir: dict[str, Any],
) -> dict[str, Any]:
    produced_by: list[str] = []
    consumed_by: list[str] = []
    emitted_by: list[str] = []
    network_arcs: list[str] = []
    for process in cpir.get("processes", []):
        process_id = str(process.get("id", ""))
        for flow in process.get("flows", []):
            if str(flow.get("commodity", "")) != commodity_id:
                continue
            direction = str(flow.get("direction", ""))
            if direction == "out":
                produced_by.append(process_id)
            elif direction == "in":
                consumed_by.append(process_id)
            elif direction == "emission":
                emitted_by.append(process_id)
    for arc in cpir.get("network_arcs", []):
        if str(arc.get("commodity", "")) == commodity_id:
            network_arcs.append(str(arc.get("id", "")))
    return _item(
        label="commodity usage",
        kind="commodity_usage",
        object_id=commodity_id,
        attributes={
            "commodity": commodity_id,
            "produced_by": _sorted_unique(produced_by),
            "consumed_by": _sorted_unique(consumed_by),
            "emitted_by": _sorted_unique(emitted_by),
            "network_arcs": _sorted_unique(network_arcs),
        },
        source_location=None,
    )


def _process_veda_items(
    process_ids: list[str],
    *,
    manifest_processes: dict[str, dict[str, Any]],
    table_indexes: TableIndexes,
) -> tuple[list[dict[str, Any]], bool]:
    items: list[dict[str, Any]] = []
    partial = False
    for process_id in _sorted_unique(process_ids):
        process_symbol = _process_symbol(process_id)
        manifest_entry = manifest_processes.get(process_symbol)
        if manifest_entry is None:
            partial = True
        items.append(
            _item(
                label="VEDA process",
                kind="veda_process",
                object_id=process_symbol,
                attributes={
                    "process_id": process_id,
                    "process_symbol": process_symbol,
                    "manifest_entry": manifest_entry,
                    "fi_process_rows": table_indexes.process_rows["~FI_PROCESS"].get(
                        process_symbol, []
                    ),
                    "fi_t_rows": table_indexes.process_rows["~FI_T"].get(
                        process_symbol, []
                    ),
                    "tfm_ins_rows": table_indexes.process_rows["~TFM_INS"].get(
                        process_symbol, []
                    ),
                    "times_summary": _process_times_summary(
                        process_symbol,
                        table_indexes=table_indexes,
                    ),
                },
                source_location=None,
            )
        )
    return items, partial


def _commodity_veda_items(
    commodity_ids: list[str],
    *,
    manifest_commodities: dict[str, dict[str, Any]],
    table_indexes: TableIndexes,
) -> tuple[list[dict[str, Any]], bool]:
    items: list[dict[str, Any]] = []
    partial = False
    for commodity_id in _sorted_unique(commodity_ids):
        commodity_symbol = _commodity_symbol(commodity_id)
        manifest_entry = manifest_commodities.get(commodity_symbol)
        if manifest_entry is None:
            partial = True
        items.append(
            _item(
                label="VEDA commodity",
                kind="veda_commodity",
                object_id=commodity_symbol,
                attributes={
                    "commodity_id": commodity_id,
                    "commodity_symbol": commodity_symbol,
                    "manifest_entry": manifest_entry,
                    "times_summary": _commodity_times_summary(
                        commodity_symbol,
                        table_indexes=table_indexes,
                    ),
                },
                source_location=None,
            )
        )
    return items, partial


def build_system_node_inspectors(
    *,
    graph_nodes: list[dict[str, Any]],
    details_nodes: dict[str, dict[str, Any]],
    context: InspectorContext,
) -> dict[str, dict[str, Any]]:
    local_maps = _local_object_maps(context.parsed_source)
    resolved_maps = {
        "commodities": context.graph.commodities,
        "technologies": context.graph.technologies,
        "technology_roles": context.graph.technology_roles,
        "facilities": context.graph.facilities,
        "fleets": context.graph.fleets,
        "opportunities": context.graph.opportunities,
    }
    locator = SourceLocator(context.source, context.source_file)
    table_indexes = _table_indexes(context.tableir)
    manifest_processes = _symbol_manifest_entries(context.manifest, "processes")
    manifest_commodities = _symbol_manifest_entries(context.manifest, "commodities")
    role_instances = {
        str(item["id"]): item
        for item in context.csir.get("technology_role_instances", [])
        if isinstance(item, dict) and item.get("id")
    }
    opportunities = {
        str(item["id"]): item
        for item in context.csir.get("opportunities", [])
        if isinstance(item, dict) and item.get("id")
    }
    processes = {
        str(item["id"]): item
        for item in context.cpir.get("processes", [])
        if isinstance(item, dict) and item.get("id")
    }
    technology_to_role = _technology_to_role_map(context.graph)

    inspectors: dict[str, dict[str, Any]] = {}
    node_by_id = {
        str(node.get("id", "")): node
        for node in graph_nodes
        if isinstance(node, dict) and node.get("id")
    }

    for node_id, node_details in details_nodes.items():
        node = node_by_id.get(node_id)
        if node is None:
            continue
        node_type = str(node.get("type", ""))
        if node_type in {"role", "instance"}:
            member_process_ids = [
                process_id
                for process_id in node_details.get("member_process_ids", []) or []
                if isinstance(process_id, str) and process_id
            ]
            if not member_process_ids:
                process_id = node_details.get("process_id")
                if isinstance(process_id, str) and process_id:
                    member_process_ids = [process_id]
            member_processes = [
                processes[process_id]
                for process_id in _sorted_unique(member_process_ids)
                if process_id in processes
            ]
            if not member_processes:
                continue
            primary_process = member_processes[0]
            role_id = node_details.get("technology_role")
            if not isinstance(role_id, str) or not role_id:
                role_id = technology_to_role.get(str(primary_process.get("technology")))

            dsl_items: list[dict[str, Any]] = []
            dsl_partial = False
            source_asset = str(primary_process.get("source_asset", "") or "")
            if not source_asset:
                source_role_instance = str(
                    primary_process.get("source_role_instance", "") or ""
                )
                source_asset = str(
                    role_instances.get(source_role_instance, {}).get("source_asset", "")
                    or ""
                )
            asset_kind, asset_id = _asset_kind_and_id(source_asset)
            if asset_kind and asset_id:
                asset_item, missing = _local_or_resolved_item(
                    local_maps=local_maps,
                    resolved_maps=resolved_maps,
                    map_key=f"{asset_kind}s",
                    object_id=asset_id,
                    label=asset_kind,
                    kind=asset_kind,
                    locator=locator,
                )
                if asset_item is not None:
                    dsl_items.append(asset_item)
                dsl_partial = dsl_partial or missing
            source_opportunity = str(
                primary_process.get("source_opportunity", "") or ""
            )
            if source_opportunity:
                opportunity_item, missing = _local_or_resolved_item(
                    local_maps=local_maps,
                    resolved_maps=resolved_maps,
                    map_key="opportunities",
                    object_id=source_opportunity,
                    label="opportunity",
                    kind="opportunity",
                    locator=locator,
                )
                if opportunity_item is not None:
                    dsl_items.append(opportunity_item)
                dsl_partial = dsl_partial or missing
            if isinstance(role_id, str) and role_id:
                role_item, missing = _local_or_resolved_item(
                    local_maps=local_maps,
                    resolved_maps=resolved_maps,
                    map_key="technology_roles",
                    object_id=role_id,
                    label="technology role",
                    kind="technology_role",
                    locator=locator,
                )
                if role_item is not None:
                    dsl_items.append(role_item)
                dsl_partial = dsl_partial or missing
            technology_ids = [
                str(value)
                for value in node_details.get("member_technologies", []) or []
                if isinstance(value, str) and value
            ] or [
                str(process.get("technology", ""))
                for process in member_processes
                if process.get("technology")
            ]
            for technology_id in _sorted_unique(technology_ids):
                technology_item, missing = _local_or_resolved_item(
                    local_maps=local_maps,
                    resolved_maps=resolved_maps,
                    map_key="technologies",
                    object_id=technology_id,
                    label="technology",
                    kind="technology",
                    locator=locator,
                )
                if technology_item is not None:
                    dsl_items.append(technology_item)
                dsl_partial = dsl_partial or missing

            semantic_items: list[dict[str, Any]] = []
            origin_item = _process_semantic_origin_item(
                primary_process,
                role_instances=role_instances,
                opportunities=opportunities,
            )
            if origin_item is not None:
                semantic_items.append(origin_item)
            if (
                isinstance(role_id, str)
                and role_id
                and role_id in context.graph.technology_roles
            ):
                semantic_items.append(
                    _item(
                        label="resolved technology role",
                        kind="technology_role",
                        object_id=role_id,
                        attributes=context.graph.technology_roles[role_id],
                        source_location=None,
                    )
                )
            if node_type == "instance":
                technology_id = str(primary_process.get("technology", "") or "")
                if technology_id and technology_id in context.graph.technologies:
                    semantic_items.append(
                        _item(
                            label="resolved technology",
                            kind="technology",
                            object_id=technology_id,
                            attributes=context.graph.technologies[technology_id],
                            source_location=None,
                        )
                    )

            lowered_items: list[dict[str, Any]] = []
            if node_type == "instance":
                lowered_items.append(
                    _item(
                        label="CPIR process",
                        kind="cpir_process",
                        object_id=str(primary_process.get("id", "")),
                        attributes=primary_process,
                        source_location=None,
                    )
                )
            else:
                for process in member_processes:
                    lowered_items.append(
                        _item(
                            label="CPIR process",
                            kind="cpir_process",
                            object_id=str(process.get("id", "")),
                            attributes=process,
                            source_location=None,
                        )
                    )

            veda_items, veda_partial = _process_veda_items(
                [str(process.get("id", "")) for process in member_processes],
                manifest_processes=manifest_processes,
                table_indexes=table_indexes,
            )
            inspectors[node_id] = {
                "title": str(node.get("label", node_id)).split("\n", 1)[0],
                "kind": "process",
                "node_type": node_type,
                "summary": {
                    "run_id": context.run_context.run_id,
                    "origin_kind": node_details.get("group_origin"),
                    "model_region": node_details.get("model_region"),
                },
                "sections": [
                    _section(
                        key="dsl",
                        label="DSL attributes",
                        default_open=True,
                        items=dsl_items,
                        partial=dsl_partial,
                    ),
                    _section(
                        key="semantic",
                        label="Resolved semantic model",
                        default_open=False,
                        items=semantic_items,
                    ),
                    _section(
                        key="lowered",
                        label="Lowered IR",
                        default_open=False,
                        items=lowered_items,
                    ),
                    _section(
                        key="veda",
                        label="VEDA/TIMES",
                        default_open=False,
                        items=veda_items,
                        partial=veda_partial or context.manifest is None,
                    ),
                ],
            }
            continue

        if node_type != "commodity":
            continue

        commodity_ids = [
            commodity_id
            for commodity_id in node_details.get("commodity_ids", []) or []
            if isinstance(commodity_id, str) and commodity_id
        ]
        if not commodity_ids:
            commodity = node_details.get("commodity")
            if isinstance(commodity, str) and commodity:
                commodity_ids = [commodity]
        commodity_ids = _sorted_unique(commodity_ids)
        if not commodity_ids:
            continue

        dsl_items = []
        dsl_partial = False
        semantic_items = []
        lowered_items = []
        for commodity_id in commodity_ids:
            dsl_item, missing = _local_or_resolved_item(
                local_maps=local_maps,
                resolved_maps=resolved_maps,
                map_key="commodities",
                object_id=commodity_id,
                label="commodity",
                kind="commodity",
                locator=locator,
            )
            if dsl_item is not None:
                dsl_items.append(dsl_item)
            dsl_partial = dsl_partial or missing
            resolved_commodity = context.graph.commodities.get(commodity_id)
            if resolved_commodity is not None:
                semantic_items.append(
                    _item(
                        label="resolved commodity",
                        kind="commodity",
                        object_id=commodity_id,
                        attributes=resolved_commodity,
                        source_location=None,
                    )
                )
            lowered_items.append(
                _commodity_usage_item(commodity_id, cpir=context.cpir)
            )

        veda_items, veda_partial = _commodity_veda_items(
            commodity_ids,
            manifest_commodities=manifest_commodities,
            table_indexes=table_indexes,
        )
        inspectors[node_id] = {
            "title": str(node.get("label", node_id)),
            "kind": "commodity",
            "node_type": node_type,
            "summary": {
                "run_id": context.run_context.run_id,
                "commodity_view_members": commodity_ids,
            },
            "sections": [
                _section(
                    key="dsl",
                    label="DSL attributes",
                    default_open=True,
                    items=dsl_items,
                    partial=dsl_partial,
                ),
                _section(
                    key="semantic",
                    label="Resolved semantic model",
                    default_open=False,
                    items=semantic_items,
                ),
                _section(
                    key="lowered",
                    label="Lowered IR",
                    default_open=False,
                    items=lowered_items,
                ),
                _section(
                    key="veda",
                    label="VEDA/TIMES",
                    default_open=False,
                    items=veda_items,
                    partial=veda_partial or context.manifest is None,
                ),
            ],
        }

    return inspectors
