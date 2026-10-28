---
slug: review-loops
grilled_at: 2026-10-27
---

## Record

### Why

Human approval of frozen tests is the bottleneck on overnight multi-ticket
runs: a night can only carry as many tickets as the operator could read the
tests of during the day. The lock itself is cheap and stays; what changes is
who has to be satisfied before it is taken. Separately, nothing today reviews
code after the gate passes — the gate checks freeze, scope and acceptance
commands (plus ruff in full_gate), then stops at "not merged — review and
merge" (`edad/session.py:1243`). Two changes, grilled together:

1. **Test-review loop** replacing human reading of tests before lock.
2. **Post-build review panel** after the gate passes.

Standing rule across both (user, 2026-10-27): every review runs in a new
session / subagent with clean context, seeing only the spec and the artifact
under review, so the reviewer takes an unbiased fresh look.

### Decisions, in the order made

**D1 — Tests are written and reviewed in the daytime, then auto-locked.**
At ticket-making time a review command sends the tests to a fresh reviewer,
loops up to 3 rounds, and locks on pass. The night controller only runs locked
tickets, unchanged. A ticket that exhausts its rounds stays unlocked.
Rejected: writing+reviewing at night per ticket — large controller change, and
a failed review is only discovered in the morning (its upside, dependent
tickets seeing the real built interface, was judged not worth it). Rejected:
daytime write / night review — splits the work oddly, inherits both downsides.
Verify: `python3 -m pytest tests/test_test_review.py::test_review_stops_after_three_rounds_and_leaves_ticket_unlocked -q`

**D2 — The human approves acceptance criteria; the lock requires a passing
review for exactly the frozen bytes.** `gate approve` refuses unless a passing
test-review record exists whose hashes match the current frozen files, and
refuses if criteria changed since the human approved them. A human override
remains for emergencies and records who approved. The night's just-in-time
re-approval (`edad/session_queue.py:479`, which calls `gate approve`) therefore
also re-checks the review record; it succeeds whenever the tests are unchanged.
Approve already proves red-at-base (`edad/gate.py:1727`); the review does not
duplicate that.
Rejected: approve nothing up front — criteria would never be seen by a human
before a night runs on them. Rejected: review optional/advisory — nothing would
stop an unreviewed test from being locked.
Verify: `python3 -m pytest tests/test_gate_approve.py::test_approve_refuses_without_a_passing_review_for_these_exact_test_bytes tests/test_gate_approve.py::test_approve_refuses_when_criteria_changed_since_human_approval tests/test_gate_approve.py::test_human_override_records_who_approved -q`

**D3 — Mutation score is a morning note, never a block.** Mutation testing
needs real code, so it runs after the build, not at test review. Weak tests are
reported (score + surviving mutants); the coding agent cannot fix frozen tests,
so blocking would only stall the night. The operator decides whether to amend
the contract and re-run (fix the contract, not the branch).
Naming: the gate already uses "mutation" for characterization-test mutation
blocks (`mutation_entries`, `edad/gate.py:1723`). The new check is called the
**mutation score** everywhere to keep the two distinct.
Rejected: block below a threshold — fails the build for a test-authoring
problem the agent cannot fix. Rejected: skip mutation — nothing objective would
measure whether tests have substance.
Verify: `python3 -m pytest tests/test_mutation_score.py::test_mutation_survivors_go_to_morning_notes_and_do_not_fail_the_ticket -q`

**D4 — After-build outcomes.** Confirmed security, blocker and major findings
go back to the coding agent to fix that night; nits go to the morning notes
(user decision, stated before the grill). Up to 2 fix rounds. Unfixed security
or blocker fails the ticket (and so stops its dependents in the queue);
unfixed major passes but is flagged first in the morning notes.
Rejected: all three fail the ticket — more failures over arguable majors.
Rejected: nothing fails — a confirmed security issue could reach the run branch.
Verify: `python3 -m pytest tests/test_review_panel.py::test_unfixed_security_finding_fails_ticket_after_two_rounds tests/test_review_panel.py::test_unfixed_major_passes_and_is_flagged_first_in_morning_notes -q`

**D5 — The writer is the ticket-making session; the reviewer is always a new
process.** Tests are written during /to-tickets as today; the skill then calls
the review command, which spawns a new `claude -p` reviewer given only the spec
and the tests (no resume/continue of any session). The writer revises and
re-submits up to the round cap.
Rejected: a fresh writer agent too — loses the discussion context behind the
spec and guesses more; the bias concern is the reviewer's, which stays fresh.
Verify: `python3 -m pytest tests/test_test_review.py::test_reviewer_runs_as_a_new_claude_process_given_only_the_spec_and_tests tests/test_test_review.py::test_reviewer_prompt_holds_the_spec_tests_and_rubric_and_nothing_else -q`

**D6 — v1 panel is code + security reviewers, in parallel fresh sessions.**
The panel is built so reviewers can be added; UX and UI-design reviewers are
deferred until a ticket touches a user interface (UI review needs the app
running plus screenshots — a separate piece of work).
Rejected: all four reading code only — UI review without seeing the screen is
weak. Rejected: all four with screenshots — largest build, untestable on any
current ticket.
Verify: `python3 -m pytest tests/test_review_panel.py::test_panel_runs_code_and_security_reviewers_as_parallel_fresh_sessions -q`

