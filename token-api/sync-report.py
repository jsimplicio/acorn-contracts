#!/usr/bin/env python3
"""Write token-api/sync-report.html: what an uncommitted token sync changed, readable in a browser.

Compares the working tree against HEAD, so run it after sync.py, figma-check.py
and resolve.py, before committing. The output is gitignored and never published.

Rows come from the raw token files, so every change shows (Proton values and
theme branches included); resolved/ only annotates them with the Nova value,
and adds rows for tokens whose own entry is untouched but whose alias target moved.

Usage: python3 token-api/sync-report.py [--open]
"""
import argparse
import datetime
import html
import json
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import sync  # noqa: E402

OUT = SCRIPT_DIR / "sync-report.html"
INFO = SCRIPT_DIR / "sync-report.json"
SAFE_SWATCH_RE = re.compile(r"^[^;{}<>]*$")
THEME_PREFIX = "$extensions.org.mozilla.themes."


def git(*args):
    return subprocess.run(["git", "-C", str(SCRIPT_DIR), *args],
                          check=True, capture_output=True, text=True).stdout


def head_json(rel):
    try:
        return json.loads(git("show", f"HEAD:./{rel}"))
    except Exception:
        return None


def tree_json(rel):
    p = SCRIPT_DIR / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def flat_fields(node, prefix="", out=None):
    """A token leaf as dotted field -> value, so a change can be named down to one theme axis."""
    out = {} if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            flat_fields(v, f"{prefix}{k}.", out)
    else:
        out[prefix[:-1]] = node
    return out


def field_diffs(old_leaf, new_leaf):
    o = flat_fields(json.loads(old_leaf)) if old_leaf else {}
    n = flat_fields(json.loads(new_leaf)) if new_leaf else {}
    rows = []
    for f in sorted(set(o) | set(n), key=lambda f: (f != "$value", f)):
        if o.get(f) != n.get(f):
            label = "theme " + f[len(THEME_PREFIX):] if f.startswith(THEME_PREFIX) else f
            rows.append((label, o.get(f), n.get(f)))
    return rows


def resolved_index(load):
    """resolved key -> token across every resolved/*.json, from HEAD or the working tree."""
    names = {Path(n).name for n in git("ls-tree", "--name-only", "HEAD", "resolved/").split()}
    names |= {p.name for p in (SCRIPT_DIR / "resolved").glob("*.json")}
    out = {}
    for name in sorted(names):
        for key, tok in ((load(f"resolved/{name}") or {}).get("tokens") or {}).items():
            out.setdefault(key, tok)
    return out


def resolved_key(stem, path):
    base = stem[: -len(".nova")] if stem.endswith(".nova") else stem
    return f"{base}.{'.'.join(s for s in path.split('.') if s != 'nova')}"


def owner_label(stem, rel, id_map):
    owners = id_map.get(stem) or (id_map.get(stem[: -len(".nova")]) if stem.endswith(".nova") else None)
    if owners:
        return ", ".join(owners)
    if rel.startswith("base/"):
        return "base tokens"
    return "not in id-map.json"


def collect():
    old_m, new_m = head_json("sync-manifest.json") or {}, tree_json("sync-manifest.json") or {}
    files = sorted(set(old_m.get("files_converted", [])) | set(new_m.get("files_converted", [])))
    id_map = sync._load_id_map()
    old_res, new_res = resolved_index(head_json), resolved_index(tree_json)

    groups, seen = {}, set()
    for rel in files:
        old, new = sync._head_and_tree_leaves(rel)
        stem = Path(rel).name[: -len(".tokens.json")]
        for path in sorted(set(old) | set(new)):
            if old.get(path) == new.get(path):
                continue
            key = resolved_key(stem, path)
            seen.add(key)
            marker = "+" if path not in old else "-" if path not in new else "~"
            groups.setdefault(owner_label(stem, rel, id_map), []).append({
                "marker": marker, "stem": stem, "path": path, "fields": field_diffs(old.get(path), new.get(path)),
                "res_old": old_res.get(key), "res_new": new_res.get(key), "via": False})
    for key in sorted(set(old_res) | set(new_res)):
        if key in seen or old_res.get(key) == new_res.get(key) or key not in old_res or key not in new_res:
            continue
        stem, _, path = key.partition(".")
        groups.setdefault(owner_label(stem, "", id_map), []).append({
            "marker": "~", "stem": stem, "path": path, "fields": [],
            "res_old": old_res[key], "res_new": new_res[key], "via": True})
    order = sorted(groups, key=lambda g: (g == "base tokens", g == "not in id-map.json", g))
    return old_m, new_m, [(g, groups[g]) for g in order]


def staleness_warnings():
    def newest(globs):
        return max((p.stat().st_mtime for g in globs for p in SCRIPT_DIR.glob(g)), default=0)
    tokens = newest(["base/*.tokens.json", "components/*.tokens.json"])
    warns = []
    resolved = min((p.stat().st_mtime for p in (SCRIPT_DIR / "resolved").glob("*.json")), default=0)
    if resolved < tokens:
        warns.append("Some resolved/ files are older than the token files: re-run resolve.py, "
                     "or the Nova column is stale.")
    fmap = SCRIPT_DIR / "figma-token-map.json"
    if fmap.is_file() and fmap.stat().st_mtime < tokens:
        warns.append("figma-token-map.json is older than the token files: re-run figma-check.py, "
                     "or the Figma column is stale.")
    return warns


