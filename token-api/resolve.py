#!/usr/bin/env python3
"""resolve.py: pre-resolve every component's real token values, for a
consumer who just wants the final answer without reimplementing the
resolution algorithm themselves.

Implements the exact algorithm documented in token-api/README.md's "How to
resolve a real token's value" section, step for step: build the base +
foundational lookup, layer Nova on top in a strict second pass, add each
component's own files (Nova winning there too), then walk every token's
$value to a literal, alias by alias, recording the hop chain.

This is a convenience export, not a new source of truth: base/, components/,
and id-map.json (written by sync.py, by hand, respectively) remain the real
data. Re-run this any time those change.

    python3 token-api/resolve.py

Writes one token-api/resolved/<id>.json per id that id-map.json's
"foundational" list or "map" actually resolves to a real file for (an id
with no real token coverage gets no output file, not an empty one).
"""

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ALIAS_RE = re.compile(r"^\{([^{}]+)\}$")
# Every {ref} anywhere in a value, not just a value that is entirely one.
# Used to report what resolution left behind, never to substitute: see the
# comment at the write site in resolve_component.
ALIAS_REF_RE = re.compile(r"\{([^{}]+)\}")
MAX_DEPTH = 12


def flatten(node, path_parts, out):
    """A leaf is any object with a $value key (DTCG shape), same rule as
    the wiki's own flattenTokens()."""
    if isinstance(node, dict) and "$value" in node:
        out[".".join(path_parts)] = node
        return
    if isinstance(node, dict):
        for key, sub in node.items():
            flatten(sub, path_parts + [key], out)


def promote_inline_nova(flat, stem):
    """input/moz-select/panel-item/panel-list nest Nova overrides under a
    literal "nova" key inside the base file instead of a sibling
    .nova.tokens.json. Promote onto the real path so it wins like any
    other Nova value, instead of showing up as a second, unmerged path."""
    prefix = f"{stem}.nova."
    for key in [k for k in flat if k.startswith(prefix)]:
        flat[stem + "." + key[len(prefix):]] = flat.pop(key)


def load_and_flatten(rel_path, stem_override=None):
    full = SCRIPT_DIR / rel_path
    if not full.is_file():
        return {}
    stem = stem_override or full.name[: -len(".tokens.json")]
    data = json.loads(full.read_text(encoding="utf-8"))
    out = {}
    flatten(data, [stem], out)
    promote_inline_nova(out, stem)
    return out


def build_base_lookup(id_map):
    """Step 1 + 2 of the README algorithm: non-nova base files and the
    foundational component files first, then every base-level nova file
    layered on top in a strict second pass (nova wins, never combined with
    step 1 in one pass, an intentional ordering, see README)."""
    lookup = {}
    for f in sorted((SCRIPT_DIR / "base").glob("*.tokens.json")):
        if ".nova." in f.name:
            continue
        lookup.update(load_and_flatten(f"base/{f.name}"))
    for name in id_map.get("foundational", []):
        lookup.update(load_and_flatten(f"components/{name}.tokens.json"))
    for f in sorted((SCRIPT_DIR / "base").glob("*.nova.tokens.json")):
        non_nova_stem = f.name[: -len(".nova.tokens.json")]
        lookup.update(load_and_flatten(f"base/{f.name}", stem_override=non_nova_stem))
    # The foundational component files get their nova siblings layered on in
    # this same second pass. Without it the shared lookup kept Proton values
    # for button.* and icon.*: icon.color.information is {color.blue.60} in
    # icon.tokens.json and {color.violet.50} in icon.nova.tokens.json, so
    # every component resolving through it exported a Proton blue.
    for name in id_map["foundational"]:
        lookup.update(
            load_and_flatten(f"components/{name}.nova.tokens.json", stem_override=name)
        )
    return lookup


# Same order sync.py's pick_default uses, so a nova branch reduced here and a
# $value reduced at conversion time can never disagree about which axis wins.
NOVA_PICK_ORDER = (
    "default",
    "brand",
    "light",
    "nativeTheme",
    "forcedColors",
    "platform",
    "prefersContrast",
    "dark",
)


