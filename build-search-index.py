#!/usr/bin/env python3
"""Build search-index.json, the corpus index.html's nav search reads.

One entry per real page in the site, holding only prose a human would
search for: descriptions, member docs, do's and don'ts, token names,
README bodies. Structural noise (types, file paths, JSON keys) is left
out on purpose -- it inflates the download and matches nothing anyone
means to search for.

Run with --check to verify the committed file is current; that is what
CI does, the same contract as update-meta.py.
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "search-index.json")

# Member groups worth indexing, in the order a reader meets them on the page.
MEMBER_GROUPS = ("attributes", "properties", "slots", "events", "methods",
                 "cssProperties", "cssParts")

DOC_PAGES = {
    "doc-component-api": ("Component API", "component-api/README.md"),
    "doc-guidance-api": ("Guidance API", "guidance-api/README.md"),
    "doc-token-api": ("Token API", "token-api/README.md"),
}


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def entries(pattern):
    """Every real contract file under a directory, skipping the machinery."""
    skip = {"schema.json", "drift-manifest.json", "sync-manifest.json"}
    for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
        name = os.path.basename(path)
        if name.startswith("_") or name in skip:
            continue
        yield path, load(os.path.relpath(path, ROOT))


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def strip_markdown(md):
    """README prose only: no fences, tables, links-as-URLs or heading marks."""
    md = re.sub(r"```.*?```", " ", md, flags=re.S)
    md = re.sub(r"`([^`]*)`", r"\1", md)
    md = re.sub(r"^\s*\|.*$", " ", md, flags=re.M)      # table rows
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)    # keep link text
    md = re.sub(r"^#{1,6}\s*", "", md, flags=re.M)
    md = re.sub(r"[*_>]", "", md)
    md = re.sub(r"\\(.)", r"\1", md)  # \" and friends, escapes for markdown, not for a reader
    return squash(md)


def build():
    pages = {}

    def page(pid, title, kind):
        return pages.setdefault(pid, {"title": title, "kind": kind, "text": []})

    for _, data in entries("component-api/*.json"):
        pid = data["id"]
        p = page(pid, data.get("name", pid), "Component")
        p["text"].append(data.get("description", ""))
        for group in MEMBER_GROUPS:
            for m in data.get(group) or []:
                if isinstance(m, dict):
                    p["text"].append(f'{m.get("name", "")} {m.get("description", "")}')

    for _, data in entries("guidance-api/*.json"):
        pid = data["id"]
        if pid not in pages:
            continue
        for group in ("dos", "donts"):
            for item in data.get(group) or []:
                pages[pid]["text"].append(item.get("text", ""))

    # A component's token names live on that component's page, so searching
    # for a token name finds the component that actually uses it. The four
    # resolved files with no component page (icon, table, opacity,
    # moz-reorderable-list) have nowhere to land and are skipped.
    for _, data in entries("token-api/resolved/*.json"):
        pid = data.get("id")
        if pid in pages:
            pages[pid]["text"].append(" ".join((data.get("tokens") or {}).keys()))

    # Token family pages: one per base/ file, matching the nav's Tokens
    # section. .nova. siblings fold into the same family, as they do there.
    families = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "token-api/base/*.tokens.json"))):
        stem = os.path.basename(path).replace(".nova", "")[: -len(".tokens.json")]
        names = []

        def walk(node, trail):
            if isinstance(node, dict):
                if "$value" in node:
                    names.append(".".join(trail))
                    return
                for key, child in node.items():
                    if not key.startswith("$"):
                        walk(child, trail + [key])

        walk(load(os.path.relpath(path, ROOT)), [stem])
        families.setdefault(stem, []).extend(names)

    for stem, names in families.items():
        p = page(f"tokens/{stem}", stem.replace("-", " ").title(), "Tokens")
        p["text"].append(" ".join(sorted(set(names))))

    for pid, (title, path) in DOC_PAGES.items():
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            page(pid, title, "Guide")["text"].append(strip_markdown(f.read()))

    for p in pages.values():
        p["text"] = squash(" ".join(p["text"]))

    return {"pages": pages}


def main():
    index = build()
    text = json.dumps(index, separators=(",", ":"), ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        current = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if current != text:
            print("search-index.json is stale, run: python3 build-search-index.py")
            return 1
        print(f"search-index.json is current ({len(index['pages'])} pages)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote search-index.json: {len(index['pages'])} pages, {len(text) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
