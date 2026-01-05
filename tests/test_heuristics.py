"""Tests for VedaLang heuristics linter."""

from vedalang.heuristics.linter import (
    H001_FixedNewCapShortLife,
    H002_DemandDeviceNoStock,
    H003_BaseYearCapacityAdequacy,
    H004_StockCoversAllDemand,
    run_heuristics,
)


class TestH001_FixedNewCapShortLife:
    """Tests for H001: Fixed new capacity with short lifetime."""

    def test_triggers_on_fixed_ncap_short_life(self):
        """Should warn when ncap_bound.fx is set with life < horizon."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],  # 30 year horizon
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                ],
                "processes": [
                    {
                        "name": "PP_SOLAR",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 1.0,
                        "life": 25,  # < 30 years
                        "ncap_bound": {"fx": 1.0},
                    }
                ],
                "scenarios": [],
            }
        }

        rule = H001_FixedNewCapShortLife()
        issues = rule.apply(model)

        assert len(issues) == 1
        assert issues[0].code == "H001"
        assert "PP_SOLAR" in issues[0].message
        assert issues[0].severity == "warning"

    def test_no_issue_when_life_exceeds_horizon(self):
        """Should not warn when lifetime covers the horizon."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [],
                        "efficiency": 0.55,
                        "life": 40,  # > 30 years
                        "ncap_bound": {"fx": 10.0},
                    }
                ],
                "scenarios": [],
            }
        }

        rule = H001_FixedNewCapShortLife()
        issues = rule.apply(model)

        assert len(issues) == 0

    def test_escalates_to_error_with_demand_growth(self):
        """Should escalate to error when connected to growing demand."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "PP_SOLAR",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 1.0,
                        "life": 25,
                        "ncap_bound": {"fx": 1.0},
                    },
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                    },
                ],
                "scenarios": [
                    {
                        "type": "demand_projection",
                        "commodity": "RSD",
                        "values": {"2020": 10, "2050": 20},
                    }
                ],
            }
        }

        rule = H001_FixedNewCapShortLife()
        issues = rule.apply(model)

        assert len(issues) == 1
        assert issues[0].severity == "error"


class TestH002_DemandDeviceNoStock:
    """Tests for H002: Demand device without stock."""

    def test_triggers_on_demand_device_without_stock(self):
        """Should error when demand device has no stock."""
        model = {
            "model": {
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                    }
                ],
            }
        }

        rule = H002_DemandDeviceNoStock()
        issues = rule.apply(model)

        assert len(issues) == 1
        assert issues[0].code == "H002"
        assert "DMD_RSD" in issues[0].message
        assert issues[0].severity == "error"

    def test_no_issue_when_stock_present(self):
        """Should not warn when demand device has stock."""
        model = {
            "model": {
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                        "stock": 100,
                    }
                ],
            }
        }

        rule = H002_DemandDeviceNoStock()
        issues = rule.apply(model)

        assert len(issues) == 0

    def test_ignores_non_demand_processes(self):
        """Should not check processes that don't output demand commodities."""
        model = {
            "model": {
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                ],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 0.55,
                    }
                ],
            }
        }

        rule = H002_DemandDeviceNoStock()
        issues = rule.apply(model)

        assert len(issues) == 0


class TestH003_BaseYearCapacityAdequacy:
    """Tests for H003: Base year capacity adequacy."""

    def test_triggers_on_insufficient_capacity(self):
        """Should warn when base year capacity is inadequate."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 0.55,
                        "stock": 0.1,  # Only 0.1 GW
                    },
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                        "stock": 100,
                    },
                ],
                "scenarios": [
                    {
                        "type": "demand_projection",
                        "commodity": "RSD",
                        "values": {"2020": 100},  # 100 PJ demand
                    }
                ],
            }
        }

        rule = H003_BaseYearCapacityAdequacy()
        issues = rule.apply(model)

        assert len(issues) == 1
        assert issues[0].code == "H003"
        assert "RSD" in issues[0].message

    def test_no_issue_with_adequate_capacity(self):
        """Should not warn when capacity is sufficient."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 0.55,
                        "stock": 50,  # 50 GW = ~740 PJ/year
                    },
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                        "stock": 100,
                    },
                ],
                "scenarios": [
                    {
                        "type": "demand_projection",
                        "commodity": "RSD",
                        "values": {"2020": 10},  # Only 10 PJ demand
                    }
                ],
            }
        }

        rule = H003_BaseYearCapacityAdequacy()
        issues = rule.apply(model)

        assert len(issues) == 0


