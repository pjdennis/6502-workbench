# CLAUDE.md

Guidance for Claude Code working on the editor. `README.md` here describes the design; `asm/CLAUDE.md` describes the assembler that builds it.

## Build and test

Run from the repository root. The assembler resolves `.include` relative to the working directory, so the sources include `asm/17/...`, `editor/...` and `firmware/...` from there.

```bash
tools/build_all.sh asm    # once: the assembler the editor is built with (asm/17/out/asm.out)
editor/verify.sh          # screen model, console and direct-io builds, Michael build (needs vasm6502_oldstyle)
tools/build_all.sh editor # the tests, plus the stable builds that editor/bin/*.sh run
editor/bin/editor.sh FILE # run it in the terminal
```

Launchers are in `editor/bin/` (console or serial-terminal mode at several speeds; `editor-michael.sh` runs it on the emulated Michael board, `editor-michael-upload.sh` uploads it to a real one).

## Conventions

- Follow `rules`: red-green-refactor TDD for both buffer content and screen redraw, corner cases included, and reuse existing helpers.
- The editor uses the host services in `asm/17/environment.asm`; on Michael they are provided by the ROM (`firmware/boards/michael/`, layout in `michael_editor_layout.inc`).
