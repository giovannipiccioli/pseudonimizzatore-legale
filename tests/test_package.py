"""Packaging metadata that must stay aligned with the runtime."""
from pathlib import Path
import re

from pseudonimizzatore_legale import __version__


def test_project_and_runtime_versions_match():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    match = re.search(
        r'^version\s*=\s*"([^"]+)"', pyproject.read_text("utf-8"), re.MULTILINE
    )
    assert match is not None
    assert match.group(1) == __version__
