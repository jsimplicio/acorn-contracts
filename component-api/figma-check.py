#!/usr/bin/env python3
"""figma-check.py (component-api): for every tracked component-api entry,
report whether a real, name-matching COMPONENT or COMPONENT_SET exists in
Mozilla's actual "Nova Styles (Experimental)" Figma file, and which real
Figma components have no tracked match at all.

Why this exists, and why it is NOT Supernova: AGENTS.md used to say to
verify a component's Figma existence via the Supernova MCP's
sn_get_figma_component_list. That is Supernova's own *mirror* of Figma, and
token-api/figma-variables-dump.json's _comment already documents why that
mirror was rejected as a source for the token-level existence check: this
design system's own Supernova sync has known gaps elsewhere in this project
family (it mislabeled its own source file and could not confirm it was even
the same file as "Nova Styles"). The same reasoning applies here: this
script hits the real Figma file directly, via figma-components-dump.json
(a full pull via the Runlayer Figma MCP connector, see that file's own
_comment for exact provenance), never Supernova. Supernova stays usable for
one question only -- "does Supernova itself have a doc page for this" --
which is a different question from "does Figma have this."

Source pool: figma-components-dump.json's entries, with three kinds
excluded from matching (each flagged on the entry itself, not dropped at
dump time):
  - icons: true   -- the Icons page is 591 pure icon assets, never a
    component-api-shaped component.
  - sandbox: true -- draft/test pages, nothing shipped.
  - internal: true -- a leading "_" or "." is a real Figma convention for
    hide-from-Assets-panel/internal-only pieces (annotation helpers, layout
    grids, an Auto-Layout sub-part broken out of its own set), confirmed by
    inspecting what the 9 so-flagged entries actually are, not assumed from
    the naming convention alone.

Matching, same spirit as token-api/figma-check.py's word-tuple approach,
adapted for compound hierarchical names ("Panel List / MenuItem") instead
of flat CSS variable names:
  1. Flatten a name to a lowercase word tuple: split on "/", "-", "." and
     spaces, AND on camelCase boundaries (MenuItem -> Menu, Item), so a
     Figma path segment and a hyphenated component-api id normalize the
     same way.
  2. "yes (exact)": the tracked component's word tuple equals a real
     Figma name's word tuple, in the same order.
  3. "yes (reordered)": same words, different order.
  4. "no (near miss)": neither of the above, but the two word-sets' Jaccard
     overlap (intersection over union, not over the smaller set -- that
     would let a bare one-word name like "Urlbar" out-score a fuller, more
     specific match like "Urlbar / Identity box" on a tie) is at least
     0.5 -- diagnostic only, still a real "no". Printed so a human can tell
     "probably the same thing, naming drifted" apart from "nothing like
     this exists".
  5. "no (total mismatch)": no real overlap at all.

This is a REPORT, not an authority: it prints findings for a human to
triage against the real Figma file (names collide, one Figma set can cover
several tracked ids the way panel-list.figma.ts covers two components, a
tracked id can legitimately map to a differently-named Figma node the way
moz-input-color maps to "Color picker" -- see AGENTS.md's Code Connect
section for documented naming splits like that one). It writes nothing to
component-api/ or index.html; a flagged mismatch is a worklist item, not a
verdict to apply mechanically.

WHAT'S ACTUALLY NEW SINCE LAST CHECK, not just "currently unmatched": the
name-matching report above answers "does component-api agree with Figma
right now", which can't tell a component that has sat unmatched for months
apart from one Figma added yesterday. For that, this script also diffs the
real Figma pool (by Figma's own stable nodeId) against
figma-components-manifest.json from the last run -- same split as
check-drift.py's hash-manifest: a plain run is read-only and reports the
diff, `--advance` is what overwrites the manifest with this run's pool.
Only advance once the "new since last check" list has actually been
triaged, for the same reason check-drift.py's own README section gives:
advancing without looking spends the signal for free. The dump itself
(figma-components-dump.json) has to be re-pulled via the Runlayer Figma MCP
connector before each real check -- this script only diffs whatever dump
is currently on disk, it does not fetch.

Usage: python3 component-api/figma-check.py [--advance]
"""
import argparse
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DUMP_PATH = SCRIPT_DIR / "figma-components-dump.json"
MANIFEST_PATH = SCRIPT_DIR / "figma-components-manifest.json"
INDEX_HTML = REPO_ROOT / "index.html"

NEAR_MISS_OVERLAP = 0.5


