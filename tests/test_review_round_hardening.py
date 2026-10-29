"""A test-review round records what was reviewed, and only rounds that ran
(review-isolation D32, D33, D34); and the reviewer process is sealed off from
the caller (D37, D38, D39).

T031 built the round: `python3 -m edad.review tests <T>` launches one reviewer,
appends the round to `.edad/hashes/<T>.review.json`, and runs approve on a
pass. T031's post-build review found four ways that round could record
something untrue:

- it hashed the frozen files after the reviewer returned, so a pass could be
  stamped on bytes the reviewer never saw (D32);
- a missing `claude`, a hung reviewer, or a ticket with nothing to review
  either crashed with a traceback or spent a round (D33);
- a corrupt review record was read as empty and overwritten (D34).

T040's post-build review found three ways the caller could still reach, or
break, the isolated reviewer:

- it inherited the caller's stdin, and `claude -p` reads piped stdin into the
  prompt (measured 2026-10-28, claude 2.1.280) (D37);
- its output was decoded with the locale's encoding, so a non-ASCII reply
  crashes under `LANG=C` (D38);
- its temp directory comes from `TMPDIR`, so a `TMPDIR` inside a project puts
  the reviewer back inside that project, silently (D39).

The round is driven through `review.main()` and `sys.argv` (seam S5). Where the
reviewer is replaced, it is replaced as `review.run_reviewer(argv) -> stdout`.
Where the real `run_reviewer` runs, only `subprocess.run` is faked. Approve is
always replaced. No test launches a model or a gate, and none shells to git.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

from edad import gate, review

TICKET = "T900"
FROZEN = "tests/test_queue.py"
TIES = "tests/test_queue_ties.py"
FROZEN_TEXT = "def test_queue_orders_by_priority():\n    assert order([2, 1]) == [1, 2]\n"
TIES_TEXT = "def test_queue_breaks_ties_by_arrival():\n    assert order([1, 1]) == [1, 1]\n"
SPEC_PATH = ".edad/specs/queue.md"
SPEC_TEXT = "---\nslug: queue\n---\nD1: the queue orders jobs by priority, lowest first\n"
NITS_ONLY = json.dumps(
    {"findings": [{"item": "T8", "severity": "nit", "issue": "the name could read better"}]}
)
REVIEWER_TIMEOUT_S = 900
PROJECT_MARKERS = (".git", "CLAUDE.md")


def inside_a_project(path: Path) -> bool:
    return any((d / m).exists() for d in (path, *path.parents) for m in PROJECT_MARKERS)


@pytest.fixture(autouse=True)
def outside_projects(monkeypatch, tmp_path_factory):
    """A fresh directory with no `.git` or `CLAUDE.md` in it or above it, made
    the system temp location for the test. It is a sibling of `tmp_path`, never
    inside the repo a test builds there. The real `run_reviewer` refuses a temp
    directory inside a project (D39), so a test that reaches it must not depend
    on where this machine's TMPDIR happens to sit."""
    candidates = [tmp_path_factory.mktemp("reviewer-tmp").resolve()]
    candidates += [Path(d).resolve() for d in ("/tmp", "/var/tmp") if Path(d).is_dir()]
    base = next((c for c in candidates if not inside_a_project(c)), None)
    if base is None:
        pytest.fail(f"no temp location outside a project among {[str(c) for c in candidates]}")
    clean = Path(tempfile.mkdtemp(prefix="edad-t041-", dir=base))
    monkeypatch.setattr(tempfile, "tempdir", str(clean))
    yield clean
    shutil.rmtree(clean, ignore_errors=True)


@pytest.fixture(autouse=True)
def claude_on_path(monkeypatch, tmp_path_factory):
    """A stand-in `claude` first on PATH, so a check for the binary finds one
    whether or not this machine has it. It is never run: `subprocess.run` is
    faked wherever the real `run_reviewer` runs."""
    bin_dir = tmp_path_factory.mktemp("bin")
    stub = bin_dir / "claude"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


