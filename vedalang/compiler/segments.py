"""Segments and commodity semantics helpers for VedaLang IR.

This module provides utilities for:
- Building segment keys from model segments configuration
- Mapping VedaLang commodity kinds to TIMES COM_TYPE
- Scoping non-tradable commodities (services) by segment
- Normalizing commodity definitions to canonical form
"""

from dataclasses import dataclass

from vedalang.conventions import commodity_namespace_enum

NAMESPACE_TO_TYPES = {
    "energy": {"fuel", "energy"},
    "fuel": {"fuel"},
    "resource": {"other", "energy"},
    "material": {"material"},
    "service": {"service"},
    "emission": {"emission"},
    "money": {"money"},
}
VALID_COMMODITY_NAMESPACES = set(commodity_namespace_enum())


def build_segments(model: dict) -> list[str]:
    """Build segment keys from model segments config.

    Segments provide demand-side context for service commodities and end-use
    processes. The granularity depends on configuration:
    - No segments: [] (flat model)
    - Coarse: ["RES", "COM"] (sectors only)
    - Fine: ["RES.lighting", "RES.heating", "COM.lighting", ...] (sector.end_use)

    Args:
        model: Model dict (may have 'segments' key at top level or nested)

    Returns:
        List of segment keys:
        - [] if no segments defined
        - ["RES", "COM"] for coarse (sectors only)
        - ["RES.lighting", "RES.heating", ...] for fine (sector.end_use)
    """
    seg_cfg = model.get("segments") or {}
    sectors = seg_cfg.get("sectors", [])
    end_uses = seg_cfg.get("end_uses")

    if not sectors:
        return []
    if not end_uses:
        return list(sectors)
    return [f"{s}.{eu}" for s in sectors for eu in end_uses]


def commodity_kind_to_com_type(kind: str) -> str:
    """Map VedaLang commodity type/kind to TIMES COM_TYPE.

    TIMES COM_TYPE from maplists.def: { DEM, NRG, MAT, ENV, FIN }

    Args:
        kind: VedaLang commodity type or normalized kind

    Returns:
        TIMES COM_TYPE code (DEM, NRG, MAT, ENV)
    """
    mapping = {
        # Canonical commodity types
        "fuel": "NRG",
        "energy": "NRG",
        "service": "DEM",
        "material": "MAT",
        "emission": "ENV",
        "money": "FIN",
        "other": "NRG",
        # Canonicalized internal kinds
        "carrier": "NRG",
    }
    return mapping.get(kind, "NRG")  # default to NRG


@dataclass
class ScopedCommodity:
    """A commodity with optional segment scope.

    Non-tradable commodities (especially services) need segment-scoped TIMES
    symbols to ensure each segment's demand is met by segment-specific supply.

    Attributes:
        id: User-facing commodity id (e.g., "lighting")
        segment: Segment key (e.g., "RES") or None for tradables
        kind: Commodity kind (service, carrier, material, emission)
        tradable: Whether commodity can flow between segments
        times_symbol: TIMES symbol (e.g., "lighting@RES" or just "lighting")
    """

    id: str
    segment: str | None
    kind: str
    tradable: bool
    times_symbol: str


def get_scoped_commodity_id(
    base_id: str,
    segment_key: str | None,
    tradable: bool,
    kind: str,
) -> str:
    """Get the TIMES symbol for a commodity, scoped by segment if non-tradable.

    Tradable commodities (carriers, materials) use their base id since they
    can flow between segments. Non-tradable commodities (services) are scoped
    to ensure segment-specific supply-demand balance.

    Args:
        base_id: Base commodity id (e.g., "lighting")
        segment_key: Segment key (e.g., "RES", "RES.lighting") or None
        tradable: Whether the commodity is tradable between segments
        kind: Commodity kind

    Returns:
        TIMES symbol:
        - "lighting" for tradables
        - "lighting@RES" for non-tradable with segment
        - "lighting" for non-tradable without segment (flat model)
    """
    if tradable or kind in ("carrier", "material"):
        return base_id
    if segment_key:
        return f"{base_id}@{segment_key}"
    return base_id


