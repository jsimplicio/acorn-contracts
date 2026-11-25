#!/usr/bin/env python3
"""realm-check.py: check resolved/ against upstream's own token resolver.

Firefox resolves a token per realm (upstream toolkit/themes/tools/
token_resolve.py): chrome is tokens-shared.css + tokens-platform.css,
in-content is tokens-shared.css + tokens-brand.css. This fetches the
generated token sheets and that resolver at one upstream commit, runs the
resolver's own Sheet code over each realm, and compares every value
resolved/ publishes with upstream's answer. It reads and prints only.

    python3 token-api/realm-check.py              # full: every realm and scheme
    python3 token-api/realm-check.py --top-level  # only the top-level values
    python3 token-api/realm-check.py --ref <sha>  # default: sync-manifest.json's commit

Realms and environments, all with browser.nova.enabled on and no high
contrast:
  in-content     tokens-brand.css
  chrome         tokens-platform.css (in-app layers apply)
  chrome-native  tokens-platform.css with -moz-native-theme (Linux default
                 theme, or any non-in-app theme)
Light and dark come from splitting light-dark() in upstream's answer.

The per-component sheets are concatenated onto each realm's second sheet,
which is safe only while no name is declared in two of them; that, the
selector contexts and the @media conditions are checked first, and an
unknown one fails the run rather than being guessed at. Upstream's one
eval() is never reached: its holds(), pinned to the source it was checked
against, is replaced with a truth table for the four known conditions.

Exit 0 when everything matches or is a keyed known exception, 1 on any
mismatch, 2 when the fetch fails or the sheets hold something this script
does not model.
"""

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import resolve  # noqa: E402

REPO_URL = "https://github.com/mozilla-firefox/firefox"
DIST = "toolkit/themes/shared/design-system/dist"
RESOLVER = "toolkit/themes/tools/token_resolve.py"
COMPONENT_GLOBS = (
    "browser/themes/shared/tabbrowser/*.tokens.css",
    "browser/themes/shared/urlbar/*.tokens.css",
    "toolkit/content/widgets/*.tokens.css",
    "toolkit/content/widgets/*/*.tokens.css",
)
PATTERNS = [f"/{DIST}/tokens-*.css", f"/{RESOLVER}"] + [f"/{g}" for g in COMPONENT_GLOBS]

NOVA = '-moz-pref("browser.nova.enabled")'
NATIVE = "(-moz-native-theme)"
FORCED = "(forced-colors)"
CONTRAST = "(prefers-contrast)"
CONDITIONS = {
    "@media (forced-colors)": lambda env: FORCED in env,
    f"@media {NOVA}": lambda env: NOVA in env,
    "@media not ((forced-colors) or (-moz-native-theme))": lambda env: FORCED not in env and NATIVE not in env,
    "@media (prefers-contrast)": lambda env: CONTRAST in env,
}
SELECTORS = {
    ":root, :host(.anonymous-content-host)",
    ":root:is([theme-in-app], :not([lwtheme])), :host(.anonymous-content-host)",
    ":root, :host",
    ":root:is([theme-in-app], :not([lwtheme])), :host",
}
IN_APP_SELECTOR = ":root:is([theme-in-app], :not([lwtheme]))"
IN_APP_MEDIA = "@media not ((forced-colors) or (-moz-native-theme))"
# Upstream's holds() as checked against CONDITIONS; any change to it fails the run.
HOLDS_SOURCE = '''def holds(cond, env):
    query = boolean_query(cond)
    if query is None:
        return cond in env
    expr = FEATURE.sub(lambda m: f" {m.group(0) in env} ", query).replace(",", " or ")
    return eval(expr, {"__builtins__": {}})'''

REALMS = {
    "in-content": ("tokens-brand.css", frozenset({NOVA})),
    "chrome": ("tokens-platform.css", frozenset({NOVA})),
    "chrome-native": ("tokens-platform.css", frozenset({NOVA, NATIVE})),
}
SCHEMES = ("light", "dark")

