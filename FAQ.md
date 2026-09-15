# FAQ

These contracts document real Firefox, so they carry real Firefox vocabulary. This page defines the terms that turn up most often across `component-api/`, `guidance-api/` and `token-api/`, and answers the questions those terms tend to raise. Every entry is grounded in this repo or in mozilla-central; paths given without a link are paths in the Firefox tree.

## This repo

### Acorn

**Acorn is Firefox's design system, and it is what this repo is named after rather than what this repo documents.** Every entry here describes mozilla-central itself: the real component, the real guidance and the real tokens that ship in Firefox, joined per component by a stable `id`. The root `README.md` states the boundary directly: nothing here describes the Acorn prototype's own naming or structure.

## Classification

### `modern`, `classic`, `dual`, `none` and `missing`

**`modern` means Lit, `classic` means real but not Lit, and that is the whole test.** A `modern` entry reaches Lit directly (`extends MozLitElement`) or through a shared base that does, and everything else that is a real, shipping implementation is `classic`, so a current ES module like `panel-list.mjs` is `classic` because its classes are plain `extends HTMLElement`. The other three kinds cover what is not one implementation: `dual` is a modern and a classic implementation coexisting for the same concept (checkbox, radio, infobar), `none` is a real surface with no widget behind it at all (`panel-separator` is a plain `<hr>`), and `missing` is a concept with no real Firefox equivalent. Age is not the test and neither is the tag prefix; full definitions and the dividing lines are in [component-api/README.md](component-api/README.md).

### Why is something `classic` when it has a `moz-` name?

**Because the `moz-` prefix is naming, not architecture.** `moz-support-link` is `class MozSupportLink extends HTMLAnchorElement`, registered as `customElements.define("moz-support-link", MozSupportLink, { extends: "a" })` in `toolkit/content/widgets/moz-support-link/moz-support-link.mjs`. It is a customized built-in, and a customized built-in cannot be Lit, so it is `classic`: see `component-api/support-link.json`. `moz-label` is the same shape, `customElements.define("moz-label", MozTextLabel, { extends: "label" })`.

### Customized built-in vs autonomous custom element

**An autonomous custom element extends `HTMLElement` and gets its own tag name; a customized built-in extends a specific existing element class and is used with `is="..."` on that element's tag.** Lit can only produce the first kind: in the vendored bundle at `toolkit/content/widgets/vendor/lit.all.mjs`, `ReactiveElement` extends `HTMLElement` and `class LitElement extends ReactiveElement`, so there is no path from Lit to a subclass of `HTMLAnchorElement` or `XULElement`. Real customized built-ins in this inventory: `support-link`, `label`, `tab` and `tabstrip`.

## Tooling
### CEM (Custom Elements Manifest)

**CEM is the open-wc/webcomponents.org JSON schema for a custom element's API surface, and `component-api/` borrows its field vocabulary, not its pipeline.** `attributes`, `slots`, `events`, `methods`, `cssProperties`, `cssParts` and `default` are CEM's own spellings, which is why the field table and `component-api/schema.json` say so; the rest diverges on purpose, starting with `id` instead of tag name as the primary key, because several real entries have no tag at all. No CEM tool produced this data: there is no full-regeneration pipeline for `component-api/`, each entry was written by reading real source, and `check-drift.py` only reports and never writes an `<id>.json`. See [component-api/README.md](component-api/README.md).


### Storybook

**Storybook is the interactive component playground Firefox runs in-tree**, from `browser/components/storybook/`, with each component's stories in a `<name>.stories.mjs` file beside its source. It is the source for a number of `usage` examples in `component-api/`. `AGENTS.md` requires checking for a real `.stories.mjs` file rather than inferring a story from a directory existing.

### Supernova

**Supernova is the design-system documentation platform Mozilla keeps an instance of this design system in, and the Supernova column on the site's coverage tables records whether the real Firefox component has an entry in it**, checked against its component lists as `AGENTS.md` describes. For tokens it is deliberately not trusted: [token-api/README.md](token-api/README.md) sets the standing rule to always use the Figma REST API directly and never Supernova, because Supernova's sync of this design system has known gaps and its token detail could not confirm which Figma file it was even reading.

### Figma Code Connect

