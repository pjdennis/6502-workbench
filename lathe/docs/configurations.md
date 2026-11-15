# Lathe: configurations (stage 11)

Status (2026-11-14): design, after spike L5, and steps 1 to 10 of the order of work built: the spike in `lathe/tests/spike_l5/`; files on Wendy 2 (section 1), the far-call run-time modules, the linker's side, which links the same object files all in one, with code in banks on Wendy 2, or with code in overlays on the default machine (section 5, "As built"); banked data, `in REGION` and `with REGION do … end` ("As built: banked data"; the form is provisional, 2026-11-14, awaiting the owner's agreement); and the compiler's own placement with its big tables in data banks at full size ("Step 10: the tables in data banks"). The gate of step 11 is met: the Lathe-written compiler, banked on Wendy 2 at full capacities, compiles its own sixteen modules and `sys` byte-identically to the host compiler (`test_src_selfhost.py`). Every number is marked **measured** (by a program in this repository, named) or **estimated** (worked out from measured numbers, with the method given).

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

**Built (step 1).** `lathe/rt/disk.lth` does all of the above over the ports, with the functions of `host.lth` that `sys.lth` uses under the same names and types (`open`, `open_out`, `close`, `read`, `write`, `argc`, `argv`, `put_byte`, `put_error`, `exit`); it has no `read_byte`, because there is no standard input. `boards.md`, "Wendy 2 with files", has the recipe; `lathe/src/sys.lth` chooses between `disk` and `host` with `#if PORTS` (every environment that compiles it defines `PORTS`, 1 for the file ports, 0 for the host services; not `DISK`, which names the module once it is imported), and `lathe/tests/test_disk.py` runs it on Wendy 2. `sys` uses no standard input on either machine, so `disk`'s lack of `read_byte` costs nothing.

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

Goal 11's non-goal: banked data is explicit. Two additions, built in step 9 ("As built: banked data", below, says where what follows was changed; the form is provisional, 2026-11-14, awaiting the owner's agreement):

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
| `switch NAME bank farcall` | The window is switched by banks, but no register and mask describe how: the far-call module alone turns a bank's value into the switch (added 2026-11-14 for the BBC, whose `rt_bbc` writes a slot to `$F4` and ROMSEL and, for a bank of the module, reads `$BFF0+n`; [`bbc.md`](bbc.md)). The linker treats it as `bank` in every other way. |
| `bank NAME N VALUE [FILE]` | Bank `N` (1 to 255) of the window: the register value, and the file the linker writes with its contents. Without a file the bank holds only data that code sets up. |
| `rom NAME N` | Bank `N` of the window is read-only: code and constant data, never a variable; its file is written but start-up does not load it (added 2026-11-14: "Functions kept in fixed memory, and read-only banks", below). |
| `overlay NAME N FILE` | Overlay `N` of the window and its file. |
| `place MODULE NAME N` | The module's code goes in bank or overlay `N`. A module not placed is fixed. By module only: a module is the unit the call structure is known by, and placing functions one by one would need names in the environment that the source can change. |
| `region REGION NAME N` | The data region `REGION` is bank `N` of the window. `region REGION fixed` (or no entry) puts it in fixed data memory. |
| `more data FIRST LAST` | A second range for variables, used when the first is full. |
| `farcall MODULE` | The run-time module that the stubs and `with` blocks call: `rt_bank`, `rt_ovl` or `rt_bbc`, in `lathe/rt/`. The build adds it as it adds `rt_frame`. |

