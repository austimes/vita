import json
import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
LSP_SERVER_PATH = PROJECT_ROOT / "tools" / "vedalang_lsp" / "server" / "server.py"
LSP_EXTENSION_PACKAGE_PATH = (
    PROJECT_ROOT / "tools" / "vedalang_lsp" / "extension" / "package.json"
)


def test_repo_version_markers_stay_in_sync() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    package_version = str(pyproject["project"]["version"])

    extension_package = json.loads(
        LSP_EXTENSION_PACKAGE_PATH.read_text(encoding="utf-8")
    )
    assert extension_package["version"] == package_version

    server_source = LSP_SERVER_PATH.read_text(encoding="utf-8")
    match = re.search(r'VedaLangServer\("vedalang-lsp", "([^"]+)"\)', server_source)
    assert match, "Could not find VedaLangServer version marker"
    assert match.group(1) == package_version
