"""Semantic assertion helpers for solver-backed known-answer tests."""

from __future__ import annotations

from math import isclose

from tools.veda_dev.times_results import TimesResults


def _scope_text(*, year: str | None, region: str | None, timeslice: str | None) -> str:
    parts: list[str] = []
    if year is not None:
        parts.append(f"year={year}")
    if region is not None:
        parts.append(f"region={region}")
    if timeslice is not None:
        parts.append(f"timeslice={timeslice}")
    return ", ".join(parts) if parts else "all scopes"


def _matches(
    row: dict,
    *,
    process: str | None = None,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
    commodity: str | None = None,
) -> bool:
    if process is not None and row.get("process") != process:
        return False
    if year is not None and row.get("year") != year:
        return False
    if region is not None and row.get("region") != region:
        return False
    if timeslice is not None and row.get("timeslice") != timeslice:
        return False
    if commodity is not None and row.get("commodity") != commodity:
        return False
    return True


def _sum_levels(rows: list[dict], **filters: str | None) -> float:
    return sum(
        float(row.get("level", 0.0))
        for row in rows
        if _matches(
            row,
            process=filters.get("process"),
            year=filters.get("year"),
            region=filters.get("region"),
            timeslice=filters.get("timeslice"),
            commodity=filters.get("commodity"),
        )
    )


def activity_level(
    results: TimesResults,
    *,
    process: str,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
) -> float:
    """Return total activity level for a process in the requested scope."""
    return _sum_levels(
        results.var_act,
        process=process,
        year=year,
        region=region,
        timeslice=timeslice,
    )


def flow_level(
    results: TimesResults,
    *,
    process: str,
    commodity: str,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
) -> float:
    """Return total commodity flow for a process in the requested scope."""
    return _sum_levels(
        results.var_flo,
        process=process,
        commodity=commodity,
        year=year,
        region=region,
        timeslice=timeslice,
    )


def flow_level_for_commodity_token(
    results: TimesResults,
    *,
    process: str,
    commodity_token: str,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
) -> float:
    """Return total flow where commodity contains the requested token."""
    token_upper = commodity_token.upper()
    return sum(
        float(row.get("level", 0.0))
        for row in results.var_flo
        if _matches(
            row,
            process=process,
            year=year,
            region=region,
            timeslice=timeslice,
        )
        and token_upper in str(row.get("commodity", "")).upper()
    )


def new_capacity_level(
    results: TimesResults,
    *,
    process: str,
    year: str | None = None,
    region: str | None = None,
) -> float:
    """Return total new capacity level for a process in the requested scope."""
    return _sum_levels(
        results.var_ncap,
        process=process,
        year=year,
        region=region,
    )


def assert_activity_at_least(
    results: TimesResults,
    *,
    process: str,
    min_level: float,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
    atol: float = 1e-6,
) -> None:
    """Assert process activity is present above a minimum threshold."""
    actual = activity_level(
        results,
        process=process,
        year=year,
        region=region,
        timeslice=timeslice,
    )
    if actual + atol < min_level:
        scope = _scope_text(year=year, region=region, timeslice=timeslice)
        raise AssertionError(
            "Expected process "
            f"'{process}' activity >= {min_level} in {scope}, got {actual}"
        )


def assert_activity_near_zero(
    results: TimesResults,
    *,
    process: str,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
    atol: float = 1e-6,
) -> None:
    """Assert process activity is effectively zero in the requested scope."""
    actual = activity_level(
        results,
        process=process,
        year=year,
        region=region,
        timeslice=timeslice,
    )
    if abs(actual) > atol:
        scope = _scope_text(year=year, region=region, timeslice=timeslice)
        raise AssertionError(
            "Expected process "
            f"'{process}' activity near zero (±{atol}) in {scope}, got {actual}"
        )


def assert_new_capacity_at_least(
    results: TimesResults,
    *,
    process: str,
    min_level: float,
    year: str | None = None,
    region: str | None = None,
    atol: float = 1e-6,
) -> None:
    """Assert solved new capacity is present above a minimum threshold."""
    actual = new_capacity_level(
        results,
        process=process,
        year=year,
        region=region,
    )
    if actual + atol < min_level:
        scope = _scope_text(year=year, region=region, timeslice=None)
        raise AssertionError(
            "Expected process "
            f"'{process}' new capacity >= {min_level} in {scope}, got {actual}"
        )


