# CLAUDE.md

Guidance for Claude Code working in this repository. The root `README.md` has the map; `docs/history.md` has the story.

## Layout

`hardware/` (boards), `firmware/` (vasm code for the boards), `emulator/`, `toolchain/{asm1,asm2,prog8}`, `tools/`, `research/`, `attic/` (parked for review: don't build, fix or delete things there unless asked). `toolchain/asm2/CLAUDE.md` has details for the assembler and editor.

## Build and test

```bash
make                      # emulator (run make and the emulator tests from the repo root)
tools/check_all.sh        # all suites: firmware asm1 asm2 emulator prog8 (~3.5 min); CI runs the same
tools/check_all.sh asm2   # one suite
```

- vasm: `vasm6502_oldstyle` on PATH. 1.9f and 2.0–2.0f give identical binaries; the manifest and CI use **2.0e**. Keep firmware portable: `.asciiz` not `.ascii`, no `#(>X)` / `#(\value)` in macros, quoted strings last in macro calls (see `firmware/README.md`; enforced by `tools/tests/test_vasm_portability.py`). Always assemble firmware through `firmware/vasm`, which adds the include path (`firmware/include-dirs`).
- `firmware/manifest.txt` holds the hash of every firmware binary. Refresh it after an intended output change: `python3 tools/firmware_manifest.py update --include-list firmware/include-dirs`.
- Slow opt-in tests are not in `check_all`: `make harte`, `P1_WENDY_SELFHOST=1`, `MERGE_SORT_FULL_N=1`, `make -C toolchain/prog8 wendy2-test`.

## Conventions

- Development follows red-green-refactor TDD.
- Moving files: make the move a pure `git mv` commit and put path fixes in a separate commit, so `git log --follow` keeps working.
- Firmware programs `.include` by bare file name, so file names must stay unique across the include directories.
- History is never rewritten. Old commits must stay buildable as they were.
