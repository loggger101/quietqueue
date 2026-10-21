# quietqueue

[![tests](https://github.com/loggger101/quietqueue/actions/workflows/tests.yml/badge.svg)](https://github.com/loggger101/quietqueue/actions/workflows/tests.yml)

Run a queue of long jobs unattended on Windows, and have it survive the things
that kill one: a closed shell, a stray Ctrl+C, a reboot, a second copy started
by a logon trigger, and a pause.

A queue that takes days dies in ways a queue that takes minutes never meets.
quietqueue is four small pieces that each closed one of those:

- **`run_queue`** runs a list of jobs one subprocess each, and skips every job
  a ledger already records as done, so killing and restarting it costs at most
  the job in flight. A failed job is retried on the next run, never skipped.
- **`supervise`** starts the queue with no console, which is the only thing
  that keeps a console control event from reaching it, then exits at once. It
  refuses to start a second copy while one runs.
- **`watch`** samples a family of processes' memory into a CSV every few
  seconds, tagged with the job running, so a memory projection becomes a
  measurement for free.
- **`pause.ps1`** freezes the whole process tree and thaws it later: the cores
  are free at once and the work in flight is kept.

Python 3.9 or later; one dependency, [psutil](https://github.com/giampaolo/psutil).
`pause.ps1` is Windows PowerShell. The rest runs on Linux and macOS too (the
supervisor detaches into a new session there), and CI runs all three.

Extracted from [economicspace](https://github.com/loggger101/economicspace)'s
campaign runner, which ran a 28-job, several-day model campaign; this
repository carries its history.

## Install

```bash
pip install "quietqueue @ git+https://github.com/loggger101/quietqueue@v0.1.0"
```

## Use

**The queue** is a script of yours that builds the jobs and hands them over:

```python
# my_queue.py
import sys
from quietqueue import Job, run_queue

jobs = [Job(key=f"{site}__{mode}", group=site, parts=(site, mode),
            command=[sys.executable, "run_one.py", site, mode])
        for site in ("north", "south") for mode in ("fast", "full")]

sys.exit(run_queue(jobs, "results.csv"))
```

```bash
python my_queue.py                 # run everything outstanding
python my_queue.py --list          # show the queue and stop
python my_queue.py --only south    # only these groups; a misspelt one is refused
```

The ledger contract: **each job appends one row to the ledger when it finishes,
success or failure**, with its key in a `job` column (`key=` names another) and
its exit code in `rc`. The queue only reads the ledger. A row with `rc == 0`
means done; any other row means retry. The ledger is a parameter, not a
command-line flag, because the job decides where its row goes: a queue pointed
at a file the job does not write to finds every job outstanding forever.

**The supervisor** starts the queue detached and exits:

```bash
python -m quietqueue.supervisor my_queue.py --log queue.log --cwd C:\work
```

or `quietqueue.supervise(target, log, cwd)` from a script of your own; pass
that script's name as `self_names=("my_supervisor",)` so the single-instance
guard never mistakes it for the queue.

**The memory watcher**, beside it:

```bash
python -m quietqueue.memwatch --out memory.csv --logs logs --skip _ --once
```

It totals every process whose name contains `--process` (default `python`) and
tags the row with the newest `<job>.log` in `--logs` written to in the last
three minutes. `--skip` names log prefixes that are not jobs. Without `--once`
it samples every `--interval` seconds (default 20) until killed.

**The pause**:

```powershell
powershell -File pause.ps1 -Match '*my_queue*','*memwatch*' -TaskName my_queue
powershell -File pause.ps1 -Match '*my_queue*','*memwatch*' -TaskName my_queue -Resume
```

`python -c "import quietqueue; print(quietqueue.pause_script())"` prints where
the installed copy is.

### Starting it from Task Scheduler

Point the task's action at the **interpreter and the supervisor directly**,
with no `.bat` and no `cmd /c` around them: the wrapper is a console owner, and
a console owner is how the kill arrives (see below). Give it an `AtLogOn`
trigger, so a reboot resumes the queue by itself, and register that trigger
**for your own user**: `New-ScheduledTaskTrigger -AtLogOn` with no `-User`
means any user, which needs elevation and fails with Access denied; `-User
"$env:USERDOMAIN\$env:USERNAME"` does not. economicspace's tasks added a
two-minute delay to the trigger. Re-running the task is always safe: the
supervisor exits 0 without starting anything when the queue is already running.

## Why it looks the way it does

Each of these was met on the campaign this came from, except the venv
launcher, which turned up while testing this package.

- **What delivers a console control event is the console, not the parent.**
  The queue died twice: once as a child of an agent's shell (session teardown,
  `0x40010004` DBG_CONTROL_BREAK), then as a scheduled task running `cmd /c`,
  when a Ctrl+C aimed at an unrelated foreground command reached it
  (`0xC000013A` STATUS_CONTROL_C_EXIT). The scheduler had re-parented it, and
  re-parenting does not move a console. `DETACHED_PROCESS` leaves the queue no
  console for an event to arrive on, and `CREATE_NEW_PROCESS_GROUP` takes it
  out of the group a Ctrl+C is broadcast to. The tells, when it happens: a
  literal `^C` in the queue log, an exit code naming a console event rather
  than a fault, and a job log that stops with no traceback.
- **A machine event looks different.** When the host went down mid-job, the
  queue log stopped mid-job, the memory log stopped in the same minute, no
  `!! job failed` line was written, and every process was gone at once. A
  signature that includes the watcher dying is the machine, not the queue; the
  event log (Kernel-Power 41, 6008) confirms it. Its stamp of the shutdown
  lags the crash.
- **The single-instance guard reads the process table.** The logon trigger
  fires on every log off and on, and two queues writing one output file is a
  corrupted job that still reports `rc 0`. `MultipleInstances IgnoreNew`
  cannot help: the supervisor exits as soon as it spawns, so the task is never
  running when the trigger fires again.
- **The guard compares file names.** The supervisor's own command line names
  the target, and the `py` launcher and the Microsoft Store `python` alias each
  spawn the real interpreter with the same arguments, so a substring test
  found the launcher and refused to start anything (a different phantom pid on
  each call). It skips its own pid, any process whose arguments equal its own,
  `-m quietqueue.supervisor`, and `self_names`; a match is an argument whose
  file name **is** the target.
- **A Windows venv's `python.exe` is a launcher.** It starts the base
  interpreter as an ordinary child, so detaching the launcher left the script
  itself with a console. Found while testing this package inside a venv. The
  supervisor reads the venv's `pyvenv.cfg` and starts the base interpreter
  directly, with `__PYVENV_LAUNCHER__` set as the launcher sets it, under
  which it runs as the venv. The pause counts each process once for the same
  reason: a launcher and its interpreter carry one command line.
- **Only `rc == 0` is done.** A failed job is retried on the next run; tidying
  its row away loses the retry. And a misspelt `--only` used to match nothing
  and report "nothing outstanding", exit 0: a queue that ran nothing and said
  it had finished. It now exits 2.
- **A failed job does not stop the queue.** Over days, one job that cannot run
  is worth far less than the jobs behind it.
- **Nothing that watches the queue should start it.** Anything that only
  reports progress may die with a session; the queue must not. Never start the
  queue from a monitor, a notebook, an agent's background shell, or anything
  that puts a `cmd` between it and the scheduler.
- **The memory watcher counts itself**, and anything else matching that runs
  alongside: two apparent peaks of 11.54 and 10.74 GB were an analysis script,
  not the job. Run analysis between jobs. `process_iter` reports another
  account's process with `memory_info` None rather than raising, which
  crashed the first version.
- **Suspending costs almost no memory.** Windows trims a suspended process's
  working set: a 16-process tree paused 5.7 h into a job held 0.4 GB rather
  than the ~25 GB it had resident, and its CPU went to zero.
- **The pause finds processes by command line, never by a remembered pid**, and
  disarms the logon trigger while paused, or the next logon would restart a
  queue you had stopped. A reboot while paused loses the job in flight, as a
  kill would.
- **A suspend-based pause inflates every wall clock measured across it**,
  including the queue's own `elapsed`. Subtract the gap in the memory log,
  which pauses with everything else, and prefer pausing between jobs when the
  job in flight is cheap to lose.

Two PowerShell traps met while testing `pause.ps1` from Python, neither of
which affects running it by hand: a Python process whose own argv holds a `*`
hangs the `powershell.exe` it starts, and `powershell -Command` turns any
non-zero `exit` into 1 (`-File` keeps it). The tests pass patterns inside
`-Command` and end it with `exit $LASTEXITCODE`.

## Develop

```bash
pip install -e ".[test]"
python -m pytest -q
```

The tests drive the queue against planted ledgers with its subprocesses faked,
the guard against a fake process table, a real detached start (no console on
Windows, a new session elsewhere), the watcher against a planted log directory
and process table, and, on Windows, `pause.ps1` against a real two-process
tree. Each of the traps above that a test covers was planted in a copy of the
package and shown to fail it.

## Licence

MIT; see [LICENSE](LICENSE).
