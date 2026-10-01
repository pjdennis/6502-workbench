# asm1: the first assembler

What it is: the first self-hosting 6502 assembler (asm1), written 2022-11 to 2025-11 (first commit `60be16b` `asm1/start`; self-hosting `07b2118` `asm1/self-hosts`). It lived at `assembler/` in the repository root, then at `toolchain/asm1/` (2026-09-24), then here (`8159cb7`, 2026-09-29, pure `git mv`; earlier history via `git log --follow`).

Contents:
- `asm.asm`, `asm2.asm`, `asm3*.asm`, `asm4*.asm`, `asmbare*.asm`, `asmprg*.asm`, `minimalophis.asm`, `asm2ophis.asm`, `asm2vasm.asm`, `asm*v.asm`: successive assembler versions. The `v` versions are written in vasm syntax and are the bootstrap seed (`asm4v.asm`); `asm4b*.asm` are the self-hosted line, `asm4b13.asm` the latest.
- `common*.asm`, `instgen*.asm`, `hash_table*.asm`: shared definitions, the instruction-table generator, and the hash table.
- `emulator.c` (fake6502 core plus console I/O), `sidebyside.cpp`, `hexdump*.c`, `zeros.c`, `console_size.c`: host helpers, built by `Makefile`.
- `asmtestgen.sh` (full bootstrap chain), `asmtest*.sh`, `asmgo*.sh`, `go*.sh`, `goprg*.sh`, `runbranchtest.sh`: build and watch scripts.
- `branch-test*.asm`, `test*.asm`, `emhello*.asm`, `hello.asm`, and so on: test and sample programs. `notes`, `todo.txt`: the author's notes.

Why it is parked: asm2 replaced it. It is no longer run by `tools/check_all.sh` or CI. Its scripts still run from this directory (needs `vasm6502_oldstyle`, a C compiler and `hexdump`; `go*.sh` also need `zsh` and `fswatch`), but this is unsupported and unchecked.

Live successor: `asm/` (asm2, 18 stages `00`-`17`) for the assembler and `emulator/` for the emulator. The `emulator.c` here is the original single-file emulator that `emulator/` grew out of.
