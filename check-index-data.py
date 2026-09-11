#!/usr/bin/env python3
"""check-index-data.py: assert index.html's DATA array and component-api/
still agree about the components they both describe.

The site's nav, home tables and per-item view are driven by a hardcoded
DATA array inside index.html, not by component-api/. That makes it a second
full inventory of the same components, and four of its nine fields (id,
kind, tagName, file) duplicate what component-api/<id>.json already says.
AGENTS.md opens by warning that adding a component means editing both and
that nothing errors if you forget, leaving it "fully documented in the data
but invisible in the UI". This is that missing error.

Four assertions, in descending order of how badly a violation hurts:

1. The id sets match exactly. An id in component-api/ but not DATA is the
   invisible-in-the-UI case AGENTS.md describes; the reverse is a nav entry
   pointing at a component with no contract behind it.
2. kind and tagName agree. These are small closed values with one right
   answer, so any difference is a real contradiction.
3. file agrees, path-aware. Both sides annotate this field with prose
   (DATA: "moz-button.mjs, icon-only variant"; component-api: a path plus a
   parenthetical), so raw strings can't be compared. Real paths are
   extracted from each side with the same regex index.html itself uses to
   linkify them, and the check is that they intersect. Entries where either
   side names no resolvable path are skipped, and `dual` entries are
   skipped entirely: DATA legitimately cites the classic implementation
   where component-api cites the modern one.

4. guidance-api coverage still matches GUIDANCE_GAPS. Guidance is authored
   by hand and does not cover every component, so the gap itself is
   expected; the gap changing without anyone noticing is not. Also catches
   an orphan: a guidance entry whose id matches no contract, meaning the
   join key points at nothing.

Known divergences live in EXCEPTIONS with a reason each, and are printed as
notes on every run rather than silently passing, so they stay visible until
someone decides them.

Usage: python3 check-index-data.py
Exits non-zero on any unexplained disagreement.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
COMPONENT_API = ROOT / "component-api"
GUIDANCE_API = ROOT / "guidance-api"
SKIP_NAMES = {"schema.json", "_meta.json", "drift-manifest.json"}

# component-api ids with no guidance-api entry, and why each one is left.
# Recorded here rather than described in guidance-api/README.md so that a
# new uncovered component fails this check instead of quietly making a
# sentence wrong.
#
# The moz-input-* five are empty subclasses of MozInputText: each is under
# 30 lines and its whole body is super.inputTemplate({ type: "email" }) or
# the equivalent. Every pitfall they have is MozInputText's, and
# input-text's own entry already records those two, so separate entries
# would be five copies of it.
GUIDANCE_GAPS = {
    "input-email",
    "input-number",
    "input-password",
    "input-tel",
    "input-url",
}

# Same pattern index.html uses at FILE_PATH_RE to decide what to linkify, so
# this check agrees with the page about what counts as a real path.
FILE_PATH_RE = re.compile(r"\b[\w.-]+(?:/[\w.-]+)+\.(?:mjs|jsx?|json|xhtml)\b")

# (id, field) -> why the two sides differ on purpose. Each is printed on
# every run; removing one should make the check pass, not fail.
EXCEPTIONS = {
    ("urlbar", "file"): (
        "Both are right about different things. DATA cites UrlbarInput.mjs, "
        "where moz-urlbar is really registered; component-api cites "
        "UrlbarInputBase.mjs, the 6,671-line class every documented field "
        "comes from. check-drift.py's tag check reports the same split."
    ),
}


def data_rows():
    """Every row of index.html's DATA array, as plain dicts. Parsed with a
    regex rather than a JS engine: the array is a flat list of object
    literals with bare keys and quoted string values, and keeping this
    dependency-free matters more here than tolerating arbitrary JS."""
    html = INDEX.read_text(encoding="utf-8")
    start = html.index("const DATA = [")
    block = html[start:html.index("\n  ];", start)]
    rows = []
    for match in re.finditer(r"\{(.*?)\}", block, re.S):
        fields = re.findall(
            r"(\w+)\s*:\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')", match.group(1)
        )
        row = {key: value[1:-1] for key, value in fields}
        if "id" in row:
            rows.append(row)
    return rows


def contracts():
    """id -> the real component-api entry."""
    out = {}
    for path in sorted(COMPONENT_API.glob("*.json")):
        if path.name in SKIP_NAMES or path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out[data["id"]] = data
    return out


def guidance_ids():
    """Every id with a real guidance-api entry."""
    return {
        path.stem
        for path in GUIDANCE_API.glob("*.json")
        if path.name not in SKIP_NAMES and not path.name.startswith("_")
    }


def guidance_problems(component_ids):
    """Where guidance coverage no longer matches what GUIDANCE_GAPS says.

    Two directions. An id with guidance but no contract is an orphan: the
    join key points at nothing. An id with neither guidance nor a place in
    GUIDANCE_GAPS is a new component whose guidance nobody has decided
    about yet, which is the case worth failing on."""
    have = guidance_ids()
    problems = []
    for cid in sorted(have - component_ids):
        problems.append((cid, "guidance entry with no component-api entry"))
    uncovered = component_ids - have
    for cid in sorted(uncovered - GUIDANCE_GAPS):
        problems.append((cid, "no guidance entry, and not a known gap"))
    for cid in sorted(GUIDANCE_GAPS - uncovered):
        problems.append((cid, "listed in GUIDANCE_GAPS but now has guidance; remove it from that set"))
    return problems, have, uncovered


def tag_set(value):
    """The real tag names in a tagName field, ignoring how it's annotated.
    Both sides record dual components as two tags in one string, but not
    identically: "button / moz-button" vs "button (classic) / moz-button
    (modern)"."""
    if not value:
        return frozenset()
    parts = (re.sub(r"\(.*?\)", "", p).strip() for p in value.split("/"))
    return frozenset(p for p in parts if p)


