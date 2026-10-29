---
slug: review-isolation
grilled_at: 2026-10-28
---

## Record

### Why

The T031 post-build review (2026-10-28, integration axis) suspected that the
test reviewer was not the fresh reader D5 (review-loops) promises. T031 added
`--tools ""` to `reviewer_argv`, and its docstring says "the prompt is all it
can read". That claim was measured the same day with `claude` 2.1.280:

- **From the repo root**, `claude -p "<probe>" --tools ""`:
  - quoted this project's auto-memory index ("Verifier reads the primary
    artifact", "Multi-ticket controller");
  - named the current branch (`t031-test-review`);
  - described T031's night, its evidence commit `e047ff4` and its bootstrap
    override.

  `--tools ""` switches tools off. It does not stop the context `claude`
  loads at startup. `run_reviewer` passes no `cwd`, so the reviewer inherits
  the caller's directory, which is the repo root.
- **From a fresh empty temp directory**, the same probe found no memory
  entries, no CLAUDE.md, no git status, and nothing about T031. It still
  carried Claude Code's default coding-assistant system prompt: a memory
  section, environment sections, and slash commands (`/code-review`, `/fast`).
- **From an empty dir plus `--system-prompt "You are a reviewer of test
  files. You have no tools."`**, the reviewer saw no skills, no MCP servers
  and no memory instructions. Still present: the user's email (a system
  reminder), the username in paths, platform, date, and model id. These are
  injected regardless. None of them is about the ticket, so they are
  accepted.
- `--bare` skips auto-memory and CLAUDE.md discovery, but per `claude --help`
  its auth is "strictly ANTHROPIC_API_KEY or apiKeyHelper (OAuth and keychain
  are never read)". The host review runs on the operator's OAuth login.

Other facts used:

- T030's frozen argv test (`tests/test_test_review.py`) asserts
  `argv[:2] == ["claude", "-p"]`, `argv.count(prompt) == 1`, a prompt that
  doesn't start with `-`, and no resume flag. A fixed `--system-prompt`
  value passes all four.
- T031's frozen tests fake `subprocess.run` with `**kwargs` (lines
  217-224), so a new `cwd=` breaks none of them. T031's tests exercise only
  fail-then-pass sequences, so whether a pass counts toward the cap is open
  to either answer.
- Acceptance commands run every iteration inside the night's sandbox with
  the network denied, so no acceptance test can launch a real `claude`.
- Precedent for a hand-run live test: `docker_tests/test_properties.py`. It
  sits outside `pyproject.toml`'s `testpaths = ["tests"]` and refuses to
  import without `EDAD_DOCKER_TESTS=1`, so a run without the variable errors
  instead of passing on nothing.
- `gate.read_record` returns `None` for both a missing record and an
  unreadable one. `gate.hash_record_path(root, tid, kind)` gives the path.

### Split (settled first)

The draft T040 is split in two:

- **T040, isolation only.** This alone blocks T032's real test review.
- **T041, hardening and docs.** It is blocked by T040 because both edit
  `edad/review.py`, and it can land any time after T040.

The order is T040, then T032's review; T041 does not block T032.

Rejected: one ticket. T032 would wait for all of it.

### D30: the reviewer starts in an empty directory with a fixed system prompt

`run_reviewer` launches `claude` with `cwd` set to a fresh empty temporary
directory outside the repo (`tempfile.TemporaryDirectory()`), deleted after
the process exits. The directory must be outside the repo: `claude` walks
upward for CLAUDE.md and git. `reviewer_argv` also passes a fixed short
`--system-prompt` that names the role (the reviewer of the given artifact,
with no tools). The reviewer's actual instructions stay in the prompt, where
T030's and T031's frozen tests already pin them. The docstring claim "the
prompt is all it can read" becomes true apart from the injected
email/username/platform/date, and the docstring should say that.

Verify (provisional names; confirmed at authoring):

    python3 -m pytest tests/test_review_isolation.py::test_the_reviewer_runs_in_an_empty_directory_outside_the_repo -q
    python3 -m pytest tests/test_review_isolation.py::test_the_reviewer_argv_replaces_the_default_system_prompt -q

