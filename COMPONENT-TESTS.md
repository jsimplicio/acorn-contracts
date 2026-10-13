# Component Tests

A test of whether this repo's own data (component-api plus token-api) is rich enough to mechanically build a real HTML/CSS component, not just describe one. Inspired by [Nathan Curtis on spec-driven UI development](https://nathanacurtis.substack.com/p/spec-driven-ui-component-development). 23 real components, atoms through small molecules, each built from nothing but what's actually in this repo, with every value traced to a real token or a real component-api fact, and every gap named instead of filled in.

## How a component actually gets built from this

`component-api/<id>.json` gives the shape: attributes, slots, variants, hand-verified against real source. `token-api/components/<basename>.tokens.json` gives the values, usually aliases that need resolving through a `<basename>.nova.tokens.json` override (nova wins when both exist), then through `base/*.tokens.json`. `token-api/resolve.py` already does this walk for light; dark isn't published anywhere (see the next section), so every dark value below was resolved by hand, reusing `resolve.py`'s own logic with its nova pick order reversed to prefer a `dark` branch where one exists.

## What this test got wrong along the way

- Missed a `.nova.tokens.json` sibling once, produced an impossible "border-radius changes with theme" result.
- Called something a gap twice without checking `base/` first (dark-mode colors, focus ring, both real).
- Almost hand-wrote a value into a synced token file, caught before it happened (see Checkbox below). No contract value was hand-edited this test, only description prose, cited against real source.
- `resolve.py`'s own published export (`token-api/resolved/*.json`) is light-only, by design: its nova pick order puts `dark` last, so a token only comes out dark-sensitive if it has an explicit `nova` branch. A hand-rolled dark picker built for this test had two real bugs of its own: it once grabbed an unrelated native-widget-theming value as if it were a dark color, and separately missed a light/dark split nested two levels deep inside a brand/platform wrapper. Fixed, every token already resolved was re-checked; only one value actually changed (button and toggle's idle background is `transparent` in dark, not a translucent black).
- Select's first build showed one fabricated custom dropdown as the default. `select.json`'s own description already said a plain `<select>` renders unless an option has an icon; that line had been read and ignored. Fixed, both real render paths are shown below.
- Panel item's border-radius: hand-picked `border.radius.small` (8px) straight off a base token instead of resolving the `panel-menuitem` basename through the real pipeline, which would have surfaced its own nova sibling overriding it to `border.radius.large` (16px). Same root mistake as the first item on this list, a nova sibling going unchecked, just a shortcut this time instead of a missing file.

## This test's own choices, not the contract

Spacing, sizing, and typography values below with no real token were either reused from the nearest real value elsewhere in this repo, or are a small invented number where nothing real was close:

- A control top-aligned to the first line of a multi-line label (checkbox, radio, toggle): no entry specifies this, just the visually obvious reading.
- Control-to-label spacing on radio and toggle (`0.5rem`): neither has its own spacing token, reused checkbox's real one instead of inventing two more numbers.
- Description text size (`0.867rem`, `font.size.small`): reused from button, not a token checkbox or toggle names itself.
- Several components with no padding/gap/radius token at all (input's inner padding, panel-list's outer padding, segmented control's item gap, promo's image radius, toolbox's own radius, toolbar field's pill radius, toolbar button's 36px box) either reuse a real value from elsewhere in this repo or are a small invented number noted inline below.
- Icon glyphs are placeholders everywhere a type/color is specified but no artwork is: message-bar, card's accordion chevron, select's chevron, toolbar button icons. The contract says what color an icon is, essentially never which icon.

---

## Button

`id: button`, kind: modern, tag `moz-button`. The richest entry tested: full state matrix across 5 visual types (`default`, `primary`, `destructive`, `muted`, `ghost`) times 5 interaction states, plus `toolbar`/`menu` sub-families reused by other components (see Box item and Page nav below).

| Token | Light | Dark |
|---|---|---|
| `button.background.color.primary.@base` | `#764edd` | `#b89cff` |
| `button.background.color.primary.hover` | `#5939a8` | `#d4c1ff` |
| `button.background.color.primary.active` | `#3e2976` | `#eaddff` |
| `button.background.color.@base` (default type, idle) | `transparent` | `transparent` |
| `button.border.color.@base` | `#764edd` | `#b89cff` |
| `button.text.color.primary.@base` | `#ffffff` | `#ffffff` |
| `focus.outline.color` (shared, not button's own) | `#764edd` | `#b89cff` |

**Where the contract ran out of answers:**
- No typeface token anywhere, only size/weight. `font.size.root`'s own `platform.default: "unset"` branch suggests this is deliberate: Firefox inherits the native OS font on purpose.
- `iconSrc` is documented as a path, but no glyph set is part of the contract; every icon anywhere in this test is a stand-in, not real Firefox iconography.
- The split-button's shared seam (`border-right: 0` between the main segment and its chevron) isn't a named token, read directly off the real layout.

Full list: `token-api/resolved/button.json`.

## Checkbox

`id: checkbox`, kind: modern (`moz-checkbox`, with a legacy classic `<checkbox>` also still coexisting in the tree). The entire real token file is two tokens:

```json
{
  "margin": { "inline": { "$value": "{space.small}" } },
  "size": { "$value": "{size.item.small}" }
}
```

That resolves to `0.5rem` margin and `16px` size. Everything else, including the checked-state color, is bare browser default on purpose, not a missing token. The checkmark's actual color comes from `accent-color: var(--color-accent-primary)`, set once globally on `:root` in `toolkit/themes/shared/in-content/common-shared.css` (confirmed at commit `1a097ed8d31f6b307a5d0ebc34a82ceaf7f3727b`), the same `color.accent.primary.@base` token behind button's primary fill and the focus ring. This fact is now cited directly in `checkbox.json`'s own description, added as prose during this test after confirming it against real source; no value in any `.tokens.json` file was touched to "complete" this (an early draft nearly added a fabricated `accentColor` token to `checkbox.tokens.json` before this was caught).

**Where the contract ran out of answers:** nothing beyond the native `accent-color` mechanism above, already resolved by citing real source rather than inventing a token.

## Radio

`id: radio`, same shape as checkbox: a modern `moz-radio-group`/`moz-radio` pair plus a legacy XUL `<radiogroup>`/`<radio>`. Radio has **no token file at all**, not even the two checkbox has. Its checked-dot color is the exact same global `accent-color: var(--color-accent-primary)` mechanism, now cited in `radio.json`'s own description the same way as checkbox.

**Where the contract ran out of answers:** no size or spacing token exists for radio itself; this test reused checkbox's real `0.5rem`/`16px` rather than inventing new numbers for an identical visual need.

## Toggle

`id: toggle`, tag `moz-toggle`. Richly specified, a full real state matrix (off/on times default/hover/active/disabled), all genuinely scheme-sensitive.

| Token | Light | Dark |
|---|---|---|
| `moz-toggle.background.color.pressed.@base` (on) | `#764edd` | `#b89cff` |
| `moz-toggle.background.color.@base` (off) | `transparent` | `transparent` |
| `moz-toggle.border.color.@base` | `#817f84` | `#949297` |
| `moz-toggle.dot.background.color.on-pressed.@base` | `#ffffff` | `#171519` |

**Where the contract ran out of answers:** label alignment and control-to-label gap aren't toggle's own tokens; this test originally left toggle's multi-line label mis-aligned relative to checkbox's correctly-aligned one before being caught and fixed to match.

## Badge

`id: badge`, tag `moz-badge`. Specified but ambiguous: real tokens exist for both a plain outlined state and a `filled` state, but the component-api doesn't say which attribute actually switches between them.

| Token | Light | Dark |
|---|---|---|
| `moz-badge.background.color.filled` | `#008865` | `#90e3c6` |
| `moz-badge.text.color.filled` | `#ffffff` | `#252428` |
| `moz-badge.border.color.@base` | `rgba(21, 20, 26, 0.4)` | `rgba(251, 251, 254, 0.4)` |

**Where the contract ran out of answers:** which attribute/value actually requests the filled look isn't stated in `badge.json`'s attributes; both states are shown here without a confirmed trigger condition.

## Link

`id: none` (no component-api entry). The inverse of badge: real, rich tokens (6, including a custom focus-outline-offset with its own written rationale), but `component-api/link.json` doesn't exist; `link` only exists as a basename folded into `breadcrumb`'s own entry.

| Token | Light | Dark |
|---|---|---|
| `link.color.@base` | `#764edd` | `#b89cff` |
| `link.color.hover` | `#5939a8` | `#d4c1ff` |
| `link.color.visited` | `#764edd` (same as `@base`) | `#b89cff` |

**Where the contract ran out of answers:** no component-api entry at all, nothing to say about underline, weight, or any attribute.

## Chip

`id: chip`. The extreme case: `component-api/chip.json` has no `tagName`, no attributes, no tokens, nothing to build. Its entire content is one sentence: no generic chip exists anywhere in mozilla-central; the closest thing is a single-purpose AI-window feature component, not a reusable primitive. No token file exists either. Correct output for a contract with nothing in it: nothing.

## Message bar

`id: message-bar`, tag `moz-message-bar`, the first molecule tested, 46 tokens. Real finding: across `@base`/`warning`/`success`/`critical`, only the icon chip's background color actually varies by type. Bar background, text color, and border stay identical for every type.

| Token | Light | Dark |
|---|---|---|
| `moz-message-bar.background.color.@base` | `#ffffff` | `#171519` |
| `moz-message-bar.text.color.@base` | `#180e30` | `#f2f0f8` |
| `moz-message-bar.icon.background.color.@base` | `#eaddff` | `#111524` |
| `moz-message-bar.icon.background.color.success` | `#c4f1e0` | `#001e12` |
| `moz-message-bar.icon.background.color.warning` | `#fde8b5` | `#270f00` |
| `moz-message-bar.icon.background.color.critical` | `#ffd9df` | `#211014` |
| `moz-message-bar.icon.color` (the glyph itself, doesn't vary by type) | `#764edd` | `#a2d3ff` |

The icon chip's real shape is a full-height strip flush to the bar's left/top/bottom edges, not a floating rounded badge: `icon.container.height: auto`, and its border-radius tokens round only the side touching the bar's own edge (`radius-start-start`/`radius-end-start`), zeroing the side touching the text (`radius-start-end`/`radius-end-end`). First build guessed a floating 28px circle instead, pattern-matched from badge's own chip shape rather than reading these radius tokens.

**Where the contract ran out of answers:**
- No icon glyph per type, only its background color.
- `border.color` is a live formula, not a stored value: `oklch(from {message-bar.icon.color} l c h / 12%)`.
- Neither the dismiss icon nor promo's dismiss icon (below) has a close-icon-size token, only margin; both were sized to this repo's general 16px icon convention instead of the inherited text size they'd otherwise default to.

## Input (text)

`id: input-text`, tag `moz-input-text`. 14 tokens shared across every `moz-input-*` variant, not just text.

| Token | Light | Dark |
|---|---|---|
| `input.background.color.@base` | `#ffffff` | `#171519` |
| `input.border.color.@base` | `#817f84` | `#949297` |
| `input.text.color.@base` | `#180e30` | `#f2f0f8` |
| `input.min-height` | `32px` | `32px` |

**Where the contract ran out of answers:**
- No padding token anywhere in `input.tokens.json`.
- The `invalid` attribute's description says it renders a red border; `border.color.error`/`text.color.error` do exist as real base tokens, but `input.tokens.json` never references either, so no specific invalid-state color is confirmed.
- `input.height`/`input.width` (16px each, the small icon size) go unused here: they don't match the real rendered height (`min-height`, 32px), an ambiguous role not applied.

## Card

`id: card`, tag `moz-card`, types `default`/`accordion`. 30 tokens, including an interactive accordion header with its own hover/active colors, and a documented Figma gap: `card.border.color` is `color-mix(in srgb, currentColor 10%, transparent)`, flagged in the token's own data as `org.mozilla.meta.ignoreFigma`: "color-mix with currentColor cannot be expressed in Figma."

| Token | Light | Dark |
|---|---|---|
| `card.background.color` | `#ffffff` | `#171519` |
| `card.border.radius.@base` | `16px` | `16px` |
| `card.border.radius.compact` | `12px` | `12px` |
| `card.header.background.color.hover` | `#d2c8ec` | `#75669f` |
| `card.header.background.color.active` | `#b6aad9` | `#9687c0` |

**Where the contract ran out of answers:** the chevron glyph and its rotation on expand/collapse aren't in the token data at all, same shape as message-bar's missing icon glyph.

## Select

`id: select`, tag `moz-select`. Two real, different components behind one id: `select.json`'s own description says it renders a plain native `<select>` when no option has an icon, or a panel-list/button combo when at least one does, an internal state property (`usePanelList`) even names the switch. That property has been in this repo's data since its first commit, confirmed via `git log`, not something introduced for this test.

A native `<select>`'s open list is OS-rendered chrome; no CSS anywhere can style it, which is why only the icon path needs the custom panel-list combo at all: a native `<option>` can't show an icon in any browser.

| Token | Light | Dark |
|---|---|---|
| `select.border.radius` | `24px`, a full pill | `24px` |
| `select.font.weight` (trigger's own value text) | `600` | `600` |
| `select.option.font.weight` (an open list's option text) | `normal` | `normal` |
| `select.option.text.color` | `#180e30` | `#f2f0f8` |

**Where the contract ran out of answers:** no token in `moz-select.tokens.json` is attributed to one render path or the other; this test assumes the trigger-level tokens apply to both paths and `option.*` only means anything in the panel-list path, since a native `<option>` can't take most of that CSS, not confirmed against real source.

## Panel list and panel item

`id: panel-list` and `id: panel-item`, the real shell/item pair behind select's icon-path combo above. Tokens split across 4 files: `panel-list`, `popup`, `panel` (resolve-only), `panel-menuitem`. One token here is a directly cited fact, not a guess: the panel item's badge dot's own `cssProperties` entry names its default as literally `var(--color-accent-primary)`.

| Token | Light | Dark |
|---|---|---|
| `panel-list.background.color.@base` | `#ffffff` | `#171519` |
| `panel-list.border.radius` | `24px` | `24px` |
| `panel-menuitem.margin.@base` (block: 0) | `0 8px` | `0 8px` |
| `panel-menuitem.border.radius` (nova, via its own nova sibling) | `16px` | `16px` |

`panel-menuitem.margin.@base`'s own block value is `0` deliberately: the token's own `$description` says "so there's always an item highlighted and no dead space when moving the pointer across items."

**Where the contract ran out of answers:**
- Item hover/active colors are an assumption, not a confirmed fact. Checked everywhere a color could hide (`panel-item.tokens.json`, `panel-menuitem.tokens.json` and its nova sibling, both components' `cssProperties` lists): none has a single color token. `button.background.color.menu.*` is named for exactly this and is used here, but nothing confirms panel-item's real CSS references it. Box item below directly aliases into this same family, real corroborating evidence, still not proof for panel-item specifically.
- Two parallel exports for the same shell (`panel-list.*` and `popup.*`) carry slightly different formulas (two different box-shadow shapes); which one the live widget actually applies isn't stated.
- No icon glyph per type, same shape as every other icon gap here.

## Promo

`id: promo`, tag `moz-promo`, types `default`/`vibrant`. 14 tokens. `vibrant` changes the background and the message text, but NOT the heading text, an asymmetric split the type name doesn't suggest.

| Token | Light | Dark |
|---|---|---|
| `moz-promo.background.color.vibrant` | `#e7e1f8` | `#3e315f` |
| `moz-promo.heading.text.color.@base` (same for vibrant too) | `#180e30` | `#f2f0f8` |
| `moz-promo.message.text.color.vibrant` | `#271c48` | `#f5ecff` |
| `moz-promo.image.size.@base` | `80px` | `80px` |

Its border is `color-mix(in **lch**, ...)`, a different color space from card's `color-mix(in srgb, ...)`, confirmed real against the raw token, not a typo carried over.

**Where the contract ran out of answers:** `imageWidth`'s own description notes `default` and `small` render alike, only `large` carries a real CSS rule, a documented quirk, not a miss. No image border-radius token exists either.

## Segmented control

`id: segmented-control` and `id: segment`. The simplest real molecule tested, 4 tokens, all on the wrapper. `segment.json`'s own description says checking an item toggles the underlying button's type between `primary` (checked) and `ghost` (unchecked), a cited fact, not an inferred reuse like panel-item's colors above.

| Token | Light | Dark |
|---|---|---|
| `segmented-control.border.color` | `#817f84` | `#949297` |
| `segmented-control.border.radius` | `29px` (`calc(button.border.radius 24px + focus.outline.width 2px + focus.outline.offset 2px + border.width 1px)`) | same |

That formula is sized so a child button's own focus ring never clips against the wrapper's corner.

**Where the contract ran out of answers:** no inter-item gap token exists.

## Visual picker item

`id: visual-picker-item`. 4 tokens, same count as segmented control. The surprise: checking an item changes only its border **width** (1px to 3px, `calc(border.width * 3)`), never its color; checked and unchecked use the exact same `border.color.interactive.@base`, the same shared gray input/select/segmented-control all use.

**Where the contract ran out of answers:** no swatch/image-area radius token.

## Reorderable list

`id: reorderable-list`. The smallest real token set tested, 3 tokens, 1 color. Only the drop-position indicator line has tokens at all: `color.accent.primary.@base` (the same accent used by button/toggle/link/message-bar), and a margin defined as literally equal to its own size (`{reorderable-list.indicator.size}`).

**Where the contract ran out of answers:** no actual drag-and-drop or keyboard reordering is encoded here, that's real JS behavior (HTML5 drag events, a ctrl+shift+up/down helper), not something either contract tracks; only the indicator's own look can be shown. The example item labels and the drag-handle glyph are invented sample content, same as every other section's placeholder text, not real Firefox strings.

## Page nav

`id: page-nav`, tag `moz-page-nav`. Nova's biggest real redesign found in this test: the non-nova file selects an item with a 4px accent indicator bar and a tinted background; nova's own sibling file explicitly zeroes the indicator's width and color (`width: 0`, `color: transparent`) and replaces it with a solid pill-shaped accent fill instead, two genuinely different visual languages for the same state.

| Token | Light | Dark |
|---|---|---|
| `moz-page-nav.button.background.color.selected` (nova) | `#764edd` | `#b89cff` |
| `moz-page-nav.button.text.color.selected` (nova) | `#ffffff` | `#252428` |
| `moz-page-nav.button.border.radius.@base` (nova) | `9999px` | `9999px` |
| `moz-page-nav.button.background.color.hover` | `#d2c8ec` | `#75669f` |

Hover/active colors are cited aliases straight to `button.background.color.hover`/`.active`, confirmed by the data, not an assumption like panel-item's.

**Where the contract ran out of answers:** `heading.logo.size` (24px) is real, the actual logo artwork isn't part of the contract.

## Fieldset

`id: fieldset`. Zero tokens, zero `cssProperties`, the same extreme as Chip, but real documented structure (legend, description, badge, inputs container) instead of nothing. Every spacing value a fieldset demo would need is invented; only its composed children (checkbox, badge) carry anything real.

**Where the contract ran out of answers:** total, not partial. No token traces the legend-to-description gap, the description-to-inputs gap, or the inputs' own gap. `inputsRole`'s real behavior (moves role/name/description/orientation onto the inputs container so they present as e.g. a radiogroup) is real documented JS behavior, not a visual fact.

## Box item, box button, box link

`id: box-item`, `id: box-button`, `id: box-link`. Three ids split one real file, `moz-box.tokens.json`, by dotted-path segment. Box item gets everything except the "button" segment (border, icon, padding); box button and box link both get ONLY the "button" segment, an identical export either way. That segment is a direct alias into `button.background/text.color.menu.*`, confirming the same family panel-item could only assume above is real.

| Token | Light | Dark |
|---|---|---|
| `moz-box.border.color` | `#b7b6ba` | `#949297` |
| `moz-box.button.background.color.hover` | `#d2c8ec` | `#75669f` |
| `moz-box.button.text.color.@base` (identical across hover/active/disabled) | `#161423` | `#fcfbff` |

**Where the contract ran out of answers:** `button.text.color.disabled` resolves to the exact same value as every other state; disabled presumably relies on opacity elsewhere, not a color token.

## Infobar

`id: infobar`, tag `notification-message`. component-api says it outright: this literally extends `moz-message-bar`. Its own 2-token file changes only two things from that base.

| Token | Light | Dark |
|---|---|---|
| `info-bar.border.color` | `#d2c8ec`, a Nova-ONLY custom pair, the token's own comment says so | `#3f3e42` |
| `info-bar.margin` | `0` (vs 4px in the non-nova default, the same kind of deliberate zeroing as page nav's indicator bar) | `0` |

**Where the contract ran out of answers:** `toolbarseparator.color` is exported alongside infobar in `id-map.json` but nothing in either component-api entry explains why a separator token rides along with a notification bar.

## Toolbox

`id: toolbox`, a real XUL tag with zero attributes worth documenting per its own component-api entry, pure tokens. The violet-to-orange window-chrome gradient is explicitly commented "only used for Nova" and "cannot be expressed in Figma."

| Token | Light | Dark |
|---|---|---|
| `toolbox.background.color.@base` | `#ffffff` | `#121114` |
| `toolbox.background.color.gradient-leading` | `#eaddff` | `#3e315f` |
| `toolbox.background.color.gradient-trailing` | `#ffdbc5` | `#701c07` |

**Where the contract ran out of answers:** the stored gradient formula's `color-mix()` calls are missing the required color-space argument (`color-mix({ref} 50%, transparent)`, not valid CSS as written); can't tell if that's a real upstream bug or a conversion-pipeline artifact from this repo.

## Table

Real tokens, **zero** component-api entry, the inverse of Link. 6 tokens: an accent-colored header and an alternating row stripe.

| Token | Light | Dark |
|---|---|---|
| `table.header.background.color` | `#764edd` | `#b89cff` |
| `table.header.text.color.@base` | `#ffffff` (confirmed identical in both schemes) | `#ffffff` |
| `table.row.background.color.alternate` | `#d6d5da` | `#312f33` |

**Where the contract ran out of answers:** nothing to say about sortable columns, row selection, or any attribute, because nothing tracks this as its own component.

## Toolbar

`id: toolbar`, the nav bar housing the url field. The url field's text has its own violet tint (`color.violet-desaturated.10`/`.70`), not the plain gray every other component in this test uses. Its focus border also drops Proton's `color-mix()` formula (real comment: "color-mix cannot be expressed in Figma") for a plain opaque accent color in nova.

| Token | Light | Dark |
|---|---|---|
| `toolbar.field.border.color.focus` | `#764edd` | `#b89cff` |
| `toolbar.field.text.color.@base` | `#3e315f` | `#e7e1f8` |
| `toolbar.padding.inline` (nova) | `6px` | `6px` |

**Where the contract ran out of answers:** the field's full-pill shape has no radius token.

## Toolbar button

`id: toolbar-button`, 30 tokens, the back/forward/reload-style icon buttons. Icon color never changes between `@base`, hover, and active, only the background and an inset outline (`outline-offset: -1px`, pulled inward) move. Hover and active backgrounds share the exact same RGB, only the alpha differs (0.25 vs 0.4).

| Token | Light | Dark |
|---|---|---|
| `toolbarbutton.icon.fill.@base` (same for hover/active) | `#75669f` | `#e7e1f8` |
| `toolbarbutton.background.color.hover` | `rgba(117, 102, 159, 0.25)` | `rgba(182, 170, 217, 0.25)` |
| `toolbarbutton.background.color.active` | `rgba(117, 102, 159, 0.4)` | `rgba(182, 170, 217, 0.4)` |
| `toolbarbutton.icon.fill.attention.@base` | `#764edd` | `#b89cff` |
| `toolbarbutton.badge.background.color` | `#961e3d` | `#ed566e` |

"Attention" (a highlighted icon) and "badge" (a numbered notification pill) are two separate, real mechanisms, easy to conflate, actually unrelated.

**Where the contract ran out of answers:** `padding.inner`/`outer` each have `@base`, `narrow`, `compact`, and a `touch` sub-axis, 7 real combinations total, not all exhaustively covered above.
