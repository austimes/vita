# VedaLang Heuristic Checks

VedaLang includes a **heuristics linter** that catches common modeling mistakes *before* expensive compilation and solving. These are pre-solve checks based on static analysis of your VedaLang source.

## Running Heuristic Checks

```bash
# Run only feasibility heuristics via deterministic lint
uv run vedalang lint model.veda.yaml --category feasibility

# Run all deterministic categories (including feasibility)
uv run vedalang lint model.veda.yaml

# Run heuristics as part of full validation
uv run vedalang validate model.veda.yaml

# Run heuristics via the design pipeline
uv run vedalang-dev pipeline model.veda.yaml --no-solver --json
```

The heuristics step runs in deterministic lint and is surfaced in `validate`
as part of the end-to-end pipeline.

---

## Available Heuristic Checks

### H001: Fixed New Capacity with Short Lifetime

**Severity:** Warning (escalates to Error with growing demand)

**Pattern detected:** A v0.2 technology/deployment path has a fixed or tightly
bounded new-capacity allowance together with a short `lifetime`.

**Why it matters:** When a process's lifetime is shorter than the model horizon, capacity retires mid-horizon and needs replacement. With fixed/constrained new capacity, the model cannot add replacement capacity, leading to capacity shortfalls and potential infeasibility.

**Example:**
```yaml
technologies:
  - id: solar_pv
    provides: service:electricity_supply
    lifetime: 25 year
facilities:
  - id: reg1_solar
    site: reg1_hub
    technology_role: electricity_supply
    stock:
      items:
        - technology: solar_pv
          metric: installed_capacity
          observed:
            value: 1 GW
            year: 2025
          ncap_bound:
            fx: 1 GW
```

**Fix:** Either extend the lifetime, remove the fixed bound, or ensure sufficient capacity is available from other sources.

---

### H002: Demand Device Without Stock

**Severity:** Error

**Pattern detected:** A service-delivering facility has no `stock` or initial
capacity specified.

**Why it matters:** Demand devices convert energy commodities (like `secondary:electricity`) into demand services (like `service:residential_demand`). Without capacity, they cannot operate, and the model becomes infeasible in the base year.

**Example (problematic):**
```yaml
technologies:
  - id: residential_device
    provides: service:residential_demand
    inputs:
      - commodity: secondary:electricity
facilities:
  - id: reg1_residential_device
    site: reg1_hub
    technology_role: residential_demand
    # Missing: stock
```

**Fix:** Add `stock` with sufficient capacity:
```yaml
    stock:
      items:
        - technology: residential_device
          metric: installed_capacity
          observed:
            value: 100 GW
            year: 2025
```

---

### H003: Base Year Capacity Inadequacy

**Severity:** Warning or Error (depending on coverage ratio)

**Pattern detected:** The base year service requirement exceeds the estimated
supply capacity from existing stock.

**Why it matters:** In the base year (typically historical/current), there should be enough existing capacity to produce the required demand. Insufficient stock causes immediate infeasibility.

**Calculation:**
- Traces the supply chain: generator stock → energy commodity → demand device → demand service
- Estimates: `supply = stock × efficiency × availability_factor × 31.536 PJ/GW/year`

**Example:**
```yaml
technologies:
  - id: simple_supply
    provides: service:residential_demand
    lifetime: 30 year
facilities:
  - id: reg1_supply
    site: reg1_hub
    technology_role: residential_demand
    stock:
      items:
        - technology: simple_supply
          metric: installed_capacity
          observed:
            value: 1 GW
            year: 2020
temporal_index_series:
  - id: residential_demand_index
    unit: index
    base_year: 2020
    values:
      "2020": 1.0
      "2030": 10.0
```

**Fix:** Increase generator stock or reduce base year demand.

---

### H004: Stock Covers All Demand

**Severity:** Warning

**Pattern detected:** Existing stock capacity can cover 95%+ of maximum
projected demand throughout the model horizon.