def make_repo(root: Path, frozen: list[str] | None = None) -> Path:
    """A ticket with approved criteria, its spec and its frozen test files."""
    frozen = [FROZEN, TIES] if frozen is None else frozen
    for d in (".edad/tickets", ".edad/specs", ".edad/hashes", "tests"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / SPEC_PATH).write_text(SPEC_TEXT)
    (root / FROZEN).write_text(FROZEN_TEXT)
    (root / TIES).write_text(TIES_TEXT)
    fields = {
        "id": TICKET,
        "spec": SPEC_PATH,
        "title": "Order the queue",
        "decisions": ["D1"],
        "scope": ["edad/queue.py"],
        "frozen": frozen,
        "acceptance": [f"python3 -m pytest {FROZEN}::test_queue_orders_by_priority -q"],
        "full_gate": ["python3 -m pytest -q"],
        "blocked_by": [],
        "kill_conditions": {"max_iterations": 4, "max_diff_lines": 100},
    }
    ticket_path = root / ".edad" / "tickets" / f"{TICKET}.md"
    ticket_path.write_text("---\n" + yaml.safe_dump(fields, sort_keys=False) + "---\n")
    ticket = gate.load_ticket(root, TICKET)
    criteria = {"sha256": gate.criteria_sha256(ticket), "approved_by": "operator@example.com"}
    (root / ".edad" / "hashes" / f"{TICKET}.criteria.json").write_text(json.dumps(criteria))
    return root


def record_path(root: Path) -> Path:
    return root / ".edad" / "hashes" / f"{TICKET}.review.json"


def record_bytes(root: Path) -> bytes | None:
    path = record_path(root)
    return path.read_bytes() if path.exists() else None


def no_process(*args, **kwargs):
    raise AssertionError("the test review spawned a process it should not have")


class Reviewer:
    """Prints the next queued output, and keeps every argv it was launched with.
    `during` runs while the reviewer is "reading", as an edit made then would."""

    def __init__(self, *outputs: str, during=None) -> None:
        self.outputs = list(outputs)
        self.during = during
        self.launches: list[list[str]] = []

    def __call__(self, argv: list[str]) -> str:
        self.launches.append(list(argv))
        if self.during is not None:
            self.during()
        return self.outputs.pop(0)


class Approver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, root: Path, ticket_id: str) -> int:
        self.calls.append(ticket_id)
        return 0


def review_tests(monkeypatch, root, reviewer, approver, run=no_process):
    """One `python3 -m edad.review tests T900`. Returns the exit code, whether
    it is returned or raised as SystemExit; any other exception that escapes
    is returned by its type name, so a crash fails an assertion, not the run.
    A reviewer given as None is left real, and `run` stands in for subprocess.run."""
    monkeypatch.setenv("EDAD_REPO", str(root))
    if reviewer is not None:
        monkeypatch.setattr(review, "run_reviewer", reviewer)
    monkeypatch.setattr(review, "run_approve", approver)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.setattr(sys, "argv", ["edad.review", "tests", TICKET])
    try:
        return review.main()
    except SystemExit as exc:
        return exc.code
    except Exception as exc:  # the crash itself is what is asserted on
        return type(exc).__name__


