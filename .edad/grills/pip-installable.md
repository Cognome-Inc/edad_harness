---
slug: pip-installable
grilled_at: 2026-09-11
amended_at: 2026-09-11
---

## Record

Grilled 2026-09-11 on `Cognome-Inc/edad_harness` @ `efb21cc`, the first ticket in the
canonical repo. Origin: the harness is about to be used against ai-sniffer by a team,
and "set `PYTHONPATH` to the harness checkout" is folklore that does not survive a
second machine. The goal is one `[project]` block so a target repo's venv can
`pip install -e /path/to/edad_harness` and `python3 -m edad.gate` resolves from
anywhere.

Facts established before the interview, by reading rather than asking: `edad/` has
exactly one third-party import (`yaml`); the host has Python 3.13 and pip 26 but no
setuptools, hatchling or flit_core, so any real install fetches a backend from the
network; the agent image is `python:3.12`; `Dockerfile.egress` copies
`edad/__init__.py` and `edad/egress_proxy.py` directly and installs nothing;
setuptools flat-layout auto-discovery would see `tests/` and `docker_tests/` beside
`edad/` and refuse, so packages must be named; every doc, skill and error message
invokes the harness as `python3 -m edad.{gate,session,session_queue}`; and
`gate_toolchain_problems` (`edad/gate.py:600`) checks every `==` line in
`requirements-gate.txt`, PyYAML included, in any environment the gate runs in.

**D1 — the package.** setuptools, because it is the backend pip assumes and nothing
else is on the host either; `packages = ["edad"]` explicitly, for the auto-discovery
reason above; distribution name `edad-harness` (matches the repo; the import name
stays `edad`); static `version = "0.1.0"` in pyproject only, nothing added to
`edad/__init__.py`; `requires-python = ">=3.12"` because the image is 3.12 and the
host 3.13; `[build-system]` `requires = ["setuptools>=68"]`,
`build-backend = "setuptools.build_meta"`. All accepted as proposed. Scope:
`pyproject.toml`.

**D2 — the dependency spec.** `PyYAML>=6.0`. The gate already refuses to run unless
PyYAML is exactly `6.0.2`, via `requirements-gate.txt`, so the `[project]` spec only
decides whether `pip install -e` conflicts with a target venv's own pins. Loose at
install, exact at gate: the two checks do different jobs.
Rejected: `PyYAML==6.0.2` — duplicates the pin, and every future bump becomes a
two-file edit with a conflict window between them.

**D3 — no console script.** `python3 -m edad.*` stays the only spelling. A console
script would be nicer to type but creates a second spelling that no doc, skill or
test knows, and the T017 host allowlist is built from ticket commands spelled the
`-m` way.
Rejected: an `edad` entry point — revisit if the team asks; cheap to add later.
Note for `to-tickets`: "no `[project.scripts]`" is green at base by absence, so it
is not its own test; it is an assertion inside the metadata test, which is red at
base because `[project]` does not exist.

**D4 — the install itself is proven by hand, not by the gate.** A real
`pip install -e .` needs a backend the host does not have, so under
`network_access: deny` no acceptance command can run one. At approval: fresh venv,
`pip install -e .`, then from a *different* cwd `python -m edad.gate --help` and
`python -c "import edad.gate, edad.session, edad.session_queue"`, recorded verbatim
in the ticket's *Before approving*, as T017 did for its docker probes.
Rejected: adding `setuptools==<ver>` to `requirements-gate.txt` so
`pip install --no-build-isolation --no-deps -e .` could run offline in-gate —
stronger evidence, but setuptools would become a gate-checked pin on every machine
and in the agent image forever, for one ticket's benefit.