# Rows that may differ from upstream: (reason, {scheme or (realm, scheme): what ours must be}, structure
# problems allowed, blocks required). Ours is None where this repo cannot substitute; an unlisted pair must
# match upstream. An exception that no longer fires fails the run, so a fixed one gets removed.
_TOGGLE = "declared upstream only under forced-colors; sync.py's pick_default gap"
_TAB = "tab's id-map does not load toolbox or toolbar, so this repo cannot resolve it"
_OPACITY = "upstream emits light-dark(0.7, 0.95); light-dark() takes only colours, so browsers compute it invalid"
EXCEPTIONS = {
    "moz-toggle.background.color.disabled": (_TOGGLE, {"light": "transparent", "dark": "transparent"}, set(), set()),
    "moz-toggle.background.color.pressed.disabled": (_TOGGLE, {"light": "#75669f", "dark": "#9687c0"}, {"a dark block"}, {"dark"}),
    "moz-toggle.border.color.disabled": (_TOGGLE, {"light": "#c7c6cb", "dark": "#515054"}, {"a dark block"}, {"dark"}),
    "moz-toggle.dot.background.color.disabled": (_TOGGLE, {"light": "#161423", "dark": "#fcfbff"}, {"a dark block"}, {"dark"}),
    "moz-toggle.dot.background.color.on-pressed.disabled": (_TOGGLE, {"light": "#ffffff", "dark": "#252428"}, {"a dark block"}, {"dark"}),
    **{row: (_TAB, {"light": None, "dark": None}, {"no realms block", "no dark block", "unresolvedRefs without substituted",
              "refs to tokens this repo does not load"}, set())
       for row in ("tab.text.color.@base", "tab.text.color.hover", "tab.text.color.selected")},
    "urlbar.icon.fill.opacity": (_OPACITY, {(r, s): v for r in ("in-content", "chrome")
                                            for s, v in (("light", "0.7"), ("dark", "0.95"))},
                                 {"a dark block"}, {"dark", "realms"}),
}


class Unmodelled(Exception):
    """The sheets hold something this script does not model."""


