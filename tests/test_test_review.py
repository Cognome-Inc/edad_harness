"""The daytime test review (review-loops D5; T031 adds D1, D9, D11, D27 here).

T030 (D5): the writer is the ticket-making session, and the reviewer is always
a brand-new `claude -p` process given only the spec, the tests and the rubric.
A resumed or continued session would carry the writer's conversation, and the
whole point of the review is a reader not anchored on the writer's reasoning.

The builders are pure, in the style of `edad.session.agent_argv`. The argv is
checked for properties, not equality, so the model pin that T034 adds (D15)
does not break this test. The prompt builder's first three inputs are pinned;
a later ticket may add an input only as a keyword with a default (T031's
disputes, T034's bandit output), so it is named where it is passed.
"""

from __future__ import annotations

import inspect

from edad import review

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
