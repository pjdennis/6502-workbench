# Repository reorganization plan

Status: **done (2026-09-24).** The reorganized history was pushed to a new repository, `pjdennis/6502-workbench`, instead of rewriting `pjdennis/6502-experiments` in place. See [§6](#6-go-live-checklist-not-yet-run).

## 1. Current state

### 1.1 History shape

- There is **one connected history** of 2,562 commits from a single root, `d297d44` (2020-07-20, "initial").
  - Note: Claude Code web sessions clone shallowly. Run `git fetch --unshallow` before analysing, or the history appears to have re-roots at `49d4c4c` and `2d486fc` that aren't really there.
- `main` (tip `9c3b88e`, 2026-01-10) is far behind. All current work is on a chain of `claude/*` branches, and each branch contains the previous ones. The tip of the chain is `claude/pld-hardware-memory-map-3hslxb` (`dd0cf45`, 2026-09-23), which is 1,545 commits ahead of `main`.
- `michael_keyboard_wip` forked from `main` at `536f200` (2023-04-22). It has 235 commits of its own: 225 from 2023, 7 from 2024 and 3 from 2026. It has never been merged back.

### 1.2 Projects that share this repo

| Area | Where it is today | Toolchain | Activity |
|---|---|---|---|
| SBC firmware for three boards: **Wendy (v1)**, **Michael (v2)** and the **Wendy2 family (wendy2 → 2b → 2c, 65C02 + 22V10 PLD, 512 KiB banked RAM)** | ~200 flat files at the root (`*.s`, `*.inc`) | vasm6502_oldstyle | 2020 → 2026 |
| Peripheral drivers: HD44780 LCD (4-bit/8-bit), SPI/parallel graphic display, keyboard via shift registers, sound/music, bit-banged serial, multitasking | root `*.inc` | vasm | 2020 → 2023 |
| Host tools: `transfer*.py` (serial upload), 15 `compile_and_upload_*.sh`, `makerom.py`, LCD OCR tools | root | Python and sh | |
| Arduino monitor/programmer sketches for Michael | `michael/` | Arduino | 2021 |
| Fonts | `font8x8/`, `character_patterns*.inc` | C and Python | |
| **asm1**: first self-hosting assembler (fake6502-based `emulator.c`, chain asm4v → asm4b13) | `assembler/`, duplicated in `assembler2/legacy/` | C and 6502 | 2022-11 → 2025-11 (frozen) |
| **asm2**: bootstrap chain from zero (`00/asm.c` → stages 01..17; 00–16 are frozen directory snapshots, only 17 is live) | `assembler2/NN/` | C and 6502 | 2026-01 → 2026-06 |
| **Editor**: vi-like, ~7.5k lines of 6502 | `assembler2/editor/` | asm2 stage 17 | 2026-02, 2026-07 |
| **Emulator**: fake6502 core; `nmos-default` host-stub machine plus a board-accurate `wendy2c` machine (PLD equations generated from `22V10-wendy2c.pld`); web, audio, serial-link and tracing features | `assembler2/emulator/`, `persistent_emulator.py` | C and Python | 2026-02 → 2026-09 |
| **Prog8 bootstrap**: p8c (Python), tinyp8, p1 self-hosting compiler; self-hosts on banked wendy2c (`fb90b8e`) | `assembler2/prog8/` | vasm, 64tass, prog8c | 2026-05 → 2026-06 |
| **BBC BASIC**: a MOS shim for Michael (`michael_beeb.s`, `ecfa0b0`, 2024-02-11) on `michael_keyboard_wip` only; it needs the external `../BeebEater` tree | root on mkwip | vasm | 2024 |
| BBC BASIC IV ROM analysis | `bbc-basic-four-analysis/` | Python | 2026-05 |
| Misc: webserver (6502 HTTP), terminal_demo, webapp, vscode/vim syntax | `assembler2/` | | stale |

### 1.3 Coupling that constrains the layout

- The emulator's `Makefile` reads `../22V10-wendy2c.pld`, which is hardware, and turns it into C.
- The emulator's goldens and demos assemble root-level `*_wendy2c.s` firmware.
- The editor `.include`s `17/environment.asm`, `17/macros.asm` and `17/to_decimal.asm`, and it is built by `17/out/asm.out`.
- prog8 runs on the emulator (both machines) and assembles with vasm.
- The bootstrap chain (`asmtestgen.sh`) builds stages in sequence, so each stage depends on the one before it.

Because of this coupling, splitting into several repos would need submodules or vendored copies in both directions, for example hardware → emulator and firmware → emulator tests. For a single developer that costs more than it gains.

### 1.4 Branch inventory and disposition

| Branch | Relation to chain tip (`pld-hardware-memory-map`) | Disposition |
|---|---|---|
| `claude/pld-hardware-memory-map-3hslxb` | tip | **becomes the new `main`** (fast-forward) |
| `claude/hdl-code-pld-uh33sg`, `editor-branch-merge-e7x682`, `assembler-v17-tests-copt83`, `prog8-bootstrap-continue-6Pzo0`, `review-wendy2-plan-MOfnA`, `review-stack-optimization-RvSu5`, `sync-text-editor-branch-AUWPA`, `setup-editor-assembler2-5cnH6`, `wendy2-emulator`, `text-editor`, `assembler2-tracking`, `main` | fully contained | delete (their commits stay reachable from main) |
| `claude/bbc-basic-four-analysis-JBZDp` (3 commits) | content copied in `5a7dd51` and identical | **real merge** (clean, so the 3 commits become ancestors), then delete |
| `michael_keyboard_wip` (235 commits) | diverged since 2023-04-22 | **real merge** (see Phase 1b), then delete |
| `asm-unified-parsing` (16 commits) | SKIP_FLAG refactor of old stage 23, never ported; noted as superseded in `5a7dd51` | tag `archive/asm-unified-parsing`, delete the branch |
| `claude/install-hexdump-5CahY` (22 commits) | webserver/webapp already copied; the **emulator socket API (`c3d9641`, `8ee8e70`, `9b974e8`) was never ported** and clashes with current stub addresses | tag `archive/install-hexdump`, open an issue "port socket API to modular emulator", delete the branch |
| `claude/prog8-assembler-gap-analysis-pJ7nG` (1 commit) | build outputs only (`.pyc`, `.wav`, generated `.asm`) | delete, no tag |

## 2. Future state

### 2.1 Decision: one repo, reorganized, with no history rewrite

- **Keep a single repository.** The coupling in §1.3 is real. Each area gets a top-level directory with its own README, so any area can later be split out with `git filter-repo --subdirectory-filter` if that becomes worthwhile.
- **Do not rewrite history.** The history is already connected and complete. Every reorganization step is a new forward commit. Because of this:
  - every old commit keeps its hash and still builds with the paths and scripts of its own time (`git worktree add /tmp/w <tag>`);
  - `git log --follow` and `git blame -C -C` follow files across the moves, provided the moves are **pure-rename commits** (§3, rule R2);
  - hash references in commit messages, such as "see 5a7dd51", stay valid.
- Rename the repo? `6502-experiments` → `6502-workbench`. This is optional; GitHub redirects old URLs.

### 2.2 Target layout

> **As built (2026-09-24), this differs from the sketch below in four places. The root `README.md` describes the real layout.**
> - The board directories are named `wendy`, `michael` and `wendy2`.
> - There is no `firmware/Makefile`. `firmware/vasm` plus `firmware/include-dirs` provide the include path, and board config files keep their original names.
> - The asm2 stages stay flat (`toolchain/asm2/00`…`17`).
> - The editor stays in `toolchain/asm2/editor/`.

```
README.md                  map of the repo + quick "how to build X"
CLAUDE.md                  build/test commands (from assembler2/.claude/CLAUDE.md)
docs/
  history.md               eras, milestone tags, how each thing was built at the time
  REORGANIZATION_PLAN.md   this file
hardware/
  wendy/                   v1 notes (6522 @ $6000, 5 MHz, 4-bit LCD, PORTA banking)
  michael/                 v2 notes; arduino/ (from michael/: monitor/programmer sketches)
  wendy2/                  board "Wendy 2"; revisions.md (2 → 2b → 2c), 22V10-wendy2c.pld, memory map
firmware/                  everything assembled by vasm for real boards
  Makefile                 BOARD=wendy|michael|wendy2; -I lib/... ; build-all + manifest
  boards/
    wendy/     base_config.inc  initialize_machine.inc  upload_and_run_{ram,eeprom}.s
    michael/   (same)            + beeb/ (BBC BASIC MOS shim; expects external BeebEater)
    wendy2/    (same)            + verification, monitor, eeprom tools (rev c hardware)
  lib/
    core/      6522, delay, utilities, copy_memory, to_decimal, convert_to_hex, buffer
    lcd/       display_routines{,_4bit,_8bit}, display_update*, display_* helpers
    graphics/  graphics_display, full_screen_console*, character_patterns*, graphics_* (mkwip)
    keyboard/  key_codes, key_names, keyboard_typematic, keyboard_driver (mkwip)
    sound/     sound, musical_notes*, morse
    tasks/     prg_*.inc (multitasking demo tasks)
    serial/    upload_and_run.inc
  programs/
    common/    board-agnostic tests/demos (buffer_test, to_decimal_test, …)
    wendy/  michael/  wendy2/     board-specific demos and tests
  fonts/       font8x8/ sources + generators
tools/                     host-side
  upload/      transfer.py (the single parameterised version from mkwip: --port --baudrate
               --noreset, USB autodetect), compile_and_upload.sh, compile_and_program.sh
  makerom.py, keynames/ (COMMANDS generator), lcd-ocr/ (lcd_ocr, lcd_inspect, calibrate)
emulator/                  from assembler2/emulator/ + persistent_emulator.py
  (Makefile references ../hardware/wendy2/22V10-wendy2c.pld and ../firmware/…)
toolchain/
  asm1/                    from assembler/ (+ extras only found in assembler2/legacy/)
  asm2/
    stages/00..16/         frozen bootstrap snapshots (load-bearing: the chain runs them)
    src/                   live stage 17 (the working assembler)
    bootstrap.sh           was asmtestgen.sh; run_tests.py, verify.sh
    pyasm/                 Python work-alike
  editor/
  prog8/
  syntax/                  vscode-asm6502/, asm6502.vim
research/
  bbc-basic-iv/            from bbc-basic-four-analysis/
attic/                     kept but not maintained: webserver, terminal_demo, webapp,
                           old plans/notes .md, lcd.asm, one-off experiments
```

Design notes:

- **Firmware include paths.** vasm's `-I` means the `.include "display_routines.inc"` lines don't need to change when the `.inc` files move into `lib/*`. The Makefile passes `-I` for each lib subdirectory and the board directory, so a program picks up its board's `base_config.inc` from `-I boards/$(BOARD)`. This replaces the `_v1` / `_v2` / `_wendy2c` filename suffixes.
- **Stage 17 vs a `src/` rename.** If moving stage 17 to `src/` makes the chain script awkward, keep the directory named `17/`. What matters is that the frozen stages are visibly separate from the live one.
- **Board name (decided 2026-09-24).** The board is **Wendy 2**, and the original v1 is **Wendy**. "2c" is *revision c* of Wendy 2, and the history supports this:
  - **Wendy 2** (`6be57cd`, 2022-04-10): 65C02, 4 MHz, VIA at `$F000`, no RAM banking.
  - **Rev b** (`14951d4`, 2022-04-23): 4 bank lines on PORTB, "2 banks of 32K".
  - **Rev c** (`ae2865b`, 2022-04-30): the commit message says the new memory map is "designed for a 512K RAM chip". It adds a 5th bank line (PB4), and the 22V10 PLD adds a dual-speed clock and 32 bank configurations.
  - The later crystal swap to 9.72 MHz (`ba13b19`) and the PLD edits happened within rev c.
  - So directories use `wendy2`, and revision-specific artifacts keep the `c`: `22V10-wendy2c.pld` and the emulator's `--machine wendy2c`, which models rev c exactly. `hardware/wendy2/revisions.md` records 2 / 2b / 2c. The `_wendy2c` filename suffixes go away with the move into `boards/wendy2/`, which also agrees with mkwip's 2023 rename (`5440a45`).

## 3. Migration plan

### Ground rules

- **R1 Green → move → green.** Following red-green-refactor, a reorganization is a pure refactor. First add the checks that prove nothing changed, and watch them fail when they should. Every move must then keep them green, with byte-identical outputs.
- **R2 Pure-rename commits.** Each move is its own commit containing only `git mv` (100% similarity). Path fixes (Makefiles, `.include`, scripts) go in a *separate* following commit. Git's rename detection then always works, so `--follow` and `blame` survive.
- **R3 One area per PR.** Small PRs into `main`, each with its tests green.
- **R4 Tag before deleting.** A branch is deleted only after its tip is reachable from `main` or has an `archive/*` tag.

### Phase 0: Safety net and baseline

1. `git fetch --unshallow`. Push `archive/<branch>` tags for **every** current branch tip, and keep a `git bundle create 6502-all.bundle --all` offline.
2. Record the green baseline on the chain tip:
   - `make -C assembler2 test` (emulator, prog8, tinyp8, p1)
   - `assembler2/asmtestgen.sh` (bootstrap chain, stage 17 self-assembles identically, 104 in-assembler tests)
   - `assembler2/verify.sh` (editor and terminal tests)
3. **New test, firmware golden manifest.**
   - Write `tools/firmware_manifest.py`. It assembles every firmware `.s`/`.asm` with both vasm flag sets (RAM upload `-esc`, EEPROM without it) and compares sha256 values against `firmware-manifest.txt`.
   - Red: the manifest doesn't exist yet, or an entry was deliberately corrupted. Green: the manifest is generated from the current tree.
   - Record the files that don't build today, such as the `wendy2_*` files that include a missing `base_config_wendy2.inc`, and the stand-alone `lcd.asm`. That way "already broken" is never confused with "broken by the move".
4. Add `tools/check_all.sh` (the suites firmware, asm1, asm2, emulator) and a GitHub Actions workflow that runs it.
   - The runner needs `vasm6502_oldstyle` (build it from source in CI); prog8c and 64tass are needed for the upstream tests.
   - Every later PR must pass this workflow.

### Phase 1: Consolidate branches (history-bearing merges)

- **1a.** Fast-forward `main` to `claude/pld-hardware-memory-map-3hslxb`. Before that, check the September PLD decision (`17e4a78`: cfg `$18` = ROM upper + lower bank 2).
- **1b.** Merge `michael_keyboard_wip` into `main` with a real merge, so the 235 commits (graphics console, keyboard driver, BBC BASIC shim, generic transfer.py) become ancestors. Expected conflicts and how to resolve them:
  - **wendy2 ↔ wendy2c renames.** Keep main's `*_wendy2c` names during the merge (all 2026 work and the emulator tests use them); Phase 3 step 7–8 then drops the suffix for everyone. Carry over mkwip's content edits (LED control `71298d5`; CONTROL_BUTTON/LED is already ported in `67e1a40`).
  - **PLD cfg `$18`.** mkwip `27bbc44` makes it RAM; main `17e4a78` makes it ROM. **Decided: upper ROM** (main's version), which the emulator config-map tests enforce. Take mkwip's other `27bbc44` changes only where they don't conflict with this.
  - **transfer.py and upload scripts.** Take mkwip's parameterised `transfer.py` and its `compile_and_upload_{board}.sh`. Delete the per-baud copies.
  - **Diverged `.inc` files** (base_config_v2, upload_and_run.inc, graphics_display, key_codes, key_names, morse, musical_notes, …). Take mkwip for Michael-specific changes. For shared files, merge by hand and let the firmware manifest show which outputs changed on purpose.
  - Binary `michael-2023-12-04.rom`, `a.out.old`, `a.out.reference`: keep the ROM (document it in `hardware/michael/`) and drop the `a.out.*` files.
  - Regenerate `firmware-manifest.txt` and review each changed hash in the PR.
- **1c.** Merge `claude/bbc-basic-four-analysis-JBZDp`. The content is identical, so the merge is clean.
- **1d.** Delete the merged branches. Tag and delete `asm-unified-parsing` and `claude/install-hexdump-5CahY`. Open an issue to port the socket API to `emulator/` at new stub and port addresses. Delete `claude/prog8-assembler-gap-analysis-pJ7nG`.

### Phase 2: Hygiene in place (no moves yet)

- `.gitignore`: `out/`, `a.out`, `__pycache__/`, `*.pyc`, `*.wav` under test outputs.
- Remove junk:
  - `stty` (stray binary) and `DISPLAY_S` (stray listing)
  - `*.old`, `display_routines_original.inc`, `upload_and_run.old.inc`
  - numbered duplicate scripts: keep each only if a later file doesn't supersede it
- Fold `assembler2/legacy/` into `assembler/`. Only `bootstrap0.sh`, `tests/asm18..21_tests.txt` and a few `test*.asm` are unique; move those, then delete the 45 byte-identical copies.
- Fix stale references:
  - `23/` paths in `terminal_demo`, `webserver` and `tests/test_webserver.py`
  - `check_ascii.sh` and `gogen.sh`
  - `assembler2/README.md` still says 23 levels
- The firmware manifest and the Phase 0 tests must stay green, except for the reviewed deletions.

### Phase 3: Restructure (each step = one pure-rename commit + one path-fix commit + green CI)

Do the most depended-upon pieces first, so later steps only need their paths fixed once:

1. `22V10-wendy2c.pld` → `hardware/wendy2/`. Fix the emulator Makefile and `pld_to_c.py` paths.
2. `assembler2/emulator/` and `persistent_emulator.py` → `emulator/`. Fix the Makefile split (the emulator gets its own Makefile; the prog8 targets move with prog8) and the Python imports.
3. `assembler/` → `toolchain/asm1/`.
4. `assembler2/{00..17}`, the chain scripts, `run_tests.py` and `pyasm.py` → `toolchain/asm2/`.
5. `assembler2/editor/` and the `editor*.sh` scripts → `toolchain/editor/`. Fix the `.include ../asm2/…` paths.
6. `assembler2/prog8/` → `toolchain/prog8/`.
7. Root `*.inc` → `firmware/lib/*`, and board configs → `firmware/boards/*` (dropping the suffixes).
   - This is the one step where the `.inc` files need a rename *with* different basenames, e.g. `base_config_v1.inc` → `boards/wendy/base_config.inc`.
   - Do it as pure renames first, then update the `.include` lines in a separate commit. The firmware manifest proves the outputs are identical.
8. Root `*.s` → `firmware/programs/{common,wendy,michael,wendy2}/`. Classify each file by the `base_config_*` it includes; the Phase 0 script can print this.
9. Host tools → `tools/`. `michael/` → `hardware/michael/arduino/`. `font8x8/` → `firmware/fonts/`.
10. `bbc-basic-four-analysis/` → `research/bbc-basic-iv/`. The stale demos and plan docs → `attic/`.
11. Move the per-area `.claude/CLAUDE.md` and `.vscode` settings to the root and update them.

### Phase 4: Make the history navigable

Add annotated **milestone tags**. Each tag message says how the thing was built *at that point*: the script name, the external tools needed, and the board.

| Tag | Commit | Date | Milestone |
|---|---|---|---|
| `wendy/first-light` | `d297d44` | 2020-07-20 | first Wendy (v1) programs, Ben Eater-style |
| `michael/ram-upload` | `eb3853c` | 2021-04-09 | Michael (v2) board: RAM upload working, v1/v2 config split |
| `wendy2/upload` | `6be57cd` | 2022-04-10 | first Wendy2 (65C02 + PLD) |
| `wendy2b/intro` | `14951d4` | 2022-04-23 | Wendy 2 rev b: 2 × 32K banks |
| `wendy2c/intro` | `ae2865b` | 2022-04-30 | Wendy 2 rev c: 512K memory map, first `22V10-wendy2c.pld` |
| `wendy2c/full` | `ca09ca6` | 2022-07-22 | full wendy2c code set, 2b removed |
| `asm1/start` | `60be16b` | 2022-11-19 | asm1 bootstrap begins |
| `fork/michael-keyboard` | `536f200` | 2023-04-22 | michael_keyboard_wip forks |
| `michael/bbc-basic` | `ecfa0b0` | 2024-02-11 | BBC BASIC on Michael via the MOS shim |
| `asm1/self-hosts` | `07b2118` | 2025-11-15 | asm1 assembles itself byte-identically |
| `asm2/start` | `005e339` | 2026-01-06 | assembler2 enters version control |
| `editor/start` | `cc718c8` | 2026-02-07 | first editor/console program |
| `asm2/stages-00-17` | `79b02ab` | 2026-02-13 | chain renumbered 00–17 |
| `emulator/split` | `3b59d2d` | 2026-02-21 | emulator gets its own directory |
| `prog8/self-hosts` | `fb90b8e` | 2026-06-07 | p1 self-hosts on banked wendy2c |
| `wendy2c/pld-cfg18-rom` | `17e4a78` | 2026-09-23 | current PLD memory-map decision |
| `reorg/before`, `reorg/after` | — | — | bracket Phase 3 |

Also write `docs/history.md`, a timeline narrative per area covering the three boards, peripherals, asm1 → asm2 → editor → prog8, and the emulator. It should link these tags and explain how to check out and build an era (`git worktree add ../era-2021 michael/ram-upload`, then the scripts of that time and `vasm6502_oldstyle` in `./`).

### Phase 5 (optional, later): split repos

If an area gets outside users, for example the emulator or the editor, extract it with `git filter-repo --subdirectory-filter emulator`, which keeps that area's full history across the moves when `--path-rename` is also used for the old paths. Before that, the wendy2c PLD becomes an input that is copied or pinned, not read through `../`.

## 4. Decisions

Decided 2026-09-24:

- PLD cfg `$18` is **upper ROM**.
- The board is named **Wendy 2** (`wendy2`), and rev c is kept where it's revision-specific (see §2.2).
- Stale material goes to **`attic/`** for later review, not deletion.

Still open:

1. Is `claude/pld-hardware-memory-map-3hslxb` ready to become `main`? The trial branch is built on it, so going live makes it part of `main`.
2. Install-hexdump socket API: port it or archive it? What it is: 7 TCP calls (create/bind/listen/accept/recv/send/close) that hand 6502 programs real host sockets, one byte per call. Its only user is a demo HTTP server, `webserver.asm`. Porting means ~200 lines of C as a new emulator module, stubs moved to the free addresses after `opendir` ($F03F+), and I/O ports moved out of the argv area ($FE00–$FFDF). It works on `nmos-default` only; real hardware has no equivalent.
3. `asm-unified-parsing` refactor: archive only (recommended; its target, stage 23, is gone) or re-do it on stage 17?
4. Rename the repository?

## 5. Progress log

### Phase 0: done 2026-09-24

- **Trial branch.** The plan commits were rebased onto `claude/pld-hardware-memory-map-3hslxb` (`dd0cf45`). No tags have been pushed yet: the `archive/*` tags wait for go-live, as agreed. Before go-live, the owner makes their own backup with `git clone --mirror`.
- **`tools/firmware_manifest.py`** and its tests (`tools/tests/`), written test-first.
  - `firmware-manifest.txt` covers **122 sources**, of which **87 build** and **35 were already broken** before any reorganization. The broken ones have `FAIL` entries:
    - old programs whose `6522.inc`/`base_config` includes clash since later `.inc` changes;
    - the 4 wendy2-era files that need the deleted `base_config_wendy2.inc`;
    - the `test/` vasm experiments;
    - the "illegal relocation" errors, which may just be stricter checking in current vasm (2.0f).
  - `michael_graphics_keyboard.s` and `michael_keyboard_show_names.s` build only with `-esc`.
  - The manifest records the vasm version, and `check` fails if the vasm on PATH differs.
- **`tools/check_all.sh [firmware|asm1|asm2|emulator]`** runs every suite:
  - `firmware`: the tool tests plus the manifest check.
  - `asm1`: `assembler/asmtestgen.sh`. This script always exits 0, and without `hexdump` it "passes" by diffing two empty dumps. The wrapper therefore requires `hexdump` and checks for the printed `OK` / `Assembled` lines.
  - `asm2`: `assembler2/verify.sh`, which covers the stage 00→17 chain, stage 17 self-assembly, 501 in-assembler tests, 1,548 editor tests and 10 terminal tests.
  - `emulator`: `make -C assembler2 test`, which covers 32 C suites, the wendy2c goldens, and the prog8, tinyp8 and p1 tests.
  - Not run (slow, opt-in): Harte, the Dormann binaries (they need cc65), `P1_WENDY_SELFHOST`, `MERGE_SORT_FULL_N`.
- **`.github/workflows/ci.yml`** runs the 4 suites as a matrix. It builds vasm from source and installs 64tass, prog8c 12.1.1 and Playwright.
- **Baseline: all 4 suites green** on the trial branch. The two Playwright web tests also pass locally.
- **Environment notes** for later sessions in this container type:
  - `git fetch --unshallow`.
  - `apt-get install 64tass`.
  - prog8c jar at `/tmp/prog8c.jar`.
  - vasm from `phoenix.owl.de/tags/vasm1_9f.tar.gz` (see Phase 1 notes).
  - `pip install playwright==1.56.0` to match the pre-installed `/opt/pw-browsers` Chromium.
  - The apt mirrors were unreachable for `bsdextrautils` (`hexdump`), so a local `od`-based `hexdump -C` stand-in was used. It isn't committed.

### Phase 1: done on the trial branch 2026-09-24 (go-live steps pending)

- **1a.** The trial branch is based on `claude/pld-hardware-memory-map-3hslxb`. Fast-forwarding `main` happens at go-live.
- **1c.** Merged `claude/bbc-basic-four-analysis-JBZDp` (`47ae72a`). There was no content change; the merge adds its 3 commits to the history.
- **1b.** Merged `michael_keyboard_wip` (`922d661`), bringing in all 235 commits. The merge commit message records each conflict resolution. In short:
  - `wendy2c` names are kept.
  - The PLD keeps cfg `$18` as upper ROM.
  - `musical_notes.inc` is ours.
  - `upload_and_run.inc` is ours plus the overridable `INTERRUPT_ROUTINE`.
  - The multitasking test is mkwip's version.
  - mkwip's deletions are accepted: the per-baud scripts and 5 wendy2-era programs.
  - Every changed firmware hash is explained. All suites are green.
- **vasm pinned to 1.9f** (owner decision). vasm 2.0+ rejects `lda #(>X)`, which the Michael graphics macros use. vasm 2.0d+ no longer NUL-terminates `.ascii`, so `4bit_hello.s` assembled "fine" but was broken.
  - With 1.9f, 8 Michael graphics programs build (RAM-upload mode) and `4bit_hello.s` regains its terminator.
  - Every other binary is byte-identical under 1.9f and 2.0f.
  - All suites are green with 1.9f.
  - Porting to current vasm is future work, outside the reorganization.
- **1d (go-live only).** Delete the merged branches, and tag-then-delete `asm-unified-parsing` / `claude/install-hexdump-5CahY`. The socket-port issue stays open.

### Phase 2: done on the trial branch 2026-09-24

- **`.gitignore`**: no change was needed. A full test run leaves the tree clean.
- **`assembler2/legacy/`**: the 45 files that were byte-identical copies of `assembler/` were removed. The 18 files unique to assembler2's early history stay.
- **`attic/`**: 48 files were moved there as pure renames, keeping their original paths. `attic/README.md` lists each item and why it's there, for the owner to decide: delete, restore or keep.
  - The firmware manifest skips `attic/` and lost only the 9 parked programs.
  - The May 2026 assembler design notes were *not* attic'd. They are real documentation and move with the assembler in Phase 3.
- **Stale paths**: the stale `23/` paths all lived in the demos that are now in the attic.
  - `assembler2/README.md` is flagged as outdated and points to `BOOTSTRAP-OVERVIEW`. It gets a full rewrite in Phase 4, once the paths are final.
  - Comments in `assembler2/emulator/` still mention `transfer_115200_wendy.py`, which is now `transfer.py --baudrate=115200`. These are fixed with Phase 3's path updates.

- **Coverage audit** (owner request: every program from every branch stays in the tree or in `attic/`).
  - Every path at the tips of `claude/pld-hardware-memory-map-3hslxb` and `michael_keyboard_wip` was checked against the tree. Each one is either present (counting `attic/`), renamed (the mkwip `wendy2_*` names are now `*_wendy2c`, and `michael_graphics_keyboard.s` is now `keyboard_driver.inc`), or an identical copy (the `legacy/` duplicates).
  - The 24 upload scripts and 5 wendy2-era programs that the mkwip merge deleted were restored to `attic/`.
  - The unique commits of the unmerged `asm-unified-parsing` and `install-hexdump` branches are in `attic/unmerged/` as patches.
  - Older files missing from the tree were removed in the branches' own history, mostly by the February 2026 stage renumbering (00–23 → 00–17). They remain in history.
  - Phase 3 moves are pure renames, so this coverage holds automatically.

### Phase 3: done on the trial branch 2026-09-24

Each step is a pure-rename commit followed by a path-fix commit. All suites pass after every pair, with an unchanged skipped-test set and unchanged test counts.

- **Step 1 (done).** `22V10-wendy2c.pld` and the pin notes moved to `hardware/wendy2/`. Regenerating the PLD header changed only its source-path comment.
- **Step 2 (done).** `assembler2/emulator/` moved to `emulator/`, and `persistent_emulator.py` into it.
  - A new repository-level `Makefile` holds the emulator build and tests, which run from the repo root. The emulator's own `emulator/...` paths are therefore unchanged.
- **Step 3 (done).** `assembler/` moved to `toolchain/asm1/`. The asm1 scripts now use vasm from PATH.
- **Step 4 (done).** `assembler2/prog8/` moved to `toolchain/prog8/`, with its own Makefile. prog8 is now a separate `check_all`/CI suite.
- **Step 5 (done).** The rest of `assembler2/` moved to `toolchain/asm2/`.
- **Deviations from §2.2, both to avoid rewriting code for no gain:**
  - The stage directories stay flat (`toolchain/asm2/00` … `17`), with no `stages/` level.
  - The editor stays at `toolchain/asm2/editor/`. Its sources include paths relative to the asm2 root (`editor/…`, `17/…`), so it is effectively an asm2 application.
- **Fix (CI caught it).** In the root Makefile, `test: $(C_TESTS)` came before `C_TESTS` was defined, so a clean checkout built no C tests. It had only passed locally because stale binaries were still on disk. The rule is now placed after the definition, and `check_all.sh` cleans before the emulator suite.
- **Step 6 (done): firmware.** Root `*.inc`/`*.s` moved to `firmware/{lib/<area>,boards/<board>,programs/<board>}`; host tools to `tools/{upload,lcd-ocr}`; the Michael ROM to `hardware/michael/`.
  - `firmware/vasm` wraps vasm with every directory in `firmware/include-dirs` on `-I`. **No `.include` line in any program changed**, apart from two `../` includes in an Arduino-era program. All 119 binaries are byte-identical, and the manifest now lives at `firmware/manifest.txt`.
  - The upload scripts, emulator goldens, demos, Playwright tests and every prog8 vasm call use the wrapper.
  - Board config files keep their names (`base_config_v1.inc` etc.), so each program's include line still says which board it targets.
- **Step 7 (done).** `michael/` moved to `hardware/michael/arduino/`, `font8x8/` to `firmware/fonts/`, and `bbc-basic-four-analysis/` to `research/bbc-basic-iv/`. The asm2 `CLAUDE.md` moved out of `.claude/`.
- **Coverage re-checked.** Every path at the pld and mkwip tips is still present, possibly renamed. The only paths not found by name are the two known renames (`michael_graphics_keyboard.s` → `keyboard_driver.inc`, and mkwip's `22V10-wendy2.pld` → `22V10-wendy2c.pld`).

### Phase 4: done on the trial branch 2026-09-24

- Root `README.md` (map, quick start) and `CLAUDE.md`.
- `docs/history.md`: timeline, how to build each era, and where files moved.
- READMEs for `firmware/`, `hardware/` (with the Wendy 2 revision history), `tools/` and `toolchain/`. `toolchain/asm2/README.md` was rewritten for the 00–17 chain.
- `tools/tests/test_doc_links.py` checks that the relative links in these guides resolve.
- **Milestone tags are not created yet.** They are listed in `tools/reorg/milestones.txt`, and `go_live.sh` creates them.

## 6. Go-live checklist (not yet run)

> **Outcome.** The in-place go-live below could not run from the reorganization session, because its git proxy only allowed pushes to that session's own branch. Instead, on 2026-09-24:
> - the owner created an empty repository, `pjdennis/6502-workbench`;
> - `main` there was set to the reorganized tip (`1c8d506`, full history);
> - the three unmerged branches were pushed as `archive/asm-unified-parsing`, `archive/claude/install-hexdump-5CahY` and `archive/claude/prog8-assembler-gap-analysis-pJ7nG`. All 2,603 commits of every old branch are in the new repository.
>
> Tags could not be pushed from that session either. `tools/reorg/create_tags.sh` creates the 16 milestone tags, an `archive/<branch>` tag for each of the 18 old branch tips (`tools/reorg/archive-tips.txt`) and `reorg/before`/`reorg/after`. It replaces `go_live.sh`, which is in history.
>
> `pjdennis/6502-experiments` is left unchanged; archiving it on GitHub is the owner's call.

Only these steps change shared state. They need the owner's go-ahead.

1. **Review.** Look through the trial branch, e.g. `git log --stat origin/main..origin/claude/repo-org-restructure-plan-e0got9`, or ask for a draft PR into `main`. Check CI is green on its tip.
2. **Backup.** Run `git clone --mirror https://github.com/pjdennis/6502-experiments.git` on your own machine.
3. **Dry run.** `tools/reorg/go_live.sh` checks that `main` fast-forwards to the trial branch and prints every command. It is tested in `tools/tests/test_go_live.py`.
4. **Apply.** `tools/reorg/go_live.sh --apply`:
   - creates 18 `archive/<branch>` tags, 16 milestone tags, `reorg/before` (`dd0cf45`) and `reorg/after`;
   - pushes the tags;
   - fast-forwards `main`, never forcing;
   - deletes the 17 other branches. The trial branch is kept.

   Every deleted branch stays reachable through its `archive/` tag, and all but three are also contained in `main`.
5. **Afterwards.**
   - Confirm CI on `main`.
   - Review `attic/README.md` and decide what to delete or restore.
   - The trial branch can be deleted once you're happy.

