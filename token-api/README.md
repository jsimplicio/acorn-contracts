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

1. Does a shallow, blobless, sparse-checkout `git clone` of
   `https://github.com/mozilla-firefox/firefox`, restricted to every real
   location a `*.tokens.json` file actually lives (see "Where these files
   really live" below), into a scratch temp directory (deleted automatically
   after the run). This is a real network fetch of the actual upstream repo
   every time, not a copy of some convenient local checkout that happened to
   already exist on this machine.
2. Converts every `*.tokens.json` file found in any of those locations and
   writes one converted file per source file under `token-api/base/` (only
   the central base/ files) or `token-api/components/` (the central
   components/ files, plus every colocated one, flattened by basename), so
   a converted file diffs cleanly against its source, line for line, group
   for group.
3. Overwrites `token-api/sync-manifest.json` with the exact commit fetched,
   fetch timestamp, per-run token/type counts, and the list of tokens where a
   `$type` was deliberately omitted or a non-standard key was preserved (see
   below), so every run is auditable against the last one.
4. Resolves the same `button.padding.inline.@base` → `space.large` →
   `dimension.relative.100` → `1rem` alias chain documented below, as a
   smoke test that the output is genuinely walkable end to end, and fails
   loudly (non-zero exit) if it doesn't resolve to `1rem`.

Useful flags:

- `--ref <branch-or-sha>`: fetch a specific ref instead of the default
  branch tip (e.g. to pin a sync to a known-good commit, or reproduce an old
  one).
- `--local-checkout <path>`: **dev/test only.** Skips the network fetch
  entirely and reads tokens from an existing local firefox checkout instead.
  Prints a loud warning banner and is recorded in the manifest as a bypass.
  This exists purely to make iterating on the converter itself faster; it is
  never the path a real sync should take, and the manifest makes it obvious
  if someone ran it this way by mistake.

## Where these files really live

Firefox's tokens are **not** all under one central directory. The obvious
location, `toolkit/themes/shared/design-system/src/tokens/{base,components}/`,
is the only one most people would think to check. Two more real patterns
also feed real components:

- **Feature-area-owned files**: `browser/themes/shared/tabbrowser/*.tokens.json`
  (tab, tab.nova, tabs-navbar) and `browser/themes/shared/urlbar/*.tokens.json`
  (urlbar, urlbar.nova, urlbarview, urlbarview.nova).
- **Component-colocated files**: several real components under
  `toolkit/content/widgets/` keep their own `*.tokens.json` directly next to
  their `.mjs`/`.css` rather than in the central tree (moz-badge, moz-toggle,
  moz-select, moz-message-bar, moz-page-nav, moz-promo, moz-input-color,
  moz-breadcrumb, moz-segmented-control, moz-reorderable-list,
  moz-visual-picker-item, panel-item, panel-list), plus a shared
  `moz-box.tokens.json` sitting directly in `toolkit/content/widgets/`
  itself (consumed by both moz-box-item and moz-box-group).

All of these are the exact same real Style-Dictionary-flavored format (a
`value` key marks a leaf, same `@base`/theme-object/alias conventions), so
none of the conversion logic below needed to change, only `SOURCE_ROOTS` in
`sync.py` needed to widen. See **`id-map.json`** for how each component
id maps to its real basename(s), since Firefox's own naming frequently
doesn't match the id used in this inventory (`info-bar` vs `infobar`, `toolbarbutton` vs
`toolbar-button`) and a few ids genuinely pull from more than one real file
at once (`panel-item` uses both `panel-menuitem.tokens.json`, shared layout
tokens from the central tree, and its own colocated `panel-item.tokens.json`
for badge/button extras). This is a real, published data file, not just logic living in
`index.html`: an agent reading only `token-api/` can see the exact mapping
without touching `index.html`'s own JavaScript. Schema:

