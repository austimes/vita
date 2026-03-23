"""Shared canonical time-series utilities for VedaLang compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CanonicalSeries:
    kind: str
    unit: str
    interpolation: str
    values: dict[int, float]
    source: str


def is_series_spec(value: Any) -> bool:
    return isinstance(value, dict) and (
        "series" in value or "values" in value
    )


def _coerce_values(values: Mapping[Any, Any]) -> dict[int, float]:
    return {
        int(year): float(amount)
        for year, amount in values.items()
    }


def _series_item_parts(series: Any) -> tuple[str, str, str, dict[int, float]]:
    if isinstance(series, dict):
        return (
            str(series["kind"]),
            str(series["unit"]),
            str(series.get("interpolation", "interp_extrap")),
            _coerce_values(series.get("values", {})),
        )
    return (
        str(series.kind),
        str(series.unit),
        str(series.interpolation),
        _coerce_values(series.values),
    )


def resolve_series_spec(
    spec: dict[str, Any],
    *,
    series_library: Mapping[str, Any],
    default_kind: str = "absolute",
    default_interpolation: str = "interp_extrap",
) -> CanonicalSeries:
    series_ref = spec.get("series")
    if series_ref is not None:
        key = str(series_ref)
        series = series_library.get(key)
        if series is None:
            raise ValueError(f"series '{key}' is not defined")
        kind, unit, interpolation, values = _series_item_parts(series)
        return CanonicalSeries(
            kind=kind,
            unit=unit,
            interpolation=interpolation,
            values=values,
            source=key,
        )

    kind = str(spec.get("kind", default_kind))
    unit = str(spec.get("unit", ""))
    interpolation = str(spec.get("interpolation", default_interpolation))
    values = _coerce_values(spec.get("values", {}))
    return CanonicalSeries(
        kind=kind,
        unit=unit,
        interpolation=interpolation,
        values=values,
        source="inline",
    )


def expand_series_to_years(
    sparse_values: Mapping[int | str, int | float],
    model_years: list[int],
    interpolation: str,
) -> dict[int, float]:
    points = sorted((int(year), float(value)) for year, value in sparse_values.items())
    if not points:
        return {}

    first_year, first_val = points[0]
    last_year, last_val = points[-1]
    extrap_backward = interpolation in ("interp_extrap", "interp_extrap_back")
    extrap_forward = interpolation in (
        "interp_extrap",
        "interp_extrap_forward",
        "interp_extrap_eps",
    )
    do_interpolate = interpolation != "none"

    dense: dict[int, float] = {}
    for year in model_years:
        exact = next((value for point_year, value in points if point_year == year), None)
        if exact is not None:
            dense[year] = exact
            continue
        if not do_interpolate:
            continue

        before = [(point_year, value) for point_year, value in points if point_year < year]
        after = [(point_year, value) for point_year, value in points if point_year > year]
        if not before:
            if extrap_backward:
                dense[year] = first_val
            continue
        if not after:
            if extrap_forward:
                dense[year] = last_val
            continue

        y0, v0 = before[-1]
        y1, v1 = after[0]
        ratio = (year - y0) / (y1 - y0)
        dense[year] = v0 + (v1 - v0) * ratio

    return dense