def assert_new_capacity_near_zero(
    results: TimesResults,
    *,
    process: str,
    year: str | None = None,
    region: str | None = None,
    atol: float = 1e-6,
) -> None:
    """Assert process new-capacity decision is effectively zero."""
    actual = new_capacity_level(
        results,
        process=process,
        year=year,
        region=region,
    )
    if abs(actual) > atol:
        scope = _scope_text(year=year, region=region, timeslice=None)
        raise AssertionError(
            "Expected process "
            f"'{process}' new capacity near zero (±{atol}) in {scope}, got {actual}"
        )


def assert_flow_ratio(
    results: TimesResults,
    *,
    process: str,
    numerator_commodity: str,
    denominator_commodity: str,
    expected_ratio: float,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-6,
) -> None:
    """Assert flow ratio for two commodities on a process."""
    numerator = flow_level(
        results,
        process=process,
        commodity=numerator_commodity,
        year=year,
        region=region,
        timeslice=timeslice,
    )
    denominator = flow_level(
        results,
        process=process,
        commodity=denominator_commodity,
        year=year,
        region=region,
        timeslice=timeslice,
    )
    if abs(denominator) <= abs_tol:
        scope = _scope_text(year=year, region=region, timeslice=timeslice)
        raise AssertionError(
            f"Cannot compute flow ratio for process '{process}' in {scope}: "
            f"denominator commodity '{denominator_commodity}' is {denominator}"
        )

    actual_ratio = numerator / denominator
    if not isclose(actual_ratio, expected_ratio, rel_tol=rel_tol, abs_tol=abs_tol):
        scope = _scope_text(year=year, region=region, timeslice=timeslice)
        raise AssertionError(
            f"Expected flow ratio {numerator_commodity}/{denominator_commodity} "
            "for process "
            f"'{process}' in {scope} to be {expected_ratio}, got {actual_ratio}"
        )


def assert_flow_activity_ratio_for_commodity_token(
    results: TimesResults,
    *,
    process: str,
    commodity_token: str,
    expected_ratio: float,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-6,
) -> None:
    """Assert commodity-token flow/activity ratio for a process."""
    flow = flow_level_for_commodity_token(
        results,
        process=process,
        commodity_token=commodity_token,
        year=year,
        region=region,
        timeslice=timeslice,
    )
    scope = _scope_text(year=year, region=region, timeslice=timeslice)
    source = results.var_flo_source or "none"
    if abs(flow) <= abs_tol:
        raise AssertionError(
            "Expected non-zero flow for process "
            f"'{process}' commodity token '{commodity_token}' in {scope}, "
            f"got {flow} (flow_source={source})"
        )

    activity = activity_level(
        results,
        process=process,
        year=year,
        region=region,
        timeslice=timeslice,
    )
    if abs(activity) <= abs_tol:
        raise AssertionError(
            "Cannot compute flow/activity ratio for process "
            f"'{process}' in {scope}: activity is {activity}"
        )

    actual_ratio = flow / activity
    if not isclose(actual_ratio, expected_ratio, rel_tol=rel_tol, abs_tol=abs_tol):
        raise AssertionError(
            "Expected flow/activity ratio for process "
            f"'{process}' commodity token '{commodity_token}' in {scope} "
            f"to be {expected_ratio}, got {actual_ratio} (flow_source={source})"
        )


def assert_process_share_at_least(
    results: TimesResults,
    *,
    process: str,
    process_pool: list[str],
    min_share: float,
    year: str | None = None,
    region: str | None = None,
    timeslice: str | None = None,
    abs_tol: float = 1e-6,
) -> None:
    """Assert process share across a process pool meets a minimum."""
    target = activity_level(
        results,
        process=process,
        year=year,
        region=region,
        timeslice=timeslice,
    )
    total = 0.0
    for pool_process in process_pool:
        total += activity_level(
            results,
            process=pool_process,
            year=year,
            region=region,
            timeslice=timeslice,
        )

    if abs(total) <= abs_tol:
        scope = _scope_text(year=year, region=region, timeslice=timeslice)
        raise AssertionError(
            "Cannot compute share for process "
            f"'{process}' in {scope}: pool activity is zero"
        )

    share = target / total
    if share + abs_tol < min_share:
        scope = _scope_text(year=year, region=region, timeslice=timeslice)
        raise AssertionError(
            f"Expected process '{process}' share >= {min_share} in {scope}, got {share}"
        )
