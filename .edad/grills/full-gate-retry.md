---
slug: full-gate-retry
grilled_at: 2026-09-15
---

## Record

Source: handoff `scratchpad/handoff-full-gate-feedback.md` (2026-09-15), the
paragraph in PR #6, and three session logs: `T020-20260914T164559.json`,
`T024-20260915T164131.json`, `T024-20260915T171448.json` — each `aborted` with
one iteration `gate_passed: true` and `abort_reason` starting "acceptance passed
but full_gate found failures this ticket introduced: ruff check . -> lint:…".

Goal: a ticket-introduced full_gate failure on a green implementation is handed
back to the agent as one more iteration instead of ending the night. After this
ships, a night whose only defect is a lint finding in the agent's own new code
finishes on the next iteration; nobody re-runs it from the approval lock.

Facts the design rests on, verified in the tree at `f657e77`:

- `initial_prompt` (`edad/session.py:630`) lists only `ticket["acceptance"]`
  and says "you are done when these commands exit 0". `full_gate` commands reach
  the agent only through `allowed_tools` (`:693`) — permissions, not text. The
  agent has never been asked to run the full gate.
- `run_session` (`:1031`) runs `evaluate(wt, ticket, "full_gate", base)` once,
  after the iteration loop (`:1118`); `full_gate_failure` (`:934`) returns
  `Unwinnable` (frozen file named), `Abort` (uncomparable baseline), `Abort`
  ("introduced"), or a fall-through `Abort`. All four end the night.
- `failure_signature` (`:830`) on a fully green record returns the constant
  `e3b0c44298fc1c14` (sha256 of empty output, truncated), which is truthy.
  `check_kills` (`:875`) fires `same_test_fails_consecutively` on any truthy
  signature repeated N times. Today a green iteration breaks the loop so this
  never matters; with retries it would kill a night for passing.
- `Record.new_failures` (`edad/gate.py:218`) carries stable keys per introduced
  failure, e.g. `lint:edad/session.py:I001`; ruff's raw output carries line
  numbers that move between iterations.
- `frozen_blocks` (`gate.py:1013`) classifies only failures naming a *frozen*
  file as unwinnable; a failure naming an out-of-scope, unfrozen file is
  "introduced".
- `session_queue.no_commit_abort` (`edad/session_queue.py:530`) reads only
  `outcome` and `iterations[].made_commit`.
- Frozen tests that pin the log: `tests/test_gate_refusal.py::
  test_a_refusal_at_the_full_gate_is_logged_the_same_way` asserts a green
  iteration followed by a full-gate refusal shows exactly one iteration with
  `gate_passed == True`; `tests/test_refused_iteration.py` imports `Night` from
  `test_gate_refusal.py` and asserts the refused iteration's fields by name (not
  the exact key set).

### D1 — Tell the agent the full-gate commands exist

The opening prompt gets a rule after rule 3: once the acceptance commands
pass, the `full_gate` commands also run; they are compared against a baseline;
anything they report in files the agent changed is the agent's to fix,
pre-existing failures elsewhere are not; run them before stopping. Every
`full_gate` command is listed verbatim.

Rejected: loop-only (costs an extra agent iteration most nights for nothing);
prompt-only (no structural protection, the abort stays possible); "must exit 0"
framing (false whenever the suite is red modulo baseline).

Scope: `edad/session.py`.

### D2 — The full gate runs inside the loop, only once acceptance is green

Same trigger as today, moved inside the iteration loop so its verdict can send
the agent back. An iteration whose acceptance fails never runs the full gate.

Rejected: every iteration (cost per iteration; the abort being fixed only
happens on green; two records to merge into one signature).

Scope: `edad/session.py`.

### D3 — Only an "introduced" full-gate failure retries; the other stops survive

`full_gate_failure`'s `Unwinnable` (a frozen file is named), its uncomparable-
baseline `Abort`, and its fall-through `Abort` still end the night: no agent
edit clears them. Only the "failures this ticket introduced" case becomes a
retry. An introduced failure naming only out-of-scope, unfrozen files is still
retried — the scoped edit often caused it and can fix it; if not, D4's repeat
kill bounds the waste at two extra iterations.

Rejected: also retrying uncomparable failures (the agent may be sent after
something pre-existing and outside its scope); aborting when no named path is
in scope (wrongly kills a night a scoped fix would clear; needs a new
classification branch and its own frozen tests).

Scope: `edad/session.py`.

### D4 — A full-gate retry spends an iteration; its signature is the introduced keys

The retry is iteration n+1 under the ticket's `max_iterations` (default 6) and
the same `check_kills`. The signature an iteration appends when acceptance is
green is `"full_gate:" + "|".join(sorted keys of full.new_failures)` when the
full gate found introduced failures, and `""` when both gates pass (the loop
ends anyway; `check_kills` ignores an empty tail). Acceptance failures keep
today's signature. This is what makes `same_test_fails_consecutively` fire on
the same lint rule missed three times at moving line numbers, and what stops
the constant green-record hash from firing it on success.

Rejected: hash signature as today (a repeated lint miss at a different line
never trips the kill; the night burns all 6 iterations); a separate, smaller
retry budget (a new ticket field and a second counter to freeze and explain);
changing `failure_signature` itself to return `""` on green (touches the
acceptance path for no gain).

Scope: `edad/session.py`.

### D5 — The Iteration record keeps `gate_passed` = acceptance and adds `full_gate`

`Iteration.gate_passed` still means the acceptance gate passed. New field
`full_gate: str | None`, default `None` (not run — acceptance failed, or the
full gate was refused before producing a verdict), else `"passed"`,
`"passed_modulo_baseline"`, or `"introduced"`. The full gate's violations are
appended to `Iteration.violations`. `outcome`, `abort_reason`, `made_commit`
are unchanged, so the queue concludes what it concludes today. Older logs
simply lack the key.

