#!/usr/bin/env python3
"""figma-check.py: for every CSS custom property this wiki's Design tokens
table can show (across ALL component pages, not just one), record whether a
real, name-matching variable exists in Mozilla's actual "Nova Styles
(Experimental)" Figma file (key Co6vXnF5SiQMcJ7UoJvZX6).

Why this exists: index.html's "Design tokens" table (see buildCssPropertyRows
/ renderCssPropertyTable) already cross-references a documented CSS custom
property against a real token-api/*.tokens.json value. This script adds a
third leg: does that same name ALSO exist as a real Figma variable?

The actual question this answers is "are Figma and code in sync," not "can
this value be traced back to Figma somehow." If Figma doesn't have a variable
matching a CSS custom property's OWN name, that's a real "not synced"
finding, even if the value happens to be reachable through some other,
differently-named variable under the hood. This script only ever compares a
name against its own name -- no chain-following.

Source of truth: the direct Figma REST API, never Supernova, whose sync of
this same design system has known gaps elsewhere in this project family (its
own token detail couldn't confirm its source file, named "Desktop Styles",
was even the same file as "Nova Styles"). That rule holds for every
token/variable-existence-in-Figma check in this project family. See
figma-variables-dump.json's own `_comment` for exactly what was fetched and
why, and token-api/README.md's "Figma existence check" section for the full
pipeline.

How the match is decided (read this before trusting a "yes"):

1. codeSyntax was checked first, not assumed absent. The Figma API response
   DOES include a `codeSyntax` field per variable -- but only 2 of 718 kept
   variables have it populated (button/background/color, tab/border/color;
   see figma-variables-dump.json's `_comment`), nowhere near enough to be a
   general match signal. So every match below is by normalized name instead.
   If a future Figma publish starts populating codeSyntax broadly, prefer it
   over this name-matching and say so explicitly in `matchMethod`.

2. Name matching normalizes BOTH sides down to a plain tuple of lowercase
   words and compares those, instead of trying to reconstruct one naming
   convention from the other:
     - an acorn-contracts CSS custom property name like
       "--box-shadow-level-1-shadow-1-x" is stripped of its leading "--" and
       split on every "-" -> ("box","shadow","level","1","shadow","1","x")
     - a Figma variable name like "box/shadow/level-1/shadow-1/x" is
       lowercased and split on every "/" AND "-" the same way ->
       ("box","shadow","level","1","shadow","1","x")
   Splitting BOTH sides on every hyphen (not just slashes) is the load-
   bearing trick: acorn-contracts' own multi-word basenames (box-shadow,
   toolbar-button) collide with Figma's habit of nesting the same two words
   as separate path segments (box / shadow) otherwise. Flattening both to a
   word tuple sidesteps the segment-boundary mismatch entirely instead of
   hard-coding a list of which basenames are "really" two words. "@base"/
   "base" segments are dropped on both sides (mirrors deriveCssVarName() in
   index.html, which already drops a literal "@base" path segment when
   deriving a CSS custom property name).

3. Two outcomes, not three -- this is a strict sync check, not a "probably
   the same" guess:
   - "yes" (exact): the word tuples match exactly, in the same order. This
     is the overwhelming majority of real matches found (badge/background/
     color, button/background/color/active, border/color/interactive,
     tab/text/color/deemphasized, text/color/list/item/hover, ...).
   - "yes" (reordered): the word tuples match as a SET but not in the same
     order. token-api/README.md's own id-map.json documentation notes real
     precedent for this ("the same taxonomy level... can land at a
     different position in different token names"), so an order-insensitive
     match is still a real match, just flagged differently from an exact
     one so a maintainer can tell them apart.
   - anything else: "no", including a one-word-off near miss (e.g. an
     acorn name that's a real Figma variable's name plus one additional
     qualifier, or vice versa -- --box-button-background-color vs. the
     real button/background/color/menu variable, --badge-border-width vs.
     the real generic border/width variable). A near miss does NOT get its
     own third state: if it doesn't match something in Figma then it
     doesn't exist, which is the whole question. It is real, useful signal
     that two names have drifted, not a coin flip to hedge on, so it is
     recorded as "no" with matchType "near-miss" as a diagnostic.

     "No" overall is a real, common, and expected outcome beyond near
     misses too: this Figma file does not cover every acorn-contracts
     component family (no urlbar/panel/toolbar/sidebar/checkbox/moz-*
     semantic color groups were found in it at all, only their
     Dimension-type size/spacing tokens in some cases), so "no" for e.g.
     every --urlbar-* or --panel-* row is a real finding, not a bug in
     this script.

   Deliberately NOT done: resolving a token's own resolve.py alias chain
   (resolved/*.json already records one, e.g. --box-button-background-
   color's real value aliases through button.background.color.menu.@base)
   and counting a hit under that DIFFERENT name as a match for the
   original name. This check's whole point is catching Figma and code
   drifting apart by name, and backfilling a match through an
   indirectly-aliased, differently-named variable hides exactly the kind
   of drift it exists to surface. A CSS custom property either has a
   same-named Figma variable or it doesn't; what its resolved value
   happens to alias to under the hood is a separate question this column
   does not answer.

4. The design-system file itself: this now hits `Co6vXnF5SiQMcJ7UoJvZX6`,
   Figma's own "Nova Styles (Experimental)" file, directly -- no Supernova
   naming ambiguity to flag anymore. See figma-variables-dump.json's
   `sourceFile` field.

Inputs (all read-only, nothing here re-fetches from Figma):
  - id-map.json + component-api/*.json's `cssProperties` -> the exact same
    universe of distinct CSS custom property names index.html's own
    buildCssPropertyRows() would produce across EVERY component page, not
    just one (component-level token paths are read from resolved/*.json,
    the pre-resolved export resolve.py already produces from those same
    inputs, since its "tokens" keys are exactly the per-id effective token
    set buildCssPropertyRows() would show as rows).
  - figma-variables-dump.json -> the direct Figma variables/local snapshot
    (see that file's own `_comment` for exactly what was fetched, what was
    excluded, and why).

Output:
  - figma-token-map.json: { "--custom-property-name": {status, matchType,
    matchedPath} } for every distinct name, plus a `counts` summary.
    matchType is one of "exact", "reordered", "near-miss" or null, and
    index.html's loadFigmaTokenMap()/figmaCheckCell() consume it.

Rerunning: this script is pure local computation (no network), so re-run it
any time resolved/*.json, component-api/*.json, or figma-variables-dump.json
change:

    python3 token-api/figma-check.py

Refreshing figma-variables-dump.json itself is a plain, credential-scoped
REST call (no agent session or MCP connection needed at all): see
token-api/README.md's "Figma existence check" section for the exact command.
"""

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORD_RE = re.compile(r"[^a-z0-9]+")


