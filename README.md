# 6502 workbench

Homebrew 6502 single-board computers and the software written for them: board firmware and peripheral drivers, self-hosting assemblers, a vi-like editor, a Prog8 compiler that compiles itself on the target, and a board-accurate emulator. It has grown since 2020. [`docs/history.md`](docs/history.md) tells the story and shows how to build each era.

This repository continues `pjdennis/6502-experiments`, reorganized in 2026-09 with its full history. Every commit of every old branch is here: `main` plus three `archive/…` branches for work that was never merged. The `archive/<branch>` tags record where each old branch pointed.

## Map

| Directory | What's there |
|---|---|
| [`hardware/`](hardware/) | The boards: **Wendy** (v1, 2020), **Michael** (v2, 2021) and **Wendy 2** (2022, now revision c). PLD equations, pin notes, revision history, and the Arduino monitor used with Michael. |
| [`firmware/`](firmware/) | Everything assembled with vasm for the real boards: shared libraries (`lib/`), per-board config and loaders (`boards/`), programs (`programs/`), fonts. |
| [`emulator/`](emulator/) | C emulator. `nmos-default` is a host-stub machine for the assemblers and editor. `wendy2c` models Wendy 2 rev c chip by chip (PLD, VIA, LCD, banked RAM), with web, audio and serial-link front ends. |
| [`toolchain/asm1/`](toolchain/asm1/) | First self-hosting 6502 assembler (2022–2025), bootstrapped with vasm. Frozen. |
| [`toolchain/asm2/`](toolchain/asm2/) | Second assembler, bootstrapped from nothing: `00/asm.c`, then stages `01`…`17`, each built by the one before. `17/` is the live assembler. Also holds the **editor** (`editor/`). |
| [`toolchain/prog8/`](toolchain/prog8/) | Prog8 compiler work: host compiler `p8c`, `tinyp8`, the self-hosting `p1`, and custom upstream prog8c targets for Wendy 2. |
| [`tools/`](tools/) | Host-side tools: serial upload (`upload/`), webcam LCD OCR (`lcd-ocr/`), `makerom.py`, the firmware regression check, `check_all.sh`. |
| [`research/`](research/) | Analyses, e.g. a byte-level breakdown of BBC BASIC IV. |
| [`attic/`](attic/) | Stale, broken or superseded things kept for review. See [`attic/README.md`](attic/README.md). |
| [`docs/`](docs/) | History, and the plan behind the 2026 reorganization. |

## Quick start

Prerequisites:
- `gcc`, `make` and `python3`
- **vasm** (`vasm6502_oldstyle`, CPU=6502 SYNTAX=oldstyle), on `PATH`. 1.9f to 2.0f all work; CI uses 2.0e from <http://phoenix.owl.de/tags/vasm2_0e.tar.gz>. See `firmware/README.md`.
- Optional: `hexdump`, `64tass`, Java with prog8c 12.1.1, and Python `playwright`. Tests that need a missing tool are skipped.

```bash
make                                   # build the emulator (emulator/emulator.out)
tools/check_all.sh                     # run every test suite (about 3.5 minutes)
tools/check_all.sh firmware asm2       # ...or just some: firmware asm1 asm2 emulator prog8

# Assemble and upload a program to a board over serial
tools/upload/compile_and_upload_wendy2.sh firmware/programs/wendy2/hello_ram_4000_wendy2c.s

# Try Wendy 2 without the hardware
bash emulator/demo_wendy2c.sh --live
```

CI (`.github/workflows/ci.yml`) runs the five `check_all.sh` suites on every push.
