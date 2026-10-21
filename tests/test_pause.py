# -*- coding: utf-8 -*-
"""pause.ps1 freezes and thaws a real two-process tree (Windows only)."""
import os
import subprocess
import sys
import time
import uuid

import psutil
import pytest

from quietqueue import pause_script

pytestmark = pytest.mark.skipif(os.name != "nt", reason="pause.ps1 is Windows PowerShell")

ROOT_SCRIPT = (
    "import subprocess, sys, time\n"
    "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
    "time.sleep(120)\n")


def ps(*args):
    """Run pause.ps1 with `args`; return (exit code, stdout).

    Through -Command, not -File: -File cannot pass an empty string, and a
    Python process whose OWN argv holds a `*` hangs the powershell.exe it
    starts (measured in economicspace), so patterns never travel in argv here.
    `exit $LASTEXITCODE` carries the script's code out; -Command alone turns
    any non-zero exit into 1, where -File keeps it.
    """
    quoted = " ".join(a if a.startswith("-") else "'" + a + "'" for a in args)
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", f"& '{pause_script()}' {quoted}; exit $LASTEXITCODE"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    return r.returncode, r.stdout.strip()


@pytest.fixture
def tree(tmp_path):
    """A python root named qq_pause_<random>.py and its sleeping child; killed afterwards."""
    name = f"qq_pause_{uuid.uuid4().hex[:8]}"
    script = tmp_path / f"{name}.py"
    script.write_text(ROOT_SCRIPT)
    root = subprocess.Popen([sys.executable, str(script)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = psutil.Process(root.pid)
    # Two processes, or four under a venv, whose python.exe is a launcher that
    # starts the base interpreter: wait for the sleeping leaf, then for the
    # tree to stop growing.
    deadline = time.time() + 30
    members, settled = [], 0
    while time.time() < deadline and settled < 3:
        now = [proc] + proc.children(recursive=True)
        has_leaf = any("time.sleep(120)" in " ".join(p.cmdline()) for p in now[1:])
        settled = settled + 1 if has_leaf and len(now) == len(members) else 0
        members = now
        time.sleep(0.2)
    assert settled == 3 and len(members) in (2, 4)
    yield name, members
    for p in members:
        try:
            p.resume()
            p.kill()
        except psutil.NoSuchProcess:
            pass


def states(members):
    """The set of the members' psutil statuses."""
    return sorted({p.status() for p in members})


def test_freeze_and_thaw_the_whole_tree(tree):
    """The root AND its child are suspended, then resumed; no task named, none touched."""
    name, members = tree
    rc, out = ps("-Match", f"*{name}*")
    assert rc == 0 and out.startswith(f"suspending {len(members)} processes")
    assert "no scheduled task named - its trigger left alone" in out
    assert states(members) == ["stopped"]
    rc, out = ps("-Resume", "-Match", f"*{name}*")
    assert rc == 0 and out.startswith(f"resuming {len(members)} processes")
    assert states(members) == ["running"]


def test_match_takes_an_array(tree):
    """Any one of several patterns names a root."""
    name, members = tree
    quoted = f"'*qq_nomatch_x*','*{name}*'"
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                        f"& '{pause_script()}' -Match {quoted}"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    assert r.stdout.startswith(f"suspending {len(members)} processes")
    assert states(members) == ["stopped"]
    ps("-Resume", "-Match", f"*{name}*")
    assert states(members) == ["running"]


def test_no_match_freezes_nothing(tree):
    """A pattern, or a process name, that matches nothing touches nothing."""
    name, members = tree
    assert ps("-Match", "*qq_nomatch_x*") == (0, "no matching processes found - nothing to do")
    assert ps("-Match", f"*{name}*", "-ProcessName", "qq_nothing%")[1].startswith("no matching")
    assert states(members) == ["running"]


def test_absent_task_is_reported_not_raised(tree):
    """A task this machine lacks is named in a line, not raised after the freeze."""
    name, members = tree
    rc, out = ps("-Match", f"*{name}*", "-TaskName", f"qq_no_task_{uuid.uuid4().hex[:6]}")
    assert rc == 0 and "here - its trigger left alone" in out
    ps("-Resume", "-Match", f"*{name}*")


def test_match_is_required():
    """No -Match exits 2 with a line, rather than prompting (a prompt hangs a scheduler)."""
    assert ps() == (2, "pause.ps1: -Match is required (see Get-Help pause.ps1 -Full)")
