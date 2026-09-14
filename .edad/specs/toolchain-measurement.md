---
slug: toolchain-measurement
grilled: .edad/grills/toolchain-measurement.md
status: draft
---

## Problem statement

T019 made every record and lock say which harness wrote it and which toolchain
versions the pin check measured. Two things are not yet true of that claim. First,
the record's `toolchain` block is not the check's measurement: `cmd_approve` probes
every pinned name twice — once to refuse a mismatch, once to write the lock — and
`evaluate` probes once and never checks at all. A hand-run `edad.gate run` on the
wrong pytest therefore writes a record naming the wrong version, and nothing in the
record says it was wrong. The `toolchain_versions` docstring says "the same
`_probe_versions` call" as the check; it is a second call. Second, nothing reads the
new blocks. `report()` does not print them, the review skill's list of `_edad` keys
does not name them, and the artifacts on disk come in three shapes — absent
(T001–T018 and every lock), `{}` (T019's own evidence, written by the pre-T019
harness through `Record`'s defaults), and the four-key block — so every future reader
has to re-derive the same normalisation and `{}` is the case it will get wrong.

## Solution

The toolchain is measured once per command. One pass over the pins file and one probe
per name produces a list of measurements; the check and the lock are two pure
readings of that same list, so they cannot disagree. `evaluate` reads the check too:
a run on a toolchain that does not match the pins dies with approve's message before
any command runs and before a `Record` exists, so a record's `toolchain` block now
means "these pins were satisfied when this verdict was made". Two pure readers
normalise the `harness` and `toolchain` blocks of any on-disk artifact into one shape
without touching the disk — T019's `{}` stays `{}`. `report()` prints both blocks
through those readers, `cmd_approve` prints the harness line beside the frozen-file
hashes, and the quickstart names the fields where it describes the record. The
existing `gate_toolchain_problems` and `toolchain_versions` names stay, as one-line
wrappers, so `session.preflight` and T019's frozen test are untouched.

## User stories

1. As an auditor reading `.edad/evidence/T0NN.json`, I want its `toolchain` block to
   be the measurement the gate accepted, so that the block asserts the pins were
   satisfied rather than reporting whatever a second probe happened to see.
2. As an operator who hand-runs `python3 -m edad.gate run T0NN` on a machine with the
   wrong pytest, I want the gate to refuse the way `approve` and `preflight` already
   do, so that a mismatched run cannot leave evidence behind.
3. As a harness developer, I want the check and the lock to read one measurement,
   so that a probe that is slow or flaky is paid for once and cannot give two answers
   in one command.
4. As the writer of any tool that reads a record or a lock, I want one reader that
   turns absent, `{}`, partial and full `harness` blocks into the same four keys, so
   that I do not re-derive the rule and get `{}` wrong.
5. As the operator reading a gate's output, I want the harness and toolchain printed
   beside the verdict, so that "who measured this, with what" is visible without
   opening the JSON — and so that the pytest bump, when it lands, is visible in the
   line the night prints.
6. As the operator reading `approve`'s output, I want the same harness line after the
   hashes, so that I can see who measured the red proof at the moment it was taken.
7. As a reviewer following `/review-branch`, I want the skill's list of `_edad` keys
   to name `harness` and `toolchain`, so that the review reads them rather than
   discovering them.
8. As a reader of `harness_dirty` or `RunState`, I want the deferred decisions they
   embody (`--untracked-files=no`; the harness field beside the tier) stated where
   the code is, so that a future change is made against the reason, not the flag.

## Seams

Seven. Five exist; the two new ones are new by construction, since the names they
observe do not exist at base.

- **`probe`**
  - **Where**: `_probe_versions` monkeypatched on the `gate` module, exactly as
    T019's D3 test already does, beneath `measure_toolchain` and the two wrappers.
  - **Exists**: yes.
  - **Observes**: that `measure_toolchain` makes one file pass and one probe per
    pinned name in file order; that it returns `[]` when the pins file is absent;
    and that `gate_toolchain_problems` and `toolchain_versions`, now wrappers, give
    the check's messages and the `{name: measured}` map unchanged. This is the
    frozen D3 test's existing attachment point; that test survives the rewrite
    with only its docstring corrected, but it is green at base and so cannot be an
    acceptance command of a red-proof ticket — D2's new probe test is, and is red
    on its own assertion.
  - **Discharges**: D2 (the measurement half).

- **`measurement`**
  - **Where**: `measure_toolchain` as a module-level name on `gate`, faked with a
    list of `Measurement`s — the one handle that steers both `evaluate` and
    `cmd_approve`.
  - **Exists**: new.
  - **Observes**: what the two callers do with a given measurement: that the record
    and the lock carry `versions_of` it; that a measurement with a problem makes
    `evaluate` die before `run_commands`; that `cmd_approve` calls it exactly once
    for the check and the lock together. The grill chose this over a per-root cache
    under the wrappers because a call count on a module-level name is something a
    test can assert and a cache lifetime is not.
  - **Discharges**: D1, D2 (the once-per-approve half), D4.

- **`verdict`**
  - **Where**: `evaluate()`'s returned `Record` and `write_record`'s JSON, driven
    with `FakeRun`; `cmd_approve` driven with an `argparse.Namespace` and read back
    from the lock, the way the red-proof tests and T019's D4 tests drive it; and
    `die()` observed as `SystemExit(2)` with its message on stderr, the way
    `refused(capsys, ...)` reads it in `tests/test_gate_red_proof.py`.
  - **Exists**: yes.
  - **Observes**: the readout side of `measurement` — the record's `toolchain`
    block, the lock's `_edad.toolchain`, and on a mismatch that no command ran and
    no record was built.
  - **Discharges**: D1, D2, D4 (with `measurement`).

- **`readers`**
  - **Where**: `harness_of(artifact)` and `toolchain_of(artifact)`, pure functions
    over a dict.
  - **Exists**: new.
  - **Observes**: the four-key normalisation — absent key, `{}` and non-dict give
    all-`None` with `source: "unknown"`; a dict keeps what it has of the four keys,
    missing ones `None` and a missing `source` `"unknown"`; `toolchain_of` gives the
    dict or `{}`; neither
    raises, neither writes. Fed fabricated dicts shaped like the three on-disk
    generations, so it never reads `.edad/` and never depends on which artifacts
    the checkout happens to hold.
  - **Discharges**: D3.

- **`report-stdout`**
  - **Where**: `report(rec)` under `capsys`, as
    `test_report_names_the_mutation_proof_tier` and the red-proof tier tests do.
  - **Exists**: yes.
  - **Observes**: a `harness` line and a `toolchain` line after `decisions`, both
    when the record carries the blocks and when it carries `{}` and prints
    `unknown` — which is the same test proving the lines go through `harness_of`
    and `toolchain_of` rather than indexing the dict.
  - **Discharges**: D5.

- **`approve-stdout`**
  - **Where**: `cmd_approve` driven from an `argparse.Namespace` under `capsys`,
    exactly as the D4 lock test drives it, reading `readouterr().out` instead of
    the lock.
  - **Exists**: yes — the red-proof tests already read approve's stderr this way;
    only the stream differs.
  - **Observes**: the harness line printed after the frozen-file hashes, through
    `harness_of` over the faked identity.
  - **Discharges**: D6.

- **`quickstart-text`**
  - **Where**: `QUICKSTART.md` read as text, the `## Evidence` section regexed the
    way T019's `## Releasing` test does.
  - **Exists**: yes.
  - **Observes**: the section names `harness` and `toolchain`.
  - **Discharges**: D7.

Decisions with no seam: D8, D9, D10 — a prompt file, a comment and a docstring, all
`unenforced` in the grill with those reasons. D6 was unenforced in the grill's round 2
on the ground that approve's stdout had no test seam; that was false (see
`approve-stdout` above), so it went back to the grill rather than being corrected
here, and round 3 enforced it.

