"""Review loops: everything that launches a reviewer model (review-loops D17).

Kept out of `edad.gate`, which is the judge: agent-invoking code does not belong
inside the verifier.

STUB (T030 contract). Every name the frozen tests reach exists and returns, so
each test is red on its assertion rather than on an import or attribute error.
The ticket's agent replaces these bodies.
"""

from __future__ import annotations

import argparse


def load_rubric(name: str) -> str:
    """The checklist `edad/rubrics/<name>.md`, read from the installed package."""
    return ""


def review_prompt(spec: str, artifact: str, rubric: str) -> str:
    """The reviewer's whole prompt: the spec, the artifact under review and the
    rubric, and nothing else (D5)."""
    return ""


def reviewer_argv(prompt: str) -> list[str]:
    """A brand-new `claude -p` reviewer process, never a resumed one (D5)."""
    return []


def cmd_tests(args: argparse.Namespace) -> int:
    return 2


def cmd_panel(args: argparse.Namespace) -> int:
    return 2


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="edad.review")


def main() -> int:
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
