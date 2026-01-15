"""Segments and commodity semantics helpers for VedaLang IR.

This module provides utilities for:
- Building segment keys from model segments configuration
- Mapping VedaLang commodity kinds to TIMES COM_TYPE
- Scoping non-tradable commodities (services) by segment
- Normalizing commodity definitions to canonical form
"""

from dataclasses import dataclass


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
    """Map VedaLang commodity kind to TIMES COM_TYPE.

    TIMES COM_TYPE from maplists.def: { DEM, NRG, MAT, ENV, FIN }

    Args:
        kind: VedaLang commodity kind (service, carrier, material, emission)

    Returns:
        TIMES COM_TYPE code (DEM, NRG, MAT, ENV)
    """
    mapping = {
        # New VedaLang naming (lowercase)
        "service": "DEM",
        "carrier": "NRG",
        "material": "MAT",
        "emission": "ENV",
        # Legacy mappings (for backward compatibility)
        "SERVICE": "DEM",
        "TRADABLE": "NRG",
        "EMISSION": "ENV",
        # Deprecated names
        "energy": "NRG",
        "demand": "DEM",
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

    Handles backward compatibility for old field names:
    - 'name' → 'id'
    - 'TRADABLE' → 'carrier', 'SERVICE' → 'service', 'EMISSION' → 'emission'

    Infers default tradable based on kind:
    - carrier, material → tradable=True
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

    # Normalize kind (legacy → new naming)
    kind = raw.get("kind", "carrier")
    kind_map = {
        "TRADABLE": "carrier",
        "SERVICE": "service",
        "EMISSION": "emission",
        # Already normalized forms pass through
        "carrier": "carrier",
        "service": "service",
        "material": "material",
        "emission": "emission",
        # Deprecated
        "energy": "carrier",
        "demand": "service",
    }
    kind = kind_map.get(kind, kind)

    # Default tradable based on kind
    tradable = raw.get("tradable")
    if tradable is None:
        tradable = kind in ("carrier", "material")

    return {
        "id": comm_id,
        "kind": kind,
        "tradable": tradable,
        "unit": raw.get("unit", "PJ"),
        "com_type": commodity_kind_to_com_type(kind),
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
