# VedaLang Heuristic Checks

VedaLang includes a **heuristics linter** that catches common modeling mistakes *before* expensive compilation and solving. These are pre-solve checks based on static analysis of your VedaLang source.

## Running Heuristic Checks

```bash
# Run heuristics as part of full validation
uv run vedalang validate model.veda.yaml

# Run heuristics via the design pipeline
uv run vedalang-dev pipeline model.veda.yaml --no-solver --json
```

The heuristics step runs automatically before compilation and reports warnings/errors.

---

## Available Heuristic Checks

### H001: Fixed New Capacity with Short Lifetime

**Severity:** Warning (escalates to Error with growing demand)

**Pattern detected:** Process has `ncap_bound.fx` (fixed new capacity) or tight `ncap_bound.up`, combined with a `life` shorter than the model horizon.

**Why it matters:** When a process's lifetime is shorter than the model horizon, capacity retires mid-horizon and needs replacement. With fixed/constrained new capacity, the model cannot add replacement capacity, leading to capacity shortfalls and potential infeasibility.

**Example:**
```yaml
processes:
  - name: PP_SOLAR
    ncap_bound:
      fx: 1  # Fixed new capacity
    life: 25  # Retires before end of 30-year horizon
```

**Fix:** Either extend the lifetime, remove the fixed bound, or ensure sufficient capacity is available from other sources.

---

### H002: Demand Device Without Stock

**Severity:** Error

**Pattern detected:** A demand device (process that outputs a demand commodity) has no `stock` or initial capacity specified.

**Why it matters:** Demand devices convert energy commodities (like `secondary:electricity`) into demand services (like `service:residential_demand`). Without capacity, they cannot operate, and the model becomes infeasible in the base year.

**Example (problematic):**
```yaml
processes:
  - name: DMD_RSD
    sets: [DMD]
    inputs:
      - commodity: secondary:electricity
    outputs:
      - commodity: service:residential_demand  # Service commodity
    # Missing: stock
```

**Fix:** Add `stock` with sufficient capacity:
```yaml
    stock: 100  # GW of demand device capacity
```

---

### H003: Base Year Capacity Inadequacy

**Severity:** Warning or Error (depending on coverage ratio)

**Pattern detected:** The base year demand exceeds the estimated supply capacity from existing stock.

**Why it matters:** In the base year (typically historical/current), there should be enough existing capacity to produce the required demand. Insufficient stock causes immediate infeasibility.

**Calculation:**
- Traces the supply chain: generator stock → energy commodity → demand device → demand service
- Estimates: `supply = stock × efficiency × availability_factor × 31.536 PJ/GW/year`

**Example:**
```yaml
processes:
  - name: PP_SIMPLE
    stock: 1  # Only 1 GW
scenario_parameters:
  - type: demand_projection
    commodity: service:residential_demand
    values:
      "2020": 500  # Needs ~500 PJ but only ~27 PJ available
```

**Fix:** Increase generator stock or reduce base year demand.

---

### H004: Stock Covers All Demand

**Severity:** Warning

**Pattern detected:** Existing stock capacity can cover 95%+ of maximum projected demand throughout the model horizon.

**Why it matters:** When stock covers all demand, the model may solve with zero investment and zero objective value. This is often unintentional and may indicate:
- Stock values too high relative to demand
- Demand projections too low
- Brownfield analysis needs confirmation

**Example:**
```yaml
processes:
  - name: PP_SIMPLE
    stock: 100  # 100 GW × 31.536 × 0.85 ≈ 2680 PJ/yr
scenario_parameters:
  - type: demand_projection
    commodity: service:residential_demand
    values:
      "2020": 50  # Only 50 PJ/yr needed
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
model:
  milestone_years: [2020, 2030, 2040, 2050]
  
  processes:
  - name: PP_CCGT
    stock: 10  # Enough for base demand
    invcost: 800  # Investment available for growth
    
  - name: DMD_RSD
    inputs:
      - commodity: secondary:electricity
    outputs:
      - commodity: service:residential_demand
    stock: 100  # Large capacity to avoid bottleneck
    
scenario_parameters:
  - type: demand_projection
    commodity: service:residential_demand
    values:
      "2020": 50   # Can be met by stock
      "2030": 100  # Forces new investment
      "2050": 200  # Significant growth
```

### Forcing Investment Decisions

```yaml
processes:
  - name: PP_CCGT
    stock: 2   # Low initial stock
    invcost: 800
    cap_bound:
      up: 50  # Allow new capacity
      
  - name: PP_WIND
    stock: 1  # Very low
    invcost: 1200
    # No cap_bound = unlimited new capacity
```
