"""
FROZEN ACCEPTANCE TEST — ticket T024.

Authored at the approve step, before implementation exists. The build agent may
read and run this file. It may NOT modify it. The gate runner verifies the file
hash before every run; a mismatch is a hard fail and aborts the session.

Run: python3 -m pytest tests/test_session_image.py -q

Nothing here talks to docker, for the reason `tests/test_session_network.py`
gives: what needs proving is the measuring and the refusing, and a test that
needed a daemon would be skipped on the machines where a wrong answer is
cheapest to ship. `probe_container` is replaced on the `session` module, as the
four network shell-outs are there; the image probe is one more call through it.

The guard has one job: the image the agent will run in must carry exactly the
versions `requirements-gate.txt` pins, or the run does not start. The host was
checked against the same pins a moment earlier; this is the other half. It
answers from inside the session's own preflight and from the queue's plan-time
tier preparation, runs on --dry-run, and stays silent on the default tier.

What the probe prints is part of the contract, because the fake below has to
say what an image would: one `<name>==<version>` line per pinned name, the
pins file's own shape. Which names it asks for is observed as substrings of
the script it hands the container.
"""

import re
from pathlib import Path

import pytest

from edad import session
from edad import session_queue as sq
from edad.session import REBUILD_IMAGE_CMD, Abort, preflight, validate_image

IMAGE = "edad-agent:latest"
NAME = "edad-fixtures"
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
TOKEN = "sk-ant-oat01-not-a-real-token"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The pins after the bump this guard exists for. The host is never consulted
# here, so the numbers are free; what matters is that the image below can
# disagree with them one name at a time.
PINS = {"pytest": "9.0.3", "ruff": "0.15.18", "PyYAML": "6.0.2"}
STALE = {"pytest": "8.4.2", "ruff": "0.15.18", "PyYAML": "6.0.1"}
TICKET = {"id": "T999", "title": "a ticket", "blocked_by": []}


def write_pins(root: Path, pins: dict[str, str] | None) -> None:
    """The checkout's requirements-gate.txt, with a comment line and a
    non-pin line so a parser that trips on either is caught here rather
    than by the first real file."""
    if pins is None:
        return
    body = "# the gate's pins, exact\n" + "".join(f"{n}=={v}\n" for n, v in pins.items())
    (root / "requirements-gate.txt").write_text(body + "-e .\n")


class Probes:
    """Every shell-out `preflight` makes on the docker tier, replaced at the
    module and recorded in one list so that order across them is observable.
    The network answers describe a network that passes; `image` is what the
    container reports for each name it is asked about."""

    def __init__(self, monkeypatch, *, image: dict[str, str] | None = None,
                 answer: tuple[int, str] | None | str = "from-image"):
        self.calls: list[tuple] = []
        self.scripts: list[str] = []

        def internal(name):
            self.calls.append(("internal", name))
            return "true"

        def egress(network, img):
            self.calls.append(("egress", network, img))
            return False

        def refuses(network, img):
            self.calls.append(("refuses", network, img))
            return True

        def permits(network, img):
            self.calls.append(("permits", network, img))
            return 0, "ok"

        def container(network, img, script, timeout=60):
            self.calls.append(("image", network, img))
            self.scripts.append(script)
            if answer != "from-image":
                return answer
            versions = image or {}
            return 0, "\n".join(f"{n}=={versions[n]}" for n in PINS if n in versions)

        monkeypatch.setattr(session, "docker_network_internal", internal)
        monkeypatch.setattr(session, "docker_network_egress", egress)
        monkeypatch.setattr(session, "proxy_refuses", refuses)
        monkeypatch.setattr(session, "proxy_permits", permits)
        monkeypatch.setattr(session, "probe_container", container)
        monkeypatch.setenv(TOKEN_VAR, TOKEN)

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def image_probes(self) -> list[tuple]:
        return [c for c in self.calls if c[0] == "image"]


