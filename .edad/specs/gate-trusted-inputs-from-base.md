---
slug: gate-trusted-inputs-from-base
grilled: .edad/grills/gate-trusted-inputs-from-base.md
status: draft
---

## Problem statement

The gate's tamper defence is a fingerprint comparison: `approve` writes a lock holding
the hash of every frozen test and of the ticket itself, and every run re-hashes those
files against the lock. But the lock is read from the same worktree the agent writes
to, and `.edad/` is exempt from the scope check because it holds "the harness's own
records". So an agent can edit a frozen test, rewrite the hash in the lock to match,
and pass both checks: the freeze check sees matching fingerprints, and the scope check
never looks under `.edad/`. This was demonstrated at HEAD in three lines. The ticket's
hash and the red proof live in the same lock, so they are forgeable in the same edit.

Two smaller holes have the same shape. `evaluate` reads the pinned toolchain from the
worktree's `requirements-gate.txt`; strip the pins and the T021 refusal is vacuous, the
evidence shipping `toolchain: {}`. And re-approving a ticket without committing the new
lock leaves the worktree — which is cut from HEAD — holding the old lock, so the gate
judges against stale fingerprints and nothing says so.

The pytest 9.0.3 bump is the first ticket that must put `requirements-gate.txt` in
scope; it walks straight into the second hole.

## Solution

The gate stops trusting the worktree's copy of anything it uses to judge the
worktree. When it knows the commit the session started from, it requires the lock and
the ticket in the worktree to be byte-identical to that commit's versions, and it
requires every tool pinned at approval to still be pinned. A divergence is reported
through the existing freeze channel — the record names the file, the existing
frozen-file kill aborts the session — so a tampered run leaves evidence saying what
was tampered rather than no evidence at all.

The same check runs before a session starts, against the main repo's HEAD, refusing
"the contract drifted, re-approve" — which catches the forgot-to-commit case and a
human's post-approval pin removal up front, before an agent can be blamed for either.

Legitimate change is routed through re-approval, which already exists: edit the test
or the ticket on main, `approve`, commit the lock, run. Pin *values* may change inside
a ticket; pin *names* may only be removed by a human commit before re-approval. Where
no base commit is given — a human running the gate by hand — nothing is compared,
and the record's `base_ref: null` says so.

## User stories

1. As the operator, I want an agent that edits a frozen test and its lock to be
   refused and the refusal recorded, so that the approval lock means what it says.
2. As the operator, I want an agent that rewrites its ticket in the worktree to be
   refused naming the ticket, so that scope, acceptance and kill conditions stay the
   contract a human approved.
3. As the operator running the pytest bump, I want to change a pinned version inside a
   ticket without being refused, so that the pin floor does not block the work it was
   designed to protect.
4. As the operator, I want an agent that removes a pinned tool to be refused, so that
   the toolchain check cannot be made vacuous from inside a ticket.
5. As the operator, I want a session to refuse to start when the lock or ticket I
   re-approved is not committed, so that the gate never silently judges against a stale
   lock.
6. As the operator, I want a session to refuse to start when a pin was removed on main
   after approval, so that the first iteration is not aborted blaming the agent for my
   change.
7. As a reader of an evidence record, I want a tamper to appear as a freeze failure
   naming the file, so that the record explains the abort without reading the session
   log.
8. As a human running the gate by hand with no base commit, I want no comparison and
   no git call, and I want the record's `base_ref: null` documented as meaning exactly
   that, so that a hand run is neither refused nor mistaken for a controller run.
9. As the maintainer of earlier tickets, I want the frozen T019 and T021 tests left
   untouched, so that this change does not re-open sealed contracts.
10. As a reader of `report()`, I want a harness block that recorded a commit but no
    source to still show that commit, so that what `harness_of` preserves is what the
    line prints.

## Seams

All four exist today. No new seam is introduced.

- **S1 — `evaluate` → `Record`.**
  **Where**: `rec.freeze_ok` and the text of `rec.violations` after `evaluate(wt,
  ticket, base_ref=<sha>)` against a real temporary git repository holding a committed
  lock, ticket and frozen test (the `git_repo` pattern in the mutation tests); for the
  no-base case, `gate.git` monkeypatched to raise and `evaluate(tmp_path, TICKET)`.
  **Exists**: yes.
  **Observes**: a rewritten lock, a rewritten ticket, or a dropped pinned name reaching
  the record as a freeze failure with the exact wording; that no git command runs and no
  problem is raised when `base_ref` is `None`; that the outcome is a record, not a `die`.
  **Discharges**: D1, D2, D3, D4, D8.

