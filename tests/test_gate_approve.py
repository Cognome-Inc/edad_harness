"""Approve refuses to lock tests nobody reviewed, or criteria nobody approved.

Review-loops moves the human from reading test lines to approving *what* a
ticket must do - its acceptance, decisions, scope and full gate - and hands the
test lines to a fresh reviewer (T030, T031). This file is the gate's half:

- `approve-criteria <T...>` (D12, D22, D26) records, from a real terminal, the
  operator's git email and a fingerprint of those four fields, in
  `.edad/hashes/<T>.criteria.json`.
- `override-review <T> --reason` (D2, D22) records, from a real terminal, an
  approval of the exact frozen bytes without a review, in
  `.edad/hashes/<T>.override.json`.
- `approve` (D2) refuses unless a passing review round, or an override, matches
  the frozen bytes as they are now, and the criteria still match the ones the
  human approved. Both checks live in `review_problems(root, ticket)` (D25), the
  one name the older frozen stand-ins fake.

The review record, `.edad/hashes/<T>.review.json`, is written by T031. Its shape
is fixed here, because this is the file that reads it:

    {"rounds": [{"round": 1, "verdict": "pass" | "fail", "model": "...",
                 "frozen": {"<frozen path>": "<sha256>"}, "findings": [...]}]}

Every command is driven through `gate.main()` and `sys.argv`, so the parser is
under test too. The terminal is faked by replacing `sys.stdin` (pytest's own
stdin is never a terminal), which deliberately pins the check to
`sys.stdin.isatty()` - D22's "stdin is a TTY" - rather than `os.isatty(0)`.
The operator's email comes from a git config file this test writes and
points `GIT_CONFIG_GLOBAL` at. That keeps the user's
real home directory out, without pinning how the gate asks git.
Everything else approve shells to is faked the way the red-proof tests fake it:
the repo is `tmp_path`, the full-gate probe finds nothing, and every acceptance
command reports a real FAILED, so the red proof is satisfied and the only thing
left to decide approval is the check under test.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from edad import gate
from edad.gate import CommandResult

TICKET = "T900"
OTHER_TICKET = "T901"
FROZEN = "tests/test_thing.py"
# A second frozen file, so a review or override that covers only some of a
# ticket's frozen files is a case the tests can state.
CYCLE = "tests/test_cycle.py"
EMAIL = "operator@example.com"
HARNESS = {"version": "0.0.0", "commit": None, "dirty": None, "source": "test"}
HEX64 = re.compile(r"[0-9a-f]{64}")


def ticket_fields(ticket_id: str = TICKET) -> dict:
    """A complete ticket's frontmatter. The four fields D26 fingerprints are
    acceptance, decisions, scope and full_gate; the rest are here so the test
    can show that changing them moves nothing."""
    return {
        "id": ticket_id,
        "title": f"Order the queue ({ticket_id})",
        "decisions": ["D1"],
        "scope": ["edad/thing.py"],
        "frozen": [FROZEN, CYCLE],
        # Names a different node per ticket, so two tickets' fingerprints differ.
        "acceptance": [f"python3 -m pytest {FROZEN}::test_{ticket_id.lower()}_orders -q"],
        "full_gate": ["python3 -m pytest -q"],
        "blocked_by": [],
        "kill_conditions": {"max_iterations": 4, "max_diff_lines": 100},
    }


def write_ticket(root: Path, fields: dict, body: str = "## Context\n\nOrder the queue.\n") -> None:
    path = root / ".edad" / "tickets" / f"{fields['id']}.md"
    path.write_text("---\n" + yaml.safe_dump(fields, sort_keys=False) + "---\n\n" + body)


def frozen_hashes(root: Path, *paths: str) -> dict[str, str]:
    """What the frozen files (all of them, unless named) hash to right now,
    computed here rather than through the gate, so a wrong hash in the gate
    cannot agree with itself."""
    return {
        p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths or (FROZEN, CYCLE)
    }


def write_review(root: Path, *rounds: tuple[str, dict[str, str]]) -> None:
    """A review record in the shape T031 writes: one entry per round, in order,
    each a (verdict, frozen hashes that round read) pair. Real records hold
    several rounds, because each invocation appends one (D27)."""
    record = {
        "rounds": [
            {
                "round": n,
                "verdict": verdict,
                "model": "claude-opus-5-5",
                "frozen": frozen,
                "findings": [],
            }
            for n, (verdict, frozen) in enumerate(rounds, start=1)
        ]
    }
    (root / ".edad" / "hashes" / f"{TICKET}.review.json").write_text(json.dumps(record))


def record_path(root: Path, ticket_id: str, kind: str) -> Path:
    """`kind` is "criteria", "override" or "review"; "" is the lock itself."""
    name = f"{ticket_id}.{kind}.json" if kind else f"{ticket_id}.json"
    return root / ".edad" / "hashes" / name


def run_failing(root, commands, deny_network, flag_paths=(), timeout_s=900):
    """Every acceptance command reports a real FAILED at the frozen node id it
    names: the red proof is satisfied, so it never decides these tests."""
    results = []
    for command in commands:
        node = next(word for word in command.split() if "::" in word)
        out = f"FAILED {node} - AssertionError\n1 failed in 0.1s\n"
        results.append(CommandResult(command, 1, 0.1, out, [], False, None))
    return results


class Stdin:
    def __init__(self, tty: bool) -> None:
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


def at_terminal(monkeypatch, tty: bool) -> None:
    monkeypatch.setattr(sys, "stdin", Stdin(tty))


def gate_cli(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["edad.gate", *argv])
    return gate.main()


def as_human(monkeypatch, *argv: str) -> int:
    """A human-only command, run by a person at a terminal. Everything else in
    this file runs with no terminal, as the night's re-approval does."""
    at_terminal(monkeypatch, True)
    try:
        return gate_cli(monkeypatch, *argv)
    finally:
        at_terminal(monkeypatch, False)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """A repo holding T900 and T901 with two frozen tests, no terminal (the
    night's view; `as_human` attaches one), and a git email from a config file
    this test owns."""
    (tmp_path / ".edad" / "tickets").mkdir(parents=True)
    (tmp_path / ".edad" / "hashes").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / FROZEN).write_text("def test_orders_the_queue():\n    assert False\n")
    (tmp_path / CYCLE).write_text("def test_refuses_a_cycle():\n    assert False\n")
    write_ticket(tmp_path, ticket_fields(TICKET))
    write_ticket(tmp_path, ticket_fields(OTHER_TICKET))

    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(f"[user]\n\temail = {EMAIL}\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no checkout's local git config is in reach

    monkeypatch.setattr(gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(gate, "run_full_gate_probe", lambda root, ticket: [])
    monkeypatch.setattr(gate, "run_commands", run_failing)
    monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
    at_terminal(monkeypatch, False)
    return tmp_path


def refusal(monkeypatch, *argv: str) -> str:
    with pytest.raises(gate.Refusal) as caught:
        gate_cli(monkeypatch, *argv)
    return str(caught.value)


# --- D2: approve needs a passing review of these exact bytes -----------------------


def test_approve_refuses_without_a_passing_review_for_these_exact_test_bytes(repo, monkeypatch):
    """A review vouches for the bytes it read, and nothing else. Approved
    criteria are in place throughout, so the review is the only thing missing.
    A lock from before this feature, matching the bytes, is in place too: it is
    no exemption (D25), and a refused approve leaves it as it was."""
    assert as_human(monkeypatch, "approve-criteria", TICKET) == 0
    lock = record_path(repo, TICKET, "")
    old_lock = json.dumps({**frozen_hashes(repo), "_edad": {"approved_at": "2026-09-01"}})
    lock.write_text(old_lock)

    # No review record at all.
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == old_lock

    # A failing round over these exact bytes.
    write_review(repo, ("fail", frozen_hashes(repo)))
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == old_lock

    # A passing round that recorded no bytes vouches for none.
    write_review(repo, ("pass", {}))
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == old_lock

    # A passing round that read only one of the two frozen files.
    write_review(repo, ("pass", frozen_hashes(repo, FROZEN)))
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == old_lock

    # The test was edited after a passing round, and the next round over the
    # new bytes failed: the pass belongs to bytes that are gone.
    old_bytes = frozen_hashes(repo)
    (repo / FROZEN).write_text("def test_orders_the_queue():\n    assert True\n")

    # The latest round passed, naming every frozen file, but over the old bytes.
    write_review(repo, ("pass", old_bytes))
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == old_lock

    # As above, and the next round over the new bytes failed.
    write_review(repo, ("pass", old_bytes), ("fail", frozen_hashes(repo)))
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == old_lock

    # A failed round, then a passing round over these exact bytes: approved,
    # with no terminal, and the lock now holds the reviewed bytes.
    write_review(repo, ("fail", old_bytes), ("pass", frozen_hashes(repo)))
    assert gate_cli(monkeypatch, "approve", TICKET) == 0
    written = json.loads(lock.read_text())
    assert {p: written[p] for p in (FROZEN, CYCLE)} == frozen_hashes(repo)


# --- D2: approve needs the criteria a human approved ------------------------------


def test_approve_refuses_when_criteria_changed_since_human_approval(repo, monkeypatch):
    """A review only says the tests fit the criteria. If the criteria moved after
    the human approved them, nobody has approved what the tests now prove."""
    write_review(repo, ("pass", frozen_hashes(repo)))
    lock = record_path(repo, TICKET, "")

    # Never approved.
    assert "criteria" in refusal(monkeypatch, "approve", TICKET).lower()
    assert not lock.exists()

    # Approved, then the acceptance list changed.
    assert as_human(monkeypatch, "approve-criteria", TICKET) == 0
    changed = ticket_fields(TICKET)
    changed["acceptance"] = [*changed["acceptance"], f"python3 -m pytest {FROZEN}::test_cycle -q"]
    write_ticket(repo, changed)
    assert "criteria" in refusal(monkeypatch, "approve", TICKET).lower()
    assert not lock.exists()

    # The human approves the changed criteria: approved.
    assert as_human(monkeypatch, "approve-criteria", TICKET) == 0
    assert gate_cli(monkeypatch, "approve", TICKET) == 0
    assert lock.exists()

    # The decisions list changes: refused again, the new lock left as it is.
    locked = lock.read_text()
    changed["decisions"] = [*changed["decisions"], "D2"]
    write_ticket(repo, changed)
    assert "criteria" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == locked
    assert as_human(monkeypatch, "approve-criteria", TICKET) == 0

    # An override stands in for the review, never for the criteria. The review
    # failed, which is when an override gets used.
    lock.unlink()
    write_review(repo, ("fail", frozen_hashes(repo)))
    assert as_human(monkeypatch, "override-review", TICKET, "--reason", "bootstrap") == 0
    changed["scope"] = [*changed["scope"], "edad/other.py"]
    write_ticket(repo, changed)
    assert "criteria" in refusal(monkeypatch, "approve", TICKET).lower()
    assert not lock.exists()


# --- D2, D22: the override names who approved, and what ----------------------------


def test_human_override_records_who_approved(repo, monkeypatch):
    """The approver is git's user.email, never a typed name, beside the reason,
    the time, and the frozen bytes the override vouches for."""
    assert as_human(monkeypatch, "override-review", TICKET, "--reason", "bootstrap") == 0

    path = record_path(repo, TICKET, "override")
    assert path.exists()
    record = json.loads(path.read_text())
    assert record["approved_by"] == EMAIL
    assert record["reason"] == "bootstrap"
    assert record["frozen"] == frozen_hashes(repo)
    assert datetime.fromisoformat(record["approved_at"]).tzinfo is not None

    # With no git email there is nobody to record: refused, and nothing written.
    path.unlink()
    (repo / "gitconfig").write_text("[user]\n\tname = Operator\n")
    with pytest.raises(gate.Refusal) as caught:
        as_human(monkeypatch, "override-review", TICKET, "--reason", "bootstrap")
    assert "email" in str(caught.value).lower()
    assert not path.exists()


# --- D12, D26: approve-criteria, batch-friendly -------------------------------------


def test_approve_criteria_accepts_several_tickets_and_fingerprints_each(repo, monkeypatch):
    """One terminal session approves a night's batch; each ticket gets its own
    record, and two tickets with different criteria get different fingerprints."""
    assert as_human(monkeypatch, "approve-criteria", TICKET, OTHER_TICKET) == 0

    records = {}
    for ticket_id in (TICKET, OTHER_TICKET):
        path = record_path(repo, ticket_id, "criteria")
        assert path.exists(), ticket_id
        records[ticket_id] = json.loads(path.read_text())
        assert HEX64.fullmatch(records[ticket_id]["sha256"]), ticket_id
        assert records[ticket_id]["approved_by"] == EMAIL
        assert datetime.fromisoformat(records[ticket_id]["approved_at"]).tzinfo is not None
    assert records[TICKET]["sha256"] != records[OTHER_TICKET]["sha256"]

    # With no git email there is nobody to record: refused, and nothing written.
    for ticket_id in (TICKET, OTHER_TICKET):
        record_path(repo, ticket_id, "criteria").unlink()
    (repo / "gitconfig").write_text("[user]\n\tname = Operator\n")
    with pytest.raises(gate.Refusal) as caught:
        as_human(monkeypatch, "approve-criteria", TICKET, OTHER_TICKET)
    assert "email" in str(caught.value).lower()
    assert not record_path(repo, TICKET, "criteria").exists()
    assert not record_path(repo, OTHER_TICKET, "criteria").exists()


# --- D22: the human-only commands need a human at a terminal ------------------------


def test_approve_criteria_refuses_without_a_terminal(repo, monkeypatch):
    """The ticket-writing session runs without a terminal; it must not be able
    to approve its own criteria."""
    at_terminal(monkeypatch, False)

    assert "terminal" in refusal(monkeypatch, "approve-criteria", TICKET).lower()
    assert not record_path(repo, TICKET, "criteria").exists()


def test_override_review_refuses_without_a_terminal(repo, monkeypatch):
    """Nor may it wave its own tests past review."""
    at_terminal(monkeypatch, False)

    msg = refusal(monkeypatch, "override-review", TICKET, "--reason", "bootstrap")
    assert "terminal" in msg.lower()
    assert not record_path(repo, TICKET, "override").exists()


# --- D22: the override stands in for a review while the bytes hold ------------------


def test_override_record_lets_reapproval_pass_while_the_tests_are_unchanged(repo, monkeypatch):
    """The night re-approves every ticket on the run branch. An override must
    carry through that, and stop carrying the moment the tests change."""
    assert as_human(monkeypatch, "approve-criteria", TICKET) == 0
    assert as_human(monkeypatch, "override-review", TICKET, "--reason", "bootstrap") == 0
    lock = record_path(repo, TICKET, "")

    # Approved with no review ever run, then re-approved with no terminal, as
    # the night does, after a review failed - which is when an override gets used.
    assert gate_cli(monkeypatch, "approve", TICKET) == 0
    write_review(repo, ("fail", frozen_hashes(repo)))
    assert gate_cli(monkeypatch, "approve", TICKET) == 0
    locked = lock.read_text()

    # An override that names only one of the two frozen files vouches for
    # neither ticket's whole set.
    override = record_path(repo, TICKET, "override")
    assert override.exists()
    whole = override.read_text()
    override.write_text(json.dumps({**json.loads(whole), "frozen": frozen_hashes(repo, FROZEN)}))
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == locked
    override.write_text(whole)

    # The tests change under an existing lock. The lock is no exemption (D25):
    # re-approval is refused, and the old lock is left exactly as it was.
    (repo / FROZEN).write_text("def test_orders_the_queue():\n    assert True\n")
    assert "review" in refusal(monkeypatch, "approve", TICKET).lower()
    assert lock.read_text() == locked


# --- D26: what the fingerprint covers -----------------------------------------------


def test_criteria_fingerprint_covers_acceptance_decisions_scope_and_full_gate_only(
    repo, monkeypatch
):
    """Each of the four fields moves the fingerprint; a title, a body, a kill
    condition, a blocker or the frozen list does not, so a typo fix does not
    need the human again. (The frozen files are the review's to vouch for.)"""
    def fingerprint(fields: dict, body: str = "## Context\n\nOrder the queue.\n") -> str:
        write_ticket(repo, fields, body)
        path = record_path(repo, TICKET, "criteria")
        path.unlink(missing_ok=True)
        assert as_human(monkeypatch, "approve-criteria", TICKET) == 0
        assert path.exists()
        return json.loads(path.read_text())["sha256"]

    base = fingerprint(ticket_fields())

    covered = {
        "acceptance": [f"python3 -m pytest {FROZEN}::test_cycle -q"],
        "decisions": ["D1", "D2"],
        "scope": ["edad/thing.py", "edad/other.py"],
        "full_gate": ["python3 -m pytest -q", "ruff check ."],
    }
    for field, value in covered.items():
        assert fingerprint({**ticket_fields(), field: value}) != base, field

    uncovered = {
        "title": "A better title",
        "kill_conditions": {"max_iterations": 6, "max_diff_lines": 200},
        "blocked_by": [OTHER_TICKET],
        "frozen": [FROZEN, CYCLE, "tests/test_other.py"],
    }
    for field, value in uncovered.items():
        assert fingerprint({**ticket_fields(), field: value}) == base, field
    assert fingerprint(ticket_fields(), body="## Context\n\nOrder the queue, typo fixed.\n") == base
