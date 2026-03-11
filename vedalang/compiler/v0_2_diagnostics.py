"""PRD Section 14 diagnostics for the VedaLang v0.2 frontend."""

from __future__ import annotations

import re
from typing import Any

from vedalang.versioning import looks_like_v0_2_source

from .v0_2_ast import (
    FacilityDecl,
    FleetDecl,
    TechnologyDecl,
    TechnologyRoleDecl,
    parse_v0_2_source,
)
from .v0_2_ir import build_v0_2_artifacts
from .v0_2_resolution import (
    ResolvedDefinitionGraph,
    RunContext,
    V0_2ResolutionError,
    allocate_fleet_stock,
    resolve_asset_stock,
    resolve_imports,
    resolve_run,
    resolve_sites,
    resolve_zone_opportunities,
)

ROLE_IMPL_HINTS = (
    "boiler",
    "heater",
    "heat_pump",
    "turbine",
    "pv",
    "battery",
    "diesel",
    "gas",
    "coal",
)
FUEL_HINTS = ("gas", "diesel", "coal", "hydrogen", "biomass", "oil")
PLACEHOLDER_RE = re.compile(r"(\$\{[^}]+\}|\{\{[^}]+\}\}|=[A-Za-z_(])")


def _location_of(obj: Any) -> str | None:
    source_ref = getattr(obj, "source_ref", None)
    path = getattr(source_ref, "path", None)
    return str(path) if isinstance(path, str) and path else None


def _diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    object_id: str,
    location: str | None = None,
    suggestion: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "object_id": object_id,
    }
    if location:
        payload["location"] = location
    if suggestion:
        payload["suggestion"] = suggestion
    return payload


def _error(
    code: str,
    obj: Any,
    message: str,
    *,
    object_id: str | None = None,
    suggestion: str | None = None,
) -> V0_2ResolutionError:
    return V0_2ResolutionError(
        code,
        object_id or getattr(obj, "id", "<unknown>"),
        message,
        location=_location_of(obj),
        suggestion=suggestion,
    )


def category_for_v0_2_code(code: str) -> str:
    if code in {"W001", "W002", "W008"}:
        return "identity"
    return "structure"


def _infer_run_id(source: dict[str, Any]) -> str | None:
    runs = source.get("runs")
    if not isinstance(runs, list) or len(runs) != 1:
        return None
    run_id = runs[0].get("id")
    return str(run_id) if run_id else None


def _validate_role_contracts(graph: ResolvedDefinitionGraph) -> None:
    for role in graph.technology_roles.values():
        primary = graph.commodities.get(role.primary_service)
        if primary is None:
            raise _error(
                "E002",
                role,
                "technology_role references missing commodity "
                f"'{role.primary_service}'",
            )
        if primary.type != "service":
            raise _error(
                "E004",
                role,
                "technology_role.primary_service must reference a service commodity",
                suggestion="Point primary_service at a commodity with `type: service`.",
            )
        for technology_id in role.technologies:
            if technology_id not in graph.technologies:
                raise _error(
                    "E002",
                    role,
                    f"technology_role references missing technology '{technology_id}'",
                    object_id=technology_id,
                )
        allowed = set(role.technologies)
        for transition in role.transitions:
            if transition.from_technology not in graph.technologies:
                raise _error(
                    "E002",
                    transition,
                    "transition references missing technology "
                    f"'{transition.from_technology}'",
                    object_id=transition.from_technology,
                )
            if transition.to_technology not in graph.technologies:
                raise _error(
                    "E002",
                    transition,
                    "transition references missing technology "
                    f"'{transition.to_technology}'",
                    object_id=transition.to_technology,
                )
            if (
                transition.from_technology not in allowed
                or transition.to_technology not in allowed
            ):
                raise _error(
                    "E005",
                    transition,
                    "technology_role transition references a technology not in "
                    "role.technologies",
                )


