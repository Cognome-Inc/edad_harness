---
slug: base-ref-validation
grilled_at: 2026-09-15
---

## Record

**Origin.** T023 review finding 2: on the CLI, `python3 -m edad.gate run <ticket>
--base-ref <bad ref>` with a mismatched toolchain surfaced a bare git traceback
instead of a refusal, because T023 moved a `changed_files(root, base_ref)` call into
`die_on_toolchain_mismatch` (`edad/gate.py:832`), ahead of anything that checks the
ref. Spec-deferred in T023 as small and CLI-only.

**What the grill found before asking anything.** The crash is not toolchain-specific.
With a matching toolchain the same `--base-ref no-such-ref` dies at
`edad/gate.py:1861` (`rec.changed_files = changed_files(root, base_ref)`): `git diff
<ref>...HEAD` runs with `check=True` and nothing catches `CalledProcessError`. The
mismatch case merely reaches the same crash earlier. Before the crash there is a
silent-wrong path: `trusted_input_problems` (`edad/gate.py:371`) swallows the git
error on a bad ref and reports "approval lock modified since <ref>" — a confident,
false verdict. A second crash shape exists: a ref that resolves but shares no history
with HEAD (probe: the empty-tree SHA `4b825dc642cb6eb9a060e54bf8d69288fbee4904`)
makes `git diff A...HEAD` exit 128 the same way; `git rev-parse --verify` would not
catch it, `git merge-base <ref> HEAD` catches both (exit 128 bad name, exit 1 no
merge base). The session controller always passes `git rev-parse HEAD`
(`edad/session.py:1040`) and the queue passes no ref, so the defect is CLI-only. A
refusal raised before any `Record` exists is already handled: T023's path logs it as
`refusal:<reason>` (`edad/session.py:1085`). No doc line needs changing: QUICKSTART
line 119 describes the record's `base_ref` field, not the flag; the gate docstring
lists the flag.

**Blast-radius probe (decisive for D3).** A prototype that ran the probe through
`subprocess.run` directly broke 8 frozen tests (`tests/test_gate_refusal.py` ×2,
`tests/test_refused_iteration.py` ×6): the T021/T023 `Night` fixture fakes `gate.git`
to answer HEAD for everything and runs the real `evaluate` against a non-git `wt/`
with a made-up base ref. The same prototype wired through `gate.git()` (catching
`CalledProcessError`) broke none — suite back to the 15-test baseline that is T025's
stubs on `main`. `_git_answer` shells out directly too and would also have broken
them. Both prototypes were reverted; nothing from the grill is in the tree.

---

**D1 — Where the check lives.** One check at the top of `evaluate`, before
`measure_toolchain` / `die_on_toolchain_mismatch`; every caller gets it, and all three
uses of the ref (toolchain message, lock-drift check, `changed_files`) are downstream
of it. Scope: `edad/gate.py`.
Rejected: catching the git error inside `changed_files` — leaves the lock-drift false
verdict in place and changes behaviour for every caller of `changed_files`. Rejected:
validating in `cmd_run` only — `evaluate` itself stays able to crash for any future
caller.

**D2 — What "valid" means.** The ref must resolve AND share history with HEAD, via
one `git merge-base <ref> HEAD` probe. A typo and a resolvable-but-unrelated ref are
both refused.
Rejected: `git rev-parse --verify` (resolves-to-a-commit only) — leaves the
unrelated-history traceback in place.

**D3 — Wiring.** The probe goes through `gate.git()` and catches
`subprocess.CalledProcessError`; not raw `subprocess`, not `_git_answer`. Verified by
the two frozen fixtures that fake `gate.git` staying green.
Rejected: direct subprocess plus re-freezing the T021/T023 fixtures to fake the new
probe — three frozen files touched for no behavioural gain.

**D4 — Ordering.** The ref check precedes the toolchain check: a bad ref plus a
mismatched toolchain refuses for the ref. A bad ref is an argument error (the operator
typed it), the toolchain message needs a valid ref to say whether the pins changed,
and the ordering removes the lock-drift false verdict entirely.
Rejected: toolchain first — the pins check would still have to survive a bad ref.

**D5 — The refusal.** Raised through `die()`, so it is a `gate.Refusal`
(`SystemExit(2)`) with `edad: <reason>` on stderr; the reason names the ref as given;
no traceback reaches the operator. Pinned at both levels: `evaluate(...)` raising
`Refusal`, and the CLI as a subprocess exiting 2 with `edad:` on stderr and
`Traceback` nowhere in its output. Also pinned: with a faked toolchain mismatch the
reason names the ref, not `requirements-gate.txt`; and the reason never contains
"approval lock modified".

