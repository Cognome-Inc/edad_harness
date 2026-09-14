---
slug: toolchain-measurement
grilled_at: 2026-09-14
---

## Record

Grilled 2026-09-14 on `Cognome-Inc/edad_harness` @ `631ff65` (PR #2 / T018 merged as
`c94b061`; PR #3 carrying T019 open, reviewer manuelwahle; `v0.1.0` local placeholder,
unpushed). Handed on from `/review-branch T019`: two follow-ups the advisory review
named as worth tickets after merge — a shared toolchain probe, and readers for the
`harness`/`toolchain` blocks T019 added.

Facts established before the interview, by reading rather than asking. The only
process that calls both `gate_toolchain_problems` and `toolchain_versions` is
`cmd_approve` (`edad/gate.py:1535`, `:1597`) — that is where every pinned name is
probed twice. `session.preflight` (`edad/session.py:111`) needs only problems;
`evaluate` (`edad/gate.py:1631`) needs only versions. `evaluate` never runs the pin
check: nothing between `:1611` and `:1632` refuses a mismatch, so a hand-run
`python3 -m edad.gate run T0NN` on the wrong pytest writes a record that names the
wrong version and never says it was wrong. The `toolchain_versions` docstring claims
"the same `_probe_versions` call" as the check; it is not. Nothing reads `harness` or
`toolchain` today — not `report()`, not `.claude/skills/next/survey.py` (which does not
import `edad`), not the queue. Three on-disk shapes exist: absent (T001–T018 records,
all 19 locks), `{}` (`.edad/evidence/T019.json`, written by the pre-T019 harness through
`Record`'s default fields), and the four-key block (everything after). The frozen D3
test (`tests/test_harness_identity.py:169`) pins `toolchain_versions(root)` making one
`_probe_versions` call per pinned name in file order and `gate_toolchain_problems(root)`
keeping its signature and messages. The frozen D4 tests (`:206`, `:230`) steer
`evaluate` and `cmd_approve` by monkeypatching `toolchain_versions` and
`gate_toolchain_problems` on the `gate` module; `tests/test_gate_red_proof.py` (not
frozen) does the same for approve. `toolchain == {}` remains a legitimate post-change
value: a target with no `requirements-gate.txt` measures nothing.

**Round 1 — what the record's `toolchain` block claims (D1).** Measured *and* checked.
`evaluate` takes one measurement, refuses a mismatch with the same `die()` message
`cmd_approve` uses, before running any command and before building the `Record`; the
record's block is that measurement. The record then means "these pins were satisfied
when this verdict was made", which is what T019's `requirements-gate.txt` header
already asserts. Cost accepted: a hand-run gate on a wrong toolchain now dies instead
of writing a record — consistent with approve and preflight. Rejected: measured only,
docstring made honest — cheaper, but the record keeps meaning "what a probe saw" and a
mismatched hand run still writes evidence. Rejected: recording the mismatch as a
violation so `passed=False` — a FAIL record for a toolchain problem is exactly what
preflight exists to keep away from the agent.

**Round 1 — shape of the shared pass (D2).** A `Measurement` dataclass
(`name`, `pinned`, `meta`, `on_path`) and `measure_toolchain(root) ->
list[Measurement]`: the one file pass and one `_probe_versions` call per name, `[]` when
the pins file is absent. Two pure readers: `toolchain_problems(measurements) ->
list[str]` (the check, messages unchanged) and `versions_of(measurements) -> dict`.
`gate_toolchain_problems(root)` and `toolchain_versions(root)` stay as one-line
wrappers so `session.preflight` and the frozen D3 test are untouched. `evaluate` and
`cmd_approve` call `measure_toolchain` once and both readers. Rejected: memoising
`_probe_versions` per command — invisible state the frozen test cannot count, and
"same measurement" becomes a property of cache lifetime. Rejected: one
`check_toolchain(root) -> (problems, versions)` — the wrappers become Middle Men and
the tuple is a Data Clump.

**Round 1 — the reader rule (D3).** One normalising reader that never writes.
`harness_of(artifact: dict) -> dict` returns exactly `{version, commit, dirty,
source}`; `toolchain_of(artifact: dict) -> dict`. Normalising on read is not
backfilling: nothing on disk is touched, T019's `{}` stays `{}`. Rejected: document
only — the rule is re-derived per reader and `{}` is the shape a reader gets wrong.
Rejected: treating `{}` as an error — wrong for T019.json, which is legitimately `{}`
and must not be edited.

**Round 1 — packaging.** One ticket, `blocked_by: [T019]`, frozen file
`tests/test_harness_identity.py` amended pre-approval (the D3 test's docstring becomes
true; D4 tests re-seamed; new tests land beside them). T019's lock is historical;
re-freezing the file under the new ticket is the normal path, as T019 did to
`tests/test_session_queue.py`. Rejected: a new frozen file, leaving the T019 file
byte-identical — the D3 docstring would stay false in the file that describes the
behaviour. Rejected: two tickets — they share a file and a test file, so they
serialise anyway; two approvals and two nights for ~150 lines.

**Round 2 — the patch seam moves (D4).** `measure_toolchain` is the one module-level
name a test fakes to steer both `evaluate` and `cmd_approve`. The frozen D4 tests are
amended pre-approval to patch it with a list of `Measurement`s. The inert patches in
`tests/test_gate_red_proof.py` are left alone: the file is out of scope, and they pass
regardless because `tmp_path` has no pins file. Rejected: keeping the wrappers as the
seam with a per-root cache underneath — the round-1 cache option by another name.

**Round 2 — `harness_of` on every shape (D3, detail).** No key, `{}`, or a non-dict →
all `None` with `source: "unknown"`. A dict that has `source` → keep what is there,
missing keys become `None`. Never raises. `toolchain_of` → the value if it is a dict,
else `{}`. Rejected: anything not the exact four-key block → unknown — a lock with
three of four keys loses the commit it did record. Rejected: partial dict raises —
contradicts "never an error" for readers of on-disk artifacts.

**Round 2 — what is printed (D5, D6).** `report()` gains two lines after `decisions`:
`harness   <source> <commit[:8]>[ dirty][ v<version>]` or `harness   unknown`, and
`toolchain <name> <ver>, ...` or `toolchain unknown`, both through the readers.
`cmd_approve` prints the same harness line after the frozen-file hashes (D6,
unenforced — approve's stdout has no test seam today). Rejected: `report()` only —
the operator reading approve's output has no other way to learn who measured the red
proof. Rejected: harness line only — the toolchain line is what makes the pytest bump
visible when it lands.

**Round 2 — scope beyond `gate.py` (D7–D10).** QUICKSTART `## Evidence` names the
`harness` and `toolchain` fields (D7, enforced by a grep test in D6's style). Three
unenforced doc edits the agent is asked for by name: the `_edad` key list in
`.claude/skills/review-branch/SKILL.md` gains `harness` and `toolchain` (D8);
`harness_dirty` gets the reason for `--untracked-files=no` (D9, in `gate.py`); the
`RunState` docstring in `edad/session_queue.py` gains a sentence on `harness` (D10).
Rejected: `gate.py` + QUICKSTART only, docstrings by hand — two hand commits for two
sentences. Rejected: code only.

**Round 3 — D6 re-grilled at `/to-spec` (2026-09-14).** The reason recorded for
leaving D6 unenforced — "approve's stdout has no test seam today" — was false when
written: the red-proof tests already read `cmd_approve`'s stderr through `capsys`, and
the frozen D4 lock test already drives `cmd_approve` end to end from an
`argparse.Namespace`, so its stdout is one `readouterr().out` away. With the mechanism
free, the only honest alternatives were "enforce it" or "one printed line is not
worth a frozen test". Enforced: the grill's own rejection of `report()`-only says the
operator has no other way to learn who measured the red proof, and a behaviour valued
that highly and pinned that cheaply should be pinned. `test_approve_prints_the_harness_line`
lands in the same frozen file, driven exactly as the D4 lock test is. Rejected:
unenforced with the corrected reason — legitimate, but it leaves the one line an
operator reads at approval as the one line nothing checks.

**Round 3 — D2's first `verify` command re-grilled after the probe (2026-09-14).**
The grill named T019's D3 test (`test_toolchain_versions_stores_what_the_pin_check_measures`)
as D2's first acceptance command. The probe showed it green at base — the wrappers
already behave as it asserts, and only its docstring changes — and `cmd_approve` proves
red or mutation for a whole ticket, never per command, so that one green command would
refuse approval of the ticket. Replaced by a new test under the same `_probe_versions`
seam, `test_measure_toolchain_probes_each_pin_once_in_file_order`, which asserts the
`Measurement` list, the probe order, both readers and the `[]` case, and is red at base
on its own assertion. The T019 test stays in the file with its docstring corrected,
proven by T019's lock and run by this ticket's `full_gate`. Rejected: adding the new
assertions to the T019 test — changing what a proven test asserts is a different act
from amending its stand-ins. Rejected: `--allow-passing` — that flag is for
re-approving an implemented ticket and would skip the red proof for all ten commands.

**Round 3 — a non-empty `harness` dict without `source` (D3, detail).** Round 2 named
"no key, `{}`, non-dict" and "a dict that has `source`" and nothing between. Decided:
a dict keeps whatever of the four keys it has and `source` defaults to `"unknown"` —
the rule is one `.get` per key, `{}` falls out of it rather than being a case, and a
commit that was recorded is never dropped, which is the same ground round 2 gave for
partial blocks. No harness since T019 writes a block without `source`, so this shape is
a hand edit or a foreign writer, and a reader that keeps the value can still say it
does not know how to interpret it. Rejected: sourceless → all unknown — `source` says
which fields to believe, but "I do not know how to read this commit" is not "there
was no commit".

**Probe, 2026-09-14 (measured, in a detached worktree at `905c8f5`; nothing committed).**
The "would ERROR, not FAIL" forecast below was wrong: the file reaches every new name
as `gate.<name>` inside a test body, so a missing name is an `AttributeError` in the
body, which pytest reports as FAILED. The stubs are still required, for the deeper
reason: without them 8 of the 9 reds were that `AttributeError` — a red that proves the
test reached the code, not that it asserts anything. With returning stubs
(`measure_toolchain` → `[]`, `toolchain_problems` → `[]`, `versions_of` → `{}`,
`harness_of`/`toolchain_of` → `{}`, the dataclass itself) all ten commands fail on their
own assertion — nine `AssertionError`s and, for the refuse test, the `RuntimeError` its
`boom` stand-in raises when base `evaluate` gathers identity before checking, which is
the behaviour that test exists to catch. The rest of the suite stays green at both
states (230 passed). Against a correct implementation all ten pass, the suite is 240
green, `ruff check .` is clean, and the scope diff is 171 numstat lines (139+/32−)
including the stubs — within `max_diff_lines: 300`. Stand-ins amended: the two D4
tests now fake `measure_toolchain`; the T019 D3 docstring is corrected; setup shared by
the approve-driving tests was extracted into `write_ticket`/`approve_fakes`/
`evaluate_fakes` helpers with the T019 assertions unchanged.

**Consequences recorded, not asked.** Red at base: `Measurement`, `measure_toolchain`,
`toolchain_problems`, `versions_of`, `harness_of`, `toolchain_of` do not exist at base,
so their tests would ERROR, not FAIL; returning stubs land before approval as T019's
did (`measure_toolchain` → `[]`, readers → `[]`/`{}`, `harness_of`/`toolchain_of` →
`{}`; the dataclass is its own stub). The amended D4 tests patch `measure_toolchain`,
which base `evaluate` does not call, so they fail on `rec.toolchain != TOOLCHAIN` — a
real FAILED. The refuse test fails at base because `evaluate` returns a record instead
of raising. Interaction with the pytest bump: once `evaluate` refuses a mismatch, a
ticket that bumps a pin makes the in-container agent's own gate run die (the image was
built on the old pin) — the agent sees a refusal, not a FAIL. Preflight already has
this property on the host; the bump ticket owns the rollout.

**Deferred, all cheap to reverse.** Exact `report()` line formatting; `Measurement`
field names and whether `measured` is a property; the `evaluate` die message wording
(reuse approve's verbatim); cleaning the inert patches in `test_gate_red_proof.py`;
kill-condition numbers (`max_diff_lines: 300` against an estimate of ~150); whether
`.claude/skills/next/survey.py` should ever print harness identity (it does not import
`edad`; the `/next` skill shows pipeline state, not provenance).

## Decisions

```yaml
decisions:
  - id: D1
    decision: "evaluate() measures the toolchain once, refuses a mismatch with approve's die() message before running any command or building the Record, and the record's toolchain block is that same measurement"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_evaluate_measures_the_toolchain_once_and_records_it -q
      - python3 -m pytest tests/test_harness_identity.py::test_evaluate_refuses_a_toolchain_mismatch_before_running_anything -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: measured only with an honest docstring — the record keeps meaning "what a probe saw" and a mismatched hand run still writes evidence; mismatch recorded as a violation with passed=False — a FAIL record for a toolchain problem is what preflight exists to keep from the agent
  - id: D2
    decision: "Measurement(name, pinned, meta, on_path); measure_toolchain(root) -> list[Measurement] is the one file pass and one _probe_versions call per name, [] when the pins file is absent; toolchain_problems(measurements) and versions_of(measurements) are pure readers with the check's messages unchanged; gate_toolchain_problems(root) and toolchain_versions(root) remain as one-line wrappers; cmd_approve measures once for both the check and the lock"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_measure_toolchain_probes_each_pin_once_in_file_order -q
      - python3 -m pytest tests/test_harness_identity.py::test_approve_measures_the_toolchain_once_for_check_and_lock -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: memoising _probe_versions per command — invisible state the frozen test cannot count; one check_toolchain(root) -> (problems, versions) — the wrappers become Middle Men and the tuple a Data Clump
  - id: D3
    decision: "harness_of(artifact) -> exactly {version, commit, dirty, source}: absent key, {} or non-dict -> all None with source unknown; a dict keeps the values it has for those four keys, missing keys become None and a missing source becomes unknown; never raises, never writes. toolchain_of(artifact) -> the value if a dict, else {}"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_harness_of_reads_absent_empty_partial_and_full_blocks_as_one_shape -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: document only — the rule is re-derived per reader and {} is the shape a reader gets wrong; {} as an error — wrong for T019.json, which is legitimately {} and must not be edited; anything short of the exact block -> unknown — a lock with three of four keys loses the commit it recorded; a sourceless dict -> all unknown — not knowing how to read a commit is not the same as there being none
  - id: D4
    decision: "measure_toolchain is the module-level seam a test fakes to steer both evaluate and cmd_approve; the frozen D4 tests are amended pre-approval to patch it with a list of Measurements; tests/test_gate_red_proof.py is left untouched"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_the_written_record_carries_harness_and_toolchain -q
      - python3 -m pytest tests/test_harness_identity.py::test_the_lock_records_harness_and_toolchain_at_approval -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: keeping the wrappers as the seam with a per-root cache underneath — the D2 cache option by another name
  - id: D5
    decision: "report() prints, after decisions, a harness line (<source> <commit[:8]>[ dirty][ v<version>], or unknown) and a toolchain line (<name> <ver>, ..., or unknown), both through harness_of/toolchain_of"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_report_prints_the_harness_and_toolchain_lines -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: harness line only — the toolchain line is what makes a pin bump visible when it lands
  - id: D6
    decision: "cmd_approve prints the same harness line after the frozen-file hashes"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_approve_prints_the_harness_line -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: report() only — the operator reading approve's output has no other way to learn who measured the red proof; unenforced with the corrected reason ("one line is not worth a frozen test") — leaves the one line an operator reads at approval as the one line nothing checks
  - id: D7
    decision: "QUICKSTART's ## Evidence section names the record's harness and toolchain fields"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_quickstart_evidence_section_names_harness_and_toolchain -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - QUICKSTART.md
    rejected: leaving it to the Releasing section, which refers to an identity block nothing earlier introduces
  - id: D8
    decision: "the _edad key list in .claude/skills/review-branch/SKILL.md gains harness and toolchain"
    unenforced: a prompt file; nothing executes it
    scope:
      - .claude/skills/review-branch/SKILL.md
    rejected: fixing by hand outside the pipeline — a hand commit for one line the ticket's agent is already in the tree for
  - id: D9
    decision: "harness_dirty carries the reason for --untracked-files=no (an untracked file changes behaviour only if something imports it; counting untracked is deferred)"
    unenforced: a comment
    scope:
      - edad/gate.py
    rejected: leaving it bare — the flag encodes a deferred decision a reader cannot recover
  - id: D10
    decision: "the RunState docstring in edad/session_queue.py gains a sentence on harness beside sandbox and network"
    unenforced: a docstring
    scope:
      - edad/session_queue.py
    rejected: keeping session_queue.py out of scope and fixing by hand — a hand commit for one sentence
deferred:
  - exact report() line formatting
  - Measurement field names; whether `measured` is a property
  - the evaluate die message wording (reuse approve's verbatim)
  - cleaning the inert gate_toolchain_problems patches in tests/test_gate_red_proof.py
  - kill-condition numbers (max_diff_lines 300 against an estimate of ~150)
  - whether .claude/skills/next/survey.py should print harness identity
```