def normalize_words(name):
    """Lowercase, strip a leading '--', split on every non-alphanumeric
    run (so '.', '/', '-', '@', whitespace all act as separators alike),
    drop empty pieces and a literal 'base' segment (the flattened form of
    '@base', which index.html's own deriveCssVarName() already drops when
    turning a token path into a CSS custom property name)."""
    s = name.strip().lower()
    if s.startswith("--"):
        s = s[2:]
    parts = [p for p in WORD_RE.split(s) if p and p != "base"]
    return tuple(parts)


def token_path_to_css_var(path):
    """The exact same rule as index.html's own deriveCssVarName(): the
    token path's dot-segments become dash-joined, "@base" is dropped
    entirely (not just blanked, since a naive string-replace leaves a
    dangling dash and, worse, does NOT strip a "moz-" first segment the way
    this does), and a "moz-" prefix on the FIRST segment only is stripped
    (moz-badge.background.color.@base -> --badge-background-color, not
    --moz-badge-background-color). Getting this wrong silently produces a
    CSS custom property name that doesn't exist anywhere on the real page,
    so every acorn-contracts name checked against Figma would miss by
    construction -- caught by cross-checking this script's own output
    against the live-rendered page in a browser (see token-api/README.md)."""
    segs = path.split(".")
    first = segs[0][4:] if segs[0].startswith("moz-") else segs[0]
    rest = [s for s in segs[1:] if s != "@base"]
    return "--" + first + ("-" + "-".join(rest) if rest else "")


