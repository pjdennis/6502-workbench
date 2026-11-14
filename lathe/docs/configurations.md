# Lathe: configurations (stage 11)

Status (2026-11-14): design, after spike L5, and code in banks and overlays built. Built so far: the spike in `lathe/tests/spike_l5/`, and steps 1 to 8 of the order of work: files on Wendy 2 (section 1), the far-call run-time modules, and the linker's side, which links the same object files all in one, with code in banks on Wendy 2, or with code in overlays on the default machine (section 5, "As built"). Steps 9 to 11 (banked data, the compiler's own placement, the gate) are not done. Every number is marked **measured** (by a program in this repository, named) or **estimated** (worked out from measured numbers, with the method given).

A KB here is 1,024 bytes.

This document says how one set of object files becomes the compiler linked **all in one**, **banked** or **chained**, chosen by the environment file, with no change to the source ([`goals.md`](goals.md), goals 11, 15, 16). It answers five questions:

1. On which emulated machine can the banked compiler run with file input and output?
2. What does a far call cost? (Spike L5: [`spikes.md`](spikes.md), "Result of L5".)
3. What must be resident, and does 16 KB hold it?
4. Where do the compiler's tables go?
5. What exactly does stage 11 build, and in what order?

## Summary

- **Machine.** Emulated Wendy 2 with `--disk DIR` already has file input and output, at `$F800-$F80F`, from any bank. The Prog8 compiler `p1` used it to compile itself banked. No emulator change is needed. Overlays are tested on the default machine with its host file services, as the spike does.
- **Far calls** cost 182 cycles more than a `JSR` and `RTS` with a 6-byte stub, measured. One stub form serves banks and overlays.
- **Resident code.** Placed by module, the compiler needs **13,862 bytes (13.5 KB) of resident code** (estimated; 12,690 bytes of it are measured code), under the 16 KB goal. It makes about **6 far calls a source line** (measured on a host compile of `reg.lth`): about 1,100 cycles a line. Lower layers never call upper ones, so the busy calls (a byte read, a character added to a name) stay inside fixed memory.
- **Tables.** 16.3 KB of tables must be in fixed memory, 18.2 KB can go in a data bank reached only by fixed code, and 6.6 KB can go in the bank of the only code that uses them (measured sizes, at today's capacities). With the error messages in the data bank, everything fits Wendy 2, with less than 1 KB to spare in the lower 32 KB and 2 KB more at `$F810-$FFF9`.
- **Chaining inside the compiler is pointless.** Compiler, linker pass 1 and linker pass 2 as separate programs is all "chained" needs to mean. Overlays by module are far too slow for a one-pass compiler.

## 1. Where the banked compiler can run

### What the emulator offers

Read from `emulator/README.md`, `emulator/emu_wendy2c.c`, `emulator/chips/syscall_ports.{h,c}`, `emulator/stubs.c` and `prog8/p1/tests/test_p1.py`.

| Machine | Memory | Banks | Files | Output | Interrupts |
|---|---|---|---|---|---|
| default (`nmos-default`) | 64 KB flat | none | host services `$F012` … `$F024`, by handle | `$F009`, `$F00C` | `BRK` only |
| `michael` | 16 KB | none | none | LCD | VIA timer |
| `wendy2c` | 512 KB | 8 RAM banks in `$8000-$EFFF` | none | LCD | VIA timer |
| **`wendy2c --disk DIR`** | the same | the same | **ports `$F800-$F80F`**, files in `DIR` | files, LCD | VIA timer |

The `$F800` ports (`syscall_ports.h`): write a file name byte by byte to `$F800` (clear with `$F801`); read `$F802` to open it for reading or `$F803` for writing, which gives a handle (0 if it failed) and makes it current; `$F804` selects the current handle; `$F805` reads a byte (0 at the end); `$F806` gives bit 7 set at the end of the file, **and then rewinds the file**; `$F807` writes a byte; `$F808` closes; `$F80F` stops the emulator. At most 16 files are open. The chip sits on the bus ahead of the RAM, in the high fixed RAM, so it is reached from every bank.

**How the Prog8 chain used it.** `P1WendySelfHost` (`prog8/p1/tests/test_p1.py`, run with `P1_WENDY_SELFHOST=1`) runs `p1` built for Wendy 2 as `emulator.out BOOT.bin --machine wendy2c --wendy2-prog p1.bin --load 0200 --disk DIR --cycle-cap 60000000000`. `p1` reads the fixed name `in.p8` and writes `out.s` through the ports (it has no command line), keeps its symbol tables in a second RAM bank through accessors in fixed high RAM, and gives assembly identical to the host compiler's in about 11 G cycles (`prog8/WENDY2_MONOLITH_BANKING_PLAN.md`). The code of `p1` was not banked: it fitted in one held bank.

**What spike L5 confirmed** (`lathe/tests/spike_l5/env_wendy2.s`, measured): a program preloaded with `--wendy2-prog` loads two bank files from `DIR` at start-up, writes its output to `out.txt`, takes timer interrupts, and ends with `STP`, whose exit report gives the CPU cycles. Loading costs 21 cycles a byte with the spike's loader in assembler; `rt_bank.start`, in Lathe through `disk.read`, takes about 78 (measured: `farcall.lth`'s 184 bytes of banks cost 14,313 cycles at start-up, beside 29 far calls at 182).

### What is missing for the Lathe compiler on Wendy 2, and how to do without it

