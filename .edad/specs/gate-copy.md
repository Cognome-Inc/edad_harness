---
slug: gate-copy
grilled: .edad/grills/gate-copy.md
status: draft
---

## Problem statement

The harness develops itself. Every night, the agent's worktree carries a full
copy of `edad/`, including the gate that will judge it, and tickets such as T026
edit that very file. Nothing today says which copy of the gate is the judge and
which is the subject. The night gets it right by accident of construction — the
controller imports its own checkout's `edad` once and calls `evaluate()`
in-process, and every command the gate runs imports the worktree's copy because
the working directory wins on `sys.path` — but no test pins either half, and a
future change that shelled the gate out from the worktree would silently hand
the agent its own gavel.

The hole is already reachable by hand: `cd` into a linked worktree and run
`python3 -m edad.gate run <ticket>`, and the worktree's own copy of the gate
judges the worktree, printing the same `harness checkout` line a main-checkout
run would. Nothing refuses, nothing flags. It is an operator path today, not the
agent's — the container has no git and the gate is never run inside it — but it
is the same class of silent-wrong verdict that T026 closed for base refs.

The question has been held since T022 and deferred by four specs in a row.

## Solution

The rule is written down and pinned: the **judge** is the copy of the gate the
night's controller imported (the main checkout when the harness develops itself;
the installed harness for any other target). The **subject** is the worktree, and
its commands import their own copy. The evidence record already names both —
`harness.commit` for the judge, `commit` for the subject — and stays as it is.

The one way the two can collapse into each other is refused: when the gate
module doing the judging lives inside the tree it is judging *and* that tree is a
linked worktree, `evaluate` refuses before it probes the base ref or measures the
toolchain, naming the tree. A hand-run from the main checkout — where judge and
subject are the same repository by design — stays allowed, because that is
approve time and every hand-run so far.

