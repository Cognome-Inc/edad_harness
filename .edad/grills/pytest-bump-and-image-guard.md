---
slug: pytest-bump-and-image-guard
grilled_at: 2026-09-15
---

## Record

Grilled 2026-09-15 against `main` @ `220f7db` (PR #5 merged: T023, refused-iteration
logging — the prerequisite every earlier spec named for this one). Input: Dependabot
PR #1, "Bump pytest from 8.4.2 to 9.0.3" (branch `dependabot/pip/pip-590e9db7b9`, a
one-line change to `requirements-gate.txt`), and the deferrals to "the bump ticket"
in `.edad/specs/harness-identity.md:183-185`, `.edad/specs/gate-refusal.md:107-109`
and `.edad/specs/gate-trusted-inputs-from-base.md:24-25`. Those specs assumed the
bump would be an agent night that "owns how its own agent's gate survives the pin
change". The facts below show the agent cannot do the part that matters, and the
design changed shape accordingly: the bump is an operator act, and the ticket is the
harness guard the bump exposes the need for.

### Facts established by running, not asking

- **The parsers survive 9.0.3.** In a throwaway venv (`pytest==9.0.3`,
  `ruff==0.15.18`, `PyYAML==6.0.2`, `-e .`) this repo's suite is **260 passed**. A
  three-case probe file (one fail, one pass, one fixture error) prints byte-identical
  summary lines under 8.4.2 and 9.0.3: `FAILED test_probe.py::test_fails - assert 0`,
  `ERROR test_probe.py::test_errors - RuntimeError: x`. The gate's two regexes
  (`PYTEST_FAILURE_RE = ^(?:FAILED|ERROR) (\S+)`, `PYTEST_FAILED_RE = ^FAILED (\S+)`,
  `edad/gate.py:577,585`) match both. This is the "parser probe first" that
  harness-identity asked for; it is done.
- Every `8.4.2` literal in `tests/` lives in a fake pins file or dict
  (`test_gate_refusal.py:23`, `test_gate_trusted_inputs.py:39`,
  `test_harness_identity.py:246,418`), never in a read of the real
  `requirements-gate.txt`. The bump changes no test.
- **Host and image are both at 8.4.2.** `python3 -m pytest --version` on the host
  and `docker run --rm edad-agent:latest python3 -m pytest --version` both print
  `pytest 8.4.2`. `Dockerfile.agent` bakes the pins at build time
  (`COPY requirements-gate.txt` + `pip install -r`), so the image only follows a
  bump when rebuilt.
- **The agent cannot install 9.0.3.** The egress proxy's allowlist is exactly
  `{"api.anthropic.com"}` (`edad/egress_proxy.py:18`). An agent night for the bump
  would run its own `python3 -m pytest` under 8.4.2 whatever the pin says.
- **The host cannot satisfy approve and evaluate in one night.** `_probe_versions`
  (`edad/gate.py:651`) runs the host's `python3 -c importlib.metadata.version(...)`
  with `cwd=root`; `_pinned_versions` reads `root/requirements-gate.txt`. `approve`
  measures the checkout (pins 8.4.2 before the bump); `evaluate` measures the
  worktree (pins 9.0.3 after the agent's edit). Same host, two different required
  versions.
- **Nothing measures the image's toolchain.** `preflight` (`edad/session.py:99`)
  checks the host via `gate_toolchain_problems`; `validate_network` probes the
  image for egress, proxy refusal and proxy permission, never for versions. After
  any bump a stale image runs the agent under old tools while the host gate judges
  under new ones, silently.
- **`validate_network`'s probe sequence is frozen.** T016's
  `tests/test_session_network.py::test_an_internal_network_is_accepted` asserts
  `probes.calls == [("internal", NAME), ("egress", NAME, IMAGE), ("refuses", NAME,
  IMAGE), ("permits", NAME, IMAGE)]`. A probe added inside `validate_network`
  breaks a done ticket's frozen file.
- The queue calls `validate_network` once at plan time (`session_queue.prepare_tier`,
  `edad/session_queue.py:1044`) and the session calls it from `preflight`; both
  turn `Abort` into a refusal. A guard only the session ran would cost a stale
  image two nights before `no_progress` fires.
- `probe_container(network, image, script)` (`edad/session.py:212`) already runs
  `python3 -c script` in a throwaway container and returns `None` when the
  container could not run — the seam the guard needs exists.
- Every existing `preflight(...)` call in the frozen suites passes sandbox `"none"`
  (`tests/test_gate_trusted_inputs.py:342`); a docker-only guard is invisible to them.
- The evidence record's `toolchain` block is `{"pytest": "8.4.2", "ruff":
  "0.15.18", "PyYAML": "6.0.2"}` (`.edad/evidence/T023.json`) — host-measured at
  evaluate time. It is the natural evidence that a bump took effect.
- `docker_tests/test_properties.py` is the one place the tier's claims meet a real
  daemon: hand-written, hand-run, opt-in via `EDAD_DOCKER_TESTS=1`, outside
  `testpaths`; "its deliverable is a test file, so there is no ticket" (its D12).
- QUICKSTART has a `## Releasing` section (one commit bumping `pyproject.toml`
  version and the pinned install line, PR, tag on the merge commit) and no
  pin-bump procedure. Current version `0.1.0`, tag `v0.1.0`.

