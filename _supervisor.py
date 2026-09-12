# -*- coding: utf-8 -*-
"""Start the campaign queue with NO CONSOLE, then exit immediately.

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
"""
import os
import subprocess
import sys

import psutil

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "campaign", "logs", "_queue.log")
TARGET = os.path.join(ROOT, "campaign", sys.argv[1] if len(sys.argv) > 1 else "run_queue.py")

# `pythonw.exe` would start a windowless interpreter but the CHILD is what has
# to be console-free, so the flags below are what matter, not this name.
exe = sys.executable.replace("pythonw.exe", "python.exe")


def already_running(script):
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
    call.  Any process whose cmdline names this supervisor is an invocation of
    it, never the work it starts.
    """
    me = os.getpid()
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if proc.pid == me:
                continue
            parts = [str(part) for part in (proc.info["cmdline"] or ())]
            if any("_supervisor" in part for part in parts):
                continue
            if any(part.endswith(script) for part in parts):
                return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


running = already_running(os.path.basename(TARGET))
if running is not None:
    with open(LOG, "a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"      supervisor: {os.path.basename(TARGET)} already running as "
                 f"pid {running}; not starting a second one\n")
    print(f"{os.path.basename(TARGET)} already running as pid {running}; nothing to do")
    raise SystemExit(0)

with open(LOG, "a", encoding="utf-8", errors="replace") as fh:
    fh.write(f"\n===== detached (no console) start: {os.path.basename(TARGET)} =====\n")
    fh.flush()
    proc = subprocess.Popen(
        [exe, TARGET],
        cwd=ROOT,
        stdout=fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        close_fds=True,
    )
    fh.write(f"      pid {proc.pid}\n")

print(f"spawned {os.path.basename(TARGET)} as pid {proc.pid}, detached")
