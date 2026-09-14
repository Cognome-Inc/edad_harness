---
slug: gate-refusal
grilled: null
status: draft
---

## Problem statement

Found in review of T020 (2026-09-14). `gate.die()` prints `edad: <msg>` and raises a
bare `SystemExit(2)`; `run_session` catches `Abort` and nothing else. Until T020, no
`die()` site sat inside the session's iteration loop in a way the agent's own edits
could trigger. T020 added one: `evaluate()` now measures the toolchain at the worktree
and refuses a mismatch before a `Record` exists. `preflight` checks the pins at the
repo root, `evaluate` checks them at `wt` — so the one thing that can flip the verdict
between the two is the agent editing `requirements-gate.txt`. Two tickets do that:
the queued pytest 8.4.2 → 9.0.3 bump, by design, in scope; and any ticket whose agent
strays into the pins file out of scope. Scope is checked *inside* `evaluate`, after
the toolchain check, so the stray is never recorded as the `diff_touches_outside_scope`
kill it is.

In both cases the `SystemExit` escapes `run_session`, the `finally` writes a session
log with the dataclass default — `outcome: "incomplete"`, `abort_reason: null` — and no
`ABORTED ... left at <wt>` line is printed. The message is on stderr, once, from
`die()`. The proxy is still removed (`cmd_run`'s `finally`) and the worktree is left.
The stop is right; the paper trail is wrong.

T020's frozen test pins that `evaluate` raises `SystemExit` with code 2 and the message
on stderr. Twenty-four other `die()` sites and every `pytest.raises(SystemExit)` in
the suite pin the same at the CLI. So the refusal must stay a `SystemExit`.

## Solution

A refusal names itself. `Refusal(SystemExit)` carries its reason: `code == 2`, `str()`
is the message. `die()` raises it — one change covers every site, nothing at the CLI
moves, every existing `SystemExit` assertion holds. `run_session` catches `Refusal`
beside `Abort` at the boundary it already has: the log says `aborted` with the
refusal as its `abort_reason`, the ABORTED line names the worktree, and the session
returns 1 — the exit code `session.main()` and the queue's `outcome_of` already read
as "failed". The boundary is the whole `try`, not one `evaluate` call: a refusal at
the acceptance gate and one at the full gate are logged the same way, and the
iterations that ran before it stay in the log.

Not `Unwinnable`: a pin the agent bumped is either the bump ticket's rollout problem
or a stray, and neither is "the ticket could never have passed". The bump ticket owns
how its own agent's gate survives a pin change; this ticket only makes the failure
legible.

## User stories

1. As an operator reading a session log after a night, I want a session the gate
   refused mid-run to say `aborted` and why, so that `incomplete` means what the
   dataclass says it means — the process died before the session could say anything
   — and not "the gate refused and nobody wrote it down".
2. As the author of the pytest bump ticket, I want the first in-container gate run
   after the pin change to leave a log naming the mismatch, so that the rollout
   problem T020 deferred to me is diagnosed from the log rather than from a missing
   line.
3. As a reviewer of an out-of-scope edit to the pins file, I want the log to carry
   the toolchain message even though the scope kill never fired, so that the stray
   is visible.
4. As a caller of any gate function outside the CLI, I want to catch a refusal by
   type and read its reason, so that I stop parsing stderr.

## Seams

Two. One new by construction; one exists.

- **`refusal`**
  - **Where**: `gate.die()` called directly; `gate.Refusal` reached as an attribute
    of the `gate` module.
  - **Exists**: new — the type is stubbed at base, `die` does not raise it.
  - **Observes**: `die()` raises an instance that is both a `Refusal` and a
    `SystemExit` with code 2, whose `str()` is the message, with `edad: <msg>` on
    stderr as before.
  - **Discharges**: D1.

- **`boundary`**
  - **Where**: `run_session(root, ticket, args)` driven from the top of its loop with
    `preflight`, `git`, `harness_identity`, `make_worktree`, `run_agent` and
    `commit_iteration` replaced on the `session` module, and the real `evaluate`
    steered by `measure_toolchain` faked on the `gate` module exactly as T020's tests
    do. The session log is read back from `<root>/.edad/sessions/`.
  - **Exists**: yes — the `try`/`except Abort`/`finally` in `run_session`.
  - **Observes**: with a mismatch at the first `evaluate`, the log says `aborted` with
    the toolchain message as `abort_reason`, stderr carries `ABORTED` and the worktree
    path, the return value is 1. With a mismatch only at the full gate, the passed
    iteration is in the log and the outcome is the same. At base both escape as
    `SystemExit` and the log says `incomplete`.
  - **Discharges**: D2.

## Implementation decisions

- `Refusal.__init__(reason)` calls `SystemExit.__init__(2)` and stores the reason;
  `__str__` returns it. Nothing else on the class.
- `die()` keeps printing before raising. The session boundary prints the ABORTED line
  too, so an in-session refusal appears twice on stderr — once in the gate's voice,
  once in the session's. Accepted: the second line is the one that names the worktree.
- `except (Abort, Refusal) as e` on the existing handler; the `Unwinnable` isinstance
  is unchanged. No new outcome string.
- The `Iteration` for a refused acceptance gate is not appended — there is no `Record`
  to build it from. The agent's output for that iteration is therefore not in the
  log. Deferred, not decided: logging the agent tail on a refused iteration needs an
  `Iteration` without a verdict, which is a shape nothing reads yet.

## Out of scope

- **The pytest 9.0.3 bump** and how its in-container agent's gate survives the pin
  change. T020 deferred the rollout to that ticket; this ticket makes its failure
  mode legible, nothing more.
- **`tests/test_session_queue.py:301`'s docstring** ("a bare SystemExit(2) from
  twenty-five sites that `session.main()` does not catch") — a frozen file of a done
  ticket; the sentence stays true at the CLI, which is the property it argues from.
- **Changing what `session.main()` or `gate.main()` return.** A `Refusal` is a
  `SystemExit`; both mains are untouched.
- **Checking scope before the toolchain in `evaluate`.** Would make the stray case a
  scope kill instead of a refusal. Not wrong, but a different ordering of the three
  checks than the one T020's frozen test pins (`harness_identity` and `run_commands`
  unreached on a mismatch), and the log is honest either way once this lands.

