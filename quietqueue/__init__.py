# -*- coding: utf-8 -*-
"""quietqueue: run a queue of long jobs unattended on Windows, and survive it.

- `run_queue` runs a list of `Job`s one subprocess each, resumably, skipping
  every job a ledger records as done (`quietqueue.runner`).
- `supervise` starts a script with no console, so no console control event can
  reach it, and refuses to start a second copy (`quietqueue.supervisor`).
- `watch` samples a family of processes' memory into a CSV, tagged with the
  job running (`quietqueue.memwatch`).
- `pause_script()` is the path of `pause.ps1`, which freezes and thaws a
  process tree so a pause costs no work.

Each module's docstring has the design and the traps behind it.
"""
import os

# The one place the version is written: pyproject.toml reads it from here, and
# a consumer pinning a git tag compares the tag against it.
__version__ = "0.1.0"

# Imported on first use rather than here: `python -m quietqueue.supervisor`
# imports this package first, and a submodule already imported by it would be
# executed a second time as __main__ (runpy warns, and the copies differ).
_LAZY = {"Job": "runner", "done_keys": "runner", "run_queue": "runner",
         "already_running": "supervisor", "supervise": "supervisor",
         "watch": "memwatch"}


def __getattr__(name):
    """Resolve the public names in `_LAZY` from their module on first use."""
    if name in _LAZY:
        import importlib
        return getattr(importlib.import_module("." + _LAZY[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def pause_script():
    """Absolute path of the installed `pause.ps1`, to run with `powershell -File`."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "pause.ps1")


__all__ = ["Job", "already_running", "done_keys", "pause_script", "run_queue",
           "supervise", "watch", "__version__"]
