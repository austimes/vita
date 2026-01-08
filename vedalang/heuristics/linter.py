"""VedaLang heuristics linter.

Pre-solve checks that catch common modeling mistakes before expensive
compilation and solving. These are advisory warnings/errors based on
static analysis of the VedaLang AST.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LintIssue:
    """A heuristic lint issue found in a VedaLang model."""

    code: str
    severity: str  # "warning" | "error"
    message: str
    location: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "context": self.context,
        }


class HeuristicRule(ABC):
    """Base class for heuristic rules."""

    code: str
    description: str
    default_severity: str = "warning"

    @abstractmethod
    def apply(self, model: dict) -> list[LintIssue]:
        """Apply this rule to a VedaLang model and return issues found."""
        raise NotImplementedError


class H001_FixedNewCapShortLife(HeuristicRule):
    """Detect fixed/tight new capacity bounds with lifetimes shorter than horizon.

    Pattern that often causes infeasibility:
    - Process has ncap_bound.fx (fixed new capacity) or very tight ncap_bound.up
    - Process has finite lifetime shorter than model horizon
    - No new capacity can be added after retirement -> capacity goes to zero
    - Growing demand cannot be met -> infeasible

    Example from minisystem.veda.yaml:
    - PP_SOLAR: ncap_bound.fx = 1, life = 25
    - Horizon: 2020 + 30 = 2050 (30 years)
    - In later periods, PP_SOLAR capacity retires and cannot be replaced
    """

    code = "H001"
    description = "Fixed new capacity with lifetime shorter than model horizon"
    default_severity = "warning"

    def apply(self, model: dict) -> list[LintIssue]:
        issues = []

        # Calculate horizon length
        model_data = model.get("model", {})
        start_year = model_data.get("start_year", 2020)
        time_periods = model_data.get("time_periods", [])
        if isinstance(time_periods, list):
            horizon_years = sum(time_periods)
        else:
            horizon_years = 30  # Default assumption

        horizon_end = start_year + horizon_years

        # Check for demand growth (escalates severity if present)
        has_demand_growth = self._has_demand_growth(model_data)

        # Build set of commodities with growing demand
        growing_demand_commodities = self._get_growing_demand_commodities(model_data)

        # Build map of which processes feed which demand commodities
        process_feeds_demand = self._build_process_demand_map(model_data)

        for proc in model_data.get("processes", []):
            proc_name = proc.get("name", "unknown")
            life = proc.get("life")
            ncap_bound = proc.get("ncap_bound", {})

            if life is None:
                continue

            # Check for fixed or tight new capacity bounds
            ncap_fx = ncap_bound.get("fx")
            ncap_up = ncap_bound.get("up")

            has_fixed = ncap_fx is not None
            has_tight_upper = ncap_up is not None and ncap_up <= 2.0  # Configurable

            if not (has_fixed or has_tight_upper):
                continue

            # Check if lifetime is shorter than horizon
            if life >= horizon_years:
                continue

            # Determine severity based on demand growth connection
            severity = self.default_severity
            feeds_growing_demand = any(
                c in growing_demand_commodities
                for c in process_feeds_demand.get(proc_name, set())
            )
            if has_demand_growth and feeds_growing_demand:
                severity = "error"

            # Build the issue
            bound_type = "fx" if has_fixed else "up"
            bound_value = ncap_fx if has_fixed else ncap_up

            msg = (
                f"Process {proc_name} has {'fixed' if has_fixed else 'tight'} "
                f"new capacity (ncap_bound.{bound_type} = {bound_value}) "
                f"and lifetime {life}y, which is shorter than the {horizon_years}y "
                f"model horizon ({start_year}-{horizon_end}). "
                f"No additional capacity can be added after retirement; "
                f"this can cause infeasibility"
            )

            if feeds_growing_demand:
                msg += ", especially with growing demand on connected commodities"
            msg += "."

            issues.append(
                LintIssue(
                    code=self.code,
                    severity=severity,
                    message=msg,
                    location=f"processes[{proc_name}].ncap_bound.{bound_type}",
                    context={
                        "process": proc_name,
                        "life": life,
                        "horizon_years": horizon_years,
                        "ncap_bound": ncap_bound,
                        "feeds_growing_demand": feeds_growing_demand,
                    },
                )
            )

        return issues

    def _has_demand_growth(self, model: dict) -> bool:
        """Check if model has any demand projections that grow over time."""
        scenarios = model.get("scenarios", [])
        for scen in scenarios:
            if scen.get("type") == "demand_projection":
                values = scen.get("values", {})
                if len(values) >= 2:
                    sorted_vals = [v for _, v in sorted(values.items())]
                    if sorted_vals[-1] > sorted_vals[0]:
                        return True
        return False

    def _get_growing_demand_commodities(self, model: dict) -> set[str]:
        """Get set of demand commodity names with growing projections."""
        growing = set()
        scenarios = model.get("scenarios", [])
        for scen in scenarios:
            if scen.get("type") == "demand_projection":
                values = scen.get("values", {})
                if len(values) >= 2:
                    sorted_vals = [v for _, v in sorted(values.items())]
                    if sorted_vals[-1] > sorted_vals[0]:
                        comm = scen.get("commodity")
                        if comm:
                            growing.add(comm)
        return growing

    def _build_process_demand_map(self, model: dict) -> dict[str, set[str]]:
        """Build map of process -> set of demand commodities it can feed.

        This uses a simple graph traversal:
        1. Find demand devices (processes that output demand commodities)
        2. Trace back through energy commodity links to find generators
        """
        # Build commodity type map
        commodity_types = {}
        for comm in model.get("commodities", []):
            commodity_types[comm.get("name")] = comm.get("type")

        # Build process -> outputs and process -> inputs maps
        proc_outputs: dict[str, set[str]] = {}
        proc_inputs: dict[str, set[str]] = {}

        for proc in model.get("processes", []):
            name = proc.get("name")
            outputs = {o.get("commodity") for o in proc.get("outputs", [])}
            inputs = {i.get("commodity") for i in proc.get("inputs", [])}
            proc_outputs[name] = outputs
            proc_inputs[name] = inputs

        # Find which demand commodities each process can ultimately feed
        # by following the energy flow: generator -> energy -> demand_device -> demand
        process_feeds_demand: dict[str, set[str]] = {p: set() for p in proc_outputs}

        # First, mark demand devices
        demand_devices = {}  # demand_device_name -> demand commodities
        for proc in model.get("processes", []):
            name = proc.get("name")
            for out in proc.get("outputs", []):
                comm = out.get("commodity")
                if commodity_types.get(comm) == "demand":
                    if name not in demand_devices:
                        demand_devices[name] = set()
                    demand_devices[name].add(comm)

        # For each demand device, find what energy commodities it consumes
        # Then find processes that output those energy commodities
        for dd_name, demand_comms in demand_devices.items():
            # What does this demand device consume?
            input_comms = proc_inputs.get(dd_name, set())
            energy_inputs = {
                c for c in input_comms if commodity_types.get(c) == "energy"
            }

            # Find processes that output these energy commodities
            for proc_name, outputs in proc_outputs.items():
                if outputs & energy_inputs:
                    # This process feeds energy to this demand device
                    process_feeds_demand[proc_name].update(demand_comms)

        return process_feeds_demand


class H002_DemandDeviceNoStock(HeuristicRule):
    """Detect demand devices without stock or initial capacity.

    Demand devices (processes that output demand commodities) typically need
    stock/capacity to function in the base year. Without it:
    - No capacity exists to convert energy to demand service
    - Model becomes infeasible in base year

    This is a common modeling oversight - demand devices are often assumed
    to "just work" but TIMES requires explicit capacity.
    """

    code = "H002"
    description = "Demand device without stock/initial capacity"
    default_severity = "error"  # Usually causes immediate infeasibility

    def apply(self, model: dict) -> list[LintIssue]:
        issues = []
        model_data = model.get("model", {})

        # Build commodity type map
        commodity_types = {}
        for comm in model_data.get("commodities", []):
            commodity_types[comm.get("name")] = comm.get("type")

        # Check each process
        for proc in model_data.get("processes", []):
            proc_name = proc.get("name", "unknown")

            # Is this a demand device? (outputs a demand commodity)
            is_demand_device = False
            demand_outputs = []
            for out in proc.get("outputs", []):
                comm = out.get("commodity")
                if commodity_types.get(comm) == "demand":
                    is_demand_device = True
                    demand_outputs.append(comm)

            if not is_demand_device:
                continue

            # Check for stock or initial capacity
            has_stock = proc.get("stock") is not None
            has_ncap_pasti = proc.get("ncap_pasti") is not None  # Future support

            if has_stock or has_ncap_pasti:
                continue

            # Demand device without stock - this is problematic
            issues.append(
                LintIssue(
                    code=self.code,
                    severity=self.default_severity,
                    message=(
                        f"Demand device {proc_name} has no stock/initial capacity. "
                        f"It outputs demand commodities {demand_outputs} but cannot "
                        f"convert energy to demand service without capacity. "
                        f"Add 'stock: <value>' to specify pre-existing capacity."
                    ),
                    location=f"processes[{proc_name}]",
                    context={
                        "process": proc_name,
                        "demand_outputs": demand_outputs,
                        "suggestion": "Add stock attribute with sufficient capacity",
                    },
                )
            )

        return issues


class H004_StockCoversAllDemand(HeuristicRule):
    """Detect when existing stock can cover all demand throughout the model horizon.

    When PRC_RESID (stock) capacity is large enough to meet all projected demand
    without requiring new investment, the model may solve with zero objective value.
    This is often unintentional and indicates:
    - Stock values are too high relative to demand
    - Demand projections are too low
    - Brownfield analysis needs explicit confirmation

    This is a warning since brownfield analyses may intentionally have this pattern.
    """

    code = "H004"
    description = "Existing stock covers all demand throughout horizon"
    default_severity = "warning"

    # PJ per GW-year at 100% capacity factor
    PJ_PER_GW_YEAR = 31.536

    def apply(self, model: dict) -> list[LintIssue]:
        issues = []
        model_data = model.get("model", {})

        # Build commodity type map
        commodity_types = {}
        for comm in model_data.get("commodities", []):
            commodity_types[comm.get("name")] = comm.get("type")

        # Get max demand per demand commodity across all years
        max_demands = self._get_max_demands(model_data)
        if not max_demands:
            return issues

        # Calculate total stock capacity that can supply each demand commodity
        stock_capacity = self._calculate_stock_capacity(model_data, commodity_types)

        # Check if stock covers all demand for any demand commodity
        for demand_comm, max_demand in max_demands.items():
            available_stock = stock_capacity.get(demand_comm, 0)

            # If stock can cover >95% of max demand, that's suspicious
            if max_demand > 0 and available_stock >= max_demand * 0.95:
                coverage_ratio = available_stock / max_demand

                issues.append(
                    LintIssue(
                        code=self.code,
                        severity=self.default_severity,
                        message=(
                            f"Existing stock capacity ({available_stock:.1f} PJ/yr) "
                            f"can cover all projected demand for {demand_comm} "
                            f"({max_demand:.1f} PJ/yr max). "
                            f"Model may solve with zero investment and zero objective "
                            f"value. Consider: (1) Reduce stock values to force "
                            f"investment decisions, (2) Increase demand projections "
                            f"to stress the system, or (3) Confirm this is intentional "
                            f"for brownfield analysis."
                        ),
                        location=f"commodities[{demand_comm}]",
                        context={
                            "demand_commodity": demand_comm,
                            "max_demand": max_demand,
                            "available_stock_capacity": available_stock,
                            "coverage_ratio": coverage_ratio,
                        },
                    )
                )

        return issues

    def _get_max_demands(self, model: dict) -> dict[str, float]:
        """Get maximum demand value for each demand commodity across all years."""
        max_demands: dict[str, float] = {}

        # Check both 'scenario_parameters' and legacy 'scenarios'
        scenario_params = (
            model.get("scenario_parameters", []) or model.get("scenarios", [])
        )

        for scen in scenario_params:
            if scen.get("type") != "demand_projection":
                continue

            commodity = scen.get("commodity")
            values = scen.get("values", {})

            if not commodity or not values:
                continue

            max_val = max(values.values())
            if commodity in max_demands:
                max_demands[commodity] = max(max_demands[commodity], max_val)
            else:
                max_demands[commodity] = max_val

        return max_demands

    def _calculate_stock_capacity(
        self, model: dict, commodity_types: dict
    ) -> dict[str, float]:
        """Calculate stock capacity that can supply each demand commodity.

        Traces: generator stock -> energy commodity -> demand device -> demand commodity
        """
        supply: dict[str, float] = {}

        # Build energy generation capacity from stock
        energy_stock_capacity: dict[str, float] = {}
        for proc in model.get("processes", []):
            stock = proc.get("stock", 0)
            if stock <= 0:
                continue

            eff = self._get_scalar_efficiency(proc)
            af = proc.get("availability_factor", 0.85)

            for out in proc.get("outputs", []):
                comm = out.get("commodity")
                if commodity_types.get(comm) == "energy":
                    capacity = stock * eff * af * self.PJ_PER_GW_YEAR
                    energy_stock_capacity[comm] = (
                        energy_stock_capacity.get(comm, 0) + capacity
                    )

        # Trace through demand devices to demand commodities
        for proc in model.get("processes", []):
            for out in proc.get("outputs", []):
                demand_comm = out.get("commodity")
                if commodity_types.get(demand_comm) != "demand":
                    continue

                # Find energy inputs to this demand device
                device_eff = self._get_scalar_efficiency(proc)
                device_stock = proc.get("stock", 0)

                for inp in proc.get("inputs", []):
                    energy_comm = inp.get("commodity")
                    if commodity_types.get(energy_comm) != "energy":
                        continue

                    # Energy available from generators
                    gen_capacity = energy_stock_capacity.get(energy_comm, 0)

                    # If device has stock, it limits throughput
                    if device_stock > 0:
                        device_capacity = (
                            device_stock * device_eff * self.PJ_PER_GW_YEAR
                        )
                        effective = min(gen_capacity, device_capacity)
                    else:
                        effective = gen_capacity * device_eff

                    supply[demand_comm] = supply.get(demand_comm, 0) + effective

        return supply

    def _get_scalar_efficiency(self, proc: dict) -> float:
        """Get efficiency as scalar (handles time-varying case)."""
        eff = proc.get("efficiency", 1.0)
        if isinstance(eff, dict):
            values = eff.get("values", {})
            if values:
                return list(values.values())[0]
            return 1.0
        return eff


class H003_BaseYearCapacityAdequacy(HeuristicRule):
    """Check if base year has sufficient capacity to meet demand.

    For the base year (typically historical/current), there should be enough
    existing capacity (stock) to produce the required demand. This catches:
    - Missing stock on generators
    - Stock values too small for the demand level
    - Unit conversion issues (e.g., stock in GW but demand in PJ)

    Uses simplified capacity-to-activity conversion:
    - 1 GW at 100% CF = 31.536 PJ/year (8760 hours * 3600 seconds/hour / 1e6)
    - Actual available activity = capacity * efficiency * availability_factor
    """

    code = "H003"
    description = "Base year capacity inadequate for demand"
    default_severity = "warning"

    # Approximate hours per year for capacity factor conversion
    HOURS_PER_YEAR = 8760
    # PJ per GW-year at 100% capacity factor
    PJ_PER_GW_YEAR = 31.536

    def apply(self, model: dict) -> list[LintIssue]:
        issues = []
        model_data = model.get("model", {})
        start_year = model_data.get("start_year", 2020)

        # Build commodity type map
        commodity_types = {}
        for comm in model_data.get("commodities", []):
            commodity_types[comm.get("name")] = comm.get("type")

        # Get base year demand values
        base_year_demands = self._get_base_year_demands(model_data, start_year)
        if not base_year_demands:
            return issues  # No demands to check

        # Build supply chain: which processes can supply which demand commodities
        # and estimate their base year capacity
        supply_capacity = self._estimate_supply_capacity(model_data, commodity_types)

        # For each demand commodity, check if supply is adequate
        for demand_comm, demand_value in base_year_demands.items():
            available = supply_capacity.get(demand_comm, 0)

            if available < demand_value * 0.5:  # Less than 50% coverage is problematic
                severity = "error" if available < demand_value * 0.1 else "warning"

                issues.append(
                    LintIssue(
                        code=self.code,
                        severity=severity,
                        message=(
                            f"Base year ({start_year}) capacity may be inadequate for "
                            f"demand commodity {demand_comm}. "
                            f"Estimated available supply: {available:.1f} PJ, "
                            f"required demand: {demand_value:.1f} PJ. "
                            f"Check that generators have sufficient 'stock' values "
                            f"and that demand devices have capacity."
                        ),
                        location=f"commodities[{demand_comm}]",
                        context={
                            "demand_commodity": demand_comm,
                            "demand_value": demand_value,
                            "available_supply": available,
                            "base_year": start_year,
                            "coverage_ratio": (
                                available / demand_value if demand_value > 0 else 0
                            ),
                        },
                    )
                )

        return issues

    def _get_base_year_demands(self, model: dict, start_year: int) -> dict[str, float]:
        """Extract base year demand values from demand projections."""
        demands = {}

        # Check both 'scenario_parameters' and legacy 'scenarios'
        scenario_params = (
            model.get("scenario_parameters", []) or model.get("scenarios", [])
        )

        for scen in scenario_params:
            if scen.get("type") != "demand_projection":
                continue

            commodity = scen.get("commodity")
            values = scen.get("values", {})

            # Find the value for start_year (or closest earlier year)
            base_value = None
            for year_str, val in sorted(values.items()):
                year = int(year_str)
                if year <= start_year:
                    base_value = val
                elif base_value is None:
                    # First value is after start year, use it anyway
                    base_value = val
                    break

            if base_value is not None and commodity:
                demands[commodity] = base_value

        return demands

    def _estimate_supply_capacity(
        self, model: dict, commodity_types: dict
    ) -> dict[str, float]:
        """Estimate base year supply capacity for each demand commodity.

        Traces the supply chain: generator stock -> energy -> demand device -> demand
        """
        supply = {}

        # Find demand devices and their connections
        for proc in model.get("processes", []):

            # Check if this outputs a demand commodity
            for out in proc.get("outputs", []):
                comm = out.get("commodity")
                if commodity_types.get(comm) != "demand":
                    continue

                # This is a demand device - estimate its capacity
                device_stock = proc.get("stock", 0)
                device_eff = self._get_scalar_efficiency(proc)

                # Device can produce: stock * efficiency * CF * PJ_PER_GW_YEAR
                # Assume demand devices have high CF (they pass through)
                device_capacity = device_stock * device_eff * self.PJ_PER_GW_YEAR

                # Also check what energy inputs this device needs
                # and if there's enough generation capacity
                for inp in proc.get("inputs", []):
                    inp_comm = inp.get("commodity")
                    if commodity_types.get(inp_comm) != "energy":
                        continue

                    # Find generators that output this energy commodity
                    gen_capacity = self._estimate_energy_generation(
                        model, inp_comm, commodity_types
                    )

                    # Supply is limited by min of device capacity and generation
                    if device_stock > 0:
                        effective_supply = min(device_capacity, gen_capacity)
                    else:
                        effective_supply = gen_capacity

                    if comm in supply:
                        supply[comm] += effective_supply
                    else:
                        supply[comm] = effective_supply

        return supply

    def _estimate_energy_generation(
        self, model: dict, energy_comm: str, commodity_types: dict
    ) -> float:
        """Estimate base year generation capacity for an energy commodity."""
        total = 0

        for proc in model.get("processes", []):
            # Check if this process outputs the energy commodity
            outputs_energy = False
            for out in proc.get("outputs", []):
                if out.get("commodity") == energy_comm:
                    outputs_energy = True
                    break

            if not outputs_energy:
                continue

            # Estimate generation capacity
            stock = proc.get("stock", 0)
            eff = self._get_scalar_efficiency(proc)
            af = proc.get("availability_factor", 0.85)  # Default assumption

            # Generation = stock * efficiency * availability * PJ_PER_GW_YEAR
            gen = stock * eff * af * self.PJ_PER_GW_YEAR
            total += gen

        return total

    def _get_scalar_efficiency(self, proc: dict) -> float:
        """Get efficiency as scalar (handles time-varying case)."""
        eff = proc.get("efficiency", 1.0)
        if isinstance(eff, dict):
            # Time-varying - get first value
            values = eff.get("values", {})
            if values:
                return list(values.values())[0]
            return 1.0
        return eff


# Registry of all heuristic rules
ALL_RULES: list[HeuristicRule] = [
    H001_FixedNewCapShortLife(),
    H002_DemandDeviceNoStock(),
    H003_BaseYearCapacityAdequacy(),
    H004_StockCoversAllDemand(),
]


@dataclass
class HeuristicsResult:
    """Result of running all heuristic checks."""

    issues: list[LintIssue]
    checks_run: list[dict[str, str]]  # [{code, description}, ...]
    error_count: int
    warning_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "issues": [i.to_dict() for i in self.issues],
            "checks_run": self.checks_run,
            "summary": {
                "total_checks": len(self.checks_run),
                "error_count": self.error_count,
                "warning_count": self.warning_count,
                "issue_count": len(self.issues),
            },
        }


def get_available_checks() -> list[dict[str, str]]:
    """Get list of all available heuristic checks.

    Returns:
        List of {code, description} dicts for all registered rules.
    """
    return [
        {"code": rule.code, "description": rule.description}
        for rule in ALL_RULES
    ]


def run_heuristics(model: dict) -> list[LintIssue]:
    """Run all heuristic rules on a VedaLang model.

    Args:
        model: Parsed VedaLang model dict (from load_vedalang)

    Returns:
        List of LintIssue objects found by all rules
    """
    issues = []
    for rule in ALL_RULES:
        try:
            rule_issues = rule.apply(model)
            issues.extend(rule_issues)
        except Exception as e:
            # Don't let a buggy rule crash the linter
            issues.append(
                LintIssue(
                    code=f"{rule.code}_ERROR",
                    severity="warning",
                    message=f"Heuristic rule {rule.code} failed: {e}",
                    location=None,
                    context={"exception": str(e)},
                )
            )
    return issues


def run_heuristics_detailed(model: dict) -> HeuristicsResult:
    """Run all heuristic rules and return detailed results.

    This is the preferred API for tools that want to show:
    - What checks were run (even if they passed)
    - Counts of errors vs warnings
    - Full issue details

    Args:
        model: Parsed VedaLang model dict (from load_vedalang)

    Returns:
        HeuristicsResult with issues and metadata
    """
    issues = run_heuristics(model)
    checks_run = get_available_checks()

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")

    return HeuristicsResult(
        issues=issues,
        checks_run=checks_run,
        error_count=error_count,
        warning_count=warning_count,
    )
