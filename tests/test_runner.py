# -*- coding: utf-8 -*-
"""run_queue against planted ledgers, with every job's subprocess faked."""
import pytest

from quietqueue import runner
from quietqueue.runner import Job, done_keys, run_queue

GROUPS = ["cislunar", "geo", "leo"]
JOBS = [Job(f"{g}__{o}", g, (g, o), ["python", "run_cell.py", g, o])
        for g in GROUPS for o in ("raw", "benef")]


class FakeCall:
    """Stands in for subprocess.call: records each command, fails the ones in `fail`."""

    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def __call__(self, cmd, cwd=None):
        """Record one job; return its planted exit code."""
        self.calls.append((list(cmd), cwd))
        return 3 if len(self.calls) in self.fail else 0


@pytest.fixture
def fake(monkeypatch):
    """A FakeCall installed as the runner's subprocess.call."""
    f = FakeCall()
    monkeypatch.setattr(runner.subprocess, "call", f)
    return f


def ledger(tmp_path, rows, header="job,rc"):
    """Write a ledger of `rows` (key, rc) and return its path."""
    p = tmp_path / "results.csv"
    p.write_text(header + "\n" + "".join(f"{k},{rc}\n" for k, rc in rows), encoding="utf-8")
    return str(p)


def test_missing_and_empty_ledger_mean_nothing_done(tmp_path):
    """No ledger, or a zero-byte one, is a queue with nothing done."""
    assert done_keys(str(tmp_path / "absent.csv")) == set()
    (tmp_path / "empty.csv").write_text("")
    assert done_keys(str(tmp_path / "empty.csv")) == set()


def test_only_rc_zero_counts_as_done(tmp_path):
    """A failed row and a blank rc are both outstanding; a later success wins."""
    p = ledger(tmp_path, [("a", 0), ("b", 1), ("c", ""), ("d", 3), ("d", 0)])
    assert done_keys(p) == {"a", "d"}


def test_key_column_is_a_parameter(tmp_path):
    """The key is read from the column named, not from `job`."""
    p = ledger(tmp_path, [("x", 0)], header="cell,rc")
    assert done_keys(p, key="cell") == {"x"}


def test_failed_row_is_retried(tmp_path, fake):
    """A job whose only row failed runs again; a done one does not."""
    p = ledger(tmp_path, [("cislunar__raw", 0), ("cislunar__benef", 1)])
    assert run_queue(JOBS, p, argv=["--only", "cislunar"]) == 0
    assert [c[0][-2:] for c in fake.calls] == [["cislunar", "benef"]]


def test_a_failure_does_not_stop_the_queue(tmp_path, monkeypatch, capsys):
    """The second job fails; every job behind it still runs."""
    f = FakeCall(fail={2})
    monkeypatch.setattr(runner.subprocess, "call", f)
    assert run_queue(JOBS, str(tmp_path / "none.csv"), argv=[]) == 0
    assert len(f.calls) == len(JOBS)
    assert "!! job failed (rc=3) -- continuing to next job" in capsys.readouterr().out


def test_list_runs_nothing(tmp_path, fake, capsys):
    """--list prints the outstanding jobs and starts none."""
    assert run_queue(JOBS, str(tmp_path / "none.csv"), argv=["--list"]) == 0
    out = capsys.readouterr().out
    assert fake.calls == []
    assert out.startswith("queue: 6 jobs | done: 0 | to run: 6\n")
    assert "   - geo  benef\n" in out


@pytest.mark.parametrize("argv", [["--only", "cislunr"], ["--only"], ["--only", "--list"],
                                  ["--only", "geo", "cislunr", "--list"]])
def test_bad_only_is_refused(tmp_path, fake, capsys, argv):
    """A misspelt or empty --only exits 2 and names the groups, running nothing."""
    assert run_queue(JOBS, str(tmp_path / "none.csv"), argv=argv) == 2
    out = capsys.readouterr().out
    assert out.startswith("--only takes groups from: cislunar geo leo")
    assert fake.calls == []


def test_only_selects_groups_in_queue_order(tmp_path, fake):
    """--only leo geo runs geo's jobs then leo's: queue order, not argument order."""
    run_queue(JOBS, str(tmp_path / "none.csv"), argv=["--only", "leo", "geo"])
    assert [c[0][2] for c in fake.calls] == ["geo", "geo", "leo", "leo"]


def test_commands_and_cwd_pass_through(tmp_path, fake):
    """Each job runs as its own argv, in `cwd`."""
    run_queue(JOBS[:1], str(tmp_path / "none.csv"), cwd="somewhere", argv=[])
    assert fake.calls == [(["python", "run_cell.py", "cislunar", "raw"], "somewhere")]


def test_nothing_outstanding(tmp_path, fake, capsys):
    """A ledger with every job done runs nothing and says so."""
    p = ledger(tmp_path, [(j.key, 0) for j in JOBS])
    assert run_queue(JOBS, p, argv=[]) == 0
    assert capsys.readouterr().out.endswith("nothing outstanding.\n")
    assert fake.calls == []


def test_words_are_parameters(tmp_path, fake, capsys):
    """`unit` and `group_noun` reach the progress lines."""
    run_queue(JOBS, str(tmp_path / "none.csv"), argv=["--only", "x"],
              unit="cell", group_noun="destinations")
    assert capsys.readouterr().out.startswith("--only takes destinations from:")
    run_queue(JOBS[:2], str(tmp_path / "none.csv"), argv=[], unit="cell")
    out = capsys.readouterr().out
    assert "queue: 2 cells" in out and "[1/2] cislunar | raw | elapsed 0.00 h" in out
