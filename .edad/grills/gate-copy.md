---
slug: gate-copy
grilled_at: 2026-09-16
---

## Record

**Origin.** Held since T022 (2026-09-14) at the user's request: "which copy of
`edad/gate.py` judges the agent's worktree". The harness develops itself, so every
agent worktree carries a copy of the judge, and tickets such as T026 edit that very
file. Deferred in turn by the T023, T024, T025 and T026 specs ("held, raise after
this one"). Raised 2026-09-16 after PR #8 merged; the user chose to address it now and
release the result as `v0.1.1`.

**What the grill measured before asking anything** (all on main = `fe2ec5a`, host
pytest 9.0.3, macOS, git 2.50.1):

- *Who judges today.* The night runs `python3 -m edad.session` with cwd = the main
  checkout, so the session process imports the main checkout's `edad` (cwd first on
  `sys.path`) and calls `evaluate()` in-process (`edad/session.py:1156`, `:1175`). The
  judge is that copy for the whole session; nothing re-imports. T026's own record
  proves it: `harness.commit = 7430aa0` (main's HEAD that night), `commit = d642848`
  (the agent's worktree). `harness_identity()` derives its block from
  `edad.__file__` (`harness_checkout()`, `edad/gate.py:~950`), so the record names
  whichever copy actually judged, by construction.
- *What is tested.* `run_commands` runs each command with `shell=True, cwd=root`
  (`edad/gate.py:526`) where `root` is the worktree, inheriting `os.environ` minus
  `ANTHROPIC_API_KEY`. Measured in a scratch venv with the harness installed
  **editable** and a copy of `edad/` in a worktree-shaped directory: `python -c
  "import edad"`, `python -m pytest` (with `pythonpath = ["."]` from `pyproject.toml`),
  and `PYTHONPATH=<elsewhere> python -c` all import the **cwd copy**. The T018-era note
  that "an editable install would import the main checkout instead" is wrong; the
  working directory wins in every case tried.
- *The hole, reproduced.* `git worktree add --detach <dir> HEAD; cd <dir>; python3 -m
  edad.gate run T026` imports `<dir>/edad/__init__.py` and judges with it — the
  subject judging itself — and prints `harness checkout 07b3df0e` exactly as a
  main-checkout run would. Nothing refuses, nothing flags. Not reachable from the
  agent's container (no git there; the gate is never run in-container), so it is an
  operator path — but a future change that shelled the gate out from the worktree
  would open it silently for every night.
- *Queue nights.* `session_queue` spawns each child with `cwd=root` while root has the
  run branch checked out (`edad/session_queue.py:513`), so a promoted ticket that edits
  `gate.py` changes the judge for later tickets that night. Each session log carries
  its own `harness` block (T019), so which copy judged each ticket is already on disk.
- *Nothing pins any of this.* No test asserts that the judge is the controller's copy,
  that commands import the worktree's, or that the two can differ.
- *Blast-radius prototype* (reverted, nothing in the tree): a five-line guard at the
  top of `evaluate` — `judge = harness_checkout(); if judge is not None and judge ==
  root.resolve() and (root / ".git").is_file(): die(...)` — leaves the full suite at
  294 passed + ruff clean (T021/T023's `Night` fakes `gate.git` and runs `evaluate`
  against a non-repo `wt/`; T022/T026 use temp repos; none is the judge's own
  checkout, so none trips), refuses from inside a worktree naming its path, and still
  passes from the main checkout.

---

**D1 — The rule.** The judge is the copy of the gate the night's controller imported
(the main checkout when the harness develops itself; the installed harness for any
other target). The subject is the worktree; its commands import their own copy. Pinned
by a regression test in the new frozen file: the worktree's `edad/gate.py` is replaced
with a sabotaged copy (freeze check neutered, `evaluate` returning a passing record),
a frozen file in the worktree is edited, and the real `gate.evaluate(wt, ...)` still
reports the frozen-hash mismatch — the sabotaged copy is never consulted. Green at
base by nature (the judge is already in-process), so it is a `full_gate` safety net,
not an acceptance command. Node id:
`tests/test_gate_judge.py::test_a_sabotaged_worktree_copy_of_the_gate_is_never_consulted`.
Scope: `edad/gate.py` (docstring), `tests/test_gate_judge.py`.
Rejected: document only, no test — a future shell-out from the worktree would hand
the agent its own gavel with nothing to catch it.

**D2 — The hole is refused.** `evaluate` refuses, first — before T026's base-ref probe
and before the toolchain is measured (it needs no git, only a path comparison) — when
the gate module it is running from lives inside the tree it is judging AND that tree
is a linked worktree: `harness_checkout() == root.resolve() and (root /
".git").is_file()`. Raised through `die()` (exit 2, `edad:` on stderr, no traceback),
naming the tree. Hand-runs from the main checkout (judge == subject, `.git` a
directory) stay allowed — that is approve time and every hand-run so far. Two
acceptance tests, both red at base: one drives `evaluate()` with `harness_checkout`
faked to the temp worktree (the seam T019's tests already fake at
`tests/test_harness_identity.py:216`); one copies the `edad/` package into the temp
repository, commits it, adds a linked worktree, and spawns `python3 -m edad.gate run
<ticket>` from inside it with no `PYTHONPATH` — the operator's actual command. A third
pins the order: with a bad `base_ref` and a mismatched toolchain, the reason names the
worktree, not the ref and not the pins. Note for the spawn test: at base the copied
package has no guard, so the child runs on to the toolchain refusal (the fixture's
pins are 8.4.2, the host's 9.0.3) — also exit 2 with `edad:` — so the test must assert
the worktree path is in the reason, not merely the exit code.
Scope: `edad/gate.py`.
Rejected: record a "self-judged" marker instead of refusing — nothing downstream reads
such a marker. Rejected: leave it as operator error — the same class of silent-wrong
verdict T026 closed for refs.

**D3 — The subject is pinned, the environment is not touched.** One test that a
command run through `run_commands(wt, ['python3 -c "import edad; print(edad.__file__)"'],
...)` prints a path under `wt`. Green at base (measured above), so a `full_gate` net.
`run_commands` sets no `PYTHONPATH` and scrubs none: cwd wins over `PYTHONPATH` and
over an editable install for both plain python and pytest, and every frozen test that
pins the command environment stays untouched. Node id:
`tests/test_gate_judge.py::test_commands_run_in_the_worktree_import_the_worktree_copy`.
Scope: `tests/test_gate_judge.py`.
Rejected: also setting `PYTHONPATH=wt` in `run_commands` — changes every command's
environment for a property that already holds.

**D4 — The judge may change within a queue night.** Accepted as-is and written down:
each child is judged by the run branch's tip at spawn time, so a promoted `gate.py`
change judges the tickets after it. The per-session `harness` block is the trace.
Unenforced.
Rejected: freezing the judge for the night (snapshot the harness at start, spawn
children from it) — a second copy of the harness to keep straight, for a case that
only exists while the harness builds itself.

**D5 — The record is unchanged.** No `judged_from` field. `harness.commit` names the
judge, `commit` names the subject, and `harness.source` says how the judge was
installed; the pair already answers the question on every night record. Unenforced
exclusion.
Rejected: a `judged_from` path — redundant, and a record-format change has readers,
tests and the report line behind it.

**D6 — Where it is written.** QUICKSTART gains a `## Which copy judges` section: judge
vs subject in two sentences, that the record names both, that the queue's judge is
the run branch's tip, and that a hand-run from inside a worktree is refused. The same
rule in `evaluate`'s docstring. One frozen text test pins the section heading and one
substring, as T018/T024's text tests do. Red at base (section absent).
Scope: `QUICKSTART.md`, `edad/gate.py`.
Rejected: docstring only — the refusal is operator-facing, so the explanation must be
where the operator reads.

**D7 — The container (unenforced exclusion).** `edad-agent:latest` has no `edad`
installed (`import edad` → `ModuleNotFoundError`); the agent's in-container test runs
import `/work`'s copy, the same cwd rule as the host. The agent cannot run D2's spawn
test (no git in the container); the ticket body says so, as T026's did. If a target's
layered image ever installs the harness, the target's own tests are unaffected by the
cwd rule. Nothing changes here.

**D8 — The release is an operator step, after merge.** `v0.1.1`, in its own PR: one
commit bumping `version` in `pyproject.toml`, the `@v0.1.1` install line in
QUICKSTART, and the `"0.1.0"` literal in T018's frozen
`tests/test_packaging.py:45` — plus a one-line fix to the Releasing section saying
that literal is part of a bump (it omits it today). The same commit carries the
already-committed D10 note on the bump spec (`07b3df0`, local main). Tag on the
merge commit, pushed. The agent ticket never touches the version. The verify
commands here are hand-run operator checks after the release, not acceptance
commands — the bump spec's D6/D8/D10 are the precedent.
Scope: `pyproject.toml`, `QUICKSTART.md`, `tests/test_packaging.py`,
`.edad/specs/pytest-bump-and-image-guard.md`.
Rejected: folding the bump into the agent ticket — mixes a release with a feature.

**Deferred, all cheap to reverse:** the refusal's exact wording (tests pin the
worktree path, not the sentence); the frozen file's name (`tests/test_gate_judge.py`
assumed above); the QUICKSTART heading text (`## Which copy judges` assumed); the diff
cap (80 suggested: a guard of a few lines, two docstring paragraphs, one QUICKSTART
section); whether the spawn test copies `edad/` with `shutil.copytree(...,
ignore=ignore_patterns("__pycache__"))` or via `git archive` of the checkout.

**Sequencing.** Next: `/to-spec` → `/to-tickets` (T027) → approve → docker night →
PR → merge → D8's release PR → tag `v0.1.1`. Blocked by nothing: T026 is on main.

## Decisions

```yaml
decisions:
  - id: D1
    decision: the judge is the copy of the gate the controller imported (main checkout, or the installed harness); the subject is the worktree, whose commands import their own copy; a sabotaged worktree copy of gate.py is never consulted by evaluate
    unenforced: green at base by nature (evaluate is already in-process), so the pinning test cannot be an acceptance command; it lives in the frozen file and runs under full_gate (python3 -m pytest -q) as a regression net — node id tests/test_gate_judge.py::test_a_sabotaged_worktree_copy_of_the_gate_is_never_consulted
    frozen:
      - tests/test_gate_judge.py
    scope:
      - edad/gate.py
      - tests/test_gate_judge.py
    rejected: document only, no test — a future shell-out from the worktree would hand the agent its own gavel with nothing to catch it
  - id: D2
    decision: evaluate refuses first — before the base-ref probe and the toolchain check — when harness_checkout() == root.resolve() and (root / ".git").is_file(), via die(), naming the tree; hand-runs from the main checkout stay allowed
    verify:
      - python3 -m pytest tests/test_gate_judge.py::test_a_gate_judging_its_own_worktree_copy_is_refused_naming_the_tree -q
      - python3 -m pytest tests/test_gate_judge.py::test_the_cli_run_from_inside_a_worktree_is_refused_with_no_traceback -q
      - python3 -m pytest tests/test_gate_judge.py::test_the_self_judge_refusal_precedes_the_base_ref_probe_and_the_toolchain_check -q
    frozen:
      - tests/test_gate_judge.py
    scope:
      - edad/gate.py
    rejected: a "self-judged" marker in the record instead of a refusal — nothing downstream reads it; leaving it as operator error — the same silent-wrong verdict class T026 closed for refs
  - id: D3
    decision: commands run through run_commands(wt, ...) import the worktree's edad by cwd; run_commands neither sets nor scrubs PYTHONPATH
    unenforced: green at base (measured — cwd wins over PYTHONPATH and over an editable install for python and pytest alike); the pinning test lives in the frozen file under full_gate — node id tests/test_gate_judge.py::test_commands_run_in_the_worktree_import_the_worktree_copy
    frozen:
      - tests/test_gate_judge.py
    scope:
      - tests/test_gate_judge.py
    rejected: also setting PYTHONPATH=wt in run_commands — changes every command's environment for a property that already holds
  - id: D4
    decision: within a queue night the judge is the run branch's tip at each child's spawn, so a promoted gate.py change judges the tickets after it; accepted and documented, the per-session harness block is the trace
    unenforced: a process decision about self-hosting only; the existing per-session harness block (T019) already records which copy judged each ticket
    scope:
      - QUICKSTART.md
    rejected: freezing the judge for the night from a snapshot of the harness — a second copy to keep straight, for a case that exists only while the harness builds itself
  - id: D5
    decision: the evidence record is unchanged — no judged_from field; harness.commit names the judge, commit names the subject, harness.source says how the judge was installed
    unenforced: an exclusion; the record format has readers, tests and the report line behind it and nothing here needs it to change
    scope: []
    rejected: a judged_from path — redundant with harness.commit + harness.source
  - id: D6
    decision: QUICKSTART gains a "## Which copy judges" section (judge vs subject, the record names both, the queue's judge is the run branch's tip, a hand-run from inside a worktree is refused) and evaluate's docstring states the same rule; a frozen text test pins the heading and one substring
    verify:
      - python3 -m pytest tests/test_gate_judge.py::test_quickstart_says_which_copy_judges_and_why_a_worktree_run_is_refused -q
    frozen:
      - tests/test_gate_judge.py
    scope:
      - QUICKSTART.md
      - edad/gate.py
    rejected: docstring only — the refusal is operator-facing, so the explanation belongs where the operator reads
  - id: D7
    decision: the container is untouched — edad-agent:latest installs no edad, the agent's in-container tests import /work's copy by the same cwd rule, and the agent cannot run D2's spawn test (no git in-container); the ticket body says so
    unenforced: an exclusion recording measured facts; nothing to change
    scope: []
    rejected: none
  - id: D8
    decision: release v0.1.1 as an operator step after the ticket merges, in its own PR — one commit bumping pyproject.toml, the QUICKSTART @v0.1.1 install line, and the "0.1.0" literal in tests/test_packaging.py:45, plus a Releasing-section line naming that literal; the commit also carries the D10 note on the bump spec; tag on the merge commit
    verify:
      - python3 -c "import tomllib; assert tomllib.load(open('pyproject.toml','rb'))['project']['version']=='0.1.1'"
      - python3 -c "assert '@v0.1.1' in open('QUICKSTART.md').read()"
      - python3 -c "assert 'test_packaging' in open('QUICKSTART.md').read().split('## Releasing')[1].split('## ')[0]"
    frozen: []
    scope:
      - pyproject.toml
      - QUICKSTART.md
      - tests/test_packaging.py
      - .edad/specs/pytest-bump-and-image-guard.md
    rejected: folding the version bump into the agent ticket — mixes a release with a feature and puts the version in agent scope
deferred:
  - the refusal's exact wording (tests pin the worktree path, not the sentence)
  - the frozen file's name (tests/test_gate_judge.py assumed)
  - the QUICKSTART heading text ("## Which copy judges" assumed)
  - the ticket's diff cap (80 suggested)
  - whether the spawn test copies edad/ with shutil.copytree ignoring __pycache__ or via git archive
```
