# Component API: schema

This directory holds one JSON file per Acorn/Firefox design-system component, describing its real API surface. It's the first output of the "Component API" effort: a machine-readable contract between what's in Figma/the Acorn API and what actually exists in mozilla-central.

## Why Custom Elements Manifest (CEM), and why `id` instead of `tagName`

The schema is built on [Custom Elements Manifest](https://github.com/webcomponents/custom-elements-manifest), the open-wc/webcomponents.org JSON schema, rather than a bespoke format. CEM already models the parts of a custom element's API surface that matter here: tag name, attributes/properties, slots, events, CSS custom properties, methods. It works equally well for Lit-based `moz-*` components and plain custom elements, since both ultimately call `customElements.define()`. The CEM analyzer also has first-class Lit support, which matters because most of Firefox's actively-developed components are Lit.

One thing doesn't fit CEM's shape as-is: **not everything in Firefox's design system is a registered custom element.** The inventory this schema covers includes:

- **modern**: a real Lit component, registered via `customElements.define()`. Lit is the whole test, reached directly (`extends MozLitElement`) or through a shared base that does (`MozBaseInputElement`, `SelectControlBaseElement`, or a subclass of another Lit component, as the `moz-input-*` family extends `MozInputText`). The `moz-*` prefix is the usual naming but not part of the definition: `sidebar-main.mjs` and `sidebar-panel-header.mjs` are real Lit components without it.
- **classic**: a real implementation that isn't Lit. Usually that means older and pre-Lit, a registered XUL/legacy custom element with a real tag name (e.g. `panel.js`'s `MozPanel extends MozElementMixin(XULPopupElement)`). A few entries are "classic" in spirit but were never registered as custom elements at all: a plain ES class (`FeatureCallout.sys.mjs`), a plain exported object (`Spotlight.sys.mjs`), a React component (`MultiStageProtonScreen.jsx`). These still have a real, documentable API surface (constructor options, methods, props), so they're recorded with `tagName: null` and full `attributes`/`methods` rather than collapsed into the `none` minimal shape. The dividing line between `none` and `classic` is whether a real widget exists at all. A built-in XUL widget tag counts as `classic` even with no JS class behind it and nothing configurable to document: `<toolbox>` carries only an id and is still a real element in the chrome, where a `<hr>` acting as a separator is not. Being old is not part of the test either: `panel-list.mjs` is a current ES module with no imports at all, defining `panel-list` and `panel-item` as plain `extends HTMLElement` classes, and all three entries drawn from it are `classic` because none of them is Lit.
- **dual**: both a modern and a classic implementation coexist in the tree for the same concept (e.g. checkbox, radio, and infobar, whose `notification-message` element extends `moz-message-bar` internally but has no JSDoc of its own).
- **none**: not a widget at all. A generic HTML element standing in for one (a plain `<hr>` used as a separator), or page structure with no element of its own to point at. No class, no `customElements.define`, no widget tag, nothing configurable.
- **missing**: no real Firefox equivalent exists at all. Either the closest thing in mozilla-central is a different, single-purpose feature component (`chip`), or chrome UI just uses the native HTML element (`details`).

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
| `cssParts` | array, optional | CEM's own field name. Real `::part()` names found in the component's own shadow-DOM render output, or a shared base class it genuinely extends (e.g. Box Item's `support-link`, inherited nowhere; Radio's `fieldset`, inherited from `SelectControlBaseElement`). Most entries have none, but not because Acorn is light-DOM: Firefox's Lit components render into a shadow root by default and `MozLitElement` does not override `createRenderRoot`, so a modern component with no `cssParts` genuinely declares no `part=` in its own template. The entries that have none are mostly the `classic` ones and the sub-items documented under a parent, neither of which has a shadow template to expose parts from. A real light-DOM case does exist and is the exception: a customized built-in like `moz-support-link` has no shadow root at all. |
| `variants` | array, optional | Enum-style axes: an attribute/property with a fixed set of allowed string values (e.g. `type`), surfaced separately from the flat `attributes` list because these are the values worth showing side-by-side in Figma/Storybook variant pickers. |
| `usage` | string, optional | A realistic, real-attribute usage example, pulled from a Storybook story, a Figma Code Connect example, or otherwise hand-built strictly from attributes actually found in source. Not a hypothetical. |
| `attributes[].type` | object, optional | CEM's own field name and shape: `{ "text": "..." }`, where `text` is the type as written in whatever syntax the source uses. An enumerated attribute's legal set is a TypeScript-style union. Note Lit usually declares only `{ type: String }`, so a union here is this contract asserting the set, not a fact recovered from source. |
| `*[].inheritedFrom` | object, optional | CEM's own field name. A `Reference`, `{name, module?}`, naming the class that **declares** the member rather than the component documenting it. CEM's Reference holds one name, so an intermediate hop stays in the description ("Inherited via MozInputText"). |
| `*[].deprecated` | string \| boolean, optional | CEM's own field name. A string is the reason. CEM has no per-VALUE form, so a legacy value of an enumerated attribute stays described in prose. |
| `implementation.verifiedAt` | object, optional | **Not CEM.** `{commit, date, scope}`, when this entry was last confirmed against real upstream source. Different from `_meta.json`, which records when the JSON was last edited here. Deliberately not backfilled. |
| `implementation.codeConnect` | string, optional | **Not CEM.** Path to the component's Figma Code Connect file. A path rather than a boolean so `check-drift.py` can report it moving. |

### Which fields are CEM's and which are ours

