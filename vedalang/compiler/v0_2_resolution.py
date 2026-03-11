"""Semantic resolution helpers for the VedaLang v0.2 frontend."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .v0_2_ast import (
    BaseYearAdjustment,
    CommodityDecl,
    FacilityDecl,
    FleetDecl,
    NetworkDecl,
    RegionPartitionDecl,
    RunDecl,
    SiteDecl,
    SpatialLayerDecl,
    SpatialMeasureSetDecl,
    StockCharacterizationDecl,
    StockObservation,
    TechnologyDecl,
    TechnologyRoleDecl,
    TemporalIndexSeriesDecl,
    V0_2Source,
    ZoneOpportunityDecl,
    ZoneOverlayDecl,
)

QUANTITY_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(.*)\s*$")


class V0_2ResolutionError(Exception):
    """Deterministic resolution error with a PRD-aligned code."""

    def __init__(
        self,
        code: str,
        object_id: str,
        message: str,
        *,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.code = code
        self.object_id = object_id
        self.message = message
        self.location = location
        self.suggestion = suggestion
        super().__init__(f"{code} {object_id}: {message}")

    def as_diagnostic(self) -> dict[str, Any]:
        """Convert the error into a machine-readable diagnostic payload."""
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": "error",
            "message": self.message,
            "object_id": self.object_id,
        }
        if self.location:
            payload["location"] = self.location
        if self.suggestion:
            payload["suggestion"] = self.suggestion
        return payload


@dataclass(frozen=True)
class ParsedQuantity:
    value: float
    unit: str


@dataclass(frozen=True)
class ResolvedDefinitionGraph:
    commodities: dict[str, CommodityDecl]
    technologies: dict[str, TechnologyDecl]
    technology_roles: dict[str, TechnologyRoleDecl]
    stock_characterizations: dict[str, StockCharacterizationDecl]
    spatial_layers: dict[str, SpatialLayerDecl]
    spatial_measure_sets: dict[str, SpatialMeasureSetDecl]
    temporal_index_series: dict[str, TemporalIndexSeriesDecl]
    region_partitions: dict[str, RegionPartitionDecl]
    zone_overlays: dict[str, ZoneOverlayDecl]
    sites: dict[str, SiteDecl]
    facilities: dict[str, FacilityDecl]
    fleets: dict[str, FleetDecl]
    zone_opportunities: dict[str, ZoneOpportunityDecl]
    networks: dict[str, NetworkDecl]
    runs: dict[str, RunDecl]


@dataclass(frozen=True)
class RunContext:
    run_id: str
    base_year: int
    currency_year: int
    region_partition: str
    model_regions: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedSite:
    id: str
    model_region: str
    zone_memberships: dict[str, str]


@dataclass(frozen=True)
class AdjustedStock:
    technology: str
    declared_metric: str
    observed: ParsedQuantity
    adjusted: ParsedQuantity
    observed_year: int
    base_year: int
    trace: dict[str, Any]


@dataclass(frozen=True)
class FleetAllocation:
    fleet_id: str
    model_region: str
    share: float
    initial_stock: tuple[AdjustedStock, ...]
    derived_stock_views: dict[str, dict[str, ParsedQuantity]]


@dataclass(frozen=True)
class ResolvedZoneOpportunity:
    id: str
    technology_role: str
    technology: str
    model_region: str


@dataclass(frozen=True)
class ResolvedAssetNewBuildLimit:
    technology: str
    max_new_capacity: ParsedQuantity


def parse_quantity(value: str | int | float) -> ParsedQuantity:
    """Parse a loose quantity literal into numeric value plus unit suffix."""
    if isinstance(value, (int, float)):
        return ParsedQuantity(value=float(value), unit="")
    match = QUANTITY_RE.match(str(value))
    if not match:
        raise V0_2ResolutionError("E016", str(value), "quantity could not be parsed")
    return ParsedQuantity(value=float(match.group(1)), unit=match.group(2).strip())


def _format_quantity(value: float, unit: str) -> ParsedQuantity:
    return ParsedQuantity(value=value, unit=unit)


def _split_factor_unit(unit: str) -> str:
    return unit.split("/", 1)[0].strip()


def _by_id(items: tuple[Any, ...], kind: str) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for item in items:
        item_id = getattr(item, "id")
        if item_id in mapping:
            raise V0_2ResolutionError("E001", item_id, f"duplicate {kind} ID")
        mapping[item_id] = item
    return mapping


def _qualify_id(alias: str, object_id: str) -> str:
    return object_id if object_id.startswith(f"{alias}.") else f"{alias}.{object_id}"


def _qualify_ref(alias: str, ref: str, candidates: set[str]) -> str:
    if ref in candidates:
        return _qualify_id(alias, ref)
    return ref


def _object_maps(source: V0_2Source) -> dict[str, dict[str, Any]]:
    return {
        "commodities": _by_id(source.commodities, "commodity"),
        "technologies": _by_id(source.technologies, "technology"),
        "technology_roles": _by_id(source.technology_roles, "technology_role"),
        "stock_characterizations": _by_id(
            source.stock_characterizations,
            "stock_characterization",
        ),
        "spatial_layers": _by_id(source.spatial_layers, "spatial_layer"),
        "spatial_measure_sets": _by_id(
            source.spatial_measure_sets, "spatial_measure_set"
        ),
        "temporal_index_series": _by_id(
            source.temporal_index_series,
            "temporal_index_series",
        ),
        "region_partitions": _by_id(source.region_partitions, "region_partition"),
        "zone_overlays": _by_id(source.zone_overlays, "zone_overlay"),
        "sites": _by_id(source.sites, "site"),
        "facilities": _by_id(source.facilities, "facility"),
        "fleets": _by_id(source.fleets, "fleet"),
        "zone_opportunities": _by_id(
            source.zone_opportunities,
            "zone_opportunity",
        ),
        "networks": _by_id(source.networks, "network"),
        "runs": _by_id(source.runs, "run"),
    }


def _package_dependency_refs(kind: str, item: Any) -> list[tuple[str, str]]:
    if kind == "technology_roles":
        refs = [("technologies", ref) for ref in item.technologies]
        refs.append(("commodities", item.primary_service))
        return refs
    if kind == "technologies":
        refs = [("commodities", item.provides)]
        refs.extend(("commodities", flow.commodity) for flow in item.inputs)
        refs.extend(("commodities", flow.commodity) for flow in item.outputs)
        refs.extend(("commodities", emission.commodity) for emission in item.emissions)
        if item.stock_characterization:
            refs.append(("stock_characterizations", item.stock_characterization))
        return refs
    if kind == "stock_characterizations":
        return [("technologies", ref) for ref in item.applies_to]
    if kind == "spatial_measure_sets":
        return [("spatial_layers", item.layer)]
    if kind == "region_partitions":
        return [("spatial_layers", item.layer)]
    if kind == "zone_overlays":
        return [("spatial_layers", item.layer)]
    if kind == "zone_opportunities":
        refs = [
            ("technology_roles", item.technology_role),
            ("technologies", item.technology),
        ]
        zone_ref = item.zone
        zone_overlay = zone_ref.rsplit(".", 1)[0] if "." in zone_ref else zone_ref
        refs.append(("zone_overlays", zone_overlay))
        return refs
    return []


def _qualify_imported_object(
    alias: str,
    kind: str,
    item: Any,
    package_maps: dict[str, dict[str, Any]],
) -> Any:
    candidates = {
        object_kind: set(items) for object_kind, items in package_maps.items()
    }
    if kind == "commodities":
        return CommodityDecl(
            id=_qualify_id(alias, item.id),
            type=item.type,
            energy_form=item.energy_form,
            description=item.description,
            source_ref=item.source_ref,
        )
    if kind == "technologies":
        return TechnologyDecl(
            id=_qualify_id(alias, item.id),
            provides=_qualify_ref(alias, item.provides, candidates["commodities"]),
            inputs=tuple(
                flow.__class__(
                    commodity=_qualify_ref(
                        alias,
                        flow.commodity,
                        candidates["commodities"],
                    ),
                    basis=flow.basis,
                    coefficient=flow.coefficient,
                    source_ref=flow.source_ref,
                )
                for flow in item.inputs
            ),
            outputs=tuple(
                flow.__class__(
                    commodity=_qualify_ref(
                        alias,
                        flow.commodity,
                        candidates["commodities"],
                    ),
                    basis=flow.basis,
                    coefficient=flow.coefficient,
                    source_ref=flow.source_ref,
                )
                for flow in item.outputs
            ),
            performance=item.performance,
            emissions=tuple(
                emission.__class__(
                    commodity=_qualify_ref(
                        alias,
                        emission.commodity,
                        candidates["commodities"],
                    ),
                    factor=emission.factor,
                    source_ref=emission.source_ref,
                )
                for emission in item.emissions
            ),
            investment_cost=item.investment_cost,
            fixed_om=item.fixed_om,
            variable_om=item.variable_om,
            lifetime=item.lifetime,
            stock_characterization=(
                _qualify_ref(
                    alias,
                    item.stock_characterization,
                    candidates["stock_characterizations"],
                )
                if item.stock_characterization
                else None
            ),
            description=item.description,
            source_ref=item.source_ref,
        )
    if kind == "technology_roles":
        return TechnologyRoleDecl(
            id=_qualify_id(alias, item.id),
            primary_service=_qualify_ref(
                alias,
                item.primary_service,
                candidates["commodities"],
            ),
            technologies=tuple(
                _qualify_ref(alias, ref, candidates["technologies"])
                for ref in item.technologies
            ),
            transitions=tuple(
                transition.__class__(
                    from_technology=_qualify_ref(
                        alias,
                        transition.from_technology,
                        candidates["technologies"],
                    ),
                    to_technology=_qualify_ref(
                        alias,
                        transition.to_technology,
                        candidates["technologies"],
                    ),
                    kind=transition.kind,
                    cost=transition.cost,
                    lead_time=transition.lead_time,
                    source_ref=transition.source_ref,
                )
                for transition in item.transitions
            ),
            description=item.description,
            source_ref=item.source_ref,
        )
    if kind == "zone_opportunities":
        qualified_zone = item.zone
        for overlay_id in sorted(candidates["zone_overlays"], key=len, reverse=True):
            if item.zone == overlay_id or item.zone.startswith(f"{overlay_id}."):
                qualified_zone = (
                    item.zone
                    if item.zone.startswith(f"{alias}.")
                    else _qualify_id(alias, item.zone)
                )
                break
        return ZoneOpportunityDecl(
            id=_qualify_id(alias, item.id),
            technology_role=_qualify_ref(
                alias,
                item.technology_role,
                candidates["technology_roles"],
            ),
            technology=_qualify_ref(alias, item.technology, candidates["technologies"]),
            zone=qualified_zone,
            max_new_capacity=item.max_new_capacity,
            profile_ref=(
                _qualify_ref(alias, item.profile_ref, set())
                if item.profile_ref
                else None
            ),
            description=item.description,
            source_ref=item.source_ref,
        )
    if kind == "stock_characterizations":
        return StockCharacterizationDecl(
            id=_qualify_id(alias, item.id),
            applies_to=tuple(
                _qualify_ref(alias, ref, candidates["technologies"])
                for ref in item.applies_to
            ),
            counted_asset_label=item.counted_asset_label,
            conversions=item.conversions,
            description=item.description,
            source_ref=item.source_ref,
        )
    if kind == "spatial_layers":
        return SpatialLayerDecl(
            id=_qualify_id(alias, item.id),
            kind=item.kind,
            key=item.key,
            geometry_file=item.geometry_file,
            source_ref=item.source_ref,
        )
    if kind == "spatial_measure_sets":
        return SpatialMeasureSetDecl(
            id=_qualify_id(alias, item.id),
            layer=_qualify_ref(alias, item.layer, candidates["spatial_layers"]),
            measures=item.measures,
            source_ref=item.source_ref,
        )
    if kind == "temporal_index_series":
        return TemporalIndexSeriesDecl(
            id=_qualify_id(alias, item.id),
            unit=item.unit,
            base_year=item.base_year,
            values=item.values,
            description=item.description,
            source_ref=item.source_ref,
        )
    if kind == "region_partitions":
        return RegionPartitionDecl(
            id=_qualify_id(alias, item.id),
            layer=_qualify_ref(alias, item.layer, candidates["spatial_layers"]),
            members=item.members,
            mapping=item.mapping,
            description=item.description,
            source_ref=item.source_ref,
        )
    if kind == "zone_overlays":
        return ZoneOverlayDecl(
            id=_qualify_id(alias, item.id),
            layer=_qualify_ref(alias, item.layer, candidates["spatial_layers"]),
            key=item.key,
            geometry_file=item.geometry_file,
            description=item.description,
            source_ref=item.source_ref,
        )
    return item


def resolve_imports(
    source: V0_2Source,
    packages: dict[str, V0_2Source],
) -> ResolvedDefinitionGraph:
    """Resolve local objects plus imported package objects with closure."""

    def visit_package(package_name: str, stack: tuple[str, ...] = ()) -> None:
        if package_name in stack:
            raise V0_2ResolutionError(
                "E003",
                package_name,
                "import cycle detected",
            )
        package = packages.get(package_name)
        if package is None:
            raise V0_2ResolutionError(
                "E003", package_name, "imported package not found"
            )
        for child in package.imports:
            visit_package(child.package, (*stack, package_name))

    imported: dict[str, dict[str, Any]] = {kind: {} for kind in _object_maps(source)}
    for item in source.imports:
        visit_package(item.package)
        package = packages.get(item.package)
        if package is None:
            raise V0_2ResolutionError(
                "E003", item.package, "imported package not found"
            )
        package_maps = _object_maps(package)
        pending: list[tuple[str, str]] = [
            (kind, object_id) for kind, ids in item.only.items() for object_id in ids
        ]
        selected: dict[str, set[str]] = {kind: set() for kind in package_maps}
        while pending:
            kind, object_id = pending.pop()
            package_kind = package_maps.get(kind)
            if package_kind is None or object_id not in package_kind:
                raise V0_2ResolutionError(
                    "E003",
                    f"{item.alias}.{object_id}",
                    f"imported {kind[:-1]} not found in package {item.package}",
                )
            if object_id in selected[kind]:
                continue
            selected[kind].add(object_id)
            for dependency in _package_dependency_refs(kind, package_kind[object_id]):
                pending.append(dependency)
        for kind, ids in selected.items():
            for object_id in ids:
                qualified = _qualify_imported_object(
                    item.alias,
                    kind,
                    package_maps[kind][object_id],
                    package_maps,
                )
                qualified_id = getattr(qualified, "id")
                if qualified_id in imported[kind]:
                    raise V0_2ResolutionError(
                        "E001", qualified_id, "duplicate imported ID"
                    )
                imported[kind][qualified_id] = qualified
    local_maps = _object_maps(source)
    merged: dict[str, dict[str, Any]] = {}
    for kind, local in local_maps.items():
        merged[kind] = dict(imported[kind])
        for object_id, item in local.items():
            if object_id in merged[kind]:
                raise V0_2ResolutionError(
                    "E001", object_id, "local ID overrides import"
                )
            merged[kind][object_id] = item
    return ResolvedDefinitionGraph(**merged)


def resolve_run(graph: ResolvedDefinitionGraph, run_id: str) -> RunContext:
    """Resolve a selected run into a deterministic compilation context."""
    run = graph.runs.get(run_id)
    if run is None:
        raise V0_2ResolutionError("E002", run_id, "run not found")
    partition = graph.region_partitions.get(run.region_partition)
    if partition is None:
        raise V0_2ResolutionError(
            "E002",
            run.region_partition,
            "run references missing region_partition",
        )
    if partition.members:
        model_regions = partition.members
    elif partition.mapping.kind == "constant" and partition.mapping.value:
        model_regions = (partition.mapping.value,)
    else:
        raise V0_2ResolutionError(
            "E002",
            partition.id,
            "region_partition does not define a member set",
        )
    return RunContext(
        run_id=run.id,
        base_year=run.base_year,
        currency_year=run.currency_year,
        region_partition=run.region_partition,
        model_regions=tuple(model_regions),
    )


def resolve_sites(
    graph: ResolvedDefinitionGraph,
    run: RunContext,
    *,
    site_region_memberships: dict[str, str | list[str]] | None = None,
    site_zone_memberships: dict[str, dict[str, str | list[str]]] | None = None,
) -> dict[str, ResolvedSite]:
    """Resolve site memberships into the selected run partition."""
    resolved: dict[str, ResolvedSite] = {}
    region_data = site_region_memberships or {}
    zone_data = site_zone_memberships or {}
    for site in graph.sites.values():
        override = None
        if site.membership_overrides:
            override = site.membership_overrides.region_partitions.get(
                run.region_partition
            )
            if override and override not in run.model_regions:
                raise V0_2ResolutionError(
                    "E017",
                    site.id,
                    "membership override target "
                    f"'{override}' is not in {run.region_partition}",
                )
        if override:
            model_region = override
        else:
            raw_membership = region_data.get(site.id)
            memberships = (
                [raw_membership]
                if isinstance(raw_membership, str)
                else list(raw_membership or [])
            )
            if len(memberships) != 1 or memberships[0] not in run.model_regions:
                raise V0_2ResolutionError(
                    "E008",
                    site.id,
                    "site cannot be resolved to exactly one model_region",
                )
            model_region = memberships[0]
        zone_memberships: dict[str, str] = {}
        for overlay_id, membership in (zone_data.get(site.id) or {}).items():
            values = [membership] if isinstance(membership, str) else list(membership)
            if len(values) != 1:
                raise V0_2ResolutionError(
                    "E014",
                    site.id,
                    f"zone overlay {overlay_id} membership is ambiguous",
                )
            zone_memberships[overlay_id] = values[0]
        if site.membership_overrides:
            zone_memberships.update(site.membership_overrides.zone_overlays)
        resolved[site.id] = ResolvedSite(
            id=site.id,
            model_region=model_region,
            zone_memberships=zone_memberships,
        )
    return resolved


def resolve_zone_opportunities(
    graph: ResolvedDefinitionGraph,
    run: RunContext,
    resolved_sites: dict[str, ResolvedSite],
) -> dict[str, ResolvedZoneOpportunity]:
    """Resolve zone opportunities to a single model region."""
    resolved: dict[str, ResolvedZoneOpportunity] = {}
    overlay_ids = sorted(graph.zone_overlays, key=len, reverse=True)
    for opportunity in graph.zone_opportunities.values():
        role = graph.technology_roles.get(opportunity.technology_role)
        if role is None:
            raise V0_2ResolutionError(
                "E003",
                opportunity.id,
                f"technology_role '{opportunity.technology_role}' is not defined",
            )
        if opportunity.technology not in role.technologies:
            raise V0_2ResolutionError(
                "E023",
                opportunity.id,
                "zone_opportunity technology must be a member of technology_role",
            )
        zone_ref = opportunity.zone
        overlay_id = next(
            (
                candidate
                for candidate in overlay_ids
                if zone_ref.startswith(f"{candidate}.")
            ),
            None,
        )
        if overlay_id is None:
            raise V0_2ResolutionError(
                "E014",
                opportunity.id,
                f"zone reference '{zone_ref}' is invalid",
            )
        zone_member = zone_ref[len(overlay_id) + 1 :]
        matching_sites = [
            site.model_region
            for site in resolved_sites.values()
            if site.zone_memberships.get(overlay_id) == zone_member
        ]
        unique = sorted(set(matching_sites))
        if len(unique) != 1:
            raise V0_2ResolutionError(
                "E014",
                opportunity.id,
                f"zone '{zone_ref}' resolves ambiguously",
            )
        model_region = unique[0]
        resolved[opportunity.id] = ResolvedZoneOpportunity(
            id=opportunity.id,
            technology_role=opportunity.technology_role,
            technology=opportunity.technology,
            model_region=model_region,
        )
    return resolved


def adjust_stock_to_base_year(
    observation: StockObservation,
    *,
    default_adjustment: BaseYearAdjustment | None,
    run: RunContext,
    graph: ResolvedDefinitionGraph,
) -> AdjustedStock:
    """Adjust one observed stock item to the selected run base year."""
    observed_quantity = parse_quantity(observation.observed.value)
    base_year = run.base_year
    obs_year = observation.observed.year
    adjustment = observation.adjust_to_base_year or default_adjustment
    if obs_year == base_year:
        adjusted = observed_quantity
        trace = {"method": "none", "observed_year": obs_year, "base_year": base_year}
    elif adjustment is None:
        raise V0_2ResolutionError(
            "E011",
            observation.technology,
            "observed year differs from run base_year and no adjustment rule "
            "is available",
        )
    elif adjustment.using_temporal_index:
        series = graph.temporal_index_series.get(adjustment.using_temporal_index)
        if (
            series is None
            or obs_year not in series.values
            or base_year not in series.values
        ):
            raise V0_2ResolutionError(
                "E011",
                observation.technology,
                "temporal index series cannot adjust the observed year to the "
                "base year",
            )
        elasticity = adjustment.elasticity if adjustment.elasticity is not None else 1.0
        ratio = series.values[base_year] / series.values[obs_year]
        adjusted = _format_quantity(
            observed_quantity.value * math.pow(ratio, elasticity),
            observed_quantity.unit,
        )
        trace = {
            "method": "temporal_index_series",
            "series": adjustment.using_temporal_index,
            "ratio": ratio,
            "elasticity": elasticity,
            "observed_year": obs_year,
            "base_year": base_year,
        }
    elif adjustment.annual_growth:
        rate = parse_quantity(adjustment.annual_growth.rate)
        normalized_rate = rate.value / 100.0 if "%" in rate.unit else rate.value
        adjusted = _format_quantity(
            observed_quantity.value
            * math.pow(1.0 + normalized_rate, base_year - obs_year),
            observed_quantity.unit,
        )
        trace = {
            "method": "annual_growth",
            "rate": normalized_rate,
            "observed_year": obs_year,
            "base_year": base_year,
        }
    else:
        raise V0_2ResolutionError(
            "E011", observation.technology, "invalid adjustment rule"
        )
    return AdjustedStock(
        technology=observation.technology,
        declared_metric=observation.metric,
        observed=observed_quantity,
        adjusted=adjusted,
        observed_year=obs_year,
        base_year=base_year,
        trace=trace,
    )


def resolve_asset_stock(
    asset: FacilityDecl | FleetDecl,
    *,
    graph: ResolvedDefinitionGraph,
    run: RunContext,
) -> tuple[AdjustedStock, ...]:
    """Adjust all stock items for one facility or fleet."""
    if asset.stock is None:
        return ()
    role = graph.technology_roles.get(asset.technology_role)
    if role is None:
        raise V0_2ResolutionError(
            "E002",
            asset.technology_role,
            "asset references missing technology_role",
        )
    allowed = set(asset.available_technologies or role.technologies)
    if asset.available_technologies and not set(asset.available_technologies).issubset(
        role.technologies
    ):
        code = "E006" if isinstance(asset, FacilityDecl) else "E007"
        raise V0_2ResolutionError(
            code, asset.id, "available_technologies not subset of role.technologies"
        )
    adjusted: list[AdjustedStock] = []
    for item in asset.stock.items:
        if item.technology not in allowed:
            raise V0_2ResolutionError(
                "E015",
                asset.id,
                "stock item technology "
                f"'{item.technology}' is not allowed by the asset",
            )
        adjusted.append(
            adjust_stock_to_base_year(
                item,
                default_adjustment=asset.stock.adjust_to_base_year,
                run=run,
                graph=graph,
            )
        )
    return tuple(adjusted)


def resolve_asset_new_build_limits(
    asset: FacilityDecl | FleetDecl,
    *,
    graph: ResolvedDefinitionGraph,
) -> tuple[ResolvedAssetNewBuildLimit, ...]:
    role = graph.technology_roles.get(asset.technology_role)
    if role is None:
        raise V0_2ResolutionError(
            "E002",
            asset.technology_role,
            "asset references missing technology_role",
        )
    allowed = set(asset.available_technologies or role.technologies)
    resolved: list[ResolvedAssetNewBuildLimit] = []
    seen: set[str] = set()
    for item in asset.new_build_limits:
        if item.technology in seen:
            raise V0_2ResolutionError(
                "E022",
                asset.id,
                "duplicate new_build_limits entry for technology "
                f"'{item.technology}'",
                location=item.source_ref.path,
            )
        seen.add(item.technology)
        if item.technology not in allowed:
            raise V0_2ResolutionError(
                "E023",
                asset.id,
                "new_build_limits technology "
                f"'{item.technology}' is not allowed by the asset",
                location=item.source_ref.path,
            )
        resolved.append(
            ResolvedAssetNewBuildLimit(
                technology=item.technology,
                max_new_capacity=parse_quantity(item.max_new_capacity),
            )
        )
    return tuple(resolved)


def _find_stock_characterization(
    graph: ResolvedDefinitionGraph,
    technology: str,
) -> StockCharacterizationDecl | None:
    for characterization in graph.stock_characterizations.values():
        if technology in characterization.applies_to:
            return characterization
    return None


def derive_stock_views(
    graph: ResolvedDefinitionGraph,
    stock: AdjustedStock,
    *,
    required_metrics: tuple[str, ...] = ("installed_capacity", "annual_activity"),
) -> dict[str, ParsedQuantity]:
    """Derive stock views required for lowering from a declared stock metric."""
    views = {stock.declared_metric: stock.adjusted}
    if stock.declared_metric != "asset_count":
        return views
    characterization = _find_stock_characterization(graph, stock.technology)
    if characterization is None:
        raise V0_2ResolutionError(
            "E012",
            stock.technology,
            "asset_count lowering requires a stock_characterization",
        )
    conversions = {
        conversion.to_metric: conversion
        for conversion in characterization.conversions
        if conversion.from_metric == "asset_count"
    }
    for metric in required_metrics:
        conversion = conversions.get(metric)
        if conversion is None:
            raise V0_2ResolutionError(
                "E012",
                stock.technology,
                f"missing asset_count -> {metric} conversion",
            )
        factor = parse_quantity(conversion.factor)
        views[metric] = _format_quantity(
            stock.adjusted.value * factor.value,
            _split_factor_unit(factor.unit),
        )
    return views


def allocate_fleet_stock(
    graph: ResolvedDefinitionGraph,
    run: RunContext,
    fleet: FleetDecl,
    adjusted_stock: tuple[AdjustedStock, ...],
    *,
    measure_weights: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, dict[str, float]] | None = None,
) -> tuple[FleetAllocation, ...]:
    """Allocate fleet stock across model regions and derive stock views."""
    if fleet.distribution.method == "direct":
        target_regions = tuple(fleet.distribution.target_regions)
        if not target_regions:
            if len(run.model_regions) != 1:
                raise V0_2ResolutionError(
                    "E020",
                    fleet.id,
                    "direct fleet distribution requires target_regions for "
                    "multi-region runs",
                    location=fleet.distribution.source_ref.path,
                )
            target_regions = (run.model_regions[0],)
        invalid = [
            region for region in target_regions if region not in run.model_regions
        ]
        if invalid:
            raise V0_2ResolutionError(
                "E021",
                fleet.id,
                "distribution.target_regions contains regions outside the "
                "selected run partition",
                location=fleet.distribution.source_ref.path,
            )
        allocations: list[FleetAllocation] = []
        for region in target_regions:
            regional_items = tuple(
                AdjustedStock(
                    technology=item.technology,
                    declared_metric=item.declared_metric,
                    observed=item.observed,
                    adjusted=_format_quantity(item.adjusted.value, item.adjusted.unit),
                    observed_year=item.observed_year,
                    base_year=item.base_year,
                    trace={
                        **item.trace,
                        "direct_binding": True,
                        "model_region": region,
                    },
                )
                for item in adjusted_stock
            )
            stock_views = {
                item.technology: derive_stock_views(graph, item)
                for item in regional_items
            }
            allocations.append(
                FleetAllocation(
                    fleet_id=fleet.id,
                    model_region=region,
                    share=1.0,
                    initial_stock=regional_items,
                    derived_stock_views=stock_views,
                )
            )
        return tuple(allocations)
    if fleet.distribution.method == "proportional":
        weight_ref = fleet.distribution.weight_by or ""
        weights = dict((measure_weights or {}).get(weight_ref, {}))
        if not weights:
            raise V0_2ResolutionError(
                "E009",
                fleet.id,
                "fleet distribution weight measure cannot be rolled up to "
                "run region_partition",
            )
    else:
        weights = dict(
            (custom_weights or {}).get(fleet.distribution.custom_weights_file or "", {})
        )
        if not weights:
            raise V0_2ResolutionError(
                "E009",
                fleet.id,
                "custom fleet distribution weights are unavailable",
            )
    total = sum(float(weights.get(region, 0.0)) for region in run.model_regions)
    if total <= 0:
        raise V0_2ResolutionError(
            "E010",
            fleet.id,
            "proportional fleet distribution has non-positive total weight",
        )
    allocations: list[FleetAllocation] = []
    for region in run.model_regions:
        share = float(weights.get(region, 0.0)) / total
        regional_items = tuple(
            AdjustedStock(
                technology=item.technology,
                declared_metric=item.declared_metric,
                observed=item.observed,
                adjusted=_format_quantity(
                    item.adjusted.value * share, item.adjusted.unit
                ),
                observed_year=item.observed_year,
                base_year=item.base_year,
                trace={**item.trace, "allocation_share": share, "model_region": region},
            )
            for item in adjusted_stock
        )
        stock_views = {
            item.technology: derive_stock_views(graph, item) for item in regional_items
        }
        allocations.append(
            FleetAllocation(
                fleet_id=fleet.id,
                model_region=region,
                share=share,
                initial_stock=regional_items,
                derived_stock_views=stock_views,
            )
        )
    return tuple(allocations)
