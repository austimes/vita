"""Typed AST objects for the VedaLang public source model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    """Stable structural source reference for diagnostics/provenance."""

    path: str


@dataclass(frozen=True)
class ImportDecl:
    package: str
    alias: str
    only: dict[str, tuple[str, ...]]
    source_ref: SourceRef


@dataclass(frozen=True)
class CommodityDecl:
    id: str
    type: str
    energy_form: str | None
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class FlowSpec:
    commodity: str
    basis: str | None
    coefficient: str | int | float | None
    source_ref: SourceRef


@dataclass(frozen=True)
class PerformanceSpec:
    kind: str
    value: float
    source_ref: SourceRef


@dataclass(frozen=True)
class EmissionFactor:
    commodity: str
    factor: str | int | float
    source_ref: SourceRef


@dataclass(frozen=True)
class ActivityBoundSpec:
    limtype: str
    value: str | int | float
    source_ref: SourceRef


@dataclass(frozen=True)
class TechnologyDecl:
    id: str
    provides: str
    inputs: tuple[FlowSpec, ...]
    outputs: tuple[FlowSpec, ...]
    performance: PerformanceSpec | None
    emissions: tuple[EmissionFactor, ...]
    investment_cost: str | int | float | None
    fixed_om: str | int | float | None
    variable_om: str | int | float | None
    activity_bound: ActivityBoundSpec | None
    lifetime: str | int | float | None
    stock_characterization: str | None
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class RoleTransition:
    from_technology: str
    to_technology: str
    kind: str
    cost: str | int | float | None
    lead_time: str | int | float | None
    source_ref: SourceRef


@dataclass(frozen=True)
class TechnologyRoleDecl:
    id: str
    primary_service: str
    technologies: tuple[str, ...]
    transitions: tuple[RoleTransition, ...]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class MetricConversion:
    from_metric: str
    to_metric: str
    factor: str | int | float
    source_ref: SourceRef


@dataclass(frozen=True)
class StockCharacterizationDecl:
    id: str
    applies_to: tuple[str, ...]
    counted_asset_label: str | None
    conversions: tuple[MetricConversion, ...]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class SpatialLayerDecl:
    id: str
    kind: str
    key: str
    geometry_file: str
    source_ref: SourceRef


@dataclass(frozen=True)
class SpatialMeasureDecl:
    id: str
    observed_year: int
    unit: str
    file: str
    column: str
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class SpatialMeasureSetDecl:
    id: str
    layer: str
    measures: tuple[SpatialMeasureDecl, ...]
    source_ref: SourceRef


@dataclass(frozen=True)
class QuantitySpec:
    scalar: str | int | float | None
    series: str | None
    interpolation: str | None
    values: dict[int, str | int | float]
    source_ref: SourceRef


@dataclass(frozen=True)
class TimeSeriesDecl:
    id: str
    kind: str
    unit: str
    interpolation: str
    base_year: int | None
    values: dict[int, float]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class YearSetDecl:
    id: str
    start_year: int
    milestone_years: tuple[int, ...]
    source_ref: SourceRef


@dataclass(frozen=True)
class PolicyCaseDecl:
    id: str
    budget: QuantitySpec
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class PolicyDecl:
    id: str
    kind: str
    emission_commodity: str
    budget: QuantitySpec | None
    cases: tuple[PolicyCaseDecl, ...]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class PartitionMapping:
    kind: str
    file: str | None
    source_key: str | None
    target_key: str | None
    value: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class RegionPartitionDecl:
    id: str
    layer: str
    members: tuple[str, ...]
    mapping: PartitionMapping
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class ZoneOverlayDecl:
    id: str
    layer: str
    key: str
    geometry_file: str
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class SiteLocation:
    point: dict[str, float] | None
    feature_ref: dict[str, str] | None
    source_ref: SourceRef


@dataclass(frozen=True)
class MembershipOverrides:
    region_partitions: dict[str, str]
    zone_overlays: dict[str, str]
    source_ref: SourceRef


@dataclass(frozen=True)
class SiteDecl:
    id: str
    location: SiteLocation
    membership_overrides: MembershipOverrides | None
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class BaseYearAdjustment:
    series: QuantitySpec
    elasticity: float | None
    source_ref: SourceRef


@dataclass(frozen=True)
class ObservedValue:
    value: str | int | float
    year: int
    source_ref: SourceRef


@dataclass(frozen=True)
class StockObservation:
    technology: str
    metric: str
    observed: ObservedValue
    adjust_to_base_year: BaseYearAdjustment | None
    source_ref: SourceRef


@dataclass(frozen=True)
class StockBlock:
    adjust_to_base_year: BaseYearAdjustment | None
    items: tuple[StockObservation, ...]
    source_ref: SourceRef


@dataclass(frozen=True)
class AssetNewBuildLimit:
    technology: str
    max_new_capacity: str | int | float
    source_ref: SourceRef


@dataclass(frozen=True)
class FacilityDecl:
    id: str
    site: str
    technology_role: str
    available_technologies: tuple[str, ...]
    stock: StockBlock | None
    new_build_limits: tuple[AssetNewBuildLimit, ...]
    policies: tuple[str, ...]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class DistributionBlock:
    method: str
    weight_by: str | None
    custom_weights_file: str | None
    target_regions: tuple[str, ...]
    source_ref: SourceRef


@dataclass(frozen=True)
class FleetDecl:
    id: str
    technology_role: str
    available_technologies: tuple[str, ...]
    stock: StockBlock | None
    new_build_limits: tuple[AssetNewBuildLimit, ...]
    distribution: DistributionBlock
    policies: tuple[str, ...]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class ZoneOpportunityDecl:
    id: str
    technology_role: str
    technology: str
    zone: str
    max_new_capacity: str | int | float
    profile_ref: str | None
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class NetworkNodeBasis:
    kind: str
    ref: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class NetworkLink:
    id: str
    from_node: str
    to_node: str
    commodity: str
    existing_transfer_capacity: str | int | float | None
    max_new_capacity: str | int | float | None
    source_ref: SourceRef


@dataclass(frozen=True)
class NetworkDecl:
    id: str
    kind: str
    node_basis: NetworkNodeBasis
    links: tuple[NetworkLink, ...]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class RunDecl:
    id: str
    veda_book_name: str
    year_set: str
    currency_year: int
    region_partition: str
    temporal_partition: str | None
    reporting_value_flows: bool
    include_cases: tuple[str, ...]
    enable_policies: tuple[str, ...]
    description: str | None
    source_ref: SourceRef


@dataclass(frozen=True)
class SourceDocument:
    dsl_version: str | None
    imports: tuple[ImportDecl, ...]
    commodities: tuple[CommodityDecl, ...]
    technologies: tuple[TechnologyDecl, ...]
    technology_roles: tuple[TechnologyRoleDecl, ...]
    stock_characterizations: tuple[StockCharacterizationDecl, ...]
    spatial_layers: tuple[SpatialLayerDecl, ...]
    spatial_measure_sets: tuple[SpatialMeasureSetDecl, ...]
    time_series: tuple[TimeSeriesDecl, ...]
    year_sets: tuple[YearSetDecl, ...]
    policies: tuple[PolicyDecl, ...]
    region_partitions: tuple[RegionPartitionDecl, ...]
    zone_overlays: tuple[ZoneOverlayDecl, ...]
    sites: tuple[SiteDecl, ...]
    facilities: tuple[FacilityDecl, ...]
    fleets: tuple[FleetDecl, ...]
    zone_opportunities: tuple[ZoneOpportunityDecl, ...]
    networks: tuple[NetworkDecl, ...]
    runs: tuple[RunDecl, ...]


def _source_ref(path: str) -> SourceRef:
    return SourceRef(path=path)


def _tuple_strings(values: Any) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or []))


def _parse_flow_spec(data: dict[str, Any], path: str) -> FlowSpec:
    return FlowSpec(
        commodity=str(data["commodity"]),
        basis=str(data["basis"]) if data.get("basis") is not None else None,
        coefficient=data.get("coefficient"),
        source_ref=_source_ref(path),
    )


def _parse_performance(
    data: dict[str, Any] | None,
    path: str,
) -> PerformanceSpec | None:
    if not data:
        return None
    return PerformanceSpec(
        kind=str(data["kind"]),
        value=float(data["value"]),
        source_ref=_source_ref(path),
    )


def _parse_emission_factor(data: dict[str, Any], path: str) -> EmissionFactor:
    return EmissionFactor(
        commodity=str(data["commodity"]),
        factor=data["factor"],
        source_ref=_source_ref(path),
    )


def _parse_activity_bound(
    data: dict[str, Any] | None,
    path: str,
) -> ActivityBoundSpec | None:
    if not data:
        return None
    return ActivityBoundSpec(
        limtype=str(data["limtype"]),
        value=data["value"],
        source_ref=_source_ref(path),
    )


def _parse_series_values(values: Any) -> dict[int, float]:
    return {
        int(year): float(value)
        for year, value in (values or {}).items()
    }


def _parse_quantity_values(values: Any) -> dict[int, str | int | float]:
    return {
        int(year): value
        for year, value in (values or {}).items()
    }


def _parse_series_spec(
    data: Any,
    path: str,
) -> QuantitySpec:
    if not isinstance(data, dict):
        raise TypeError(f"{path} must be an object")
    has_series = data.get("series") is not None
    has_values = bool(data.get("values"))
    if has_series == has_values:
        raise TypeError(f"{path} must define exactly one of series or values")
    return QuantitySpec(
        scalar=None,
        series=(str(data["series"]) if data.get("series") else None),
        interpolation=(
            str(data["interpolation"]) if data.get("interpolation") else None
        ),
        values=_parse_quantity_values(data.get("values")),
        source_ref=_source_ref(path),
    )


def _parse_base_year_adjustment(
    data: dict[str, Any] | None, path: str
) -> BaseYearAdjustment | None:
    if not data:
        return None
    elasticity = data.get("elasticity")
    series_spec = _parse_series_spec(data["series"], f"{path}.series")
    return BaseYearAdjustment(
        series=series_spec,
        elasticity=float(elasticity) if elasticity is not None else None,
        source_ref=_source_ref(path),
    )


def _parse_observed_value(data: dict[str, Any], path: str) -> ObservedValue:
    return ObservedValue(
        value=data["value"],
        year=int(data["year"]),
        source_ref=_source_ref(path),
    )


def _parse_stock_observation(data: dict[str, Any], path: str) -> StockObservation:
    return StockObservation(
        technology=str(data["technology"]),
        metric=str(data["metric"]),
        observed=_parse_observed_value(data["observed"], f"{path}.observed"),
        adjust_to_base_year=_parse_base_year_adjustment(
            data.get("adjust_to_base_year"),
            f"{path}.adjust_to_base_year",
        ),
        source_ref=_source_ref(path),
    )


def _parse_stock_block(data: dict[str, Any] | None, path: str) -> StockBlock | None:
    if not data:
        return None
    return StockBlock(
        adjust_to_base_year=_parse_base_year_adjustment(
            data.get("adjust_to_base_year"),
            f"{path}.adjust_to_base_year",
        ),
        items=tuple(
            _parse_stock_observation(item, f"{path}.items[{idx}]")
            for idx, item in enumerate(data.get("items") or [])
        ),
        source_ref=_source_ref(path),
    )


def _parse_asset_new_build_limits(
    values: Any,
    path: str,
) -> tuple[AssetNewBuildLimit, ...]:
    return tuple(
        AssetNewBuildLimit(
            technology=str(item["technology"]),
            max_new_capacity=item["max_new_capacity"],
            source_ref=_source_ref(f"{path}[{idx}]"),
        )
        for idx, item in enumerate(values or [])
    )


def parse_source(source: dict[str, Any]) -> SourceDocument:
    """Parse a validated public source mapping into typed AST objects."""
    raw_year_sets = list(source.get("year_sets") or [])
    return SourceDocument(
        dsl_version=str(source["dsl_version"]) if source.get("dsl_version") else None,
        imports=tuple(
            ImportDecl(
                package=str(item["package"]),
                alias=str(item["as"]),
                only={
                    key: _tuple_strings(value)
                    for key, value in (item.get("only") or {}).items()
                },
                source_ref=_source_ref(f"imports[{idx}]"),
            )
            for idx, item in enumerate(source.get("imports") or [])
        ),
        commodities=tuple(
            CommodityDecl(
                id=str(item["id"]),
                type=str(item["type"]),
                energy_form=(
                    str(item["energy_form"])
                    if item.get("energy_form") is not None
                    else None
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"commodities[{idx}]"),
            )
            for idx, item in enumerate(source.get("commodities") or [])
        ),
        technologies=tuple(
            TechnologyDecl(
                id=str(item["id"]),
                provides=str(item["provides"]),
                inputs=tuple(
                    _parse_flow_spec(flow, f"technologies[{idx}].inputs[{flow_idx}]")
                    for flow_idx, flow in enumerate(item.get("inputs") or [])
                ),
                outputs=tuple(
                    _parse_flow_spec(flow, f"technologies[{idx}].outputs[{flow_idx}]")
                    for flow_idx, flow in enumerate(item.get("outputs") or [])
                ),
                performance=_parse_performance(
                    item.get("performance"),
                    f"technologies[{idx}].performance",
                ),
                emissions=tuple(
                    _parse_emission_factor(
                        emission,
                        f"technologies[{idx}].emissions[{emission_idx}]",
                    )
                    for emission_idx, emission in enumerate(item.get("emissions") or [])
                ),
                investment_cost=item.get("investment_cost"),
                fixed_om=item.get("fixed_om"),
                variable_om=item.get("variable_om"),
                activity_bound=_parse_activity_bound(
                    item.get("activity_bound"),
                    f"technologies[{idx}].activity_bound",
                ),
                lifetime=item.get("lifetime"),
                stock_characterization=(
                    str(item["stock_characterization"])
                    if item.get("stock_characterization")
                    else None
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"technologies[{idx}]"),
            )
            for idx, item in enumerate(source.get("technologies") or [])
        ),
        technology_roles=tuple(
            TechnologyRoleDecl(
                id=str(item["id"]),
                primary_service=str(item["primary_service"]),
                technologies=_tuple_strings(item.get("technologies")),
                transitions=tuple(
                    RoleTransition(
                        from_technology=str(transition["from"]),
                        to_technology=str(transition["to"]),
                        kind=str(transition["kind"]),
                        cost=transition.get("cost"),
                        lead_time=transition.get("lead_time"),
                        source_ref=_source_ref(
                            f"technology_roles[{idx}].transitions[{transition_idx}]"
                        ),
                    )
                    for transition_idx, transition in enumerate(
                        item.get("transitions") or []
                    )
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"technology_roles[{idx}]"),
            )
            for idx, item in enumerate(source.get("technology_roles") or [])
        ),
        stock_characterizations=tuple(
            StockCharacterizationDecl(
                id=str(item["id"]),
                applies_to=_tuple_strings(item.get("applies_to")),
                counted_asset_label=(
                    str(item["counted_asset_label"])
                    if item.get("counted_asset_label")
                    else None
                ),
                conversions=tuple(
                    MetricConversion(
                        from_metric=str(conversion["from_metric"]),
                        to_metric=str(conversion["to_metric"]),
                        factor=conversion["factor"],
                        source_ref=_source_ref(
                            "stock_characterizations"
                            f"[{idx}].conversions[{conversion_idx}]"
                        ),
                    )
                    for conversion_idx, conversion in enumerate(
                        item.get("conversions") or []
                    )
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"stock_characterizations[{idx}]"),
            )
            for idx, item in enumerate(source.get("stock_characterizations") or [])
        ),
        spatial_layers=tuple(
            SpatialLayerDecl(
                id=str(item["id"]),
                kind=str(item["kind"]),
                key=str(item["key"]),
                geometry_file=str(item["geometry_file"]),
                source_ref=_source_ref(f"spatial_layers[{idx}]"),
            )
            for idx, item in enumerate(source.get("spatial_layers") or [])
        ),
        spatial_measure_sets=tuple(
            SpatialMeasureSetDecl(
                id=str(item["id"]),
                layer=str(item["layer"]),
                measures=tuple(
                    SpatialMeasureDecl(
                        id=str(measure["id"]),
                        observed_year=int(measure["observed_year"]),
                        unit=str(measure["unit"]),
                        file=str(measure["file"]),
                        column=str(measure["column"]),
                        description=(
                            str(measure["description"])
                            if measure.get("description")
                            else None
                        ),
                        source_ref=_source_ref(
                            f"spatial_measure_sets[{idx}].measures[{measure_idx}]"
                        ),
                    )
                    for measure_idx, measure in enumerate(item.get("measures") or [])
                ),
                source_ref=_source_ref(f"spatial_measure_sets[{idx}]"),
            )
            for idx, item in enumerate(source.get("spatial_measure_sets") or [])
        ),
        time_series=tuple(
            TimeSeriesDecl(
                id=str(item["id"]),
                kind=str(item["kind"]),
                unit=str(item["unit"]),
                interpolation=str(item["interpolation"]),
                base_year=int(item["base_year"]) if item.get("base_year") else None,
                values=_parse_series_values(item.get("values")),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"time_series[{idx}]"),
            )
            for idx, item in enumerate(source.get("time_series") or [])
        ),
        year_sets=tuple(
            YearSetDecl(
                id=str(item["id"]),
                start_year=int(item["start_year"]),
                milestone_years=tuple(
                    int(year) for year in (item.get("milestone_years") or [])
                ),
                source_ref=_source_ref(f"year_sets[{idx}]"),
            )
            for idx, item in enumerate(raw_year_sets)
        ),
        policies=tuple(
            PolicyDecl(
                id=str(item["id"]),
                kind=str(item["kind"]),
                emission_commodity=str(item["emission_commodity"]),
                budget=(
                    _parse_series_spec(
                        item["budget"],
                        f"policies[{idx}].budget",
                    )
                    if item.get("budget") is not None
                    else None
                ),
                cases=tuple(
                    PolicyCaseDecl(
                        id=str(case["id"]),
                        budget=_parse_series_spec(
                            case["budget"],
                            f"policies[{idx}].cases[{case_idx}].budget",
                        ),
                        description=(
                            str(case["description"])
                            if case.get("description")
                            else None
                        ),
                        source_ref=_source_ref(f"policies[{idx}].cases[{case_idx}]"),
                    )
                    for case_idx, case in enumerate(item.get("cases") or [])
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"policies[{idx}]"),
            )
            for idx, item in enumerate(source.get("policies") or [])
        ),
        region_partitions=tuple(
            RegionPartitionDecl(
                id=str(item["id"]),
                layer=str(item["layer"]),
                members=_tuple_strings(item.get("members")),
                mapping=PartitionMapping(
                    kind=str(item["mapping"]["kind"]),
                    file=(
                        str(item["mapping"]["file"])
                        if item["mapping"].get("file")
                        else None
                    ),
                    source_key=(
                        str(item["mapping"]["source_key"])
                        if item["mapping"].get("source_key")
                        else None
                    ),
                    target_key=(
                        str(item["mapping"]["target_key"])
                        if item["mapping"].get("target_key")
                        else None
                    ),
                    value=(
                        str(item["mapping"]["value"])
                        if item["mapping"].get("value")
                        else None
                    ),
                    source_ref=_source_ref(f"region_partitions[{idx}].mapping"),
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"region_partitions[{idx}]"),
            )
            for idx, item in enumerate(source.get("region_partitions") or [])
        ),
        zone_overlays=tuple(
            ZoneOverlayDecl(
                id=str(item["id"]),
                layer=str(item["layer"]),
                key=str(item["key"]),
                geometry_file=str(item["geometry_file"]),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"zone_overlays[{idx}]"),
            )
            for idx, item in enumerate(source.get("zone_overlays") or [])
        ),
        sites=tuple(
            SiteDecl(
                id=str(item["id"]),
                location=SiteLocation(
                    point=(
                        {
                            "lat": float(item["location"]["point"]["lat"]),
                            "lon": float(item["location"]["point"]["lon"]),
                        }
                        if item.get("location", {}).get("point")
                        else None
                    ),
                    feature_ref=(
                        {
                            "layer": str(item["location"]["feature_ref"]["layer"]),
                            "id": str(item["location"]["feature_ref"]["id"]),
                        }
                        if item.get("location", {}).get("feature_ref")
                        else None
                    ),
                    source_ref=_source_ref(f"sites[{idx}].location"),
                ),
                membership_overrides=(
                    MembershipOverrides(
                        region_partitions={
                            str(key): str(value)
                            for key, value in (
                                item.get("membership_overrides", {})
                                .get("region_partitions", {})
                                .items()
                            )
                        },
                        zone_overlays={
                            str(key): str(value)
                            for key, value in (
                                item.get("membership_overrides", {})
                                .get("zone_overlays", {})
                                .items()
                            )
                        },
                        source_ref=_source_ref(
                            f"sites[{idx}].membership_overrides"
                        ),
                    )
                    if item.get("membership_overrides")
                    else None
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"sites[{idx}]"),
            )
            for idx, item in enumerate(source.get("sites") or [])
        ),
        facilities=tuple(
            FacilityDecl(
                id=str(item["id"]),
                site=str(item["site"]),
                technology_role=str(item["technology_role"]),
                available_technologies=_tuple_strings(
                    item.get("available_technologies")
                ),
                stock=_parse_stock_block(item.get("stock"), f"facilities[{idx}].stock"),
                new_build_limits=_parse_asset_new_build_limits(
                    item.get("new_build_limits"),
                    f"facilities[{idx}].new_build_limits",
                ),
                policies=_tuple_strings(item.get("policies")),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"facilities[{idx}]"),
            )
            for idx, item in enumerate(source.get("facilities") or [])
        ),
        fleets=tuple(
            FleetDecl(
                id=str(item["id"]),
                technology_role=str(item["technology_role"]),
                available_technologies=_tuple_strings(
                    item.get("available_technologies")
                ),
                stock=_parse_stock_block(item.get("stock"), f"fleets[{idx}].stock"),
                new_build_limits=_parse_asset_new_build_limits(
                    item.get("new_build_limits"),
                    f"fleets[{idx}].new_build_limits",
                ),
                distribution=DistributionBlock(
                    method=str(item["distribution"]["method"]),
                    weight_by=(
                        str(item["distribution"]["weight_by"])
                        if item["distribution"].get("weight_by")
                        else None
                    ),
                    custom_weights_file=(
                        str(item["distribution"]["custom_weights_file"])
                        if item["distribution"].get("custom_weights_file")
                        else None
                    ),
                    target_regions=_tuple_strings(
                        item["distribution"].get("target_regions")
                    ),
                    source_ref=_source_ref(f"fleets[{idx}].distribution"),
                ),
                policies=_tuple_strings(item.get("policies")),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"fleets[{idx}]"),
            )
            for idx, item in enumerate(source.get("fleets") or [])
        ),
        zone_opportunities=tuple(
            ZoneOpportunityDecl(
                id=str(item["id"]),
                technology_role=str(item["technology_role"]),
                technology=str(item["technology"]),
                zone=str(item["zone"]),
                max_new_capacity=item["max_new_capacity"],
                profile_ref=(
                    str(item["profile_ref"]) if item.get("profile_ref") else None
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"zone_opportunities[{idx}]"),
            )
            for idx, item in enumerate(source.get("zone_opportunities") or [])
        ),
        networks=tuple(
            NetworkDecl(
                id=str(item["id"]),
                kind=str(item["kind"]),
                node_basis=NetworkNodeBasis(
                    kind=str(item["node_basis"]["kind"]),
                    ref=(
                        str(item["node_basis"]["ref"])
                        if item["node_basis"].get("ref")
                        else None
                    ),
                    source_ref=_source_ref(f"networks[{idx}].node_basis"),
                ),
                links=tuple(
                    NetworkLink(
                        id=str(link["id"]),
                        from_node=str(link["from"]),
                        to_node=str(link["to"]),
                        commodity=str(link["commodity"]),
                        existing_transfer_capacity=link.get(
                            "existing_transfer_capacity"
                        ),
                        max_new_capacity=link.get("max_new_capacity"),
                        source_ref=_source_ref(
                            f"networks[{idx}].links[{link_idx}]"
                        ),
                    )
                    for link_idx, link in enumerate(item.get("links") or [])
                ),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"networks[{idx}]"),
            )
            for idx, item in enumerate(source.get("networks") or [])
        ),
        runs=tuple(
            RunDecl(
                id=str(item["id"]),
                veda_book_name=str(item["veda_book_name"]),
                year_set=str(item["year_set"]),
                currency_year=int(item["currency_year"]),
                region_partition=str(item["region_partition"]),
                temporal_partition=(
                    str(item["temporal_partition"])
                    if item.get("temporal_partition")
                    else None
                ),
                reporting_value_flows=bool(
                    (item.get("reporting") or {}).get("value_flows", True)
                ),
                include_cases=_tuple_strings(item.get("include_cases")),
                enable_policies=_tuple_strings(item.get("enable_policies")),
                description=(
                    str(item["description"]) if item.get("description") else None
                ),
                source_ref=_source_ref(f"runs[{idx}]"),
            )
            for idx, item in enumerate(source.get("runs") or [])
        ),
    )
