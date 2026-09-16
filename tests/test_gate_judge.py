"""Which copy of the gate judges, and which is judged.

The harness develops itself, so every agent worktree carries a full copy of
`edad/` - including `gate.py`, the module that will judge it - and tickets edit
that very file. Two copies are in play on every night. The JUDGE is the copy the
controller process imported: the main checkout when the harness builds itself,
the installed harness for any other target. The SUBJECT is the worktree, and the
commands the gate runs in it import their own copy, because the working
directory wins on `sys.path`. Nothing pinned either half before this file.

The one way the two collapse into each other is a hand-run from inside a linked
worktree: `cd <worktree>; python3 -m edad.gate run T` imports the worktree's
`edad/gate.py` and judges the worktree with it - the subject grading itself,
printing the same `harness checkout` line a main-checkout run would. `evaluate`
refuses that, first, before the base-ref probe (T026) and the toolchain check
(T021): the gate module it is running from lives inside the tree it is judging,
AND that tree's `.git` is a file - which is what makes it a linked worktree and
not the main checkout, where judge and subject are the same repository by
design and every hand-run at approve time depends on that.

Four seams. `evaluate` on a real temporary repository with the judge's location
set by replacing `gate.harness_checkout`, as T019's tests do. The gate CLI
spawned from inside a real linked worktree that carries a committed copy of the
package, with no `PYTHONPATH` - the operator's actual command, and the only way
the self-judging path is reached. `run_commands` on a worktree, reading what a
command's own `import edad` resolves to. And QUICKSTART as text.

Two tests here are green before the change and stay in this file as the
regression net `full_gate` runs: the sabotage test (D1) and the import test
(D3). The three refusal tests and the QUICKSTART test are the acceptance.

The agent's container has no git. Every test here but the QUICKSTART one builds
a real repository and a linked worktree, and one spawns `python3 -m edad.gate`;
they fail there, and the verifier on the host judges them. That is the
environment, not the agent's defect.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from edad import gate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(gate.__file__).resolve().parent

TICKET_ID = "T900"
FROZEN = "tests/test_thing.py"
PINFILE = "requirements-gate.txt"
LOCK = f".edad/hashes/{TICKET_ID}.json"
TICKET = f".edad/tickets/{TICKET_ID}.md"
PINS = {"pytest": "8.4.2", "ruff": "0.15.18"}
HARNESS = {"version": None, "commit": "c" * 40, "dirty": False, "source": "checkout"}
MISMATCH = "does not match requirements-gate.txt"

TICKET_TEXT = f"""---
id: {TICKET_ID}
title: a ticket
decisions: [D1]
scope:
  - {PINFILE}
frozen:
  - {FROZEN}
acceptance:
  - python3 -m pytest {FROZEN}::test_one -q
full_gate:
  - python3 -m pytest -q
kill_conditions:
  network_access: deny
---