**D7 — Fix rounds have their own cap (2) but share the ticket's diff-line
cap.** Separate from `max_iterations`; total diff must still fit
`max_diff_lines`. A fix that blows the size cap means the shape was wrong,
which is the cap's job to catch.
Rejected: separate line budget — the cap stops catching a change that has
outgrown its shape. Rejected: share everything — a ticket that took many build
iterations has nothing left for fixes.
Verify: `python3 -m pytest tests/test_review_panel.py::test_fix_rounds_have_their_own_cap_but_share_the_diff_line_cap -q`

**D8 — bandit, version-pinned in `requirements-gate.txt`, measured with the
toolchain like ruff.** Nights run with network denied; bandit is fully offline.
Rejected: semgrep — fetches rules from its registry by default; offline use
means vendoring and maintaining rules. Rejected: no scanner — security would
rest on judgment alone.
Verify: `python3 -m pytest tests/test_gate_toolchain.py::test_bandit_is_pinned_and_measured_with_the_toolchain -q`

**D9 — Test review passes when no blocker or major remains; disputes allowed.**
Nits are noted, not required. The writer may dispute a finding with a written
reason; the next round's new reviewer sees the finding and the reason and
rules on it. Reviewer output that does not match the expected structure counts
as a failed round.
Rejected: zero findings, no disputes — a picky or wrong reviewer can sink a
good ticket in three rounds.
Verify: `python3 -m pytest tests/test_test_review.py::test_review_passes_with_only_nits_left tests/test_test_review.py::test_a_disputed_finding_and_its_reason_reach_the_next_reviewer tests/test_test_review.py::test_malformed_reviewer_output_counts_as_a_failed_round -q`

**D10 — Bandit high-severity + high-confidence findings are final.** No agent
can dismiss them. Lower bandit findings go to the disprover; every dismissal is
listed in the morning notes with its reason. All panel findings (reviewer or
scanner, below that bar) go to a fresh disprover agent that tries to refute
them; only survivors count as confirmed.
Rejected: disprover judges everything — a confident wrong dismissal could pass
a real issue. Rejected: all bandit findings final — low-level noise would
trigger pointless fix rounds.
Verify: `python3 -m pytest tests/test_review_panel.py::test_high_severity_high_confidence_bandit_finding_cannot_be_dismissed tests/test_review_panel.py::test_dismissed_findings_are_listed_in_morning_notes_with_reasons -q`

**D11 — Where records live.** The test-review record is committed beside the
approval lock (under `.edad/hashes/`), and is what approve checks. Each
ticket's evidence record carries a summary of the panel (findings, fixes,
still-open). Morning notes are a Markdown file in `.edad/runs/` beside the
night's JSON log, uncommitted like the log (`write_run_log`,
`edad/session_queue.py:935` — the run branch must not carry files no ticket's
scope allows).
Rejected: everything uncommitted in `.edad/runs/` — the proof tests were
reviewed would not be in git, so approval would rest on a local file.
Verify: `python3 -m pytest tests/test_review_panel.py::test_evidence_record_carries_the_panel_summary tests/test_test_review.py::test_review_record_is_written_beside_the_lock -q`

**D12 — Criteria approval is a command:**
`python3 -m edad.gate approve-criteria T030 T031 T032` records a fingerprint
of each ticket's criteria and decision list; batch-friendly. D2's lock refusal
compares against it.
Rejected: a `criteria_approved_by:` field in the ticket — anyone, including an
agent, can type a field; the harness already rejects field-as-approval
(`edad/session.py:134`).
Verify: `python3 -m pytest tests/test_gate_approve.py::test_approve_criteria_accepts_several_tickets_and_fingerprints_each -q`

**D13 — `--skip-review-panel` exists, recorded loudly.** For emergencies such
as broken reviewers while the harness is being fixed. A skip is stamped in the
evidence record and at the top of the morning notes.
Rejected: no escape hatch — a broken reviewer would block every night,
including the one meant to fix it.
Verify: `python3 -m pytest tests/test_review_panel.py::test_skipping_the_panel_is_stamped_in_evidence_and_morning_notes -q`

**D14 — Four severity levels, defined by consequence.**

```
SECURITY  exploitable: injection, secrets in code/logs, unsafe
          file/network/subprocess use, auth bypass.
          -> fix tonight; unfixed = ticket fails
BLOCKER   wrong result, crash, data loss, or breaks an acceptance
          criterion for a named input.
          -> fix tonight; unfixed = ticket fails
MAJOR     works today but a named, likely input or change breaks it:
          unhandled edge case, swallowed error, duplicated logic that
          will drift.
          -> fix tonight; unfixed = flagged first in notes
NIT       style, naming, readability, taste.  -> morning notes only
```

Rule: every finding above NIT must name the concrete input or scenario that
triggers it, or it is downgraded to NIT.
Rejected: three levels with security folded in — a security issue could land
as a major and only be flagged, against the user's stated intent.
Verify: `python3 -m pytest tests/test_review_panel.py::test_a_finding_without_a_named_trigger_is_downgraded_to_nit -q`