```jsonc
{
  // Loaded unconditionally for every component, since these basenames are
  // referenced by many unrelated component files, so treated as de-facto
  // foundational despite living in components/, not base/.
  "foundational": ["button", "icon"],
  // component id -> real basename(s). A plain array means every basename
  // listed is genuinely this id's own content, displayed as this id's
  // rows. More than one entry means the real component genuinely draws
  // from more than one file (panel-item's own colocated badge/button
  // extras file, for example).
  "map": {
    "panel-item": ["panel-menuitem", "panel-item"],
    // {own, resolve} instead of a plain array when this id's own tokens
    // alias into a basename that ALSO has its own separate id/page
    // elsewhere: "own" is what's displayed as this id's rows, "resolve"
    // is loaded into the lookup so those aliases still resolve, but never
    // displayed here too (button aliases into two of Toolbar Button's
    // tokens; Toolbar Button already has its own page for its own full
    // set, so button's page shows only its own rows, not a second copy).
    "button": { "own": ["button"], "resolve": ["toolbarbutton"] },
    // An "own" entry can also be {basename, onlySegment} instead of a
    // bare string, for when this id's real tokens are a subset of a
    // larger file that ALSO has its own separate id/page: only tokens
    // with that exact segment somewhere in their dotted path are
    // exported (never a substring match). Icon Button is the 6 real
    // button.tokens.json tokens with an exact "icon" segment
    // (button.icon.fill, button.padding.icon, button.size.icon.@base,
    // ...), not the whole file Button's own page already shows.
    "icon-button": { "own": [{ "basename": "button", "onlySegment": "icon" }], "resolve": [] },
    "...": ["..."]
  }
}
```

