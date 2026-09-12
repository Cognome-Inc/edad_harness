---
slug: pip-installable
grilled: .edad/grills/pip-installable.md
status: draft
---

## Problem statement

The harness is about to be used against ai-sniffer by a team, and the only way to run
it from a target repo today is `export PYTHONPATH=/path/to/this/repo`. That line is
in QUICKSTART with the comment "until the package is installable". It works on the
machine it was typed on and nowhere else: it is not recorded in any environment, it
is not versioned, and a second teammate discovers it by asking. The harness's own
thesis is that a gate's verdict must be a property of the commit and not of whatever
happened to be installed that day; the harness itself is currently the one tool in
the chain that thesis does not cover.

## Solution

`edad_harness` is a pip-installable distribution. A target repo's venv installs it
one of two ways, both documented in QUICKSTART: a teammate pins it by tag
(`pip install git+https://github.com/Cognome-Inc/edad_harness@v0.1.0`) so their gate
runs a known harness version; a harness developer installs their checkout editable
(`pip install -e /path/to/edad_harness`) so edits are live. Either way
`python3 -m edad.gate`, `edad.session` and `edad.session_queue` resolve from any
working directory, and `PYTHONPATH` is gone from the docs. The invocation spelling
does not change; nothing else about the harness changes.

## User stories

1. As a teammate setting up ai-sniffer, I want to install the harness with one pip
   line at a fixed version, so that my gate runs the same harness as everyone
   else's and I never learn about `PYTHONPATH`.
2. As a harness developer, I want an editable install from my checkout, so that a
   fix in `edad/` is live in the target repo without a reinstall.
3. As an operator running the gate in a target venv with its own dependency pins, I
   want the harness's PyYAML requirement to be loose, so that installing the harness
   does not fight the target's lockfile while the gate's own exact pin still applies.
4. As anyone reading a doc, skill, error message or T017's host allowlist, I want
   `python3 -m edad.*` to remain the only way to invoke the harness, so that no
   second spelling appears that those places do not know.
5. As a teammate following QUICKSTART, I want the pinned install line to actually
   resolve, so that the first command in the doc does not fail on a missing tag.
6. As a reviewer approving the ticket, I want the real install proven end to end in
   a fresh venv and written into the ticket, so that "the metadata tests pass"
   is not mistaken for "the install works".

## Seams

Two existing seams discharge every enforced decision; two hand-run seams cover the
two decisions the gate cannot observe. No decision is without a seam.

- **`pyproject-metadata`**
  - **Where**: `pyproject.toml` at the repo root, parsed with `tomllib` (stdlib on
    3.12 and 3.13; no new dependency). The frozen test locates the root the way
    `test_egress_proxy.py` and `test_session_queue.py` already do,
    `Path(__file__).resolve().parents[1]`, so it reads the worktree's copy under a
    gate run and never the main checkout's.
  - **Exists**: yes — the file exists and already carries the pytest and ruff tables.
    The `[build-system]`, `[project]` and `[tool.setuptools]` tables the tests assert
    on do not exist yet, which is why every node here is red at base.
  - **Observes**: the build backend and its requirement; the distribution name,
    version and `requires-python`; the dependency list and the looseness of its one
    entry; that `packages` is exactly `["edad"]`; and the absence of
    `[project.scripts]` (asserted inside the metadata node, per the grill's note to
    `to-tickets` — absence alone is green at base and cannot be its own test).
  - **Discharges**: D1, D2, D3.

- **`quickstart-text`**
  - **Where**: `QUICKSTART.md` at the repo root, read as text; for the tag check,
    cross-read with `pyproject.toml` through the `pyproject-metadata` seam.
  - **Exists**: yes. `PYTHONPATH` appears exactly once today, at line 17, in the
    Install section; nothing else in the repo — docs, skills, `edad/` — mentions it.
  - **Observes**: that the text contains the pinned `pip install git+…@v<version>`
    form and the `pip install -e` form; that `PYTHONPATH` appears nowhere in the
    **whole file** (not only the Install section — moving the line under another
    heading must not pass); and that the tag in the pinned line equals
    `[project].version`, so the doc cannot drift from the pyproject it describes.
  - **Discharges**: D5.

