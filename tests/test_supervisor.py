# -*- coding: utf-8 -*-
"""The single-instance guard against a fake process table, and a real detached start."""
import os
import time
import uuid

import psutil
import pytest

from quietqueue import supervisor
from quietqueue.supervisor import already_running, console_python, supervise

ME = ["C:\\py\\python.exe", "supervise.py", "my_queue.py"]


class FakeProc:
    """A process_iter entry: a pid and an info dict, or an error on access."""

    def __init__(self, pid, cmdline=None, error=None):
        self.pid = pid
        self._cmdline = cmdline
        self._error = error

    @property
    def info(self):
        """The attributes process_iter was asked for; raises when planted to."""
        if self._error:
            raise self._error
        return {"cmdline": self._cmdline}

    def cmdline(self):
        """This process's own command line, for the guard's self-comparison."""
        return list(self._cmdline)


@pytest.fixture
def table(monkeypatch):
    """Install a fake process table; the test fills `rows`. This process is pid 1."""
    rows = []
    me = FakeProc(1, ME)
    monkeypatch.setattr(supervisor.os, "getpid", lambda: 1)
    monkeypatch.setattr(supervisor.psutil, "Process", lambda pid: me)
    monkeypatch.setattr(supervisor.psutil, "process_iter", lambda attrs: [me] + rows)
    return rows


def test_finds_the_target_by_file_name(table):
    """A python running C:\\work\\my_queue.py is the target."""
    table.append(FakeProc(7, ["python.exe", os.path.join("work", "my_queue.py")]))
    assert already_running("my_queue.py") == 7


def test_skips_itself(table):
    """Its own command line names the target; its own pid is never a match."""
    assert already_running("my_queue.py") is None


def test_skips_a_launcher_duplicate(table):
    """py and the Store alias spawn python with the SAME arguments: that is not the target."""
    table.append(FakeProc(8, ["C:\\Windows\\py.exe"] + ME[1:]))
    assert already_running("my_queue.py") is None


def test_skips_module_invocations(table):
    """Another `python -m quietqueue.supervisor my_queue.py` is a supervisor, not the target."""
    table.append(FakeProc(9, ["python", "-m", "quietqueue.supervisor", "my_queue.py", "--log", "q.log"]))
    assert already_running("my_queue.py") is None


def test_self_names_skip_a_calling_script(table):
    """A script of yours that calls supervise() is skipped once named, found otherwise."""
    table.append(FakeProc(10, ["python", "_supervisor.py", "my_queue.py", "--extra"]))
    assert already_running("my_queue.py") == 10
    assert already_running("my_queue.py", self_names=("_supervisor",)) is None


def test_a_suffix_is_not_the_target(table):
    """old_my_queue.py ends with the target's name and is a different script."""
    table.append(FakeProc(11, ["python", "old_my_queue.py"]))
    assert already_running("my_queue.py") is None


def test_unreadable_processes_are_passed_over(table):
    """No cmdline, a vanished process and a denied one are not matches and do not raise."""
    table.extend([FakeProc(12, None), FakeProc(13, error=psutil.NoSuchProcess(13)),
                  FakeProc(14, error=psutil.AccessDenied(14))])
    assert already_running("my_queue.py") is None


@pytest.mark.skipif(os.name != "nt", reason="only Windows venvs start through a launcher")
def test_real_interpreter_sees_through_a_venv(tmp_path):
    """A venv's python.exe is swapped for its base and __PYVENV_LAUNCHER__;
    no pyvenv.cfg, or a home without the interpreter, leaves it alone."""
    base = tmp_path / "base"
    scripts = tmp_path / "venv" / "Scripts"
    base.mkdir()
    scripts.mkdir(parents=True)
    exe = str(scripts / "python.exe")
    assert supervisor.real_interpreter(exe) == (exe, {})
    (tmp_path / "venv" / "pyvenv.cfg").write_text(f"home = {base}\nversion = 3.14.0\n")
    assert supervisor.real_interpreter(exe) == (exe, {})
    (base / "python.exe").write_text("")
    assert supervisor.real_interpreter(exe) == (str(base / "python.exe"),
                                                {"__PYVENV_LAUNCHER__": exe})


@pytest.mark.skipif(os.name == "nt", reason="POSIX behaviour")
def test_real_interpreter_off_windows_is_identity():
    """Off Windows a venv's python is a symlink, not a launcher: nothing to see through."""
    assert supervisor.real_interpreter("/v/bin/python") == ("/v/bin/python", {})


def test_console_python():
    """pythonw is swapped for python; anything else is kept."""
    assert console_python("C:\\P\\pythonw.exe") == "C:\\P\\python.exe"
    assert console_python("/usr/bin/python3") == "/usr/bin/python3"


TARGET = r'''
import os, time
detached = None
if os.name == "nt":
    import ctypes
    # 0 means no console is attached at all.  GetConsoleWindow() is not the
    # test: a console created with CREATE_NO_WINDOW, which an inherited one
    # may be, has no window and still delivers Ctrl+C.
    buf = (ctypes.c_uint32 * 8)()
    detached = ctypes.windll.kernel32.GetConsoleProcessList(buf, 8) == 0
else:
    detached = os.getsid(0) == os.getpid()   # a new session: its own leader
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "up.txt"), "w") as fh:
    fh.write(f"{os.getpid()} {detached}")
print("target says hello", flush=True)
time.sleep(60)
'''


def test_detached_start_and_second_refusal(tmp_path, capsys):
    """A real start: no console (Windows) or its own session (POSIX), output in
    the log, and a second start refused while the first runs."""
    target = tmp_path / f"qq_target_{uuid.uuid4().hex[:8]}.py"
    target.write_text(TARGET)
    log = tmp_path / "queue.log"
    pid = supervise(str(target), str(log), cwd=str(tmp_path))
    try:
        assert isinstance(pid, int)
        assert f"spawned {target.name} as pid {pid}, detached" in capsys.readouterr().out
        up = tmp_path / "up.txt"
        deadline = time.time() + 30
        while not up.exists() and time.time() < deadline:
            time.sleep(0.2)
        child_pid, detached = up.read_text().split()
        # The script itself, or under a venv the base interpreter that the
        # venv's python.exe launcher starts: then the pid returned is the
        # launcher's, and the script runs in its child.
        assert int(child_pid) == pid or int(child_pid) in [
            c.pid for c in psutil.Process(pid).children(recursive=True)]
        assert detached == "True"

        assert supervise(str(target), str(log), cwd=str(tmp_path)) is None
        assert "already running as pid" in capsys.readouterr().out
        deadline = time.time() + 10
        while "target says hello" not in log.read_text() and time.time() < deadline:
            time.sleep(0.2)
        text = log.read_text()
        assert f"===== detached (no console) start: {target.name} =====" in text
        assert f"      pid {pid}\n" in text
        assert "target says hello" in text
        assert "not starting a second one" in text
    finally:
        try:
            parent = psutil.Process(pid)
            for p in parent.children(recursive=True) + [parent]:
                p.kill()
        except psutil.NoSuchProcess:
            pass


def test_main_exits_zero(tmp_path, monkeypatch):
    """The command line exits 0 when the target is already running, too."""
    monkeypatch.setattr(supervisor, "already_running", lambda *a, **k: 4242)
    assert supervisor.main([str(tmp_path / "t.py"), "--log", str(tmp_path / "l.log")]) == 0
    assert "pid 4242" in (tmp_path / "l.log").read_text()
