# Component API: schema

This directory holds one JSON file per Acorn/Firefox design-system component, describing its real API surface. It's the first output of the "Component API" effort: a machine-readable contract between what's in Figma/the Acorn API and what actually exists in mozilla-central.

## Why Custom Elements Manifest (CEM), and why `id` instead of `tagName`

The schema is built on [Custom Elements Manifest](https://github.com/webcomponents/custom-elements-manifest), the open-wc/webcomponents.org JSON schema, rather than a bespoke format. CEM already models the parts of a custom element's API surface that matter here: tag name, attributes/properties, slots, events, CSS custom properties, methods. It works equally well for Lit-based `moz-*` components and plain custom elements, since both ultimately call `customElements.define()`. The CEM analyzer also has first-class Lit support, which matters because most of Firefox's actively-developed components are Lit.

One thing doesn't fit CEM's shape as-is: **not everything in Firefox's design system is a registered custom element.** The inventory this schema covers includes:

- **modern**: a real Lit component, registered via `customElements.define()`. Lit is the whole test, reached directly (`extends MozLitElement`) or through a shared base that does (`MozBaseInputElement`, `SelectControlBaseElement`, or a subclass of another Lit component, as the `moz-input-*` family extends `MozInputText`). The `moz-*` prefix is the usual naming but not part of the definition: `sidebar-main.mjs` and `sidebar-panel-header.mjs` are real Lit components without it.
- **classic**: a real implementation that isn't Lit. Usually that means older and pre-Lit, a registered XUL/legacy custom element with a real tag name (e.g. `panel.js`'s `MozPanel extends MozElementMixin(XULPopupElement)`). A few entries are "classic" in spirit but were never registered as custom elements at all: a plain ES class (`FeatureCallout.sys.mjs`), a plain exported object (`Spotlight.sys.mjs`), a React component (`MultiStageProtonScreen.jsx`). These still have a real, documentable API surface (constructor options, methods, props), so they're recorded with `tagName: null` and full `attributes`/`methods` rather than collapsed into the `none` minimal shape. The dividing line between `none` and `classic` is whether real, citable config/behavior exists to document, not whether a tag was ever registered. Being old is not part of the test either: `panel-list.mjs` is a current ES module with no imports at all, defining `panel-list` and `panel-item` as plain `extends HTMLElement` classes, and all three entries drawn from it are `classic` because none of them is Lit.
- **dual**: both a modern and a classic implementation coexist in the tree for the same concept (e.g. checkbox, radio, and infobar, whose `notification-message` element extends `moz-message-bar` internally but has no JSDoc of its own).
- **none**: not a component at all, and nothing real to document beyond "this script exists and wires up markup." No class, no `customElements.define`, no meaningful config surface. Just a script wiring listeners onto existing markup by id/selector (e.g. `navigator-toolbox.js`). No tag name exists because nothing was ever registered.
- **missing**: no real Firefox equivalent exists at all (prototype-only, or the browser just uses a native HTML element like `<details>`).

Because of this, CEM's usual primary key, tag name, can't be the primary key here: several real, load-bearing pieces of this inventory have no tag name at all, and CEM has no room for "this isn't a custom element but it's still real and worth documenting."

So this schema uses **`id`**, a stable slug matching the `id` field in `index.html`'s `DATA` array, as the universal primary key. It is always present, regardless of implementation kind. **`tagName` is optional**, and is `null` whenever nothing was ever registered as a custom element.

## Field reference

| Field | Type | Notes |
|---|---|---|
| `id` | string, required | Stable slug. Matches `index.html`'s `DATA` array `id` for the same concept. Never null. |
| `tagName` | string \| null | The real, registered custom element tag name, if one exists. `null` for `none`/`missing` kinds, and sometimes for `modern`/`classic` kinds where a class exists but no distinct tag was ever registered (e.g. a second class living in the same file as another component). |
| `description` | string | One or two sentences, grounded in the actual source file, not a generic restatement of the component's name. |
| `implementation.kind` | enum | One of `modern` (Lit), `classic` (real but not Lit), `none` (not a component), `missing` (no real-Firefox equivalent), `dual` (both modern and classic exist side by side). |
| `implementation.file` | string | Path relative to the mozilla-central root. The primary source-of-truth file this JSON was derived from. |
| `attributes` | array, optional | CEM's own field name (not `attrs`). Real attributes/properties read off the class (JSDoc `@property` for modern components, direct attribute getters/`observedAttributes` for classic ones). Each entry: `name`, `type`, `description`, optional `default`, optional `figmaConfig`. |
| `attributes[].default` | string, optional | CEM's own field name. This attribute's real default value/state when not otherwise set, straight from source (a getter's fallback, an `observedAttributes` initial state, etc.). Omitted, not guessed, when source doesn't establish one explicitly. |
| `attributes[].figmaConfig` | boolean, optional | Whether this attribute is real user-facing configuration (something a designer would set in Figma) vs. internal/plumbing-only state. Only set `true`/`false` when there's real signal: a Figma Code Connect (`.figma.ts`) mapping, or an attribute that's obviously internal wiring (e.g. an id used only for a11y association). Omitted, not guessed, when genuinely unclear. |
| `slots` | array, optional | Real `<slot>`s found in the component's render output. Default slot is named `(default)`. |
| `events` | array, optional | Real events the component dispatches (JSDoc `@fires`, or actual `dispatchEvent`/`new CustomEvent` calls found in source). |
| `methods` | array, optional | Real public methods on the class, beyond standard property accessors. |
| `cssProperties` | array, optional | Real CSS custom properties the component's stylesheet reads (JSDoc `@cssproperty`, or `var(--foo, ...)` usage in the component's own CSS). |
| `cssProperties[].default` | string, optional | CEM's own field name. The property's real literal value set directly in the component's own CSS, for a property with no backing design token (token-api coverage takes precedence when both exist). Omitted, not guessed, when no such real default exists (e.g. a value only ever set inline per-instance). |
| `cssParts` | array, optional | CEM's own field name. Real `::part()` names found in the component's own shadow-DOM render output, or a shared base class it genuinely extends (e.g. Box Item's `support-link`, inherited nowhere; Radio's `fieldset`, inherited from `SelectControlBaseElement`). Acorn is mostly light-DOM by design, so most entries have none of these; light-DOM components can't expose real parts at all. |
| `variants` | array, optional | Enum-style axes: an attribute/property with a fixed set of allowed string values (e.g. `type`), surfaced separately from the flat `attributes` list because these are the values worth showing side-by-side in Figma/Storybook variant pickers. |
| `usage` | string, optional | A realistic, real-attribute usage example, pulled from a Storybook story, a Figma Code Connect example, or otherwise hand-built strictly from attributes actually found in source. Not a hypothetical. |

