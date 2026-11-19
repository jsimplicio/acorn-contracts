# Token API

Firefox's real design tokens, converted from their native Style Dictionary format into the [W3C Design Tokens Community Group (DTCG)](https://tr.designtokens.org/format/) format (`$value`/`$type`/`$description`). Where `component-api/` and `guidance-api/` describe *components*, this describes the *design tokens* they are built from.

Nothing here is hand-copied: `sync.py` fetches straight from `https://github.com/mozilla-firefox/firefox`. How to rerun it, and how the conversion works inside, is on the [Maintaining](../MAINTAINING.md) page.

## Reading the files

- **`base/`** holds the central base tokens and **`components/`** every component-level file, one converted file per upstream source file, same filenames. `.nova.` variants are separate files named like their non-nova counterparts.
- **A token is any object with a `$value`.** An alias is the curly-brace dot path `{group.token}`, resolved against the namespace of the file it points into: the source file's stem (`space.tokens.json` → `space`), never a wrapping key inside the file.
- **`.@base`** is the default child of a group that also has named siblings, a Style Dictionary workaround (`--font-weight` and `--font-weight-semibold` cannot both exist otherwise). References keep it literally, so every alias is a directly walkable JSON path.
- **`$value` is one picked branch when the source had several.** A token whose upstream value was keyed by theme (`light`, `dark`, `forcedColors`, `prefersContrast`, `nativeTheme`, `platform`, `brand`, `default`) keeps the complete original object under `$extensions["org.mozilla.themes"]`. Read that, not `$value`, for anything theme-dependent.
- **A `nova` branch is the real Nova value.** Where `$extensions["org.mozilla.themes"].nova` exists, shaped `{comment?, value}`, it wins over `$value` (see the resolve algorithm below).
- **`$extensions["org.mozilla.meta"]`** keeps any other non-standard key verbatim, such as upstream's per-token `"override": true`.
- **`$description`** is upstream's `comment`.
- **`$type` is inferred** from the value's shape, then its path. Composite values (border shorthands, multi-layer shadows, bare keywords) stay plain strings and untyped. The full inference table is on Maintaining.

## `id-map.json`

Which token files belong to which component. Firefox's naming often differs from the ids here (`info-bar` vs `infobar`, `toolbarbutton` vs `toolbar-button`), one component can draw from several files, and one file can be shared by several components. Published data rather than logic inside `index.html`, so a consumer reading only `token-api/` can see the mapping. It is hand-maintained: which component's CSS consumes which file's custom properties is a judgment call. `manifest.json` publishes the same link per component as `tokenBasenames`.

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

**`foundational`** is loaded for every component, because these basenames are referenced by many unrelated files. They live in `components/` but behave as base tokens.

| Shape under `map` | Means |
|---|---|
| `["a", "b"]` | Every basename listed is this id's own content and is displayed as its rows. |
| `{ "own": [...], "resolve": [...] }` | `own` is displayed; `resolve` is loaded so aliases resolve but is never shown. For when this id aliases into a basename that has its own page: `button` aliases into Toolbar Button's tokens. |
| `{ "basename": "x", "onlySegment": "y" }` | Inside `own`: only the tokens with that exact dotted-path segment. Icon Button is the `button.tokens.json` tokens with an `icon` segment. |
| `{ "basename": "x", "excludeSegments": ["y"] }` | Inside `own`: every token except those with any of these segments, for the other component sharing the file. Tab excludes `group`, which Tab Group takes with `onlySegment`. |

A segment match is exact and position-independent: the token taxonomy only includes the levels a name needs, so the same level lands at different positions in different names, and a substring match would false-positive.

**Fallback.** An id with no entry in `map` tries `<id>.tokens.json` directly, the same fallback `index.html` uses.

**Cross-component aliases** resolve in three cases: `button` and `icon` always (via `foundational`), a basename with its own page via `resolve`, and a basename with no page of its own as a plain extra entry (`panel` lists `popup`). Anything else shows as `(unresolved)` rather than a silently wrong value.

## How to resolve a real token's value

The exact algorithm, so a consumer reading only `token-api/` can reproduce the site's values. `resolved/*.json` is this already done.

1. **Build the shared lookup.** Flatten every non-`.nova.` `base/*.tokens.json` into a `"<basename>.<dotted.path>"` map keyed by each file's stem, then the `foundational` files from `components/` the same way.
2. **Layer Nova on top, in a separate, later pass.** Flatten every `base/*.nova.tokens.json`, and every `components/<name>.nova.tokens.json` for a `foundational` name, under its **non-nova** stem, overwriting matching keys.
3. **Add the component's own files.** Look up the id in `id-map.json`'s `map` (fall back to `[id]`). For each basename, merge `<basename>.tokens.json`, then `<basename>.nova.tokens.json` on top.
4. **Resolve a value.** Take the token's `nova` branch if it has one, else `$value`. If it matches `^\{([^{}]+)\}$`, look the path up and repeat, taking the `nova` branch at every hop. Anything else is the answer.

> **Warning** Step 2 has to be its own pass. A nova file and its non-nova sibling write the same keys, so merging both in one pass leaves the winner depending on fetch order.

