"""The gate does not trust the worktree's copy of what it uses to judge the worktree.

The approval lock and the ticket sit under `.edad/`, which `INFRA_PREFIXES` keeps out
of every scope check, and `check_freeze` reads both from the tree it is verifying -
the agent's worktree. So an agent can edit a frozen test, rewrite its hash in the
lock, and pass: the freeze check sees matching hashes and the scope check never
looks. Three lines, demonstrated at HEAD. The ticket's hash and the red proof live in
the same lock and are forgeable in the same edit; `requirements-gate.txt` is read
from the same tree, so stripping the pins makes T021's refusal vacuous.

These pin the fix. When `evaluate` knows the base commit, the worktree's lock and
ticket must be byte-identical to `git show {base}:<path>`, and every name the lock
recorded as pinned at approval must still be pinned; a divergence is a freeze
failure in the record, naming the file and who may change it. `preflight` runs the
same check against the main repo at HEAD, so an uncommitted re-approval or a human's
post-approval pin removal is refused before a worktree exists, never blamed on the
agent. With no base there is no comparison and no `git show`. The frozen T019/T021
suites fake `check_freeze`, `approval_meta` and `changed_files` by lambda, so the
check is additive and those call shapes do not move.

Every case here shells to git against a temporary repository, except the no-base
case. Under `--sandbox docker` that fails for the agent and passes for the verifier;
an environment artifact, not the agent's to work around.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

from edad import gate, session

PROJECT_ROOT = Path(__file__).resolve().parents[1]

HEAD = "a" * 40
HARNESS = {"version": None, "commit": HEAD, "dirty": False, "source": "checkout"}
PINS = {"pytest": "8.4.2", "ruff": "0.15.18"}
TICKET_ID = "T900"
FROZEN = "tests/test_thing.py"
LOCK = f".edad/hashes/{TICKET_ID}.json"
TICKET = f".edad/tickets/{TICKET_ID}.md"
PINFILE = "requirements-gate.txt"

TICKET_TEXT = f"""---
id: {TICKET_ID}
title: a ticket
decisions: [D1]
scope:
  - {PINFILE}
frozen:
  - {FROZEN}
acceptance:
  - python3 -m pytest {FROZEN}::test_one -q
full_gate:
  - python3 -m pytest -q
kill_conditions:
  network_access: deny
---

## Context

A ticket.
"""


# --- helpers ---------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def measured(pins: dict) -> list:
    """A satisfied `Measurement` per pin - the shape T020's tests steer
    `evaluate` with, here kept honest against the repository's own pin file."""
    return [gate.Measurement(name, ver, ver, None) for name, ver in pins.items()]


class FakeRun:
    """Stands in for `run_commands`: every command a clean pass."""

    def __call__(self, root, commands, timeout_s=None, **kw):
        return [
            gate.CommandResult(c, 0, 0.1, "1 passed", [], False, None) for c in commands
        ]