| Gap | Without changing the emulator |
|---|---|
| `--wendy2-prog` loads only into bank configuration `$01`. | The start-up code loads each bank's file through the ports, as the spike does: about 600,000 cycles for 28 KB *(estimated from 21 a byte)*. |
| No command line. The compiler takes `SOURCE OUTDIR IMPORTDIR...`. | `argc` and `argv` read the file `args` in `DIR` at their first call: one argument a line (a carriage return before the line feed is dropped; a last line without a line feed counts), at most 16 arguments and 256 bytes of text with their zeros. |
| No output or error stream. | Standard output goes to a file `out`, error messages to a file `errors` (created at the first byte), and the test reads them. |
| The exit code written to `$F80F` is not the emulator's exit status, and the exit report says "(cycle cap)" after it. | `exit(code)` writes the code in decimal and a line feed to a file `status` and ends with `STP` (the report then says "(STP)"). No `status` file means `main` returned: status 0. |
| `$F805` gives 0 at the end; `$F806` rewinds at the end. | `read` tests `$F806` first and sets the carry at the end, as the default machine's `read` does. After `$F806` has reported the end, the next read would start the file again, so `read` keeps a flag for each handle that says the file ended, cleared by `open`. |
| One current handle. | `read`, `write` and `close` select their handle (`$F804`) on every call: 4 cycles more a byte. Sixteen files can be open at once, so the compiler's source, interface files (one opening another) and object file can all be open together, as on the default machine: nothing is buffered or reopened. |
| `--disk` makes the emulator change directory before it opens `--wendy2-prog`. | Give the program's path as an absolute path. |
| `lathe/env/wendy2.env` and `boards.md` say Wendy 2 has no host services. | A new environment `wendy2disk.env` and a board entry that passes `--disk` (stage 11, step 1). |

**Built (step 1).** `lathe/rt/disk.lth` does all of the above over the ports, with the functions of `host.lth` that `sys.lth` uses under the same names and types (`open`, `open_out`, `close`, `read`, `write`, `argc`, `argv`, `put_byte`, `put_error`, `exit`); it has no `read_byte`, because there is no standard input. `boards.md`, "Wendy 2 with files", has the recipe; `lathe/tests/test_disk.py` runs `sys.lth`, with `host` renamed `disk`, on Wendy 2.

### Changes to the emulator the owner may choose (none is required)

| Change | Files | Tests |
|---|---|---|
| **The exit code of `$F80F` as the process's exit status**, and the report saying "(power off)". | `emulator/emu_wendy2c.c` (the end of the run: return `sysc_state.poweroff_code`; the report's reason), `emulator/README.md`. | A new `emulator/tests/test_chip_syscall_ports.c` (the chip has no unit test now) and a Makefile target; the spike's runner then checks the status. |
| **Program arguments on Wendy 2**: `--disk-args A B …` and two ports, `$F809` read gives the number of arguments and `$F80A` reads the next byte of them (0 between arguments). | `emulator/cli.{c,h}` (`--disk-args`), `emulator/chips/syscall_ports.{c,h}`, `emulator/emu_wendy2c.c`, `emulator/README.md`; `tests/test_cli.c`. | The new chip test. |

Recommendation: the first, which is about ten lines and makes failures visible to a test; not the second, because the `args` file works and keeps the port block as it is. A bank register on the default machine was considered and is not recommended: Wendy 2 already has the real hardware, and a second banking scheme would be one more thing for the emulator to keep.

### Overlays on the default machine

The default machine has 64 KB of flat RAM and host files, so an overlay is a file loaded into a window by the program itself. The spike's `ovl-host` configuration does it: a window at `$8000-$8FFF`, overlays `L5OV1.BIN` and `L5OV2.BIN` in the emulator's working directory, loaded with `$F012` (open), `$F018` (read) and `$F015` (close). The test runs the emulator with its working directory set to the build's directory. That is the way to test the overlay routine of stage 11; it needs no banks.

## 2. The far call

Measured by spike L5 ([`spikes.md`](spikes.md), "Result of L5"). The choice for stage 11:

- **The stub**, in fixed memory, 6 bytes: `JSR fc_call` / `.byte N` / `.word f-1`. `N` is the bank's register value, or the overlay's number.
- **The bank routine** (`lathe/tests/spike_l5/rt_bank.s`, 101 bytes, NMOS instructions): reentrant, keeps the port's other bits, A, X, Y and flags in, A, X and carry out. 182 cycles over a plain call. It becomes `lathe/rt/rt_bank.lth`, `asm` functions.
- **The overlay routine** (`rt_ovl.s`, 107 bytes and the loader): 82 cycles while the overlay is in the window, a load (43 cycles a byte on the default machine) when it is not, and a second load on the way back. Not reentrant.

## 3. What must be resident

### The modules and their sizes

Measured by `lathe/tests/spike_l5/l5calls.py`: code bytes of every function some test program of the ten twins keeps (the method of `size_report.py --report`). The six modules not written yet are estimated from their lines of Python code at 7.4 to 8.6 bytes a line, the range the middle layers measured (`fbuf` 7.51, `cond` 7.44, `out` 8.58, `reg` 8.60).

| Module | Bytes of code | |
|---|---|---|
| err | 465 | measured (and 5,140 of constant data: the messages) |
| kernel | 4,248 | measured |
| src | 338 | measured |
| lex | 2,192 | measured (305 of constant data) |
| typetab | 927 | measured |
| fold | 1,299 | measured |
| fbuf | 3,221 | measured |
| out | 2,172 | measured |
| reg | 6,947 | measured |
| cond | 2,448 | measured |
| inline | 3,359 to 3,904 | estimated, 454 lines |
| gen | 10,426 to 12,117 | estimated, 1,409 lines |
| asmblock | 4,218 to 4,902 | estimated, 570 lines |
| expr | 8,761 to 10,182 | estimated, 1,184 lines |
| decl | 6,304 to 7,327 | estimated, 852 lines |
| lathec | 1,087 to 1,264 | estimated, 147 lines |
| sys, rt_math, rt_frame | 495 | measured, the parts the twins use |
| **total** | **58,900 to 64,450** | |