def normalize_commodity(raw: dict) -> dict:
    """Normalize commodity dict to canonical form.

    Commodity `type` is the canonical field.

    Infers default tradable based on type:
    - fuel, energy, material, other → tradable=True
    - service, emission → tradable=False

    Args:
        raw: Raw commodity definition from VedaLang source

    Returns:
        Normalized commodity dict with fields:
        - id: Canonical commodity id
        - kind: Normalized kind (service, carrier, material, emission)
        - tradable: Boolean tradability
        - unit: Unit string (default "PJ")
        - com_type: TIMES COM_TYPE code
    """
    # id takes precedence over name
    comm_id = raw.get("id") or raw.get("name")
    if not comm_id:
        raise ValueError("Commodity must have 'id' or 'name' field")
    comm_id = comm_id.lower()

    # Normalize canonical commodity type -> internal kind used for scoping
    raw_type = raw.get("type")
    type_to_kind = {
        "fuel": "carrier",
        "energy": "carrier",
        "service": "service",
        "material": "material",
        "emission": "emission",
        "money": "money",
        "other": "carrier",
    }

    if raw_type is None:
        raise ValueError("Commodity must define 'type'")

    if raw_type not in type_to_kind:
        raise ValueError(f"Commodity '{comm_id}' has unsupported type '{raw_type}'")

    namespace = None
    base_name = comm_id
    if ":" in comm_id:
        namespace, _, base_name = comm_id.partition(":")
        if namespace not in VALID_COMMODITY_NAMESPACES:
            raise ValueError(
                f"Commodity '{comm_id}' has unsupported namespace '{namespace}'"
            )
        expected_types = NAMESPACE_TO_TYPES.get(namespace)
        if expected_types is None:
            raise ValueError(
                f"Commodity '{comm_id}' namespace '{namespace}' has no type mapping"
            )
        if raw_type not in expected_types:
            raise ValueError(
                "Commodity namespace/type mismatch for "
                f"'{comm_id}': namespace '{namespace}' implies type in "
                f"{sorted(expected_types)} but got type '{raw_type}'"
            )
        if not base_name:
            raise ValueError(f"Commodity '{comm_id}' must include a name after ':'")

    kind = type_to_kind[raw_type]

    # Default tradable based on canonical type
    tradable = raw.get("tradable")
    if tradable is None:
        tradable = raw_type in ("fuel", "energy", "material", "money", "other")

    return {
        "id": comm_id,
        "kind": kind,
        "type": raw_type,
        "tradable": tradable,
        "unit": raw.get("unit", "PJ"),
        "com_type": commodity_kind_to_com_type(raw_type),
    }


def build_scoped_commodity_registry(
    commodities: list[dict],
    segment_keys: list[str],
) -> dict[str, list[ScopedCommodity]]:
    """Build a registry of scoped commodities.

    For each commodity, creates ScopedCommodity entries:
    - Tradable commodities get a single entry (no segment scope)
    - Non-tradable commodities get one entry per segment

    Args:
        commodities: List of raw commodity definitions
        segment_keys: List of segment keys from build_segments()

    Returns:
        Dict mapping base commodity id to list of ScopedCommodity entries
    """
    registry: dict[str, list[ScopedCommodity]] = {}

    for raw in commodities:
        norm = normalize_commodity(raw)
        comm_id = norm["id"]
        kind = norm["kind"]
        tradable = norm["tradable"]

        entries = []
        if tradable or not segment_keys:
            # Single unscoped entry
            entries.append(
                ScopedCommodity(
                    id=comm_id,
                    segment=None,
                    kind=kind,
                    tradable=tradable,
                    times_symbol=comm_id,
                )
            )
        else:
            # One entry per segment
            for seg in segment_keys:
                times_symbol = get_scoped_commodity_id(comm_id, seg, tradable, kind)
                entries.append(
                    ScopedCommodity(
                        id=comm_id,
                        segment=seg,
                        kind=kind,
                        tradable=tradable,
                        times_symbol=times_symbol,
                    )
                )

        registry[comm_id] = entries

    return registry