**D5 — QUICKSTART installs by pip, in two forms, and never mentions `PYTHONPATH`.**
*Amended 2026-09-11 at `to-spec`.* The first cut said only `pip install -e
/path/to/edad_harness`. That is right for someone developing the harness and wrong as
the default for a teammate on the target: an editable install makes the gate's verdict
on their machine a function of whichever harness commit they have checked out — the
same disease `requirements-gate.txt` cures for pytest and ruff, with the harness itself
as the unpinned tool. The same `[project]` block also enables
`pip install git+https://github.com/Cognome-Inc/edad_harness@v0.1.0`, a fixed version
with no local clone. So the install section shows the pinned form for a target's team
and the `-e` form for harness developers, and the `PYTHONPATH` line goes. Enforced by
two nodes in the same frozen file: one that the text says both forms and says
`PYTHONPATH` nowhere in the file (whole file, not just the section — moving the line
under another heading must not pass), and one that the tag in the pinned line matches
`[project].version`, because the doc describing a pyproject is the cheapest drift to
prevent. Scope: `QUICKSTART.md`.

**D6 — the merge is tagged `v0.1.0`.** The pinned install line only resolves if the tag
exists, and the tag can only exist once the pyproject has landed, so it is an
operator step at merge, not something the worktree can carry. Unenforced: a tag is
repository state the gate cannot see from inside a worktree. Recorded here so it is a
decision someone owns rather than a line in a doc that quietly does not work.

**Not in scope, and why.** Neither Dockerfile: the agent image runs the *target's*
tests, not `edad`, and the egress image copies its two files directly. Rejected:
installing the package into the agent image — nothing in the container imports it.

**Noted, not decided.** An editable install makes `edad` importable from
site-packages, which is the worktree-shadowing trap: a gate run in
`.edad/worktrees/<ticket>` must import the worktree's `edad`, not the main
checkout's. Here it is neutralised by `pythonpath = ["."]` (pytest puts it first on
`sys.path`) and by `-m` putting cwd first. That is Python semantics rather than
anything this ticket changes, so it is recorded as a fact, not a decision.

**Deferred, cheap to reverse.** Whether a console script is ever added.

**Handed to the next ticket, not deferred.** When `0.1.0` moves and who bumps it was
deferred in the first cut. Once teammates pin to the tag it stops being cheap: the
version is what an evidence record should name as the tool that produced it
(`importlib.metadata.version("edad-harness")`, so nothing is added to
`edad/__init__.py`). That is its own ticket — evidence records carry the harness
version — and the bump discipline belongs to it.

## Decisions

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
    rejected: hatchling or flit as backend — nothing on the host has any backend; setuptools is what pip assumes
  - id: D2
    decision: PyYAML>=6.0 is the only runtime dependency; the exact pin stays in requirements-gate.txt
    verify:
      - python3 -m pytest tests/test_packaging.py::test_pyyaml_is_the_only_dependency_and_is_loose -q
    frozen:
      - tests/test_packaging.py
    scope:
      - pyproject.toml
    rejected: PyYAML==6.0.2 in [project] — duplicates the gate's pin and conflicts with target venvs
  - id: D3
    decision: no console script; python3 -m edad.* remains the only invocation
    verify:
      - python3 -m pytest tests/test_packaging.py::test_project_metadata_names_the_distribution -q
    frozen:
      - tests/test_packaging.py
    scope:
      - pyproject.toml
    rejected: an `edad` entry point — a second spelling no doc, skill or allowlist knows
  - id: D4
    decision: pip install -e works end to end from a fresh venv and resolves edad from another cwd
    unenforced: a real install fetches a build backend; the host has none and the gate runs with network_access deny. Proven by hand at approval and recorded in the ticket.
    scope:
      - pyproject.toml
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
    rejected: editable install as the only documented form — makes the gate's verdict on a teammate's machine depend on their harness checkout
  - id: D6
    decision: the merge commit of this ticket is tagged v0.1.0 so the pinned install line resolves
    unenforced: a git tag is repository state outside the worktree; the gate cannot observe it. Operator step at merge, recorded in the ticket.
    scope: []
    rejected: documenting the pinned form without a tag — a doc line that does not work
deferred:
  - whether a console script is ever added
```
