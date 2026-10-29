---
slug: review-loops
grilled: .edad/grills/review-loops.md
status: draft
---

## Problem statement

A night of tickets can only be as long as the operator's day was. Before any
ticket runs, a human has to read its frozen tests and approve them, and that
reading is the bottleneck: the lock itself is cheap, but the attention behind it
is not. The harness has no other way to know the tests are any good.

At the other end, nothing reviews the code once the gate passes. The gate checks
that frozen files are untouched, that the diff stays in scope, and that the
acceptance commands (and ruff, under the full gate) pass — then stops at "not
merged — review and merge". A change can satisfy every frozen test and still
carry a security hole, a swallowed error, or an edge case the tests never named,
and the first reader to notice is the operator in the morning, if anyone.

## Solution

Two review loops, both run by fresh reviewers who see only the spec and the
thing under review.

**Before the night:** the human approves *what* a ticket must do — its
acceptance criteria, decisions, scope and full gate — with one batch command,
typed at a terminal, which records their git email. The tests themselves are
reviewed by a fresh reviewer against a written checklist, one round per
invocation of the review command. The ticket-writing session revises or disputes
findings and runs the command again, up to three rounds. A passing round locks
the ticket through the normal approve. The lock refuses:

- tests whose exact bytes were never reviewed;
- criteria that changed since the human approved them.

A ticket whose review never passes stays unlocked, and only a person approving
changed criteria gives it more rounds. For emergencies, a terminal-only override
command records the operator's git email and a reason, tied to the current test
bytes.

**After the gate passes, inside each session:**

1. A panel of a code reviewer and a security reviewer, with bandit's output
   attached, reads the change.
2. A fresh disprover tries to refute every finding except bandit's
   high-severity, high-confidence ones, which are final.
3. Confirmed security, blocker and major findings go back to the coding agent
   for up to two fix rounds. Each round re-runs the whole gate inside the
   ticket's existing diff-size cap, and a fresh reviewer re-checks only those
   findings.
4. If the gate is still red after the last round, the branch goes back to its
   last green commit and the findings count as unfixed.
5. An unfixed security or blocker finding ends the session as `review_failed`,
   with no evidence, and its dependents are skipped. An unfixed major passes but
   is the first thing the operator reads.
6. A mutation score is measured and reported, never enforced. It counts how many
   deliberately broken versions of the changed code the frozen tests catch.

A repo that has not pinned bandit and mutmut has its panel refused, with the
install line and the skip flag named. An emergency skip flag exists, and every
use of it is stamped where the operator will see it.

**In the morning:** the queue writes one Markdown file per night beside the
night's log. It lists what needs the operator first, then test strength,
dismissed findings with reasons, what was fixed overnight, and finally nits. A
single-ticket run prints the same summary instead of writing a file.

## User stories

