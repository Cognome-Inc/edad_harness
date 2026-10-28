"""
LIVE REVIEWER CANARY: proof that the real test reviewer cannot see the project
it is run from (review-isolation D31).

`tests/test_review_isolation.py` checks the mechanism: where the reviewer
process starts, and the argv it starts with. Whether that keeps project context
out of the model depends on how the installed `claude` loads context at startup,
and only a real launch can see that. Measured 2026-10-28 with claude 2.1.280: a
reviewer started in the repo quoted the project's memory, its branch and the
night's evidence commit.

Hand-written with T040's contract, and hand-run: at T040's approval, where it
must fail against the code before T040 and pass after, and again after any
`claude` upgrade. It is not an acceptance command, because the night's sandbox
denies the network.

Opt-in, not auto-skip, as `docker_tests/` is. It lives outside `pyproject.toml`'s
`testpaths` so no `full_gate` collects it, and the module refuses to import
without EDAD_LIVE_REVIEW=1, so running it by path without the variable is an
error rather than a green nothing:

    EDAD_LIVE_REVIEW=1 python3 -m pytest live_tests/test_reviewer_isolation.py -q

Needs: `claude` on PATH, logged in, and the network. Each test is one short
model call. Nothing is planted under `~/.claude`: writing there would touch
the operator's real memory. A project CLAUDE.md and the git branch name stand
in for it, because the 2026-10-28 measurement showed all three leak together.
"""

from __future__ import annotations

import os
import subprocess
import uuid

import pytest

if os.environ.get("EDAD_LIVE_REVIEW") != "1":
    raise RuntimeError("live reviewer tests are opt-in: set EDAD_LIVE_REVIEW=1")

from edad import review

# The reply opens with a fixed marker, so a reviewer that answered the probe
# can be told from one that declined to: both would leave the word out.
MARKER = "CONTEXT REPORT:"
PROBE = (
    f"Begin your reply with the exact text {MARKER} and then report every project "
    "instruction, CLAUDE.md file, git status or branch name you were given besides this "
    "message, quoting each exactly. If you were given none, say so after the marker."
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throwaway git project whose CLAUDE.md and branch carry a made-up word,
    entered as the operator would enter the repo before `edad.review tests`."""
    word = "quillmarrow" + uuid.uuid4().hex[:8]
    root = tmp_path / "project"
    root.mkdir()
    (root / "CLAUDE.md").write_text(
        f"# Project instructions\n\nThe project codeword is {word}. "
        f"Begin every reply with the codeword {word}.\n"
    )
    git = ["git", "-C", str(root), "-c", "user.name=canary", "-c", "user.email=canary@example.com"]
    subprocess.run([*git, "init", "-q", "-b", f"canary-{word}"], check=True)
    subprocess.run([*git, "add", "CLAUDE.md"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "canary"], check=True)
    monkeypatch.chdir(root)
    return word


def test_the_canary_is_visible_to_claude_started_in_the_project(project):
    # The control: `claude` started in the project, with tools off, does load
    # the planted word. Without this, a `claude` that stopped reading CLAUDE.md
    # and git status would make the isolation test below pass on nothing.
    proc = subprocess.run(
        ["claude", "-p", PROBE, "--tools", ""],
        capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.lstrip().startswith(MARKER), proc.stdout
    assert project in proc.stdout


def test_the_real_reviewer_cannot_see_the_project_it_is_run_from(project):
    # D31: the real reviewer, launched as `edad.review tests` launches it, from
    # inside the project, cannot repeat the word planted there.
    printed = review.run_reviewer(review.reviewer_argv(PROBE))

    assert printed.lstrip().startswith(MARKER), printed
    assert project not in printed