## Implementation decisions

Everything but two doc edits lives in the gate module, beside the version probing
T019 left there.

The measurement becomes a value. A small dataclass holds, per pinned name, what was
pinned and what the two probes saw (the importable version and the one first on
PATH — kept separate, as the probe already does, because which one runs is a
property of how the command is spelled). One function produces the list: one pass
over the pins file, one probe per name, an empty list when there is no pins file.
That last case is a legitimate answer, not an error — a target without a pins file
measures nothing, and T019's `{}` is that answer written down.

The check and the lock become readings of that value. The check keeps its three
messages word for word; the version map keeps its `{name: measured}` shape with
`measured` meaning "importable, else on PATH", as before. Both are pure, so both can
be exercised on fabricated measurements without a subprocess. The two names the rest
of the harness already imports — `gate_toolchain_problems` and `toolchain_versions`
— stay as one-line compositions of measure-then-read, which is what keeps
`session.preflight` and T019's frozen test untouched. The grill rejected collapsing
the pair into one function returning a tuple: the wrappers would become Middle Men
over a Data Clump, and a caller wanting only the problems would be handed the
versions too.

`evaluate` gains the check. It measures once, reads the problems, and dies with
`cmd_approve`'s message if there are any — before any command runs, before a
`Record` exists — then builds the record with the versions from that same list. The
cost is deliberate: a hand-run gate on the wrong toolchain now refuses instead of
writing evidence, which is exactly what `approve` and `preflight` already do at
their doors. The alternatives were rejected on what the record would then mean:
measuring without checking leaves it meaning "what a probe saw", and recording the
mismatch as a violation produces the FAIL-for-a-toolchain-reason that preflight
exists to keep away from the agent. `cmd_approve` measures once too, and uses that
one list for both its check and its lock.

