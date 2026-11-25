#!/usr/bin/env python3
"""Convert a raw Figma variables/local response into token-api/figma-variables-dump.json.

Usage: python3 token-api/figma-dump.py <raw.json> [--allow-shrink]

The raw file is what MAINTAINING.md's curl writes. Only each variable's name,
resolvedType, collection name and remote flag are kept, Figma's
deletedButReferenced ghosts are dropped, and the names of variables with a
populated codeSyntax are listed, so no ids or keys reach the repo.
"""
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent / "figma-variables-dump.json"
FILE_NAME = "Nova Styles (Experimental)"

COMMENT = [
    f"Every real Figma variable in Mozilla's '{FILE_NAME}' file, from one REST call:",
    "GET /v1/files/$FIGMA_FILE_KEY/variables/local, converted by token-api/figma-dump.py.",
    "The Figma REST API directly, never Supernova, whose sync of this design system has",
    "known gaps. The file key is deliberately not committed.",
    "",
    "Kept per variable: name, type (resolvedType), collection (by name) and remote.",
    "Values, modes, aliases, ids and descriptions are dropped: figma-check.py matches",
    "names only. Variables Figma flags deletedButReferenced are listed separately and",
    "excluded, since they no longer exist as live variables and counting them would be",
    "a false 'exists in Figma'. codeSyntaxPopulated lists the variables whose codeSyntax",
    "is filled in. Re-running the fetch regenerates this file from scratch;",
    "see MAINTAINING.md's 'Figma checks' section.",
]


def main():
    args = [a for a in sys.argv[1:] if a != "--allow-shrink"]
    allow_shrink = len(args) != len(sys.argv) - 1
    if len(args) != 1:
        sys.exit(__doc__.strip().splitlines()[2])
    sys.argv[1:] = args
    try:
        raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"Could not read {sys.argv[1]} as JSON: {e}")
    if not isinstance(raw, dict) or raw.get("error") or "meta" not in raw:
        sys.exit("Not a variables/local response: " + (f"status {raw.get('status')}, {raw.get('message') or raw.get('err') or 'no meta block'}" if isinstance(raw, dict) else "not a JSON object"))
    meta = raw["meta"]
    if not isinstance(meta, dict):
        sys.exit("Not a variables/local response: meta is not an object")
    raw_collections = meta.get("variableCollections") or {}
    raw_vars = meta.get("variables") or {}
    if not isinstance(raw_collections, dict) or not isinstance(raw_vars, dict):
        sys.exit("Not a variables/local response: variables and variableCollections must be objects")
    all_vars = list(raw_vars.values())
    if not raw_collections:
        sys.exit("Not a variables/local response: no variableCollections")
    if not all(isinstance(v, dict) and isinstance(v.get("name"), str)
               and isinstance(v.get("variableCollectionId"), str)
               and isinstance(v.get("resolvedType"), (str, type(None))) for v in all_vars):
        sys.exit("Not a variables/local response: every variable needs a string name and "
                 "variableCollectionId, and a string or null resolvedType")
    collections = {cid: c["name"] if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"]
                   else "(unnamed collection)" for cid, c in raw_collections.items()}
    ghosts = sorted(v["name"] for v in all_vars if v.get("deletedButReferenced"))
    kept = sorted(
        ({
            "name": v["name"],
            "type": v.get("resolvedType"),
            "collection": collections.get(v.get("variableCollectionId"), "(unknown collection)"),
            "remote": bool(v.get("remote")),
        } for v in all_vars if not v.get("deletedButReferenced")),
        key=lambda x: (x["collection"], x["name"]),
    )
    if not kept:
        sys.exit("Response has no live variables; refusing to overwrite the dump with an empty one.")
    if OUT.is_file() and not allow_shrink:
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
            if not isinstance(existing, dict) or not isinstance(existing.get("variables"), list):
                raise ValueError("no variables list")
            before = len(existing["variables"])
        except (ValueError, AttributeError, TypeError):
            sys.exit(f"The existing {OUT.name} is not a valid dump; rerun with --allow-shrink to replace it.")
        if len(kept) < before / 2:
            sys.exit(f"Response has {len(kept)} live variables against {before} in the existing dump; "
                     "rerun with --allow-shrink if that drop is real.")
    out = {
        "_comment": COMMENT,
        "fetchedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fetchedBy": "GET https://api.figma.com/v1/files/$FIGMA_FILE_KEY/variables/local (X-Figma-Token header, see MAINTAINING.md)",
        "sourceFile": {"name": FILE_NAME, "key": "$FIGMA_FILE_KEY"},
        "totalVariablesInFile": len(all_vars),
        "excludedDeletedButReferenced": ghosts,
        "codeSyntaxPopulated": sorted(v["name"] for v in all_vars if not v.get("deletedButReferenced")
                                      and isinstance(v.get("codeSyntax"), dict) and any(v["codeSyntax"].values())),
        "variableCountByCollection": dict(sorted(Counter(v["collection"] for v in kept).items())),
        "variables": kept,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}: {len(kept)} variables kept, {len(ghosts)} deletedButReferenced excluded, "
          f"{len(out['variableCountByCollection'])} collections.")


if __name__ == "__main__":
    main()
