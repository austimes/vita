"""Demands lowering for VedaLang compiler.

This module compiles VedaLang demand blocks into scenario parameters that
can be emitted as TableIR (and ultimately VEDA Excel).

Per FR7: Demands are specified against service commodities (kind=service)
and scopes. Demands are declared independently of which variants exist;
feasibility is validated by the linter.
"""

from .naming import NamingRegistry
from .segments import get_scoped_commodity_id


class DemandError(Exception):
    """Error during demand compilation."""

    pass


def compile_demands(
    model: dict,
    commodities: dict[str, dict],
    scope_keys: list[str],
    registry: NamingRegistry | None = None,
) -> list[dict]:
    """Convert demands block to scenario parameters format.

    For each demand:
    1. Resolve commodity (must be service kind)
    2. Determine scope key from sector/scope fields
    3. Get scoped commodity ID (lighting@RES)
    4. Create scenario parameter with type=demand_projection

    Args:
        model: Model dict (may have 'demands' key at top level)
        commodities: Dict mapping commodity id to normalized commodity dict
        scope_keys: List of scope keys from build_scopes()
        registry: Optional NamingRegistry for symbol generation

    Returns:
        List of scenario parameter dicts compatible with existing TableIR emission.

    Raises:
        DemandError: If commodity is unknown or not a service commodity.
    """
    demands = model.get("demands") or []
    if not demands:
        return []

    result = []
    for d in demands:
        commodity = d["commodity"]
        comm_info = commodities.get(commodity)

        if not comm_info:
            raise DemandError(f"Unknown commodity in demand: {commodity}")

        kind = comm_info.get("kind", "carrier")
        if kind != "service":
            raise DemandError(
                f"Demands must reference service commodities, "
                f"got {commodity} (kind={kind})"
            )

        region = d["region"]
        scope_key = d.get("scope") or d.get("sector")

        tradable = comm_info.get("tradable", False)
        scoped_id = get_scoped_commodity_id(commodity, scope_key, tradable, kind)

        if registry:
            scoped_id = registry.get_commodity_symbol(commodity, scope_key)

        name_parts = ["demand", commodity, region]
        if scope_key:
            name_parts.append(scope_key.replace(".", "_"))
        else:
            name_parts.append("ALL")
        param_name = "_".join(name_parts)

        param: dict = {
            "name": param_name,
            "type": "demand_projection",
            "commodity": scoped_id,
            "region": region,
            "values": d["values"],
            "interpolation": d.get("interpolation", "interp_extrap"),
        }

        if scope_key:
            param["scope"] = scope_key

        result.append(param)

    return result
