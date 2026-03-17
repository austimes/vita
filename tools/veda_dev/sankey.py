"""Generate Sankey diagram data from TIMES model results.

This module extracts flow data from GDX files and produces Sankey diagram
specifications that can be rendered with various visualization libraries.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from .gdx_utils import dump_symbol_csv, find_gdxdump


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


@dataclass
class SankeyDataMulti:
    """Multi-year/region Sankey data for interactive visualization."""

    nodes: list[str] = field(default_factory=list)
    years: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    # links[year][region] = list of {source_idx, target_idx, value, commodity}
    links: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    title: str = "Energy Flows"
    errors: list[str] = field(default_factory=list)

    def to_html_interactive(self, width: int = 900, height: int = 600) -> str:  # noqa: E501
        """Generate interactive HTML with collapsible sidebar, year dropdown, and region multi-select."""
        data_json = json.dumps(
            {
                "title_base": self.title,
                "nodes": self.nodes,
                "years": self.years,
                "regions": self.regions,
                "links": self.links,
            }
        )

        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{self.title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; display: flex; min-height: 100vh; }}

        /* Sidebar */
        .sidebar {{
            width: 240px;
            min-width: 240px;
            background: #f5f5f5;
            border-right: 1px solid #ddd;
            padding: 16px;
            display: flex;
            flex-direction: column;
            transition: margin-left 0.2s ease;
        }}
        .sidebar.collapsed {{
            margin-left: -240px;
        }}
        .sidebar h2 {{
            margin: 0 0 16px 0;
            font-size: 14px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .control-group {{
            margin-bottom: 20px;
        }}
        .control-group label {{
            display: block;
            font-weight: 600;
            color: #333;
            margin-bottom: 6px;
            font-size: 13px;
        }}
        #year-select, #region-select {{
            width: 100%;
            padding: 4px;
            font-size: 13px;
            border: 1px solid #ccc;
            border-radius: 4px;
            background: white;
        }}
        #region-select:focus {{
            outline: none;
            border-color: #4a90d9;
        }}
        .hint {{
            font-size: 11px;
            color: #888;
            margin-top: 4px;
        }}

        /* Toggle button */
        .toggle-btn {{
            position: fixed;
            left: 240px;
            top: 10px;
            z-index: 100;
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 0 4px 4px 0;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 14px;
            transition: left 0.2s ease;
        }}
        .toggle-btn:hover {{
            background: #f0f0f0;
        }}
        .sidebar.collapsed + .main-content .toggle-btn,
        body:has(.sidebar.collapsed) .toggle-btn {{
            left: 0;
            border-radius: 0 4px 4px 0;
        }}

        /* Main content */
        .main-content {{
            flex: 1;
            padding: 20px;
            overflow: auto;
        }}
        h1 {{
            color: #333;
            margin: 0 0 10px 0;
            font-size: 24px;
        }}
        .info {{
            color: #666;
            margin-bottom: 10px;
            font-size: 14px;
        }}
        .no-data {{
            color: #c00;
            font-style: italic;
            padding: 20px;
        }}
        #sankey {{
            width: 100%;
            height: calc(100vh - 120px);
            min-height: 400px;
        }}
    </style>
</head>
<body>
    <aside class="sidebar" id="sidebar">
        <h2>Controls</h2>
        <div class="control-group">
            <label for="year-select">Year</label>
            <select id="year-select" size="8"></select>
            <div class="hint">Click to select year</div>
        </div>
        <div class="control-group">
            <label for="region-select">Regions</label>
            <select id="region-select" multiple size="8">
                <option value="__ALL__" selected>All regions (aggregated)</option>
            </select>
            <div class="hint">Ctrl/Cmd+click for multiple</div>
        </div>
    </aside>

    <button class="toggle-btn" id="toggle-btn" title="Toggle sidebar">☰</button>

    <main class="main-content">
        <h1 id="chart-title">{self.title}</h1>
        <div id="sankey-info" class="info"></div>
        <div id="sankey"></div>
        <div id="no-data" class="no-data" style="display:none;">No flow data for this selection.</div>
    </main>

    <script>
        var sankeyData = {data_json};
        var currentYearIndex = 0;
        var selectedRegions = [];

        // Sidebar toggle
        document.getElementById('toggle-btn').addEventListener('click', function() {{
            var sidebar = document.getElementById('sidebar');
            var btn = document.getElementById('toggle-btn');
            sidebar.classList.toggle('collapsed');
            btn.style.left = sidebar.classList.contains('collapsed') ? '0' : '240px';
            // Trigger Plotly resize after transition
            setTimeout(function() {{ Plotly.Plots.resize('sankey'); }}, 250);
        }});

        function initYearSelect() {{
            var select = document.getElementById('year-select');

            sankeyData.years.forEach(function(year, idx) {{
                var opt = document.createElement('option');
                opt.value = idx;
                opt.textContent = year;
                if (idx === 0) opt.selected = true;
                select.appendChild(opt);
            }});

            select.addEventListener('change', function() {{
                currentYearIndex = parseInt(this.value, 10);
                renderSankey();
            }});

            // Arrow key navigation works natively with <select>
        }}

        function initRegionSelect() {{
            var select = document.getElementById('region-select');

            sankeyData.regions.forEach(function(r) {{
                var opt = document.createElement('option');
                opt.value = r;
                opt.textContent = r;
                select.appendChild(opt);
            }});

            selectedRegions = sankeyData.regions.slice();

            select.addEventListener('change', function() {{
                var values = Array.from(this.selectedOptions).map(function(o) {{ return o.value; }});

                if (values.length === 0 || values.includes('__ALL__')) {{
                    selectedRegions = sankeyData.regions.slice();
                    Array.from(this.options).forEach(function(opt) {{
                        opt.selected = (opt.value === '__ALL__');
                    }});
                }} else {{
                    selectedRegions = values;
                    Array.from(this.options).forEach(function(opt) {{
                        if (opt.value === '__ALL__') opt.selected = false;
                    }});
                }}
                renderSankey();
            }});
        }}

        function getSelectedRegionsLabel() {{
            if (selectedRegions.length === sankeyData.regions.length) {{
                return 'All regions';
            }}
            return selectedRegions.join(', ');
        }}

        function aggregateLinks(year, regions) {{
            var perRegion = sankeyData.links[year] || {{}};
            var aggMap = new Map();

            regions.forEach(function(region) {{
                var links = perRegion[region] || [];
                links.forEach(function(lnk) {{
                    var key = lnk.source + '|' + lnk.target + '|' + (lnk.commodity || '');
                    var existing = aggMap.get(key);
                    if (!existing) {{
                        existing = {{ source: lnk.source, target: lnk.target, value: 0, commodity: lnk.commodity || '' }};
                        aggMap.set(key, existing);
                    }}
                    existing.value += lnk.value;
                }});
            }});

            return Array.from(aggMap.values());
        }}

        function buildTrace(year, regions) {{
            var aggregated = aggregateLinks(year, regions);

            return {{
                type: "sankey",
                orientation: "h",
                node: {{
                    pad: 15,
                    thickness: 20,
                    line: {{ color: "black", width: 0.5 }},
                    label: sankeyData.nodes,
                    color: "steelblue"
                }},
                link: {{
                    source: aggregated.map(function(l) {{ return l.source; }}),
                    target: aggregated.map(function(l) {{ return l.target; }}),
                    value: aggregated.map(function(l) {{ return l.value; }}),
                    customdata: aggregated.map(function(l) {{ return l.commodity; }}),
                    hovertemplate: 'From: %{{source.label}}<br>To: %{{target.label}}<br>Flow: %{{value:.2f}}<br>Commodity: %{{customdata}}<extra></extra>'
                }}
            }};
        }}

        var sankeyLayout = {{ title: "", font: {{ size: 12 }}, margin: {{ l: 10, r: 10, t: 10, b: 10 }} }};

        function renderSankey() {{
            var year = sankeyData.years[currentYearIndex];
            var regionLabel = getSelectedRegionsLabel();
            var title = sankeyData.title_base + ' - ' + regionLabel + ' ' + year;

            document.getElementById('chart-title').textContent = title;
            document.getElementById('sankey-info').textContent = 'Region(s): ' + regionLabel + ' | Year: ' + year;

            var aggregated = aggregateLinks(year, selectedRegions);
            if (aggregated.length === 0) {{
                document.getElementById('sankey').style.display = 'none';
                document.getElementById('no-data').style.display = 'block';
                return;
            }}
            document.getElementById('sankey').style.display = 'block';
            document.getElementById('no-data').style.display = 'none';

            var trace = buildTrace(year, selectedRegions);
            Plotly.react('sankey', [trace], sankeyLayout, {{responsive: true}});
        }}

        document.addEventListener('DOMContentLoaded', function() {{
            initYearSelect();
            initRegionSelect();
            renderSankey();
        }});

        // Resize handler
        window.addEventListener('resize', function() {{
            Plotly.Plots.resize('sankey');
        }});
    </script>
</body>
</html>"""


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