Rejected: `gate_passed` meaning both gates (loses "acceptance was green" from
the log); a separate `SessionLog.full_gate_attempts` list (two places for one
iteration's story); a fourth value `"refused"` (the refusal is already the
`abort_reason`; a second copy drifts).

Scope: `edad/session.py`.

### D6 — A full-gate retry gets its own, narrower prompt

`full_gate_retry_prompt(ticket, full, iteration, sandbox, network)`: iteration n
of the ticket passed its acceptance commands; the full gate found failures this
ticket introduced; the verifier's own output per failing command (same
`describe` treatment as `retry_prompt`, including the killed-command case);
clear these without changing behaviour, acceptance must still pass, same scope
and frozen rules, same network rule.

Rejected: reuse `retry_prompt` (opens "did not pass the gate … Fix the
implementation", inviting behaviour changes to green code).

Scope: `edad/session.py`.

### D7 — Exhaustion with acceptance green says so, naming the last failures

When the iteration budget runs out and the last iteration passed acceptance but
the full gate was still red, `abort_reason` is
`exhausted N iterations: acceptance passed, full_gate still failing: <cmd> ->
<keys>[; …]`, distinct from today's "exhausted N iterations without passing the
gate", which stays for the acceptance case.

Rejected: same message as today (indistinguishable from an acceptance failure
in the log).

Scope: `edad/session.py`.

### D8 — A Refusal at the full gate is unchanged

`evaluate(..., "full_gate", ...)` raising `Refusal` still propagates out of the
loop with no extra iteration appended; the green iteration's `full_gate` field
is `None`. The frozen test pinning this stays green.

Scope: `edad/session.py`.

### D9 — The module docstring's flow line is corrected

`edad/session.py:8` reads
`worktree -> [ prompt -> agent -> commit -> gate ]xN -> full gate -> evidence`.
It becomes a line in which the full gate sits inside the `xN` bracket, e.g.
`worktree -> [ prompt -> agent -> commit -> acceptance -> (full gate) ]xN -> evidence`.
QUICKSTART's "gate after every iteration" pointer stays true and is not touched.

Rejected: a new QUICKSTART paragraph (no section describes the loop today; it
would be a new one, out of proportion); no doc change (the flow line is the
first thing anyone reads in the file).

Scope: `edad/session.py`.

### Frozen test

`tests/test_full_gate_retry.py`, authored by the user before approval. It
builds its own driver (not `Night` from `test_gate_refusal.py`: the real
`evaluate` with the all-pass `FakeRun` cannot produce an "introduced" verdict
and would need patching on top) that replaces `session.evaluate` with a
scripted sequence of `Record`s and replaces `preflight`, `git`,
`harness_identity`, `make_worktree`, `run_agent`, `commit_iteration`,
`write_record` and `promote_evidence` the way `Night` does. Per memory
"probe each candidate wiring" and "frozen stand-ins pin call arity": run the
candidate change against the existing frozen suite (`grep -ln 'run_session\|
full_gate' tests/*.py`) before authoring; no signature in the frozen suite is
expected to change.

### One-record-per-attempt

`write_record(root, full)` now runs once per full-gate attempt, so
`.edad/records/` gains one full-gate record per green-acceptance iteration;
`promote_evidence` promotes the last, passing one. Not a decision — it is what
the existing functions do when called inside the loop — recorded so nobody
reads the extra records as a defect.


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

### Deferred (cheap to reverse)

- Exact sentences of the D1 rule and the D6 prompt.
- The console `gate:` line's full-gate verdict text.
- Whether `full_gate_retry_prompt` reuses `retry_prompt.describe` by extraction
  or by copy.

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
    rejected: gate_passed meaning both gates — hides that acceptance was green; separate SessionLog list — two places for one iteration; a "refused" value — duplicates abort_reason
  - id: D6
    decision: a full-gate retry uses its own prompt stating acceptance passed, quoting the verifier's output per failing command, and asking for the findings to be cleared without changing behaviour under the same scope, frozen and network rules
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_full_gate_retry_prompt_says_acceptance_passed_and_quotes_each_failure -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    rejected: reuse retry_prompt — opens "did not pass the gate... Fix the implementation", inviting behaviour changes to green code
  - id: D7
    decision: 'exhausting the budget with acceptance green and the full gate red aborts with "exhausted N iterations: acceptance passed, full_gate still failing: <cmd> -> <keys>"'
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_running_out_of_iterations_with_acceptance_green_names_the_full_gate_failures -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    rejected: today's generic exhaustion message — indistinguishable from an acceptance failure in the log
  - id: D8
    decision: a Refusal raised by the full-gate evaluate still propagates with no extra iteration; that iteration's full_gate field is None
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_a_refused_full_gate_leaves_the_field_unset -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    rejected: recording full_gate "refused" — a second copy of the abort reason
  - id: D9
    decision: the module docstring flow at edad/session.py:8 places the full gate inside the xN bracket; the old "]xN  ->  full gate  ->  evidence" sequence is gone
    verify:
      - python3 -m pytest tests/test_full_gate_retry.py::test_the_module_docstring_no_longer_puts_the_full_gate_after_the_loop -q
    frozen:
      - tests/test_full_gate_retry.py
    scope:
      - edad/session.py
    rejected: QUICKSTART paragraph — no section describes the loop today; no doc change — the stale line is the first thing read
deferred:
  - exact sentences of the D1 rule and the D6 prompt
  - the console `gate:` line's full-gate verdict text
  - whether full_gate_retry_prompt reuses retry_prompt.describe by extraction or by copy
```