**D15 — Reviewers and disprover run `claude -p --model claude-opus-5-5`,
overridable via `EDAD_REVIEW_MODEL`; the model used is written into the review
record.** (The coding agent pins no model today — `agent_argv`,
`edad/session.py:814`; this is independent of it.)
Rejected: Sonnet 5.5 for all — reasonable if cost bites; the override allows it
without code change. Rejected: Opus reviews / Sonnet disproves — a weaker
disprover is where real findings get wrongly dismissed.
Verify: `python3 -m pytest tests/test_review_panel.py::test_reviewer_argv_pins_opus_and_honours_EDAD_REVIEW_MODEL tests/test_review_panel.py::test_review_record_names_the_model_used -q`

**D16 — Mutation score: `mutmut==3.8.0`, pinned; mutates only source files the
ticket changed (not tests, not docs); runs only that ticket's frozen tests;
hard stop at 10 minutes, reported as "partial" with the score so far.**
Rejected: whole repo, no cap — hours per ticket, mostly measuring untouched
code. Rejected: changed lines only, 5 min — mutmut works per function, would
need our own filtering.
Verify: `python3 -m pytest tests/test_mutation_score.py::test_mutation_targets_changed_source_files_only tests/test_mutation_score.py::test_mutation_stops_at_ten_minutes_and_reports_partial -q`

**D17 — New module `edad/review.py`:** `python3 -m edad.review tests <T>`
(daytime loop) and `python3 -m edad.review panel <T>` (called by the night run
after the gate passes; also runs under single-ticket `edad.session run`).
Rejected: `edad.gate review` — gate.py is the judge and already 1700+ lines;
agent-invoking code does not belong inside the verifier.
Verify: `python3 -m pytest tests/test_review_cli.py::test_review_cli_has_tests_and_panel_subcommands -q`

**D18 — Test-review checklist (`edad/rubrics/tests.md`), from the Coursera
test-case guidance adapted to automated tests:**

```
T1 TRACE     every acceptance criterion has >=1 test, and every test
             names the criterion/decision it proves      (gap = MAJOR)
T2 COVERAGE  happy path, error path, and boundaries (empty, max,
             invalid, duplicate, None) for each criterion (gap = MAJOR)
T3 ONE THING one behavior per test                       (MAJOR)
T4 ASSERTS   precise expected values; no bare 'no exception' /
             truthy checks                               (MAJOR)
T5 RED FIRST would fail against the base for the right reason,
             not an import error                         (BLOCKER)
T6 ISOLATED  no order dependence, shared state, network, clock,
             or real home dir                            (MAJOR)
T7 SETUP     preconditions explicit in the test or a named fixture (NIT)
T8 NAMES     name reads as the expected behavior
             (test_<does>_when_<condition>)              (NIT)
```

Rejected: adding T9 "not over-specified" — overlaps with this harness's
deliberate pinning of some messages.

**D19 — Panel checklists (`edad/rubrics/code.md`, `edad/rubrics/security.md`):**

```
CODE      C1 correctness: wrong result / crash for an input the frozen
             tests don't cover
          C2 error handling: swallowed or misreported errors
          C3 edge cases: empty, huge, concurrent, partial
          C4 fits the codebase: reuses helpers, matches naming and
             comment density
          C5 a simpler shape exists for the same behavior
          C6 scope creep: change does more than the ticket
SECURITY  (bandit output attached)
          S1 injection: shell/subprocess, SQL, path traversal
          S2 secrets: tokens in code, logs, errors, records
          S3 untrusted input reaches file/network/exec
          S4 unsafe deserialization (yaml.load, pickle)
          S5 permissions / sandbox / egress weakened
          S6 dependency added or pin loosened
```

Style is left to ruff. Rejected: C7 performance — rarely matters here, would
mostly produce nits.
D18/D19 verify (that every item reaches the prompt; wording itself is a
preference): `python3 -m pytest tests/test_review_cli.py::test_every_rubric_item_reaches_the_reviewer_prompt -q`

**D20 — Morning notes, act-first layout,** one Markdown file per night in
`.edad/runs/`:

```
# Night <date> - run branch <branch>
## Needs you            (panel skipped; failed tickets; unfixed majors)
## Test strength        (mutation score per ticket, survivors)
## Dismissed findings   (with reasons)
## Fixed overnight
## Nits                 (grouped by ticket)
```

Rejected: per-ticket sections — the operator would scan every section to find
what needs action.
Verify: `python3 -m pytest tests/test_morning_notes.py::test_morning_notes_put_needs_you_first_and_nits_last -q`

### Re-grill, 2026-10-27 (gaps raised by /to-spec)

The spec listed seven gaps under "Must be re-grilled before /to-tickets". Each
is settled below. Facts measured before asking: all 27 existing tickets
(T001–T027) have evidence and the queue never re-approves a done ticket; the
five frozen stand-ins fake gate functions with `monkeypatch.setattr` exactly as
they already fake `gate_toolchain_problems`; the session commits evidence at
`edad/session.py:1236`, straight after the build loop finds the full gate green;
locks are only ever read by exact name (`.edad/hashes/<T>.json`), so files
beside them are safe; the night's log is `.edad/runs/<stamp>.json` and the queue
already reads each session's log (`edad/session_queue.py:996`); the shell a
Claude session runs commands in has no terminal attached (`sys.stdin.isatty()`
is False).

