# Acorn Contracts: Agent Guidance

Procedural rules for working in this repo. See `README.md` for what each API is and why it's shaped the way it is; this file is about how to do the work correctly.

## Adding a new component

Writing `component-api/<id>.json` and updating `manifest.json` is not enough to make a component show up on the live site (`index.html`). The nav, home tables, and per-item view are all driven by a separate, hardcoded `DATA` array inside `index.html`'s own `<script>` block, alphabetized by name. Add a matching entry there too (`id`, `name`, `group`, `figma`, `supernova`, `storybook`, `kind`, `tagName`, `file`), in alphabetical position. Without it, the component is fully documented in the data but invisible in the UI.

`check-index-data.py` now errors on exactly that (run by `check-contracts.yml`): it asserts the two id sets match and that `kind`, `tagName` and `file` agree wherever both sides name them. It does not remove the need to write the `DATA` entry by hand, it just means forgetting fails CI instead of failing silently. Deliberate divergences go in that script's `EXCEPTIONS` with a reason, and are printed on every run rather than passing quietly.

**Verify `figma`/`supernova` with real evidence, don't guess.** These mean whether the real Firefox component (not Acorn's own) has a citation in Firefox's own internal Figma/Supernova instance. Check via the Supernova MCP:
- `sn_get_component_list` (paginate via `cursor`) for canonical Supernova components.
- `sn_get_figma_component_list` (paginate via `cursor`, ~300+ entries) for real Figma component records; search the full list by the component's real name (e.g. "Five Star", "Button group"), not just the first page.