**Code Connect maps a Figma component to real code, so Figma's Dev Mode shows the actual snippet to write.** Firefox's mappings are `<name>.figma.ts` files, one beside each component that has a mapping, for example `toolkit/content/widgets/moz-button/moz-button.figma.ts`; `browser/components/storybook/docs/README.figma-code-connect.stories.md` is the in-tree guide. These files are one of the two accepted signals for `attributes[].figmaConfig` in `component-api/`, since they name the props a designer really configures.

## Web component vocabulary

### Lit

**Lit is the small reactive templating library Firefox vendors and builds its current components on.** It lives at `toolkit/content/widgets/vendor/lit.all.mjs`, with the vendoring setup under `toolkit/content/vendor/lit/`. Being Lit-based is exactly what makes a component `modern` here.

### MozLitElement

**`MozLitElement` is Firefox's own Lit base class, `export class MozLitElement extends LitElement` in `toolkit/content/widgets/lit-utils.mjs`.** It adds Firefox-specific behavior on top of Lit, notably automatic Fluent wiring for shadow roots and the `mapped` property option below.

### "Inherited from" and the shared bases

**A member described as "Inherited from X" is genuinely real on the component; it is just declared once on a shared base class instead of on the component itself.** The bases that show up are `MozBaseInputElement` and `MozBoxBase`, both `extends MozLitElement` in `toolkit/content/widgets/lit-utils.mjs`, and `MozInputText` (`extends MozBaseInputElement`, in `toolkit/content/widgets/moz-input-text/moz-input-text.mjs`), which the whole `moz-input-*` family extends in turn. On the classic side, `MozButtonBase` is `toolkit/content/widgets/button.js`'s `class MozButtonBase extends MozElements.BaseText`, exported as `MozElements.ButtonBase` and used by `toolbarbutton.js`. So `input-email`'s `label` reads "Inherited from MozBaseInputElement via MozInputText": you set it on `moz-input-email` as normal, the description simply lives with the class that defines it.

### Shadow DOM

**A separate DOM tree attached to an element, encapsulating its markup and styles from the surrounding page.** Lit renders into a shadow root by default, which is why attributes used inside a component's own template are not attributes on the host: see the `title` and `aria-label` entries in `component-api/button.json`, and `mapped` below for the mechanism. Events do not cross the shadow boundary on their own unless they are `composed`, so components re-dispatch the ones consumers need (`component-api/box-group.json`).

### `mapped`

**`mapped: true` on a Lit property declaration tells `MozLitElement` to accept a standard attribute on the host, remove it from the host, and apply it to an element inside the shadow tree.** That is why `component-api/` descriptions read "the `title` attribute, mapped onto the inner input", and why `moz-button` declares `title`, `accessKey` and its `aria*` properties as `{ type: String, mapped: true }`. The implementation is `createProperty` and `willUpdate` in `toolkit/content/widgets/lit-utils.mjs`, which also notes the attribute cannot be unset once set.

### Light DOM

**The ordinary DOM children of an element, as authored by the consumer, as opposed to the component's shadow tree.** A customized built-in such as `moz-support-link` has no shadow root at all, so all of its content is light DOM. `component-api/README.md`'s `cssParts` row is the place this distinction bites: a light-DOM component cannot expose real `::part()` names.

### Slot

**A `<slot>` in a component's template is a placeholder where the consumer's own light-DOM content is rendered.** `moz-button` renders a single default slot and listens on its `slotchange` to decide whether it has label text. The `slots` array in each `component-api/<id>.json` lists the real slots found in that component's render output, with the unnamed one recorded as `(default)`.

### Reflected attribute

**A property that writes its value back out to the matching HTML attribute, so the DOM and CSS can see it.** In Lit this is `reflect: true` in `static properties`: `moz-button` reflects `label`, `type`, `size`, `disabled`, `iconPosition` and `menuId`. Classic components do the same thing by hand through getters, setters and `attributeChangedCallback`, which is why `component-api/` descriptions say things like "reflected get/set property; observed attribute" (`component-api/panel-list.json`).

### Lifecycle callbacks

**`connectedCallback` runs when an element is inserted into the document, `disconnectedCallback` when it is removed, and `attributeChangedCallback` when an observed attribute changes.** Much of `guidance-api/` is about that timing rather than about the API: `panel-item`'s `submenu` is read once in `connectedCallback` and is not an observed attribute, so setting it later does nothing, and `moz-checkbox` captures `defaultChecked` there exactly once, so a value assigned afterwards is not what `form.reset()` restores. See `guidance-api/panel-item.json` and `guidance-api/checkbox.json`.