**D6 — Regression guards.** A valid ancestor ref still evaluates normally (no
refusal, a record is produced); `base_ref=None` runs no probe.

**D7 — Test shape.** New frozen `tests/test_gate_base_ref.py` building a real temp
git repository, the pattern `tests/test_gate_trusted_inputs.py` (T022) set. The check
IS a git call, so faking git would fake the thing under test. The agent's container
has no git, so it cannot run this file; the ticket body says so, as T025's did, and
the verifier on the host judges. The two existing frozen suites that D3 cites are
frozen for this ticket too (read-only), as T023 did with `test_gate_refusal.py`.
Rejected: faking git via monkeypatch — runs in-container but pins the exact git
invocation and proves nothing about real git.

**D8 — Exclusions (unenforced, recorded).** Deliberately out of this ticket:
(a) `trusted_input_problems` keeps swallowing git errors on `git show
<ref>:<lock>` — after D1 a failure there can only mean "no lock at base", which is
what the code already means by it; (b) the evidence record keeps `base_ref` as given,
not resolved to a SHA — a record-format change with readers and tests behind it;
(c) `--base` keeps working as argparse's abbreviation of `--base-ref`; (d) not-a-repo
and git-not-installed are untouched — pre-existing (`git(root, "rev-parse", "HEAD")`
at `edad/gate.py:1823` would crash the same way) and unreachable from the CLI, which
resolves `root` via `git rev-parse --show-toplevel` before `evaluate` runs.
Rejected: resolving `base_ref` to a SHA in the record — wider blast radius for a
finding about a traceback. Rejected: `allow_abbrev=False` — breaks the operator's
own muscle memory and any script using `--base`.

**Deferred, all cheap to reverse:** the exact refusal wording, and whether it is one
message or two split on git's exit code (128 bad name / 1 no merge base); whether the
`base_ref=None` guard pins the verb `merge-base` through a `gate.git` recorder
(acceptable — D2 names the verb); whether the new test builds its own temp repo or
imports `test_gate_mutation.git_repo` (own repo preferred — reuse adds a fourth
frozen file).

**Sequencing note (operator, not design).** Per
`.edad/specs/pytest-bump-and-image-guard.md`, this ticket is the one approved after
the host `pip install` of the pytest 9.0.3 pins, so its dry-run exercises T024's
image refusal. Its contract commit and approval wait for PR #7 (T025) to merge; the
grill does not.

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
    rejected: git rev-parse --verify — a ref with no merge base still crashes `git diff A...HEAD`
  - id: D3
    decision: the probe runs through gate.git() catching subprocess.CalledProcessError, not raw subprocess and not _git_answer, so the frozen fixtures that fake gate.git intercept it
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_the_probe_reaches_git_through_the_gate_git_seam -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    rejected: direct subprocess plus re-freezing the T021/T023 fixtures — three frozen files touched for no behavioural gain (prototype broke 8 tests)
  - id: D4
    decision: the ref check precedes the toolchain check; a bad ref with a mismatched toolchain refuses for the ref
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_a_bad_ref_with_a_mismatched_toolchain_is_refused_for_the_ref -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
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
    rejected: none — the shape is die()'s existing contract
  - id: D6
    decision: a valid ancestor ref still evaluates normally and base_ref=None runs no probe
    verify:
      - python3 -m pytest tests/test_gate_base_ref.py::test_the_probe_runs_for_an_ancestor_ref_and_not_for_none -q
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    rejected: none
  - id: D7
    decision: the new frozen test builds a real temp git repository (the T022 pattern); the agent cannot run it in-container and the ticket says so
    unenforced: the file's shape is fixed by its frozen hash and every node id in it is already a D1–D6 command; a whole-file command is refused by approve's node-id rule
    frozen:
      - tests/test_gate_base_ref.py
    scope:
      - edad/gate.py
    rejected: faking git via monkeypatch — pins the exact invocation and proves nothing about real git
  - id: D8
    decision: out of scope — trusted_input_problems keeps swallowing git errors; base_ref stays as given in the record; the --base abbreviation stays; not-a-repo and git-missing untouched
    unenforced: exclusions are recorded, not tested; each is a pre-existing behaviour left as is
    scope:
      - edad/gate.py
    rejected: resolve base_ref to a SHA in the record — record-format change with readers behind it; allow_abbrev=False — breaks --base for the operator and scripts
deferred:
  - exact refusal wording, and whether it is one message or two split on git's exit code (128 bad name / 1 no merge base)
  - whether the base_ref=None guard pins the verb `merge-base` through a gate.git recorder (acceptable — D2 names it)
  - whether the new test builds its own temp repo or imports test_gate_mutation.git_repo (own repo preferred; reuse adds a fourth frozen file)
```
