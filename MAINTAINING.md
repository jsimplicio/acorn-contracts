# Maintaining

How to keep this repo's data current: rerunning the syncs, regenerating what is derived, and the internals that only matter when one of those breaks. If you only want to read the data, the three API pages are enough.

## Keeping it current

Several checked-in files are derived from others, and **no sync regenerates them for you.** The order matters, because each step reads the previous step's output:

```sh
python3 token-api/sync.py         # 1. fetch + convert real upstream tokens (network)
python3 token-api/resolve.py      # 2. re-resolve: sync.py just rewrote its inputs
python3 token-api/figma-check.py  # 3. re-check names: resolved/ and base/ moved
python3 build-manifest.py         # 4. token basenames may have changed
python3 build-search-index.py     # 5. any of the above, or any README edit, feeds this
```

`update-meta.py` is the one exception to the order: it reads this repo's own git history, so it runs *after* committing a change to `component-api/` or `guidance-api/`, not before.

`component-api/figma-check.py` is a second exception: it runs on its own schedule, not as part of this chain. Re-run it whenever `component-api/figma-components-dump.json` gets re-pulled (see `component-api/README.md`), and pass `--advance` only once its diff has actually been triaged.

**Steps 2-5 are the easy half to forget, and forgetting them is silent.** A stale derived file still validates against its schema and still looks plausible. Each derived file therefore has a CI guard in `.github/workflows/check-derived.yml`. Treat that as the backstop, not the reminder: run the chain locally and CI has nothing to say.

**`component-api/` has no sync at all, deliberately.** `check-drift.py` reports which tracked components' real source moved and which real widgets have no entry yet; writing an actual `<id>.json` still means reading real upstream source (see `component-api/README.md`). A plain run is read-only and safe to repeat. `--advance` stores this run's hashes as the new baseline, recording every finding as checked whether or not anyone acted on it, so pass it only once the findings are triaged, and pin it with `--ref` to the commit you triaged. `AGENTS.md` has the triage procedure.

**`--ref <branch-or-sha>`** pins `sync.py` or `check-drift.py` to a specific upstream commit rather than the default branch tip, for reproducing an old sync or holding one steady.

## Token sync

```sh
python3 token-api/sync.py
```

Every run:

1. **Clone.** A shallow, blobless, sparse checkout of `mozilla-firefox/firefox` into a temp directory, restricted to the locations below and deleted afterwards. A real network fetch every time, never a local checkout that happens to already exist.
2. **Convert.** One output file per source file, under `base/` or `components/`, so a converted file diffs cleanly against its source line for line.
3. **Record.** `sync-manifest.json` gets the commit fetched, the timestamp, per-run counts, and every token where a `$type` was omitted or a non-standard key preserved. Each run is auditable against the last.
4. **Verify.** Resolves one known chain as a smoke test and exits non-zero if it does not (see "Smoke test" below).

| Flag | Effect |
|---|---|
| `--ref <branch-or-sha>` | Fetch a specific ref instead of the default branch tip, to pin a sync or reproduce an old one. |
| `--local-checkout <path>` | **Dev only.** Skips the fetch and reads a local firefox checkout. Prints a warning banner and records the bypass in the manifest, so a run this way is obvious afterwards. |

After `resolve.py` and `figma-check.py`, and before committing, `python3 token-api/sync-report.py --open` writes a gitignored page of every token change since the last commit, field by field. While it exists, the local site's nav shows it as "Last sync report"; the published site never has it.

### Where the sources live

Firefox's tokens are **not** all in one place. The central set is under `toolkit/themes/shared/design-system/src/tokens/{base,components}/`. Three other patterns feed real components, all in the same format, so only `SOURCE_ROOTS` in `sync.py` widens for a new location.

| Also in | Holds |
|---|---|
| `browser/themes/shared/tabbrowser/` | tab, tab.nova, tabs-navbar |
| `browser/themes/shared/urlbar/` | urlbar, urlbar.nova, urlbarview, urlbarview.nova |
| `toolkit/content/widgets/<component>/` | components keeping tokens beside their own `.mjs` |
| `toolkit/content/widgets/moz-box.tokens.json` | shared by moz-box-item and moz-box-group |