1. As an operator, I want to approve a batch of tickets' criteria in one command, so that my daytime attention goes to *what* is built, not to reading every test line.
2. As an operator, I want criteria approval and the review override to work only from a real terminal and record my git email, so that the ticket-writing session cannot approve its own work.
3. As an operator, I want tests reviewed by a reviewer that has never seen the conversation that wrote them, so that the review is not anchored on the writer's reasoning.
4. As a ticket-writing session, I want each review command to run exactly one round and remember the rounds before it, so that I can revise between rounds without losing the count.
5. As an operator, I want a fourth round refused until I re-approve changed criteria, so that a stuck ticket comes back through a person rather than through a deleted file.
6. As an operator, I want approve to refuse when the frozen tests changed after their review, so that a passing review cannot be reused for different tests.
7. As an operator, I want approve to refuse when the acceptance, decisions, scope or full gate changed after I approved them, but not when only the ticket's prose changed, so that what runs is what I agreed to without re-approving typo fixes.
8. As an operator in an emergency, I want an override tied to the current test bytes that the night's re-approval accepts, so that a broken reviewer does not block the night meant to fix it.
9. As a ticket-writing session, I want to dispute a finding with a written reason that the next fresh reviewer rules on, so that one wrong reviewer cannot sink a good ticket.
10. As the harness, I want reviewer output that does not match the expected structure to count as a failed round, so that garbage is never read as a pass.
11. As an operator, I want the panel to run before evidence is committed, so that a ticket with a confirmed security finding never produces evidence.
12. As an operator, I want a panel failure reported as its own outcome, so that I can tell a confirmed finding from a broken build without reading a reason string.
13. As an operator, I want confirmed security and blocker findings fixed overnight or the ticket failed, so that no confirmed security issue reaches the run branch.
14. As an operator, I want each fix round to re-run the full gate and re-check only the confirmed findings, so that a fix cannot break what was green and the rounds converge.
15. As an operator, I want a fix that leaves the gate red rolled back to the last green commit, so that an attempted fix of a mere major does not fail an otherwise good ticket.
16. As an operator, I want an unfixed major to pass but be listed first in my notes, so that arguable findings do not fail the night but cannot hide.
17. As an operator, I want every finding the disprover dismissed listed with its reason, so that I can catch a wrong dismissal.
18. As an operator, I want a finding that names no concrete triggering input downgraded to a nit, so that fix rounds are spent on real failures.
19. As an operator, I want each ticket's mutation score and surviving mutants in my notes, limited to the files the ticket changed and capped at ten minutes, so that I can decide whether the tests need amending without the night stalling.
20. As an operator, I want fix rounds to share the ticket's diff-size cap, so that a fix that outgrows the ticket's shape is still caught.
21. As an operator on a repo without bandit and mutmut pinned, I want the panel refused with the install line and the skip flag named, so that I know exactly what to do instead of getting a silent pass.
22. As an operator, I want `--skip-review-panel` for emergencies, stamped in the evidence and at the top of the notes, so that a skip is never silent.
23. As an operator, I want the model each review used recorded, and overridable without a code change, so that I can trade cost for strength knowingly.
24. As an operator, I want bandit and mutmut pinned and version-checked like ruff, so that the security verdict and the mutation score belong to the commit and work offline.

## Seams

**S1 — `gate approve` and its parser**, with the new `approve-criteria` and `override-review` subcommands and approve's new `review_problems` check
- **Exists**: yes (`approve`, and the five frozen stand-ins that drive it). `approve-criteria`, `override-review` and `review_problems` are new.
- **Observes**: given a ticket, frozen files, review, criteria and override records laid out in a temp repo, and a faked terminal:
  - whether approval is granted or refused, and with what message;
  - what the criteria fingerprint covers;
  - whether the override record lets re-approval pass;
  - whether the human-only commands refuse without a terminal.

  The existing stand-ins observe that approve still succeeds once `review_problems` is faked to report nothing.
- **Discharges**: D2, D12, D22, D25, D26.

**S2 — toolchain measurement** (the single probe that today measures pytest, ruff and PyYAML against `requirements-gate.txt`)
- **Exists**: yes.
- **Observes**: that bandit and mutmut are pinned and are measured and reported alongside the others.
- **Discharges**: D8, D24 (pins).

**S3 — review CLI parser** (built apart from `main()`, as `edad.session` and `edad.session_queue` already do)
- **Exists**: new.
- **Observes**: that `tests <T>` and `panel <T>` are subcommands and reach their handlers, without spawning a process.
- **Discharges**: D17.

**S4 — reviewer command and prompt builders** (pure, in the style of the existing agent-command builder)
- **Exists**: new.
- **Observes**:
  - the exact command a reviewer or disprover is launched with: a new `claude -p`, the pinned model or the override, and no resume or continue;
  - the prompt it is given: the spec, the artifact under review and every checklist item, and nothing else.
- **Discharges**: D5, D15 (command half), D18, D19.

**S5 — the test-review round**, with the reviewer runner and approve passed in
- **Exists**: new.
- **Observes**, for one invocation against the review record on disk:
  - the round counter, and the refusal of a fourth round;
  - when the counter resets;
  - pass or fail;
  - how disputes reach the next reviewer;
  - malformed output counted as a failed round;
  - the record written beside the lock;
  - whether approve was called on a pass.
- **Discharges**: D1, D9, D11 (review-record half), D27.

**S6 — the panel run**, with the reviewers, disprover, fixer, gate and bandit runners passed in; it returns a panel result
- **Exists**: new.
- **Observes**:
  - which reviewers ran, and that they ran in parallel as fresh sessions;
  - which findings were confirmed, dismissed or final, and any severity downgrades;
  - fix rounds against their own cap and the shared diff cap;
  - the gate re-run each round, and only confirmed findings re-reviewed;
  - the reset to the last green commit;
  - ticket pass or fail, the skip stamp, the model recorded, and the summary for the evidence record.
