"""T030: the review module's CLI and its rubrics (review-loops D17, D18, D19).

`edad.review` is where every model launch in the review loops lives, kept out of
the gate (D17). Its parser is built apart from `main()`, as `edad.session` does
it, so the wiring is testable without spawning a process: each subcommand is
checked to reach its own handler, with the handlers faked and any subprocess
call turned into a failure.

The rubrics are the grill's checklists (D18: T1-T8; D19: C1-C6 and S1-S6). The
grill leaves their wording a preference, so the tests pin each item's id and
label, in its own rubric file and in the prompt built from it, and no other
rubric's ids in that prompt.

The harness is pip-installed into targets, and `packages = ["edad"]` ships
`.py` files only. A rubric that is not package data exists in this checkout and
in no install, so the reviewer's prompt would lose its checklist on every target
and nowhere here. The rubrics are therefore loaded from outside the checkout's
root, and the last test pins the package-data entry that ships them.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from edad import review

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SPEC = "SPEC: the change a ticket must make"
ARTIFACT = "def test_the_change(): ..."

RUBRIC_ITEMS = {
    "tests": [
        "T1 TRACE", "T2 COVERAGE", "T3 ONE THING", "T4 ASSERTS",
        "T5 RED FIRST", "T6 ISOLATED", "T7 SETUP", "T8 NAMES",
    ],
    "code": [
        "C1 correctness", "C2 error handling", "C3 edge cases",
        "C4 fits the codebase", "C5 a simpler shape", "C6 scope creep",
    ],
    "security": [
        "S1 injection", "S2 secrets", "S3 untrusted input",
        "S4 unsafe deserialization", "S5 permissions", "S6 dependency",
    ],
}
ITEM_IDS = {"tests": r"\bT[1-8]\b", "code": r"\bC[1-6]\b", "security": r"\bS[1-6]\b"}


def no_process(*args, **kwargs):
    raise AssertionError("the CLI wiring spawned a process")


def test_review_cli_has_tests_and_panel_subcommands(monkeypatch):
    # D17: each subcommand reaches its own handler, and nothing is spawned.
    calls = []
    monkeypatch.setattr(review, "cmd_tests", lambda args: calls.append(("tests", args.ticket)) or 0)
    monkeypatch.setattr(review, "cmd_panel", lambda args: calls.append(("panel", args.ticket)) or 0)
    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(subprocess, "Popen", no_process)

    codes = []
    for cmd in ("tests", "panel"):
        monkeypatch.setattr(sys, "argv", ["edad.review", cmd, "T030"])
        codes.append(review.main())

    assert codes == [0, 0]
    assert calls == [("tests", "T030"), ("panel", "T030")]


def test_review_cli_without_a_subcommand_or_ticket_exits_with_usage(monkeypatch):
    # D17: a missing subcommand or ticket is argparse's usage error, not a crash.
    monkeypatch.setattr(review, "cmd_tests", lambda args: 0)
    monkeypatch.setattr(review, "cmd_panel", lambda args: 0)
    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    codes = []
    for argv in (["edad.review"], ["edad.review", "tests"], ["edad.review", "panel"]):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            review.main()
        codes.append(exc.value.code)

    assert codes == [2, 2, 2]


def test_every_rubric_item_reaches_the_reviewer_prompt(monkeypatch, tmp_path):
    # D18, D19: each item lives in its own rubric file and reaches only its own prompt.
    monkeypatch.chdir(tmp_path)
    missing, foreign = {}, {}
    for name, items in RUBRIC_ITEMS.items():
        rubric = review.load_rubric(name)
        prompt = review.review_prompt(SPEC, ARTIFACT, rubric)
        missing[name] = [i for i in items if i not in rubric or i not in prompt]
        foreign[name] = [
            other for other, ids in ITEM_IDS.items() if other != name and re.search(ids, prompt)
        ]

    assert missing == {"tests": [], "code": [], "security": []}
    assert foreign == {"tests": [], "code": [], "security": []}


def test_rubric_files_ship_as_package_data():
    # D18, D19: the rubrics reach the prompt on a git+ install, not only in this checkout.
    # Patterns are resolved as setuptools resolves them, by glob from the package
    # directory, where "*" stops at a "/": "*.md" ships nothing under rubrics/.
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    package_data = config["tool"]["setuptools"].get("package-data", {})
    patterns = [*package_data.get("edad", []), *package_data.get("*", [])]
    package = PROJECT_ROOT / "edad"

    shipped = {p.relative_to(package).as_posix() for pat in patterns for p in package.glob(pat)}

    assert [f"rubrics/{name}.md" in shipped for name in RUBRIC_ITEMS] == [True, True, True]
