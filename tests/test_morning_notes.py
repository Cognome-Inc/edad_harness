"""T032: the morning notes, one act-first Markdown page per night (review-loops D20).

Seam S7 is a pure writer: `review.morning_notes(date, run_branch, sessions)`
returns the page as a string, and writing it to `.edad/runs/` is T037's. Its
`sessions` are the night's session logs, which is what the queue reads (T037):
each has `ticket`, `outcome` and `abort_reason` as today, and a `panel` that
T036 adds, or None when the session ended before the panel ran:

    panel = {
        "skipped": bool,                  # --skip-review-panel (D13)
        "unfixed": [finding, ...],        # confirmed, still open after the fix rounds (D4)
        "fixed": [finding, ...],          # confirmed and fixed overnight
        "dismissed": [finding, ...],      # refuted by the disprover, each with a "reason" (D10)
        "nits": [finding, ...],
        "mutation_score": {"killed": int, "total": int, "survivors": [str, ...],
                           "partial": bool} | None,  # D3; partial = the ten-minute stop (D16)
    }
    finding = {"item": "C3", "severity": "major", "issue": "..."}

The layout is the grill's: a title line, then exactly five sections in a fixed
order, so the operator reads what needs them first. Each test feeds the same
night and checks one section; every finding must land in its own section and in
no other, so a writer that prints everything everywhere fails.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from edad import review

DATE = "2026-10-29"
BRANCH = "edad/run-20261029T010000"
SECTIONS = ["Needs you", "Test strength", "Dismissed findings", "Fixed overnight", "Nits"]


def finding(item, severity, issue, **extra):
    return {"item": item, "severity": severity, "issue": issue, **extra}


def panel(**fields):
    base = {
        "skipped": False, "unfixed": [], "fixed": [], "dismissed": [], "nits": [],
        "mutation_score": None,
    }
    return {**base, **fields}


# Listed so that the order the page needs is not the order the sessions came in:
# the clean ticket comes first, and what needs the operator comes last.
NIGHT = [
    {   # passed clean: nothing of it belongs under "Needs you"
        "ticket": "T050", "outcome": "passed", "abort_reason": None,
        "panel": panel(
            mutation_score={
                "killed": 7, "total": 9,
                "survivors": ["edad.review.render__mutmut_3", "edad.review.render__mutmut_8"],
                "partial": True,
            },
            dismissed=[
                finding("C3", "major", "empty list crashes the loop",
                        reason="the caller filters empty lists first"),
                finding("S3", "security", "path from the log is not checked",
                        reason="the log is written by the harness itself"),
            ],
            fixed=[finding("C2", "blocker", "swallowed OSError on write")],
            nits=[
                finding("C4", "nit", "rename tmp to scratch"),
                finding("C5", "nit", "two helpers could be one"),
            ],
        ),
    },
    {   # passed with an unfixed major
        "ticket": "T051", "outcome": "passed", "abort_reason": None,
        "panel": panel(
            mutation_score={"killed": 5, "total": 5, "survivors": [], "partial": False},
            unfixed=[finding("C1", "major", "off-by-one drops the last ticket")],
            nits=[finding("C4", "nit", "docstring says queue, means session")],
        ),
    },
    {   # failed in review: an unfixed security finding
        "ticket": "T052", "outcome": "review_failed",
        "abort_reason": "unfixed security finding after 2 fix rounds",
        "panel": panel(unfixed=[finding("S2", "security", "token written to the session log")]),
    },
    {   # the panel was skipped
        "ticket": "T053", "outcome": "passed", "abort_reason": None,
        "panel": panel(skipped=True),
    },
    {   # failed in the build loop: the panel never ran
        "ticket": "T054", "outcome": "aborted", "abort_reason": "max_iterations reached",
        "panel": None,
    },
    {   # passed, but the run stopped before any mutant finished: a score of nothing
        "ticket": "T055", "outcome": "passed", "abort_reason": None,
        "panel": panel(mutation_score={"killed": 0, "total": 0, "survivors": [], "partial": True}),
    },
]


@pytest.fixture(autouse=True)
def pure(monkeypatch, tmp_path):
    """S7 is pure: it spawns nothing, and the tests run where a stray file would show."""
    def no_process(*args, **kwargs):
        raise AssertionError("the notes writer spawned a process")

    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.chdir(tmp_path)
    yield
    assert list(tmp_path.iterdir()) == [], "the notes writer wrote a file"


def sections(page):
    """The `## ` headings in page order, and {heading: [lines]} for every expected one."""
    order, body, current = [], {h: [] for h in SECTIONS}, None
    for line in page.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            order.append(current)
            body.setdefault(current, [])
        elif current is not None:
            body[current].append(line)
    return order, body


def where(page, text):
    """The headings of every section whose lines contain `text`."""
    _, body = sections(page)
    return [h for h, lines in body.items() if any(text in line for line in lines)]


def line_index(lines, *parts):
    """Index of the first line containing every one of `parts`."""
    for i, line in enumerate(lines):
        if all(p in line for p in parts):
            return i
    raise AssertionError(f"no line contains all of {parts!r}:\n" + "\n".join(lines))


def notes(sessions=NIGHT):
    page = review.morning_notes(DATE, BRANCH, sessions)
    assert isinstance(page, str)
    return page


def test_morning_notes_put_needs_you_first_and_nits_last():
    # D20: a title naming the night and its run branch, then the five sections in order
    page = notes()
    assert page.splitlines()[:1] == [f"# Night {DATE} - run branch {BRANCH}"]
    order, _ = sections(page)
    assert order == SECTIONS


def test_morning_notes_keep_every_section_when_the_night_has_nothing_to_report():
    # D20: the layout is fixed, so an empty night still has all five headings
    page = notes([])
    assert page.splitlines()[:1] == [f"# Night {DATE} - run branch {BRANCH}"]
    order, _ = sections(page)
    assert order == SECTIONS


def test_needs_you_lists_the_panel_skip_then_failed_tickets_then_unfixed_majors():
    # D20 "Needs you" (D13 skip stamp at the top; D4 unfixed major flagged first)
    page = notes()
    _, body = sections(page)
    lines = body["Needs you"]
    skip = line_index(lines, "T053", "skipped")
    failed = [line_index(lines, "T052", "review_failed"), line_index(lines, "T054", "aborted")]
    major = line_index(lines, "T051", "off-by-one drops the last ticket")
    assert skip < min(failed)
    assert max(failed) < major
    assert where(page, "unfixed security finding after 2 fix rounds") == ["Needs you"]
    assert where(page, "max_iterations reached") == ["Needs you"]
    assert where(page, "token written to the session log") == ["Needs you"]
    assert where(page, "off-by-one drops the last ticket") == ["Needs you"]
    assert not any("T050" in line for line in lines), "a clean ticket needs nothing"


def test_test_strength_shows_each_tickets_mutation_score_and_its_survivors():
    # D20 "Test strength" (D3: survivors reach the notes; D16: a stopped run says partial)
    page = notes()
    _, body = sections(page)
    lines = body["Test strength"]
    t050 = line_index(lines, "T050")
    t051 = line_index(lines, "T051")
    assert re.search(r"\b7 ?/ ?9\b", lines[t050])
    assert "partial" in lines[t050]
    assert re.search(r"\b5 ?/ ?5\b", lines[t051])
    assert "partial" not in lines[t051]
    for survivor in ("edad.review.render__mutmut_3", "edad.review.render__mutmut_8"):
        assert t050 < line_index(lines, survivor) < t051, "a survivor sits under its ticket"
        assert where(page, survivor) == ["Test strength"]
    # a 0/0 score is shown as it is, not divided into a percentage
    t055 = lines[line_index(lines, "T055")]
    assert re.search(r"\b0 ?/ ?0\b", t055)
    assert "partial" in t055
    # no score was measured for these, so none may be shown
    for ticket in ("T052", "T053", "T054"):
        assert not any(ticket in line and re.search(r"\d ?/ ?\d", line) for line in lines)


def test_dismissed_findings_are_listed_each_with_its_own_reason():
    # D20 "Dismissed findings (with reasons)" (D10)
    page = notes()
    _, body = sections(page)
    lines = body["Dismissed findings"]
    line_index(lines, "T050", "empty list crashes the loop", "the caller filters empty lists first")
    line_index(lines, "T050", "path from the log is not checked",
               "the log is written by the harness itself")
    assert where(page, "empty list crashes the loop") == ["Dismissed findings"]
    assert where(page, "the caller filters empty lists first") == ["Dismissed findings"]
    assert where(page, "path from the log is not checked") == ["Dismissed findings"]
    assert where(page, "the log is written by the harness itself") == ["Dismissed findings"]


def test_fixed_overnight_lists_the_findings_the_fix_rounds_closed():
    # D20 "Fixed overnight"
    page = notes()
    _, body = sections(page)
    line_index(body["Fixed overnight"], "T050", "swallowed OSError on write")
    assert where(page, "swallowed OSError on write") == ["Fixed overnight"]


def test_nits_are_grouped_under_their_ticket():
    # D20 "Nits (grouped by ticket)"
    page = notes()
    _, body = sections(page)
    lines = body["Nits"]
    t050 = line_index(lines, "T050")
    t051 = line_index(lines, "T051")
    rename = line_index(lines, "rename tmp to scratch")
    helpers = line_index(lines, "two helpers could be one")
    docstring = line_index(lines, "docstring says queue, means session")
    assert t050 <= rename < t051
    assert t050 <= helpers < t051
    assert t051 <= docstring
    for nit in ("rename tmp to scratch", "two helpers could be one",
                "docstring says queue, means session"):
        assert where(page, nit) == ["Nits"]
