"""A refused iteration is logged, and a refusal in a worktree names the pins.

T021 made a mid-session `Refusal` an ordinary `aborted` with a reason, and deferred
the iteration itself: `run_session` appends the `Iteration` only after `evaluate`
returns, so when `evaluate` refuses - the toolchain check, which runs before the
`Record` exists - the agent's committed work is in git and absent from the log.
`session_queue.no_commit_abort` reads `iterations: []` as "the agent never ran" and
two such nights trip the `no_progress` breaker for a reason that is false.

The same refusal advises `pip install -r requirements-gate.txt`. In a worktree that
file may be the one the agent just wrote, possibly out of scope, and nothing records
that it did.

These pin the fix. Every test drives T021's `Night`: `run_session` from the top of its
loop, `evaluate` real, the agent editing the pins in iteration 1 so the toolchain
measurement no longer fits. `Night` fakes `changed_files` to `[]`; the tests that need
the pins file to have changed override that on the `gate` module, which is where
`evaluate` looks it up.
"""

from test_gate_refusal import HEAD, MISMATCH, TICKET, MeasureSequence, Night, measured

from edad import gate, session
from edad.session import run_session
from edad.session_queue import no_commit_abort

PINS = "requirements-gate.txt"
INSTALL_ADVICE = "Install the pins: pip install -r requirements-gate.txt"


def refused_night(monkeypatch, tmp_path, changed=None) -> tuple[Night, MeasureSequence]:
    """A `Night` whose only iteration is refused at the acceptance gate. `changed`
    is what `changed_files` reports the worktree touched since base; `None` keeps
    the fixture's `[]`."""
    measure = MeasureSequence(measured(pytest=("9.0.3", None)))
    night = Night(monkeypatch, tmp_path, measure)
    if changed is not None:
        monkeypatch.setattr(gate, "changed_files", lambda root, base_ref: list(changed))
    return night, measure


# --- D1: the refusal still ends the session; the iteration is logged first ----------


def test_a_refused_iteration_is_logged_then_the_session_aborts(monkeypatch, tmp_path, capsys):
    """The agent ran and committed; `evaluate` refused. The session ends exactly
    as T021 pinned - `aborted`, the refusal as its reason, exit 1, the ABORTED line
    - and the iteration that was refused is in the log. One iteration, because a
    refusal is not retried: `evaluate` was reached once, and there was no second
    agent run to log."""
    night, measure = refused_night(monkeypatch, tmp_path)

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "aborted", log
    assert MISMATCH in (log["abort_reason"] or ""), log["abort_reason"]
    assert rc == 1, "a refused session is a failed one"
    assert len(log["iterations"]) == 1, (
        "the refused iteration is in the log, and only it: " + repr(log["iterations"])
    )
    assert measure.calls == 1, "evaluate ran once; a refusal is not retried"
    err = capsys.readouterr().err
    assert "ABORTED" in err and str(night.wt) in err


# --- D2: the iteration's shape ------------------------------------------------------


def test_the_refused_iteration_carries_the_verdict_the_commit_and_the_agent_tail(
    monkeypatch, tmp_path
):
    """The existing `Iteration`, no new field: the gate did not pass, the signature
    is the refusal with a `refusal:` prefix so it cannot be mistaken for a failed
    test, the violations are the refusal, the commit and the agent's exit and tail
    are what the session measured. No `Record` is written for it - there was none."""
    night, _ = refused_night(monkeypatch, tmp_path)

    night.run()

    log = night.log()
    assert len(log["iterations"]) == 1, "the refused iteration is logged: " + repr(log)
    it = log["iterations"][0]
    assert it["n"] == 1
    assert it["gate_passed"] is False
    assert it["signature"].startswith("refusal:"), it["signature"]
    assert MISMATCH in it["signature"], it["signature"]
    assert it["violations"] == [log["abort_reason"]], it["violations"]
    assert it["made_commit"] is True, "Night's commit_iteration returns a new SHA"
    assert it["commit"] == "b" * 40
    assert it["agent_exit"] == 0
    assert it["agent_output"] == "bumped the pin", "the agent's tail, as for any iteration"
    assert not (night.root / ".edad" / "records").exists(), "no Record for a refused run"


# --- D3: what the queue reads -------------------------------------------------------


