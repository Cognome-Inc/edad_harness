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

The toolchain-measurement ticket amends this file before re-freezing it. The
record and lock tests now steer the toolchain by faking `measure_toolchain` with a
list of `Measurement`s - the one module-level name both `evaluate` and
`cmd_approve` read - because after that ticket neither caller touches
`toolchain_versions` or `gate_toolchain_problems`, and a fake of either would be
inert. Its own tests follow: the measurement is taken once per command and the
record's block *is* that measurement; a mismatch refuses before anything runs; the
two readers turn every on-disk shape into one; `report()` and `approve` print
what the readers see; the quickstart names the fields.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

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


def measured(**overrides) -> list:
    """A `Measurement` per sentinel pin, satisfied: importable at the pinned
    version, nothing on PATH. `overrides` swaps one name's (meta, on_path)."""
    return [
        gate.Measurement(name, ver, *overrides.get(name, (ver, None)))
        for name, ver in TOOLCHAIN.items()
    ]


class FakeMeasure:
    """Stands in for `measure_toolchain`, counting calls: one measurement per
    command is the property, and a count is what a cache lifetime is not."""

    def __init__(self, measurements: list):
        self.measurements = measurements
        self.calls = 0

    def __call__(self, root):
        self.calls += 1
        return list(self.measurements)


def write_ticket(tmp_path: Path) -> None:
    """A repo the way the lock test needs one: the ticket, its frozen file, and
    the directories `cmd_approve` writes under."""
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


def approve_fakes(monkeypatch, tmp_path: Path) -> None:
    """Everything `cmd_approve` shells to, faked the way the red-proof tests do:
    the repo is `tmp_path`, the probe finds nothing, the red is a real FAILED."""
    monkeypatch.setattr(gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(gate, "run_full_gate_probe", lambda root, ticket: [])
    monkeypatch.setattr(gate, "run_commands", FakeRun({ACC: (1, failed(NODE), False)}))
    monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))


