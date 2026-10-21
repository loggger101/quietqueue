# -*- coding: utf-8 -*-
"""memwatch against a planted log directory and a fake process table."""
import csv
import os
import time

import pytest

from quietqueue import memwatch


class Mi:
    """A memory_info with only the field memwatch reads."""

    def __init__(self, gb):
        self.rss = gb * 1e9


class Gone(dict):
    """An info dict for a process that vanished mid-iteration."""

    def __getitem__(self, k):
        raise memwatch.psutil.NoSuchProcess(99)


class P:
    """A process_iter entry."""

    def __init__(self, info):
        self.info = info


TABLE = [P({"name": "python.exe", "memory_info": Mi(1.25)}),
         P({"name": "pythonw.exe", "memory_info": Mi(0.5)}),
         P({"name": "Python", "memory_info": Mi(2.0004)}),
         P({"name": "chrome.exe", "memory_info": Mi(9.0)}),
         # another account's python: process_iter fills a denied field with None
         P({"name": "python.exe", "memory_info": None}),
         P({"name": None, "memory_info": Mi(3.0)}),
         P(Gone())]


class Vm:
    """virtual_memory(): 68.6 GB total, 30.1234 GB available."""
    total = 68.6e9
    available = 30.1234e9


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """A log directory with live, stale and non-job logs, and the fake table installed."""
    d = tmp_path / "logs"
    d.mkdir()
    now = time.time()
    for name, age in {"cislunar__raw.log": 30, "cislunar__benef.log": 120,
                      "geo__raw.log": 600, "_queue.log": 1, "stage2_geo.log": 2,
                      "leo__raw.txt": 1}.items():
        p = d / name
        p.write_text("x")
        os.utime(p, (now - age, now - age))
    monkeypatch.setattr(memwatch.psutil, "process_iter", lambda attrs: TABLE)
    monkeypatch.setattr(memwatch.psutil, "virtual_memory", lambda: Vm())
    return str(d)


def test_current_job_is_the_newest_live_job_log(logs):
    """Skipped prefixes and non-.log files are passed over; the newest live log wins."""
    assert memwatch.current_job(logs, skip=("_", "stage2")) == "cislunar__raw"


def test_skip_prefixes_matter(logs):
    """Without the prefixes, the queue's own log is taken for a job."""
    assert memwatch.current_job(logs) == "_queue"


def test_nothing_live(logs):
    """With a 10 s window nothing but the skipped logs is live: no job."""
    assert memwatch.current_job(logs, skip=("_", "stage2"), live_s=10) == ""


def test_sample_totals_the_family(logs):
    """Three pythons count (case-insensitive); the denied one, the vanished one,
    the nameless one and chrome do not."""
    row = memwatch.sample(logs, skip=("_", "stage2"))
    assert row[1:] == ["cislunar__raw", 3, 3.75, 2.0, 38.477]


def test_once_writes_header_and_one_row(logs, tmp_path):
    """--once: a header and one row, and a second run appends with no second header."""
    out = str(tmp_path / "memory.csv")
    memwatch.main(["--out", out, "--logs", logs, "--skip", "_", "--skip", "stage2", "--once"])
    memwatch.main(["--out", out, "--logs", logs, "--skip", "_", "--skip", "stage2", "--once"])
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == memwatch.COLUMNS
    assert len(rows) == 3 and all(r[1] == "cislunar__raw" for r in rows[1:])


def test_columns_are_a_parameter(logs, tmp_path):
    """A consumer's own column names head the file."""
    out = str(tmp_path / "m.csv")
    names = ["ts", "cell", "n_python", "total_rss_gb", "max_proc_rss_gb", "sys_used_gb"]
    memwatch.watch(out, logs, once=True, columns=names)
    assert open(out, encoding="utf-8").readline().strip() == ",".join(names)


def test_loop_sleeps_between_rows(logs, tmp_path, monkeypatch):
    """Without once, it samples, flushes and sleeps the interval, until stopped."""
    sleeps = []

    class Stop(Exception):
        """Raised by the third sleep to end the loop."""

    def fake_sleep(s):
        """Record the interval; stop on the third call."""
        sleeps.append(s)
        if len(sleeps) == 3:
            raise Stop()

    monkeypatch.setattr(memwatch.time, "sleep", fake_sleep)
    out = str(tmp_path / "m.csv")
    with pytest.raises(Stop):
        memwatch.watch(out, logs, interval_s=7)
    assert sleeps == [7, 7, 7]
    assert len(open(out, encoding="utf-8").read().splitlines()) == 4
