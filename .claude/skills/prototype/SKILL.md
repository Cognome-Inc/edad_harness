---
name: prototype
description: "Build a throwaway prototype to answer a design question before it is grilled: a shareable one-file demo that lets a non-developer push a state model through awkward cases, or several structurally different UI variants on one route. Its output is the reaction and the scenarios that felt wrong — grill input, never code for main. Use when a decision is hard to reason about on paper, or to resolve a prototype waypoint."
argument-hint: "The question the prototype must answer, and optionally the waypoint or grill it feeds"
disable-model-invocation: true
---

# Prototype (EDAD)

A prototype is **throwaway code that answers a question**. The question decides the
shape.

## What a prototype produces here

Not code. In this method nothing reaches main except through a ticket with frozen
tests, and the agent writes that code under the gate. A prototype is upstream of all
of it: it exists because someone could not tell, on paper, whether a state model or
a layout is right, and it ends when they can.

Its outputs, in order of value:

1. **The reaction** — "wait, that shouldn't be possible", "I assumed X would be
   different". Each one is a decision waiting for a grill.
2. **The scenarios** — the walkthroughs that produced the reactions. A scenario that
   felt wrong is a frozen test in waiting: the grill pins the decision to it, the
   ticket freezes it, the agent turns it green.
3. **The artifact**, kept as a primary source on a spike branch, so the walkthrough
   can be rerun by whoever reads the grill later.

The validated logic does **not** lift into the real module. It is the wrong language
half the time, and the right code is the agent's to write against the tests the
prototype helped specify. Say so in the artifact's intro so nobody tries.

## Pick a branch

Identify which question is being answered, from the prompt, the surrounding code, or
by asking:

- **"Does this logic / state model feel right?"** → [LOGIC.md](LOGIC.md). One
  self-contained HTML file — free-play buttons plus tabbed guided walkthroughs —
  that pushes the model through cases hard to reason about on paper, driveable by a
  non-developer. Works for any target, including a pure backend or CLI: the model
  is re-expressed in the demo, not imported.
- **"What should this look like?"** → [UI.md](UI.md). Several structurally different
  variants of one page in the target's own stack, switchable from a floating bar.
  Only for a target that has a UI; the harness itself has none.

Getting this wrong wastes the whole prototype. If the question is ambiguous and the
user isn't reachable, default by surroundings — a module or a data shape → logic; a
page or component → UI — and state the assumption at the top of the artifact.

## Rules that apply to both

1. **HITL.** A prototype resolves through a human's reaction. The agent builds and
   hands over; it never plays the human's side. Never built inside an EDAD session,
   never in any ticket's scope.
2. **State the question, visibly, in the artifact.** One paragraph a reader sees
   without opening source. A prototype answering the wrong question is pure waste,
   and you only find out later.
3. **Trivial to run.** A logic demo is one file the user double-clicks, or an
   Artifact link. A UI prototype starts from one command in the target's task
   runner. No thinking required to start it.
4. **No persistence by default.** State lives in memory. If the question is
   persistence itself, hit a scratch store with a "PROTOTYPE, wipe me" name.
5. **Skip the polish.** No tests, no error handling beyond what makes it run, no
   abstractions. Learn something fast.
6. **Surface the state.** After every action (logic) or variant switch (UI), render
   the full relevant state so the change is visible.
7. **Capture when done.**
   - Commit the prototype to `spike/<slug>` (`spike/<slug>-W0N` when it resolves a
     waypoint), off main, never merged.
   - Record the answer — the question, the reactions, the scenarios that felt wrong,
     and the spike branch + commit — in the waypoint's Resolution when there is a
     map, otherwise in the grill record's Record section when the grill runs.
   - Nothing from the prototype lands on main. The grill pins the decisions; the
     ticket freezes the scenarios as tests.
