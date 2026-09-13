---
name: review-branch
description: "Review a finished EDAD ticket before merge along separate axes: Drift (what the diff does that no frozen test or decision covers), Craft (smells and standard breaches the gate cannot see), and, when the diff crosses a seam, Integration (what the diff changes for code and readers outside it). Advisory only, never a gate. Use before merging a promoted ticket, or when asked to review a session's output."
argument-hint: "Ticket ID (T0NN), a run branch (edad/run-<TS>), or nothing to infer from the checkout"
disable-model-invocation: true
---

# Review branch (EDAD)

Review the work a session produced, before a human merges it. Separate axes, run as
isolated sub-agents so none pollutes another's context, reported side by side and
never merged.

- **Drift** — what the diff does that no frozen acceptance test asserts and no
  approved decision calls for.
- **Craft** — smells and documented-standard breaches that the gate is blind to.
- **Integration** (conditional) — what the diff changes for callers, readers and
  documents outside the diff, which the frozen tests cannot see because they are
  outside scope.

## This is advisory. It is not a gate.

A promoted evidence record already states that the code satisfies an approved
contract, derived mechanically, reproducibly, from an exit code. Nothing here
supersedes that or adds to it.

What this produces is an opinion. It goes to the scratchpad, it is never cited in an
evidence record, and it never enters `full_gate` — a gate whose verdict depends on a
model's judgement is not reproducible, and reproducibility is the property the whole
harness exists to provide. If a finding here matters enough to enforce, the answer is
a new ticket with a frozen test, not a stricter reviewer.

Say this in the report's header, so a reader who arrives at the file alone cannot
mistake it for evidence.

## Deliberately not checked here

The gate already answers these, mechanically, and a second soft opinion competing
with a hard verdict is worse than no opinion. Each maps to a field in the evidence
record:

- **Do the acceptance and full-gate commands pass?** `commands_ok`, `commands[]`.
- **Did the diff stay inside scope?** `scope_violations`, `scope_enforced`.
- **Is the change too large?** `kill_conditions.max_diff_lines`, checked every iteration.
- **Were the frozen tests altered?** `freeze_ok`, against `.edad/hashes/<ID>.json`.

Do not re-litigate any of them. If the ticket has a promoted evidence record, they
all passed; read it rather than re-deriving.

## The review is fresh

The session log carries `iterations[].agent_output` — the agent's own account of what
it did. **No sub-agent sees it.** A reviewer who reads the author's summary first
reviews the summary, not the diff. The aggregator may read it after every sub-agent
has reported, only to note where the agent's account and the reviewers' findings
disagree.

Sub-agents receive the diff, the contract, and the codebase. Not this conversation,
not the grill transcript's conclusions, not each other's reports.

## Process

### 1. Establish the subject — deterministically, before spawning anything

The argument is a ticket ID, a run branch, or nothing.

- **Ticket ID (`T0NN`).** The primary key. Everything else derives from it.
- **Run branch (`edad/run-<TS>`).** Read `.edad/runs/<TS>.json` → `tickets`. Review
  each ticket whose `status` is `promoted`, separately, each against its own base.
  List skipped tickets with their `skip_reason` in the report header and do not
  review them.
- **Nothing.** Infer from the checkout: a `edad/t0NN` branch names the ticket; a
  run branch is handled as above; anything else, ask.

Branches here are not the unit of review. `edad/t0NN` (session worktree),
`edad/run-<TS>` (queue output) and a human PR branch all contain the same ticket
commits, and the run branch also carries evidence and re-lock commits on top. Key on
the ticket and read the evidence record; do not diff to `HEAD`.

Resolve, and print as one block before doing anything else:

```
ticket:        T0NN
evidence:      .edad/evidence/T0NN.json      (promoted | absent)
outcome:       passed | passed_modulo_baseline | unwinnable | aborted | incomplete
base_ref:      <sha>      # evidence.base_ref, else session.base_commit
commit:        <sha>      # evidence.commit, else last session.iterations[].commit
changed_files: [...]      # evidence.changed_files
spec:          .edad/specs/<name>.md         # ticket frontmatter `spec:`
frozen:        [...]                         # ticket frontmatter `frozen:`
full_gate:     [...]                         # ticket frontmatter `full_gate:`
diff lines:    N          # git diff --stat base_ref..commit
```

