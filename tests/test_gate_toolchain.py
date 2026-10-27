"""T028: bandit and mutmut are gate pins, measured like ruff (review-loops D8, D24).

The review panel runs bandit over a ticket's change and mutmut over its frozen
tests. Both verdicts must be properties of the commit, the same rule pytest and
ruff already follow: pinned exactly in `requirements-gate.txt`, measured by the
one `measure_toolchain` pass, named in every record's `toolchain` block, and
refused by approve when the host does not carry them.

Both are command-line tools the panel shells out to, so each gets a
`VERSION_PROBES` entry the way ruff has one: a pip-installed copy satisfying the
pin while an older one sits first on PATH is the drift the probe exists to
catch, and without an entry the check cannot see PATH at all.

The tests read the real pins file and fake only `_probe_versions`, so they pin
the file's contents and the measurement's reading of them together, and no test
here depends on what the machine running it has installed. The session's refusal
to start the panel when either pin is missing (the other half of D24) is the
panel-wiring ticket's, in `tests/test_session_panel.py`.

Toolchain tests from before this ticket live in `tests/test_harness_identity.py`;
this file sits beside them rather than inside a file an earlier ticket froze.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from edad import gate

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def measure_with(monkeypatch, seen: dict) -> list:
    """Measure the real pins file with `_probe_versions` answering from `seen`;
    a name `seen` does not mention is found at its own pin, importable and on
    PATH alike, so only the tool under test can produce a problem."""
    pins = dict(gate._pinned_versions(PROJECT_ROOT))

    def probe(root, name):
        return seen.get(name, (pins[name], pins[name]))

    monkeypatch.setattr(gate, "_probe_versions", probe)
    return gate.measure_toolchain(PROJECT_ROOT)


def assert_measured_like_ruff(monkeypatch, name: str, pinned: str) -> None:
    """The four things "pinned and measured like ruff" means for one tool."""
    assert (name, pinned) in gate._pinned_versions(PROJECT_ROOT), (
        f"requirements-gate.txt pins {name}=={pinned}"
    )

    probe = gate.VERSION_PROBES.get(name)
    assert probe is not None, f"{name} is a CLI the panel runs, so its PATH copy is probed"
    assert name in probe and "--version" in probe, probe

    ms = measure_with(monkeypatch, {})
    assert gate.versions_of(ms)[name] == pinned, "the record's toolchain block names it"
    assert gate.toolchain_problems(ms) == [], "found at its pin, nothing to report"

    missing = gate.toolchain_problems(measure_with(monkeypatch, {name: (None, None)}))
    assert missing == [f"{name}: not found on the gate's python3 or PATH (pinned {pinned})"], (
        "approve's refusal names it, and says PATH was looked at"
    )

    split = gate.toolchain_problems(measure_with(monkeypatch, {name: (pinned, "0.0.1")}))
    assert len(split) == 1 and split[0].startswith(f"{name}: {pinned} importable but 0.0.1"), (
        f"a stale {name} first on PATH is caught, as it is for ruff: {split}"
    )


# --- D8 / D24: bandit -----------------------------------------------------------------


def test_bandit_is_pinned_and_measured_with_the_toolchain(monkeypatch):
    """D8, with D24's version: bandit==1.9.4, probed on PATH like ruff."""
    assert_measured_like_ruff(monkeypatch, "bandit", "1.9.4")


# --- D24: mutmut ----------------------------------------------------------------------


FAKE_MUTMUT = """\
#!{python}
# Behaves as mutmut 3.8.0 does: its configuration loads at import, even for
# --version, and dies unless it can guess a source directory from the cwd.
import os, sys
if not (os.path.isdir("src") or os.path.isdir("lib")):
    sys.exit("FileNotFoundError: Could not figure out where the code to mutate is.")
print("mutmut, version 3.8.0")
"""


def test_mutmut_is_pinned_and_measured_with_the_toolchain(monkeypatch, tmp_path):
    """D24: mutmut==3.8.0, probed on PATH like ruff, so a mutation score names
    the toolchain that measured it.

    mutmut 3.8.0 reads its configuration on import, so a bare `mutmut
    --version` run in a repo it cannot guess a source directory for - this
    one: no `src/`, no `lib/`, no directory named after the checkout - exits
    1 with a traceback. The probe would then see nothing on PATH and fall back
    to metadata alone, and a stale PATH copy would go unseen. The probe must
    answer from a checkout like that, measured here against a stand-in binary
    that fails exactly the way the real one does."""
    assert_measured_like_ruff(monkeypatch, "mutmut", "3.8.0")

    monkeypatch.undo()  # the real _probe_versions, not measure_with's fake
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "mutmut"
    fake.write_text(FAKE_MUTMUT.format(python=sys.executable))
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    checkout = tmp_path / "edad_harness"
    (checkout / "edad").mkdir(parents=True)

    _, on_path = gate._probe_versions(checkout, "mutmut")
    assert on_path == "3.8.0", (
        "the PATH probe answers from a checkout mutmut cannot guess a source "
        "directory for"
    )
