# Attic

Parked material: things that are no longer used, no longer build, or were never merged. Nothing here is built or tested, `tools/check_all.sh` and CI skip it, and `tools/firmware_manifest.py` skips it. Files are kept only so the owner can review them, and docs here describe the state of the code at the time, so paths inside them (`23/`, `assembler2/`, `toolchain/`, root-level names) are historical.

Each item keeps its original path relative to the time of the move, except where noted. History is still available with `git log --follow -- <path>` (for files that were moved twice, also `git log -- <old path>`). The moves are described in `docs/REORGANIZATION_PLAN.md` and the eras in `docs/history.md`.

For each item, decide whether to **delete** it (it stays in git history), **restore** it (`git mv` it back and fix it), or **keep** it here.

## Index of top-level entries

Directories (each has its own README):

| Entry | What it is | Why it is parked | Live successor |
|---|---|---|---|
| `asm1/` | First self-hosting 6502 assembler (2022-11 to 2025-11), its bootstrap scripts and its own `emulator.c` | Frozen since asm2 replaced it; not run by `check_all.sh` or CI | `asm/` (asm2 chain), `emulator/` |
| `asm-legacy/` | Early asm2 tests and scripts from before the stage directories, asm18-21 tests, two finished plans | Superseded by per-stage `asm/NN/tests/` | `asm/` |
| `assembler2/` | Leftovers of the old `assembler2/` directory: 6502 web server demo, terminal demo, review and plan notes, old scripts | Use removed stage `23/` paths and the old single-file emulator; socket API never merged | `asm/`, `emulator/`, `editor/` |
| `test/` | Early vasm syntax experiments and `makebin*.py` helpers | Most do not assemble with the current includes | `firmware/`, `tools/tests/` |
| `hardware/` | Two Michael Arduino-directory files that duplicate live ones | Duplicates | `hardware/michael/arduino/`, `firmware/programs/wendy/hello.s`, `tools/upload/compile_and_program.sh` |
| `unmerged/` | `git format-patch` exports of branch work that was never merged | Does not apply to the current tree | none (see its README) |

Upload scripts, wendy 2 programs and notes (single files):

| Entry | What it is | Why it is parked | Live successor |
|---|---|---|---|
| `compile_and_upload*.sh` (15) | Per-baud / per-board assemble-and-upload wrappers (2020-22), call `./vasm6502_oldstyle` and `transfer_*.py` from the repo root | Replaced by one parameterised script; the root-level paths they assume no longer exist | `tools/upload/compile_and_upload{,_michael,_wendy,_wendy2}.sh` |
| `transfer_*.py` (9) | Per-baud serial upload scripts; `transfer_with_length*.py` are older protocol variants | Replaced by `--port`, `--baudrate`, `--noreset` and USB auto-detect | `tools/upload/transfer.py` |
| `wendy2_call_eeprom.s`, `wendy2_hello_in_eeprom.s`, `wendy2_relocate_test.s`, `wendy2relocate.s`, `test_delay_wendy2.s` | Wendy 2 / rev b era programs (2022) | Include `base_config_wendy2.inc`, which no longer exists (deleted on michael_keyboard_wip, 2023); restored here only for review | `firmware/programs/wendy2/`, `firmware/boards/wendy2/base_config_wendy2c.inc` |
| `lcd.asm`, `lcd_test_2.asm` | Stand-alone LCD tests (2022-02) with hard-coded `$6000` VIA addresses | Do not assemble with the current includes | `firmware/lib/lcd/` routines |
| `DISPLAY_S` | Early assembly listing (2020), VIA port equates and LCD code | Stray, unreferenced | `firmware/lib/lcd/` |
| `display_routines_original.inc`, `upload_and_run.old.inc`, `michael_keyboard-v2.s.old` | Superseded copies of a display library, the RAM upload loader and the Michael keyboard demo (2020-21); the last two include `base_config_v1.inc`/`base_config_v2.inc` | Old versions of live files | `firmware/lib/`, `firmware/programs/michael/` |
| `a.out.old`, `a.out.reference` | Old build outputs from michael_keyboard_wip (2023) | Binary build artifacts | regenerate with `firmware/vasm` |
| `stty` | Stray 687-byte binary (a 6502 image with "Hello, from ram!") | Not referenced | none |
| `commands.txt`, `Connection 38400.stc`, `gdiff.sh` | Early notes (vasm flags, `screen`/`minipro` lines), serial-terminal settings, a `git diff` pager helper | Personal 2020 notes | `tools/upload/`, `firmware/README.md` |
| `TODO` | Two old Michael to-do items (modified ASCII key codes, editor up/down arrows) | Old (2022-02) | none |
| `plan-for-wendy2-merge-sort-demo.md` | Plan for `wendy2_merge_sort.s` (2026-05) | Implemented; kept as design record | `firmware/programs/wendy2/wendy2_merge_sort.s` |

## Where things came from

- **Assembler and toolchain reorganization (2026-09-29).** `toolchain/` was dissolved: `toolchain/asm1/` became `attic/asm1/`, `toolchain/asm2/legacy/` became `attic/asm-legacy/`, and `toolchain/asm2/.claude/` became `attic/asm-legacy/claude-plans/`. (asm2 itself became `asm/`, its editor `editor/`, and `prog8/` moved to the top level.)
- **Michael Arduino directory cleanup (2026-09-24).** `hardware/michael/arduino/` was split by purpose; the two duplicates went to `attic/hardware/michael/arduino/`.
- **Restored after the michael_keyboard_wip merge.** The merge accepted that branch's 2023 deletions of the upload scripts and Wendy 2 programs. They were restored here as they were at `claude/pld-hardware-memory-map-3hslxb` (`dd0cf45`), so every program from every branch stays reviewable. Earlier history is under their original root-level paths (`git log -- <name>`).
- **`unmerged/`.** Commits that exist only on branches that were never merged, exported with `git format-patch`. The branches themselves were deleted in the 2026-09 reorganization; each is kept as an `archive/<branch>` tag, so `git log archive/claude/install-hexdump-5CahY` shows the original commits. `claude/prog8-assembler-gap-analysis-pJ7nG` holds only generated build output, so nothing from it is kept.