- **S2 — `preflight` → `Abort`.**
  **Where**: `session.preflight(root, ticket, "host", dry_run=True)` in a temporary
  repository, with the toolchain check faked and `ANTHROPIC_API_KEY` unset, raising
  `Abort` whose message starts `contract drifted since HEAD; re-approve:`.
  **Exists**: yes.
  **Observes**: refusal before any worktree exists, for a lock or ticket that differs
  from HEAD and for a pinned name missing from the main repo's pin file.
  **Discharges**: D5.

- **S3 — `report()` stdout.**
  **Where**: the `harness` line of `report(rec)`, read through the T020 `report_line`
  helper.
  **Exists**: yes.
  **Observes**: a source-unknown block's commit and dirty flag surviving to the printed
  line.
  **Discharges**: D9.

- **S4 — `QUICKSTART.md` text.**
  **Where**: a regex over the `## Evidence` section, in the T020 D7 style.
  **Exists**: yes.
  **Observes**: the sentence explaining a null `base_ref`.
  **Discharges**: D6.

D7 — the frozen file as a whole, red at base — is discharged by running the file; it
attaches to every seam above and needs none of its own. No decision lacks a seam.

Not added: a function-level seam on the new function's return value. S1 sees the same
wording through the record, and a fifth seam would only put one more name into the
frozen file for the implementer to be pinned to.

## Implementation decisions

**One new function, two call sites.** A trusted-input check lives in the gate module
beside the freeze check and returns a list of problems, in the shape of the toolchain
problem reader it most resembles. `evaluate` calls it when it has a base commit and
appends its problems to the freeze problems — so `freeze_ok` goes false, the record
carries the message, and the session's existing frozen-file kill condition aborts the
run. No new kill condition, no new record field, no new failure class. The session's
preflight calls the same function against the main repo with HEAD as the base and
turns any problem into an abort with a "re-approve" prefix.

**Compare, don't relocate.** The lock and ticket stay where they are and keep being
read by the functions that read them today. The new check proves the worktree's copy
equals the base commit's copy before those readers run. This keeps every existing
call shape — which matters because the frozen T019 and T021 suites fake the freeze
check, the approval-meta reader and the changed-files reader by lambda, and any
signature change would break hashed tests. A file present in the worktree and absent
at base is a divergence, not a pass.

**The trusted inputs are enumerated.** Exactly the files the gate reads to judge: the
approval lock and the ticket. The docstring states the principle so a future input is
added deliberately. The whole `.edad/` tree is not compared, because evidence
promotion legitimately commits into it from inside the worktree.

**The pin floor comes from the lock.** The lock already records, at approval, the
names of every pinned tool. Once the lock is proven equal to base, the floor is: every
name in the lock's toolchain block must be a name in the fresh measurement. Values are
free to change — the bump ticket needs that. Names may not vanish. There is no
ticket-level escape hatch; removing a pin is a human commit before re-approval. A lock
from before toolchain recording has no block and the floor is vacuous, which is right:
those tickets are done.

**No base, no comparison.** When `evaluate` has no base commit — the human CLI path —
the check is skipped entirely, pins included, and makes no git call. The record's
existing `base_ref: null` is the signal; QUICKSTART's evidence section says what it
means. The record schema does not change.

**Wording.** Three specific messages, one per input, each naming the file and who may
change it; the preflight prefixes its refusal so the reader knows it happened before
the run, not during it. The messages are fixed in the decisions block.

**One cosmetic fix rides along.** The printed harness line now honours what the
harness reader deliberately preserves: a block with a commit but no source prints
`unknown` plus the short commit and the dirty flag. The toolchain line is left alone —
after this change a locked ticket cannot produce an empty toolchain block, so `unknown`
is accurate for every record that can still carry one.

**Migration and rollback.** Additive. No record or lock changes shape; old records are
unaffected. Rollback is removing two calls. The workflow cost is that re-approval and
its commit become a hard prerequisite for a session rather than a courtesy, and the
preflight says so.

**Ordering.** This lands before the pytest 9.0.3 bump.

## Out of scope

- **Which copy of the gate's own source judges the worktree.** The worktree contains
  `edad/gate.py`, in scope for tickets in this repo; which copy runs is an
  import-resolution question, not a file-read one, and collides with the
  editable-install / worktree trap. Same principle, different mechanism. **Separate
  ticket, after this one lands — flagged by the user as not to be lost.**
- The session queue. It launches sessions by subprocess and inherits preflight.
- The frozen T019 and T021 test files. Untouched by construction (D1).
- The toolchain line's `unknown` for an empty block (D9 rejects changing it).
- Making `.edad/` read-only in the sandbox, or moving locks out of the repo — both
  rejected in the grill in favour of comparing to base.

## Further notes

**Red at base without stubs — probed.** The frozen file was authored at
`/to-tickets` and every `verify` run at base: all eight acceptance node ids FAIL on
their intended assertion, none ERRORs, so no stub is needed. Two guards in the file
are green at base by nature — no `git show` when there is no base; a changed pin
*value* is not a divergence — and so cannot be red proofs. They are not in
`acceptance`; `full_gate` runs them. The grill's round 5 records the amendment to D1
and D8.

