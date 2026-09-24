# Attic

Things that are no longer used or no longer work, kept here for the owner to review. Nothing here is built or tested. `tools/firmware_manifest.py` skips this directory.

Each item keeps its original path. For example, `attic/assembler2/webserver/` used to be `assembler2/webserver/`. Its full history is still available with `git log --follow`. Moved in the reorganization, 2026-09-24. See `docs/REORGANIZATION_PLAN.md`.

For each item, decide whether to **delete** it (it stays in git history), **restore** it (`git mv` it back and fix it), or **keep** it here.

| Item | Last changed | Why it's here |
|---|---|---|
| `stty` | 2020 | Stray binary (687 bytes), not referenced |
| `DISPLAY_S` | 2020 | Stray assembly listing |
| `a.out.old`, `a.out.reference` | 2023 | Old build outputs from michael_keyboard_wip |
| `display_routines_original.inc`, `upload_and_run.old.inc`, `michael_keyboard-v2.s.old` | 2020–21 | Superseded copies of live files |
| `lcd.asm`, `lcd_test_2.asm` | 2022-02 | Stand-alone LCD tests with hard-coded `$6000` addresses; no longer assemble |
| `commands.txt`, `gdiff.sh`, `Connection 38400.stc` | 2020 | Early notes, a git-diff helper, and serial-terminal settings |
| `TODO` | 2022-02 | Old to-do list |
| `test/` | 2020–23 | vasm syntax experiments and `makebin*.py`; most don't assemble |
| `plan-for-wendy2-merge-sort-demo.md` | 2026-05 | Plan for `wendy2_merge_sort.s`, which has been implemented |
| `assembler2/webserver/`, `assembler2/tests/` | 2026-03/07 | 6502 HTTP demo and its test. They need the emulator socket API, which was never ported (branch and tag `archive/claude/install-hexdump-5CahY`), and use stage `23/` paths |
| `assembler2/terminal_demo/` | 2026-02 | ANSI terminal demo; uses stage `23/` paths |
| `assembler2/webapp/` | 2026-03 | Python "hello world" server; not 6502-related |
| `assembler2/gogen.sh` | 2026-02 | Watch mode for `emulator.c`, which no longer exists |
| `assembler2/new_asmtestgen.sh` | 2026-02 | Alternate bootstrap-chain script, superseded by `asmtestgen.sh` |
| `assembler2/check_ascii.sh` | 2026-02 | Scans the old `22/` and `23/` stages |
| `assembler2/REVIEW` | 2026-02 | Review of asm22 (before the renumber) |
| `assembler2/archive/` | 2026-02 | Earlier plan documents |
| `assembler2/UNIFIED_PARSING_ANALYSIS.md` | 2026-07 | Analysis for the `asm-unified-parsing` refactor, which was never ported to stage 17 (branch and tag `archive/asm-unified-parsing`) |

## Michael Arduino directory cleanup (2026-09-24)

| Item | Why it's here |
|---|---|
| `hardware/michael/arduino/hello-again.s` | Byte-identical to `firmware/programs/wendy/hello.s` (Ben Eater's hello world, copied to test the new board) |
| `hardware/michael/arduino/compile_and_program.sh` | Same as `tools/upload/compile_and_program.sh` (minipro EEPROM burner) |

## Restored after the michael_keyboard_wip merge

The merge accepted michael_keyboard_wip's 2023 deletions of these files. They were restored here, as they were at `claude/pld-hardware-memory-map-3hslxb` (`dd0cf45`), so every program from every branch stays reviewable. Their earlier history is under their original root-level paths (`git log -- <name>`).

| Item | Why it's here |
|---|---|
| `compile_and_upload*.sh` (15), `transfer_*.py` (9) | Per-baud and per-board copies of the upload scripts. They were replaced by the parameterised `transfer.py` (`--port`, `--baudrate`, `--noreset`, USB auto-detect) and `compile_and_upload_{michael,wendy,wendy2,wendy2_noreset}.sh`. `transfer_with_length*.py` are older protocol variants. |
| `wendy2_call_eeprom.s`, `wendy2_hello_in_eeprom.s`, `wendy2_relocate_test.s`, `wendy2relocate.s`, `test_delay_wendy2.s` | Wendy 2 / rev b-era programs (2022). They include `base_config_wendy2.inc`, which no longer exists, and were deleted on michael_keyboard_wip in 2023. |

## Unmerged branch work (`unmerged/`)

Commits that exist only on branches that were never merged, exported with `git format-patch` so they can be read here. The branches themselves are kept in this repository as `archive/…` branches (and `archive/…` tags).

| Item | What it is |
|---|---|
| `unmerged/asm-unified-parsing/` (16 patches, 2026-02-10) | A "unified parsing" refactor of the old stage-23 assembler that replaces the SKIP_DEPTH skip path with a SKIP_FLAG, plus a backport to stage 22 and a test split. Stage 23 was later renumbered away, and stage 17 still uses SKIP_DEPTH, so these don't apply as-is. |
| `unmerged/install-hexdump/` (5 patches, 2026-03-28) | The emulator TCP socket API (patches 3–5, against the old single-file `assembler2/emulator.c`), the 6502 web server demo, and a Python hello-world web app. Only the demos reached the tree (now `attic/assembler2/webserver/` etc.); the emulator socket code was never ported. |

`claude/prog8-assembler-gap-analysis-pJ7nG` holds only generated build output (`__pycache__`, a test `.wav`, `prog8/upstream/out/*.asm`), so nothing from it is kept.