The compiler reads none of these (it reads `cpu` and `define` only), so an object file is the same in every configuration (`lathe/tests/cases/e2e-config/farcall.lth` checks it: the program's modules are the same bytes in four configurations, but for the CPU byte of the `MOD` record where a 6502 configuration is compared with a 65C02 one).

**As built** (steps 2 and 4 to 8; `lathe/host/lk_envf.py`, `lk_win.py`; the decisions this section left open):

- **The order of entries.** A window comes before its `switch`, the switch before its `bank` or `overlay` entries, and these before the `place` and `region` entries that name them. Names are folded to lower case; file names are kept as written.
- **Checks** (each a link error with a number, `lathe/host/README.md`): a window inside zero page or the stack's page, or overlapping `code`, `data`, `more` or another window (34); an unknown window, bank or overlay (42); a window, bank, overlay, module or region named twice (43); a `bank` in a window switched by `overlay` or the reverse, a bank number outside 1 to 255, an overlay without a file (3); a module placed in a bank without a file (51); a placed module that is not linked (44); code placed in two windows (50: the far-call modules and their tables serve one window); overlays not numbered 1 to N (52: `rt_ovl.load` indexes the table by the number); code placed with no `farcall` entry (54); the far-call module placed in a window (49); a far-call module that is not linked or lacks `call` or `start` (46). Not checked: that the `switch` register and mask are those `rt_bank` has as constants (`bank farcall` has none), that the far-call module suits the kind of switch, and that what `start` calls (`disk`) is fixed.
- **`region`** is read and checked (the window and bank must exist, a region is named once), and used since step 9 ("As built: banked data").
- **`more data FIRST LAST`.** With it, the frames are laid out first in `data`; then each variable not in zero page goes in `data` if it still fits there, and otherwise in `more`, in the order they are defined. Without it nothing changes: variables first, then the frames.
- **Stubs and the table** follow `$start` and `$init`, not the far-call routine: they are then at addresses known before any object is placed. The stubs are in the order of the functions, a function's copies together; the table follows them, then the file names. A function in a window has stubs if kept code outside its bank or overlay calls it, if kept code or kept constant data takes its address (including `@f` inside `f`), or if the start-up code calls it (`main`, or a module's `$init`, which `$init` calls through the stub after `start` has loaded the banks). Then **every** copy of it has a stub, so a stub's address is worked out from the function table and a count per object file; no table of stubs is kept. A copy for an interrupt context whose stub nothing uses costs 6 bytes.
- **The stub of a copy for context N** calls the copy of `FARCALL.call` for N, or the first copy if N makes no far call itself.
- **A call of a stub counts as a call of `FARCALL.call`**: the linker adds a call from every function that makes a far call to `call`, and from the block of every class with a member in a window (a call through the class may go through a stub), before the graph is built. `call` and `start` are roots of context 0. So `rt_ovl.load`'s slots are placed above the frame of any function that makes a far call.
- **Sizes.** A bank's or overlay's contents are judged for the fit check by their size **as written**, before any instruction shrinks, and with every variable that may go in the bank counted whether or not zero page took it (and a byte more for a word on an NMOS 6502, for the page rule). Zero page only makes code smaller and only takes variables out of the bank, so what is placed is never larger than what was judged: whether a program links cannot depend on what zero page promotion chose (`lathe/tests/test_lk_windows.py` links one program with two sizes of zero page, at the edge of fitting). The error says by how many bytes the judged size is over. Fixed code keeps the rule it had (its final size).
- **Constants and variables** of a module in a window (step 8) go in its bank by the rule below. A variable goes in a bank, never an overlay (an overlay is loaded again from its file, which would lose it). Constant data is placed with the code, in object order. Variables in a bank are placed at its top, going down, in the order they are defined; they are not in the bank's file, which ends with the last byte of code or constant data. A variable of the bank that zero page took is in zero page.
- **Files.** Each bank or overlay file is written in the directory of `OUT.bin`, by a reading of its own of the object files placed there, after the image: one output file is open at a time. `build.py` copies them beside the image, and `--run` puts them where the program reads them (the `--disk` directory, or the default machine's working directory).
- **The assembler path** (`lo2asm` and `asm/pyasm.py`) renders only programs linked all in one: `build.py --asm` with an environment that places code is an error. The identity check of the linker against the assembler path covers every all-in-one configuration, as before; with no window the linker's output is unchanged for every program.

**As built: banked data** (step 9, 2026-11-14; provisional form). Where the design above was silent or wrong:

- **Declarations.** `in REGION` goes on a variable of the module, a `static` variable and a constant table or string (`const NAME: T in REGION = …`). Not with `zp` or `at`, not on a local or a number constant, and no initial value (error 182): setting one inside a mapping in `$init` was the larger choice. A variable in a region is never in zero page (class 2), so whether a program links cannot depend on promotion.
- **The rule of use** is in the compiler: a name of a region, used or with its address taken anywhere (expressions, `asm` operands, inline expansions), must be inside a `with` block of its region, and the innermost block decides (error 118). The check is at `reg.object_symbol`, the one place every use of a variable or table goes through.
- **Nesting.** A block inside a block of the same region is free: no code. A block of another region maps its bank; inside it only that region's names can be used, which is what one window allows. Leaving several blocks by `return`, `break` or `continue` unmaps once, with the temporary of the outermost block left (of the function, or inside the nearest loop): it holds the bank found before all of them.
- **The bank symbol.** `LDA #bank` names the first variable or table of the region the block uses (the fbuf entry is filled in at the block's end), or if it uses none, the first the module declares (`expr.region_symbol`); a block with neither is error 184. (Until 2026-11-14 a block that used none was error 183, now retired: the linker learns a bank only from a variable or table of the region, but any the module declares will do.)
- **map and unmap.** The compiler calls `rt_with.map` and `rt_with.unmap` and writes an `IMP` record of `rt_with`. With a `farcall MODULE` entry, the linker reads every name `rt_with.X` as `MODULE.X` (`lk_name.rename_farcall`, and the hash in `mark_object`), and `build.py` compiles MODULE for the `IMP`; with none, `build.py` links `lathe/rt/rt_with.lth`, two lone `RTS`. So the object files are the same in every configuration, and the stage A text path renders all-in-one links unchanged (kind 6 is `#$00`). `rt_bank.map` is `JMP select`; `rt_bank.unmap` takes the bank in Y and keeps A, X, Y and the flags, so a result and a status pass through a `return`. `rt_ovl.map` and `unmap` are lone `RTS`: a region cannot be in an overlay.
- **Placement.** A region's constants go in its bank from the window's first address, in object order with the bank's code; its variables at the bank's top going down, as a placed module's (step 8). The fit is judged as for code banks. A bank that holds constants of a region must have a file, which start-up loads (link error 59); a bank of variables only needs none, and the map shows it as `W 8000 0000 N -`. A region bank may also hold code: code in it can never name the region (only fixed functions have `with` blocks), and code that runs inside a block is all fixed (below).
- **Without placed code.** A program with something in a region in a bank uses the far-call module even if no code is placed: `lk_envf.placed()` is true, start-up calls `start` to load bank files, and `call` and `back` are kept though nothing calls them (about 100 bytes; `lk_graph` roots them).
- **Checks** (link errors): until 2026-11-14 a function with a `with` block (a kind 6 fix-up, `lk_tab.F_WITH`) placed in a window (55) and a call flagged inside a block that reaches a function in a window (56); both are retired, because such functions are now kept in fixed memory ("Functions kept in fixed memory, and read-only banks", below); an interrupt context that reaches a function with a `with` block (57), and `with` in an interrupt function is a compile error (119), a conservative rule: the routines would be safe there; a region in an overlay, or in another window than code or another region (58); a region in a bank with no `farcall` entry (54); overflow (45).
- **Interfaces** carry `in REGION`: a variable's placement byte 8 and the region's name, and a constant table as entry kind 9 (`lathe/host/README.md`).
- **Inline.** `with` cannot be in an inline function: `lathe/host/inline.py` counts it as opening a block and refuses it when it saves a body, with `asm`, `static` and `#if` (error 168, `cases/err/inline_with.lth`). A body without `with` that uses a region expands inside a caller's block.
- **Costs** (measured, `with` as a function's last statement, 200 calls): all in one 24 cycles and 12 bytes a block (14 with the temporary in main memory), banked on Wendy 2 90 cycles; about 9 cycles more where the block is not last (estimated: `JSR` and `RTS` instead of the tail call's `JMP`).

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

Built in step 3: `lathe/rt/rt_bank.lth` (Wendy 2's banks, files through `disk`) and `lathe/rt/rt_ovl.lth` (overlays, files through `host`, so the default machine only); in stage 12 a third, `lathe/rt/rt_bbc.lth`, for the BBC Model B+128 (below, "The third: rt_bbc"). `call` and `back` are the spike's instructions as `asm` functions, the same bytes and cycles: 101 bytes and 182 cycles a far call for banks, 107 bytes and 82 cycles for overlays (measured, `lathe/tests/test_farcall.py`). What the linker of steps 5 to 7 uses:

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

### The third: rt_bbc

`lathe/rt/rt_bbc.lth` (stage 12, step 3; [`bbc.md`](bbc.md), "Step 3, as built"): the same interface (`call`, `back`, `start`, `select`, `map`, `unmap`) and the same stub and table, for the BBC Model B+128's one window, `$8000-$BFDF`, with `switch WIN bank farcall` and `farcall rt_bbc` (`lathe/env/bbc-bank.env`). NMOS instructions only.

- **A bank's value** is `$80 + n` for bank n of the module (sixteen, scheme `direct16`) and s for sideways slot s. A slot is selected by writing it to `$F4` (the MOS's copy) and then to ROMSEL (`$FE30`); a bank of the module by selecting the module's slot so and reading `$BFF0+n`, written `LDA $BF70,Y` with the value in Y, so that no `AND` is needed.
- **What is in the window** cannot be read back (ROMSEL is write only, the latch has no read), so the variable `now` holds its value, set before each switch. `call` pushes it and `back` selects it again, as `rt_bank` pushes and restores the port's bits: nested and recursive far calls, and far calls from a handler, are safe. `map` gives it and `unmap` selects it again.
- **The latch is not on the stack.** A slot's value says nothing of the bank the module holds while the slot is in the window. It need not: whatever puts the module back in the window (`back`, `unmap`) latches the bank its own value names. So `unmap` of a block entered from code in a bank reads the latch address again, because a far call made while the block's slot is mapped leaves the latch elsewhere. Since kept functions ("Functions kept in fixed memory") nothing a call inside a block reaches is in a bank, so in compiled code that far call is an interrupt handler's; but a handler may make one. Putting back only the slot, as first designed, is unsound; `test_bbc_bank.py` makes such a call through an address taken in asm (the emulator's BBC has no interrupts) and shows it.
- **Interrupts.** `call` and `back` disable them, for their saved registers, as `rt_bank`'s do. `map` and `unmap` need not: `now` is set first, so a handler's far call that comes between the writes pushes the new value and puts all of it back.
- **The module's slot** is the variable `mslot`, which `start` sets: from the environment's `define MODULE_SLOT` (rt_bbc's `SLOT`) for a program run with `*RUN`, from the stub of the module's bank 0 (`$07F4`, the slot the MOS gave the service call) in the ROM form, where `start` loads nothing ([`bbc.md`](bbc.md), "Step 3, as built: the ROM form").
- **start** loads each bank's file through `bbc.lth`'s `open`, `read` and `close`, into the module or a sideways slot, and leaves the window as the program found it.
- **Costs** (measured, `lathe/tests/test_bbc_bank.py`, as `test_farcall.py` measures Wendy 2's): a far call from fixed code into a bank **187** cycles more than a call (Wendy 2: 182), between two banks of the module 197; a `with` block as the function's last statement **64** cycles entered from fixed code and 79 from a bank (186, 195 and 78 before the slot was a variable), against 24 all in one (Wendy 2: 90). `call` and `back` are 136 bytes with their variables in zero page, as in `farcall.lth` (`rt_bank`'s 101), and 156 where zero page has no room for them, as in `gentest` (154 with the slot a constant): each switch has two paths, a slot and a bank of the module, and each path its own copy of the code that follows, so that neither jumps.

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

**The rule.** A constant table, a string or a module-level variable of a module whose code is in a window goes into the same bank **only if** every fix-up that names it is in that bank's code and none of them takes its address (kinds 2 and 3, or any fix-up in constant data). Otherwise it goes in fixed memory. The linker decides this from the fix-ups it already reads; the map says where each went. Since object format version 4 (2026-11-14) an address the code forms only to reach an element, to index a table of more than 256 bytes by a word, a row of a `rows` array or an element of a large array field of a record, is fix-up kinds 7 and 8, not 2 and 3, and does not count as taken: such a table follows its module into the bank too. A function kept in fixed memory (since 2026-11-14, "Functions kept in fixed memory, and read-only banks") is not in that bank's code, so what it names is fixed; a variable is never in a read-only bank.

**Why kinds 7 and 8 are safe.** The compiler writes them only in `gen.element_pointer`, which adds the index to the address in a zero page temporary of the function and reads or writes the element through it with `(zp),Y` in the same expression; the address is not stored anywhere else, passed or returned. `@t[i]` is the one way to keep it, and the compiler knows it is being parsed (`gen.address_of`, set by the `@` of `expr.factor` for its own designator only, not for the index expressions inside it): that address escapes and is kinds 2 and 3, as `@t` always was. So the address is used only while the function that formed it runs, and:

- **Which bank is mapped then.** The function's own: a function in a window runs only with its bank mapped, a far call it makes returns with that bank mapped again, and an interrupt that far-calls puts back the bank it found. The table is in that bank by the rule's first half (every fix-up naming it is in that bank's code).
- **`with` blocks** are never in a function in a window: a function with one is kept in fixed memory, and so is every function that runs inside one ("Functions kept in fixed memory"). So no block can map another bank between forming the address and using it, and a kept function's own kind 7 or 8 fix-up keeps the table fixed, since the kept function is not in its module's bank.
- **Inline functions exported to other modules.** The fix-up is written in the function the body is expanded in, so the rule judges the expander's bank: expanded in fixed code or in another bank, the table is fixed, as before.
- **Interrupt functions** are fixed, so a kind 7 or 8 fix-up of one makes the table fixed; one in a function an interrupt context calls is in that function's bank, as above.
- **`asm` blocks** stay conservative: `#<t` and `#>t` written in an `asm` block are kinds 2 and 3, whatever the code does with them.
- **Data in a region** is placed by its region, never by this rule; a block maps its bank for the whole block, and error 118 keeps every use inside one.
- **A local array** (a slot) can be indexed by a word too: kinds 7 and 8 then name a slot, and frames are always fixed.
- **Copies for contexts** of a function are in its bank, so they read the same copy of the table.

- **Why.** A pointer to a string in bank 3, passed to a function in bank 5, points at bank 5's code by the time it is used. The rule makes that impossible without any check of types: anything whose address is taken is fixed. Fixed code called with a plain `JSR` from bank 3 could safely read bank 3's constants, but only until it makes a far call; the rule does not try to use that.
- **The cost for the compiler** is small: the host compiler's byte constants outside `err` and `lex` are about 750 bytes (gen 193, asmblock 465, decl 65, lathec 25); `lex` is fixed anyway. `err`'s messages (5,140 bytes, constants of a fixed module) are fixed under any rule unless declared `in MSGS` and read inside `with MSGS do … end` in `err`: a change to `err.lth`'s source, which the goals allow because banked data is explicit. The alternative in `architecture.md`, messages in a file read only when an error is reported, saves the same and needs the file system.
- **Frames are always fixed.** Slots are shared between functions in different banks.

### Changes to the object format

None for code in banks or overlays: the linker needs only `CALL` records and fix-ups, which it has. For banked data (version 3; as built, the first row is a `RGN` record before the `VAR` or `DATA` record instead of a flag, because `DATA` has no flag byte: [`object-format.md`](object-format.md)):

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
| 9 (done) | Banked data: `in REGION` and `with REGION do … end` in the compiler (host first); object format version 3; the linker's region placement and checks. | Error cases (use outside `with`; `with` in a function placed in a window; a call to a window inside `with`); an end-to-end case with a table in a data bank, linked banked and all in one (`regions.lth`, `withirq.lth`). |
| 10 (done) | The compiler's own placement: `kernel.names`, `fbuf.buffer` and `err`'s messages `in` regions, `lex` mapping around a whole name; `wendy2bank.env` as above. | The ten twins' test programs pass when linked banked on Wendy 2; the map shows at most 16 KB of resident code. |
| 11 (done) | The gate of stage 11 (and of stage 7): the Lathe-written compiler, linked banked, compiles itself on Wendy 2 with `--disk`, and its objects equal the host compiler's. | The identity test, opt-in like `P1_WENDY_SELFHOST` if it is slow. |

Step 10's code half is done ahead of step 9 (below): the test programs of `outtest`, `regtest`, `condtest` and `gentest` run banked on Wendy 2 with the small tables, all in fixed memory.

## Measured on the compiler's test programs

Measured 2026-11-14 by `lathe/tests/bank_report.py` (maps and emulator runs) on the four test programs that hold code generation, built by `src_support.build_banked` with `lathe/src/compiler-bank.env`, and checked against the Python twins section by section by `lathe/tests/test_src_banked.py` (`lathe/host/README.md`, "The banked build"). The first banked link of anything large, about 38 KB of code.

**The placement.** Fixed: err, kernel, src, lex, typetab, fold, fbuf, sys, disk, rt_bank, rt_math (and rt_frame where linked). Bank 1, the front end's place: the test drivers, `script`, `listing`, `regcmd` and the test's main module; they call down into banks 2 and 3 and into fixed memory, and nothing below calls them, as will be true of `lathec`, `decl` and `expr`. Bank 2: gen, reg, out. Bank 3: cond. That is **placement E, not D**: with cond in bank 2, gentest's bank 2 is judged 1,437 bytes over 28 KB (link error 45). As placed it would hold 25,795 bytes (gen, reg, out and cond: 23,824 of code and constants, 1,971 of variables), but the linker judges a bank by its contents as written, before zero page shrinks them ("As built", "Sizes"), and for these modules that is 30,109 bytes: 4,314 more (17%). And `gen` measures 12,322 bytes of code, above the 12,117 that section 3 estimated at most. So bank 2 with cond in it does not fit, now or later, unless the judged size comes closer to the placed one.

**What `gentest` takes** (the largest; the small tables):

| | Bytes | |
|---|---|---|
| resident code | 10,108 | measured: err 464, kernel 3,041, fbuf 3,158, fold 1,299, typetab 812, sys 190, disk 485, rt_bank 303, rt_math 310, `$start` and `$init` 46 |
| stubs | 864 | 144 stubs |
| resident code and stubs | **10,972** | against the 16 KB goal and section 3's 13,862 for the whole compiler, which counts 2,530 of lex and src that gentest does not link, and 96 stubs |
| resident constants | 6,194 | 4,882 of them err's messages, 943 the command words of two drivers (their address is taken, so fixed) |
| fixed variables and slots | 13,025 | `$0200-$34E0` |
| free fixed memory | 4,091 | 1,311 below the code (`$3A00`), 754 above it, 2,026 at `$F810-$FFF9` (the `more` range, unused) |
| bank 1 | 4,585 file, 250 variables | gentest, script, listing, regcmd |
| bank 2 | 21,371 file, 1,970 variables | gen, reg, out |
| bank 3 | 2,453 file, 1 variable | cond |

The other three: resident code and stubs 8,831 (regtest, 69 stubs), 9,025 (condtest, 80), 7,036 (outtest, 21); their banks 2 hold 7,821 (reg, out) and 2,128 bytes (out).

**Stubs.** 144, against the 96 estimated for the whole compiler. The drivers in bank 1 call many more functions of reg, gen and out than the host's front end does (`regcmd` reaches most of reg), and every copy of a function in a bank gets a stub when one does. The front end's own count will be known when `expr` and `decl` are linked.

**Far calls and cycles, all 113 sections of `gen.txt`** (each section a run of its own, the banks loaded again each time):

| Build | CPU cycles |
|---|---|
| all in one, default machine (`compiler-small.env`) | 42,793,503 |
| all in one, Wendy 2 (`compiler-bank.env` without its window entries) | 44,038,227 |
| banked, Wendy 2 | 269,839,982 |

- **3,460 far calls** in all, counted by a copy of `rt_bank.call` that adds to a counter (`bank_report.py`): 30 a section, 141 at most. At 182 cycles they cost 629,720 cycles, 1.4% of the all-in-one run.
- **Loading the banks at start-up**: 28,409 bytes in 1,991,131 cycles, **70 cycles a byte** (an empty script banked, less the same all in one on Wendy 2, less its 12 far calls). That is 225 million of the 270 million cycles: the tests pay it 113 times, a compile once.
- What is left, 803,952 cycles less the far calls' 629,720, is the difference of layout: the banked link puts other variables in zero page. In `regtest` (46 sections of `reg.txt`, 1,043 far calls) the remainder is 189,444 cycles against 189,826 for the far calls, so the count and the cost agree.
- `condtest`, 20 sections of `cond.txt`: 1,270 far calls; `outtest`, 9 sections of `out.txt`: 232.

**What the first large banked link showed.**

- **No fault** in the linker's stubs, placement, data of banked modules or context copies, in `rt_bank` or in `disk`: every section of the four scripts gave the Python's output the first time it ran.
- **The judged size is the limit, not the placed size** (above). Placement D needs either cond out of bank 2 (E, as built) or a judged size closer to the placed one.
- **`place` of a module the program does not link is an error** (44), so one environment cannot serve programs that link different parts of the compiler. The test harness writes an environment for each program, without the `place` lines of modules it does not link and with one for its main module. The compiler itself links all its modules, so `wendy2bank.env` is not affected.
- **A bank with a file and nothing placed** in it (bank 3 of `regtest`) gets an empty file, which `start` opens and loads: harmless.
- **Fixed memory is the constraint**, as section 4 foresaw. At the small capacities gentest leaves 4 KB; `lex` and `src` will take 2.5 KB of it, and the full-size tables cannot fit until the data bank of step 9 takes `kernel.names` and `fbuf.buffer`. The `outtest` sections that test a full table of 2,048 bytes (out.txt sections 3 to 6) give error 87 banked, as the Python does at the small capacities: they are compared, but they test the small limit.
- **`#if` in an `inline` function is error 168**, so `sys`'s choice of `disk` or `host` writes each inline function twice, whole.

**`exprtest`, the test of `expr.lth`** (measured 2026-11-14 by `bank_report.py --program exprtest --script expr`, 165 sections), the first program that links the front end's code: EXPR and INLINE in bank 1 with the drivers, ASMBLOCK in bank 3 beside COND, and LEX and SRC fixed. It has about 68 KB of code as written and cannot be built all in one on either machine.

| | Bytes | |
|---|---|---|
| resident code | 13,848 | gentest's 10,108, and lex 2,234, src 377 |
| stubs | 906 | 151 stubs |
| resident constants | 6,284 | 4,926 of them err's messages |
| resident code, stubs and constants but the messages | **16,112** | under the 16 KB goal by 272 bytes |
| free fixed memory | 272 | 28 below the code (`$2D80`), 82 above it, 162 at `$F810-$FFF9`: the small build's capacities had to come down to fit (text memory 1,280 to 896, name heap 1,024 to 768, labels 192 to 128, weights 64 to 32, types 64 to 32) |
| bank 1 | 23,782 file, 887 variables | exprtest, script, listing, regcmd, **expr 15,207**, inlines 3,680 |
| bank 2 | 22,231 file, 1,987 variables | gen, reg, out |
| bank 3 | 6,589 file, 565 variables | cond, asmblock |

- **Far calls**: 12,449 in the 165 sections, 75 a section, 758 at most (section 8, `for` loops): EXPR calls GEN and REG in bank 2 at every operand, and ASMBLOCK in bank 3 calls REG back. The start-up of an empty script takes 3.8 million cycles, 14 far calls.
- **What `decl` and `lathec` needed** (estimated here before they were written: about 29 KB for bank 1 with expr and inlines) is in "The compiler itself, banked", below: `inlines` moved to bank 3 when `with` made `expr` larger, and `decl` and `out` went to a fifth bank.
- **The cost of recursion** (`docs/code-model.md`, "Recursion"): 45 of `expr.lth`'s 77 functions are `recursive`; their saving calls push 482 bytes in all and cost about 5,800 bytes of code, a third of the module. At run time a level of parentheses takes 12 bytes of the 6502's stack and none of rt_frame's; the arguments of a call about 20 and 28; an inline expansion about 26 and 23; a `for` 6 and 20. `expr.MAX_NESTING` (16 levels, error 88) keeps both stacks within their 256 bytes; measured past the limit, the twin still gets through 16 parentheses inside each other (18 levels) and 8 calls inside each other's arguments (18 levels), and overflows a stack at 20 parentheses and at 10 calls, so the limit leaves about two levels to spare.

## The compiler itself, banked

Measured 2026-11-14 by `lathe/tests/bank_report.py --compile` on `lathe/src/lathec.lth`, the compiler's main module, which links the twins of all sixteen host modules, built by `src_support.build_banked` with `lathe/src/compiler-bank.env` (the small build's tables, `SMALL 1`), and tested by `lathe/tests/test_src_lathec.py`, which runs it on the corpus against the host compiler at the same capacities (`lathe/host/README.md`, "The compiler in Lathe").

**The placement.** Fixed: err, kernel, src, lex, typetab, fbuf, sys, disk, rt_bank, rt_math, rt_frame. Bank 1: lathec and expr. Bank 2: gen and reg. Bank 3: cond, asmblock, inlines and fold. Bank 5: decl and out. Placement D with E's cond, as the test programs had it, does not link: decl and lathec in bank 1 beside expr and inlines judge it 1,413 bytes over 28 KB; with inlines in bank 3 and decl there too, bank 2 (gen, reg, out) is judged 259 bytes over, because the whole compiler keeps functions of reg and out that no test program does; with out in bank 3 as well, bank 3 is 571 over. So a fifth bank holds decl and out. It is bank 5 because bank 4 is the data bank that step 10 is to fill (`region NAMES WIN 4`). DECL calls EXPR (bank 1) once a declaration or a function body, and GEN calls OUT (bank 5) for each symbol, call and fix-up record: both are far calls now.

| | Bytes | |
|---|---|---|
| resident code | 13,234 | err, kernel, src, lex, typetab, fbuf, sys, disk, rt_bank, rt_math, rt_frame, `$start` and `$init` |
| stubs | 1,062 | 177 stubs, against 96 estimated in section 3 and 151 for exprtest |
| resident constants | 5,975 | 5,256 of them err's messages |
| resident code, stubs and constants but the messages | **15,015** | under the 16 KB goal by 1,369 bytes |
| free fixed memory | 1,468 | 1 below the code (`$3080`), 81 above it, 1,386 at `$F810-$FFF9` |
| bank 1 | 17,706 file, 419 variables | lathec, expr |
| bank 2 | 20,371 file, 2,438 variables | gen, reg |
| bank 3 | 12,645 file, 771 variables | cond, asmblock, inlines, fold |
| bank 5 | 10,877 file, 1,033 variables | decl, out |

In all 74,092 bytes of code, 72,653 of them the sixteen modules (`size_report.py --report`; `spikes.md`, "L4 revised").

**Compiling** (each run loads the 61,599 bytes of the four bank files first; the far calls are counted by the counting copy of `rt_bank`):

| Input | Lines | CPU cycles | Far calls | |
|---|---|---|---|---|
| the start-up alone (a command line that stops at error 61) | | 4,460,076 | 12 | loading the banks, about 70 cycles a byte |
| `cases/snap/compare.lth` | 182 | 8,089,856 | 1,382 | 7.6 a line; 251,524 cycles, 3 % of the run |
| `cases/snap/for_loops.lth` | 128 | 7,875,117 | 1,383 | 10.8 a line |
| `cases/snap/case_of.lth` | 120 | 6,421,863 | 603 | 5.0 a line |
| `lathe/rt/rt_math.lth` | 370 | 9,952,878 | 904 | 2.4 a line: mostly `asm` |

Beyond the start-up, compiling takes about 20,000 cycles a source line of ordinary code (compare.lth: 3.6 million cycles for 182 lines), and the far calls 3 % of it: about 8 a line where EXPR, GEN and REG work together, against the 6 that spike L5 estimated.

**What it compiles.** Every input of `test_src_lathec.py` gives the host compiler's status, output, error output and files, byte for byte: 681 inputs (the 632 modules of the corpus and 49 made for what the corpus lacks: command lines, damaged interfaces, each capacity of the small build). With the small build's tables (name heap 1,536 bytes, 264 symbols, a function buffer of 1,024, text memory of 896), 393 of 395 error cases, 89 of 116 end-to-end modules, 55 of 56 snapshot cases and all 11 run-time modules fit; of the 54 modules of `lathe/src/`, 2 do (`sys`, `lk_op`): 47 stop at the name heap (error 70) and 5 at the text memory (82), whose arguments and the file names of imported inline functions leave too little beside the 384 bytes of saved tokens and the 256 of the path. Those that do not fit stop at the same capacity error, at the same place, on both. The tables at full size are 50 KB: they fit since step 10 put the name heap, the function buffer, the string, the saved tokens and the messages in data banks ("Step 10: the tables in data banks, and the compiler compiling itself", below).

## Step 10: the tables in data banks, and the compiler compiling itself

Built and measured 2026-11-14. `lathe/src/compiler-bank.env` now defines `SMALL 0`: the banked compiler and its test programs have the full capacities (`test_src_banked.py` checks each table's size in the map against the host's).

**What is in which region, and why.**

| Region | Bank | What | Bytes | Used inside blocks of |
|---|---|---|---|---|
| `NAMES` | 4, variables only (no file) | `kernel.names`, the name heap | 18,944 | kernel; LEX's block around a name (`kernel.name_put`, an exported inline function) |
| `MSGS` | 6, its file loaded at start-up | `err.MESSAGES_1` to `_3`: the texts as three strings of lines (a string holds 2,048 bytes; the strings of a table in a region are not in it, so a table of 127 strings would have left the texts fixed) | 5,259 | `err.fatal_start` |
| `FUNCBUF` | 6 | `fbuf.buffer`, `label_offset`, `label_uses` | 4,864 | fbuf |
| `STRING` | 6 | `lex.string` | 2,048 | lex (`lex.string_byte()` for EXPR and INLINE) |
| `TOKENS` | 6 | `kernel.tokens`, INLINE's saved tokens, out of the text memory | 2,048 | kernel (`token_byte`, `set_token_byte`, and `get` on a memory stream) |

Names have a bank of their own because they are the table that grows: the heap went from 17,920 to 18,944 bytes in this step (`expr.lth` needs 18,122 with the names this step exports, measured by `memory_report.py --corpus`), and bank 4 can take it to 28 KB. Everything else shares bank 6 (14,219 bytes), which then needs a file for the messages. Nothing copies between regions, so two banks cost nothing but one more file: a block of another region inside a block only happens through calls (`err.fatal` inside an FBUF block; `src.next_byte`, which maps TOKENS, inside LEX's STRING block for a saved string), and those map their own bank and put back the one they found.

**The rest of fixed memory, and what had to move.** With these out, fixed memory was still about 1.3 KB short at full size (the estimate of the brief, confirmed by the links), and more when the merged compiler raised `MAX_SYMS` to 560. Moved, by measurement on the maps:

- the saved tokens (2 KB) left the text memory for the token memory (`TOKENS`): text memory 4,096 to 2,048 bytes in host and twin (768 and 384 in the small build); INLINE reaches its records only through `kernel.token_byte()` and `set_token_byte()` (a refactor of `inline.py`, its behaviour the same);
- `lex.string` (2 KB) into `STRING`;
- `fbuf.label_offset` and `label_uses` (768) into `FUNCBUF`;
- `out.table` (2 KB) did **not** go into OUT's bank, though only bank 5 names it once EXPR fills a table through `out.table_byte()`: a 2,048-byte array is indexed by a `word`, which the compiler did with `LDA #<table` / `#>table` (fix-up kinds 2 and 3), and the linker's rule counted those as taking its address (section 5, "The rule"). Since object format version 4 it does: "out.table in OUT's bank", below;
- `reg.slot_size`, `slot_name`, `slot_weight` and `slot_kind` (1,152) are in bank 2 in the compiler; the test driver `regcmd` (bank 1) named them, which put them in fixed memory in the test programs, so it reads them through `lathe/src/slotview.lth`, four accessors placed in bank 2 (not a twin: the Python driver reads the columns itself);
- `fold` stays in bank 3 (the stopgap): fixed memory has no room for its 1,299 bytes. It is called by GEN (bank 2) and COND (bank 3) only when both operands are constants; in bank 2 beside GEN it fits the test programs, but not with the merged placement;
- `typetab` (935 bytes of code) goes into bank 2 beside GEN and REG, its busiest callers: `exprtest` does not fit otherwise, at any split (measured: its 2,048-byte `out.table` must be whole in one range, `$F810-$FFF9` holds 2,026, and with it in the lower range the code no longer fits). The compiler alone (`lathec`) would fit with typetab fixed;
- the split between variables and fixed code moves to `$4280`, and `compiler.env`'s (the default machine) to `$4400` for the larger name heap.

**The final layout** (`lathec`, the compiler, from its map, `bank_report.map_report`):

| | Bytes | |
|---|---|---|
| resident code | 13,358 | err, kernel, src, lex, fbuf, sys, disk, rt_bank, rt_math, rt_frame, `$start`, `$init` |
| stubs | 1,230 | 205 |
| resident code and stubs | **14,588** | under the 16 KB goal by 1,796 |
| resident constants | 479 | none of them err's messages now |
| fixed variables and slots | 16,512 + 1,083 | `$0200-$427F`, and `$F810-$FE5A` |
| free fixed memory | 1,620 | 0 below the code (`$4280`), 677 above it, 943 at `$F810-$FFF9` |
| bank 1 | 17,659 file, 419 variables | lathec, expr |
| bank 2 | 21,408 file, 2,871 variables | gen, reg, typetab |
| bank 3 | 12,589 file, 773 variables | cond, asmblock, inlines, fold |
| bank 4 | 18,944 variables, no file | the name heap |
| bank 5 | 10,792 file, 2,825 variables | decl, out |
| bank 6 | 5,259 file, 8,960 variables | the messages; the function buffer and labels, the string, the saved tokens |

`exprtest`, the largest test program: resident code and stubs 13,848 (12,612 and 206 stubs), 713 bytes free above the code and 899 at `$F810`, none below.

**The granularity of the blocks.** A block costs 12 bytes and about 90 cycles banked, so each maps around a whole operation of the fixed module that owns the table, not around a byte: KERNEL around each name operation (`name_end`, `sym_find` with its thawing, `freeze`, `put_name`, `names_release`), LEX around the characters of a name (with `kernel.name_put`, an inline function that only a block can expand) and around all the keywords in `init`, FBUF around an entry added (entries are now built in a fixed stage of 7 bytes and put in the buffer at once by `end_entry()`: a refactor of `fbuf.py`), around `finish` and around each of OUT's walks (`fbuf.put_fixups`, `put_code`, the loops OUT had, moved into FBUF in the Python too), ERR around a whole message. Helpers that read a table through a pointer the block passes them (`name_is_new`, `chain_find`, `spelling_hash`, `same_spelling`, `entry_runs_on`, `skips_jump`, `code_size`, `emit_entry`, `walk_step`, `thread`, `layout`, `widen`, `find_loops`, `message_start`) have no block of their own. Counted by the counting copy of `rt_bank.map` (`bank_report.py`) and, for where they come from, by counting the same calls in the host over `expr.txt` (a profile, not kept): in the test programs most blocks are start-up (LEX's keywords, entered once a run until `init` was given one block for all of them) and the drivers' walks of the function buffer (`listing`, a block per instruction), not compiling.

**Pointers into a region.** Nothing checks that a pointer into a region is used only inside its block, so every one was found by reading: each `@names`, `@buffer`, `@tokens`, `@MESSAGES_n` and `@string` is taken inside a block, the pointer-taking helpers above are called only inside blocks (checked mechanically: a script lists every call of them outside a `with` block of the calling function, and the only ones are calls from other helpers of the list), and no such pointer is stored in a variable that outlives its block, returned, or passed to code outside the owning module, but one: `kernel.token_start()` returns `@tokens`, which INLINE keeps as `saved_start` and in records (`sym_value` of an inline function) and reads only through `kernel.token_byte()`, inside that function's block; `inlines.lth` and `inlinetest.lth` were read for every dereference (`p[k]`), and those that remain are of file names in the text memory.

**The cost.** All in one (where a block is two calls of a lone `RTS`, 24 cycles): `lextest`'s code grows from 4,810 to 5,160 bytes (`size_report.py`: err 461 to 540, kernel 996 to 1,065, lex 2,184 to 2,392), and the 115 sections of `gen.txt` on the default machine (`compiler-small.env`) take 45,227,169 cycles against 44,255,258 before step 10: 2.2 % more, the blocks and the staged entries of FBUF. Banked, measured by `bank_report.py`:

| | before step 10 | after |
|---|---|---|
| `gen.txt`, 115 sections | 287,128,144 cycles, 3,501 far calls | 338,501,318 cycles, 4,595 far calls, 11,635 blocks (1.0 million cycles) |
| `expr.txt` | 166 sections, 698,946,711 cycles, 12,568 far calls | 177 sections, 848,009,261 cycles, 17,682 far calls, 49,770 blocks (4.5 million cycles) |
| start-up (an empty `expr.txt` section) | 3,869,121 cycles | 4,411,576 cycles: bank 6's 5,259 bytes of messages loaded too |

Most of the growth is start-up, paid once a section: the messages' file (about 370,000 cycles a run) and, after the merge, a fifth code bank. The far calls grew with typetab and out in banks.

**The compiler compiling itself** (`lathe/tests/test_src_selfhost.py`, all with `LATHE_SELFHOST=1`; the counts by `bank_report.py`'s counting copies; each compile is a run of its own that loads the 92,000 bytes of bank files first). Every object and interface file equals the host compiler's, byte for byte:

| Module | Lines | CPU cycles | Far calls | `with` blocks |
|---|---|---|---|---|
| err | 473 | 19,413,203 | 9,270 | 10,778 |
| kernel | 864 | 43,448,164 | 10,265 | 19,615 |
| src | 137 | 13,615,521 | 1,631 | 5,829 |
| lex | 830 | 35,698,345 | 11,226 | 17,117 |
| typetab | 272 | 16,483,758 | 3,800 | 6,729 |
| fold | 248 | 18,781,362 | 4,387 | 7,691 |
| fbuf | 911 | 39,852,970 | 10,937 | 17,142 |
| out | 440 | 27,980,674 | 6,250 | 12,366 |
| reg | 1,470 | 74,161,644 | 23,675 | 34,225 |
| cond | 571 | 33,267,794 | 8,515 | 15,055 |
| gen | 2,360 | 119,180,214 | 36,657 | 54,150 |
| asmblock | 921 | 50,119,580 | 13,454 | 22,608 |
| inlines | 792 | 53,391,956 | 12,730 | 24,406 |
| expr | 2,190 | 119,230,234 | 28,563 | 51,288 |
| decl | 1,449 | 85,009,081 | 22,121 | 38,942 |
| lathec | 266 | 23,452,050 | 4,229 | 12,424 |
| sys | 201 | 8,436,697 | 1,165 | 2,148 |
| **total** | **14,395** | **781,523,247** | **208,875** | **352,513** |

(the cycles are those of the counting build, a few hundred cycles a run more than `test_src_selfhost.py`'s 775,864,658.) About 54,000 cycles a line, the start-up of each run included (about 5 million cycles a run, *estimated* from exprtest's empty section and the larger bank files: some 85 million of the 782); the far calls 14.5 a line (2,640 cycles, 4.9 %), the blocks 24.5 a line (2,200 cycles, 4.1 %). The whole self-compile is 6.5 minutes of a 2 MHz Wendy 2.

**And the corpus.** `test_src_lathec.py` with `LATHE_LATHEC_FULL=1 LATHE_BANKED_ALL=1` runs the banked compiler at full size against the host at full size on all 687 inputs (the corpus, with the twins, and the inputs made for it): every one fits and every one is the same. By default the test keeps comparing at the small capacities (`src_support.build_program(..., small=True, banked=True)` writes `define SMALL 1`), where the inputs it was written for reach the small limits.

**Faults found.** One, in the compiler: a region read from an interface and the frozen entry of an exported variable of the same spelling (`kernel.names in NAMES`) are two name entries, and once a function has thawed the variable the lexer gives the region's word as the thawed entry; the region was compared by entry, so the next `with NAMES` block in that module was error 118. Regions are now compared by spelling (`reg.same_region()`, in `reg.object_symbol` and EXPR's `with` statement, host and twins); `test_banked_data.py`, "a region spelled like an imported variable is one region", is the smallest program that showed it. A section of `gen.txt` that stood for "another region" with a number that spelled nothing now uses no region.

**The form of `with`, for the owner.**

- **A block had to use a name of its region** (error 183), so a fixed function that reached a region only through a pointer it was given needed a use for nothing but the bank symbol: `kernel.token_byte(p)` was `tokens[p - @tokens]`, where `p[0]` would do. Since 2026-11-14 a block names its bank by the module's first variable or table of the region when it uses none, and `token_byte`, `set_token_byte` and `get` read `p[0]`; only a block of a region the module declares nothing in must still use something of it (error 184), since the object file names a bank by a symbol of its region.
- **`inline` functions cannot hold a block**, but an inline function that uses a region and is expanded inside a block works, and is the tool for a busy accessor (`kernel.name_put`); it must be exported with the names it uses, which costs every importer name-heap bytes.
- **A pointer into a region is unchecked**, as the language says; here it was manageable by keeping such pointers in the owning module's functions and parameters.
- No result was needed from inside a block that a `return` could not give; nesting through calls of fixed functions of another region worked unchanged.

**What stands beyond step 11.** The gate of stage 7 is met by this test. The name heap is the capacity to watch: `expr.lth` needs 18,122 of the 18,944 bytes (4 % spare), with room in bank 4 for 28 KB. Fixed memory had 1,620 bytes free in the compiler and none to speak of in `exprtest`, so a further fixed table or resident function needed something moved first (the candidates: the drivers' command words, 711 bytes of fixed constants in exprtest because their address is taken; `out.table` if the linker's rule changed: since done, 3,744 bytes free, "out.table in OUT's bank", below).

## out.table in OUT's bank

Built and measured 2026-11-14 (`python3 lathe/tests/bank_report.py`'s `map_report` on the maps of `lathec` and `exprtest` built by `src_support.build_banked`; the far calls by `bank_report.py --program exprtest --script expr`).

**What changed.** Object format version 4 tells an address formed only to reach an element (fix-up kinds 7 and 8) from one taken (2 and 3): "The rule" and "Why kinds 7 and 8 are safe", in section 5. One more thing named `out.table` from outside bank 5: GEN's `table_element` stored the bytes of a constant table being made into it directly. It now calls `out.table_byte()` (host and twin; `outtest` too), a far call from bank 2 to bank 5 for each byte of a constant table, which only declarations of tables make. With that, `out.table` (2,048 bytes) is `V E5BC 0800 out.table b=5` in `lathec`'s map, beside OUT's other tables at the top of bank 5 (bank 5: 10,792 bytes of file and 4,873 of variables, 15,665 of its 28 KB). `test_src_banked.py` checks it in each test program that links OUT.

**Fixed memory freed** (`lathec`):

| | free below the code | above it | at `$F810-$FFF9` | in all |
|---|---|---|---|---|
| step 10 (above) | 0 | 677 | 943 | 1,620 |
| a `with` block need not use a name of its region (`kernel.token_byte` and the like read `p[0]`: kernel's code 78 bytes smaller) | 0 | 755 | 943 | 1,698 |
| `out.table` in bank 5 | 963 | 755 | 2,026 | **3,744** |

`exprtest`: 919, 791 and 2,026, in all 3,736. The variables now all fit `data` (`$0200-$3EBC` in `lathec`, `$3EE8` in `exprtest`), so nothing is at `$F810`, and the 963 bytes below the code are code's only if the split at `$4280` moves down (to `$3F00`, measured below); the 2,026 at `$F810` take variables only, which a lower split would push there.

**What the room could hold.** Both measured with the split at `$3F00` (`data $0200 $3EFF`, `code $3F00 $7FFF`), neither adopted: the placement is the owner's choice.

| | `lathec`: resident code, stubs and constants | free fixed memory (below, above, `$F810`) | `exprtest`, 178 sections of `expr.txt`: cycles banked, far calls | its start-up (an empty section) |
|---|---|---|---|---|
| as built (fold and typetab in banks 3 and 2) | 14,989 | 963, 755, 2,026 | 856,963,012, 17,781 | 4,436,222 |
| `fold` fixed | 16,276: 108 under the 16 KB goal | 67, 364, 2,026 | 840,776,981, 17,754 | 4,345,288 |
| `typetab` fixed (fold back in bank 3) | 15,780: 604 under | 82, 860, 1,578 | 845,331,967, 15,861 | 4,370,390 |

`fold` fits fixed memory again (1,299 bytes of code; it was moved to bank 3 for want of room), but it is called only when both operands are constants: it saves 27 far calls in `expr.txt`, and what it saves in cycles is mostly the start-up's loading of a smaller bank 3 file (91,000 cycles a run). `typetab` (935 bytes) is called from EXPR (bank 1), DECL (bank 5) and COND (bank 3) as well as from bank 2: fixed, it saves 1,920 far calls (11 %) and 24 stubs, and leaves the resident code 604 bytes under the goal against 108. So `typetab` is the better use of the room if one is wanted; with either, about 1,000 bytes stay free besides what `$F810` holds.

**The banked linker** (`lathe/src/linker-bank.env`, `lk_banked.build_linker`, its map) gains more: `lk_name.local` (2,800 bytes of variables) and `lk_err.messages` and `messages2` (2,703 bytes of constants) are indexed by a word only in bank 1's code and follow it there, so its free fixed memory goes from 2,142 bytes (27 below the code, 153 above, 1,962 at `$F810`) to 7,645 (2,763, 2,856, 2,026), and its resident code, stubs and constants from 9,895 to 7,192 bytes (`spikes.md`, "The whole linker in Lathe, banked on Wendy 2", has the layout before: the small build's `MAX_LOCALS` was cut from 1,600 to 1,400 to fit, which this room would undo). The linker's test programs (`linker.env`, `linker-bank.env`) still link and run as before (`test_src_lk.py`, `test_src_link.py`).

## Functions kept in fixed memory, and read-only banks

Built and measured 2026-11-14, for the BBC Model B+128 ([`bbc.md`](bbc.md), "Changes to the linker"), where the code banks are ROM and the data regions sideways RAM in the same window; built and tested on Wendy 2 and in overlays. Both changes are in the linker only (`lathe/host/lk_envf.py`, `lk_scan.py`, `lk_win.py`, `lk_place.py`, `lk_emit.py`, `lk_map.py` and their twins): the compiler and the object format are unchanged.

### A read-only bank

```
bank      WIN 2 $12 KROM2.BIN
rom       WIN 2                  ; bank 2 of WIN is read-only (a ROM)
```

- **The entry.** `rom WIN N` names a bank that a `bank` entry has given, after it, as `place` and `region` do. It is a separate entry because the file of a `bank` entry is optional: a word after it would be read as a file named `rom`. Checks: an unknown window or bank (42), the same bank twice (43), a window switched by `overlay`, or anything after the number (3: an overlay is loaded from its file, so it is never there already).
- **What goes in it.** Code and constant data, as in any bank. Never a variable: the variables of a module placed in it go to fixed memory (`data`, then `more`), as if the module were not placed (`lk_win.bank_def`). A region in it may hold constant tables and strings; a variable in such a region is link error 60, naming it (`lk_place.place_bank_vars`).
- **Its file** is still written, the bytes of the bank as for any other, but the bank is not in the table `$banks` that `FARCALL.start` loads: it is there already. With every bank read-only the table has a count of 0.
- **The map** ends its `W` line with ` rom`: `W 8000 002F 2 KROM2.BIN rom`.

### Functions kept in fixed memory

**The rule.** In a module placed in a bank or overlay, these functions stay in fixed memory (`lk_scan.bank_in` gives 0 for them), and the map ends the `F` line of each with `k=N`, N its module's bank:

1. a function with a `with` block (a kind 6 fix-up: `lk_tab.F_WITH`);
2. a function that a call inside a block names (`CALL` flag bit 2), and for a call through a pointer, every function taken as that class (its `MEMB` records; `lk_tab.F_FIXED`, and `lk_name.X_BLOCK` on the symbol, so that a function defined after the call, or a member named in a later file, is marked too). Not a function taken only as a class merged with it: classes are merged because they share a member, which makes them share parameters, but a pointer of a class holds only functions taken as that class;
3. everything a function of 2 calls, directly or through a pointer (as in 2), at any depth (`lk_scan.keep_called`, a pass for each level of calls until nothing new is found; the edges that only place storage, `E_PENDING` and `E_VIA`, are not calls). Not what a function of 1 calls outside its blocks: that runs with no region mapped, and stays in its bank.

The rest of the module stays in its bank. A kept function's copies for interrupt contexts are kept with it. Everything else follows from `lk_scan.fn_bank`, which every part of the linker already asks: a kept function is fixed code.

**Why the callees' callees are kept too.** For the mapping alone, the direct callees would do. A far call from fixed code saves what is in the window and puts it back: `rt_bank.call` reads the port's bank bits and pushes them under the return address (`LDA PORT` / `AND #BANK_BITS` / `STA $0103,X`), and `rt_bank.back` writes them back (`ORA $0102,X` / `STA PORT`); `rt_ovl.call` notes the overlay in the window and `back` loads it again, and a region is never in an overlay (58). So a direct callee that far-calls into a bank comes back to its region mapped, and so does the block. But a block may pass a pointer into its region down, and while the block runs the pointer is good wherever it is used (`language.md`, "Banked data": only an address used *after* the block is the programmer's responsibility). The compiler does this: `kernel.name_is_new` and `chain_find` pass `@names` to `spelling_hash` and `same_spelling`, and FBUF's walks pass `@buffer` to their helpers ("Pointers into a region", in step 10). A helper kept only because it is called inside a block calls another that is not; that one stays in the bank, runs with its own bank in the window, and reads that instead of the region. Measured: with only the direct callees kept, the compiler with kernel, lex, fbuf, err and src placed (below) compiled `gen.lth` to an object file different from the host's; with the rule above, to the same. `cases/e2e-config/kept.lth` holds the smallest such program (`libkept.add8`, reached through `tally`): its sum is `06`, not `C4`, if only the direct callees are kept. So the rule is what the rule before it was in effect: everything that runs inside a block is fixed code, and the window holds the region for the whole block.

**The argument, in short.**

- *What runs while a block is active*: its own function, and what that calls inside the block, at any depth, through pointers too. All of it is fixed, so no call in the block's extent changes the window. Only a nested block of another region does, and it puts the bank back at its end; and an interrupt handler's far call, which puts back what it found.
- *Calls*: a kept function is fixed, so it is reached from every bank: its module's functions in the bank call it with a plain `JSR` (`lk_scan.crosses` is false for a fixed callee), and it calls them through their stubs, as any fixed caller does (`lk_win.mark_stubs`). `@f` of a kept function is its own address, so a call through a pointer reaches it without a far call.
- *Data follows the function*, not the module (`lk_graph.note_named`): a constant or variable of a placed module goes in the bank only if every function that names it is in that bank (a kept function is not) and nothing takes its address in a way that escapes (kinds 2 and 3, or any fix-up in constant data; kinds 7 and 8 do not count: "Why kinds 7 and 8 are safe", which holds because no function in a window has a block).
- *Recursion*: the marks are a fixed point, so a cycle of calls is kept whole; a kept recursive function calls itself with a plain `JSR`.
- *Inline functions*: an expansion is code of the function it is expanded in, and the compiler flags each call an expansion makes inside a block (`out.call` sees `out.with_region`), so what it reaches is kept. `with` cannot be in an inline function (168).
- *Interrupt functions*: always fixed; one in a placed module is still error 47, not kept, since a handler must not run a block anyway (119, 57).
- *Determinism*: the marks come from the records alone (kind 6 fix-ups, `CALL` flags, the calls, `MEMB` records), in the order of the files, before anything is placed, so whether a program links, and its bytes, depend only on the objects and the environment file.

**Errors.** 55 (a function with a block in a window) and 56 (a call inside a block that reaches a window) are retired: every such case is now kept, and neither number is reused. Nothing of them remains: a block in an overlay configuration maps a region that is in fixed memory (a region cannot be in an overlay, 58, and regions are in the window code is placed in), and its function is kept as in a bank, which costs nothing. What stays an error: a handler that reaches a function with a block (57), a region in an overlay or in another window (58), constants of a region in a bank with no file (59), a region or code with no `farcall` entry (54), an interrupt function in a window (47) or reaching an overlay (48), and now a variable in a region in a read-only bank (60).

**Tests.** `test_lk_windows.py`: `ReadOnly`, and in `Regions` a function with a block kept with its call outside the block going through a stub; a call inside a block keeping its callee and the callee's callee, the data that follow them, and a function in the bank calling the kept one with a `JSR`; context copies; the functions taken as a class called through, but not one taken only as a class merged with it, and what a member calls through another class; a block in an overlay configuration. `test_lo2asm.py`: the map's `k=` and ` rom`. `cases/e2e-config/kept.lth` runs on Wendy 2 banked, with bank 2 read-only (the program loads that bank itself, as a ROM would be there already), in overlays, and all in one on both machines, with the same output; `test_farcall.py` checks where each of its functions and tables went.

### Measured: the compiler with only what must be fixed

`lathec` built as `compiler-bank.env` builds it, and again with `kernel`, `lex`, `fbuf`, `err` and `src` placed in a seventh bank (`typetab` is placed already), measured by `python3 lathe/tests/bank_report.py DIR --selfhost [--all-placed] gen`: the map, and `gen.lth` (2,360 lines) compiled as `test_src_selfhost.py` compiles it; both builds give the host compiler's files. Nothing committed for Wendy 2 changed: the placement as built is faster, and Wendy 2 has the fixed memory.

| | as built | all placed |
|---|---|---|
| fixed code | 13,857 | 10,573 |
| of it kept, by module | | kernel 4,270 (34 functions), fbuf 3,174 (34), lex 1,023 (13), err 556 (8), src 88 (2): **9,111** |
| other fixed code | kernel 5,347, fbuf 3,623, lex 2,440, err 608, src 377, and the rest as at the right | disk 487, rt_math 353, rt_bank 326, sys 190, `$init` 46, rt_frame 42, `$start` 18: 1,462 |
| stubs | 208 (1,248 bytes) | 256 (1,536 bytes) |
| **code in fixed memory** | **15,105** | **12,109** |
| fixed constant data | 479 | 456 |
| bank 7 | | 3,321 bytes of file: lex 1,417, kernel 1,077, fbuf 449, src 289, err 52, and 37 of constants; 86 of variables |
| `gen.lth` compiled: CPU cycles | 117,223,034 | 122,785,615 (+4.7 %) |
| far calls | 36,891 | 65,018 (+28,127: 5.1 million cycles at 182) |
| `with` blocks | 59,739 | 59,739 |

(Measured after the import lists and the smaller name heap of the BBC work were merged; before, the kept code was 8,721 bytes and the code in fixed memory 11,689 against 14,510.)

- **What has to be in RAM** on a machine whose code banks are ROM: 11.8 KB of code (kept 8.9 KB, the run-time modules and the file interface 1.4 KB, stubs 1.5 KB), against the 9 KB `bbc.md` estimated for the kept part. Kept with only the direct callees it was 7,539 bytes (before the merge), and wrong (above).
- **What else stays fixed, and why.** Code: the run-time modules (`disk`, `sys`, `rt_bank`, `rt_math`, `rt_frame`) and the start-up. Constants (456 bytes): `lex`'s two keyword strings (269), named by `lex.init`, which is kept (its block holds the keywords); `$banks` (87); the module and function names `gen`, `expr` and `lathec` pass to OUT (`gen.frame_module`, `expr.map_name` and the like, 64), whose address is taken; `disk`'s and `err`'s small tables, named by fixed or kept code. Variables: kernel's symbol columns (12,702 bytes), named by modules in banks 1, 2, 3 and 5; reg's 901 and fbuf's 688, named from more than one bank or by kept code; the run-time's and `disk`'s. The placed modules keep 10,769 bytes of variables in their banks on Wendy 2 (bank 1 419, bank 2 2,871, bank 3 902, bank 5 6,491, bank 7 86); in read-only banks those go to fixed memory too.
- **The cost**: 28,127 more far calls in compiling `gen.lth`, from the code of banks 1, 2, 3 and 5 calling the functions of kernel, lex, fbuf and src that stayed in bank 7 (lex's token functions above all); 4.7 % more cycles. The blocks are the same.
- **The linker** grew by 720 bytes of code in `lktest4` (`lk_scan.keep_called`, the `rom` entry, the map's marks), which no longer fitted `lathe/src/linker.env`, whose split between code and variables moved from `$9500` to `$9860` (with the `exit return ADDR` of the BBC work beside it; 44 bytes of code and 63 of variables are left); `linker-bank.env` needed no change.

## Decisions for the owner

| Decision | Recommendation |
|---|---|
| Change the emulator? | Not required. If yes, only the exit status of `$F80F` (about ten lines in `emu_wendy2c.c` and a chip test). |
| Placement D, with E as the fallback if bank 2 overflows. | Accept. It meets 16 KB with 2.5 KB to spare. Bank 2 does overflow as the linker judges it (measured on gentest, "Measured on the compiler's test programs"), so the test programs use E. |
| The 6-byte stub (182 cycles) against the 12-byte stub (130). | The 6-byte stub: about 530 bytes less resident (stubs and routine), about 300 cycles a line more. |
| `with REGION do … end` as the form of explicit banked data. | Accept, or name another word; `map` would clash with names already used (`libmaps.Map`). |
| Interrupt handlers may far-call into banks. | Allow (measured safe); forbid overlays and `with` in them. |
| Error messages: in a data bank (`in MSGS`) or in a file. | The data bank now, since Wendy 2 has banks to spare; the file when a machine without banks is a target. |
| Chaining inside the compiler. | Drop it. Chained means compiler and linker as separate programs. |

## Changes proposed to other documents

Made on 2026-11-14 for what steps 1 to 9 built (architecture.md, code-model.md, build-plan.md, boards.md, language.md, object-format.md). The text that was put in:

- **`architecture.md`, "Configurations"**, the row **Chained**: "Compiler, linker pass 1 and linker pass 2 are separate programs run in order. They share nothing in memory; the files are the interface. The compiler itself is not divided further: banks make that pointless, and on a machine without banks it does not save enough ([`configurations.md`](configurations.md))." And replace the paragraph "If the front end alone exceeds…" with: "Dividing the front end in time was the fallback of L4; [`configurations.md`](configurations.md) shows it would save about 4.5 KB, not enough to matter."
- **`architecture.md`, "The environment description"**: replace the sketch for Wendy 2 by the `wendy2bank.env` above, and the table of entries by the one in "The environment file" here.
- **`code-model.md`, "Code in windows"**, add: "`@f` of a function in a window is the address of its stub, wherever it is taken. A constant or variable of a module in a window goes into its bank only if nothing outside the bank names it and nothing takes its address. An interrupt function is always fixed; what it calls may be in a bank, never in an overlay."
- **`code-model.md`, "Data in windows"**: replace "the program switches it in with a run-time call before use" by "the program uses it inside `with REGION do … end`, which maps the bank and maps back what was there".
- **`object-format.md`**: the three changes of version 3 above, under "Records" and "Fix-up kind".
- **`language.md`**: `with REGION do … end` under statements, and `in REGION` described under declarations; `with` added to the keywords.
- **`build-plan.md`, stage 11**: "Spike first: L5 (done)." and the order of work above as its steps; the open item on compiler size can point here for the banked configuration.
- **`boards.md`, Wendy 2**: a paragraph on `--disk DIR` and the `$F800` ports, and the environment `wendy2disk.env`.