**Deferred from the grill, all cheap:** the exact test function names inside the
frozen file (the node ids in the decisions block are the intended names); kill-condition
numbers for the ticket.

**Nothing needs re-grilling.** The narrative above introduces no decision the grill did
not settle.

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
    seam: S1
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
    seam: S1
    rejected: diffing the whole .edad/ tree against base — promote_evidence commits into .edad/evidence/ in the worktree, so the rule needs exceptions from day one
  - id: D3
    decision: "Pin floor: every key of the lock's _edad.toolchain (read via the existing approval_meta call) must be a key of the fresh measurement; values may change, names may not disappear; no ticket-level escape hatch; an absent block is vacuous"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_pinned_name_dropped_since_approval_is_refused -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    seam: S1
    rejected: parsing `git show base:requirements-gate.txt` — a second parser and a floor tied to a commit rather than to what the approver read; a ticket-declared `unpins:` field — hatches are how the T021 boundary goes vacuous again
  - id: D4
    decision: "A diverged trusted input rides the freeze channel: problems appended to freeze_problems, freeze_ok=False, the record written naming the file, and the existing default-on frozen_file_hash_mismatch kill aborts the session; no new kill condition, no new Record field"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_divergence_is_a_freeze_failure_in_the_record_not_a_die -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    seam: S1
    rejected: die() before the Record exists, like the toolchain mismatch — a tampered run would leave no evidence
  - id: D5
    decision: "session.preflight calls the same function against the main repo with base_ref=\"HEAD\" — lock equals HEAD, ticket equals HEAD, lock's pinned names ⊆ the main repo's requirements-gate.txt — and aborts with `contract drifted since HEAD; re-approve:` before cutting a worktree"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_preflight_refuses_an_uncommitted_or_drifted_contract -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/session.py
    seam: S2
    rejected: auto-committing the lock and ticket at session start — the harness would author commits on main; lock and ticket only at preflight — a human's post-approval pin removal would surface mid-session as an agent violation
  - id: D6
    decision: "No Record schema change; base_ref null is the signal that inputs were not compared to a commit, and QUICKSTART's `## Evidence` section says so"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_quickstart_evidence_section_explains_null_base_ref -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - QUICKSTART.md
    seam: S4
    rejected: an `inputs_trusted_against` field on Record — a schema change every reader must learn
  - id: D7
    decision: "One frozen file, tests/test_gate_trusted_inputs.py, six cases (lock tamper, ticket tamper, pin dropped, no base_ref, preflight refusal, harness_line partial commit), red at base through returning stubs so they FAIL rather than ERROR"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - tests/test_gate_trusted_inputs.py
    seam: S1, S2, S3, S4
    rejected: a separate tests/test_session_preflight.py for the preflight case — two frozen files, two locks to read
  - id: D8
    decision: "trusted_input_problems(root: Path, ticket_id: str, base_ref: str | None) -> list[str] in edad/gate.py beside check_freeze; three specific messages — `approval lock modified since {base}: .edad/hashes/{id}.json (the harness's record of what was approved is not the agent's to edit)`, `ticket modified since {base}: .edad/tickets/{id}.md (re-approve to adopt the change)`, `pinned name dropped since approval: {name} (requirements-gate.txt at approval pinned it; removing a pin is a human commit before re-approval)`; base_ref None skips the whole check including the pin floor"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_refusal_wording_names_the_file_and_who_may_change_it -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    seam: S1
    rejected: "check_trusted_inputs returning (ok, problems); one generic `trusted input differs from {base}: <path>` message; running the pin floor when base_ref is None — two rules in one function"
  - id: D9
    decision: "harness_line prints `unknown` plus the short commit and `dirty` when a source-unknown block carries them, honouring what harness_of preserves; toolchain_line is left unchanged"
    verify:
      - python3 -m pytest tests/test_gate_trusted_inputs.py::test_harness_line_keeps_a_partial_blocks_commit -q
    frozen:
      - tests/test_gate_trusted_inputs.py
    scope:
      - edad/gate.py
    seam: S3
    rejected: leaving both lines alone — harness_of's preservation had no reader honouring it; changing toolchain_line — D3 makes a post-approval {} impossible for a locked ticket, so `unknown` stays accurate
deferred:
  - exact test function names inside tests/test_gate_trusted_inputs.py (the selectors above are the intended names)
  - kill-condition numbers for the ticket
  - two green-at-base guards live in the frozen file but not in acceptance (no-base makes no git show; a changed pin value is not a divergence); full_gate runs them
  - SEPARATE TICKET, not deferred within this one — which copy of edad/gate.py judges the worktree (import resolution; editable-install/worktree trap); ticket it after this lands
```
