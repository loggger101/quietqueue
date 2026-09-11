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

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "campaign", "logs", "_queue.log")
TARGET = os.path.join(ROOT, "campaign", sys.argv[1] if len(sys.argv) > 1 else "run_queue.py")

# `pythonw.exe` would start a windowless interpreter but the CHILD is what has
# to be console-free, so the flags below are what matter, not this name.
exe = sys.executable.replace("pythonw.exe", "python.exe")

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
