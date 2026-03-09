# VedaLang Modeling Conventions

This guide describes the active **v0.2** modeling contract.

<!-- GENERATED:canonical-enums:start -->
- `stage` = one of `supply | conversion | distribution | storage | end_use | sink`
- `commodity.type` = one of `fuel | energy | service | material | emission | money | other`
- `commodity namespace prefix` = one of `primary | resource | secondary | service | material | emission | money`
<!-- GENERATED:canonical-enums:end -->

## Core Objects

- `commodities` define the ledger vocabulary.
- `technologies` define concrete physical pathways.
- `technology_roles` group substitutable technologies around one service intent.
- `facilities` place named site-bound stock.
- `fleets` place distributed or generic stock boundaries.
- `opportunities` represent place-bound greenfield/new-build classes.
- `networks` represent inter-regional transfer infrastructure.
- `runs` define the model region partition and reporting currency year.

## Naming

- Use service-oriented `technology_role` IDs such as `space_heat_supply` or
  `mobility_service`.
- Use technology IDs that describe whole pathways, not bolt-on measures:
  `gas_boiler`, `heat_pump`, `traditional_with_feed_additives`.
- Keep IDs stable and technology-neutral where the object is meant to represent
  a service contract rather than a pathway.

## Commodities

- `primary:*` is for primary combustible or extractive fuels.
- `secondary:*` is for secondary carriers like electricity or hydrogen.
- `service:*` is for end-use service demand.
- `emission:*` is for ledger emissions only.
- `material:*` is for physical material flows.

`emission:*` commodities do not belong in `inputs` or `outputs`; emit them only
through `technologies[*].emissions`.

## Technologies and Roles

- Prefer one service-oriented `technology_role` with multiple technologies over
  multiple fuel-specific roles.
- Put pathway-specific physical inputs on the technology.
- Set `technology_roles[*].primary_service` to the `service:*` or carrier that
  role ultimately delivers.
- Use `technology_roles[*].transitions` for explicit retrofit/changeover logic.

Example:

```yaml
commodities:
  - id: primary:natural_gas
    kind: primary
  - id: secondary:electricity
    kind: secondary
  - id: service:space_heat
    kind: service

technologies:
  - id: gas_boiler
    provides: service:space_heat
    inputs:
      - commodity: primary:natural_gas
        basis: HHV
    performance:
      kind: efficiency
      value: 0.9
  - id: heat_pump
    provides: service:space_heat
    inputs:
      - commodity: secondary:electricity
    performance:
      kind: cop
      value: 3.0

technology_roles:
  - id: space_heat_supply
    primary_service: service:space_heat
    technologies: [gas_boiler, heat_pump]
```

## Spatial Deployment

- Put exact point/polygon placement on `sites`.
- Use `facilities` for named site-bound assets whose site identity matters.
- Use `fleets` for distributed stock and for toy-scale generic sector stock.
- For toy models, prefer `fleets[*].distribution.method: direct` so authors do
  not need spatial weights or site geometry just to instantiate stock.
- Use `membership_overrides` only when the site-to-region mapping would be
  ambiguous otherwise.
- Use `opportunities` only for place-bound build classes: site, zone, or region
  specific greenfield/resource opportunities.
- Do not use `opportunities` for generic “technology exists in the role but has
  zero stock” cases.

## Stocks and Costs

- Existing stock belongs under `facilities[*].stock.items` or `fleets[*].stock.items`.
- Technology-specific capped buildout on an instantiated asset boundary belongs
  under `facilities[*].new_build_limits` or `fleets[*].new_build_limits`.
- Costs belong on `technologies` as explicit literals, for example
  `220 AUD2024/kW` or `25 AUD2024/MWh`.
- Heating-value basis must be explicit on combustible flow sites.
- Do not rely on implicit interpolation; prefer explicit year-indexed values.

## Relationship Guide

| Intent | Preferred object |
|---|---|
| Existing stock at a named place | `facility.stock` |
| Existing generic/distributed stock | `fleet.stock` |
| Generic alternative technology with no current stock | `technology_roles[*].technologies` |
| Retrofit or upgrade of existing stock | `technology_roles[*].transitions` |
| Technology-specific new-build cap on an instantiated asset boundary | `facility.new_build_limits` or `fleet.new_build_limits` |
| Place-bound greenfield/resource/build class | `opportunity` |

Valid `opportunity` examples:

- REZ-specific wind class
- Region-specific mine expansion step
- Site-specific greenfield project with distinct place identity

Non-`opportunity` examples:

- Generic heat pump rollout in a single-region residential fleet
- EV uptake in a generic passenger fleet
- Retrofit of an existing facility already represented in role transitions

## Diagnostics Expectations

- A technology role that delivers end-use service must still have physical
  inputs somewhere in its technologies unless it is a true supply or sink role.
- Facilities and opportunities are place-based objects; fleets are the default
  authoring surface for toy models and generic distributed sectors.
- Commodity kind should align with topology:
  `primary` for fuels, `secondary` for carriers, `service` for demands,
  `emission` for ledger outputs.
- Multi-run sources should be explicit about which run a tool is operating on.

## Checklist

- [ ] `dsl_version: "0.2"` is present.
- [ ] Technology roles are service-oriented, not fuel-pathway-oriented.
- [ ] Technology names describe whole pathways.
- [ ] Combustible flows carry explicit `basis`.
- [ ] Existing stock is placed through `facilities` or `fleets`.
- [ ] Generic toy-model stock uses fleets with `distribution.method: direct`.
- [ ] Capped buildout on existing assets uses `new_build_limits`.
- [ ] `opportunities` are reserved for place-bound build classes.
- [ ] Networks are modeled with `networks`, not fake technologies.
- [ ] Runs are present and identify the intended region partition.
