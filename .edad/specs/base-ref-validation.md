---
slug: base-ref-validation
grilled: .edad/grills/base-ref-validation.md
status: draft
---

## Problem statement

An operator who runs the gate by hand with a base ref that is wrong - a typo, a
branch that no longer exists, a commit from an unrelated history - gets a bare git
traceback instead of a refusal. The gate has a refusal mechanism for exactly this
kind of thing (it refuses a mismatched toolchain, a tampered lock, a missing ticket)
and a bad ref bypasses it. Worse, before the crash the lock-drift check reads the bad
ref as "the approval lock was modified since <ref>" - a confident verdict about the
agent's honesty that is simply false. The finding that surfaced this (T023's review)
saw it behind a mismatched toolchain, but the crash is there on a healthy toolchain
too; the mismatch only moves it earlier.

## Solution

The gate checks the base ref once, first, and refuses in its own voice when the ref
is not a commit that shares history with HEAD: exit 2, a one-line `edad:` message on
stderr naming the ref the operator typed, no traceback. Every later use of the ref
- the toolchain message, the lock-drift comparison, the changed-files diff - can then
trust it. The session controller and the queue never pass a ref that could fail this
check, so nights are unaffected; the frozen tests that fake git for the session path
stay green because the probe reaches git through the same seam they fake.

## User stories

1. As the operator, I want `edad.gate run T --base-ref <typo>` to refuse with a
   message naming the ref, so that I fix the argument rather than read a traceback.
2. As the operator, I want a ref that exists but shares no history with HEAD to be
   refused the same way, so that a wrong branch is caught before the diff runs.
3. As the operator, I want a bad ref to be reported as a bad ref even when my
   toolchain is also mismatched, so that the first thing I am told is the cheapest
   thing to fix.
4. As the operator, I want a bad ref never to be reported as a modified approval
   lock, so that the record's trust verdicts stay true.
5. As the session controller, I want `evaluate` with the real base ref I pass to
   behave exactly as today, so that no night changes because of this.
6. As the author of the frozen session tests, I want the probe to go through the
   git seam my fixtures already fake, so that my tests stay green without edits.

## Seams

- **evaluate on a temp repository** - **Where**: `gate.evaluate(root, ticket,
  "acceptance", base_ref)` against a real `git init` repository in `tmp_path`, as
  `tests/test_gate_trusted_inputs.py` (T022) already does; a toolchain mismatch is
  produced by replacing `gate.measure_toolchain`, as `tests/test_gate_refusal.py`'s
  `Night` does. **Exists**: yes. **Observes**: whether a `Refusal` is raised or a
  `Record` returned, the refusal's reason text, and which check spoke first.
  **Discharges**: D1, D2, D4, D5 (the function half), D6 (the ancestor half), D7.
- **the frozen gate.git fakes** - **Where**: the T021/T023 `Night` fixture in
  `tests/test_gate_refusal.py`, reused by `tests/test_refused_iteration.py`, which
  replaces `gate.git` and runs the real `evaluate` against a directory that is not a
  repository. **Exists**: yes, frozen, unchanged. **Observes**: that the probe
  reaches git through `gate.git` - routed anywhere else it meets real git in a
  non-repository and refuses, turning eight green tests red (the grill's prototype
  showed exactly this). Runs under `full_gate`, not acceptance (see the amendment).
  **Discharges**: D3 as the regression net; D3's acceptance command is the call-log
  seam's failing-`merge-base` wrapper.
- **the gate CLI as a subprocess** - **Where**: `[sys.executable, "-m",
  "edad.gate", "run", <ticket>, "--base-ref", <ref>]` with `cwd` the temp
  repository, `PYTHONPATH` at the checkout and `EDAD_REPO` at the repository.
  **Exists**: new - no test in the suite spawns an `edad` module today
  (`tests/test_session_queue.py` asserts an argv, it does not run it).
  **Observes**: exit code, stderr, stdout. **Discharges**: D5 (the CLI half - the
  reported symptom).
- **gate.git call log** - **Where**: `gate.git` replaced by a recording wrapper
  around the real function, on the temp repository. **Exists**: replacing
  `gate.git` is established; recording is new. **Observes**: which git verbs
  `evaluate` ran, or made to fail for one verb. **Discharges**: D3 (the acceptance
  command), D6 (both halves, one test). This seam pins the verb `merge-base`, which
  the grill's deferred note accepts because D2 names it.

No seam: D8, the exclusions - unenforced by design and carried as such.