### `bubbles`, `cancelable` and `composed`

**Three properties of a dispatched event: `bubbles` lets it travel up through ancestors, `cancelable` lets a listener `preventDefault()` it, and `composed` lets it escape the shadow boundary.** `component-api/`'s `events` entries are only a name plus a description, so these words in the description are the whole contract: `moz-input-search`'s `MozInputSearch:search` is "Bubbling, composed", `dialog`'s `dialogaccept` and `dialogcancel` are "Cancelable", and `moz-box-group` re-dispatches `scroll` on the host because the shadow-tree original does not cross the boundary by itself.

### `aria-*`

**ARIA shows up in two shapes here.** On Lit components it is a camelCase property: `MozLitElement` turns `ariaLabel` into the `aria-label` attribute by inserting the hyphen after `aria`, and the result is `mapped` onto an inner control rather than left on the host, which is what `component-api/button.json` means by "used in shadow DOM and therefore not as an attribute on `moz-button`". On classic components it is a literal hyphenated observed attribute forwarded to an internal element, as with `panel-item`'s `aria-haspopup`.

## Firefox platform vocabulary

### Chrome

**Chrome is Firefox's own user interface, as opposed to web content, and has nothing to do with the browser named Chrome.** `build/docs/chrome-registration.md` defines it as "the set of user interface elements of the application window that are outside the window's content area": toolbars, menu bars, title bars. It is also the `chrome://` URL scheme those files are loaded through, as in the `iconsrc="chrome://global/skin/icons/settings.svg"` in `component-api/page-nav-item.json`'s usage example.

### XUL

**XUL is Mozilla's XML-based UI language, used for application artifacts like windows, popups, panels and menus rather than for pages.** Firefox is migrating to HTML where it can, but some elements still require XUL, notably anything that must be drawn outside a window's bounds; `browser/components/storybook/docs/README.xul-and-html.stories.md` is the in-tree explanation. The shared base is the mixin `MozElements.MozElementMixin` in `toolkit/content/customElements.js`, applied to whichever native class an element needs: `MozXULElement` is that mixin over `XULElement` and is what `findbar.js`'s `MozFindbar` and `dialog.js`'s `MozDialog` extend, while `panel.js`'s `MozPanel` applies it to `XULPopupElement` instead.

### `nsI*` interfaces

**Names beginning with `nsI` are XPCOM interfaces, declared in XPIDL (`.idl`) files and callable from both C++ and JavaScript.** `xpcom/docs/xpidl.md` is the reference for the language itself. The ones that appear in these contracts are `nsIFilePicker` (`widget/nsIFilePicker.idl`) and `nsIFile` (`xpcom/io/nsIFile.idl`), both in `component-api/input-folder.json`, which opens the native folder picker.

### Pref

**A pref is an entry in libpref, Firefox's key/value store, used for feature flags, user preferences and internal parameters alike.** `modules/libpref/docs/index.md` covers the design; defaults for Firefox ship in `browser/app/profile/firefox.js`. Components read prefs at runtime, which is why guidance entries warn about pref observers outliving the element (`guidance-api/tabstrip.json`).

### Places

**Places is Firefox's history and bookmarks system, a SQLite database plus a model-view-controller layer connecting it to the front end.** See `browser/components/places/docs/index.md`. It matters here because the bookmarks toolbar has no custom element: `PlacesToolbar extends PlacesViewBase` in `browser/components/places/content/browserPlacesViews.js` is a plain view class, manually constructed by `browser-places.js`, as documented in `component-api/bookmarks-toolbar.json`.

### CustomizableUI

**`CustomizableUI` is the module that registers toolbar areas and decides where widgets live and how overflow behaves**, at `browser/components/customizableui/CustomizableUI.sys.mjs`. `<toolbar>` has no JS class of its own, so its documented configuration is the set of attributes CustomizableUI reads off it: see `component-api/toolbar.json`.

### ASRouter

**ASRouter, the Activity Stream Router, is the component that decides which in-product message a user sees and when**, per `browser/components/asrouter/docs/messaging-glossary.md`, with the implementation at `browser/components/asrouter/modules/ASRouter.sys.mjs`. Several entries here are ASRouter message surfaces rather than widgets: `component-api/callout.json` (`FeatureCallout`) and `component-api/spotlight-modal.json` (`Spotlight`).

### SUMO