def esc(v):
    if v is None:
        return ""
    return html.escape(v if isinstance(v, str) else json.dumps(v))


def swatch(value, type_):
    if type_ != "color" or not isinstance(value, str) or not SAFE_SWATCH_RE.match(value) or "url(" in value:
        return ""
    return f'<span class="sw" style="background:{html.escape(value, quote=True)}"></span>'


def fields_cell(row):
    if row["via"]:
        return '<td><span class="note via">own entry unchanged, an alias it points at moved</span></td>'
    whole = row["marker"] in ("+", "-")
    lines = []
    for label, o, n in row["fields"]:
        if whole:
            body = f"<code>{esc(n if o is None else o)}</code>"
        elif o is None:
            body = f'<span class="pill pill-add">new</span> <code>{esc(n)}</code>'
        elif n is None:
            body = f'<span class="pill pill-rem">removed</span> <code class="gone">{esc(o)}</code>'
        else:
            body = f"<code>{esc(o)}</code> &rarr; <code>{esc(n)}</code>"
        lines.append(f'<div class="field"><code class="fl">{esc(label)}</code><div>{body}</div></div>')
    return f'<td>{"".join(lines)}</td>'


def nova_cell(row):
    o, n = row["res_old"], row["res_new"]
    if o is None and n is None:
        return '<td><span class="note">not exported</span></td>'
    def one(t):
        return f'{swatch(t.get("value"), t.get("type"))}<code>{esc(t.get("value"))}</code>'
    if o == n:
        return f'<td>{one(n)}<div class="note">unchanged</div></td>'
    chain = (n or {}).get("chain") or []
    via = f'<div class="chain">via {" &rarr; ".join(f"<code>{esc(c)}</code>" for c in chain)}</div>' if chain else ""
    if o is None:
        return f"<td>{one(n)}{via}</td>"
    if n is None:
        return f'<td><span class="pill pill-rem">removed</span> {one(o)}</td>'
    return f"<td>{one(o)} &rarr; {one(n)}{via}</td>"


def figma_cell(figma_map, row):
    if row["marker"] == "-":
        return "<td></td>"
    var = sync._derive_css_var_name(row["stem"], row["path"])
    status = figma_map.get(var)
    label = status if status in ("yes", "no") else "not in map"
    return f'<td><span class="fig fig-{label.replace(" ", "-")}">{label}</span><div class="chain"><code>{esc(var)}</code></div></td>'


MARK = {"+": ("added", "add"), "-": ("removed", "rem"), "~": ("changed", "chg")}


