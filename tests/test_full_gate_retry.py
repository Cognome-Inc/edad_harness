"""A ticket-introduced full_gate failure on green acceptance is one more
iteration, not the end of the night.

Three nights (T020, T024 nights 1 and 4) ended on a single ruff finding in the
agent's own new code with acceptance fully green, because the full gate ran once
after the loop and its "introduced" verdict was an Abort. The agent was never told
the full gate existed: `initial_prompt` lists only the acceptance commands.

Every test here drives `run_session` through a scripted `evaluate` - the real one
cannot produce an "introduced" verdict without a baseline and a git worktree, and
what is under test is what the session does with each verdict, not how the gate
reaches it. The agent, git, the worktree, record writing and evidence promotion
are replaced the way T021's `Night` replaces them; `full_gate_failure` is real.

Spec: .edad/specs/full-gate-retry.md (D1-D9).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from edad import gate, session
from edad.gate import CommandResult, Record, Refusal
from edad.session import full_gate_retry_prompt, initial_prompt, network_rule, run_session
from edad.session_queue import no_commit_abort

HEAD = "a" * 40
ACCEPT = "python3 -m pytest tests/test_thing.py::test_it -q"
SUITE = "python3 -m pytest -q"
LINT = "ruff check ."
KEY = "lint:edad/session.py:I001"

TICKET = {
    "id": "T900",
    "title": "a ticket",
    "_body": "",
    "scope": ["edad/session.py"],
    "frozen": ["tests/test_thing.py"],
    "acceptance": [ACCEPT],
    "full_gate": [SUITE, LINT],
    "kill_conditions": {"max_iterations": 6, "same_test_fails_consecutively": 3},
}


# --- records the scripted gate hands back -----------------------------------


def result(command: str, exit_code: int = 0, output: str = "1 passed",
           named_paths: tuple[str, ...] = ()) -> CommandResult:
    return CommandResult(command, exit_code, 0.1, output, list(named_paths), False, None)


def record(gate_name: str, commands: list[CommandResult], **fields) -> Record:
    rec = Record(
        ticket="T900", started_at="2026-09-15T00:00:00+00:00", commit="0" * 40,
        base_ref=HEAD, gate=gate_name, freeze_ok=True,
        commands_ok=all(c.ok for c in commands), commands=commands,
    )
    for k, v in fields.items():
        setattr(rec, k, v)
    return rec


def acceptance_pass() -> Record:
    return record("acceptance", [result(ACCEPT)])


def acceptance_fail() -> Record:
    return record(
        "acceptance",
        [result(ACCEPT, 1, "FAILED tests/test_thing.py::test_it - assert 0 == 1")],
        violations=[f"command failed (1): {ACCEPT}"],
    )


def full_pass() -> Record:
    return record("full_gate", [result(SUITE), result(LINT)])


def full_introduced(*keys: str, path: str = "edad/session.py") -> Record:
    """What the ratchet reports for a lint finding this ticket introduced."""
    keys = keys or (KEY,)
    lines = "\n".join(f"{path}:12:1: {k.rsplit(':', 1)[1]} unsorted imports" for k in keys)
    return record(
        "full_gate",
        [result(SUITE), result(LINT, 1, lines, named_paths=(path,))],
        new_failures={LINT: list(keys)},
        violations=[f"command failed (1): {LINT}"],
    )


def full_unwinnable() -> Record:
    """The suite fails inside the ticket's own frozen file."""
    return record(
        "full_gate",
        [result(SUITE, 1, "FAILED tests/test_thing.py::test_it",
                named_paths=("tests/test_thing.py",)),
         result(LINT)],
        new_failures={SUITE: ["pytest:tests/test_thing.py::test_it"]},
        violations=[f"command failed (1): {SUITE}"],
    )


def full_uncomparable() -> Record:
    return record(
        "full_gate",
        [result(SUITE), result(LINT, 1, "make: *** Error 1")],
        uncomparable_failures=[LINT],
        violations=[f"command failed (1): {LINT}"],
    )


def full_modulo_baseline() -> Record:
    """The suite is red, and everything red was already in the baseline."""
    return record(
        "full_gate",
        [result(SUITE, 1, "FAILED tests/test_old.py::test_legacy"), result(LINT)],
        new_failures={SUITE: []},
        violations=[f"command failed (1): {SUITE}"],
    )