**Why it matters:** When stock covers all demand, the model may solve with zero investment and zero objective value. This is often unintentional and may indicate:
- Stock values too high relative to demand
- Demand projections too low
- Brownfield analysis needs confirmation

**Example:**
```yaml
technologies:
  - id: simple_supply
    provides: service:residential_demand
    lifetime: 30 year
facilities:
  - id: reg1_supply
    site: reg1_hub
    technology_role: residential_demand
    stock:
      items:
        - technology: simple_supply
          metric: installed_capacity
          observed:
            value: 100 GW
            year: 2020
temporal_index_series:
  - id: residential_demand_index
    unit: index
    base_year: 2020
    values:
      "2020": 1.0
      "2030": 1.1
```

**Guidance:**
1. **Force investment:** Reduce stock values to stress the system
2. **Increase demand:** Make demand projections grow over time
3. **Confirm intent:** If brownfield analysis is intentional, the warning can be ignored

---

## Interpreting Heuristic Output

The heuristics output includes:

| Field | Description |
|-------|-------------|
| `code` | Heuristic identifier (e.g., H001, H002) |
| `severity` | `warning` or `error` |
| `message` | Human-readable description |
| `location` | Path to the problematic element in VedaLang |
| `context` | Additional data for debugging |

Example JSON output:
```json
{
  "code": "H004",
  "severity": "warning",
  "message": "Existing stock capacity (2680.6 PJ/yr) can cover all projected demand for RSD (50.0 PJ/yr max)...",
  "location": "commodities[RSD]",
  "context": {
    "demand_commodity": "RSD",
    "max_demand": 50,
    "available_stock_capacity": 2680.56,
    "coverage_ratio": 53.6112
  }
}
```

---

## Adding New Heuristics

Heuristics are implemented in `vedalang/heuristics/linter.py`. Each rule:
1. Extends `HeuristicRule` base class
2. Implements `apply(model) -> list[LintIssue]`
3. Is registered in `ALL_RULES`

To propose a new heuristic:
1. Create a `bd` issue describing the pattern and why it causes problems
2. Implement the rule in `linter.py`
3. Add tests in `tests/test_heuristics.py`

---

## Common Modeling Patterns

### Ensuring Feasible Base Year

```yaml
dsl_version: "0.2"
commodities:
  - id: secondary:electricity
    kind: secondary
  - id: service:residential_demand
    kind: service
technologies:
  - id: ccgt
    provides: service:residential_demand
    inputs:
      - commodity: secondary:electricity
    investment_cost: 800 AUD2024/kW
    lifetime: 30 year
technology_roles:
  - id: residential_demand
    primary_service: service:residential_demand
    technologies: [ccgt]
facilities:
  - id: reg1_demand
    site: reg1_hub
    technology_role: residential_demand
    stock:
      items:
        - technology: ccgt
          metric: installed_capacity
          observed:
            value: 10 GW
            year: 2020
temporal_index_series:
  - id: residential_demand_index
    unit: index
    base_year: 2020
    values:
      "2020": 1.0
      "2030": 2.0
      "2050": 4.0
runs:
  - id: reg1_2020
    base_year: 2020
    currency_year: 2024
    region_partition: reg1_partition
```

### Forcing Investment Decisions

```yaml
technologies:
  - id: ccgt
    provides: service:electricity_supply
    investment_cost: 800 AUD2024/kW
    cap_bound:
      up: 50 GW
  - id: wind
    provides: service:electricity_supply
    investment_cost: 1200 AUD2024/kW
facilities:
  - id: reg1_ccgt
    site: reg1_hub
    technology_role: electricity_supply
    stock:
      items:
        - technology: ccgt
          metric: installed_capacity
          observed:
            value: 2 GW
            year: 2025
  - id: reg1_wind
    site: reg1_hub
    technology_role: electricity_supply
    stock:
      items:
        - technology: wind
          metric: installed_capacity
          observed:
            value: 1 GW
            year: 2025
```