Scope: `edad/review.py`.

Rejected:

- `--bare`: API-key auth only, so the daytime review would stop working
  on the operator's login.
- Empty cwd alone: it fixes the leak of project knowledge but keeps the
  coding-assistant framing and the slash-command listing.

### D31: a live canary proves the isolation, run by hand at approval

`live_tests/test_reviewer_isolation.py` is modelled on `docker_tests/`. It
sits outside `testpaths` and refuses to import without `EDAD_LIVE_REVIEW=1`.
It builds a temp git project with a made-up word in its CLAUDE.md and in its
branch name, chdirs into it, runs the real `review.run_reviewer` on a probe
prompt, and asserts the word is not in the output. It does not plant
anything under `~/.claude` (auto-memory): writing there would touch the
operator's real memory. CLAUDE.md and git status are the stand-ins, and the
2026-10-28 measurement showed memory and git status leak together.

It is hand-written with T040's contract, like `docker_tests`. It must fail
at base (today's leak) and pass after T040. It is run by hand at approval
and again after any `claude` upgrade. It is not an acceptance command,
because the night's sandbox has no network.

Verify (hand-run):

    EDAD_LIVE_REVIEW=1 python3 -m pytest live_tests/test_reviewer_isolation.py -q

Scope: `live_tests/test_reviewer_isolation.py` (authored at contract time,
not by the agent).

Rejected:

- The mechanism test alone: a `claude` release that loads context
  differently would go unnoticed.
- A one-off shell probe: nothing to re-run after an upgrade.
- Putting it in `docker_tests/`: the name says docker, and this test needs
  none.

### D32: the reviewer's bytes and the recorded hashes are the same bytes

`cmd_tests` reads each frozen file's bytes once. It builds the artifact from
those bytes and records the round's `frozen` hashes from the same bytes. Today
it calls `gate.frozen_hashes_now` after `run_reviewer` returns, so tests
edited while the reviewer runs get a pass stamped on bytes it never saw, and
`review_problems` accepts that pass.

Verify (provisional):

    python3 -m pytest tests/test_review_round_hardening.py::test_a_round_records_the_bytes_the_reviewer_was_shown -q

Scope: `edad/review.py`.

Rejected: hashing just before launch, which leaves a window between the
read and the hash.

### D33: a reviewer that could not run uses up no round

These extend T031's "a reviewer that exits non-zero spends no round" rule:

- a missing `claude` binary (`FileNotFoundError`) is a `gate.die`;
- a reviewer still running after 900 s is a `gate.die` naming the timeout,
  with the timeout a constant in `review.py`;
- a ticket with no frozen files is refused before anything launches, with
  approve's own message ("ticket declares no frozen files").

None of these writes anything.

Verify (provisional):

    python3 -m pytest tests/test_review_round_hardening.py::test_a_missing_reviewer_binary_is_refused_and_spends_no_round -q
    python3 -m pytest tests/test_review_round_hardening.py::test_a_reviewer_that_times_out_is_refused_and_spends_no_round -q
    python3 -m pytest tests/test_review_round_hardening.py::test_a_ticket_with_no_frozen_files_launches_no_reviewer -q

Scope: `edad/review.py`.

Rejected:

- No timeout: it is a daytime command and the operator can Ctrl-C, but a
  hang blocks the ticket-writing session silently.
- A timeout counted as a failed round: it burns a round on an
  infrastructure fault.

### D34: a corrupt review record is refused, never overwritten

If `.edad/hashes/<T>.review.json` exists but is unreadable, or its `rounds`
is not a list, `cmd_tests` refuses through `gate.die` naming the file. It
launches nothing and writes nothing. Today it treats the record as empty and
overwrites it, destroying the history T031 says is never rewritten. Missing
and unreadable are told apart here (the path exists, `read_record` returns
`None`). Approve's reader is unchanged: a corrupt record still counts as no
record there, which is consistent with "absence is unknown".

Verify (provisional):

    python3 -m pytest tests/test_review_round_hardening.py::test_a_corrupt_review_record_is_refused_and_left_alone -q

Scope: `edad/review.py`.

Rejected: moving the record aside and starting at round 1. That is a reset
by deletion, which D27 rejects.

### D35: doc and wording fixes (unenforced)

These are in T041's scope and checked by the post-build review, not by a
test:

- `.claude/skills/next/SKILL.md:49-50` and `edad/session.py:141` still say
  to run `python3 -m edad.gate approve` for an unlocked ticket. Since T029
  that is refused without a review. Point them to `approve-criteria` plus
  `edad.review tests`, or `override-review`.
- In `.claude/skills/to-tickets/SKILL.md`:
  - "Approval hashes the acceptance tests…" now follows "asking the
    operator for `approve-criteria`" and reads as if that command writes
    the lock. Reword it.
  - Re-wrap the 101-character line.
  - Add the case where a round passes but approve fails: re-run plain
    `edad.gate approve <T>`, since the pass is recorded and re-reviewing
    would spend a round.
  - Document D36.
- A dispute after a criteria reset is refused with "before any round has
  run", which is untrue. Reword it, for example "no round under the current
  criteria".
- *(Added 2026-10-28, T040 post-build review.)* T040's `run_reviewer`
  docstring says `claude` "finds no CLAUDE.md". It finds no *project*
  CLAUDE.md: a user-level `~/.claude/CLAUDE.md` loads from any directory.
  Say so, beside the other injections the `reviewer_argv` docstring admits.

Unenforced because: these are prose and message wording, which the
review-loops spec already lists as cheap to tune. A string-pinning test is
brittle and proves only that a word appears.

Scope: `.claude/skills/next/SKILL.md`, `.claude/skills/to-tickets/SKILL.md`,
`edad/session.py`, `edad/review.py`.

Rejected: testing `session.py`'s message only.

### D36: a passing round counts toward the three (kept as built)

T031's counter counts every round under the current criteria fingerprint,
passes included. A ticket that passed on round 3 and later has its tests
re-authored under unchanged criteria gets no more rounds. The way out is
`approve-criteria` over changed criteria, or `override-review`: a person in
the loop, which is D27's intent. This is documented in the to-tickets skill
(D35).

Unenforced because: it is T031's existing behaviour, already pinned by
T031's frozen counter tests for the fail sequences. This decision only
declines to change it.

Scope: none (documentation via D35).

Rejected: counting only failed rounds. That changes what the record's
`round` means and needs a new frozen test for a case that arises only when
tests are re-authored after lock.

### Amendment (2026-10-28): T040's post-build review

T040's three fresh reviewers (drift, craft, integration) found no drift, but
three ways the caller can still reach or break the isolated reviewer. The
operator chose to make them real decisions in T041, which already edits
`run_reviewer`, rather than notes.

### D37: the reviewer's stdin is closed

`run_reviewer` launches `claude` with stdin closed (`stdin=subprocess.DEVNULL`).
Today it inherits the caller's stdin, and `claude -p` reads piped stdin into
its prompt. Measured 2026-10-28 with `claude` 2.1.280, from an empty temp dir
with `--system-prompt` and `--tools ""`: a line piped in was quoted back word
for word. The same call with stdin from `/dev/null` showed only what `claude`
always injects. So `edad.review tests` run from a pipe or a script hands the
reviewer whatever the caller pipes in, which is the kind of leak D30 closes.

Verify:

    python3 -m pytest tests/test_review_round_hardening.py::test_the_reviewer_cannot_read_the_callers_stdin -q

Scope: `edad/review.py`.

Rejected: leaving it to the operator not to pipe, since a script or a session
runner pipes by default.

### D38: the reviewer's output is read as UTF-8

`run_reviewer` decodes the reviewer's output as UTF-8 (`encoding="utf-8"`),
not with the locale's encoding. Under `LANG=C`, as on some CI images, a
non-ASCII reply raises `UnicodeDecodeError` today. `load_rubric` already reads
as UTF-8. T031's frozen `test_a_reviewer_that_fails_to_run_uses_up_no_round`
returns real output only when `capture_output=True` and `text=True` are both
passed, so `text=True` stays and `encoding` is added beside it.

Verify:

    python3 -m pytest tests/test_review_round_hardening.py::test_the_reviewers_output_is_read_as_utf8 -q

Scope: `edad/review.py`.

Rejected: `errors="replace"`, which turns a garbled reply into a
plausible-looking one; a reply that isn't valid UTF-8 should stay a crash or a
malformed round, not be quietly patched.

### D39: a temp directory inside a project is refused

D30's empty directory comes from the system temp location, which `TMPDIR`
sets. If `TMPDIR` points inside a project, the reviewer starts inside it and
`claude` loads that project again, with no error. `run_reviewer` therefore
checks the directory it made and every directory above it for `.git` or
`CLAUDE.md`, the same markers T040's frozen test uses. If it finds one, it
refuses through `gate.die` before launching, naming what it found, and the
directory is still removed. Nothing in the harness sets `TMPDIR`, and the
night's container uses `/tmp`.

Verify:

    python3 -m pytest tests/test_review_round_hardening.py::test_a_temp_directory_inside_a_project_launches_no_reviewer -q

Scope: `edad/review.py`.

Rejected:

- A fixed `dir=` of its own: there is no location that is outside every
  project on every machine, and it would bypass the operator's `TMPDIR`.
- `.claude/` as a marker: `~/.claude` is user-level and loads anyway, so a
  `TMPDIR` under the home directory would be refused for nothing.

### Deferred

- The `trigger` field in the shared reviewer output format: T034 (D14 is its
  decision). Extra keys are already allowed and ignored by every reader, so
  adding it later doesn't break T032's records.
- `cmd_tests`'s criteria check duplicates `gate.review_problems`' check and
  message (gate.py:1784-1789). A shared helper needs `gate.py` in scope.
  Leave it until a ticket touches both.
- Exact `--system-prompt` wording, the timeout constant's name, the test
  names, refusal wording, and the temp-directory prefix. All are cheap to
  change and settled at authoring.

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
    rejected: --bare — API-key auth only, daytime review would stop on the operator's OAuth login; empty cwd alone — keeps the coding-assistant system prompt and slash-command listing
  - id: D31
    decision: an opt-in live canary (live_tests/test_reviewer_isolation.py, EDAD_LIVE_REVIEW=1, outside testpaths) plants a made-up word in a temp project's CLAUDE.md and branch name and asserts the real reviewer cannot repeat it; hand-written with T040's contract, red at base, hand-run at approval and after claude upgrades, never an acceptance command
    verify:
      - EDAD_LIVE_REVIEW=1 python3 -m pytest live_tests/test_reviewer_isolation.py -q
    frozen:
      - live_tests/test_reviewer_isolation.py
    scope:
      - live_tests/test_reviewer_isolation.py
    rejected: mechanism test only — a claude release that loads context differently goes unnoticed; one-off shell probe — nothing to re-run after an upgrade; docker_tests/ — the name says docker and this needs none
  - id: D32
    decision: cmd_tests reads each frozen file's bytes once and both builds the artifact and records the round's frozen hashes from those same bytes
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_round_records_the_bytes_the_reviewer_was_shown -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
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
    rejected: no timeout — a hang blocks the writing session silently; timeout as a failed round — burns a round on an infrastructure fault
  - id: D34
    decision: an existing but unreadable review record, or one whose rounds is not a list, is refused by cmd_tests naming the file; nothing is launched or written; approve's reader is unchanged
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_corrupt_review_record_is_refused_and_left_alone -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
    rejected: move aside and start at round 1 — a reset by deletion, which D27 rejects
  - id: D35
    decision: fix stale approve advice (next/SKILL.md:49-50, session.py:141), the to-tickets approval wording and 101-char line, document pass-then-approve-fails (re-run plain gate approve) and D36, reword the dispute-after-reset refusal, and say run_reviewer's docstring means no *project* CLAUDE.md
    unenforced: prose and message wording, already listed as cheap to tune; a string-pinning test is brittle; checked by the post-build review
    scope:
      - .claude/skills/next/SKILL.md
      - .claude/skills/to-tickets/SKILL.md
      - edad/session.py
      - edad/review.py
    rejected: test session.py's message only — still a string pin for one line of many
  - id: D36
    decision: a passing round keeps counting toward the three rounds under the current criteria (T031's behaviour, unchanged); the way out after a re-author is approve-criteria over changed criteria or override-review
    unenforced: declines to change T031's behaviour, which its frozen counter tests already pin for fail sequences; documented via D35
    scope: []
    rejected: count only failed rounds — changes what `round` means and needs a new frozen test for a case that arises only when tests are re-authored after lock
  - id: D37
    decision: run_reviewer launches claude with stdin closed (stdin=subprocess.DEVNULL), so input piped to `edad.review tests` cannot reach the reviewer
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_the_reviewer_cannot_read_the_callers_stdin -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
    rejected: leave it to the operator not to pipe — scripts and session runners pipe by default
  - id: D38
    decision: run_reviewer decodes the reviewer's output as UTF-8 (encoding="utf-8" beside T031's capture_output=True, text=True), not the locale's encoding
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_the_reviewers_output_is_read_as_utf8 -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
    rejected: errors="replace" — quietly patches a garbled reply into a plausible one
  - id: D39
    decision: run_reviewer refuses (gate.die, before any launch, naming what it found) when its temp directory or any directory above it holds .git or CLAUDE.md; the directory is still removed
    verify:
      - python3 -m pytest tests/test_review_round_hardening.py::test_a_temp_directory_inside_a_project_launches_no_reviewer -q
    frozen:
      - tests/test_review_round_hardening.py
    scope:
      - edad/review.py
    rejected: a fixed dir= of its own — nowhere is outside every project on every machine, and it bypasses TMPDIR; .claude/ as a marker — ~/.claude is user-level and loads anyway
deferred:
  - trigger field in the shared reviewer output format — T034 owns D14; extra keys are allowed and ignored, so adding it later breaks no record
  - cmd_tests's criteria check duplicates gate.review_problems' — a shared helper needs gate.py in scope
  - exact --system-prompt wording, timeout constant name, test names, refusal wording, temp-dir prefix — cheap to change, settled at authoring
```

## Authoring probe (2026-10-28, to-tickets)

Detached worktree at e047ff4, claude 2.1.280. Test names confirmed as the
grill's provisional ones; no stubs needed, since every behaviour changes an
existing function.

- Base: all 7 acceptance commands FAILED on assertions (`--tb=line`): no `cwd`;
  no `--system-prompt`; hash of edited bytes recorded; `FileNotFoundError`
  escaped; no `timeout`; no-frozen ticket launched and recorded a round;
  corrupt record overwritten. `ruff check .` clean.
- Live canary at base: isolation test FAILED (reviewer repeated the planted
  word); its control (plain `claude` in the project sees the word) passed.
- T040 throwaway (21 lines, `edad/review.py`): D30 green, live canary 2 passed,
  suite 330 passed + T041's 5 red.
- T041 throwaway (+35 lines): all green, suite 335 passed.
- The live canary gained a control test beyond D31's wording: without it, a
  `claude` that stopped loading CLAUDE.md would make the canary pass vacuously.

## Re-probe (2026-10-28, after T040 merged, main 5d77df4)

T041's five tests were re-run at the new base: all five still FAILED on the same
assertions. D37–D39's three tests were added to the same frozen file. At base
all three FAILED on assertions: stdin not closed (`[False]`); output decoded
with the locale's encoding (`None`); a temp dir inside a project launched and
recorded a round. Full suite at base: 8 failed (exactly T041's), 330 passed.

Throwaway fix for all of T041 (`edad/review.py`, +42/−10): all 8 green, full
suite 338 passed, ruff clean, live canary 2 passed. The first throwaway
dropped `text=True` for `encoding="utf-8"` and broke T031's frozen
`test_a_reviewer_that_fails_to_run_uses_up_no_round`, whose fake returns
output only with `text=True` (hence D38's wording).
