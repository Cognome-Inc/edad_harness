"""A base ref the gate cannot use is refused, not crashed on.

`evaluate(root, ticket, gate_name, base_ref)` uses `base_ref` three times: the
toolchain refusal asks whether the pins changed since it, the trusted-input check
compares the lock at it, and `changed_files` diffs against it. None of them
checked the ref first. A ref that does not resolve, or one that shares no history
with HEAD, made `git diff <ref>...HEAD` exit 128 inside `changed_files` - a bare
`CalledProcessError` traceback for the operator who typed `--base-ref` wrong - and
before that the trusted-input check read the same git error as "approval lock
modified since <ref>", a false verdict about the agent. With a mismatched
toolchain the crash merely arrived earlier, from the refusal's own pins check.

These tests attach at four seams. Most call `evaluate` on a real temporary
repository - the check IS a git call, so a fake would test the fake - with the
toolchain replaced the way T021's `Night` replaces it and `run_commands` a clean
pass. One spawns the gate CLI, because the reported symptom is the CLI's. Two wrap
`gate.git` around the real function: one to record which verbs ran, one to make
the probe fail for a valid ref - which only a probe routed through `gate.git`
notices, and that routing is what keeps T021's and T023's frozen fixtures, which
fake `gate.git` and run the real `evaluate` against a non-repository, green.

The agent's container has no git. Every test here fails there; the verifier on
the host judges them. That is the environment, not the agent's defect.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from edad import gate

TICKET_ID = "T900"
FROZEN = "tests/test_thing.py"
PINFILE = "requirements-gate.txt"
LOCK = f".edad/hashes/{TICKET_ID}.json"
TICKET = f".edad/tickets/{TICKET_ID}.md"
PINS = {"pytest": "8.4.2", "ruff": "0.15.18"}
HARNESS = {"version": None, "commit": "c" * 40, "dirty": False, "source": "checkout"}
MISMATCH = "does not match requirements-gate.txt"
LOCK_DRIFT = "approval lock modified"

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
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def measured(pins: dict, *, broken: str | None = None) -> list:
    """A satisfied `Measurement` per pin, or one that is not on the path at
    all when `broken` names it - the shape T021's `Night` steers the toolchain
    refusal with."""
    return [
        gate.Measurement(name, ver, None if name == broken else ver, None)
        for name, ver in pins.items()
    ]


class FakeRun:
    """Stands in for `run_commands`: every command a clean pass."""

    def __call__(self, root, commands, timeout_s=None, **kw):
        return [
            gate.CommandResult(c, 0, 0.1, "1 passed", [], False, None) for c in commands
        ]


class Repo:
    """A repository the gate can evaluate: a frozen test, a ticket, the pins,
    a lock written by hand, all committed as `base`; then one more commit on
    top so `base` is a real ancestor of HEAD and not HEAD itself; and an
    orphan commit on a side branch that shares no history with either."""

    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        self.root = tmp_path / "repo"
        (self.root / "tests").mkdir(parents=True)
        (self.root / ".edad" / "hashes").mkdir(parents=True)
        (self.root / ".edad" / "tickets").mkdir()
        self.write(FROZEN, "def test_one():\n    assert True\n")
        self.write(TICKET, TICKET_TEXT)
        self.write(PINFILE, "".join(f"{n}=={v}\n" for n, v in PINS.items()))
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "gate@example.invalid")
        _git(self.root, "config", "user.name", "edad tests")
        self.write_lock()
        self.base = self.commit("approved")
        self.write("notes.txt", "later\n")
        self.head = self.commit("later")
        # An orphan: a commit that resolves but has no merge base with HEAD.
        _git(self.root, "checkout", "-q", "--orphan", "elsewhere")
        _git(self.root, "rm", "-rfq", ".")
        self.write("other.txt", "unrelated\n")
        self.unrelated = self.commit("unrelated")
        _git(self.root, "checkout", "-q", "main")
        monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
        monkeypatch.setattr(gate, "run_commands", FakeRun())
        monkeypatch.setattr(gate, "measure_toolchain", lambda root: measured(PINS))

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).write_text(text)

    def commit(self, msg: str) -> str:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", msg)
        return _git(self.root, "rev-parse", "HEAD")

    def write_lock(self) -> None:
        lock = {
            FROZEN: gate.sha256(self.root / FROZEN),
            gate.LOCK_META_KEY: {
                "ticket_sha256": gate.sha256(self.root / TICKET),
                "decisions": ["D1"],
                "red_proof": [{"command": "python3 -m pytest", "exit_code": 1}],
                "toolchain": dict(PINS),
            },
        }
        self.write(LOCK, json.dumps(lock, indent=2) + "\n")

    def ticket(self) -> dict:
        return gate.load_ticket(self.root, TICKET_ID)

    def evaluate(self, base_ref: str | None) -> gate.Record:
        return gate.evaluate(self.root, self.ticket(), "acceptance", base_ref)

    def refusal(self, base_ref: str) -> str:
        """The reason `evaluate` refused `base_ref` - and it must refuse, not
        crash: a `CalledProcessError` escaping is the defect."""
        with pytest.raises(gate.Refusal) as caught:
            self.evaluate(base_ref)
        return str(caught.value)


class GitLog:
    """`gate.git`, recorded: the real function, with every verb it was asked
    for kept in order."""

    def __init__(self, monkeypatch) -> None:
        self.verbs: list[str] = []
        real = gate.git

        def recording(root, *args):
            self.verbs.append(args[0])
            return real(root, *args)

        monkeypatch.setattr(gate, "git", recording)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Repo:
    return Repo(tmp_path, monkeypatch)


# --- D1: the ref is checked first --------------------------------------------


def test_a_bad_base_ref_is_refused_before_anything_else_runs(repo, monkeypatch):
    """The check is the first thing `evaluate` does with the ref: no diff, no
    lock comparison at the ref, no toolchain measurement happens first."""
    log = GitLog(monkeypatch)
    measured_calls = []
    monkeypatch.setattr(
        gate, "measure_toolchain",
        lambda root: measured_calls.append(root) or measured(PINS),
    )

    reason = repo.refusal("no-such-ref")

    assert "no-such-ref" in reason, reason
    assert "diff" not in log.verbs and "show" not in log.verbs, log.verbs
    assert measured_calls == [], "the toolchain was measured before the ref was checked"


# --- D2: what a valid ref is ---------------------------------------------------


def test_a_ref_that_does_not_resolve_is_refused_naming_the_ref(repo):
    reason = repo.refusal("no-such-ref")
    assert "no-such-ref" in reason, reason


def test_a_ref_with_no_shared_history_is_refused_naming_the_ref(repo):
    """The orphan commit resolves - `rev-parse --verify` would accept it - but
    `git diff <ref>...HEAD` has no merge base to work from and exits 128."""
    reason = repo.refusal(repo.unrelated)
    assert repo.unrelated in reason, reason


# --- D3: the probe goes through gate.git --------------------------------------


def test_the_probe_reaches_git_through_the_gate_git_seam(repo, monkeypatch):
    """The ref is valid and real git would say so. Only a probe routed through
    `gate.git` sees this wrapper's answer and refuses; a probe that shells out
    on its own asks real git, gets a merge base, and evaluates as if nothing
    were wrong. T021's and T023's frozen fixtures fake `gate.git` and run the
    real `evaluate` against a directory that is not a repository - this is the
    routing that keeps them green."""
    real = gate.git

    def failing_merge_base(root, *args):
        if args[0] == "merge-base":
            raise subprocess.CalledProcessError(128, ["git", *args])
        return real(root, *args)

    monkeypatch.setattr(gate, "git", failing_merge_base)

    reason = repo.refusal(repo.base)
    assert repo.base in reason, reason


# --- D4: ref before toolchain --------------------------------------------------


def test_a_bad_ref_with_a_mismatched_toolchain_is_refused_for_the_ref(repo, monkeypatch):
    """Both are wrong; the ref is named. The pins complaint would have to ask
    whether the pins changed since the ref, and it cannot ask a ref like this."""
    monkeypatch.setattr(gate, "measure_toolchain", lambda root: measured(PINS, broken="ruff"))

    reason = repo.refusal("no-such-ref")

    assert "no-such-ref" in reason, reason
    assert MISMATCH not in reason, reason


# --- D5: the refusal ---------------------------------------------------------


def test_the_refusal_is_a_refusal_naming_the_ref_not_a_lock_drift_verdict(repo):
    """`Refusal` is what `die` raises, so the CLI exits 2 with the reason on
    stderr and `run_session` logs a refused iteration. The lock is present and
    untouched; a bad ref must never read as the agent having edited it."""
    with pytest.raises(gate.Refusal) as caught:
        repo.evaluate("no-such-ref")

    assert caught.value.code == 2
    assert "no-such-ref" in caught.value.reason, caught.value.reason
    assert LOCK_DRIFT not in caught.value.reason, caught.value.reason


def test_the_cli_exits_2_with_the_refusal_on_stderr_and_no_traceback(repo):
    """The symptom as reported: `edad.gate run T --base-ref <bad>` on the
    command line. The child finds `edad` where this interpreter found it and
    the repository through `EDAD_REPO`, the gate's own root override. The
    toolchain there is the host's real one, which the verifier has - and the
    ref is refused before it is measured."""
    checkout = Path(gate.__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(checkout), "EDAD_REPO": str(repo.root)}
    proc = subprocess.run(
        [sys.executable, "-m", "edad.gate", "run", TICKET_ID, "--base-ref", "no-such-ref"],
        cwd=repo.root, env=env, capture_output=True, text=True, check=False,
    )

    assert proc.returncode == 2, (proc.returncode, proc.stderr[-800:])
    assert "edad: " in proc.stderr and "no-such-ref" in proc.stderr, proc.stderr[-800:]
    assert "Traceback" not in proc.stderr + proc.stdout, proc.stderr[-800:]


# --- D9: a ref that reads as an option ----------------------------------------


def test_a_ref_that_git_would_read_as_an_option_is_refused_naming_the_ref(repo, monkeypatch):
    """`--octopus` is a merge-base flag, and `git merge-base --octopus HEAD`
    exits 0. A probe that hands the ref to git positionally lets it through,
    and the operator gets the pre-ticket symptom back: the false lock-drift
    verdict, then `git diff --octopus...HEAD` as a bare traceback. Reachable
    from the CLI as `--base-ref=--octopus`. The probe must end git's option
    parsing before the ref (`--end-of-options`), so that a ref like this fails
    at the probe and is refused by name like any other bad ref - before any
    diff or lock comparison runs."""
    log = GitLog(monkeypatch)

    reason = repo.refusal("--octopus")

    assert "--octopus" in reason, reason
    assert LOCK_DRIFT not in reason, reason
    assert "diff" not in log.verbs and "show" not in log.verbs, log.verbs


# --- D6: what must not change ---------------------------------------------------


def test_the_probe_runs_for_an_ancestor_ref_and_not_for_none(repo, monkeypatch):
    """A ref that is an ancestor of HEAD - every ref the session controller
    passes - is probed once and then evaluates exactly as before, record and
    all. No ref means no probe: nothing to check, nothing asked."""
    log = GitLog(monkeypatch)
    rec = repo.evaluate(repo.base)
    assert isinstance(rec, gate.Record) and rec.base_ref == repo.base
    assert log.verbs.count("merge-base") == 1, log.verbs

    log.verbs.clear()
    rec = repo.evaluate(None)
    assert isinstance(rec, gate.Record) and rec.base_ref is None
    assert "merge-base" not in log.verbs, log.verbs