### Who calls whom

The host modules import only modules below them (`lathe/tests/test_layers.py`), and the Lathe twins keep that order. So a call goes down the table above, never up, and the compiler makes no call through a pointer between modules. A far call happens only when a module in a bank calls a module in another bank. Calls into fixed memory are plain `JSR`s, whoever makes them.

`l5calls.py` traces a host compile of `lathe/src/reg.lth` (1,401 lines, 46,727 bytes, 8,347 tokens) with `sys.setprofile` and counts each call from a function of one module to a function of another. Measured:

- 840,341 calls of compiler functions in all, 349,077 of them between modules: **249 a line**.
- The busiest are at the bottom: `kernel → sys` 65.5 a line (a byte read or written), `src → kernel` 33.4, `lex → src` 33.4, `lex → kernel` 22.1 (a character added to a name), `out → kernel` 21.4.
- Between the upper modules: `gen → reg` 7.7 a line, `gen → typetab` 6.8, `reg → typetab` 6.8, `lex → err` 6.2 (the position of each token), `out → fbuf` 5.0, `expr → lex` 4.9, `expr → gen` 4.6, `expr → err` 3.5, `reg → fbuf` 3.0, `cond → reg` 2.4, `expr → inline` 1.6, `gen → cond` 1.4; everything else is below 1.5 a line.

The static matrix (distinct pairs of functions, from the twins' `CALL` records and from the host source) is printed by the same tool.

### Placements

Each placement puts a module's code in fixed memory or in a bank. Resident code is the fixed modules, the run-time modules, the far-call routine and one 6-byte stub for each function in a bank that the host source calls from outside that bank. Far calls are those of the traced compile. Cycles are at 130 and 182 a far call, measured.

| Placement | Resident (KB) | Banks (KB of code) | Far calls a line | Cycles a line |
|---|---|---|---|---|
| **D (proposed)**: fixed err, kernel, src, lex, typetab, fold, fbuf; bank 1 lathec, decl, expr, inline; bank 2 gen, reg, cond, out; bank 3 asmblock | **13.5** | 19.1–22.1, 21.5–23.1, 4.1–4.8 | **5.9** | 770–1,070 |
| E (fallback of D): cond in bank 3 with asmblock | 13.7 | 19.1–22.1, 19.1–20.7, 6.5–7.2 | 9.7 | 1,270–1,770 |
| A: D with asmblock in bank 1 | 13.5 | 23.2–26.9, 21.5–23.1 | 5.9 | 770–1,070 |
| B: out fixed, lex in bank 1 | 13.4 | 25.3–29.1 (over 28 KB), 19.4–21.0 | 5.8 | 760–1,060 |
| C: reg and out in a third bank | 13.8 | 23.2–26.9, 12.6–14.2, 8.9 | 16.6 | 2,160–3,030 |
| one bank per phase: lex+decl, expr, gen+cond, reg+fbuf+out | 9.9–10.1 | four, 11.6–14.7 each | 24.5 | 3,180–4,460 |
| code generation fixed | 33.6–35.4 (over 16 KB) | | 1.7 | |

(The far calls into `asmblock` are not in this trace: `reg.lth` has no `asm` block. They come only with `asm` lines.)

**Is placement by module fast enough? Yes**, for one reason: the lower layers are fixed, and they are where the busy calls go. The upper modules call each other a few times a line, not thousands. In placement D the far calls cost about 1,100 cycles a line *(estimated: 5.9 measured × 182 measured)*. The lexer alone measured 553 cycles a byte (`spikes.md`, L4), 18,400 cycles a line of `reg.lth`; the whole compile will be several times that *(estimated 50,000 to 100,000 cycles a line)*, so the far calls cost 1 to 2%. What would make it slow is a placement that cuts between `gen` and `reg` (7.7 a line), or puts `lex`, `src` or `kernel` in a bank (34 to 66 a line each): placement C and the placement by phase show it.

**Resident against 16 KB**: 13,862 bytes in placement D *(estimated; 12,690 of them are measured code, the rest the run-time modules (495), the routine (101) and 96 stubs (576))*. That leaves 2,522 bytes, which the estimates for `gen` and `expr` do not touch: they are in banks.

## 4. Where the tables go

### The rule of one window

Wendy 2 has one window, `$8000-$EFFF`, which switches as a whole (the two 16 KB halves follow one register). Code running in the window cannot see a data bank, because mapping the data bank removes the code. So:

- a table used by code in a bank must be in fixed memory, or in that same bank;
- a table in a **data bank** is reached only by fixed code, which maps the bank, uses the table and maps back what was there before, all before it returns. It may call other fixed functions meanwhile, but no function in a window.

### Each table, by the modules that name it

From `memory_report.py` (sizes) and the host source (`l5calls.py`, "Tables under placement D"), at the capacities of 2026-11-14:

| Where (placement D) | Tables | Bytes |
|---|---|---|
| **Fixed**: named by modules in two places | the symbol columns (6,528) and members (640): named by decl, expr, gen, inline, reg, out, asmblock; text memory (4,096): err, inline, lathec, kernel; `lex.string` (2,048): expr, gen, inline; `out.table` (2,048): expr, gen; `reg`'s operand stack and frame; `typetab`; `fbuf`'s label notes; the small ones | 16,667 |
| **Data bank**: named only by fixed code | `kernel.names` (12,800); `fbuf.buffer` (4,096), `label_offset`, `label_uses`; small tables of `kernel` and `fbuf` | 18,593 |
| **Bank 1** (front end): named only by its own code | `expr.case_value`, decl's and inline's small tables | 801 |
| **Bank 2** (code generation) | `out`'s table fix-ups (2,048), `reg.slot_size` and `slot_name` (768), `gen`'s | 5,355 |
| **Bank 3** | `asmblock`'s labels | 607 |
| **Data bank, constant** | `err`'s messages | 5,140 |

### Does it fit Wendy 2?

| Memory | Holds | Bytes | Of |
|---|---|---|---|
| `$0000-$01FF` | zero page, stack | 512 | 512 |
| `$0200-$7FFF` | resident code 13,862; fixed tables 16,667; `lex`'s constants 305; constants whose address is passed on, about 750 *(estimated from the host's byte constants)* | 31,584 | 32,256 |
| `$F810-$FFF9` | free fixed RAM, for tables that outgrow the lower 32 KB (any table up to 2,026 bytes) | 0 | 2,026 |
| bank 1 | code 19,511–22,677, tables 801 | 20,312–23,478 | 28,672 |
| bank 2 | code 21,993–23,684, tables 5,355 | 27,348–29,039 | 28,672 |
| bank 3 | code 4,218–4,902, tables 607 | 4,825–5,509 | 28,672 |
| bank 4 (data) | names, function buffer, messages | 23,733 | 28,672 |

