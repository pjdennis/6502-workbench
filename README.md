# 6502 workbench

Homebrew 6502 single-board computers and the software written for them: board firmware and peripheral drivers, self-hosting assemblers, a vi-like editor, a Prog8 compiler that compiles itself on the target, and a board-accurate emulator. It has grown since 2020. [`docs/history.md`](docs/history.md) tells the story and shows how to build each era.

This repository continues `pjdennis/6502-experiments`, reorganized in 2026-09 with its full history. Every commit of every old branch is here: on `main`, or, for work that was never merged, reachable from an `archive/<branch>` tag. There is one such tag for each old branch, recording where it pointed.

## Map

| Directory | What's there |
|---|---|
| [`hardware/`](hardware/) | The boards: **Wendy** (v1, 2020), **Michael** (v2, 2021) and **Wendy 2** (2022, now revision c). PLD equations, pin notes, revision history, and the Arduino monitor used with Michael. |
| [`firmware/`](firmware/) | Everything assembled with vasm for the real boards: shared libraries (`lib/`), per-board config and loaders (`boards/`), programs (`programs/`), fonts. |
| [`emulator/`](emulator/) | C emulator. `nmos-default` is a host-stub machine for the assemblers and editor. `wendy2c` models Wendy 2 rev c chip by chip (PLD, VIA, LCD, banked RAM), with web, audio and serial-link front ends. |
| [`asm/`](asm/) | The assembler, bootstrapped from nothing: `00/asm.c`, then stages `01`…`17`, each built by the one before. `17/` is the live assembler. |
| [`editor/`](editor/) | A vi-like text editor written in the assembler's dialect and built by stage 17. Runs in the emulator's terminal and on the Michael board. |
| [`prog8/`](prog8/) | Prog8 compiler work: host compiler `p8c`, `tinyp8`, the self-hosting `p1`, and custom upstream prog8c targets for Wendy 2. |
| [`tools/`](tools/) | Host-side tools: serial upload (`upload/`), webcam LCD OCR (`lcd-ocr/`), `makerom.py`, the firmware regression check, `check_all.sh`. |
| [`research/`](research/) | Analyses, e.g. a byte-level breakdown of BBC BASIC IV. |
| [`attic/`](attic/) | Stale, broken or superseded things kept for review, including the first assembler (`asm1/`, 2022–2025). See [`attic/README.md`](attic/README.md). |
| [`docs/`](docs/README.md) | History, the plan behind the 2026 reorganization, and the plans for Michael's ROM and upload format (both done). |

## Quick start

Prerequisites:
- `gcc`, `make` and `python3`
- **vasm** (`vasm6502_oldstyle`, CPU=6502 SYNTAX=oldstyle), on `PATH`. 1.9f to 2.0f all work; CI uses 2.0f from <http://phoenix.owl.de/tags/vasm2_0f.tar.gz>. See `firmware/README.md`.
- Optional: `hexdump`, `64tass`, Java with prog8c 12.1.1, and Python `playwright`. Tests that need a missing tool are skipped.

```bash
make                                   # build the emulator (emulator/emulator.out)
tools/build_all.sh                     # ...or the emulator, assembler and editor (about 30 seconds)
tools/check_all.sh                     # run the test suites, all but the slow prog8 (about 2 minutes)
tools/check_all.sh firmware asm        # ...or just some: firmware asm editor emulator prog8

# Assemble and upload a program to a board over serial
tools/upload/compile_and_upload_wendy2.sh firmware/programs/wendy2/hello_ram_4000_wendy2c.s

# Try Wendy 2 without the hardware
bash emulator/demo_wendy2c.sh --live
```

CI (`.github/workflows/ci.yml`) runs all five `check_all.sh` suites, prog8 included, on every push.