Why a segment match, not a fixed position: this repo's own real design token
taxonomy (Ecosystem > Domain > Object > Pattern > Component > Element >
Category > Type > Concept > Property > Modifier > Variant > State > Scale,
see acorn.firefox.com's "How design tokens work: taxonomy" page) explicitly
says a token name only includes "enough levels to describe and communicate
[its] intent", not every level every time. That means the same taxonomy
level (e.g. a "Modifier" like `icon`) can land at a different position in
different token names, so anchoring `onlySegment` to a fixed position
(like "right after the basename") would miss real matches. An exact
dotted-path-segment match works regardless of position; a substring match
would not (it would false-positive on any path that happens to contain a
segment's letters without being that segment).

An id with no entry in `map` falls back to trying `<id>.tokens.json`
directly (in case a future sync adds a file that happens to match the
id itself), same fallback `index.html` uses.

**Known limitation:** a component's token file can alias into a *different*
component's own file. `button` and `icon` are covered unconditionally (see
`foundational` above), every real cross-reference into a basename with its
own separate id/page uses `{own, resolve}` as above, and every other real
cross-reference (into a basename with no id/page of its own, e.g. `panel`
including `popup`, since `panel.nova.tokens.json` genuinely aliases into
`{popup.border.radius}`) is listed as a plain extra array entry, since
there's no separate page for it to duplicate against either way. A
reference to some *other* file not covered by any of those would only
resolve while viewing a page that happens to already load that file for
its own reasons; there's no fully general cross-component alias
resolution. Shows up as a `(unresolved)` diagnostic in `index.html` rather
than a silently wrong value, so it's visible when it happens, just not
automatically fixed.

## How to resolve a real token's value

This is the exact algorithm, not a description of what happens to already
be true of `index.html`. Any consumer reading only `token-api/`'s files, no
`index.html`, can reproduce the same resolved values by following it:

1. **Build the shared lookup.** For every file in `base/*.tokens.json`
   (skip `.nova.` ones for now), flatten it into a flat
   `"<basename>.<dotted.path>"` -> token map, keyed by the file's own
   filename stem (`space.tokens.json` -> prefix `space`). Then flatten
   `components/<name>.tokens.json` for every `name` in `id-map.json`'s
   `foundational` list into that same map, same rule (prefix by that file's
   own basename, `button`/`icon`).
1b. **Proton scale steps Nova replaced are already gone.** Firefox ships both
   generations side by side: `color.tokens.json` is the Proton ramp (steps
   0-110, oklch) and `color.nova.tokens.json` is the Nova one (0-90, hex), on
   different scales. Merging them key by key (step 2) does not remove a step
   Nova dropped, it keeps the Proton one, which then lands at the end of a
   scale it does not belong to: `color.gray.100` (#15141a) is visibly
   *lighter* than `color.gray.90` (#121114), and `border.radius.xxlarge`
   was listed when Nova has no such radius. `sync.py` drops those at
   conversion time (`prune_superseded_scale_steps`), so nothing downstream
   has to know about it. Four guards keep it off anything live:

   - **`base/` only.** A component token's real consumer is CSS in
     mozilla-central, not another token, so "nothing aliases it" says
     nothing about whether it is live. Applying this to `components/` would
     delete ~45 real tokens (`moz-toggle.dot.width`, `card.gap.compact`).
   - **Only a group Nova rewrote.** Nova defines no `white`/`black` group at
     all, so those are the only ramp there is and they stay.
   - **Only a flat scale** (every member a leaf). `background.color` holds
     nested groups (`box`, `list`, `dimmed`) so it is never touched;
     `border.radius` is seven flat leaves so it is.
   - **Only a step nothing references under Nova.** Not a raw scan of the
     files: both generations live in the same file, so a blanket scan counts
     a reference that exists only in a superseded Proton definition, which is
     enough to keep a dead token alive forever. A Proton token its own
     `.nova` sibling redefines is skipped, as is the non-nova half of a token
     carrying its own `nova` branch. `color.gray.100` is the worked example:
     a raw scan finds 10 tokens pointing at it, but 8 are Proton definitions
     Nova replaces, leaving 2 real ones (`toolbar.text.color` and
     `table.header.text.color.@base`, neither of which has a Nova
     definition yet).

   19 steps go: `100`/`110` on red, orange, yellow, green, cyan, blue,
   violet, purple and pink, plus `border.radius.xxlarge`. `color.gray.100`
   and `border.radius.circle`/`large` stay, all three still aliased by real
   tokens with no Nova replacement.

2. **Layer Nova on top, in a second pass.** For every `base/*.nova.tokens.json`
   file **and every `components/<name>.nova.tokens.json` for a `name` in
   `foundational`**, flatten it under its **non-nova** stem
   (`border.nova.tokens.json` -> prefix `border`, the same prefix as step 1's
   `border.tokens.json`) and merge into the *same* map, overwriting matching
   keys. The foundational half is easy to miss and silently wrong when
   missed: `icon.color.information` is `{color.blue.60}` in
   `icon.tokens.json` and `{color.violet.50}` in `icon.nova.tokens.json`, so
   skipping it hands every component that resolves through `icon.*` a Proton
   blue where Nova is violet. This has to be a
   second, later pass, not combined with step 1: a nova file and its
   non-nova sibling write the same keys, so if both were merged in one
   pass with no ordering guarantee, which one "wins" would depend on fetch
   timing, not on Nova actually being the intended winner.
2b. **A `moz-*` file also registers under its unprefixed name.** Firefox's
   own files refer to these components without the prefix:
   `moz-message-bar.tokens.json` contains
   `oklch(from {message-bar.icon.color} l c h / 20%)` and
   `moz-toggle.tokens.json` aliases `{toggle.dot.height}`. That is the same
   convention the generated CSS custom property names follow (`moz-select`
   -> `--select-*`). Flatten such a file a second time under the bare name
   and merge those keys into the lookup too, or those aliases resolve to
   nothing. Lookup only: a token's own displayed/exported path keeps the
   file's real basename.

3. **Add the component's own files.** Look up the id in `id-map.json`'s
   `map` (fall back to `[id]` if absent). For each basename in that list,
   flatten `components/<basename>.tokens.json` under its own basename and
   merge into the map (still step-1-style, non-nova first), then flatten
   `components/<basename>.nova.tokens.json` the same way and merge on top
   (Nova wins, same reason as step 2).
4. **Resolve a value.** Given a token's `$value`: if it's not a string
   matching `^\{([^{}]+)\}$`, that literal value (or object, for a
   theme-dimension-keyed token, see below) is the answer. If it does match,
   look up the captured path in the merged map from steps 1-3 and repeat
   this step on *that* token's `$value`, tracking each hop. If a path
   isn't in the map, stop and report it unresolved (don't guess); a real
   depth cap (12) guards against an accidental cycle, never expected to
   trigger on real data.
4b. **A `nova` branch wins over `$value`.** 38 tokens carry a
   `$extensions["org.mozilla.themes"].nova` branch, shaped
   `{comment?, value}`, where `value` is a literal or another theme object
   with its own `light`/`dark`. That branch is the real Nova value and
   `$value` is the Proton one `pick_default` surfaced, so it has to win
   wherever it exists. `text.color.@base` is the clearest case: `$value` is
   `{color.gray.100}`, a Proton grey, while its Nova value is
   `{color.violet-desaturated.90}` light / `{color.violet-desaturated.0}`
   dark. Resolving `$value` alone silently shows Proton.

5. **Theme-dimension values.** If a token's `$value` is itself an object
   (not a string), it's already been reduced by `sync.py` to the single
   most-typical branch per `DEFAULT_PICK_ORDER` above; the full original
   set of theme branches is preserved losslessly under
   `$extensions["org.mozilla.themes"]` if a consumer needs a *different*
   theme's value specifically.

## Figma existence check: figma-check.py

Every component page's "Design tokens" table (built by `index.html`'s
`buildCssPropertyRows()`/`renderCssPropertyTable()`) has a 4th column, "In
Figma": does this row's own CSS custom property name also exist as a real
variable in Mozilla's actual "Nova Styles (Experimental)" Figma file (key
`Co6vXnF5SiQMcJ7UoJvZX6`)? This is that same "verify with real evidence"
discipline `AGENTS.md`'s "Verify figma/supernova with real evidence" section
uses for `component-api/`'s own `figma`/`supernova` fields, applied one level
down, at the individual token/CSS custom property level instead of the
whole-component level.