Every array/field is **omitted, not padded**, when genuinely empty or unknown for a given component. Every field that is present must trace back to a real, cited source file, nothing here is invented.

## Minimal shape for `none` / `missing` components

Components with `implementation.kind` of `none` or `missing` have no real attributes/slots/events/etc. to document, that would be fabrication. Their JSON files carry only `id`, `tagName: null`, `description`, and `implementation`. Example (`toolbox`):

```jsonc
{
  "id": "toolbox",
  "tagName": null,
  "description": "...",
  "implementation": { "kind": "none", "file": "browser/base/content/navigator-toolbox.js" }
}
```

## Source of the worklist

The original 57-item inventory (ids, prior `kind`/`tagName`/`file` classification) came from `index.html`'s `DATA` array. This directory adds the actual API shape (attributes/slots/events/methods/cssProperties) on top of that prior classification. It does not re-derive `kind` or `file` from scratch, though a handful of entries were corrected where opening the real source contradicted the original citation (see individual file descriptions for any such notes). 14 more components (`button-group`, `five-star`, the `input-*` family, `label`, `reorderable-list`, `support-link`, `textarea`) were added later, found by `check-drift.py` below.

## Keeping the inventory current: `check-drift.py`

Unlike `token-api/sync.py`, there's no full-regeneration pipeline here: writing a correct `<id>.json` needs a human or agent actually reading and understanding real source, not a deterministic transform. `check-drift.py` instead does the two mechanical parts of staying current:

1. For every tracked component's `implementation.file`, fetches its current real content via a sparse git clone and hashes it, comparing against the hash from the last run (stored in `drift-manifest.json`). Flags anything that changed since this repo's own entry was last checked against it. The manifest records each id's path next to its hash, so repointing an entry at a different file is reported as a repoint, not as upstream movement — comparing hashes across two different files says nothing either way.
2. Lists the real current contents of `toolkit/content/widgets/`, filtered to files that actually call `customElements.define(...)` (not Storybook demos or shared helpers), and flags any real component with no `component-api/` entry pointing at it yet. Split into `moz-*`-prefixed (Acorn's own naming convention, high-confidence real findings) vs. other native widgets (legacy XUL-era elements, generally out of scope, reported as FYI only, doesn't fail the run).
3. For every entry with a `tagName`, checks the cited file really registers it via `customElements.define()`. A file can sit unchanged at its recorded path while no longer defining the tag the entry claims — neither the hash nor the existence check sees that. When the tag turns up in a sibling file instead, that file is named and the run still passes: splitting registration out from the class holding the API is a real upstream pattern (`moz-urlbar` is registered in a 12-line `UrlbarInput.mjs` beside the 6,671-line `UrlbarInputBase.mjs` every documented field comes from), so the citation is usually right and only the check is naive. Only a tag found in no fetched file at all fails the run.

```
python3 component-api/check-drift.py [--ref <branch-or-sha>]
```

It only reports; it never writes to any `<id>.json`. Use its output as the worklist for the actual documentation pass, see `AGENTS.md` for how to verify `figma`/`supernova`/`storybook` on a new find and the `index.html` nav-registration step that's easy to miss.

## Files in this directory

- One `<id>.json` per component (71 total), the real, populated entries described above.
- `schema.json`: the schema above as a real, machine-checkable JSON Schema (draft 2020-12), not just this README's prose. Validated against all real entries.
- `_meta.json`: per-id `lastCommit`/`lastModified`, each one's real last commit in this repo's own git history (not a fabricated timestamp), plus the repo `HEAD` this was generated against. Says when the JSON was last edited here, not when it was last verified against real Firefox source, those can differ.
