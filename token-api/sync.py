#!/usr/bin/env python3
"""sync.py: pull Firefox's real design tokens and convert them to DTCG format.

WHAT THIS DOES
--------------
1. Fetches real token source files from the real upstream GitHub repo,
   https://github.com/mozilla-firefox/firefox, via a shallow, blobless,
   sparse-checkout `git` clone into a scratch temp directory. Firefox's real
   `*.tokens.json` files do NOT all live under one central directory: besides
   the central `toolkit/themes/shared/design-system/src/tokens/{base,
   components}/`, several real components colocate their own token file
   right next to their source (`toolkit/content/widgets/<component>/`), and
   two feature areas keep their own (`browser/themes/shared/tabbrowser/`,
   `browser/themes/shared/urlbar/`), found by a full-repo sweep of the real
   tree, not assumed. See SOURCE_ROOTS below for the exact list. Only these
   locations are fetched, not the rest of the ~mozilla-central tree. This is
   a real network fetch every run, not a copy of any pre-existing local
   checkout.
2. Walks every `*.tokens.json` file found in any of those locations
   (Firefox's native Style-Dictionary-flavored token format, see
   `toolkit/themes/shared/design-system/docs/README.design-tokens.stories.md`
   in that repo) and converts each token leaf into W3C DTCG shape
   (`$value`/`$type`/`$description`).
3. Writes one converted file per source file, under `token-api/base/` (only
   the central base/ files) or `token-api/components/` (the central
   components/ files AND every colocated file, flattened by basename, no
   two real files across all these locations share a basename, verified),
   so a human can diff a converted file against its source line-for-line.
4. Writes `token-api/sync-manifest.json` recording the exact upstream commit
   fetched, when, per-file/token counts, and each output file's real source
   path (since output no longer mirrors one single source tree), so a
   re-run is auditable.
5. Resolves the button -> space -> dimension alias chain
   (`button.padding.inline.@base` -> `space.large` -> `dimension.relative.100`)
   as a smoke test that the converted output is actually walkable, and prints
   the result.
6. Prints a "What's new since last sync" summary: commit/leaf-count deltas
   against the manifest this run just overwrote, plus a real `git diff
   --stat` against the last commit for the actual per-file changes.

See `token-api/README.md` for the full write-up of *why* each conversion rule
is shaped the way it is (the theme-dimension `$extensions` convention, the
`$type` inference rules, the `.@base` decision, etc). This docstring only
covers mechanics.

RERUNNING
---------
    python3 token-api/sync.py

Every run re-fetches the current tip of the upstream default branch (or
whatever `--ref` names) and overwrites `token-api/base/`,
`token-api/components/`, and the manifest. There is no manual step; this
script is the only supported way those directories get produced or updated.

Flags:
    --ref <branch-or-sha>     Fetch this ref instead of the default branch tip.
    --local-checkout <path>   DEV/TEST ONLY. Skip the network entirely and
                               read tokens straight out of an existing local
                               firefox checkout at <path>. Prints a loud
                               warning banner and records the bypass in the
                               manifest, because the real deliverable is the
                               network path above, this flag exists purely
                               to make iterating on the converter faster.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/mozilla-firefox/firefox"
SCRIPT_DIR = Path(__file__).resolve().parent

# Where real *.tokens.json files actually live upstream, found by sweeping a
# full local clone of REPO_URL with `find . -iname '*.tokens.json'` (not
# assumed from the central tree alone). Each entry is (repo-relative
# directory, output category). The central design-system pair is mandatory
# (sync fails loudly if either is missing after fetch); everything else is
# best-effort, colocated files are a real but less certain-to-persist
# pattern, so a location vanishing upstream is reported, not fatal.
SOURCE_ROOTS = [
    ("toolkit/themes/shared/design-system/src/tokens/base", "base", True),
    ("toolkit/themes/shared/design-system/src/tokens/components", "components", True),
    ("browser/themes/shared/tabbrowser", "components", False),
    ("browser/themes/shared/urlbar", "components", False),
    # Non-recursive: catches moz-box.tokens.json, which sits directly here
    # (shared by moz-box-item and moz-box-group) rather than in its own
    # component subdirectory like the rest of toolkit/content/widgets/.
    ("toolkit/content/widgets", "components", False),
]
# One level deeper under toolkit/content/widgets/: each real component's own
# subdirectory (moz-badge/, moz-toggle/, panel-list/, ...) may colocate its
# own *.tokens.json alongside its .mjs/.css. Walked separately from
# SOURCE_ROOTS above because it's a directory-of-directories glob, not a
# single flat directory, and most subdirectories have no tokens file at all.
WIDGET_COMPONENT_DIRS_ROOT = "toolkit/content/widgets"

# Sparse-checkout patterns (non-cone mode, gitignore-style globs) covering
# exactly the SOURCE_ROOTS above plus the one-level-deeper widget
# subdirectories, never the rest of toolkit/content/widgets/ (hundreds of
# unrelated .mjs/.css/.stories files that blob:none would otherwise fetch on
# checkout).
SPARSE_PATTERNS = [
    "toolkit/themes/shared/design-system/src/tokens/**",
    "browser/themes/shared/tabbrowser/*.tokens.json",
    "browser/themes/shared/urlbar/*.tokens.json",
    "toolkit/content/widgets/*.tokens.json",
    "toolkit/content/widgets/*/*.tokens.json",
]

# Theme-dimension keys Firefox uses inside a token's `value` object (see
# README.design-tokens.stories.md's "Theming" + "HCM media queries" sections).
# Priority order for picking the single "most typical" value to surface as
# top-level $value, most-canonical first. Recursed into when the picked entry
# is itself a nested theme object (e.g. `brand: {default: ...}`).
DEFAULT_PICK_ORDER = (
    "default",
    "brand",
    "light",
    "nativeTheme",
    "forcedColors",
    "platform",
    "prefersContrast",
    "dark",
)

# $type inference: exact path-segment membership, checked in this order.
# A path segment is one dotted component of the token's full name, namespace
# (filename stem) included, with any "@base" segments stripped first.
FONT_WEIGHT_SEGMENTS = {"weight"}
FONT_FAMILY_SEGMENTS = {"family"}
COLOR_SEGMENTS = {"color", "fill", "stroke"}
NUMBER_SEGMENTS = {"opacity"}
DIMENSION_SEGMENTS = {
    "space",
    "dimension",
    "padding",
    "gap",
    "size",
    "radius",
    "width",
    "height",
    "min-height",
    "min-width",
    "max-width",
    "inset",
    "offset",
    "margin",
}

ALIAS_RE = re.compile(r"^\{([^{}]+)\}$")
BORDER_SHORTHAND_RE = re.compile(r"(^|\s)solid(\s|$)")
# A value that IS a color, independent of whatever the token's own path says.
# Anchored to the start of the string so a value merely containing one of
# these deeper in a larger composite (a gradient's color-mix() ingredient,
# for instance) is correctly left alone for that composite's own handling.
COLOR_LITERAL_RE = re.compile(
    r"^(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(|oklab\(|lab\(|lch\(|color-mix\()"
)


class Report:
    """Accumulates stats/flags across the whole conversion run for the final summary."""

    def __init__(self):
        self.files = []  # (relative_path, leaf_count)
        self.leaf_total = 0
        self.theme_object_total = 0
        self.type_counts = {}
        self.omitted_type = []  # (dotted_path, reason)
        self.extra_keys = []  # (dotted_path, {key: value})
        self.pruned = []  # dotted paths dropped by prune_superseded_ramp_steps

    def note_type(self, t):
        self.type_counts[t] = self.type_counts.get(t, 0) + 1


def pick_default(value):
    """Given Firefox's theme-dimension-keyed `value` object (or a plain
    literal), return the single most-typical value to surface as $value.

    Rule (documented in README.md): prefer an explicit "default" key, else
    recurse into "brand" (itself often `{default: ...}`), else "light", else
    nativeTheme, forcedColors, platform (recursed), prefersContrast, dark, in
    that order, whichever theme axis is present first. Falls back to the
    first remaining key (skipping "comment") if none of the known axes are
    present, so this never raises on a shape we haven't seen.
    """
    if not isinstance(value, dict):
        return value
    for key in DEFAULT_PICK_ORDER:
        if key in value:
            return pick_default(value[key])
    for key, sub in value.items():
        if key != "comment":
            return pick_default(sub)
    return None


def infer_type(path_segments, value):
    """Infer a DTCG $type from a token's group path, or return (None, reason)
    when the case is genuinely ambiguous/composite and shouldn't be guessed.
    """
    if isinstance(value, str):
        v = value.strip()
        if BORDER_SHORTHAND_RE.search(v) and ("{" in v or any(c.isdigit() for c in v)):
            return None, "composite border shorthand (width+style+color as a flat string, not decomposed into DTCG's {width,style,color} border type)"
        if "," in v and "{" in v and re.match(r"^-?\d", v):
            return None, "composite shadow (multiple comma-separated layers as a flat string, not decomposed into DTCG's shadow type)"
        # A value can BE a color regardless of what its own token's path says.
        # Found by a full corpus scan: 70+ real tokens (tab.group.blue.@base,
        # tab.selected.textcolor, ...) hold a real color, either a literal
        # color function/hex or a pure alias straight into the base color
        # palette ({color.blue.50}), but their own path never spells out
        # "color" (segments like "group.blue.@base" or "selected.textcolor",
        # the latter one fused word, not two segments). Checking the value's
        # own shape catches these honestly, without guessing from an
        # unrelated path convention or following a multi-hop alias chain.
        if COLOR_LITERAL_RE.match(v):
            return "color", None
        alias_m = ALIAS_RE.match(v)
        if alias_m and alias_m.group(1).split(".")[0] == "color":
            return "color", None

    clean = [s for s in path_segments if s != "@base"]
    segset = set(clean)

    if segset & COLOR_SEGMENTS:
        return "color", None
    if "font" in segset and segset & FONT_WEIGHT_SEGMENTS:
        return "fontWeight", None
    if "font" in segset and segset & FONT_FAMILY_SEGMENTS:
        return "fontFamily", None
    if segset & NUMBER_SEGMENTS:
        return "number", None
    if segset & DIMENSION_SEGMENTS:
        return "dimension", None
    return None, "ambiguous group path, no type rule matched"


def convert_leaf(node, path_segments, report):
    """Convert one Firefox token leaf (a dict containing "value") to DTCG shape."""
    dotted = ".".join(path_segments)
    raw_value = node["value"]
    extra_keys = {k: v for k, v in node.items() if k not in ("value", "comment")}

    result = {}
    if isinstance(raw_value, dict):
        result["$value"] = pick_default(raw_value)
        result.setdefault("$extensions", {})["org.mozilla.themes"] = raw_value
        report.theme_object_total += 1
    else:
        result["$value"] = raw_value

    if "comment" in node:
        result["$description"] = node["comment"]

    t, reason = infer_type(path_segments, result["$value"])
    if t:
        result["$type"] = t
        report.note_type(t)
    else:
        report.omitted_type.append((dotted, reason))

    if extra_keys:
        result.setdefault("$extensions", {})["org.mozilla.meta"] = extra_keys
        report.extra_keys.append((dotted, extra_keys))

    report.leaf_total += 1
    return result


def convert_group(node, path_segments, report):
    """Recursively convert a Firefox token group. A dict with a "value" key is
    a leaf (Firefox's own convention); anything else is a nesting group."""
    if isinstance(node, dict) and "value" in node:
        return convert_leaf(node, path_segments, report)
    if isinstance(node, dict):
        return {
            key: convert_group(sub, path_segments + [key], report)
            for key, sub in node.items()
        }
    raise TypeError(
        f"unexpected non-dict at {'.'.join(path_segments)!r}: {node!r} "
        "(every group in Firefox's token format should be a plain object)"
    )


def fetch_via_github(ref, workdir):
    """Shallow, blobless, sparse-checkout clone of the real upstream repo,
    restricted to SPARSE_PATTERNS (every real *.tokens.json location, not
    one single subtree). Returns (commit_sha, commit_date_iso).

    Chosen approach: `git init` + `git remote add` + `git fetch --depth 1
    --filter=blob:none origin <ref>` + `git sparse-checkout set <patterns>`
    (non-cone mode, since these are gitignore-style file globs across several
    unrelated directories, not a small set of whole directories) + `git
    checkout FETCH_HEAD`. This works uniformly whether --ref is a branch name
    or a full commit SHA (GitHub supports fetching an exact SHA at depth 1),
    unlike `git clone --branch`, which only accepts branch/tag names.
    """
    def run(*args):
        subprocess.run(["git", "-C", str(workdir), *args], check=True)

    print(f"Fetching {ref or '(default branch)'} from {REPO_URL} ...", flush=True)
    subprocess.run(["git", "init", "-q", str(workdir)], check=True)
    run("remote", "add", "origin", REPO_URL)
    run("fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", ref or "HEAD")
    run("sparse-checkout", "init", "--no-cone")
    run("sparse-checkout", "set", *SPARSE_PATTERNS)
    run("checkout", "--quiet", "FETCH_HEAD")

    sha = subprocess.run(
        ["git", "-C", str(workdir), "rev-parse", "FETCH_HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    date = subprocess.run(
        ["git", "-C", str(workdir), "log", "-1", "--format=%cI", "FETCH_HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    print(f"Fetched commit {sha} ({date}) via real network clone of {REPO_URL}.")
    return sha, date


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default=None, help="branch or commit SHA to fetch (default: upstream default branch tip)")
    parser.add_argument("--local-checkout", default=None, help="DEV/TEST ONLY: read tokens from this local firefox checkout instead of fetching from GitHub")
    args = parser.parse_args()

    fetch_method = None
    commit_sha = None
    commit_date = None

    if args.local_checkout:
        print("=" * 70)
        print("WARNING: --local-checkout given. Skipping the real GitHub fetch")
        print("and reading tokens from a local directory instead. This is a")
        print("dev/test shortcut only, it is NOT the deliverable sync path.")
        print("=" * 70)
        repo_root = Path(args.local_checkout).resolve()
        if not repo_root.is_dir():
            sys.exit(f"error: {repo_root} does not exist")
        try:
            commit_sha = subprocess.run(
                ["git", "-C", str(args.local_checkout), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            commit_date = subprocess.run(
                ["git", "-C", str(args.local_checkout), "log", "-1", "--format=%cI"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
        except Exception:
            pass
        fetch_method = f"local-checkout-bypass:{args.local_checkout}"
        _run_conversion(repo_root, fetch_method, commit_sha, commit_date, args.ref)
    else:
        with tempfile.TemporaryDirectory(prefix="acorn-token-sync-") as tmp:
            commit_sha, commit_date = fetch_via_github(args.ref, Path(tmp))
            fetch_method = f"github-sparse-clone:{REPO_URL}"
            _run_conversion(Path(tmp), fetch_method, commit_sha, commit_date, args.ref)


def discover_source_files(repo_root):
    """Every real *.tokens.json file across all known locations (SOURCE_ROOTS
    plus one level deeper under toolkit/content/widgets/). Returns a list of
    (abs_path, output_category, mandatory) tuples."""
    found = []
    for rel_dir, category, mandatory in SOURCE_ROOTS:
        src_dir = repo_root / rel_dir
        if not src_dir.is_dir():
            if mandatory:
                sys.exit(f"error: expected {src_dir} to exist after fetch")
            print(f"  note: {rel_dir}/ not found upstream, skipping (not fatal, not a central location)")
            continue
        for src_file in sorted(src_dir.glob("*.tokens.json")):
            found.append((src_file, category, rel_dir))

    widgets_root = repo_root / WIDGET_COMPONENT_DIRS_ROOT
    if widgets_root.is_dir():
        for sub in sorted(p for p in widgets_root.iterdir() if p.is_dir()):
            for src_file in sorted(sub.glob("*.tokens.json")):
                rel_dir = f"{WIDGET_COMPONENT_DIRS_ROOT}/{sub.name}"
                found.append((src_file, "components", rel_dir))
    return found


def _load_prior_manifest():
    """Best-effort read of the manifest this run is about to overwrite, so
    the end-of-run summary can report what changed since last time."""
    path = SCRIPT_DIR / "sync-manifest.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


ALIAS_REF_RE = re.compile(r"\{([^{}]+)\}")


def _iter_tokens(node, path=()):
    """Every (dotted path, token) leaf in a converted tree."""
    if isinstance(node, dict) and "$value" in node:
        yield ".".join(path), node
        return
    if isinstance(node, dict):
        for key, sub in node.items():
            yield from _iter_tokens(sub, path + (key,))


def _lookup_path(tree, dotted):
    node = tree
    for seg in dotted.split("."):
        if not isinstance(node, dict) or seg not in node:
            return None
        node = node[seg]
    return node


def _live_under_nova(token):
    """The part of a token that still says anything under Nova.

    A token declaring a `nova` branch is fully described by it: its $value is
    the Proton value pick_default surfaced, and every non-nova theme branch
    belongs to that same superseded definition. Anything else keeps its
    $value and its theme branches, which are still live.
    """
    themes = (token.get("$extensions") or {}).get("org.mozilla.themes") or {}
    nova = themes.get("nova")
    if isinstance(nova, dict) and "value" in nova:
        return nova["value"]
    return {
        "value": token.get("$value"),
        "themes": {k: v for k, v in themes.items() if k != "nova"},
    }


def _collect_alias_refs(namespaces):
    """Every `{dotted.path}` that is still referenced under Nova.

    Deliberately not a scan of the raw JSON. Firefox ships both generations
    in the same files, so a blanket scan counts a reference that only exists
    in a superseded Proton definition, and that is enough to keep a dead
    token alive forever. Two things are skipped: a Proton token its own
    .nova sibling redefines outright, and the non-nova half of a token that
    carries its own `nova` branch.

    color.gray.100 is the worked example. A raw scan finds 10 tokens
    pointing at it; 8 of those are Proton definitions that Nova replaces
    (button.text.color.@base is {color.violet.90} in button.nova, and
    text.color.@base's nova branch is {color.violet-desaturated.90}), so only
    2 are real.
    """
    refs = set()
    for stem, tree in namespaces.items():
        nova_tree = None if stem.endswith(".nova") else namespaces.get(f"{stem}.nova")
        for path, token in _iter_tokens(tree):
            if nova_tree is not None and _lookup_path(nova_tree, path) is not None:
                continue
            fragment = _live_under_nova(token)
            for match in ALIAS_REF_RE.finditer(json.dumps(fragment)):
                refs.add(match.group(1))
    return refs


def _is_scale_group(members):
    """A group whose every member is a leaf token, i.e. a flat scale: a
    colour ramp (0, 10, ... 90) or a size scale (xsmall ... xxlarge, circle).

    This is the discriminator that keeps pruning off semantic tokens.
    background.color holds nested groups (box, list, dimmed), so it is not a
    scale and nothing under it is ever touched; border.radius is seven flat
    leaves, so it is. It matters because a scale's steps are meant to be one
    complete, consistent vocabulary, and a step Nova dropped from a scale it
    rewrote is genuinely superseded, whereas a semantic token Nova simply
    did not restate is still the live definition of that colour.
    """
    return bool(members) and all(
        isinstance(v, dict) and "$value" in v for v in members.values()
    )


def prune_superseded_scale_steps(namespaces, base_stems):
    """Drop Proton-era scale steps that Nova's version of the same scale
    replaced and nothing references any more.

    Firefox ships both generations side by side: color.tokens.json is the
    Proton ramp (0-110, oklch) and color.nova.tokens.json is the Nova one
    (0-90, hex), on different scales. index.html merges them key by key with
    Nova winning (the algorithm README.md documents), so a step Nova dropped
    is not removed, it survives from the Proton file and lands at the end of
    the Nova scale it does not belong to. That is why color.gray.100
    (#15141a) reads LIGHTER than color.gray.90 (#121114), and why
    border.radius.xxlarge is still listed when Nova has no such radius.

    Four guards keep this from deleting anything real:
      * base/ only. A component token's real consumer is CSS in
        mozilla-central, not another token, so "nothing aliases it" says
        nothing about whether it is live. Applying this to components/
        would delete ~45 real tokens (moz-toggle.dot.width, card.gap.compact
        and friends) that Nova simply does not restate.
      * only a group Nova actually rewrote. Nova defines no white/black
        group at all, so those are the only ramp there is and they stay.
      * only a flat scale (see _is_scale_group), never a semantic group.
      * only a step nothing anywhere references, nova branches included.
        color.gray.100 is still aliased by 8 real tokens with no Nova
        replacement, and border.radius.circle/large are aliased too, so all
        three stay rather than being deleted out from under their consumers.
    Returns the sorted paths dropped, for the run's own change summary.
    """
    refs = _collect_alias_refs(namespaces)
    dropped = []
    for stem, tree in namespaces.items():
        if stem not in base_stems:
            continue
        nova_tree = namespaces.get(f"{stem}.nova")
        if not isinstance(nova_tree, dict):
            continue
        for group, members in tree.items():
            nova_members = nova_tree.get(group)
            if not isinstance(members, dict) or not isinstance(nova_members, dict):
                continue
            if not _is_scale_group(members) or not _is_scale_group(nova_members):
                continue
            for key in [k for k in members if k not in nova_members]:
                path = f"{stem}.{group}.{key}"
                if path in refs:
                    continue
                del members[key]
                dropped.append(path)
    return sorted(dropped)


def _run_conversion(repo_root, fetch_method, commit_sha, commit_date, ref_arg):
    prior_manifest = _load_prior_manifest()
    report = Report()
    converted_namespaces = {}  # filename stem -> converted tree, for verification

    out_files = []
    pending_writes = []  # (category, filename, rel_dir, converted), written after pruning
    source_paths = {}  # output entry ("components/foo.tokens.json") -> real repo-relative source path

    # Clear previous output first -- a source file that disappears upstream
    # (or moves to a different category) must not leave a stale converted
    # file behind that this run no longer wrote.
    for category in ("base", "components"):
        out_dir = SCRIPT_DIR / category
        if out_dir.is_dir():
            for stale in out_dir.glob("*.tokens.json"):
                stale.unlink()

    source_files = discover_source_files(repo_root)
    seen_basenames = {}  # basename -> (category, source rel_dir), to catch any future collision loudly
    for src_file, category, rel_dir in source_files:
        if src_file.name in seen_basenames:
            prev_category, prev_rel_dir = seen_basenames[src_file.name]
            sys.exit(
                f"error: basename collision, {src_file.name} found in both "
                f"{prev_rel_dir}/ and {rel_dir}/, the flat components/ output "
                f"can't hold both, this needs a real disambiguation rule now"
            )
        seen_basenames[src_file.name] = (category, rel_dir)

        stem = src_file.name[: -len(".tokens.json")]
        with open(src_file, encoding="utf-8") as f:
            data = json.load(f)

        # A stem like "color.nova" (from color.nova.tokens.json) names two
        # things at once: the base namespace ("color") and the override
        # axis ("nova"). Split it so type inference sees "color" as its
        # own path segment instead of one opaque "color.nova" token.
        converted = convert_group(data, stem.split("."), report)
        converted_namespaces[stem] = converted
        pending_writes.append((category, src_file.name, rel_dir, converted))

    # Pruning compares a file against its own .nova sibling, so it can only
    # run once every file has been converted. That is why writing waits until
    # after this rather than happening inside the loop above.
    base_stems = {
        filename[: -len(".tokens.json")]
        for category, filename, _, _ in pending_writes
        if category == "base"
    }
    report.pruned = prune_superseded_scale_steps(converted_namespaces, base_stems)

    for category, filename, rel_dir, converted in pending_writes:
        out_dir = SCRIPT_DIR / category
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / filename, "w", encoding="utf-8") as f:
            json.dump(converted, f, indent=2, ensure_ascii=False)
            f.write("\n")

        leaf_count = _count_leaves(converted)
        out_entry = f"{category}/{filename}"
        report.files.append((out_entry, leaf_count))
        out_files.append(out_entry)
        source_paths[out_entry] = f"{rel_dir}/{filename}"

    # --- verification: walk the real button -> space -> dimension alias chain ---
    chain_ok, chain_trail, chain_value = _verify_chain(converted_namespaces)

    # --- manifest ---
    manifest = {
        "source": {
            "repo": REPO_URL,
            "source_roots": [f"{d} ({cat})" for d, cat, _ in SOURCE_ROOTS] + [f"{WIDGET_COMPONENT_DIRS_ROOT}/* (components, one level deep)"],
            "ref_requested": ref_arg or "(default branch)",
            "commit": commit_sha,
            "commit_date": commit_date,
            "fetch_method": fetch_method,
        },
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files_converted": out_files,
        "source_paths": source_paths,
        "leaf_token_total": report.leaf_total,
        "theme_object_total": report.theme_object_total,
        "type_counts": report.type_counts,
        "omitted_type_count": len(report.omitted_type),
        "omitted_type_examples": [
            {"path": p, "reason": r} for p, r in report.omitted_type
        ],
        "extra_key_flags": [
            {"path": p, "keys": k} for p, k in report.extra_keys
        ],
        "verification": {
            "chain": "button.padding.inline.@base -> space.large -> dimension.relative.100",
            "trail": chain_trail,
            "resolved_value": chain_value,
            "expected": "1rem",
            "ok": chain_ok,
        },
    }
    manifest_path = SCRIPT_DIR / "sync-manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # --- summary to stdout ---
    print()
    print(f"Converted {len(out_files)} files, {report.leaf_total} leaf tokens total.")
    print(f"  theme-dimension-keyed values (-> $extensions): {report.theme_object_total}")
    print(f"  $type assigned: {report.type_counts}")
    print(f"  $type omitted (ambiguous/composite, flagged): {len(report.omitted_type)}")
    print(f"  non-value/comment keys preserved (-> $extensions.org.mozilla.meta): {len(report.extra_keys)}")
    print()
    print("Verification chain: " + " -> ".join(chain_trail))
    print(f"  resolved value: {chain_value!r} (expected '1rem') -> {'OK' if chain_ok else 'FAILED'}")
    print()
    print(f"Manifest written to {manifest_path}")
    _print_change_summary(prior_manifest, manifest, out_files)
    if not chain_ok:
        sys.exit("verification chain FAILED, see output above")


def _print_change_summary(prior, current, out_files):
    """What's new since the last sync: commit/count deltas from the two
    manifests, plus a real git diff --stat for the actual content changes."""
    print()
    print("--- What's new since last sync ---")
    if prior is None:
        print("  (no prior sync-manifest.json found, nothing to compare against)")
        return

    old_commit = prior.get("source", {}).get("commit", "?")
    new_commit = current["source"]["commit"]
    print(f"  commit: {old_commit} -> {new_commit}")

    old_total = prior.get("leaf_token_total", 0)
    new_total = current["leaf_token_total"]
    print(f"  leaf tokens: {old_total} -> {new_total} ({new_total - old_total:+d})")

    old_files = set(prior.get("files_converted", []))
    new_files = set(out_files)
    for f in sorted(new_files - old_files):
        print(f"  + added:   {f}")
    for f in sorted(old_files - new_files):
        print(f"  - removed: {f}")

    try:
        diff = subprocess.run(
            ["git", "-C", str(SCRIPT_DIR), "diff", "--stat", "--",
             "base", "components", "sync-manifest.json"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if diff:
            print()
            print("  content changes vs last commit:")
            print("\n".join(f"  {line}" for line in diff.splitlines()))
    except Exception:
        pass  # not a git repo, or git unavailable; the counts above still stand


def _count_leaves(node):
    if isinstance(node, dict) and "$value" in node:
        return 1
    if isinstance(node, dict):
        return sum(_count_leaves(v) for v in node.values())
    return 0


def _resolve_path(namespaces, dotted_path):
    parts = dotted_path.split(".")
    ns = parts[0]
    if ns not in namespaces:
        raise KeyError(f"unknown token namespace {ns!r} (from path {dotted_path!r})")
    node = namespaces[ns]
    for seg in parts[1:]:
        if not isinstance(node, dict) or seg not in node:
            raise KeyError(f"segment {seg!r} not found while resolving {dotted_path!r}")
        node = node[seg]
    return node


def _resolve_value(namespaces, dotted_path, trail):
    trail.append(dotted_path)
    node = _resolve_path(namespaces, dotted_path)
    if not isinstance(node, dict) or "$value" not in node:
        raise ValueError(f"{dotted_path!r} resolved to a group, not a leaf token")
    val = node["$value"]
    if isinstance(val, str):
        m = ALIAS_RE.match(val.strip())
        if m:
            return _resolve_value(namespaces, m.group(1), trail)
    return val


def _verify_chain(namespaces):
    trail = []
    try:
        value = _resolve_value(namespaces, "button.padding.inline.@base", trail)
        return value == "1rem", trail, value
    except Exception as e:
        trail.append(f"ERROR: {e}")
        return False, trail, None


if __name__ == "__main__":
    main()