Then the range is `git diff <base_ref>..<commit>` — two dots, both refs are on one
line — and the commits are `git log <base_ref>..<commit> --oneline`. The evidence
commit and the re-lock commit are excluded by construction; if `.edad/` files appear
in the diff anyway, the range is wrong. Stop and say so.

Where to look when evidence is absent, in order: the newest
`.edad/records/T0NN-*.json` (an unpromoted gate record), then the newest
`.edad/sessions/T0NN-*.json`. A `red_proof`-bearing lock at `.edad/hashes/T0NN.json`
with none of those means the ticket was approved and never run: nothing to review.

Confirm the base resolves and the diff is non-empty before spawning anything. A bad
ref should fail here, not inside three sub-agents.

### 2. Load the contract

Read, and do not re-derive:

- `.edad/tickets/T0NN.md` — scope, frozen, acceptance, full_gate, kill_conditions,
  and the prose sections. Its `decisions:` list holds **IDs only**.
- `.edad/specs/<name>.md`, the `## Decisions` YAML block — the decision text. Each
  entry has `decision`, `verify`, `scope`, `frozen`, `seam`, and either `rejected`
  (enforced decisions: the alternatives the grill turned down) or `unenforced` (why
  no test covers it). Both matter to Drift; see the brief.
- `.edad/hashes/T0NN.json` — the approval lock. Top-level keys are frozen paths →
  sha256; the `_edad` block holds `approved_at`, `ticket_sha256`, `decisions`,
  `red_proof`, `mutation_proof`, `full_gate_baseline`.
- The frozen test files named by the ticket, at `<commit>`. **These are the
  contract.** Not the spec, not the ticket prose — the assertions.

If there is no lock, this branch did not come from the pipeline. Say so plainly in
the report and review it on the Craft axis only; there is no contract to measure
drift against.

Note the outcome, and what it means for the review:

- `passed` — the normal case.
- `passed_modulo_baseline` — the full gate passed except for failures already present
  at approval, listed in the lock's `full_gate_baseline`. Name them in the header so
  a reader does not mistake them for findings.
- `unwinnable` — the agent proved the ticket cannot be satisfied. You are reviewing a
  ticket defect, not the agent's work; say which.
- `aborted` — a kill condition fired (`abort_reason`). The branch is partial; review
  what is there and say it is partial.

Two kinds of noise the reviewers should be told about in advance:

- Stubs are authored before the base commit ("returning stubs" in the ticket
  commit), so the diff shows stub → implementation. That is the intended shape,
  not over-fitting.
- The ticket may carry a "not yours to fix" section (git failing inside the docker
  sandbox, for instance). Pass it through so a reviewer does not rediscover it.

### 3. Size the review

Count changed files and diff lines from step 1.

- **Small — up to 6 files and 400 diff lines.** One sub-agent per axis.
- **Large — above either.** Shard by file: group `changed_files` into shards of at
  most 3 files or ~250 lines, keeping files that import each other in the same shard.
  Spawn one sub-agent per shard per axis. Every shard gets the full contract and the
  full text of every frozen test; only its file list differs. Then run one
  **reconcile pass per axis** (step 5) before aggregating.

Never trade coverage for a smaller brief: a sub-agent with a 900-line diff will
review the first 300 lines and skim the rest. Sharding is how thoroughness survives
size.

### 4. Spawn the sub-agents in parallel

All in one message. Each gets the repo path, the diff range, the commit list, the
resolved block from step 1, and the noise notes from step 2. Each must end its report
with a **coverage ledger**: every hunk in its file list (`file:@@ line range`) with
one word — `covered`, `finding`, or `skipped` and why. A ledger with gaps is a
finding against the review itself; the aggregator reports it.

**Drift sub-agent.** Add: the full text of every frozen test file, the ticket's
`scope`, the spec's `## Decisions` block in full (enforced and unenforced), and the
ticket's `## Required interface` section if present.

