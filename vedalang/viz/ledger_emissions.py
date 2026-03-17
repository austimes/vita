"""Shared helpers for ledger-emission visualization metadata."""

from __future__ import annotations

from typing import Any

from vedalang.compiler.resolution import parse_quantity

KNOWN_GASES = {
    "co2": {"code": "CO2", "color_key": "co2"},
    "carbondioxide": {"code": "CO2", "color_key": "co2"},
    "ch4": {"code": "CH4", "color_key": "ch4"},
    "methane": {"code": "CH4", "color_key": "ch4"},
    "n2o": {"code": "N2O", "color_key": "n2o"},
    "nitrousoxide": {"code": "N2O", "color_key": "n2o"},
}
GAS_ORDER = {"CO2": 0, "CH4": 1, "N2O": 2}


def empty_ledger_emissions() -> dict[str, Any]:
    return {
        "present": False,
        "state": "none",
        "coverage": "none",
        "gases": [],
    }


def emission_palette() -> dict[str, str]:
    return {
        "co2": "#ef4444",
        "ch4": "#f97316",
        "n2o": "#38bdf8",
        "other": "#c084fc",
    }


def ledger_state_from_value(value: Any) -> str | None:
    amount = _coerce_amount(value)
    if amount is None or amount == 0:
        return None
    return "emit" if amount > 0 else "remove"


def summarize_ledger_emissions(
    entries: list[dict[str, Any]],
    *,
    member_ids: list[str],
) -> dict[str, Any]:
    if not entries:
        return empty_ledger_emissions()

    by_gas: dict[str, dict[str, Any]] = {}
    emitting_members: set[str] = set()
    saw_emit = False
    saw_remove = False

    for entry in entries:
        commodity_id = str(entry.get("commodity_id", "") or "")
        state = str(entry.get("state", "") or "")
        member_id = str(entry.get("member_id", "") or "")
        if not commodity_id or state not in {"emit", "remove"}:
            continue

        gas = by_gas.setdefault(
            commodity_id,
            {
                **classify_ledger_gas(commodity_id),
                "commodity_id": commodity_id,
                "states": set(),
                "member_ids": set(),
            },
        )
        gas["states"].add(state)
        if member_id:
            gas["member_ids"].add(member_id)
            emitting_members.add(member_id)
        if state == "emit":
            saw_emit = True
        else:
            saw_remove = True

    if not by_gas:
        return empty_ledger_emissions()

    if saw_emit and saw_remove:
        overall_state = "mixed"
    elif saw_emit:
        overall_state = "emit"
    else:
        overall_state = "remove"

    relevant_members = [member_id for member_id in member_ids if member_id]
    if not relevant_members:
        coverage = "all_members"
    else:
        coverage = (
            "all_members"
            if len(emitting_members) == len(set(relevant_members))
            else "some_members"
        )

    gases = []
    for commodity_id, gas in sorted(
        by_gas.items(),
        key=lambda item: gas_sort_key(item[0], item[1]["code"]),
    ):
        del commodity_id
        states = gas["states"]
        gas_state = "mixed" if len(states) > 1 else next(iter(states))
        gases.append(
            {
                "commodity_id": gas["commodity_id"],
                "code": gas["code"],
                "known": gas["known"],
                "color_key": gas["color_key"],
                "state": gas_state,
                "member_process_ids": sorted(gas["member_ids"]),
            }
        )

    return {
        "present": True,
        "state": overall_state,
        "coverage": coverage,
        "gases": gases,
    }


def mermaid_emission_suffix(ledger_emissions: dict[str, Any] | None) -> str:
    if not isinstance(ledger_emissions, dict) or not ledger_emissions.get("present"):
        return ""
    tokens = []
    for gas in ledger_emissions.get("gases", []) or []:
        code = str(gas.get("code", "") or "")
        state = str(gas.get("state", "") or "")
        if not code:
            continue
        if state == "remove":
            tokens.append(f"-{code}")
        elif state == "mixed":
            tokens.append(f"{code}±")
        else:
            tokens.append(code)
    return "/".join(tokens)


def classify_ledger_gas(commodity_id: str) -> dict[str, Any]:
    normalized = _normalize_gas_key(commodity_id)
    known = KNOWN_GASES.get(normalized)
    if known is not None:
        return {
            "code": known["code"],
            "color_key": known["color_key"],
            "known": True,
        }
    return {
        "code": _fallback_gas_code(commodity_id),
        "color_key": "other",
        "known": False,
    }


def gas_sort_key(commodity_id: str, code: str) -> tuple[int, str, str]:
    rank = GAS_ORDER.get(code, len(GAS_ORDER))
    return (rank, code if rank < len(GAS_ORDER) else commodity_id.lower(), commodity_id)


def _normalize_gas_key(commodity_id: str) -> str:
    return "".join(ch for ch in commodity_id.lower() if ch.isalnum())


def _fallback_gas_code(commodity_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in commodity_id.upper())
    return cleaned.strip("_") or "OTHER"


def _coerce_amount(value: Any) -> float | None:
    if isinstance(value, dict):
        amount = value.get("amount")
        if amount is None:
            return None
        return float(amount)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return parse_quantity(value).value
        except Exception:  # noqa: BLE001 — fall back to plain float parse
            try:
                return float(value)
            except ValueError:
                return None
    return None
