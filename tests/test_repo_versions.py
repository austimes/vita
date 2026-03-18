import tomllib
from pathlib import Path

from vedalang.version import VEDALANG_CLI_VERSION
from vita.version import VITA_CLI_VERSION

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
def test_repo_version_markers_stay_in_sync() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    package_version = str(pyproject["project"]["version"])

    assert VITA_CLI_VERSION == package_version
    assert VEDALANG_CLI_VERSION == package_version
