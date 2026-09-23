from __future__ import annotations

import re
import tomllib
from pathlib import Path


def test_removed_provider_dependencies_are_not_declared() -> None:
    """B4 must remove packages whose final provider importers disappeared in B3."""
    backend_root = Path(__file__).resolve().parents[1]
    project_paths = [
        backend_root / "pyproject.toml",
        backend_root / "packages" / "harness" / "pyproject.toml",
    ]
    declared_names: set[str] = set()
    for project_path in project_paths:
        project = tomllib.loads(project_path.read_text(encoding="utf-8"))["project"]
        declarations = list(project.get("dependencies", []))
        for extra_dependencies in project.get("optional-dependencies", {}).values():
            declarations.extend(extra_dependencies)
        declared_names.update(re.split(r"[\s\[<=>!~;]", dependency, maxsplit=1)[0].lower().replace("_", "-") for dependency in declarations)

    removed_provider_dependencies = {
        "agent-client-protocol",
        "boxlite",
        "e2b-code-interpreter",
        "exa-py",
        "firecrawl-py",
        "kubernetes",
        "langchain-openviking",
        "opensandbox",
        "tavily-python",
        "tenki",
    }

    assert declared_names.isdisjoint(removed_provider_dependencies)


def test_removed_sandbox_extras_are_not_declared() -> None:
    """Deleted sandbox providers must not remain installable harness extras."""
    pyproject_path = Path(__file__).resolve().parents[1] / "packages" / "harness" / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert {"boxlite", "tenki", "opensandbox"}.isdisjoint(optional_dependencies)