## Implementation decisions

**The check.** `evaluate` gains one guard at its top, before the toolchain
measurement: when a base ref is given, ask git for the merge base of that ref and
HEAD through the module's own `git` helper, and turn a failed answer into a refusal
through `die`, naming the ref as it was given. One probe answers both questions the
grill found - does the ref resolve, and does it share history with HEAD - because
git's merge-base fails for both (D1, D2). Nothing else in `evaluate` moves; the
toolchain check, the lock-drift check and the changed-files diff simply run after a
ref they can trust (D4).

**Why the helper and not a subprocess.** The frozen session tests replace the
module's `git` helper with a stand-in and run the real `evaluate` against a
directory that is not a repository, with a made-up base ref. A probe that shells out
on its own would meet real git there and refuse; a probe through the helper gets the
stand-in's answer and passes. The grill prototyped both: eight frozen tests red one
way, none the other. `_git_answer` shells out on its own too and is not an option
(D3).

**The refusal.** `die` already does everything the refusal needs: it prints
`edad: <reason>` to stderr and raises `Refusal`, which is a `SystemExit(2)` the CLI
lets escape and the session controller logs as a refused iteration. The reason names
the ref; no `Record` is built, so nothing is written (D5). Because the guard runs
first, a bad ref is never mistaken for a modified approval lock, and never hidden
behind a toolchain complaint.

**What must not change.** A ref that is an ancestor of HEAD - which is every ref
the session controller passes - evaluates exactly as before, and no ref at all
means no probe (D6). Both are guarded by tests so that an over-eager check cannot
pass the gate.

**The test.** One new frozen file on a real temporary repository, the pattern T022
set: the check is a git call, so a faked git would test the fake. The agent's
container has no git and cannot run this file; the ticket body says so and the
verifier on the host judges, as it did for T022. The two existing frozen suites the
wiring decision cites are frozen for this ticket too, read-only (D7).

## Out of scope

- The lock-drift check keeps swallowing git errors on `git show <ref>:<lock>`; after
  the guard a failure there can only mean "no lock at base", which is what the code
  already takes it to mean (D8).
- The evidence record keeps `base_ref` as the operator gave it, not resolved to a
  SHA - a record-format change with readers and tests behind it (D8).
- `--base` keeps working as argparse's abbreviation of `--base-ref` (D8).
- Not-a-repository and git-not-installed are untouched: pre-existing (`rev-parse
  HEAD` inside `evaluate` would fail the same way) and unreachable from the CLI,
  which resolves its root through git before `evaluate` runs (D8).
- The pytest 9.0.3 bump and T024's image guard: separate, already specified in
  `.edad/specs/pytest-bump-and-image-guard.md`. This ticket is the one that spec
  approves after the host pip install, so its dry-run exercises the image refusal.

## Further notes

Deferred from the grill, all cheap to reverse:

- The exact refusal wording, and whether it is one message or two split on git's
  exit code (128 for a name that does not resolve, 1 for no merge base). The tests
  pin that the ref is named, not the sentence around it.
- Whether the `base_ref=None` guard pins the verb `merge-base` through the call-log
  seam. Accepted: D2 names the verb.
- Whether the new test builds its own temporary repository or imports
  `test_gate_mutation.git_repo`. Own repository preferred: reuse adds a fourth
  frozen file.

Sequencing, from the bump spec: this ticket's contract commit and approval happen
after the host installs the pytest 9.0.3 pins, so that its dry-run is the one that
expects and then clears T024's image refusal. PR #7 (T025) is merged, so nothing else
blocks it.