- **`editable-install`** (hand-run; not an acceptance command)
  - **Where**: a fresh venv on the approver's machine: `pip install -e .`, then from
    a different cwd `python -m edad.gate --help` (exits 0 today) and
    `python -c "import edad.gate, edad.session, edad.session_queue"`.
  - **Exists**: yes, as a procedure; not as anything the gate can run. A real
    install fetches a build backend from the network, the host has none, and the
    gate runs under `network_access: deny`.
  - **Observes**: that the metadata the `pyproject-metadata` seam checked actually
    produces an install from which the three modules resolve outside the checkout.
  - **Discharges**: D4 — as the verbatim transcript in the ticket's *Before
    approving*, the way T017 recorded its docker probes.

- **`git-tag`** (hand-run; not an acceptance command)
  - **Where**: `git tag v0.1.0` on the merge commit, pushed to `Cognome-Inc/edad_harness`.
  - **Exists**: as a procedure. A tag is repository state; a gate running inside
    `.edad/worktrees/<ticket>` cannot observe whether one exists on a commit that
    does not exist yet.
  - **Observes**: that the pinned install line in QUICKSTART resolves.
  - **Discharges**: D6.

Decisions with no seam: none. D4 and D6 are `unenforced` with the reasons above
rather than silently prose.

## Implementation decisions

One file gains three tables and one doc changes two lines.

The distribution is built by setuptools, the backend pip assumes and the only sane
choice on a host that has no backend at all. Its packages are named explicitly rather
than auto-discovered, because setuptools' flat-layout discovery would see the test
directories beside the package and refuse. The distribution is named after the repo;
the import name stays `edad`. The version is a static string in the project metadata
and nowhere else — `importlib.metadata` answers "which version" for an installed
package, so nothing is added to the package's `__init__`. Python 3.12 is the floor
because the agent image is 3.12 and the host is 3.13.

The single runtime dependency is declared loose. The gate already refuses to run
unless PyYAML matches the exact pin in the gate's requirements file, so the project
metadata does not need to repeat that pin; it only needs to not conflict with a target
venv. Loose at install, exact at gate — the two checks have different jobs, and
folding them together would make every future bump a two-file edit with a conflict
window between them.

No console script is added. `python3 -m edad.*` is the spelling every doc, skill,
error message and the T017 host allowlist knows, and a second spelling would be one
none of them know.

QUICKSTART's install section replaces the `PYTHONPATH` line with two pip lines: the
pinned-by-tag form as the default for a target's team, and the editable form for
harness developers. The pinned form is what makes the harness's own thesis apply to
the harness — a teammate's gate verdict becomes a property of a named harness
version rather than of whichever commit they have checked out. That form only works
if the tag exists, so tagging the merge is a recorded operator step.

The install itself is proven by hand at approval and transcribed into the ticket. The
gate cannot run it: it needs a build backend from the network and the gate runs with
the network denied. Pinning setuptools in the gate's requirements to allow an offline
in-gate install was considered and rejected as a permanent toolchain pin on every
machine and in the agent image for one ticket's benefit.

## Out of scope

- **Both Dockerfiles.** The agent image runs the *target's* tests, not `edad`; the
  egress image copies its two files directly. Nothing in either container imports the
  harness, so nothing installs it. (Grill: "Not in scope".)
- **The worktree-shadowing trap.** An editable install makes `edad` importable from
  site-packages; a gate run in `.edad/worktrees/<ticket>` still imports the
  worktree's `edad` because pytest's `pythonpath = ["."]` and `-m`'s cwd-first rule
  both put the worktree ahead of site-packages. Python semantics, not this ticket's
  work; recorded as a fact in the grill.
- **Recording the harness version in evidence records**, and with it who bumps
  `0.1.0` and when. Its own ticket; see Further notes.
- **Scaffolding a target repo** (`requirements-gate.txt` copy, `.claude/skills/`
  copy) — the same folklore problem as `PYTHONPATH`, and a candidate for a later
  `python3 -m edad.init`. Not raised in this grill; needs its own.

## Further notes

- **Next ticket, handed on rather than deferred.** Evidence records currently name
  the target commit but not the harness that judged it. Once teammates pin by tag,
  the record should carry `importlib.metadata.version("edad-harness")`, and the
  version-bump discipline (when `0.1.0` moves, who moves it, tag-on-merge as a rule
  rather than a one-off D6) belongs to that ticket. Needs its own grill.
