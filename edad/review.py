"""Review loops: everything that launches a reviewer model (review-loops D17).

Kept out of `edad.gate`, which is the judge: agent-invoking code does not belong
inside the verifier.

`tests <T>` runs exactly one round per invocation (D27).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

from edad import gate


def load_rubric(name: str) -> str:
    """The checklist `edad/rubrics/<name>.md`, read from the installed package."""
    return (resources.files("edad") / "rubrics" / f"{name}.md").read_text(encoding="utf-8")


def review_prompt(
    spec: str, artifact: str, rubric: str, *, disputes: list[dict] | None = None
) -> str:
    """The reviewer's whole prompt: the spec, the artifact under review and the
    rubric, and nothing else (D5). The instruction comes first: a spec opens with
    `---` front matter, and an argv element starting with `-` reads as a flag.
    `disputes` are the writer's replies to the last round's findings."""
    text = (
        "You are a reviewer. Judge the ARTIFACT against the SPEC, checking every item "
        "of the RUBRIC. Reply with only a JSON object: "
        '{"findings": [{"item": <rubric item id>, '
        '"severity": "security" | "blocker" | "major" | "nit", "issue": "<what is wrong>"}]}. '
        'With nothing to report, reply {"findings": []}.\n\n'
        f"=== SPEC ===\n{spec}\n\n"
        f"=== ARTIFACT ===\n{artifact}\n\n"
        f"=== RUBRIC ===\n{rubric}\n"
    )
    if disputes:
        text += (
            "\n=== DISPUTES ===\nThe writer disputes these findings of the previous round. "
            "Rule on each: keep the finding if the reason does not answer it.\n"
        )
        for d in disputes:
            f = d["finding"]
            text += (
                f"\n{d['id']} [{f['item']}, {f['severity']}]: {f['issue']}\n"
                f"Writer's reason: {d['reason']}\n"
            )
    return text


REVIEWER_SYSTEM_PROMPT = (
    "You are a reviewer. Read the material in the user's message and report "
    "your findings exactly as that message instructs."
)


def reviewer_argv(prompt: str) -> list[str]:
    """A brand-new `claude -p` reviewer process, never a resumed one (D5), with
    every tool off and a fixed `--system-prompt` in place of Claude Code's
    default. The prompt is the only task material it gets, but `claude` still
    injects the account email, username, platform, date and model id."""
    return ["claude", "-p", prompt, "--system-prompt", REVIEWER_SYSTEM_PROMPT, "--tools", ""]


def run_reviewer(argv: list[str]) -> str:
    """Launch the reviewer in a fresh empty directory outside any project, so
    `claude` finds no CLAUDE.md, git status or memory; the directory is deleted
    when the process exits. Return what it printed. A reviewer that exits
    non-zero judged nothing: refuse, so no round is used up."""
    with tempfile.TemporaryDirectory(prefix="edad-reviewer-") as empty:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False, cwd=empty)
    if proc.returncode != 0:
        gate.die(f"the reviewer exited {proc.returncode}; no round recorded: {proc.stderr.strip()}")
    return proc.stdout


def run_approve(root: Path, ticket_id: str) -> int:
    """`python3 -m edad.gate approve <T>` in `root`; its exit code."""
    return subprocess.run(
        [sys.executable, "-m", "edad.gate", "approve", ticket_id], cwd=root, check=False
    ).returncode


MAX_ROUNDS = 3
SEVERITIES = ("security", "blocker", "major", "nit")
FAILING = ("security", "blocker", "major")
FENCE = re.compile(r"\A```(?:json)?[ \t]*\n(.*)\n```\Z", re.DOTALL)


def parse_findings(text: str) -> list[dict] | None:
    """The reviewer's findings, numbered F1.. in print order; None if malformed."""
    text = text.strip()
    m = FENCE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return None
    out = []
    for i, f in enumerate(data["findings"], 1):
        if (
            not isinstance(f, dict)
            or not isinstance(f.get("item"), str)
            or not isinstance(f.get("issue"), str)
            or f.get("severity") not in SEVERITIES
        ):
            return None
        out.append(
            {"id": f"F{i}", "item": f["item"], "severity": f["severity"], "issue": f["issue"]}
        )
    return out


def parse_disputes(raw: list[str], last: dict | None) -> list[dict]:
    """Each `F<n>=reason` against the last round's findings; refuses on any bad one."""
    if raw and last is None:
        gate.die("--dispute given before any round has run; there is no finding to dispute")
    known = {f["id"]: f for f in (last or {}).get("findings", [])}
    out = []
    for item in raw:
        fid, sep, reason = item.partition("=")
        if not sep or not re.fullmatch(r"F[1-9][0-9]*", fid) or not reason.strip():
            gate.die(f"bad --dispute {item!r}: expected F<n>=<reason> with a reason")
        if fid not in known:
            gate.die(f"--dispute {fid} names no finding of the last round")
        out.append({"id": fid, "finding": known[fid], "reason": reason.strip()})
    return out


def model_of(argv: list[str]) -> str | None:
    for i, a in enumerate(argv[:-1]):
        if a == "--model":
            return argv[i + 1]
    return None


def cmd_tests(args: argparse.Namespace) -> int:
    root = gate.repo_root()
    ticket = gate.load_ticket(root, args.ticket)
    tid = ticket["id"]
    criteria = gate.read_record(root, tid, "criteria")
    if not criteria or criteria.get("sha256") != gate.criteria_sha256(ticket):
        gate.die(
            f"{tid}: criteria not approved, or changed since approval; "
            f"run `approve-criteria {tid}` at a terminal"
        )
    fingerprint = criteria["sha256"]
    record = gate.read_record(root, tid, "review") or {}
    all_rounds = record.get("rounds") if isinstance(record.get("rounds"), list) else []
    counted = [r for r in all_rounds if isinstance(r, dict) and r.get("criteria") == fingerprint]
    if len(counted) >= MAX_ROUNDS:
        gate.die(
            f"{tid}: {MAX_ROUNDS} review rounds used under these criteria; change the ticket "
            f"and ask the operator for `approve-criteria {tid}`, or `override-review`"
        )
    disputes = parse_disputes(args.dispute, counted[-1] if counted else None)

    frozen = ticket.get("frozen") or []
    gate.die_on_missing_frozen(root, frozen)
    spec = (root / ticket["spec"]).read_text(encoding="utf-8")
    artifact = "\n\n".join(
        f"--- {rel} ---\n{(root / rel).read_text(encoding='utf-8')}" for rel in frozen
    )
    prompt = review_prompt(spec, artifact, load_rubric("tests"), disputes=disputes)
    argv = reviewer_argv(prompt)
    printed = run_reviewer(argv)

    findings = parse_findings(printed)
    malformed = findings is None
    findings = findings or []
    passed = not malformed and not any(f["severity"] in FAILING for f in findings)
    number = len(counted) + 1
    all_rounds.append({
        "round": number,
        "verdict": "pass" if passed else "fail",
        "model": model_of(argv),
        "frozen": gate.frozen_hashes_now(root, ticket),
        "criteria": fingerprint,
        "findings": findings,
        "disputes": disputes,
        "malformed": malformed,
    })
    gate.write_hash_record(root, tid, "review", {**record, "rounds": all_rounds})

    print(f"{tid}: review round {number} of {MAX_ROUNDS}: {'pass' if passed else 'fail'}")
    if malformed:
        print("  the reviewer's output did not match the expected format")
    for f in findings:
        print(f"  {f['id']} [{f['severity']}] {f['item']}: {f['issue']}")
    if not passed:
        return 1
    return run_approve(root, tid)


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
