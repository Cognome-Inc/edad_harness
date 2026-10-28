"""The daytime test review (review-loops D1, D5, D9, D11, D27).

T030 (D5): the writer is the ticket-making session, and the reviewer is always
a brand-new `claude -p` process given only the spec, the tests and the rubric.
A resumed or continued session would carry the writer's conversation, and the
whole point of the review is a reader not anchored on the writer's reasoning.

The builders are pure, in the style of `edad.session.agent_argv`. The argv is
checked for properties, not equality, so the model pin that T034 adds (D15)
does not break this test. The prompt builder's first three inputs are pinned;
a later ticket may add an input only as a keyword with a default (T031's
disputes, T034's bandit output), so it is named where it is passed.

T031 (D1, D9, D11, D27): `python3 -m edad.review tests <T>` runs exactly one
round. A CLI cannot call back into the session that launched it, so D1's loop
of three rounds spans three invocations, and the writer revises or disputes
in between. Each round is appended to `.edad/hashes/<T>.review.json`, beside
the lock, in the shape `gate.review_problems` reads (fixed in T029). A round
passes when the reviewer leaves no security, blocker or major finding, and a
passing round runs approve itself.

The rounds are driven through `review.main()` and `sys.argv`, so the parser and
`--dispute` are under test too. The two collaborators that would launch a
process, `review.run_reviewer(argv) -> stdout` and `review.run_approve(root,
ticket_id) -> exit code`, are replaced (seam S5), and any other subprocess call
fails the test. The repo is `tmp_path`, reached through `EDAD_REPO`. The fake
approve writes a lock, as the real one does, so "left unlocked" is something
the tests can see.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import yaml

from edad import gate, review

# Real specs open with YAML front matter: a prompt that started with the spec
# would reach the CLI as an argument beginning with "-".
SPEC = "---\nslug: review-loops\n---\nSPEC: approve refuses tests whose bytes were never reviewed"
TESTS = "def test_approve_refuses_unreviewed_bytes(): ..."
RUBRIC = "T1 TRACE every acceptance criterion has >=1 test"

RESUME_FLAGS = {"--resume", "-r", "--continue", "-c"}

# Room for a short instruction and section headings around the three inputs;
# a builder that appends a ticket, a transcript or notes does not fit.
MAX_FRAMING = 600


def test_reviewer_runs_as_a_new_claude_process_given_only_the_spec_and_tests(monkeypatch):
    # D5: the operator's agent override must not leak a resume into the reviewer.
    monkeypatch.setenv("EDAD_AGENT_CMD", "other-agent -p --continue")
    monkeypatch.delenv("EDAD_REVIEW_MODEL", raising=False)
    prompt = review.review_prompt(SPEC, TESTS, RUBRIC)

    argv = review.reviewer_argv(prompt)

    assert argv[:2] == ["claude", "-p"]
    assert argv.count(prompt) == 1
    assert not prompt.startswith("-")
    assert [a for a in argv if a.split("=")[0] in RESUME_FLAGS] == []


def test_reviewer_prompt_holds_the_spec_tests_and_rubric_and_nothing_else(monkeypatch, tmp_path):
    # D5: the prompt is built from its inputs alone - not the cwd, not a ticket file.
    params = list(inspect.signature(review.review_prompt).parameters.values())
    prompt = review.review_prompt(SPEC, TESTS, RUBRIC)
    monkeypatch.chdir(tmp_path)

    elsewhere = review.review_prompt(SPEC, TESTS, RUBRIC)

    assert [p.name for p in params[:3]] == ["spec", "artifact", "rubric"]
    assert [p.kind == p.KEYWORD_ONLY and p.default is not p.empty for p in params[3:]] == (
        [True] * len(params[3:])
    )
    assert [part in prompt for part in (SPEC, TESTS, RUBRIC)] == [True, True, True]
    assert len(prompt) - len(SPEC + TESTS + RUBRIC) <= MAX_FRAMING
    assert elsewhere == prompt


# --- T031: one round per invocation -------------------------------------------

TICKET = "T900"
FROZEN = "tests/test_queue.py"
# A second frozen file, so "every frozen file reaches the reviewer" is checkable.
TIES = "tests/test_queue_ties.py"
SPEC_PATH = ".edad/specs/queue.md"
SPEC_TEXT = "---\nslug: queue\n---\nD1: the queue orders jobs by priority, lowest first\n"
FROZEN_TEXT = "def test_queue_orders_by_priority():\n    assert order([2, 1]) == [1, 2]\n"
TIES_TEXT = "def test_queue_breaks_ties_by_arrival():\n    assert order([1, 1]) == [1, 1]\n"
EMAIL = "operator@example.com"
# The writer's reasoning, in the ticket body: never an input to the reviewer (D5).
CONTEXT = "The writer chose a stable sort because ties keep their arrival order."

EMPTY_QUEUE = "no test covers an empty queue"
TIED_PRIORITY = "no test covers two jobs with the same priority"
LOOSE_ASSERT = "asserts a truthy value, not the order"


def finding(item: str, severity: str, issue: str) -> dict:
    return {"item": item, "severity": severity, "issue": issue}


def output(*findings: dict) -> str:
    """What the reviewer prints when it follows the format: one JSON object."""
    return json.dumps({"findings": list(findings)})


FAILING = output(finding("T2", "major", EMPTY_QUEUE))
NIT = "the name could read as a behaviour"
NITS_ONLY = output(finding("T8", "nit", NIT))


def write_ticket(root: Path, acceptance: str = "test_queue_orders_by_priority") -> None:
    fields = {
        "id": TICKET,
        "spec": SPEC_PATH,
        "title": "Order the queue",
        "decisions": ["D1"],
        "scope": ["edad/queue.py"],
        "frozen": [FROZEN, TIES],
        "acceptance": [f"python3 -m pytest {FROZEN}::{acceptance} -q"],
        "full_gate": ["python3 -m pytest -q"],
        "blocked_by": [],
        "kill_conditions": {"max_iterations": 4, "max_diff_lines": 100},
    }
    path = root / ".edad" / "tickets" / f"{TICKET}.md"
    front = yaml.safe_dump(fields, sort_keys=False)
    path.write_text("---\n" + front + "---\n\n## Context\n\n" + CONTEXT + "\n")


def approve_criteria(root: Path, at: str = "2026-10-28T09:00:00+00:00") -> None:
    """What `approve-criteria` writes (T029). The fingerprint is the gate's own,
    because what is under test here is the counter, not the fingerprint."""
    ticket = gate.load_ticket(root, TICKET)
    record = {"sha256": gate.criteria_sha256(ticket), "approved_by": EMAIL, "approved_at": at}
    (root / ".edad" / "hashes" / f"{TICKET}.criteria.json").write_text(json.dumps(record))


def make_repo(root: Path) -> Path:
    """A ticket with approved criteria, its spec and its two frozen test files."""
    for d in (".edad/tickets", ".edad/specs", ".edad/hashes", "tests"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / SPEC_PATH).write_text(SPEC_TEXT)
    (root / FROZEN).write_text(FROZEN_TEXT)
    (root / TIES).write_text(TIES_TEXT)
    write_ticket(root)
    approve_criteria(root)
    return root


def record_path(root: Path) -> Path:
    return root / ".edad" / "hashes" / f"{TICKET}.review.json"


def record_bytes(root: Path) -> bytes | None:
    path = record_path(root)
    return path.read_bytes() if path.exists() else None


def lock_path(root: Path) -> Path:
    return root / ".edad" / "hashes" / f"{TICKET}.json"


def rounds(root: Path) -> list[dict]:
    """The review record's rounds; [] while there is no record."""
    path = record_path(root)
    return json.loads(path.read_text())["rounds"] if path.exists() else []


