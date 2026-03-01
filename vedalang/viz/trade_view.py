"""Trade lens builders for the RES query engine."""

from __future__ import annotations

from typing import Any

from .graph_models import (
    FilterSpec,
    build_trade_graph,
    extract_ire_symbols,
    extract_trade_attrs_from_compiled,
    extract_trade_links_from_compiled,
    extract_trade_links_from_source,
)


def build_source_trade_view(source: dict, *, filters: FilterSpec) -> dict[str, Any]:
    """Build trade view from source trade_links."""
    links = extract_trade_links_from_source(source)
    return build_trade_graph(source, filters=filters, trade_links=links)


def build_compiled_trade_view(
    source: dict,
    *,
    filters: FilterSpec,
    tableir: dict,
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build trade view from compiled TRADELINKS + IRE symbols."""
    links = extract_trade_links_from_compiled(tableir)
    ire_rows = extract_ire_symbols(manifest)
    trade_attrs = extract_trade_attrs_from_compiled(tableir)
    return build_trade_graph(
        source,
        filters=filters,
        trade_links=links,
        ire_processes=ire_rows,
        trade_attrs=trade_attrs,
    )
