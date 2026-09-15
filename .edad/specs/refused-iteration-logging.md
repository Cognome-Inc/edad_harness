---
slug: refused-iteration-logging
grilled: .edad/grills/refused-iteration-logging.md
status: draft
---

## Problem statement

When the gate refuses to run on an agent's worktree — today, because the agent
changed `requirements-gate.txt` and the gate's toolchain no longer matches it — the
session stops, which is right, but the iteration that led there is dropped from the
session log. The agent ran, its work was committed, and the log says no iteration
happened. The overnight queue reads a log with no iterations as "the agent is not
running", counts it toward its no-progress breaker, and after two such nights stops
the whole queue for a reason that is false.

The same refusal tells the operator to install the pins from `requirements-gate.txt`.
In a worktree, that file may be the one the agent just wrote — possibly outside the
ticket's scope — and the scope violation is never recorded because the refusal
happens before anything is measured.

T021 deferred the first half of this ("logging the agent tail on a refused iteration
needs an `Iteration` without a verdict, which is a shape nothing reads yet"). The
queue consequence was not identified then. The pytest 9.0.3 bump is the first ticket
whose agent edits the pins by design, so its night will produce exactly this log.

## Solution

A refusal still ends the session on its first occurrence, but the refused iteration
is written to the session log first: which commit the agent made, that the gate did
not pass, that the reason was a refusal, and the agent's last output. Because the
iteration records a commit, the queue reads a refused night as a night where the
agent ran and was refused, not as a night where nothing ran.

The refusal message, when the gate is judging a worktree and the worktree changed
`requirements-gate.txt` since the base, says that — and whether that file was in the
ticket's scope — instead of advising the operator to install the agent's pins. The
two other places the install advice appears, approving a ticket and the session's
pre-flight check, judge the operator's own checkout and keep their wording.

## User stories

1. As the operator reading a session log in the morning, I want a refused night to
   show the iteration that was refused — its commit and the agent's output — so that
   I can tell a refusal from an agent that never ran.
2. As the overnight queue, I want to count only nights where the agent made no
   commit toward the no-progress breaker, so that a refused-but-committed night does
   not shut the queue down with the wrong reason.
3. As the operator reading a refusal, I want to be told when the worktree itself
   changed the pins, so that I do not install what the agent wrote.
4. As the operator, I want a refusal after an out-of-scope pin change to name the
   stray file, so that the scope violation is on record even though the gate never
   ran.
5. As the operator approving a ticket on my own checkout, I want the existing
   "install the pins" advice unchanged, because there it is correct.
7. As the operator, I want a refusal after the agent rewrote a *frozen* pins file to
   say the file is frozen, not "in scope", so that the log records what happened —
   a frozen file was rewritten — even though the freeze check never ran.
6. As the author of the pytest bump ticket, I want a refused session to stop after
   one iteration rather than retry, so that the bump does not spend a night's
   iteration budget being refused for the same reason each time.

## Seams

- **Night session** — **Where**: T021's `Night` fixture drives `run_session` from the
  top of its iteration loop with preflight, git, the worktree, the agent and the
  commit replaced, and `evaluate` real. **Exists**: yes. **Observes**: the session
  log written under `.edad/sessions/` (`iterations`, `outcome`, `abort_reason`), the
  return value, stderr, and — through `MeasureSequence.calls` — how many times
  `evaluate` reached the toolchain measurement, which is how "one evaluate call, no
  retry" is observed without reaching into the loop. `changed_files` is faked to
  `[]` by the fixture and overridden per test to steer the pins-changed,
  pins-unchanged and out-of-scope cases. **Discharges**: D1, D2, D4, D5, D6.
- **Queue reading** — **Where**: `session_queue.no_commit_abort`, a pure function
  over the log dict. **Exists**: yes. **Observes**: whether the queue counts a given
  log toward `no_commit_aborts`. Fed the log the Night session seam produced.
  **Discharges**: D3.

No new seams. A third, calling `evaluate` directly for D4/D6 as
`tests/test_harness_identity.py` does, was considered and not used: the refusal
reason is already visible in `abort_reason` through the Night session, and a direct
call would need its own git repository for `changed_files`. Every decision has a
seam; nothing is unenforced.

## Implementation decisions

**The session loop.** The call to the gate inside the iteration loop is wrapped so
that a refusal is caught, the iteration appended to the log, and the refusal
re-raised to the existing session-boundary handler. Nothing after the append runs:
no record is written, no kill conditions are checked, no retry prompt is built. The
existing handler still sets the outcome to aborted with the refusal as its reason.
Exactly one gate call happens in a refused session.

**The iteration's shape.** The existing iteration dataclass is reused with no new
field. The gate is recorded as not passed; the signature is the refusal reason with
a `refusal:` prefix so a reader can tell it from a failed test; the violations list
holds the reason; whether the agent committed is recorded as measured; the agent's
output tail is kept. The signature is never consulted by the kill checks because
the loop does not continue, so it is a display field on the log.

**The queue.** Unchanged. Its existing check reads only whether any iteration made a
commit, so with the iteration logged it reads a refused-but-committed night as
progress and resets its counter. A refused night whose agent committed nothing still
counts, as it should. No refusal-specific breaker is added.

**The refusal wording.** The shared refusal helper grows keyword arguments with
defaults. Only `evaluate` passes them, and only when a base reference is set and the
pins file is among the files changed since that base. In that case the message keeps
the frozen prefix, states that the worktree changed the pins file, states whether the
file is in scope (using the existing "out of scope: <file>" wording for a stray),
and omits the install advice. One case is asked before the scope verdict: if the
pins file is in the ticket's `frozen` list, the message says so in the freeze check's
own wording, "frozen file modified: <file>", and never "in scope". `check_scope`
admits every frozen path on the assumption that the hash check caught any change
first; on the refusal path it has not run, so without this a rewritten frozen file
would be reported as in scope (D7, amended 2026-09-15 after the first night's review;
the first implementation had exactly that misreport). With no base reference the changed-files check is not
run at all — that path is exercised by an existing frozen test in a directory that
is not a git repository — and the wording is unchanged. With the pins unchanged the
wording is unchanged. Approve's call and the pre-flight's own message are not
touched.

**The scope violation's record.** The refusal reason itself, which names the file and
its scope verdict, is the record: through the iteration's violations it lands in the
session log. No partial gate record is written to the records directory, and the
refusal exception class gains nothing.

**Frozen tests.** A new test file imports T021's `Night`, `MeasureSequence` and
`measured` helpers rather than copying them; both files are frozen so the fixture
cannot be altered by the agent. A test needing a different ticket scope calls
`run_session` directly with a modified ticket rather than amending the fixture.

## Out of scope

- **Retrying after a refusal.** Rejected at D1. A refusal is a property of the
  environment, not of the agent's last edit.
- **A refusal breaker in the queue.** Rejected at D3; the refusal names itself in
  the log's abort reason.
- **Dirty-pins checks at approve and pre-flight.** Rejected at D4; those judge the
  operator's own checkout.
- **Partial records for refused runs.** Rejected at D5; nothing reads the records
  directory and the shape would look like a failed run.
- **Editing T021's spec.** Its deferral at `.edad/specs/gate-refusal.md:100-103` is
  closed by this spec citing it, not by editing that file.
- **The gate-copy question** — which copy of the gate module judges the worktree.
  Held as its own ticket; raise it after this one.
- **The pytest 9.0.3 bump** and how its in-container agent's gate survives the pin
  change. Its own grill; it closes Dependabot PR #1. This ticket lands first.

## Further notes

- The "ticket declares no commands" refusal inside `evaluate` is logged identically
  under D1/D2. No special wording; no decision needed.
- Before approval, probe every `verify` at base, at stubs and at impl. The two
  green-at-base guards (D6, and the pins-unchanged wording it pins) belong in the
  frozen file and in `full_gate`, not in `acceptance` — T022's precedent.
- Before approval, grep the frozen suites for fixtures that run `run_session` or
  `evaluate` for real and probe the change against them: `tests/test_gate_refusal.py`
  (`Night`; `changed_files` faked to `[]` keeps T021's tests on the old wording) and
  `tests/test_gate_trusted_inputs.py` (fakes a matching toolchain; never reaches the
  refusal). Neither is expected to need amendment; if one does, amend by hand
  pre-approval with `raising=False` and record it in the ticket's Context.

- Amendment 2026-09-15, after the first night passed (`4ecbbac`): review found that a
  ticket freezing `requirements-gate.txt` produced "requirements-gate.txt is in
  scope" on the refusal path, because `check_scope` trusts the freeze check to have
  run first. D7 added, one frozen test added, the branch reset to the contract
  commits and re-approved; the agent redoes the work. The grill never asked "what if
  the pins file is frozen?" — an unconsidered branch, not a decision reversed.

Deferred from the grill, all cheap to reverse:

- Exact prose of the two new sentences beyond the pinned substrings.
- A git failure inside `changed_files` on the refusal path escapes untyped and the
  log says `incomplete` — pre-existing on the happy path, not introduced here.
- Whether a refusal signature should be truncated; the reason carries version
  strings, which are stable across runs.

## Decisions

```yaml
decisions:
  - id: D1
    decision: A Refusal from evaluate still ends the session on first occurrence; the refused iteration is appended to the log before the re-raise (one evaluate call, one iteration, outcome aborted, exit 1)
    verify:
      - python3 -m pytest tests/test_refused_iteration.py::test_a_refused_iteration_is_logged_then_the_session_aborts -q
    frozen:
      - tests/test_refused_iteration.py
      - tests/test_gate_refusal.py
    scope:
      - edad/session.py
    seam: Night session
    rejected: retryable refusal (gate_passed=False, loop continues) — no Record for retry_prompt, environment unchanged between iterations, bump would burn its night budget
  - id: D2
    decision: The refused iteration reuses Iteration unchanged — gate_passed=False, signature "refusal:"+reason, violations=[reason], made_commit as measured, agent_output tail; no Record written for it
    verify:
      - python3 -m pytest tests/test_refused_iteration.py::test_the_refused_iteration_carries_the_verdict_the_commit_and_the_agent_tail -q
    frozen:
      - tests/test_refused_iteration.py
      - tests/test_gate_refusal.py
    scope:
      - edad/session.py
    seam: Night session
    rejected: a new `refused` field on Iteration — every log reader learns a field the signature prefix already carries
  - id: D3
    decision: A refused night whose agent committed is not a no-commit abort (no_commit_abort returns False, no_commit_aborts resets); one that committed nothing still is; no new breaker, no change to session_queue.py
    verify:
      - python3 -m pytest tests/test_refused_iteration.py::test_a_refused_night_that_committed_is_not_a_no_commit_abort -q
    frozen:
      - tests/test_refused_iteration.py
      - tests/test_gate_refusal.py
    scope:
      - edad/session.py
    seam: Queue reading
    rejected: a refusal-specific queue breaker — abort_reason already names the refusal; two refused nights is morning triage
  - id: D4
    decision: In evaluate only, with base_ref set and toolchain problems present, if requirements-gate.txt is in changed_files(root, base_ref) the refusal keeps the frozen prefix, says "worktree changed requirements-gate.txt" and "in scope", and never says "pip install"; base_ref None skips changed_files; unchanged pins keep "Install the pins"; approve and preflight untouched
    verify:
      - python3 -m pytest tests/test_refused_iteration.py::test_a_refusal_after_the_worktree_changed_the_pins_does_not_advise_installing_them -q
    frozen:
      - tests/test_refused_iteration.py
      - tests/test_gate_refusal.py
    scope:
      - edad/gate.py
    seam: Night session
    rejected: checking dirty pins at approve/preflight too — there the edit is the operator's and the install advice is right; pinning full sentences — the advice is the part expected to be reworded
  - id: D5
    decision: An out-of-scope pin change is named in the refusal reason as "out of scope: requirements-gate.txt" and therefore appears in iterations[0].violations on the session log; no partial Record, Refusal class unchanged
    verify:
      - python3 -m pytest tests/test_refused_iteration.py::test_a_refusal_after_an_out_of_scope_pin_change_names_the_stray_in_the_log -q
    frozen:
      - tests/test_refused_iteration.py
      - tests/test_gate_refusal.py
    scope:
      - edad/gate.py
      - edad/session.py
    seam: Night session
    rejected: Refusal.violations attribute — T021 pinned "nothing else on the class"; partial Record — a shape nothing reads that looks like a failed run
  - id: D6
    decision: With base_ref set and the pins unchanged, the refusal wording is unchanged, "Install the pins" included (green-at-base guard; frozen, run by full_gate, not in acceptance)
    verify:
      - python3 -m pytest tests/test_refused_iteration.py::test_a_refusal_with_the_pins_unchanged_keeps_the_install_advice -q
    frozen:
      - tests/test_refused_iteration.py
      - tests/test_gate_refusal.py
    scope:
      - edad/gate.py
    seam: Night session
    rejected: none
  - id: D7
    decision: When requirements-gate.txt is in the ticket's frozen list, the refusal names it as "frozen file modified: requirements-gate.txt" (checked against ticket["frozen"] before check_scope) and never says "in scope"; lands in iterations[0].violations like D5
    verify:
      - python3 -m pytest tests/test_refused_iteration.py::test_a_refusal_after_a_frozen_pin_change_names_the_frozen_file_not_the_scope -q
    frozen:
      - tests/test_refused_iteration.py
      - tests/test_gate_refusal.py
    scope:
      - edad/gate.py
    seam: Night session
    rejected: changing check_scope to reject frozen paths — every happy-path caller relies on the hash check having run first; running check_freeze before the toolchain refusal — the ordering is pinned by D4's rationale
deferred:
  - Exact prose of the two new sentences beyond the pinned substrings
  - A git failure inside changed_files on the refusal path escapes untyped (pre-existing on the happy path)
  - Whether a refusal signature should be truncated
```