# --- the driver ---------------------------------------------------------------


class ScriptedNight:
    """Drives `run_session` with `evaluate` replaced by a script: each call takes
    the next item, records which gate was asked for, and returns it - or raises
    it, when the item is an exception. Everything else the loop touches is
    replaced as T021's `Night` replaces it, plus record writing and evidence
    promotion, which need a real git worktree."""

    def __init__(self, monkeypatch, tmp_path: Path, script: list, ticket: dict = TICKET,
                 commit_per_iteration: bool = True) -> None:
        self.root = tmp_path
        self.wt = tmp_path / "wt"
        self.wt.mkdir(parents=True)
        self.ticket = ticket
        self.script = list(script)
        self.gates: list[str] = []          # gate names, in the order evaluate was asked
        self.prompts: list[str] = []        # the prompt handed to each agent run
        self.records: list[Record] = []     # what write_record was given
        self.promoted: list[Record] = []    # what promote_evidence was given
        self.args = SimpleNamespace(
            ticket=ticket["id"], sandbox="none", network=None, image=None,
            yolo=False, dry_run=False,
        )

        def evaluate(root, tkt, gate_name="acceptance", base_ref=None):
            self.gates.append(gate_name)
            assert self.script, f"the loop asked for a {gate_name} run the script did not expect"
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        def run_agent(argv, workdir):
            self.prompts.append(argv[1])
            return 0, "did the work"

        def commit_iteration(wt, tid, n):
            return f"{n:040d}" if commit_per_iteration else HEAD

        def write_record(root, rec):
            self.records.append(rec)
            return root / ".edad" / "records" / "r.json"

        def promote_evidence(root, wt, tid, rec):
            self.promoted.append(rec)
            return wt / ".edad" / "evidence" / f"{tid}.json"

        monkeypatch.setattr(session, "preflight", lambda *a, **k: [])
        monkeypatch.setattr(session, "git", lambda *a, **k: HEAD)
        monkeypatch.setattr(session, "harness_identity", lambda: {"version": "test"})
        monkeypatch.setattr(session, "make_worktree",
                            lambda root, tid, base: (self.wt, "edad/t900"))
        monkeypatch.setattr(session, "agent_argv", lambda prompt, *a, **k: ["agent", prompt])
        monkeypatch.setattr(session, "run_agent", run_agent)
        monkeypatch.setattr(session, "commit_iteration", commit_iteration)
        monkeypatch.setattr(session, "evaluate", evaluate)
        monkeypatch.setattr(session, "write_record", write_record)
        monkeypatch.setattr(session, "promote_evidence", promote_evidence)

    def run(self) -> int:
        return run_session(self.root, self.ticket, self.args)

    def log(self) -> dict:
        [path] = list((self.root / ".edad" / "sessions").glob("T900-*.json"))
        return json.loads(path.read_text())


def with_budget(max_iterations: int) -> dict:
    return {**TICKET, "kill_conditions": {**TICKET["kill_conditions"],
                                          "max_iterations": max_iterations}}


# --- D1: the agent is told the full gate exists ------------------------------

# One sentence that both names the agent's changed/touched/modified files and
# assigns their findings to the agent (yours / your ... to clear|fix). Word
# boundaries keep "unchanged" and "untouched" from counting; the same-sentence
# rule keeps the scope rule's "you may modify" from pairing with a distant "yours".
OWNS_CHANGED_FILES = re.compile(
    r"[^.\n]*\byou\b[^.\n]*\b(changed|touched|modified|edited)\b[^.\n]*"
    r"\b(yours|your own|your responsibility|you must (fix|clear))\b"
)


def test_the_opening_prompt_names_every_full_gate_command_and_the_baseline_rule():
    """`initial_prompt` listed only `acceptance` and said "you are done when
    these exit 0"; `full_gate` reached the agent only as permission patterns.
    The lost nights were not disobedience - the agent was told it was done."""
    text = initial_prompt(TICKET)

    for command in TICKET["full_gate"]:
        assert command in text, f"the full-gate command {command!r} is not in the prompt"
    assert "baseline" in text, "the agent must know these are judged against a baseline"
    assert text.index(ACCEPT) < text.index(LINT), "acceptance first, then the full gate"
    # The rule the three nights needed: findings in files the agent changed are
    # its own to clear, and it should run the commands itself before stopping.
    # Pinned as a rule, not a word: one sentence that names the agent's own
    # changed files AND assigns the findings to it. A bare "changed" would be
    # met by "unchanged"; a bare "yours" by the scope rule.
    assert OWNS_CHANGED_FILES.search(text), (
        "the prompt must say findings in files the agent changed are its own to clear"
    )
    assert re.search(r"\bbefore you stop\b|\byourself\b", text), (
        "the agent must be told to run the full-gate commands itself"
    )