**SUMO is support.mozilla.org, Mozilla's support site.** `moz-support-link` exists to link to it: it builds its `href` from a `support-page` short-hand plus the `app.support.baseURL` pref, whose shipped default is `https://support.mozilla.org/1/firefox/%VERSION%/%OS%/%LOCALE%/`. See `component-api/support-link.json` and `guidance-api/support-link.json`.

## Design tokens

### Proton and Nova

**Nova is the current design-token generation, Proton the one before it.** Firefox ships both side by side in `toolkit/themes/shared/design-system/src/tokens/`, as paired files: `color.tokens.json` next to `color.nova.tokens.json`, `button.tokens.json` next to `button.nova.tokens.json`. "Proton" is the older Firefox UI generation generally, still visible in-tree in the shipped pref `browser.proton.toolbar.version` and in `MultiStageProtonScreen.jsx`; in `token-api/` it specifically means the non-`.nova.` half of a pair, and resolving `$value` alone silently gives you that half, which [token-api/README.md](token-api/README.md) explains at length.

### Design token

**A design token is one named design decision, stored as data so it can be consumed by CSS, by Figma and by anything else.** Firefox's live in `toolkit/themes/shared/design-system/src/tokens/{base,components}/`, plus a few component-local and theme-local locations listed in [token-api/README.md](token-api/README.md). Each one surfaces in the browser as a CSS custom property.

### DTCG

**DTCG is the [W3C Design Tokens Community Group](https://tr.designtokens.org/format/) format, the `$value`/`$type`/`$description` shape.** Firefox's own token files are in a Style-Dictionary-flavored format instead; `token-api/sync.py` converts them to DTCG, which is what `token-api/` publishes. The conversion rules, and the places where a Firefox value does not fit DTCG cleanly, are documented in [token-api/README.md](token-api/README.md).

### Alias

**An alias is a token whose value is a reference to another token, written in curly braces**, for example `"$value": "{color.accent.primary.@base}"` in `button.tokens.json`. Resolving one means following the chain to a literal, taking the correct theme branch at every hop rather than only the first: a reference such as `"light": "{color.violet-desaturated.20}"` sits inside a theme object inside a `nova` override, so the hop you follow depends on the context you are resolving for. The full resolution algorithm is in [token-api/README.md](token-api/README.md).

> **Note** "Alias" occasionally shows up in `component-api/` in an unrelated sense, meaning a legacy attribute value kept working as a synonym for another. `message-bar`'s `critical` type is one of these.

### What does the "In Figma" column actually check?

**Only whether a variable of the same name exists in Mozilla's Figma file. It says nothing about whether the values agree.** It is a name-vs-name existence check with a strict two-state `yes`/`no` answer, deliberately not following alias chains. The rule, the normalization, and why a row full of `no`s is a real finding rather than a bug are in [token-api/README.md](token-api/README.md)'s "Figma existence check: figma-check.py" section.

### Why do some tokens say they cannot round-trip to Figma?

**Because a few Firefox tokens are defined as context-dependent expressions, and no static format can hold one.** `text.color.deemphasized` is `color-mix(in srgb, currentColor 69%, transparent)`, which is neither a literal colour DTCG can represent nor a value Figma can bake without picking one context and being wrong in the others. [token-api/README.md](token-api/README.md)'s "Why some values cannot round-trip at all" names the layer that gives out in each case.

## Localization

### Fluent

**Fluent is Mozilla's localization system, and the one Firefox front-end code uses.** `intl/l10n/docs/fluent/tutorial.md` is the in-tree developer guide. Components integrate with it rather than holding English strings: `MozLitElement` connects Fluent to a component's render root automatically, and `moz-support-link` fills its own localized text via Fluent when no content is supplied.

### `data-l10n-id` and "Fluent id"

**A Fluent id is a message key in an `.ftl` file (FTL, Fluent Translation List, is Fluent's key-value message format), and `data-l10n-id` is the DOM attribute that binds an element to one.** Set `data-l10n-id="home-page-header"` and Fluent populates that element's text content and any localizable attributes from the message, as in `intl/l10n/docs/fluent/tutorial.md`. Several attributes in `component-api/` exist only to carry one, and `guidance-api/support-link.json` and `guidance-api/five-star.json` call out when setting it yourself overrides a component's own default.

### l10n

**l10n is the standard numeronym for "localization"** (`l`, 10 characters, `n`), as recorded in `intl/l10n/docs/glossary.md`. i18n for "internationalization" is the same construction.
