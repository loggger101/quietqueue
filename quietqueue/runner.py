# -*- coding: utf-8 -*-
"""Run a queue of long jobs unattended, resumably.

    from quietqueue import Job, run_queue

    jobs = [Job("cislunar__raw", "cislunar", ("cislunar", "raw"),
                [sys.executable, "run_cell.py", "cislunar", "raw"]), ...]
    sys.exit(run_queue(jobs, "results.csv"))

and then, from the script that holds those lines:

    python my_queue.py                    # run everything outstanding
    python my_queue.py --list             # show the queue and stop
    python my_queue.py --only cislunar    # only these groups

Each job is one subprocess. The ledger is a CSV the JOB writes, one row per
finished job, carrying the job's key (in the column `key` names, `job` by
default) and its exit code in an `rc` column; the
queue only reads it, and skips every job whose key has a row with `rc == 0`.
So it is safe to kill and restart: at most the in-flight job is lost, as long
as each job appends its row the moment it finishes.

The ledger is a parameter, never a command-line flag: the job decides where its
row goes, and a queue pointed at a file the job does not append to would find
every job outstanding forever.

Built for economicspace's campaign, where one job is a 0.5-8 h model run and a
queue is twenty-eight of them over several days.
"""
import collections
import csv
import os
import subprocess
import sys
import time

# One unit of work. `key` is the value the job writes into the ledger's key
# column when it finishes; `group` is what `--only` selects by; `parts` are
# printed joined by two spaces in the queue listing and by " | " in the banner
# before the job runs; `command` is the argv it runs as.
Job = collections.namedtuple("Job", "key group parts command")


def done_keys(ledger, key="job"):
    """Keys already recorded in the ledger with `rc == 0`.

    Only rc 0 counts as done, so a failed job is retried on the next run rather
    than silently skipped for the rest of the queue. A missing or empty ledger
    means nothing is done.
    """
    done = set()
    if not os.path.exists(ledger) or os.path.getsize(ledger) == 0:
        return done
    with open(ledger, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("rc")) == "0":
                done.add(row[key])
    return done


def run_queue(jobs, ledger, *, key="job", cwd=None, argv=None,
              unit="job", group_noun="groups"):
    """Run every outstanding job in order, one subprocess each.

    `argv` (default `sys.argv[1:]`) takes `--list` (print the queue and stop)
    and `--only GROUP ...`; the groups `--only` accepts are those the jobs
    carry, in queue order. `key` is the ledger's key column, `cwd` the
    directory each job runs in. `unit` and `group_noun` are only words in the
    progress lines. Returns the exit code: 0, or 2 for a bad `--only`.

    A failed job does NOT stop the queue: over a queue measured in days, one
    job that cannot run is worth far less than the jobs behind it, and the
    ledger records the failure for a later retry.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    groups = list(dict.fromkeys(job.group for job in jobs))
    only = []
    if "--only" in args:
        only = [a for a in args[args.index("--only") + 1:] if a != "--list"]
        # A misspelt name used to match nothing and report an empty queue as
        # "nothing outstanding", exit 0: a queue that ran nothing and said it
        # was finished.
        unknown = [g for g in only if g not in groups]
        if unknown or not only:
            print(f"--only takes {group_noun} from: {' '.join(groups)}"
                  f"{'; not ' + ' '.join(unknown) if unknown else ''}")
            return 2
    queue = [job for job in jobs if not only or job.group in only]

    done = done_keys(ledger, key)
    todo = [job for job in queue if job.key not in done]

    print(f"queue: {len(queue)} {unit}s | done: {len(queue) - len(todo)} | to run: {len(todo)}")
    for job in todo:
        print("   - " + "  ".join(job.parts))
    if "--list" in args:
        return 0
    if not todo:
        print("nothing outstanding.")
        return 0

    t_start = time.time()
    for i, job in enumerate(todo, 1):
        print(f"\n{'=' * 78}\n[{i}/{len(todo)}] {' | '.join(job.parts)}"
              f" | elapsed {(time.time()-t_start)/3600:.2f} h\n{'=' * 78}", flush=True)
        rc = subprocess.call(job.command, cwd=cwd)
        if rc != 0:
            print(f"!! {unit} failed (rc={rc}) -- continuing to next {unit}", flush=True)
    print(f"\nqueue finished in {(time.time()-t_start)/3600:.2f} h", flush=True)
    return 0
