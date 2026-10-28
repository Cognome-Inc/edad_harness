"""Review loops: everything that launches a reviewer model (review-loops D17).

Kept out of `edad.gate`, which is the judge: agent-invoking code does not belong
inside the verifier.

STUB (T031 contract): `cmd_tests`, `run_reviewer` and `run_approve` exist and
return, and the parser takes `--dispute`, so each frozen test in
`tests/test_test_review.py` is red on its assertion rather than on an attribute
error. The ticket's agent replaces these bodies.
"""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path


def load_rubric(name: str) -> str:
    """The checklist `edad/rubrics/<name>.md`, read from the installed package."""
    return (resources.files("edad") / "rubrics" / f"{name}.md").read_text(encoding="utf-8")


def review_prompt(spec: str, artifact: str, rubric: str) -> str:
    """The reviewer's whole prompt: the spec, the artifact under review and the
    rubric, and nothing else (D5). The instruction comes first: a spec opens with
    `---` front matter, and an argv element starting with `-` reads as a flag."""
    return (
        "You are a reviewer. Judge the ARTIFACT against the SPEC, checking every item "
        "of the RUBRIC. Report each finding with its item id and a severity.\n\n"
        f"=== SPEC ===\n{spec}\n\n"
        f"=== ARTIFACT ===\n{artifact}\n\n"
        f"=== RUBRIC ===\n{rubric}\n"
    )


def reviewer_argv(prompt: str) -> list[str]:
    """A brand-new `claude -p` reviewer process, never a resumed one (D5)."""
    return ["claude", "-p", prompt]


def run_reviewer(argv: list[str]) -> str:
    """Launch the reviewer and return what it printed."""
    return ""


def run_approve(root: Path, ticket_id: str) -> int:
    """`python3 -m edad.gate approve <T>` in `root`; its exit code."""
    return 2


def cmd_tests(args: argparse.Namespace) -> int:
    print("edad.review tests: not built yet (T031)", file=sys.stderr)
    return 2


def cmd_panel(args: argparse.Namespace) -> int:
    print("edad.review panel: not built yet (T036)", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="edad.review")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tests", help="review a ticket's frozen tests")
    t.add_argument("ticket")
    t.add_argument(
        "--dispute", action="append", default=[], metavar='F<n>="reason"',
        help="dispute a finding of the last round; the next reviewer rules on it",
    )
    t.set_defaults(func=cmd_tests)
    n = sub.add_parser("panel", help="re-run the review panel on a worktree")
    n.add_argument("ticket")
    n.set_defaults(func=cmd_panel)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
