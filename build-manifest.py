#!/usr/bin/env python3
"""Build manifest.json, the discovery entry point a consumer fetches first.

It answers one question per component: which of the three APIs actually
have a file for this id, and which token basenames back it. Everything is
read off the files on disk, so it cannot disagree with them.

This was hand-kept until 2026-09-16 and had gone wrong: eight components
gained guidance in "Write guidance for eight of the fourteen uncovered
components" and the manifest still said `guidanceApi: false` for all eight.
Four other derived files are generated and checked in CI while the one an
external consumer starts from was not, which is the wrong way round.

Run with --check to verify the committed file is current, the same
contract as update-meta.py and build-search-index.py.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "manifest.json")
SKIP = {"schema.json", "drift-manifest.json", "sync-manifest.json"}

# Bumped when a published field changes shape, so a consumer can detect it
# rather than breaking silently. See the Versioning note in README.md.
SCHEMA_VERSION = "1.0.0"

APIS = {
    "componentApi": "component-api/<id>.json",
    "guidanceApi": "guidance-api/<id>.json",
    "tokenApi": ("token-api/components/<basename>.tokens.json "
                 "(see token-api/id-map.json for id -> basename)"),
}


def ids_in(directory):
    out = set()
    for name in os.listdir(os.path.join(ROOT, directory)):
        if not name.endswith(".json") or name.startswith("_") or name in SKIP:
            continue
        out.add(name[:-5])
    return out


def basenames_for(cid, id_map):
    """The token basenames a component resolves to, per id-map.json's rules."""
    entry = id_map["map"].get(cid)
    if entry is None:
        return []
    if isinstance(entry, list):
        return list(entry)
    names = []
    for own in entry.get("own") or []:
        names.append(own["basename"] if isinstance(own, dict) else own)
    return names


def build():
    comp, guid = ids_in("component-api"), ids_in("guidance-api")
    with open(os.path.join(ROOT, "token-api/id-map.json"), encoding="utf-8") as f:
        id_map = json.load(f)
    tokens_dir = os.path.join(ROOT, "token-api/components")
    present = set(os.listdir(tokens_dir)) if os.path.isdir(tokens_dir) else set()

    components = {}
    for cid in sorted(comp | guid):
        names = basenames_for(cid, id_map)
        real = [n for n in names if f"{n}.tokens.json" in present]
        nova = [n for n in names if f"{n}.nova.tokens.json" in present]
        components[cid] = {
            "componentApi": cid in comp,
            "guidanceApi": cid in guid,
            "tokenApi": bool(real),
            "tokenBasenames": real,
            "novaTokenBasenames": nova,
        }
    return {"schemaVersion": SCHEMA_VERSION, "apis": APIS, "components": components}


def main():
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        current = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if current != text:
            print("manifest.json is stale, run: python3 build-manifest.py")
            return 1
        print(f"manifest.json is current ({len(json.loads(text)['components'])} components)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote manifest.json: {len(build()['components'])} components")
    return 0


if __name__ == "__main__":
    sys.exit(main())