def _validate_dependency_closure(graph: ResolvedDefinitionGraph) -> None:
    for role in graph.technology_roles.values():
        if role.primary_service not in graph.commodities:
            raise _error(
                "E018",
                role,
                "missing dependency closure object after import resolution",
                object_id=role.primary_service,
            )
        for technology_id in role.technologies:
            if technology_id not in graph.technologies:
                raise _error(
                    "E018",
                    role,
                    "missing dependency closure object after import resolution",
                    object_id=technology_id,
                )
    for technology in graph.technologies.values():
        if technology.provides not in graph.commodities:
            raise _error(
                "E018",
                technology,
                "missing dependency closure object after import resolution",
                object_id=technology.provides,
            )
        for flow in (*technology.inputs, *technology.outputs, *technology.emissions):
            if flow.commodity not in graph.commodities:
                raise _error(
                    "E018",
                    technology,
                    "missing dependency closure object after import resolution",
                    object_id=flow.commodity,
                )


def _contains_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.search(value.strip()))


UNRESOLVED_FORMULA_MESSAGE = (
    "CSIR emission attempted with unresolved placeholders or formula strings"
)


def _validate_unresolved_formulas(graph: ResolvedDefinitionGraph) -> None:
    for technology in graph.technologies.values():
        for flow in technology.inputs:
            if _contains_placeholder(flow.coefficient):
                raise _error(
                    "E019",
                    flow,
                    UNRESOLVED_FORMULA_MESSAGE,
                    object_id=technology.id,
                )
        for flow in technology.outputs:
            if _contains_placeholder(flow.coefficient):
                raise _error(
                    "E019",
                    flow,
                    UNRESOLVED_FORMULA_MESSAGE,
                    object_id=technology.id,
                )
        for emission in technology.emissions:
            if _contains_placeholder(emission.factor):
                raise _error(
                    "E019",
                    emission,
                    UNRESOLVED_FORMULA_MESSAGE,
                    object_id=technology.id,
                )


def _role_name(role: TechnologyRoleDecl) -> str:
    return role.id.lower()


def _technology_name(technology: TechnologyDecl) -> str:
    return technology.id.lower()