def test_a_round_records_the_bytes_the_reviewer_was_shown(monkeypatch, tmp_path):
    # D32: the round's `frozen` hashes are of the bytes put in front of the
    # reviewer. A test edited while the reviewer runs must not get a pass
    # stamped on bytes the reviewer never saw.
    root = make_repo(tmp_path)
    shown = (root / FROZEN).read_bytes()
    edited = FROZEN_TEXT + "\n\ndef test_queue_is_vacuous():\n    pass\n"
    reviewer = Reviewer(NITS_ONLY, during=lambda: (root / FROZEN).write_text(edited))

    code = review_tests(monkeypatch, root, reviewer, Approver())

    prompt = reviewer.launches[0] if reviewer.launches else []
    assert code == 0
    assert any(FROZEN_TEXT in a for a in prompt) and not any("vacuous" in a for a in prompt)
    recorded = json.loads(record_path(root).read_text())["rounds"][-1]["frozen"]
    assert recorded == {
        FROZEN: hashlib.sha256(shown).hexdigest(),
        TIES: hashlib.sha256(TIES_TEXT.encode()).hexdigest(),
    }
    assert recorded[FROZEN] != hashlib.sha256((root / FROZEN).read_bytes()).hexdigest()


def test_a_missing_reviewer_binary_is_refused_and_spends_no_round(
    monkeypatch, tmp_path, tmp_path_factory, capsys
):
    # D33: no `claude` on PATH is a clean refusal (exit 2, no traceback), not
    # a crash; nothing is recorded, so the next reviewer that runs is round 1.
    root = make_repo(tmp_path)
    approver = Approver()
    empty_bin = tmp_path_factory.mktemp("empty-bin")
    monkeypatch.setenv("PATH", str(empty_bin))  # no `claude` to find, by lookup or by launch

    def missing(argv, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    code = review_tests(monkeypatch, root, None, approver, run=missing)
    err = capsys.readouterr().err

    assert (code, record_bytes(root), approver.calls) == (2, None, [])
    assert "Traceback" not in err and "claude" in err


def test_a_reviewer_that_times_out_is_refused_and_spends_no_round(monkeypatch, tmp_path, capsys):
    # D33: the reviewer is given 900 s. One still running then is a refusal
    # naming the timeout, not a failed round: a hang is an infrastructure
    # fault and must not use up one of the three rounds.
    root = make_repo(tmp_path)
    approver = Approver()
    timeouts = []

    def hung(argv, **kwargs):
        timeouts.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout") or 0)

    code = review_tests(monkeypatch, root, None, approver, run=hung)
    err = capsys.readouterr().err

    assert timeouts == [REVIEWER_TIMEOUT_S]
    assert (code, record_bytes(root), approver.calls) == (2, None, [])
    assert str(REVIEWER_TIMEOUT_S) in err


def test_a_ticket_with_no_frozen_files_launches_no_reviewer(monkeypatch, tmp_path, capsys):
    # D33: with nothing to review, the round is refused before any reviewer
    # launches, with approve's own message, since approve would refuse the
    # ticket anyway.
    root = make_repo(tmp_path, frozen=[])
    reviewer = Reviewer(NITS_ONLY)
    approver = Approver()

    code = review_tests(monkeypatch, root, reviewer, approver)
    err = capsys.readouterr().err

    assert (code, reviewer.launches, record_bytes(root), approver.calls) == (2, [], None, [])
    assert "ticket declares no frozen files" in err


# Unreadable, not an object, and an object whose `rounds` is not a list.
CORRUPT = ("{not json", "[]", '{"rounds": "three"}')


def test_a_corrupt_review_record_is_refused_and_left_alone(monkeypatch, tmp_path, capsys):
    # D34: a review record that exists but cannot be read as rounds is refused,
    # naming the file. Nothing launches and the record is never overwritten:
    # the round history is append-only, and a reset is a person's decision.
    outcomes = []
    for i, body in enumerate(CORRUPT):
        root = make_repo(tmp_path / f"repo{i}")
        record_path(root).write_text(body)
        reviewer = Reviewer(NITS_ONLY)
        approver = Approver()

        code = review_tests(monkeypatch, root, reviewer, approver)
        err = capsys.readouterr().err

        outcomes.append((
            code,
            reviewer.launches,
            record_bytes(root),
            approver.calls,
            f"{TICKET}.review.json" in err,
        ))

    assert outcomes == [(2, [], body.encode(), [], True) for body in CORRUPT]


def text_mode(kwargs) -> bool:
    return any(kwargs.get(k) for k in ("text", "universal_newlines", "encoding", "errors"))


def judged(argv, stdout, kwargs):
    """What a real `subprocess.run` returns for a reviewer that judged: text
    when asked for text, bytes when not."""
    out = stdout if text_mode(kwargs) else stdout.encode("utf-8")
    return subprocess.CompletedProcess(argv, 0, stdout=out, stderr=out[:0])


def test_the_reviewer_cannot_read_the_callers_stdin(monkeypatch, tmp_path):
    # D37: `claude -p` reads piped stdin into its prompt, so a reviewer that
    # inherits stdin from `edad.review tests` run in a pipe or a script sees
    # whatever the caller pipes in. Its stdin is closed, and the round still runs.
    root = make_repo(tmp_path)
    approver = Approver()
    stdins = []

    def run(argv, **kwargs):
        stdins.append(kwargs.get("stdin") == subprocess.DEVNULL or kwargs.get("input") is not None)
        return judged(argv, NITS_ONLY, kwargs)

    code = review_tests(monkeypatch, root, None, approver, run=run)

    assert (code, stdins, approver.calls) == (0, [True], [TICKET])


def test_the_reviewers_output_is_read_as_utf8(monkeypatch, tmp_path):
    # D38: the reviewer's reply is decoded as UTF-8 whatever the locale says, so
    # a finding in non-ASCII text is recorded as written instead of crashing
    # the round under `LANG=C`.
    root = make_repo(tmp_path)
    issue = "the name “naïve_order” reads as a café menu — rename it"
    reply = json.dumps(
        {"findings": [{"item": "T8", "severity": "nit", "issue": issue}]}, ensure_ascii=False
    )
    encodings = []

    def run(argv, **kwargs):
        encodings.append(kwargs.get("encoding") if text_mode(kwargs) else "bytes")
        return judged(argv, reply, kwargs)

    code = review_tests(monkeypatch, root, None, Approver(), run=run)

    assert len(encodings) == 1
    # bytes, decoded by the caller; or text with UTF-8 named (None is the locale's)
    used = encodings[0]
    assert used == "bytes" or (used is not None and codecs.lookup(used).name == "utf-8")
    assert code == 0
    assert json.loads(record_path(root).read_text())["rounds"][-1]["findings"][0]["issue"] == issue


def test_a_temp_directory_inside_a_project_launches_no_reviewer(
    monkeypatch, tmp_path, capsys, outside_projects
):
    # D39: the reviewer's empty directory comes from the system temp location.
    # When that location sits inside a project (a `.git` or `CLAUDE.md` in it or
    # any directory above), `claude` would load that project, so the round is
    # refused before any launch, naming what it found, and spends no round.
    # The directory it made is removed.
    outcomes = []
    # Each case's paths are neutral, so the marker named in the error can only
    # come from the one planted, and the project sits where nothing above it
    # is a project.
    for i, marker in enumerate(PROJECT_MARKERS):
        root = make_repo(tmp_path / f"case{i}")
        project = outside_projects / f"case{i}"
        (project / "tmp").mkdir(parents=True)
        if marker == ".git":
            (project / ".git").mkdir()
        else:
            (project / "CLAUDE.md").write_text("Project instructions.\n")
        monkeypatch.setattr(tempfile, "tempdir", str(project / "tmp"))
        approver = Approver()
        launches = []

        def run(argv, launches=launches, **kwargs):
            launches.append(list(argv))
            return judged(argv, NITS_ONLY, kwargs)

        code = review_tests(monkeypatch, root, None, approver, run=run)
        err = capsys.readouterr().err

        outcomes.append((
            code,
            launches,
            record_bytes(root),
            approver.calls,
            marker in err,
            list((project / "tmp").iterdir()),
        ))

    assert outcomes == [(2, [], None, [], True, [])] * 2
