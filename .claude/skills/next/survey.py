"""Where every EDAD effort in this target stands. Mechanical; prints, decides nothing.

Reads the working tree and git. It sees the checkout, not every branch: a lock or
evidence that lives only on another branch is invisible here, and the report says
which branch was surveyed so the reader knows what it could not see.

This file sits inside the tree that `ruff check .` walks in every full_gate, so it
must stay clean under the target's own rule set.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

RUN = "python3 -m edad.session run {tid} [--sandbox docker]"


def git(*args: str) -> str | None:
    r = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def is_ancestor(sha: str | None, ref: str) -> bool:
    if not sha:
        return False
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, ref], capture_output=True, check=False
    )
    return r.returncode == 0


def frontmatter(path: Path) -> tuple[dict, str]:
    parts = path.read_text().split("---", 2)
    if len(parts) < 3:
        return {}, parts[-1]
    return (yaml.safe_load(parts[1]) or {}), parts[2]


def latest(dirpath: Path, ticket: str) -> dict | None:
    files = sorted(dirpath.glob(f"{ticket}-*.json")) if dirpath.exists() else []
    return json.loads(files[-1].read_text()) if files else None


def section(body: str, title: str) -> list[str]:
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    if not m:
        return []
    lines = (ln.strip() for ln in m.group(1).splitlines())
    return [ln for ln in lines if ln and not ln.startswith("<!--")]


def md_files(d: Path) -> list[Path]:
    return sorted(d.glob("*.md")) if d.exists() else []


class Survey:
    def __init__(self, root: Path, mainline: str) -> None:
        self.root = root
        self.edad = root / ".edad"
        self.mainline = mainline
        self.grills = {p.stem: p for p in md_files(self.edad / "grills")}
        self.specs: dict[str, dict] = {}
        self.spec_of_grill: dict[str, str] = {}
        for p in md_files(self.edad / "specs"):
            fm, _ = frontmatter(p)
            self.specs[p.stem] = fm
            g = fm.get("grilled") or []
            for gpath in g if isinstance(g, list) else [g]:
                self.spec_of_grill[Path(str(gpath)).stem] = p.stem
            self.spec_of_grill.setdefault(p.stem, p.stem)
        self.tickets: dict[str, tuple[dict, Path]] = {}
        self.by_spec: dict[str, list[str]] = {}
        for p in md_files(self.edad / "tickets"):
            fm, _ = frontmatter(p)
            if fm.get("id"):
                self.tickets[fm["id"]] = (fm, p)
                self.by_spec.setdefault(Path(str(fm.get("spec", ""))).stem, []).append(fm["id"])

    # ---- maps ------------------------------------------------------------------

    def maps(self) -> None:
        maps_dir = self.edad / "maps"
        for m in sorted(maps_dir.glob("*/MAP.md")) if maps_dir.exists() else []:
            self.one_map(m)

    def one_map(self, m: Path) -> None:
        fm, body = frontmatter(m)
        slug = fm.get("slug", m.parent.name)
        wps = {frontmatter(p)[0]["id"]: frontmatter(p)[0] for p in sorted(m.parent.glob("W*.md"))}
        open_ = [w for w in wps.values() if w["status"] == "open"]
        frontier = [
            w
            for w in open_
            if not w.get("claimed_by")
            and all(wps.get(b, {}).get("status") == "closed" for b in w.get("blocked_by") or [])
        ]
        claimed = [w for w in open_ if w.get("claimed_by")]
        fog = section(body, "Not yet specified")
        handed = section(body, "Handed off")
        print(
            f"\nmap {slug}: {len(wps)} waypoints, {len(open_)} open, "
            f"{len(frontier)} on the frontier, {len(claimed)} claimed"
        )
        for w in frontier:
            print(f"    frontier  {w['id']}  {w['type']:<9} {w['title']}")
        for w in claimed:
            print(f"    claimed   {w['id']}  by {w['claimed_by']}  {w['title']}")
        if fog:
            print(f"    fog       {len(fog)} line(s) not yet specified")
        for ln in handed:
            print(f"    handed    {ln.strip('- ')}")
        if not open_ and not fog:
            print("    next      map complete — all chunks under Handed off, else /wayfinder")
        elif frontier:
            print(f"    next      /wayfinder {slug}")
        elif claimed:
            print("    next      frontier empty, claimed work in flight — wait, or /wayfinder")
        else:
            print("    next      frontier empty and fog remains — /wayfinder to graduate fog")

    # ---- tickets ---------------------------------------------------------------

    def ticket_state(self, tid: str) -> tuple[str, str | None]:
        fm, path = self.tickets[tid]
        ev_p = self.edad / "evidence" / f"{tid}.json"
        if ev_p.exists():
            ev = json.loads(ev_p.read_text())
            if is_ancestor(ev.get("commit"), self.mainline):
                return "merged", None
            return "evidence, not on mainline", f"/review-branch {tid}, then PR and merge"
        for raw in fm.get("blocked_by") or []:
            b = str(raw).split()[0]
            if b in self.tickets:
                bs, _ = self.ticket_state(b)
                if bs != "merged":
                    return f"blocked by {b} ({bs})", f"finish {b} first"
        lock_p = self.edad / "hashes" / f"{tid}.json"
        if not lock_p.exists():
            return "ticket, no lock", f"read it, then: python3 -m edad.gate approve {tid}"
        meta = json.loads(lock_p.read_text()).get("_edad", {})
        if meta.get("ticket_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            return "lock stale — ticket edited since lock", f"python3 -m edad.gate approve {tid}"
        return self.session_state(tid)

    def session_state(self, tid: str) -> tuple[str, str | None]:
        s = latest(self.edad / "sessions", tid)
        if s:
            oc = s.get("outcome")
            if oc in ("passed", "passed_modulo_baseline"):
                return f"session {oc}, evidence not in this checkout", "look on the run branch"
            if oc in ("aborted", "unwinnable"):
                why = s.get("abort_reason") or ""
                fix = "fix the contract (ticket or frozen tests), re-approve, re-run"
                return f"session {oc} {why}".strip(), fix
            return f"session {oc}", "a session is running or crashed; check .edad/sessions/"
        if latest(self.edad / "records", tid):
            return "gate record, no session", RUN.format(tid=tid)
        return "locked, never run", RUN.format(tid=tid) + "  (or queue it)"

    def efforts(self) -> None:
        shown: set[str] = set()
        for slug in self.grills:
            sslug = self.spec_of_grill.get(slug)
            spec = self.specs.get(sslug) if sslug else None
            print(f"\ngrill {slug}")
            if not spec or not sslug:
                print("    spec      none\n    next      /to-spec on the grill record")
                continue
            if sslug in shown:
                print(f"    spec      {sslug} (shared; listed above)")
                continue
            shown.add(sslug)
            tids = self.by_spec.get(sslug, [])
            print(f"    spec      {sslug}, status {spec.get('status', '?')}, {len(tids)} ticket(s)")
            if not tids:
                print("    next      /to-tickets on the spec")
            for tid in tids:
                st, nxt = self.ticket_state(tid)
                title = self.tickets[tid][0].get("title", "")
                print(f"    {tid}  {st:<44} {title[:50]}")
                if nxt:
                    print(f"          next  {nxt}")
        orphans = [
            t
            for t, (fm, _) in self.tickets.items()
            if Path(str(fm.get("spec", ""))).stem not in self.specs
        ]
        if orphans:
            print("\ntickets with no spec behind them:", ", ".join(orphans))

    # ---- leftovers -------------------------------------------------------------

    def leftovers(self) -> None:
        notes = md_files(self.root / "docs" / "research")
        if notes:
            print(f"\nresearch notes: {len(notes)} under docs/research/ (latest {notes[-1].name})")
        spikes = git("branch", "--list", "spike/*")
        if spikes:
            print("spike branches:", " ".join(s.strip("* ") for s in spikes.splitlines()))
        runs_dir = self.edad / "runs"
        runs = sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []
        if runs:
            r = json.loads(runs[-1].read_text())
            tickets = (r.get("tickets") or {}).items()
            states = ", ".join(f"{t} {v.get('status')}" for t, v in tickets)
            print(f"last queue run: {runs[-1].stem} on {r.get('run_branch')} — {states}")
        tag = git("describe", "--tags", "--abbrev=0", self.mainline)
        if tag:
            ahead = git("rev-list", "--count", f"{tag}..{self.mainline}")
            print(f"release: last tag {tag}, {ahead} commit(s) on {self.mainline} since")


def main() -> int:
    top = git("rev-parse", "--show-toplevel")
    if not top:
        print("not a git repository")
        return 2
    root = Path(top)
    mainline = "main" if git("rev-parse", "--verify", "main") else "master"
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    head = git("rev-parse", "--short", "HEAD")
    print(f"target:   {root.name}   surveyed on {branch} @ {head}   mainline {mainline}")
    if not (root / ".edad").exists():
        print("state:    no .edad/ — not an EDAD target yet")
        print("next:     install per QUICKSTART, then validate the rig")
        return 0
    if not (root / "requirements-gate.txt").exists():
        print("state:    .edad/ present, no requirements-gate.txt")
        print("next:     copy the harness's pins file (QUICKSTART, Install)")
    s = Survey(root, mainline)
    s.maps()
    s.efforts()
    s.leftovers()
    return 0


if __name__ == "__main__":
    sys.exit(main())