# --- D2: the full gate runs inside the loop, only on green acceptance --------


def test_the_full_gate_does_not_run_when_acceptance_fails(monkeypatch, tmp_path):
    """Acceptance red: no full gate that iteration. Acceptance green: the full
    gate runs in the same iteration, and an introduced failure sends the loop
    round again rather than out."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_fail(),
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_pass(),
    ])

    night.run()

    assert night.gates == ["acceptance", "acceptance", "full_gate", "acceptance", "full_gate"], (
        night.gates
    )
    assert night.log()["outcome"] == "passed"


def test_an_introduced_full_gate_failure_is_retried_and_the_next_iteration_promotes(
    monkeypatch, tmp_path
):
    """The T020/T024 shape: green acceptance, one lint finding, and a second
    iteration that clears it. The night promotes evidence from the passing full
    gate instead of aborting on the first."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_pass(),
    ])

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "passed", log["abort_reason"]
    assert log["abort_reason"] is None
    assert rc == 0
    assert len(log["iterations"]) == 2, log["iterations"]
    assert [it["gate_passed"] for it in log["iterations"]] == [True, True]
    assert len(night.promoted) == 1 and night.promoted[0].gate == "full_gate"
    assert night.promoted[0].passed, "the record promoted is the passing one, not the first"
    assert log["evidence"] == ".edad/evidence/T900.json"
    # One record per attempt: acceptance, full, acceptance, full.
    assert [r.gate for r in night.records] == ["acceptance", "full_gate", "acceptance", "full_gate"]


# --- D3: only "introduced" retries -------------------------------------------


def test_an_unwinnable_full_gate_still_ends_the_night(monkeypatch, tmp_path):
    """A failure inside a frozen file is one no permitted edit clears. It stops
    the night as `unwinnable`, in the iteration it happened, and the iteration
    records what the full gate found."""
    night = ScriptedNight(monkeypatch, tmp_path, [acceptance_pass(), full_unwinnable()])

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "unwinnable", log
    assert "frozen" in log["abort_reason"]
    assert rc == 1
    assert night.gates == ["acceptance", "full_gate"], "no retry was attempted"
    [it] = log["iterations"]
    assert it["gate_passed"] is True, "acceptance was green; the log must still say so"
    assert f"command failed (1): {SUITE}" in it["violations"], (
        "the full gate's violations land on the iteration that ran it: " + repr(it)
    )


def test_an_uncomparable_full_gate_still_ends_the_night(monkeypatch, tmp_path):
    """"Could not compare" is not "nothing new"; retrying it would ask the agent
    to clear something that may be pre-existing and outside its scope."""
    night = ScriptedNight(monkeypatch, tmp_path, [acceptance_pass(), full_uncomparable()])

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "aborted", log
    assert "baseline could not be applied" in log["abort_reason"], log["abort_reason"]
    assert rc == 1
    assert night.gates == ["acceptance", "full_gate"], "no retry was attempted"
    [it] = log["iterations"]
    assert it["gate_passed"] is True
    assert f"command failed (1): {LINT}" in it["violations"], repr(it)