def extract_sankey_multi(
    gdx_path: Path,
    min_flow: float = 0.01,
) -> SankeyDataMulti:
    """Extract Sankey diagram data for all years and regions from a GDX file.

    Args:
        gdx_path: Path to the GDX file
        min_flow: Minimum flow value to include

    Returns:
        SankeyDataMulti with all years/regions data for interactive visualization
    """
    sankey = SankeyDataMulti()

    gdxdump = find_gdxdump()
    if not gdxdump:
        sankey.errors.append("gdxdump not found. Set GDXDUMP env var or install GAMS.")
        return sankey

    if not gdx_path.exists():
        sankey.errors.append(f"GDX file not found: {gdx_path}")
        return sankey

    # Extract F_IN and F_OUT
    f_in_csv = dump_symbol_csv(gdx_path, "F_IN", gdxdump)
    f_in_rows = parse_csv(f_in_csv) if f_in_csv else []

    f_out_csv = dump_symbol_csv(gdx_path, "F_OUT", gdxdump)
    f_out_rows = parse_csv(f_out_csv) if f_out_csv else []

    if not f_in_rows and not f_out_rows:
        sankey.errors.append("No flow data (F_IN/F_OUT) found in GDX file")
        return sankey

    # Collect all years, regions, and nodes across all data
    all_years: set[str] = set()
    all_regions: set[str] = set()
    nodes_set: set[str] = set()

    # First pass: collect all metadata
    for row in f_in_rows + f_out_rows:
        year = row.get("ALLYEAR", row.get("T", ""))
        region = row.get("R", "")
        process = row.get("P", "")
        commodity = row.get("C", "")

        if year:
            all_years.add(year)
        if region:
            all_regions.add(region)
        if process:
            nodes_set.add(process)
        if commodity:
            nodes_set.add(f"[{commodity}]")

    # Build stable node list (sorted for consistency)
    sankey.nodes = sorted(nodes_set)
    sankey.years = sorted(all_years)
    sankey.regions = sorted(all_regions)
    node_index = {name: i for i, name in enumerate(sankey.nodes)}

    # Initialize links structure: links[year][region] = []
    sankey.links = {
        year: {region: [] for region in sankey.regions} for year in sankey.years
    }

    # Structure to aggregate: (year, region, source, target, commodity) -> value
    flow_aggregates: dict[tuple[str, str, str, str, str], float] = {}

    # Process F_IN: commodity flows INTO process
    for row in f_in_rows:
        year = row.get("ALLYEAR", row.get("T", ""))
        region = row.get("R", "")
        process = row.get("P", "")
        commodity = row.get("C", "")

        try:
            value = float(row.get("Val", 0))
        except ValueError:
            continue

        if abs(value) < min_flow:
            continue

        source = f"[{commodity}]"
        target = process
        key = (year, region, source, target, commodity)
        flow_aggregates[key] = flow_aggregates.get(key, 0) + value

    # Process F_OUT: commodity flows OUT OF process
    for row in f_out_rows:
        year = row.get("ALLYEAR", row.get("T", ""))
        region = row.get("R", "")
        process = row.get("P", "")
        commodity = row.get("C", "")

        try:
            value = float(row.get("Val", 0))
        except ValueError:
            continue

        if abs(value) < min_flow:
            continue

        source = process
        target = f"[{commodity}]"
        key = (year, region, source, target, commodity)
        flow_aggregates[key] = flow_aggregates.get(key, 0) + value

    # Build links by year/region with node indices
    for (year, region, source, target, commodity), value in flow_aggregates.items():
        year_links = sankey.links.get(year, {})
        if value >= min_flow and year in sankey.links and region in year_links:
            source_idx = node_index.get(source, 0)
            target_idx = node_index.get(target, 0)
            sankey.links[year][region].append(
                {
                    "source": source_idx,
                    "target": target_idx,
                    "value": value,
                    "commodity": commodity,
                }
            )

    # Sort each region's links by value descending
    for year in sankey.links:
        for region in sankey.links[year]:
            sankey.links[year][region].sort(key=lambda x: x["value"], reverse=True)

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