def _warn_role_identity(
    role: TechnologyRoleDecl,
    graph: ResolvedDefinitionGraph,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    role_name = _role_name(role)
    if any(hint in role_name for hint in ROLE_IMPL_HINTS):
        warnings.append(
            _diagnostic(
                "W001",
                "warning",
                "technology_role ID appears implementation-specific rather than "
                "service-oriented",
                object_id=role.id,
                location=_location_of(role),
            )
        )
    if any(hint in role_name for hint in FUEL_HINTS):
        warnings.append(
            _diagnostic(
                "W002",
                "warning",
                "technology_role ID appears fuel-specific where a "
                "service-oriented role would be clearer",
                object_id=role.id,
                location=_location_of(role),
            )
        )
    inconsistent = [
        technology_id
        for technology_id in role.technologies
        if technology_id in graph.technologies
        and graph.technologies[technology_id].provides != role.primary_service
    ]
    if inconsistent:
        warnings.append(
            _diagnostic(
                "W004",
                "warning",
                "technology_role includes technologies whose `provides` field is "
                "inconsistent with primary_service",
                object_id=role.id,
                location=_location_of(role),
            )
        )
    ambiguous_name = any(
        _technology_name(graph.technologies[technology_id]) == role_name
        for technology_id in role.technologies
        if technology_id in graph.technologies
    )
    if ambiguous_name:
        warnings.append(
            _diagnostic(
                "W008",
                "warning",
                "role/technology naming is ambiguous; the role sounds like a "
                "concrete technology",
                object_id=role.id,
                location=_location_of(role),
            )
        )
    return warnings


def _warn_stock_shape(
    asset: FacilityDecl | FleetDecl,
    graph: ResolvedDefinitionGraph,
) -> list[dict[str, Any]]:
    if asset.stock is None or len(asset.stock.items) != 1:
        return []
    role = graph.technology_roles.get(asset.technology_role)
    if role is None:
        return []
    available = tuple(asset.available_technologies or role.technologies)
    if len(available) <= 1 or role.transitions:
        return []
    return [
        _diagnostic(
            "W009",
            "warning",
            "asset declares stock for one technology but exposes multiple "
            "technologies without transitions",
            object_id=asset.id,
            location=_location_of(asset),
        )
    ]


def _warn_stock_characterization(
    graph: ResolvedDefinitionGraph,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    by_technology: dict[str, Any] = {}
    for characterization in graph.stock_characterizations.values():
        for technology_id in characterization.applies_to:
            by_technology[technology_id] = characterization

    for asset in (*graph.facilities.values(), *graph.fleets.values()):
        if asset.stock is None:
            continue
        if any(item.metric != "asset_count" for item in asset.stock.items):
            continue
        for item in asset.stock.items:
            characterization = by_technology.get(item.technology)
            if characterization and not characterization.counted_asset_label:
                warnings.append(
                    _diagnostic(
                        "W011",
                        "warning",
                        "asset_count is used without counted_asset_label in the "
                        "resolved stock_characterization",
                        object_id=item.technology,
                        location=_location_of(characterization),
                    )
                )
    return warnings


def _warn_run_specific(
    graph: ResolvedDefinitionGraph,
    run: RunContext | None,
    *,
    site_region_memberships: dict[str, str | list[str]] | None = None,
    site_zone_memberships: dict[str, dict[str, str | list[str]]] | None = None,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if run is None:
        return warnings

    for measure_set in graph.spatial_measure_sets.values():
        for measure in measure_set.measures:
            if run.base_year - measure.observed_year >= 5:
                warnings.append(
                    _diagnostic(
                        "W003",
                        "warning",
                        "spatial weight measure observed_year is materially older "
                        "than the selected run base_year",
                        object_id=measure.id,
                        location=_location_of(measure),
                    )
                )

    for site in graph.sites.values():
        if site.membership_overrides:
            warnings.append(
                _diagnostic(
                    "W006",
                    "warning",
                    "membership override is present; prefer geometric resolution "
                    "when it is sufficient",
                    object_id=site.id,
                    location=_location_of(site.membership_overrides),
                )
            )

    standard_measures = {
        measure.id
        for measure_set in graph.spatial_measure_sets.values()
        for measure in measure_set.measures
    }
    for fleet in graph.fleets.values():
        if fleet.distribution.custom_weights_file:
            message = (
                "custom distribution file is used"
                if not standard_measures
                else "custom distribution file is used when standard spatial "
                "measures are available"
            )
            warnings.append(
                _diagnostic(
                    "W007",
                    "warning",
                    message,
                    object_id=fleet.id,
                    location=_location_of(fleet.distribution),
                )
            )
        if fleet.stock is None:
            continue
        for item in fleet.stock.items:
            adjustment = item.adjust_to_base_year or fleet.stock.adjust_to_base_year
            if (
                adjustment
                and adjustment.annual_growth is not None
                and graph.temporal_index_series
            ):
                warnings.append(
                    _diagnostic(
                        "W010",
                        "warning",
                        "annual growth adjustment is used even though "
                        "temporal_index_series values are available",
                        object_id=fleet.id,
                        location=_location_of(adjustment.annual_growth),
                    )
                )
    resolved_sites = resolve_sites(
        graph,
        run,
        site_region_memberships=site_region_memberships,
        site_zone_memberships=site_zone_memberships,
    )
    resolved_zone_opportunities = resolve_zone_opportunities(
        graph,
        run,
        resolved_sites,
    )
    asset_regions: list[tuple[str, str, str, str, str | None]] = []
    for facility in graph.facilities.values():
        role = graph.technology_roles.get(facility.technology_role)
        site = resolved_sites.get(facility.site)
        if role is None or site is None:
            continue
        for technology in facility.available_technologies or role.technologies:
            asset_regions.append(
                ("facility", facility.id, site.model_region, technology, facility.site)
            )
        available = tuple(facility.available_technologies or role.technologies)
        primary = graph.commodities.get(role.primary_service)
        if (
            len(run.model_regions) == 1
            and primary is not None
            and primary.type == "service"
            and (len(available) > 1 or role.transitions or len(available) != 1)
        ):
            warnings.append(
                _diagnostic(
                    "W013",
                    "warning",
                    "single-region service facility looks like generic stock; "
                    "prefer a fleet with distribution.method: direct for toy "
                    "models unless the site identity matters",
                    object_id=facility.id,
                    location=_location_of(facility),
                )
            )
    for fleet in graph.fleets.values():
        role = graph.technology_roles.get(fleet.technology_role)
        if role is None:
            continue
        adjusted = resolve_asset_stock(fleet, graph=graph, run=run)
        allocations = allocate_fleet_stock(
            graph,
            run,
            fleet,
            adjusted,
            measure_weights=measure_weights,
            custom_weights=custom_weights,
        )
        for allocation in allocations:
            for technology in fleet.available_technologies or role.technologies:
                asset_regions.append(
                    ("fleet", fleet.id, allocation.model_region, technology, None)
                )
    for opportunity in graph.zone_opportunities.values():
        resolved = resolved_zone_opportunities.get(opportunity.id)
        if resolved is None:
            continue
        duplicates = [
            (asset_kind, asset_id)
            for (
                asset_kind,
                asset_id,
                model_region,
                technology,
                _site_id,
            ) in asset_regions
            if (
                model_region == resolved.model_region
                and technology == opportunity.technology
            )
        ]
        if duplicates:
            warnings.append(
                _diagnostic(
                    "W012",
                    "warning",
                    "zone opportunity duplicates a technology already available "
                    "through a facility or fleet in the same resolved region; "
                    "prefer asset new_build_limits for generic capped buildout",
                    object_id=opportunity.id,
                    location=_location_of(opportunity),
                )
            )
    return warnings


def collect_v0_2_diagnostics(
    source: dict[str, Any],
    *,
    selected_run: str | None = None,
    packages: dict[str, Any] | None = None,
    site_region_memberships: dict[str, str | list[str]] | None = None,
    site_zone_memberships: dict[str, dict[str, str | list[str]]] | None = None,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Collect PRD Section 14 diagnostics for a v0.2 source document."""
    if not looks_like_v0_2_source(source):
        return []

    try:
        parsed = parse_v0_2_source(source)
        normalized_packages = {
            name: parse_v0_2_source(pkg) if isinstance(pkg, dict) else pkg
            for name, pkg in (packages or {}).items()
        }
        graph = resolve_imports(parsed, normalized_packages)
        _validate_role_contracts(graph)
        _validate_dependency_closure(graph)
        _validate_unresolved_formulas(graph)

        diagnostics: list[dict[str, Any]] = []
        for role in graph.technology_roles.values():
            diagnostics.extend(_warn_role_identity(role, graph))
        for asset in (*graph.facilities.values(), *graph.fleets.values()):
            diagnostics.extend(_warn_stock_shape(asset, graph))
        diagnostics.extend(_warn_stock_characterization(graph))

        run_id = selected_run or _infer_run_id(source)
        run: RunContext | None = None
        if run_id is not None:
            run = resolve_run(graph, run_id)
            build_v0_2_artifacts(
                graph,
                run,
                site_region_memberships=site_region_memberships,
                site_zone_memberships=site_zone_memberships,
                measure_weights=measure_weights,
                custom_weights=custom_weights,
            )
        diagnostics.extend(
            _warn_run_specific(
                graph,
                run,
                site_region_memberships=site_region_memberships,
                site_zone_memberships=site_zone_memberships,
                measure_weights=measure_weights,
                custom_weights=custom_weights,
            )
        )
        return sorted(
            diagnostics,
            key=lambda diag: (diag["severity"], diag["code"], diag["object_id"]),
        )
    except V0_2ResolutionError as exc:
        return [exc.as_diagnostic()]