### Round 1 — what this ticket is

**D1 — The bump is an operator act, not an agent night.** The one-line pin change
is merged by hand after the host and the image are at 9.0.3. No ticket, no night,
no evidence record for the bump itself. Rationale: the agent cannot install the new
version, the host cannot serve both `approve` and `evaluate`, and a pin change's
whole risk is "does the environment follow the pin" — which the agent has no hands
on. Unenforced: a process decision; its evidence is D8.
Rejected: an agent night with the operator upgrading host + image between approve
and run — proves T022's pin floor for real, but the environment leads the pin, the
reverse of what a pin is for. Rejected: widening the proxy allowlist to PyPI for
one ticket — the allowlist is the security boundary; a per-ticket hole is the wrong
shape.

**D2 — An image-toolchain guard, as its own agent ticket, landing before the
bump.** A new `validate_image(image, root)` in `edad/session.py`, docker sandbox
only, called right after `validate_network` from both `preflight` (session) and
`prepare_tier` (queue, plan time). `validate_network` and T016's frozen file are
untouched. Frozen test: a new `tests/test_session_image.py` faking
`probe_container` on the `session` module.
Verify:
- `python3 -m pytest tests/test_session_image.py::test_a_stale_image_is_refused_at_preflight_naming_each_tool_and_the_rebuild_command -q`
- `python3 -m pytest tests/test_session_image.py::test_the_queue_refuses_a_stale_image_at_plan_time -q`
- `python3 -m pytest tests/test_session_image.py::test_a_matching_image_is_accepted_after_validate_network_and_asks_once -q`
- `python3 -m pytest tests/test_session_image.py::test_an_unsandboxed_run_never_probes_the_image -q`
Scope: `edad/session.py`, `edad/session_queue.py`, `tests/test_session_image.py`.
Rejected: preflight only — a stale image costs a night before the breaker fires.
Rejected: inside `validate_network`, amending T016's frozen test — a done ticket's
frozen file grows, the pattern T023 refused.

**D3 — Finding 2 from the T023 review stays out.** (A bad `--base-ref` on the
`edad.gate run` CLI surfaces as a bare git traceback when the toolchain also
mismatches.) Different file, different seam; its own tiny ticket later.
Unenforced: a scoping decision.
Rejected: folding it into the guard ticket — one PR, but a scope spanning two
unrelated fixes.

### Round 2 — the guard's shape

