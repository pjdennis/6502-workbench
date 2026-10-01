# Plan: extend `assembler2/emulator/` into a wendy2c board-level simulator

> **Status (2026-09-30): implemented, apart from the items below.** This is the
> original plan, kept for its narrative; paths and commands in it are from the
> `assembler2/` era (`assembler2/emulator/` is now `emulator/`, and
> `asmtestgen.sh` and `run_tests.py` are now in `asm/`; `./commit` no longer
> exists). For the current state
> read `README.md`, `chips/README.md` and `tests/README.md`.
>
> - Done: phases 0-11 (decomposition, bus, 65C02 core with Dormann and Harte
>   harnesses, `--machine wendy2c`, PLD, ROM, RAM, CPU on the bus, VIA, LCD, LED
>   and button), 13 (serial chip, demo script) and 17's README (the usage text
>   is printed when `emulator.out` runs with no arguments; there is no `--help`
>   flag).
>
> - Done differently: the LED/button panel (phase 11) is a status line above the
>   LCD in `--live`, with SPACE as the button instead of F1. Audio (phase 12) uses vendored miniaudio with `--wav` and
>   `--audio`, not `--audio-out` / SDL2 (`audio.c`). The serial upload socket
>   (13b/13c) became `--serial-link` with `wendy2c_emu_link.py` and
>   `wendy2c_emu_upload.py` (`wendy2_upload.py` still writes framed files for
>   `--serial-input`). The button is PA1, the control LED PA2 (see
>   `chips/led_buttons.h`). Beyond the plan: `--machine michael`, `--web`,
>   `--live`, `--lcd-trace`, `--disk`. The LCD size question (open question 4)
>   became `--lcd-panel 16x2|16x1-5x10`, not `--lcd-rows`/`--lcd-cols`.
> - Not done as written: phase 16's scripted run (its `--audio-out`,
>   `--serial-socket` and F1 never existed); the goldens and end-to-end targets
>   in `tests/README.md` cover that ground instead.
> - Never built: phase 14 (ST7920 stub), 15a (`E6502_TRACE=bus`), 15b
>   (snapshots), 15c (`--selftest` / `make selftest`; `make test` and
>   `make harte` cover it).

## Branch & ground rules

- Cut a new branch from `text-editor`: `git checkout -b wendy2-emulator`.
- Default mode (no flags, or only the existing flags) must keep the same `read6502`/`write6502` direct-`memory[]` path and the NMOS Fake6502 dispatch, so the asm bootstrap and the editor's 305-test suite are byte-identical and not measurably slower.
- All commits via `./commit -m"..."` from `assembler2/`.
- Every phase ends with three "regression gates":
  - `make` builds cleanly with `-Wall -Werror` for new files.
  - `./asmtestgen.sh` completes and `17/out/asm.out == 17/out/asm_2.out`.
  - `python3 run_tests.py -q` and `python3 editor/tests/editor_tests.py -q` pass.
- TDD: every C source file added gets a matching `emulator/tests/test_*.c` linked into the existing greatest-based suite, and `make test` is the first thing run on every commit. New `make selftest` and `make harte` targets get added later but never replace the existing `make test`.
- Refactor-first / refactor-after rhythm: a "refactor only" commit precedes every behavior-change commit when an extraction is needed; a follow-up "cleanup" commit removes dead code after a feature lands.

## Investigate-first items (settle before designing chips)

These get a 1-commit "investigation note" file (`assembler2/emulator/INVESTIGATION-wendy2c.md`) at the start of phase 1, and the answers feed every following phase.

1. **Serial wiring.** From the source we have so far, wendy2c serial RX is on the VIA: `PCR = PCR_CB2_IND_NEG_E`, `ACR = ACR_SR_IN_T2`, `SR` is read after a CB2 start-bit interrupt fires, and T2 is reloaded for half-bit timing. So the SERIAL_USB module talks to the VIA's CB2 (start-bit edge) + SR (shifted-in byte), not to a separate UART. The investigation note records this and pins down: TX side appears unused by `upload_and_run_ram_wendy2c.s` (it only receives); confirm by grepping every `BPS_*` and `SR` write in `upload_and_run.inc` etc. before writing the SERIAL module.
2. **RAM size.** *(Resolved: 512 KiB chip, see INVESTIGATION-wendy2c.md §2.)* The PLD's `R15..R18` drive RAM `A18..A15`, CPU `A15` drives RAM `A14`, and CPU `A14` goes only to the PLD. `C0..C4` bank two windows, `$0000-$3FFF` and `$8000-$EFFF`; the per-config map is in `README.md`.
3. **LED + button bit positions.** The `multitasking_test_wendy2c.s` uses `LED_PORT = PORTB`, `LED_MASK = %01000000` (PB6) and `T1_SQWAVE_OUT = %10000000` (PB7). No button bit is actually wired in `multitasking_test_wendy2c.s`; the comments mention PORTA bit 5 = `CONTROL_BUTTON`. Confirm whether `wendy2c_led_test.s` or any other on-target program reads it — if not, defer button input plumbing past LED rendering and revisit.
4. **20x4 vs 16x2 LCD.** `base_config_wendy2c.inc` defines 16x2 active and 20x4 commented out. Default LCD module to 16x2; expose `--lcd-rows N --lcd-cols N` to override.
5. **CKS/CK ordering.** The PLD has `CKS.R = /CKS` and `CK.R = CK*/CKS + /CK*CKS + /ROMCS*/CK`. CKS is OSC/2 unconditional. CK transitions on CKS edges; with /ROMCS true, the third term keeps CK low for one extra OSC cycle so a ROM access takes 2 CPU cycles' worth of OSC ticks. Document the chosen scheduling: each OSC tick: (1) latch combinational inputs visible to PLD from the previous tick, (2) update CKS registered output, (3) update CK registered output, (4) on the falling edge of CK, advance one CPU bus phase. This avoids any combinational loop.