**Amendment, 2026-09-15 (at `/to-tickets`).** Three verify entries could not be
acceptance commands as written. `edad.gate approve` refuses a whole-file pytest
command (D3's two existing suites, D7's `tests/test_gate_base_ref.py -q`) and refuses
any acceptance command that produces no `FAILED` before the work exists (D3's suites
and D6's two guards are green at base by nature). The decisions are unchanged; their
verification is re-encoded, and each new command was watched go red at base and green
on the grill's prototype:
- **D3** is pinned by one test in the new frozen file that wraps the real `gate.git`
  to fail only for `merge-base`, on a valid ref: a probe routed through `gate.git`
  refuses, a probe that shells out on its own asks real git and does not (verified:
  the raw-subprocess prototype fails exactly this test). The two existing suites leave
  `verify` and `frozen`; they still run under `full_gate` (`python3 -m pytest -q`),
  where a regression in them is caught.
- **D6**'s two guards become one test with a recording wrapper around `gate.git`: an
  ancestor ref makes exactly one `merge-base` call and returns a `Record`; `None`
  makes none. Red at base because no call is made. It pins the verb, as the deferred
  note allowed.
- **D7** becomes unenforced: the file's shape is fixed by its frozen hash, every node
  id in it is already under D1–D6, and no command distinguishes a real repository
  from a fake. The node id under D5's CLI check sets `PYTHONPATH` and `EDAD_REPO` for
  the child - the first test in the suite to spawn `edad.gate`; the queue tests only
  assert an argv.

## Decisions

Carried from `.edad/grills/base-ref-validation.md` verbatim; `seam:` is the one
field added here.

```yaml
decisions:
  - id: D1
    decision: evaluate validates base_ref once, at its top, before the toolchain check; all three downstream uses of the ref trust it
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_a_bad_base_ref_is_refused_before_anything_else_runs -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    seam: evaluate on a temp repository
    rejected: catch inside changed_files — leaves the lock-drift false verdict, changes every caller; validate in cmd_run only — evaluate stays crashable for other callers
  - id: D2
    decision: a valid base_ref resolves AND shares history with HEAD, decided by one `git merge-base <ref> HEAD` probe; a typo and a resolvable-but-unrelated ref are both refused
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_a_ref_that_does_not_resolve_is_refused_naming_the_ref -q
      - python3 -m pytest tests/test_gate_base_ref.py::test_a_ref_with_no_shared_history_is_refused_naming_the_ref -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    seam: evaluate on a temp repository
    rejected: git rev-parse --verify — a ref with no merge base still crashes `git diff A...HEAD`
  - id: D3
    decision: the probe runs through gate.git() catching subprocess.CalledProcessError, not raw subprocess and not _git_answer, so the frozen fixtures that fake gate.git intercept it
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_the_probe_reaches_git_through_the_gate_git_seam -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    seam: gate.git call log; the frozen gate.git fakes (full_gate)
    rejected: direct subprocess plus re-freezing the T021/T023 fixtures — three frozen files touched for no behavioural gain (prototype broke 8 tests)
  - id: D4
    decision: the ref check precedes the toolchain check; a bad ref with a mismatched toolchain refuses for the ref
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_a_bad_ref_with_a_mismatched_toolchain_is_refused_for_the_ref -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    seam: evaluate on a temp repository
    rejected: toolchain first — its pins check would still have to survive a bad ref
  - id: D5
    decision: the refusal is a gate.Refusal via die() naming the ref as given — exit 2, "edad:" on stderr, no traceback — and never reports "approval lock modified" for a bad ref
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_the_refusal_is_a_refusal_naming_the_ref_not_a_lock_drift_verdict -q
      - python3 -m pytest tests/test_gate_base_ref.py::test_the_cli_exits_2_with_the_refusal_on_stderr_and_no_traceback -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    seam: evaluate on a temp repository; the gate CLI as a subprocess
    rejected: none — the shape is die()'s existing contract
  - id: D6
    decision: a valid ancestor ref still evaluates normally and base_ref=None runs no probe
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_the_probe_runs_for_an_ancestor_ref_and_not_for_none -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    seam: gate.git call log
    rejected: none
  - id: D7
    decision: the new frozen test builds a real temp git repository (the T022 pattern); the agent cannot run it in-container and the ticket says so
    unenforced: the file's shape is fixed by its frozen hash and every node id in it is already a D1–D6 command; a whole-file command is refused by approve's node-id rule
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    seam: none (unenforced)
    rejected: faking git via monkeypatch — pins the exact invocation and proves nothing about real git
  - id: D8
    decision: out of scope — trusted_input_problems keeps swallowing git errors; base_ref stays as given in the record; the --base abbreviation stays; not-a-repo and git-missing untouched
    unenforced: exclusions are recorded, not tested; each is a pre-existing behaviour left as is
    scope:
      - edad/gate.py
    seam: none (unenforced)
    rejected: resolve base_ref to a SHA in the record — record-format change with readers behind it; allow_abbrev=False — breaks --base for the operator and scripts
deferred:
  - exact refusal wording, and whether it is one message or two split on git's exit code (128 bad name / 1 no merge base)
  - whether the base_ref=None guard pins the verb `merge-base` through a gate.git recorder (acceptable — D2 names it)
  - whether the new test builds its own temp repo or imports test_gate_mutation.git_repo (own repo preferred; reuse adds a fourth frozen file)
```
