---
slug: pytest-bump-and-image-guard
grilled: .edad/grills/pytest-bump-and-image-guard.md
status: draft
---

## Problem statement

Dependabot's PR #1 bumps the gate's pytest pin from 8.4.2 to 9.0.3. Three earlier
specs deferred to "the bump ticket" on the assumption that an agent night would own
it. It cannot. The agent has no route to PyPI (the egress proxy allows one host, the
model API), so it would run the old pytest whatever the pin says; and the host
cannot serve both halves of one night, because `approve` measures the checkout at
the old pin and `evaluate` measures the worktree at the new one.

Underneath that is the real gap. The harness measures the host's toolchain against
the pins before every run, and it probes the agent image for egress and proxy
behaviour — but nothing ever asks the image what versions it carries. The image
bakes the pins in at build time and only follows a bump when rebuilt. After any pin
bump, a stale image runs the agent under old tools while the host gate judges under
new ones, and nothing says so.

## Solution

The bump itself becomes an operator act: install on the host, rebuild the image,
merge the one-line PR. No ticket, no night, no evidence record for the pin change.

What does get a ticket is the guard the bump exposes the need for. A docker-tier
run — session or queue — asks the image, in one throwaway container, for the
installed version of every name pinned in `requirements-gate.txt`, and refuses to
start unless each one matches exactly. The refusal names every mismatch and the
exact rebuild command. A probe that could not run refuses too, on the tier's
standing rule that what was not measured is not promised. The guard runs on
`--dry-run` as well, so an operator can see the refusal without spending a night.

The procedure for bumping a pin is written once in QUICKSTART, in the order the
guard forces, and the rebuild command it quotes is the same constant the refusal
prints — a frozen test ties the two together. After the guard and the bump are both
on main, one release (`v0.1.1`) marks "records from here are made under pytest 9".

## User stories

1. As an operator, I want a run to refuse at preflight when the agent image's
   toolchain does not match the pins, so that a stale image cannot silently run the
   agent under different tools than the gate judging it.
2. As an operator, I want the refusal to name each mismatched tool with the version
   found and the version pinned, and the rebuild command, so that I can fix it
   without diagnosing.
3. As an operator running a queue night, I want the same refusal at plan time,
   before any branch is cut or session spawned, so that a stale image costs seconds
   rather than a night of aborts.
4. As an operator, I want the image probe to run on `--dry-run`, so that the bump
   procedure's "expect a refusal, rebuild, expect none" step needs no real night.
5. As an operator, I want a run whose image probe could not execute at all to be
   refused rather than warned, so that an unmeasured image is never treated as a
   matching one.
6. As an operator on the default (unsandboxed) tier, I want the image never
   probed, so that a docker problem cannot refuse a run that never needed docker.
7. As an operator bumping a pin, I want QUICKSTART to give me the order of
   operations and the rebuild command, and a test that fails if the command it
   quotes drifts from the one the refusal prints.
8. As a reader of evidence, I want the first record after the bump to say
   `toolchain.pytest: 9.0.3`, so that which pins a record was made under is in the
   record and not in anyone's memory.

## Seams

- **Image probe** — **Where**: `probe_container` on the `session` module, faked
  the way the T016 `Probes` fixture fakes the four network shell-outs. **Exists**:
  yes. **Observes**: the script handed to the container (so which names it asks
  for, and that it asks once), the image and network handed with it, how many times
  it was called, and what the guard does with each kind of answer — `None`, a
  non-zero exit, a mismatched version, a match. **Discharges**: D4, D9.
- **Session preflight** — **Where**: `preflight(...)` with the docker sandbox,
  the network shell-outs faked as above and the image probe faked beside them.
  **Exists**: yes. **Observes**: that the image probe follows the network checks,
  the refusal text, that sandbox `none` never probes, and that `--dry-run` still
  does. **Discharges**: D2, D9.
- **Queue plan time** — **Where**: `run_queue` with `session_queue.validate_network`
  faked as the frozen queue suite's `Docker` fixture does, plus the image probe
  fake. **Exists**: yes. **Observes**: a stale image becomes the queue's `Refusal`
  before the run branch is cut. **Discharges**: D2.
- **QUICKSTART as text** — **Where**: the file read as text and the constant
  imported from the session module; T018's pinned-install-line test is the
  precedent. **Exists**: yes. **Observes**: the rebuild command the refusal prints
  appears verbatim in the `## Bumping a gate pin` section. **Discharges**: D5.