- **Discharges**: D4, D6, D7, D10, D11 (evidence half), D13, D14, D15 (record half), D23.

**S7 — the morning-notes writer** (pure: night results in, Markdown out)
- **Exists**: new.
- **Observes**: the order and contents of each section:
  - "Needs you": the skip stamp, failed tickets and unfixed majors;
  - mutation scores, dismissals with reasons, fixes, and nits.
- **Discharges**: D20. It also carries the notes side of D3, D4, D10 and D13, whose tests may feed S6's or S10's result through S7.

**S8 — the session run** (`run_session` with its collaborators faked by `monkeypatch`, as `tests/test_full_gate_retry.py` already does)
- **Exists**: yes.
- **Observes**:
  - that the panel is called after the build loop finds the full gate green and before the evidence is promoted;
  - that a failing panel ends the session as `review_failed`, with exit 1 and no evidence promoted;
  - that the panel is refused when bandit or mutmut is not pinned;
  - what lands in the session log.
- **Discharges**: D21 (session half), D24 (refusal).

**S9 — the night queue run** (the queue with its `run_session` faked, as `tests/test_session_queue.py` already does)
- **Exists**: yes.
- **Observes**: that a morning-notes file is written beside the night's JSON log in `.edad/runs/`, built from the session logs.
- **Discharges**: D21 (morning-notes half).

