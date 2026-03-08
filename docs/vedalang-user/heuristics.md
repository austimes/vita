# VedaLang Heuristic Checks

VedaLang's deterministic heuristics run on the active v0.2 public DSL before
compilation and solver work. They focus on stock-coverage gaps that are cheap
to detect from the authored source.

## Running Heuristic Checks

```bash
# Run only feasibility heuristics
uv run vedalang lint model.veda.yaml --category feasibility

# Run all deterministic lint categories
uv run vedalang lint model.veda.yaml

# Run heuristics as part of full validation
uv run vedalang validate model.veda.yaml
```

## Available Heuristic Checks

### H001: Service Asset Without Stock

**Severity:** Warning

**Pattern detected:** A `facility` or `fleet` uses a `technology_role` whose
`primary_service` is a `service:*` commodity, but the asset has no
`stock.items`.

**Why it matters:** Service-delivering assets usually need explicit base-year
stock observations to anchor installed service capacity or activity. A service
asset without stock is often an incomplete v0.2 model fragment.

**Example:**

```yaml
commodities:
  - id: service:space_heat
    kind: service

technology_roles:
  - id: space_heat_supply
    primary_service: service:space_heat
    technologies: [heat_pump]

facilities:
  - id: home_heat
    site: home
    technology_role: space_heat_supply
```

**Fix:** Add `stock.items` for the existing base-year asset, or remove the
asset until it is ready to be modeled.

### H002: Annual-Activity Stock Without Matching Installed Capacity

**Severity:** Warning

**Pattern detected:** A service asset records `annual_activity` stock for a
service, but no asset in that same service family records
`installed_capacity`.

**Why it matters:** `annual_activity` observations without any companion
installed-capacity stock often indicate an incomplete base-year stock picture.
That weakens brownfield anchoring and usually means the service is only
partially modeled.

**Example:**

```yaml
facilities:
  - id: district_heat
    site: reg1_hub
    technology_role: space_heat_supply
    stock:
      items:
        - technology: heat_pump
          metric: annual_activity
          observed:
            value: 12 PJ
            year: 2025
```

**Fix:** Confirm the service is intentionally activity-only, or add matching
`installed_capacity` stock for the same service.

## Output Shape

Heuristic diagnostics include:

- `code`: heuristic identifier such as `H001`
- `severity`: `warning` or `error`
- `message`: human-readable explanation
- `location`: approximate source path
- `context`: structured detail for debugging or downstream tooling

Example JSON diagnostic:

```json
{
  "code": "H001",
  "severity": "warning",
  "message": "Facility 'home_heat' uses service role 'space_heat_supply' but has no stock observations.",
  "location": "facilities[0].stock",
  "context": {
    "asset": "home_heat",
    "technology_role": "space_heat_supply",
    "section": "facilities"
  }
}
```
