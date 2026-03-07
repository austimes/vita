# VedaLang Modeling Conventions

This guide describes the active **v0.2** modeling contract. Older
`model/roles/variants/providers` examples are archive material only and should
not be used for new authoring.

<!-- GENERATED:canonical-enums:start -->
- `stage` = one of `supply | conversion | distribution | storage | end_use | sink`
- `commodity.type` = one of `fuel | energy | service | material | emission | money | other`
- `commodity namespace prefix` = one of `primary | resource | secondary | service | material | emission | money`
<!-- GENERATED:canonical-enums:end -->

## Core Objects

- `commodities` define the ledger vocabulary.
- `technologies` define concrete physical pathways.
- `technology_roles` group substitutable technologies around one service intent.
- `sites`, `facilities`, and `fleets` place existing stock in space.
- `opportunities` represent new-build options.
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
- Use `facilities` for named site-bound assets.
- Use `fleets` for distributed stock allocated across a run’s model regions.
- Use `membership_overrides` only when the site-to-region mapping would be
  ambiguous otherwise.
- Use `opportunities` for optional future build rather than encoding “latent”
  technologies as fake existing stock.

## Stocks and Costs

- Existing stock belongs under `facilities[*].stock.items` or `fleets[*].stock.items`.
- Costs belong on `technologies` as explicit literals, for example
  `220 AUD2024/kW` or `25 AUD2024/MWh`.
- Heating-value basis must be explicit on combustible flow sites.
- Do not rely on implicit interpolation; prefer explicit year-indexed values.

## Diagnostics Expectations

- A technology role that delivers end-use service must still have physical
  inputs somewhere in its technologies unless it is a true supply or sink role.
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
- [ ] Optional future build is represented with `opportunities`.
- [ ] Networks are modeled with `networks`, not fake technologies.
- [ ] Runs are present and identify the intended region partition.