---

## Phase plan

### Phase 0 — branch + investigation note

- **Goal**: branch from `text-editor`; write `assembler2/emulator/INVESTIGATION-wendy2c.md` answering the five questions above.
- **Files touched**: new `assembler2/emulator/INVESTIGATION-wendy2c.md` only.
- **Test added**: none yet (doc only).
- **Definition of done**: regression gates pass; doc committed.
- **Commit**: `./commit -m"wendy2: branch + investigation notes for serial/RAM/LCD/PLD ordering"`

### Phase 1 — emulator decomposition refactor (no behavior change)

The current `emulator.c` mixes CLI parsing, file I/O, stub serial, console handling, trace, and the main loop. Before adding new modes, factor out three things so the next phases have stable seams to plug into. **No flag changes, no semantic changes.**

1a. **Refactor: extract trace.** Move the `trace_*` and `E6502_TRACE` parsing into `emulator/trace.c/.h`. Tests: add `tests/test_trace.c` that exercises the ring buffer wrap and the histogram top-N. Commit: `emulator: extract trace.c/.h (no behavior change)`.

1b. **Refactor: extract CLI option parsing.** New `emulator/cli.c/.h` with `struct emu_opts` and `int parse_args(int argc, char **argv, struct emu_opts *o)`. `emulator.c` consumes the struct. Tests: `tests/test_cli.c` with table-driven argv vectors (including unknown flag, missing value, `--mhz 1.5 --baud 115200`). Commit: `emulator: extract cli.c/.h (no behavior change)`.

1c. **Refactor: extract main run-loop into `emu_run.c`.** The default-mode loop (the `while (!done) { step6502(); ... throttle ... }` block in both `main` and `server_main`) becomes `int emu_run_default(struct emu_opts *o)`. Server mode keeps wrapping it inside the protocol loop. Commit: `emulator: extract emu_run_default (no behavior change)`.

- **Definition of done after each sub-phase**: full regression gates green.
- **Why this matters**: phase 4 needs `emu_run_wendy2c(...)` as a sibling of `emu_run_default(...)`, and we cannot afford to copy-paste the throttle/sigint/trace code.

### Phase 2 — bus / chip-module vtable scaffolding (still not wired in)

Add the chip-module interface but don't dispatch through it yet.

- **New files**:
  - `emulator/bus.h` — defines `struct chip` with vtable `tick(self, bus*)`, `read(self, bus*, addr, *data) → bool claimed`, `write(self, bus*, addr, data) → bool claimed`, `reset(self)`, plus `struct bus` (address, data latch, RWB, /ROMCS, /RAMCS, /VIACS, /WR, IRQ, NMI, RES lines, OSC tick counter, list of chips).
  - `emulator/bus.c` — registration, reset broadcast, transaction helpers, but `bus_step` is a stub that just increments tick count.
- **Tests** (`tests/test_bus.c`): register two dummy chips with overlapping read claims, verify "first claim wins" deterministic behavior; verify `bus_reset` walks all chips; verify line-toggle sequencing within a single `bus_step` (input lines latched then registered outputs updated).
- **Wiring**: none — `bus.c` is compiled but not referenced from `emulator.c`. Add the new sources to the Makefile so unused-warning checks pass.
- **Commit**: `wendy2: add bus/chip vtable scaffolding (not wired)`
- **Definition of done**: regression gates pass; `make test` runs the new test_bus.

### Phase 3 — 65C02 CPU core (standalone, before any wendy2 wiring)

The CPU is the single biggest risk; bring it up against gold-standard test suites before any board pieces depend on it.

3a. **Refactor cpu_core for variant selection (no behavior change).** Add `extern int cpu_variant; #define CPU_NMOS 0`, `#define CPU_65C02 1`. Default initializer = `CPU_NMOS`. Wrap the existing NMOS `addrtable`/`optable`/`ticktable` as `addrtable_nmos` etc. Add empty `addrtable_65c02`/`optable_65c02`/`ticktable_65c02` initialized to NMOS values (identical). `step6502` picks tables at top. Commit: `cpu_core: add cpu_variant dispatch (NMOS unchanged)`.

