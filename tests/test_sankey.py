"""Tests for Sankey diagram generation from TIMES results."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.veda_dev.sankey import (
    SankeyData,
    SankeyDataMulti,
    SankeyLink,
    extract_sankey,
    extract_sankey_multi,
)


class TestSankeyData:
    def test_to_dict_empty(self):
        """Empty SankeyData converts to valid dict."""
        data = SankeyData()
        result = data.to_dict()
        assert result["nodes"] == []
        assert result["links"] == []
        assert result["errors"] == []

    def test_to_dict_with_data(self):
        """SankeyData with nodes and links converts properly."""
        data = SankeyData(
            nodes=["ProcessA", "[ELC]"],
            links=[
                SankeyLink(
                    source="ProcessA",
                    target="[ELC]",
                    value=100.0,
                    commodity="ELC",
                    year="2020",
                    region="R1",
                )
            ],
            title="Test",
            year="2020",
            region="R1",
        )
        result = data.to_dict()
        assert len(result["nodes"]) == 2
        assert len(result["links"]) == 1
        assert result["links"][0]["value"] == 100.0
        assert result["links"][0]["source"] == 0
        assert result["links"][0]["target"] == 1

    def test_to_mermaid(self):
        """Mermaid output is valid sankey-beta format."""
        data = SankeyData(
            nodes=["ProcessA", "[ELC]"],
            links=[
                SankeyLink(
                    source="ProcessA",
                    target="[ELC]",
                    value=100.0,
                    commodity="ELC",
                    year="2020",
                    region="R1",
                )
            ],
        )
        mermaid = data.to_mermaid()
        assert mermaid.startswith("sankey-beta")
        assert '"ProcessA","[ELC]",100.00' in mermaid

    def test_to_html(self):
        """HTML output contains Plotly configuration."""
        data = SankeyData(
            nodes=["ProcessA", "[ELC]"],
            links=[
                SankeyLink(
                    source="ProcessA",
                    target="[ELC]",
                    value=100.0,
                    commodity="ELC",
                    year="2020",
                    region="R1",
                )
            ],
            title="Test Sankey",
            year="2020",
            region="R1",
        )
        html = data.to_html()
        assert "plotly" in html.lower()
        assert "sankey" in html.lower()
        assert "Test Sankey" in html or "Energy Flows" in html


class TestExtractSankey:
    def test_missing_gdx_file(self, tmp_path):
        """Returns error when GDX file doesn't exist."""
        result = extract_sankey(tmp_path / "nonexistent.gdx")
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()

    @patch("tools.veda_dev.sankey.find_gdxdump")
    def test_missing_gdxdump(self, mock_find, tmp_path):
        """Returns error when gdxdump is not available."""
        mock_find.return_value = None
        gdx_file = tmp_path / "test.gdx"
        gdx_file.touch()
        result = extract_sankey(gdx_file)
        assert len(result.errors) > 0
        assert "gdxdump not found" in result.errors[0]

    @patch("tools.veda_dev.sankey.dump_symbol_csv")
    @patch("tools.veda_dev.sankey.find_gdxdump")
    def test_extracts_flows_from_mock_data(self, mock_find, mock_dump, tmp_path):
        """Correctly extracts and structures flow data."""
        mock_find.return_value = "/usr/bin/gdxdump"

        f_in_csv = (
            '"R","ALLYEAR","T","P","C","S","Val"\n'
            '"R1","2020","2020","DMD","ELC","ANNUAL",50.0'
        )
        f_out_csv = (
            '"R","ALLYEAR","T","P","C","S","Val"\n'
            '"R1","2020","2020","DMD","HEAT","ANNUAL",45.0'
        )

        def side_effect(gdx_path, symbol, gdxdump):
            if symbol == "F_IN":
                return f_in_csv
            elif symbol == "F_OUT":
                return f_out_csv
            return None

        mock_dump.side_effect = side_effect

        gdx_file = tmp_path / "test.gdx"
        gdx_file.touch()

        result = extract_sankey(gdx_file)

        assert len(result.errors) == 0
        assert result.year == "2020"
        assert result.region == "R1"
        assert len(result.nodes) == 3
        assert "[ELC]" in result.nodes
        assert "[HEAT]" in result.nodes
        assert "DMD" in result.nodes
        assert len(result.links) == 2


class TestSankeyDataMulti:
    """Tests for SankeyDataMulti (interactive visualization)."""

    def test_to_html_interactive_basic(self):
        """Interactive HTML contains expected elements."""
        data = SankeyDataMulti(
            nodes=["ProcessA", "[ELC]"],
            years=["2020", "2030"],
            regions=["R1", "R2"],
            links={
                "2020": {
                    "R1": [
                        {"source": 0, "target": 1, "value": 100.0, "commodity": "ELC"}
                    ],
                    "R2": [
                        {"source": 0, "target": 1, "value": 50.0, "commodity": "ELC"}
                    ],
                },
                "2030": {
                    "R1": [
                        {"source": 0, "target": 1, "value": 120.0, "commodity": "ELC"}
                    ],
                    "R2": [
                        {"source": 0, "target": 1, "value": 60.0, "commodity": "ELC"}
                    ],
                },
            },
            title="Test Interactive Sankey",
        )
        html = data.to_html_interactive()

        # Check for Plotly
        assert "plotly" in html.lower()
        assert "sankey" in html.lower()

        # Check for collapsible sidebar
        assert "sidebar" in html
        assert "toggle-btn" in html

        # Check for year dropdown (not slider)
        assert "year-select" in html

        # Check for region multi-select
        assert "region-select" in html
        assert "All regions" in html

        # Check data is embedded
        assert "2020" in html
        assert "2030" in html
        assert "R1" in html
        assert "R2" in html

        # Check JavaScript functions
        assert "renderSankey" in html
        assert "aggregateLinks" in html
        assert "Plotly.react" in html


