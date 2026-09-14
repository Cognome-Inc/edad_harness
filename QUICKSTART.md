# EDAD — quickstart

A gate runner for agent-written code. A ticket names the acceptance tests an
agent must make pass, the files it may touch, and the conditions under which
it is stopped. The tests are hashed at approval and the agent cannot edit
them; a run is judged by the gate, never by the agent's own report.

The harness is a tool. It runs *against* a target repo — the one whose code
the agent changes — and keeps that repo's tickets, locks and evidence under
`<target>/.edad/`. This repo holds only the harness and its own tests.

## Install

Into the target repo's environment:

    pip install -r requirements-gate.txt      # the gate's pins, exact
    pip install git+https://github.com/Cognome-Inc/edad_harness@v0.1.0   # the harness, pinned

Developing the harness itself? Install your checkout editable instead, so
edits are live: `pip install -e /path/to/edad_harness`.

The target repo needs, at its root:

- `requirements-gate.txt` — a copy of this repo's. The gate refuses to run on
  mismatched pins: its verdict must be a property of the commit, not of
  whatever was installed that day.
- `.edad/tickets/`, `.edad/grills/`, `.edad/specs/` — the harness creates
  only the directories it writes to itself.
- `.gitignore` entries for `.edad/records/ sessions/ worktrees/ runs/`.
  Evidence and hashes are deliberately committed — see this repo's
  `.gitignore` for the reasoning.
- `.claude/skills/` — copy this repo's. The method ships with the harness.
- If `ruff check .` is going in `full_gate`: a pinned `[tool.ruff.lint]
  select` in its pyproject, for the same reason as the pins.

## Validate the rig before any agent touches it

Write one throwaway ticket, `T001`, against something small and pure in the
target, with a `mutation:` block (brownfield: the test is green on day one,
so the proof is that it dies under a named edit). Then, from the target root:

    python3 -m edad.gate approve T001     # hashes the frozen tests; runs the proof
    python3 -m edad.gate run T001         # => PASS

Now break each check by hand and confirm the gate sees it:

| scenario                          | freeze | scope | commands |
|-----------------------------------|--------|-------|----------|
| correct, in scope                 | PASS   | PASS  | PASS     |
| acceptance not yet met            | PASS   | PASS  | FAIL     |
| frozen test edited                | FAIL   | -     | not run  |
| touched files outside `scope`     | PASS   | FAIL  | PASS     |

Row three is the whole thesis: a tampered acceptance test is never executed,
so a passing suite cannot launder a weakened contract. Delete the ticket
afterwards; the rig is validated against *that* tree.

## Run

    python3 -m edad.session run T00N                        # host tier, you watch
    python3 -m edad.session run T00N --sandbox docker       # container, unattended
    python3 -m edad.session_queue run T00N T00M ...         # a night's queue

The docker tier needs `Dockerfile.agent` built as `edad-agent:latest` plus
the target's own test dependencies layered on top (`--image` names the
result), and `Dockerfile.egress` as `edad-egress:latest`. Inside the
container the agent runs with permissions bypassed — the container is the
boundary. On the host it is allowed exactly the ticket's own gate commands.

## Evidence

Every run writes `.edad/records/<ticket>-<ts>-<sha>.json`: commit, per-check
verdict, per-command exit code, duration, output tail. That file is the
record. The agent's own summary of its work is not an input to it. Two more
blocks say who ran it: `harness` carries the running harness's version,
commit, dirtiness and install source, and `toolchain` carries the pinned
tools' versions as the gate measured them before running. When a ticket
passes its full gate the controller promotes the record to
`.edad/evidence/<ticket>.json`, committed beside the code it verifies.

## Releasing

A release is one commit, merged by pull request, followed by a tag on the
merge commit. Nothing is bumped per ticket: the commits between releases are
identified in evidence records and locks by `harness.commit`, not by a
version number.

To cut one:

1. In a single commit, bump `version` in `pyproject.toml` and the pinned
   `pip install git+...@vX.Y.Z` line in this file's Install section to match.
   The two must agree — a mismatch here is what the packaging tests catch.
2. Open a pull request with that commit and merge it.
3. On the merge commit, `git tag vX.Y.Z` and `git push origin vX.Y.Z`. Placing
   and pushing the tag is an operator act; nothing in the gate does it for you.

A teammate who installs `git+...@vX.Y.Z` afterwards gets a harness whose
identity block names that tag's commit. Nobody needs to run a release for a
harness change to be identifiable — an editable install or an uninstalled
checkout reports its own commit regardless.

## Where to read next

- `edad/gate.py` — approve, freeze, scope, red and mutation proofs, the
  full_gate baseline ratchet
- `edad/session.py` — worktree + container + `claude -p`, kill conditions,
  gate after every iteration
- `edad/session_queue.py` — many tickets on one run branch, overnight
- `.claude/skills/` — find-seams / grill-me / to-spec / to-tickets / handoff
- `.edad/` — this harness was built with itself; T001–T017 are the record