def test_an_introduced_failure_outside_scope_is_retried_not_aborted(monkeypatch, tmp_path):
    """The failure names a file the agent may not edit, but the scoped edit is
    often what caused it (a broken import, a changed call) and a scoped fix
    clears it. It is retried; the repeat kill bounds the case where it cannot."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), full_introduced("lint:edad/session_queue.py:F401",
                                           path="edad/session_queue.py"),
        acceptance_pass(), full_pass(),
    ])

    night.run()

    log = night.log()
    assert log["outcome"] == "passed", log["abort_reason"]
    assert len(log["iterations"]) == 2


# --- D4: a retry spends an iteration; the signature is the introduced keys ---


def test_the_same_introduced_keys_three_iterations_running_end_the_night(
    monkeypatch, tmp_path
):
    """Ruff's output carries line numbers that move between iterations, so a
    hash of it never repeats and the repeat kill never fires. The keys the
    ratchet already computed do repeat, and are the signature."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_pass(),      # never reached
    ])

    night.run()

    log = night.log()
    assert log["outcome"] == "aborted", log
    assert "identical failure 3 iterations running" in log["abort_reason"], log["abort_reason"]
    assert KEY in log["abort_reason"], "the kill names the finding, not a hash"
    assert len(log["iterations"]) == 3, log["iterations"]
    assert [it["signature"] for it in log["iterations"]] == [f"full_gate:{KEY}"] * 3
    assert night.script, "the fourth iteration never ran"


def test_two_retries_with_different_keys_then_a_pass_promote(monkeypatch, tmp_path):
    """Three green acceptance runs in a row. A green record's own signature is a
    constant, truthy hash - had that been appended, the repeat kill would have
    fired on the third iteration for passing. Different findings each time
    means no kill; the signature joins sorted keys with `|`; a fully green
    iteration contributes an empty signature."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), full_introduced(KEY),
        acceptance_pass(), full_introduced("lint:edad/session.py:E501", KEY),
        acceptance_pass(), full_pass(),
    ])

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "passed", log["abort_reason"]
    assert rc == 0
    assert [it["signature"] for it in log["iterations"]] == [
        f"full_gate:{KEY}",
        f"full_gate:lint:edad/session.py:E501|{KEY}",
        "",
    ], log["iterations"]


def test_a_full_gate_retry_spends_an_iteration_of_the_ticket_budget(monkeypatch, tmp_path):
    """No second counter. Two iterations of budget, two green-acceptance
    iterations with a lint miss each, and the night is over: the loop does not
    ask for a third agent run."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_pass(),      # never reached
    ], ticket=with_budget(2))

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "aborted", log
    assert rc == 1
    assert len(log["iterations"]) == 2, log["iterations"]
    assert len(night.prompts) == 2, "two agent runs, not three"
    assert night.gates == ["acceptance", "full_gate", "acceptance", "full_gate"]


# --- D5: the iteration record ------------------------------------------------