class TestH004_StockCoversAllDemand:
    """Tests for H004: Stock covers all demand."""

    def test_triggers_when_stock_covers_all_demand(self):
        """Should warn when existing stock can meet all projected demand."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 0.55,
                        "stock": 100,  # 100 GW -> ~1478 PJ/yr
                        "availability_factor": 0.85,
                    },
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                        "stock": 1000,
                    },
                ],
                "scenarios": [
                    {
                        "type": "demand_projection",
                        "commodity": "RSD",
                        "values": {"2020": 10, "2030": 15, "2050": 20},  # Max 20 PJ
                    }
                ],
            }
        }

        rule = H004_StockCoversAllDemand()
        issues = rule.apply(model)

        assert len(issues) == 1
        assert issues[0].code == "H004"
        assert issues[0].severity == "warning"
        assert "RSD" in issues[0].message
        assert "brownfield" in issues[0].message.lower()

    def test_no_issue_when_demand_exceeds_stock(self):
        """Should not warn when demand exceeds available stock capacity."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 0.55,
                        "stock": 1,  # 1 GW -> ~14.8 PJ/yr
                        "availability_factor": 0.85,
                    },
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                        "stock": 1000,
                    },
                ],
                "scenarios": [
                    {
                        "type": "demand_projection",
                        "commodity": "RSD",
                        "values": {"2020": 10, "2050": 100},  # Max 100 PJ >> 14.8 PJ
                    }
                ],
            }
        }

        rule = H004_StockCoversAllDemand()
        issues = rule.apply(model)

        assert len(issues) == 0

    def test_no_issue_when_no_stock(self):
        """Should not warn when processes have no stock (greenfield model)."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 0.55,
                        # No stock
                    },
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                        "stock": 1000,
                    },
                ],
                "scenarios": [
                    {
                        "type": "demand_projection",
                        "commodity": "RSD",
                        "values": {"2020": 10, "2050": 20},
                    }
                ],
            }
        }

        rule = H004_StockCoversAllDemand()
        issues = rule.apply(model)

        assert len(issues) == 0

    def test_no_issue_when_no_demand_projections(self):
        """Should not warn when there are no demand projections."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                ],
                "processes": [
                    {
                        "name": "PP_CCGT",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 0.55,
                        "stock": 100,
                    },
                ],
                "scenarios": [],
            }
        }

        rule = H004_StockCoversAllDemand()
        issues = rule.apply(model)

        assert len(issues) == 0


class TestRunHeuristics:
    """Tests for the run_heuristics function."""

    def test_runs_all_rules(self):
        """Should run all registered rules."""
        model = {
            "model": {
                "start_year": 2020,
                "time_periods": [10, 10, 10],
                "commodities": [
                    {"name": "ELC", "type": "energy"},
                    {"name": "RSD", "type": "demand"},
                ],
                "processes": [
                    {
                        "name": "PP_SOLAR",
                        "outputs": [{"commodity": "ELC"}],
                        "efficiency": 1.0,
                        "life": 25,
                        "ncap_bound": {"fx": 1.0},
                    },
                    {
                        "name": "DMD_RSD",
                        "inputs": [{"commodity": "ELC"}],
                        "outputs": [{"commodity": "RSD"}],
                        "efficiency": 1.0,
                    },
                ],
                "scenarios": [],
            }
        }

        issues = run_heuristics(model)

        codes = {i.code for i in issues}
        assert "H001" in codes  # Short life
        assert "H002" in codes  # No stock on demand device

    def test_handles_rule_exceptions(self):
        """Should catch and report rule failures without crashing."""
        issues = run_heuristics({})

        assert all(i.severity == "warning" for i in issues if "_ERROR" in i.code)