def render(old_m, new_m, groups, warns, figma_map, fetched_at):
    parts = [f'<p class="warn"><strong>Warning:</strong> {esc(w)}</p>' for w in warns]
    counts = {m: sum(1 for _, rows in groups for r in rows if r["marker"] == m and not r["via"]) for m in MARK}
    via = sum(1 for _, rows in groups for r in rows if r["via"])
    if not groups:
        parts.append("<p>No token changed since the last commit.</p>")
    else:
        parts.append(f'<p class="summary">{counts["+"]} added, {counts["-"]} removed, {counts["~"]} changed'
                     f'{f", plus {via} changed through an alias" if via else ""}.</p>')
        parts.append('<ul class="toc">' + "".join(
            f'<li><a href="#g{i}">{esc(g)}</a> <span class="n">{len(rows)}</span></li>'
            for i, (g, rows) in enumerate(groups)) + "</ul>")
    for i, (g, rows) in enumerate(groups):
        parts.append(f'<h2 id="g{i}">{esc(g)}</h2><div class="scroll"><table><thead><tr>'
                     "<th></th><th>Token</th><th>What changed</th><th>Nova value</th><th>In Figma</th></tr></thead><tbody>")
        for r in rows:
            word, cls = MARK[r["marker"]]
            parts.append(f'<tr class="{cls}"><td><span class="tag">{word}</span></td>'
                         f'<td><code>{esc(r["stem"])}.{esc(r["path"])}</code></td>'
                         f"{fields_cell(r)}{nova_cell(r)}{figma_cell(figma_map, r)}</tr>")
        parts.append("</tbody></table></div>")

    old_src = old_m.get("source", {}).get("commit", "?")
    new_src = new_m.get("source", {}).get("commit", "?")
    meta = (f"Upstream <code>{esc(old_src[:10])}</code> &rarr; <code>{esc(new_src[:10])}</code> &middot; "
            f"compared against repo HEAD <code>{esc(git('rev-parse', '--short', 'HEAD').strip())}</code> &middot; "
            f"generated {esc(datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))} &middot; "
            f"Figma dump fetched {esc(fetched_at or 'unknown')}")
    return TEMPLATE.replace("{{META}}", meta).replace("{{BODY}}", "\n".join(parts))


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Token Sync Report</title>
<script>if (new URLSearchParams(location.search).has("embed")) document.documentElement.classList.add("embed");</script>
<style>
@font-face { font-family: "Tisa Pro"; src: url("../TisaPro-Regular.woff") format("woff"); }
@font-face { font-family: "Freight Sans"; src: url("../Freight-Sans-Medium.woff") format("woff"); font-weight: 400; }
@font-face { font-family: "Freight Sans"; src: url("../Freight-Sans-Bold.woff2") format("woff2"); font-weight: 700; }
@font-face { font-family: "JetBrains Mono"; src: url("../JetBrains-Mono.woff2") format("woff2"); }
:root { color-scheme: light; --bg: #fbfbfe; --surface: #fff; --text: #15141a; --muted: #5b5b66; --line: #e0e0e6;
  --add: #1a7f37; --rem: #b4232c; --chg: #8a5a00; --warn-bg: #fff4ce; --warn-line: #e5b700; --link: #0061e0; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; --bg: #1c1b22; --surface: #2b2a33;
  --text: #fbfbfe; --muted: #bfbfc9; --line: #45444f; --add: #57d17a; --rem: #ff848b; --chg: #f2c14e;
  --warn-bg: #3d3416; --warn-line: #a68a00; --link: #80ebff; } }
:root[data-theme="dark"] { color-scheme: dark; --bg: #1c1b22; --surface: #2b2a33; --text: #fbfbfe; --muted: #bfbfc9;
  --line: #45444f; --add: #57d17a; --rem: #ff848b; --chg: #f2c14e; --warn-bg: #3d3416; --warn-line: #a68a00; --link: #80ebff; }
.embed body { background: transparent; padding: 0 0 24px; }
body { margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--text);
  font-family: "Tisa Pro", -apple-system, "Segoe UI", sans-serif; line-height: 1.5; }
main { max-width: 1200px; margin: 0 auto; }
h1, h2 { font-family: "Freight Sans", -apple-system, "Segoe UI", sans-serif; }
h2 { margin: 36px 0 8px; font-size: 20px; }
.meta { color: var(--muted); font-size: 14px; }
.summary { font-size: 18px; }
code { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 13px; overflow-wrap: anywhere; word-break: normal; }
td:nth-child(2) code { overflow-wrap: break-word; }
.warn { background: var(--warn-bg); border-left: 4px solid var(--warn-line); padding: 8px 12px; }
a { color: var(--link); }
.toc { display: flex; flex-wrap: wrap; gap: 4px 16px; padding: 0; list-style: none; }
.toc .n { color: var(--muted); font-size: 13px; }
.scroll { overflow-x: auto; }
table { width: 100%; min-width: 980px; border-collapse: collapse; background: var(--surface); font-size: 14px; }
th, td { text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid var(--line); }
td:nth-child(2) { width: 22%; } td:nth-child(3) { width: 40%; } td:nth-child(4) { width: 18%; } td:nth-child(5) { width: 14%; }
th { color: var(--muted); font-weight: normal; font-size: 13px; }
.tag { font-family: "Freight Sans", -apple-system, "Segoe UI", sans-serif; font-size: 13px; font-weight: 700; }
tr.add .tag { color: var(--add); } tr.rem .tag { color: var(--rem); } tr.chg .tag { color: var(--chg); }
.none { color: var(--muted); font-style: italic; }
.field + .field { margin-top: 8px; }
.field .fl { display: block; }
.fl { color: var(--muted); font-size: 12px; }
.gone { color: var(--muted); text-decoration: line-through; }
.pill { display: inline-block; font-family: "Freight Sans", -apple-system, "Segoe UI", sans-serif; font-size: 12px; font-weight: 700; padding: 0 6px; border-radius: 4px; border: 1px solid currentColor; line-height: 1.5; }
.pill-add { color: var(--add); } .pill-rem { color: var(--rem); }
.chain code { font-size: 12px; }
.note { font-family: "Freight Sans", -apple-system, "Segoe UI", sans-serif; color: var(--muted); font-size: 13px; }
.chain { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.note.via { color: var(--chg); }
.sw { display: inline-block; width: 14px; height: 14px; border-radius: 3px; margin-right: 6px;
  vertical-align: -2px; border: 1px solid var(--line); }
.fig-yes { color: var(--add); } .fig-no { color: var(--rem); } .fig-not-in-map { color: var(--muted); }
</style></head>
<body><main>
<h1>Token sync report</h1>
<p class="meta">{{META}}</p>
{{BODY}}
</main></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--open", action="store_true", help="open the report in a browser")
    args = ap.parse_args()
    old_m, new_m, groups = collect()
    dump = tree_json("figma-variables-dump.json") or {}
    OUT.write_text(render(old_m, new_m, groups, staleness_warnings(), sync._load_figma_map(),
                          dump.get("fetchedAt")), encoding="utf-8")
    INFO.write_text(json.dumps({
        "generatedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "upstream": new_m.get("source", {}).get("commit"),
        "changes": sum(len(rows) for _, rows in groups),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