@pytest.fixture
def root(tmp_path: Path, monkeypatch) -> Path:
    """A checkout where everything preflight checks that is not the image
    passes: no API key, a satisfied host toolchain, an approval lock, a clean
    tree, no drift, the CLI on PATH and logged in. The pins file is the one
    input the tests vary, so it is written per test."""
    (tmp_path / ".edad" / "hashes").mkdir(parents=True)
    (tmp_path / ".edad" / "hashes" / "T999.json").write_text("{}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(session, "gate_toolchain_problems", lambda root: [])
    monkeypatch.setattr(session, "check_freeze", lambda root, ticket: (True, []))
    monkeypatch.setattr(session, "trusted_input_problems", lambda root, tid, ref: [])
    monkeypatch.setattr(session, "changed_files", lambda root, base: [])
    monkeypatch.setattr(session.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(session, "agent_has_credential", lambda: True)
    return tmp_path


# --- D2: refused at preflight, refused at plan time, silent off the tier -------


def test_a_stale_image_is_refused_at_preflight_naming_each_tool_and_the_rebuild_command(
    monkeypatch, root
):
    """Two of three pins disagree. Both are named, found then pinned, the one
    that matches is not, and the message ends in the thing to do about it."""
    write_pins(root, PINS)
    Probes(monkeypatch, image=STALE)

    with pytest.raises(Abort) as excinfo:
        preflight(root, TICKET, "docker", False, NAME, IMAGE)

    message = str(excinfo.value)
    assert f"image {IMAGE} does not match requirements-gate.txt" in message
    assert "pytest 8.4.2, pinned 9.0.3" in message
    assert "PyYAML 6.0.1, pinned 6.0.2" in message
    assert "ruff" not in message, "a matching pin is not a mismatch"
    assert REBUILD_IMAGE_CMD in message


def test_the_queue_refuses_a_stale_image_at_plan_time(monkeypatch, tmp_path):
    """`prepare_tier` is where the queue validates the tier once, with root
    still on main and no session spawned. The image check lands there too, so
    a stale image costs seconds at ticket zero rather than a night. The queue
    has no --image flag, so it asks about the default image; the refusal is the
    queue's `Refusal`, as every `validate_network` refusal already is; and the
    proxy this run created on the way in is removed on the way out."""
    write_pins(tmp_path, PINS)
    calls: list[tuple] = []

    def ensure(network):
        calls.append(("ensure", network))
        return True

    def validate(sandbox, network, *args, **kwargs):
        calls.append(("validate", network))
        return []

    def remove(network):
        calls.append(("remove", network))

    monkeypatch.setattr(sq, "ensure_egress_proxy", ensure)
    monkeypatch.setattr(sq, "validate_network", validate)
    monkeypatch.setattr(sq, "remove_egress_proxy", remove)
    probes = Probes(monkeypatch, image=STALE)

    with pytest.raises(sq.Refusal) as excinfo:
        sq.prepare_tier("docker", NAME, tmp_path)

    assert "pytest 8.4.2, pinned 9.0.3" in str(excinfo.value)
    assert probes.image_probes() == [("image", NAME, session.DEFAULT_IMAGE)]
    assert [c[0] for c in calls] == ["ensure", "validate", "remove"], calls

    # And a `none` night still asks docker nothing at all.
    matching = Probes(monkeypatch, image=PINS)
    assert sq.prepare_tier("none", None, tmp_path) is False
    assert matching.calls == []


def test_a_matching_image_is_accepted_after_validate_network_and_asks_once(monkeypatch, root):
    """Accepted means the image was asked, once, after every network probe:
    the network checks are cheaper and their refusals plainer, and T016 pins
    their order, so the image probe is appended rather than interleaved."""
    write_pins(root, PINS)
    probes = Probes(monkeypatch, image=PINS)

    skipped = preflight(root, TICKET, "docker", False, NAME, IMAGE)

    assert skipped == []
    assert probes.names() == ["internal", "egress", "refuses", "permits", "image"]
    assert probes.image_probes() == [("image", NAME, IMAGE)]


def test_an_unsandboxed_run_never_probes_the_image(monkeypatch, root):
    """The default tier asserts nothing about an image, so it asks nothing:
    probing anyway would let a missing image or a stopped daemon refuse a run
    that never needed docker. Pins present, and still no call."""
    write_pins(root, PINS)
    probes = Probes(monkeypatch, image=STALE)

    assert preflight(root, TICKET, "none", True) == []
    assert preflight(root, TICKET, "none", False) == []

    assert probes.calls == []


# --- D4: one probe, every pinned name, exact match, unmeasured is refused -------


def test_the_image_probe_asks_once_for_every_pinned_name(monkeypatch, tmp_path):
    """One container start, a script that names every pin in the checkout's
    file, on the network the operator named. And with nothing pinned - no file,
    or a file with no `==` line - no container at all: the host check compares
    nothing in that case, and so does this one. That clause is what keeps the
    frozen queue suite, whose fixture repo has no pins file, off a real docker
    wherever docker is absent - the agent's own container included."""
    write_pins(tmp_path, PINS)
    probes = Probes(monkeypatch, image=PINS)

    validate_image(IMAGE, tmp_path, NAME)

    assert probes.image_probes() == [("image", NAME, IMAGE)]
    (script,) = probes.scripts
    for name in PINS:
        assert name in script, f"the probe never asks about {name}"

    unpinned = tmp_path / "unpinned"
    unpinned.mkdir()
    quiet = Probes(monkeypatch, image=PINS)
    validate_image(IMAGE, unpinned, NAME)
    (unpinned / "requirements-gate.txt").write_text("# nothing pinned\n-e .\n")
    validate_image(IMAGE, unpinned, NAME)
    assert quiet.calls == []


def test_an_image_probe_that_could_not_run_is_refused(monkeypatch, tmp_path):
    """Not measured is not promised. A container that could not be run at all
    (None) and a script that did not finish cleanly (non-zero) are both
    refusals that name the image; neither is a mismatch, so no pin is blamed."""
    write_pins(tmp_path, PINS)

    Probes(monkeypatch, answer=None)
    with pytest.raises(Abort) as excinfo:
        validate_image(IMAGE, tmp_path, NAME)
    assert IMAGE in str(excinfo.value)
    assert "pinned" not in str(excinfo.value)

    Probes(monkeypatch, answer=(1, "Traceback"))
    with pytest.raises(Abort) as excinfo:
        validate_image(IMAGE, tmp_path, NAME)
    assert IMAGE in str(excinfo.value)
    assert "pinned" not in str(excinfo.value)


# --- D5: the procedure and the refusal quote one rebuild command ---------------


def test_quickstart_quotes_the_rebuild_command_the_refusal_names(monkeypatch, tmp_path):
    """One constant, quoted by the refusal and by the procedure, so the doc and
    the message cannot drift apart. The section also has to give the order the
    guard forces: install the pins on the host, dry-run and expect the image
    refusal, rebuild, dry-run again. Read as text, as T018 reads the pinned
    install line."""
    assert REBUILD_IMAGE_CMD.startswith("docker build"), REBUILD_IMAGE_CMD
    assert "Dockerfile.agent" in REBUILD_IMAGE_CMD
    assert IMAGE in REBUILD_IMAGE_CMD

    write_pins(tmp_path, PINS)
    Probes(monkeypatch, image=STALE)
    with pytest.raises(Abort) as excinfo:
        validate_image(IMAGE, tmp_path, NAME)
    assert REBUILD_IMAGE_CMD in str(excinfo.value)

    text = (PROJECT_ROOT / "QUICKSTART.md").read_text()
    m = re.search(r"^## Bumping a gate pin\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, "QUICKSTART.md has no `## Bumping a gate pin` section"
    section = m.group(1)
    assert REBUILD_IMAGE_CMD in section

    install = section.index("pip install -r requirements-gate.txt")
    rebuild = section.index(REBUILD_IMAGE_CMD)
    first_dry = section.index("--dry-run")
    last_dry = section.rindex("--dry-run")
    assert install < first_dry < rebuild < last_dry, (
        "the order is: install the pins, dry-run expecting the refusal, rebuild, dry-run clean"
    )


# --- D9: the probe runs on --dry-run ------------------------------------------


def test_the_image_probe_runs_on_dry_run(monkeypatch, root):
    """The network validation stops after the isolation check on a dry-run
    because the proxy probes spend a model turn. The image probe is one
    container start and no model turn, and the bump procedure depends on a
    dry-run surfacing this refusal - so it runs, after the checks the dry-run
    still makes, and refuses a stale image the same way."""
    write_pins(root, PINS)
    probes = Probes(monkeypatch, image=STALE)

    with pytest.raises(Abort) as excinfo:
        preflight(root, TICKET, "docker", True, NAME, IMAGE)

    assert "pytest 8.4.2, pinned 9.0.3" in str(excinfo.value)
    assert probes.names() == ["internal", "egress", "image"]

    # A matching image on a dry-run is accepted, and the skipped checks are
    # still reported as skipped: the image probe was not one of them.
    fine = Probes(monkeypatch, image=PINS)
    skipped = preflight(root, TICKET, "docker", True, NAME, IMAGE)
    assert fine.names() == ["internal", "egress", "image"]
    assert skipped == list(session.DRY_RUN_SKIPS)
