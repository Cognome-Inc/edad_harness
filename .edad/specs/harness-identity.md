---
slug: harness-identity
grilled: .edad/grills/harness-identity.md
status: draft
---

## Problem statement

An evidence record says which commit of the *target* it judged, which decisions the
passing tests discharge, and that those tests were proven capable of failing. It does
not say which harness did the judging. Until T018 that was moot: there was one
checkout of the harness and it was on the operator's machine. Now a teammate installs
it by tag, a developer installs a checkout editable, and this repo gates itself from
an uninstalled tree — three harnesses that can differ, and every record they write
looks the same. The gate's own thesis is that a verdict is a property of the commit
and not of what was installed that day; it enforces that for pytest, ruff and PyYAML
through the pins file, and it is silent about itself. The pins are in the same
position one step down: the gate measures their versions before every run, refuses a
mismatch, and then throws the measurement away, so a record's toolchain is
recoverable only by reading the pins file at the record's commit.

## Solution

Every artifact the harness writes names the harness that wrote it. The evidence record
and the approval lock carry a `harness` block — version, commit, whether the checkout
was dirty, and how it was installed — and a `toolchain` block with the versions the
pin check actually measured. The session log and the run log carry the `harness`
block beside the fields that already say how a run was made. Nothing refuses to run
on account of any of this; a harness that cannot identify itself says `unknown`
rather than failing. A release becomes a deliberate, documented operator act — bump,
PR, tag — and the records identify everything between releases by commit.

## User stories

1. As an auditor reading `.edad/evidence/T0NN.json`, I want it to name the harness
   commit and the toolchain versions that produced it, so that I can reproduce the
   verdict without reconstructing what was installed that night.
2. As a teammate who installed the harness by tag, I want my records to say `vcs`,
   the tag's commit and `dirty: null`, so that nobody has to ask which harness I ran.
3. As a harness developer running an edited checkout, I want the record to say
   `editable`, my head commit and `dirty: true`, so that a verdict made under
   uncommitted changes is visibly not reproducible rather than silently so.
4. As the operator of this repo gating itself from an uninstalled tree, I want the
   record to still identify the harness by commit with `version: null`, so that
   self-hosted evidence is as traceable as anyone else's.
5. As a reviewer of an approval lock, I want it to say which harness and toolchain
   measured the red proof and the baseline, so that a lock is not vouching for a
   measurement nobody can attribute.
6. As anyone on a machine where metadata is missing and git is absent or broken, I
   want the gate to run and record `unknown` rather than refuse, so that identity
   never becomes a reason a night does not happen.
7. As the operator bumping a pin, I want the pins file to say what a bump actually
   means — new records under new pins, old records still valid for their commits — so
   that a Dependabot alert does not read as "re-run eighteen tickets".
8. As the person cutting a release, I want the procedure written where I will read
   it, so that the tag the pinned install line depends on is never forgotten.

## Seams

Six. Four exist; the two new ones are new by construction, since the functions they
observe do not exist yet.

- **`identity-core`**
  - **Where**: `identify_harness()`, the pure function in the gate module.
  - **Exists**: new.
  - **Observes**: the mode → identity rules from fabricated inputs, one set per
    mode — a `direct_url` with `vcs_info`, one with `dir_info.editable`, no metadata
    with a checkout head, and nothing at all. Deterministic on every machine, which
    is the reason the core is pure: on this laptop the harness is editable-installed,
    in the container it is a bare checkout, on a teammate's it is a tag install.
  - **Discharges**: D1.

- **`identity-gatherer`**
  - **Where**: `harness_identity()` in the gate module, with its metadata read and its
    two git shell-outs reachable as names on the module so a test can make each one
    fail — the way `docker_network_internal` is a named module-level function for the
    same reason.
  - **Exists**: new.
  - **Observes**: that with metadata raising and git failing it returns nulls and
    `unknown` and does not raise.
  - **Discharges**: D2.

- **`toolchain-probe`**
  - **Where**: `toolchain_versions(root)` over `_probe_versions`, which the existing
    pin-check tests already monkeypatch.
  - **Exists**: the probe exists; the function over it is new.
  - **Observes**: the `{name: measured | null}` map for every `==` line, and — via the
    existing `gate_toolchain_problems` tests staying green — that the check's
    behaviour is unchanged after being rewritten on top of it.
  - **Discharges**: D3.

- **`verdict`**
  - **Where**: `evaluate()` — "the single entry point for anything that needs a
    verdict" — and `write_record`; and for the lock, `cmd_approve` driven the way
    `approve_red()` in the red-proof tests drives it.
  - **Exists**: yes. `test_gate_record.py` already drives `evaluate()` with `FakeRun`
    and reads `write_record`'s JSON; the red-proof tests already read `_edad` out of
    the lock after a faked approve.
  - **Observes**: with `harness_identity` and `toolchain_versions` patched to
    sentinels, that the record the gate *builds* carries both, that the JSON on disk
    carries both, and that the lock's `_edad` block carries both at approval.
  - **Discharges**: D4.