**D4 — One probe, metadata versions, every pinned name, exact match.** `validate_image`
runs ONE `python3 -c` script in the image via `probe_container`, on the named
internal network (it reaches nothing there, which is fine — the probe needs no
network), printing `importlib.metadata.version(name)` for every name in the
checkout's `requirements-gate.txt` (`_pinned_versions(root)` — the same pins the
host was checked against moments earlier). Every value must equal its pin. The
refusal names each mismatch and the rebuild command, in this shape (substrings
pinned, prose free): `image edad-agent:latest does not match requirements-gate.txt:
pytest 8.4.2, pinned 9.0.3. Rebuild it: docker build -f Dockerfile.agent -t
edad-agent:latest .` A probe that could not run (`probe_container` → `None`, or a
non-zero exit) refuses too: not measured is not promised, as every other tier probe
holds. With nothing pinned (no `requirements-gate.txt`, or no `==` line in it) no
probe runs: the host check compares nothing in that case, and so does this one.
Amended at `/to-spec` 2026-09-15 after probing the wiring: an always-probe guard in
`prepare_tier` fails four tests in the frozen `tests/test_session_queue.py` wherever
docker is absent — the agent's own container included — because their fixture repo
has no pins file; a no-pins-no-probe guard leaves all 58 green.
Verify:
- `python3 -m pytest tests/test_session_image.py::test_the_image_probe_asks_once_for_every_pinned_name -q`
- `python3 -m pytest tests/test_session_image.py::test_an_image_probe_that_could_not_run_is_refused -q`
Scope: `edad/session.py`, `tests/test_session_image.py`.
Rejected: also probing PATH binaries (`ruff --version`) inside the image — the
image has only pip's binaries, nothing to drift from. Rejected: warn rather than
refuse when unmeasured — a warning at 3am is a log line nobody reads.

**D5 — The bump procedure is written once in QUICKSTART, and its rebuild command
is enforced.** A `## Bumping a gate pin` section. The rebuild command lives in one
constant in `edad/session.py` that both the refusal message and QUICKSTART quote;
a frozen test reads QUICKSTART and asserts the constant appears verbatim (T018's
pinned-line test is the precedent). The section's order, corrected in round 3
(D9): merge the pin PR → `pip install -r requirements-gate.txt` on the host →
approve the next ticket → `--dry-run` a night and EXPECT the image refusal →
rebuild the image → `--dry-run` again, expect none → run that night for real.
Verify:
- `python3 -m pytest tests/test_session_image.py::test_quickstart_quotes_the_rebuild_command_the_refusal_names -q`
Scope: `QUICKSTART.md`, `edad/session.py`, `tests/test_session_image.py`.
Rejected: QUICKSTART only, unenforced — the doc and the message drift. Rejected:
no doc, the refusal is the procedure — the operator learns the order by being
refused.

