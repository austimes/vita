"""Generate Sankey diagram data from TIMES model results.

This module extracts flow data from GDX files and produces Sankey diagram
specifications that can be rendered with various visualization libraries.
"""

from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any


@dataclass
class SankeyLink:
    """A link (flow) in the Sankey diagram."""

    source: str
    target: str
    value: float
    commodity: str
    year: str
    region: str = ""
    timeslice: str = ""


@dataclass
class SankeyData:
    """Complete Sankey diagram data structure."""

    nodes: list[str] = field(default_factory=list)
    links: list[SankeyLink] = field(default_factory=list)
    title: str = ""
    year: str = ""
    region: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        node_index = {name: i for i, name in enumerate(self.nodes)}
        return {
            "title": self.title,
            "year": self.year,
            "region": self.region,
            "nodes": [{"name": n} for n in self.nodes],
            "links": [
                {
                    "source": node_index.get(link.source, 0),
                    "target": node_index.get(link.target, 0),
                    "value": link.value,
                    "commodity": link.commodity,
                    "source_name": link.source,
                    "target_name": link.target,
                }
                for link in self.links
            ],
            "errors": self.errors,
        }

    def to_mermaid(self) -> str:
        """Generate Mermaid Sankey diagram code."""
        lines = ["sankey-beta", ""]
        for link in self.links:
            lines.append(f'"{link.source}","{link.target}",{link.value:.2f}')
        return "\n".join(lines)

    def to_html(self, width: int = 900, height: int = 600) -> str:
        """Generate standalone HTML with Plotly Sankey visualization."""
        data = self.to_dict()

        node_labels = [n["name"] for n in data["nodes"]]
        sources = [link["source"] for link in data["links"]]
        targets = [link["target"] for link in data["links"]]
        values = [link["value"] for link in data["links"]]
        commodities = [link["commodity"] for link in data["links"]]

        title = self.title or f"Energy Flows - {self.year}"

        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
        body {{ margin: 20px; }}
        h1 {{ color: #333; }}
        .info {{ color: #666; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="info">Region: {self.region} | Year: {self.year}</div>
    <div id="sankey" style="width:{width}px; height:{height}px;"></div>
    <script>
        var data = {{
            type: "sankey",
            orientation: "h",
            node: {{
                pad: 15,
                thickness: 20,
                line: {{ color: "black", width: 0.5 }},
                label: {json.dumps(node_labels)},
                color: "steelblue"
            }},
            link: {{
                source: {json.dumps(sources)},
                target: {json.dumps(targets)},
                value: {json.dumps(values)},
                customdata: {json.dumps(commodities)},
                hovertemplate: 'From: %{{source.label}}<br>To: %{{target.label}}' +
                    '<br>Flow: %{{value:.2f}}<br>Commodity: %{{customdata}}' +
                    '<extra></extra>'
            }}
        }};

        var layout = {{
            title: "",
            font: {{ size: 12 }}
        }};

        Plotly.newPlot('sankey', [data], layout);
    </script>
</body>
</html>"""


def find_gdxdump() -> str | None:
    """Find gdxdump executable."""
    import os
    import shutil

    default_path = "/Library/Frameworks/GAMS.framework/Resources/gdxdump"
    if os.path.exists(default_path):
        return default_path

    env_path = os.environ.get("GDXDUMP")
    if env_path and os.path.exists(env_path):
        return env_path

    return shutil.which("gdxdump")


def dump_symbol_csv(gdx_path: Path, symbol: str, gdxdump: str) -> str | None:
    """Dump a symbol from GDX to CSV format."""
    cmd = [gdxdump, str(gdx_path), f"Symb={symbol}", "Format=csv", "EpsOut=0"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return proc.stdout
        return None
    except Exception:
        return None


def parse_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse CSV output from gdxdump."""
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(StringIO(csv_text))
    return list(reader)


def extract_sankey(
    gdx_path: Path,
    year: str | None = None,
    region: str | None = None,
    aggregate_timeslices: bool = True,
    min_flow: float = 0.01,
) -> SankeyData:
    """Extract Sankey diagram data from a GDX file.

    Args:
        gdx_path: Path to the GDX file
        year: Filter to a specific year (uses first year if None)
        region: Filter to a specific region (uses first region if None)
        aggregate_timeslices: Sum flows across all timeslices
        min_flow: Minimum flow value to include

    Returns:
        SankeyData with nodes, links, and metadata
    """
    sankey = SankeyData()

    gdxdump = find_gdxdump()
    if not gdxdump:
        sankey.errors.append("gdxdump not found. Set GDXDUMP env var or install GAMS.")
        return sankey

    if not gdx_path.exists():
        sankey.errors.append(f"GDX file not found: {gdx_path}")
        return sankey

    # Extract F_IN (inputs to processes)
    f_in_csv = dump_symbol_csv(gdx_path, "F_IN", gdxdump)
    f_in_rows = parse_csv(f_in_csv) if f_in_csv else []

    # Extract F_OUT (outputs from processes)
    f_out_csv = dump_symbol_csv(gdx_path, "F_OUT", gdxdump)
    f_out_rows = parse_csv(f_out_csv) if f_out_csv else []

    if not f_in_rows and not f_out_rows:
        sankey.errors.append("No flow data (F_IN/F_OUT) found in GDX file")
        return sankey

    # Determine available years and regions
    all_years = set()
    all_regions = set()
    for row in f_in_rows + f_out_rows:
        all_years.add(row.get("ALLYEAR", row.get("T", "")))
        all_regions.add(row.get("R", ""))

    # Use specified or first available
    target_year = year or (min(all_years) if all_years else "")
    target_region = region or (min(all_regions) if all_regions else "")

    sankey.year = target_year
    sankey.region = target_region
    sankey.title = f"Energy Flows - {target_region} {target_year}"

    # Aggregate flows: commodity -> process (inputs), process -> commodity (outputs)
    # Structure: commodity nodes and process nodes
    # Links: commodity -> process (input), process -> commodity (output)

    flow_aggregates: dict[tuple[str, str, str], float] = {}
    nodes_set: set[str] = set()

    # Process F_IN: commodity flows INTO process
    for row in f_in_rows:
        row_year = row.get("ALLYEAR", row.get("T", ""))
        row_region = row.get("R", "")

        if row_year != target_year or row_region != target_region:
            continue

        process = row.get("P", "")
        commodity = row.get("C", "")
        timeslice = row.get("S", "")

        try:
            value = float(row.get("Val", 0))
        except ValueError:
            continue

        if abs(value) < min_flow:
            continue

        # Commodity -> Process link
        key = (f"[{commodity}]", process, commodity)
        if aggregate_timeslices:
            flow_aggregates[key] = flow_aggregates.get(key, 0) + value
        else:
            key = (f"[{commodity}]", process, f"{commodity}:{timeslice}")
            flow_aggregates[key] = flow_aggregates.get(key, 0) + value

        nodes_set.add(f"[{commodity}]")
        nodes_set.add(process)

    # Process F_OUT: commodity flows OUT OF process
    for row in f_out_rows:
        row_year = row.get("ALLYEAR", row.get("T", ""))
        row_region = row.get("R", "")

        if row_year != target_year or row_region != target_region:
            continue

        process = row.get("P", "")
        commodity = row.get("C", "")
        timeslice = row.get("S", "")

        try:
            value = float(row.get("Val", 0))
        except ValueError:
            continue

        if abs(value) < min_flow:
            continue

        # Process -> Commodity link
        key = (process, f"[{commodity}]", commodity)
        if aggregate_timeslices:
            flow_aggregates[key] = flow_aggregates.get(key, 0) + value
        else:
            key = (process, f"[{commodity}]", f"{commodity}:{timeslice}")
            flow_aggregates[key] = flow_aggregates.get(key, 0) + value

        nodes_set.add(process)
        nodes_set.add(f"[{commodity}]")

    # Build nodes list (sorted for consistency)
    sankey.nodes = sorted(nodes_set)

    # Build links
    for (source, target, commodity), value in flow_aggregates.items():
        if value >= min_flow:
            sankey.links.append(
                SankeyLink(
                    source=source,
                    target=target,
                    value=value,
                    commodity=commodity,
                    year=target_year,
                    region=target_region,
                )
            )

    # Sort links by value descending
    sankey.links.sort(key=lambda x: x.value, reverse=True)

    return sankey


def get_available_years(gdx_path: Path) -> list[str]:
    """Get list of years available in the GDX file."""
    gdxdump = find_gdxdump()
    if not gdxdump:
        return []

    f_in_csv = dump_symbol_csv(gdx_path, "F_IN", gdxdump)
    if not f_in_csv:
        return []

    years = set()
    for row in parse_csv(f_in_csv):
        years.add(row.get("ALLYEAR", row.get("T", "")))

    return sorted(years)


def get_available_regions(gdx_path: Path) -> list[str]:
    """Get list of regions available in the GDX file."""
    gdxdump = find_gdxdump()
    if not gdxdump:
        return []

    f_in_csv = dump_symbol_csv(gdx_path, "F_IN", gdxdump)
    if not f_in_csv:
        return []

    regions = set()
    for row in parse_csv(f_in_csv):
        regions.add(row.get("R", ""))

    return sorted(regions)
