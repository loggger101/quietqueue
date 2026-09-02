# -*- coding: utf-8 -*-
"""Run the campaign queue unattended, resumably.

Reads campaign/results.csv, skips every cell already recorded with rc == 0, and
runs the rest in order via run_cell.py.  Safe to kill and restart: at most the
in-flight cell is lost, because run_cell.py appends its ledger row the moment a
cell finishes.

    py campaign/run_queue.py            # run everything outstanding
    py campaign/run_queue.py --list     # show the queue and stop
    py campaign/run_queue.py --only cislunar lunar_surface
"""
import csv
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
LEDGER = os.path.join(CAMP, "results.csv")

# best case first, then work outward; cheapest cell first within a destination
#
# ⚠️  THIS IS THE 20-CELL CAMPAIGN'S FIVE, NOT EVERY DESTINATION THE MODEL HAS.
# `mars_orbit` (calc 1.18.0) and `geo` (calc 1.19.0) are missing on purpose:
# this list is what campaign/README.md pins its stamps to, and adding two
# destinations turns a 26.1 h campaign into a 28-cell one of roughly 35 h.
# Widening it is a decision, not a fix.  `master.DELIVERY_DESTINATIONS` is the
# live list if you want all of them.
DESTS = ["cislunar", "lunar_surface", "leo", "mars_surface", "earth_surface"]
CELLS = [("raw", "off"), ("raw", "on"), ("benef", "off"), ("benef", "on")]

QUEUE = [(d, o, s) for d in DESTS for (o, s) in CELLS]


def done_cells():
    """Cell names already recorded in the ledger with `rc == 0`.

    Only rc 0 counts as done, so a failed cell is retried on the next run rather
    than silently skipped for the rest of the campaign.
    """
    done = set()
    if not os.path.exists(LEDGER) or os.path.getsize(LEDGER) == 0:
        return done
    with open(LEDGER, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("rc")) == "0":
                done.add(row["cell"])
    return done


def main():
    """Run every outstanding cell in order, one subprocess each.

    A failed cell does NOT stop the queue: over a campaign measured in days, one
    cell that cannot build is worth far less than the nineteen behind it, and
    the ledger records the failure for a later retry.
    """
    args = sys.argv[1:]
    only = []
    if "--only" in args:
        only = args[args.index("--only") + 1:]
    queue = [c for c in QUEUE if not only or c[0] in only]

    done = done_cells()
    todo = [c for c in queue if f"{c[0]}__{c[1]}__search-{c[2]}" not in done]

    print(f"queue: {len(queue)} cells | done: {len(queue) - len(todo)} | to run: {len(todo)}")
    for d, o, s in todo:
        print(f"   - {d}  {o}  search-{s}")
    if "--list" in args:
        return 0
    if not todo:
        print("nothing outstanding.")
        return 0

    t_start = time.time()
    for i, (d, o, s) in enumerate(todo, 1):
        print(f"\n{'=' * 78}\n[{i}/{len(todo)}] {d} | {o} | search-{s}"
              f" | elapsed {(time.time()-t_start)/3600:.2f} h\n{'=' * 78}", flush=True)
        rc = subprocess.call(["py", os.path.join(CAMP, "run_cell.py"), d, o, s], cwd=ROOT)
        if rc != 0:
            print(f"!! cell failed (rc={rc}) -- continuing to next cell", flush=True)
    print(f"\nqueue finished in {(time.time()-t_start)/3600:.2f} h", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
