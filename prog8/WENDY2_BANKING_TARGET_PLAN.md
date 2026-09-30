# Plan: a banked Prog8 target for the wendy2 machine

Establish a new **external** Prog8 compilation target (`wendy2`) that
exposes the wendy2/wendy2c memory-banking hardware, and demonstrate
banking of **code and data** running on the emulator in `wendy2c` mode.

This is a planning document. No code is changed by committing it.
Companion docs: [`PLAN.md`](./PLAN.md), [`ASM_MIGRATION_PLAN.md`](./ASM_MIGRATION_PLAN.md),
[`upstream/README.md`](./upstream/README.md) (the existing custom-target
scaffolding this builds on).

---

> **Status (in progress):** M0-M4 + M6 done -- the custom `wendy2` target
> compiles with upstream prog8c, boots on the emulator, drives the LCD, and
> demonstrates banked **data** (T1/T2/T4) and banked **code** (T3); 6 e2e
> golden tests green (`make -C assembler2 wendy2-test`). Implementation lives
> in `upstream/wendy2.properties` + `upstream/libraries/wendy2/` +
> `upstream/demos/` + `upstream/tests/`; see
> [`upstream/libraries/wendy2/README.md`](./upstream/libraries/wendy2/README.md).
> **M5** (the `$F800+` OS-call read/write emulator enhancement, S2.6) is the
> remaining milestone -- now folded into the disk-boot subsystem:
> [`WENDY2_DISK_BOOT_DESIGN.md`](./WENDY2_DISK_BOOT_DESIGN.md) (alternate
> monitor ROM + simulated SPI storage + loading programs over the file-I/O
> OS calls).

## 1. Goal & scope

* A custom upstream-Prog8 target `wendy2` (a `.properties` file +
  `libraries/wendy2/`), sibling to the existing `upstream/nmos` target,
  so banked programs compile with the official `prog8c.jar` -- "external
  if possible" satisfied.
* A small **banking runtime** in the target's syslib (hand-rolled, since
  upstream's `@bank`/`callfar` are hard-gated to cx16/c64/c128 -- see S3).
* Demo `.p8` programs + LCD goldens + a test runner that prove banked
  **data** and banked **code** work on the emulator under `--machine wendy2c`.

Out of scope: real-hardware bring-up (the emulator is the oracle);
self-hosting/p8c support (upstream prog8c is primary; a p8c path is a
later option, S9).

---

## 2. The hardware/emulator banking model (verified)

All facts below were read from the emulator + PLD, not assumed.

### 2.1 Address map
* **`$0000-$7FFF` -- fixed RAM, always.** Every `romcs`/`viacs` PLD term
  requires `a15=1` (`chips/clock_22v10_pld_generated.h:10-21`), so the
  lower 32K is RAM in every bank configuration. Holds ZP (`$00-$FF`),
  stack (`$0100-$01FF`), and the resident program.
* **`$F000-$F7FF` -- VIA 6522, always mapped**, independent of bank bits
  (`pld_viacs` ignores `c0..c4`, `clock_22v10_pld_generated.h:14-17`).
  This is essential: the bank-select register *is* a VIA port, so it must
  stay reachable in every bank.
* **`$F800-$FFFF` (2 KB) -- fixed RAM for every config except `$00`.**
  Verified by executing the PLD equations: across all configs `$10-$1F`
  this region maps to one physical address (`$0F800-$0FFFF`); it is ROM
  *only* in config `$00`. The CPU vectors `$FFFA-$FFFF` live here, so once
  the program leaves config `$00` they are in stable RAM regardless of
  which upper bank is selected (see S2.3).
* **`$8000-$EFFF` (28 KB) -- the switchable window.** ROM when the bank
  config is `$00` or `$10`; otherwise a RAM bank
  (`pld_romcs`/`pld_ramcs`, lines 10-21). This (not the full upper 32 K)
  is where banked code/data lives.
* The lower and upper CPU windows always land in **disjoint physical
  RAM halves** (CPU A15 -> RAM A14, `chips/ram_628128.c:5-27`), so
  switching the upper bank never disturbs the lower 32K.