class Repo:
    """A real repository holding an approved ticket: frozen test, ticket, pin
    file and lock, all committed at `base`. The tests then do what an agent's
    iteration does - edit, `git add -A`, commit - and ask the gate.

    The lock is written by hand rather than through `cmd_approve` so the test
    controls its `_edad` block: `toolchain` is the pin floor, `red_proof` is the
    forgeable claim. Hashes are the real `sha256` of the committed files, so
    `check_freeze` is satisfied by every tamper below that rewrites them - which
    is the point."""

    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        self.root = tmp_path / "repo"
        (self.root / "tests").mkdir(parents=True)
        (self.root / ".edad" / "hashes").mkdir(parents=True)
        (self.root / ".edad" / "tickets").mkdir()
        self.write(FROZEN, "def test_one():\n    assert True\n")
        self.write(TICKET, TICKET_TEXT)
        self.write(PINFILE, "".join(f"{n}=={v}\n" for n, v in PINS.items()))
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "gate@example.invalid")
        _git(self.root, "config", "user.name", "edad tests")
        self.write_lock(self.fresh_lock())
        self.base = self.commit("approved")
        self.pins = dict(PINS)
        monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
        monkeypatch.setattr(gate, "run_commands", FakeRun())
        monkeypatch.setattr(gate, "measure_toolchain", lambda root: measured(self.pins))

    # -- files --
    def write(self, rel: str, text: str) -> None:
        (self.root / rel).write_text(text)

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text()

    def commit(self, msg: str) -> str:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", msg)
        return _git(self.root, "rev-parse", "HEAD")

    # -- the lock --
    def fresh_lock(self) -> dict:
        return {
            FROZEN: gate.sha256(self.root / FROZEN),
            gate.LOCK_META_KEY: {
                "ticket_sha256": gate.sha256(self.root / TICKET),
                "decisions": ["D1"],
                "red_proof": [{"command": "python3 -m pytest", "exit_code": 1}],
                "toolchain": dict(PINS),
            },
        }

    def lock(self) -> dict:
        return json.loads(self.read(LOCK))

    def write_lock(self, lock: dict) -> None:
        self.write(LOCK, json.dumps(lock, indent=2) + "\n")

    # -- the gate --
    def ticket(self) -> dict:
        return gate.load_ticket(self.root, TICKET_ID)

    def evaluate(self) -> gate.Record:
        return gate.evaluate(self.root, self.ticket(), "acceptance", self.base)

    # -- tampers, each what an agent's iteration would leave behind --
    def tamper_frozen_and_relock(self) -> str:
        """Edit the frozen test, rewrite its hash in the lock to match, commit."""
        self.write(FROZEN, "def test_one():\n    assert True  # weakened\n")
        lock = self.lock()
        lock[FROZEN] = gate.sha256(self.root / FROZEN)
        self.write_lock(lock)
        return self.commit("iteration 1")

    def tamper_ticket_and_relock(self) -> str:
        """Widen the ticket's scope, rewrite the ticket hash in the lock, commit."""
        widened = TICKET_TEXT.replace(f"  - {PINFILE}\n", f"  - {PINFILE}\n  - edad/gate.py\n")
        self.write(TICKET, widened)
        lock = self.lock()
        lock[gate.LOCK_META_KEY]["ticket_sha256"] = gate.sha256(self.root / TICKET)
        self.write_lock(lock)
        return self.commit("iteration 1")

    def drop_pin(self, name: str) -> str:
        """Remove one pinned tool from the pin file, and from what the gate
        would measure, then commit - an in-scope edit for the fixture ticket."""
        self.pins.pop(name)
        self.write(PINFILE, "".join(f"{n}=={v}\n" for n, v in self.pins.items()))
        return self.commit("iteration 1")


def freeze_violations(rec: gate.Record) -> list[str]:
    """The record's violations minus the ones `check_freeze` already produced
    today, so an assertion here cannot be satisfied by the old check."""
    old = ("frozen file", "ticket modified since approval")
    return [v for v in rec.violations if not v.startswith(old)]


# --- D1, D2: the worktree's lock and ticket must equal base's ----------------------


def test_lock_rewritten_to_match_an_edited_frozen_test_is_refused(tmp_path, monkeypatch):
    """The three-line tamper. `check_freeze` is satisfied - the hash in the
    lock matches the edited test - and the scope check never sees `.edad/`.
    Only a comparison against base can say the lock is not the approved one."""
    repo = Repo(tmp_path, monkeypatch)
    repo.tamper_frozen_and_relock()

    ok, _ = gate.check_freeze(repo.root, repo.ticket())
    assert ok, "precondition: the old check is fooled, or this test proves nothing"

    rec = repo.evaluate()

    assert rec.freeze_ok is False
    assert any(LOCK in v for v in freeze_violations(rec)), rec.violations


def test_ticket_rewritten_in_the_worktree_is_refused(tmp_path, monkeypatch):
    """Scope widened in the worktree and the ticket hash in the lock rewritten
    to match. `check_freeze` passes; the base comparison names the ticket."""
    repo = Repo(tmp_path, monkeypatch)
    repo.tamper_ticket_and_relock()

    ok, _ = gate.check_freeze(repo.root, repo.ticket())
    assert ok, "precondition: the old check is fooled"

    rec = repo.evaluate()

    assert rec.freeze_ok is False
    assert any(TICKET in v for v in freeze_violations(rec)), rec.violations


# --- D3: the pin floor ---------------------------------------------------------------


