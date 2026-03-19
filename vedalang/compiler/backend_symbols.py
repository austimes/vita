"""Explicit backend symbol contracts for VEDA/TIMES emission."""

from __future__ import annotations

import re
from typing import Any

from .artifacts import ResolvedArtifacts
from .resolution import ResolvedDefinitionGraph

GAMS_IDENTIFIER_MAX = 63
EXCEL_SHEET_NAME_MAX = 31

PROCESS_ALIAS_PATTERN = {
    "facilities": "PRC_FAC_{asset_id}_{technology_id}",
    "fleets": "PRC_FLT_{asset_id}_{technology_id}",
}


def commodity_symbol(commodity_id: str) -> str:
    return f"COM_{commodity_id}"


def run_symbol(run_id: str) -> str:
    return f"RUN_{run_id}"


def user_constraint_symbol(constraint_id: str) -> str:
    """Build a deterministic backend-safe symbol for user constraints."""
    stem = re.sub(r"[^A-Za-z0-9]+", "_", str(constraint_id)).strip("_")
    return f"UC_{stem or 'AUTO'}"


def trade_sheet_name(commodity_id: str) -> str:
    return f"U_{commodity_id}"


def trade_process_pattern(commodity_id: str) -> str:
    return f"TB_{commodity_id}_*,TU_{commodity_id}_*"


def process_symbol(
    process: dict[str, Any],
    *,
    role_instances_by_id: dict[str, dict[str, Any]],
) -> str:
    technology_id = str(process["technology"])
    source_role_instance = str(process.get("source_role_instance", "") or "")
    if source_role_instance:
        role_instance = role_instances_by_id[source_role_instance]
        source_asset = str(role_instance["source_asset"])
        asset_kind, asset_id = source_asset.split(".", 1)
        template = PROCESS_ALIAS_PATTERN.get(asset_kind)
        if template is None:
            raise ValueError(f"Unsupported role-instance asset kind: {asset_kind}")
        return template.format(asset_id=asset_id, technology_id=technology_id)
    source_zone_opportunity = str(process.get("source_zone_opportunity", "") or "")
    if source_zone_opportunity:
        return f"PRC_ZOP_{source_zone_opportunity}_{technology_id}"
    raise ValueError(f"Unsupported process source for backend symbol: {process!r}")