- **Deferred from the grill:** whether a console script is ever added. Cheap to add
  later; revisit if the team asks.
- **Install order in QUICKSTART.** `pip install -r requirements-gate.txt` first pins
  PyYAML to 6.0.2; the harness's `>=6.0` is then already satisfied and pip leaves it
  alone. The reverse order resolves the same way after the second command, so the
  order is a matter of not doing redundant work, not of correctness. Not a decision.
- **For `to-tickets`.** All four enforced decisions share one frozen file and one
  seam family, and D1–D4 share one scope path, so this is one ticket. D5's second
  node cross-reads `pyproject.toml`, so the ticket's scope must include both
  `pyproject.toml` and `QUICKSTART.md` — it does. D6 has an empty scope by design.
  The frozen test must pass `ruff check .` with the pinned rule set, as every frozen
  file does.
- **Amendment trail.** D5 was reworded and D6 added at `to-spec` on 2026-09-11, with
  the user's agreement, in the grill record first and then carried here — the
  decisions block below is a copy of the grill's, not an edit of it.

## Decisions

Carried from `.edad/grills/pip-installable.md` verbatim; `seam:` is the only field
added. Four enforced (D1, D2, D3, D5), two unenforced (D4, D6).

```yaml
decisions:
  - id: D1
    decision: setuptools-built distribution `edad-harness` 0.1.0, packages exactly ["edad"], requires-python >=3.12
    verify:
      - python3 -m pytest tests/test_packaging.py::test_build_system_is_setuptools -q
      - python3 -m pytest tests/test_packaging.py::test_project_metadata_names_the_distribution -q
      - python3 -m pytest tests/test_packaging.py::test_packages_is_exactly_edad -q
    frozen:
      - tests/test_packaging.py
    scope:
      - pyproject.toml
    seam: pyproject-metadata
    rejected: hatchling or flit as backend — nothing on the host has any backend; setuptools is what pip assumes
  - id: D2
    decision: PyYAML>=6.0 is the only runtime dependency; the exact pin stays in requirements-gate.txt
    verify:
      - python3 -m pytest tests/test_packaging.py::test_pyyaml_is_the_only_dependency_and_is_loose -q
    frozen:
      - tests/test_packaging.py
    scope:
      - pyproject.toml
    seam: pyproject-metadata
    rejected: PyYAML==6.0.2 in [project] — duplicates the gate's pin and conflicts with target venvs
  - id: D3
    decision: no console script; python3 -m edad.* remains the only invocation
    verify:
      - python3 -m pytest tests/test_packaging.py::test_project_metadata_names_the_distribution -q
    frozen:
      - tests/test_packaging.py
    scope:
      - pyproject.toml
    seam: pyproject-metadata
    rejected: an `edad` entry point — a second spelling no doc, skill or allowlist knows
  - id: D4
    decision: pip install -e works end to end from a fresh venv and resolves edad from another cwd
    unenforced: a real install fetches a build backend; the host has none and the gate runs with network_access deny. Proven by hand at approval and recorded in the ticket.
    scope:
      - pyproject.toml
    seam: editable-install (hand-run)
    rejected: pinning setuptools in requirements-gate.txt to install offline in-gate — a permanent toolchain pin for one ticket
  - id: D5
    decision: QUICKSTART's install section shows the pinned `pip install git+…@v0.1.0` form for a target's team and `pip install -e` for harness developers, and PYTHONPATH appears nowhere in the file
    verify:
      - python3 -m pytest tests/test_packaging.py::test_quickstart_installs_by_pip_not_pythonpath -q
      - python3 -m pytest tests/test_packaging.py::test_quickstart_pinned_tag_matches_project_version -q
    frozen:
      - tests/test_packaging.py
    scope:
      - QUICKSTART.md
    seam: quickstart-text
    rejected: editable install as the only documented form — makes the gate's verdict on a teammate's machine depend on their harness checkout
  - id: D6
    decision: the merge commit of this ticket is tagged v0.1.0 so the pinned install line resolves
    unenforced: a git tag is repository state outside the worktree; the gate cannot observe it. Operator step at merge, recorded in the ticket.
    scope: []
    seam: git-tag (hand-run)
    rejected: documenting the pinned form without a tag — a doc line that does not work
deferred:
  - whether a console script is ever added
```