> Brief: The frozen tests are the entire enforced contract; the spec's decisions are
> the approved intent. Report, per file and hunk:
> (a) **Unasserted behaviour** — code in the diff that no assertion in the frozen
> tests exercises. Name the hunk and say which assertion you expected to cover it
> and didn't. Then check the unenforced decisions: code that discharges one of them
> (a comment, a doc section, a tag procedure) is *unasserted but approved* — list it
> under a separate heading and do not call it drift. Code with neither an assertion
> nor a decision behind it is the main finding: nobody approved it, and the gate
> cannot see it because the file is in scope.
> (b) **Rejected alternatives** — every enforced decision carries `rejected:`. Look
> for each rejected shape in the diff. Finding one is the strongest drift there is.
> (c) **Over-fitting** — implementation shaped to satisfy the assertion rather than
> the behaviour: hardcoded returns, special-cased inputs, branches that exist only
> for a test value, monkeypatch seams that exist only because a test patches there.
> Stub → implementation is expected; do not report it as such.
> (d) **Undischarged decisions** — enforced or unenforced decisions you cannot find
> implemented in the diff.
> Quote the assertion or the decision for each finding. Do not report whether tests
> pass; that is already known. Under 400 words per shard, plus the ledger.

**Craft sub-agent.** Add: whatever standards exist in the target, and the smell
baseline below pasted in full — it has no other access to it. Look for, and pass if
present:

- Documented standards: `CONTRIBUTING.md`, `CODING_STANDARDS.md`, `docs/adr/`,
  `CLAUDE.md`, or whatever the target's README points at. Many targets — this
  harness included — have none; say so in the report rather than inventing one.
- Lint configuration (`[tool.ruff]` in `pyproject.toml`, an ESLint config, …) —
  enforced by the gate where the ticket's `full_gate:` runs it; skip whatever those
  commands enforce. Read the list; do not assume which linter.
- `.edad/specs/<name>.md` `## Implementation decisions` and `## Out of scope` — the
  design rationale for this change, the nearest thing to an ADR.
- The observed house style: read a handful of the target's existing files beside the
  diff and describe their register in two lines for the sub-agent — comment density,
  whether comments give reasons or restate code, naming, error handling. A hunk that
  departs from the observed register is a judgement-call finding, labelled as
  observed, never a hard one.

> Brief: Report, per file and hunk: (a) every place the diff breaches a documented
> standard, citing the file and the rule; (b) every place it breaches the observed
> house style, labelled as observed; (c) any baseline smell, named, with the hunk
> quoted. A documented repo standard always overrides the baseline. Documented
> breaches may be hard findings; observed-style and baseline smells are always
> judgement calls, labelled as such ("possible Feature Envy"). Skip anything the
> full_gate commands already enforce. Under 400 words per shard, plus the ledger.

**Integration sub-agent** — spawn when any of these hold, and say in the header
which one did; otherwise write "Integration: not run — <reason>" and move on:

- `changed_files` spans more than one module under `edad/`.
- The diff changes a function signature, a dataclass's fields, or the key-set of
  anything written to disk (a record, a lock, a session or run log).
- The diff changes a document that describes behaviour (`QUICKSTART.md`, a header
  comment in a pins file).
- The diff is large by step 3.

Add: the list of changed public names (grep the diff for `^\+def |^\+class |^\+    [a-z_]+: ` and dataclass fields), and the ticket's `scope`.

> Brief: Read outward from the diff, not inward. For each changed public name,
> changed field, or changed on-disk key: (a) **Callers and readers outside the
> diff** — every site in the repo that calls the function, constructs the class,
> reads the key, or parses the file, and whether the change is consistent with what
> that site assumes. Quote the site. The gate ran the full suite, so a caller that
> *crashes* is already excluded; you are looking for callers that still run and now
> mean something different. (b) **Documents** — anything under `QUICKSTART.md`,
> `.edad/specs/`, docstrings, or file-header comments that describes the changed
> behaviour and was not updated, or was updated inconsistently. (c) **Schema
> readers** — for any key added to or removed from a written artifact, whether every
> reader treats absence the way the spec says (this harness's rule: absence is
> unknown, never an error, never backfilled). (d) **Seams crossed** — a change in
> one scope file that only makes sense because of a change in another; name the
> pair and say whether the ticket's `seam:` names it. Do not review the diff's
> internals; Drift and Craft own those. Under 400 words per shard, plus a ledger of
> every changed public name with `checked` / `finding`.