class TestExtractSankeyMulti:
    """Tests for extract_sankey_multi."""

    def test_missing_gdx_file(self, tmp_path):
        """Returns error when GDX file doesn't exist."""
        result = extract_sankey_multi(tmp_path / "nonexistent.gdx")
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()

    @patch("tools.veda_dev.sankey.find_gdxdump")
    def test_missing_gdxdump(self, mock_find, tmp_path):
        """Returns error when gdxdump is not available."""
        mock_find.return_value = None
        gdx_file = tmp_path / "test.gdx"
        gdx_file.touch()
        result = extract_sankey_multi(gdx_file)
        assert len(result.errors) > 0
        assert "gdxdump not found" in result.errors[0]

    @patch("tools.veda_dev.sankey.dump_symbol_csv")
    @patch("tools.veda_dev.sankey.find_gdxdump")
    def test_extracts_multi_year_region_data(self, mock_find, mock_dump, tmp_path):
        """Correctly extracts data for all years and regions."""
        mock_find.return_value = "/usr/bin/gdxdump"

        # Multi-year, multi-region data
        f_in_csv = (
            '"R","ALLYEAR","T","P","C","S","Val"\n'
            '"R1","2020","2020","DMD","ELC","ANNUAL",50.0\n'
            '"R1","2030","2030","DMD","ELC","ANNUAL",60.0\n'
            '"R2","2020","2020","DMD","ELC","ANNUAL",40.0\n'
            '"R2","2030","2030","DMD","ELC","ANNUAL",45.0'
        )
        f_out_csv = (
            '"R","ALLYEAR","T","P","C","S","Val"\n'
            '"R1","2020","2020","DMD","HEAT","ANNUAL",45.0\n'
            '"R1","2030","2030","DMD","HEAT","ANNUAL",55.0\n'
            '"R2","2020","2020","DMD","HEAT","ANNUAL",35.0\n'
            '"R2","2030","2030","DMD","HEAT","ANNUAL",40.0'
        )

        def side_effect(gdx_path, symbol, gdxdump):
            if symbol == "F_IN":
                return f_in_csv
            elif symbol == "F_OUT":
                return f_out_csv
            return None

        mock_dump.side_effect = side_effect

        gdx_file = tmp_path / "test.gdx"
        gdx_file.touch()

        result = extract_sankey_multi(gdx_file)

        assert len(result.errors) == 0
        assert result.years == ["2020", "2030"]
        assert result.regions == ["R1", "R2"]
        assert len(result.nodes) == 3  # DMD, [ELC], [HEAT]
        assert "[ELC]" in result.nodes
        assert "[HEAT]" in result.nodes
        assert "DMD" in result.nodes

        # Check links structure
        assert "2020" in result.links
        assert "2030" in result.links
        assert "R1" in result.links["2020"]
        assert "R2" in result.links["2020"]

        # Check link values (indices)
        r1_2020_links = result.links["2020"]["R1"]
        assert len(r1_2020_links) == 2  # one F_IN, one F_OUT


class TestSankeyCLI:
    """Test Vita sankey CLI subcommand."""

    def test_sankey_help(self):
        """Sankey --help works."""
        import subprocess

        result = subprocess.run(
            ["uv", "run", "vita", "sankey", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0
        assert "--gdx" in result.stdout
        assert "--year" in result.stdout
        assert "--format" in result.stdout

    def test_sankey_missing_gdx(self, tmp_path):
        """Returns error for missing GDX file."""
        import subprocess

        result = subprocess.run(
            [
                "uv",
                "run",
                "vita",
                "sankey",
                "--gdx",
                str(tmp_path / "nonexistent.gdx"),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()


@pytest.mark.skipif(
    not Path("/Library/Frameworks/GAMS.framework/Resources/gdxdump").exists(),
    reason="gdxdump not available",
)
class TestSankeyWithRealGDX:
    """Integration tests with real GDX file (requires GAMS)."""

    @pytest.fixture
    def gdx_path(self):
        path = Path(__file__).parent.parent / "tmp/gams/scenario.gdx"
        if not path.exists():
            pytest.skip("No GDX file available for testing")
        return path

    def test_extract_real_gdx(self, gdx_path):
        """Extracts Sankey data from real GDX."""
        result = extract_sankey(gdx_path)
        assert len(result.errors) == 0

    def test_list_years_real_gdx(self, gdx_path):
        """List years from real GDX."""
        from tools.veda_dev.sankey import get_available_years

        years = get_available_years(gdx_path)
        assert len(years) >= 1

    def test_json_output(self, gdx_path):
        """JSON output is valid."""
        result = extract_sankey(gdx_path)
        output = json.dumps(result.to_dict())
        data = json.loads(output)
        assert "nodes" in data
        assert "links" in data

    def test_extract_multi_real_gdx(self, gdx_path):
        """Extracts multi-year/region Sankey data from real GDX."""
        result = extract_sankey_multi(gdx_path)
        assert len(result.errors) == 0
        assert len(result.years) >= 1
        assert len(result.regions) >= 1
        assert len(result.nodes) >= 1

    def test_interactive_html_real_gdx(self, gdx_path):
        """Interactive HTML generation works with real GDX."""
        result = extract_sankey_multi(gdx_path)
        assert len(result.errors) == 0

        html = result.to_html_interactive()
        assert "plotly" in html.lower()
        assert "sidebar" in html
        assert "year-select" in html
        assert "region-select" in html
        # Check that data is embedded
        for year in result.years:
            assert year in html
        for region in result.regions:
            assert region in html
