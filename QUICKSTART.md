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
    pip install git+https://github.com/Cognome-Inc/edad_harness@v0.1.1   # the harness, pinned

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

## Bumping a gate pin

`requirements-gate.txt` pins the versions both the host gate and the agent's
container image are measured against. A docker-tier run refuses to start
unless the image carries exactly those pins, so bumping one takes a few
steps, in the order the guard forces:

1. Merge the pin-bump pull request to `requirements-gate.txt` on `main`.
   Until it merges, the host's own toolchain check refuses first — on the
   old pins there is nothing for the image check to disagree with yet — so
   the image refusal below is only reachable after this merge.
2. Install the new pins into the host's gate environment:

       pip install -r requirements-gate.txt

3. Approve the next ticket as usual.
4. Dry-run a docker-tier night and expect the image refusal, because the
   agent's container still carries the old pins:

       python3 -m edad.session run T00N --sandbox docker --network <name> --dry-run

   The refusal names each stale tool and prints the command that rebuilds
   the base image:

       docker build -f Dockerfile.agent -t edad-agent:latest .

   That alone does not finish the job. The docker tier never runs the agent
   in `edad-agent:latest` itself — it runs it in the image `--image` names,
   built on top of that base with the target's own test dependencies layered
   on, and that layered image keeps the old pin until it is rebuilt in turn.
   Rebuild the base above, then rebuild the `--image` image from its own
   Dockerfile too; skipping the second rebuild just brings the same refusal
   back on the next dry-run.
5. Dry-run once more and expect no refusal:

       python3 -m edad.session run T00N --sandbox docker --network <name> --dry-run

6. Run that night for real: the same command, minus the flag.

## Evidence

Every run writes `.edad/records/<ticket>-<ts>-<sha>.json`: commit, per-check
verdict, per-command exit code, duration, output tail. That file is the
record. The agent's own summary of its work is not an input to it. Two more
blocks say who ran it: `harness` carries the running harness's version,
commit, dirtiness and install source, and `toolchain` carries the pinned
tools' versions as the gate measured them before running. When a ticket
passes its full gate the controller promotes the record to
`.edad/evidence/<ticket>.json`, committed beside the code it verifies.
`base_ref` names the commit the gate compared the worktree's approval lock,
ticket and pin floor against; `null` means the gate was run by hand with no
base, so nothing was compared.

## Which copy judges

The harness develops itself, so every agent worktree carries a full copy of
`edad/` — including `gate.py`, the module that judges it. Two copies are in
play on every night. The judge is the copy the controller process imported:
`python3 -m edad.session` runs with the main checkout as its working
directory and imports `edad` once, so the judge stays the main checkout's
copy for the whole session (the installed harness, for any other target). The
subject is the worktree — the commands the gate runs there import their own
copy, because the working directory wins on `sys.path`.

The record names both, so you never have to guess which copy ran: `harness`
(`harness.commit`) is the judge, `commit` is the subject's HEAD. In a queue
night the judge is the run branch's tip at each child's spawn, so promoting a
`gate.py` change partway through a queue changes which copy judges the
tickets spawned after it.

The one way the two copies collapse into each other is a hand-run from
inside a worktree: `cd <worktree>; python3 -m edad.gate run T` would import
the worktree's own `edad/gate.py` and use it to judge the worktree — the
subject grading itself. The gate refuses that, naming the worktree, before it
checks anything else. Judge from the main checkout instead.

## Releasing

A release is one commit, merged by pull request, followed by a tag on the
merge commit. Nothing is bumped per ticket: the commits between releases are
identified in evidence records and locks by `harness.commit`, not by a
version number.

To cut one:

1. In a single commit, bump `version` in `pyproject.toml`, the pinned
   `pip install git+...@vX.Y.Z` line in this file's Install section, and the
   version literal `tests/test_packaging.py` asserts against `pyproject.toml`.
   The three must agree — a mismatch here is what the packaging tests catch,
   and that test is a frozen file from T018, so a bump edits it outside any
   ticket, on purpose.
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
