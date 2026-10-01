# asm-unified-parsing (16 patches, 2026-02-10)

Branch `asm-unified-parsing` (tag `archive/asm-unified-parsing`), exported with `git format-patch` (author Phil Dennis). It applies to `assembler2/` as it was on 2026-02-10.

What it does: a "unified parsing" refactor of the stage-23 assembler. In skipped conditional blocks (`SKIP_DEPTH > 0`) it follows the normal parsing path and suppresses state changes through a `SKIP_FLAG`, instead of a separate skipping path. Patch list: 0001 backports multiple data directives per line to stage 22, 0002 splits the v23 tests into topical subdirectories, 0003-0015 introduce `SKIP_FLAG` step by step and remove the old skip code, 0016 adds `UNIFIED_PARSING_ANALYSIS.md` (kept as `../../assembler2/UNIFIED_PARSING_ANALYSIS.md`).

Why it is parked: stage 23 was renumbered away on 2026-02-13 (chain is now `00`-`17` in `asm/`), and stage 17 still uses `SKIP_DEPTH`, so the patches do not apply.

Successor: none. Conditional assembly lives in `asm/17/`.
