"""Parsing and validation logic for VedaLang naming grammar.

Validates commodity and process IDs according to naming conventions.
"""

import re
from dataclasses import dataclass

VALID_ROLES = {"GEN", "EUS", "CNV", "EXT", "TRD", "STO", "CAP", "SEQ"}

COMMODITY_PREFIXES = {
    "TRADABLE": "C",
    "SERVICE": "S",
    "EMISSION": "E",
}


@dataclass
class CommodityIDValidation:
    valid: bool
    kind: str | None
    code: str
    context: str | None
    error: str | None


@dataclass
class ParsedProcessID:
    technology: str
    role: str
    geo: str
    segment: str | None = None
    variant: str | None = None
    vintage: str | None = None


@dataclass
class ProcessIDValidation:
    valid: bool
    parsed: ParsedProcessID | None
    error: str | None


def validate_commodity_id(
    name: str, kind: str, context: str | None = None
) -> CommodityIDValidation:
    """Validate a commodity ID matches its kind.

    Patterns:
    - TRADABLE: C:{CODE} (e.g., C:ELC, C:GAS)
    - SERVICE: S:{CODE}:{SECTOR}.{SEGMENT}[.{SUBSEGMENT}] (e.g., S:RSD:RES.ALL)
    - EMISSION: E:{CODE} (e.g., E:CO2)

    Args:
        name: The commodity ID to validate
        kind: Expected kind (TRADABLE, SERVICE, EMISSION)
        context: For SERVICE, the expected context (e.g., RES.ALL)

    Returns:
        CommodityIDValidation with validation result
    """
    if kind not in COMMODITY_PREFIXES:
        return CommodityIDValidation(
            valid=False,
            kind=None,
            code="",
            context=None,
            error=(
                f"Unknown commodity kind: {kind}."
                f" Must be one of: {list(COMMODITY_PREFIXES.keys())}"
            ),
        )

    expected_prefix = COMMODITY_PREFIXES[kind]
    parts = name.split(":")

    if len(parts) < 2:
        return CommodityIDValidation(
            valid=False,
            kind=kind,
            code="",
            context=None,
            error=(
                f"Invalid commodity ID format: {name}."
                f" Expected {expected_prefix}:CODE"
            ),
        )

    actual_prefix = parts[0]
    if actual_prefix != expected_prefix:
        return CommodityIDValidation(
            valid=False,
            kind=kind,
            code="",
            context=None,
            error=(
                f"Wrong prefix for {kind} commodity:"
                f" got '{actual_prefix}',"
                f" expected '{expected_prefix}'"
            ),
        )

    if kind == "SERVICE":
        if len(parts) != 3:
            return CommodityIDValidation(
                valid=False,
                kind=kind,
                code=parts[1] if len(parts) > 1 else "",
                context=None,
                error=(
                    f"SERVICE commodity requires format"
                    f" S:CODE:SECTOR.SEGMENT, got: {name}"
                ),
            )

        code = parts[1]
        ctx = parts[2]

        if not re.match(r"^[A-Z]+\.[A-Z0-9_]+(\.[A-Z0-9_]+)?$", ctx):
            return CommodityIDValidation(
                valid=False,
                kind=kind,
                code=code,
                context=ctx,
                error=(
                    f"Invalid SERVICE context format: {ctx}."
                    f" Expected SECTOR.SEGMENT[.SUBSEGMENT]"
                ),
            )

        if context is not None and ctx != context:
            return CommodityIDValidation(
                valid=False,
                kind=kind,
                code=code,
                context=ctx,
                error=f"Context mismatch: got '{ctx}', expected '{context}'",
            )

        return CommodityIDValidation(
            valid=True,
            kind=kind,
            code=code,
            context=ctx,
            error=None,
        )

    if kind in ("TRADABLE", "EMISSION"):
        if len(parts) != 2:
            return CommodityIDValidation(
                valid=False,
                kind=kind,
                code="",
                context=None,
                error=(
                    f"{kind} commodity requires format"
                    f" {expected_prefix}:CODE, got: {name}"
                ),
            )

        code = parts[1]
        if not re.match(r"^[A-Z0-9]+$", code):
            return CommodityIDValidation(
                valid=False,
                kind=kind,
                code=code,
                context=None,
                error=(
                    f"Invalid {kind} code format: {code}."
                    f" Must be uppercase alphanumeric"
                ),
            )

        return CommodityIDValidation(
            valid=True,
            kind=kind,
            code=code,
            context=None,
            error=None,
        )

    return CommodityIDValidation(
        valid=False,
        kind=kind,
        code="",
        context=None,
        error=f"Unhandled commodity kind: {kind}",
    )


