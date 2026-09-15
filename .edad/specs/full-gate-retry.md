---
slug: full-gate-retry
grilled: .edad/grills/full-gate-retry.md
status: draft
---

## Problem statement

A night runs the agent in iterations. After each one the ticket's own acceptance
commands run; once they pass, the broader full gate — the linter and the whole
suite — runs once. If that run fails because of something the agent itself just
wrote, the night ends: no retry, no message to the agent, and the next run rebuilds
the worktree from the approval lock, discarding an implementation whose acceptance
was green. Three nights have been lost this way (T020, T024 nights 1 and 4), each to
a single ruff finding in the agent's own new code, each recovered only by a manual
re-run that passed first time.

The agent is also never told the full gate exists. Its opening prompt lists only the
acceptance commands and says it is done when they exit 0. The full-gate commands
reach it only as permission patterns — what it may run, not what it is asked to run.
So the lost nights were not disobedience: the agent was told it was finished, and
it was.

## Solution

The agent is told up front that the full gate runs after acceptance, what its
commands are, and that anything they report in files the agent changed is the
agent's to clear. The full gate moves inside the iteration loop: once acceptance
passes it runs, and a failure the ticket introduced is handed back to the agent as
one more iteration, with the verifier's exact output and a narrower instruction —
acceptance is green, clear these without changing behaviour. That iteration counts
against the ticket's normal budget and the same kill conditions, so a lint rule
missed three iterations running still ends the night. Failures that are not the
agent's to fix — inside a frozen file, or ones the baseline cannot compare — still
end the night as they do today.

The session log gains one field per iteration saying how the full gate went, keeps
its existing meaning for everything else, and the overnight queue reads a retried
night exactly as it reads any other.

## User stories

1. As the operator, I want a night whose only defect is a lint finding in the
   agent's own code to finish on the next iteration, so that a green implementation
   is not discarded and rebuilt from scratch.
2. As the agent, I want to be told the full-gate commands and that findings in files
   I changed are mine to clear, so that I run them before I stop rather than learning
   about them from a retry.
3. As the agent sent back for a full-gate failure, I want to be told my acceptance
   tests pass and shown the verifier's exact output, so that I clear the findings
   without rewriting working code.
4. As the operator, I want a full-gate retry to spend an iteration under the same
   limits as any other, so that a stuck agent cannot loop on lint forever.
5. As the operator, I want the same finding missed three iterations running to end
   the night with the finding named, even when its line number moved, so that the
   repeat kill works for lint the way it works for tests.
6. As the operator, I want a full-gate failure inside a frozen file, or one the
   baseline cannot compare, to still end the night, so that a contract problem is
   not retried as if the agent could fix it.
7. As the operator reading a session log, I want each iteration to say whether the
   full gate ran and what it found, separately from whether acceptance passed, so
   that a lint miss on green code is distinguishable from a broken implementation.
8. As the operator, I want a night that runs out of iterations with acceptance green
   to say so and name the full-gate failures still standing, so that I can tell it
   from a night that never passed acceptance.
9. As the overnight queue, I want a retried night's log to read the way any log
   reads today, so that nothing I conclude about progress changes.
10. As the operator, I want a toolchain refusal at the full gate to be logged exactly
    as it is today, so that the existing frozen test for it stays green.

## Seams

- **Scripted night** — **Where**: a driver in the new frozen test file that runs
  `run_session` with `session.evaluate` replaced by a scripted sequence of `Record`s
  (acceptance pass, full gate introduced, full gate pass, …) and the same side
  effects replaced that T021's `Night` replaces — preflight, git, the worktree, the
  agent, the commit — plus record writing and evidence promotion, which need a real
  git worktree. **Exists**: the pattern (`Night`) exists; this driver is new, and
  self-contained in the new file. **Observes**: the session log written under
  `.edad/sessions/` (`iterations[].gate_passed`, `iterations[].full_gate`,
  `iterations[].signature`, `iterations[].violations`, `outcome`, `abort_reason`),
  the return code, stderr, the sequence of gate names `evaluate` was asked for, and
  the prompt handed to each agent run through the faked agent's argv.
  **Discharges**: D2, D3 (the retry half), D4, D5, D7, D8.
