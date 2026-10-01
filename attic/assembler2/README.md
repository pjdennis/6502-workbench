# assembler2: leftovers of the old `assembler2/` directory

What it is: items left from the pre-reorganization `assembler2/` directory (the asm2 workspace, 2026-01 to 2026-09), moved here 2026-09-24. The live parts became `asm/`, `emulator/` and `editor/`. All paths inside these files are from that time: the `23/` stage (renumbered away as `17`), `assembler2/emulator.out`, `./emulator/emulator.out` run from `assembler2/`.

| Item | What it is | Why parked |
|---|---|---|
| `webserver/` (`webserver.asm`, screenshot), `tests/` (`test_webserver.py`, `ansi_screen.py`) | A 6502 HTTP server demo and its test | Needs the emulator TCP socket API, which was never merged (see `../unmerged/install-hexdump/`) |
| `webapp/` (`server.py`, screenshot) | Python "hello world" web app | Not 6502-related |
| `terminal_demo/` | ANSI terminal demo (`demo.asm`, `run.sh`, `run_slow.sh`) | Includes `23/environment.asm` |
| `gogen.sh` | Watch mode for the old `emulator.c` | `emulator.c` no longer exists (see `../asm1/emulator.c`) |
| `new_asmtestgen.sh` | Alternate bootstrap-chain script | Superseded by `asmtestgen.sh` (now `asm/asmtestgen.sh`, `asm/verify.sh`) |
| `check_ascii.sh` | Scans `22/`, `23/` and `editor/` for non-ASCII bytes | Names removed stage directories |
| `REVIEW` | Code review of `asm22.asm` (before the renumber) | Historical; line numbers refer to that file |
| `UNIFIED_PARSING_ANALYSIS.md` | Analysis for the `asm-unified-parsing` refactor | The refactor was never ported to stage 17 (see `../unmerged/asm-unified-parsing/`) |
| `archive/` | Earlier plans: `REFactor_tests_plan.md` (per-version test folders, done), and three editor plans (`batching-plan.md`, `editor-small-buffer-test-optimization-plan.md`, `editor-unicode-plan.md`) | Editor plans belong to `editor/`; its current docs are `editor/README.md` and `editor/CLAUDE.md` |

Live successors: `asm/` (assembler chain), `emulator/`, `editor/`.
