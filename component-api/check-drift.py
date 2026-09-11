#!/usr/bin/env python3
"""check-drift.py: report which real Firefox source component-api tracks
has changed since last check, and which real toolkit/content/widgets/
components aren't tracked at all yet.

component-api/ has no rerunnable regeneration script (see its own
README: "regenerate by hand, or ask an agent to"), because writing a
correct *.json entry from real source needs a human/agent reading and
understanding that source, not a deterministic transform the way
token-api/sync.py's DTCG conversion is. This script doesn't try to do
that either. What it DOES do, mechanically:

1. For every component-api/<id>.json with a real `implementation.file`
   (skips `kind: "missing"` entries, which have no real file), fetches
   that exact file's current content via a real sparse git clone of
   mozilla-firefox/firefox and hashes it. Compares against the hash
   stored in component-api/drift-manifest.json from the last run;
   anything different means the real source moved since component-api
   was last checked against it.
   The manifest records each id's file path alongside its hash, so
   repointing an entry at a different file is reported as exactly that
   rather than as upstream movement: the two hashes belong to two
   different files and comparing them says nothing.
2. Lists the real current contents of toolkit/content/widgets/ (flat
   files and one-level-deep component subdirectories, same shape
   token-api/sync.py's own WIDGET_COMPONENT_DIRS_ROOT already
   documents) and flags any real .mjs/.js file there that no tracked
   component's implementation.file points at: a real widget with no
   component-api entry at all yet.
3. For every entry carrying a tagName, checks that the cited file really
   registers it via customElements.define(). A file can sit unchanged at
   its recorded path while no longer defining the tag the entry claims,
   which neither the hash nor the existence check can see. Where the tag
   turns up in a sibling file instead, that file is named: registration
   is sometimes deliberately split out from the class holding the API,
   so the citation is usually still correct and only the check is naive.

Prints a report and writes component-api/drift-manifest.json (this run's
hashes, for next run's comparison). Does not touch any component-api/
*.json content itself; the report is the starting point for the actual
re-derivation work (by hand or by an agent), not a replacement for it.

Usage: python3 component-api/check-drift.py [--ref <branch-or-sha>]
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/mozilla-firefox/firefox"
SCRIPT_DIR = Path(__file__).resolve().parent
WIDGETS_ROOT = "toolkit/content/widgets"


def load_tracked_components():
    """id -> {file, kind, tagName} for every component-api/<id>.json with a real file."""
    tracked = {}
    for path in sorted(SCRIPT_DIR.glob("*.json")):
        if path.name in ("schema.json", "_meta.json", "drift-manifest.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        impl = data.get("implementation", {})
        if impl.get("kind") == "missing":
            continue
        file = impl.get("file")
        if file:
            tracked[path.stem] = {
                "file": file,
                "kind": impl.get("kind"),
                "tagName": data.get("tagName"),
            }
    return tracked


def defines_tag(source, tag):
    """Whether source really registers this exact tag name via
    customElements.define("<tag>", ...). \\s* spans newlines so a
    prettier-wrapped multi-line call still matches."""
    pattern = r"""customElements\.define\(\s*["']%s["']""" % re.escape(tag)
    return re.search(pattern, source) is not None


def prior_entry(prior_entries, cid):
    """(file, hash) this id was last recorded against, or (None, None) if
    it wasn't. Manifests written before the file path was recorded store a
    bare hash string; those yield a None file, which just skips the
    repoint comparison for that id until the next run rewrites it."""
    value = prior_entries.get(cid)
    if value is None:
        return None, None
    if isinstance(value, str):
        return None, value
    return value.get("file"), value.get("hash")


def tag_candidates(tag_name):
    """Every real tag name recorded in one entry's tagName field. A few
    dual entries record both of theirs in a single string, sometimes with
    a parenthetical: "moz-checkbox / checkbox", "button (classic) /
    moz-button (modern)". Any one of them really being defined in the
    cited file makes that citation coherent."""
    out = []
    for part in tag_name.split("/"):
        part = re.sub(r"\(.*?\)", "", part).strip()
        if part:
            out.append(part)
    return out


def find_tag_definer(repo_root, tag):
    """Which really-fetched file registers this tag, when the cited one
    doesn't. Turns a bare miss into an actionable report: a tag can sit in
    a thin subclass file next to the base class holding the real API
    (moz-urlbar is defined in a 12-line UrlbarInput.mjs beside the
    6,671-line UrlbarInputBase.mjs that every entry field comes from), in
    which case the citation is right and only this check is naive."""
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix not in (".mjs", ".js"):
            continue
        if defines_tag(path.read_text(encoding="utf-8", errors="ignore"), tag):
            return str(path.relative_to(repo_root))
    return None


def fetch_sources(ref, workdir, patterns):
    """Real shallow, blobless, sparse-checkout clone, same technique as
    token-api/sync.py's fetch_via_github, just with our own patterns."""
    def run(*args):
        subprocess.run(["git", "-C", str(workdir), *args], check=True)

    print(f"Fetching {ref or '(default branch)'} from {REPO_URL} ...", flush=True)
    subprocess.run(["git", "init", "-q", str(workdir)], check=True)
    run("remote", "add", "origin", REPO_URL)
    run("fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", ref or "HEAD")
    run("sparse-checkout", "init", "--no-cone")
    run("sparse-checkout", "set", *patterns)
    run("checkout", "--quiet", "FETCH_HEAD")

    sha = subprocess.run(
        ["git", "-C", str(workdir), "rev-parse", "FETCH_HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    print(f"Fetched commit {sha} via real network clone of {REPO_URL}.")
    return sha


def discover_widget_files(repo_root):
    """Every real component under toolkit/content/widgets/ (flat and one
    level deep) that actually defines a custom element, as repo-relative
    path strings. Filters out .stories.mjs (Storybook demos, not the
    component) and shared helpers like lit-utils.mjs by content, not name:
    only a file containing a real customElements.define(...) call counts,
    since that's the actual signal a Storybook/vendor/legacy-XUL-helper
    file lacks."""
    root = repo_root / WIDGETS_ROOT
    candidates = []
    if not root.is_dir():
        return []
    for pattern in ("*.mjs", "*.js"):
        candidates += [(f"{WIDGETS_ROOT}/{p.name}", p) for p in root.glob(pattern) if ".stories." not in p.name]
    for sub in root.iterdir():
        if not sub.is_dir() or sub.name == "vendor":
            continue
        for pattern in ("*.mjs", "*.js"):
            candidates += [(f"{WIDGETS_ROOT}/{sub.name}/{p.name}", p) for p in sub.glob(pattern) if ".stories." not in p.name]

    found = [rel for rel, p in candidates if "customElements.define(" in p.read_text(encoding="utf-8", errors="ignore")]
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default=None, help="branch or commit SHA to fetch (default: upstream default branch tip)")
    args = parser.parse_args()

    tracked = load_tracked_components()
    manifest_path = SCRIPT_DIR / "drift-manifest.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    prior_entries = prior.get("entries") or prior.get("hashes", {})

    # A few real entries (e.g. split-button) cite more than one source in
    # prose rather than a single clean path; skip those for hashing rather
    # than false-flagging them as "moved upstream".
    uncheckable = {cid: info["file"] for cid, info in tracked.items() if " " in info["file"]}
    tracked = {cid: info for cid, info in tracked.items() if cid not in uncheckable}

    # Each tracked file's own directory comes along too, so a tag that
    # isn't in the cited file can still be traced to the sibling that
    # really defines it rather than just reported as missing.
    tracked_dirs = sorted({str(Path(info["file"]).parent) for info in tracked.values()})
    patterns = sorted({info["file"] for info in tracked.values()}) + [
        f"{WIDGETS_ROOT}/*.mjs", f"{WIDGETS_ROOT}/*.js",
        f"{WIDGETS_ROOT}/*/*.mjs", f"{WIDGETS_ROOT}/*/*.js",
    ] + [f"{d}/*.mjs" for d in tracked_dirs] + [f"{d}/*.js" for d in tracked_dirs]

    with tempfile.TemporaryDirectory(prefix="acorn-drift-check-") as tmp:
        repo_root = Path(tmp)
        commit_sha = fetch_sources(args.ref, repo_root, patterns)

        new_entries = {}
        changed = []
        repointed = []
        missing_upstream = []
        tag_checked = 0
        tag_missing = []
        for cid, info in tracked.items():
            src = repo_root / info["file"]
            if not src.is_file():
                missing_upstream.append((cid, info["file"]))
                continue
            digest = hashlib.sha256(src.read_bytes()).hexdigest()
            new_entries[cid] = {"file": info["file"], "hash": digest}
            prior_file, prior_hash = prior_entry(prior_entries, cid)
            if prior_hash is None:
                pass
            elif prior_file is not None and prior_file != info["file"]:
                # This repo repointed the citation; the two hashes belong to
                # two different files, so comparing them says nothing about
                # whether upstream moved.
                repointed.append((cid, prior_file, info["file"]))
            elif prior_hash != digest:
                changed.append((cid, info["file"]))
            # A file can still exist at its recorded path while no longer
            # defining the tag this entry claims for it: renamed element,
            # registration moved to another file, or a citation that was
            # always pointing one file off. The hash check can't see that.
            if info["tagName"]:
                tag_checked += 1
                source = src.read_text(encoding="utf-8", errors="ignore")
                candidates = tag_candidates(info["tagName"])
                if not any(defines_tag(source, t) for t in candidates):
                    tag_missing.append((cid, candidates, info["file"]))

        # Where each missed tag really lives, looked up once per miss.
        tag_missing = [
            (cid, candidates, file, next(
                ((t, d) for t in candidates if (d := find_tag_definer(repo_root, t))), None
            ))
            for cid, candidates, file in tag_missing
        ]

        tracked_files = {info["file"] for info in tracked.values()}
        untracked = [f for f in discover_widget_files(repo_root) if f not in tracked_files]

    manifest_path.write_text(
        json.dumps({"commit": commit_sha, "entries": new_entries}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"Checked {len(tracked)} tracked components against commit {commit_sha}.")
    print()
    if changed:
        print(f"CHANGED since last check ({len(changed)}), real source moved, needs a re-check:")
        for cid, file in changed:
            print(f"  {cid}: {file}")
    else:
        print("No tracked component's real source changed since last check.")
    print()
    if repointed:
        print(f"REPOINTED ({len(repointed)}), this repo changed the citation, not upstream:")
        for cid, old_file, new_file in repointed:
            print(f"  {cid}: {old_file} -> {new_file}")
        print()
    if tag_missing:
        print(f"TAG NOT FOUND ({len(tag_missing)} of {tag_checked} checked), cited file exists but does not define this tag:")
        for cid, candidates, file, definer in tag_missing:
            print(f"  {cid}: no customElements.define for {' / '.join(candidates)} in {file}")
            if definer:
                print(f"    really defined in {definer[1]}")
            else:
                print("    not defined in any sibling file either")
    else:
        print(f"All {tag_checked} cited tag names are really defined in their cited file.")
    print()
    # moz-* is Acorn's own tracked naming convention (every current modern/
    # dual component matches it); other native widgets under this dir are
    # legacy XUL-replacement elements that were never in scope, so they're
    # reported separately and don't fail the run on their own.
    moz_new = [f for f in untracked if Path(f).stem.startswith("moz-")]
    other_new = [f for f in untracked if f not in moz_new]
    if moz_new:
        print(f"NEW moz-* components ({len(moz_new)}), no component-api entry yet:")
        for f in moz_new:
            print(f"  {f}")
    else:
        print("No new untracked moz-* components found.")
    if other_new:
        print()
        print(f"Other untracked native widgets ({len(other_new)}), likely out of Acorn's scope, FYI only:")
        for f in other_new:
            print(f"  {f}")
    if missing_upstream:
        print()
        print(f"NOTE: {len(missing_upstream)} tracked file(s) no longer exist upstream at their recorded path (moved or removed):")
        for cid, file in missing_upstream:
            print(f"  {cid}: {file}")
    if uncheckable:
        print()
        print(f"NOTE: {len(uncheckable)} tracked component(s) cite more than one source in prose, not checked here:")
        for cid, file in uncheckable.items():
            print(f"  {cid}: {file}")

    # A tag traced to a sibling file is reported but doesn't fail: splitting
    # registration out from the class is a real, deliberate pattern upstream
    # (see find_tag_definer), so the citation is usually still the right one.
    # A tag defined in no fetched file at all is the genuine drift case.
    tag_lost = [m for m in tag_missing if not m[3]]

    if changed or moz_new or missing_upstream or tag_lost:
        sys.exit(1)


if __name__ == "__main__":
    main()
