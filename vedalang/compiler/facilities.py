"""Facility primitive lowering for VedaLang mode-based fuel switching.

This module translates top-level facility/template declarations into compiler
constructs (demands, process variants, availability, process parameters) and
emits additional policy artifacts (UC rows).
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .ir import Variant
from .registry import VedaLangError


def _sanitize_scope_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", value.lower())
    token = token.strip("_")
    return token or "facility"


def _series_values(series: dict) -> dict[str, float]:
    values = series.get("values", {}) if isinstance(series, dict) else {}
    return {str(k): float(v) for k, v in values.items()}


def _scale_series(values: dict[str, float], factor: float) -> dict[str, float]:
    if factor == 1.0:
        return dict(values)
    return {str(y): float(v) * factor for y, v in values.items()}


def _value_for_year(values: dict[str, float], year: int) -> float:
    if not values:
        return 0.0
    key = str(year)
    if key in values:
        return float(values[key])
    years = sorted(int(y) for y in values)
    prev = [y for y in years if y <= year]
    if prev:
        return float(values[str(prev[-1])])
    return float(values[str(years[0])])


@dataclass
class ModeSpec:
    id: str
    fuel_in: str
    capex: float
    existing: bool
    efficiency: Any | None
    emission_factors: dict[str, Any]
    ramp_rate: float | None


@dataclass
class FacilityVariantSpec:
    id: str
    baseline_mode: str
    mode_ladder: list[str]
    modes: list[ModeSpec]


@dataclass
class FacilityEntity:
    """Internal resolved facility entity after selection and regional splitting."""

    facility_id: str
    class_name: str
    template_id: str
    role: str
    scope: str
    region: str
    representation: str
    output_series: dict[str, float]
    output_interpolation: str
    primary_output_commodity: str
    cap_base: float
    cap_unit: str
    capacity_coupling: str
    no_backsliding: bool
    variants: list[FacilityVariantSpec]
    safeguard: dict[str, Any] | None
    ranking_metric: float


def _resolve_spatial_mapping(
    source: dict, location_ref: str
) -> list[tuple[str, float]]:
    model = source.get("model", {})
    regions = model.get("regions", [])
    region_scheme = model.get("region_scheme")

    if location_ref in regions:
        return [(location_ref, 1.0)]

    mappings = source.get("spatial_mappings", []) or []
    if not region_scheme:
        raise VedaLangError(
            f"Facility location_ref '{location_ref}' requires "
            "model.region_scheme or direct region name"
        )

    for mapping in mappings:
        if mapping.get("scheme") != region_scheme:
            continue
        if mapping.get("from") not in (None, "facility_location_ref"):
            continue
        entries = (mapping.get("map") or {}).get(location_ref)
        if not entries:
            continue
        resolved: list[tuple[str, float]] = []
        total = 0.0
        for entry in entries:
            region = entry["region"]
            share = float(entry.get("share", 1.0))
            if region not in regions:
                raise VedaLangError(
                    f"Spatial mapping for '{location_ref}' references "
                    f"unknown region '{region}'"
                )
            resolved.append((region, share))
            total += share
        if abs(total - 1.0) > 1e-6:
            raise VedaLangError(
                f"Spatial mapping shares for '{location_ref}' must sum to "
                f"1.0 (got {total})"
            )
        return resolved

    raise VedaLangError(
        f"No spatial mapping found for location_ref '{location_ref}' "
        f"under scheme '{region_scheme}'"
    )


def _mode_variant_id(
    facility_id: str,
    role: str,
    template_variant_id: str,
    mode_id: str,
) -> str:
    return "_".join(
        [
            "fac",
            _sanitize_scope_token(facility_id),
            "role",
            _sanitize_scope_token(role),
            "var",
            _sanitize_scope_token(template_variant_id),
            "mode",
            _sanitize_scope_token(mode_id),
        ]
    )


def _normalize_template_variants(
    template: dict,
    template_id: str,
    commodities: dict[str, dict],
) -> list[FacilityVariantSpec]:
    template_variants = template.get("variants") or []
    if not template_variants:
        raise VedaLangError(
            f"Facility template '{template_id}' must define at least one variant"
        )

    result: list[FacilityVariantSpec] = []
    seen_variant_ids: set[str] = set()

    for variant in template_variants:
        variant_id = variant["id"]
        if variant_id in seen_variant_ids:
            raise VedaLangError(
                f"Facility template '{template_id}' has duplicate variant "
                f"'{variant_id}'"
            )
        seen_variant_ids.add(variant_id)

        modes = variant.get("modes") or []
        if not modes:
            raise VedaLangError(
                f"Facility template '{template_id}' variant '{variant_id}' "
                "must define modes"
            )

        mode_specs: list[ModeSpec] = []
        mode_ids: set[str] = set()
        for mode in modes:
            mode_id = mode["id"]
            if mode_id in mode_ids:
                raise VedaLangError(
                    f"Facility template '{template_id}' variant '{variant_id}' "
                    f"has duplicate mode '{mode_id}'"
                )
            mode_ids.add(mode_id)

            fuel = mode["fuel_in"]
            commodity = commodities.get(fuel)
            if commodity is None:
                raise VedaLangError(
                    f"Facility template '{template_id}' variant '{variant_id}' mode "
                    f"'{mode_id}' references unknown fuel '{fuel}'"
                )
            if commodity.get("kind") == "emission":
                raise VedaLangError(
                    f"Facility template '{template_id}' variant '{variant_id}' mode "
                    f"'{mode_id}' cannot use emission commodity '{fuel}' as fuel_in"
                )

            mode_specs.append(
                ModeSpec(
                    id=mode_id,
                    fuel_in=fuel,
                    capex=float(mode.get("capex", 0.0)),
                    existing=bool(mode.get("existing", False)),
                    efficiency=deepcopy(mode.get("efficiency")),
                    emission_factors=deepcopy(mode.get("emission_factors") or {}),
                    ramp_rate=(
                        float(mode["ramp_rate"])
                        if mode.get("ramp_rate") is not None
                        else None
                    ),
                )
            )

        baseline_mode = variant["baseline_mode"]
        if baseline_mode not in mode_ids:
            raise VedaLangError(
                f"Facility template '{template_id}' variant '{variant_id}' "
                f"baseline_mode '{baseline_mode}' must reference one of its modes"
            )

        mode_ladder = list(variant.get("mode_ladder") or [])
        if set(mode_ladder) != mode_ids:
            raise VedaLangError(
                f"Facility template '{template_id}' variant '{variant_id}' mode_ladder "
                "must contain each mode exactly once"
            )

        baseline_spec = next(m for m in mode_specs if m.id == baseline_mode)
        if not baseline_spec.existing:
            raise VedaLangError(
                f"Facility template '{template_id}' variant '{variant_id}' baseline "
                f"mode '{baseline_mode}' must set existing=true"
            )

        existing_count = sum(1 for m in mode_specs if m.existing)
        if existing_count != 1:
            raise VedaLangError(
                f"Facility template '{template_id}' variant '{variant_id}' must have "
                "exactly one mode with existing=true"
            )

        result.append(
            FacilityVariantSpec(
                id=variant_id,
                baseline_mode=baseline_mode,
                mode_ladder=mode_ladder,
                modes=mode_specs,
            )
        )

    return result


def _entity_aggregation_key(entity: FacilityEntity, keys: list[str]) -> tuple:
    values: list[Any] = []
    for key in keys:
        if key == "template":
            values.append(entity.template_id)
        elif key == "class":
            values.append(entity.class_name)
        elif key == "region":
            values.append(entity.region)
        elif key == "primary_output_commodity":
            values.append(entity.primary_output_commodity)
        else:
            raise VedaLangError(
                f"Unsupported facility_selection.aggregation_key '{key}'"
            )
    return tuple(values)


def _aggregate_entities(
    entities: list[FacilityEntity], aggregation_keys: list[str]
) -> list[FacilityEntity]:
    grouped: dict[tuple[Any, ...], list[FacilityEntity]] = {}
    for entity in entities:
        key = _entity_aggregation_key(entity, aggregation_keys)
        grouped.setdefault(key, []).append(entity)

    result: list[FacilityEntity] = []
    for idx, (_, group) in enumerate(sorted(grouped.items())):
        base = group[0]

        output_values: dict[str, float] = {}
        for entity in group:
            for y, v in entity.output_series.items():
                output_values[y] = output_values.get(y, 0.0) + float(v)

        total_cap = sum(float(entity.cap_base) for entity in group)

        safeguard = None
        if base.safeguard:
            baseline_year = int(base.safeguard["baseline_year"])
            weighted_intensity = 0.0
            denom = 0.0
            for entity in group:
                y_val = _value_for_year(entity.output_series, baseline_year)
                weighted_intensity += (
                    float(entity.safeguard["baseline_intensity"]) * y_val
                )
                denom += y_val
            agg_intensity = (
                weighted_intensity / denom
                if denom > 0
                else float(base.safeguard["baseline_intensity"])
            )
            safeguard = deepcopy(base.safeguard)
            safeguard["baseline_intensity"] = agg_intensity

        result.append(
            FacilityEntity(
                facility_id=f"agg_{base.template_id}_{base.region}_{idx + 1}",
                class_name=base.class_name,
                template_id=base.template_id,
                role=base.role,
                scope=f"{base.scope}_agg{idx + 1}",
                region=base.region,
                representation="archetype",
                output_series=output_values,
                output_interpolation=base.output_interpolation,
                primary_output_commodity=base.primary_output_commodity,
                cap_base=total_cap,
                cap_unit=base.cap_unit,
                capacity_coupling=base.capacity_coupling,
                no_backsliding=base.no_backsliding,
                variants=deepcopy(base.variants),
                safeguard=safeguard,
                ranking_metric=sum(e.ranking_metric for e in group),
            )
        )

    return result


def prepare_facilities(
    source: dict,
    commodities: dict[str, dict],
    model_years: list[int],
) -> tuple[dict, dict]:
    """Materialize facilities into source-level demands/availability/parameters."""
    if not source.get("facilities"):
        return source, {"entities": [], "template_map": {}, "model_years": []}

    transformed = deepcopy(source)

    template_map = {t["id"]: t for t in transformed.get("facility_templates", [])}
    if not template_map:
        raise VedaLangError("facilities requires facility_templates")

    template_variants: dict[str, list[FacilityVariantSpec]] = {}
    for template_id, template in template_map.items():
        template_variants[template_id] = _normalize_template_variants(
            template, template_id, commodities
        )

    entities: list[FacilityEntity] = []

    for facility in transformed.get("facilities", []):
        facility_id = facility["id"]
        template_id = facility["template"]
        template = template_map.get(template_id)
        if template is None:
            raise VedaLangError(
                f"Facility '{facility_id}' references unknown template '{template_id}'"
            )

        class_name = facility["class"]
        if class_name != template["class"]:
            raise VedaLangError(
                f"Facility '{facility_id}' class '{class_name}' does not "
                f"match template class '{template['class']}'"
            )

        output_values = _series_values(facility.get("output_series") or {})
        if not output_values:
            raise VedaLangError(
                f"Facility '{facility_id}' output_series.values must not be empty"
            )
        output_interp = (facility.get("output_series") or {}).get(
            "interpolation", "interp_extrap"
        )

        cap_base_decl = facility.get("cap_base") or {}
        cap_base = float(cap_base_decl.get("value", 0.0))
        cap_unit = str(cap_base_decl.get("unit", ""))

        safeguard = (
            deepcopy(facility.get("safeguard")) if class_name == "safeguard" else None
        )
        baseline_metric = 0.0
        if safeguard:
            baseline_year = int(safeguard["baseline_year"])
            baseline_intensity = float(safeguard["baseline_intensity"])
            baseline_output = _value_for_year(output_values, baseline_year)
            baseline_metric = baseline_intensity * baseline_output

        for region, share in _resolve_spatial_mapping(
            transformed, facility["location_ref"]
        ):
            suffix = f"_{region.lower()}" if share != 1.0 else ""
            piece_id = f"{facility_id}{suffix}"
            scope_token = _sanitize_scope_token(piece_id)
            scope = f"{template['sector']}.{scope_token}"

            entities.append(
                FacilityEntity(
                    facility_id=piece_id,
                    class_name=class_name,
                    template_id=template_id,
                    role=template["role"],
                    scope=scope,
                    region=region,
                    representation=facility.get("representation", "individual"),
                    output_series=_scale_series(output_values, share),
                    output_interpolation=output_interp,
                    primary_output_commodity=template["primary_output_commodity"],
                    cap_base=cap_base * share,
                    cap_unit=cap_unit,
                    capacity_coupling=facility.get("capacity_coupling", "le"),
                    no_backsliding=bool(facility.get("no_backsliding", True)),
                    variants=deepcopy(template_variants[template_id]),
                    safeguard=safeguard,
                    ranking_metric=baseline_metric * share,
                )
            )

    selection = transformed.get("facility_selection") or {}
    mode = selection.get("mode", "top_n_by_baseline_emissions")
    if mode != "top_n_by_baseline_emissions":
        raise VedaLangError(f"Unsupported facility_selection.mode '{mode}'")
    ranking_metric = selection.get("ranking_metric", "baseline_emissions")
    if ranking_metric != "baseline_emissions":
        raise VedaLangError(
            f"Unsupported facility_selection.ranking_metric '{ranking_metric}'"
        )

    n_individual = selection.get("n_individual")
    aggregation_keys = selection.get("aggregation_keys") or [
        "template",
        "class",
        "region",
        "primary_output_commodity",
    ]
    mandatory_keys = {"template", "primary_output_commodity"}
    if not mandatory_keys.issubset(set(aggregation_keys)):
        raise VedaLangError(
            "facility_selection.aggregation_keys must include at least "
            "'template' and 'primary_output_commodity'"
        )

    explicit_archetypes = [e for e in entities if e.representation == "archetype"]
    individuals = [e for e in entities if e.representation != "archetype"]

    if n_individual is None:
        n_individual = len(individuals)

    individuals_sorted = sorted(
        individuals,
        key=lambda e: (-e.ranking_metric, e.facility_id),
    )
    selected_individual = individuals_sorted[:n_individual]
    to_aggregate = individuals_sorted[n_individual:]
    selected_entities = list(explicit_archetypes) + list(selected_individual)

    if to_aggregate:
        selected_entities.extend(_aggregate_entities(to_aggregate, aggregation_keys))

    demands = list(transformed.get("demands") or [])
    availability = list(transformed.get("availability") or [])
    process_parameters = list(transformed.get("process_parameters") or [])
    process_variants = list(transformed.get("process_variants") or [])

    existing_variant_ids = {v["id"] for v in process_variants}
    context_entities = []

    for entity in selected_entities:
        demands.append(
            {
                "commodity": entity.primary_output_commodity,
                "region": entity.region,
                "scope": entity.scope,
                "values": dict(entity.output_series),
                "interpolation": entity.output_interpolation,
            }
        )

        variant_blocks = []
        for template_variant in entity.variants:
            mode_entries = []
            for mode in template_variant.modes:
                synthetic_variant_id = _mode_variant_id(
                    entity.facility_id,
                    entity.role,
                    template_variant.id,
                    mode.id,
                )
                if synthetic_variant_id in existing_variant_ids:
                    raise VedaLangError(
                        "Facility-generated mode variant id collision: "
                        f"'{synthetic_variant_id}'"
                    )
                existing_variant_ids.add(synthetic_variant_id)

                process_variant = {
                    "id": synthetic_variant_id,
                    "role": entity.role,
                    "inputs": [{"commodity": mode.fuel_in}],
                    "outputs": [{"commodity": entity.primary_output_commodity}],
                    "investment_cost": float(mode.capex),
                }
                if mode.efficiency is not None:
                    process_variant["efficiency"] = deepcopy(mode.efficiency)
                if mode.emission_factors:
                    process_variant["emission_factors"] = deepcopy(
                        mode.emission_factors
                    )
                process_variants.append(process_variant)

                availability.append(
                    {
                        "variant": synthetic_variant_id,
                        "regions": [entity.region],
                        "scopes": [entity.scope],
                    }
                )

                mode_entries.append(
                    {
                        "mode_id": mode.id,
                        "process_variant_id": synthetic_variant_id,
                        "is_baseline": mode.id == template_variant.baseline_mode,
                        "ramp_rate": mode.ramp_rate,
                        "emission_factors": deepcopy(mode.emission_factors),
                    }
                )

            variant_blocks.append(
                {
                    "variant_id": template_variant.id,
                    "baseline_mode": template_variant.baseline_mode,
                    "mode_ladder": list(template_variant.mode_ladder),
                    "modes": mode_entries,
                }
            )

        context_entities.append(
            {
                "facility_id": entity.facility_id,
                "class_name": entity.class_name,
                "template_id": entity.template_id,
                "role": entity.role,
                "scope": entity.scope,
                "region": entity.region,
                "primary_output_commodity": entity.primary_output_commodity,
                "cap_base": float(entity.cap_base),
                "cap_unit": entity.cap_unit,
                "capacity_coupling": entity.capacity_coupling,
                "no_backsliding": bool(entity.no_backsliding),
                "variant_blocks": variant_blocks,
                "safeguard": entity.safeguard,
                "output_series": entity.output_series,
            }
        )

    transformed["demands"] = demands
    transformed["availability"] = availability
    transformed["process_parameters"] = process_parameters
    transformed["process_variants"] = process_variants

    context = {
        "entities": context_entities,
        "template_map": template_map,
        "model_years": list(model_years),
    }

    return transformed, context


def build_facility_variant_metadata(
    context: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build facility/mode metadata keyed by generated process variant id."""
    metadata: dict[str, dict[str, Any]] = {}
    for entity in context.get("entities", []):
        facility_id = str(entity.get("facility_id", ""))
        template_id = str(entity.get("template_id", ""))
        class_name = str(entity.get("class_name", ""))
        role = str(entity.get("role", ""))
        scope = str(entity.get("scope", ""))
        region = str(entity.get("region", ""))
        cap_base = float(entity.get("cap_base", 0.0))
        cap_unit = str(entity.get("cap_unit", ""))
        capacity_coupling = str(entity.get("capacity_coupling", "le"))
        no_backsliding = bool(entity.get("no_backsliding", True))

        for variant_block in entity.get("variant_blocks", []):
            template_variant_id = str(variant_block.get("variant_id", ""))
            baseline_mode = str(variant_block.get("baseline_mode", ""))
            mode_ladder = [str(mode) for mode in variant_block.get("mode_ladder", [])]
            ladder_index = {mode_id: idx for idx, mode_id in enumerate(mode_ladder)}
            for mode in variant_block.get("modes", []):
                process_variant_id = str(mode.get("process_variant_id", ""))
                if not process_variant_id:
                    continue
                mode_id = str(mode.get("mode_id", ""))
                metadata[process_variant_id] = {
                    "facility_id": facility_id,
                    "template_id": template_id,
                    "class_name": class_name,
                    "role": role,
                    "scope": scope,
                    "region": region,
                    "template_variant_id": template_variant_id,
                    "mode_id": mode_id,
                    "is_baseline_mode": bool(mode.get("is_baseline", False)),
                    "baseline_mode": baseline_mode,
                    "mode_ladder": list(mode_ladder),
                    "mode_ladder_index": int(ladder_index.get(mode_id, -1)),
                    "ramp_rate": mode.get("ramp_rate"),
                    "cap_base": cap_base,
                    "cap_unit": cap_unit,
                    "capacity_coupling": capacity_coupling,
                    "no_backsliding": no_backsliding,
                }
    return metadata