The patch seam moves. T019's record and lock tests steer the toolchain by faking
`toolchain_versions` and `gate_toolchain_problems`; once `evaluate` and
`cmd_approve` call neither, those fakes are inert. The frozen file is amended before
approval so those two tests fake `measure_toolchain` with a list of measurements —
one handle steering both callers, and one whose call count a test can assert. The
per-root cache the grill rejected would have kept the old fakes working at the price
of state no test can count. The same inert fake in `tests/test_gate_red_proof.py` is
left alone: that file is out of scope, and the fake is harmless there because
`tmp_path` has no pins file.

Two readers normalise on the way out, never on disk. Given any artifact dict,
`harness_of` returns exactly the four keys; an absent block, `{}`, or something that
is not a dict reads as unknown, and a dict is trusted for what it has of the four
keys and given `None` for what it lacks, `"unknown"` for a missing `source` — so a
lock with three of the four keys keeps the commit it recorded rather than being
demoted to unknown, and `{}` is a consequence of the rule rather than a case of
it. `toolchain_of`
returns the dict or `{}`. Neither raises, because a reader of on-disk artifacts that
raises on an old shape is a reader that stops the night over history. Nothing is
backfilled: normalising on read is the opposite of editing the record, and T019's
evidence stays `{}`.

`report()` prints the two blocks through those readers, after the `decisions` line:
the harness as source, short commit, a dirty marker and the version when there is
one, or `unknown`; the toolchain as name–version pairs, or `unknown`. `cmd_approve`
prints the same harness line after the frozen-file hashes, so the operator taking a
red proof sees who measured it — pinned by a test, since the D4 lock test already
drives approve end to end and reading its stdout costs one line.

Beyond the gate module: the quickstart's `## Evidence` section names the two
fields, since the `## Releasing` section already refers to `harness.commit` without
anything earlier introducing it; the review skill's list of `_edad` keys gains
both; `harness_dirty` gets the reason for `--untracked-files=no`; and the `RunState`
docstring gets a sentence on `harness` beside `sandbox` and `network`. The last
three are prompt text, a comment and a docstring — unenforced, and asked of the
agent by name because the agent is already in the tree.

## Out of scope

- **The pytest 8.4.2 → 9.0.3 bump.** Its own ticket, after the parser probe
  harness-identity's spec named. This design has one consequence for it, recorded
  in the grill and not decided here: once `evaluate` refuses a mismatch, a ticket
  that bumps a pin makes the in-container agent's own gate run die, because the
  image was built on the old pin — the agent sees a refusal, not a FAIL. Preflight
  already has this property on the host; the bump ticket owns the rollout.
- **Cleaning the inert `gate_toolchain_problems` fake in
  `tests/test_gate_red_proof.py`.** Deferred; the file is out of scope.
- **`.claude/skills/next/survey.py` printing harness identity.** Deferred; it does
  not import `edad`, and `/next` shows pipeline state, not provenance.
- **Toolchain in the session and run logs.** T019 decided record and lock only;
  nothing here reopens it.
- **Pinning the harness itself in a target's pins file.** Still deferred from
  harness-identity, until ai-sniffer has run some nights.

## Further notes

- **Deferred from the grill, with reasons:** exact `report()` line formatting;
  `Measurement`'s field names and whether `measured` is a property (both cheap to
  rename before approval); the `evaluate` die message wording (reuse approve's
  verbatim); the red-proof fake cleanup; kill-condition numbers (`max_diff_lines:
  300` against an estimate of ~150); whether `survey.py` should print identity.
- **For `to-tickets`.** One ticket, `blocked_by: [T019]`. All enforced decisions
  share `tests/test_harness_identity.py` as their frozen file and D1–D6 and D9 share
  `edad/gate.py` as scope; D7, D8 and D10 add one path each. T019's lock on the
  test file is historical; re-freezing it under the new ticket is the normal path,
  as T019 did to `tests/test_session_queue.py`.