def validate_backend_aliases(
    graph: ResolvedDefinitionGraph,
    artifacts: ResolvedArtifacts,
) -> list[dict[str, Any]]:
    """Return semantic diagnostics for backend alias length and collisions."""
    diagnostics: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], str] = {}
    role_instances_by_id = {
        item["id"]: item for item in artifacts.csir.get("technology_role_instances", [])
    }

    def location_of(obj: Any) -> str | None:
        source_ref = getattr(obj, "source_ref", None)
        path = getattr(source_ref, "path", None)
        return str(path) if isinstance(path, str) and path else None

    def push(
        *,
        code: str,
        message: str,
        object_id: str,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "code": code,
            "severity": "error",
            "message": message,
            "object_id": object_id,
        }
        if location:
            payload["location"] = location
        if suggestion:
            payload["suggestion"] = suggestion
        diagnostics.append(payload)

    def check_length(
        *,
        code: str,
        alias: str,
        limit: int,
        kind: str,
        object_id: str,
        location: str | None,
        suggestion: str,
    ) -> None:
        if len(alias) <= limit:
            return
        push(
            code=code,
            object_id=object_id,
            location=location,
            message=(
                f"{kind} '{alias}' exceeds the {limit}-character limit "
                f"({len(alias)} characters)"
            ),
            suggestion=suggestion,
        )

    def check_collision(
        *,
        alias: str,
        namespace: str,
        origin: str,
        object_id: str,
        location: str | None,
        suggestion: str,
    ) -> None:
        key = (namespace, alias)
        prior = seen.get(key)
        if prior is None:
            seen[key] = origin
            return
        if prior == origin:
            return
        push(
            code="E026",
            object_id=object_id,
            location=location,
            message=(
                f"backend alias collision: '{alias}' is produced by both "
                f"'{prior}' and '{origin}'"
            ),
            suggestion=suggestion,
        )

    for commodity in sorted(graph.commodities.values(), key=lambda item: item.id):
        alias = commodity_symbol(commodity.id)
        check_length(
            code="E022",
            alias=alias,
            limit=GAMS_IDENTIFIER_MAX,
            kind="commodity alias",
            object_id=commodity.id,
            location=location_of(commodity),
            suggestion="Shorten the commodity `id` so the emitted `COM_*` alias fits.",
        )
        check_collision(
            alias=alias,
            namespace="commodity",
            origin=f"commodity:{commodity.id}",
            object_id=commodity.id,
            location=location_of(commodity),
            suggestion="Rename one of the commodities so `COM_*` aliases differ.",
        )

        sheet = trade_sheet_name(commodity.id)
        check_length(
            code="E023",
            alias=sheet,
            limit=EXCEL_SHEET_NAME_MAX,
            kind="trade worksheet name",
            object_id=commodity.id,
            location=location_of(commodity),
            suggestion=(
                "Shorten the commodity `id` so the emitted `U_*` trade worksheet "
                "name fits Excel's 31-character limit."
            ),
        )
        check_collision(
            alias=sheet,
            namespace="trade_sheet",
            origin=f"trade_sheet:{commodity.id}",
            object_id=commodity.id,
            location=location_of(commodity),
            suggestion="Rename one of the commodities so `U_*` worksheet names differ.",
        )

        for trade_alias in (f"TB_{commodity.id}", f"TU_{commodity.id}"):
            check_length(
                code="E024",
                alias=trade_alias,
                limit=GAMS_IDENTIFIER_MAX,
                kind="trade process stem",
                object_id=commodity.id,
                location=location_of(commodity),
                suggestion=(
                    "Shorten the commodity `id` so emitted `TB_*`/`TU_*` trade "
                    "process stems fit the 63-character limit."
                ),
            )
            check_collision(
                alias=trade_alias,
                namespace="trade_process",
                origin=f"trade_process:{trade_alias}",
                object_id=commodity.id,
                location=location_of(commodity),
                suggestion=(
                    "Rename one of the commodities so trade process stems differ."
                ),
            )

    for run in sorted(graph.runs.values(), key=lambda item: item.id):
        alias = run_symbol(run.id)
        check_length(
            code="E025",
            alias=alias,
            limit=GAMS_IDENTIFIER_MAX,
            kind="run alias",
            object_id=run.id,
            location=location_of(run),
            suggestion="Shorten the run `id` so the emitted `RUN_*` alias fits.",
        )
        check_collision(
            alias=alias,
            namespace="run",
            origin=f"run:{run.id}",
            object_id=run.id,
            location=location_of(run),
            suggestion="Rename one of the runs so `RUN_*` aliases differ.",
        )

    for process in artifacts.cpir.get("processes", []):
        alias = process_symbol(process, role_instances_by_id=role_instances_by_id)
        technology_id = str(process["technology"])
        if process.get("source_role_instance"):
            role_instance = role_instances_by_id[str(process["source_role_instance"])]
            source_asset = str(role_instance["source_asset"])
            asset_kind, asset_id = source_asset.split(".", 1)
            object_id = asset_id
            if asset_kind == "facilities":
                location = location_of(graph.facilities[asset_id])
                suggestion = (
                    f"Shorten facility id '{asset_id}' or technology id "
                    f"'{technology_id}' so the emitted `PRC_FAC_*` alias fits."
                )
            else:
                location = location_of(graph.fleets[asset_id])
                suggestion = (
                    f"Shorten fleet id '{asset_id}' or technology id "
                    f"'{technology_id}' so the emitted `PRC_FLT_*` alias fits."
                )
        else:
            asset_id = str(process["source_zone_opportunity"])
            object_id = asset_id
            location = location_of(graph.zone_opportunities[asset_id])
            suggestion = (
                f"Shorten zone opportunity id '{asset_id}' or technology id "
                f"'{technology_id}' so the emitted `PRC_ZOP_*` alias fits."
            )

        check_length(
            code="E021",
            alias=alias,
            limit=GAMS_IDENTIFIER_MAX,
            kind="process alias",
            object_id=object_id,
            location=location,
            suggestion=suggestion,
        )
        check_collision(
            alias=alias,
            namespace=f"process:{process['model_region']}",
            origin=f"process:{process['id']}",
            object_id=object_id,
            location=location,
            suggestion=(
                f"Rename asset id '{asset_id}' or technology id '{technology_id}' "
                "so emitted process aliases differ."
            ),
        )

    return diagnostics
