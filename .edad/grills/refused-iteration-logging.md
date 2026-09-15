---
slug: refused-iteration-logging
grilled_at: 2026-09-15
---

## Record

Grilled 2026-09-15 against `main` @ `60def98` (PR #4 merged; T020–T022 promoted).
Input: the handoff for review findings #1 and #2 from 2026-09-14; the starting point
was T021's deferral at `.edad/specs/gate-refusal.md:100-103` ("logging the agent tail
on a refused iteration needs an `Iteration` without a verdict, which is a shape
nothing reads yet"). This grill closes that deferral by citation; T021's spec is not
edited. #1 and #2 are one ticket, landing before the pytest 9.0.3 bump (decided
2026-09-14, recorded in the handoff; not re-opened here).

### Facts established by running, not asking

- Reproduced #1 through T021's `Night` fixture: an agent that edits the pins in
  iteration 1 produces a session log with `outcome: aborted`, `iterations: []`;
  `session_queue.no_commit_abort(log)` returns `True`; two such nights make
  `breaker_fired(no_commit_aborts=2, ...)` return `"no_progress"`.
- A `Refusal` already ends the session on its first occurrence: the
  `except (Abort, Refusal)` at `edad/session.py:1064` is outside the iteration
  loop. There is no retry today. The handoff's "two refusals in a row" question
  only exists if refusals are made retryable.
- `Iteration.signature` is read only by `check_kills` (`edad/session.py:826-830`),
  which the loop never reaches after a refusal. On the log it is a display field.
- Nothing reads `.edad/records/`; only `write_record` (`edad/gate.py:1907`) writes
  there. No one-Record-per-iteration expectation exists.
- Two `die()` sites are reachable inside `evaluate`: "ticket declares no
  '<gate>' commands" (`edad/gate.py:1793`) and the toolchain mismatch
  (`edad/gate.py:1796`). Nothing `evaluate` calls after the Record exists dies.
- The "Install the pins: pip install -r requirements-gate.txt" advice lives in two
  places: `edad/gate.py:814-823` (`die_on_toolchain_mismatch`, shared by `evaluate`
  and `cmd_approve`) and the session preflight `edad/session.py:113-121`. Approve
  and preflight run against the operator's checkout, where the advice is right.
  Only `evaluate` runs against the agent's worktree.
- The prefix "does not match requirements-gate.txt" is frozen twice:
  `tests/test_harness_identity.py:405` (via `evaluate(tmp_path, TICKET)` — no
  `base_ref`, `tmp_path` is not a git repo) and `MISMATCH` in
  `tests/test_gate_refusal.py`. The advice sentence is pinned nowhere.
- `no_commit_abort` is frozen at `tests/test_session_queue.py:731-737` on
  `iterations[].made_commit` alone.
- T022's `tests/test_gate_trusted_inputs.py` fakes `measure_toolchain` to match the
  pins, so it never reaches the refusal branch; the #2 change is unreachable from
  that suite. `Night` is the only frozen fixture that reaches it; there
  `changed_files` is faked to `[]` and `commit_iteration` to a fixed SHA distinct
  from the fake HEAD, so `made_commit` is `True`.
- No direct callers of `die_on_toolchain_mismatch` in `tests/`; keyword args with
  defaults change no frozen call.
- Probe: a file in `tests/` can `from test_gate_refusal import Night, MeasureSequence,
  measured` under pytest's default prepend import mode (`pythonpath = ["."]`,
  `testpaths = ["tests"]`, `tests/` is not a package). Ran and passed, then removed.

### Decisions, in the order made

**D1 — A refusal stays a session-ending abort; the refused iteration is logged first.**
`run_session` wraps `rec = evaluate(...)` in `try/except Refusal`, appends the
`Iteration`, and re-raises. Exactly one `evaluate` call per refused session, exactly
one iteration in the log, `outcome: aborted`, `abort_reason` = the refusal, exit 1.
The bump ticket's "in-container gate survives the pin change" question is untouched
and stays the bump's own grill.
Rejected: retryable refusal (`gate_passed=False`, loop continues) — the environment
does not change between iterations, `retry_prompt` would have no `Record` to describe
to the agent, and the bump would burn its whole night budget being refused.

**D2 — The logged iteration reuses `Iteration` unchanged.** `gate_passed=False`,
`signature="refusal:" + reason`, `violations=[reason]`, `made_commit` as measured,
`agent_output=out[-AGENT_TAIL:]`. No `Record` is written for a refused iteration.
Distinguishable from a failed gate by the `refusal:` prefix and by `abort_reason`.
Rejected: a new `refused: str | None` field — every log reader learns a field for a
distinction the signature prefix already carries.