### 2.2 Bank-select register & the 8 upper RAM banks
Bank config = VIA **PORT B bits 0-4** (`base_config_wendy2c.inc:6-7`,
`BANK_PORT=PORTB`, `BANK_MASK=%00011111`). Rather than derive the mapping
by hand, the full 32-config space was enumerated by executing the PLD
equations (`clock_22v10_pld_generated.h`). The configs that keep the
**lower 32K constant** are `$00, $01, $10-$17`, and among those the
switchable window resolves to exactly **8 distinct RAM banks plus ROM**:

  | logical bank | PORTB | upper-window phys ($8000) | window |
  |--------------|-------|---------------------------|--------|
  | 0 | `$01` | `$04000` | RAM |
  | 1 | `$11` | `$14000` | RAM |
  | 2 | `$12` | `$24000` | RAM |
  | 3 | `$13` | `$34000` | RAM |
  | 4 | `$14` | `$44000` | RAM |
  | 5 | `$15` | `$54000` | RAM |
  | 6 | `$16` | `$64000` | RAM |
  | 7 | `$17` | `$74000` | RAM |
  | (reset) | `$00` | -- | **ROM** |
  | (ROM)   | `$10` | -- | **ROM** |

So there are **8 upper RAM banks** (not 7), with the lower 32K constant
across all of them. The nuance the hardware exploits: by the raw r-bit
math config `$10` would be a **duplicate of bank 0 (`$01`)** -- both
select upper phys `$04000` -- so that otherwise-redundant config is
**repurposed to map ROM** into the window instead. `$00` is the power-on
reset config (also ROM). `$11-$17` are the same `%10xxx` values
`verification_wendy2c.s:95-150` exercises and passes on this emulator
(and real hardware).

The bank field is therefore not a clean contiguous bitfield; the target's
`set_upper_bank(0..7)` uses a small const translation table
`[$01,$11,$12,$13,$14,$15,$16,$17]` (S4.4). (Each PORTB value also maps
the window's two 16K halves to physical `2k`/`2k+1`; a probe test (T1)
confirms distinctness/non-aliasing empirically.)

### 2.3 What is fixed vs. switched (vectors are NOT a problem)
* Fixed across a switch: `$0000-$7FFF` (code/ZP/stack/data), the VIA at
  `$F000-$F7FF`, **and `$F800-$FFFF`** -- the latter is fixed RAM for every
  config except `$00` (verified: identical physical `$0F800-$0FFFF` across
  `$01,$10-$17`).
