#!/usr/bin/env python3
"""update-meta.py: regenerate component-api/_meta.json and
guidance-api/_meta.json from this repo's own git history.

Each entry records the real last commit that touched that file (git log -1
-- <file>), which is what makes the date meaningful rather than a
fabricated timestamp. Two things make that go stale on its own, and both
have already happened here:

  * A history rewrite. Squashing to a single commit left all 114 entries,
    and both repoHead values, citing SHAs that no longer existed anywhere.
  * A new file. 14 component-api entries (button-group, five-star, the
    input-* family, label, reorderable-list, support-link, textarea) were
    simply never added, so the metadata silently described fewer files than
    the directory held.

Usage:
  python3 update-meta.py            rewrite both files
  python3 update-meta.py --check    exit non-zero if either is out of date

--check compares the `files` map only, deliberately not repoHead. repoHead
records the repo HEAD at generation time, so committing a regenerated file
moves it by definition: a plain "regenerate and git diff" check would fail
on every run forever, for a field that carries no per-file information.
"""

import collections
import json
import os
import subprocess
import sys

DIRS = ("component-api", "guidance-api")
# Not component entries: the metadata itself, the schema, the drift script's
# own state file, and guidance-api's authoring skeleton.
SKIP = {"schema.json", "drift-manifest.json"}


def git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main():
    check_only = "--check" in sys.argv[1:]
    head_commit = git("log", "-1", "--format=%H")
    head_date = git("log", "-1", "--format=%aI")
    exit_code = 0

    for directory in DIRS:
        path = os.path.join(directory, "_meta.json")
        existing = json.load(open(path, encoding="utf-8"))

        ids = sorted(
            name[:-5]
            for name in os.listdir(directory)
            if name.endswith(".json") and not name.startswith("_") and name not in SKIP
        )

        files = collections.OrderedDict()
        untracked = []
        for entry_id in ids:
            line = git("log", "-1", "--format=%H %aI", "--", f"{directory}/{entry_id}.json")
            if not line:
                # On disk but never committed, so there is no real date to
                # record. Reported rather than given a made-up one.
                untracked.append(entry_id)
                continue
            commit, date = line.split(" ", 1)
            files[entry_id] = {"lastCommit": commit, "lastModified": date}

        out = collections.OrderedDict()
        out["note"] = existing["note"]
        out["repoHead"] = {"commit": head_commit, "date": head_date}
        out["files"] = files

        if check_only:
            stale = existing["files"] != files
            missing = sorted(set(files) - set(existing["files"]))
            extra = sorted(set(existing["files"]) - set(files))
            if stale:
                print(f"{path}: OUT OF DATE. Run 'python3 update-meta.py' and commit.")
                if missing:
                    print(f"  files with no entry: {', '.join(missing)}")
                if extra:
                    print(f"  entries with no file: {', '.join(extra)}")
                changed = sorted(
                    k for k in files
                    if k in existing["files"] and existing["files"][k] != files[k]
                )
                if changed:
                    print(f"  entries pointing at the wrong commit: {', '.join(changed)}")
                exit_code = 1
            else:
                print(f"{path}: current ({len(files)} entries)")
        else:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(out, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            print(f"{path}: {len(files)} entries")

        if untracked:
            print(f"  not yet committed, so left out: {', '.join(untracked)}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
