"""Unit tests for semantic solver assertion helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.solver_assertions import (
    activity_level,
    assert_activity_at_least,
    assert_activity_near_zero,
    assert_flow_ratio,
    assert_process_share_at_least,
    flow_level,
)
from tools.veda_dev.times_results import TimesResults


def _sample_results() -> TimesResults:
    results = TimesResults(gdx_path=Path("/tmp/example.gdx"))
    results.var_act = [
        {
            "region": "R1",
            "year": "2030",
            "process": "wind",
            "timeslice": "ANNUAL",
            "level": 90.0,
        },
        {
            "region": "R1",
            "year": "2030",
            "process": "gas",
            "timeslice": "ANNUAL",
            "level": 10.0,
        },
    ]
    results.var_flo = [
        {
            "region": "R1",
            "year": "2030",
            "process": "ccgt",
            "commodity": "natural_gas",
            "timeslice": "ANNUAL",
            "level": 80.0,
        },
        {
            "region": "R1",
            "year": "2030",
            "process": "ccgt",
            "commodity": "electricity",
            "timeslice": "ANNUAL",
            "level": 40.0,
        },
    ]
    return results


def test_activity_and_flow_level_helpers() -> None:
    results = _sample_results()

    assert activity_level(
        results,
        process="wind",
        year="2030",
        region="R1",
    ) == pytest.approx(90.0)
    assert flow_level(
        results,
        process="ccgt",
        commodity="natural_gas",
        year="2030",
        region="R1",
    ) == pytest.approx(80.0)


def test_assertion_helpers_success_paths() -> None:
    results = _sample_results()

    assert_activity_at_least(
        results,
        process="wind",
        min_level=80.0,
        year="2030",
        region="R1",
    )
    assert_activity_near_zero(
        results,
        process="solar",
        year="2030",
        region="R1",
    )
    assert_flow_ratio(
        results,
        process="ccgt",
        numerator_commodity="natural_gas",
        denominator_commodity="electricity",
        expected_ratio=2.0,
        year="2030",
        region="R1",
    )
    assert_process_share_at_least(
        results,
        process="wind",
        process_pool=["wind", "gas"],
        min_share=0.85,
        year="2030",
        region="R1",
    )


def test_assertion_helpers_emit_context_on_failure() -> None:
    results = _sample_results()

    with pytest.raises(AssertionError, match="process 'gas'.*year=2030, region=R1"):
        assert_activity_at_least(
            results,
            process="gas",
            min_level=20.0,
            year="2030",
            region="R1",
        )

    with pytest.raises(AssertionError, match="flow ratio"):
        assert_flow_ratio(
            results,
            process="ccgt",
            numerator_commodity="natural_gas",
            denominator_commodity="electricity",
            expected_ratio=1.0,
            year="2030",
            region="R1",
        )