* Switched: only `$8000-$EFFF`.
* **CPU vectors are stable.** `$FFFA-$FFFF` sit in the fixed `$F800-$FFFF`
  RAM, so the design is: config `$00` is the power-on/startup view only;
  the program switches away from it immediately, and (if it needs
  interrupts) installs the handler address into `$FFFE/$FFFF` *after* that
  switch. The vector then holds regardless of which upper RAM bank is
  selected -- interrupts and banking coexist. The bank-switch helper still
  brackets the switch+access with `SEI`/`CLI` for atomicity (so an ISR that
  also banks can't interleave), not for vector safety.

### 2.4 Boot/load path (how a wendy2c program actually runs)
From `p8c/__main__.py:38,63-90`: the emulator runs a **boot ROM at
`$8000-$FFFF`** (`upload_and_run_eeprom_wendy2c.s` -> `wendy2c_boot.bin`)
with `--machine wendy2c --serial-input <framed> --cycle-cap N`. The boot
ROM receives the program over serial (framed by
`emulator/wendy2_upload.py`), writes it to **RAM at `$4000`**, and jumps
to it. So the program runs from the fixed lower 32K -- exactly where
banked code needs its switch/trampoline routines to live.

### 2.5 Output & test capture
The HD44780 LCD (4-bit, via PORTA/PORTB). The emulator prints the final
LCD frame on **stderr** at end-of-run (`emu_wendy2c.c:748-754`,
`  |row|` lines); `--lcd-trace PATH` dumps a frame per change. The
existing `prog8/tests/test_e2e_lcd.py` already asserts on those `|...|`
rows -- the wendy2 test runner reuses that mechanism. (Once the OS-call
read/write exists -- S2.6 -- tests can instead capture a host stream,
which is easier to golden than the LCD.)

### 2.6 OS calls (read/write) in fixed high RAM -- emulator enhancement
**Direction:** expose OS read/write (and the file-I/O primitives needed
for a self-hosting toolchain) as fixed entry points in the `$F800+`
region, callable from any bank.

Why fixed high RAM works: `$F800-$FFFF` is fixed across all configs
(S2.3), so a jump table / stub block there is reachable identically
whether the program is in bank 0 or bank 7 -- the natural home for an OS
ABI. (The nmos machine already does the analogous thing with injected
stub code at `$F006+`, `stubs.c` -- but those ports sit in the `$F000`
page, which on wendy2c is the **VIA**, so the wendy2 stubs must live
above it.)

What's missing today: the wendy2c emulator wires the real VIA/RAM/ROM/LCD
chips and **does not** install the `generate_stubs` host-I/O ports, so
there is currently no read/write/open/close syscall path in `wendy2c`
mode. Adding one is an **emulator enhancement**.

Proposed shape (mirrors the nmos stub design, relocated above the VIA):
* **Host-I/O port block, bus-trapped, `$F800-$F80F`** (a handful of
  addresses the wendy2c bus intercepts *before* the RAM chip): read-byte +
  EOF flag, write-byte, write-stderr, exit, open/close/read-handle/
  write-handle, argc/argv. Same host semantics as `stubs.c`'s ports.
* **Stub/jump table in fixed RAM at `$F810+`**, installed at machine init
  (the wendy2 analog of `generate_stubs`): the `jsr`-able OS entry points
  banked code calls. Stays clear of the vectors at `$FFFA-$FFFF`.
* The `$F800-$F80F` carve-out is the only RAM lost from the 2 KB fixed
  window; `$F810-$FFF9` remains RAM for the stub bodies + any resident OS
  state.

**Chosen approach: the port-block carve-out above**, for consistency with
the existing `stubs.c` port-based mechanism (a PC/execution-hook variant
was considered and rejected to keep one syscall mechanism across machines).

Payoff: (a) tests capture a host stream instead of OCR-ing the LCD;
(b) it's the prerequisite for ever running the **self-hosting toolchain**
(compiler reading a source file, writing output) on `wendy2c` -- the same
file-I/O surface the nmos target already enjoys, now bank-safe. On real
hardware these entry points would be a small resident kernel doing serial
I/O; the emulator provides them directly. The ABI (fixed `$F800+` entry
points) is identical either way.

---

## 3. Upstream Prog8 capability & the gap

From the v12.1.1 jar (full findings in this session's research):

* **Custom targets are first-class** via `-target foo.properties`
  (`ConfigFileTarget`). Keys: `cpu`, `encoding`, `output_type`,
  `load_address`, `memtop`, `bss_highram_start/end`,
  `bss_goldenram_start/end`, `io_regions`, `zp_scratch_*`,
  `zp_fullsafe/kernalsafe/basicsafe`, `virtual_registers`, `library`,
  `custom_launcher_code`, `assembler_options`. Assembler is always 64tass.
* A custom target must ship `libraries/<name>/syslib.p8` providing the
  `sys`, `cx16` (the 16 virtual registers `r0..r15`), and
  `p8_sys_startup` blocks (incl. `init_system`, `cleanup_at_exit`,
  `sys.exit*`). The repo's `upstream/libraries/nmos/syslib.p8` is the
  working template.
* **Banking must be hand-rolled.** `@bank N` extsubs and the
  `callfar()`/`callfar2()` builtins exist but their codegen is gated by a
  literal `targetName in {cx16,c64,c128}` check -- a custom target gets
  *"callfar is not supported on the selected compilation target."* The
  `rombank()`/`rambank()` helpers are ordinary cx16 *library* code, not
  builtins. There is no `.properties` key for a bank register, and no
  per-variable `@bank` data placement.

**Conclusion:** define our own bank helpers + far-call trampoline in
`libraries/wendy2/`, and access banked data manually via `@(addr)` /
`peek`/`poke`. No compiler changes needed.

---

## 4. Target design

### 4.1 `upstream/wendy2.properties`
```
cpu = 65c02                 ; wendy2c is a 65C02 (stz/bra used by demos)
encoding = cp437
output_type = RAW
load_address = $4000        ; matches the boot-ROM serial-upload model
memtop = $8000              ; program + BSS live entirely in $4000-$7FFF
bss_highram_start = 0       ; banking is manual; no compiler-managed hi BSS
bss_highram_end = 0
bss_goldenram_start = 0
bss_goldenram_end = 0
io_regions = $f000-$f7ff    ; VIA -- compiler must not allocate here
zp_scratch_ptr = $f8        ; (mirror nmos.properties ZP scratch layout)
zp_scratch_b1 = $fa
zp_scratch_reg = $fb
zp_scratch_w1 = $fc
zp_scratch_w2 = $fe
zp_fullsafe = $30-$f7
zp_kernalsafe = $30-$f7
zp_basicsafe = $30-$f7
virtual_registers = $02
library = ./libraries/wendy2
custom_launcher_code =
assembler_options =
```
Notes: `memtop=$8000` keeps every prog8 variable in the fixed lower 32K;
the banked window is touched only through explicit windowed addresses, so
the compiler never needs to know it's banked. ZP `$00-$2F` left for the
VIA shadow + bank state + the runtime's pointers.

### 4.2 `upstream/libraries/wendy2/syslib.p8`
Start from `libraries/nmos/syslib.p8` and change:
* **`sys.exit*` / `p8_sys_startup.cleanup_at_exit`** end with `STP` (the
  wendy2c "halt"; the emulator dumps the LCD on STP / cycle cap), or
  `jmp` the `$F800+` OS exit stub once S2.6 lands. There is no `$F00F`
  exit syscall in wendy2c mode (that's the nmos machine).
* **I/O binding.** Route byte read/write (and the file primitives) at the
  fixed `$F800+` OS-call entry points (S2.6) -- the nmos syslib's
  `$F006+` references, retargeted above the VIA. Until that enhancement
  lands, `txt.*` output goes to the LCD driver (S4.3) only.
* **`init_system`**: set VIA DDRA/DDRB for the 4-bit LCD + bank bits
  (mirror `base_config_wendy2c.inc` + the existing init), HD44780 4-bit
  init, and **switch from config `$00` to the default working bank
  `$01` (logical bank 0)** so the upper window is RAM that code/data can be
  loaded into. Keep a **PORTB shadow byte in ZP** so bank/LCD-E bits
  compose without read-back surprises.

### 4.3 `upstream/libraries/wendy2/textio.p8` (output)
Port the 4-bit HD44780 driver (`display_routines_4bit.inc`,
`display_string*.inc`) into Prog8 `inline asmsub`s exposed as
`txt.chrout(ubyte)`, `txt.print(str)`, `txt.clear()`, `txt.print_ub`
(hex). This is the **bulk of bring-up** -- mechanical, mirrors the
existing vasm `.inc` line-for-line, validated by an LCD golden before any
banking work. (Upstream `.p8` can't `.include` the vasm `.inc` files, so
they're reimplemented.)

### 4.4 The banking runtime (`libraries/wendy2/banking.p8`)
All in the fixed lower 32K (so it survives a switch). Logical bank IDs
**0-7** map to PORTB configs via the const table
`BANKCFG = [$01,$11,$12,$13,$14,$15,$16,$17]` (S2.2); the LCD-E bit
(bit 5) is preserved via the ZP PORTB shadow.

* `wendy2.set_upper_bank(ubyte n)` -- `SEI`; shadow = (shadow & %11100000)
  | BANKCFG[n & 7]; `sta PORTB`; settle nops (hardware fidelity); `CLI`
  (or restore the saved I flag). IRQs are bracketed for atomicity, not for
  vector safety (vectors are in fixed RAM, S2.3).
* `wendy2.set_rom()` -- select config `$10` (ROM in the window), e.g. to
  call back into boot-ROM services; rarely needed by demos.
* `wendy2.get_upper_bank() -> ubyte`.
* `wendy2.bank_poke(ubyte n, uword win, ubyte v)` /
  `bank_peek(ubyte n, uword win) -> ubyte` -- save current bank, switch to
  `n`, access `$8000+win` (or absolute `win` in `$8000-$EFFF`), restore.
  The save/switch/access/restore is the proven `verification_wendy2c.s`
  pattern.
* `wendy2.callfar(ubyte n, uword win) -> ubyte` -- the **far-call
  trampoline** (our hand-rolled `x16jsrfar` equivalent): save bank, switch
  to `n`, `jsr (win)` into `$8000+`, restore bank, return A. Lives in the
  fixed region by construction (it's a normal asmsub at `$4000+`).

Banked **data** = `bank_peek/poke` or a thin pointer wrapper. Banked
**code** = `callfar` to a routine previously copied into a bank's window.

---

## 5. Build & run harness

Mirror `p8c --run` (`p8c/__main__.py:81-90,179-182`):

`upstream/wendy2_run.sh <demo.p8> [--lcd-out FILE]`:
1. `cd upstream && java -jar /tmp/prog8c.jar -target wendy2.properties
   -out OUT demo.p8` -> RAW binary at `$4000`.
2. Frame it: `python3 ../emulator/wendy2_upload.py OUT/demo.bin -o demo.framed`.
3. Build the boot ROM once (`vasm6502_oldstyle` on
   `upload_and_run_eeprom_wendy2c.s`, as `build_boot_rom` does) ->
   `wendy2c_boot.bin`.
4. Run: `emulator.out wendy2c_boot.bin --machine wendy2c
   --serial-input demo.framed --cycle-cap N` -> capture the LCD frame from
   stderr (and, once S2.6 lands, the OS-write host stream / output file --
   easier to golden).

(64tass + the prog8 jar + the emulator are the only host deps; all were
installed/built in this session's container -- see `setup`-style notes in
`upstream/`.)

---

## 6. Demo programs + tests

Each `.p8` lands a known string on the 16x2 LCD; the runner diffs the
captured frame against a `.expected.lcd` golden (same discipline as
`test_e2e_lcd.py`). All live under `upstream/libraries/wendy2/tests/` (or
`prog8/tests/wendy2/`).

(`win` below is an absolute address in the switchable window `$8000-$EFFF`.)

* **T1 `bank_probe.p8` -- data banking proof + bank-set discovery.**
  For `bank in 0..7`: `bank_poke(bank, $A000, $40+bank)`. Then read all
  back with `bank_peek` and verify each equals `$40+bank` (proves the 8
  writes land in distinct banks and the lower-32K program is undisturbed).
  Print `bank8 OK` / the count of distinct banks. *This test empirically
  confirms the 8-bank set* derived in S2.2.

* **T2 `banked_data.p8` -- banked arrays.** Fill `$A000..$A0FF` in bank 0
  with `i`, and in bank 1 with `255-i`; then for several indices read
  `bank_peek(0,..)+bank_peek(1,..)` and assert it's always `255`; print
  the checksum in hex. Demonstrates banked **data** beyond one 32K map.

* **T3 `banked_code.p8` -- banked code via far-call.** At startup copy a
  tiny routine (hand-written `%asm{{ }}`, position-correct for `$A000`)
  into bank 2's window, then `wendy2.callfar(2, $A000)`; the routine
  returns `A=$2A`; print it as `*`. Proves a `jsr` into a switched-in bank
  works and control returns with the original bank restored.

* **T4 `bank_counters.p8` -- round-trip/persistence.** Keep a 1-byte
  counter at `$A010` in each of banks 0-7; loop 3 times incrementing every
  bank's counter; finally read them out -> expect eight `3`s. Stresses
  repeated switching + restore and that all 8 banks retain independent
  state.

A `test_wendy2_banking.py` registers one test per `.p8`/`.expected.lcd`
pair, skips if `prog8c.jar`/`64tass`/`vasm`/emulator are absent, and is
wired into `make prog8-test` (or a new `make wendy2-test`).

---

## 7. Milestones

* **M0 -- target skeleton.** `wendy2.properties` + minimal syslib
  (`sys`/`cx16`/`p8_sys_startup`, exit=STP). A `main { }` that just `STP`s
  compiles and runs to a blank-LCD golden. Proves the custom target +
  boot-upload + emulator chain end-to-end.
* **M1 -- output.** `textio.p8` 4-bit HD44780 driver; `hello.p8` prints
  to the LCD (golden). No banking yet.
* **M2 -- bank register + probe.** `set_upper_bank`/`get_upper_bank`/
  `bank_peek`/`bank_poke`; T1 green; the usable bank set is recorded.
* **M3 -- banked data.** T2, T4 green.
* **M4 -- banked code.** `callfar` trampoline; T3 green.
* **M5 -- OS calls (emulator enhancement, S2.6).** Add the `$F800+`
  host-I/O ports + stub table to the wendy2c emulator; retarget the syslib
  I/O to them; switch the demos/runner to host-stream goldens. Optional for
  the banking demos (they work LCD-only), but the prerequisite for a
  self-hosting toolchain on `wendy2c`.
* **M6 -- docs + CI.** README for the target; `make wendy2-test`; link
  from `PLAN.md`.

Critical path is **M1** (the LCD driver port) -- the only large piece for
the banking demos; banking itself (M2-M4) is small once output works. M5
(OS calls) is a separable workstream gated on the emulator change.

---

## 8. Risks / open questions

* **LCD driver port (largest task).** Must match the emulator's HD44780
  protocol/timing exactly. Mitigate by mirroring `display_routines_4bit.inc`
  and gating M1 behind an LCD golden before touching banking.
* **Bank count -- RESOLVED (8).** Enumerating all 32 configs confirms 8
  upper RAM banks (configs `$01,$11-$17`) with the lower 32K constant, plus
  ROM via `$00`/`$10` (the repurposed duplicate of bank 0). T1 verifies
  empirically.
* **Vectors -- RESOLVED (not banked).** `$F800-$FFFF` (incl. `$FFFA-$FFFF`)
  is fixed RAM for every config except `$00`. The program leaves config
  `$00` at startup and installs any IRQ/NMI handler into `$FFFE/$FFFF`
  once; it then holds across all bank switches. Interrupt-driven banked
  programs are fully supported (a banking ISR should still save/restore the
  current bank itself).
* **OS-call emulator enhancement (S2.6 / M5).** Carving the `$F800-$F80F`
  port block out of the fixed RAM window must not break the vectors
  (`$FFFA-$FFFF`) or any resident OS state, and the wendy2c bus must trap
  those addresses ahead of the RAM chip. Scope is contained (mirrors the
  existing `stubs.c` ports), but it is a C/emulator change, separate from
  the prog8-side work. Real hardware would implement the same ABI as a
  resident serial-I/O kernel.
* **Assembler coupling.** This target uses 64tass (upstream's fixed
  assembler). It does not depend on the on-host-assembler migration
  ([`ASM_MIGRATION_PLAN.md`](./ASM_MIGRATION_PLAN.md)); the two are
  independent.
* **memtop headroom.** `$4000-$7FFF` (16 KB) for code+vars; the LCD driver
  + banking runtime are small, but a large demo could crowd it. Lower
  `load_address` toward `$0200` if needed (the boot ROM can upload there
  too -- verify against `upload_and_run_eeprom_wendy2c.s`).

## 9. Optional follow-on: p8c support

p8c already has a `wendy2c` target and now accepts raw `%asm{{ }}` blocks,
so the same banking runtime (as inline asm) could be offered to p8c-built
programs later -- useful for the self-host story, but not required for
this target. Upstream prog8c is the primary, "external" path per the
request.
</content>
