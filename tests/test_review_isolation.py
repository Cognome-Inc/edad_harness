"""The test reviewer is isolated from the repo it reviews (review-isolation D30).

`--tools ""` switches the reviewer's tools off, but not the context `claude`
loads at startup. Started in the repo, a reviewer was measured (2026-10-28,
claude 2.1.280) quoting the project's memory, its branch and the night's
evidence commit. Started in an empty directory with a fixed `--system-prompt`,
it saw none of that, and no coding-assistant framing either.

These tests see the mechanism only: where the process starts, and the argv it
starts with. What the model is actually given is checked by the live canary in
`live_tests/test_reviewer_isolation.py` (D31), run by hand.

The round is driven through `review.main()` with only `subprocess.run` faked,
so the real `run_reviewer` runs (seam S5). The argv is checked through
`reviewer_argv` (seam S4). No test launches a model, and none shells to git.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from edad import gate, review

TICKET = "T900"
FROZEN = "tests/test_queue.py"
FROZEN_TEXT = "def test_queue_orders_by_priority():\n    assert order([2, 1]) == [1, 2]\n"
SPEC_PATH = ".edad/specs/queue.md"
SPEC_TEXT = "---\nslug: queue\n---\nD1: the queue orders jobs by priority, lowest first\n"
NITS_ONLY = json.dumps(
    {"findings": [{"item": "T8", "severity": "nit", "issue": "the name could read better"}]}
)
# A short role statement, not a second set of instructions: those stay in the prompt.
MAX_SYSTEM_PROMPT = 300


def make_repo(root: Path) -> Path:
    """A ticket with approved criteria, its spec and one frozen test file."""
    for d in (".edad/tickets", ".edad/specs", ".edad/hashes", "tests"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / SPEC_PATH).write_text(SPEC_TEXT)
    (root / FROZEN).write_text(FROZEN_TEXT)
    # What the reviewer must not find by walking up from where it starts.
    (root / "CLAUDE.md").write_text("Project instructions the reviewer must never see.\n")
    (root / ".git").mkdir()
    fields = {
        "id": TICKET,
        "spec": SPEC_PATH,
        "title": "Order the queue",
        "decisions": ["D1"],
        "scope": ["edad/queue.py"],
        "frozen": [FROZEN],
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


def no_process(*args, **kwargs):
    raise AssertionError("the test review spawned a process it should not have")


def test_the_reviewer_runs_in_an_empty_directory_outside_the_repo(monkeypatch, tmp_path):
    # D30: the reviewer process starts in a fresh empty directory with no
    # project above it, so `claude` finds no CLAUDE.md, git status or project
    # memory, and the directory is gone once the reviewer has exited, whether
    # it judged anything or crashed. The system temp location is pinned to a
    # directory beside the repo, so the outcome does not depend on where the
    # machine running this keeps its temp files.
    base = tmp_path.resolve()
    root = make_repo(base / "repo")
    system_tmp = base / "system-tmp"
    system_tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(system_tmp))
    exits = [1, 0]  # a reviewer that crashes, then one that judges
    seen = []

    def fake_run(argv, **kwargs):
        cwd = kwargs.get("cwd")
        where = Path(cwd).resolve() if cwd is not None else None
        seen.append({
            "cwd_given": cwd is not None,
            "is_dir": where is not None and where.is_dir(),
            "empty": where is not None and where.is_dir() and list(where.iterdir()) == [],
            "inside_repo": where is not None and where.is_relative_to(root),
            "in_system_temp": where is not None and where.is_relative_to(system_tmp),
            "project_above": where is not None and any(
                (p / marker).exists()
                for p in (where, *where.parents)
                if p.is_relative_to(base)
                for marker in (".git", "CLAUDE.md")
            ),
            "path": where,
        })
        code = exits.pop(0)
        return subprocess.CompletedProcess(argv, code, stdout=NITS_ONLY, stderr="crashed")

    approvals = []
    monkeypatch.setenv("EDAD_REPO", str(root))
    monkeypatch.chdir(root)  # where `edad.review tests` is normally run from
    monkeypatch.setattr(review, "run_approve", lambda r, t: approvals.append(t) or 0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.setattr(sys, "argv", ["edad.review", "tests", TICKET])
    codes = []
    for _ in range(2):
        try:
            codes.append(review.main())
        except SystemExit as exc:
            codes.append(exc.code)

    keys = ("cwd_given", "is_dir", "empty", "inside_repo", "in_system_temp", "project_above")
    facts = [{k: launch[k] for k in keys} for launch in seen]
    assert (codes, len(seen), approvals) == ([2, 0], 2, [TICKET])
    assert facts == [{
        "cwd_given": True,
        "is_dir": True,
        "empty": True,
        "inside_repo": False,
        "in_system_temp": True,
        "project_above": False,
    }] * 2
    paths = [launch["path"] for launch in seen]
    assert paths[0] != paths[1]  # fresh each time, never reused
    assert [p.exists() for p in paths] == [False, False]


def system_prompts(argv: list[str]) -> list[str]:
    """Every `--system-prompt` value in the argv, in either spelling."""
    values = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--system-prompt"]
    return values + [a.split("=", 1)[1] for a in argv if a.startswith("--system-prompt=")]


def test_the_reviewer_argv_replaces_the_default_system_prompt(monkeypatch):
    # D30: a fixed short `--system-prompt` replaces Claude Code's default
    # coding-assistant prompt (memory instructions, environment sections, slash
    # commands). It names the reviewer's role and nothing about the ticket; the
    # instructions stay in the prompt, which still appears once.
    monkeypatch.delenv("EDAD_REVIEW_MODEL", raising=False)
    first = review.review_prompt(SPEC_TEXT, FROZEN_TEXT, review.load_rubric("tests"))
    second = review.review_prompt("---\nslug: other\n---\nD9: another spec\n", "x = 1\n", "R1 rule")

    argvs = [review.reviewer_argv(first), review.reviewer_argv(second)]
    values = [system_prompts(argv) for argv in argvs]

    assert [argv[:2] for argv in argvs] == [["claude", "-p"]] * 2
    assert [argvs[0].count(first), argvs[1].count(second)] == [1, 1]
    assert [len(v) for v in values] == [1, 1]
    fixed = values[0][0]
    assert values[1][0] == fixed  # fixed: the same whatever is under review
    assert 0 < len(fixed.strip()) <= MAX_SYSTEM_PROMPT
    assert "review" in fixed.lower()
    assert [text in fixed for text in ("queue", "D1", "slug", "T1 ")] == [False] * 4
    assert [a for a in argvs[0] if a.startswith("--append-system-prompt")] == []