def tracked_rows():
    """id/name/tagName for every row of index.html's own DATA array -- the
    same source of truth check-index-data.py's data_rows() reads, and the
    same regex-not-a-JS-engine approach, kept local rather than imported so
    this script has no dependency on another script's internals."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    start = html.index("const DATA = [")
    block = html[start:html.index("\n  ];", start)]
    rows = []
    for match in re.finditer(r"\{(.*?)\}", block, re.S):
        fields = re.findall(
            r"(\w+)\s*:\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|true|false)", match.group(1)
        )
        row = {key: (value[1:-1] if value[0] in "\"'" else value) for key, value in fields}
        if "id" in row:
            rows.append(row)
    return rows


def flatten(name):
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return tuple(w.lower() for w in re.split(r"[^A-Za-z0-9]+", name) if w)


def report_manifest_diff(pool):
    """What's actually new/removed in the real Figma file since the last
    --advance, keyed by Figma's own nodeId (stable across a rename; a plain
    name-keyed diff would report every rename as a delete+add)."""
    current = {e["nodeId"]: e for e in pool}
    if not MANIFEST_PATH.exists():
        print("No baseline yet (figma-components-manifest.json doesn't exist): "
              "every entry below is unestablished, not necessarily new. Triage "
              "this run, then re-run with --advance so the NEXT run can show "
              "true additions/removals instead of a flat snapshot.")
        return
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    prior = manifest.get("entries", {})
    added = [e for nid, e in current.items() if nid not in prior]
    removed = [e for nid, e in prior.items() if nid not in current]
    renamed = [(prior[nid]["name"], e["name"], e)
               for nid, e in current.items() if nid in prior and prior[nid]["name"] != e["name"]]
    if not (added or removed or renamed):
        print(f"No real additions/removals/renames since the baseline fetched "
              f"{manifest.get('fetchedAt', 'at an unrecorded time')}.")
        return
    print(f"Changes since the baseline fetched {manifest.get('fetchedAt', 'at an unrecorded time')}: "
          f"{len(added)} added, {len(removed)} removed, {len(renamed)} renamed.")
    for e in added:
        print(f"  + [{e['pageName']}] {e['name']} ({e['type']})")
    for e in removed:
        print(f"  - [{e.get('pageName', '?')}] {e['name']} ({e.get('type', '?')})")
    for old, new, e in renamed:
        print(f"  ~ [{e['pageName']}] \"{old}\" -> \"{new}\"")


def advance_manifest(pool, dump):
    MANIFEST_PATH.write_text(json.dumps({
        "fetchedAt": dump.get("fetchedAt", "unrecorded"),
        "entries": {e["nodeId"]: {"name": e["name"], "pageName": e["pageName"], "type": e["type"]}
                    for e in pool},
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Advanced figma-components-manifest.json with {len(pool)} entries.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--advance", action="store_true",
                         help="overwrite figma-components-manifest.json with this run's pool")
    args = parser.parse_args()

    dump = json.loads(DUMP_PATH.read_text(encoding="utf-8"))
    entries = dump["entries"]
    pool = [e for e in entries if not e["icons"] and not e["sandbox"] and not e["internal"]]
    skipped = len(entries) - len(pool)

    report_manifest_diff(pool)
    print()

    figma_tuples = {flatten(e["name"]): e["name"] for e in pool}

    rows = tracked_rows()
    print(f"Checked {len(rows)} tracked component-api entries against "
          f"{len(pool)} real Figma components/component sets "
          f"({skipped} excluded: icons, sandbox or internal-only).")

    exact = reordered = near = mismatch = 0
    near_lines, mismatch_lines, exact_disagree_lines, no_but_candidate_lines = [], [], [], []

    for row in rows:
        cid = row["id"]
        name = row.get("name", cid)
        tag = row.get("tagName", "")
        candidates = {flatten(name), flatten(cid.replace("-", " "))}
        if tag:
            candidates.add(flatten(tag.replace("moz-", "")))

        best = None
        for cand in candidates:
            if cand in figma_tuples:
                best = ("exact", figma_tuples[cand])
                break
        if best is None:
            for cand in candidates:
                if sorted(cand) in (sorted(c) for c in figma_tuples):
                    fname = next(f for t, f in figma_tuples.items() if sorted(t) == sorted(cand))
                    best = ("reordered", fname)
                    break
            # Score each candidate spelling against each real Figma name
            # SEPARATELY (never pool their words into one set first): a
            # component with multiple spellings -- display name, id, and a
            # tagName that doesn't share the "moz-" prefix, e.g. "tab"'s
            # tagName is "tabbrowser-tab" -- would otherwise leak words from
            # one spelling into another's score. That's exactly what first
            # broke this: pooling let "tabbrowser" drag "tab"'s real match
            # against "Tabstrip / Tab" down from a clean 50% to a diluted 33%.
            if best is None:
                best_overlap, best_match = 0.0, None
                for cand in candidates:
                    cset = set(cand)
                    if not cset:
                        continue
                    for ftuple, fname in figma_tuples.items():
                        fset = set(ftuple)
                        if not fset:
                            continue
                        # Jaccard (intersection/union), not intersection/min:
                        # min() lets a short bare word like "Urlbar" tie a
                        # fuller, more specific match like "Urlbar / Identity
                        # box" on the same overlap score. Jaccard's union
                        # denominator rewards the fuller match instead of
                        # picking whichever tied entry is iterated first.
                        overlap = len(cset & fset) / len(cset | fset)
                        if overlap > best_overlap:
                            best_overlap, best_match = overlap, fname
                if best_overlap >= NEAR_MISS_OVERLAP:
                    best = ("near", best_match, best_overlap)
                else:
                    best = ("mismatch", best_match, best_overlap)

        claimed = row.get("figma", "")
        kind = best[0]
        if kind == "exact":
            exact += 1
            if claimed == "no":
                exact_disagree_lines.append(
                    f"  {cid}: claimed figma=\"no\", but real Figma has \"{best[1]}\"")
        elif kind == "reordered":
            reordered += 1
            if claimed == "no":
                exact_disagree_lines.append(
                    f"  {cid}: claimed figma=\"no\", but real Figma has \"{best[1]}\" (reordered)")
        elif kind == "near":
            near += 1
            if claimed == "yes":
                near_lines.append(f"  {cid}: claimed figma=\"yes\", closest real match is only "
                                   f"\"{best[1]}\" ({best[2]:.0%} word overlap)")
            elif claimed == "no":
                no_but_candidate_lines.append(
                    f"  {cid}: claimed figma=\"no\", but \"{best[1]}\" is a {best[2]:.0%} "
                    f"word-overlap candidate -- check by eye, may be new or renamed upstream")
        else:
            mismatch += 1
            if claimed == "yes":
                mismatch_lines.append(
                    f"  {cid}: claimed figma=\"yes\", no real match found"
                    + (f" (closest: \"{best[1]}\", {best[2]:.0%} overlap)" if best[1] else ""))

    print()
    print(f"  yes (exact match):      {exact}")
    print(f"  yes (reordered match):  {reordered}")
    print(f"  no (near miss):         {near}  (diagnostic only, still a real 'no')")
    print(f"  no (total mismatch):    {mismatch}")

    if exact_disagree_lines:
        print()
        print(f"CLAIMED \"no\" BUT A REAL MATCH EXISTS ({len(exact_disagree_lines)}), "
              f"index.html's DATA is stale, needs a human to confirm and fix:")
        for line in exact_disagree_lines:
            print(line)

    if no_but_candidate_lines:
        print()
        print(f"CLAIMED \"no\" BUT A CANDIDATE MATCH EXISTS ({len(no_but_candidate_lines)}), "
              f"not proof (see near-miss rule above) but worth a human look -- this is how "
              f"a genuinely new or renamed upstream Figma component would first show up:")
        for line in no_but_candidate_lines:
            print(line)

    if mismatch_lines:
        print()
        print(f"CLAIMED \"yes\" BUT NO REAL MATCH FOUND ({len(mismatch_lines)}), "
              f"needs a human to re-check (name may have changed upstream in Figma):")
        for line in mismatch_lines:
            print(line)

    if near_lines:
        print()
        print(f"CLAIMED \"yes\" ON ONLY A NEAR MISS ({len(near_lines)}), "
              f"worth a second look:")
        for line in near_lines:
            print(line)

    tracked_tuples = set()
    for row in rows:
        tracked_tuples.add(flatten(row.get("name", row["id"])))
        tracked_tuples.add(flatten(row["id"].replace("-", " ")))
        if row.get("tagName"):
            tracked_tuples.add(flatten(row["tagName"].replace("moz-", "")))

    untracked = []
    for e in pool:
        ftuple = flatten(e["name"])
        if ftuple in tracked_tuples:
            continue
        fset = set(ftuple)
        if any(len(fset & set(t)) / len(fset | set(t)) >= NEAR_MISS_OVERLAP
               for t in tracked_tuples if t):
            continue
        untracked.append(e)

    print()
    print(f"REAL FIGMA COMPONENTS WITH NO TRACKED MATCH AT ALL ({len(untracked)}), "
          f"not necessarily a gap -- some are internal sub-parts of a tracked set, see "
          f"docstring -- but worth a human glance:")
    for e in untracked:
        print(f"  [{e['pageName']}] {e['name']} ({e['type']})")

    print()
    if args.advance:
        advance_manifest(pool, dump)
    else:
        print("Baseline NOT advanced (no --advance): re-run with --advance once the "
              "diff above has been triaged, so the next run reports only what's "
              "actually new.")


if __name__ == "__main__":
    main()