- **Prompt builders** — **Where**: `initial_prompt` and the new
  `full_gate_retry_prompt`, called directly and their text read, as
  `tests/test_session_network.py` already does for `initial_prompt`. **Exists**:
  yes; the new builder is a new name at the same seam. **Observes**: the prompt
  text. **Discharges**: D1, D6.
- **Failure classification** — **Where**: `full_gate_failure`, a pure function over
  a `Record`, as `tests/test_session_promotion.py` already exercises it.
  **Exists**: yes. **Observes**: which kind of stop a failed full gate is.
  **Discharges**: D3 (the still-aborts half).
- **Queue reading** — **Where**: `session_queue.no_commit_abort`, a pure function
  over the log dict, fed a log the scripted night produced. **Exists**: yes.
  **Observes**: whether the queue counts a given log toward `no_commit_aborts`.
  **Discharges**: D5 (the queue-unchanged claim).
- **Module docstring** — **Where**: `edad.session.__doc__`. **Exists**: yes.
  **Observes**: the flow line at the top of the module. **Discharges**: D9.

No new seam beyond the scripted driver. Reusing `Night` from
`tests/test_gate_refusal.py` was considered and not taken: it runs the real
`evaluate` with every command passing and cannot produce an "introduced" verdict
without patching on top. Every decision has a seam; nothing is unenforced.

## Implementation decisions

**The opening prompt.** A rule is added after the "you are done when these exit 0"
rule: once the acceptance commands pass, the full-gate commands also run; they are
compared against a baseline; anything they report in files the agent changed is the
agent's to fix and pre-existing failures elsewhere are not; run them before stopping.
Every full-gate command is listed verbatim. The permission list is already derived
from both command lists and is not touched (D1).

**The loop.** The full gate no longer runs after the loop. Inside it, when an
iteration's acceptance passes, the full gate runs in that same iteration. Three
outcomes: it passes (outright or modulo the approved baseline) and the session
promotes evidence as today; it failed for a reason the existing classifier calls
unwinnable, uncomparable, or unexplained, and that exception ends the night as today;
it found failures this ticket introduced, and the loop continues with the full-gate
retry prompt. The full gate never runs in an iteration whose acceptance failed. A
failure naming only files outside the ticket's scope but not frozen is "introduced"
and is retried like any other; if the agent cannot clear it from scope the repeat
kill ends the night after three identical signatures (D2, D3).

**Budget and the repeat kill.** A full-gate retry is the next iteration under the
ticket's `max_iterations` and the same `check_kills`. The signature an iteration
appends to the kill list when acceptance is green is the introduced-failure keys the
gate record already holds, joined and prefixed so they cannot be mistaken for an
acceptance signature, or the empty string when both gates pass. This replaces the
constant hash a green record produces today, which is truthy and would otherwise
fire the repeat kill on three passing acceptance runs in a row. Acceptance failures
keep today's signature; the shared signature function is not changed (D4).

**The iteration record.** `gate_passed` keeps meaning the acceptance gate passed.
One field is added: the full gate's verdict, unset when it did not run (acceptance
failed, or the gate was refused before producing a verdict), otherwise passed,
passed modulo baseline, or introduced. The full gate's violations are appended to
the iteration's violations. Outcome, abort reason and whether the agent committed
are unchanged, so the queue's no-commit check reads a retried night as it reads any
other. Older logs lack the key and nothing reads it (D5).

**The retry prompt.** A second prompt builder, distinct from the acceptance retry
prompt, states that the iteration passed its acceptance commands and that the full
gate found failures this ticket introduced, quotes the verifier's output per failing
command with the same killed-command treatment the acceptance retry uses, and asks
for the findings to be cleared without changing behaviour, under the same scope,
frozen and network rules. It exists because the acceptance retry prompt opens with
"did not pass the gate … fix the implementation", which on green code invites the
wrong kind of edit (D6).

