"""Tests for GAMS listing file diagnostic parsing."""

import pytest

from tools.veda_run_times.runner import parse_gams_listing


class TestParseGamsListing:
    """Test parse_gams_listing with various GAMS output scenarios."""

    def test_optimal_solution(self):
        """Test parsing a successful optimal solution."""
        content = """
               S O L V E      S U M M A R Y

     MODEL   energy_model
     TYPE    LP
     SOLVER  CBC

**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
**** OBJECTIVE VALUE               123456.789

"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is True
        assert diag["summary"]["problem_type"] is None
        assert "Solved successfully" in diag["summary"]["message"]

        assert diag["execution"]["ran_solver"] is True
        assert diag["execution"]["model_status"]["code"] == 1
        assert diag["execution"]["model_status"]["category"] == "optimal"
        assert diag["execution"]["solve_status"]["code"] == 1
        assert diag["execution"]["solve_status"]["category"] == "ok"
        assert diag["execution"]["objective"]["value"] == pytest.approx(123456.789)

        assert diag["compilation"]["ok"] is True
        assert not any(diag["flags"].values())

    def test_locally_optimal(self):
        """Test parsing locally optimal (NLP) solution."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      2 LOCALLY OPTIMAL
**** OBJECTIVE VALUE               42.0
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is True
        assert diag["execution"]["model_status"]["code"] == 2
        assert diag["execution"]["model_status"]["category"] == "optimal"

    def test_integer_solution(self):
        """Test parsing integer solution (MIP)."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      8 INTEGER SOLUTION
**** OBJECTIVE VALUE               999
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is True
        assert diag["execution"]["model_status"]["code"] == 8
        assert diag["execution"]["model_status"]["category"] == "optimal"

    def test_infeasible_model(self):
        """Test parsing infeasible model."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      4 INFEASIBLE

---- MODEL INFEASIBILITY DETECTED
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is False
        assert diag["summary"]["problem_type"] == "infeasible"
        assert diag["execution"]["model_status"]["code"] == 4
        assert diag["execution"]["model_status"]["category"] == "infeasible"
        assert diag["flags"]["infeasible"] is True

    def test_unbounded_model(self):
        """Test parsing unbounded model."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      3 UNBOUNDED
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is False
        assert diag["summary"]["problem_type"] == "unbounded"
        assert diag["execution"]["model_status"]["code"] == 3
        assert diag["execution"]["model_status"]["category"] == "unbounded"
        assert diag["flags"]["unbounded"] is True

    def test_syntax_error(self):
        """Test parsing compilation with syntax error."""
        content = """
SYNTAX ERROR in file "model.gms" line 42

**** ERROR at line 42: Unknown identifier "FOO"
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is False
        assert diag["summary"]["problem_type"] == "syntax_error"
        assert diag["compilation"]["ok"] is False
        assert diag["flags"]["syntax_error"] is True
        assert len(diag["compilation"]["errors"]) > 0

    def test_domain_violation(self):
        """Test parsing domain violation."""
        content = """
**** DOMAIN VIOLATION detected in equation EQ1

**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
"""
        diag = parse_gams_listing(content)

        assert diag["flags"]["domain_violation"] is True
        # Domain violation alone doesn't prevent OK if solution is optimal
        assert diag["summary"]["problem_type"] == "domain_violation"

    def test_licensing_problem(self):
        """Test parsing licensing error."""
        content = """
**** LICENSE ERROR: Demo mode limit exceeded
**** SOLVER STATUS     7 LICENSING PROBLEM
**** MODEL STATUS     11 LICENSING PROBLEM
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is False
        assert diag["summary"]["problem_type"] == "licensing"
        assert diag["execution"]["model_status"]["code"] == 11
        assert diag["execution"]["model_status"]["category"] == "licensing"
        assert diag["flags"]["licensing_problem"] is True

    def test_solver_failure(self):
        """Test parsing solver failure."""
        content = """
**** SOLVER STATUS    10 ERROR SOLVER FAILURE
**** MODEL STATUS     13 ERROR NO SOLUTION
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is False
        assert diag["summary"]["problem_type"] == "solver_failure"
        assert diag["execution"]["solve_status"]["code"] == 10
        assert diag["execution"]["solve_status"]["category"] == "solver_failure"
        assert diag["flags"]["solver_failure"] is True

    def test_scientific_notation_objective(self):
        """Test parsing objective value in scientific notation."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
**** OBJECTIVE VALUE               1.23e+06
"""
        diag = parse_gams_listing(content)

        assert diag["execution"]["objective"]["value"] == pytest.approx(1.23e6)

    def test_fortran_d_notation_objective(self):
        """Test parsing objective value with Fortran D notation."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
**** OBJECTIVE VALUE               4.56D+03
"""
        diag = parse_gams_listing(content)

        assert diag["execution"]["objective"]["value"] == pytest.approx(4560.0)

    def test_negative_objective(self):
        """Test parsing negative objective value."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
**** OBJECTIVE VALUE              -789.123
"""
        diag = parse_gams_listing(content)

        assert diag["execution"]["objective"]["value"] == pytest.approx(-789.123)

    def test_empty_content(self):
        """Test parsing empty content."""
        diag = parse_gams_listing("")

        assert diag["summary"]["ok"] is True
        assert diag["execution"]["ran_solver"] is False
        assert diag["execution"]["model_status"]["code"] is None
        assert diag["execution"]["solve_status"]["code"] is None

    def test_multiple_errors(self):
        """Test parsing multiple error lines."""
        content = """
**** ERROR 1: First error
**** ERROR 2: Second error
**** ERROR 3: Third error
"""
        diag = parse_gams_listing(content)

        assert len(diag["compilation"]["errors"]) == 3
        assert len(diag["messages"]["errors"]) == 3

    def test_warnings_parsed(self):
        """Test parsing warning lines."""
        content = """
*** WARNING: This is a warning
*** WARNING: Another warning
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is True
        assert len(diag["compilation"]["warnings"]) == 2
        assert len(diag["messages"]["warnings"]) == 2

    def test_raw_lines_captured(self):
        """Test that raw status lines are captured."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