def test_pinned_name_dropped_since_approval_is_refused(tmp_path, monkeypatch):
    """The lock recorded `ruff` as pinned at approval; the worktree's pin file
    no longer names it. Lock and ticket are untouched and equal base, so this is
    the floor alone: names may not vanish, whatever the values do."""
    repo = Repo(tmp_path, monkeypatch)
    repo.drop_pin("ruff")

    rec = repo.evaluate()

    assert rec.freeze_ok is False
    assert any("ruff" in v for v in freeze_violations(rec)), rec.violations
    assert not any(LOCK in v or TICKET in v for v in rec.violations), (
        "lock and ticket equal base; only the pin should be named"
    )


def test_a_changed_pin_value_is_not_a_divergence(tmp_path, monkeypatch):
    """The bump ticket changes `pytest==8.4.2` to a newer pin. The floor is
    over names, so this passes the trusted-input check; whether the new value
    is installed is T020's mismatch refusal, faked satisfied here."""
    repo = Repo(tmp_path, monkeypatch)
    repo.pins["pytest"] = "9.0.3"
    repo.write(PINFILE, "".join(f"{n}=={v}\n" for n, v in repo.pins.items()))
    repo.commit("iteration 1")

    rec = repo.evaluate()

    assert rec.freeze_ok is True, rec.violations


# --- D4: a freeze failure in the record, not a die --------------------------------


def test_divergence_is_a_freeze_failure_in_the_record_not_a_die(tmp_path, monkeypatch):
    """The outcome is a `Record` the session writes and the existing
    `frozen_file_hash_mismatch` kill reads - not a `Refusal` that leaves
    nothing behind. And a tampered run executes no commands, as today."""
    repo = Repo(tmp_path, monkeypatch)
    repo.tamper_frozen_and_relock()

    rec = repo.evaluate()  # no SystemExit

    assert isinstance(rec, gate.Record)
    assert rec.freeze_ok is False
    assert rec.commands == [], "a tampered run runs nothing"
    assert rec.passed is False
    assert freeze_violations(rec), "the reason is in `violations`, where the kill reads it"


# --- D8: wording, and no base means no comparison ----------------------------------


def test_refusal_wording_names_the_file_and_who_may_change_it(tmp_path, monkeypatch):
    """Three messages, verbatim. Each names the file and says who may change it."""
    repo = Repo(tmp_path, monkeypatch)
    repo.tamper_frozen_and_relock()
    repo.tamper_ticket_and_relock()
    repo.drop_pin("ruff")

    rec = repo.evaluate()

    assert (
        f"approval lock modified since {repo.base}: {LOCK} "
        "(the harness's record of what was approved is not the agent's to edit)"
    ) in rec.violations
    assert (
        f"ticket modified since {repo.base}: {TICKET} (re-approve to adopt the change)"
    ) in rec.violations
    assert (
        "pinned name dropped since approval: ruff (requirements-gate.txt at approval "
        "pinned it; removing a pin is a human commit before re-approval)"
    ) in rec.violations


def test_no_base_ref_makes_no_git_call_and_no_problem(tmp_path, monkeypatch):
    """A hand-run gate has no base to compare against. Nothing is compared,
    `git show` is never run, and the record's `base_ref: null` is the signal.
    Steered the way T021's frozen test steers `evaluate`, so the only git the
    gate may run is the `rev-parse` it already does for the record's commit."""
    calls: list[tuple] = []

    def recording_git(root, *args):
        calls.append(args)
        return HEAD

    monkeypatch.setattr(gate, "git", recording_git)
    monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
    monkeypatch.setattr(gate, "approval_meta", lambda root, ticket_id: {})
    monkeypatch.setattr(gate, "check_freeze", lambda root, ticket: (True, []))
    monkeypatch.setattr(gate, "changed_files", lambda root, base_ref: [])
    monkeypatch.setattr(gate, "run_commands", FakeRun())
    monkeypatch.setattr(gate, "measure_toolchain", lambda root: measured(PINS))
    ticket = {
        "id": TICKET_ID, "frozen": [FROZEN], "scope": [PINFILE],
        "acceptance": ["python3 -m pytest -q"], "kill_conditions": {},
    }

    rec = gate.evaluate(tmp_path, ticket)

    assert rec.base_ref is None
    assert rec.freeze_ok is True, rec.violations
    assert not any("show" in c for c in calls), calls
    assert not any("modified since" in v or "pinned name dropped" in v for v in rec.violations)