A component with no matching name in either list gets `figma: "no"` / `supernova: "no"`, not an omitted field or a guess. As of 2026-09-01 this Supernova connection covers real Firefox chrome/toolkit components (not just Acorn's own), confirmed by finding real matches like "Toolbox", "Tabstrip", "Bookmarks Toolbar" in the list.

**Verify `storybook` with a real check, don't infer from directory structure.** A component's own subdirectory existing under `toolkit/content/widgets/` doesn't mean it has a story; check for a real `<name>.stories.mjs` file specifically (a quick sparse `git fetch` scoped to `toolkit/content/widgets/*/*.stories.mjs` works, see `component-api/check-drift.py` for the same clone technique).

**Editing a `component-api/` or `guidance-api/` entry takes two commits, in this order.** Commit the entry first, then run `python3 update-meta.py` and commit the result separately. `_meta.json` records each file's real last commit, so regenerating it before the content commit records the *previous* commit and `update-meta.py --check` fails in CI. Bundling both into one commit fails the same way, and `--amend` cannot rescue it either: amending mints a new SHA that `_meta.json` would then not be citing. Two commits is structural, not a style preference.

`hooks/pre-push` catches forgetting the second one. It runs the read-only checks (schema validation, `check-index-data.py`, `update-meta.py --check`) before a push leaves the machine, so the failure lands locally instead of as a red X on a public commit. It is not installed by cloning, because `.git/hooks` is not versioned:

```sh
git config core.hooksPath hooks
```

It only reads. `token-api/resolved/` and `figma-token-map.json` are verified in CI by regenerating and diffing, and are left out deliberately: a hook that rewrites files under you mid-push is worse than the red X it would prevent. `git push --no-verify` skips it when a red push is intentional.

## Syncing with upstream

`token-api/sync.py` is a real rerunnable pipeline (see `token-api/README.md`). `component-api/` has no equivalent full-regeneration script; `component-api/check-drift.py` only detects which tracked components' real source changed and which real `toolkit/content/widgets/` components have no entry yet (see `component-api/README.md`). Writing or updating an actual `component-api/<id>.json` entry still means reading the real current source yourself (or delegating to an agent) and following the schema, same as before drift detection existed.

**Only run `check-drift.py` when you intend to act on the report.** Running it is not free and not read-only: it rewrites `drift-manifest.json` with the hashes it just saw, so every component it flagged is recorded as checked against the new commit whether or not anyone re-derived it. Run it, walk away, and the next run reports nothing — the signal is spent. mozilla-central also moves constantly, so a run taken purely out of curiosity will flag a fresh batch of changed files and then mark them all as seen. `22af93e` deliberately left the manifest un-advanced for exactly this reason, and only `433b0da` advanced it, once the 20 flagged components had actually been triaged.

Triaging a flagged component is much cheaper than re-reading its source: diff the two commits for that one file (`git diff <manifest commit> <new commit> -- <path>`) and check whether anything the entry documents actually moved. Most hash changes are comments, CSS or refactors that leave every documented field true — of the 20 flagged on 2026-09-10, 16 were no-ops.

## Comparing a component against its Figma Code Connect file

Some components upstream have a `<name>.figma.ts` beside them; `grep -rl 'figma.connect' toolkit/content/widgets` in a checkout lists them. Diffing one against its contract is how the drift recorded in `~/Documents/acorn-figma-code-drift.md` was found: five real bugs, including a Figma variant that emits no Dev Mode snippet at all. Worth doing when a component's variants change. No configuration needed: the `.css` and `.figma.ts` are siblings of `implementation.file`.

The comparison that works: take the values the contract declares (`variants`, and the union in `type.text`), the values the component's own CSS selects on (`[attr="x"]` exact, `[attr~="x"]` word match), and the right-hand values of each `figma.enum(...)`. A healthy component satisfies **declared == CSS + default**, because a `default` value never carries a selector of its own and Figma never lists it.

**The part that's an instruction rather than reference: four things look like drift and are not.** Each of these was flagged, investigated and found innocent on 2026-09-16, so don't re-file them.

1. **A `figma.enum`/`boolean`/`string` prop is an input to a code snippet, not an element attribute.** `moz-input-text.figma.ts` has `errorMessage` and `text`; neither is a property on any input class. Compare against the attributes the `example` template actually emits, not the prop names.
2. **`moz-label.figma.ts` deliberately maps props that are not label attributes**, and says so in its own comment: the Figma Label component stands for the label-plus-description-plus-icon cluster that moz-checkbox, moz-radio, moz-toggle and moz-fieldset render internally.
3. **One file can hold several `figma.connect` blocks for different tags.** `panel-list.figma.ts` covers both `panel-list` and `panel-item`. Merging their props makes panel-item's `label`/`iconSrc`/`badged`/`submenu`/`rule` look undocumented.
4. **A `.figma.ts` basename is the Figma component's name, not the element's.** `toolkit/content/widgets/moz-input-color/color-picker.figma.ts` is `moz-input-color`'s file. Map by directory, not by filename, or a component looks untracked when it is not.
5. **Compare Figma props against slots as well as attributes.** `promo.figma.ts`'s `actions` prop is a real slot, not a missing attribute.
6. **Check which base class a component actually extends before diffing inherited members.** `MozBoxButton extends MozBoxBase`, not `MozBaseInputElement`, so comparing it against the latter's 13 properties invents seven gaps.

An entry that has one records it as `implementation.codeConnect`, the path to the file. A path rather than a boolean so it can rot visibly: `check-drift.py` fetches it alongside the implementation file and reports `CODE CONNECT GONE` if it moves, the same way it reports a moved implementation. More entries carry one than there are files, because this inventory splits some things upstream keeps together: `panel-list.figma.ts` covers both `panel-list` and `panel-item`, and `moz-page-nav.figma.ts` covers the nav, its items and its separator.

## Checking whether a token/CSS custom property exists in Figma

Every component page's Design tokens table has an "In Figma" column, built from `token-api/figma-token-map.json`. The source rule (always the Figma REST API, never Supernova), the matching algorithm, the strict two-state `yes`/`no` result, why alias chains are never followed, and how to regenerate both the map and the dump behind it are all in `token-api/README.md`'s "Figma existence check" section, with the full match algorithm in `token-api/figma-check.py`'s own docstring. Read one of those before touching that column or its data; don't re-derive the rules from this file.

The part that's an instruction rather than reference: **a row full of `no`s is a real finding, not a bug to fix.** Entire component families (urlbar, panel, toolbar, sidebar, checkbox, most `moz-*` components) have no matching *semantic color* group in that Figma file at all. Loosening the match rule until those turn into `yes`es defeats the entire point of an existence check.