def _pick(value):
    if not isinstance(value, dict):
        return value
    for key in NOVA_PICK_ORDER:
        if key in value:
            return _pick(value[key])
    for key, sub in value.items():
        if key != "comment":
            return _pick(sub)
    return None


def effective_value(token):
    """A token's real Nova value, which is not always its $value.

    38 tokens carry $extensions["org.mozilla.themes"].nova, shaped
    {comment?, value}: that branch is the Nova value and $value is the
    Proton one pick_default surfaced at conversion time. text.color.@base is
    the clearest case, $value is {color.gray.100} (a Proton grey) while its
    Nova value is {color.violet-desaturated.90}. Nova is what this export is
    written against, so the nova branch wins wherever a token has one.
    See token-api/README.md step 4b."""
    if not isinstance(token, dict):
        return None
    themes = (token.get("$extensions") or {}).get("org.mozilla.themes") or {}
    nova = themes.get("nova")
    if isinstance(nova, dict) and "value" in nova:
        return _pick(nova["value"])
    return token.get("$value")


def resolve_alias(value, lookup, depth=0):
    if depth > MAX_DEPTH or not isinstance(value, str):
        return value, []
    m = ALIAS_RE.match(value)
    if not m:
        return value, []
    path = m.group(1)
    target = lookup.get(path)
    if target is None:
        return f"{value} (unresolved)", []
    # effective_value, not $value: a chain has to take the Nova branch at
    # EVERY hop, or the last one quietly hands back a Proton value.
    inner_value, inner_chain = resolve_alias(effective_value(target), lookup, depth + 1)
    return inner_value, [path] + inner_chain


def load_basename_into(basename, lookup, effective):
    non_nova = load_and_flatten(f"components/{basename}.tokens.json")
    lookup.update(non_nova)
    # Firefox's own files refer to a moz-* component by its UNPREFIXED name:
    # moz-message-bar.tokens.json contains
    # "oklch(from {message-bar.icon.color} l c h / 20%)" and moz-toggle
    # aliases {toggle.dot.height}. Same convention the generated --var names
    # follow (moz-select -> --select-*). These extra lookup keys are what let
    # those resolve; they never reach `effective`, so an exported token path
    # stays the file's own real name.
    if basename.startswith("moz-"):
        bare = basename[len("moz-"):]
        lookup.update(load_and_flatten(f"components/{basename}.tokens.json", stem_override=bare))
        lookup.update(load_and_flatten(f"components/{basename}.nova.tokens.json", stem_override=bare))
    if effective is not None:
        effective.update(non_nova)
    # stem_override=basename, not the filename's own stem ("panel.nova"):
    # a nova sibling must land on the SAME keys as its non-nova
    # counterpart to actually overwrite them. Missing this the first
    # time silently produced base values dressed up as "resolved",
    # caught by checking panel.border.radius against the wiki's own
    # live-rendered value (24px, not what this bug produced).
    nova = load_and_flatten(f"components/{basename}.nova.tokens.json", stem_override=basename)
    lookup.update(nova)
    if effective is not None:
        effective.update(nova)


