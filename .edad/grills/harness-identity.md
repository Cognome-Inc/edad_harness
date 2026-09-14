---
slug: harness-identity
grilled_at: 2026-09-12
---

## Record

Grilled 2026-09-12 on `Cognome-Inc/edad_harness` @ `1b2f21c` (T018 merged locally,
PR #2 open, `v0.1.0` tagged and unpushed). Handed on from
`.edad/grills/pip-installable.md`: once teammates install the harness by tag and
developers by editable checkout, "which harness produced this verdict" becomes a
question the evidence record cannot answer. The harness's own thesis — a verdict is a
property of the commit, not of what was installed that day — currently covers pytest,
ruff and PyYAML through `requirements-gate.txt` and does not cover the harness.

Facts established before the interview, by reading rather than asking. The evidence
record (`Record` in `edad/gate.py`) carries the *target's* `commit`, `baseline_commit`,
`decisions` and `red_proof`, and nothing about the harness; neither does the lock's
`_edad` block, `SessionLog`, or the run log's `as_log()`. What the harness can learn
about itself depends on how it was installed: a `git+…@v0.1.0` install has
`direct_url.json` with `vcs_info.commit_id` and `requested_revision`; an editable
install reports `version` `0.1.0` whatever commit is checked out, with
`direct_url.json` `dir_info.editable` pointing at the checkout; an uninstalled checkout
(how this repo gates itself) has no metadata at all — except that a gitignored
`edad_harness.egg-info/` left by any earlier `pip install -e` answers `0.1.0` from the
cwd, so `version` alone is unreliable as an identity. `gate_toolchain_problems`
already measures pytest/ruff/PyYAML versions via `_probe_versions` and discards them
after comparing. Blast radius, probed: a new field on `Record` and `SessionLog` breaks
no frozen test; a new top-level run-log key breaks exactly one, the exact key-set
assertion in `tests/test_session_queue.py` (~:1430). The approve tests monkeypatch
`gate_toolchain_problems` to `[]`, so version *gathering* needs its own name to be
fakeable independently. Session-log tests pin field *order*
(`keys[keys.index("network_access") + 1] == "permissions"`). `pytest==8.4.2` has a
Dependabot medium (tmpdir handling, fixed 9.0.3); the gate parses pytest's
`FAILED`/`ERROR` lines, so a major bump is not a one-line edit.

**Round 1 — record, don't pin.** The harness *records* its identity in every artifact
and never refuses to run on account of it. Rejected: also pinning the harness in the
target's `requirements-gate.txt` so the gate refuses a mismatch — stronger, but the
line would have to be a `git+` URL rather than `==`, the harness repo would need an
editable install to gate itself, and every release becomes a commit in every target.
Revisit once ai-sniffer has run some nights and a harness upgrade has actually
happened.

**D1 — the identity, and its pure core.** `identify_harness(version, direct_url, head,
dirty) -> dict` in `edad/gate.py`, returning exactly `{"version", "commit", "dirty",
"source"}`. Commit is the primary fact; version is the label. Rules: `direct_url` with
`vcs_info` → `source: "vcs"`, `commit` from `vcs_info.commit_id`, `dirty: null`
(nothing to measure); `direct_url` with `dir_info.editable` → `"editable"`, commit and
dirty from the checkout; no metadata but a checkout head → `"checkout"`, version null;
nothing → `"unknown"`, all null. Pure, so the frozen tests feed one fabricated input
set per mode and are deterministic on every machine. Rejected: version+commit only
(loses "dirty", the case that silently produces an unreproducible record, and cannot
tell a tag install from a developer checkout); version only (every commit between tags
reads `0.1.0`); a single function tested against the real machine (passes here, fails
in the container). Scope: `edad/gate.py`.

**D2 — the gatherer.** `harness_identity() -> dict` in `edad/gate.py`, beside
`_probe_versions`: reads `importlib.metadata` for `edad-harness` and its
`direct_url.json`; locates the checkout as `Path(edad.__file__).resolve().parents[1]`
only if `.git` exists there; runs `git rev-parse HEAD` and `git status --porcelain
--untracked-files=no`; feeds D1. **Never raises**: anything it cannot learn is null and
the source degrades to `unknown`. That is what record-only means. Rejected: a new
module `edad/identity.py` — keeps `gate.py` smaller but adds a file to scope and an
import in two modules, for two functions that belong beside the existing version
probing. Scope: `edad/gate.py`.

**D3 — `toolchain_versions(root) -> dict`.** Extracted from `gate_toolchain_problems`:
`{name: measured}` for every `==` line in `requirements-gate.txt`, null when not found.
`gate_toolchain_problems` is rewritten on top of it with unchanged behaviour; its
existing tests stay green. A separate name so the approve tests, which fake the
problems check, can fake the gathering too. Scope: `edad/gate.py`.

**D4 — record and lock carry both.** `Record` gains `harness: dict` and `toolchain:
dict` after `uncomparable_failures`, populated where `rec = Record(...)` is built;
`write_record`'s payload has them. The lock's `_edad` block gains the same two keys at
approval, so the lock says which harness and which toolchain measured the red proof
and the baseline. Old records and locks simply lack the keys; readers treat absence
as unknown; **no backfill** — a backfilled value is the record asserting something the
gate never measured. Scope: `edad/gate.py`.

**D5 — the two logs carry the harness.** `SessionLog.harness: dict` immediately after
`permissions`; the run log's `as_log()` gains top-level `"harness"` immediately after
`"network"`. Toolchain is *not* in the logs — record and lock only. The frozen key-set
assertion in `tests/test_session_queue.py` is amended pre-approval to include
`"harness"`. Rejected: record and lock only (a session log already says how a run was
made — sandbox, permissions — and the harness belongs beside those); record only.
Scope: `edad/session.py`, `edad/session_queue.py`.

**D6 — releases are an operator act, documented in QUICKSTART.** A release is a commit
that edits `version` in `pyproject.toml` and the pinned line in `QUICKSTART.md`
(T018's `test_quickstart_pinned_tag_matches_project_version` forces them to agree),
merged by PR, tagged `vX.Y.Z` on the merge commit, tag pushed. Not per ticket; not
derived at build time; the static version of pip-installable's D1 holds. Commits
between releases are identified in records by `harness.commit`. Written once, as a
`## Releasing` section in QUICKSTART. Rejected: bump patch on every merged ticket
(every ticket a release, the bump in every diff); setuptools-scm (a build-time network
dependency, and the version leaves the file the metadata test reads); a separate
`RELEASING.md` (a second doc for five lines); grill/spec only (not where an operator
would read). Scope: `QUICKSTART.md`.

**D7 — the tag itself.** Unenforced: repository state, in the operator's hands; the
gate cannot see a tag on a commit that does not exist yet. Documented by D6.

**D8 — `requirements-gate.txt` header reworded.** "Bumping any pin invalidates prior
evidence" overstates it: each record stays valid for its commit, because the check
guaranteed the pins at that commit, and from D4 on the record says which. A bump means
*new* records are made under different pins. Unenforced: a comment. Rejected: keeping
the wording — it would imply re-running eighteen tickets for a pytest bump. Scope:
`requirements-gate.txt`.

**Not in scope, and why.** The pytest 8.4.2 → 9.0.3 bump: its own ticket, after a probe
that 9.0.3 still emits the lines `PYTEST_FAILURE_RE` / `PYTEST_FAILED_RE` and the `-q`
summary parser match, with this repo's own suite as evidence. This design records what
ran; the bump changes what runs, and mixing them makes one ticket's evidence depend on
the other's toolchain. Not urgent: the gate runs pytest in a sandbox on a worktree.
Rejected: folding it in; dismissing the alert.

**Deferred, cheap to reverse.** Whether a dirty harness checkout prints a one-line
warning at run time (record-only says no). Whether `dirty` counts untracked files
(`--untracked-files=no` for now). Pinning the harness in targets — after ai-sniffer
nights.

## Decisions

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
    rejected: version-only or version+commit identity — cannot tell a tag install from an edited developer checkout; a real-machine test — depends on how this laptop has the harness installed
  - id: D2
    decision: harness_identity() gathers importlib.metadata, direct_url.json and the checkout's git head/dirtiness, never raises, degrades to unknown
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_the_gatherer_never_raises_and_degrades_to_unknown -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
    rejected: a new edad/identity.py module — a file in scope and two imports for two functions that belong beside _probe_versions
  - id: D3
    decision: "toolchain_versions(root) -> {name: measured|null} extracted from gate_toolchain_problems, which is rewritten on it with unchanged behaviour"
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_toolchain_versions_stores_what_the_pin_check_measures -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - edad/gate.py
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
    rejected: record and lock only — the logs already say how a run was made and the harness belongs beside sandbox and permissions
  - id: D6
    decision: a release is an operator commit bumping pyproject version and QUICKSTART's pinned line, PR-merged, tagged vX.Y.Z, tag pushed; documented as a `## Releasing` section in QUICKSTART
    verify:
      - python3 -m pytest tests/test_harness_identity.py::test_quickstart_has_a_releasing_section_naming_the_tag_step -q
    frozen:
      - tests/test_harness_identity.py
    scope:
      - QUICKSTART.md
    rejected: per-ticket patch bumps — every ticket a release; setuptools-scm — a build-time network dependency and the version leaves the file; RELEASING.md — a second doc for five lines
  - id: D7
    decision: the release tag is placed and pushed by the operator on the merge commit
    unenforced: a git tag is repository state outside any worktree; the gate cannot observe it. Documented by D6.
    scope: []
    rejected: deriving or checking the tag in-gate — tags are absent in a fresh clone or the container and present in a worktree; the check would answer differently per machine
  - id: D8
    decision: requirements-gate.txt header says a bump changes what future records are made under; prior records stay valid for their commits
    unenforced: a comment in a pins file
    scope:
      - requirements-gate.txt
    rejected: keeping "bumping any pin invalidates prior evidence" — would imply re-running eighteen tickets for a pytest bump
deferred:
  - whether a dirty harness checkout prints a one-line warning at run time
  - whether dirty counts untracked files (--untracked-files=no for now)
  - pinning the harness version in a target's requirements-gate.txt, after ai-sniffer nights
  - pytest 8.4.2 -> 9.0.3 as its own ticket, after a probe of the output parsers
```
