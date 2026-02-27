"""Eval framework package for vedalang-dev."""

from .config import build_candidate_matrix
from .dataset import default_dataset_path, load_dataset
from .runner import compare_runs, render_report, run_eval

__all__ = [
    "build_candidate_matrix",
    "compare_runs",
    "default_dataset_path",
    "load_dataset",
    "render_report",
    "run_eval",
]