- **It fits, with little to spare.** Fixed memory has 672 bytes left below `$8000` and 2 KB above `$F810`. Bank 2 is over by up to 367 bytes at the upper estimate of `gen`; placement E (cond to bank 3) then leaves 2,217 to 3,908 bytes of room there, at 3.8 more far calls a line.
- **What grows.** The name heap is to grow to about 16 KB for `gen`, `expr` and `decl` (`architecture.md`, "What stays in memory"): it is in the data bank, which has 4,939 bytes of room. The symbol table is to grow to about 500 rows: 2 KB more in fixed memory, which only `$F810-$FFF9` holds. The ways on in `architecture.md` (import only what is named, fewer exports) shrink both. If they are not done, the text memory's saved tokens (2 KB) can move to the data bank, with `inline` reaching them through `kernel` functions instead of `env.mem`.
- **The cost of the data bank.** The compile enters a function of `kernel` that touches `names`, or of `fbuf` that touches its buffer, 30.6 times a line from another module (measured, `l5calls.py`). At about 40 cycles to map the bank and map back *(estimated)*, about 1,200 cycles a line. Most of it is `lex` adding a name character by character (13 a line): with `lex.name_or_keyword` mapping the bank once around the whole name (it is fixed code, and calls only fixed code), entries fall to about 15 a line.
- **Banks used:** 4 of the 7 that are not the start-up configuration's.

### What the language needs for banked data

Goal 11's non-goal: banked data is explicit. Two additions:

1. **`in REGION`** on a module-level variable or constant (already in `language.md`'s grammar sketch, not yet built): `var names: [12800]byte in NAMES`. The object file records the region's name. The environment says where `NAMES` is: a bank of a window, or fixed memory. A region the environment does not name is ordinary fixed memory, so the all-in-one environment needs no entry.
2. **`with REGION do … end`**, a statement like `critical`: a variable or constant `in REGION` may be used only inside it (a compile error otherwise). It compiles to `LDA #bank(REGION)` (a new fix-up kind: the region's register value, 0 for fixed memory) / `JSR farcall.map`, which maps the bank and gives the old value in A, stored in a temporary of the function; and at the end, and at every `return`, `break` or `continue` that leaves it, `LDA temporary` / `JSR farcall.unmap`. Blocks nest. The linker checks that a function with a `with` block is in fixed memory, and that no call made inside one reaches code in a window (a `CALL` flag). In a configuration where the region is fixed, the routines are a lone `RTS`: 30 cycles a block *(estimated)*; the linker may turn the two `JSR`s into `BIT abs` (4 cycles each) as a later refinement.

`p1` reached the same arrangement on Wendy 2 by hand: code fixed, symbol tables in a bank behind accessors.

## 5. The design for stage 11

### The environment file

The version-1 entries stay as they are: `code` and `data` are the fixed memory for code and for variables. New entries (version 2), in the same form:

```
; wendy2bank.env: the compiler on Wendy 2, banked
cpu       65c02
zeropage  $00 $FF
code      $0200 $3DFF            ; fixed: code, stubs, the far-call routine, fixed constants
data      $3E00 $7FFF            ; fixed: variables, frames, fixed tables (the split by hand,
                                 ; as in lathe/src/compiler.env)
more      data $F810 $FFF9       ; a second fixed range for variables
stack     $FF
exit      stop
output    raw

window    WIN $8000 $EFFF        ; an address range whose contents are switched
switch    WIN bank $F000 $1F     ; switched by the bank register at $F000, bits $1F
bank      WIN 1 $11 LATHE1.BIN   ; bank 1: the register's value, and the file written for it
bank      WIN 2 $12 LATHE2.BIN
bank      WIN 3 $13 LATHE3.BIN
bank      WIN 4 $14              ; no file: data only, nothing to load
place     lathec WIN 1           ; a module's code goes in bank 1 of WIN
place     decl WIN 1
place     expr WIN 1
place     inline WIN 1
place     gen WIN 2
place     reg WIN 2
place     cond WIN 2
place     out WIN 2
place     asmblock WIN 3
region    NAMES WIN 4            ; the source's `in NAMES`
region    MSGS WIN 4
farcall   rt_bank                ; the run-time module for far calls and for loading banks
define    BOARD 2
define    DISK 1                 ; sys reads its arguments from the file `args`
```

```
; overlays on the default machine (a test configuration)
window    OVL $8000 $9FFF
switch    OVL overlay
overlay   OVL 1 L5OV1.BIN        ; overlay 1: the file written for it, loaded on demand
place     asmblock OVL 1
farcall   rt_ovl
```

| Entry | Meaning |
|---|---|
| `window NAME FIRST LAST` | An address range whose contents change. It must not overlap `code`, `data`, `more` or another window. |
| `switch NAME bank ADDR MASK` | The window is switched by writing the bits `MASK` of the register at `ADDR`; the other bits are kept. |
| `switch NAME overlay` | The window is filled by loading a file. |
| `bank NAME N VALUE [FILE]` | Bank `N` (1 to 255) of the window: the register value, and the file the linker writes with its contents. Without a file the bank holds only data that code sets up. |
| `overlay NAME N FILE` | Overlay `N` of the window and its file. |
| `place MODULE NAME N` | The module's code goes in bank or overlay `N`. A module not placed is fixed. By module only: a module is the unit the call structure is known by, and placing functions one by one would need names in the environment that the source can change. |
| `region REGION NAME N` | The data region `REGION` is bank `N` of the window. `region REGION fixed` (or no entry) puts it in fixed data memory. |
| `more data FIRST LAST` | A second range for variables, used when the first is full. |
| `farcall MODULE` | The run-time module that the stubs and `with` blocks call: `rt_bank` or `rt_ovl`, in `lathe/rt/`. The build adds it as it adds `rt_frame`. |

The compiler reads none of these (it reads `cpu` and `define` only), so an object file is the same in every configuration (`lathe/tests/cases/e2e-config/farcall.lth` checks it: the program's modules are the same bytes in four configurations, but for the CPU byte of the `MOD` record where a 6502 configuration is compared with a 65C02 one).

**As built** (steps 2 and 4 to 8; `lathe/host/lk_envf.py`, `lk_win.py`; the decisions this section left open):

- **The order of entries.** A window comes before its `switch`, the switch before its `bank` or `overlay` entries, and these before the `place` and `region` entries that name them. Names are folded to lower case; file names are kept as written.
- **Checks** (each a link error with a number, `lathe/host/README.md`): a window inside zero page or the stack's page, or overlapping `code`, `data`, `more` or another window (34); an unknown window, bank or overlay (42); a window, bank, overlay, module or region named twice (43); a `bank` in a window switched by `overlay` or the reverse, a bank number outside 1 to 255, an overlay without a file (3); a module placed in a bank without a file (51); a placed module that is not linked (44); code placed in two windows (50: the far-call modules and their tables serve one window); overlays not numbered 1 to N (52: `rt_ovl.load` indexes the table by the number); code placed with no `farcall` entry (54); the far-call module placed in a window (49); a far-call module that is not linked or lacks `call` or `start` (46). Not checked: that the `switch` register and mask are those `rt_bank` has as constants, that the far-call module suits the kind of switch, and that what `start` calls (`disk`) is fixed.
- **`region`** is read and checked (the window and bank must exist, a region is named once), and not yet used: that is step 9.
- **`more data FIRST LAST`.** With it, the frames are laid out first in `data`; then each variable not in zero page goes in `data` if it still fits there, and otherwise in `more`, in the order they are defined. Without it nothing changes: variables first, then the frames.
- **Stubs and the table** follow `$start` and `$init`, not the far-call routine: they are then at addresses known before any object is placed. The stubs are in the order of the functions, a function's copies together; the table follows them, then the file names. A function in a window has stubs if kept code outside its bank or overlay calls it, if kept code or kept constant data takes its address (including `@f` inside `f`), or if the start-up code calls it (`main`, or a module's `$init`, which `$init` calls through the stub after `start` has loaded the banks). Then **every** copy of it has a stub, so a stub's address is worked out from the function table and a count per object file; no table of stubs is kept. A copy for an interrupt context whose stub nothing uses costs 6 bytes.
- **The stub of a copy for context N** calls the copy of `FARCALL.call` for N, or the first copy if N makes no far call itself.
- **A call of a stub counts as a call of `FARCALL.call`**: the linker adds a call from every function that makes a far call to `call`, and from the block of every class with a member in a window (a call through the class may go through a stub), before the graph is built. `call` and `start` are roots of context 0. So `rt_ovl.load`'s slots are placed above the frame of any function that makes a far call.
- **Sizes.** A bank's or overlay's contents are judged for the fit check by their size **as written**, before any instruction shrinks, and with every variable that may go in the bank counted whether or not zero page took it (and a byte more for a word on an NMOS 6502, for the page rule). Zero page only makes code smaller and only takes variables out of the bank, so what is placed is never larger than what was judged: whether a program links cannot depend on what zero page promotion chose (`lathe/tests/test_lk_windows.py` links one program with two sizes of zero page, at the edge of fitting). The error says by how many bytes the judged size is over. Fixed code keeps the rule it had (its final size).
- **Constants and variables** of a module in a window (step 8) go in its bank by the rule below. A variable goes in a bank, never an overlay (an overlay is loaded again from its file, which would lose it). Constant data is placed with the code, in object order. Variables in a bank are placed at its top, going down, in the order they are defined; they are not in the bank's file, which ends with the last byte of code or constant data. A variable of the bank that zero page took is in zero page.
- **Files.** Each bank or overlay file is written in the directory of `OUT.bin`, by a reading of its own of the object files placed there, after the image: one output file is open at a time. `build.py` copies them beside the image, and `--run` puts them where the program reads them (the `--disk` directory, or the default machine's working directory).
- **The assembler path** (`lo2asm` and `asm/pyasm.py`) renders only programs linked all in one: `build.py --asm` with an environment that places code is an error. The identity check of the linker against the assembler path covers every all-in-one configuration, as before; with no window the linker's output is unchanged for every program.

### What the linker does

1. **Placement.** Each function gets the place of its module; each copy for an interrupt context too. Constant data and variables of a module in a window get its bank under the rule below; everything else is fixed.
2. **Which calls cross.** A reference crosses windows when it names a function in a window and the code that holds it is not in the same bank or overlay: a `CALL` record's call (`JSR`, or `JMP` for `return f(...)`), or a fix-up of kind 2, 3 or 5 that takes the function's address, or any fix-up in constant data. The linker points it at the function's stub. A `JMP` to a stub works: the stub's frame restores the bank of the code that jumped, one switch more than needed.
3. **Stubs.** One per copy of a function in a window that is called from outside its bank, whose address is taken anywhere, or that the start-up code calls. They are placed in fixed code after `$init`, in the order of the functions, and the table after them ("As built" above). A context copy has its own stub.
4. **Sizes.** The window's contents are placed from the window's first address, per bank, in object order. A bank whose contents do not fit is a link error saying by how many bytes, as for the other ranges. The fit is judged by the contents as written, before shrinking ("As built").
5. **Start-up.** `$start` sets the stack, then `LDA #<$banks` / `LDX #>$banks` / `JSR farcall.start` (or `$overlays`), before `$init`. `start` loads each bank's file (banks) or does nothing but set "no overlay" (overlays). The linker writes the table it reads, in fixed constant data (below, "The far-call run-time modules").
6. **Output.**

| Configuration | Files |
|---|---|
| All in one | One image, as now. |
| Banked | The fixed image (`output raw` or `image`, as now) and one file per bank that has a `FILE`: the bank's bytes from the window's first address to its last placed byte, nothing else. |
| Overlays | The fixed image and one file per overlay, the same raw form. |

   The raw form needs no load format: the window's address is in the environment and the program. A later machine whose loader wants a header (a Commodore `PRG`) gets it from an `output` option.
7. **The map.** F lines of a function in a window end with `b=N` (bank or overlay), and so do the D and V lines of constants and variables in a bank. New lines: `W FIRST SIZE N FILE` for each bank or overlay's contents (SIZE is the bytes of its file), after the F lines; `T ADDRESS 0006 name` for each stub, after the F line of its copy; and `D ADDRESS SIZE $banks` (or `$overlays`), the table with its names, after the line of `$init`. `size_report.py` and the tools that read F lines keep working: they read the first four fields.

### The far-call run-time modules

Built in step 3: `lathe/rt/rt_bank.lth` (Wendy 2's banks, files through `disk`) and `lathe/rt/rt_ovl.lth` (overlays, files through `host`, so the default machine only). `call` and `back` are the spike's instructions as `asm` functions, the same bytes and cycles: 101 bytes and 182 cycles a far call for banks, 107 bytes and 82 cycles for overlays (measured, `lathe/tests/test_farcall.py`). What the linker of steps 5 to 7 uses:

| Name | What it is |
|---|---|
| `farcall.call` | The entry of every stub's `JSR`. On entry the stack holds the stub's address + 2 (the JSR's return address) above the caller's return address; A, X, Y and the flags are the caller's arguments and go to the function as they are. It returns from the function to the caller with A, X and the carry as the function left them; Y and the other flags are lost. It is reached only from stubs, so the linker must keep it (and `back`, which `call` names) when it writes a stub. |
| `farcall.back` | Where a function entered through `call` returns to. Not called by anything else. |
| `farcall.start(table: ^byte)` | Called by `$start` with the table's address in A (low) and X (high), before `$init`. It must not use initial values: `rt_bank.start` uses only `disk.open`, `read`, `close` and `exit`, which need none. A bank or overlay file that cannot be opened stops the program with status 255. |
| `rt_bank.select(value: byte in a): byte in a` | Sets the bank bits and gives the old ones. For the `with` blocks of step 9 (`map` and `unmap` can be built on it); not used by the stubs. |
| `rt_ovl.load(n)`, `rt_ovl.loads()`, `rt_ovl.count` | Load overlay `n`; the number of loads so far. |

**The stub**, 6 bytes in fixed code: `$20` (JSR) and the address of `farcall.call`; one byte, the bank's register value (`bank` entry) or the overlay's number (1 to 255); one word, the function's address less one. Because `rt_ovl.call` calls `rt_ovl.load`, a Lathe function with slots, the linker must count a call of a stub as a call of `farcall.call` (a `CALL` record of the stub, or the same effect), so that `load`'s slots are not shared with a function that is active across the far call.

**The tables**, constant data in fixed memory, written by the linker:

```
$banks      .word WINDOW        ; the window's first address: where each file is loaded
            .byte N             ; the number of banks that have a file
            N times:
            .byte VALUE         ; the bank's register value ($11 for bank 1 of Wendy 2)
            .word NAME          ; the address of its file name, zero-terminated, fixed memory

$overlays   .word WINDOW        ; the window's first address: where an overlay is loaded
            .byte N             ; the number of overlays
            N times, overlay 1 first:
            .word NAME          ; the address of its file name
```

The window's address is in the table so that the module needs no constant from the environment. The bank register is not: `rt_bank` has Wendy 2's (`$F000`, bits `$1F`, keeping `$E0`) as constants, and the `switch WIN bank ADDR MASK` entry must name the same (the linker can check it; another board needs `#if` in `rt_bank`). `start` also makes the bank bits of port B outputs, since a program may start before anything has set the port's direction.

**How it is tested** (`lathe/tests/test_farcall.py`, with the linker's stubs and tables): spike L5's program in Lathe, `lathe/tests/cases/e2e-config/farcall.lth`, gives the spike's output banked on Wendy 2, in overlays on the default machine and all in one on both. Measured with the same objects linked all in one: a far call costs **182** cycles more than a call (banks), **82** while the overlay is in the window; the program makes **49** overlay loads, as the spike's did; `call` and `back` are 101 and 107 bytes, a stub 6, and a missing bank or overlay file stops the program with status 255. The whole program (29 far calls) takes 7,210 cycles all in one on Wendy 2 and 26,801 banked, of which 5,278 are the far calls and the rest the start-up's loading of 184 bytes; on the default machine 5,603 all in one and 262,160 with overlays, the 49 loads.

### Function addresses and pointer classes

- **`@f` of a function in a window is its stub's address**, wherever it is taken. A pointer is then good in any bank, and a call through it is an ordinary `JSR` to the caller's `JMP (pointer)`. A call through a pointer to a function in the caller's own bank pays a far call (spike: `ptr3`).
- **Class blocks** are slots, so fixed memory: arguments cross without help.
- **Copies for contexts** follow their module's place; each has its own stub if it needs one.

### Interrupts

- **An `interrupt` function is always fixed**: it is entered from the vector and ends in `RTI`, so it cannot be entered through a stub. A module that has one, and is placed in a window, is a link error naming the function.
- **What it calls may be in a bank**, because the bank routine is reentrant (spike: the timer test). It costs the handler 182 cycles a far call and 3 bytes of stack. The environment says the routine is reentrant by the kind `switch … bank`.
- **It must not reach an overlay**: the overlay loader is not reentrant, and loading a file in an interrupt is not acceptable. A link error names the handler and the function.
- **It must not use `with`** (code-model.md, "Data in windows", already says interrupt contexts must not use banked variables). This keeps the map routines simple; they are still safe if a handler far-calls while the main program is inside a `with` block, because the far call restores what it found.
- **An NMI handler** must not reach code in a window: the routine masks IRQ only. Lathe does not know which handler is the NMI's, so this is documented, not checked.

### Recursion

`rt_frame` is fixed, so a saving call's pushes and pops are plain calls. Recursion across banks works (spike: `rec`, 20 levels between two banks). Each level that crosses takes 5 bytes of the 6502's stack instead of 2, so the limit of about 120 levels (code-model.md) becomes about 50 if every level crosses. The compiler's own recursion is inside `expr`, one bank, so its levels do not cross; only the calls from `expr` to `gen` at the leaves do.

### Constants and variables of a module in a window

**The rule.** A constant table, a string or a module-level variable of a module whose code is in a window goes into the same bank **only if** every fix-up that names it is in that bank's code and none of them takes its address (kinds 2 and 3, or any fix-up in constant data). Otherwise it goes in fixed memory. The linker decides this from the fix-ups it already reads; the map says where each went.

- **Why.** A pointer to a string in bank 3, passed to a function in bank 5, points at bank 5's code by the time it is used. The rule makes that impossible without any check of types: anything whose address is taken is fixed. Fixed code called with a plain `JSR` from bank 3 could safely read bank 3's constants, but only until it makes a far call; the rule does not try to use that.
- **The cost for the compiler** is small: the host compiler's byte constants outside `err` and `lex` are about 750 bytes (gen 193, asmblock 465, decl 65, lathec 25); `lex` is fixed anyway. `err`'s messages (5,140 bytes, constants of a fixed module) are fixed under any rule unless declared `in MSGS` and read inside `with MSGS do … end` in `err`: a change to `err.lth`'s source, which the goals allow because banked data is explicit. The alternative in `architecture.md`, messages in a file read only when an error is reported, saves the same and needs the file system.
- **Frames are always fixed.** Slots are shared between functions in different banks.

### Changes to the object format

None for code in banks or overlays: the linker needs only `CALL` records and fix-ups, which it has. For banked data (version 3, with the `SYM` flag `architecture.md` already plans):

| Change | Why |
|---|---|
| `VAR` and `DATA`: flag bit 0 "in a region", followed by the region's name (string). | `in REGION`. |
| Fix-up kind 6: one byte, the register value of the region of the symbol named (a variable or constant data in the region), 0 if the region is fixed. | `LDA #bank(REGION)` in a `with` block. |
| `CALL` flag bit 2: the call is made inside a `with` block. | The check that no call there reaches a window. |

### The chained configuration

"Chained phases" can mean three things for this compiler:

1. **Compiler, linker pass 1, linker pass 2 as separate programs.** This is already so: the compiler writes object files and the linker reads them. Stage 8's linker in Lathe is a separate program. On a 64 KB machine with a disk and no banks this is the chained configuration, and nothing more is needed in the compiler for it.
2. **The compiler divided in time** (a tokenising program, then the rest; the fallback in `architecture.md`). It would take `lex` and `src` (2.5 KB) and the string buffer (2 KB) out of the second program, and leave about 56 KB of code with the expression parser, code generator and function buffer active together. That does not make the compiler fit a machine without banks, so it is not worth a program and a token file format.
3. **Overlays by module inside the compiler.** Placement D's 5.9 crossings a line would each cost two loads of a 20 KB overlay: about 1.7 million cycles a crossing, 10 million a line *(estimated from the measured 43 cycles a byte)*. Unusable. Overlays are useful only for code used rarely: `asmblock` (only at `asm` blocks), the interface writer, the start-up of `lathec`, the error messages.

**Plainly: with banks, chaining inside the compiler is pointless, and without banks it does not help enough.** On a machine with no banks, the compiler as projected (59 to 64 KB of code, 42 KB of tables) does not fit as one pass, however it is chained; that needs a smaller compiler, which is the owner's open decision after L4.

### Order of work

Each step ends in a test that fails before it and passes after. The first three need no compiler change and can run beside the work on stage 7.

| Step | Work | Test |
|---|---|---|
| 1 | `lathe/env/wendy2disk.env` (Wendy 2 with `--disk`), its board entry in `driver/boards.py` (passes `--disk` with a work directory, reads output from a file), a Wendy 2 `sys` over the `$F800` ports (`lathe/rt/disk.lth`: open, read with the carry at the end, write, close, the `args` file). | An end-to-end case that copies a file to another on Wendy 2. |
| 2 (done) | Environment version 2 in `lk_envf.py`: `window`, `switch`, `bank`, `overlay`, `place`, `region`, `more`, `farcall`, with their errors. | Link errors: overlapping window, unknown window, bank twice, `place` of a module not linked (`test_lk_windows.py`). |
| 3 | `lathe/rt/rt_bank.lth` and `rt_ovl.lth`: the spike's routines as `asm` functions, with `start` and the tables `$banks` / `$overlays`. | Unit tests on hand-built objects (as `test_boards.py` builds them) linked by hand: the spike's output, both machines. |
| 4 (done) | Linker: placement of a module's code in a bank; sizes per bank; the window files; the map's `b=`, `W` lines. No calls across yet. | A program whose only banked function is called from its own bank: runs on Wendy 2 (`tests/cases/e2e-config/inbank.lth`, which loads its bank itself); the map is as expected; a bank that overflows is a link error. |
| 5 (done) | Linker: stubs, calls redirected to them, `@f` as the stub, `$start` calling `farcall.start`. | The spike's three-module program written in Lathe (`tests/cases/e2e-config/farcall.lth`): nested calls, A/X/carry, recursion, pointers, a pointer class with members in two banks; the same objects linked all in one on Wendy 2 and on the default machine give the same output. |
| 6 (done) | Interrupt rules: an `interrupt` function in a window is an error; a handler reaching an overlay is an error; a handler reaching a bank works. | Two link-error cases; the spike's timer test in Lathe (`farirq.lth`). |
| 7 (done) | Overlays: the same program with `switch overlay`, on the default machine. | Same output; the number of loads is as computed (49). |
| 8 (done) | Constants and variables of a module in a window, by the rule above. | A constant used only by its bank's code lands in the bank (map); one whose address is taken lands in fixed memory; both run (`bankdata.lth`). |
| 9 | Banked data: `in REGION` and `with REGION do … end` in the compiler (host first); object format version 3; the linker's region placement and checks. | Error cases (use outside `with`; `with` in a function placed in a window; a call to a window inside `with`); an end-to-end case with a table in a data bank, linked banked and all in one. |
| 10 | The compiler's own placement: `kernel.names`, `fbuf.buffer` and `err`'s messages `in` regions, `lex` mapping around a whole name; `wendy2bank.env` as above. | The ten twins' test programs pass when linked banked on Wendy 2; the map shows at most 16 KB of resident code. |
| 11 | The gate of stage 11 (and of stage 7): the Lathe-written compiler, linked banked, compiles itself on Wendy 2 with `--disk`, and its objects equal the host compiler's. | The identity test, opt-in like `P1_WENDY_SELFHOST` if it is slow. |

## Decisions for the owner

| Decision | Recommendation |
|---|---|
| Change the emulator? | Not required. If yes, only the exit status of `$F80F` (about ten lines in `emu_wendy2c.c` and a chip test). |
| Placement D, with E as the fallback if bank 2 overflows. | Accept. It meets 16 KB with 2.5 KB to spare. |
| The 6-byte stub (182 cycles) against the 12-byte stub (130). | The 6-byte stub: about 530 bytes less resident (stubs and routine), about 300 cycles a line more. |
| `with REGION do … end` as the form of explicit banked data. | Accept, or name another word; `map` would clash with names already used (`libmaps.Map`). |
| Interrupt handlers may far-call into banks. | Allow (measured safe); forbid overlays and `with` in them. |
| Error messages: in a data bank (`in MSGS`) or in a file. | The data bank now, since Wendy 2 has banks to spare; the file when a machine without banks is a target. |
| Chaining inside the compiler. | Drop it. Chained means compiler and linker as separate programs. |

## Changes proposed to other documents

Made on 2026-11-14 for what steps 1 to 8 built (architecture.md, code-model.md, build-plan.md, boards.md); the parts about `with`, `in REGION` and object format version 3 wait for step 9. The text to put in:

- **`architecture.md`, "Configurations"**, the row **Chained**: "Compiler, linker pass 1 and linker pass 2 are separate programs run in order. They share nothing in memory; the files are the interface. The compiler itself is not divided further: banks make that pointless, and on a machine without banks it does not save enough ([`configurations.md`](configurations.md))." And replace the paragraph "If the front end alone exceeds…" with: "Dividing the front end in time was the fallback of L4; [`configurations.md`](configurations.md) shows it would save about 4.5 KB, not enough to matter."
- **`architecture.md`, "The environment description"**: replace the sketch for Wendy 2 by the `wendy2bank.env` above, and the table of entries by the one in "The environment file" here.
- **`code-model.md`, "Code in windows"**, add: "`@f` of a function in a window is the address of its stub, wherever it is taken. A constant or variable of a module in a window goes into its bank only if nothing outside the bank names it and nothing takes its address. An interrupt function is always fixed; what it calls may be in a bank, never in an overlay."
- **`code-model.md`, "Data in windows"**: replace "the program switches it in with a run-time call before use" by "the program uses it inside `with REGION do … end`, which maps the bank and maps back what was there".
- **`object-format.md`**: the three changes of version 3 above, under "Records" and "Fix-up kind".
- **`language.md`**: `with REGION do … end` under statements, and `in REGION` described under declarations; `with` added to the keywords.
- **`build-plan.md`, stage 11**: "Spike first: L5 (done)." and the order of work above as its steps; the open item on compiler size can point here for the banked configuration.
- **`boards.md`, Wendy 2**: a paragraph on `--disk DIR` and the `$F800` ports, and the environment `wendy2disk.env`.