**Exhaustion.** When the budget runs out and the last iteration passed acceptance but
the full gate was still red, the abort reason says so and names the commands and
keys still failing. The existing exhaustion message is kept for the case where
acceptance never passed (D7).

**Refusal at the full gate.** Unchanged: a refusal raised by the full-gate `evaluate`
propagates out of the loop, no extra iteration is appended, and the green iteration's
full-gate field stays unset (D8).

**Records.** The full-gate record is written once per attempt, so the records
directory gains one full-gate record per green-acceptance iteration; evidence
promotes the last, passing one. Not a decision — it is what the existing functions
do when called inside the loop — noted so the extra records are not read as a
defect.

**The docstring.** The module's flow line places the full gate inside the repeated
bracket; the old sequence with the full gate after the loop is gone. QUICKSTART's
"gate after every iteration" pointer stays true and is not touched (D9).

**Frozen test.** One new file with its own scripted driver, authored before
approval. Per the standing rule, the candidate change is probed against the frozen
suite before authoring; no signature in the frozen suite is expected to change.

## Out of scope

- **Running the full gate on every iteration.** Rejected at D2.
- **Retrying uncomparable or unwinnable full-gate failures.** Rejected at D3; those
  are ticket or tool problems, not agent problems.
- **A separate retry budget or a new ticket field.** Rejected at D4; `max_iterations`
  and `same_test_fails_consecutively` are reused as-is.
- **Changing the queue.** Nothing in D5 alters what it reads; `edad/session_queue.py`
  is not in scope.
- **A QUICKSTART section on the loop.** Rejected at D9.
- **The T023 review finding 2 grill and the pytest 8.4.2 → 9.0.3 bump.** Sequenced
  after this ticket; the bump's next agent night runs under this loop.
- **The gate-copy ticket.** Still held.

## Further notes

**Amendment, 2026-09-15 (at `/to-tickets`, D5).** The field's four values said
nothing about a full gate that ended the night as unwinnable or uncomparable. It
stays `None` there: the abort reason already names the outcome, and a second copy
on the iteration is the drift the rejected `"refused"` value was avoiding. The
full gate's violations are still appended to that iteration's `violations`, so the
iteration is not silent about it. Not pinned by a frozen test; cheap to reverse.

**Amendment, 2026-09-15 (at `/to-tickets`).** D3, D5 and D8 listed existing,
green-today test runs as verification (`tests/test_session_promotion.py`,
`tests/test_refused_iteration.py`, `tests/test_session_queue.py`, and
`test_gate_refusal.py::test_a_refusal_at_the_full_gate_is_logged_the_same_way`).
`edad.gate approve` refuses a whole-file pytest command and refuses any acceptance
command that produces no `FAILED` before the work exists, so none of them can be an
acceptance command. They are removed from `verify` and `frozen`; they still run
under the ticket's `full_gate` (`python3 -m pytest -q`), which is where a
regression in them is caught. The decisions themselves are unchanged.

Deferred from the grill, all cheap to reverse:

- Exact sentences of the D1 rule and the D6 prompt — the tests pin substance
  (each command named, "baseline", acceptance passed), not wording.
- The console `gate:` line's full-gate verdict text.
- Whether the retry prompt reuses the acceptance retry's `describe` helper by
  extraction or by copy.

The named test functions in the decisions block do not exist yet; they are the
contract for the frozen file the user writes before approval.

## Decisions