def main():
    rows = data_rows()
    real = contracts()
    by_id = {r["id"]: r for r in rows}
    problems = []

    print(f"index.html DATA: {len(rows)} rows. component-api/: {len(real)} entries.")
    if len(by_id) != len(rows):
        dupes = sorted({r["id"] for r in rows if list(by_id).count(r["id"])})
        problems.append(("(duplicate ids in DATA)", "id", ", ".join(dupes), ""))

    for cid in sorted(set(real) - set(by_id)):
        problems.append((cid, "id", "missing from index.html DATA",
                         "documented but invisible in the UI"))
    for cid in sorted(set(by_id) - set(real)):
        problems.append((cid, "id", "in DATA with no component-api entry",
                         "nav entry with no contract behind it"))

    for cid in sorted(set(real) & set(by_id)):
        row, entry = by_id[cid], real[cid]
        impl = entry["implementation"]

        if row.get("kind") != impl["kind"]:
            problems.append((cid, "kind", row.get("kind"), impl["kind"]))

        if tag_set(row.get("tagName")) != tag_set(entry.get("tagName")):
            problems.append((cid, "tagName", row.get("tagName"), entry.get("tagName")))

        # dual entries deliberately cite different implementations on each side
        if impl["kind"] != "dual":
            in_data = set(FILE_PATH_RE.findall(row.get("file") or ""))
            in_api = set(FILE_PATH_RE.findall(impl.get("file") or ""))
            if in_data and in_api and not (in_data & in_api):
                problems.append((cid, "file", ", ".join(sorted(in_data)),
                                 ", ".join(sorted(in_api))))

    known = [p for p in problems if (p[0], p[1]) in EXCEPTIONS]
    unknown = [p for p in problems if (p[0], p[1]) not in EXCEPTIONS]

    if known:
        print()
        print(f"Known divergences ({len(known)}), explained in EXCEPTIONS:")
        for cid, field, a, b in known:
            print(f"  {cid}.{field}: index.html={a!r} component-api={b!r}")
            print(f"    {EXCEPTIONS[(cid, field)]}")

    gaps, have, uncovered = guidance_problems(set(real))
    print()
    print(f"guidance-api/: {len(have)} entries, covering {len(real) - len(uncovered)} "
          f"of {len(real)} components, {len(uncovered)} known gap(s).")

    print()
    if unknown or gaps:
        if unknown:
            print(f"DISAGREEMENT ({len(unknown)}), index.html and component-api/ differ:")
            for cid, field, a, b in unknown:
                if field == "id":
                    print(f"  {cid}: {a} ({b})")
                else:
                    print(f"  {cid}.{field}: index.html={a!r} component-api={b!r}")
        if gaps:
            print(f"GUIDANCE COVERAGE ({len(gaps)}), changed since GUIDANCE_GAPS was written:")
            for cid, why in gaps:
                print(f"  {cid}: {why}")
        sys.exit(1)

    print("index.html DATA and component-api/ agree on every shared field, "
          "and guidance coverage matches GUIDANCE_GAPS.")


if __name__ == "__main__":
    main()
