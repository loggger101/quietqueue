# -*- coding: utf-8 -*-
"""Sample total python RSS every 20 s and record the peak per campaign cell.

Exists because 1.17.7 bounded _CALENDAR_CACHE against a PROJECTED 11-18 GB that
nobody had measured -- no full-catalog run had been made since 1.16.0.  This
turns that projection into a measurement, for free, across the whole campaign.
Appends to campaign/memory.csv; one row per sample.
"""
import csv
import os
import time

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "campaign", "memory.csv")
LOG_DIR = os.path.join(ROOT, "campaign", "logs")


def current_cell():
    """Newest cell log that was written to in the last 3 minutes."""
    best, best_t = "", 0.0
    now = time.time()
    for f in os.listdir(LOG_DIR):
        if not f.endswith(".log") or f.startswith("_") or f.startswith("stage2"):
            continue
        t = os.path.getmtime(os.path.join(LOG_DIR, f))
        if now - t < 180 and t > best_t:
            best, best_t = f[:-4], t
    return best


def main():
    new = not os.path.exists(OUT) or os.path.getsize(OUT) == 0
    with open(OUT, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ts", "cell", "n_python", "total_rss_gb", "max_proc_rss_gb", "sys_used_gb"])
        while True:
            tot = 0.0
            mx = 0.0
            n = 0
            for p in psutil.process_iter(["name", "memory_info"]):
                try:
                    if "python" in (p.info["name"] or "").lower():
                        r = p.info["memory_info"].rss / 1e9
                        tot += r
                        mx = max(mx, r)
                        n += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            vm = psutil.virtual_memory()
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), current_cell(), n,
                        round(tot, 3), round(mx, 3), round((vm.total - vm.available) / 1e9, 3)])
            fh.flush()
            time.sleep(20)


if __name__ == "__main__":
    main()
