# CLAUDE.md: working in this repo

quietqueue is four pieces in `quietqueue/` (`runner.py`, `supervisor.py`,
`memwatch.py`, `pause.ps1`) and their tests. Most of the code is a trap with
its reason beside it; README's "Why it looks the way it does" is the list.
Rules:

- **psutil and the standard library only, ASCII only, a docstring on every
  definition.** `tests/test_rules.py` enforces all three. The supervisor is
  the one process that must not fail.
- **The queue only reads the ledger; the job writes it.** Never give
  `run_queue` a command-line flag for the ledger path, and never treat any
  `rc` but `"0"` as done.
- **Do not "simplify" these**, each of which was a real bug: matching the
  guard's target by substring or suffix instead of file name; dropping any of
  the guard's skips (own pid, equal arguments, `-m quietqueue.supervisor`,
  `self_names`); a `.bat` or `cmd /c` between the scheduler and the
  supervisor; holding the child instead of exiting; `memory_info` assumed
  non-None; `[Parameter(Mandatory)]` in `pause.ps1` (it prompts, and a prompt
  hangs a scheduler); freezing roots without their descendants; spawning a
  Windows venv's `python.exe` instead of `real_interpreter`'s base (the
  launcher is detached, the script is not). CI's `venv` job is the only leg
  that runs inside a venv.
- **`__init__` resolves its names lazily.** An eager `from .supervisor import`
  there makes `python -m quietqueue.supervisor` run the module twice.
- **A new trap gets a planted test.** Re-introduce the bug in a copy of the
  package and show its test fails before trusting the test's pass.
- **Testing `pause.ps1` from Python**: pass patterns inside `-Command`, never
  in the Python process's own argv (a `*` there hangs the child powershell),
  and end the command with `exit $LASTEXITCODE`.
- **The version is written once**, `quietqueue.__version__`; `pyproject.toml`
  reads it. A release bumps it, adds a CHANGELOG entry, and tags `vX.Y.Z`.
  Consumers pin the tag (economicspace: `requirements-campaign.txt`, and its
  `campaign/quietqueue_pin.py` refuses any other installed version rather
  than installing one).
- The tree lives in OneDrive. `*-DESKTOP-*` files are sync-conflict copies:
  diff, then delete; never commit one. Never `git stash`.