```yaml
decisions:
  - id: D1
    decision: initial_prompt lists every full_gate command, says they run once acceptance passes, are judged against a baseline, and findings in files the agent changed are the agent's to clear
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_opening_prompt_names_every_full_gate_command_and_the_baseline_rule -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Prompt builders
    rejected: loop-only — costs an extra iteration most nights; prompt-only — no structural protection; "must exit 0" framing — false when the suite is red modulo baseline
  - id: D2
    decision: the full gate runs inside the iteration loop, only in an iteration whose acceptance passed
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_full_gate_does_not_run_when_acceptance_fails -q
      - python3 -m pytest tests/test_full_gate_retry.py::test_an_introduced_full_gate_failure_is_retried_and_the_next_iteration_promotes -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Scripted night
    rejected: full gate on every iteration — cost per iteration, and the abort being fixed only happens on green
  - id: D3
    decision: only the "introduced" full_gate_failure outcome becomes a retry; Unwinnable, the uncomparable-baseline Abort and the fall-through Abort still end the night; out-of-scope unfrozen introduced failures are retried too
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_an_unwinnable_full_gate_still_ends_the_night -q
      - python3 -m pytest tests/test_full_gate_retry.py::test_an_uncomparable_full_gate_still_ends_the_night -q
      - python3 -m pytest tests/test_full_gate_retry.py::test_an_introduced_failure_outside_scope_is_retried_not_aborted -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Scripted night; Failure classification
    rejected: retrying uncomparable failures — may be pre-existing and outside scope; aborting when no named path is in scope — kills nights a scoped fix would clear, needs a new classification branch
  - id: D4
    decision: a full-gate retry counts under max_iterations and the same kill conditions; a green-acceptance iteration's signature is "full_gate:" + sorted new_failures keys, or "" when both gates pass
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_same_introduced_keys_three_iterations_running_end_the_night -q
      - python3 -m pytest tests/test_full_gate_retry.py::test_two_retries_with_different_keys_then_a_pass_promote -q
      - python3 -m pytest tests/test_full_gate_retry.py::test_a_full_gate_retry_spends_an_iteration_of_the_ticket_budget -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Scripted night
    rejected: hash signature as today — moving line numbers never trip the repeat kill; separate retry budget — second counter and ticket field to freeze; changing failure_signature globally — touches the acceptance path for no gain
  - id: D5
    decision: Iteration.gate_passed keeps meaning acceptance passed; new field full_gate is None, "passed", "passed_modulo_baseline" or "introduced" (None also when the full gate ended the night as unwinnable or uncomparable - abort_reason carries that); full-gate violations are appended to violations; the queue's reads are unchanged
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_iteration_log_says_acceptance_passed_and_what_the_full_gate_found -q
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_queue_reads_a_retried_night_the_same_way -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Scripted night; Queue reading
    rejected: gate_passed meaning both gates — hides that acceptance was green; separate SessionLog list — two places for one iteration; a "refused" value — duplicates abort_reason
  - id: D6
    decision: a full-gate retry uses its own prompt stating acceptance passed, quoting the verifier's output per failing command, and asking for the findings to be cleared without changing behaviour under the same scope, frozen and network rules
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_full_gate_retry_prompt_says_acceptance_passed_and_quotes_each_failure -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Prompt builders
    rejected: reuse retry_prompt — opens "did not pass the gate... Fix the implementation", inviting behaviour changes to green code
  - id: D7
    decision: 'exhausting the budget with acceptance green and the full gate red aborts with "exhausted N iterations: acceptance passed, full_gate still failing: <cmd> -> <keys>"'
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_running_out_of_iterations_with_acceptance_green_names_the_full_gate_failures -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Scripted night
    rejected: today's generic exhaustion message — indistinguishable from an acceptance failure in the log
  - id: D8
    decision: a Refusal raised by the full-gate evaluate still propagates with no extra iteration; that iteration's full_gate field is None
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_a_refused_full_gate_leaves_the_field_unset -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Scripted night
    rejected: recording full_gate "refused" — a second copy of the abort reason
  - id: D9
    decision: the module docstring flow at edad/session.py:8 places the full gate inside the xN bracket; the old "]xN  ->  full gate  ->  evidence" sequence is gone
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_module_docstring_no_longer_puts_the_full_gate_after_the_loop -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    seam: Module docstring
    rejected: QUICKSTART paragraph — no section describes the loop today; no doc change — the stale line is the first thing read
deferred:
  - exact sentences of the D1 rule and the D6 prompt
  - the console `gate:` line's full-gate verdict text
  - whether full_gate_retry_prompt reuses retry_prompt.describe by extraction or by copy
```