- **Checkout one-liners** — **Where**: hand-run Python one-liners against the
  checkout on `main`: the pins file, the newest evidence record, `pyproject.toml`.
  **Exists**: yes. **Observes**: the pin landed, the first post-bump record says
  9.0.3, the version was bumped. These are operator checks after operator steps —
  no frozen file, no ticket. **Discharges**: D6, D8, D10.
- **Real daemon** — **Where**: `docker_tests/test_properties.py`, opt-in via
  `EDAD_DOCKER_TESTS=1`, outside `testpaths`, hand-run. **Exists**: yes.
  **Observes**: the guard against the real image. Alongside it, two live meetings
  that are not tests at all: the guard ticket's own docker night passing silently,
  and the bump procedure's two dry-runs. **Discharges**: D7.

No new seams. Every enforced decision has one. D1 and D3 have none, and say so:
D1 is a process decision (its effect is what D8 checks) and D3 is a scoping
decision.

## Implementation decisions

**The guard.** One new function in the session module, docker tier only. It reads
the checkout's pins — the same list the host was just checked against — and, if
there is at least one, runs a single Python script in a throwaway container on the
named internal network, printing the installed version of each pinned name. Every
value must equal its pin. Any mismatch, a container that could not run, or a
non-zero exit is a refusal in the tier's usual shape. With nothing pinned no probe
runs, exactly as the host check compares nothing in that case. That last clause
was settled by running the two candidate wirings against the frozen queue suite:
an always-probe guard fails four done tests wherever docker is absent — including
inside the agent's own container, where its gate runs — because their fixture repo
has no pins file. The probe needs no network to do its job; the named network is
just where every other tier probe runs.

**Where it is called.** Right after the network validation, from both places that
call it: the session's preflight and the queue's plan-time tier preparation. The
network validation itself and the done ticket that froze its probe sequence are
untouched. The queue's tier preparation gains the repository root as an argument
(its only caller already has it; the frozen fake for the network call accepts any
arguments, so nothing frozen notices). The queue has no image flag yet, so at plan
time it checks the default image; the session checks whichever image it was given.

**Dry-run.** The network validation stops after the isolation check on dry-run
because the proxy probes spend a model turn. The image probe is one container
start and no model turn, so it runs on dry-run too. That is what makes the bump
procedure workable without a real night — and it also fixes the procedure's order:
until the pin PR is merged, the host toolchain check refuses first, so the image
refusal is only reachable after the merge.

**The refusal.** Prefix naming the image and the pins file, one entry per mismatch
as tool, found, pinned, then the rebuild command. The command is one constant that
the refusal and QUICKSTART both quote. Exact prose beyond those pinned substrings
is deferred.

**The procedure.** QUICKSTART gains a `## Bumping a gate pin` section: merge the
pin PR, install the pins on the host, approve the next ticket, dry-run and expect
the image refusal, rebuild, dry-run again and expect none, then run that night for
real. Its first real use is the pytest bump; the night that follows is the
evidence the bump took effect.

**The release.** None for the pin alone. `v0.1.1` after the guard and the bump are
both on main, cut exactly as the existing Releasing section says.

## Out of scope

- The bump itself, as agent work. It is an operator act (D1); no ticket carries it.
- T023 review finding 2 — a bad `--base-ref` on the gate CLI surfacing as a bare
  git traceback when the toolchain also mismatches. Different file, different seam;
  its own small ticket later (D3), and the natural next ticket to approve for the
  bump procedure's dry-run step.
- A queue-level `--image` flag. Still deferred from the sandbox tier; plan time
  checks the default image.
- Widening the egress allowlist to PyPI so an agent could install the new version.
  Rejected in the grill: the allowlist is the security boundary.
- Probing PATH binaries inside the image. Only pip's binaries exist there; nothing
  to drift from.

## Further notes

Order of operations, from the grill: the guard ticket (D2, D4, D5, D9) goes
through `to-tickets`, approval, a docker night, PR and merge — that night is the
guard's first real meeting with an image (D7a). Then merge PR #1 and install the
pins on the host (D6). Approve the next ticket, dry-run expecting the image refusal,
rebuild, dry-run clean (D7b). Run that night; its record is D8. Release `v0.1.1`
(D10). The opt-in docker case (D7c) whenever convenient.