## Decisions

```yaml
decisions:
  - id: D1
    decision: "gate.Refusal is a SystemExit subclass with code 2 whose str() is the reason; gate.die(msg) prints 'edad: <msg>' to stderr as before and raises Refusal(msg), so every die() site is catchable by type and unchanged at the CLI"
    verify:
      - python3 -m pytest tests/test_gate_refusal.py::test_die_raises_a_refusal_that_is_still_an_exit_2 -q
    frozen:
      - tests/test_gate_refusal.py
    scope:
      - edad/gate.py
    seam: refusal
    rejected: a Refusal that is not a SystemExit — breaks T020's frozen evaluate test and every pytest.raises(SystemExit) in the suite, and moves both mains; converting only die_on_toolchain_mismatch — leaves the other twenty-four sites as the same hazard
  - id: D2
    decision: "run_session catches Refusal beside Abort at its existing boundary: outcome aborted, abort_reason the refusal's message, the ABORTED line naming the worktree, return 1; the same for a refusal at the acceptance gate and at the full gate, with earlier iterations kept in the log"
    verify:
      - python3 -m pytest tests/test_gate_refusal.py::test_a_refusal_at_the_acceptance_gate_is_logged_as_aborted_with_its_reason -q
      - python3 -m pytest tests/test_gate_refusal.py::test_a_refusal_at_the_full_gate_is_logged_the_same_way -q
    frozen:
      - tests/test_gate_refusal.py
    scope:
      - edad/session.py
    seam: boundary
    rejected: catching bare SystemExit at the boundary — SystemExit(2) carries no reason, so abort_reason would be '2'; wrapping each evaluate call — misses the next die() site; a new outcome 'refused' — nothing reads it and outcome_of already maps 1 and 2 alike
```