**Source is the direct Figma REST API, not Supernova.** An earlier version
of this check matched against a Supernova MCP token-list snapshot instead.
The repo maintainer rejected that as the wrong source for this kind of
check: Supernova's sync of this design system has known gaps elsewhere in
this project family (its own token detail reported its source file as
`Desktop Styles` and there was no way to independently confirm that was even
the same file as `Nova Styles`). The rule for this whole project family is
now: a token/variable-existence-in-Figma check always hits the Figma REST
API directly, never Supernova. `Co6vXnF5SiQMcJ7UoJvZX6` is confirmed as the
right file by cross-reference, not assumption: it's the exact file and
endpoint (`GET /v1/files/{FILE_ID}/variables/local`) the sibling
`ai-native-ux-hub` repo's `prototype/design-system/scripts/gen_tokens_css.py`
already pulls from to generate that project's own `tokens.css`.

**codeSyntax was checked first, not assumed useless**, same discipline as
the earlier Supernova-based pass, just re-verified against the new source
rather than carried over as an assumption. This direct Figma API response
DOES include a `codeSyntax` field per variable (Supernova's schema didn't
expose one at all) -- but only 2 of the 718 kept variables in the file have
it populated (`button/background/color`, `tab/border/color`; see
`figma-variables-dump.json`'s `_comment`), nowhere near enough of the file
to be a general match signal. Matching is still by normalized name instead
(below). If a future Figma publish starts populating `codeSyntax` broadly,
that should become the primary signal and this file should say so
explicitly, not silently keep using name matching once a better one exists.

**The pipeline, three files:**

1. `figma-variables-dump.json`: every real variable in the "Nova Styles
   (Experimental)" file, fetched with one REST call:

   ```sh
   set -a && source prototype/design-system/.env && set +a  # in ai-native-ux-hub, for FIGMA_TOKEN
   curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
     "https://api.figma.com/v1/files/Co6vXnF5SiQMcJ7UoJvZX6/variables/local" \
     -o /tmp/figma-variables-raw.json
   ```

   Unlike the Supernova snapshot it replaces, this **is** a standalone,
   credential-scoped, fully rerunnable fetch, the same way `sync.py`'s git
   clone is: no agent session or MCP connection needed, just a Figma
   personal access token (this repo has none of its own; the token used to
   build the current dump lives in the sibling `ai-native-ux-hub` repo's
   `prototype/design-system/.env`, read there once and never written to this
   repo). See the file's own leading `_comment` for the exact endpoint,
   what's kept per variable (`name`, `type`, `collection`, `remote`; values,
   modes, and aliasing are dropped since matching is purely name-based), and
   what's excluded (2 of the file's 720 raw variables are Figma's own
   `deletedButReferenced` ghosts and don't count as "exists in Figma").