The shape follows [CEM](https://github.com/webcomponents/custom-elements-manifest) wherever CEM has an opinion, and diverges deliberately in ten places. CEM permits extra properties (it sets `additionalProperties: false` nowhere) but defines no formal extension mechanism, so ours stay flat and are listed here rather than wrapped in a namespace.

| ours, not CEM's | why |
|---|---|
| `id` | The primary key. CEM keys on tag name, and several real entries have no tag at all. |
| `implementation` and its `kind`, `file`, `verifiedAt`, `codeConnect` | CEM describes a manifest of modules; it has no place to say "this is the real Firefox file, and here is how modern it is". |
| `variants` | The designer-facing subset of an enumerated attribute's values, for a Figma or Storybook variant picker. May be narrower than the legal set in `type.text`. |
| `usage` | A realistic example. CEM has `demos`, which points at URLs rather than inline snippets. |
| `attributes[].figmaConfig` | Whether an attribute is user-facing configuration rather than internal plumbing. |
| `methods` as a top-level array | CEM puts methods and fields together in one `members` array with a `kind` discriminator. Splitting them reads better on a page, at the cost of a restructure. |

Everything else in the table above uses CEM's own field name and, where CEM defines one, its shape.

Every array/field is **omitted, not padded**, when genuinely empty or unknown for a given component. Every field that is present must trace back to a real, cited source file, nothing here is invented.

## Minimal shape for `none` / `missing` components

Components with `implementation.kind` of `none` or `missing` have no real attributes/slots/events/etc. to document, that would be fabrication. Their JSON files carry only `id`, `tagName: null`, `description`, and `implementation`. Example (`panel-separator`, a plain `<hr>` a consumer slots into `<panel-list>`, with no tag or class of its own):

```jsonc
{
  "id": "panel-separator",
  "tagName": null,
  "description": "...",
  "implementation": { "kind": "none", "file": "toolkit/content/widgets/panel-list/panel-list.mjs" }
}
```

Only `panel-separator` and `page-nav-separator` are `none` today. Both really are plain `<hr>`s, which is why the XUL-tag rule above does not make them `classic`.

## Source of the worklist

The original 57-item inventory (ids, prior `kind`/`tagName`/`file` classification) came from `index.html`'s `DATA` array. This directory adds the actual API shape (attributes/slots/events/methods/cssProperties) on top of that prior classification. It does not re-derive `kind` or `file` from scratch, though a handful of entries were corrected where opening the real source contradicted the original citation (see individual file descriptions for any such notes). 14 more components (`button-group`, `five-star`, the `input-*` family, `label`, `reorderable-list`, `support-link`, `textarea`) were added later, found by `check-drift.py` below.

## Keeping the inventory current: `check-drift.py`

Unlike `token-api/sync.py`, there's no full-regeneration pipeline here: writing a correct `<id>.json` needs a human or agent actually reading and understanding real source, not a deterministic transform. `check-drift.py` instead does the two mechanical parts of staying current:

1. **Hash every cited file.** For each tracked component's `implementation.file`, fetch its current real content via a sparse git clone and hashes it, comparing against the hash from the last run (stored in `drift-manifest.json`). Flags anything that changed since this repo's own entry was last checked against it. The manifest records each id's path next to its hash, so repointing an entry at a different file is reported as a repoint, not as upstream movement — comparing hashes across two different files says nothing either way.
2. **Find untracked widgets.** List the real current contents of `toolkit/content/widgets/`, filtered to files that actually call `customElements.define(...)` (not Storybook demos or shared helpers), and flags any real component with no `component-api/` entry pointing at it yet. Split into `moz-*`-prefixed (Acorn's own naming convention, high-confidence real findings) vs. other native widgets (legacy XUL-era elements, generally out of scope, reported as FYI only, doesn't fail the run).
3. **Verify the cited tag.** For every entry with a `tagName`, check the cited file really registers it via `customElements.define()`. A file can sit unchanged at its recorded path while no longer defining the tag the entry claims — neither the hash nor the existence check sees that. When the tag turns up in a sibling file instead, that file is named and the run still passes: splitting registration out from the class holding the API is a real upstream pattern (`moz-urlbar` is registered in a 12-line `UrlbarInput.mjs` beside the 6,671-line `UrlbarInputBase.mjs` every documented field comes from), so the citation is usually right and only the check is naive. Only a tag found in no fetched file at all fails the run.

```
python3 component-api/check-drift.py [--ref <branch-or-sha>]
```

It only reports; it never writes to any `<id>.json`. Use its output as the worklist for the actual documentation pass, see `AGENTS.md` for how to verify `figma`/`supernova`/`storybook` on a new find and the `index.html` nav-registration step that's easy to miss.

## Files in this directory

| File | What it is |
|---|---|
| `<id>.json` | One per component, the populated entries described above. `check-index-data.py` reports the current count and asserts it matches `index.html`'s inventory. |
| `schema.json` | The schema above as a draft 2020-12 JSON Schema, not just this README's prose. Enforced by `validate-schemas.py` on every push. |
| `_meta.json` | Per-id `lastCommit`/`lastModified`, each one's real last commit in this repo's history, plus the `HEAD` it was generated against. |

An entry may also carry `implementation.verifiedAt`: `{commit, date, scope}`, recording when its contents were last confirmed against real upstream source. That is a different question from `_meta.json`'s, which says when the JSON was last edited *here*. It is deliberately not backfilled, because for most of the inventory nobody knows the answer, and inventing one would be exactly the kind of fiction the rest of this directory avoids. An absent `verifiedAt` means unconfirmed since the field existed.

Set it only after actually reading the cited source. Never from `check-drift.py`'s hash comparison, and never from a name-presence check: `support-link` and `label` both kept every documented member name while their class declarations changed to `StylesMixin(...)` under them, so both of those signals would have said "unchanged". `scope: "implementation"` records the weaker claim that only the kind/file/tagName line was checked.

**`_meta.json` says when the JSON was last edited here**, not when it was last
verified against real Firefox source. Those can differ.