def fetch(ref, workdir):
    def run(*args):
        subprocess.run(["git", "-C", str(workdir), *args], check=True)

    print(f"Fetching {ref} from {REPO_URL} ...", flush=True)
    subprocess.run(["git", "init", "-q", str(workdir)], check=True)
    run("remote", "add", "origin", REPO_URL)
    run("fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", ref)
    run("sparse-checkout", "init", "--no-cone")
    run("sparse-checkout", "set", *PATTERNS)
    run("checkout", "--quiet", "FETCH_HEAD")
    return subprocess.run(["git", "-C", str(workdir), "rev-parse", "FETCH_HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def load_upstream(root):
    """Upstream's token_resolve.py, unchanged, with holds() (its one eval()) swapped for CONDITIONS."""
    path = root / RESOLVER
    source = path.read_text(encoding="utf-8")
    nodes = list(ast.walk(ast.parse(source)))
    funcs = [n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == "holds"]
    uses = [n for n in nodes if isinstance(n, ast.Name) and n.id == "holds"]
    if source.count("eval(") != 1 or "exec(" in source:
        raise Unmodelled(f"{RESOLVER}: expected exactly one eval(), inside holds(), and no exec()")
    if len(funcs) != 1 or ast.get_source_segment(source, funcs[0]) != HOLDS_SOURCE:
        raise Unmodelled(f"{RESOLVER}: holds() is not the version this script's truth table was checked against")
    if len(uses) != 1:
        raise Unmodelled(f"{RESOLVER}: holds is referenced from somewhere new")
    spec = importlib.util.spec_from_file_location("token_resolve", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def holds(cond, env):
        if cond not in CONDITIONS:
            raise Unmodelled(f"unknown condition {cond!r}")
        return CONDITIONS[cond](env)

    module.holds = holds
    return module


def component_sheets(root):
    return sorted(p for g in COMPONENT_GLOBS for p in root.glob(g))


def check_sheets(tr, root):
    """Fail on what concatenating the sheets and the truth table cannot model."""
    seen = {}
    for path in [root / DIST / n for n in tr.SHEETS] + component_sheets(root):
        rel = str(path.relative_to(root))
        for (ctx, name), _ in tr.decls(path.read_text(encoding="utf-8")).items():
            parts = ctx.split(" > ")
            selectors = [p for p in parts if not p.startswith("@")]
            if len(selectors) != 1 or selectors[0] not in SELECTORS:
                raise Unmodelled(f"{rel}: {name} under unknown selector context {ctx!r}")
            if (IN_APP_SELECTOR in selectors[0]) != (IN_APP_MEDIA in parts):
                raise Unmodelled(f"{rel}: {name} has the in-app selector or media without the other: {ctx!r}")
            for part in parts:
                if part.startswith("@") and not part.startswith("@layer ") and part not in CONDITIONS:
                    raise Unmodelled(f"{rel}: {name} under unknown condition {part!r}")
            if "/dist/" in rel:
                continue
            prior = seen.setdefault(name, rel)
            if prior != rel:
                raise Unmodelled(f"{name} declared in both {prior} and {rel}")
    for main in tr.SHEETS:
        main_names = {n for _, n in tr.decls((root / DIST / main).read_text(encoding="utf-8"))}
        for name in main_names & seen.keys():
            raise Unmodelled(f"{name} declared in {main} and {seen[name]}")


def realm_sheets(tr, root, tmp):
    """({realm: (Sheet, env)}, every name a token sheet declares), each realm's second sheet
    carrying every per-component sheet."""
    components = "".join("\n" + p.read_text(encoding="utf-8") for p in component_sheets(root))
    sheets = {}
    for importer in {imp for imp, _ in REALMS.values()}:
        directory = tmp / importer
        directory.mkdir()
        (directory / "tokens-shared.css").write_text((root / DIST / "tokens-shared.css").read_text(encoding="utf-8"))
        (directory / importer).write_text((root / DIST / importer).read_text(encoding="utf-8") + components)
        sheet = tr.Sheet(str(directory), importer)
        if not sheet.lightweight:
            raise Unmodelled(f"{importer}: upstream does not mark it lightweight")
        unknown = [f for f in sheet.features if f not in (NOVA, NATIVE, FORCED, CONTRAST)]
        if unknown:
            raise Unmodelled(f"{importer}: unknown features {unknown}")
        sheets[importer] = sheet
    names = {n for sheet in sheets.values() for _, n in sheet.decls}
    return {realm: (sheets[imp], env) for realm, (imp, env) in REALMS.items()}, names


LIGHT_DARK_RE = re.compile(r"(?<![\w-])light-dark\(", re.IGNORECASE)
# A colour: a hex, a colour function, or one identifier that is not a keyword; anything else is not.
COLOUR_FUNCTION_RE = re.compile(r"(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix|light-dark|var)\(",
                                re.IGNORECASE)
NOT_COLOUR_WORDS = {"inherit", "initial", "unset", "revert", "revert-layer", "none", "auto", "normal"}


def is_colour(arg):
    if re.fullmatch(r"#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})", arg, re.IGNORECASE):
        return True
    m = COLOUR_FUNCTION_RE.match(arg)
    if m:
        level = 1
        for k in range(m.end(), len(arg)):
            level += {"(": 1, ")": -1}.get(arg[k], 0)
            if not level:
                return k == len(arg) - 1
        return False
    return bool(re.fullmatch(r"-?[a-z][\w-]*", arg, re.IGNORECASE)) and arg.lower() not in NOT_COLOUR_WORDS


class NotAColour(Exception):
    """light-dark() around something that is not a colour, which browsers reject."""


def split_light_dark(value, scheme):
    """value with every light-dark(a, b) replaced by a or b, nested ones included."""
    out, i = [], 0
    while True:
        m = LIGHT_DARK_RE.search(value, i)
        if m is None:
            out.append(value[i:])
            return "".join(out)
        out.append(value[i:m.start()])
        k, level, commas = m.end(), 1, []
        while k < len(value) and level:
            ch = value[k]
            level += {"(": 1, ")": -1}.get(ch, 0)
            if ch == "," and level == 1:
                commas.append(k)
            k += 1
        if level or len(commas) != 1:
            raise Unmodelled(f"light-dark() without exactly two arguments in {value!r}")
        args = [value[m.end():commas[0]].strip(), value[commas[0] + 1:k - 1].strip()]
        if not all(is_colour(a) for a in args):
            raise NotAColour(value)
        out.append(split_light_dark(args[scheme == "dark"], scheme))
        i = k


DANGLING_RE = re.compile(r"var\(\s*(--[\w-]+)")


def upstream_value(realms, token_names, realm, scheme, css_name):
    """{"value": ...}, {"value": None, "declared": False[, "via": name]} or {"invalid": value}."""
    sheet, env = realms[realm]
    winner = sheet.effective(env).get(css_name)
    if winner is None:
        return {"value": None, "declared": False}
    value = winner[0]
    # A leftover var() to a token name is dangling; one to a consumer sheet's variable stays as written.
    for ref in DANGLING_RE.findall(value):
        if ref in token_names:
            return {"value": None, "declared": False, "via": ref}
    try:
        return {"value": split_light_dark(value, scheme)}
    except NotAColour:
        return {"invalid": value}


def css_name(row):
    parts = [p for p in row.split(".") if p != "@base"]
    if parts[0].startswith("moz-"):
        parts[0] = parts[0][len("moz-"):]
    return "--" + "-".join(parts)


def normalise(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return value
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\(\s+", "(", value)
    value = re.sub(r"\s+\)", ")", value)
    return re.sub(r"\s*,\s*", ", ", value)


def component_lookup(id_map, base, id_):
    """id_'s lookup, built the way resolve.py builds it (an unmapped id is its own basename)."""
    entry = id_map.get("map", {}).get(id_, [id_])
    lookup = dict(base)
    own = entry if isinstance(entry, list) else entry["own"]
    resolve_only = [] if isinstance(entry, list) else entry.get("resolve", [])
    for o in own:
        resolve.load_basename_into(o if isinstance(o, str) else o["basename"], lookup, None)
    for b in resolve_only:
        resolve.load_basename_into(b, lookup, None)
    return lookup


def published_rows():
    """(file, row name, row, lookup) for every row resolved/ publishes, _base.json included."""
    id_map = json.loads((SCRIPT_DIR / "id-map.json").read_text(encoding="utf-8"))
    base = resolve.build_base_lookup(id_map)
    if not (SCRIPT_DIR / "resolved" / "_base.json").is_file():
        yield "_base.json", None, MISSING, "is missing"
    for path in sorted((SCRIPT_DIR / "resolved").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            yield path.name, None, MISSING, f"cannot be read as JSON ({e})"
            continue
        if (not isinstance(data, dict) or not isinstance(data.get("tokens"), dict)
                or not isinstance(data.get("id", ""), str)):
            yield path.name, None, MISSING, "has no tokens object, or a non-string id"
            continue
        if path.name == "_base.json":
            want = set(base_token_names())
            for name in sorted(want - data["tokens"].keys()):
                yield path.name, name, MISSING, "is missing this base token"
            for name in sorted(data["tokens"].keys() - want):
                yield path.name, name, MISSING, "is not a base token"
        lookup = base if path.name == "_base.json" else component_lookup(id_map, base, data.get("id", path.stem))
        for name, row in data["tokens"].items():
            yield path.name, name, row, lookup


MISSING = object()


def base_token_names():
    """Every <stem>.<path> in base/, the keys _base.json must have."""
    names = set()
    for f in (SCRIPT_DIR / "base").glob("*.tokens.json"):
        stem = f.name.split(".")[0]
        names.update(resolve.load_and_flatten(f"base/{f.name}", stem_override=stem))
    return names


def substitute(value, lookup, depth=0):
    """value with every {ref} replaced by its resolved value, or None if one cannot be."""
    if not isinstance(value, str):
        return value
    if depth > resolve.MAX_DEPTH:
        return None
    failed = False

    def one(m):
        nonlocal failed
        target = lookup.get(m.group(1))
        if target is None:
            failed = True
            return m.group(0)
        inner, _ = resolve.resolve_alias(resolve.effective_value(target), lookup)
        inner = substitute(inner, lookup, depth + 1)
        if inner is None:
            failed = True
            return m.group(0)
        return inner if isinstance(inner, str) else normalise(inner)

    out = resolve.ALIAS_REF_RE.sub(one, value)
    return None if failed else out


def published(row, realm, scheme):
    """The consumer rule: realms[realm][scheme], else dark for dark, else top level."""
    entry = (row.get("realms") or {}).get(realm, {}).get(scheme)
    if entry is None and scheme == "dark":
        entry = row.get("dark")
    return entry if entry is not None else row


def comparable(entry, lookup, top):
    """What an entry publishes, composites substituted; None when it cannot be."""
    if entry.get("declared") is False:
        return {k: entry[k] for k in ("value", "declared", "via") if k in entry}
    if "substituted" in entry:
        return {"value": entry["substituted"]}
    if entry.get("unresolvedRefs"):
        if not top:
            return "(unresolvedRefs without substituted)"
        value = substitute(entry["value"], lookup)
        return None if value is None else {"value": value}
    return {"value": entry["value"]}


def same(ours, theirs):
    if not isinstance(ours, dict) or "invalid" in theirs:
        return False
    if theirs.get("declared") is False:
        return ours.get("declared") is False and ours.get("via") == theirs.get("via")
    return normalise(ours["value"]) == normalise(theirs["value"])


NO_EXPECTATION = object()
ENTRY_KEYS = ("value", "chain", "unresolvedRefs", "substituted", "declared", "via")


def check(realms, token_names, rows, top_level):
    mismatches, excused, matched, fired = [], [], 0, set()
    pairs = [("in-content", "light")] if top_level else [(r, s) for r in REALMS for s in SCHEMES]
    for fname, name, row, lookup in rows:
        if row is MISSING:
            if not (top_level and fname == "_base.json" and name is None and lookup == "is missing"):
                mismatches.append(f"{fname}{' ' + name if name else ''} {lookup}")
            continue
        malformed = shape_problem(row)
        if malformed:
            mismatches.append(f"{fname} {name}: {malformed}")
            continue
        css = css_name(name)
        theirs = {(r, s): upstream_value(realms, token_names, r, s, css) for r, s in pairs}
        reason, expected, allowed, required = EXCEPTIONS.get(name, (None, {}, set(), set()))
        problems, row_excused = [], []
        for realm, scheme in pairs:
            entry = published(row, realm, scheme)
            ours = comparable(entry, lookup, entry is row)
            if same(ours, theirs[(realm, scheme)]):
                continue
            key = (realm, scheme) if (realm, scheme) in expected else scheme
            want = expected.get(key, NO_EXPECTATION)
            line = f"{fname} {name} [{realm} {scheme}]: ours {fmt(ours)}, upstream {fmt(theirs[(realm, scheme)])}"
            if want is NO_EXPECTATION:
                problems.append(line)
            elif ours is None if want is None else isinstance(ours, dict) and normalise(ours.get("value")) == want:
                row_excused.append(f"{line}  ({reason})")
                fired.add((name, key))
            else:
                problems.append(f"{line}; expected ours {fmt(want)}")
        if not top_level:
            for block in sorted(required - row.keys()):
                problems.append(f"{fname} {name}: no {block} block; this exception requires one")
            for kind, detail in structure_problems(row, theirs, lookup, realms, token_names, css):
                line = f"{fname} {name}: {kind}" + (f", {detail}" if detail else "")
                if kind in allowed:
                    row_excused.append(f"{line}  ({reason})")
                    fired.add((name, kind))
                else:
                    problems.append(line)
        mismatches += problems
        excused += row_excused
        matched += not problems and not row_excused
    for name, (_, expected, allowed, _) in sorted(EXCEPTIONS.items()):
        keys = [k for k in expected if k in ("light", ("in-content", "light"))] if top_level else [*expected, *allowed]
        mismatches += [f"exception for {name} {k} no longer fires; remove it" for k in keys if (name, k) not in fired]
    return matched, mismatches, excused


def shape_problem(row):
    """Why a row is malformed, or None: entries are dicts of known keys, realms is 3 realms x 2 schemes."""
    def entry_problem(e):
        if not isinstance(e, dict) or "value" not in e:
            return "an entry without a value"
        extra = sorted(set(e) - set(ENTRY_KEYS))
        return f"an entry with unknown keys {extra}" if extra else None
    if not isinstance(row, dict) or "value" not in row:
        return "not a token entry"
    if set(row) - {"type", "dark", "realms", *ENTRY_KEYS}:
        return f"unknown keys {sorted(set(row) - {'type', 'dark', 'realms', *ENTRY_KEYS})}"
    if "dark" in row and entry_problem(row["dark"]):
        return f"a dark block that is {entry_problem(row['dark'])}"
    if "realms" in row:
        block = row["realms"]
        if not (isinstance(block, dict) and set(block) == set(REALMS)
                and all(isinstance(v, dict) and set(v) == set(SCHEMES) for v in block.values())):
            return f"a malformed realms block (needs exactly {', '.join(REALMS)} x {', '.join(SCHEMES)})"
        for realm, schemes in block.items():
            for scheme, e in schemes.items():
                if entry_problem(e):
                    return f"a realms {realm} {scheme} entry that is {entry_problem(e)}"
    return None


def entry_problems(entry, lookup, top):
    """Where an entry's value, unresolvedRefs, substituted and declared disagree with each other."""
    value = entry.get("value")
    if entry.get("declared") is False:
        return [] if value is None else ["an undeclared entry with a value"]
    refs = list(dict.fromkeys(resolve.ALIAS_REF_RE.findall(value))) if isinstance(value, str) else []
    out = []
    if "via" in entry:
        out.append("via on a declared entry")
    if any(r not in lookup for r in refs):
        out.append("refs to tokens this repo does not load")
    if entry.get("unresolvedRefs", []) != refs:
        out.append(f"unresolvedRefs that are not the refs in value ({refs})")
    if "substituted" in entry and not refs:
        out.append("substituted without unresolvedRefs")
    if "substituted" in entry and refs:
        if top:
            own = substitute(value, lookup)
            fits = own is None or normalise(own) == normalise(entry["substituted"])
        else:
            # Refs resolve per realm, so off the top level each {ref} only has to stand for something.
            parts = resolve.ALIAS_REF_RE.split(normalise(value))
            pattern = "".join("(.+?)" if i % 2 else re.escape(part) for i, part in enumerate(parts))
            fits = re.fullmatch(pattern, normalise(entry["substituted"]), re.DOTALL) is not None
        if not fits:
            out.append("substituted that is not value with its refs substituted")
    return out


def flat_value(v):
    """One comparable value per upstream answer, undeclared and invalid ones kept apart."""
    if "invalid" in v:
        return ("invalid", v["invalid"])
    if v.get("declared") is False:
        return ("undeclared", v.get("via"))
    return normalise(v["value"])


RAW = {}  # {(Sheet, env): {name: winning declaration, unresolved}}


def upstream_is_template(realms, token_names, realm, scheme, css):
    """Whether upstream's winning declaration here, aliases followed, is text around var()s to tokens."""
    sheet, env = realms[realm]
    if (sheet, env) not in RAW:
        best = {}
        for conds, important, rank, i, name, val, _ in sheet.records:
            if all(CONDITIONS[c](env) for c in conds) and (name not in best or best[name][0] < (important, rank, i)):
                best[name] = ((important, rank, i), val)
        RAW[(sheet, env)] = {n: v for n, (_, v) in best.items()}
    raw, seen = RAW[(sheet, env)].get(css), set()
    while raw is not None and css not in seen:
        seen.add(css)
        try:
            raw = split_light_dark(raw, scheme)
        except NotAColour:
            return False
        alias = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", raw)
        if not alias:
            return any(ref in token_names for ref in DANGLING_RE.findall(raw))
        css, raw = alias.group(1), RAW[(sheet, env)].get(alias.group(1))
    return False


def upstream_template(entry, realms, token_names, realm, scheme):
    """entry's value with each {ref} replaced by upstream's value for it here, or None if one has none."""
    failed = False

    def one(m):
        nonlocal failed
        ref = upstream_value(realms, token_names, realm, scheme, css_name(m.group(1)))
        failed = failed or "value" not in ref or ref["value"] is None
        return "" if failed else ref["value"]

    out = resolve.ALIAS_REF_RE.sub(one, entry["value"])
    return None if failed else out


def structure_problems(row, theirs, lookup, realms, token_names, css):
    """Blocks resolved/ must carry exactly where upstream differs, and the in-content invariant."""
    out = []
    entries = [(row, True, None)] + ([(row["dark"], False, ("in-content", "dark"))] if "dark" in row else [])
    entries += [(e, False, (r, s)) for r, v in row.get("realms", {}).items() for s, e in v.items()]
    for entry, top, where in entries:
        out += [(p, "") for p in entry_problems(entry, lookup, top)]
        # Off the top level, the template itself must be upstream's: its refs, filled in here, give the row's value.
        want = theirs.get(where) if where else None
        if (want and want.get("value") is not None and not entry.get("unresolvedRefs")
                and upstream_is_template(realms, token_names, *where, css)):
            out.append((f"{where[0]} {where[1]}: a value without the refs upstream's declaration has",
                        "upstream's declaration keeps embedded references"))
        if want and want.get("value") is not None and entry.get("unresolvedRefs") and isinstance(entry["value"], str):
            got = upstream_template(entry, realms, token_names, *where)
            if got is None or normalise(got) != normalise(want["value"]):
                out.append((f"{where[0]} {where[1]}: a value whose refs do not give upstream's value",
                            f"upstream {fmt(want)}, refs give {fmt(got)}"))
    flat = {k: flat_value(v) for k, v in theirs.items()}
    by_realm = any(flat[(r, s)] != flat[("in-content", s)] for r in REALMS for s in SCHEMES)
    dark_differs = flat[("in-content", "dark")] != flat[("in-content", "light")]
    if by_realm and "realms" not in row:
        out.append(("no realms block", "upstream differs by realm"))
    if "realms" in row and not by_realm:
        out.append(("a realms block", "upstream does not differ by realm"))
    if dark_differs and "dark" not in row:
        out.append(("no dark block", "upstream dark differs from light"))
    if "dark" in row and not dark_differs:
        out.append(("a dark block", "upstream dark equals light"))
    if row.get("unresolvedRefs") and "substituted" not in row:
        out.append(("unresolvedRefs without substituted", "the plan wants one wherever this repo can substitute"))
    if "realms" in row:
        ic = row["realms"]["in-content"]
        top = {k: row[k] for k in ENTRY_KEYS if k in row}
        if ic["light"] != top:
            out.append(("a realms in-content light entry", "must equal the top-level entry (invariant)"))
        if "dark" in row and ic.get("dark") != row["dark"]:
            out.append(("a realms in-content dark entry", "must equal dark (invariant)"))
    return out


def fmt(entry):
    if isinstance(entry, str):
        return repr(entry) if entry[:1] != "(" else entry
    if entry is None:
        return "(cannot substitute)"
    if "invalid" in entry:
        return f"invalid ({entry['invalid']})"
    if entry.get("declared") is False:
        return "undeclared" + (f" (needs {entry['via']})" if entry.get("via") else "")
    return repr(entry["value"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default=None, help="upstream commit (default: sync-manifest.json's)")
    parser.add_argument("--top-level", action="store_true", help="compare only each row's top-level value")
    parser.add_argument("--local-checkout", default=None, help="DEV/TEST ONLY: read sheets from this firefox checkout")
    args = parser.parse_args()

    manifest = json.loads((SCRIPT_DIR / "sync-manifest.json").read_text(encoding="utf-8"))
    ref = args.ref or manifest["source"]["commit"]
    with tempfile.TemporaryDirectory(prefix="acorn-realm-check-") as tmp:
        tmp = Path(tmp)
        try:
            if args.local_checkout:
                root, sha = Path(args.local_checkout), "(local checkout)"
            else:
                root = tmp / "firefox"
                sha = fetch(ref, root)
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"realm-check: fetching {ref} failed: {e}", file=sys.stderr)
            return 2
        try:
            if not (root / RESOLVER).is_file():
                raise Unmodelled(f"no {RESOLVER} under {root}")
            tr = load_upstream(root)
            check_sheets(tr, root)
            (tmp / "realms").mkdir()
            realms, token_names = realm_sheets(tr, root, tmp / "realms")
            matched, mismatches, excused = check(realms, token_names, published_rows(), args.top_level)
        except Unmodelled as e:
            print(f"realm-check: cannot model the sheets at {sha}: {e}", file=sys.stderr)
            return 2

    mode = "top-level values" if args.top_level else "every realm and scheme"
    print(f"Checked resolved/ against upstream {sha}, {mode}.")
    print(f"  {matched} rows match.")
    if excused:
        print(f"  {len(excused)} known exceptions:")
        for line in excused:
            print(f"    {line}")
    if mismatches:
        print(f"  {len(mismatches)} MISMATCHES:")
        for line in mismatches:
            print(f"    {line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