**D21 — The panel runs inside the session, between the green gate and the
evidence commit (gap 1).** `run_session` calls the panel after the build loop
breaks on a green full gate and before `promote_evidence`; fix rounds reuse the
session's own agent loop and the summary lands in the evidence. Both
`edad.session run` and the night get it. The panel result is written into the
evidence record and the session log. A ticket the panel fails ends with a new
outcome `review_failed`: exit 1, no evidence promoted, branch left for
inspection; the queue treats it as failed, so dependents are skipped. The queue
writes the morning notes to `.edad/runs/<stamp>.md`, beside the night's JSON
log, built from the session logs (failed tickets have no evidence, so evidence
cannot be the source). Single-ticket `edad.session run` prints the panel
summary and writes no notes file. `python3 -m edad.review panel <T>` (D17)
remains as a manual re-run on a worktree left behind.
Rejected: the queue calls the panel after the session — evidence is already
committed and the agent loop is gone by then. Rejected: reuse `aborted` for a
panel failure — the morning reader could not tell a broken build from a
confirmed finding without parsing a reason string. Rejected: single-ticket run
writes a notes file too — not needed; it prints.
Verify: `python3 -m pytest tests/test_session_panel.py::test_panel_runs_after_the_green_gate_and_before_the_evidence_commit tests/test_session_panel.py::test_panel_failure_ends_the_session_as_review_failed_with_no_evidence tests/test_session_panel.py::test_queue_writes_morning_notes_beside_the_run_log -q`

**D22 — Human-only commands require a terminal; identity comes from git
config (gap 3).** `python3 -m edad.gate approve-criteria …` and a new
`python3 -m edad.gate override-review <T> --reason "…"` both refuse unless
stdin is a TTY. The approver recorded is `git config user.email`, never a typed
name. The override writes `.edad/hashes/<T>.override.json`, holding the email,
the reason, the time and the hashes of the current frozen files; approve
accepts it in place of a passing review while those bytes are unchanged, so the
night's non-interactive re-approval still passes. Known limit: a determined
actor can fake a terminal — this stops accidents and casual self-approval by
the ticket-writing session, not a hostile operator.
Rejected: git email only, no terminal check — the ticket-writing session could
approve its own criteria. Rejected: a typed `--approved-by NAME` — the
field-as-approval weakness D12 rejected.
Verify: `python3 -m pytest tests/test_gate_approve.py::test_approve_criteria_refuses_without_a_terminal tests/test_gate_approve.py::test_override_review_refuses_without_a_terminal tests/test_gate_approve.py::test_override_record_lets_reapproval_pass_while_the_tests_are_unchanged -q`

**D23 — Every fix round re-runs the gate; only confirmed findings are
re-reviewed; red at the end resets (gap 5).** Each fix round re-runs everything
the build loop checks: acceptance, full gate, scope, frozen hashes and the
shared `max_diff_lines` (D7). A fresh reviewer then re-checks only the
confirmed findings, not a whole new panel. A red gate after round 1 goes into
round 2's prompt. If the gate is still red after the last round, the worktree
is reset to the last green commit and the findings count as unfixed: security
or blocker fails the ticket (D4), major passes flagged first.
Rejected: a red gate after the last round fails the ticket outright — an
attempted fix of a mere major would fail an otherwise good ticket. Rejected: a
full new panel after every round — new findings can appear every round and the
cap stops meaning anything.
Verify: `python3 -m pytest tests/test_review_panel.py::test_each_fix_round_re_runs_the_gate tests/test_review_panel.py::test_fix_rounds_re_review_only_the_confirmed_findings tests/test_review_panel.py::test_red_gate_after_the_last_fix_round_resets_to_the_last_green_commit_and_counts_findings_unfixed -q`

**D24 — `bandit==1.9.4` and `mutmut==3.8.0` both pinned in
`requirements-gate.txt`, measured like ruff (gap 6).** Every record names
their versions. A repo whose pins file lists them must install them or approve
refuses (the existing toolchain rule). A repo whose pins file does not list them
(ai-sniffer today) is otherwise untouched, but its session refuses to start the
panel, naming the install line and `--skip-review-panel`. bandit 1.9.4 was the
latest release when checked on 2026-10-27; this pins the bandit version D8 left
open.
Rejected: a separate `requirements-review.txt` checked only by the panel — two
pin files to keep in step. Rejected: pin bandit only — the mutation score
would be a number with no recorded toolchain behind it.
Verify: `python3 -m pytest tests/test_gate_toolchain.py::test_bandit_is_pinned_and_measured_with_the_toolchain tests/test_gate_toolchain.py::test_mutmut_is_pinned_and_measured_with_the_toolchain tests/test_session_panel.py::test_session_refuses_to_start_the_panel_when_bandit_or_mutmut_is_not_pinned -q`