def parse_process_id(process_id: str) -> ProcessIDValidation:
    """Parse a process ID following the grammar.

    Grammar: P:{TECH}:{ROLE}:{GEO}[:{SEGMENT}][:{VARIANT}][:{VINTAGE}]

    Examples:
    - P:CCG:GEN:NEM_EAST
    - P:DEM:EUS:NEM_EAST:RES.ALL
    - P:PCC:CAP:NSW.NCC:CCS90

    Args:
        process_id: The process ID string to parse

    Returns:
        ProcessIDValidation with parsed components or error
    """
    parts = process_id.split(":")

    if len(parts) < 4:
        return ProcessIDValidation(
            valid=False,
            parsed=None,
            error=(
                f"Process ID must have at least 4 parts"
                f" (P:TECH:ROLE:GEO), got: {process_id}"
            ),
        )

    prefix = parts[0]
    if prefix != "P":
        return ProcessIDValidation(
            valid=False,
            parsed=None,
            error=f"Process ID must start with 'P:', got prefix '{prefix}'",
        )

    tech = parts[1]
    role = parts[2]
    geo = parts[3]

    if role not in VALID_ROLES:
        return ProcessIDValidation(
            valid=False,
            parsed=None,
            error=f"Unknown role: {role}. Must be one of: {sorted(VALID_ROLES)}",
        )

    segment: str | None = None
    variant: str | None = None
    vintage: str | None = None

    remaining = parts[4:]

    if role == "EUS":
        if not remaining:
            return ProcessIDValidation(
                valid=False,
                parsed=None,
                error=f"Role EUS requires a segment (e.g., RES.ALL), got: {process_id}",
            )
        segment = remaining[0]
        remaining = remaining[1:]

    for part in remaining:
        if part in ("EXIST", "NEW"):
            vintage = part
        elif "." in part and segment is None:
            segment = part
        else:
            if variant is None:
                variant = part
            elif vintage is None:
                vintage = part

    parsed = ParsedProcessID(
        technology=tech,
        role=role,
        geo=geo,
        segment=segment,
        variant=variant,
        vintage=vintage,
    )

    return ProcessIDValidation(valid=True, parsed=parsed, error=None)


def generate_process_id(
    technology: str,
    role: str,
    geo: str,
    segment: str | None = None,
    variant: str | None = None,
    vintage: str | None = None,
) -> str:
    """Generate a process ID from components.

    Args:
        technology: Technology code (e.g., CCG, PV, WND)
        role: Role code (e.g., GEN, EUS, CNV)
        geo: Geographic region (e.g., NEM_EAST, NSW.NCC)
        segment: Demand segment, required if role=EUS (e.g., RES.ALL)
        variant: Technology variant (e.g., CCS90)
        vintage: Vintage marker (e.g., EXIST, NEW)

    Returns:
        Process ID string: P:{TECH}:{ROLE}:{GEO}[:{SEGMENT}][:{VARIANT}][:{VINTAGE}]

    Raises:
        ValueError: If role is invalid or EUS without segment
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {role}. Must be one of: {sorted(VALID_ROLES)}")

    if role == "EUS" and segment is None:
        raise ValueError("Role EUS requires a segment")

    parts = ["P", technology, role, geo]

    if segment is not None:
        parts.append(segment)
    if variant is not None:
        parts.append(variant)
    if vintage is not None:
        parts.append(vintage)

    return ":".join(parts)