def test_a_refused_night_that_committed_is_not_a_no_commit_abort(monkeypatch, tmp_path):
    """`no_commit_abort` reads `iterations[].made_commit` and nothing else, and it
    is not changed here: with the refused iteration logged, a night whose agent
    committed and was refused reads as the agent running - the counter resets.
    A refused night whose agent committed nothing still counts, as it should."""
    night, _ = refused_night(monkeypatch, tmp_path)
    night.run()
    assert no_commit_abort(night.log()) is False, (
        "the agent ran and committed; this is a refusal, not an agent that is not running"
    )

    # A second night, the agent committing nothing: commit_iteration returns base.
    (tmp_path / "second").mkdir()
    second, _ = refused_night(monkeypatch, tmp_path / "second")
    monkeypatch.setattr(session, "commit_iteration", lambda wt, tid, n: HEAD)
    second.run()
    assert no_commit_abort(second.log()) is True, "nothing committed is still nothing committed"


# --- D4: the worktree changed the pins ----------------------------------------------


def test_a_refusal_after_the_worktree_changed_the_pins_does_not_advise_installing_them(
    monkeypatch, tmp_path
):
    """`evaluate` has a base and `requirements-gate.txt` is among the files changed
    since it. The refusal keeps its frozen prefix and the check's own problem line,
    says the worktree changed the pins and that the file is in this ticket's scope
    (TICKET puts it there), and does not tell the operator to install what the
    agent wrote."""
    night, _ = refused_night(monkeypatch, tmp_path, changed=[PINS])

    night.run()

    reason = night.log()["abort_reason"] or ""
    assert MISMATCH in reason, reason
    assert "pytest: 9.0.3, pinned 8.4.2" in reason, "the check's own line survives"
    assert f"worktree changed {PINS}" in reason, reason
    assert "in scope" in reason and "out of scope" not in reason, reason
    assert "pip install" not in reason, "never advise installing the worktree's pins"


# --- D5: an out-of-scope pin change is on record ------------------------------------


def test_a_refusal_after_an_out_of_scope_pin_change_names_the_stray_in_the_log(
    monkeypatch, tmp_path
):
    """Same refusal, a ticket whose scope does not admit the pins file. The reason
    names the stray in `check_kills`' own wording, and because the reason is the
    refused iteration's violation, the scope violation is in the session log
    without a `Record` ever existing."""
    night, _ = refused_night(monkeypatch, tmp_path, changed=[PINS])
    ticket = {**TICKET, "scope": ["edad/session.py"]}

    run_session(night.root, ticket, night.args)

    log = night.log()
    reason = log["abort_reason"] or ""
    assert f"worktree changed {PINS}" in reason, reason
    assert f"out of scope: {PINS}" in reason, reason
    assert "pip install" not in reason, reason
    [it] = log["iterations"]
    assert any(f"out of scope: {PINS}" in v for v in it["violations"]), it["violations"]


# --- D7: a frozen pins file is named as frozen, not as in scope --------------------


def test_a_refusal_after_a_frozen_pin_change_names_the_frozen_file_not_the_scope(
    monkeypatch, tmp_path
):
    """Same refusal, a ticket that freezes the pins file instead of scoping it.
    `check_scope` admits every frozen path on the assumption that the hash check
    caught any change first - on the refusal path it has not run yet, so a frozen
    file the agent rewrote would read as "in scope". The reason names it in the
    freeze check's own wording, `frozen file modified: <file>`, and never as in
    scope, so the log records what happened: a frozen file was rewritten."""
    night, _ = refused_night(monkeypatch, tmp_path, changed=[PINS])
    ticket = {**TICKET, "scope": ["edad/session.py"], "frozen": [*TICKET["frozen"], PINS]}

    run_session(night.root, ticket, night.args)

    log = night.log()
    reason = log["abort_reason"] or ""
    assert f"worktree changed {PINS}" in reason, reason
    assert f"frozen file modified: {PINS}" in reason, reason
    assert "in scope" not in reason, "a frozen file is not a scoped one: " + reason
    assert "pip install" not in reason, reason
    [it] = log["iterations"]
    assert any(f"frozen file modified: {PINS}" in v for v in it["violations"]), it["violations"]


# --- D6: green at base - the pins unchanged, the advice unchanged -------------------


def test_a_refusal_with_the_pins_unchanged_keeps_the_install_advice(monkeypatch, tmp_path):
    """The worktree changed other files but not the pins, and the toolchain still
    does not fit: the environment is the operator's, and the install advice is
    right. Green at base; not in `acceptance`; `full_gate` runs it so the change
    cannot over-reach."""
    night, _ = refused_night(monkeypatch, tmp_path, changed=["edad/session.py"])

    night.run()

    reason = night.log()["abort_reason"] or ""
    assert MISMATCH in reason, reason
    assert INSTALL_ADVICE in reason, reason
    assert "worktree changed" not in reason, reason
