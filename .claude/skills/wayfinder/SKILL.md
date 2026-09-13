---
name: wayfinder
description: "Plan a chunk of work too big for one session as a committed map of waypoints — decision questions, not build slices — under .edad/maps/, and resolve them one per session until what remains can go straight into /grill-me, /to-spec and /to-tickets. Use when an idea is too large or too foggy to grill in one sitting, or to work the next waypoint of an existing map."
argument-hint: "A loose idea to chart, or a map slug (and optionally a waypoint) to work"
disable-model-invocation: true
---

# Wayfinder (EDAD)

A loose idea has arrived, too big for one session and wrapped in fog: the way from
here to the **destination** isn't visible yet. Wayfinding finds that way; it does not
charge at the destination. This skill charts the way as a committed **map** under
`.edad/maps/`, then works its **waypoints** — questions whose resolution is a
decision, not slices of a build — one per session, until the way is clear.

## Where this sits in the pipeline

`/grill-me` interviews until every decision is pinned to a command that would fail if
it were wrong; `/to-spec` and `/to-tickets` turn that into build tickets the gate can
run. All three assume the design fits in one head. Wayfinder is the layer above: it
exists for the effort that would need six grills, and it ends by handing each one
over.

Vocabulary, because the words are already taken downstream:

- A **ticket** is `.edad/tickets/T0NN.md`: a build unit with frozen tests and a lock.
  Wayfinder never creates one.
- A **waypoint** is a question on the map. Resolving it is a *planning* decision. It
  is not a `Dn`: a decision earns a `Dn` only when a grill pins it to a failing
  command. The grill cites the waypoint in its Record; the map never gains a `Dn`.
- The **destination** is what the map is finding its way to: one spec, a sequence of
  specs, or a single decision to lock before planning starts. Never a change made in
  place — the pipeline makes changes; a map decides what to build.

## Plan, don't do

Each waypoint resolves a decision. The map is done when nothing is left to decide
before someone runs `/grill-me` on a chunk. The pull to just do the work is the
signal you've reached the edge of the map: stop, and hand off to the pipeline. An
effort can override this in its **Notes** (a `task` waypoint that provisions
something, say), but absent that, produce decisions, not deliverables.

## Refer by name

Every map and waypoint has a **title**. In everything the human reads — narration,
the map's Decisions-so-far — use the title, never a bare `W03`. The id rides inside
the link, not in place of the name.

## The map

`.edad/maps/<slug>/MAP.md` is the canonical artifact; its waypoints are sibling files
`.edad/maps/<slug>/W01.md`, `W02.md`, …, committed beside it. Same home as the grills
and specs the map feeds; same YAML-frontmatter shape as everything else the method
writes.

The map is an **index**, not a store. It lists the decisions made and links the
waypoints that hold their detail; a decision lives in exactly one place, its
waypoint, so the map gists and links, never restates.

### MAP.md

The whole map at low resolution, loaded once per session. Open waypoints are **not**
listed here — they are found by the frontier query.

```markdown
---
slug: <slug>
charted_at: <yyyy-mm-dd>
---

## Destination

<what reaching the end looks like: the spec(s) or decision this effort is finding
its way to. One or two lines; every session orients to it before choosing a waypoint.>

## Notes

<domain; skills every session should consult; standing preferences for this effort;
whether task waypoints may execute rather than decide>

## Decisions so far

<!-- one line per closed waypoint, enough to judge relevance; zoom the link for detail -->

- [<waypoint title>](W0N.md): <one-line gist of the answer>

## Not yet specified

<!-- fog of war: in-scope questions you can't yet phrase sharply. Graduates into
waypoints as the frontier advances. -->

## Out of scope

<!-- work ruled beyond the destination. Closed, never graduates. -->

- [<waypoint title>](W0N.md): <why it sits past the destination>

## Handed off

<!-- chunks whose way is clear: the grill that took them -->

- <chunk>: `.edad/grills/<name>.md`
```

### Waypoints

```markdown
---
id: W03
title: <the question as a title>
type: research | prototype | grill | task
status: open | closed | out-of-scope
blocked_by: [W01, W02]
claimed_by: null            # a name; set before any work, committed immediately
claimed_at: null
resolved_at: null
---

## Question

<the decision or investigation this waypoint resolves, sized to one session>

## Resolution

<empty until resolved. Then: the answer, what was rejected and why, links to any
asset — a research note, a spike branch, a checklist — never the asset pasted in>
```

A session **claims** a waypoint by setting `claimed_by` and committing, **first**,
before any work, so concurrent sessions skip it. The field *is* the claim: open and
unclaimed means takeable. Sessions share the map through git, so pull before
claiming and commit the claim on its own.

A waypoint is **unblocked** when every id in `blocked_by` is `closed`. The
**frontier** is the open, unblocked, unclaimed waypoints — the edge of the known.
Print it at the start of every working session:

```
python3 - .edad/maps/<slug> <<'PY'
import sys, yaml, pathlib
d = pathlib.Path(sys.argv[1])
wps = {}
for p in sorted(d.glob('W*.md')):
    fm = yaml.safe_load(p.read_text().split('---')[1]); wps[fm['id']] = fm
for w in wps.values():
    if w['status'] == 'open' and not w['claimed_by'] \
       and all(wps[b]['status'] == 'closed' for b in w.get('blocked_by') or []):
        print(f"{w['id']}  {w['type']:<9} {w['title']}")
PY
```

