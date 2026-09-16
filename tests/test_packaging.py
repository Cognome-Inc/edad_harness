"""T018: the harness is a pip-installable distribution (D1, D2, D3, D5).

Every test here reads a file at the repo root as data - `pyproject.toml` through
`tomllib`, `QUICKSTART.md` as text - and never installs anything. A real install needs
a build backend the host does not have and the gate runs with the network denied, so
the install itself is proven by hand at approval (D4) and this file pins the metadata
that install is made from. The root is located from this file, the way
`test_egress_proxy.py` does, so a gate run reads the worktree's copy and not the main
checkout's.
"""

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The pinned install line QUICKSTART shows a target's team. The tag it names must be
# the project's version, so the doc cannot drift from the pyproject it describes.
PINNED_INSTALL_RE = re.compile(
    r"pip install git\+https://github\.com/Cognome-Inc/edad_harness@v(\d+\.\d+\.\d+)"
)


def pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())


def quickstart() -> str:
    return (PROJECT_ROOT / "QUICKSTART.md").read_text()


# --- D1: the package -------------------------------------------------------------


def test_build_system_is_setuptools():
    build = pyproject().get("build-system", {})
    assert build.get("requires") == ["setuptools>=68"]
    assert build.get("build-backend") == "setuptools.build_meta"


def test_project_metadata_names_the_distribution():
    project = pyproject().get("project", {})
    assert project.get("name") == "edad-harness"
    assert project.get("version") == "0.1.1"
    assert project.get("requires-python") == ">=3.12"
    # D3: no console script. Absence is green at base, so it lives inside this
    # test, which is red at base because [project] does not exist.
    assert "scripts" not in project
    assert "gui-scripts" not in project


def test_packages_is_exactly_edad():
    # Named, not auto-discovered: flat-layout discovery would see tests/ and
    # docker_tests/ beside edad/ and refuse.
    setuptools_table = pyproject().get("tool", {}).get("setuptools", {})
    assert setuptools_table.get("packages") == ["edad"]


# --- D2: the dependency spec -----------------------------------------------------


def test_pyyaml_is_the_only_dependency_and_is_loose():
    deps = pyproject().get("project", {}).get("dependencies")
    assert deps is not None, "[project].dependencies is missing"
    assert len(deps) == 1, deps
    (dep,) = deps
    assert re.fullmatch(r"PyYAML\s*>=\s*6\.0", dep), dep
    # The exact pin is the gate's job, via requirements-gate.txt.
    assert "==" not in dep


# --- D5: QUICKSTART installs by pip -----------------------------------------------


def test_quickstart_installs_by_pip_not_pythonpath():
    text = quickstart()
    assert PINNED_INSTALL_RE.search(text), "no pinned `pip install git+...@vX.Y.Z` line"
    assert "pip install -e " in text, "no editable `pip install -e` line"
    # Whole file, not just the Install section: moving the line under another
    # heading must not pass.
    assert "PYTHONPATH" not in text


def test_quickstart_pinned_tag_matches_project_version():
    match = PINNED_INSTALL_RE.search(quickstart())
    assert match, "no pinned `pip install git+...@vX.Y.Z` line"
    version = pyproject().get("project", {}).get("version")
    assert version is not None, "[project].version is missing"
    assert match.group(1) == version
