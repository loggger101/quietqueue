# -*- coding: utf-8 -*-
"""House rules over the package source: ASCII, docstrings, imports, git pins.

The rules are samebytes' (`samebytes.source`, `samebytes.docs`), the one copy
the repositories in this family share; what they read is this package's.
"""
import pathlib

import pytest
from samebytes import docs, source

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "quietqueue"
SOURCES = sorted(PKG.glob("*.py"))
ALLOWED = {"psutil"}


def test_sources_found():
    """The rules below read real files, not an empty glob."""
    assert {p.name for p in SOURCES} >= {"__init__.py", "runner.py", "supervisor.py", "memwatch.py"}


@pytest.mark.parametrize("path", SOURCES + [PKG / "pause.ps1"], ids=lambda p: p.name)
def test_ascii_only(path):
    """Every byte is ASCII: Windows' cp1252 console crashes on printing anything else."""
    assert source.non_ascii(str(ROOT), [str(path)]) == ([], 1)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_definition_has_a_docstring(path):
    """Modules, classes and functions all say what they are for."""
    bad, n = source.docstrings(str(ROOT), [str(path)])
    assert bad == [] and n >= 1


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_imports_are_stdlib_or_psutil(path):
    """psutil is the one dependency; nothing else may be imported."""
    assert source.imports(str(ROOT), [str(path)], allowed=ALLOWED)[0] == []


def test_git_pins_agree():
    """Every `github.com/loggger101/<repo>@<ref>` names one ref per repository.

    samebytes is pinned in pyproject's test extra and in CI's hooks job; the
    hooks job sat on v0.1.0 while the test extra moved to v0.3.0. CHANGELOG is
    left out: an old pin there is history.
    """
    files = ["pyproject.toml", ".github/workflows/tests.yml", "README.md", "CLAUDE.md"]
    bad, n = docs.pins(str(ROOT), files, "loggger101")
    assert bad == [] and n >= 3, "; ".join(bad)
