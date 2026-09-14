"""A gate refusal reached mid-session is logged, not escaped.

`gate.die()` raised a bare `SystemExit(2)`; `run_session` catches `Abort`. T020 put
the first per-iteration refusal in `evaluate` - the toolchain check - so a session
whose agent edits `requirements-gate.txt` (the pin bump ticket by design, any other
ticket by straying) exits the whole process before a `Record` exists, and the
`finally` writes a session log saying `outcome: "incomplete"` with no reason. These
pin the fix: a refusal is a `SystemExit` that names itself, and the session boundary
turns it into an ordinary `aborted` with the refusal as its reason.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from edad import gate, session
from edad.session import run_session

HEAD = "a" * 40
HARNESS = {"version": None, "commit": HEAD, "dirty": False, "source": "checkout"}
TOOLCHAIN = {"pytest": "8.4.2", "ruff": "0.15.18"}
ACC = "python3 -m pytest tests/test_thing.py::test_one -q"
FULL = "python3 -m pytest -q"
TICKET = {
    "id": "T900",
    "frozen": ["tests/test_thing.py"],
    "scope": ["requirements-gate.txt"],
    "acceptance": [ACC],
    "full_gate": [FULL],
    "kill_conditions": {"network_access": "deny"},
}
MISMATCH = "does not match requirements-gate.txt"


# --- helpers ---------------------------------------------------------------------


def measured(**overrides) -> list:
    """A satisfied `Measurement` per sentinel pin; `overrides` swaps one name's
    (meta, on_path) - the same shape T020's tests steer `evaluate` with."""
    return [
        gate.Measurement(name, ver, *overrides.get(name, (ver, None)))
        for name, ver in TOOLCHAIN.items()
    ]


class MeasureSequence:
    """Stands in for `measure_toolchain`: one prepared answer per call, in
    order, so a test can make the pins fit at the acceptance gate and stop
    fitting at the full gate - which is what an agent editing the pins file
    in its last iteration looks like from the verifier."""

    def __init__(self, *answers: list):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, root):
        self.calls += 1
        return list(self.answers.pop(0))


class FakeRun:
    """Stands in for `run_commands`: every command a clean pass."""

    def __call__(self, root, commands, timeout_s=None, **kw):
        return [
            gate.CommandResult(c, 0, 0.1, "1 passed", [], False, None) for c in commands
        ]


class Night:
    """Drives `run_session` from the top of its iteration loop with every side
    effect replaced: preflight, git, the worktree, the agent and its commit.
    `evaluate` itself is real - what is under test is what the session does
    with the refusal `evaluate` raises, so the refusal must be the real one."""

    def __init__(self, monkeypatch, tmp_path: Path, measure) -> None:
        self.root = tmp_path
        self.wt = tmp_path / "wt"
        self.wt.mkdir()
        self.args = SimpleNamespace(
            ticket="T900", sandbox="none", network=None, image=None,
            yolo=False, dry_run=False,
        )
        # The session's own side effects.
        monkeypatch.setattr(session, "preflight", lambda *a, **k: [])
        monkeypatch.setattr(session, "git", lambda *a, **k: HEAD)
        monkeypatch.setattr(session, "harness_identity", lambda: dict(HARNESS))
        monkeypatch.setattr(session, "make_worktree",
                            lambda root, tid, base: (self.wt, "edad/t900"))
        monkeypatch.setattr(session, "run_agent",
                            lambda argv, workdir: (0, "bumped the pin"))
        monkeypatch.setattr(session, "commit_iteration", lambda wt, tid, n: "b" * 40)
        # Everything the real `evaluate` reaches beyond the toolchain.
        monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
        monkeypatch.setattr(gate, "git", lambda root, *args: HEAD)
        monkeypatch.setattr(gate, "approval_meta", lambda root, ticket_id: {})
        monkeypatch.setattr(gate, "check_freeze", lambda root, ticket: (True, []))
        # T022's base comparison. `run_session` passes a real `base_ref`, so
        # without this the check runs for real against an empty `wt/`, reports
        # the lock and ticket absent, and the freeze kill fires at iteration 1
        # before the toolchain refusal these tests are about. `raising=False`
        # keeps the suite green at the commit T022 is judged against.
        monkeypatch.setattr(gate, "trusted_input_problems",
                            lambda root, ticket_id, base_ref: [], raising=False)
        monkeypatch.setattr(gate, "changed_files", lambda root, base_ref: [])
        monkeypatch.setattr(gate, "run_commands", FakeRun())
        monkeypatch.setattr(gate, "measure_toolchain", measure)

    def run(self):
        """The session's return value - or the `SystemExit` that escaped it,
        which is the defect: a session must return and write its log."""
        try:
            return run_session(self.root, TICKET, self.args)
        except SystemExit as e:
            return e

    def log(self) -> dict:
        files = list((self.root / ".edad" / "sessions").glob("T900-*.json"))
        assert len(files) == 1, "one session log per session, whatever happened"
        return json.loads(files[0].read_text())


# --- D1: a refusal names itself ---------------------------------------------------


def test_die_raises_a_refusal_that_is_still_an_exit_2(capsys):
    """Every `die()` site becomes catchable by type, and none of them changes
    at the CLI: a `Refusal` is a `SystemExit` with code 2, the message is on
    stderr as before, and `str()` of it is the reason - which is what a
    session log's `abort_reason` needs and what `SystemExit(2)` cannot give."""
    with pytest.raises(SystemExit) as exc:
        gate.die("the gate's toolchain does not match requirements-gate.txt: x")

    assert isinstance(exc.value, gate.Refusal), "die() raises the typed refusal"
    assert exc.value.code == 2, "and it is still exit 2 at the CLI"
    assert str(exc.value) == "the gate's toolchain does not match requirements-gate.txt: x"
    assert "edad: the gate's toolchain" in capsys.readouterr().err, "stderr unchanged"


# --- D2: the session boundary --------------------------------------------------------


def test_a_refusal_at_the_acceptance_gate_is_logged_as_aborted_with_its_reason(
    monkeypatch, tmp_path, capsys
):
    """The agent edits `requirements-gate.txt` in iteration 1; `evaluate` refuses
    before any command runs. The session must end the way any other stop does:
    a log saying `aborted` and why, the ABORTED line naming the worktree, and
    exit 1 - not `incomplete`, no reason, and a process that simply vanished."""
    mismatch = measured(pytest=("9.0.3", None))
    night = Night(monkeypatch, tmp_path, MeasureSequence(mismatch))

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "aborted", log
    assert MISMATCH in (log["abort_reason"] or ""), log["abort_reason"]
    assert "pytest: 9.0.3, pinned 8.4.2" in log["abort_reason"], "the check's own line"
    assert rc == 1, "a refused session is a failed one, as main() already reports it"
    err = capsys.readouterr().err
    assert "ABORTED" in err and str(night.wt) in err, "the operator learns where the branch is"


def test_a_refusal_at_the_full_gate_is_logged_the_same_way(monkeypatch, tmp_path):
    """The pins fit when acceptance ran and stop fitting by the full gate. The
    boundary is the whole session, not one `evaluate` call: the iteration that
    passed is in the log, and the refusal that followed is its abort reason."""
    fits, mismatch = measured(), measured(pytest=("9.0.3", None))
    night = Night(monkeypatch, tmp_path, MeasureSequence(fits, mismatch))

    rc = night.run()

    log = night.log()
    assert [it["gate_passed"] for it in log["iterations"]] == [True], log["iterations"]
    assert log["outcome"] == "aborted", log
    assert MISMATCH in (log["abort_reason"] or ""), log["abort_reason"]
    assert rc == 1