def _intensity_path(
    safeguard: dict,
    model_years: list[int],
) -> dict[int, float]:
    baseline_year = int(safeguard["baseline_year"])
    baseline_intensity = float(safeguard["baseline_intensity"])
    blocks = safeguard.get("intensity_decline_blocks") or []
    overrides = {
        int(y): float(v)
        for y, v in (safeguard.get("explicit_intensity_overrides") or {}).items()
    }

    def rate_for_year(year: int) -> float:
        for block in blocks:
            if int(block["from_year"]) <= year <= int(block["to_year"]):
                return float(block["annual_decline_pct"]) / 100.0
        return 0.0

    years = sorted(int(y) for y in model_years)
    path: dict[int, float] = {}
    current = baseline_intensity
    last_year = baseline_year
    for year in years:
        if year < baseline_year:
            path[year] = baseline_intensity
            continue
        for step_year in range(last_year + 1, year + 1):
            current = current * (1.0 - rate_for_year(step_year))
        path[year] = current
        last_year = year

    path[baseline_year] = baseline_intensity
    for year, value in overrides.items():
        if year in path:
            path[year] = value

    return path


def _mode_emission_factor(
    mode: dict[str, Any],
    emission_commodity: str,
    year: int,
) -> float:
    factors = mode.get("emission_factors") or {}
    value = factors.get(emission_commodity)
    if value is None and emission_commodity.endswith(":co2"):
        value = factors.get("co2")
    if value is None:
        return 0.0
    if isinstance(value, dict):
        values = value.get("values") or {}
        if not values:
            return 0.0
        normalized = {str(k): float(v) for k, v in values.items()}
        return _value_for_year(normalized, year)
    return float(value)