**S10 — the mutation-score run**, with the mutmut runner and the clock passed in. Split out of the panel when the shared panel test file was split.
- **Exists**: new.
- **Observes**:
  - which source files are mutated (only those the ticket changed, not tests or docs) and which tests run (only the ticket's frozen ones);
  - the score and the surviving mutants;
  - the ten-minute stop reported as "partial";
  - that the result never fails the ticket.
- **Discharges**: D3, D16.

**Decisions with no seam:** none. The old spec's one gap was the panel's wiring
into the session and the queue. The re-grill settled it as D21, and it attaches
at S8 and S9, both of which exist.

## Implementation decisions

**A new module owns all review work.** The gate stays the judge. It gains:

- approve's new review check, as its own function;
- the criteria-approval and review-override subcommands;
- the bandit and mutmut pins in its toolchain check.

Everything that launches a model lives in the new review module. That module has
two subcommands:

- one daytime test-review round;
- a manual re-run of the panel on a worktree left behind.

**Daytime flow.**

1. The ticket-writing skill authors tickets and tests as it does today.
2. The operator, at a terminal, runs criteria approval over the batch. It
   records a fingerprint of each ticket's acceptance, decisions, scope and full
   gate, plus the operator's git email and the time. The record is committed
   beside the lock, because the night branches from main and must read it.
3. The skill runs the test-review command once per round. Each round:
   - launches a brand-new reviewer process with only the spec and the tests;
   - accumulates its findings, and any disputes the writer passed, in a review
     record committed beside the lock;
   - on a pass, runs approve itself.
4. Approve now refuses when:
   - no passing review (or override) matches the current frozen bytes;
   - the criteria fingerprint no longer matches.

Red-at-base proof stays approve's job and is not repeated by the review. A
fourth round is refused, and the counter resets only when the human re-approves
changed criteria.

**Override.** A terminal-only command records:

- the operator's git email;
- a reason;
- the time;
- the hashes of the current frozen files.

Approve accepts it in place of a passing review while those bytes are unchanged.
This stops accidents and casual self-approval. It does not stop a hostile
operator, who can fake a terminal.

**Existing frozen suite.** Five frozen stand-ins call approve directly. While the
approve ticket is being written, and before it is approved, each gains a single
fake of the new review check, alongside the toolchain fake it already has.
Nothing they assert changes. Locks from before this feature get no exemption.
Every existing ticket is done, and the night never re-approves a done ticket.

**The night is unchanged up to the gate.** The night still only runs locked
tickets. Its just-in-time re-approval now also re-checks the review record or
override, and succeeds whenever the tests are unchanged.

**After the gate passes**, inside the session and before evidence is promoted,
the panel runs:

1. The session refuses to start the panel unless bandit and mutmut are pinned,
   naming the install line and the skip flag.
2. Bandit runs first, offline.
3. Code and security reviewers run in parallel as fresh sessions, each with its
   own checklist.
4. Every finding below the bandit high/high bar goes to a fresh disprover.
5. Survivors at security, blocker or major go to the coding agent as a fix
   round, through the session's own agent loop. Each round:
   - re-runs acceptance, the full gate, scope, the frozen hashes and the shared
     diff-size cap;
   - is followed by a fresh reviewer re-checking only the confirmed findings;
   - passes a red gate on into the next round's prompt.

   There are two rounds, counted apart from the build iterations. Red after the
   last round resets to the last green commit, and the findings count as unfixed.
6. Mutation testing runs mutmut over only the source files the ticket changed,
   using only that ticket's frozen tests, with a ten-minute stop.
7. The panel's summary goes into the evidence record and the session log.

An unfixed security or blocker finding ends the session with the new outcome
`review_failed`. The queue already treats any failed exit as failed and skips
the ticket's dependents.

**Morning notes** are written by the queue from the session logs, because failed
tickets have no evidence to read. They sit beside the night's JSON log,
uncommitted, for the same reason that log is: the run branch must not carry
files no ticket's scope allows. A single-ticket run prints the summary and
writes no file.

**Severity scale** (from the grill record, verbatim):

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

The test-review checklist (T1–T8) and the panel checklists (C1–C6, S1–S6) are
recorded verbatim in the grill record under D18 and D19. They live as rubric
files the prompts are built from. The test-review pass bar is "no blocker or
major remains".

**Model.** Reviewers and the disprover pin Opus 5.5. An environment variable
overrides it, and every record names the model used. This is independent of the
coding agent, which pins no model today.

**Naming.** The new measurement is always called the **mutation score**. The
gate already uses "mutation" for characterization-test mutation blocks, and the
two must not be confused.

## Out of scope

- UX and UI-design reviewers, and running the app for screenshots. Deferred in the grill record; the panel is built so they can be added.
- Exact reviewer prompt wording beyond the checklists. Deferred, to be tuned after real reviews.
- Performance review (C7). Rejected under D19.
- Gating on the mutation score. Rejected under D3.
- Semgrep or any network-fetching scanner. Rejected under D8.
- Protection against a hostile operator faking a terminal. A known limit, stated under D22.

## Further notes

**The seven gaps from the first /to-spec are all settled** by the re-grill:

| Gap | Settled by |
| --- | --- |
| 1. Panel wiring | D21 |
| 2. Frozen stand-ins and old locks | D25 |
| 3. Override interface | D22 |
| 4. Fingerprint storage | D26 |
| 5. Gate re-run per fix round | D23 |
| 6. Pins | D24 |
| 7. Shared test file | Amended D3, D16 and D20, which moved to `tests/test_mutation_score.py` and `tests/test_morning_notes.py` |

D27 came from checking D1 against D5.

**For /to-tickets.** None of these change a decision. They are things the
slicing has to get right.

1. **D25's verify is green at base.** The grill record says it belongs in the
   D2 ticket's `full_gate`, never its `acceptance`, because approve's red proof
   would refuse it. Taking `verify` into `acceptance` as usual would produce a
   ticket that cannot be approved. D25 is a stand-in amendment folded into the
   D2 ticket, not a ticket of its own.
2. **D25 edits three existing frozen files.** Each holds the lock of an earlier,
   done ticket, and those locks go stale. The grill accepts this, since nothing
   re-checks a done ticket's lock. At the code level, the three
   `tests/test_harness_identity.py` call sites (`:306`, `:456`, `:545`) all get
   their fakes from one shared helper, `approve_fakes`
   (`tests/test_harness_identity.py:136`). The grill says "each gains one line";
   adding it once in the helper fakes all three. It also doesn't sit "alongside
   the toolchain fake", because those three fake `measure_toolchain` instead.
   Either way, nothing they assert changes. The ticket author should pick one
   and say which.
3. **Shared frozen files.** Tickets that share one are authored one at a time:

   | Frozen file | Decisions |
   | --- | --- |
   | `tests/test_review_panel.py` | D4, D6, D7, D10, D11, D13, D14, D15, D23 |
   | `tests/test_gate_approve.py` | D2, D12, D22, D26 |
   | `tests/test_test_review.py` | D1, D5, D9, D11, D27 |
   | `tests/test_session_panel.py` | D21, D24 |
   | `tests/test_gate_toolchain.py` | D8, D24 |

   The panel ticket is blocked by the notes ticket (D20), per the amendment.
4. **Later decisions narrow earlier ones.** The earlier entries are carried
   verbatim, so the newer one must win where they differ:

   | Earlier decision | What it says | Narrowed by | What wins |
   | --- | --- | --- | --- |
   | D12 | Fingerprints "criteria and decision list" | D26 | Acceptance, decisions, scope and full_gate |
   | D17 | The panel "is called by the night run" | D21 | It runs inside the session; `edad.review panel <T>` is only a manual re-run |
   | D8 | No bandit version | D24 | Pins `bandit==1.9.4` |
   | D1 | "Loops up to 3 rounds" | D27 | The loop spans invocations, one round each |

   The ticket text for the earlier decision should say so, without rewording the
   decision line.
5. **Paths checked on 2026-10-27:**
   - These exist: `edad/gate.py`, `edad/session.py`, `edad/session_queue.py`,
     `requirements-gate.txt` (today pytest, ruff and PyYAML only),
     `QUICKSTART.md`, `.claude/skills/to-tickets/SKILL.md`, and D25's three
     frozen files.
   - These are new: `edad/review.py`, the `edad/rubrics/` directory, and the
     frozen files `tests/test_test_review.py`, `test_gate_approve.py`,
     `test_review_panel.py`, `test_mutation_score.py`, `test_morning_notes.py`,
     `test_review_cli.py`, `test_session_panel.py` and `test_gate_toolchain.py`.
     Toolchain tests live in `tests/test_harness_identity.py` today, so
     `test_gate_toolchain.py` is a new file beside them.
   - `.edad/runs/` is already gitignored.
6. **The queue spawns each session as a subprocess** (`session_argv`). So
   `--skip-review-panel` on a night must be passed through that command line,
   which is why D13's scope includes the queue.

**Deferred in the grill record** (cheap to reverse):
- UX and UI-design reviewers, plus screenshots of the running app. No ticket has a UI yet, and the panel is pluggable.
- Exact reviewer prompt wording beyond the checklists. Cheap to tune after real reviews.
- Version-probe commands for bandit and mutmut. An implementation detail.
- The JSON shape of the review, criteria and override records. Cheap to change before first use.
- Refusal message wording. Cheap to tune.
- Bandit's target paths. The recommendation is the ticket's changed source files, as for mutmut.
- How `edad.review panel <T>` locates a left-behind worktree. A manual tool, so cheap to change.

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
    seam: S5 test-review round
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
    seam: S1 gate approve
    rejected: approve nothing up front — criteria never seen by a human; review optional — unreviewed tests could be locked
  - id: D3
    decision: mutation score runs after the build and is reported in morning notes only; it never fails a ticket; named "mutation score" to stay distinct from the gate's existing mutation blocks
    verify:
      - python3 -m pytest tests/test_mutation_score.py::test_mutation_survivors_go_to_morning_notes_and_do_not_fail_the_ticket -q
    frozen:
      - tests/test_mutation_score.py
    scope:
      - edad/review.py
    seam: S10 mutation-score run (notes via S7)
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
    seam: S6 panel run (notes via S7)
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
    seam: S4 reviewer command and prompt builders
    rejected: fresh writer agent too — loses spec discussion context; bias concern is the reviewer's
  - id: D6
    decision: v1 panel runs code and security reviewers as parallel fresh sessions; reviewers are pluggable; UX/UI deferred
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_panel_runs_code_and_security_reviewers_as_parallel_fresh_sessions -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
    seam: S6 panel run
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
    seam: S6 panel run
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
    seam: S2 toolchain measurement
    rejected: semgrep — fetches rules online, network is denied at night; no scanner — security rests on judgment alone
  - id: D9
    decision: test review passes when no blocker or major remains; writer may dispute with a reason the next fresh reviewer rules on; malformed reviewer output is a failed round
    verify:
      - python3 -m pytest tests/test_test_review.py::test_review_passes_with_only_nits_left tests/test_test_review.py::test_a_disputed_finding_and_its_reason_reach_the_next_reviewer tests/test_test_review.py::test_malformed_reviewer_output_counts_as_a_failed_round -q
    frozen:
      - tests/test_test_review.py
    scope:
      - edad/review.py
    seam: S5 test-review round
    rejected: zero findings, no disputes — a wrong reviewer sinks a good ticket
  - id: D10
    decision: bandit high-severity+high-confidence findings are final; all other findings go to a fresh disprover agent; dismissals are listed in morning notes with reasons
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_high_severity_high_confidence_bandit_finding_cannot_be_dismissed tests/test_review_panel.py::test_dismissed_findings_are_listed_in_morning_notes_with_reasons -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
    seam: S6 panel run (notes via S7)
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
    seam: S5 test-review round (review record); S6 panel run (evidence summary)
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
    seam: S1 gate approve
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
    seam: S6 panel run (notes via S7)
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
    seam: S6 panel run
    rejected: three levels with security folded in — security could be graded major and only flagged
  - id: D15
    decision: reviewers and disprover run `claude -p --model claude-opus-5-5`, overridable by EDAD_REVIEW_MODEL; the model is written into the review record
    verify:
      - python3 -m pytest tests/test_review_panel.py::test_reviewer_argv_pins_opus_and_honours_EDAD_REVIEW_MODEL tests/test_review_panel.py::test_review_record_names_the_model_used -q
    frozen:
      - tests/test_review_panel.py
    scope:
      - edad/review.py
    seam: S4 reviewer command and prompt builders (argv); S6 panel run (record)
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
    seam: S10 mutation-score run
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
    seam: S3 review CLI parser
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
    seam: S4 reviewer command and prompt builders
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
    seam: S4 reviewer command and prompt builders
    rejected: C7 performance — rarely matters here, mostly nits
  - id: D20
    decision: morning notes are one Markdown file per night in .edad/runs/, sections in order Needs you, Test strength, Dismissed findings, Fixed overnight, Nits
    verify:
      - python3 -m pytest tests/test_morning_notes.py::test_morning_notes_put_needs_you_first_and_nits_last tests/test_morning_notes.py::test_morning_notes_keep_every_section_when_the_night_has_nothing_to_report tests/test_morning_notes.py::test_needs_you_lists_the_panel_skip_then_failed_tickets_then_unfixed_majors tests/test_morning_notes.py::test_test_strength_shows_each_tickets_mutation_score_and_its_survivors tests/test_morning_notes.py::test_dismissed_findings_are_listed_each_with_its_own_reason tests/test_morning_notes.py::test_fixed_overnight_lists_the_findings_the_fix_rounds_closed tests/test_morning_notes.py::test_nits_are_grouped_under_their_ticket -q
    frozen:
      - tests/test_morning_notes.py
    scope:
      - edad/review.py
      - edad/session_queue.py
    seam: S7 morning-notes writer
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
    seam: S8 session run (panel order, review_failed); S9 night queue run (morning notes)
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
    seam: S1 gate approve
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
    seam: S6 panel run
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
    seam: S2 toolchain measurement (pins); S8 session run (panel refusal)
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
    seam: S1 gate approve (existing frozen stand-ins)
    rejected: exempt pre-feature locks — needs a cutoff rule, protects nothing ever re-approved; skip_review Namespace field — changes the stand-ins' call shape
  - id: D26
    decision: approve-criteria writes committed .edad/hashes/<T>.criteria.json — sha256 over acceptance, decisions, scope and full_gate, plus git email and time; review record is .edad/hashes/<T>.review.json
    verify:
      - python3 -m pytest tests/test_gate_approve.py::test_criteria_fingerprint_covers_acceptance_decisions_scope_and_full_gate_only -q
    frozen:
      - tests/test_gate_approve.py
    scope:
      - edad/gate.py
    seam: S1 gate approve
    rejected: acceptance+decisions only — scope/full_gate drift unnoticed; whole ticket file — body typo needs the human again
  - id: D27
    decision: each `edad.review tests <T>` invocation runs one round; rounds and --dispute F<n>="reason" accumulate in .edad/hashes/<T>.review.json; a fourth round is refused; the counter resets only on a new approve-criteria over changed criteria; a passing round runs gate approve
    verify:
      - python3 -m pytest tests/test_test_review.py::test_each_invocation_runs_one_round_and_a_fourth_is_refused tests/test_test_review.py::test_round_counter_resets_only_when_criteria_are_reapproved tests/test_test_review.py::test_a_dispute_that_names_no_finding_of_the_last_round_is_refused tests/test_test_review.py::test_the_reviewer_is_given_the_spec_every_frozen_file_and_the_tests_rubric_and_no_tools tests/test_test_review.py::test_a_passing_round_runs_gate_approve_in_the_repo tests/test_test_review.py::test_a_reviewer_that_fails_to_run_uses_up_no_round -q
    frozen:
      - tests/test_test_review.py
    scope:
      - edad/review.py
    seam: S5 test-review round
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
