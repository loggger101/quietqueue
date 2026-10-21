# -*- coding: utf-8 -*-
"""House rules over the package source: ASCII, docstrings, imports."""
import ast
import pathlib
import sys

import pytest

PKG = pathlib.Path(__file__).resolve().parent.parent / "quietqueue"
SOURCES = sorted(PKG.glob("*.py"))
ALLOWED = {"psutil"}


def test_sources_found():
    """The rules below read real files, not an empty glob."""
    assert {p.name for p in SOURCES} >= {"__init__.py", "runner.py", "supervisor.py", "memwatch.py"}


@pytest.mark.parametrize("path", SOURCES + [PKG / "pause.ps1"], ids=lambda p: p.name)
def test_ascii_only(path):
    """Every byte is ASCII: Windows' cp1252 console crashes on printing anything else."""
    bad = [i for i, line in enumerate(path.read_bytes().splitlines(), 1)
           if any(b > 127 for b in line)]
    assert bad == [], f"{path.name}: non-ASCII on lines {bad}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_definition_has_a_docstring(path):
    """Modules, classes and functions all say what they are for."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = [n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               and not ast.get_docstring(n)]
    assert ast.get_docstring(tree), f"{path.name} has no module docstring"
    assert missing == []


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_imports_are_stdlib_or_psutil(path):
    """psutil is the one dependency; nothing else may be imported."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            names.add(n.module.split(".")[0])
    stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
    if stdlib is None:
        pytest.skip("sys.stdlib_module_names needs Python 3.10")
    assert names - stdlib - ALLOWED == set()
