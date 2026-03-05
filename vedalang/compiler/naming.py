"""Deterministic symbol generation for TIMES entities.

This module provides the NamingRegistry class for stable, reproducible symbol
names across compilation runs. All TIMES symbols are generated through the
registry to ensure determinism.

Per FR12 and FR17: VedaLang user-facing IDs are not TIMES symbols. The
compiler generates deterministic TIMES/VEDA symbols using this registry.
"""

import re

PROCESS_SYMBOL_PATTERN = re.compile(
    r"^(FAC|FLT)::([^:]+)::ROLE::([^:]+)::VAR::([^:]+)::MODE::([^:]+)$"
)


def _sanitize_token(raw: str) -> str:
    """Sanitize token for stable, xl2times-safe process symbols."""
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", str(raw).strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "x"


def parse_process_symbol(symbol: str) -> dict[str, str] | None:
    """Parse canonical provider-aware process symbol to structured fields."""
    match = PROCESS_SYMBOL_PATTERN.fullmatch(symbol or "")
    if not match:
        return None
    provider_kind, provider_id, role_id, variant_id, mode_id = match.groups()
    return {
        "provider_kind": provider_kind,
        "provider_id": provider_id,
        "role_id": role_id,
        "variant_id": variant_id,
        "mode_id": mode_id,
    }


ProcessKey = tuple[
    str,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]


class NamingRegistry:
    """Deterministic symbol generation for TIMES entities.

    Ensures stable, reproducible symbol names across compilation runs.
    Symbols are cached after first generation to guarantee stability.
    """

    def __init__(self) -> None:
        self._commodities: dict[tuple[str, str | None], str] = {}
        self._processes: dict[ProcessKey, str] = {}

    def get_commodity_symbol(
        self, commodity_id: str, segment: str | None = None
    ) -> str:
        """Get or create TIMES symbol for commodity.

        Tradable commodities use their base id. Non-tradable commodities
        with segments are scoped using @ separator.

        Args:
            commodity_id: Base commodity id (e.g., "lighting")
            segment: Segment key (e.g., "RES", "RES.lighting") or None

        Returns:
            TIMES symbol:
            - "electricity" for tradables (no segment)
            - "lighting@RES" for scoped non-tradables

        Examples:
            >>> reg = NamingRegistry()
            >>> reg.get_commodity_symbol("electricity", None)
            'electricity'
            >>> reg.get_commodity_symbol("lighting", "RES")
            'lighting@RES'
        """
        key = (commodity_id, segment)
        if key not in self._commodities:
            if segment:
                self._commodities[key] = f"{commodity_id}@{segment}"
            else:
                self._commodities[key] = commodity_id
        return self._commodities[key]

    def get_process_symbol(
        self,
        variant_id: str,
        region: str,
        segment: str | None = None,
        *,
        provider_kind: str | None = None,
        provider_id: str | None = None,
        role_id: str | None = None,
        mode_id: str | None = None,
    ) -> str:
        """Get or create TIMES symbol for process.

        Generates deterministic process names from variant, region, and
        optional segment. Dots in segments are replaced with underscores.

        Args:
            variant_id: Variant id (e.g., "led_lighting")
            region: Region code (e.g., "SINGLE", "R1")
            segment: Segment key (e.g., "RES", "RES.lighting") or None

        Returns:
            TIMES process symbol:
            - "led_lighting_SINGLE_RES" with segment
            - "simple_generator_SINGLE" without segment

        Examples:
            >>> reg = NamingRegistry()
            >>> reg.get_process_symbol("led_lighting", "SINGLE", "RES")
            'led_lighting_SINGLE_RES'
            >>> reg.get_process_symbol("generator", "R1", None)
            'generator_R1'
            >>> reg.get_process_symbol("led", "R1", "RES.lighting")
            'led_R1_RES_lighting'
        """
        key = (
            variant_id,
            region,
            segment,
            provider_kind,
            provider_id,
            role_id,
            mode_id,
        )
        if key not in self._processes:
            if provider_kind and provider_id and role_id and mode_id:
                kind_token = "FAC" if provider_kind.lower() == "facility" else "FLT"
                provider_token = _sanitize_token(provider_id)
                role_token = _sanitize_token(role_id)
                variant_token = _sanitize_token(variant_id)
                mode_token = _sanitize_token(mode_id)
                self._processes[key] = (
                    f"{kind_token}::{provider_token}::ROLE::{role_token}"
                    f"::VAR::{variant_token}::MODE::{mode_token}"
                )
            else:
                parts = [variant_id, region]
                if segment:
                    parts.append(segment.replace(".", "_"))
                self._processes[key] = "_".join(parts)
        return self._processes[key]

    def get_all_commodities(self) -> dict[tuple[str, str | None], str]:
        """Return all registered commodity symbols (for testing/debugging)."""
        return dict(self._commodities)

    def get_all_processes(self) -> dict[tuple, str]:
        """Return registered process symbols.

        For legacy symbols this returns 3-tuples `(variant, region, segment)`.
        Provider-aware symbols return extended tuple keys.
        """
        result: dict[tuple, str] = {}
        for key, value in self._processes.items():
            (
                variant_id,
                region,
                segment,
                provider_kind,
                provider_id,
                role_id,
                mode_id,
            ) = key
            if (
                provider_kind is None
                and provider_id is None
                and role_id is None
                and mode_id is None
            ):
                result[(variant_id, region, segment)] = value
            else:
                result[key] = value
        return result

    def clear(self) -> None:
        """Clear all registered symbols (mainly for testing)."""
        self._commodities.clear()
        self._processes.clear()
