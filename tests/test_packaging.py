"""Packaging metadata and the ``agent`` entrypoint."""

from __future__ import annotations

import tomllib
from importlib.metadata import entry_points
from pathlib import Path

import typer

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _project() -> dict[str, object]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    return project


def test_entrypoint_declared_and_importable() -> None:
    scripts = _project()["scripts"]
    assert isinstance(scripts, dict)
    assert scripts["agent"] == "middletic.cli.main:app"

    module_path, attr = scripts["agent"].split(":")
    module = __import__(module_path, fromlist=[attr])
    assert isinstance(getattr(module, attr), typer.Typer)


def test_installed_console_script_resolves_to_app() -> None:
    (entry,) = entry_points(group="console_scripts", name="agent")
    assert entry.value == "middletic.cli.main:app"
    assert isinstance(entry.load(), typer.Typer)


def test_metadata_complete() -> None:
    project = _project()
    for key in ("description", "readme", "license", "authors", "keywords", "urls", "classifiers"):
        assert project.get(key), f"missing [project].{key}"
    classifiers = project["classifiers"]
    assert isinstance(classifiers, list)
    assert "Environment :: Console" in classifiers
    assert "Intended Audience :: Developers" in classifiers
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    urls = project["urls"]
    assert isinstance(urls, dict)
    assert {"Homepage", "Repository", "Issues"} <= set(urls)


def test_py_typed_marker_shipped() -> None:
    assert (PYPROJECT.parent / "src" / "middletic" / "py.typed").exists()