**D6 — PR #1 merges as-is once the guard is on main.** Dependabot keeps its
provenance; the pins header was already reworded by T019; nothing else to review.
Verify (after the merge, on main):
- `python3 -c "assert 'pytest==9.0.3' in open('requirements-gate.txt').read()"`
Scope: `requirements-gate.txt` (the PR's one line; not agent-touched).
Rejected: close PR #1 for a hand commit — same change, less provenance.

### Round 3 — proof against a real daemon, release, dry-run

**D7 — The guard meets a real image twice, plus one opt-in case.** (a) The guard
ticket's own docker night runs `validate_image` for real at preflight with image
and pins both at 8.4.2: it must pass silently — its evidence record is the proof.
(b) The bump procedure (D5) is the first real refusal: the `--dry-run` between
host install and rebuild MUST refuse naming `pytest 8.4.2, pinned 9.0.3`, and the
one after the rebuild must not. (c) One opt-in case in
`docker_tests/test_properties.py` probing the real image, hand-written and
hand-run per that file's D12 — no ticket, not in any gate.
Verify (hand-run, outside `full_gate`; not a frozen acceptance command):
- `EDAD_DOCKER_TESTS=1 python3 -m pytest docker_tests/test_properties.py -q -k image`
Scope: `docker_tests/test_properties.py`.
Rejected: procedure only — the bump night proves it once and nothing re-proves it.
Rejected: the faked-probe unit test alone — every other tier claim has its one
meeting with a real daemon.

**D8 — Evidence that the bump took effect is the next agent night's record.** Its
`toolchain.pytest` reads `9.0.3`, which is what the pins header promises ("new
records are made under different pins"); the image guard not firing at that
night's preflight is the rest.
Verify (after that night):
- `python3 -c "import json,glob,os; r=json.load(open(max(glob.glob('.edad/evidence/*.json'), key=os.path.getmtime))); assert r['toolchain']['pytest']=='9.0.3', r['toolchain']"`
Scope: none (reads evidence).
Rejected: a hand-run full gate on main with a committed note — human-readable,
nothing enforces it.

**D9 — `validate_image` runs on `--dry-run` too.** `validate_network` stops after
the isolation check on dry-run because the proxy probes spend a model turn; the
image probe is one container start and no model turn, and D5's procedure depends on
dry-run surfacing the refusal. Re-opened from round 2's first draft of the
procedure: with the checkout still at 8.4.2 and the host at 9.0.3, preflight's HOST
toolchain check (`edad/session.py:113`) refuses first, so the image refusal is only
reachable once the pin PR is merged — hence D5's order.
Verify:
- `python3 -m pytest tests/test_session_image.py::test_the_image_probe_runs_on_dry_run -q`
Scope: `edad/session.py`, `tests/test_session_image.py`.
Rejected: skip on dry-run and report it skipped — consistent with the proxy probes,
but the procedure would need a real night to see the refusal.

**D10 — No release for the pin alone; `v0.1.1` after the guard and the bump are
both on main.** One tag marks "records from here are made under pytest 9". Follows
QUICKSTART's `## Releasing` exactly.
Verify (after the release commit):
- `python3 -c "import tomllib; assert tomllib.load(open('pyproject.toml','rb'))['project']['version']=='0.1.1'"`
Scope: `pyproject.toml`, `QUICKSTART.md` (the release commit; operator, not agent).
Rejected: no release at all — the record's toolchain block already says which pins.
Rejected: a release before and after — two releases for one pin.

### Order of operations

1. Guard ticket (D2, D4, D5, D9): grill → `/to-spec` → `/to-tickets` → approve →
   docker night → PR → merge. Its night is D7(a).
2. Merge PR #1 (D6). Host `pip install -r requirements-gate.txt`.
3. Approve the next ticket (finding 2, D3, is the natural candidate). `--dry-run`:
   expect the image refusal (D7(b)). Rebuild. `--dry-run`: clean.
4. Run that night; its record is D8.
5. Release `v0.1.1` (D10). D7(c) whenever convenient.

### Deferred (all cheap to reverse)

- Exact refusal prose beyond the pinned substrings (`image <name> does not match
  requirements-gate.txt`, `<tool> <found>, pinned <want>`, the rebuild command).
- The constant's name (`REBUILD_IMAGE_CMD` or similar), and whether `validate_image`
  takes `root` or an already-read pins list.
- Whether the evidence record should also carry the image's measured versions —
  redundant while the guard enforces equality; leave it out.
- The exact shape of the opt-in `docker_tests` case.
- Whether `validate_image` for a custom `--image NAME` puts NAME into the rebuild
  command's `-t` (it should; trivial).

## Decisions

```yaml
decisions:
  - id: D1
    decision: The pytest 8.4.2 -> 9.0.3 bump is an operator act (host install, image rebuild, merge PR #1), not an agent night; no ticket and no evidence record for the pin change itself
    unenforced: a process decision; its effect is checked by D8
    scope:
      - requirements-gate.txt
    rejected: an agent night with the operator switching host/image between approve and run — the environment would lead the pin; widening the proxy allowlist to PyPI for one ticket — the allowlist is the security boundary
  - id: D2
    decision: A new validate_image(image, root) in edad/session.py, docker sandbox only, called right after validate_network from both preflight and session_queue.prepare_tier; validate_network and T016's frozen test untouched; a new frozen test file fakes probe_container on the session module
    verify:
      - python3 -m pytest tests/test_session_image.py::test_a_stale_image_is_refused_at_preflight_naming_each_tool_and_the_rebuild_command -q
      - python3 -m pytest tests/test_session_image.py::test_the_queue_refuses_a_stale_image_at_plan_time -q
      - python3 -m pytest tests/test_session_image.py::test_a_matching_image_is_accepted_after_validate_network_and_asks_once -q
      - python3 -m pytest tests/test_session_image.py::test_an_unsandboxed_run_never_probes_the_image -q
    frozen:
      - tests/test_session_image.py
    scope:
      - edad/session.py
      - edad/session_queue.py
      - tests/test_session_image.py
    rejected: preflight only — a stale image costs a night before no_progress fires; inside validate_network with T016's frozen test amended — a done ticket's frozen file grows
  - id: D3
    decision: T023 review finding 2 (bare git traceback on a bad --base-ref via the edad.gate run CLI when the toolchain also mismatches) is not part of this design; its own ticket later
    unenforced: a scoping decision
    scope: []
    rejected: folding it into the guard ticket — one PR, but a scope spanning two unrelated fixes in two files
  - id: D4
    decision: validate_image runs one python3 -c script in the image via probe_container on the named network, printing importlib.metadata versions for every name in the checkout's requirements-gate.txt; every value must equal its pin; the refusal names each mismatch as "<tool> <found>, pinned <want>" under the prefix "image <name> does not match requirements-gate.txt" and quotes the rebuild command; a probe that could not run refuses; with nothing pinned no probe runs, as the host check compares nothing
    verify:
      - python3 -m pytest tests/test_session_image.py::test_the_image_probe_asks_once_for_every_pinned_name -q
      - python3 -m pytest tests/test_session_image.py::test_an_image_probe_that_could_not_run_is_refused -q
    frozen:
      - tests/test_session_image.py
    scope:
      - edad/session.py
      - tests/test_session_image.py
    rejected: also probing PATH binaries inside the image — only pip's binaries exist there; warn instead of refuse when unmeasured — every other tier probe refuses
  - id: D5
    decision: QUICKSTART gains a "## Bumping a gate pin" section with the order merge pin PR -> host pip install -> approve next ticket -> --dry-run expecting the image refusal -> rebuild -> --dry-run clean -> real night; the rebuild command is one constant in edad/session.py quoted by both the refusal and QUICKSTART, tied by a frozen test
    verify:
      - python3 -m pytest tests/test_session_image.py::test_quickstart_quotes_the_rebuild_command_the_refusal_names -q
    frozen:
      - tests/test_session_image.py
    scope:
      - QUICKSTART.md
      - edad/session.py
      - tests/test_session_image.py
    rejected: QUICKSTART only, unenforced — doc and message drift; no doc — the operator learns the order by being refused
  - id: D6
    decision: Dependabot PR #1 merges as-is once the guard is on main; no hand commit
    verify:
      - python3 -c "assert 'pytest==9.0.3' in open('requirements-gate.txt').read()"
    frozen: []
    scope:
      - requirements-gate.txt
    rejected: close PR #1 for an operator commit — same change, less provenance
  - id: D7
    decision: The guard meets a real image at the guard ticket's own docker night (must pass silently), at the bump procedure's two dry-runs (refuse, then pass), and in one opt-in hand-run case in docker_tests/test_properties.py; none of these is a frozen acceptance command
    verify:
      - EDAD_DOCKER_TESTS=1 python3 -m pytest docker_tests/test_properties.py -q -k image
    frozen: []
    scope:
      - docker_tests/test_properties.py
    rejected: procedure only — nothing re-proves it later; the faked-probe unit test alone — every other tier claim has one meeting with a real daemon
  - id: D8
    decision: Evidence that the bump took effect is the next agent night's record, whose toolchain.pytest reads 9.0.3, with the image guard not firing at that night's preflight
    verify:
      - python3 -c "import json,glob,os; r=json.load(open(max(glob.glob('.edad/evidence/*.json'), key=os.path.getmtime))); assert r['toolchain']['pytest']=='9.0.3', r['toolchain']"
    frozen: []
    scope: []
    rejected: a hand-run full gate on main with a committed note — nothing enforces it
  - id: D9
    decision: validate_image runs on --dry-run too (one container start, no model turn); the image refusal is reachable only after the pin PR is merged, because preflight's host toolchain check refuses first otherwise — which fixes D5's order
    verify:
      - python3 -m pytest tests/test_session_image.py::test_the_image_probe_runs_on_dry_run -q
    frozen:
      - tests/test_session_image.py
    scope:
      - edad/session.py
      - tests/test_session_image.py
    rejected: skip on dry-run and report it skipped — the procedure would need a real night to see the refusal
  - id: D10
    decision: No release for the pin alone; tag v0.1.1 after the guard ticket and PR #1 are both on main, per QUICKSTART's Releasing section
    verify:
      - python3 -c "import tomllib; assert tomllib.load(open('pyproject.toml','rb'))['project']['version']=='0.1.1'"
    frozen: []
    scope:
      - pyproject.toml
      - QUICKSTART.md
    rejected: no release at all — the record already says which pins; a release before and after — two releases for one pin
deferred:
  - Exact refusal prose beyond the pinned substrings
  - The rebuild constant's name; whether validate_image takes root or a pins list
  - Whether the evidence record also carries the image's measured versions (redundant while the guard enforces equality)
  - The exact shape of the opt-in docker_tests case
  - A custom --image NAME goes into the rebuild command's -t
```