## Context
"""

# A gate module that would pass anything. Importing it leaves a marker beside
# itself, so "never consulted" is a file that does not exist, not an inference.
SABOTAGED_GATE = '''
from pathlib import Path

Path(__file__).with_name("CONSULTED").write_text("the worktree copy was imported\\n")


def check_freeze(root, ticket):
    return True, []


def evaluate(root, ticket, gate_name="acceptance", base_ref=None):
    class Passed:
        passed = True
        freeze_ok = True
        violations = []

    return Passed()
'''


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def measured(pins: dict, *, broken: str | None = None) -> list:
    """A satisfied `Measurement` per pin, or one that is not on the path at
    all when `broken` names it - the shape T021's `Night` steers the toolchain
    refusal with."""
    return [
        gate.Measurement(name, ver, None if name == broken else ver, None)
        for name, ver in pins.items()
    ]


class FakeRun:
    """Stands in for `run_commands`: every command a clean pass."""

    def __call__(self, root, commands, timeout_s=None, **kw):
        return [
            gate.CommandResult(c, 0, 0.1, "1 passed", [], False, None) for c in commands
        ]


class Repo:
    """A repository the gate can evaluate - a frozen test, a ticket, the pins,
    a lock written by hand, all committed - plus a linked worktree of it, the
    shape every agent session runs in. With `package=True` a copy of this
    checkout's `edad/` is committed into it first, so the worktree carries its
    own gate the way a self-hosting night's does."""

    def __init__(self, tmp_path: Path, *, package: bool = False) -> None:
        self.root = tmp_path / "repo"
        (self.root / "tests").mkdir(parents=True)
        (self.root / ".edad" / "hashes").mkdir(parents=True)
        (self.root / ".edad" / "tickets").mkdir()
        self.write(FROZEN, "def test_one():\n    assert True\n")
        self.write(TICKET, TICKET_TEXT)
        self.write(PINFILE, "".join(f"{n}=={v}\n" for n, v in PINS.items()))
        if package:
            shutil.copytree(
                PACKAGE, self.root / "edad", ignore=shutil.ignore_patterns("__pycache__")
            )
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "gate@example.invalid")
        _git(self.root, "config", "user.name", "edad tests")
        self.write_lock()
        self.head = self.commit("approved")
        # A linked worktree: `.git` there is a file pointing back at the
        # repository, which is what the guard keys on.
        self.wt = tmp_path / "wt"
        _git(self.root, "worktree", "add", "-q", "--detach", str(self.wt), "HEAD")
        assert (self.wt / ".git").is_file()
        assert (self.root / ".git").is_dir()

    def write(self, rel: str, text: str, *, under: Path | None = None) -> None:
        ((under or self.root) / rel).write_text(text)

    def commit(self, msg: str) -> str:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", msg)
        return _git(self.root, "rev-parse", "HEAD")

    def write_lock(self) -> None:
        lock = {
            FROZEN: gate.sha256(self.root / FROZEN),
            gate.LOCK_META_KEY: {
                "ticket_sha256": gate.sha256(self.root / TICKET),
                "decisions": ["D1"],
                "red_proof": [{"command": "python3 -m pytest", "exit_code": 1}],
                "toolchain": dict(PINS),
            },
        }
        self.write(LOCK, json.dumps(lock, indent=2) + "\n")

    def evaluate(self, root: Path, base_ref: str | None = None) -> gate.Record:
        return gate.evaluate(root, gate.load_ticket(root, TICKET_ID), "acceptance", base_ref)

    def refusal(self, root: Path, base_ref: str | None = None) -> gate.Refusal:
        with pytest.raises(gate.Refusal) as caught:
            self.evaluate(root, base_ref)
        return caught.value


def names(path: Path, text: str) -> bool:
    """Whether `text` names `path`, in either spelling a resolver can give it."""
    return str(path) in text or str(path.resolve()) in text


@pytest.fixture
def quiet(monkeypatch):
    """The parts of `evaluate` that are not under test, held still: identity
    a constant, the toolchain satisfied, every command a clean pass."""
    monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
    monkeypatch.setattr(gate, "run_commands", FakeRun())
    monkeypatch.setattr(gate, "measure_toolchain", lambda root: measured(PINS))


@pytest.fixture
def repo(tmp_path, quiet) -> Repo:
    return Repo(tmp_path)


@pytest.fixture
def hosted(tmp_path) -> Repo:
    """A repository whose worktree carries its own copy of the package."""
    return Repo(tmp_path, package=True)


# --- D2: the refusal ---------------------------------------------------------------


def test_a_gate_judging_its_own_worktree_copy_is_refused_naming_the_tree(repo, monkeypatch):
    """The judge's own checkout is the tree under judgement, and that tree is a
    linked worktree: refuse, through `die()` - exit 2, a reason - and name the
    tree, so the operator can see which run they made. The main checkout
    judging itself is not this case: `.git` there is a directory, and that run
    is approve time and every hand-run so far."""
    judge = repo.wt.resolve()
    monkeypatch.setattr(gate, "harness_checkout", lambda: judge)
    refused = repo.refusal(repo.wt)

    assert refused.code == 2
    assert names(repo.wt, refused.reason), refused.reason

    main = repo.root.resolve()
    monkeypatch.setattr(gate, "harness_checkout", lambda: main)
    rec = repo.evaluate(repo.root)
    assert isinstance(rec, gate.Record), "the main checkout judging itself stays allowed"
    assert rec.freeze_ok, rec.violations