# --- D5: preflight refuses before a worktree exists --------------------------------


def preflight(repo: Repo, monkeypatch):
    """`session.preflight` in the temporary repo with everything that is not
    the contract switched off: no API key, a satisfied toolchain, dry run so
    the `claude` CLI is not required, the default sandbox so no docker."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(session, "gate_toolchain_problems", lambda root: [])
    return session.preflight(repo.root, repo.ticket(), "none", dry_run=True)


def test_preflight_refuses_an_uncommitted_or_drifted_contract(tmp_path, monkeypatch):
    """Three drifts the dirty-tree check cannot see - `.edad/` is filtered from
    it - and `check_freeze` cannot either, because each keeps the hashes true.
    Each is refused before any worktree, with the same prefix, naming the cause."""
    repo = Repo(tmp_path, monkeypatch)
    assert preflight(repo, monkeypatch) == [], "precondition: the committed contract passes"
    prefix = "contract drifted since HEAD; re-approve:"

    # A re-approval that was never committed: the lock's `_edad` block changed
    # (here the red proof) while its hashes still match the tree.
    lock = repo.lock()
    lock[gate.LOCK_META_KEY]["red_proof"] = None
    repo.write_lock(lock)
    with pytest.raises(session.Abort) as exc:
        preflight(repo, monkeypatch)
    assert str(exc.value).startswith(prefix), str(exc.value)
    assert LOCK in str(exc.value)
    repo.write_lock(repo.fresh_lock())

    # The ticket edited and the lock's ticket hash updated to match, uncommitted.
    repo.write(TICKET, TICKET_TEXT.replace("title: a ticket", "title: a wider ticket"))
    lock = repo.lock()
    lock[gate.LOCK_META_KEY]["ticket_sha256"] = gate.sha256(repo.root / TICKET)
    repo.write_lock(lock)
    with pytest.raises(session.Abort) as exc:
        preflight(repo, monkeypatch)
    assert str(exc.value).startswith(prefix), str(exc.value)
    assert TICKET in str(exc.value)
    repo.write(TICKET, TICKET_TEXT)
    repo.write_lock(repo.fresh_lock())
    assert _git(repo.root, "status", "--porcelain") == "", "restored to the committed contract"

    # A human removed a pin on main after approval and committed it. Lock and
    # ticket equal HEAD; the lock's floor no longer holds. Refused here, not
    # mid-session where it would read as the agent's doing.
    repo.drop_pin("ruff")
    with pytest.raises(session.Abort) as exc:
        preflight(repo, monkeypatch)
    assert str(exc.value).startswith(prefix), str(exc.value)
    assert "ruff" in str(exc.value)


# --- D6: the quickstart explains a null base_ref -----------------------------------


def test_quickstart_evidence_section_explains_null_base_ref():
    """The record's `base_ref: null` now means "nothing was compared to a
    commit"; the section that describes the record is where a reader learns it."""
    text = (PROJECT_ROOT / "QUICKSTART.md").read_text()
    m = re.search(r"^## Evidence[ \t]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, "QUICKSTART.md has no `## Evidence` section"
    section = m.group(1)
    assert "base_ref" in section, "the field is not named"
    assert "null" in section, "the null case is not explained"
    assert re.search(r"compar", section), "what a null base_ref means for comparison is not said"


# --- D9: the harness line keeps what harness_of preserves ---------------------------


def test_harness_line_keeps_a_partial_blocks_commit(capsys):
    """`harness_of` keeps a commit from a block with no `source` - "no source
    says how to read the commit, not that there was none" - and `report()` is
    where that preservation is finally visible."""
    rec = gate.Record(
        ticket=TICKET_ID, started_at="2026-09-14T00:00:00+00:00", commit=HEAD,
        base_ref=None, gate="acceptance", freeze_ok=True, commands_ok=True,
    )
    rec.harness = {"commit": HEAD, "dirty": True}

    gate.report(rec)
    out = capsys.readouterr().out
    lines = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("harness")]
    assert len(lines) == 1, out
    line = lines[0]

    assert "unknown" in line, "no source is still unknown"
    assert HEAD[:8] in line, "the commit the block recorded is dropped"
    assert "dirty" in line
