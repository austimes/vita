"""PCG (Primary Commodity Group) diagnostic tool.

Compares explicit vs inferred PCG for migration help.
xl2times infers PCG using priority DEM > MAT > NRG > ENV > FIN,
checking OUTPUT side first then INPUT.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

# PCG priority order (highest to lowest)
PCG_PRIORITY = ["DEM", "MAT", "NRG", "ENV", "FIN"]


@dataclass
class PCGResult:
    """Result of PCG inference for a process."""

    process: str
    inferred: str | None
    explicit: str | None
    match: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "process": self.process,
            "inferred": self.inferred,
            "explicit": self.explicit,
            "match": self.match,
            "reason": self.reason,
        }


@dataclass
class PCGCheckResult:
    """Aggregate result of PCG check."""

    results: list[PCGResult]
    matches: int
    overrides: int
    inference_failures: int

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total_processes": len(self.results),
                "matches": self.matches,
                "overrides": self.overrides,
                "inference_failures": self.inference_failures,
            },
        }


def _commodity_kind_to_cset(kind: str) -> str:
    """Map VedaLang commodity kind to VEDA Cset."""
    mapping = {
        "TRADABLE": "NRG",
        "SERVICE": "DEM",
        "EMISSION": "ENV",
        # Legacy names
        "energy": "NRG",
        "material": "MAT",
        "emission": "ENV",
        "demand": "DEM",
    }
    return mapping.get(kind, "NRG")


def _infer_pcg(
    process: dict,
    commodity_kinds: dict[str, str],
) -> tuple[str | None, str]:
    """
    Infer PCG for a process using xl2times rules.

    Priority: DEM > MAT > NRG > ENV > FIN
    Check OUTPUT side first, then INPUT.

    Returns:
        Tuple of (inferred_pcg, reason)
    """
    # Collect output commodities
    outputs = process.get("outputs", [])
    if process.get("output"):
        outputs = [{"commodity": process["output"]}]

    output_csets = []
    for out in outputs:
        comm = out.get("commodity")
        if comm and comm in commodity_kinds:
            cset = _commodity_kind_to_cset(commodity_kinds[comm])
            output_csets.append(cset)

    # Collect input commodities
    inputs = process.get("inputs", [])
    if process.get("input"):
        inputs = [{"commodity": process["input"]}]

    input_csets = []
    for inp in inputs:
        comm = inp.get("commodity")
        if comm and comm in commodity_kinds:
            cset = _commodity_kind_to_cset(commodity_kinds[comm])
            input_csets.append(cset)

    # Check outputs first by priority
    for cset in PCG_PRIORITY:
        if cset in output_csets:
            return f"{cset}O", f"Output commodity has {cset} type"

    # Then check inputs by priority
    for cset in PCG_PRIORITY:
        if cset in input_csets:
            return f"{cset}I", f"Input commodity has {cset} type"

    return None, "No commodities match known types"


def check_pcg(model_path: Path) -> PCGCheckResult:
    """
    Check PCG inference for all processes in a VedaLang model.

    Args:
        model_path: Path to VedaLang .veda.yaml file

    Returns:
        PCGCheckResult with analysis for each process
    """
    with open(model_path) as f:
        data = yaml.safe_load(f)

    model = data.get("model", {})

    # Build commodity kind lookup
    commodity_kinds: dict[str, str] = {}
    for comm in model.get("commodities", []):
        name = comm.get("name")
        kind = comm.get("kind") or comm.get("type", "TRADABLE")
        if name:
            commodity_kinds[name] = kind

    results: list[PCGResult] = []

    for process in model.get("processes", []):
        name = process.get("name", "UNKNOWN")
        explicit = process.get("primary_commodity_group")

        inferred, reason = _infer_pcg(process, commodity_kinds)

        if inferred is None:
            match = explicit is None
            results.append(
                PCGResult(
                    process=name,
                    inferred=None,
                    explicit=explicit,
                    match=match,
                    reason=reason,
                )
            )
        elif explicit is None:
            results.append(
                PCGResult(
                    process=name,
                    inferred=inferred,
                    explicit=None,
                    match=True,
                    reason=f"No explicit PCG, inference: {reason}",
                )
            )
        else:
            match = inferred == explicit
            results.append(
                PCGResult(
                    process=name,
                    inferred=inferred,
                    explicit=explicit,
                    match=match,
                    reason=reason if match else f"Override: {reason}",
                )
            )

    matches = sum(1 for r in results if r.match)
    overrides = sum(1 for r in results if r.explicit and not r.match)
    inference_failures = sum(1 for r in results if r.inferred is None)

    return PCGCheckResult(
        results=results,
        matches=matches,
        overrides=overrides,
        inference_failures=inference_failures,
    )


def format_pcg_result(result: PCGCheckResult) -> str:
    """Format PCG check result for console output."""
    lines = []

    for r in result.results:
        if r.inferred is None:
            status = "⚠" if r.explicit else "?"
            lines.append(
                f"Process {r.process}: inferred=None, explicit={r.explicit} "
                f"{status} ({r.reason})"
            )
        elif r.match:
            if r.explicit:
                lines.append(
                    f"Process {r.process}: inferred={r.inferred}, "
                    f"explicit={r.explicit} ✓ (match)"
                )
            else:
                lines.append(
                    f"Process {r.process}: inferred={r.inferred} ✓ "
                    "(no explicit PCG needed)"
                )
        else:
            lines.append(
                f"Process {r.process}: inferred={r.inferred}, "
                f"explicit={r.explicit} ⚠ (override)"
            )

    lines.append("")
    lines.append(
        f"Summary: {len(result.results)} processes, {result.matches} matches, "
        f"{result.overrides} overrides, {result.inference_failures} inference failures"
    )

    return "\n".join(lines)
