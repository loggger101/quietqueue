# Changelog

## Unreleased

No code or printed output changed; nothing a consumer pinning v0.1.0 runs is
different.

- `.githooks/`: samebytes' stat-cache hook (this tree lives in OneDrive), its
  `eol=lf` pin in `.gitattributes`, and a CI job, `hooks`, that holds the
  copies to the samebytes tag it names.
- CI: `actions/checkout` and `actions/setup-python` at v7, which run on
  Node.js 24; v4 and v5 targeted Node.js 20, which the runners deprecate.
- `pyproject.toml`: Changelog and Issues links, and the macOS and monitoring
  classifiers.
- `tests/test_rules.py` runs its rules through `samebytes.source` (v0.3.0, a
  test extra), the copy the family shares. The import rule now answers on
  Python 3.9 instead of skipping there.
- README and docstrings: the traps' headings as plain statements, and the
  runner's usage example as generic as the README's (it still named the
  campaign's group and `run_cell.py`). CLAUDE.md names the consumer's pin
  files.

## v0.1.0 (2026-10-20)

First release: economicspace's campaign runner (`campaign/run_queue.py`,
`_supervisor.py`, `memwatch.py` and `_pause.ps1` as of economicspace d68a5a2),
made into a package. The twelve commits that built them are replayed at the
start of this repository's history, limited to those files.

What changed in moving it:

- **Generic.** economicspace's step 1 (its #161) had already turned each
  file's constants into parameters; here the campaign's own values (its
  destinations and cells, `results.csv`, `run_cell.py`, its log names and
  task name) are gone, and the defaults are generic: the ledger's key column
  is `job`, memwatch's columns are `job` and `n_procs`, `pause.ps1` names no
  task. `python -m quietqueue.supervisor` and `python -m quietqueue.memwatch`
  are command lines over them.
- **The guard is stricter about what the target is.** It matches an argument
  whose file name is the target, where economicspace matched any argument
  ending with it (`old_my_queue.py` would have counted). It also skips a
  process whose arguments equal its own, which covers the `py` launcher's and
  the Store alias's duplicate without naming the supervisor, and
  `-m quietqueue.supervisor`; a calling script is named in `self_names`.
- **POSIX detaches too**, into a new session; economicspace only ever ran the
  supervisor on Windows.
- **A venv's script is detached, not only its launcher.** A Windows venv's
  `python.exe` starts the base interpreter as an ordinary child, which then
  had a console (found testing inside a venv; economicspace runs a non-venv
  interpreter and never met it). The supervisor now starts the base
  interpreter named by `pyvenv.cfg` directly, with `__PYVENV_LAUNCHER__`.
- **`pause.ps1` suspends each process once.** A launcher and the interpreter
  it starts both match `-Match`, and the shared subtree was collected twice:
  harmless, as resume did the same, but the count printed was too high.
- **`pause.ps1` requires `-Match`** and exits 2 without it, rather than
  defaulting to economicspace's patterns; it does not prompt. Its lines say
  "matching processes" and "trigger" for "campaign processes" and "reboot
  trigger".

Tests: the queue against planted ledgers, the guard against a fake process
table, a real detached start, the watcher against a planted log directory and
process table, and `pause.ps1` against a real process tree on Windows; each of
fifteen traps is planted in a copy of the package and shown to fail
its test.