def _append_constraint(
    constraints: list[dict],
    uc_name: str,
    rows: list[dict],
) -> None:
    if not rows:
        return
    constraints.append(
        {
            "name": uc_name,
            "type": "__uc_rows__",
            "category": "policies",
            "rows": rows,
        }
    )


def generate_facility_artifacts(
    context: dict,
    variants: dict[str, Variant],
    process_symbol_map: dict[tuple[str, str, str | None], str],
) -> tuple[list[dict], list[dict]]:
    """Generate extra UC constraints for facilities."""
    del variants  # variant objects are not required by mode-based facility lowering.

    entities = context.get("entities", [])
    model_years = sorted(int(y) for y in context.get("model_years", []))

    tfm_rows: list[dict] = []
    constraints: list[dict] = []

    for entity in entities:
        facility_id = entity["facility_id"]
        region = entity["region"]
        scope = entity["scope"]
        cap_base = float(entity.get("cap_base", 0.0))
        no_backsliding = bool(entity.get("no_backsliding", True))
        coupling = entity.get("capacity_coupling", "le")
        coupling_limtype = "FX" if coupling == "eq" else "UP"

        for variant_block in entity.get("variant_blocks", []):
            variant_id = variant_block["variant_id"]
            mode_rows = []
            for mode in variant_block.get("modes", []):
                symbol = process_symbol_map.get(
                    (mode["process_variant_id"], region, scope)
                )
                if not symbol:
                    continue
                mode_rows.append({**mode, "process_symbol": symbol})

            if not mode_rows:
                continue

            for year in model_years:
                uc_name = f"FAC_CAP_COUPLE_{facility_id}_{variant_id}_{year}"
                rows = [
                    {
                        "uc_n": uc_name,
                        "description": f"Facility capacity coupling for {facility_id}",
                        "region": region,
                        "year": year,
                        "process": mode["process_symbol"],
                        "commodity": "",
                        "side": "LHS",
                        "uc_cap": 1,
                    }
                    for mode in mode_rows
                ]
                rows.append(
                    {
                        "uc_n": uc_name,
                        "description": f"Facility capacity coupling for {facility_id}",
                        "region": region,
                        "year": year,
                        "process": "",
                        "commodity": "",
                        "limtype": coupling_limtype,
                        "uc_rhsrt": cap_base,
                    }
                )
                _append_constraint(constraints, uc_name, rows)

            if model_years:
                y0 = model_years[0]
                for mode in mode_rows:
                    init_value = cap_base if mode.get("is_baseline") else 0.0
                    uc_name = (
                        f"FAC_CAP_INIT_{facility_id}_{variant_id}_{mode['mode_id']}_{y0}"
                    )
                    init_desc = f"Facility initial mode capacity for {facility_id}"
                    rows = [
                        {
                            "uc_n": uc_name,
                            "description": init_desc,
                            "region": region,
                            "year": y0,
                            "process": mode["process_symbol"],
                            "commodity": "",
                            "side": "LHS",
                            "uc_cap": 1,
                        },
                        {
                            "uc_n": uc_name,
                            "description": init_desc,
                            "region": region,
                            "year": y0,
                            "process": "",
                            "commodity": "",
                            "limtype": "FX",
                            "uc_rhsrt": init_value,
                        },
                    ]
                    _append_constraint(constraints, uc_name, rows)

            if no_backsliding and len(model_years) > 1:
                for mode in mode_rows:
                    if mode.get("is_baseline"):
                        continue
                    for idx in range(1, len(model_years)):
                        prev_year = model_years[idx - 1]
                        year = model_years[idx]
                        uc_name = (
                            "FAC_CAP_MONO_"
                            f"{facility_id}_{variant_id}_{mode['mode_id']}_{year}"
                        )
                        mono_desc = f"Facility no-backslide for {facility_id}"
                        rows = [
                            {
                                "uc_n": uc_name,
                                "description": mono_desc,
                                "region": region,
                                "year": year,
                                "process": mode["process_symbol"],
                                "commodity": "",
                                "side": "LHS",
                                "uc_cap": 1,
                            },
                            {
                                "uc_n": uc_name,
                                "description": mono_desc,
                                "region": region,
                                "year": prev_year,
                                "process": mode["process_symbol"],
                                "commodity": "",
                                "side": "LHS",
                                "uc_cap": -1,
                            },
                            {
                                "uc_n": uc_name,
                                "description": mono_desc,
                                "region": region,
                                "year": year,
                                "process": "",
                                "commodity": "",
                                "limtype": "LO",
                                "uc_rhsrt": 0,
                            },
                        ]
                        _append_constraint(constraints, uc_name, rows)

            if len(model_years) > 1:
                for mode in mode_rows:
                    ramp_rate = mode.get("ramp_rate")
                    if ramp_rate is None:
                        continue
                    ramp_limit = float(ramp_rate) * cap_base
                    for idx in range(1, len(model_years)):
                        prev_year = model_years[idx - 1]
                        year = model_years[idx]
                        uc_name = (
                            "FAC_CAP_RAMP_"
                            f"{facility_id}_{variant_id}_{mode['mode_id']}_{year}"
                        )
                        rows = [
                            {
                                "uc_n": uc_name,
                                "description": f"Facility ramp limit for {facility_id}",
                                "region": region,
                                "year": year,
                                "process": mode["process_symbol"],
                                "commodity": "",
                                "side": "LHS",
                                "uc_cap": 1,
                            },
                            {
                                "uc_n": uc_name,
                                "description": f"Facility ramp limit for {facility_id}",
                                "region": region,
                                "year": prev_year,
                                "process": mode["process_symbol"],
                                "commodity": "",
                                "side": "LHS",
                                "uc_cap": -1,
                            },
                            {
                                "uc_n": uc_name,
                                "description": f"Facility ramp limit for {facility_id}",
                                "region": region,
                                "year": year,
                                "process": "",
                                "commodity": "",
                                "limtype": "UP",
                                "uc_rhsrt": ramp_limit,
                            },
                        ]
                        _append_constraint(constraints, uc_name, rows)

        safeguard = entity.get("safeguard")
        if safeguard:
            intensity_path = _intensity_path(safeguard, model_years)
            emission_commodity = safeguard.get("emission_commodity", "emission:co2")

            safeguard_modes = []
            for variant_block in entity.get("variant_blocks", []):
                for mode in variant_block.get("modes", []):
                    symbol = process_symbol_map.get(
                        (mode["process_variant_id"], region, scope)
                    )
                    if not symbol:
                        continue
                    safeguard_modes.append({**mode, "process_symbol": symbol})

            for year in model_years:
                target_intensity = float(
                    intensity_path.get(year, intensity_path[max(intensity_path)])
                )
                uc_name = f"FAC_INT_{facility_id}_{year}"
                rows = []
                for mode in safeguard_modes:
                    ef = _mode_emission_factor(mode, emission_commodity, year)
                    coef = ef - target_intensity
                    if abs(coef) < 1e-12:
                        continue
                    rows.append(
                        {
                            "uc_n": uc_name,
                            "description": f"Safeguard intensity for {facility_id}",
                            "region": region,
                            "year": year,
                            "process": mode["process_symbol"],
                            "commodity": "",
                            "side": "LHS",
                            "uc_act": coef,
                        }
                    )
                if not rows:
                    continue
                rows.append(
                    {
                        "uc_n": uc_name,
                        "description": f"Safeguard intensity for {facility_id}",
                        "region": region,
                        "year": year,
                        "process": "",
                        "commodity": "",
                        "limtype": "UP",
                        "uc_rhsrt": 0,
                    }
                )
                _append_constraint(constraints, uc_name, rows)

    return tfm_rows, constraints
