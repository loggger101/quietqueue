# -*- coding: utf-8 -*-
"""Start a long-running script with NO CONSOLE, then exit immediately.

    python -m quietqueue.supervisor my_queue.py --log queue.log [--cwd DIR]

or, from a script of your own, `supervise(target, log, cwd)`.

Built for a queue measured in days that was killed twice by a console control
event (economicspace's campaign, 2026-09), after scheduling it had not fixed
it:

    rc=0x40010004  DBG_CONTROL_BREAK      the queue was a child of an agent
                                          shell; session teardown took the
                                          tree
    rc=0xC000013A  STATUS_CONTROL_C_EXIT  the queue was a scheduled task, but
                                          the task ran `cmd /c ...`, and that
                                          cmd attached to the SHARED console,
                                          so a Ctrl+C aimed at an unrelated
                                          foreground command reached it

In the second, Task Scheduler had re-parented the process and the kill still
arrived, because what propagates a console control event is the CONSOLE, not
the parent. The tell was a literal `^C` written into the queue log, and two
exit codes that both name a console event rather than a fault.

On Windows, DETACHED_PROCESS gives the target no console at all, so there is
no console for an event to arrive on; CREATE_NEW_PROCESS_GROUP additionally
takes it out of the group any Ctrl+C would be broadcast to. Elsewhere the
target starts in a new session, out of the terminal's process group. Its
output goes to the log opened here, so nothing needs a console to write to.

This exits as soon as the child is spawned: holding the child would give a
scheduled task something to wait on, which is the console-owning process this
exists to avoid. Point the scheduled task at the interpreter and this module
DIRECTLY; a `.bat` or `cmd /c` wrapper is a console owner again.
"""
import argparse
import os
import subprocess
import sys

import psutil

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

# How this module appears on a command line when run with `-m`; see
# `already_running` for why the guard must skip such processes.
MODULE_NAME = "quietqueue.supervisor"


def console_python(exe=None):
    """The console interpreter beside `exe` (default `sys.executable`).

    `pythonw.exe` would start a windowless interpreter, but the CHILD is what
    has to be console-free, and the creation flags are what make it so, not
    this name. The console one is kept so the target's output reaches the log.
    """
    exe = sys.executable if exe is None else exe
    return exe.replace("pythonw.exe", "python.exe")


def real_interpreter(exe):
    """The interpreter to spawn for `exe`, and the environment it needs.

    On Windows a venv's `python.exe` is a LAUNCHER: it starts the base
    interpreter as an ordinary child, so the launcher is detached and the
    script, running in that child, has a console again (measured: the
    child's console process list was 1, against 0 for a direct start). So
    for a venv interpreter (one with a `pyvenv.cfg` naming `home` beside its
    folder) this returns the base interpreter in `home` and
    `__PYVENV_LAUNCHER__` set to `exe`, which is what the launcher itself
    passes, and under which the base interpreter runs as the venv (its
    `sys.prefix` and site-packages). Anything else is returned as given.
    """
    if os.name != "nt":
        return exe, {}
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(exe))), "pyvenv.cfg")
    try:
        with open(cfg, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return exe, {}
    for line in lines:
        name, sep, value = line.partition("=")
        if sep and name.strip().lower() == "home":
            base = os.path.join(value.strip(), os.path.basename(exe))
            if os.path.isfile(base):
                return base, {"__PYVENV_LAUNCHER__": exe}
    return exe, {}


def already_running(script, self_names=()):
    """PID of a live process already running `script`, or None.

    A scheduled task that resumes the queue at logon (so a reboot does not
    leave it idle for hours, as one did) also fires on an ordinary log off and
    on, and a SECOND queue would race the first for its output files and its
    ledger: a corrupted job that still reports rc 0.

    `MultipleInstances IgnoreNew` on the task cannot cover this: the supervisor
    exits as soon as it has spawned, so the TASK is never running when the
    trigger fires again; only the detached grandchild is. The check has to look
    at processes, not at the scheduler.

    [!] The target has to be matched as the script being RUN, not merely as a
    word on the command line. A supervisor invoked as `supervise.py
    my_queue.py` has the target on its own command line, and the `py` launcher
    and the Microsoft Store `python` alias compound it: each spawns the real
    python.exe with the SAME arguments, so a naive substring test finds the
    launcher, excluding this pid is not enough, and the guard then refuses to
    start anything at all (measured in economicspace: the first version
    reported a different phantom pid on each call). So a process is skipped
    when its arguments equal this one's, when it runs this module with `-m`,
    or when an argument contains one of `self_names` (the name of a script of
    yours that calls `supervise`). A process runs `script` when an argument's
    file name IS `script`, not merely ends with it.
    """
    me = os.getpid()
    try:
        my_args = [str(part) for part in psutil.Process(me).cmdline()[1:]]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        my_args = None
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if proc.pid == me:
                continue
            parts = [str(part) for part in (proc.info["cmdline"] or ())]
            if my_args is not None and parts[1:] == my_args:
                continue
            if MODULE_NAME in parts:
                continue
            if any(name in part for name in self_names for part in parts):
                continue
            if any(os.path.basename(part) == script for part in parts):
                return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def supervise(target, log, cwd=None, self_names=(), exe=None):
    """Start the script `target` detached from every console; return its pid.

    Returns None, starting nothing, when a process is already running a script
    of the same file name, and says so in `log` and on stdout. The target's
    output is appended to `log`, after a start banner and its pid. `cwd` is
    the directory it runs in (default: this process's); `exe` the interpreter
    (default: the console one beside `sys.executable`; a venv's is started
    through its base interpreter, see `real_interpreter`).
    """
    name = os.path.basename(target)
    running = already_running(name, self_names)
    if running is not None:
        with open(log, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"      supervisor: {name} already running as "
                     f"pid {running}; not starting a second one\n")
        print(f"{name} already running as pid {running}; nothing to do")
        return None

    if os.name == "nt":
        detach = {"creationflags": DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                  | CREATE_NO_WINDOW}
    else:
        detach = {"start_new_session": True}
    interpreter, extra_env = real_interpreter(console_python(exe))
    env = dict(os.environ, **extra_env) if extra_env else None
    with open(log, "a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n===== detached (no console) start: {name} =====\n")
        fh.flush()
        proc = subprocess.Popen(
            [interpreter, target],
            cwd=cwd,
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            **detach,
        )
        fh.write(f"      pid {proc.pid}\n")

    print(f"spawned {name} as pid {proc.pid}, detached")
    return proc.pid


def main(argv=None):
    """`python -m quietqueue.supervisor TARGET --log LOG [--cwd DIR]`.

    Exits 0 whether it started the target or found it already running, which
    is what lets a logon trigger fire on every logon.
    """
    p = argparse.ArgumentParser(prog="python -m quietqueue.supervisor",
                                description="Start TARGET with no console and exit.")
    p.add_argument("target", help="the script to run")
    p.add_argument("--log", required=True, help="file the target's output is appended to")
    p.add_argument("--cwd", default=None, help="directory the target runs in")
    a = p.parse_args(argv)
    supervise(os.path.abspath(a.target), a.log, cwd=a.cwd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
