# UI prototype

Generate **several structurally different UI variations** on a single route in the
target's own stack, switchable from a floating bottom bar. The user flips between
them in the browser, picks one (or steals bits from each), and the rest go to the
spike branch.

**Only for a target with a UI.** The harness itself has none; this branch exists for
the projects that copy these skills in.

If the question is logic or state rather than appearance, use [LOGIC.md](LOGIC.md).

## When this is the right shape

- "What should this page look like?"
- "I want to see a few options for this dashboard before committing."
- "Try a different layout for the settings screen."
- Any time someone would otherwise spend a day choosing between three vague
  mockups in their head.

## Two sub-shapes: strongly prefer A

A UI prototype is easier to judge when it's **butting up against the rest of the
app**: real header, real sidebar, real data, real density. A route on its own is a
vacuum where every variant looks fine.

### Sub-shape A: on an existing page (preferred)

The route exists. Variants render **on the same route**, gated by a `?variant=`
search param. Existing data fetching, params and auth stay; only the rendering
swaps. Something that doesn't yet have a page but would naturally live inside one (a
new section, a new card, a new step in a flow) is still sub-shape A: mount the
variants inside the host.

### Sub-shape B: a new page (last resort)

Only when the thing genuinely has no existing page to live inside. Create a
throwaway route following the target's routing convention — no new top-level
structure — named so it's obviously a prototype (`prototype` in the path or
filename). Same `?variant=` pattern. Before choosing B, check again for a host page:
an empty route hides the design problems a populated one exposes.

## Process

### 1. State the question and pick N

Default **3 variants**; cap at 5. Write the plan in one line at the prototype's
location or top-of-file, with the question from the waypoint or grill if one was
named:

> "Three variants of the settings page, switchable via `?variant=`, on the existing
> `/settings` route. Question: …"

### 2. Generate structurally different variants

Each variant holds to the page's purpose, the data it has access to, and the
target's component library and styling system, and exports a clear name
(`VariantA`, `VariantB`, `VariantC`).

Variants must disagree about **structure**: layout, information hierarchy, primary
affordance — not colour. Three slightly-tweaked card grids is wallpaper. If two come
out alike, redo one with an explicit constraint ("no card grid").

### 3. Wire them together

One switcher on the route:

```tsx
// pseudo-code; adapt to the target's framework
const variant = searchParams.get('variant') ?? 'A';
return (
  <>
    {variant === 'A' && <VariantA {...data} />}
    {variant === 'B' && <VariantB {...data} />}
    {variant === 'C' && <VariantC {...data} />}
    <PrototypeSwitcher variants={['A','B','C']} current={variant} />
  </>
);
```

Sub-shape A: existing data fetching stays above the switcher. Sub-shape B: the
throwaway route mounts the same switcher.

### 4. The floating switcher

A fixed bar at bottom-centre: left arrow, `B (Sidebar layout)` label, right arrow,
wrapping both ways. Arrows update the search param through the framework's router
so a variant is shareable and reload-stable. `←`/`→` keys cycle too, except when an
`<input>`, `<textarea>` or `[contenteditable]` has focus. Visually distinct from the
page — high-contrast pill, subtle shadow — so it's obviously not part of what's
being judged. Hidden in production builds (`NODE_ENV !== 'production'` or the
target's equivalent), so a stray merge can't ship it. One shared component,
wherever the target keeps shared UI.

### 5. Hand it over

Give the URL and the `?variant=` keys. The useful feedback is usually "the header
from B with the sidebar from C" — that is the design they want.

### 6. Capture

When a variant has won:

- Commit the whole set — every variant and the switcher — to `spike/<slug>` (or
  `spike/<slug>-W0N`), never merged. The full set is the primary source.
- Write the answer where [SKILL.md](SKILL.md) says: which variant (or which
  combination), why, and what each losing variant showed.
- **Nothing lands on main from here.** The winner is not folded in by hand: it was
  written under prototype constraints, and in this method the real page is built
  under a ticket, against whatever the grill decided to freeze — a snapshot, a
  rendered-structure assertion, an accessibility check. Remove every variant and
  the switcher from the working branch once the spike branch holds them.

## Anti-patterns

- **Variants that differ only in colour or copy.** Real variants disagree about
  structure.
- **Sharing too much between variants.** A shared `<Header>` is fine; a shared
  `<Layout>` defeats the point.
- **Wiring variants to real mutations.** Read-only, or a stub. The question is
  "what should this look like", not "does the backend work".
- **Promoting a variant straight to production.** Prototype code has no tests and
  no error handling; the ticket rebuilds it properly.