- **`logs`**
  - **Where**: `asdict(SessionLog(...))` field order, the T017 precedent, and
    `RunState.as_log()`.
  - **Exists**: yes.
  - **Observes**: `harness` immediately after `permissions` in the session log and
    immediately after `network` in the run log, defaulting to `{}`. This proves the
    field and its position, not that the session populates it — the same choice T017
    made for `permissions`; populating it is one line beside the `permissions=` call,
    and the ticket's Required interface names it.
  - **Discharges**: D5. The exact key-set assertion on `as_log()` in
    `tests/test_session_queue.py` (~:1432) is a frozen stand-in amended **before
    approval** to include `harness`.

- **`quickstart-text`**
  - **Where**: `QUICKSTART.md` read as text, as T018's packaging tests do.
  - **Exists**: yes.
  - **Observes**: a `## Releasing` section that names the tag step.
  - **Discharges**: D6.

Decisions with no seam: D7 (the tag is repository state outside any worktree and
absent in a fresh clone or the container; a check would answer differently per
machine) and D8 (a comment in the pins file). Both are `unenforced` with those reasons.

## Implementation decisions

Two new functions and one extraction, all in the gate module beside the existing
version probing; two dataclass fields; one key in each of three dictionaries; a doc
section; a comment.

The identity is a four-field block and the commit is its primary fact. A version is a
label that every commit between two releases shares, so on its own it cannot
distinguish a developer's edited checkout from the release it claims to be — and the
stale metadata an earlier editable install leaves in the tree makes even the label
untrustworthy from a bare checkout. The `source` field says how the harness was
installed so a reader knows which of the other fields to believe: a tag install's
commit came from pip's own record and has no checkout to be dirty; an editable
install's commit came from the checkout and its dirtiness is measured; a bare
checkout has a commit and no version; and `unknown` means nothing could be learned.

Deciding is separated from gathering so the decision is testable everywhere. The pure
core takes the four raw facts and applies the rules; the gatherer collects them from
package metadata and from git at the directory the imported package lives in, only
when that directory is a git checkout. The gatherer never raises. That is not
robustness for its own sake — it is what "record, don't pin" means: identity is
something the harness reports about itself, never a precondition of running.

The toolchain measurement the pin check already performs is kept instead of
discarded. A small function returns what was measured for every pinned name, and the
pin check is rewritten to consume it, so the two cannot disagree. It has its own name
because the approve tests already fake the check and must be able to fake the
gathering independently.

Both blocks land in the evidence record and in the approval lock, because the lock's
red proof and baseline are measurements too, made by some harness under some
toolchain. The record's schema simply grows two keys; artifacts written before this
lack them, and a reader treats absence as unknown. Nothing is backfilled — a
backfilled value would be the record asserting something the gate never measured,
which is the one thing a record in this harness must never do. The session log and
run log get the harness block only, positioned beside the fields that already
describe how a run was made.

A release is an explicit operator act: one commit that moves the version in the
project metadata and the pinned install line in the quickstart (T018's test already
forces them to agree), merged by pull request, tagged on the merge commit, tag pushed.
The version stays a static string, as pip-installable's D1 decided, and nothing is
bumped per ticket. The procedure is written once, in the quickstart, because that is
the only document and the pinned-tag test already ties it to the version.

The pins file's header currently says a bump invalidates prior evidence. It does not:
the pin check guaranteed the pins at each record's commit, and from this change on
the record says which they were. A bump means new records are made under different
pins. The header is reworded to say that.

## Out of scope

- **Pinning the harness in a target's pins file** so the gate refuses a mismatch.
  Rejected for now in the grill's round 1 and deferred until ai-sniffer has run some
  nights and a real harness upgrade has happened. The record this ticket adds is what
  would make that decision informed.
- **The pytest 8.4.2 → 9.0.3 bump** (Dependabot medium, tmpdir handling). Its own
  ticket, after a probe that 9.0.3 still emits the lines the gate's pytest parsers
  match, with this repo's suite as evidence. This design records what ran; that one
  changes what runs.
- **Toolchain in the logs.** Record and lock only, per the grill.
- **Warning on a dirty checkout at run time.** Deferred; record-only says no.

## Further notes

- **Deferred from the grill, with reasons:** a run-time warning on a dirty harness
  checkout (cheap to add once someone wants it; record-only says not now); whether
  `dirty` counts untracked files (`--untracked-files=no` for now — an untracked file
  changes behaviour only if something imports it); harness pinning in targets (after
  ai-sniffer nights); the pytest 9 bump (own ticket, parser probe first).
- **For `to-tickets`.** All six enforced decisions share one new frozen file and one
  more frozen stand-in, and D1–D4 share one scope path, so this is one ticket; D5 adds
  two scope paths, D6 and D8 one each. Stubs before approval must *return* the wrong
  shape, not raise: `identify_harness` returning `{}`, `harness_identity` returning
  `{}`, `toolchain_versions` returning `{}` — so every frozen test fails on its own
  assertion. The `as_log()` key-set amendment in `tests/test_session_queue.py` happens
  before that file is hashed. `full_gate` will run `ruff check .` — the new frozen
  file must be clean under the pinned rule set and `target-version = "py312"`.
