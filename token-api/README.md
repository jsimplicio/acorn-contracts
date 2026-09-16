# Token API

This directory holds Firefox's real design tokens, converted from their native
Style-Dictionary-flavored format into the [W3C Design Tokens Community Group
(DTCG)](https://tr.designtokens.org/format/) format (`$value`/`$type`/`$description`).
It's the third artifact in this repo's set of machine-readable contracts,
alongside `component-api/` (real attributes/slots/events, CEM-shaped) and
`guidance-api/` (do's and don'ts). Where those two describe *components*,
this one describes the *design tokens* those components are built from.

Nothing here is hand-copied. `sync.py` fetches straight from the real upstream
repo, `https://github.com/mozilla-firefox/firefox`, and is meant to be
rerun any time upstream tokens change.

## How to rerun it

```sh
python3 token-api/sync.py
```

That's it. Every run:

1. **Clone.** A shallow, blobless, sparse checkout of
   `mozilla-firefox/firefox` into a temp directory, restricted to the
   locations below and deleted afterwards. A real network fetch every time,
   never a local checkout that happens to already exist.
2. **Convert.** One output file per source file, under `base/` or
   `components/`, so a converted file diffs cleanly against its source line
   for line.
3. **Record.** `sync-manifest.json` gets the commit fetched, the timestamp,
   per-run counts, and every token where a `$type` was omitted or a
   non-standard key preserved. Each run is auditable against the last.
4. **Verify.** Resolves `button.padding.inline.@base` → `space.large` →
   `dimension.relative.100` → `1rem` as a smoke test, and exits non-zero if
   it does not.

| Flag | Effect |
|---|---|
| `--ref <branch-or-sha>` | Fetch a specific ref instead of the default branch tip, to pin a sync or reproduce an old one. |
| `--local-checkout <path>` | **Dev only.** Skips the fetch and reads a local firefox checkout. Prints a warning banner and records the bypass in the manifest, so a run this way is obvious afterwards. |

## Where these files really live

Firefox's tokens are **not** all in one place. The central set is under
`toolkit/themes/shared/design-system/src/tokens/{base,components}/`. Three
other patterns feed real components, all in the same Style-Dictionary
format, so only `SOURCE_ROOTS` in `sync.py` widens for a new location.

| Also in | Holds |
|---|---|
| `browser/themes/shared/tabbrowser/` | tab, tab.nova, tabs-navbar |
| `browser/themes/shared/urlbar/` | urlbar, urlbar.nova, urlbarview, urlbarview.nova |
| `toolkit/content/widgets/<component>/` | components keeping tokens beside their own `.mjs` |
| `toolkit/content/widgets/moz-box.tokens.json` | shared by moz-box-item and moz-box-group |

## `id-map.json`

Maps each component id to its real basename(s), because Firefox's naming
often differs from the id used here (`info-bar` vs `infobar`, `toolbarbutton`
vs `toolbar-button`) and some ids draw from more than one file. Published
data rather than logic inside `index.html`, so a consumer reading only
`token-api/` can see the mapping. Schema:

```jsonc
{
  "foundational": ["button", "icon"],
  "map": {
    "panel-item": ["panel-menuitem", "panel-item"],
    "button": { "own": ["button"], "resolve": ["toolbarbutton"] },
    "icon-button": { "own": [{ "basename": "button", "onlySegment": "icon" }], "resolve": [] }
  }
}
```

**`foundational`** is loaded for every component, because these basenames are
referenced by many unrelated files. They live in `components/` but behave as
base tokens.

| Shape under `map` | Means |
|---|---|
| `["a", "b"]` | Every basename listed is this id's own content and is displayed as its rows. More than one means the component genuinely draws from more than one file. |
| `{ "own": [...], "resolve": [...] }` | `own` is displayed; `resolve` is loaded so aliases still resolve but is never shown here. For when this id aliases into a basename that has its own page. `button` aliases into two of Toolbar Button's tokens. |
| `{ "basename": "x", "onlySegment": "y" }` | Inside `own`: export only tokens carrying that exact dotted-path segment. Icon Button is the 6 `button.tokens.json` tokens with an exact `icon` segment, not the whole file Button already shows. |


**Why a segment match, not a fixed position.** This repo's own token
taxonomy (Ecosystem > Domain > Object > Pattern > Component > Element >
Category > Type > Concept > Property > Modifier > Variant > State > Scale,
see acorn.firefox.com's "How design tokens work: taxonomy" page) says a
token name only includes "enough levels to describe and communicate [its]
intent", not every level every time.

So the same level (a "Modifier" like `icon`, say) lands at different
positions in different names. Anchoring `onlySegment` to a fixed position
would miss real matches; an exact dotted-path-segment match works wherever
it sits. A substring match would not, false-positiving on any path that
merely contains a segment's letters.

**Fallback.** An id with no entry in `map` tries `<id>.tokens.json`
directly, in case a future sync adds a file matching the id itself. Same
fallback `index.html` uses.

**Known limitation.** A component's token file can alias into a *different*
component's file. Three cases are covered:

- **`button` and `icon`** — unconditionally, via `foundational` above.
- **A basename with its own id/page** — `{own, resolve}`, so it resolves
  without being displayed twice.
- **A basename with no page of its own** — a plain extra array entry, since
  there is nothing to duplicate against. `panel` picks up `popup` this way,
  because `panel.nova.tokens.json` aliases into `{popup.border.radius}`.

Anything else resolves only while viewing a page that already loads that file
for its own reasons. There is no general cross-component alias resolution, and
it surfaces as an `(unresolved)` diagnostic in `index.html` rather than a
silently wrong value.

## How to resolve a real token's value

The exact algorithm, not a description of what `index.html` happens to do.
A consumer reading only `token-api/` can reproduce the same values.

1. **Build the shared lookup.** Flatten every `base/*.tokens.json` (skip the
   `.nova.` ones for now) into a `"<basename>.<dotted.path>"` map keyed by
   each file's own stem, then the `foundational` files from `components/`
   the same way.
2. **Layer Nova on top, in a second pass.** Flatten every
   `base/*.nova.tokens.json`, and every `components/<name>.nova.tokens.json`
   for a `foundational` name, under its **non-nova** stem and merge,
   overwriting matching keys.
3. **Add the component's own files.** Look up the id in `id-map.json`'s `map`
   (fall back to `[id]`). For each basename, merge `<basename>.tokens.json`,
   then `<basename>.nova.tokens.json` on top.
4. **Resolve a value.** If `$value` matches `^\{([^{}]+)\}$`, look the captured
   path up in the merged map and repeat on that token, tracking each hop.
   Anything else is already the answer.
5. **Theme-dimension values.** An object `$value` has already been reduced by
   `sync.py` to one branch per `DEFAULT_PICK_ORDER`; the full original set is
   preserved under `$extensions["org.mozilla.themes"]`.

> **Warning** Step 2 has to be a separate, later pass. A nova file and its
> non-nova sibling write the same keys, so merging both in one pass leaves the
> winner depending on fetch timing rather than on Nova being intended.

> **Warning** The foundational half of step 2 is the easy half to miss, and
> silently wrong when missed. `icon.color.information` is `{color.blue.60}` in
> `icon.tokens.json` and `{color.violet.50}` in `icon.nova.tokens.json`, so
> skipping it hands every component resolving through `icon.*` a Proton blue
> where Nova is violet.

> **Warning** A `nova` branch wins over `$value`. Many tokens carry
> `$extensions["org.mozilla.themes"].nova`, shaped `{comment?, value}`; that
> branch is the real Nova value and `$value` is the Proton one `pick_default`
> surfaced. `text.color.@base` is the clearest case: `$value` is
> `{color.gray.100}`, a Proton grey, while its Nova value is
> `{color.violet-desaturated.90}` light / `{color.violet-desaturated.0}` dark.
> Resolving `$value` alone silently shows Proton.

> **Note** A `moz-*` file also registers under its unprefixed name. Firefox's
> own files refer to these components without the prefix:
> `moz-message-bar.tokens.json` contains
> `oklch(from {message-bar.icon.color} l c h / 20%)`, and
> `moz-toggle.tokens.json` aliases `{toggle.dot.height}`. Flatten such a file
> a second time under the bare name, or those aliases resolve to nothing.
> Lookup only: the token's own exported path keeps the real basename.

> **Note** In step 4, a path missing from the map is reported unresolved
> rather than guessed, and a depth cap of 12 guards against an accidental
> cycle. It is not expected to trigger on real data.

**Proton scale steps Nova replaced are already gone.** Firefox ships both
generations side by side: `color.tokens.json` is the Proton ramp (steps
0-110, oklch), `color.nova.tokens.json` the Nova one (0-90, hex), on
different scales. Merging them key by key does not remove a step Nova
dropped, it keeps the Proton one, which then lands at the end of a scale it
does not belong to. `color.gray.100` (#15141a) is visibly *lighter* than
`color.gray.90` (#121114), and `border.radius.xxlarge` was listed when Nova
has no such radius.

`sync.py` drops those at conversion time (`prune_superseded_scale_steps`), so
nothing downstream has to know. Four guards keep it off anything live:

- **`base/` only.** A component token's real consumer is CSS in
  mozilla-central, not another token, so "nothing aliases it" says nothing
  about whether it is live. Applying this to `components/` would delete ~45
  real tokens (`moz-toggle.dot.width`, `card.gap.compact`).
- **Only a group Nova rewrote.** Nova defines no `white`/`black` group at all,
  so those are the only ramp there is and they stay.
- **Only a flat scale** (every member a leaf). `background.color` holds nested
  groups (`box`, `list`, `dimmed`) so it is never touched; `border.radius` is
  seven flat leaves so it is.
- **Only a step nothing references under Nova.** Not a raw scan: both
  generations live in the same file, so a blanket scan counts a reference that
  exists only in a superseded Proton definition, which would keep a dead token
  alive forever. A Proton token its own `.nova` sibling redefines is skipped,
  as is the non-nova half of a token carrying its own `nova` branch.

`color.gray.100` is the worked example, and the shape of the answer matters
more than the tally, which has moved twice already. A raw scan for
`{color.gray.100}` finds more tokens than really depend on it: some are
Proton definitions their own `nova` branch replaces, and only the ones with
no Nova value left are genuinely still pointing at a Proton grey. As of
2026-09-16 that was `button.text.color.@base`,
`toolbar.field.text.color.@base`, `toolbar.text.color` and
`toolbox.text.color.@base`, while `text.color.@base` has a `nova` branch and
so does not count.

To recount rather than trust that list, walk every non-`.nova.` file in
`base/` and `components/`, keep the tokens whose `$value` is exactly
`{color.gray.100}`, and drop any that carry
`$extensions["org.mozilla.themes"].nova`.

19 steps go: `100`/`110` on red, orange, yellow, green, cyan, blue, violet,
purple and pink, plus `border.radius.xxlarge`. `color.gray.100` and
`border.radius.circle`/`large` stay, all three still aliased by real tokens
with no Nova replacement.

## Light and dark, and what the theme toggle actually switches

Every token page resolves its values for one theme at a time, and the theme
toggle re-resolves the whole page rather than swapping a stylesheet. A token
that reads the same in both is genuinely the same value, not a page that
failed to update.

A token's theme values live in
`$extensions["org.mozilla.themes"]`, as `light` and `dark` alongside
`nativeTheme`, `forcedColors` and `prefersContrast`. Plain `$value` is the
fallback when a token declares no themes block at all.

A row can change in dark mode three ways, and only the first is visible in
the token's own definition:

1. **It declares its own `dark`.** `color.accent.primary.@base` is
   `{color.violet.50}` light and `{color.violet.30}` dark.
2. **It aliases something that does.** `color.accent.primary.selected`
   declares no `dark` of its own in the Nova generation; it points at
   `button.background.color.primary.active`, which resolves through to
   `color.accent.primary.active`, which does. Resolution has to take the
   dark branch at *every* hop, not just the first, or the last hop quietly
   hands back a light value.
3. **Its value is relative to `currentColor`.** `text.color.deemphasized` is
   `color-mix(in srgb, currentColor 69%, transparent)`. The string is
   identical in both themes, but it renders from whatever text colour is in
   force, and that flips. See the round-trip section below for why these
   tokens are a special case in more ways than this one.

So "does this change in dark mode" cannot be answered by comparing two
declarations. Only a fully resolved value per theme answers it, which is
what the pages do and what any consumer of this directory has to do too.

Primitives (`color.blue.50`, `space.small`, every `font.*` and `size.*`) have
no theme variance at all and are not expected to: the semantic layer above
them is where light and dark diverge.

## Figma existence check: figma-check.py

The "In Figma" column on every component page and every base token page
answers one narrow question: does this row's own CSS custom property name
also exist as a real variable in Mozilla's "Nova Styles (Experimental)"
Figma file? It is a name-vs-name sync check, not "can this value be traced
back to Figma somehow."

**Always the Figma REST API directly, never Supernova.** Supernova's sync of
this design system has known gaps, and its token detail could not confirm
which Figma file it was even reading. This is a standing rule for the whole
project family.

**Matching is by name, because `codeSyntax` is nearly empty.** The API does
return a `codeSyntax` field, but only 2 of the file's 718 variables populate
it. If a future publish fills it in broadly, that should become the primary
signal and this section should say so rather than quietly keeping name
matching once something better exists.

**The three files.**

**Step 1 — `figma-variables-dump.json`.** every variable in the file, one REST call.
   Needs a Figma personal access token; this repo has none of its own.

   ```sh
   curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
     "https://api.figma.com/v1/files/$FIGMA_FILE_KEY/variables/local" \
     -o /tmp/figma-variables-raw.json
   ```

   See the file's own `_comment` for what is kept per variable and why 2 of
   the 720 raw variables (Figma's `deletedButReferenced` ghosts) are dropped.

**Step 2 — `figma-check.py`.** pure local computation, no network. Rerun it any time
   `resolved/*.json`, `component-api/*.json`, `base/*.tokens.json` or the
   dump changes:

   ```sh
   python3 token-api/figma-check.py
   ```

   It builds the same universe of property names `index.html` would render
   across every component page *and* every base token family, then normalizes each name and each Figma
   variable name to a tuple of lowercase words, splitting on every
   non-alphanumeric character. That split is what makes `box-shadow` collide
   correctly with Figma's `box / shadow` without a hardcoded list of which
   basenames are "really" two words.

**Step 3 — `figma-token-map.json`.** the output that `index.html` fetches at render
   time. A baked lookup file rather than a live query, for the same reason
   `id-map.json` and `sync-manifest.json` are files: the page is static.

**How a match is decided.**

| result | meaning |
| --- | --- |
| same words, same order | `yes` |
| same words, different order | `yes`, `matchType: "reordered"` |
| anything else | `no` |
| token declares `ignoreFigma` | `ignored`, with the design system's own `reason` |

### Why some values cannot round-trip at all

A design token wants to be format-agnostic: one fact, expressible in CSS, in
Figma, in iOS, anywhere. Most are. A few are not, and it is worth being
precise about where each layer gives out, because the answer is not "Figma is
behind."

Take the two that upstream flags hardest:

```jsonc
"deemphasized": { "$value": "color-mix(in srgb, currentColor 69%, transparent)", "$type": "color" }
```

**Layer 1, the token format.** That entry claims `$type: "color"`, but its
value is a CSS *expression*, not a colour. DTCG's colour type is a literal:
a concrete value in a named colour space. The format has no expression
syntax, no function calls, no arithmetic. So this token is already outside
what DTCG can represent. It survives the conversion only because the value
rides through as an opaque string that happens to be valid CSS. Nothing
downstream can interpret it, reason about it, or convert it.

**Layer 2, `currentColor`.** Even granting the expression, `currentColor` is
not a colour. It is a reference to whatever `color` is inherited at the point
of use. The same token is grey at 69% in body text, red at 69% inside an
error region, and follows a theme flip for free. That is deliberate and it is
the whole point of the token: it is defined *relative to its context*.

**Layer 3, Figma.** A Figma colour variable holds a resolved RGBA. The alpha
half is expressible, `color-mix(in srgb, X 69%, transparent)` is exactly X at
69% alpha. What is not expressible is "69% of whatever colour this inherits",
because there is no inheritance to refer to. Figma has to bake in one base
colour, which is correct for exactly one context and silently wrong in every
other. `border.color.transparent` fails one layer earlier and for a different
reason: it exists to be overridden by `prefers-contrast`, a media query, which
is not a colour question at all.

So a hex-with-alpha in Figma is not Figma being lossy about a colour. It is a
static answer standing in for a value that was defined as dynamic, two layers
after the token format already stopped being able to describe it.

**This does not change the "In Figma" answer.** That column asks whether the
name exists, and for these it does: four of the five have an exact same-named
variable. A token carrying `$extensions["org.mozilla.meta"].ignoreFigma`
keeps its real `yes`/`no` and carries the reason as `valueCaveat`, surfaced
in the cell's tooltip rather than as a third status. The five today are two
`text.color.*`, two `focus.outline.*`, and `border.color.transparent`.

**Strictly two states, never three.** A near miss (one word off) is recorded
as `no` with `matchType: "near-miss"` and the close variable in
`matchedPath`, as a diagnostic only. It is still a miss. Hedging on it would
hide the exact drift this check exists to surface.

**No alias-chain following.** `--box-button-background-color` has no matching
Figma variable even though its value resolves through
`button/background/color/menu`. That is the correct finding: counting a match
through a differently-named variable answers a different question than the
one this column asks.

Two kinds of `no` are expected rather than bugs: near misses, and entire
component families this Figma file simply does not cover (no urlbar, panel,
toolbar, sidebar, checkbox or `moz-*` semantic colour groups appear in it).

Deliberately not restated here as a total: the last version of this line
said 640 property names and was stale by 273 the moment base families were
added. `figma-token-map.json`'s own `counts` block has the current numbers,
and `python3 token-api/figma-check.py` prints them.

## Source format (Firefox's native tokens)

Every file above feeds a [Style Dictionary](https://amzn.github.io/style-dictionary/)
build (see `toolkit/themes/shared/design-system/docs/README.design-tokens.stories.md`
upstream for the authoritative explanation of the central tree's own
conventions, which the colocated files also follow). The parts that matter
for this converter:

- **A leaf is any object with a `value` key.** Everything else is a plain
  nesting group. This is Style Dictionary's own convention, not something
  Firefox invented, and it's exactly how DTCG's `$value` distinguishes a
  token from a group too, so the two formats already agree on the basic
  shape.
- **`@base`** is a workaround for a Style Dictionary limitation: you can't
  nest a token name past a segment that already has a `value` (so
  `--font-weight` and `--font-weight-semibold` can't both exist unless the
  first is written as `font.weight.@base`). References sometimes target
  `.@base` explicitly (`{button.border.color.@base}`) and sometimes reference
  a group without it (implying its default child).
- **Theme-dimension-keyed values.** A single token's `value` is sometimes an
  object keyed by `forcedColors` / `brand` / `nativeTheme` / `platform` /
  `prefersContrast` / `light` / `dark` / `default`, each holding a different
  value for that context. Real and common, seen in roughly a third of
  converted tokens.
- **`.nova.tokens.json` files** are a second, orthogonal axis: whole override
  files, one per "override identifier" (only `nova` today, gated behind
  `browser.nova.enabled`, see `config/override-identifiers.js` upstream),
  redefining a subset of tokens. Structurally identical `*.tokens.json`
  files, just consumed at build time as a `@media -moz-pref(...)` layer
  rather than the base cascade. This sync includes them, named exactly like
  their non-`.nova` counterparts so they stay independently diffable.
- **`"override": true`** is a separate, per-token flag (unrelated to the
  `.nova` file mechanism above) seen only in
  `color.tokens.json`, `border.tokens.json`, `icon.tokens.json`, and
  `toolbox.tokens.json`. Per upstream's own build config
  (`config/tokens-config.js`), it marks a token as excluded from the main
  build/Storybook/stylelint token tables. Preserved losslessly (see below),
  not silently dropped.
- **`comment`** is a human-readable annotation next to `value`, not consumed
  by the build. One case (`font.tokens.json`'s `size.small`) nests a
  `comment` *inside* a theme-dimension value object rather than beside the
  leaf's own `value`/`comment`, that one rides along untouched inside the
  `$extensions` blob (see below) rather than being promoted to
  `$description`, since only a leaf's own top-level `comment` is treated as
  the token's description.

## Conversion rules applied

1. **`value` → `$value`**, **`comment` → `$description`**, for any leaf whose
   `value` is a plain literal or a single `{alias}` reference string.
2. **Group structure is preserved exactly.** A source token at
   `button.padding.inline.@base` becomes a DTCG token at the same path in
   `components/button.tokens.json`, so the converted file is diffable
   against the source by eye.
3. **Aliases keep Firefox's own `{group.token}` syntax, `.@base` included.**
   DTCG's alias syntax is the same curly-brace dot-path syntax already, so
   this is a no-op beyond renaming `value`. **Decision: `.@base` segments are
   kept literally**, not resolved away, because a group can have both an
   `@base` child and named siblings (`button.background.color` has `@base`,
   `hover`, `disabled`, `primary`, ...), dropping `.@base` from a reference
   would make it ambiguous with the group itself, which isn't a leaf. Keeping
   it explicit means a reference is always a literal, directly-walkable JSON
   path with no implicit-default convention a consumer has to separately
   know about.
4. **Theme-dimension-keyed values** get one representative `$value` at the
   top level, plus the complete original object under
   `$extensions["org.mozilla.themes"]`. Every variant in the source is still
   there verbatim; the flattening is for top-level convenience only.
   Picking order, in `sync.py`'s `pick_default()` / `DEFAULT_PICK_ORDER`:
   `default`, then `brand` (itself often `{default: ...}`), `light`,
   `nativeTheme`, `forcedColors`, `platform`, `prefersContrast`, `dark`, and
   last whatever key is left. `default` beats `brand` deliberately: a token
   stating an explicit default says that value applies regardless of brand or
   platform, a stronger signal than whatever `brand` happens to be.
5. **`"override": true`** and any other non-`value`/`comment` sibling key
   found on a leaf is preserved verbatim under
   `$extensions["org.mozilla.meta"]`, so it isn't silently lost even though
   DTCG has no first-class slot for it.
6. **`$type` is inferred, never guessed per-value.** The value's own shape is
   tested first, then the token's path.

| Test, in order | `$type` |
|---|---|
| Value is a literal colour function (`rgb(`, `rgba(`, `hsl(`, `hsla(`, `oklch(`, `oklab(`, `lab(`, `lch(`, `color-mix(`) or a `#` hex triple, or an alias whose first path segment is `color` | `color` |
| Path contains `color`, `fill` or `stroke` | `color` |
| Path contains `font` plus `weight`, or `font` plus `family` | `fontWeight`, `fontFamily` |
| Path contains `opacity` | `number` |
| Path contains `space`, `dimension`, `padding`, `gap`, `size`, `radius`, `width`, `height`, `min-height`, `min-width`, `max-width`, `inset`, `offset` or `margin` | `dimension` |
| Nothing matches, or the value is a composite that cannot flatten to a scalar | omitted, and logged |

**Why the value is tested before the path.** It catches tokens like
`tab.selected.textcolor`, whose own path never spells out "color", "fill" or
"stroke", but whose value leaves no doubt.

**`fill` and `stroke` are a deliberate extension** past a literal "color"
keyword. `button.icon.fill` and `button.icon.stroke` hold unambiguous colours
with no "color" anywhere in the path.

**What counts as an un-flattenable composite.** A `{width} solid {color}`
border shorthand, a multi-layer `box-shadow` string, a bare CSS keyword
(`button.content.alignment`, `"center"`), or an alias pointing at an
already-composite token (`popup.box.shadow` → `{box-shadow.level-3}`).

**Why those are not decomposed.** DTCG has composite `border` and `shadow`
types, and the real shapes parse cleanly enough to build them. Doing so would
replace `$value` with a structured object instead of the source's own string,
breaking the "diffs cleanly against source, line for line" guarantee above.
See `sync-manifest.json`'s `omitted_type_examples` for the current list.

**Known limitation.** Type inference does not generally follow alias chains. A
token whose `$value` is a pure alias does not inherit its target's `$type`
through multiple hops; it is inferred independently. The one exception is the
direct `{color.*}` check above, a single structural hop rather than
chain-walking. In practice both routes land on the same answer, except for the
alias-to-composite cases, which correctly stay untyped either way.

## Verifying the output resolves correctly

The token-file "namespace" a `{alias}` reference resolves into is the source
filename's stem (e.g. `space.tokens.json` → namespace `space`), which is
never repeated as a wrapping key inside the file itself, this is exactly
how Firefox's own build resolves references, and the converted files
preserve it unchanged. `sync.py` builds this namespace-to-file map after every
conversion and walks this chain:

```
components/button.tokens.json  → padding.inline.@base  → "{space.large}"
base/space.tokens.json         → large                 → "{dimension.relative.100}"
base/dimension.tokens.json     → relative.100           → "1rem"
```

This runs automatically at the end of every `sync.py` run and fails the run
(non-zero exit) if it doesn't resolve to `"1rem"`. It's a smoke test, not
exhaustive validation, it proves the converted files are walkable by an
agent or script that only reads `token-api/`, not that every alias in the
corpus resolves (though nothing in the conversion logic is chain-specific,
so there's no reason to expect others to behave differently).

## Files

| File | What it is |
|---|---|
| `sync.py` | The fetch and convert script. Its docstring covers the mechanics; this README covers the why. |
| `sync-manifest.json` | Last run's record: commit, timestamp, counts, `source_paths`, every `$type`-omitted and meta-flagged token, and the verification chain. Overwritten each run. |
| `base/*.tokens.json` | Converted central base tokens, one file per source file, same filenames, `.nova.` variants included. |
| `components/*.tokens.json` | Every component-level file, central and colocated, flattened together by basename. `source_paths` records where each came from. |
| `id-map.json` | Component id to token basename(s), plus the `foundational` list. |
| `schema.json` | The `base/`/`components/` tree as a draft 2020-12 JSON Schema, enforced by `validate-schemas.py`. |
| `resolve.py`, `resolved/*.json` | Pre-resolved export: every `$value` already walked to its literal, so a simple consumer need not reimplement the algorithm. Derived, not a source of truth. |
| `figma-variables-dump.json`, `figma-check.py`, `figma-token-map.json` | The "In Figma" column. The dump is a credential-scoped REST snapshot; `figma-check.py` is pure local computation; the map is what `index.html` fetches. |

**`id-map.json` is hand-maintained, not generated.** Which real component's CSS
consumes which file's custom properties is a judgment call, not something
derivable from the token files themselves.

**`resolved/` has one exception to "walked to its final literal".** A value
holding a reference inside a longer string (`{border.width} solid
{button.border.color.@base}`, or `oklch(from {message-bar.icon.color} l c h /
20%)`) is not substituted. The resolver only walks a value that is entirely
one alias, the same deliberate rule `index.html` follows when printing one.

Each such token carries an `unresolvedRefs` array naming the references still
in its `value`. Without it they were indistinguishable from a plain literal,
since both reported an empty `chain`. A consumer wanting a fully-substituted
string has to do that substitution itself, and `unresolvedRefs` says which
refs to do it for.

## Scope

This pass converts every file across all of `SOURCE_ROOTS` in `sync.py` as
they exist upstream today; see `sync-manifest.json` for the current file
and token counts. It does not touch `component-api/` or `guidance-api/`;
`id-map.json` is maintained by hand alongside this script, not generated
by it (see "Files" above). It does not attempt to decompose composite
values (borders, shadows, gradients) into DTCG's structured composite
types, that's future work. It also does not attempt full cross-component
alias resolution (see "Known limitation" above).