#### Smell baseline

Applies even where the repo documents nothing. Each reads *what it is* → *how to fix*.

- **Mysterious Name**: a name that doesn't reveal what it does or holds. → rename; if
  no honest name comes, the design is murky.
- **Duplicated Code**: the same logic shape in more than one hunk or file. → extract
  the shape, call it from both.
- **Feature Envy**: a method reaching into another object's data more than its own. →
  move the method onto the data it envies.
- **Data Clumps**: the same few fields travelling together, a type wanting to be born.
  → bundle them into one type.
- **Primitive Obsession**: a primitive standing in for a domain concept. → give the
  concept its own small type.
- **Repeated Switches**: the same cascade on the same type recurring. → polymorphism,
  or one shared map.
- **Shotgun Surgery**: one logical change forcing scattered edits. → gather what
  changes together.
- **Divergent Change**: one module edited for several unrelated reasons. → split so
  each changes for one reason.
- **Speculative Generality**: abstraction or hooks for needs the ticket doesn't have.
  → delete; inline back until a real need shows.
- **Message Chains**: long `a.b().c().d()` the caller shouldn't depend on. → hide the
  walk behind one method.
- **Middle Man**: something that mostly delegates onward. → cut it, call the target.
- **Refused Bequest**: a subclass ignoring most of what it inherits. → composition.

**Agent-specific, and worth extra weight here.** An agent optimising for a frozen test
has a standing incentive toward Speculative Generality (hedging against assertions it
can't see), toward Middle Man (a wrapper that makes a test convenient and nothing
else), and toward seams that exist only because a test monkeypatches there (a
function split at the exact line the test fakes, with no other reason to be two
functions). Look for all three.

### 5. Reconcile — only when sharded

One reconcile sub-agent per axis, given every shard report for that axis and the
full diff. It does three things and nothing else:

- Merges the shard ledgers into one and lists any hunk no shard covered.
- Hunts the smells that only exist across shards: Duplicated Code between files,
  Shotgun Surgery, Data Clumps, a rejected alternative assembled from pieces in two
  files. Shard reviewers cannot see these by construction.
- De-duplicates findings that two shards reported from opposite ends of the same
  seam.

It does not rerank, soften, or drop a shard's finding. If it disagrees with one, it
says so beside the finding and leaves the original in place.

### 6. Aggregate

Write the report to `<scratchpad>/review-<TICKET>-<commit7>-<timestamp>.md`, print
the path, and present each axis under its own heading — `## Drift`, `## Craft`,
`## Integration` — verbatim or lightly cleaned, with its merged coverage ledger at the
end of the section. If a ledger has gaps, say so at the top of that section: an
unreviewed hunk is not a clean hunk.

Do **not** merge or rerank across axes. Code can be immaculate and implement
unasserted behaviour; code can discharge every decision and be a mess; code can be
both and still change what a reader elsewhere believes. Merging lets one mask the
others, which is the reason they run apart.

Only now read `agent_output`. Add a short `## Agent's account vs. findings` section:
anything the agent claimed that a reviewer contradicts, and anything a reviewer found
that the agent did not mention. Do not adjust any finding on the strength of the
agent's account.

Close with:

- Findings per axis, and the worst within each — never a single winner across axes.
- Coverage: hunks reviewed / hunks in diff, per axis.
- A **merge note**: whether anything found here should become a follow-up ticket
  before merge, or after, or not at all. Advisory, one line, the user decides.

## Why separate axes

- Follows every standard, implements behaviour nobody asked for → Craft pass, Drift fail.
- Discharges the contract exactly, in code the next person will hate → Drift pass,
  Craft fail.
- Both clean, and a reader of the record elsewhere now silently gets a different
  answer → Integration fail.

The gate catches none of them. It answers whether the contract was satisfied, which
is a different question from whether the diff stayed inside it, a different question
again from whether the code is any good, and a different question again from what
the change did to everything the contract could not see.
