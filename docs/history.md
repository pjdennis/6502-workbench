# History

The repository has a single, unbroken git history, from `d297d44` ("initial", 2020-07-20) to today. Nothing has been rewritten. Every commit below still exists with its original hash, and checking one out gives the files, paths and scripts of that time.

> **Tags.** The milestone names below are annotated tags, listed in `tools/reorg/milestones.txt` and created by `tools/reorg/create_tags.sh --apply`. If `git tag` shows none, run that script, or use the commit hashes, which work either way.

## Building an older era

Check the era out into its own worktree, so your current checkout is untouched:

```bash
git worktree add ../6502-2021 eb3853c        # or a tag name once tags exist
cd ../6502-2021
```

Then build it the way that era did, using the table below.

**Before 2026-09, everything lived at the repository root.** Programs were assembled with `vasm6502_oldstyle` from the root (usually a `./vasm6502_oldstyle` binary or symlink there) and uploaded with the `compile_and_upload*.sh` / `transfer*.py` scripts of that commit. Use **vasm 1.9f**. vasm 2.0+ rejects some of the code, and 2.0d+ changes `.ascii` (see `firmware/README.md`).

## Timeline

| When | Milestone | Commit | How it was built then |
|---|---|---|---|
| 2020-07-20 | **Wendy** (v1) first programs, Ben Eater-style breadboard | `d297d44` (`wendy/first-light`) | Root `*.s` with vasm. `makerom.py` for the earliest ROM. |
| 2020-08 | Serial upload-and-run loader, per-baud `transfer_*.py` scripts, `base_config_v1.inc` | — | `./compile_and_upload_<baud>.sh prog.s` |
| 2021-01-22 | **Michael bring-up**: an Arduino emulates ROM/RAM/IO and the clock around a bare CPU, then loads real RAM (01-22) and programs the EEPROM in circuit (01-28) | `6b02ccc`, `cb4fc57` | Arduino IDE; `michael/` (now `hardware/michael/arduino/`) |
| 2021-04-06 | Michael runs standalone: first bring-up programs | `e8c33fc` | `michael/*.s` (now `firmware/programs/michael/bringup/`) |
| 2021-04-09 | **Michael** (v2): RAM upload working, v1/v2 config split | `eb3853c` (`michael/ram-upload`) | `./compile_and_upload*.sh`, with `base_config_v2.inc` |
| 2022-04-10 | **Wendy 2**: 65C02 + 22V10 | `6be57cd` (`wendy2/upload`) | as above, `base_config_wendy2.inc` |
| 2022-04-23 | Wendy 2 rev b (2 × 32K banks) | `14951d4` (`wendy2b/intro`) | `base_config_wendy2b.inc` |
| 2022-04-30 | Wendy 2 **rev c**: 512K memory map, `22V10-wendy2c.pld` | `ae2865b` (`wendy2c/intro`) | `base_config_wendy2c.inc`; PLD via GALasm |
| 2022-07-22 | Full wendy2c code set, rev b removed | `ca09ca6` (`wendy2c/full`) | |
| 2022-09 | Michael SPI graphic display | — | `hello_michael_spi.s`, `graphics_display.inc` |
| 2022-11-19 | **asm1** bootstrap begins | `60be16b` (`asm1/start`) | `cd assembler`, then the `go*.sh` / `asmtest*.sh` scripts of the time (`asmtestgen.sh` from 2022-11-26) |
| 2023-04-22 | `michael_keyboard_wip` forks: graphics console, keyboard driver; `wendy2c` renamed `wendy2` there | `536f200` (`fork/michael-keyboard`) | |
| 2024-02-11 | **BBC BASIC on Michael** through a MOS shim | `ecfa0b0` (`michael/bbc-basic`) | `upload_and_run_michael_beeb.s`; needs the external `../BeebEater` tree |
| 2025-11-15 | asm1 assembles itself byte-identically | `07b2118` (`asm1/self-hosts`) | `cd assembler && ./asmtestgen.sh` (needs `../vasm6502_oldstyle`, `hexdump`) |
| 2026-01-06 | **asm2** enters version control (flat `asmNN.asm` files) | `005e339` (`asm2/start`) | `cd assembler2 && ./asmtestgen.sh` |
| 2026-02-07 | Per-stage directories; first editor program | `b4e2f4a`, `cc718c8` (`editor/start`) | `cd assembler2 && ./asmtestgen.sh`; `python3 editor/tests/editor_tests.py` |
| 2026-02-13 | Chain renumbered 00–23 → **00–17** | `79b02ab` (`asm2/stages-00-17`) | `cd assembler2 && ./verify.sh` |
| 2026-02-21 | Emulator gets its own directory | `3b59d2d` (`emulator/split`) | `make -C assembler2` |
| 2026-03-28 | Emulator TCP socket API + 6502 web server (never merged) | `9b974e8` (branch `claude/install-hexdump-5CahY`) | See `attic/unmerged/install-hexdump/` |
| 2026-05-12 | Board-accurate **wendy2c** emulator machine | `646a262` | `make -C assembler2 test` (vasm on PATH) |
| 2026-05-31 | Prog8 work begins (`p8c` walking skeleton); BBC BASIC IV analysis | `2cf87c2`, `0231e2c` | `make -C assembler2 prog8-test` |
| 2026-06-07 | **p1 self-hosts** on banked Wendy 2 (byte-identical to host p8c) | `fb90b8e` (`prog8/self-hosts`) | `P1_WENDY_SELFHOST=1 make -C assembler2 p1-test` (~18 min) |
| 2026-09-23 | PLD cfg `$18` restored to upper ROM | `17e4a78` (`wendy2c/pld-cfg18-rom`) | `make -C assembler2 test` |
| 2026-09-24 | **Reorganization**: `michael_keyboard_wip` merged, new layout, CI; moved to the new repository `pjdennis/6502-workbench` | `reorg/before` … `reorg/after` | `make`, `tools/check_all.sh` (see the root README) |