Two safety-net tests pin the halves that already hold (a sabotaged worktree copy
of the gate is never consulted; commands run in the worktree import the
worktree's copy), and QUICKSTART tells the operator which copy judges and why a
run from inside a worktree is refused. The work is released as `v0.1.1` in its
own PR after the ticket merges.

## User stories

1. As an operator reading a night's evidence, I want to know which copy of the
   gate produced the verdict, so that a ticket editing `gate.py` cannot leave me
   guessing whether it graded itself.
2. As an operator who runs the gate by hand from inside a worktree, I want a
   refusal that names the tree, so that I do not read a self-judged PASS as a
   real one.
3. As an operator running the gate by hand from the main checkout at approve
   time, I want that to keep working unchanged, so that the refusal does not
   break the path every approval already uses.
4. As a maintainer changing how the gate is invoked, I want a test that goes
   red if the worktree's copy of the gate ever gets consulted, so that a
   shell-out from the worktree cannot land silently.
5. As a maintainer, I want a test that pins "the subject's commands import the
   subject's copy", so that a later "helpful" `PYTHONPATH` change cannot make
   the worktree's tests run against the main checkout's code.
6. As an operator running a queue night, I want it written down that a promoted
   `gate.py` change judges the tickets after it, so that a mid-night change of
   judge is an understood property with a trace, not a surprise.
7. As a teammate installing the harness for another target, I want the release
   to carry this rule, so that `pip install ...@v0.1.1` gives me the refusal and
   the documentation together.

## Seams

- **evaluate on a temp repository, judge location faked** - **Where**:
  `gate.evaluate(root, ticket, ...)` against a real `git init` repository in
  `tmp_path` with an approved ticket and a frozen file, as
  `tests/test_gate_trusted_inputs.py` (T022) and `tests/test_gate_base_ref.py`
  (T026) already do; the judge's location is set by replacing
  `gate.harness_checkout` by name, as `tests/test_harness_identity.py` (T019)
  already does; a toolchain mismatch by replacing `gate.measure_toolchain`, as
  the T021/T023 `Night` does. **Exists**: yes — each piece is established,
  their combination is new. **Observes**: whether a `Refusal` is raised or a
  `Record` returned, the refusal's reason text, which check spoke first, and —
  for the sabotage test — that a worktree whose own `edad/gate.py` has been
  neutered still gets its edited frozen file reported as a hash mismatch by the
  real `evaluate`. **Discharges**: D1 (safety net under `full_gate`), D2 (the
  function half and the ordering), D9 (the same seam with a real submodule
  checkout — `git submodule add` of the temp repository — as the tree judged).
- **the gate CLI from inside a linked worktree** - **Where**:
  `[sys.executable, "-m", "edad.gate", "run", <ticket>]` with `cwd` a linked
  worktree (`git worktree add`) of the temp repository, the repository carrying
  a committed copy of the `edad/` package, and **no** `PYTHONPATH` — so the
  child imports the worktree's copy by cwd, which is the operator's actual
  command and the only way the self-judging path is reached. **Exists**: the
  subprocess seam is T026's (`tests/test_gate_base_ref.py`); that test sets
  `PYTHONPATH` at the checkout, so the no-`PYTHONPATH`, copied-package variant
  is new. **Observes**: exit code, stderr (the `edad:` line, no traceback), and
  whether the reason names the worktree. At base the copied package has no
  guard, so the child runs on to the toolchain refusal — also exit 2 with
  `edad:` — which is why the test must assert the worktree path is in the
  reason, not merely the exit code. **Discharges**: D2 (the CLI half).
- **run_commands on a worktree** - **Where**: `gate.run_commands(wt, [...],
  ...)` called directly, as `tests/test_gate_record.py` already does, with a
  worktree-shaped directory holding a copy of `edad/`. **Exists**: yes.
  **Observes**: a command's stdout, so `python3 -c "import edad;
  print(edad.__file__)"` shows which copy the subject imports. **Discharges**:
  D3 (safety net under `full_gate`).
- **QUICKSTART as text** - **Where**: `QUICKSTART.md` read as a string and
  searched for a heading and a substring, as `tests/test_packaging.py` (T018),
  `tests/test_gate_trusted_inputs.py` (T022) and `tests/test_harness_identity.py`
  (T019) already do. **Exists**: yes. **Observes**: that the `## Which copy
  judges` section is present and says what the decision requires.
  **Discharges**: D6.
- **the operator's shell after the release** - **Where**: the three one-liners
  in D8's `verify`, run by hand on main after the release PR merges and the tag
  is pushed. **Exists**: yes; not a pytest seam and not an acceptance command —
  the bump spec's D6/D8/D10 are the precedent. No frozen file, no ticket.
  **Discharges**: D8.

No seam: D4, D5 and D7 — a process decision about self-hosting and two
exclusions, unenforced by design and carried as such. D4's trace already exists
(the per-session `harness` block, T019); D5 and D7 change nothing.

## Implementation decisions

**The rule (D1).** Judge and subject are named and told apart. The judge is
whichever gate module the controller process imported — for the harness
developing itself that is the main checkout, since the night runs with cwd
there and imports `edad` once; for any other target it is the installed
harness. The subject is the worktree; the commands the gate runs in it inherit
the working directory and so import the worktree's own copy. The record needs
no change to show this: the identity block derives from where the judging
module lives, so `harness.commit` already names the judge and `commit` the
subject. `evaluate`'s docstring states the rule. A regression test in the new
frozen file sabotages the worktree's copy of the gate and shows the real
`evaluate` never consults it. That test is green at base — the judge is already
in-process — so it is a `full_gate` safety net, not an acceptance command.

**The refusal (D2).** `evaluate` gains a guard at its top, ahead of the base-ref
probe (T026) and the toolchain measurement (T021), because it needs neither git
nor a measurement — only a path comparison. The condition is exactly: the
judging module's own checkout root equals the root being judged, *and* that
root's `.git` is a file rather than a directory — which is what distinguishes a
linked worktree from the main checkout. It refuses through the existing `die()`
path: exit 2, `edad:` on stderr, no traceback, the tree's path in the reason. The
main checkout judging itself stays allowed; that is every hand-run so far. Three
acceptance tests, all red at base: the function driven with the judge's location
faked to the temp worktree; the CLI spawned from inside a real linked worktree
carrying a copy of the package, with no `PYTHONPATH`; and the ordering — with a
bad `base_ref` and a mismatched toolchain present, the reason names the
worktree and neither of the others. The grill's reverted prototype of this guard
left the full suite at 294 passed and ruff clean, so no existing frozen test
trips.

**The subject's environment (D3).** `run_commands` is not touched. It sets no
`PYTHONPATH` and scrubs none; the grill measured that the working directory wins
over `PYTHONPATH` and over an editable install, for plain `python` and for
`pytest` alike, which corrects the T018-era note that said otherwise. One
`full_gate` test pins the property. Setting `PYTHONPATH=wt` was rejected as a
change to every command's environment for something that already holds.

**Queue nights (D4).** Within a queue night each child is spawned with the run
branch checked out, so it is judged by the run branch's tip at that moment — a
promoted `gate.py` change judges the tickets after it. Accepted as-is and
written into QUICKSTART; the per-session `harness` block is the trace.
Snapshotting the harness at the start of a night was rejected as a second copy
to keep straight for a case that only exists while the harness builds itself.

**The record (D5) and the container (D7).** Both unchanged. No `judged_from`
field — the pair `harness.commit` / `commit` plus `harness.source` already
answers the question, and the record format has readers, tests and the report
line behind it. The agent image installs no `edad`; in-container test runs
import `/work`'s copy by the same cwd rule; and the agent cannot run D2's spawn
test in the container (no git there), which the ticket body will say, as
T026's did.

**Where the operator reads it (D6).** QUICKSTART gains a `## Which copy judges`
section — judge versus subject in two sentences, that the record names both,
that a queue night's judge is the run branch's tip, and that a hand-run from
inside a worktree is refused. One frozen text test pins the heading and one
substring; red at base because the section is absent.

**The release (D8).** `v0.1.1`, cut by the operator after the ticket merges, in
its own PR: one commit bumping the version in `pyproject.toml`, the pinned
install line in QUICKSTART, and the version literal in T018's frozen packaging
test — plus one line added to the Releasing section saying that literal is part
of a bump, which it omits today (the bump spec's D10 amendment noted this). The
same commit carries the already-committed D10 note on the bump spec. The tag
goes on the merge commit. The agent ticket never touches the version.

## Out of scope

- Changing the evidence record format — D5 excludes it.
- Changing the agent image or the in-container environment — D7 excludes it.
- Freezing the judge for a whole queue night — D4 rejects it.
- Setting or scrubbing `PYTHONPATH` in `run_commands` — D3 rejects it.
- The version bump and tag — D8, an operator step in a separate PR, never in the
  agent ticket's scope.
- A refusal for the main checkout judging itself — D2 deliberately allows it;
  approve time and every hand-run depend on it.

## Further notes

The grill's measurements, all on main = `fe2ec5a`, host pytest 9.0.3, macOS,
git 2.50.1, are recorded in `.edad/grills/gate-copy.md` and are the evidence
behind D1 and D3 being green at base. The hole was reproduced by hand there; the
guard was prototyped and reverted, nothing of it is in the tree.

`to-tickets` notes:

- D1 and D3 carry `unenforced:` because their tests are green at base; the
  tests still exist, in the frozen file, and `full_gate` runs them. They are
  not acceptance commands and must not be listed as such.
- D2's spawn test: at base the copied package has no guard, so the child
  refuses on the toolchain instead (fixture pins 8.4.2, host 9.0.3) — also exit
  2 with `edad:`. The test must assert the worktree path is in the reason for
  its red-at-base to be the right red.
- D8's `verify` commands are hand-run operator checks after the release — no
  frozen file, no ticket, as the bump spec's D6/D8/D10 were handled.
- The ticket body should say the agent cannot run D2's spawn test in the
  container (no git), as T026's did.

- Amendment 2026-09-16, after night 1 (`e9a65a0`, tag `t027-night-1`, passed):
  review found D2's `is_file()` test also matches a submodule checkout, whose
  `.git` is a `gitdir:` file pointing under `modules` rather than `worktrees`.
  D9 pins what "linked worktree" means (target directly under a `worktrees`
  directory), one frozen test asserts both halves in one node so it is red on
  main and at `e9a65a0`, the ticket gains the command and D9, the cap goes
  80 → 90, `approve --rebaseline` (baseline 4 → 5), and the agent redoes the
  work from the amended contract per [[fix-the-contract-not-the-branch]].

Deferred from the grill, all cheap to reverse:

- The refusal's exact wording — tests pin the worktree path, not the sentence.
- The frozen file's name — `tests/test_gate_judge.py` assumed throughout.
- The QUICKSTART heading text — `## Which copy judges` assumed.
- The ticket's diff cap — 80 suggested: a guard of a few lines, two docstring
  paragraphs, one QUICKSTART section.
- Whether the spawn test copies `edad/` with `shutil.copytree(...,
  ignore=ignore_patterns("__pycache__"))` or via `git archive` of the checkout.

## Decisions

Carried from `.edad/grills/gate-copy.md` verbatim; `seam:` is the one field
added here. `to-tickets` reads this block and the Seams section, nothing else.

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
    seam: evaluate on a temp repository, judge location faked (full_gate)
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
    seam: evaluate on a temp repository, judge location faked; the gate CLI from inside a linked worktree
    rejected: a "self-judged" marker in the record instead of a refusal — nothing downstream reads it; leaving it as operator error — the same silent-wrong verdict class T026 closed for refs
  - id: D3
    decision: commands run through run_commands(wt, ...) import the worktree's edad by cwd; run_commands neither sets nor scrubs PYTHONPATH
    unenforced: green at base (measured — cwd wins over PYTHONPATH and over an editable install for python and pytest alike); the pinning test lives in the frozen file under full_gate — node id tests/test_gate_judge.py::test_commands_run_in_the_worktree_import_the_worktree_copy
    frozen:
      - tests/test_gate_judge.py
    scope:
      - tests/test_gate_judge.py
    seam: run_commands on a worktree (full_gate)
    rejected: also setting PYTHONPATH=wt in run_commands — changes every command's environment for a property that already holds
  - id: D4
    decision: within a queue night the judge is the run branch's tip at each child's spawn, so a promoted gate.py change judges the tickets after it; accepted and documented, the per-session harness block is the trace
    unenforced: a process decision about self-hosting only; the existing per-session harness block (T019) already records which copy judged each ticket
    scope:
      - QUICKSTART.md
    seam: none (unenforced)
    rejected: freezing the judge for the night from a snapshot of the harness — a second copy to keep straight, for a case that exists only while the harness builds itself
  - id: D5
    decision: the evidence record is unchanged — no judged_from field; harness.commit names the judge, commit names the subject, harness.source says how the judge was installed
    unenforced: an exclusion; the record format has readers, tests and the report line behind it and nothing here needs it to change
    scope: []
    seam: none (unenforced)
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
    seam: QUICKSTART as text
    rejected: docstring only — the refusal is operator-facing, so the explanation belongs where the operator reads
  - id: D7
    decision: the container is untouched — edad-agent:latest installs no edad, the agent's in-container tests import /work's copy by the same cwd rule, and the agent cannot run D2's spawn test (no git in-container); the ticket body says so
    unenforced: an exclusion recording measured facts; nothing to change
    scope: []
    seam: none (unenforced)
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
    seam: the operator's shell after the release
    rejected: folding the version bump into the agent ticket — mixes a release with a feature and puts the version in agent scope
  - id: D9
    decision: for D2's condition, a linked worktree is a tree whose .git is a file whose `gitdir:` target lies directly under a directory named `worktrees`; a submodule checkout (`gitdir:` under `modules`) is a main checkout and judging it from inside stays allowed — a file read, still no git
    verify:
      - python3 -m pytest tests/test_gate_judge.py::test_a_linked_worktree_is_refused_but_a_submodule_checkout_is_not -q
    frozen:
      - tests/test_gate_judge.py
    scope:
      - edad/gate.py
    seam: evaluate on a temp repository, judge location faked
    rejected: git rev-parse --git-dir vs --git-common-dir — a git call before the toolchain check, and the T021/T023 fakes of gate.git answer a constant for every verb; noting it and moving on — a pinned condition known to be wrong is a contract defect
deferred:
  - the refusal's exact wording (tests pin the worktree path, not the sentence)
  - the frozen file's name (tests/test_gate_judge.py assumed)
  - the QUICKSTART heading text ("## Which copy judges" assumed)
  - the ticket's diff cap (80 suggested)
  - whether the spawn test copies edad/ with shutil.copytree ignoring __pycache__ or via git archive
```
