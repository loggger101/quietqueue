# -*- coding: utf-8 -*-
"""Sample total python RSS every 20 s and record the peak per campaign cell.

Exists because 1.17.7 bounded _CALENDAR_CACHE against a PROJECTED 11-18 GB that
nobody had measured -- no full-catalog run had been made since 1.16.0.  This
turns that projection into a measurement, for free, across the whole campaign.
Appends to campaign/memory.csv; one row per sample.

    python campaign/memwatch.py          # sample until killed
    python campaign/memwatch.py --once   # write one row and stop

`watch()` takes the output file, the log directory a job's name is read from,
the log-name prefixes that are not jobs, the process name it totals and the
interval; the constants below are this campaign's values for them.
"""
import csv
import os
import sys
import time

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "campaign", "memory.csv")
LOG_DIR = os.path.join(ROOT, "campaign", "logs")
# The queue's and the harnesses' own logs start with `_`, and Stage 2's
# pricing logs with `stage2`: neither is a cell.
SKIP_PREFIXES = ("_", "stage2")
PROCESS_NAME = "python"
INTERVAL_S = 20
# A log written to within this long is a job still running.
LIVE_S = 180

HEADER = ["ts", "cell", "n_python", "total_rss_gb", "max_proc_rss_gb", "sys_used_gb"]


def current_cell(log_dir=LOG_DIR, skip=SKIP_PREFIXES, live_s=LIVE_S):
    """Newest job log that was written to in the last `live_s` seconds."""
    best, best_t = "", 0.0
    now = time.time()
    for f in os.listdir(log_dir):
        if not f.endswith(".log") or f.startswith(skip):
            continue
        t = os.path.getmtime(os.path.join(log_dir, f))
        if now - t < live_s and t > best_t:
            best, best_t = f[:-4], t
    return best


def sample(log_dir=LOG_DIR, skip=SKIP_PREFIXES, process_name=PROCESS_NAME):
    """One row: time, current job, and the matching processes' RSS in GB.

    Totals every process whose name contains `process_name`, because Stage 4
    runs a worker pool and the interesting number is the machine's footprint.
    ⚠️  It counts ITSELF and any analysis process running alongside, which is
    how two apparent peaks of 11.54 and 10.74 GB turned out to be measurement
    contamination rather than the pipeline.
    """
    tot = 0.0
    mx = 0.0
    n = 0
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            # process_iter fills a DENIED attribute with None rather
            # than raising, so another account's python reads as None.
            mi = p.info["memory_info"]
            if mi is not None and process_name in (p.info["name"] or "").lower():
                r = mi.rss / 1e9
                tot += r
                mx = max(mx, r)
                n += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    vm = psutil.virtual_memory()
    return [time.strftime("%Y-%m-%d %H:%M:%S"), current_cell(log_dir, skip), n,
            round(tot, 3), round(mx, 3), round((vm.total - vm.available) / 1e9, 3)]


def watch(out, log_dir, skip=SKIP_PREFIXES,
          process_name=PROCESS_NAME, interval_s=INTERVAL_S, once=False):
    """Append one row to `out` every `interval_s` until killed (or once).

    The header is written only when `out` is missing or empty, so a restarted
    watcher carries on the same file.
    """
    new = not os.path.exists(out) or os.path.getsize(out) == 0
    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(HEADER)
        while True:
            w.writerow(sample(log_dir, skip, process_name))
            fh.flush()
            if once:
                return
            time.sleep(interval_s)


def main(argv=None):
    """This campaign's watcher: `memory.csv`, the campaign logs, every 20 s."""
    args = sys.argv[1:] if argv is None else list(argv)
    watch(OUT, LOG_DIR, once="--once" in args)


if __name__ == "__main__":
    main()