> **Warning** Don't skip the foundational half of step 2. `icon.color.information` is `{color.blue.60}` in `icon.tokens.json` and `{color.violet.50}` in `icon.nova.tokens.json`, so skipping it hands every component resolving through `icon.*` a Proton blue where Nova is violet.

> **Warning** Resolving `$value` alone silently shows Proton wherever a `nova` branch exists. `text.color.@base` is `{color.gray.100}`, a Proton grey, in `$value`, and `{color.violet-desaturated.90}` light / `{color.violet-desaturated.0}` dark in its Nova branch.

> **Note** A `moz-*` file also registers under its unprefixed name, because Firefox's own files refer to these components without the prefix (`moz-message-bar.tokens.json` contains `oklch(from {message-bar.icon.color} l c h / 20%)`). Flatten such a file a second time under the bare name for lookup only; the exported path keeps the real basename.

> **Note** A path missing from the map is reported unresolved rather than guessed, and a depth cap of 12 guards against a cycle.

Proton scale steps that Nova replaced are already removed at conversion, so a scale holds only steps that belong to it (see Maintaining).

## Light and dark

Values resolve for one theme at a time; the site's theme toggle re-resolves the whole page rather than swapping a stylesheet. A token's theme values live in `$extensions["org.mozilla.themes"]` as `light` and `dark` alongside `nativeTheme`, `forcedColors` and `prefersContrast`; `$value` is the fallback when a token has no themes block.

A value can change in dark mode three ways, and only the first is visible in the token's own definition:

1. **It declares its own `dark`.** `color.accent.primary.@base` is `{color.violet.50}` light and `{color.violet.30}` dark.
2. **It aliases something that does.** Resolution has to take the dark branch at *every* hop, or the last hop hands back a light value.
3. **Its value is relative to `currentColor`.** `text.color.deemphasized` is `color-mix(in srgb, currentColor 69%, transparent)`, the same string in both themes, rendering from whatever text colour is in force.

So "does this change in dark mode" can only be answered by a fully resolved value per theme. Primitives (`color.blue.50`, `space.small`, every `font.*` and `size.*`) have no theme variance; the semantic layer above them is where light and dark diverge.

## The "In Figma" column

Every component page and every base token page answers one narrow question per row: does this CSS custom property name also exist as a variable in Mozilla's "Nova Styles (Experimental)" Figma file? A name-vs-name existence check, not "can this value be traced back to Figma".

**Always the Figma REST API directly, never Supernova**, a standing rule for this project family: Supernova's sync of this design system has known gaps.

| Names compared as lowercase word tuples | Result |
| --- | --- |
| same words, same order | `yes` |
| same words, different order | `yes`, `matchType: "reordered"` |
| anything else | `no` |

- **Strictly two states.** A near miss (one word off) is still `no`, recorded with `matchType: "near-miss"` and the close variable in `matchedPath` as a diagnostic only. Hedging on it would hide the drift this check exists to surface.
- **No alias-chain following.** `--box-button-background-color` is `no` even though it resolves through `button/background/color/menu`: a match through a differently-named variable answers a different question.
- **`ignoreFigma` is a caveat, not a status.** A token that upstream marks `$extensions["org.mozilla.meta"].ignoreFigma` keeps its real `yes`/`no` and carries the reason as `valueCaveat`, shown in the cell's tooltip. These are the tokens whose value cannot round-trip to Figma; the [FAQ](../FAQ.md) explains why.
- **Two kinds of `no` are expected:** near misses, and whole component families this Figma file does not cover (urlbar, panel, toolbar, sidebar, checkbox and most `moz-*` semantic colour groups).

`figma-token-map.json`'s `counts` block has the current totals. How to regenerate the column is on Maintaining.

## Files

| File | What it is |
|---|---|
| `base/*.tokens.json` | Converted central base tokens, `.nova.` variants included. |
| `components/*.tokens.json` | Every component-level file, central and colocated, by basename. `sync-manifest.json`'s `source_paths` records where each came from. |
| `id-map.json` | Component id to token basename(s), plus the `foundational` list. |
| `resolve.py`, `resolved/*.json` | Pre-resolved export: every value already walked to its literal. Derived, not a source of truth. |
| `sync.py` | The fetch and convert script. |
| `sync-manifest.json` | Last sync's record: commit, timestamp, counts, `source_paths`, every `$type`-omitted and meta-flagged token. |
| `sync-report.py` | Writes a gitignored `sync-report.html` of every token change since the last commit; while it exists, the local site's nav shows it as "Last sync report". |
| `schema.json` | The `base/`/`components/` tree as a draft 2020-12 JSON Schema, enforced by `validate-schemas.py`. |
| `figma-variables-dump.json`, `figma-dump.py`, `figma-check.py`, `figma-token-map.json` | The "In Figma" column: a REST snapshot of the Figma file, the script that converts the raw response into it, the local matcher, and the map the site fetches. |

**`resolved/` leaves embedded references alone.** A value holding a reference inside a longer string (`{border.width} solid {button.border.color.@base}`) is not substituted; only a value that is entirely one alias is walked. Each such token carries an `unresolvedRefs` array naming the references still in its `value`, so a consumer wanting a fully substituted string knows which to replace.

**Not covered:** composite values are not decomposed into DTCG's structured `border`/`shadow` types, and there is no general cross-component alias resolution beyond `id-map.json`.