2. `figma-check.py`: pure local computation, no network. Builds the exact
   same universe of distinct CSS custom property names `index.html`'s own
   `buildCssPropertyRows()` would show as rows across EVERY component page
   (token-backed names from `resolved/*.json`, plus documented-but-not-
   necessarily-token-backed names from every `component-api/*.json`'s
   `cssProperties`), normalizes each one and every real Figma variable name
   in `figma-variables-dump.json` down to a plain tuple of lowercase words
   (splitting on every non-alphanumeric character, so an acorn-contracts
   basename's own internal hyphen, like `box-shadow`, collides correctly
   with Figma nesting the same two words as separate path segments,
   `box / shadow`, instead of needing a hard-coded list of which basenames
   are "really" two words), and compares:
   - **exact match** (same words, same order) -> `yes`
   - **reordered match** (same words, different order) -> `yes`, flagged
     `matchType: "reordered"` so a maintainer can tell an exact hit from a
     looser one. Real precedent for this in the taxonomy itself (see "Why a
     segment match, not a fixed position" above): the same taxonomy level
     can land at a different position in different token names.
   - anything else -> `no`, a strict two-state result, not three. This
     includes a **near-miss** (one tuple is the other's word set plus or
     minus exactly one word, e.g. `--box-button-background-color` vs. the
     real `button/background/color/menu` variable): an earlier version
     gave this its own third state, `ambiguous`. The repo maintainer
     rejected that: "if it doesn't match something we see in figma/the
     import file then it doesn't exist... that's the goal, are these
     syncing." A near miss is still not a match, and hedging on it hides
     the exact drift this check exists to surface. It's recorded as `no`
     with `matchType: "near-miss"` and a `matchedPath` (the close-but-not-
     matching variable) purely as a diagnostic -- useful for spotting a
     systematic gap (e.g. every `--tab-group-*-invert` name misses on the
     same word, "invert", across an entire family), never treated as a
     softer status than a total mismatch. This and the common, expected
     outcome of entire component families this Figma file doesn't cover at
     all (no urlbar/panel/toolbar/sidebar/checkbox/moz-* semantic *color*
     groups were found in it, only some of their Dimension-type
     size/spacing tokens) are the two flavors of `no`, not a bug in the
     matching.

   Rerun any time `resolved/*.json`, `component-api/*.json`, or
   `figma-variables-dump.json` change:

   ```sh
   python3 token-api/figma-check.py
   ```

3. `figma-token-map.json`: the output, `{"--custom-property-name": {status,
   matchType, matchedPath}}` for every distinct name plus a `counts`
   summary. This is what `index.html` actually fetches at render time (see
   `loadFigmaTokenMap()`); it is a baked lookup file, not a live query,
   since `index.html` is a static page with no server-side code, the same
   reason `id-map.json` and `sync-manifest.json` are files instead of
   inline logic. Schema is unchanged from the Supernova-sourced version, so
   `index.html`'s consumption of it needed no changes when the source
   underneath it swapped.

**Recomputed from scratch against a fuller universe, not assumed to match
the old counts.** The direct Figma pull covers 718 real variables (after
excluding the 2 `deletedButReferenced` ghosts) across every collection in
the file, versus 269 tokens in the old Supernova snapshot, so the counts
moved a lot, not just at the margins: 324 exact + 11 reordered = 335 `yes`
(was 103 + 5 = 108), 305 `no` (was 424, before folding `ambiguous` in --
see below), out of the same 640 distinct CSS custom property names. Treat
the higher `yes` count as the direct pull finding real coverage the
Supernova snapshot missed, not as the matching rule having gotten looser
(the rule itself is unchanged; see
`figma-check.py`'s own docstring).

**Why this doesn't follow alias chains.** A tempting way to shrink the
`ambiguous`/`no` buckets: `resolve.py` already recorded every token's real
alias chain in `resolved/*.json` (e.g. `--box-button-background-color`'s
value resolves through `button.background.color.menu.@base`), so checking
whether any hop of that chain matches a Figma variable turns a lot of
near-misses into a "yes." This was tried and explicitly rejected by the repo
maintainer: the point of this column is to catch Figma and code drifting
apart, and counting a match through a differently-named variable an
indirect alias happens to touch hides exactly the drift this check exists
to surface. `--box-button-background-color` not having its own matching
Figma variable is the real, correct finding, even though its value is
reachable through `button/background/color/menu` under the hood -- that's a
different question (does this value trace back to Figma at all) from the
one this column answers (does Figma and code agree on this name). Keep this
script comparing a name to its own name only.

**Why `ambiguous` got folded into `no`.** A separate, earlier decision (not
the alias-chain one above) gave a one-word-off near miss its own third
status, reasoning that it was too close to call either way. Also rejected,
for the same underlying principle: "if it doesn't match something we see in
figma/the import file then it doesn't exist... that's the goal, are these
syncing." A near miss is real signal that the name has drifted, not an
unresolved maybe -- it's recorded as `no` with `matchType: "near-miss"` so
the close call is still visible in the data and in each row's tooltip, but
it never renders as anything other than `&cross;`.

**Spot-checked, not blindly trusted**: a handful of matches (`badge/*`,
`button/background/color/*`, `border/color/interactive*`, `focus/outline*`,
`text/color*`, `box/shadow/level-*`) were independently verified by reading
the actual `token-api/base/*.tokens.json` and `token-api/components/*.tokens.json`
source for those paths and confirming the real token structure justifies the
match, not just the string comparison. The initial version of this script
had a real bug (it derived `--moz-badge-background-color` instead of the
correct `--badge-background-color`, missing `deriveCssVarName()`'s "moz-"
stripping rule) caught exactly this way, by cross-checking the script's own
output against the live-rendered page in a browser.

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
- **`.nova.tokens.json` files** are a second, orthogonal axis: Firefox's
  build supports whole override files, one per "override identifier"
  (currently only `nova`, gated behind the `browser.nova.enabled` pref, see
  `config/override-identifiers.js` upstream), which redefine a subset of
  tokens with alternate values. They're structurally identical
  `*.tokens.json` files, just consumed differently at build time (as a
  `@media -moz-pref(...)` override layer rather than the base cascade).
  These are genuinely part of `base/*.tokens.json` and
  `components/*.tokens.json`, so this sync includes them, converting and
  naming them exactly like their non-`.nova` counterparts (e.g.
  `color.nova.tokens.json` next to `color.tokens.json`) so they stay
  independently diffable against source.
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
4. **Theme-dimension-keyed values** get a single representative `$value` at
   the top level, plus the complete original object preserved losslessly
   under `$extensions["org.mozilla.themes"]`. Every `forcedColors`/`brand`/
   `nativeTheme`/`platform`/`light`/`dark`/`prefersContrast` variant that
   exists in the source is still present, verbatim, in the output, nothing
   is dropped, only "flattened" for the top-level `$value` convenience. The
   picking rule, in priority order: an explicit `default` key if present,
   else recurse into `brand` (itself often `{default: ...}`), else `light`,
   else `nativeTheme`, else `forcedColors`, else recurse into `platform`,
   else `prefersContrast`, else `dark`, else (last resort) whatever key is
   left. Implemented in `sync.py`'s `pick_default()` and
   `DEFAULT_PICK_ORDER`. `default` beats `brand` deliberately: a token that
   states an explicit default is telling you that value applies regardless
   of brand/platform, which is a stronger and more literal signal than
   "whatever `brand` happens to be."
5. **`"override": true`** and any other non-`value`/`comment` sibling key
   found on a leaf is preserved verbatim under
   `$extensions["org.mozilla.meta"]`, so it isn't silently lost even though
   DTCG has no first-class slot for it.
6. **`$type` is inferred first from the value's own shape, then from the
   token's own group path**, not guessed per-value:
   - the value itself is a literal color function/hex (`rgb(`, `rgba(`,
     `hsl(`, `hsla(`, `oklch(`, `oklab(`, `lab(`, `lch(`, `color-mix(`, or a
     `#`-prefixed hex triple), or a pure `{alias}` reference whose first path
     segment is literally `color` (e.g. `{color.blue.50}`) → `color`. This
     catches real tokens like `tab.selected.textcolor`, whose own path never
     spells out "color", "fill", or "stroke" at all, but whose value is
     unambiguous.
   - failing that, path contains `color`, `fill`, or `stroke` → `color` (the
     latter two are a deliberate extension beyond a literal "color" keyword:
     Firefox has tokens like `button.icon.fill`/`button.icon.stroke` whose
     values are unambiguously colors but whose path never spells out
     "color")
   - `font` + `weight` in path → `fontWeight`; `font` + `family` → `fontFamily`
   - `opacity` in path → `number`
   - path contains any of `space`/`dimension`/`padding`/`gap`/`size`/`radius`/
     `width`/`height`/`min-height`/`min-width`/`max-width`/`inset`/`offset`/
     `margin` → `dimension`
   - **omitted entirely**, and logged, when none of the above apply, or when
     the value is a composite string DTCG doesn't sanction flattening into a
     scalar type, specifically: a full `{width} solid {color}` border
     shorthand (DTCG has a composite `border` type with `{width, style,
     color}` sub-fields, but the source stores this as one flat string, not
     decomposed, so forcing `$type: "border"` on a bare string would be
     wrong), and multi-layer `box-shadow` strings (same issue, DTCG's
     `shadow` type expects structured layers, not a flat comma-joined
     string). Decomposing either into real DTCG composite objects is
     possible (the real shapes are consistent enough to parse: border is
     always exactly `<width> solid <color>`, shadow layers are comma-
     separated with the color always last) but was deliberately not done
     here, since it would mean replacing `$value` with a structured object
     instead of the original string, breaking the explicit "diffs cleanly
     against source, line for line" guarantee above. This category also
     covers a bare CSS keyword with no DTCG type at all
     (`button.content.alignment`, `"center"`; `card.cover.image.object.fit`,
     `"cover"`) and an alias that points *at* an already-composite token
     (e.g. `popup.box.shadow` → `{box-shadow.level-3}`). See
     `sync-manifest.json`'s `omitted_type_examples` for the current list.
   - **Known limitation:** type inference does not generally follow alias
     chains. A token whose `$value` is a pure alias to another token doesn't
     inherit that target's `$type` from a multi-hop chain, it's inferred
     independently (the one deliberate exception is the direct
     `{color.*}` check above, a single, structural hop, not chain-walking).
     In practice this lands on the same answer either way, except for the
     alias-to-composite cases just above, which correctly stay untyped
     either way since their target is itself undecomposed.

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

- `sync.py`: the fetch + convert script, rerun any time upstream tokens
  change. Read its docstring for the mechanics; this README covers the *why*
  behind each rule.
- `sync-manifest.json`: output of the last run: exact commit fetched, fetch
  timestamp, per-file/type counts, `source_paths` (each output file's real
  upstream path, since output no longer mirrors one single source tree), the
  full list of `$type`-omitted and `$extensions.org.mozilla.meta`-flagged
  tokens, and the verification chain result. Overwritten every run, check it
  after rerunning to see what changed upstream.
- `base/*.tokens.json`: the converted central base tokens (colors, space,
  dimension, ...), one file per upstream source file, same filenames
  (`.nova.` variants included).
- `components/*.tokens.json`: every converted component-level token file,
  central AND colocated flattened together by basename (guaranteed not to
  collide), same filenames as their real source. See `sync-manifest.json`'s
  `source_paths` for exactly where each
  one really came from, and `id-map.json` for how a component id maps
  to its real basename(s).
- `id-map.json`: real, published mapping from component id to real
  token basename(s), plus the small `foundational` list (see "Where these
  files really live" above for the schema). Maintained by hand alongside
  this script, not generated, since the id-to-file mapping requires a
  judgment call (which real component's CSS actually consumes which file's
  custom properties) that isn't mechanically derivable from the token files
  themselves.
- `schema.json`: `base/`/`components/`'s DTCG-shaped tree as a real,
  machine-checkable JSON Schema (draft 2020-12), not just this README's
  prose. Validated against real data, and confirmed to reject a malformed
  leaf.
- `resolve.py` / `resolved/*.json`: a pre-resolved export, every real
  token's `$value` already walked to its final literal (see "How to resolve
  a real token's value" above) so a simple consumer doesn't have to
  reimplement that algorithm just to get an answer. `base/`, `components/`,
  and `id-map.json` remain the real source of truth; this is a derived
  convenience, re-run `python3 token-api/resolve.py` any time those change.
  Cross-checked against `index.html`'s own live-rendered values before being
  trusted, and kept in sync the same way after any change to the algorithm.
- `figma-variables-dump.json` / `figma-check.py` / `figma-token-map.json`:
  the "In Figma" column on every component page's Design tokens table (see
  "Figma existence check" above for the full pipeline and matching rule).
  `figma-variables-dump.json` is a direct Figma REST API snapshot (`GET
  /v1/files/Co6vXnF5SiQMcJ7UoJvZX6/variables/local`), a real credential-
  scoped rerunnable fetch, no agent/MCP session needed; `figma-check.py` is
  pure local computation, re-run any time `resolved/*.json`,
  `component-api/*.json`, or the dump change; `figma-token-map.json` is
  what `index.html` actually fetches.

## Scope

This pass converts every file across all of `SOURCE_ROOTS` in `sync.py` as
they exist upstream today; see `sync-manifest.json` for the current file
and token counts. It does not touch `component-api/` or `guidance-api/`;
`id-map.json` is maintained by hand alongside this script, not generated
by it (see "Files" above). It does not attempt to decompose composite
values (borders, shadows, gradients) into DTCG's structured composite
types, that's future work. It also does not attempt full cross-component
alias resolution (see "Known limitation" above).
