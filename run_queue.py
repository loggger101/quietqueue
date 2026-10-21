# -*- coding: utf-8 -*-
"""Run the campaign queue unattended, resumably.

Reads campaign/results.csv, skips every cell already recorded with rc == 0, and
runs the rest in order via run_cell.py.  Safe to kill and restart: at most the
in-flight cell is lost, because run_cell.py appends its ledger row the moment a
cell finishes.

    python campaign/run_queue.py            # run everything outstanding
    python campaign/run_queue.py --list     # show the queue and stop
    python campaign/run_queue.py --only cislunar lunar_surface

The runner itself, `run_queue()`, knows nothing about cells: it takes a list
of `Job`s (a ledger key, a group `--only` selects by, the parts its progress
lines print, and the command that runs it) and the ledger path, and runs every
job whose key is not yet in the ledger with `rc == 0`.  What is this
campaign's is below it: `DESTS`, `CELLS`, how a cell is named and the
`run_cell.py` command that runs one.

The queue only READS the ledger; the command writes it.  So the ledger is a
parameter here and never a command-line flag: pointing the queue at a file the
command does not append to would make every job look outstanding forever.
"""
import collections
import csv
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
LEDGER = os.path.join(CAMP, "results.csv")
RUN_CELL = os.path.join(CAMP, "run_cell.py")

# Best case first, then work outward; cheapest cell first within a destination.
# `geo` and `mars_orbit` are third and fourth rather than last because, when
# the 2026-09 campaign was queued, no cell had ever been run at either, and a
# campaign measured in days should learn its unknowns early.  That campaign
# measured them (MEASURED_DEST_SECONDS), so the order is kept for continuity,
# not need.  `gto` joins this list only once a cell is measured.
DESTS = ["cislunar", "lunar_surface", "geo", "mars_orbit",
         "leo", "mars_surface", "earth_surface"]
CELLS = [("raw", "off"), ("raw", "on"), ("benef", "off"), ("benef", "on")]

QUEUE = [(d, o, s) for d in DESTS for (o, s) in CELLS]

# One unit of work.  `key` is the value the command writes into the ledger's
# key column when it finishes; `group` is what `--only` selects by; `parts`
# are printed joined by two spaces in the queue listing and by " | " in the
# banner before the job runs; `command` is the argv it runs as.
Job = collections.namedtuple("Job", "key group parts command")


def cell_jobs(queue=None):
    """This campaign's queue as `Job`s, one `run_cell.py` call per cell.

    The key is the cell name `run_cell.py` writes into the ledger's `cell`
    column, `<dest>__<ore>__search-<off|on>`; the two are built separately,
    so a change to one is a change to both.
    """
    return [Job(f"{d}__{o}__search-{s}", d, (d, o, f"search-{s}"),
                [sys.executable, RUN_CELL, d, o, s])
            for d, o, s in (QUEUE if queue is None else queue)]


def done_keys(ledger, key="cell"):
    """Keys already recorded in the ledger with `rc == 0`.

    Only rc 0 counts as done, so a failed job is retried on the next run rather
    than silently skipped for the rest of the campaign.  A missing or empty
    ledger means nothing is done.
    """
    done = set()
    if not os.path.exists(ledger) or os.path.getsize(ledger) == 0:
        return done
    with open(ledger, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("rc")) == "0":
                done.add(row[key])
    return done


def run_queue(jobs, ledger, *, key="cell", cwd=None, argv=None,
              unit="cell", group_noun="destinations"):
    """Run every outstanding job in order, one subprocess each.

    `argv` takes `--list` (print the queue and stop) and `--only GROUP ...`;
    the groups `--only` accepts are those the jobs carry, in queue order.
    `unit` and `group_noun` are only words in the progress lines.

    A failed job does NOT stop the queue: over a campaign measured in days, one
    cell that cannot build is worth far less than the cells behind it, and
    the ledger records the failure for a later retry.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    groups = list(dict.fromkeys(job.group for job in jobs))
    only = []
    if "--only" in args:
        only = [a for a in args[args.index("--only") + 1:] if a != "--list"]
        # A misspelt name used to match nothing and report an empty queue as
        # "nothing outstanding", exit 0: a campaign that ran no cell and said
        # it was finished.
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


def main(argv=None):
    """This campaign's queue against this campaign's ledger."""
    return run_queue(cell_jobs(), LEDGER, cwd=ROOT, argv=argv)


if __name__ == "__main__":
    sys.exit(main())
