#!/usr/bin/env python3
"""Refuse a push whose new commits carry a Figma file URL or a file-key-shaped string.

Reads pre-push's stdin (`<local ref> <local sha> <remote ref> <remote sha>` per line)
and scans the message and diff of every commit the push would publish. Matches the
shape, never a literal key, so this file can't leak what it guards. Use the
`$FIGMA_FILE_KEY` placeholder instead (see AGENTS.md).
"""
import re
import subprocess
import sys

ZERO = "0" * 40
FIGMA_URL = re.compile(r"figma\.com/(?:design|file|proto|board|make)/[0-9A-Za-z]{10,}")
TOKEN = re.compile(r"\b[0-9A-Za-z]{22,128}\b")


def key_shaped(s):
    return any(c.isupper() for c in s) and any(c.islower() for c in s) and any(c.isdigit() for c in s)


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def outgoing(local_sha, remote_sha):
    if local_sha == ZERO:
        return []
    rng = [local_sha, "--not", "--remotes"] if remote_sha == ZERO else [f"{remote_sha}..{local_sha}"]
    return git("rev-list", *rng).split()


def mask(s):
    return s[:4] + "..." if len(s) > 4 else s


def main():
    hits = []
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        for sha in outgoing(parts[1], parts[3]):
            text = git("show", "--format=%B", sha)
            found = [m.group(0) for m in FIGMA_URL.finditer(text)]
            found += [t for t in TOKEN.findall(text) if key_shaped(t)]
            if found:
                hits.append((sha[:7], git("show", "-s", "--format=%s", sha).strip(), sorted(set(found))))
    if not hits:
        print("  ok   no Figma file URLs or key-shaped strings in outgoing commits")
        return 0
    print("  FAIL outgoing commits carry a Figma file URL or key-shaped string:")
    for sha, subject, found in hits:
        for f in sorted(found, key=len, reverse=True):
            subject = subject.replace(f, mask(f))
        print(f"         {sha} {subject}")
        for f in found:
            print(f"           {mask(f)}")
    print("         Replace it with $FIGMA_FILE_KEY (message: git commit --amend or rebase).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