`to-tickets` note: D6, D7, D8 and D10 carry `verify` commands that are hand-run
operator checks after operator steps, with no frozen file. They should not become
agent tickets. The one agent ticket here is D2 + D4 + D5 + D9, with the single
frozen file `tests/test_session_image.py`.

D8's check reads the newest evidence record by modification time, so it is only
meaningful run right after the first post-bump night.

Deferred from the grill, all cheap to reverse:

- Exact refusal prose beyond the pinned substrings.
- The rebuild constant's name; whether the guard takes the root or an already-read
  pins list.
- Whether the evidence record should also carry the image's measured versions —
  redundant while the guard enforces equality, so left out.
- The exact shape of the opt-in `docker_tests` case.
- A custom `--image NAME` goes into the rebuild command's `-t` (it should; trivial).

## Decisions

Carried verbatim from the grill record, with `seam:` added to each entry and
nothing else changed.

```yaml
decisions:
  - id: D1
    decision: The pytest 8.4.2 -> 9.0.3 bump is an operator act (host install, image rebuild, merge PR #1), not an agent night; no ticket and no evidence record for the pin change itself
    unenforced: a process decision; its effect is checked by D8
    scope:
      - requirements-gate.txt
    seam: none (unenforced)
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
    seam: session preflight; queue plan time
    rejected: preflight only — a stale image costs a night before no_progress fires; inside validate_network with T016's frozen test amended — a done ticket's frozen file grows
  - id: D3
    decision: T023 review finding 2 (bare git traceback on a bad --base-ref via the edad.gate run CLI when the toolchain also mismatches) is not part of this design; its own ticket later
    unenforced: a scoping decision
    scope: []
    seam: none (unenforced)
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
    seam: image probe
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
    seam: QUICKSTART as text
    rejected: QUICKSTART only, unenforced — doc and message drift; no doc — the operator learns the order by being refused
  - id: D6
    decision: Dependabot PR #1 merges as-is once the guard is on main; no hand commit
    verify:
      - python3 -c "assert 'pytest==9.0.3' in open('requirements-gate.txt').read()"
    frozen: []
    scope:
      - requirements-gate.txt
    seam: checkout one-liners
    rejected: close PR #1 for an operator commit — same change, less provenance
  - id: D7
    decision: The guard meets a real image at the guard ticket's own docker night (must pass silently), at the bump procedure's two dry-runs (refuse, then pass), and in one opt-in hand-run case in docker_tests/test_properties.py; none of these is a frozen acceptance command
    verify:
      - EDAD_DOCKER_TESTS=1 python3 -m pytest docker_tests/test_properties.py -q -k image
    frozen: []
    scope:
      - docker_tests/test_properties.py
    seam: real daemon
    rejected: procedure only — nothing re-proves it later; the faked-probe unit test alone — every other tier claim has one meeting with a real daemon
  - id: D8
    decision: Evidence that the bump took effect is the next agent night's record, whose toolchain.pytest reads 9.0.3, with the image guard not firing at that night's preflight
    verify:
      - python3 -c "import json,glob,os; r=json.load(open(max(glob.glob('.edad/evidence/*.json'), key=os.path.getmtime))); assert r['toolchain']['pytest']=='9.0.3', r['toolchain']"
    frozen: []
    scope: []
    seam: checkout one-liners
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
    seam: image probe; session preflight
    rejected: skip on dry-run and report it skipped — the procedure would need a real night to see the refusal
  - id: D10
    decision: No release for the pin alone; tag v0.1.1 after the guard ticket and PR #1 are both on main, per QUICKSTART's Releasing section
    verify:
      - python3 -c "import tomllib; assert tomllib.load(open('pyproject.toml','rb'))['project']['version']=='0.1.1'"
    frozen: []
    scope:
      - pyproject.toml
      - QUICKSTART.md
    seam: checkout one-liners
    rejected: no release at all — the record already says which pins; a release before and after — two releases for one pin
deferred:
  - Exact refusal prose beyond the pinned substrings
  - The rebuild constant's name; whether validate_image takes root or a pins list
  - Whether the evidence record also carries the image's measured versions (redundant while the guard enforces equality)
  - The exact shape of the opt-in docker_tests case
  - A custom --image NAME goes into the rebuild command's -t
```
