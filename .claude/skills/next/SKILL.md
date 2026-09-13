---
name: next
description: "Say where this target stands in the EDAD pipeline and what to run next — which skill or harness command, on which artifact. Runs a mechanical survey of .edad/ and git, then reads the result against the pipeline. Use at the start of a session, when unsure which skill applies, or when asked what's next / where are we."
argument-hint: "Optional: a ticket, grill, spec or map to focus on"
disable-model-invocation: true
---

# Next (EDAD)

The method is a pipeline with a skill or a harness command at every step. This skill
answers one question: **given what is in the tree right now, which step is next, on
what?**

It does not do the step. It names it.

## 1. Survey, mechanically

Run the script beside this file from the target root and print its output whole:

```
python3 .claude/skills/next/survey.py
```

It reads `.edad/` and git and prints, per effort, where every artifact stands and a
mechanical `next` line. What it prints is true of the **checkout it ran on**: a lock
or an evidence record that lives only on another branch is invisible to it, and it
says which branch it surveyed so the reader knows what it could not see. If the user
is on a feature branch and the answer looks stale, run it again on the run branch or
mainline before reasoning.

Whatever the survey prints outranks anything in this conversation, a handoff
document, or memory. When they disagree, the survey is right.

## 2. Read it against the pipeline

The pipeline, and what enters and leaves each step:

| you have                                   | next                                              |
|--------------------------------------------|---------------------------------------------------|
| an idea too big or foggy for one sitting   | `/wayfinder <idea>` — chart a map                 |
| a map with a frontier                      | `/wayfinder <slug>` — work one waypoint            |
| … whose frontier waypoint is `research`    | `/research` (background; several may run at once) |
| … whose frontier waypoint is `prototype`   | `/prototype`                                      |
| a chunk under **Handed off** with no grill | `/grill-me` on it                                 |
| an idea that fits one sitting              | `/grill-me`                                       |
| … that touches legacy code                 | `/find-seams` first, then `/grill-me`             |
| a grill record with no spec                | `/to-spec`                                        |
| a spec with no tickets                     | `/to-tickets`                                     |
| a ticket with no lock                      | read it; `python3 -m edad.gate approve T0NN`      |
| a lock the ticket has drifted from         | `python3 -m edad.gate approve T0NN` again         |
| a locked ticket never run                  | `python3 -m edad.session run T0NN [--sandbox docker]`, or queue a night: `python3 -m edad.session_queue run T0NN T0NM …` |
| a session `aborted` or `unwinnable`        | fix the contract — ticket or frozen tests — never the branch; re-approve; re-run |
| evidence not on mainline                   | `/review-branch T0NN`, then PR and merge (human)   |
| evidence on mainline                       | the next ticket in `blocked_by` order, or the next grill |
| a release due                              | QUICKSTART `## Releasing`                         |
| a session ending, work unfinished          | `/handoff`                                        |

Two things the survey cannot see and you must ask or infer:

- **Is a release due?** The survey prints commits on mainline since the last tag.
  Whether that is a release is the operator's call; say the number and stop.
- **Has a review already been done?** Review reports go to the scratchpad, not the
  tree. If the user says T0NN was reviewed, believe them and move to merge.

## 3. Answer

Lead with the one thing to do now, as a command or a skill invocation with its
argument filled in. Then, if there is more than one live effort, the rest in the
order they are blocked — a ticket waiting on another ticket is not next.

Refer to artifacts by title — the ticket's, the map's, the waypoint's — never by
bare id alone; the id rides with the title.

If the user named an artifact, answer for that one first and mention the others in
a line.

If the survey shows nothing open — every ticket merged, no grill without a spec, no
map with a frontier — say so, and that the next step is a new idea: `/grill-me` if it
fits a sitting, `/wayfinder` if it doesn't.

Do not run the step. Naming it is the whole job; the user decides.
