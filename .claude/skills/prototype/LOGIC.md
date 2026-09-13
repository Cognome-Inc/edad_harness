# Logic prototype

A single self-contained HTML file — a **shareable demo** — that lets anyone drive a
state model by clicking buttons. Use when the question is about **business logic,
state transitions, or data shape**: the kind of thing that looks reasonable on paper
and only feels wrong once pushed through real cases.

One file with nothing to install, so it can go to a designer, a PM, a domain expert.
It speaks their language, not the code's.

## When this is the right shape

- "I'm not sure this state machine handles X then Y."
- "Does this data model let me represent the case where…"
- "I want to feel out what the API should look like before writing it."
- Anything where someone wants to **press buttons and watch state change**.

If the question is "what should this look like", use [UI.md](UI.md).

## Process

### 1. State the question

Before writing code, write what state model and what question this prototypes: one
paragraph, at the top of the demo, visible on the page. If a waypoint or grill was
named, take the question from it verbatim.

### 2. Isolate the logic in a pure module

Put the logic — the part answering the question — in a single `<script>` block
written as a small pure module: no DOM, no `document`, no button handlers reaching
in. The page calls into it; nothing flows back. Shape by question:

- **A pure reducer** `(state, action) => state` — discrete events, one state value.
- **A state machine** — explicit states and transitions, when "which actions are
  even legal right now" is part of the question.
- **Pure functions** over a plain data type — no current state, just transformations.
- **A class with a clear method surface** — when the logic genuinely owns ongoing
  internal state.

Pick the shape that fits the question, not the one easiest to wire to a page.

Purity matters here for a different reason than the original method gives: this
module will **not** lift into the target (wrong language, and the agent writes the
real one against frozen tests). It stays pure so the walkthroughs are
**reproducible** — a reader of the grill record can rerun exactly the scenario the
human reacted to. That is the same reason the gate wants exit codes.

### 3. Build the shareable HTML file

One file, plain HTML/CSS/JS: no framework, no bundler, no server, everything inline.
Written for a non-developer: every label in **domain language**, buttons and state
reading like the business, not the reducer.

Top to bottom:

1. **Title and the question** from step 1, plus one line saying this is a prototype
   whose logic will not ship.
2. **Current state**: the full relevant state as a labelled panel, not a JSON dump,
   re-rendered after every click, with what just changed called out.
3. **Free-play buttons**: one per action, always available, any order.
4. **Guided walkthroughs**: scenarios, one per tab. Each tab: a short plain-language
   description of the situation and what to watch for, then the ordered buttons to
   press. Each step is a real button; starting a walkthrough resets to a known
   initial state so it runs the same way every time.

Choose scenarios for the awkward cases: the happy path, a tricky edge, an attempt at
something that should be illegal. **Name each scenario the way a test would be
named** — `a_refund_after_settlement_is_refused`, not "Scenario 3" — because that
is what it becomes.

Restrained: clean typography, generous spacing, one accent colour, no animation.

### 4. Hand it over

Two deliveries, both:

- **The file**, so it survives being emailed and opens by double-click.
- **An Artifact**, when the Artifact tool is available: publish the same file and
  hand over the link. Non-developers open a link; they don't always open an HTML
  attachment. The artifact is delivery only; the file is the primary source.

The interesting moments are "wait, that shouldn't be possible" and "huh, I assumed
X". Those are bugs in the *idea*, which is the point. If they want a new action or
scenario, add it. Prototypes evolve.

### 5. Capture

When the question is answered:

- Commit the file to `spike/<slug>` (or `spike/<slug>-W0N`), never merged.
- Write the answer where [SKILL.md](SKILL.md) says: the question, each reaction,
  the scenario that produced it, the spike branch + commit, the artifact URL if any.
- List the scenarios that felt wrong, by their test-shaped names, as **candidate
  frozen tests** for the grill. That list is the prototype's most valuable line.

## Anti-patterns

- **Don't add tests.** A prototype that needs tests is no longer a prototype. The
  scenarios *become* tests later, under a ticket — not here.
- **Don't wire it to real storage.** In-memory unless persistence is the question.
- **Don't generalise.** No "what if we later want X". One question.
- **Don't blur logic and page.** The module never touches the DOM.
- **Don't reach for a framework or server.** One file, double-click.
- **Don't try to lift the module into the target.** It is a JS re-expression of a
  model that may be Python, Go, or SQL. The agent writes the real one.