- **Red at base — measured, not forecast** (probe of 2026-09-14, recorded in the
  grill). Without stubs, 8 of the 9 new-name tests go red on `AttributeError` — a red
  that proves the test reached the code, not that it asserts anything. With
  returning stubs (`measure_toolchain` → `[]`, `toolchain_problems` → `[]`,
  `versions_of` → `{}`, `harness_of`/`toolchain_of` → `{}`, the dataclass as itself)
  all ten acceptance commands fail on their own assertion and the other 230 tests
  stay green. Against a correct implementation: 240 green, ruff clean, 171 numstat
  lines in scope including the stubs. The amended frozen file and the stubs are in
  the working tree, uncommitted, as the pre-approval state; the implementation was
  thrown away with the probe worktree.
- **Amended frozen stand-ins, before approval:** the two D4 tests fake
  `measure_toolchain` instead of `toolchain_versions`/`gate_toolchain_problems`;
  the T019 D3 test's docstring is corrected and its assertions untouched; setup
  shared by the approve-driving tests is in `write_ticket`/`approve_fakes`/
  `evaluate_fakes` helpers. Editing the file sets T019's `freeze_ok` to False —
  historical, as T019 did to T017's file.
- **Gaps needing re-grilling:** none remaining. D6's reason, D2's first command
  and D3's sourceless-dict edge were re-grilled on 2026-09-14 (round 3); every path
  in `scope` and `frozen` exists at `905c8f5`.

## Decisions

Carried from `.edad/grills/toolchain-measurement.md` verbatim; `seam:` is the only
field this stage added. `to-tickets` reads this block and the Seams section and
nothing else in this file.

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
    seam: verdict, measurement
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
    seam: probe, measurement
    rejected: memoising _probe_versions per command — invisible state the frozen test cannot count; one check_toolchain(root) -> (problems, versions) — the wrappers become Middle Men and the tuple a Data Clump
  - id: D3
    decision: "harness_of(artifact) -> exactly {version, commit, dirty, source}: absent key, {} or non-dict -> all None with source unknown; a dict keeps the values it has for those four keys, missing keys become None and a missing source becomes unknown; never raises, never writes. toolchain_of(artifact) -> the value if a dict, else {}"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_harness_of_reads_absent_empty_partial_and_full_blocks_as_one_shape -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    seam: readers
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
    seam: measurement, verdict
    rejected: keeping the wrappers as the seam with a per-root cache underneath — the D2 cache option by another name
  - id: D5
    decision: "report() prints, after decisions, a harness line (<source> <commit[:8]>[ dirty][ v<version>], or unknown) and a toolchain line (<name> <ver>, ..., or unknown), both through harness_of/toolchain_of"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_report_prints_the_harness_and_toolchain_lines -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    seam: report-stdout
    rejected: harness line only — the toolchain line is what makes a pin bump visible when it lands
  - id: D6
    decision: "cmd_approve prints the same harness line after the frozen-file hashes"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_approve_prints_the_harness_line -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    seam: approve-stdout
    rejected: report() only — the operator reading approve's output has no other way to learn who measured the red proof; unenforced with the corrected reason ("one line is not worth a frozen test") — leaves the one line an operator reads at approval as the one line nothing checks
  - id: D7
    decision: "QUICKSTART's ## Evidence section names the record's harness and toolchain fields"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_quickstart_evidence_section_names_harness_and_toolchain -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - QUICKSTART.md
    seam: quickstart-text
    rejected: leaving it to the Releasing section, which refers to an identity block nothing earlier introduces
  - id: D8
    decision: "the _edad key list in .claude/skills/review-branch/SKILL.md gains harness and toolchain"
    unenforced: a prompt file; nothing executes it
    scope:
      - .claude/skills/review-branch/SKILL.md
    seam: none (prompt file)
    rejected: fixing by hand outside the pipeline — a hand commit for one line the ticket's agent is already in the tree for
  - id: D9
    decision: "harness_dirty carries the reason for --untracked-files=no (an untracked file changes behaviour only if something imports it; counting untracked is deferred)"
    unenforced: a comment
    scope:
      - edad/gate.py
    seam: none (comment)
    rejected: leaving it bare — the flag encodes a deferred decision a reader cannot recover
  - id: D10
    decision: "the RunState docstring in edad/session_queue.py gains a sentence on harness beside sandbox and network"
    unenforced: a docstring
    scope:
      - edad/session_queue.py
    seam: none (docstring)
    rejected: keeping session_queue.py out of scope and fixing by hand — a hand commit for one sentence
deferred:
  - exact report() line formatting
  - Measurement field names; whether `measured` is a property
  - the evaluate die message wording (reuse approve's verbatim)
  - cleaning the inert gate_toolchain_problems patches in tests/test_gate_red_proof.py
  - kill-condition numbers (max_diff_lines 300 against an estimate of ~150)
  - whether .claude/skills/next/survey.py should print harness identity
```
