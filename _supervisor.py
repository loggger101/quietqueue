# -*- coding: utf-8 -*-
"""Start the campaign queue with NO CONSOLE, then exit immediately.

    python.exe campaign/_supervisor.py [run_queue.py | memwatch.py]

A campaign measured in days has now been killed twice by a console control
event, and scheduling alone did not fix it:

    2026-09-09  rc=0x40010004  DBG_CONTROL_BREAK      queue was a child of an
                                                      agent shell; session
                                                      teardown took the tree
    2026-09-11  rc=0xC000013A  STATUS_CONTROL_C_EXIT  queue was a scheduled
                                                      task, but the task ran
                                                      `cmd /c ...`, and that
                                                      cmd attached to the
                                                      SHARED console -- so a
                                                      Ctrl+C aimed at an
                                                      unrelated foreground
                                                      command reached it

The second is the instructive one: Task Scheduler re-parented the process and
the kill still arrived, because what propagates a console control event is the
CONSOLE, not the parent.  The tell was a literal `^C` written into the queue
log, and two exit codes that both name a console event rather than a fault.

DETACHED_PROCESS gives the queue no console at all, so there is no console for
an event to arrive on; CREATE_NEW_PROCESS_GROUP additionally takes it out of
the group any Ctrl+C would be broadcast to.  Stage 4's own output already goes
to a per-cell file, and the queue's goes to the handle opened here, so nothing
needs a console to write to.

This exits as soon as the child is spawned: holding the child would give the
scheduled task something to wait on, which is the console-owning process this
exists to avoid.

`supervise()` is the part that knows nothing about the campaign: a target
script, the log its output goes to, the directory it runs in, and the name
this supervisor's own command line carries.  The constants below are this
campaign's values for them, and the scheduled tasks name only this file.
"""
import os
import subprocess
import sys

import psutil

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
LOG = os.path.join(CAMP, "logs", "_queue.log")
DEFAULT_TARGET = "run_queue.py"
# What every invocation of this supervisor has on its command line; see
# `already_running` for why the guard must skip such processes.
SELF_NAME = "_supervisor"

# `pythonw.exe` would start a windowless interpreter but the CHILD is what has
# to be console-free, so the flags below are what matter, not this name.
exe = sys.executable.replace("pythonw.exe", "python.exe")


def already_running(script, self_name=SELF_NAME):
    """PID of a live process already running `script`, or None.

    The tasks carry an AtLogOn trigger so a reboot resumes the campaign by
    itself -- the machine went down mid-cell on 2026-09-11 and sat idle five
    hours because nothing restarted it.  That trigger also fires on an ordinary
    log off and on, though, and a SECOND queue would race the first for one
    `profitability_catalog.csv` and one ledger.  Two runs writing one output
    file is a corrupted cell that still reports rc 0, which is the quiet wrong
    answer this repo names as its fifth defect class.

    `MultipleInstances IgnoreNew` on the task cannot cover this: the supervisor
    exits as soon as it has spawned, so the TASK is never running when the
    trigger fires again -- only the detached grandchild is.  The check has to
    look at processes, not at the scheduler.

    ⚠️  The target's name has to be matched as the script being RUN, not merely
    as a word on the command line.  This supervisor is invoked as
    `_supervisor.py run_queue.py`, so its own cmdline contains the target, and
    `py` compounds it: the launcher spawns python.exe with the SAME arguments,
    so a naive substring test finds the launcher, excluding self is not enough,
    and the guard then refuses to start anything at all.  Measured, not
    predicted -- the first version reported a different phantom pid on each
    call.  Any process whose cmdline names this supervisor (`self_name`) is an
    invocation of it, never the work it starts.
    """
    me = os.getpid()
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if proc.pid == me:
                continue
            parts = [str(part) for part in (proc.info["cmdline"] or ())]
            if any(self_name in part for part in parts):
                continue
            if any(part.endswith(script) for part in parts):
                return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def supervise(target, log=LOG, cwd=ROOT, self_name=SELF_NAME):
    """Start `target` detached from every console; return its pid.

    Returns None, starting nothing, when a process is already running a script
    of the same name, and says so in `log` and on stdout.  `target`'s output
    goes to `log`, appended, between a start banner and its pid.
    """
    name = os.path.basename(target)
    running = already_running(name, self_name)
    if running is not None:
        with open(log, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"      supervisor: {name} already running as "
                     f"pid {running}; not starting a second one\n")
        print(f"{name} already running as pid {running}; nothing to do")
        return None

    with open(log, "a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n===== detached (no console) start: {name} =====\n")
        fh.flush()
        proc = subprocess.Popen(
            [exe, target],
            cwd=cwd,
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
            close_fds=True,
        )
        fh.write(f"      pid {proc.pid}\n")

    print(f"spawned {name} as pid {proc.pid}, detached")
    return proc.pid


def main(argv=None):
    """Supervise `campaign/<argv[0]>`, `run_queue.py` when none is given.

    Exits 0 whether it started the target or found it already running, which
    is what lets the AtLogOn trigger fire on every logon.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    supervise(os.path.join(CAMP, args[0] if args else DEFAULT_TARGET))
    return 0


if __name__ == "__main__":
    sys.exit(main())