## Waypoint types

Every waypoint is **HITL** (worked *with* a human who speaks for themselves) or
**AFK** (the agent alone). A HITL waypoint resolves only through that live
exchange; the agent never plays the human's side (a grill that answers its own
questions has broken this).

- **research** (AFK). A fact a decision waits on, from outside the working
  directory. Resolved by `/research`, which writes `docs/research/<date>-<slug>.md`
  and lists what it could not verify. The waypoint's Resolution links the note and
  carries the Unverified list forward — an unverified fact is not a resolved
  waypoint.
- **prototype** (HITL). Raise the fidelity of the discussion with something cheap and
  concrete to react to. Resolved by `/prototype`, which builds it on a
  `spike/<slug>-W0N` branch that is never merged and returns the reactions and the
  scenarios that felt wrong. The Resolution records those — they are the next grill's
  input — and links the branch, never the artifact itself. Use when "how should it
  behave" or "how should it look" is the question.
- **grill** (HITL). Conversation. The default. Call `/grill-me` on the question; call
  `/find-seams` first when the decision touches legacy code and nothing could yet
  prove it wrong. The grill record goes to `.edad/grills/` as usual and is linked
  from the Resolution. A grill waypoint whose answer turns out to be "this chunk is
  ready" is the map's exit for that chunk: record it under **Handed off**.
- **task** (HITL or AFK). Work that must happen before a decision *can* be made —
  signing up for a service so its API can be judged, provisioning access, moving data
  so its shape can be seen. The one type that does rather than decides; it earns its
  place by unblocking a decision, never by delivering the destination. AFK where the
  agent can drive it alone, otherwise a precise checklist for the human. The
  Resolution records what was done and the facts later waypoints depend on
  (where credentials live, new URLs, row counts).

## Fog of war

The map is *deliberately* incomplete: don't chart what you can't yet see. Beyond the
live waypoints lies the fog — decisions and investigations you can tell are coming
but can't pin down, because they hang on questions still open. Resolving a waypoint
clears the fog ahead of it, graduating whatever is now specifiable into fresh
waypoints, until the way is clear.

**Not yet specified** is where that dim view is written. Everything there is in
scope, just not sharp enough to be a waypoint. Write as loosely or fully as the view
allows; it doubles as a signpost for whoever reads the map next.

**Fog or waypoint?** Whether you can state the question precisely now — *not* whether
you can answer it now.

- **Waypoint when** the question is sharp, even if blocked.
- **Not yet specified when** you can't yet phrase it that sharply. Don't pre-slice
  the fog: one patch may graduate into several waypoints, or none.

## Out of scope

Fog only gathers *toward* the destination. Work past it is **out of scope** — a
scoping act, not a step on the route. When an existing waypoint turns out to sit past
the destination, set `status: out-of-scope`, and leave one line under **Out of
scope**: the gist and why, linking it. It stays out of **Decisions so far**, which
records the route actually walked.

Out-of-scope work never graduates. It returns only if the destination is redrawn,
and then as a fresh map.

## Invocation

Two modes. Either way, **never resolve more than one waypoint per session**, except
research waypoints, which run in the background. End every session with `/handoff`
naming the map.

### Chart the map

The user arrives with a loose idea.

1. **Name the destination.** `/grill-me`, aimed at one question: what is this map
   finding its way to — which spec(s), or which decision? The destination fixes the
   scope, so it is settled first.
2. **Map the frontier.** Grill again, **breadth-first**: fan across the whole space
   rather than deep on any thread, surfacing the open decisions and the first steps
   takeable now. **If this surfaces no fog** — the way is already clear and the
   whole thing fits one grill — you don't need a map. Stop, say so, and offer
   `/grill-me` on the idea directly.
3. **Create `MAP.md`**: Destination and Notes filled, Decisions-so-far empty, the fog
   sketched into **Not yet specified**.
4. **Create the waypoints you can specify now**, then wire `blocked_by` in a
   **second pass** (ids first, edges after). Everything you can't yet specify stays
   in the fog.
5. **Fire the research.** For each `research` waypoint, claim it and invoke
   `/research` in the background, with the waypoint's Question as the pinned question
   and `MAP.md` as the context. Their notes land in `docs/research/` on this branch.
6. Commit the map and stop. Charting is one session's work; it resolves nothing by
   hand.

### Work the map

The user names a map slug, optionally a waypoint.

1. Load `MAP.md` — the low-res view — and print the frontier.
2. Choose. If the user named a waypoint, take it. Otherwise the first frontier
   waypoint. **Claim it and commit** before any work.
3. Resolve it by type. **Zoom as needed**: read the full body of any related or
   closed waypoint on demand; invoke whatever skills **Notes** names.
4. Record: fill the waypoint's **Resolution**, set `status: closed` and
   `resolved_at`, append the one-line gist to **Decisions so far**.
5. Advance the frontier: create newly specifiable waypoints (create, then wire);
   clear each graduated patch from **Not yet specified** so it lives only as its
   waypoint. If the answer shows a waypoint sits past the destination, rule it out of
   scope rather than resolving it. If it invalidates other waypoints, amend or close
   them and say so in the Resolution.
6. If the answer clears a chunk's way entirely, add it under **Handed off** with the
   grill that will take it — and stop there. Running the grill is the next session's
   work.
7. Commit, `/handoff`.

Other sessions may be working other frontier waypoints at the same time; expect the
map to have moved when you pull.