def test_the_iteration_log_says_acceptance_passed_and_what_the_full_gate_found(
    monkeypatch, tmp_path
):
    """`gate_passed` keeps meaning acceptance. The full gate's verdict is its own
    field: unset when it did not run, else what it found."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_fail(),
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_modulo_baseline(),
    ])

    night.run()

    log = night.log()
    assert log["outcome"] == "passed_modulo_baseline", log["abort_reason"]
    one, two, three = log["iterations"]
    assert (one["gate_passed"], one["full_gate"]) == (False, None), one
    assert (two["gate_passed"], two["full_gate"]) == (True, "introduced"), two
    assert f"command failed (1): {LINT}" in two["violations"], two
    assert (three["gate_passed"], three["full_gate"]) == (True, "passed_modulo_baseline"), three


def test_the_queue_reads_a_retried_night_the_same_way(monkeypatch, tmp_path):
    """`no_commit_abort` reads `outcome` and `iterations[].made_commit` and
    nothing else. A retried night where the agent committed nothing on either
    iteration is still a no-commit abort; one where it committed is not."""
    idle = ScriptedNight(monkeypatch, tmp_path / "idle", [
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_introduced(),
    ], ticket=with_budget(2), commit_per_iteration=False)
    idle.run()
    idle_log = idle.log()
    assert len(idle_log["iterations"]) == 2, "the retry happened"
    assert [it["made_commit"] for it in idle_log["iterations"]] == [False, False]
    assert no_commit_abort(idle_log) is True

    busy = ScriptedNight(monkeypatch, tmp_path / "busy", [
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_introduced(),
    ], ticket=with_budget(2))
    busy.run()
    busy_log = busy.log()
    assert len(busy_log["iterations"]) == 2
    assert no_commit_abort(busy_log) is False


# --- D6: the retry prompt ---------------------------------------------------


def test_the_full_gate_retry_prompt_says_acceptance_passed_and_quotes_each_failure(
    monkeypatch, tmp_path
):
    """Not `retry_prompt`: that one opens "did not pass the gate ... Fix the
    implementation", which on green code invites the wrong kind of edit. This
    one says acceptance passed, quotes the verifier's output for each failing
    command and nothing for the passing ones, and carries the network rule."""
    rec = full_introduced()
    text = full_gate_retry_prompt(TICKET, rec, 1)

    # Says acceptance PASSED - and not merely that something "did not pass the
    # acceptance gate", which contains the same two words and is exactly the
    # message D6 rejects.
    assert re.search(r"\bacceptance\b[^.\n]*\bpassed\b", text), text
    assert "did not pass" not in text and "Fix the implementation" not in text, (
        "this is the acceptance retry's opening; on green code it invites the wrong edit"
    )
    assert text != session.retry_prompt(TICKET, rec, 1), "reusing retry_prompt is rejected"
    # The discriminator bites: the rejected prompt fails it.
    assert "did not pass" in session.retry_prompt(TICKET, rec, 1)
    assert "T900" in text
    assert f"$ {LINT}" in text, "the failing command, as the verifier ran it"
    assert "I001 unsorted imports" in text, "the verifier's own output, not a summary"
    assert f"$ {SUITE}" not in text, "the passing command is not quoted"
    assert "frozen" in text, "the frozen rule still applies"
    assert network_rule("none") in text
    assert network_rule("docker", network="edad-fixtures") in full_gate_retry_prompt(
        TICKET, rec, 1, "docker", "edad-fixtures"
    )

    # And the loop hands exactly this prompt to the agent on the retry.
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), rec,
        acceptance_pass(), full_pass(),
    ])
    night.run()
    assert night.prompts[0] == initial_prompt(TICKET, "none", None)
    assert night.prompts[1] == full_gate_retry_prompt(TICKET, rec, 1, "none", None)


# --- D7: exhaustion with acceptance green says so ----------------------------


def test_running_out_of_iterations_with_acceptance_green_names_the_full_gate_failures(
    monkeypatch, tmp_path
):
    """Distinct from "exhausted N iterations without passing the gate", which
    stays for the acceptance case. An operator grepping session logs can tell
    the two apart without opening a record."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), full_introduced(),
        acceptance_pass(), full_introduced(),
    ], ticket=with_budget(2))

    night.run()

    reason = night.log()["abort_reason"] or ""
    head = "exhausted 2 iterations: acceptance passed, full_gate still failing: "
    assert reason.startswith(head), reason
    assert f"{LINT} -> {KEY}" in reason, reason

    # The acceptance case is unchanged.
    never = ScriptedNight(monkeypatch, tmp_path / "never", [
        acceptance_fail(), acceptance_fail(),
    ], ticket=with_budget(2))
    never.run()
    assert never.log()["abort_reason"] == "exhausted 2 iterations without passing the gate"


# --- D8: a refusal at the full gate is unchanged -----------------------------


def test_a_refused_full_gate_leaves_the_field_unset(monkeypatch, tmp_path):
    """The refusal propagates as it did before the loop changed: one iteration,
    acceptance green, the refusal as the abort reason, no retry. The full gate
    produced no verdict, so the field says so."""
    night = ScriptedNight(monkeypatch, tmp_path, [
        acceptance_pass(), Refusal("pinned toolchain mismatch: pytest: 9.0.3, pinned 8.4.2"),
        acceptance_pass(), full_pass(),      # never reached
    ])

    rc = night.run()

    log = night.log()
    assert log["outcome"] == "aborted", log
    assert "pinned toolchain mismatch" in log["abort_reason"]
    assert rc == 1
    [it] = log["iterations"]
    assert it["gate_passed"] is True
    assert it["full_gate"] is None, it
    assert night.gates == ["acceptance", "full_gate"]
    assert isinstance(gate.Refusal("x"), SystemExit), "still the CLI's exit, caught by the loop"


# --- D9: the docstring -------------------------------------------------------


def test_the_module_docstring_no_longer_puts_the_full_gate_after_the_loop():
    """The flow line is the first thing anyone reads in the module. The full
    gate sits inside the repeated bracket now."""
    doc = session.__doc__ or ""

    assert "]xN  ->  full gate  ->  evidence" not in doc, "the old sequence is gone"
    assert re.search(r"\[[^\]]*full gate[^\]]*\]\s*xN", doc), (
        "the full gate is named inside the xN bracket: " + doc.splitlines()[7]
    )