**D25 — The five stand-ins get a one-line fake; old locks get no exemption
(gap 2).** Approve's new check is its own gate function,
`review_problems(root, ticket)`. While the D2 ticket is being written, before
approve, each of the five stand-ins (`tests/test_gate_red_proof.py:335`,
`tests/test_gate_mutation.py:523`, `tests/test_harness_identity.py:306`, `:456`,
`:545`) gains one line, `monkeypatch.setattr(gate, "review_problems", lambda
root, tkt: [])`, alongside the toolchain fake it already has. Nothing they
assert changes. Locks from before this feature are not exempt: all 27 tickets
are done and never re-approved by the night; re-approving one by hand needs a
review or the override like any ticket. Editing those three files makes their
old tickets' locks stale; nothing re-checks a done ticket's lock.
Rejected: exempt pre-feature locks — needs a cutoff rule and protects nothing
that is ever re-approved. Rejected: a new `skip_review` field on the
Namespace — changes the stand-ins' call shape instead of faking a function the
way they already do.
Verify (a regression check, green at base — belongs in the D2 ticket's
`full_gate`, never its `acceptance`, where approve's red proof would refuse
it): `python3 -m pytest tests/test_gate_red_proof.py tests/test_gate_mutation.py tests/test_harness_identity.py -q`

**D26 — The criteria fingerprint covers the enforced fields and is committed
beside the lock (gap 4).** `approve-criteria` writes
`.edad/hashes/<T>.criteria.json`: a sha256 over the ticket's `acceptance`,
`decisions`, `scope` and `full_gate`, plus the approver's git email and the
time. Committed, because the night branches from main and must read it. Prose
body edits (Context, Goal) do not force re-approval. The review record sits
beside it as `.edad/hashes/<T>.review.json`, the override as
`.edad/hashes/<T>.override.json`.
Rejected: `acceptance` + `decisions` only, as D12 first worded it — a scope or
full_gate change after human approval would go unnoticed. Rejected: the whole
ticket file — a typo fix in the body would need the human again.
Verify: `python3 -m pytest tests/test_gate_approve.py::test_criteria_fingerprint_covers_acceptance_decisions_scope_and_full_gate_only -q`