3b. **Add 65C02 fixes (no new opcodes yet).** In the 65C02 tables only:
- Fix `JMP ($abcd)` page-bug (`ind_65c02` reads `+1` without page wrap).
- Decimal-mode N/Z calculation after ADC/SBC.
- BRK clears D after pushing status.
- Documented NOP slots become 1 cycle / 1 byte where applicable; the 6 multi-byte NMOS NOPs (1C/3C/5C/7C/DC/FC) become absolute-NOPs.
Tests (`tests/test_cpu_65c02_fixes.c`): JMP indirect across $10FF / $11FF boundary; DECIMAL ADC of $99 + $01; BRK side-effects on D.
Commit: `cpu_core: 65c02 baseline fixes (jmp-ind, decimal N/Z, brk-D)`.

3c. **Add new 65C02 opcodes group A.** `bra`, `phx`, `phy`, `plx`, `ply`, `stz` (4 modes), `inc`/`dec` A. Tests: unit-test each instruction's regs/flags. Commit: `cpu_core: 65c02 bra/phx/phy/plx/ply/stz/inc-a/dec-a`.

3d. **Add new 65C02 opcodes group B.** `trb` (zp/abs), `tsb` (zp/abs), `(zp)` indirect mode for LDA/STA/ORA/AND/EOR/ADC/SBC/CMP, `JMP ($abcd,X)`. Tests: `trb`/`tsb` flag semantics (Z = A & M before write), `(zp)` zero-page wrap-around, jmp-indirect-X. Commit: `cpu_core: 65c02 trb/tsb/(zp)/jmp-(abs,X)`.

3e. **Add `bbr0..7`/`bbs0..7`/`rmb0..7`/`smb0..7` (WDC bit ops).** Tests: each opcode form. Commit: `cpu_core: 65c02 bbr/bbs/rmb/smb bit ops`.

3f. **Add `wai`, `stp`.** Implement `wai` by setting a `wai_pending` flag that makes `step6502` consume 1 cycle and not advance PC until an IRQ/NMI clears it. `stp` sets `stp_pending` that halts `step6502` until `reset6502`. Tests: assert WAI returns and PC advances when `irq6502()` is called; STP held until `reset6502`. Commit: `cpu_core: 65c02 wai/stp`.