def test_the_cli_run_from_inside_a_worktree_is_refused_with_no_traceback(hosted):
    """The operator's actual command: `cd <worktree>; python3 -m edad.gate run
    T`, no `PYTHONPATH`, no `EDAD_REPO`. The child resolves its root from the
    working directory and imports the worktree's own `edad/` from there - the
    subject judging itself. Exit 2, `edad:` and the worktree on stderr, and no
    traceback on either stream.

    Before the guard, the copied package refuses on something else - the
    fixture pins pytest 8.4.2 and the host has 9.0.3 - and that is exit 2 with
    `edad:` too. The worktree's path in the reason is what tells the two
    apart, so it is what this test asserts."""
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "EDAD_REPO"}}
    proc = subprocess.run(
        [sys.executable, "-m", "edad.gate", "run", TICKET_ID],
        cwd=hosted.wt, env=env, capture_output=True, text=True, check=False,
    )

    assert proc.returncode == 2, (proc.returncode, proc.stderr[-800:])
    assert "edad: " in proc.stderr, proc.stderr[-800:]
    assert names(hosted.wt, proc.stderr), proc.stderr[-800:]
    assert "Traceback" not in proc.stderr + proc.stdout, proc.stderr[-800:]


def test_the_self_judge_refusal_precedes_the_base_ref_probe_and_the_toolchain_check(
    repo, monkeypatch
):
    """With a ref that does not resolve AND a toolchain that does not match,
    the reason still names the worktree and neither of the others: the
    self-judge check needs no git and no measurement, only a path comparison,
    so it runs before both. A verdict from a gate the subject wrote is wrong
    whatever else is also wrong."""
    judge = repo.wt.resolve()
    monkeypatch.setattr(gate, "harness_checkout", lambda: judge)
    monkeypatch.setattr(gate, "measure_toolchain", lambda root: measured(PINS, broken="pytest"))

    refused = repo.refusal(repo.wt, "no-such-ref")

    assert names(repo.wt, refused.reason), refused.reason
    assert "no-such-ref" not in refused.reason, refused.reason
    assert MISMATCH not in refused.reason, refused.reason


# --- D1: the worktree's copy is never the judge (full_gate net) --------------------


def test_a_sabotaged_worktree_copy_of_the_gate_is_never_consulted(hosted, quiet):
    """The worktree's `edad/gate.py` is replaced by one that passes anything
    and leaves a marker when imported; a frozen file in the worktree is edited.
    The real `evaluate` - this process's copy, the judge - still reports the
    hash mismatch, and the marker was never written. Green today because the
    judge is already in-process; here so that a future shell-out from the
    worktree cannot hand the agent its own gavel silently."""
    hosted.write("edad/gate.py", SABOTAGED_GATE, under=hosted.wt)
    hosted.write(FROZEN, "def test_one():\n    assert False\n", under=hosted.wt)

    rec = hosted.evaluate(hosted.wt)

    assert not rec.freeze_ok, rec.violations
    assert any(FROZEN in v for v in rec.violations), rec.violations
    assert not rec.passed
    assert not (hosted.wt / "edad" / "CONSULTED").exists(), "the worktree's gate was imported"


# --- D3: the subject's commands import the subject's copy (full_gate net) ----------


def test_commands_run_in_the_worktree_import_the_worktree_copy(hosted, monkeypatch):
    """A gate command runs with the worktree as its working directory and the
    environment as it is - `run_commands` neither sets nor scrubs `PYTHONPATH`.
    The working directory wins anyway: even with `PYTHONPATH` pointing at this
    checkout, `import edad` inside the command resolves to the worktree's copy.
    That is what makes the worktree the subject."""
    monkeypatch.setenv("PYTHONPATH", str(PROJECT_ROOT))
    (result,) = gate.run_commands(
        hosted.wt, ['python3 -c "import edad; print(edad.__file__)"'], deny_network=True
    )

    assert result.exit_code == 0, result.output_tail
    imported = Path(result.output_tail.strip().splitlines()[-1])
    assert imported.resolve().is_relative_to(hosted.wt.resolve()), imported
    assert not imported.resolve().is_relative_to(PROJECT_ROOT), imported


# --- D6: the operator can read the rule --------------------------------------------


def test_quickstart_says_which_copy_judges_and_why_a_worktree_run_is_refused():
    """The refusal is operator-facing, so the explanation lives where the
    operator reads: a `## Which copy judges` section that names the worktree
    and says a run from inside one is refused."""
    text = (PROJECT_ROOT / "QUICKSTART.md").read_text()
    m = re.search(r"^## Which copy judges[ \t]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, "QUICKSTART.md has no `## Which copy judges` section"
    section = m.group(1)
    assert "worktree" in section, "the worktree is not named"
    assert re.search(r"refus", section), "that a run from inside a worktree is refused is not said"
