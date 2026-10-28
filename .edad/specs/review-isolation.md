---
slug: review-isolation
grilled: .edad/grills/review-isolation.md
status: draft
---

## Problem statement

The test reviewer is meant to be a fresh reader. It should see only the spec,
the frozen tests and the rubric (review-loops D5), so its verdict is not shaped
by how the tests came to be written. It is not a fresh reader today. T031 turned
its tools off and wrote "the prompt is all it can read", but `claude` loads
context at startup whatever the tool settings. The reviewer starts in the repo
root, and a measured probe (2026-10-28, `claude` 2.1.280) showed it could quote
this project's memory index, name the current branch and describe T031's night.
It also still runs under Claude Code's default coding-assistant system prompt,
which lists slash commands and memory instructions.

T031's post-build review also found four weak spots in the review round:

- The pass is stamped on the frozen files' hashes as they stand *after* the
  reviewer returns, so tests edited during a review get approved unseen.
- A corrupt review record is silently overwritten, which destroys the history
  that is supposed to be append-only.
- A missing `claude` binary crashes with a traceback and the same exit code as
  a failed round. A hung reviewer blocks forever.
- A ticket with no frozen files launches a reviewer on nothing and spends a
  round that approve will then refuse anyway.

Some advice in the skills and session messages is also stale since T029. It
still tells the operator to run plain `approve` on an unlocked ticket, and that
is now refused without a review.

## Solution

The reviewer is launched in a brand-new empty directory outside the repo, which
is deleted afterwards, and with a short fixed system prompt that names its role.
It then sees the prompt and nothing about the project. The only things left are
the account email, username, platform, date and model id, which `claude` injects
regardless and which say nothing about the ticket. A hand-run live canary proves
this against the real `claude`, at approval and after every `claude` upgrade.

The round records the hashes of exactly the bytes the reviewer was shown. A
reviewer that could not run, whether the binary is missing, it timed out after
900 s, or there was nothing to review, spends no round and writes nothing. A
corrupt review record stops the command instead of being overwritten.

A separate, later ticket corrects the stale advice and documents two behaviours
the operator needs to know about. First, a pass still counts toward the three
rounds. Second, when a round passes but approve fails, re-run plain approve
rather than re-reviewing.

The work splits into **T040** (isolation, D30–D31), which must land before
T032's real test review, and **T041** (hardening and docs, D32–D36), which is
blocked by T040 only because both edit the same module.

## User stories

1. As a ticket author, I want the test reviewer to know nothing about the
   project beyond the spec and tests I hand it, so that its pass means the
   tests stand on their own.
2. As a ticket author, I want the reviewer free of the coding-assistant framing
   and slash-command listing, so that it reads as a reviewer and not as a
   helper in my repo.
3. As the operator, I want a re-runnable check against the real `claude` that
   the reviewer cannot see a planted project secret, so that a `claude` upgrade
   that loads context differently is caught.
4. As the operator, I want the daytime review to keep working on my OAuth login,
   so that isolation does not cost me the review.
5. As the operator, I want a pass to be recorded against the bytes the reviewer
   actually read, so that tests edited mid-review cannot be approved unseen.
6. As a ticket author, I want a missing `claude`, a hung reviewer or a ticket
   with no frozen files refused cleanly without using up a round, so that
   infrastructure faults don't eat into my three rounds.
7. As the operator, I want a corrupt review record to stop the command and be
   left as it is, so that the round history is never silently destroyed.
8. As the operator, I want the skills and session messages to name the commands
   that actually work since T029, so that I'm not sent to a refused `approve`.
9. As a ticket author whose round passed but whose approve then failed, I want
   to be told to re-run plain approve, so that I don't spend another round.

## Seams

**S4 — reviewer command builder** (`reviewer_argv`, named as in the
review-loops spec)
- **Exists**: yes. T030's frozen argv test drives it.
- **Observes**: the exact argv the reviewer is launched with, including a fixed
  `--system-prompt` value. The value is distinct from the review prompt, which
  appears exactly once, and the argv starts with `claude -p`.
- **Discharges**: D30 (system-prompt half).

**S5 — the test-review round** (`edad.review tests <T>` via `review.main()`,
named as in the review-loops spec), driven through T031's `run=` hook. The real
`run_reviewer` runs and only `subprocess.run` is faked.
- **Exists**: yes. `test_a_reviewer_that_fails_to_run_uses_up_no_round` already
  drives it this way.
- **Observes**:
  - the `cwd` and `timeout` the reviewer process is given. The fake can check,
    during the call, that the directory exists, is empty and is outside the
    repo, and afterwards that it is gone;
  - the review record on disk, including each round's `frozen` hashes. A fake
    that edits a frozen file mid-call shows which bytes were hashed;
  - the exit code and whether anything was written when the fake raises
    `FileNotFoundError` or `TimeoutExpired`, when the ticket has no frozen
    files, or when the record on disk is corrupt.