- **Not decided here and needing no grill:** the exact wording of the `## Releasing`
  section and of the pins-file header. Both are prose; D6's test checks only that the
  section exists and names the tag step.
- **This spec was written while T018 (PR #2) is open and unmerged.** Nothing here
  depends on T018's code — the identity functions read metadata that exists with or
  without the `[project]` table — but the `## Releasing` section presumes the pinned
  install line T018 adds to QUICKSTART, so the ticket should be blocked on T018 having
  merged rather than run against a tree without it.

## Decisions

Carried from `.edad/grills/harness-identity.md` verbatim; `seam:` is the only field
added. Six enforced (D1–D6), two unenforced (D7, D8).

```yaml
decisions:
  - id: D1
    decision: "identify_harness(version, direct_url, head, dirty) -> {version, commit, dirty, source}; source in {vcs, editable, checkout, unknown}; commit primary, version the label"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_a_vcs_install_is_identified_by_its_recorded_commit -q
      - python3 -m pytest tests/test_harness_identity.py::test_an_editable_install_is_identified_by_the_checkout_head_and_dirtiness -q
      - python3 -m pytest tests/test_harness_identity.py::test_a_bare_checkout_is_identified_by_head_with_no_version -q
      - python3 -m pytest tests/test_harness_identity.py::test_nothing_known_is_unknown_with_nulls_not_an_error -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    seam: identity-core
    rejected: version-only or version+commit identity — cannot tell a tag install from an edited developer checkout; a real-machine test — depends on how this laptop has the harness installed
  - id: D2
    decision: harness_identity() gathers importlib.metadata, direct_url.json and the checkout's git head/dirtiness, never raises, degrades to unknown
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_the_gatherer_never_raises_and_degrades_to_unknown -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    seam: identity-gatherer
    rejected: a new edad/identity.py module — a file in scope and two imports for two functions that belong beside _probe_versions
  - id: D3
    decision: "toolchain_versions(root) -> {name: measured|null} extracted from gate_toolchain_problems, which is rewritten on it with unchanged behaviour"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_toolchain_versions_stores_what_the_pin_check_measures -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    seam: toolchain-probe
    rejected: leaving the pins out — recoverable by git show, but the record should be self-describing
  - id: D4
    decision: Record and the lock's _edad block carry harness and toolchain; absent in old artifacts means unknown, never backfilled
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_the_written_record_carries_harness_and_toolchain -q
      - python3 -m pytest tests/test_harness_identity.py::test_the_lock_records_harness_and_toolchain_at_approval -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    seam: verdict
    rejected: pinning the harness in the target's requirements-gate.txt so the gate refuses a mismatch — deferred until a real harness upgrade has happened on ai-sniffer
  - id: D5
    decision: SessionLog.harness immediately after permissions; run log as_log() gains top-level harness immediately after network; toolchain not in the logs
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_the_session_log_records_the_harness_beside_permissions -q
      - python3 -m pytest tests/test_harness_identity.py::test_the_run_log_records_the_harness_beside_network -q
    frozen:
      - tests/test_harness_identity.py
      - tests/test_session_queue.py
    scope:
      - edad/session.py
      - edad/session_queue.py
    seam: logs
    rejected: record and lock only — the logs already say how a run was made and the harness belongs beside sandbox and permissions
  - id: D6
    decision: a release is an operator commit bumping pyproject version and QUICKSTART's pinned line, PR-merged, tagged vX.Y.Z, tag pushed; documented as a `## Releasing` section in QUICKSTART
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_quickstart_has_a_releasing_section_naming_the_tag_step -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - QUICKSTART.md
    seam: quickstart-text
    rejected: per-ticket patch bumps — every ticket a release; setuptools-scm — a build-time network dependency and the version leaves the file; RELEASING.md — a second doc for five lines
  - id: D7
    decision: the release tag is placed and pushed by the operator on the merge commit
    unenforced: a git tag is repository state outside any worktree; the gate cannot observe it. Documented by D6.
    scope: []
    seam: none (operator act)
    rejected: deriving or checking the tag in-gate — tags are absent in a fresh clone or the container and present in a worktree; the check would answer differently per machine
  - id: D8
    decision: requirements-gate.txt header says a bump changes what future records are made under; prior records stay valid for their commits
    unenforced: a comment in a pins file
    scope:
      - requirements-gate.txt
    seam: none (comment)
    rejected: keeping "bumping any pin invalidates prior evidence" — would imply re-running eighteen tickets for a pytest bump
deferred:
  - whether a dirty harness checkout prints a one-line warning at run time
  - whether dirty counts untracked files (--untracked-files=no for now)
  - pinning the harness version in a target's requirements-gate.txt, after ai-sniffer nights
  - pytest 8.4.2 -> 9.0.3 as its own ticket, after a probe of the output parsers
```