class Reviewer:
    """Prints the next queued output, and keeps every argv it was launched with."""

    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.launches: list[list[str]] = []

    def __call__(self, argv: list[str]) -> str:
        self.launches.append(list(argv))
        return self.outputs.pop(0)


class Approver:
    """Locks the ticket, as `gate approve` would, and keeps every call. With a
    non-zero `code` it is an approve that refused, and writes no lock. It also
    keeps what the real approve's review check would have said at that moment,
    so a round recorded only after approve ran is visible."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls: list[tuple[Path, str]] = []
        self.review_problems: list[list[str]] = []

    def __call__(self, root: Path, ticket_id: str) -> int:
        self.calls.append((Path(root).resolve(), ticket_id))
        ticket = gate.load_ticket(Path(root), ticket_id)
        self.review_problems.append(gate.review_problems(Path(root), ticket))
        if self.code == 0:
            lock_path(Path(root)).write_text("{}\n")
        return self.code


def no_process(*args, **kwargs):
    raise AssertionError("the test review spawned a process")


def review_tests(monkeypatch, root, reviewer, approver, *disputes: str, run=no_process) -> int:
    """One `python3 -m edad.review tests T900 [--dispute F<n>=reason ...]`,
    returning its exit code whether it returns one or refuses with SystemExit.
    A runner given as None is left real, and `run` stands in for subprocess.run."""
    monkeypatch.setenv("EDAD_REPO", str(root))
    if reviewer is not None:
        monkeypatch.setattr(review, "run_reviewer", reviewer)
    if approver is not None:
        monkeypatch.setattr(review, "run_approve", approver)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    argv = ["edad.review", "tests", TICKET]
    for d in disputes:
        argv += ["--dispute", d]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        return review.main()
    except SystemExit as exc:
        return exc.code


def test_review_passes_with_only_nits_left(monkeypatch, tmp_path):
    # D9: nits are noted, not required; security, blocker or major fails the round.
    # A code fence around the JSON, or a key the format does not name, still
    # follows the format. A pass whose approve refuses exits with approve's code.
    extra = {**finding("T8", "nit", NIT), "line": 3}
    cases = {
        "nits": NITS_ONLY,
        "none": output(),
        "json fence": "```json\n" + NITS_ONLY + "\n```\n",
        "plain fence": "```\n" + NITS_ONLY + "\n```",
        "extra key": output(extra),
        "extra top-level key": json.dumps({"findings": [], "summary": "sound tests"}),
        "approve refuses": NITS_ONLY,
        "major": FAILING,
        "blocker": output(finding("T5", "blocker", "green against the base")),
        "security": output(finding("T6", "security", "reads the real home dir")),
        "nit and major": output(
            finding("T8", "nit", "naming"), finding("T2", "major", EMPTY_QUEUE)
        ),
    }
    seen = {}
    root_of_nits, approved = tmp_path / "nits", None
    for name, printed in cases.items():
        root = make_repo(tmp_path / name.replace(" ", "-"))
        approver = Approver(3 if name == "approve refuses" else 0)
        code = review_tests(monkeypatch, root, Reviewer(printed), approver)
        seen[name] = (code, [r["verdict"] for r in rounds(root)], len(approver.calls))
        if name == "nits":
            approved = (approver.calls, approver.review_problems)

    # Approve is called once the passing round is on disk, or it would refuse it.
    assert approved == ([(root_of_nits.resolve(), TICKET)], [[]])
    assert seen == {
        "nits": (0, ["pass"], 1),
        "none": (0, ["pass"], 1),
        "json fence": (0, ["pass"], 1),
        "plain fence": (0, ["pass"], 1),
        "extra key": (0, ["pass"], 1),
        "extra top-level key": (0, ["pass"], 1),
        "approve refuses": (3, ["pass"], 1),
        "major": (1, ["fail"], 0),
        "blocker": (1, ["fail"], 0),
        "security": (1, ["fail"], 0),
        "nit and major": (1, ["fail"], 0),
    }


def test_a_disputed_finding_and_its_reason_reach_the_next_reviewer(monkeypatch, tmp_path):
    # D9, D27: findings are F1, F2, ... in the order the reviewer printed them,
    # numbered per round; `--dispute` is repeatable and names a finding of the
    # most recent round, which reaches the next reviewer with the reason. A
    # reason may itself hold "=", as one quoting an assert does.
    root = make_repo(tmp_path)
    empty, tied = "an empty queue is covered", "ties: assert order([1, 1]) == [1, 1]"
    loose = "the assert is exact"
    reviewer = Reviewer(
        output(finding("T2", "major", EMPTY_QUEUE), finding("T6", "blocker", TIED_PRIORITY)),
        output(finding("T4", "major", LOOSE_ASSERT)),
        NITS_ONLY,
    )
    review_tests(monkeypatch, root, reviewer, Approver())
    review_tests(monkeypatch, root, reviewer, Approver(), f"F1={empty}", f"F2={tied}")

    review_tests(monkeypatch, root, reviewer, Approver(), f"F1={loose}")

    def shown(launch: int, issue: str, reason: str) -> bool:
        return any(issue in a and reason in a for a in reviewer.launches[launch])

    keys = ("id", "item", "severity", "issue")
    paired = [
        [(d["id"], tuple(d["finding"][k] for k in keys), d["reason"]) for d in r["disputes"]]
        for r in rounds(root)
    ]
    assert len(reviewer.launches) == 3
    assert [shown(1, EMPTY_QUEUE, empty), shown(1, TIED_PRIORITY, tied)] == [True, True]
    assert shown(2, LOOSE_ASSERT, loose) is True
    assert paired == [
        [],
        [
            ("F1", ("F1", "T2", "major", EMPTY_QUEUE), empty),
            ("F2", ("F2", "T6", "blocker", TIED_PRIORITY), tied),
        ],
        [("F1", ("F1", "T4", "major", LOOSE_ASSERT), loose)],
    ]


def test_a_dispute_that_names_no_finding_of_the_last_round_is_refused(monkeypatch, tmp_path):
    # D27: a dispute the next reviewer could not rule on is refused, launching
    # nothing and writing nothing: an id the last round did not print, a missing
    # or empty reason, a bad id, or a dispute before any round has run.
    root = make_repo(tmp_path / "after-a-round")
    reviewer = Reviewer(FAILING)
    review_tests(monkeypatch, root, reviewer, Approver())
    before = record_bytes(root)
    seen = {}
    bad = ("F2=it is covered", "F0=it is covered", "F1=", "F1= ", "F1", "1=it is covered", "x")
    for dispute in bad:
        code = review_tests(monkeypatch, root, reviewer, Approver(), dispute)
        seen[dispute] = (code, len(reviewer.launches), record_bytes(root) == before)
    # One bad dispute refuses the whole invocation, even beside a good one.
    mixed = ("F1=it is covered", "F9=so is this")
    code = review_tests(monkeypatch, root, reviewer, Approver(), *mixed)
    seen["good and bad"] = (code, len(reviewer.launches), record_bytes(root) == before)
    fresh = make_repo(tmp_path / "no-round-yet")
    first = Reviewer(NITS_ONLY)
    early = review_tests(monkeypatch, fresh, first, Approver(), "F1=it is covered")
    # Round 1 printed F1 and F2, round 2 only F1: F2 is no finding of the last round.
    stale = make_repo(tmp_path / "earlier-round-only")
    two = output(finding("T2", "major", EMPTY_QUEUE), finding("T2", "major", TIED_PRIORITY))
    third = Reviewer(two, FAILING, NITS_ONLY)
    review_tests(monkeypatch, stale, third, Approver())
    review_tests(monkeypatch, stale, third, Approver())
    stale_before = record_bytes(stale)
    late = review_tests(monkeypatch, stale, third, Approver(), "F2=ties are covered")

    assert seen == {d: (2, 1, True) for d in seen}
    assert (early, first.launches, record_bytes(fresh)) == (2, [], None)
    assert (late, len(third.launches), record_bytes(stale) == stale_before) == (2, 2, True)


def test_malformed_reviewer_output_counts_as_a_failed_round(monkeypatch, tmp_path):
    # D9: output that is not the expected structure is a failed round that counts
    # toward the three, never a pass and never a crash.
    cases = {
        "prose": "The tests look thorough to me. No findings.",
        "empty": "",
        "not an object": json.dumps([finding("T2", "major", EMPTY_QUEUE)]),
        "no findings key": json.dumps({}),
        "findings null": json.dumps({"findings": None}),
        "findings not a list": json.dumps({"findings": "none"}),
        "finding not an object": json.dumps({"findings": ["T2 major"]}),
        "no severity": json.dumps({"findings": [{"item": "T8", "issue": "naming"}]}),
        "no item": json.dumps({"findings": [{"severity": "nit", "issue": "naming"}]}),
        "item not a string": output(finding(8, "nit", "naming")),
        "no issue": json.dumps({"findings": [{"item": "T8", "severity": "nit"}]}),
        "unknown severity": output(finding("T8", "critical", "naming")),
        "truncated": NITS_ONLY[:-2],
        "prose around json": "Here are my findings:\n" + NITS_ONLY,
        "prose around a fence": "Here are my findings:\n```json\n" + NITS_ONLY + "\n```",
        "two fences": "```\n```json\n" + NITS_ONLY + "\n```\n```",
        "findings an object": json.dumps({"findings": {}}),
        "issue not a string": output(finding("T8", "nit", 5)),
    }
    seen = {}
    for name, printed in cases.items():
        root = make_repo(tmp_path / name.replace(" ", "-"))
        approver = Approver()
        code = review_tests(monkeypatch, root, Reviewer(printed), approver)
        seen[name] = (code, [(r["round"], r["verdict"]) for r in rounds(root)], len(approver.calls))

    # Counted toward the three: after three of them a fourth round is refused.
    root = make_repo(tmp_path / "three-malformed")
    garbage = Reviewer(cases["prose"], cases["empty"], cases["truncated"], NITS_ONLY)
    codes = [review_tests(monkeypatch, root, garbage, Approver()) for _ in range(4)]

    assert seen == {name: (1, [(1, "fail")], 0) for name in cases}
    assert (codes, len(garbage.launches)) == ([1, 1, 1, 2], 3)


def test_review_record_is_written_beside_the_lock(monkeypatch, tmp_path):
    # D11: one record, `.edad/hashes/<T>.review.json`, every round appended to it,
    # in the shape approve reads: after a passing round, approve's review check is met.
    # Each round keeps the frozen bytes it read: the writer revises between rounds.
    root = make_repo(tmp_path)
    reviewer = Reviewer(FAILING, NITS_ONLY)

    def hashes() -> dict[str, str]:
        return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in (FROZEN, TIES)}

    review_tests(monkeypatch, root, reviewer, Approver())
    first_bytes = hashes()
    revised = FROZEN_TEXT + "\n\ndef test_queue_handles_empty():\n    assert order([]) == []\n"
    (root / FROZEN).write_text(revised)
    reason = "test_queue_handles_empty covers it"
    approver = Approver()
    code = review_tests(monkeypatch, root, reviewer, approver, f"F1={reason}")
    # A pass after a failed round still locks; then the fake approve's lock goes,
    # so the only file left to see is the review's.
    locked = (code, len(approver.calls), lock_path(root).exists())
    lock_path(root).unlink(missing_ok=True)

    got = rounds(root)

    assert sorted(p.name for p in (root / ".edad" / "hashes").iterdir()) == [
        f"{TICKET}.criteria.json",
        f"{TICKET}.review.json",
    ]
    assert locked == (0, 1, True)
    assert first_bytes != hashes()
    assert [(r["round"], r["verdict"], r["frozen"]) for r in got] == [
        (1, "fail", first_bytes),
        (2, "pass", hashes()),
    ]
    keys = ("id", "item", "severity", "issue")
    assert [[{k: f[k] for k in keys} for f in r["findings"]] for r in got] == [
        [{"id": "F1", "item": "T2", "severity": "major", "issue": EMPTY_QUEUE}],
        [{"id": "F1", "item": "T8", "severity": "nit", "issue": NIT}],
    ]
    disputes = [[(d["id"], d["finding"]["issue"], d["reason"]) for d in r["disputes"]] for r in got]
    assert disputes == [[], [("F1", EMPTY_QUEUE, reason)]]
    assert gate.review_problems(root, gate.load_ticket(root, TICKET)) == []


def test_each_invocation_runs_one_round_and_a_fourth_is_refused(monkeypatch, tmp_path, capsys):
    # D27: one reviewer per invocation; a fourth invocation launches nothing,
    # changes nothing and names the way out.
    root = make_repo(tmp_path)
    reviewer = Reviewer(FAILING, FAILING, FAILING, NITS_ONLY)
    codes, launched = [], []
    for _ in range(3):
        codes.append(review_tests(monkeypatch, root, reviewer, Approver()))
        launched.append(len(reviewer.launches))
    before = record_bytes(root)
    capsys.readouterr()

    codes.append(review_tests(monkeypatch, root, reviewer, Approver()))

    assert codes == [1, 1, 1, 2]
    assert launched == [1, 2, 3]
    assert len(reviewer.launches) == 3
    assert record_bytes(root) == before
    assert "approve-criteria" in capsys.readouterr().err


def test_round_counter_resets_only_when_criteria_are_reapproved(monkeypatch, tmp_path):
    # D27: approving the same criteria again resets nothing, and neither does
    # changing them without approval; approving changed criteria starts again at 1.
    root = make_repo(tmp_path)
    reviewer = Reviewer(FAILING, FAILING, FAILING, FAILING)
    for _ in range(3):
        review_tests(monkeypatch, root, reviewer, Approver())
    codes = []

    approve_criteria(root, at="2026-10-29T09:00:00+00:00")
    codes.append(review_tests(monkeypatch, root, reviewer, Approver()))
    write_ticket(root, acceptance="test_queue_orders_ties_by_arrival")
    codes.append(review_tests(monkeypatch, root, reviewer, Approver()))
    approve_criteria(root, at="2026-10-30T09:00:00+00:00")
    codes.append(review_tests(monkeypatch, root, reviewer, Approver()))

    assert codes == [2, 2, 1]
    assert len(reviewer.launches) == 4
    assert [r["round"] for r in rounds(root)] == [1, 2, 3, 1]


def test_review_stops_after_three_rounds_and_leaves_ticket_unlocked(monkeypatch, tmp_path):
    # D1: three failed rounds and the ticket is not locked, even when a fourth
    # reviewer would have passed it; approve is never called.
    root = make_repo(tmp_path)
    reviewer = Reviewer(FAILING, FAILING, FAILING, NITS_ONLY)
    approver = Approver()

    for _ in range(4):
        review_tests(monkeypatch, root, reviewer, approver)

    assert approver.calls == []
    assert lock_path(root).exists() is False
    assert [r["verdict"] for r in rounds(root)] == ["fail", "fail", "fail"]


def test_the_reviewer_is_given_the_spec_every_frozen_file_and_the_tests_rubric_and_no_tools(
    monkeypatch, tmp_path
):
    # D27, D5: the round's one reviewer is a new `claude -p` whose prompt holds
    # the ticket's spec, each frozen file under its path, and the tests rubric;
    # `--tools ""` leaves it nothing else to read. The ticket is not an input:
    # its Context is the writer's reasoning (D5).
    root = make_repo(tmp_path)
    reviewer = Reviewer(NITS_ONLY)

    review_tests(monkeypatch, root, reviewer, Approver())

    argv = reviewer.launches[0] if reviewer.launches else []
    prompt = next((a for a in argv if SPEC_TEXT in a), "")
    parts = (FROZEN, FROZEN_TEXT, TIES, TIES_TEXT, review.load_rubric("tests"))
    assert (len(reviewer.launches), argv[:2]) == (1, ["claude", "-p"])
    assert [part in prompt for part in parts] == [True] * len(parts)
    only_in_ticket = ("edad/queue.py", "Order the queue", CONTEXT)
    assert [text in prompt for text in only_in_ticket] == [False, False, False]
    assert [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--tools"] == [""]


def test_a_passing_round_runs_gate_approve_in_the_repo(monkeypatch, tmp_path):
    # D27: the real approve runner is `python3 -m edad.gate approve <T>` in the
    # repo, and its exit code is the command's.
    root = make_repo(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), Path(kwargs.get("cwd") or ".").resolve()))
        if kwargs.get("check"):  # as the real one does: a refused approve would raise
            raise subprocess.CalledProcessError(5, argv)
        return subprocess.CompletedProcess(argv, 5, stdout="", stderr="")

    code = review_tests(monkeypatch, root, Reviewer(NITS_ONLY), None, run=fake_run)

    assert code == 5
    assert calls == [([sys.executable, "-m", "edad.gate", "approve", TICKET], root.resolve())]


def test_a_reviewer_that_fails_to_run_uses_up_no_round(monkeypatch, tmp_path):
    # D27: a reviewer process that exits non-zero judged nothing, so the
    # invocation is refused, nothing is recorded, and the next reviewer that
    # does run is round 1.
    root = make_repo(tmp_path)
    approver = Approver()

    def crashed(argv, **kwargs):
        # It printed well-formed output before failing: the exit code decides, not the text.
        return subprocess.CompletedProcess(argv, 1, stdout=NITS_ONLY, stderr="claude: interrupted")

    def reviewed(argv, **kwargs):
        # The real stdout exists only when the process's output is captured as text.
        captured = kwargs.get("capture_output") is True and kwargs.get("text") is True
        return subprocess.CompletedProcess(argv, 0, stdout=NITS_ONLY if captured else None)

    codes = [review_tests(monkeypatch, root, None, approver, run=crashed)]
    after_crash = (record_bytes(root), len(approver.calls))
    codes.append(review_tests(monkeypatch, root, None, approver, run=reviewed))

    assert codes == [2, 0]
    assert after_crash == (None, 0)
    assert [(r["round"], r["verdict"]) for r in rounds(root)] == [(1, "pass")]
