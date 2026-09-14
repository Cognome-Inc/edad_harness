---
slug: gate-trusted-inputs-from-base
grilled_at: 2026-09-14
---

## Record

Grilled 2026-09-14 on `Cognome-Inc/edad_harness` @ `62df609` (branch
`t020-toolchain-measurement`, T020 + T021 done, unpushed). Prompted by three findings
on T021's boundary — `evaluate` reads `requirements-gate.txt` from the agent's
worktree; `toolchain_line` prints `unknown` for `{}`; `harness_line` drops a partial
block's commit — and a fourth raised in discussion: the agent can write to the
worktree that holds both the frozen tests and their approval lock, and `.edad/` is
excluded from scope.

Facts established before the interview, by reading and by running rather than by
asking. **The tamper is three lines and works today.** In a throwaway clone of HEAD:
edit `tests/test_gate_refusal.py` (T021's frozen file) → `check_freeze` fails; rewrite
the one hash in `.edad/hashes/T021.json` → `check_freeze` passes; `changed_files`
returns only the test file (`.edad/` is filtered by `INFRA_PREFIXES`,
`edad/gate.py:365`), and `check_scope` admits it because `edad/gate.py:428` adds
`frozen` to `allowed` on the theory that frozen files are checked by hash. The two
checks cover for each other and both trust a file the agent owns. The lock's
`_edad.ticket_sha256` and `red_proof` sit in the same file, so the ticket hash and the
red proof are forgeable in the same edit. `commit_iteration` (`edad/session.py:859`)
does `git add -A`, so the rewritten lock is committed — auditable in the branch diff,
but the gate is meant to be the verdict.

Nothing currently stops it. `session.preflight` runs `check_freeze` against the main
repo once (`edad/session.py:130`); every iteration thereafter is `evaluate(wt, ...)`
(`:1016`), and `check_freeze`/`approval_meta` both resolve `root / ".edad" / "hashes"`
— the worktree's copy. `allowed_tools` restricts Bash commands, not file writes; the
sandbox tier does not mount `.edad/` read-only.

The session's dirty-tree refusal (`edad/session.py:157`) uses `changed_files`, which
filters `.edad/` — so an uncommitted or modified lock is invisible to it. The worktree
is cut from HEAD: a *new* uncommitted lock is absent there (every iteration fails "no
approval lock" — confusing but safe); a *re-approved* uncommitted lock leaves the
worktree holding the old one, and the gate judges against stale hashes. That is an
existing bug, not a hypothetical.

The frozen suites for T019 and T021 fake `check_freeze(root, ticket)`,
`approval_meta(root, ticket_id)` and `changed_files(root, base_ref)` by lambda
(`tests/test_gate_refusal.py:99-101`, `tests/test_harness_identity.py:151-152`) and call
`evaluate(tmp_path, TICKET)` with no `base_ref`. Any change to those call shapes breaks
hashed tests; an additive check with a new name that is a no-op when `base_ref is None`
does not. `_pinned_versions` and `_probe_versions` are faked by the T020 frozen tests
but the new check does not need them.

A modified frozen file today lands as `freeze_ok=False` in the record and the
default-on `frozen_file_hash_mismatch` kill aborts the session naming it
(`edad/session.py:795`); a toolchain mismatch by contrast `die`s before any record
exists. The lock records the pinned names at approval in `_edad.toolchain`, so once
the lock is proven equal to base, "names at base" needs no second `git show`. The
queue subprocesses `edad.session` (`edad/session_queue.py:501`), so it inherits
`preflight`; `session_queue.py` is not in scope. All 21 locks are tracked in git; the
T021 precedent committed the lock before iteration 1 (`440475e`).

`requirements-gate.txt` at `edad/gate.py:1726` is the same shape as the lock hole — a
gate input read from the tree under judgment. Delete the pins and
`_pinned_versions` returns `[]`, `toolchain_problems([])` is `[]`, the refusal never
fires, and the record ships `toolchain: {}`. Not a regression (main had no in-evaluate
check) but the pytest-bump ticket must put that file in scope, so this closes before
that ticket is authored.

**Round 1 — mechanism (D1).** Compare-to-base, not read-from-base. A new check inside
`evaluate` (so CLI and controller cannot drift) that, when `base_ref` is set, requires
the worktree's copy of each trusted input to be byte-identical to
`git show {base}:<path>` and refuses naming the file otherwise. The existing
`check_freeze(root, ticket)` then reads a copy already proven to equal base. Every
current call shape survives, so the frozen T019/T021 stand-ins need no amendment, and
the refusal says "you edited the lock" rather than "hash mismatch". Rejected:
read-from-base (`check_freeze` reads the lock via `git show` directly) — changes
`check_freeze`'s signature or hides `base` in module state, so three hashed tests need
pre-approval amendment; wins only if legitimate in-worktree lock edits are expected,
and they are not.

**Round 1 — uncommitted lock at session start (D5, part).** Refuse. `preflight` aborts
when the main repo's lock or ticket differs from `git show HEAD:<path>` — "commit the
approval before running". Matches the T020/T021 practice; approval stays a human
commit. Rejected: the session auto-commits `.edad/hashes` and the ticket before cutting
the worktree — convenient, but the harness starts authoring commits on main.

**Round 1 — CLI path with no `base_ref` (D6).** No new record field. The record already
carries `base_ref: null`, and that is the signal that inputs were not compared to a
commit; QUICKSTART's `## Evidence` section documents it. Rejected: an
`inputs_trusted_against: base|worktree` field on `Record` — a schema change every
reader has to learn.

**Round 1 — pin removal (D3, part).** Refuse, no hatch. A name pinned at approval that
is absent now is a divergence. Values may change (a bump ticket needs that); the set of
names may only grow. Removing a pin is a human commit on main before re-approval.
Rejected: a ticket-declared `unpins:` field — escape hatches are how the T021 boundary
goes vacuous again.

**Round 2 — failure class (D4).** The freeze channel. The check's problems are appended
to `freeze_problems`, `freeze_ok=False`, the record is written naming the file, and the
existing default-on `frozen_file_hash_mismatch` kill aborts the session on the same
iteration. No new kill condition, no new `Record` field, and evidence records the
tamper. Rejected: `die` like the toolchain mismatch — a tampered run would leave no
record at all.

**Round 2 — which inputs (D2).** Enumerated: exactly the files the gate reads,
`.edad/hashes/{id}.json` and `.edad/tickets/{id}.md`, with the principle stated in the
docstring ("every input the gate trusts is compared to base") so a future input is
added deliberately. A file present in the worktree and absent at base is a divergence.
Rejected: comparing the whole `.edad/` tree — `promote_evidence` commits into
`.edad/evidence/` in the worktree, so the whole-tree rule needs exceptions from day
one.

**Round 2 — where the pinned names at base come from (D3).** The lock's own
`_edad.toolchain` keys, read through the existing `approval_meta` call in `evaluate`.
After the lock is proven equal to base, `set(toolchain_of(meta)) ⊆ set(rec.toolchain)`
is the whole check: no `git show` of `requirements-gate.txt`, no text parser for a base
blob, and the floor is tied to *approval* (what the human read) rather than to a
commit. Pre-T019 locks have no block, so `{}` is vacuous there — correct, those
tickets are done. Rejected: parsing `git show base:requirements-gate.txt` — needs
`_pinned_versions` split into a text parser and is one more thing to keep equal.

**Round 2 — frozen test layout (D7).** One new frozen file,
`tests/test_gate_trusted_inputs.py`, six cases: (a) lock rewritten to match an edited
frozen test → `freeze_ok` False naming the lock; (b) ticket rewritten in the worktree
→ named; (c) pinned name absent from the fresh measurement → named; (d)
`base_ref=None` → no git call at all (monkeypatch `git` to raise) and no problem; (e)
`preflight` refuses a lock or ticket that differs from HEAD in the main repo, and a
pinned name missing from the main repo's `requirements-gate.txt`; (f) `harness_line`
keeps a partial block's commit (D9). Red at base via T021's returning-stub pattern so
they FAIL, not ERROR. Rejected: splitting (e) into `tests/test_session_preflight.py` —
two frozen files, two locks to read.

**Round 3 — preflight runs all three (D5).** Choosing the lock's toolchain keys as the
floor means the check compares approval to now. A human who commits a pin removal on
main after approval leaves the lock and ticket equal to HEAD, so a lock/ticket-only
preflight passes and the first `evaluate` aborts the session blaming the agent. So
`preflight` runs the same function against the main repo with `base_ref="HEAD"` —
lock equals HEAD, ticket equals HEAD, lock's pinned names ⊆ the main repo's
`requirements-gate.txt` — and refuses before a worktree is cut. One function, two call
sites. Rejected: lock and ticket only at preflight, accepting the misattribution as
rare.

**Round 4 — name and shape (D8).** `trusted_input_problems(root: Path, ticket_id: str,
base_ref: str | None) -> list[str]` in `edad/gate.py`, next to `check_freeze`; returns
the list and callers decide, matching `toolchain_problems`, the sibling it most
resembles. Rejected: `check_trusted_inputs` returning `(ok, problems)`.

**Round 4 — wording (D8).** Three specific messages: lock —
`approval lock modified since {base}: .edad/hashes/{id}.json (the harness's record of what was approved is not the agent's to edit)`;
ticket — `ticket modified since {base}: .edad/tickets/{id}.md (re-approve to adopt the change)`;
pin — `pinned name dropped since approval: {name} (requirements-gate.txt at approval pinned it; removing a pin is a human commit before re-approval)`.
`preflight` prefixes its refusal with `contract drifted since HEAD; re-approve:`.
Rejected: one generic `trusted input differs from {base}: <path>`.

**Round 4 — `base_ref=None` skips everything (D8).** Including the pin check, which
needs no git and could run. One rule — no base, no comparison — matching D6's
`base_ref: null` semantics; a human running the gate by hand is not the threat.
Rejected: running the pin floor unconditionally — two rules in one function.

**Round 4 — cosmetics (D9).** `harness_line` is fixed in this ticket: for
`source == "unknown"` it prints `unknown` plus the short commit and `dirty` when the
block carries them, honouring what `harness_of` deliberately preserves (the frozen D3
test of T020 asserts the preservation; no reader honoured it). `toolchain_line` is left
alone: D3 makes a post-approval `{}` impossible for a locked ticket, so `unknown` is
accurate for every record that can still carry it. Rejected: neither — both to a
notes file.

**Round 5 — re-grilled at `/to-tickets` (2026-09-14): the no-base case cannot be a
red proof.** The frozen file was authored and every `verify` probed at base. Eight of
the nine named node ids FAIL on their intended assertion with no stubs: the tamper
cases on `freeze_ok is False`, preflight on `DID NOT RAISE`, QUICKSTART on the missing
field, `harness_line` on the missing commit. `test_no_base_ref_makes_no_git_call_and_no_problem`
is green at base by nature — "no `git show` when `base_ref` is None" is already true
before the work exists — and `approve`'s per-command rule (`edad/gate.py:1168`)
refuses any pytest acceptance command that produces no FAILED in the frozen file. So
it is removed from D1's and D8's `verify` lists and stays in the frozen file as a
regression guard, run by `full_gate`'s `python3 -m pytest -q`. The same holds for a
second guard added while authoring, `test_a_changed_pin_value_is_not_a_divergence`
(D3: values may change) — green at base, in the file, not in `acceptance`. D1 keeps
the lock-tamper command; D8 keeps the wording command. Also found while authoring:
`evaluate` already runs `git rev-parse HEAD` for the record's `commit`, so "no git
call" in D1/D8 means no `git show` by the check — the guard asserts exactly that.

**Scope.** `edad/gate.py` (the function, its call in `evaluate`, `harness_line`),
`edad/session.py` (`preflight`), `QUICKSTART.md` (`## Evidence`),
`tests/test_gate_trusted_inputs.py` (frozen). Not `edad/session_queue.py`; not the
T019/T021 frozen files.

**Migration and rollback.** Additive; no on-disk record or lock changes shape. Old
records are unaffected. Rollback is removing the call from `evaluate` and `preflight`.
Workflow cost: re-approval and its commit become a hard prerequisite for a session
rather than a courtesy; preflight says so.

**Explicitly out of scope — a separate ticket, not to be lost.** The agent's worktree
also contains `edad/gate.py` itself, in scope for tickets in this repo. Which copy of
the gate judges the worktree is an import-resolution question (the editable-install /
worktree trap), not a file-read one, and collides with how `python3 -m pytest` resolves
`edad` inside `wt`. Same principle ("the gate's trusted inputs come from base"),
different mechanism. Ticket it after this one lands.

**Ordering.** This ticket comes before the pytest 9.0.3 bump, which is the first
ticket to put `requirements-gate.txt` in scope.

**Deferred.** None costly. Exact test function names inside the frozen file (the
`-k` selectors below are the intended names); kill-condition numbers for the ticket.

## Decisions

```yaml
decisions:
  - id: D1
    decision: "Compare-to-base: evaluate() calls a new additive check that, when base_ref is set, requires the worktree's copy of each trusted input to be byte-identical to `git show {base}:<path>`; check_freeze, approval_meta and changed_files keep their signatures and call shapes; base_ref None is a no-op with no git call"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_lock_rewritten_to_match_an_edited_frozen_test_is_refused -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    rejected: read-from-base (check_freeze reads the lock via git show) — changes a call shape three hashed stand-ins pin, and the refusal reads as a hash mismatch rather than an edited lock
  - id: D2
    decision: "The trusted inputs are enumerated by path — .edad/hashes/{id}.json and .edad/tickets/{id}.md — with the principle stated in the docstring; a file present in the worktree and absent at base is a divergence"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_lock_rewritten_to_match_an_edited_frozen_test_is_refused -q
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_ticket_rewritten_in_the_worktree_is_refused -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    rejected: diffing the whole .edad/ tree against base — promote_evidence commits into .edad/evidence/ in the worktree, so the rule needs exceptions from day one
  - id: D3
    decision: "Pin floor: every key of the lock's _edad.toolchain (read via the existing approval_meta call) must be a key of the fresh measurement; values may change, names may not disappear; no ticket-level escape hatch; an absent block is vacuous"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_pinned_name_dropped_since_approval_is_refused -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    rejected: parsing `git show base:requirements-gate.txt` — a second parser and a floor tied to a commit rather than to what the approver read; a ticket-declared `unpins:` field — hatches are how the T021 boundary goes vacuous again
  - id: D4
    decision: "A diverged trusted input rides the freeze channel: problems appended to freeze_problems, freeze_ok=False, the record written naming the file, and the existing default-on frozen_file_hash_mismatch kill aborts the session; no new kill condition, no new Record field"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_divergence_is_a_freeze_failure_in_the_record_not_a_die -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    rejected: die() before the Record exists, like the toolchain mismatch — a tampered run would leave no evidence
  - id: D5
    decision: "session.preflight calls the same function against the main repo with base_ref=\"HEAD\" — lock equals HEAD, ticket equals HEAD, lock's pinned names ⊆ the main repo's requirements-gate.txt — and aborts with `contract drifted since HEAD; re-approve:` before cutting a worktree"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_preflight_refuses_an_uncommitted_or_drifted_contract -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/session.py
    rejected: auto-committing the lock and ticket at session start — the harness would author commits on main; lock and ticket only at preflight — a human's post-approval pin removal would surface mid-session as an agent violation
  - id: D6
    decision: "No Record schema change; base_ref null is the signal that inputs were not compared to a commit, and QUICKSTART's `## Evidence` section says so"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_quickstart_evidence_section_explains_null_base_ref -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - QUICKSTART.md
    rejected: an `inputs_trusted_against` field on Record — a schema change every reader must learn
  - id: D7
    decision: "One frozen file, tests/test_gate_trusted_inputs.py, six cases (lock tamper, ticket tamper, pin dropped, no base_ref, preflight refusal, harness_line partial commit), red at base through returning stubs so they FAIL rather than ERROR"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - tests/test_gate_trusted_inputs.py
    rejected: a separate tests/test_session_preflight.py for the preflight case — two frozen files, two locks to read
  - id: D8
    decision: "trusted_input_problems(root: Path, ticket_id: str, base_ref: str | None) -> list[str] in edad/gate.py beside check_freeze; three specific messages — `approval lock modified since {base}: .edad/hashes/{id}.json (the harness's record of what was approved is not the agent's to edit)`, `ticket modified since {base}: .edad/tickets/{id}.md (re-approve to adopt the change)`, `pinned name dropped since approval: {name} (requirements-gate.txt at approval pinned it; removing a pin is a human commit before re-approval)`; base_ref None skips the whole check including the pin floor"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_refusal_wording_names_the_file_and_who_may_change_it -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    rejected: "check_trusted_inputs returning (ok, problems); one generic `trusted input differs from {base}: <path>` message; running the pin floor when base_ref is None — two rules in one function"
  - id: D9
    decision: "harness_line prints `unknown` plus the short commit and `dirty` when a source-unknown block carries them, honouring what harness_of preserves; toolchain_line is left unchanged"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_harness_line_keeps_a_partial_blocks_commit -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    rejected: leaving both lines alone — harness_of's preservation had no reader honouring it; changing toolchain_line — D3 makes a post-approval {} impossible for a locked ticket, so `unknown` stays accurate
deferred:
  - exact test function names inside tests/test_gate_trusted_inputs.py (the selectors above are the intended names)
  - kill-condition numbers for the ticket
  - two green-at-base guards live in the frozen file but not in acceptance (no-base makes no git show; a changed pin value is not a divergence); full_gate runs them
  - SEPARATE TICKET, not deferred within this one — which copy of edad/gate.py judges the worktree (import resolution; editable-install/worktree trap); ticket it after this lands
```
