#!/usr/bin/env python3
"""Convert a raw Figma variables/local response into token-api/figma-variables-dump.json.

Usage: python3 token-api/figma-dump.py <raw.json>

The raw file is what MAINTAINING.md's curl writes. Only each variable's name,
resolvedType, collection name and remote flag are kept, and Figma's
deletedButReferenced ghosts are dropped, so no ids or keys reach the repo.
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
    "a false 'exists in Figma'. Re-running the fetch regenerates this file from scratch;",
    "see MAINTAINING.md's 'Figma checks' section.",
]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[2])
    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if raw.get("error") or "meta" not in raw:
        sys.exit(f"Not a variables/local response: status {raw.get('status')}, {raw.get('message') or raw.get('err') or 'no meta block'}")
    meta = raw["meta"]
    collections = {cid: c.get("name", cid) for cid, c in meta.get("variableCollections", {}).items()}
    all_vars = list(meta.get("variables", {}).values())
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
    out = {
        "_comment": COMMENT,
        "fetchedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fetchedBy": "GET https://api.figma.com/v1/files/$FIGMA_FILE_KEY/variables/local (X-Figma-Token header, see MAINTAINING.md)",
        "sourceFile": {"name": FILE_NAME, "key": "$FIGMA_FILE_KEY"},
        "totalVariablesInFile": len(all_vars),
        "excludedDeletedButReferenced": ghosts,
        "variableCountByCollection": dict(sorted(Counter(v["collection"] for v in kept).items())),
        "variables": kept,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}: {len(kept)} variables kept, {len(ghosts)} deletedButReferenced excluded, "
          f"{len(out['variableCountByCollection'])} collections.")


if __name__ == "__main__":
    main()