### Source format

Every file above feeds a [Style Dictionary](https://amzn.github.io/style-dictionary/) build; upstream's `toolkit/themes/shared/design-system/docs/README.design-tokens.stories.md` is the authoritative explanation. The parts that matter for the converter:

- **A leaf is any object with a `value` key**; everything else is a nesting group. DTCG's `$value` distinguishes a token from a group the same way.
- **Theme-dimension values.** A `value` is sometimes an object keyed by `forcedColors` / `brand` / `nativeTheme` / `platform` / `prefersContrast` / `light` / `dark` / `default`, one value per context. Common: grep the converted files for `org.mozilla.themes` to see how common.
- **`.nova.tokens.json` files** are whole override files for the `nova` override identifier (gated behind `browser.nova.enabled`, see `config/override-identifiers.js` upstream), redefining a subset of tokens. Consumed at build time as a `@media -moz-pref(...)` layer rather than the base cascade.
- **`"override": true`** is a separate, per-token flag, unrelated to `.nova` files. Per upstream's `config/tokens-config.js` it excludes a token from the main build, Storybook and stylelint token tables.
- **`comment`** is a human annotation beside `value`, not consumed by the build. One case (`font.tokens.json`'s `size.small`) nests a `comment` inside a theme-dimension object instead; that one rides along inside `$extensions` rather than becoming `$description`.

### Conversion rules

1. **`value` → `$value`, `comment` → `$description`**, for a leaf whose `value` is a literal or a single `{alias}`.
2. **Group structure is preserved exactly**, so a converted file diffs against its source by eye.
3. **Aliases keep Firefox's `{group.token}` syntax, `.@base` included.** Dropping `.@base` would make a reference ambiguous with the group itself when the group also has named siblings (`button.background.color` has `@base`, `hover`, `disabled`, `primary`, ...).
4. **Theme-dimension values** get one representative `$value`, chosen by `pick_default()` / `DEFAULT_PICK_ORDER`: `default`, then `brand`, `light`, `nativeTheme`, `forcedColors`, `platform`, `prefersContrast`, `dark`, then whatever key is left. The complete original object goes under `$extensions["org.mozilla.themes"]`. `default` beats `brand` because a token stating an explicit default says it applies regardless of brand.
5. **`"override": true`** and any other non-`value`/`comment` key on a leaf is kept verbatim under `$extensions["org.mozilla.meta"]`.
6. **`$type` is inferred, never guessed per value.** The value's shape is tested first, then the path:

| Test, in order | `$type` |
|---|---|
| Value is a literal colour function (`rgb(`, `rgba(`, `hsl(`, `hsla(`, `oklch(`, `oklab(`, `lab(`, `lch(`, `color-mix(`) or a `#` hex triple, or an alias whose first path segment is `color` | `color` |
| Path contains `color`, `fill` or `stroke` | `color` |
| Path contains `font` plus `weight`, or `font` plus `family` | `fontWeight`, `fontFamily` |
| Path contains `opacity` | `number` |
| Path contains `space`, `dimension`, `padding`, `gap`, `size`, `radius`, `width`, `height`, `min-height`, `min-width`, `max-width`, `inset`, `offset` or `margin` | `dimension` |
| Nothing matches, or the value is a composite that cannot flatten to a scalar | omitted, and logged |

Testing the value first catches tokens like `tab.selected.textcolor`, whose path never says "color". `fill` and `stroke` count because `button.icon.fill` and `button.icon.stroke` are colours with no "color" in the path.

**Composites are left as strings.** A `{width} solid {color}` border shorthand, a multi-layer `box-shadow`, a bare keyword (`button.content.alignment`, `"center"`), or an alias to one of those. DTCG has composite `border` and `shadow` types, but building them would replace the source's own string and break the line-for-line diff. `sync-manifest.json`'s `omitted_type_examples` lists the current ones.

**Type inference does not follow alias chains**, apart from the single `{color.*}` hop above. In practice both routes land on the same answer; alias-to-composite tokens correctly stay untyped either way.

### Superseded Proton scale steps

Firefox ships two generations side by side: `color.tokens.json` is the Proton ramp, `color.nova.tokens.json` the Nova one, on different scales. Merging them key by key keeps a Proton step Nova dropped, which then sits at the end of a scale it does not belong to (Proton's `100` and `110` steps sit past Nova's `90`, and `border.radius.xxlarge` was listed when Nova has no such radius). `sync.py` drops those at conversion time (`prune_superseded_scale_steps`), under four guards:

- **`base/` only.** A component token's real consumer is CSS in mozilla-central, not another token, so "nothing aliases it" says nothing about whether it is live.
- **Only a group Nova rewrote.** Nova defines no `white`/`black` group, so those stay.
- **Only a flat scale** (every member a leaf). `background.color` holds nested groups and is never touched; `border.radius` is flat leaves, so it is.
- **Only a step nothing references under Nova.** A Proton token its own `.nova` sibling redefines is skipped, as is the non-nova half of a token carrying its own `nova` branch; a blanket scan would count references that exist only in superseded definitions and keep dead tokens alive forever.

A step that real tokens still alias with no Nova replacement stays, which is why `color.gray.100` and `border.radius.circle`/`large` are still in `base/`. What counts as a live reference is `sync.py`'s `_collect_alias_refs` and `_live_under_nova`: a token's Nova value if it has one, otherwise its `$value` and theme branches, across `.nova.` files too. Read those rather than recounting by hand, since a reference can sit in a theme branch or a Nova value as well as in `$value`.

### Smoke test

The namespace an `{alias}` resolves into is the source file's stem (`space.tokens.json` → `space`), never repeated as a wrapping key inside the file, exactly as Firefox's own build resolves references. After every conversion `sync.py` walks:

```
components/button.tokens.json  → padding.inline.@base  → "{space.large}"
base/space.tokens.json         → large                 → "1rem"
```

and fails the run if it does not end at `"1rem"`. It proves the converted files are walkable by something reading only `token-api/`, not that every alias in the corpus resolves.

## Figma checks

### Tokens: the "In Figma" column

What the column means is on the Token API page. To regenerate it:

**1. Pull `token-api/figma-variables-dump.json`**, every variable in the file, in one REST call. It needs a Figma personal access token; this repo has none of its own.

```sh
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FIGMA_FILE_KEY/variables/local" \
  -o /tmp/figma-variables-raw.json
```

Then convert it, which keeps only each variable's name, type, collection and remote flag, drops Figma's `deletedButReferenced` ghosts, lists which variables populate `codeSyntax`, and writes the dump:

```sh
python3 token-api/figma-dump.py /tmp/figma-variables-raw.json
```

It refuses an error response, an empty or malformed one, and one with under half the existing dump's variables, and stops if the existing dump itself is not valid (pass `--allow-shrink` in either case if replacing it is intended). The raw response carries Figma ids and keys, so it stays outside the repo; delete it afterwards. Never commit the file key: name the file ("Nova Styles (Experimental)") and keep `$FIGMA_FILE_KEY` as the placeholder.

**2. Run `python3 token-api/figma-check.py`.** Pure local computation, no network. Rerun it whenever `resolved/*.json`, `component-api/*.json`, `base/*.tokens.json` or the dump changes. It builds the same set of property names the site renders (every component page and every base token family), then normalizes each name and each Figma variable name to a tuple of lowercase words, splitting on every non-alphanumeric character. That split is what makes `box-shadow` match Figma's `box / shadow` without a hardcoded list of two-word basenames.

**3. Commit `token-api/figma-token-map.json`**, the baked lookup the site fetches, since the page is static. CI regenerates it and fails if it differs.

Matching is by name because Figma's `codeSyntax` field was nearly empty when last counted, from a pull before `figma-dump.py` existed. `figma-dump.py` now records which variables populate it, as the dump's `codeSyntaxPopulated`; the committed dump predates that, so the next pull is the first that records it. If a future publish fills it in broadly, it should become the primary signal.

### Components

`component-api/figma-check.py` checks component entries against a pulled list of the file's components. See `component-api/README.md`.