- **Discharges**: D30 (empty-directory half), D32, D33, D34.

**L1 — live reviewer canary** (the real `review.run_reviewer` against the real
`claude`, from inside a temp git project with a planted word)
- **Exists**: new. It is modelled on `docker_tests/`: it sits outside
  `testpaths` and refuses to import without its opt-in variable.
- **Observes**: whether a word planted in the project's CLAUDE.md and branch
  name can appear in what the reviewer prints. This is the one thing S4 and S5
  cannot see: what the model is actually given at startup.
- **Discharges**: D31.

**Decisions with no seam:** D35 (doc and message wording) and D36 (a pass keeps
counting, as built). Both are marked `unenforced` in the grill with reasons, and
are checked by T041's post-build review.

L1 has a command but is **not an acceptance command**. The night's sandbox
denies the network, so it cannot launch a real `claude`. It is run by hand at
T040's approval, where it must be red at base and green after, and again after
any `claude` upgrade.

## Implementation decisions

- **Isolation lives inside the reviewer runner.** It creates a temporary
  directory with the standard library, launches the reviewer there and lets it
  be deleted on exit. The runner keeps its one-argument shape. T031's frozen
  `Reviewer` stand-in replaces it with a one-argument callable, so the
  directory cannot be passed in by the caller.
- **The system prompt is a short fixed role statement** added to the argv
  builder. The reviewer's real instructions (spec, artifact, rubric, disputes)
  stay in the prompt, where T030's and T031's tests already pin them. The
  docstring is corrected to say what the reviewer can still see (the injected
  email, username, platform, date and model id).
- **`--bare` is not used.** It gives the strongest isolation, but it
  authenticates only by API key, and the host review runs on the operator's
  OAuth login.
- **The round reads each frozen file once**, as bytes. It builds the artifact
  and the round's recorded hashes from that one read, instead of re-hashing
  from disk after the reviewer returns.