**D3 — The queue reads a refused-but-committed night as not a no-commit abort; no
new breaker, no queue change.** With D2, `no_commit_abort` sees `made_commit=True`
and returns `False`, so `no_commit_aborts` resets. A refused night whose agent
committed nothing still counts (`True`). Two refused nights across tickets is
morning triage — `abort_reason` names the refusal — not a breaker.
Rejected: a refusal-specific breaker in `session_queue.py` — more code and a frozen
queue test for a signal the operator already reads by name.

**D4 — The worktree-changed-the-pins wording, in `evaluate` only, on `base_ref` only.**
When toolchain problems exist AND `base_ref` is set AND `requirements-gate.txt` is in
`changed_files(root, base_ref)`, the refusal keeps the frozen prefix
"the gate's toolchain does not match requirements-gate.txt: <problems>", then says
"worktree changed requirements-gate.txt" and whether it is "in scope" for the
ticket, and does NOT say "pip install". When `base_ref` is `None`, `changed_files`
is not called at all (it would `git status` a non-repo in
`test_harness_identity.py`) and the wording is unchanged. When the pins are
unchanged the wording is unchanged, "Install the pins" included.
`die_on_toolchain_mismatch` grows keyword arguments with defaults; `cmd_approve`'s
call and the session preflight's own message are untouched.
Pinned by substring, not full sentence: prefix (already `MISMATCH`),
`worktree changed requirements-gate.txt`, `in scope` / `out of scope:
requirements-gate.txt`, and `"pip install" not in reason`. Prose beyond those is the
implementer's.
Rejected: checking a dirty `requirements-gate.txt` at approve and preflight too — a
dirty checkout there is the operator's own edit, and the install advice is right.
Rejected: pinning full sentences (T022 D8 style) — the advice is the one part
expected to be reworded.

**D5 — An out-of-scope pin change is recorded in the refusal reason as
`out of scope: requirements-gate.txt`**, `check_kills`' own wording, and therefore
lands in `iterations[0].violations` on the session log via D2. That is the record.
No partial `Record` in `.edad/records/`; the `Refusal` class is unchanged.
Rejected: `Refusal.violations: list[str]` — T021's spec pinned "nothing else on the
class". Rejected: writing a partial `Record` before the toolchain check — a shape
nothing reads, and one with `commands_ok=False` and no commands reads as a failed
run rather than a refused one.

**Frozen file placement.** New `tests/test_refused_iteration.py` importing `Night`,
`MeasureSequence`, `measured` from `tests/test_gate_refusal.py`. Both files are
listed under `frozen` so the agent cannot alter the fixture. Any `Night` amendment
is hand-made pre-approval with `raising=False` where needed, recorded in the
ticket's Context (precedent `1f8ee1b`). The out-of-scope test may call
`run_session(night.root, {**TICKET, "scope": [...]}, night.args)` directly rather
than amend the fixture.
Rejected: amending T021's frozen file — a done ticket's frozen file grows and its
stale lock drifts further. Rejected: copying `Night` — two fixtures to keep in step.

**Ticket scope.** `edad/session.py` and `edad/gate.py` only. QUICKSTART/README do
not describe the session log's iteration shape or the refusal advice.
Rejected: adding `.edad/specs/gate-refusal.md` to scope to edit the deferral
paragraph — the new spec cites and closes it.

**Not a decision, noted:** the "no commands" `die` at `edad/gate.py:1793` is also a
`Refusal` inside `evaluate` and is logged identically under D1/D2. No special
wording.

### Verification

Every `verify` below must be red at base (the file does not exist yet) and green at
impl; the two green-at-base guards live in the frozen file but not in `acceptance`
(T022 precedent) — `full_gate` runs them. Probe each at base, stubs and impl per
the house rule before approval.

### Deferred (cheap to reverse)

- Exact prose of the two new sentences beyond the pinned substrings.
- A git failure inside `changed_files` on the refusal path escapes untyped and the
  log says `incomplete` — pre-existing on the happy path, not introduced here.
- Whether `signature` for a refusal should be truncated; the reason carries the
  version strings, which are stable across runs.

### Held, not folded in (own tickets, raise after this one)

- The gate-copy ticket: which copy of `edad/gate.py` judges the worktree
  (`python3 -m pytest` from a worktree puts its `edad/` first on `sys.path`).
- The pytest 9.0.3 bump's in-container-gate question; it closes Dependabot PR #1.

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
    rejected: none
deferred:
  - Exact prose of the two new sentences beyond the pinned substrings
  - A git failure inside changed_files on the refusal path escapes untyped (pre-existing on the happy path)
  - Whether a refusal signature should be truncated
```