**** OBJECTIVE VALUE               100
"""
        diag = parse_gams_listing(content)

        assert "MODEL STATUS" in diag["raw"]["model_status_line"]
        assert "SOLVER STATUS" in diag["raw"]["solve_status_line"]
        assert "OBJECTIVE VALUE" in diag["raw"]["objective_line"]

    def test_integer_infeasible(self):
        """Test parsing integer infeasible model."""
        content = """
**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS     10 INTEGER INFEASIBLE

No integer solution exists
"""
        diag = parse_gams_listing(content)

        assert diag["summary"]["ok"] is False
        assert diag["execution"]["model_status"]["code"] == 10
        assert diag["execution"]["model_status"]["category"] == "infeasible"
        assert diag["flags"]["integer_infeasible"] is True
        assert diag["flags"]["infeasible"] is True

    def test_unknown_symbol(self):
        """Test parsing unknown symbol error."""
        content = """
**** UNKNOWN SYMBOL: X
**** ERROR at line 10: Symbol not defined
"""
        diag = parse_gams_listing(content)

        assert diag["flags"]["unknown_symbol"] is True
        assert diag["compilation"]["ok"] is False

    def test_solver_name_parsed(self):
        """Test parsing solver name from listing."""
        content = """
     SOLVER  CPLEX

**** SOLVER STATUS     1 NORMAL COMPLETION
**** MODEL STATUS      1 OPTIMAL
"""
        diag = parse_gams_listing(content)

        assert diag["execution"]["solver"] == "CPLEX"


class TestDiagnosticStructure:
    """Test that diagnostic structure matches expected schema."""

    def test_all_top_level_keys_present(self):
        """Ensure all required top-level keys are present."""
        diag = parse_gams_listing("")

        required_keys = [
            "compilation",
            "execution",
            "flags",
            "summary",
            "messages",
            "raw",
        ]
        for key in required_keys:
            assert key in diag, f"Missing key: {key}"

    def test_compilation_structure(self):
        """Test compilation section structure."""
        diag = parse_gams_listing("")

        assert "ok" in diag["compilation"]
        assert "errors" in diag["compilation"]
        assert "warnings" in diag["compilation"]
        assert isinstance(diag["compilation"]["errors"], list)
        assert isinstance(diag["compilation"]["warnings"], list)

    def test_execution_structure(self):
        """Test execution section structure."""
        diag = parse_gams_listing("")

        assert "ran_solver" in diag["execution"]
        assert "model_status" in diag["execution"]
        assert "solve_status" in diag["execution"]
        assert "objective" in diag["execution"]
        assert "solver" in diag["execution"]

        assert "code" in diag["execution"]["model_status"]
        assert "text" in diag["execution"]["model_status"]
        assert "category" in diag["execution"]["model_status"]

        assert "value" in diag["execution"]["objective"]
        assert "name" in diag["execution"]["objective"]
        assert "sense" in diag["execution"]["objective"]

    def test_flags_structure(self):
        """Test flags section structure."""
        diag = parse_gams_listing("")

        expected_flags = [
            "syntax_error",
            "domain_violation",
            "infeasible",
            "unbounded",
            "integer_infeasible",
            "solver_failure",
            "licensing_problem",
            "unknown_symbol",
        ]
        for flag in expected_flags:
            assert flag in diag["flags"], f"Missing flag: {flag}"
            assert isinstance(diag["flags"][flag], bool)

    def test_summary_structure(self):
        """Test summary section structure."""
        diag = parse_gams_listing("")

        assert "ok" in diag["summary"]
        assert "problem_type" in diag["summary"]
        assert "message" in diag["summary"]
        assert isinstance(diag["summary"]["ok"], bool)
        assert isinstance(diag["summary"]["message"], str)

    def test_messages_structure(self):
        """Test messages section structure."""
        diag = parse_gams_listing("")

        assert "errors" in diag["messages"]
        assert "warnings" in diag["messages"]
        assert "info" in diag["messages"]
        assert isinstance(diag["messages"]["errors"], list)
        assert isinstance(diag["messages"]["warnings"], list)
        assert isinstance(diag["messages"]["info"], list)

    def test_raw_structure(self):
        """Test raw section structure."""
        diag = parse_gams_listing("")

        assert "model_status_line" in diag["raw"]
        assert "solve_status_line" in diag["raw"]
        assert "objective_line" in diag["raw"]