- **Infrastructure refusals go through the gate's existing `die`.** These are a
  missing binary, a timeout (a 900 s constant in the review module), a ticket
  with no frozen files (using approve's own message) and a corrupt record
  (naming the file). They join T031's "non-zero exit spends no round" rule, and
  none of them writes anything.
- **Corrupt and missing records are told apart** in the review command by
  whether the record path exists, since the gate's record reader returns
  nothing for both. Approve's reader is deliberately unchanged: there a corrupt
  record still counts as no record.
- **The live canary** builds a throwaway git project with a made-up word in its
  CLAUDE.md and branch name, runs the real reviewer from inside it, and asserts
  the word does not appear. It plants nothing in the operator's real memory
  directory. CLAUDE.md and git status stand in for memory, because the
  measurement showed all three leak together.

## Out of scope

- A `trigger` field in the shared reviewer output format: owned by T034
  (review-loops D14).
- Sharing `cmd_tests`'s criteria check with `gate.review_problems`: needs
  `gate.py` in scope; left for a ticket that touches both.
- Counting only failed rounds: rejected in D36.
- The post-build panel's reviewers. This spec isolates the test reviewer's
  launcher. The panel (T032 onward) should launch through the same runner, but
  that wiring belongs to the panel's own tickets.

## Further notes

- **Deferred from the grill, settled at authoring:** the exact `--system-prompt`
  wording, the timeout constant's name, the final test names, the refusal
  wording and the temp-directory prefix.
- **Probe at authoring.** None of the three frozen files exists yet, so the
  `verify` commands could not be run at base in this stage. When `to-tickets`
  authors them, run each command at base, at base plus stubs, and against a
  throwaway implementation. Every acceptance command must be red at base. D31
  must be red at base against the real `claude` (today's leak) and green after.
- **Frozen stand-in arity.** T031's `Reviewer` stand-in fixes
  `run_reviewer(argv)` at one argument, and T030's argv test fixes
  `argv[:2] == ["claude", "-p"]` with the prompt appearing once. Neither breaks
  under D30 as decided, but probe both at authoring.
- **The T040 draft ticket is stale.** It cites the review-loops spec, puts all
  five tests in one frozen file and keeps the docs work in its scope. Under the
  split, T040 is D30 and D31 with `tests/test_review_isolation.py`, plus the
  live canary authored with the contract. T041 is D32 to D36 with
  `tests/test_review_round_hardening.py`. `to-tickets` should rewrite T040 and
  create T041 from this spec.
- **Line references in D35 checked against the tree on 2026-10-28.** They are
  `.claude/skills/next/SKILL.md:49-50` (the two `approve` rows) and
  `edad/session.py:141` (the "no approval lock" abort). The 101-character line
  in `.claude/skills/to-tickets/SKILL.md` is line 299.
- `live_tests/` does not exist yet. T040's contract creates it, and it is not in
  the agent's scope.

## Decisions

```yaml
decisions:
  - id: D30
    decision: run_reviewer launches claude with cwd a fresh empty temp dir outside the repo (deleted after), and reviewer_argv passes a fixed short --system-prompt naming the role; the reviewer's instructions stay in the prompt
    verify:
      - python3 -m pytest tests/test_review_isolation.py::test_the_reviewer_runs_in_an_empty_directory_outside_the_repo -q
      - python3 -m pytest tests/test_review_isolation.py::test_the_reviewer_argv_replaces_the_default_system_prompt -q
    frozen:
      - tests/test_review_isolation.py
    scope:
      - edad/review.py
    seam: S4 reviewer command builder (--system-prompt); S5 test-review round (empty cwd)
    rejected: --bare — API-key auth only, daytime review would stop on the operator's OAuth login; empty cwd alone — keeps the coding-assistant system prompt and slash-command listing
  - id: D31
    decision: an opt-in live canary (live_tests/test_reviewer_isolation.py, EDAD_LIVE_REVIEW=1, outside testpaths) plants a made-up word in a temp project's CLAUDE.md and branch name and asserts the real reviewer cannot repeat it; hand-written with T040's contract, red at base, hand-run at approval and after claude upgrades, never an acceptance command
    verify:
      - EDAD_LIVE_REVIEW=1 python3 -m pytest live_tests/test_reviewer_isolation.py -q
    frozen:
      - live_tests/test_reviewer_isolation.py
    scope:
      - live_tests/test_reviewer_isolation.py
    seam: L1 live reviewer canary
    rejected: mechanism test only — a claude release that loads context differently goes unnoticed; one-off shell probe — nothing to re-run after an upgrade; docker_tests/ — the name says docker and this needs none
  - id: D32
    decision: cmd_tests reads each frozen file's bytes once and both builds the artifact and records the round's frozen hashes from those same bytes
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_round_records_the_bytes_the_reviewer_was_shown -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
    seam: S5 test-review round
    rejected: hash just before launch — leaves a window between read and hash
  - id: D33
    decision: a reviewer that could not run spends no round and writes nothing — a missing claude binary and a 900 s timeout are gate.die; a ticket with no frozen files is refused before any launch
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_missing_reviewer_binary_is_refused_and_spends_no_round -q
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_reviewer_that_times_out_is_refused_and_spends_no_round -q
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_ticket_with_no_frozen_files_launches_no_reviewer -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
    seam: S5 test-review round
    rejected: no timeout — a hang blocks the writing session silently; timeout as a failed round — burns a round on an infrastructure fault
  - id: D34
    decision: an existing but unreadable review record, or one whose rounds is not a list, is refused by cmd_tests naming the file; nothing is launched or written; approve's reader is unchanged
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_corrupt_review_record_is_refused_and_left_alone -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
    seam: S5 test-review round
    rejected: move aside and start at round 1 — a reset by deletion, which D27 rejects
  - id: D35
    decision: fix stale approve advice (next/SKILL.md:49-50, session.py:141), the to-tickets approval wording and 101-char line, document pass-then-approve-fails (re-run plain gate approve) and D36, and reword the dispute-after-reset refusal
    unenforced: prose and message wording, already listed as cheap to tune; a string-pinning test is brittle; checked by the post-build review
    scope:
      - .claude/skills/next/SKILL.md
      - .claude/skills/to-tickets/SKILL.md
      - edad/session.py
      - edad/review.py
    seam: none — unenforced
    rejected: test session.py's message only — still a string pin for one line of many
  - id: D36
    decision: a passing round keeps counting toward the three rounds under the current criteria (T031's behaviour, unchanged); the way out after a re-author is approve-criteria over changed criteria or override-review
    unenforced: declines to change T031's behaviour, which its frozen counter tests already pin for fail sequences; documented via D35
    scope: []
    seam: none — unenforced
    rejected: count only failed rounds — changes what `round` means and needs a new frozen test for a case that arises only when tests are re-authored after lock
deferred:
  - trigger field in the shared reviewer output format — T034 owns D14; extra keys are allowed and ignored, so adding it later breaks no record
  - cmd_tests's criteria check duplicates gate.review_problems' — a shared helper needs gate.py in scope
  - exact --system-prompt wording, timeout constant name, test names, refusal wording, temp-dir prefix — cheap to change, settled at authoring
```