**D27 — Test review runs one round per invocation (found while checking D1
against D5).** A CLI cannot call back into the ticket-writing session that
launched it, so D1's loop spans invocations. Each `python3 -m edad.review tests
<T>` runs exactly one round with a fresh reviewer. Round count and every
round's findings accumulate in `.edad/hashes/<T>.review.json`. The writer
disputes a finding with `--dispute F3="reason"` (repeatable); the next reviewer
sees the finding and the reason (D9). A fourth round is refused. The counter
resets only when the human re-runs approve-criteria over changed criteria, so a
stuck ticket goes back through a person. A passing round runs `gate approve`
itself (D1's auto-lock).
Rejected: deleting the review record resets the counter — the cap stops
meaning anything. Rejected: an in-process loop with a fresh writer agent —
reverses D5; the writer would lose the spec conversation.
Verify: `python3 -m pytest tests/test_test_review.py::test_each_invocation_runs_one_round_and_a_fourth_is_refused tests/test_test_review.py::test_round_counter_resets_only_when_criteria_are_reapproved tests/test_test_review.py::test_a_dispute_that_names_no_finding_of_the_last_round_is_refused tests/test_test_review.py::test_the_reviewer_is_given_the_spec_every_frozen_file_and_the_tests_rubric_and_no_tools tests/test_test_review.py::test_a_passing_round_runs_gate_approve_in_the_repo tests/test_test_review.py::test_a_reviewer_that_fails_to_run_uses_up_no_round -q`

**Amended D3, D16, D20 — the shared panel test file is split by seam (gap 7).**
`tests/test_review_panel.py` was frozen by eleven decisions, forcing strictly
serial authoring. D3 and D16 now freeze `tests/test_mutation_score.py`, D20
freezes `tests/test_morning_notes.py`; their verify commands above and below
are amended to the new paths with the same test names. Decision ids are
unchanged. D4, D10 and D13's notes assertions stay in the panel file and drive
the notes writer, so the panel ticket is blocked by the notes ticket.
Rejected: keep one file — panel tickets authored and merged strictly in
sequence.

### Deferred

- UX and UI-design reviewers, and running the app for screenshots — no ticket
  has a user interface yet; the panel is built to add reviewers.
- Exact reviewer prompt wording beyond the checklists — cheap to tune after
  seeing real reviews.

## Decisions

```yaml
decisions:
  - id: D1
    decision: tests are written and reviewed in the daytime by `edad.review tests`, looping up to 3 rounds, then auto-locked; exhausted rounds leave the ticket unlocked
    verify:
      - python3 -m pytest tests/test_test_review.py::test_review_stops_after_three_rounds_and_leaves_ticket_unlocked -q
    frozen:
      - tests/test_test_review.py
    scope:
      - edad/review.py
      - .claude/skills/to-tickets/SKILL.md
    rejected: write+review at night per ticket — large controller change, failures found only in the morning; daytime write/night review — inherits both downsides
  - id: D2
    decision: gate approve refuses without a passing test-review record matching the current frozen bytes, refuses if criteria changed since approve-criteria; a human override remains and records who approved
    verify:
      - python3 -m pytest tests/test_gate_approve.py::test_approve_refuses_without_a_passing_review_for_these_exact_test_bytes tests/test_gate_approve.py::test_approve_refuses_when_criteria_changed_since_human_approval tests/test_gate_approve.py::test_human_override_records_who_approved -q
    frozen:
      - tests/test_gate_approve.py
    scope:
      - edad/gate.py
      - edad/session_queue.py
      - QUICKSTART.md
    rejected: approve nothing up front — criteria never seen by a human; review optional — unreviewed tests could be locked
  - id: D3
    decision: mutation score runs after the build and is reported in morning notes only; it never fails a ticket; named "mutation score" to stay distinct from the gate's existing mutation blocks
    verify:
      - python3 -m pytest tests/test_mutation_score.py::test_mutation_survivors_go_to_morning_notes_and_do_not_fail_the_ticket -q
    frozen:
      - tests/test_mutation_score.py
    scope:
      - edad/review.py
    rejected: block below a threshold — fails the build for a test problem the agent cannot fix; skip mutation — nothing objective measures test substance
  - id: D4
    decision: confirmed security/blocker/major findings go back to the agent for up to 2 fix rounds; unfixed security or blocker fails the ticket; unfixed major passes flagged first in morning notes; nits go to notes only
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_unfixed_security_finding_fails_ticket_after_two_rounds tests/test_review_panel.py::test_unfixed_major_passes_and_is_flagged_first_in_morning_notes -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
      - edad/session.py
    rejected: all three fail the ticket — failures over arguable majors; nothing fails — confirmed security could reach the run branch
  - id: D5
    decision: the ticket-making session writes tests; the reviewer is always a new `claude -p` process given only the spec and tests, never a resumed session
    verify:
      - python3 -m pytest tests/test_test_review.py::test_reviewer_runs_as_a_new_claude_process_given_only_the_spec_and_tests tests/test_test_review.py::test_reviewer_prompt_holds_the_spec_tests_and_rubric_and_nothing_else -q
    frozen:
      - tests/test_test_review.py
    scope:
      - edad/review.py
      - .claude/skills/to-tickets/SKILL.md
    rejected: fresh writer agent too — loses spec discussion context; bias concern is the reviewer's
  - id: D6
    decision: v1 panel runs code and security reviewers as parallel fresh sessions; reviewers are pluggable; UX/UI deferred
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_panel_runs_code_and_security_reviewers_as_parallel_fresh_sessions -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
    rejected: all four reading code only — UI review blind to the screen; all four with screenshots — largest build, untestable on current tickets
  - id: D7
    decision: panel fix rounds have their own cap of 2, separate from max_iterations, but the total diff must still fit max_diff_lines
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_fix_rounds_have_their_own_cap_but_share_the_diff_line_cap -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
      - edad/session.py
    rejected: separate line budget — cap stops catching an outgrown shape; share everything — no budget left after a long build
  - id: D8
    decision: bandit is pinned in requirements-gate.txt and measured with the toolchain like ruff
    verify:
      - python3 -m pytest tests/test_gate_toolchain.py::test_bandit_is_pinned_and_measured_with_the_toolchain -q
    frozen:
      - tests/test_gate_toolchain.py
    scope:
      - requirements-gate.txt
      - edad/gate.py
    rejected: semgrep — fetches rules online, network is denied at night; no scanner — security rests on judgment alone
  - id: D9
    decision: test review passes when no blocker or major remains; writer may dispute with a reason the next fresh reviewer rules on; malformed reviewer output is a failed round
    verify:
      - python3 -m pytest tests/test_test_review.py::test_review_passes_with_only_nits_left tests/test_test_review.py::test_a_disputed_finding_and_its_reason_reach_the_next_reviewer tests/test_test_review.py::test_malformed_reviewer_output_counts_as_a_failed_round -q
    frozen:
      - tests/test_test_review.py
    scope:
      - edad/review.py
    rejected: zero findings, no disputes — a wrong reviewer sinks a good ticket
  - id: D10
    decision: bandit high-severity+high-confidence findings are final; all other findings go to a fresh disprover agent; dismissals are listed in morning notes with reasons
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_high_severity_high_confidence_bandit_finding_cannot_be_dismissed tests/test_review_panel.py::test_dismissed_findings_are_listed_in_morning_notes_with_reasons -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
    rejected: disprover judges everything — wrong dismissal passes a real issue; all bandit final — noise triggers pointless fix rounds
  - id: D11
    decision: test-review record committed beside the lock under .edad/hashes/; panel summary in each evidence record; morning notes uncommitted in .edad/runs/
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_evidence_record_carries_the_panel_summary tests/test_test_review.py::test_review_record_is_written_beside_the_lock -q
    frozen:
      - tests/test_review_panel.py
      - tests/test_test_review.py
    scope:
      - edad/review.py
      - edad/gate.py
      - edad/session.py
      - edad/session_queue.py
    rejected: all uncommitted — review proof absent from git, approval would rest on a local file
  - id: D12
    decision: "`python3 -m edad.gate approve-criteria <T...>` fingerprints each ticket's criteria and decision list, batch-friendly"
    verify:
      - python3 -m pytest tests/test_gate_approve.py::test_approve_criteria_accepts_several_tickets_and_fingerprints_each -q
    frozen:
      - tests/test_gate_approve.py
    scope:
      - edad/gate.py
      - QUICKSTART.md
    rejected: criteria_approved_by field — a typed field proves nothing; harness already rejects field-as-approval
  - id: D13
    decision: --skip-review-panel exists for emergencies; a skip is stamped in the evidence record and at the top of morning notes
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_skipping_the_panel_is_stamped_in_evidence_and_morning_notes -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
      - edad/session.py
      - edad/session_queue.py
    rejected: no escape hatch — a broken reviewer blocks the night meant to fix it
  - id: D14
    decision: four severities (security, blocker, major, nit) defined by consequence; a finding above nit without a named trigger input/scenario is downgraded to nit
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_a_finding_without_a_named_trigger_is_downgraded_to_nit -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
      - edad/rubrics/*.md
    rejected: three levels with security folded in — security could be graded major and only flagged
  - id: D15
    decision: reviewers and disprover run `claude -p --model claude-opus-5-5`, overridable by EDAD_REVIEW_MODEL; the model is written into the review record
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_reviewer_argv_pins_opus_and_honours_EDAD_REVIEW_MODEL tests/test_review_panel.py::test_review_record_names_the_model_used -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
    rejected: Sonnet for all — fine if cost bites, override allows it; Opus reviews/Sonnet disproves — weak disprover wrongly dismisses
  - id: D16
    decision: mutation score uses mutmut==3.8.0 pinned, mutates only source files the ticket changed, runs only the ticket's frozen tests, stops at 10 minutes and reports partial
    verify:
      - python3 -m pytest tests/test_mutation_score.py::test_mutation_targets_changed_source_files_only tests/test_mutation_score.py::test_mutation_stops_at_ten_minutes_and_reports_partial -q
    frozen:
      - tests/test_mutation_score.py
    scope:
      - edad/review.py
      - requirements-gate.txt
    rejected: whole repo no cap — hours, measures untouched code; changed lines 5 min — needs custom per-line filtering
  - id: D17
    decision: new module edad/review.py with `tests` and `panel` subcommands; panel is called by the night run after the gate passes and under single-ticket edad.session run
    verify:
      - python3 -m pytest tests/test_review_cli.py::test_review_cli_has_tests_and_panel_subcommands -q
    frozen:
      - tests/test_review_cli.py
    scope:
      - edad/review.py
      - edad/session.py
    rejected: edad.gate review — agent-invoking code does not belong in the judge
  - id: D18
    decision: test-review checklist T1–T8 in edad/rubrics/tests.md, as recorded above
    verify:
      - python3 -m pytest tests/test_review_cli.py::test_every_rubric_item_reaches_the_reviewer_prompt -q
    frozen:
      - tests/test_review_cli.py
    scope:
      - edad/rubrics/tests.md
      - edad/review.py
    rejected: T9 not-over-specified — overlaps with deliberate message pinning in this harness
  - id: D19
    decision: panel checklists C1–C6 in edad/rubrics/code.md and S1–S6 in edad/rubrics/security.md, as recorded above; style left to ruff
    verify:
      - python3 -m pytest tests/test_review_cli.py::test_every_rubric_item_reaches_the_reviewer_prompt -q
    frozen:
      - tests/test_review_cli.py
    scope:
      - edad/rubrics/code.md
      - edad/rubrics/security.md
      - edad/review.py
    rejected: C7 performance — rarely matters here, mostly nits
  - id: D20
    decision: morning notes are one Markdown file per night in .edad/runs/, sections in order Needs you, Test strength, Dismissed findings, Fixed overnight, Nits
    verify:
      - python3 -m pytest tests/test_morning_notes.py::test_morning_notes_put_needs_you_first_and_nits_last -q
    frozen:
      - tests/test_morning_notes.py
    scope:
      - edad/review.py
      - edad/session_queue.py
    rejected: per-ticket sections — operator scans everything to find what needs action
  - id: D21
    decision: run_session runs the panel between the green full gate and promote_evidence; result goes into evidence and session log; a panel failure is a new outcome review_failed (exit 1, no evidence, dependents skipped); the queue writes morning notes to .edad/runs/<stamp>.md from session logs; single-ticket run prints the summary only
    verify:
      - python3 -m pytest tests/test_session_panel.py::test_panel_runs_after_the_green_gate_and_before_the_evidence_commit tests/test_session_panel.py::test_panel_failure_ends_the_session_as_review_failed_with_no_evidence tests/test_session_panel.py::test_queue_writes_morning_notes_beside_the_run_log -q
    frozen:
      - tests/test_session_panel.py
    scope:
      - edad/session.py
      - edad/session_queue.py
      - edad/review.py
    rejected: queue calls the panel after the session — evidence already committed, agent loop gone; reuse aborted — broken build and confirmed finding indistinguishable; single run writes notes — not needed
  - id: D22
    decision: approve-criteria and a new override-review command refuse unless stdin is a TTY; approver is git config user.email; override writes .edad/hashes/<T>.override.json tied to the current frozen bytes, accepted by approve in place of a passing review
    verify:
      - python3 -m pytest tests/test_gate_approve.py::test_approve_criteria_refuses_without_a_terminal tests/test_gate_approve.py::test_override_review_refuses_without_a_terminal tests/test_gate_approve.py::test_override_record_lets_reapproval_pass_while_the_tests_are_unchanged -q
    frozen:
      - tests/test_gate_approve.py
    scope:
      - edad/gate.py
      - QUICKSTART.md
    rejected: git email without a terminal check — the writing session could approve its own criteria; typed --approved-by — field-as-approval
  - id: D23
    decision: every fix round re-runs acceptance, full gate, scope, frozen hashes and the shared diff cap; a fresh reviewer re-checks only confirmed findings; a red gate feeds the next round, and red after the last round resets to the last green commit with findings counted unfixed
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_each_fix_round_re_runs_the_gate tests/test_review_panel.py::test_fix_rounds_re_review_only_the_confirmed_findings tests/test_review_panel.py::test_red_gate_after_the_last_fix_round_resets_to_the_last_green_commit_and_counts_findings_unfixed -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
      - edad/session.py
    rejected: red after last round fails outright — a fix attempt on a major fails a good ticket; full new panel each round — findings never converge
  - id: D24
    decision: bandit==1.9.4 and mutmut==3.8.0 pinned in requirements-gate.txt and measured with the toolchain like ruff; the session refuses to start the panel when either is not pinned, naming the install line and --skip-review-panel
    verify:
      - python3 -m pytest tests/test_gate_toolchain.py::test_bandit_is_pinned_and_measured_with_the_toolchain tests/test_gate_toolchain.py::test_mutmut_is_pinned_and_measured_with_the_toolchain tests/test_session_panel.py::test_session_refuses_to_start_the_panel_when_bandit_or_mutmut_is_not_pinned -q
    frozen:
      - tests/test_gate_toolchain.py
      - tests/test_session_panel.py
    scope:
      - requirements-gate.txt
      - edad/gate.py
      - edad/session.py
    rejected: separate requirements-review.txt — two pin files to keep in step; bandit only — mutation score with no recorded toolchain
  - id: D25
    decision: approve's review check is its own function review_problems(root, ticket); the five frozen stand-ins each gain one monkeypatch line faking it, added before approve; locks predating the feature get no exemption
    verify:
      - python3 -m pytest tests/test_gate_red_proof.py tests/test_gate_mutation.py tests/test_harness_identity.py -q
    frozen:
      - tests/test_gate_red_proof.py
      - tests/test_gate_mutation.py
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: exempt pre-feature locks — needs a cutoff rule, protects nothing ever re-approved; skip_review Namespace field — changes the stand-ins' call shape
  - id: D26
    decision: approve-criteria writes committed .edad/hashes/<T>.criteria.json — sha256 over acceptance, decisions, scope and full_gate, plus git email and time; review record is .edad/hashes/<T>.review.json
    verify:
      - python3 -m pytest tests/test_gate_approve.py::test_criteria_fingerprint_covers_acceptance_decisions_scope_and_full_gate_only -q
    frozen:
      - tests/test_gate_approve.py
    scope:
      - edad/gate.py
    rejected: acceptance+decisions only — scope/full_gate drift unnoticed; whole ticket file — body typo needs the human again
  - id: D27
    decision: each `edad.review tests <T>` invocation runs one round; rounds and --dispute F<n>="reason" accumulate in .edad/hashes/<T>.review.json; a fourth round is refused; the counter resets only on a new approve-criteria over changed criteria; a passing round runs gate approve
    verify:
      - python3 -m pytest tests/test_test_review.py::test_each_invocation_runs_one_round_and_a_fourth_is_refused tests/test_test_review.py::test_round_counter_resets_only_when_criteria_are_reapproved tests/test_test_review.py::test_a_dispute_that_names_no_finding_of_the_last_round_is_refused tests/test_test_review.py::test_the_reviewer_is_given_the_spec_every_frozen_file_and_the_tests_rubric_and_no_tools tests/test_test_review.py::test_a_passing_round_runs_gate_approve_in_the_repo tests/test_test_review.py::test_a_reviewer_that_fails_to_run_uses_up_no_round -q
    frozen:
      - tests/test_test_review.py
    scope:
      - edad/review.py
    rejected: deleting the record resets the counter — cap meaningless; in-process loop with fresh writer — reverses D5
deferred:
  - UX and UI-design reviewers plus app-running screenshots — no ticket has a UI yet; panel is pluggable
  - exact reviewer prompt wording beyond the checklists — cheap to tune after real reviews
  - version-probe commands for bandit and mutmut in VERSION_PROBES — implementation detail
  - JSON shape of the review, criteria and override records — cheap to change before first use
  - refusal message wording — cheap to tune
  - bandit's target paths (recommended - the ticket's changed source files, as for mutmut) — cheap to change
  - how `edad.review panel <T>` locates a left-behind worktree — manual tool, cheap to change
```