def collect_acorn_css_property_names():
    """Every distinct CSS custom property name index.html's own
    buildCssPropertyRows() would show as a row, across ALL component pages,
    not just one: every token-backed name (from resolved/*.json, which
    already applied id-map.json's per-id basename rules the same way
    loadComponentTokens() does in index.html) plus every documented-but-not-
    necessarily-token-backed name (component-api/*.json's own
    `cssProperties`)."""
    names = set()
    resolved_dir = SCRIPT_DIR / "resolved"
    for f in sorted(resolved_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for path in data.get("tokens", {}):
            names.add(token_path_to_css_var(path))
    component_api_dir = REPO_ROOT / "component-api"
    skip = {"schema.json", "_meta.json", "drift-manifest.json"}
    for f in sorted(component_api_dir.glob("*.json")):
        if f.name in skip:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        for prop in data.get("cssProperties") or []:
            names.add(prop["name"])
    return names


def load_figma_words(dump):
    """Returns (exact_index, multiset_index, all_word_tuples) where
    exact_index maps an order-sensitive word tuple -> [original Figma
    variable names], and multiset_index maps a sorted (order-insensitive)
    word tuple -> [original variable names]. Both indexes are built from the
    same variable list, so a lookup that misses `exact_index` can still be
    checked against `multiset_index`."""
    exact_index = {}
    multiset_index = {}
    all_tuples = []
    for var in dump["variables"]:
        words = normalize_words(var["name"])
        if not words:
            continue
        exact_index.setdefault(words, []).append(var["name"])
        multiset_index.setdefault(tuple(sorted(words)), []).append(var["name"])
        all_tuples.append(words)
    return exact_index, multiset_index, all_tuples


def near_miss_path(acorn_words, all_tuples, exact_index):
    """Diagnostic only, does NOT affect status (see main(): a near miss is
    still a real 'no'). Some real Figma variable name whose word SET
    differs from the acorn name's word set by exactly one word, in either
    direction (one extra qualifier acorn has that Figma doesn't, or vice
    versa). Only considered when there is no exact or reordered match
    already (checked by the caller first). Returns the first such name
    found, or None if this is a total mismatch, not just a near one."""
    acorn_set = set(acorn_words)
    for words in all_tuples:
        candidate_set = set(words)
        diff = acorn_set.symmetric_difference(candidate_set)
        if len(diff) == 1 and len(acorn_set) > 1 and len(candidate_set) > 1:
            return exact_index[words][0]
    return None


def main():
    dump = json.loads((SCRIPT_DIR / "figma-variables-dump.json").read_text(encoding="utf-8"))
    exact_index, multiset_index, all_tuples = load_figma_words(dump)

    names = collect_acorn_css_property_names()
    results = {}
    counts = {"yes_exact": 0, "yes_reordered": 0, "no_near_miss": 0, "no_total_mismatch": 0}

    for name in sorted(names):
        words = normalize_words(name)
        if words in exact_index:
            results[name] = {
                "status": "yes",
                "matchType": "exact",
                "matchedPath": exact_index[words][0],
            }
            counts["yes_exact"] += 1
            continue
        sorted_words = tuple(sorted(words))
        if len(words) >= 2 and sorted_words in multiset_index:
            results[name] = {
                "status": "yes",
                "matchType": "reordered",
                "matchedPath": multiset_index[sorted_words][0],
            }
            counts["yes_reordered"] += 1
            continue
        # Still "no" either way -- near_miss_path is recorded as a
        # diagnostic (matchedPath/matchType "near-miss") so a maintainer
        # can spot a real systematic gap (e.g. an entire --tab-group-
        # *-invert family missing the exact same "invert" word), but it is
        # NOT a softer status than a total mismatch. See this file's
        # docstring, item 3, for why a near miss doesn't get its own state.
        near = near_miss_path(words, all_tuples, exact_index) if len(words) > 1 else None
        if near:
            results[name] = {"status": "no", "matchType": "near-miss", "matchedPath": near}
            counts["no_near_miss"] += 1
            continue
        results[name] = {"status": "no", "matchType": None, "matchedPath": None}
        counts["no_total_mismatch"] += 1

    out = {
        "generatedBy": "token-api/figma-check.py",
        "generatedFrom": "token-api/figma-variables-dump.json",
        "matchMethod": (
            "codeSyntax checked directly against this Figma file's own variable data and "
            "found populated on only 2 of 718 kept variables (nowhere near a usable general "
            "signal), so matching is by normalized-word-tuple comparison of the CSS custom "
            "property name against every real Figma variable name in Nova Styles "
            "(Experimental) (Co6vXnF5SiQMcJ7UoJvZX6), not codeSyntax. This checks a name "
            "against its OWN name only -- it deliberately does not follow a token's resolved "
            "alias chain to count a match under some other, differently-named Figma "
            "variable, since the point of this column is catching Figma and code drifting "
            "apart, and backfilling through an alias would hide exactly that. Strict "
            "two-state result (yes/no), not three: a one-word-off near miss is still 'no', "
            "recorded with matchType 'near-miss' purely as a diagnostic, not a softer status. "
            "See this script's own docstring for the full rule."
        ),
        "notes": [
            "Source is a direct Figma REST API pull (GET /v1/files/Co6vXnF5SiQMcJ7UoJvZX6/"
            "variables/local), never Supernova, whose sync of this design system has known "
            "gaps elsewhere in this project family. See figma-variables-dump.json's own "
            "`_comment` for what was fetched and excluded."
        ],
        "counts": {**counts, "total": len(names)},
        "properties": results,
    }
    out_file = SCRIPT_DIR / "figma-token-map.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    total_yes = counts["yes_exact"] + counts["yes_reordered"]
    total_no = counts["no_near_miss"] + counts["no_total_mismatch"]
    print(f"Checked {len(names)} distinct CSS custom property names against "
          f"{len(dump['variables'])} real Figma variable names.")
    print(f"  yes (exact match):      {counts['yes_exact']}")
    print(f"  yes (reordered match):  {counts['yes_reordered']}")
    print(f"  yes total:              {total_yes}")
    print(f"  no (near miss):         {counts['no_near_miss']} (diagnostic only, still a real 'no')")
    print(f"  no (total mismatch):    {counts['no_total_mismatch']}")
    print(f"  no total:               {total_no}")
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