## By area

**Boards.** Wendy (v1, 2020) and Michael (v2, 2021) share a library of LCD, keyboard, sound, serial and multitasking routines. Each board has its own `base_config_*.inc` and `initialize_machine_*.inc`. Wendy 2 (2022) moved to a 65C02 with PLD glue logic and banked RAM; its revisions are in `hardware/wendy2/README.md`. Work on Michael's graphics console and keyboard driver continued on `michael_keyboard_wip` from 2023 to 2024 (BBC BASIC). That branch also carried a Wendy 2 LED control and a 2026 PLD experiment. It was merged in the 2026 reorganization.

**Assemblers.** `asm1` (2022–2025, now `toolchain/asm1`) was bootstrapped with vasm. `asm2` (2026, now `toolchain/asm2`) starts from a small C assembler and builds 17 stages, each assembled by the one before. Stage history lives in the stage directories themselves. `BOOTSTRAP-OVERVIEW` summarises what each stage added.

**Editor.** A vi-like editor written in asm2's dialect (from 2026-02, `toolchain/asm2/editor`).

**Emulator.** It started as asm1's single-file `emulator.c` built on fake6502. From 2026-02 it is a modular emulator with a host-stub machine for the assemblers and editor. In 2026-05 it gained a board-level Wendy 2 rev c model generated from the real PLD equations, with web, audio and serial-link front ends (`emulator/`).

**Prog8.** A host compiler, then on-target compilers. It culminated in `p1` compiling itself on the emulated banked Wendy 2 (`toolchain/prog8`).

## Where things moved in 2026-09

`git log --follow <new path>` follows a file back through the move. The main moves:

| Before | After |
|---|---|
| root `*.inc` | `firmware/lib/<area>/` |
| root `base_config_*`, `initialize_machine_*`, `upload_and_run_{ram,eeprom}_*` | `firmware/boards/<board>/` |
| root `*.s` programs | `firmware/programs/<board>/` |
| root `transfer.py`, `compile_and_*.sh`; LCD webcam tools | `tools/upload/`; `tools/lcd-ocr/` |
| `22V10-wendy2c.pld`, `notes` | `hardware/wendy2/` |
| `michael/` sketches; its emulated-machine programs; its host scripts; its real-board programs | `hardware/michael/arduino/{6502-*,programs,host}/`; `firmware/programs/michael/bringup/` |
| `michael-2023-12-04.rom` | `hardware/michael/` |
| `font8x8/` | `firmware/fonts/` |
| `assembler/` | `toolchain/asm1/` |
| `assembler2/` (incl. `editor/`) | `toolchain/asm2/` |
| `assembler2/prog8/` | `toolchain/prog8/` |
| `assembler2/emulator/`, `assembler2/persistent_emulator.py` | `emulator/` |
| `bbc-basic-four-analysis/` | `research/bbc-basic-iv/` |
| stale, broken or superseded files | `attic/` (same relative path) |
