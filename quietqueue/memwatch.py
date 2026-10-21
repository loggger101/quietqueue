# -*- coding: utf-8 -*-
"""Sample the total RSS of a family of processes, tagged with the job running.

    python -m quietqueue.memwatch --out memory.csv --logs logs/ [--once]

Appends one CSV row per sample: time, the job running, how many processes
matched, their total and largest RSS, and the machine's memory in use, in GB.
The job running is the newest `<job>.log` in the log directory written to in
the last few minutes, so a queue whose jobs each write their own log tags
every sample for free.

Built for economicspace's campaign, where a cache had been bounded against a
PROJECTED 11-18 GB that nobody had measured; this turned the projection into a
measurement across the whole campaign.
"""
import argparse
import csv
import os
import sys
import time

import psutil

INTERVAL_S = 20
# A log written to within this long is a job still running.
LIVE_S = 180
COLUMNS = ["ts", "job", "n_procs", "total_rss_gb", "max_proc_rss_gb", "sys_used_gb"]


def current_job(log_dir, skip=(), live_s=LIVE_S):
    """Newest job log written to in the last `live_s` seconds, without `.log`.

    Logs whose names start with one of `skip` are not jobs (a queue's own log,
    say) and are passed over; so is anything not ending in `.log`. "" when no
    job log is live.
    """
    best, best_t = "", 0.0
    now = time.time()
    for f in os.listdir(log_dir):
        if not f.endswith(".log") or f.startswith(tuple(skip)):
            continue
        t = os.path.getmtime(os.path.join(log_dir, f))
        if now - t < live_s and t > best_t:
            best, best_t = f[:-4], t
    return best


def sample(log_dir, skip=(), process_name="python"):
    """One row: time, current job, and the matching processes' RSS in GB.

    Totals every process whose name contains `process_name` (case-insensitive),
    because a job that runs a worker pool has a footprint no one process shows.
    [!] It counts ITSELF and anything else matching that runs alongside, an
    analysis script, say: in economicspace two apparent peaks of 11.54 and
    10.74 GB turned out to be that contamination, not the job.
    """
    tot = 0.0
    mx = 0.0
    n = 0
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            # process_iter fills a DENIED attribute with None rather
            # than raising, so another account's process reads as None.
            mi = p.info["memory_info"]
            if mi is not None and process_name.lower() in (p.info["name"] or "").lower():
                r = mi.rss / 1e9
                tot += r
                mx = max(mx, r)
                n += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    vm = psutil.virtual_memory()
    return [time.strftime("%Y-%m-%d %H:%M:%S"), current_job(log_dir, skip), n,
            round(tot, 3), round(mx, 3), round((vm.total - vm.available) / 1e9, 3)]


def watch(out, log_dir, skip=(), process_name="python",
          interval_s=INTERVAL_S, once=False, columns=None):
    """Append one row to `out` every `interval_s` until killed (or once).

    The header, `columns` (default `COLUMNS`; six names, in `sample`'s order),
    is written only when `out` is missing or empty, so a restarted watcher
    carries on the same file.
    """
    new = not os.path.exists(out) or os.path.getsize(out) == 0
    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(COLUMNS if columns is None else columns)
        while True:
            w.writerow(sample(log_dir, skip, process_name))
            fh.flush()
            if once:
                return
            time.sleep(interval_s)


def main(argv=None):
    """`python -m quietqueue.memwatch --out CSV --logs DIR [options]`."""
    p = argparse.ArgumentParser(prog="python -m quietqueue.memwatch",
                                description="Sample process RSS into a CSV.")
    p.add_argument("--out", required=True, help="CSV appended to")
    p.add_argument("--logs", required=True, help="directory of per-job <job>.log files")
    p.add_argument("--skip", action="append", default=[], metavar="PREFIX",
                   help="log-name prefix that is not a job (repeatable)")
    p.add_argument("--process", default="python", help="process-name substring to total")
    p.add_argument("--interval", type=float, default=INTERVAL_S, help="seconds between rows")
    p.add_argument("--once", action="store_true", help="write one row and stop")
    a = p.parse_args(argv)
    watch(a.out, a.logs, a.skip, a.process, a.interval, a.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
