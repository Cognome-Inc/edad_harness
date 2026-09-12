"""T019: every artifact the harness writes names the harness that wrote it (D1-D6).

An evidence record says which commit of the *target* it judged and never which
harness did the judging. Since T018 there are three harnesses that can differ - a
tag install, an editable checkout, and this repo gating itself from an uninstalled
tree - and every record they write looks the same. These tests pin the identity
block, the toolchain block, and where each lands.

Deciding is separated from gathering so the decision is testable everywhere: the
core (D1) is pure and fed fabricated inputs, one set per install mode, so it answers
the same on this laptop, in the container and on a teammate's machine. The gatherer
(D2) is exercised through its named seams - the metadata read and the git
shell-outs are module-level names, the pattern `docker_network_internal`
established - so no test here shells to git and none depends on how the machine
running it has the harness installed. The record and lock tests (D4) replace
`harness_identity` and `toolchain_versions` with sentinels and follow the values
through `evaluate`, `write_record` and `cmd_approve`, the way the red-proof tests
drive approve. The log tests (D5) read field order off `asdict(SessionLog)` and
`RunState.as_log()`, the T017 precedent. D6 reads `QUICKSTART.md` as text, as the
packaging tests do.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

from edad import gate
from edad.gate import CommandResult, cmd_approve, evaluate, write_record
from edad.session import SessionLog
from edad.session_queue import Plan, RunState

PROJECT_ROOT = Path(__file__).resolve().parents[1]

HEAD = "a" * 40
TAG_COMMIT = "b" * 40

# What `direct_url.json` says for the two pip install paths QUICKSTART documents.
VCS_DIRECT_URL = {
    "url": "https://github.com/Cognome-Inc/edad_harness",
    "vcs_info": {"vcs": "git", "commit_id": TAG_COMMIT, "requested_revision": "v0.1.0"},
}
EDITABLE_DIRECT_URL = {
    "url": "file:///home/dev/edad_harness",
    "dir_info": {"editable": True},
}

UNKNOWN = {"version": None, "commit": None, "dirty": None, "source": "unknown"}

# Sentinels for the plumbing tests: recognisable, and not what any real machine
# would produce, so a test that sees them knows the value came through the seam.
HARNESS = {"version": "9.9.9", "commit": "f" * 40, "dirty": None, "source": "vcs"}
TOOLCHAIN = {"pytest": "0.0.1", "ruff": "0.0.2", "PyYAML": "0.0.3"}

# A ticket the way the red-proof tests describe one: hypothetical, so the fixtures
# read as the shape a ticket has rather than as self-reference.
FROZEN = "tests/test_thing.py"
NODE = f"{FROZEN}::test_orders_the_queue"
ACC = f"python3 -m pytest {NODE} -q"
TICKET = {
    "id": "T900",
    "frozen": [FROZEN],
    "scope": ["edad/thing.py"],
    "acceptance": [ACC],
    "kill_conditions": {"network_access": "deny"},
}


class FakeRun:
    """Stands in for `run_commands`: keyed by command, defaulting to a clean pass."""

    def __init__(self, table: dict | None = None):
        self.table = table or {}

    def __call__(self, root, commands, deny_network, flag_paths=(), timeout_s=900):
        out = []
        for c in commands:
            exit_code, text, killed = self.table.get(c, (0, "", False))
            out.append(CommandResult(c, exit_code, 0.1, text, [], killed, None))
        return out


def failed(*nodes: str) -> str:
    """What pytest prints when a test ran and its assertion went off. Exit 1."""
    body = "".join(f"FAILED {n} - AssertionError\n" for n in nodes)
    return f"{body}{len(nodes)} failed in 0.4s\n"


def boom(*args, **kwargs):
    raise RuntimeError("this seam is broken on purpose")


# --- D1: the identity, and its pure core ----------------------------------------


def test_a_vcs_install_is_identified_by_its_recorded_commit():
    """`pip install git+...@v0.1.0`: pip's own record names the commit, and there
    is no checkout to be dirty, so `dirty` is null rather than False."""
    assert gate.identify_harness("0.1.0", VCS_DIRECT_URL, None, None) == {
        "version": "0.1.0", "commit": TAG_COMMIT, "dirty": None, "source": "vcs",
    }


def test_an_editable_install_is_identified_by_the_checkout_head_and_dirtiness():
    """`pip install -e`: metadata says 0.1.0 whatever commit is checked out, so
    the commit comes from the checkout and its dirtiness is measured. A verdict
    made under uncommitted changes is visibly unreproducible, not silently so."""
    assert gate.identify_harness("0.1.0", EDITABLE_DIRECT_URL, HEAD, True) == {
        "version": "0.1.0", "commit": HEAD, "dirty": True, "source": "editable",
    }
    assert gate.identify_harness("0.1.0", EDITABLE_DIRECT_URL, HEAD, False)["dirty"] is False


def test_a_bare_checkout_is_identified_by_head_with_no_version():
    """How this repo gates itself. No metadata, a head: the commit is the
    identity and the version is null. A stale `egg-info` left by an earlier
    editable install can still answer `0.1.0` from the cwd, so a version read
    without a `direct_url` to vouch for it is not trusted as a label either."""
    assert gate.identify_harness(None, None, HEAD, False) == {
        "version": None, "commit": HEAD, "dirty": False, "source": "checkout",
    }
    stale = gate.identify_harness("0.1.0", None, HEAD, False)
    assert stale["source"] == "checkout"
    assert stale["version"] is None, "a version with no direct_url is a stale label"
    assert stale["commit"] == HEAD


def test_nothing_known_is_unknown_with_nulls_not_an_error():
    """Identity is something the harness reports about itself, never a
    precondition of running."""
    assert gate.identify_harness(None, None, None, None) == UNKNOWN


# --- D2: the gatherer -------------------------------------------------------------


def test_the_gatherer_never_raises_and_degrades_to_unknown(monkeypatch, tmp_path):
    """The seams are names on the module: the metadata read, the checkout
    locator, and the two git shell-outs. Each is made to fail in turn and the
    gatherer keeps answering. That is what record-only means - identity is never
    a reason a night does not happen."""
    monkeypatch.setattr(gate, "harness_metadata", lambda: ("0.1.0", dict(EDITABLE_DIRECT_URL)))
    monkeypatch.setattr(gate, "harness_checkout", lambda: tmp_path)
    monkeypatch.setattr(gate, "harness_head", lambda checkout: HEAD)
    monkeypatch.setattr(gate, "harness_dirty", lambda checkout: True)
    assert gate.harness_identity() == {
        "version": "0.1.0", "commit": HEAD, "dirty": True, "source": "editable",
    }, "with every seam answering, the gatherer feeds the core"

    monkeypatch.setattr(gate, "harness_metadata", boom)
    assert gate.harness_identity() == {
        "version": None, "commit": HEAD, "dirty": True, "source": "checkout",
    }, "broken metadata degrades to what git can still say"

    monkeypatch.setattr(gate, "harness_head", boom)
    monkeypatch.setattr(gate, "harness_dirty", boom)
    assert gate.harness_identity() == UNKNOWN, "broken git degrades to unknown"

    monkeypatch.setattr(gate, "harness_checkout", boom)
    assert gate.harness_identity() == UNKNOWN, "nothing answering is unknown, not a raise"


# --- D3: the toolchain probe ------------------------------------------------------


def test_toolchain_versions_stores_what_the_pin_check_measures(monkeypatch, tmp_path):
    """One entry per `==` line in requirements-gate.txt, null when the probe found
    nothing, and the same `_probe_versions` call the pin check makes - so the
    record and the check cannot disagree about what was measured."""
    (tmp_path / "requirements-gate.txt").write_text(
        "# the gate's pins\n"
        "pytest==8.4.2\n"
        "ruff==0.15.18   # trailing comment\n"
        "PyYAML==6.0.2\n"
        "loose>=1.0\n"
        "\n"
    )
    seen = {"pytest": ("8.4.2", "8.4.2"), "ruff": (None, None), "PyYAML": ("6.0.2", None)}
    probed: list[str] = []

    def probe(root, name):
        probed.append(name)
        return seen[name]

    monkeypatch.setattr(gate, "_probe_versions", probe)

    assert gate.toolchain_versions(tmp_path) == {
        "pytest": "8.4.2", "ruff": None, "PyYAML": "6.0.2",
    }
    assert probed == ["pytest", "ruff", "PyYAML"], "one probe per pinned name, in file order"

    problems = gate.gate_toolchain_problems(tmp_path)
    assert len(problems) == 1 and problems[0].startswith("ruff: not found"), (
        f"the pin check's behaviour is unchanged by the extraction: {problems}"
    )

    assert gate.toolchain_versions(tmp_path / "nowhere") == {}, "no pins file, nothing measured"


# --- D4: the record and the lock --------------------------------------------------


def test_the_written_record_carries_harness_and_toolchain(monkeypatch, tmp_path):
    """`evaluate` is the single entry point for anything that needs a verdict, so
    the block is populated there and nowhere else; `write_record`'s payload
    carries it through to disk, after `uncomparable_failures`."""
    monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
    monkeypatch.setattr(gate, "toolchain_versions", lambda root: dict(TOOLCHAIN))
    monkeypatch.setattr(gate, "git", lambda root, *args: HEAD)
    monkeypatch.setattr(gate, "approval_meta", lambda root, ticket_id: {})
    monkeypatch.setattr(gate, "check_freeze", lambda root, ticket: (True, []))
    monkeypatch.setattr(gate, "changed_files", lambda root, base_ref: [])
    monkeypatch.setattr(gate, "run_commands", FakeRun())

    rec = evaluate(tmp_path, TICKET)
    assert rec.harness == HARNESS
    assert rec.toolchain == TOOLCHAIN

    payload = json.loads(write_record(tmp_path, rec).read_text())
    assert payload["harness"] == HARNESS
    assert payload["toolchain"] == TOOLCHAIN
    keys = list(payload)
    after = keys.index("uncomparable_failures") + 1
    assert keys[after : after + 2] == ["harness", "toolchain"]


def test_the_lock_records_harness_and_toolchain_at_approval(monkeypatch, tmp_path):
    """The red proof and the baseline are measurements too, made by some harness
    under some toolchain. The lock's `_edad` block says which."""
    (tmp_path / ".edad" / "tickets").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / FROZEN).write_text("# the frozen test\n")
    (tmp_path / ".edad" / "tickets" / "T900.md").write_text(
        "---\n"
        "id: T900\n"
        f"frozen:\n  - {FROZEN}\n"
        "scope:\n  - edad/thing.py\n"
        f"acceptance:\n  - {ACC}\n"
        "---\n\nbody\n"
    )
    monkeypatch.setattr(gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(gate, "gate_toolchain_problems", lambda root: [])
    monkeypatch.setattr(gate, "run_full_gate_probe", lambda root, ticket: [])
    monkeypatch.setattr(gate, "run_commands", FakeRun({ACC: (1, failed(NODE), False)}))
    monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
    monkeypatch.setattr(gate, "toolchain_versions", lambda root: dict(TOOLCHAIN))

    args = argparse.Namespace(ticket="T900", allow_passing=False, rebaseline=False)
    assert cmd_approve(args) == 0

    lock = json.loads((tmp_path / ".edad" / "hashes" / "T900.json").read_text())
    meta = lock["_edad"]
    assert meta["red_proof"], "the red was taken; the block below says who measured it"
    assert meta["harness"] == HARNESS
    assert meta["toolchain"] == TOOLCHAIN


# --- D5: the two logs -------------------------------------------------------------


def test_the_session_log_records_the_harness_beside_permissions():
    """A session log already says how a run was made - sandbox, network,
    permissions. The harness belongs beside those, defaulting to "nothing
    recorded" rather than omitting the field. Toolchain stays out of the logs."""
    def log(**kw) -> dict:
        return asdict(SessionLog(
            ticket="T1", started_at="now", base_commit="0" * 40,
            branch="edad/t1", sandbox="docker", **kw,
        ))

    keys = list(log())
    assert keys[keys.index("permissions") + 1] == "harness"
    assert log()["harness"] == {}
    assert log(harness=dict(HARNESS))["harness"] == HARNESS
    assert "toolchain" not in log()


def test_the_run_log_records_the_harness_beside_network():
    """The run log's top level says which tier the night ran under; which
    harness ran it sits right after, so "which harness ran tonight" is a lookup
    rather than a reconstruction from N session logs."""
    plan = Plan(order=["T1"], done=set(), independent=[{"T1"}])
    tickets = {"T1": {"id": "T1", "blocked_by": []}}

    log = RunState(plan, tickets).as_log()
    keys = list(log)
    assert keys[keys.index("network") + 1] == "harness"
    assert log["harness"] == {}
    assert "toolchain" not in log

    assert RunState(plan, tickets, harness=dict(HARNESS)).as_log()["harness"] == HARNESS


# --- D6: releasing is documented where the operator reads ----------------------------


def test_quickstart_has_a_releasing_section_naming_the_tag_step():
    """A release is an operator act - bump, PR, tag, push - and the tag is the
    thing the pinned install line depends on and the one step nothing else
    forces. The section has to name it."""
    text = (PROJECT_ROOT / "QUICKSTART.md").read_text()
    m = re.search(r"^## Releasing[ \t]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, "QUICKSTART.md has no `## Releasing` section"
    section = m.group(1)
    assert "pyproject.toml" in section, "the bump is not named"
    assert "git tag" in section, "the tag step is not named"
    assert "git push" in section, "pushing the tag is not named"
