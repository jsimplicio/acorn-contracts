#!/usr/bin/env python3
"""validate-schemas.py: check every entry in this repo against the schema
its own directory already ships.

All three APIs carry a real, machine-checkable JSON Schema (draft 2020-12),
and component-api/README.md describes its one as "validated against all real
entries". Nothing actually ran that validation: no script called it and no CI
job invoked it, so the claim rested on someone having checked once by hand.
A schema nothing runs is documentation, not a guard, and this repo's whole
premise is that its contracts are machine-readable.

What gets validated against what:

  component-api/*.json   -> component-api/schema.json
  guidance-api/*.json    -> guidance-api/schema.json
  token-api/base/*.json,
  token-api/components/* -> token-api/schema.json

Skipped everywhere: schema.json itself, _meta.json, drift-manifest.json, and
any _-prefixed file (guidance-api/_skeleton.json is an authoring template,
not an entry). token-api/resolved/ is deliberately not checked here; it is a
derived artifact with its own shape, already guarded by check-derived.yml
regenerating it and diffing.

Usage: python3 validate-schemas.py
Exits non-zero if any entry fails, printing each failure's file, JSON path
and message.
"""

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    sys.exit(
        "validate-schemas.py needs the jsonschema package:\n"
        "    python3 -m pip install jsonschema"
    )

ROOT = Path(__file__).resolve().parent

# (schema path, directories whose *.json files it validates)
TARGETS = [
    ("component-api/schema.json", ["component-api"]),
    ("guidance-api/schema.json", ["guidance-api"]),
    ("token-api/schema.json", ["token-api/base", "token-api/components"]),
]

SKIP_NAMES = {"schema.json", "_meta.json", "drift-manifest.json"}


def entries(dirname):
    """Every real entry file in a directory: not the schema, not metadata,
    not an _-prefixed authoring template."""
    for path in sorted((ROOT / dirname).glob("*.json")):
        if path.name in SKIP_NAMES or path.name.startswith("_"):
            continue
        yield path


def main():
    failures = []
    total = 0

    for schema_rel, dirs in TARGETS:
        schema = json.loads((ROOT / schema_rel).read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        checked = 0
        for dirname in dirs:
            for path in entries(dirname):
                checked += 1
                data = json.loads(path.read_text(encoding="utf-8"))
                for err in validator.iter_errors(data):
                    where = "/".join(str(p) for p in err.absolute_path) or "(root)"
                    failures.append((path.relative_to(ROOT), where, err.message))
        total += checked
        print(f"{schema_rel}: {checked} entries")

    print()
    if failures:
        print(f"INVALID ({len(failures)} error(s) across {total} entries):")
        for rel, where, message in failures:
            print(f"  {rel} at {where}")
            print(f"    {message}")
        sys.exit(1)

    print(f"All {total} entries validate against their schema.")


if __name__ == "__main__":
    main()