def resolve_component(id_, entry, base_lookup):
    """Steps 3-4: this id's own files (non-nova then nova, nova winning),
    merged into a copy of the base lookup, then every one of its own real
    tokens resolved against that merged lookup.

    `entry` is either a plain basename list (every basename is genuinely
    this id's own content) or {"own": [...], "resolve": [...]} when this
    id's own tokens alias into a basename that also has its own separate
    id/page elsewhere: "resolve" basenames are loaded into the lookup so
    those aliases still resolve, but never added to `effective`, so this
    id's resolved export doesn't duplicate the whole of another id's own
    token file. An "own" entry can also be {"basename": ..., "onlySegment":
    ...} for when this id's real tokens are a subset of a file that ALSO
    has its own separate id/page: only tokens with that exact segment
    somewhere in their dotted path are exported (Panel Separator is
    panel.separator.* inside panel.tokens.json; Icon Button is the 6
    button.*.icon.* tokens inside button.tokens.json, real Acorn taxonomy
    levels -- see token-api/README.md -- not a fixed position, since the
    taxonomy itself says not every level is present in every name), or
    {"basename": ..., "excludeSegments": [...]} for the OTHER id sharing
    that file, so the two partition it instead of one showing the other's
    content too (Tab excludes "group", Tab Group's own entry is the
    onlySegment "group" counterpart, both real separately-implemented
    widgets sharing one real tab.tokens.json). The whole file still feeds
    the lookup either way, only the exported subset is filtered."""
    own = entry if isinstance(entry, list) else entry["own"]
    resolve_only = [] if isinstance(entry, list) else entry.get("resolve", [])
    lookup = dict(base_lookup)
    effective = {}
    for own_entry in own:
        basename = own_entry if isinstance(own_entry, str) else own_entry["basename"]
        only_segment = None if isinstance(own_entry, str) else own_entry.get("onlySegment")
        exclude_segments = None if isinstance(own_entry, str) else own_entry.get("excludeSegments")
        if only_segment is None and exclude_segments is None:
            load_basename_into(basename, lookup, effective)
        else:
            scratch = {}
            load_basename_into(basename, lookup, scratch)
            kept = scratch.items()
            if only_segment is not None:
                kept = [(p, t) for p, t in kept if only_segment in p.split(".")]
            if exclude_segments is not None:
                kept = [(p, t) for p, t in kept if not any(s in p.split(".") for s in exclude_segments)]
            effective.update(dict(kept))
    for basename in resolve_only:
        load_basename_into(basename, lookup, None)
    if not effective:
        return None
    resolved = {}
    for path, token in sorted(effective.items()):
        value, chain = resolve_alias(effective_value(token), lookup)
        resolved[path] = {
            "value": value,
            "type": token.get("$type"),
            "chain": chain,
        }
        # ALIAS_RE is anchored, so a value holding more than one ref
        # ("{border.width} solid {button.border.color.@base}") is returned
        # untouched with an empty chain -- identical to how a plain literal
        # like "1px" is returned. A chain can also END on a composite, which
        # reads as more resolved than it is. Neither case is substituted
        # here: printing a composite unsubstituted is this project's
        # deliberate choice in two other places (resolve_alias above, and
        # index.html's substituteAliases, which is scoped to previews and
        # says so). What was wrong is claiming there was nothing to resolve,
        # so the refs left behind are stated instead. Read off the final
        # value, which covers both cases in one rule.
        refs = ALIAS_REF_RE.findall(value) if isinstance(value, str) else []
        if refs:
            resolved[path]["unresolvedRefs"] = list(dict.fromkeys(refs))
    return resolved


def main():
    id_map = json.loads((SCRIPT_DIR / "id-map.json").read_text(encoding="utf-8"))
    base_lookup = build_base_lookup(id_map)

    # Every id with a real basename list: id-map.json's own map, plus any id
    # that has its own <id>.tokens.json even without a map entry (the same
    # direct-match fallback the wiki itself uses).
    ids = dict(id_map.get("map", {}))
    all_mapped_basenames = set()
    for entry in ids.values():
        own = entry if isinstance(entry, list) else entry["own"]
        resolve_only = [] if isinstance(entry, list) else entry.get("resolve", [])
        all_mapped_basenames.update(o if isinstance(o, str) else o["basename"] for o in own)
        all_mapped_basenames.update(resolve_only)
    for f in (SCRIPT_DIR / "components").glob("*.tokens.json"):
        if ".nova." in f.name:
            continue
        stem = f.name[: -len(".tokens.json")]
        if stem not in ids and stem not in all_mapped_basenames:
            ids.setdefault(stem, [stem])

    out_dir = SCRIPT_DIR / "resolved"
    out_dir.mkdir(exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()

    written = 0
    for id_, entry in sorted(ids.items()):
        resolved = resolve_component(id_, entry, base_lookup)
        if resolved is None:
            continue
        own = entry if isinstance(entry, list) else entry["own"]
        own_basenames = [o if isinstance(o, str) else o["basename"] for o in own]
        out_file = out_dir / f"{id_}.json"
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump({"id": id_, "basenames": own_basenames, "tokens": resolved}, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        written += 1

    print(f"Wrote {written} resolved token files to {out_dir}")


if __name__ == "__main__":
    main()
