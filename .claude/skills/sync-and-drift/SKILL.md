---
name: sync-and-drift
description: >
  Run acorn-contracts' full sync/drift/Figma-check chain (token sync, component source
  drift, Figma existence checks for both tokens and components), regenerate the derived
  files, and close with one consolidated summary. Use whenever the user asks to sync
  tokens, check drift, check Figma, or just says "let's sync" / "check drift" / "catch up
  with upstream" in this repo. Do NOT use for a one-off doc-staleness or writing-quality
  audit (those are separate, broader passes, not part of this routine chain).
---

# Sync and drift

This repo has no single command that runs the whole chain. It's four independently-readable
scripts, run in order, then derived files regenerated, then one human-facing summary.
Building one combined script was considered and rejected: it would couple four
independently-debuggable things into one thing that's harder to debug when one leg
breaks. Run them separately, every time.

## The chain, in order

```sh
python3 token-api/sync.py              # 1. fetch + convert real upstream tokens (network)
python3 token-api/figma-check.py       # 2. token-level Figma existence check
python3 component-api/check-drift.py   # 3. component source-file drift (no --advance)
python3 component-api/figma-check.py   # 4. component-level Figma existence check (no --advance)
python3 token-api/resolve.py           # 5. re-resolve: sync.py just rewrote its inputs
python3 build-manifest.py              # 6. token basenames may have changed
python3 build-search-index.py          # 7. any of the above, or any doc edit, feeds this
python3 check-index-data.py            # 8. validate index.html DATA vs component-api/
python3 validate-schemas.py            # 9. validate every entry against its schema
```

**Step 4 needs a fresh pull first to mean anything.** `component-api/figma-check.py`
only diffs whatever's sitting in `component-api/figma-components-dump.json`. It does not
fetch. Re-pull that dump via the Runlayer Figma MCP connector
(`figma_list_file_components_for_code_connect`) before step 4 if you want it to report
real additions/removals since last time, not just "no changes" because nothing refreshed.
Same logic applies to `token-api/figma-token-map.json` from step 2 feeding step 1's
cross-reference annotations, so run step 1 before step 2, not after, or the annotations
reflect a stale prior sync's Figma state.

**Never pass `--advance`** to `check-drift.py` or `component-api/figma-check.py` without
the user explicitly triaging the diff first. Advancing before looking spends the signal
for free. The baseline then reports nothing on the next run even though nobody actually
checked anything. See `AGENTS.md`'s "Syncing with upstream" section for the full rule.

## Before summarizing

- **Re-read the actual current output, every time.** Don't paraphrase from memory of an
  earlier run, even one from the same session. A tool's bucket/count is cheap to re-check
  and expensive to misreport.
- **Give ONE consolidated summary across all 9 steps**, not a separate dump per script.
  `sync.py`'s own token-change report already groups by owning component (via
  `token-api/id-map.json`) and annotates each with Figma status. Lead with that, not a
  flat list.
- **Separate genuinely new findings from permanent, expected states.** Some things will
  show up on every single run and are not regressions: a component id whose words are a
  strict subset of a compound Figma name (e.g. `textarea` vs "Input Textarea") will always
  score as "near miss," never "exact." That's the matcher working correctly, not a flag
  to re-investigate each time. A base-stem token with no entry in `id-map.json` is only
  worth naming once, not re-flagging every run once it's been noted.
- **Check `~/Documents/acorn-next.md`'s "Evaluated and rejected" section before proposing
  any new tooling** in response to something this chain surfaces. Several plans have
  already been built and discarded; don't re-propose them.
- **Don't fabricate counts or dates.** No hardcoded numbers in any doc fix this surfaces,
  no `verifiedAt` without actually reading the cited source.

## Separate, not part of this routine

A full doc-staleness sweep (stale counts, broken links, leftover references to something
just renamed) and a writing/headings-quality audit are both heavier, broader passes. Only
run those when the user actually asks for them, not automatically after every sync.