def evaluate_fakes(monkeypatch) -> None:
    """Everything `evaluate` reaches beyond the toolchain, faked as the record
    test always has."""
    monkeypatch.setattr(gate, "harness_identity", lambda: dict(HARNESS))
    monkeypatch.setattr(gate, "git", lambda root, *args: HEAD)
    monkeypatch.setattr(gate, "approval_meta", lambda root, ticket_id: {})
    monkeypatch.setattr(gate, "check_freeze", lambda root, ticket: (True, []))
    monkeypatch.setattr(gate, "changed_files", lambda root, base_ref: [])
    monkeypatch.setattr(gate, "run_commands", FakeRun())


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
    nothing, and one `_probe_versions` call per pinned name - the wrappers over
    `measure_toolchain` each take one measurement, and the check's messages are
    unchanged by the extraction."""
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
    carries it through to disk, after `uncomparable_failures`. The toolchain is
    steered through `measure_toolchain`, the one name `evaluate` reads."""
    evaluate_fakes(monkeypatch)
    monkeypatch.setattr(gate, "measure_toolchain", FakeMeasure(measured()))

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
    under some toolchain. The lock's `_edad` block says which. The toolchain is
    steered through `measure_toolchain`, the one name `cmd_approve` reads."""
    write_ticket(tmp_path)
    approve_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(gate, "measure_toolchain", FakeMeasure(measured()))

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


# ==== toolchain-measurement: the measurement is a value, and it is read ===========


# --- D1: evaluate measures once, refuses a mismatch, records the measurement -------


def test_evaluate_measures_the_toolchain_once_and_records_it(monkeypatch, tmp_path):
    """One `measure_toolchain` call per verdict, and the record's block is
    `versions_of` that call - not a second probe that happened to agree."""
    evaluate_fakes(monkeypatch)
    measure = FakeMeasure(measured())
    monkeypatch.setattr(gate, "measure_toolchain", measure)

    rec = evaluate(tmp_path, TICKET)

    assert measure.calls == 1, "measured once, for the check and the record together"
    assert gate.toolchain_problems(measure.measurements) == [], "the fixture is satisfied"
    assert rec.toolchain == gate.versions_of(measure.measurements) == TOOLCHAIN


def test_evaluate_refuses_a_toolchain_mismatch_before_running_anything(
    monkeypatch, tmp_path, capsys
):
    """A hand-run gate on the wrong pytest dies the way approve and preflight do,
    with the check's own message, before any command runs and before the Record
    is built - so no record ever says a mismatched toolchain was measured."""
    evaluate_fakes(monkeypatch)
    monkeypatch.setattr(gate, "measure_toolchain", FakeMeasure(measured(pytest=("0.0.9", None))))
    # Identity is gathered when the Record is built; a command run is the gate
    # proper. Neither may happen on a mismatch.
    monkeypatch.setattr(gate, "harness_identity", boom)
    monkeypatch.setattr(gate, "run_commands", boom)

    with pytest.raises(SystemExit) as exc:
        evaluate(tmp_path, TICKET)

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "does not match requirements-gate.txt" in err, "approve's message, verbatim"
    assert "pytest: 0.0.9, pinned 0.0.1" in err, "the check's problem line, unchanged"


# --- D2: the measurement is a value; one measurement per approve ------------------


def test_measure_toolchain_probes_each_pin_once_in_file_order(monkeypatch, tmp_path):
    """One file pass and one `_probe_versions` call per pinned name, carried as
    values the two readers consume; the check's messages are unchanged; `[]`
    when there is no pins file, which is a real answer - a target that pins
    nothing measures nothing - and not an error."""
    (tmp_path / "requirements-gate.txt").write_text(
        "pytest==8.4.2\n"
        "ruff==0.15.18   # trailing comment\n"
        "PyYAML==6.0.2\n"
        "loose>=1.0\n"
    )
    seen = {"pytest": ("8.4.2", "8.4.2"), "ruff": (None, None), "PyYAML": ("6.0.2", None)}
    probed: list[str] = []

    def probe(root, name):
        probed.append(name)
        return seen[name]

    monkeypatch.setattr(gate, "_probe_versions", probe)

    ms = gate.measure_toolchain(tmp_path)
    assert probed == ["pytest", "ruff", "PyYAML"], "one probe per pinned name, in file order"
    assert [(m.name, m.pinned, m.meta, m.on_path) for m in ms] == [
        ("pytest", "8.4.2", "8.4.2", "8.4.2"),
        ("ruff", "0.15.18", None, None),
        ("PyYAML", "6.0.2", "6.0.2", None),
    ]
    assert gate.versions_of(ms) == {"pytest": "8.4.2", "ruff": None, "PyYAML": "6.0.2"}
    problems = gate.toolchain_problems(ms)
    assert len(problems) == 1 and problems[0].startswith("ruff: not found"), problems
    assert gate.measure_toolchain(tmp_path / "nowhere") == [], "no pins file, nothing measured"
    assert probed == ["pytest", "ruff", "PyYAML"], "measuring nothing probes nothing"



def test_approve_measures_the_toolchain_once_for_check_and_lock(monkeypatch, tmp_path):
    """The check that refuses a broken toolchain and the block the lock records are
    two readings of one measurement, not two probes."""
    write_ticket(tmp_path)
    approve_fakes(monkeypatch, tmp_path)
    measure = FakeMeasure(measured())
    monkeypatch.setattr(gate, "measure_toolchain", measure)

    args = argparse.Namespace(ticket="T900", allow_passing=False, rebaseline=False)
    assert cmd_approve(args) == 0

    assert measure.calls == 1, "measured once, for the check and the lock together"
    lock = json.loads((tmp_path / ".edad" / "hashes" / "T900.json").read_text())
    assert lock["_edad"]["toolchain"] == gate.versions_of(measure.measurements) == TOOLCHAIN


# --- D3: the readers -----------------------------------------------------------------


def test_harness_of_reads_absent_empty_partial_and_full_blocks_as_one_shape():
    """Three generations are on disk - no key (T001-T018, every lock), `{}`
    (T019's own evidence), the four-key block - and a lock can carry three of
    the four keys. One reader gives all of them the same shape, keeps what a
    partial block did record, never raises, and never writes."""
    full = dict(HARNESS)
    partial = {"version": None, "commit": HEAD, "source": "bare"}

    assert gate.harness_of({}) == UNKNOWN, "no key"
    assert gate.harness_of({"harness": {}}) == UNKNOWN, "T019.json's `{}` reads as unknown"
    assert gate.harness_of({"harness": None}) == UNKNOWN
    assert gate.harness_of({"harness": "vcs"}) == UNKNOWN, "a non-dict is not a block"
    assert gate.harness_of({"harness": full}) == full
    assert gate.harness_of({"harness": partial}) == {
        "version": None, "commit": HEAD, "dirty": None, "source": "bare",
    }, "a partial block keeps the commit it recorded"
    assert gate.harness_of({"harness": {"commit": HEAD, "dirty": False}}) == {
        "version": None, "commit": HEAD, "dirty": False, "source": "unknown",
    }, "no source says how to read the commit, not that there was none"
    assert list(gate.harness_of({"harness": {**full, "host": "x"}})) == [
        "version", "commit", "dirty", "source",
    ], "exactly the four keys, in the record's order"

    assert gate.toolchain_of({}) == {}
    assert gate.toolchain_of({"toolchain": {}}) == {}
    assert gate.toolchain_of({"toolchain": None}) == {}
    assert gate.toolchain_of({"toolchain": dict(TOOLCHAIN)}) == TOOLCHAIN

    artifact = {"harness": {}, "toolchain": {}}
    gate.harness_of(artifact)
    gate.toolchain_of(artifact)
    assert artifact == {"harness": {}, "toolchain": {}}, "normalising on read is not backfilling"


# --- D5, D6: what is printed ---------------------------------------------------------


def report_line(out: str, label: str) -> str:
    lines = [ln.strip() for ln in out.splitlines() if ln.strip().startswith(label)]
    assert len(lines) == 1, f"expected one `{label}` line, got {lines!r} in:\n{out}"
    return lines[0]


def test_report_prints_the_harness_and_toolchain_lines(monkeypatch, tmp_path, capsys):
    """After `decisions`: who measured, and with what - through the readers, so a
    record from before the blocks existed prints `unknown` rather than crashing."""
    evaluate_fakes(monkeypatch)
    monkeypatch.setattr(gate, "measure_toolchain", FakeMeasure(measured()))
    rec = evaluate(tmp_path, TICKET)

    gate.report(rec)
    out = capsys.readouterr().out
    harness = report_line(out, "harness")
    assert "vcs" in harness and HARNESS["commit"][:8] in harness and "v9.9.9" in harness
    assert "dirty" not in harness, "a tag install has no checkout to be dirty"
    toolchain = report_line(out, "toolchain")
    assert "pytest 0.0.1" in toolchain and "ruff 0.0.2" in toolchain and "PyYAML 0.0.3" in toolchain

    rec.harness = {"version": None, "commit": HEAD, "dirty": True, "source": "editable"}
    gate.report(rec)
    harness = report_line(capsys.readouterr().out, "harness")
    assert "editable" in harness and HEAD[:8] in harness and "dirty" in harness
    assert "v" + "None" not in harness and " v" not in harness, "no version, no version label"

    rec.harness, rec.toolchain = {}, {}
    gate.report(rec)
    out = capsys.readouterr().out
    assert "unknown" in report_line(out, "harness")
    assert "unknown" in report_line(out, "toolchain")


def test_approve_prints_the_harness_line(monkeypatch, tmp_path, capsys):
    """The operator taking a red proof sees who measured it, on the same line
    `report()` prints, after the frozen-file hashes."""
    write_ticket(tmp_path)
    approve_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(gate, "measure_toolchain", FakeMeasure(measured()))

    args = argparse.Namespace(ticket="T900", allow_passing=False, rebaseline=False)
    assert cmd_approve(args) == 0

    out = capsys.readouterr().out
    harness = report_line(out, "harness")
    assert "vcs" in harness and HARNESS["commit"][:8] in harness and "v9.9.9" in harness
    assert out.index(FROZEN) < out.index(harness), "after the hashes, not before"


# --- D7: the quickstart names the fields ---------------------------------------------


def test_quickstart_evidence_section_names_harness_and_toolchain():
    """`## Releasing` already leans on `harness.commit`; the section that
    describes the record is where a reader learns the field exists."""
    text = (PROJECT_ROOT / "QUICKSTART.md").read_text()
    m = re.search(r"^## Evidence[ \t]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, "QUICKSTART.md has no `## Evidence` section"
    section = m.group(1)
    assert "harness" in section, "the harness field is not named"
    assert "toolchain" in section, "the toolchain field is not named"