3g. **Klaus Dormann functional test harness.**
- New folder `emulator/tests/dormann/` containing vendored upstream sources `6502_functional_test.a65` and `65C02_extended_opcodes_test.a65c` (from the amb5l/Klaus Dormann fork that targets `ca65`). These are GPLv3+ only — add `tests/dormann/LICENSE` (GPLv3 text) and a `tests/dormann/README` recording upstream URL + commit hash and the licensing note. The repo's own license posture is unaffected since the tests link no project code.
- Build dependency: **`cc65` toolchain (`ca65`/`ld65`)** must be installed. Add a one-line note to `assembler2/README.md` and a friendly error in the Dormann Makefile if `ca65` is missing.
- New `tests/dormann/Makefile`: runs `ca65` + `ld65` against the vendored sources to produce `6502_functional_test.bin` and `65C02_extended_opcodes_test.bin`. The `.bin` artifacts go to `tests/dormann/out/` and are gitignored.
- New `emulator/tests/test_dormann.c`: greatest test that loads each binary at $0000, sets PC=$0400, runs until PC equals the documented success trap address or hits a stuck-trap (PC unchanged for >2 instructions in a row, which Klaus's test uses as failure indicator). Reports last PC on failure. If the `.bin` is missing (ca65 unavailable), the test is reported as SKIP (greatest `SKIP()`) with a clear message, and `make test` stays green.
- Wire into `make test`. Commit: `tests: klaus-dormann harness for NMOS and 65C02 cores`.
- **Definition of done**: both Dormann binaries return success for their respective `cpu_variant` when `ca65` is available. If a fix is needed, that fix is its own follow-up commit referencing the Dormann failure PC.

3h. **Tom Harte ProcessorTests harness.**
- New folder `emulator/tests/harte/` with a small README pointing to the upstream git submodule or a "download script" (do NOT vendor the 5+ GB of JSON; instead `tests/harte/fetch.sh` clones the upstream into a gitignored `harte/data/` dir, and `make harte` first runs `fetch.sh` if data missing).
- New `emulator/tests/harte_runner.c` (linked into a `harte_runner.out`): for a given CPU variant and an opcode in `00..FF`, iterate through the JSON test cases (use a small hand-rolled JSON parser — only objects/arrays/strings/numbers needed), set up CPU regs + RAM as `initial` says, install a bus-log shim that records each `(addr, val, R/W)`, single-step one instruction, compare `final` regs + RAM + cycle log.
- `make harte` target runs all 256 opcodes for both `6502` and `wdc65c02` JSON dirs. For now allow `HARTE_LIMIT=N` env var to test only the first N vectors per opcode for fast loops.
- **If `harte/data/` is missing**, `make harte` prints `WARNING: Harte data not fetched; run tests/harte/fetch.sh first. Skipping.` and exits 0. Same skip-with-warning behavior in `--selftest` (phase 15c). The build never fails because Harte data is absent — explicit fetch is opt-in.
- Commit: `tests: tom-harte processortests harness (cycle-exact)`.
- **Definition of done**: NMOS dispatch passes Harte for the documented-opcodes set (undoc opcodes may be allow-listed against the NMOS undocumented `lax`/`sax`/etc. behavior we already implement); 65C02 passes Harte for all 256 opcodes. Document any allow-listed mismatches in `emulator/tests/harte/known-deltas.md`.

3i. **CPU bus-callback hooks.** Add `extern void (*cpu_bus_read_tap)(uint16_t, uint8_t)` and `extern void (*cpu_bus_write_tap)(uint16_t, uint8_t)` in `cpu_core.h`, called from inside `read6502`/`write6502`. Default = NULL. This is how phase 5's bus-mode CPU wrapper sees each transaction (and how the Harte runner already records cycle-by-cycle logs). Commit: `cpu_core: add bus tap callbacks (default null)`.

After phase 3 the new CPU core is fully tested before any wendy2 hardware exists.

### Phase 4 — `--machine wendy2c` switch and OSC

Open the door to the bus path without wiring any chips yet — just the new top-level run loop.

4a. **Add `--machine` and `--cpu` flags.**
- `parse_args` accepts `--machine nmos-default|wendy2c` (default = `nmos-default`) and `--cpu nmos|65c02` (default = `nmos`).
- When `--machine wendy2c` is set without `--cpu`, default `--cpu` to `65c02`.
- Validate that `--machine wendy2c` + `--cpu nmos` is rejected with an error (Wendy is a W65C02S board).
- Tests: `test_cli.c` additions cover all three combinations.
- Commit: `wendy2: --machine and --cpu flags (parsing only, no behavior)`.

4b. **Add `emu_run_wendy2c()` shell.**
- New file `emulator/emu_wendy2c.c/.h`.
- Function `int emu_run_wendy2c(struct emu_opts *o)` constructs an empty `struct bus`, attaches no chips, runs an OSC loop that just steps `bus.tick_count` and exits if `done` after a small cap (so the smoke test below terminates).
- `main()` dispatches: if `o->machine == MACHINE_WENDY2C`, call `emu_run_wendy2c(o)`; else call `emu_run_default(o)`.
- Tests: `tests/test_machine_dispatch.c` builds a 1-byte input file and ensures `--machine wendy2c` returns 0 and the default path is unchanged byte-for-byte.
- Commit: `wendy2: emu_run_wendy2c shell wired to --machine flag`.

4c. **OSC module.**
- New `emulator/chips/osc.c/.h`. `osc_tick(self, bus*)` just increments `bus->osc_ticks`. Constructor takes target frequency. Used later by audio-sink for sample-rate decimation.
- Tests: `tests/test_chip_osc.c` registers OSC into a bus, runs 1000 ticks, asserts counter.
- Commit: `wendy2: OSC chip`.

After phase 4, you can run `emulator.out --machine wendy2c some.bin` and it just spins; importantly the default path is byte-identical, which the regression gates confirm.

### Phase 5 — 22V10 clock + chip-select decoder

5a. **`chips/clock_22v10.c/.h`** implements the PLD equations literally.
- Inputs latched from the bus: `OSC` edge, `A11..A15`, `RWRB`, `C0..C4` (from a callback into VIA — VIA doesn't exist yet, so for now the clock module exposes `set_bank_config(uint8_t)` and the bus stores `C0..C4`).
- Registered outputs: `CKS`, `CK`.
- Combinational outputs: `/WR`, `/ROMCS`, `/RAMCS`, `/VIACS`, `R15..R18`.
- The `tick(bus*)` method runs in two phases (as the investigation note specifies): combinational first, registered second.
5b. **Cycle-step semantics.** On falling CK edge, the clock module sets `bus->cpu_cycle_due = 1`. The CPU module (next phase) consumes this; the rest of the bus just runs combinational reads/writes when the CPU module asks.
5c. **Tests** (`tests/test_chip_clock.c`):
- Free-running OSC produces CKS at OSC/2 (verify duty cycle).
- With `/ROMCS` low, CK runs at CKS/2.
- With `/ROMCS` high, CK == CKS.
- `R15..R18` decode matches a hand-computed truth-table of 8 representative (A11..A15, C0..C4) combinations from the PLD file.
- `/RAMCS`, `/ROMCS`, `/VIACS` are mutually exclusive on every test point.
- **Commit**: `wendy2: clock_22v10 PLD model + chip select decode`.

### Phase 6 — ROM (28C256, 32 KiB)

- `chips/rom_28c256.c/.h`. Constructor takes a filename to mmap (or read into a `uint8_t[0x8000]`). `read` claims when `/ROMCS && bus->RWB`. Writes ignored (28C256 EEPROM write protocol not modelled — out of scope; the assembler bootstrap and Wendy code only program via a flasher in real life).
- Tests: `tests/test_chip_rom.c` builds a tiny 32 KiB pattern, places it on the bus, verifies bytes at `$8000..$FFFF` come back through `bus_read` with `/ROMCS` asserted, and don't with `/ROMCS` deasserted.
- New `--rom path/to/rom.bin` CLI option (only honored under `--machine wendy2c`).
- **Commit**: `wendy2: rom_28c256 module + --rom flag`.

### Phase 7 — RAM (512 KiB, banked; module keeps the `628128` name)

- `chips/ram_628128.c/.h`. Internal `uint8_t[0x80000]` (512 KiB). Read/write claim when `/RAMCS` asserted; physical address formed as `(R18 R17 R16 R15) << 15 | CPU A15 << 14 | A13..A0`.
- Tests: write to `$0000` with `C0..C4 = 1`, read back with `C0..C4 = 2`; verify the two lower banks are physically distinct (configs `$00` and `$01` both select lower bank 1, so they share `$0000`). Also verify writes around `$f800` follow the PLD `C4=1` overlay rule (RAM at `$f800` even though normally selected ROM).
- **Commit**: `wendy2: ram_628128 module with bank-mapped addresses`.

### Phase 8 — CPU on the bus

This is where the real CPU starts being driven by CK edges instead of free-running.

- `chips/cpu_65c02.c/.h`: wraps `step6502` so that each `tick(bus*)` call, when the clock module signals `cpu_cycle_due`, advances the CPU by exactly one bus cycle.
- Implementation note: Fake6502 doesn't natively expose cycle-by-cycle bus transactions; it runs whole instructions. There are two acceptable strategies — pick one in the investigation note before this phase:
  1. **Per-instruction execute, then "credit" the bus.** When CK fires and `instruction_cycles_remaining == 0`, call `step6502`; record `instruction_cycles_remaining = clockticks6502 - last`; tick the bus down to zero. This is *cycle-accurate timing-wise* but bus-transactions happen in a burst at the start of each instruction.
  2. **True per-cycle bus.** Replace `step6502` with a state-machine that consumes one bus cycle per call. Bigger rewrite. The Harte cycle-by-cycle harness from phase 3h tells us whether strategy 1 is enough for everything wendy2c needs (the wendy2c programs do not rely on intra-instruction bus order — they only care that an SR write completes before T2 fires).
- **Recommendation**: strategy 1, plus the `cpu_bus_read_tap`/`cpu_bus_write_tap` hooks already in place so the bus-trace mode (phase 14) shows the per-bus-transaction sequence in instruction order.
- Wire `IRQ`/`NMI`/`RES` bus lines to `irq6502`/`nmi6502`/`reset6502`.
- Tests: a synthetic ROM (assembled as part of the test harness via a tiny assembled string baked into the test binary or precompiled) that does `lda #$42; sta $0200; brk`; verify the bus saw R(addr=PC+0)=A9, R(PC+1)=42, W($0200)=42, plus IRQ vector pull at $FFFE.
- **Commit**: `wendy2: cpu_65c02 chip wrapping fake6502 step on bus`.

After phase 8, the smoke test is: run a stripped-down ROM containing `wendy2c_eeprom_show.s` (which uses `stp`) on `--machine wendy2c`, watch it hit `stp` and the emulator exit cleanly.

### Phase 9 — VIA 6522 (core registers + T1/T2 + PB7 + IRQ)

This is the biggest chip. Split into two commits.

9a. **VIA register model.**
- `chips/via_6522.c/.h`. All 16 registers; correct read-vs-write side effects (T1CL read clears T1 IFR, T1CH write resets T1, T1LH write doesn't reset, T2CL read clears T2 IFR, T2CH write starts T2 and clears IFR, SR read/write clears SR IFR, IFR/IER bit-7 semantics).
- ORA/IRA/ORB/IRB/DDRA/DDRB with input-vs-output direction; reading PORTA returns external-pin value where DDR=0, ORA where DDR=1.
- `tick(bus*)`: decrement T1 and T2 per phi2 cycle; on T1 underflow, if ACR T1=continuous, reload from latches; if T1 output enabled, toggle PB7; raise IFR-T1 / IFR-T2 as appropriate.
- IRQ output to bus = `(IFR & IER & 0x7F) != 0`.
- Tests (`tests/test_chip_via.c`): T1 timed mode IRQ count, T1 continuous PB7 toggle frequency, T2 one-shot IRQ, IFR clear semantics, PORTA in/out direction.
- **Commit**: `wendy2: via_6522 core (regs + T1/T2 + PB7 + IRQ)`.

9b. **VIA CA/CB lines + SR.**
- CA1/CA2/CB1/CB2 edge detection per PCR; CB2-as-input independent-interrupt edge fires ICB2.
- SR modes: at minimum `ACR_SR_IN_T2` and `ACR_SR_OUT_T2` (the modes `upload_and_run.inc` uses). When in shift-in-T2 mode, on each T2 underflow shift one bit from a "CB2 line" into SR, count 8 bits, fire ISR.
- The "CB2 line" is exposed as `via_set_cb2(uint8_t bit)` and `via_get_cb2()` so the SERIAL_USB module in phase 13 can drive it.
- Tests: drive a known bit pattern into CB2 + T2 ticks, read SR, verify the value (matches the bit-reversal that `upload_and_run.inc`'s `TRANSLATE` table compensates for).
- Wire VIA's `C0..C4` (PORTB low 5 bits when programmed as outputs) into `clock_22v10.set_bank_config()` — this closes the loop on bank switching.
- **Commit**: `wendy2: via_6522 ca/cb/sr + bank-config wired to clock`.

### Phase 10 — LCD HD44780

- `chips/lcd_hd44780.c/.h`. Inputs come from VIA PORTA (`DISPLAY_DATA_MASK = %11110000` upper nibble for 4-bit), `RW = %00001000`, `RS = %00000001`, plus `E` from PORTB `%00100000` (per `base_config_wendy2c.inc`). The chip subscribes to VIA-PORT-write notifications: extend the VIA's `tick` to call `bus_notify_port_write(port_index, value)` whenever ORA/ORB changes a visible output bit. The LCD's read of busy-flag is satisfied by VIA's PORTA input-bit-7 path (the existing assembly polls BF via reads of `PORTA` while RW=1 and RS=0 and E pulsed high).
- State: DDRAM 80 bytes, CGRAM 64 bytes (8 chars × 8 rows × 5 cols), AC, entry-mode, display-on-cursor-blink flags, 1-line vs 2-line, 4-bit vs 8-bit mode (only 4-bit used here but model both), busy-flag with a configurable busy duration (default ~40 us emulated time so the existing on-target polling exits naturally).
- Rendering: the LCD module exposes `lcd_render(char *buf16x2)` and a "dirty since last frame" flag. The terminal mode prints two lines into a status area at the top of the screen, with CGRAM slot 6 rendered as `~` and CGRAM slot 7 as `\`, and any DDRAM byte equal to `0x7e` (yen on the ROM) printed as itself unless overridden by a `lcd_translate_glyph(code, char *out)` hook.
- Line-address mapping: 16x2 → row 0 starts at $00, row 1 at $40. 20x4 → row 0 $00, row 1 $40, row 2 $14, row 3 $54.
- Tests (`tests/test_chip_lcd.c`): function-set 4-bit, write "Hello", read back DDRAM at $00..$04; busy-flag clear after the configured time; CGRAM slot 6 writes appear when DDRAM character 6 is rendered.
- **Commit**: `wendy2: lcd_hd44780 chip + terminal status-bar render`.

### Phase 11 — LED + button mapping

- `chips/led_buttons.c/.h`. Subscribes to PORTB writes for LED bits (PB6 from `multitasking_test_wendy2c.s`); presents button-bit injection via `led_buttons_press(uint8_t bit)`/`release(bit)`, which appears on PORTA inputs.
- Terminal status-bar update: extend the LCD-frame area to a 3-line panel — line 0 = "[●] LED  [F1]=ctrl btn" with the bullet replaced by `○` or `●` depending on PB6 state; line 1-2 = LCD content.
- Wire raw-termios key reader (already used by terminal/console mode in `emulator.c`) to inject button presses: F1 → CONTROL_BUTTON pin. Use the `terminal_interactive` path's existing select() loop; in wendy2c mode the loop polls the keyboard between OSC ticks at a coarse rate (every N ticks).
- Tests (`tests/test_chip_led_buttons.c`): write PB6 high/low, observe LED state change; inject button press, observe PORTA bit reading.
- **Commit**: `wendy2: led + button chip with status-bar render and F-key injection`.

### Phase 12 — Audio (WAV + optional SDL2)

- `chips/audio_sink.c/.h`. Subscribes to PB7 writes (T1 squarewave goes through ORB bit 7 when ACR T1-output is enabled — see VIA model). At each OSC tick records the current PB7 level; on every Nth tick (where N = OSC_freq / 44100) box-downsamples the last window to one int16 sample.
- WAV writer: **lazy open** — the file at `--audio-out wendy2c.wav` is created and the WAV header reserved only on the first non-trivial PB7 activity (defined as the first PB7 level *change* observed after VIA ACR T1-output-enable is set; transient bit-wiggles before T1 is configured don't count). If the run never produces non-trivial activity, no file is written. Header back-patched at close.
- Optional SDL2 live: `--audio-live` opens SDL2 audio, queues samples in a ring buffer. Compile SDL2 support behind `#ifdef HAVE_SDL2` and a `make` variable `EMU_AUDIO_LIVE=1`; the default `make` does NOT link SDL2 (so the bootstrap chain has no new dependency).
- Cap: hard duration cap default 60 s, override with `--audio-duration N`.
- Tests (`tests/test_chip_audio.c`): drive a synthetic 1 kHz square via PB7, render 1 s of audio, FFT-free assertion that the zero-crossing rate is 2000 ± 5 Hz.
- **Commit**: `wendy2: audio_sink module (WAV always, SDL2 opt-in)`.

### Phase 13 — Serial USB / upload socket

13a. **SERIAL_USB chip** (`chips/serial_usb.c/.h`).
- Drives VIA CB2 + SR + T2 the same way the real USB serial chip does when bytes arrive. Has a software queue of bytes to deliver; for each queued byte it pulses CB2 low (start bit edge), then over T2-driven shift cycles streams the 8 bits in (bit-reversed, matching the `TRANSLATE` table inversion in `upload_and_run.inc`). On TX side (not currently exercised but model for completeness), accumulates bits shifted out by VIA's `ACR_SR_OUT_T2` mode into bytes and writes them to an output sink.
- Tests: queue a known byte sequence, drive the VIA into shift-in-T2 mode for one byte each, verify `SR` reads return the right bytes in the right order.
- **Commit**: `wendy2: serial_usb chip driving via cb2+sr`.

13b. **Unix-domain socket frontend** (`emulator/serial_socket.c/.h`).
- New `--serial-socket /tmp/wendy2.sock` CLI option (only valid with `--machine wendy2c`). Emulator creates the socket on startup; on `accept()`, reads bytes and forwards them into `serial_usb_rx_queue()`. Triggers a `RES` pulse on connect by default; `--no-reset-on-connect` disables.
- Print the socket path on stderr at startup so the uploader can find it.
- Tests: spawn the emulator as a subprocess (greatest with `popen`), connect, send a 4-byte sequence, verify the emulator stays alive.
- **Commit**: `wendy2: serial unix-socket frontend + reset-on-connect`.

13c. **Uploader script** (`emulator/wendy2_upload.py`).
- Mirrors `transfer_115200_wendy.py` framing: 2-byte LE length + payload + 2-byte BSD checksum.
- Connects to `--serial-socket` path (positional arg).
- No DTR pulse (the socket connect already triggers reset).
- Tests: in a Python test alongside `editor/tests/editor_tests.py` style, start emulator with a tiny test ROM that just echoes received bytes to LCD, upload a small payload, scrape the rendered LCD frame to verify.
- **Commit**: `wendy2: wendy2_upload.py + python integration test`.

13d. **Demo launch script** (`emulator/demo_wendy2c.sh`).
- One command that takes a fresh checkout end-to-end: builds artifacts, launches the emulated wendy2c, uploads a small demo program over the socket, and shows its output on the (emulated) LCD in the terminal. Intended for human inspection — "does the whole pipeline work?"
- Behavior:
  1. From `assembler2/`, ensure `emulator/emulator.out` is built (`make` if stale).
  2. Assemble the ROM-side listener `upload_and_run_ram_wendy2c.s` (from repo root) into `emulator/out/demo_rom.bin` using the existing bootstrap-asm pipeline (re-uses the same toolchain `asmtestgen.sh` uses, so no new dep).
  3. Assemble the RAM-side payload — default `hello_ram_4000_wendy2c.s` (already in the repo) — into `emulator/out/demo_payload.bin`. Allow override via `DEMO_PAYLOAD=path/to/other.s` env var; the script picks up the chosen `.s`, finds its load address from the file name suffix (`_4000_` or `_5000_`), and passes it through to the uploader.
  4. Pick a per-invocation socket path `${TMPDIR:-/tmp}/wendy2-demo-$$.sock` so concurrent demos don't collide. Trap EXIT to remove the socket and kill the emulator child.
  5. Background-spawn `(sleep 0.5 && python3 emulator/wendy2_upload.py "$SOCK" emulator/out/demo_payload.bin) &` so the uploader fires once the emulator is listening.
  6. `exec` the emulator in the foreground: `./emulator/emulator.out --machine wendy2c --rom emulator/out/demo_rom.bin --serial-socket "$SOCK" --audio-out emulator/out/demo.wav`. The user sees the LCD status-bar render live; on the demo payload `hello_ram_4000_wendy2c.s` the LCD prints its hello message, the emulator halts on `stp` or hangs visibly, user hits Ctrl-C to exit, EXIT trap cleans up.
- Flags:
  - `--auto-exit SECONDS` (used by the test below): after upload, send SIGTERM to the emulator after N seconds. Exit code reflects whether the expected LCD content was seen (when combined with `--expect "..."`).
  - `--expect STRING`: when used with `--auto-exit`, scrape the final-frame LCD snapshot dump (produced via SIGUSR1 + the snapshot machinery from phase 15b — or, until 15b lands, a `--lcd-dump-on-exit` flag added in this commit) and fail if STRING isn't present.
  - `--no-audio`: omit `--audio-out` so the run produces no WAV at all (lazy-open in phase 12 means a quiet run would skip it anyway, but this is the explicit toggle).
- Tests:
  - `emulator/tests/test_demo_script.sh` invokes `demo_wendy2c.sh --auto-exit 5 --expect "HELLO"` and asserts exit-0.
  - Wire that shell test into the existing `make test` target alongside the greatest C suite (as a non-greatest sibling — same exit-code contract).
- Documentation: phase 17 README gets a "Try the demo" section that just says `cd assembler2 && emulator/demo_wendy2c.sh`.
- **Commit**: `wendy2: demo_wendy2c.sh end-to-end smoke launch script`.

### Phase 14 — ST7920 graphic display stub

- `chips/gd_st7920.c/.h`. Subscribes to GD_PORT writes (PORTA bits per `base_config_wendy2c.inc`: `GD_CLK %01`, `GD_RSTB %02`, `GD_CSB %04`, `GD_DC %08`, `GD_MOSI %10`, `GD_MISO %20`). State machine: on CSB falling edge, start SPI byte capture; on each CLK rising edge, shift one MOSI bit in. After 8 bits, drop the byte on the floor (no actual frame buffer — this is just to keep the on-target code from spinning forever on BUSY). MISO returns 0 always so any read of "ready" succeeds.
- Tests: drive a few SPI bytes, verify the chip never claims a bus address (it's a port-bit subscriber, no MMIO) and that internal byte buffer holds the right sequence.
- **Commit**: `wendy2: st7920 spi stub absorbs gd traffic`.

### Phase 15 — Diagnostics extras

15a. **Bus-trace ring mode.** Extend `trace_mode` to recognize `bus` in the `E6502_TRACE` env var. When active, a ring buffer of `struct bus_evt { uint64_t cyc; uint16_t pc; uint16_t addr; uint8_t data; uint8_t rw; uint8_t cs_hit; }` is filled from the CPU bus tap. On hang/timeout / SIGINT, dumped. Tests: drive a known sequence, dump ring, verify last entry matches expected. Commit: `emulator: trace=bus mode (cycle-resolved bus log)`.

15b. **Snapshot / save-restore.**
- `--save-state F` on `SIGUSR1`: pickle CPU regs (`pc/sp/a/x/y/status`), full 64 KiB CPU memory image *and* the wendy2 extended-RAM banks, VIA full state (all regs, T1/T2 counters and latches, SR shift counter, internal IFR), LCD (CGRAM/DDRAM/cursor/AC/entry-mode/display-on), audio-sink WAV position, OSC tick count, serial RX/TX queue state.
- `--load-state F` at startup: opposite.
- Format: simple `struct snapshot_header` + tagged sections, version byte = 1.
- Tests: snapshot mid-run of `wendy2c_interrupt_demo.s` -derived ROM, restore, continue, verify final LCD frame matches the no-snapshot run.
- Commit: `wendy2: snapshot save/restore on SIGUSR1 / --load-state`.

15c. **`--selftest` mode.**
- Runs Dormann (NMOS), Dormann (65C02), Harte (NMOS), Harte (65C02), prints one line per suite (`PASS Dormann-NMOS 23456 cycles` / `FAIL Harte-65C02 op=$1A vector 17`), exits 0 if all PASS else 1.
- New `make selftest` target chains it.
- Commit: `emulator: --selftest runs dormann+harte for both cores`.

### Phase 16 — End-to-end verification (no code, just running)

This phase has no source changes — it's a verification pass that the constraints in the brief actually hold. If anything fails, fix-it commits go here.

16a. Build the wendy2c monolithic ROM (`multitasking_test_wendy2c.s` + supporting includes) using existing scripts.
16b. Launch the new emulator: `./emulator/emulator.out --machine wendy2c --rom multitasking_test.bin --audio-out demo.wav --serial-socket /tmp/wendy2.sock`.
16c. Verify in terminal: status-bar shows the LED toggling; LCD shows the 4 counters + chase + morse; pressing F1 visibly affects PORTA bit 5 (read via the bus trace).
16d. Verify `demo.wav` plays the Star-Spangled Banner squarewave when opened in any audio app (manual check, scripted as "expect a non-empty WAV with mean energy > threshold and dominant frequency within reasonable range for a melody").
16e. Build `editor.asm` separately as a wendy2c-targeted variant (if applicable) and upload it via `wendy2_upload.py` through the socket; confirm the editor's first frame renders on LCD.
- Commit (if anything was tweaked): `wendy2: end-to-end verification fixes`.

### Phase 17 — README + CLI help

- Update `assembler2/emulator/README.md` (create if missing) with the new flags, the machine model, the wendy2c terminal UI, and pointers to the Dormann/Harte test sources.
- Update `--help` text inside `cli.c` to list the new options.
- Commit: `wendy2: docs + cli help`.

---

## Regression discipline summary

Every phase's commit-completion checklist:

1. `make` clean build, no new warnings.
2. `make test` passes (greatest C tests).
3. `./asmtestgen.sh` passes (asm bootstrap byte-identical; this is the hardest one and the reason `--machine wendy2c` must be opt-in and the default `step6502` path must not gain branches).
4. `python3 run_tests.py -q` (305 tests) passes.
5. `python3 editor/tests/editor_tests.py -q` passes.
6. From phase 3g onwards: `make selftest` passes (or once it exists, `make harte` once for each variant after CPU phases).

Commits stay small and single-purpose. Each new C source goes in with a same-commit `test_*.c`.

## Acknowledged uncertainty

- **CPU-on-bus strategy 1 vs 2** in phase 8: strategy 1 (per-instruction, then "credit") is recommended but the call should be made only after phase 3h shows the Harte cycle-log assertion is *not* needed by anything wendy2c does. If the wendy2c serial RX in phase 13 turns out to depend on intra-instruction bus order (it probably doesn't — the SR fires at T2 underflow, which happens between instructions), this becomes a strategy-2 follow-up.
- **RAM chip size**: resolved as 512 KiB (INVESTIGATION-wendy2c.md §2).
- **Button bit**: still uncertain whether any program actually reads it; phase 11 lands the LED first and adds a `// TODO: confirm bit-5 vs bit-other` note that gets resolved when (or if) a program reads `CONTROL_BUTTON`.
- **Per-cycle clock pacing of CPU vs OSC**: documented in phase 0; if the chosen ordering produces flaky test behavior on a real wendy2c ROM, the fix lives in `clock_22v10.c` not in any chip — that isolation is the whole point of the chip-vtable layout.

## Critical files for implementation

- `assembler2/emulator/emulator.c`
- `assembler2/emulator/cpu_core.c`
- `assembler2/emulator/cpu_core.h`
- `22V10-wendy2c.pld`
- `upload_and_run.inc`
