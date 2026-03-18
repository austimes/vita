"""Curated starter assets for ``vita init``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StarterDemo:
    """Metadata for a curated demo shipped with Vita."""

    id: str
    title: str
    asset_filename: str
    target_relpath: Path
    default_run: str
    question: str
    featured: bool = False
    experiment_asset_filename: str | None = None


CURATED_STARTER_DEMOS: tuple[StarterDemo, ...] = (
    StarterDemo(
        id="toy_agriculture",
        title="Agriculture & Land",
        asset_filename="demo.toy_agriculture.veda.yaml",
        target_relpath=Path("models/demos/toy_agriculture.veda.yaml"),
        default_run="single_2025",
        question=(
            "Represent methane abatement and sequestration under a cap and inspect "
            "the implied abatement stack."
        ),
    ),
    StarterDemo(
        id="toy_buildings",
        title="Built Environment",
        asset_filename="demo.toy_buildings.veda.yaml",
        target_relpath=Path("models/demos/toy_buildings.veda.yaml"),
        default_run="single_2025",
        question=(
            "Replace gas heating with heat pumps and inspect electricity, peak, "
            "and emissions impacts."
        ),
    ),
    StarterDemo(
        id="toy_electricity_2ts",
        title="Electricity & Energy",
        asset_filename="demo.toy_electricity_2ts.veda.yaml",
        target_relpath=Path("models/demos/toy_electricity_2ts.veda.yaml"),
        default_run="electricity_2node_2025",
        question=(
            "Test how demand uplift and constraints change least-cost build and "
            "firming choices."
        ),
    ),
    StarterDemo(
        id="toy_industry",
        title="Industry",
        asset_filename="demo.toy_industry.veda.yaml",
        target_relpath=Path("models/demos/toy_industry.veda.yaml"),
        default_run="single_2025",
        question=(
            "Apply an emissions constraint to industrial heat demand and inspect "
            "which clean-heat technology is selected."
        ),
        featured=True,
        experiment_asset_filename="experiment.toy_industry_core.experiment.yaml",
    ),
    StarterDemo(
        id="toy_resources",
        title="Resources",
        asset_filename="demo.toy_resources.veda.yaml",
        target_relpath=Path("models/demos/toy_resources.veda.yaml"),
        default_run="single_2025",
        question=(
            "Explore mining electrification and low-carbon fuel substitution under "
            "cost and emissions pressure."
        ),
    ),
    StarterDemo(
        id="toy_transport",
        title="Transport",
        asset_filename="demo.toy_transport.veda.yaml",
        target_relpath=Path("models/demos/toy_transport.veda.yaml"),
        default_run="single_2025",
        question=(
            "Estimate the system effects of EV uptake, charging shape, and petrol "
            "displacement."
        ),
    ),
)

MINIMAL_STARTER_MODEL = Path("models/example.veda.yaml")
MINIMAL_STARTER_RUN = "demo_2025"


def featured_starter_demo() -> StarterDemo:
    """Return the featured curated starter demo."""
    for demo in CURATED_STARTER_DEMOS:
        if demo.featured:
            return demo
    raise RuntimeError("No featured curated starter demo is configured.")
