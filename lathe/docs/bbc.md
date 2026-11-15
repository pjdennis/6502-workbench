# Lathe on a BBC Model B+128

Status (2026-11-15): design, with the measurements it rests on. Built: the emulator's machine (`emulator/`, `--machine bbcbplus`), step 2, programs all in one run with `*RUN` through the MOS ([`boards.md`](boards.md), "The BBC Micro"; "Step 2, as built", below), and step 3: banked programs with the module in its developer's form ("Step 3, as built") and the ROM form, programs of a module image started by `*` commands ("Step 3, as built: the ROM form"). This is the first period machine of stage 12 in [`build-plan.md`](build-plan.md).

## The idea

The owner's proposal: the compiler and the linker in **one sideways ROM socket**, in a module that carries its own bank switching, with the compiler's tables in the B+128's 64 KB of sideways RAM and the rest in main RAM. A developer uses a module that holds RAM in place of the ROM, loaded from disk, so that nothing is burned while the tools change.

## The hardware assumed

| Part | What it is |
|---|---|
| CPU | 6512A, an NMOS 6502, 2 MHz |
| Main RAM | `$0000-$7FFF`. Zero page `$00-$8F` belongs to the current language; `$0400-$07FF` is the language's workspace; a program has PAGE to HIMEM, `$1900-$7BFF` with DFS in mode 7 (25,344 bytes) |
| Sideways window | `$8000-$BFFF`, one of sixteen slots chosen by ROMSEL at `$FE30`, with its copy at `$F4` |
| Sideways RAM | four 16 KB slots (0, 1, 12, 13 on the B+128) |
| The module | one slot; sixteen 16 KB banks of ROM (256 KB) behind it |

**How the module switches.** A ROM socket has no write line, so the bank is chosen by reading: a read of `$BFF0+n` selects bank n, from any bank. This is this project's own design, in the manner of the Computer Concepts carriers of 1987 (Inter-Word, SpellMaster), which switch on reads of addresses at the top of the ROM. The emulator also models the SpellMaster carrier itself (eight banks, 128 KB), which holds the compiler alone but not the compiler and the linker together (measured below).

**The developer's module** holds RAM. A write while its slot is selected goes to the selected bank; switching is the same. A loader run from disk fills it from the image file.

**What the emulator does not have.** No Acorn ROM is in the repository, so the MOS is the emulator's own behind the documented entry points, and there are no interrupts. What that leaves unproved is at the end.

## Measured before designing

From the compiler as built banked for Wendy 2 (`lathe/src/compiler-bank.env`), relinked with the BBC's CPU and zero page (2026-11-14):

| Build | Code, bytes |
|---|---|
| Wendy 2: 65C02, zero page `$00-$FF` | 75,065 |
| NMOS 6502, same zero page | 75,067 |
| Zero page `$00-$8F` (144 bytes) | 76,554 |
| Both | 76,556 |

- **The CPU costs nothing**: the code generator does not yet use the 65C02's instructions.
- **The smaller zero page costs 1,489 bytes**, 2%.
- **One module does not fit a bank**: `expr` is 17,253 bytes, and a bank is 16,384 less its header. It has to be split in two.
- **Compiler and linker do not fit 128 KB**: 76.6 KB of code and 6.5 KB of constants for the compiler, about 48 KB for the linker, 131 KB before any bank is left part empty. Hence sixteen banks.

Where the compiler's 52 KB of variables are today, and where they can go on the BBC:

| Variables | Bytes | On Wendy 2 | On the BBC |
|---|---|---|---|
| Name heap | 18,944 | data bank 4 | a sideways RAM slot, once import lists bring it under 16 KB |
| Function buffer, labels, string, saved tokens | 8,960 | data bank 6 | a second sideways RAM slot |
| Variables of modules placed in code banks | 6,905 | in the module's own bank | main RAM: a ROM bank holds no variables |
| Fixed variables | 17,188 | fixed memory | main RAM |

So main RAM has to hold every variable that is not in a region, the stubs, and every function that must be in RAM. A function must be in RAM if it has a `with` block or runs inside one, because the sideways RAM and the module share the window: while a table is mapped, the module is not there. The linker now keeps exactly those functions in fixed memory when their module is placed in a bank ([`configurations.md`](configurations.md), "Functions kept in fixed memory, and read-only banks"), so the figure is measured, not estimated.

**Measured (2026-11-15)**, on the compiler as it stands after import lists, with `kernel`, `lex`, `fbuf`, `err` and `src` placed in banks too:

| In main RAM | Bytes |
|---|---|
| Variables not in a region | 25,841 |
| Code kept fixed (`kernel` 4,270, `fbuf` 3,174, `lex` 1,023, `err` 556, `src` 88) | 9,111 |
| Other fixed code (file calls, arithmetic, far calls, start-up) | 1,462 |
| Stubs (256) | 1,536 |
| Fixed constants | 456 |
| **Total** | **38,406** |
| Available: `$1900-$7BFF` and `$0401-$06FF` | 26,111 |

**It does not fit as the compiler stands, by 12.3 KB.** Placing those five modules costs 4.7% more cycles on Wendy 2 (28,000 more far calls in compiling `gen.lth`).

What can leave main RAM, with accessor functions in front of it:

| Table | Bytes | Read by |
|---|---|---|
| The symbol and member columns of `kernel` | 10,388 | most modules, directly, in about 400 places |
| `out.table` and OUT's fix-up tables | 4,096 | OUT, and GEN through `out.table_byte` |
| `kernel.text` | 2,048 | through pointers |

The symbol table and OUT's tables together are 14.5 KB, one sideways slot, and bring main RAM to about 23.9 KB before the accessors' own code: about 2 KB to spare. The accessors may also make the code smaller, because every access to a column of more than 256 rows now computes a 16-bit address in line (about 13 bytes each).

## Design

**Memory.**

| Where | What |
|---|---|
| Zero page `$00-$8F` | the linker's zero page |
| `$0400` | the stack pointer the start-up code keeps (`exit return $0400`) |
| `$0401-$06FF` | data (`more data`) |
| `$0700-$07FF` | the command line, where OSARGS 1 points while the tool runs (not `$0400-$07FF` as data, as first written: step 2) |
| `$1900-$7BFF` | data, then the resident code and the stubs |
| Module banks | code and constants; the image of the resident code, copied to RAM when the tool starts. In the developer's form, RAM, the variables of the modules placed there too, at the bank's top (step 3) |
| Sideways slot A | the name heap |
| Sideways slot B | function buffer, labels, string, saved tokens |
| Sideways slot C | the symbol table, if it moves |

**The environment file.** One window, `$8000-$BFDF` (the last 32 bytes of every bank are left for the switching addresses and the read an instruction makes of the byte after it). A bank's value says what it is: bit 7 set is a bank of the module (the low bits its number), otherwise a sideways slot. The far-call module turns a value into the writes and reads that select it.

**Changes to the linker.**

1. A bank can be marked as ROM: it takes code and constants and never variables. (Done, 2026-11-14: `rom WIN N`.)
2. A function with a `with` block, and a function called inside one, stays in fixed memory when its module is placed in a bank. Until 2026-11-14 that was link error 55 or 56, and the whole module had to be fixed. The map lists what was kept. (Done; used on the BBC in step 3.)
3. (Made in step 3.) `switch WIN bank farcall`: the window is switched by banks, but no register and mask describe it, because a bank of the module is selected by a write and a read, and a value with bit 7 set written to ROMSEL would page in the B+'s private RAM. The linker treats it as `bank` otherwise ([`configurations.md`](configurations.md), "The environment file").

**The far-call module, `rt_bbc`.** The same interface as `rt_bank` (`call`, `back`, `map`, `unmap`, `start`). Selecting a module bank writes the module's slot to `$F4` and `$FE30` and reads `$BFF0+n`; selecting a sideways slot writes the slot. ~~The module's latch keeps its bank while a sideways slot is in the window, so leaving a `with` block is one write. Both should cost far less than Wendy 2's 182 and 90 cycles.~~ Built in step 3, the machine corrected both sentences: leaving a block entered from a bank latches the bank again, because a far call made inside the block (through a fixed function) moves the latch; and a far call costs about what Wendy 2's does, 187 cycles, because neither ROMSEL nor the latch can be read back and the switch is three accesses, not one. A block costs 64 or 79 cycles against Wendy 2's 90. "Step 3, as built".

**The MOS interface, `bbc.lth`.** The interface of `host.lth` and `disk.lth` over OSFIND, OSBGET, OSBPUT, OSWRCH and OSNEWL, OSRDCH and OSARGS. The arguments are the tail of the `*` command. Built in step 2.

**The module image.** A host tool packs the bank files of the compiler and of the linker into one image. Every bank begins with the same sideways ROM header and the same few bytes of service code, so the MOS finds a valid ROM whichever bank the latch holds. That code answers only unknown commands and `*HELP`, selects bank 0 and goes on there. Bank 0 knows `*LATHE` and `*LLINK`: it copies the tool's resident code to main RAM and enters it. (Built in step 3: "Step 3, as built: the ROM form".)

**The developer's flow.** `*RUN LOADMOD` reads the image from disk into the RAM module, bank by bank. After that the commands work as from the ROM. (Built in step 3.)

## Order of work

1. The emulator's machine. Done.
2. Programs all in one on the BBC: `bbc.lth`, the environment file, the board in the test driver, the end-to-end cases. **Done (2026-11-14)**: below.
3. Banked: `rt_bbc`, ROM banks and the kept functions in the linker, the image tool, the header and service code, the loader. The far-call and banked-data cases run on the BBC. **First half done (2026-11-15)**: `rt_bbc`, its environment, the driver, the cases and the compiler's banked test programs, with the module in its developer's form (RAM) loaded by the program's start-up code; below. The linker's read-only banks and kept functions are done too (2026-11-14, another change; kept functions are used on the BBC below). **Second half done (2026-11-15)**: the image tool, the header and service code, bank 0's `*` commands, the loader, the ROM form of `rt_bbc` and `bbc.lth`; "Step 3, as built: the ROM form".
4. The compiler: `expr` split, the placement, the budget measured. The symbol table behind accessors if that is what stands between. The test programs, then the compiler compiling itself.
5. The linker in the same module, at the capacities that fit.

## Step 2, as built

`lathe/rt/bbc.lth`, `lathe/env/bbc.env`, the `bbc` board of `lathe/host/driver/boards.py` and the tests `lathe/tests/test_bbc*.py`; the recipe is in [`boards.md`](boards.md), "The BBC Micro".

- **Arguments**: the tail of `*RUN NAME ARGS`, from OSARGS with A=1, Y=0, as a real MOS gives it; the emulator provides it, so no convention of this project's own was needed. Split at spaces, with `"..."` for an argument that is empty or holds a space.
- **The end**: returning from `main`, or `exit(0)` from any depth, returns to the MOS. For the second the linker learnt one thing: `exit return ADDR`, whose start-up code begins with `TSX` / `STX ADDR` (here `$0400`), so that `exit` can put S back and return. `exit(N)` with N not 0 raises the MOS error N, `Exit N`: the emulator ends with status 1 and prints the message, a real BBC's language reports it. Both close every file (OSFIND 0, Y=0).
- **Errors** go where output goes: the BBC has one stream.
- **Line ends**: the BBC's is CR, and OSNEWL writes LF CR. `put_byte(10)` is OSNEWL, `read_byte` gives CR as LF, and files are never translated.
- **Files**: an error OSFIND raises (`Bad name`, `Too many open files`) is caught through BRKV for the call and gives 0, as a missing file does; `read` remembers the end of a file, because OSBGET raises `EOF` when it is called again there.
- **sys.lth** chooses `bbc` with `define PORTS 2`: each `#if PORTS` block is the `#else` of an `#if PORTS == 2`, and every other build is byte for byte what it was. `build.py` compiles every module an `import` line names, under any `#if`, and a module's `$init` is linked whether or not anything else of it is used: so `bbc.lth` has no initial values (argc and argv read the tail again at each call, which stays at `$0700`).
- **The corpus**: 67 of the 69 end-to-end cases run on the BBC with `--bbc-strict` and give their expected output (their `import host` is `lathe/rt/bbc/host.lth`, host's interface over bbc). `asm_pointer` and `state` store at `$C800`, `$FA` and `$EFF8`, which are the MOS's there.
- **The compiler's test programs**: `lextest`, `errtest`, `kerneltest` and `srctest` in the small build fit `$1900-$7BFF` (`lathe/src/compiler-bbc.env`) and give what their twins give, section by section. In the small build `kerneltest`'s normal run declares more names than the small name heap holds, so it ends with error 70, as its twin does.

Measured (2026-11-14), code and constant data in bytes, each program linked with the small build's capacities on the default machine (zero page `$00-$FF`, host services) and on the BBC (zero page `$00-$8F`, bbc.lth); and the variables outside zero page:

| Program | Code, default | Code, BBC | Variables, default | Variables, BBC | Fits `$1900-$7BFF` |
|---|---|---|---|---|---|
| copytest | 381 | 967 | 272 | 748 | yes |
| errtest | 6,229 | 6,621 | 405 | 721 | yes |
| srctest | 7,486 | 8,057 | 1,473 | 1,949 | yes |
| typetest | 9,078 | 9,649 | 1,915 | 2,391 | yes |
| foldtest | 9,480 | 10,051 | 1,739 | 2,215 | yes |
| lktest1 | 9,826 | 10,412 | 1,048 | 1,524 | yes |
| lextest | 10,758 | 11,335 | 3,277 | 3,753 | yes |
| fbuftest | 11,510 | 12,081 | 3,575 | 4,051 | yes |
| kerneltest | 12,883 | 13,463 | 7,977 | 8,453 | yes, by 3.4 KB |
| outtest | 15,823 | 16,510 | 11,099 | 11,622 | no: 28.1 KB |
| regtest | 25,044 | 25,922 | 13,209 | 13,769 | no |
| asmtest | 25,869 | 27,021 | 14,200 | 14,798 | no |
| condtest | 27,845 | 28,736 | 13,209 | 13,773 | no |
| inlinetest | 43,783 | 45,282 | 15,129 | 15,727 | no |
| gentest | 44,737 | 46,182 | 14,867 | 15,465 | no |

- **bbc.lth costs 586 bytes of code and 476 of variables** (`copytest`: 381 bytes over `host.lth`'s fixed addresses, 967 over the MOS): the name for OSFIND, the arguments' text (256 bytes), the BRK block, the catching of errors.
- **The smaller zero page costs little in these programs**: about the same 586 bytes for the small ones, about 860 more for `gentest`, 2% as for the banked compiler above.
- `exprtest` and `lktest2` to `lktest4` need more than 16 KB of variables even at the small capacities, and the full builds of `lextest` (25.9 KB of variables) and `kerneltest` do not fit; `srctest` and `errtest` do at full size. Everything larger than `kerneltest` waits for the banks (steps 3 and 4).
- **A byte through the MOS** in this emulator: `bbc.read` 70 cycles, `bbc.write` 38, `put_byte` 31; a byte copied by `copytest` through `sys`, 141. The emulator's MOS takes 2 cycles a call of its own, so these are a floor: the real MOS and DFS cost much more a byte, and the disc more again.

What step 2 showed in the design:

- `$0400-$07FF` is not all data: the command line `*RUN` was given is at `$0700` (BASIC's input buffer, and the emulator's `--bbc-command`), and the tool must leave it, or read it before anything of `$init` runs. The table above is corrected.
- A program run with `*RUN` from BASIC and returning to the MOS returns into BASIC, whose zero page (`$00-$8F`) and workspace it has used. Whether BASIC survives that cannot be seen here (no BASIC ROM). The open question below, ending a tool by OSBYTE 142, stands, and applies to `*RUN` too.

## Step 3, as built (first half)

`lathe/rt/rt_bbc.lth`, `lathe/env/bbc-bank.env`, `lathe/src/compiler-bbc-bank.env`, the `bbc` board's module options (`boards.module_options`), and the tests `lathe/tests/test_bbc_bank.py` and `test_bbc_bank_src.py`; the recipe is in [`boards.md`](boards.md), "Banked: the module and sideways RAM", and the module beside `rt_bank` and `rt_ovl` in [`configurations.md`](configurations.md), "The third: rt_bbc".

- **Selecting** a bank of the module: its slot to `$F4`, then to ROMSEL, then a read of `$BFF0+n`. A sideways slot: the slot to `$F4`, then to ROMSEL. `$F4` first, always: the MOS's interrupt and filing-system code put ROMSEL back from it.
- **Restoring.** Neither ROMSEL nor the latch reads back, so `rt_bbc.now` holds the value of what is in the window, set before every switch. `call` pushes it and `back` selects it again; the value is on the stack, as `rt_bank`'s bank is, so nested and recursive far calls work (`farcall.lth`'s 20 levels, and this step's own 20 levels that alternate between two banks and enter a `with` block at each).
- **Leaving a `with` block** is not one write, as designed. A block's value says only which slot was in the window; if that was the module, `unmap` reads `$BFF0+n` again, because a far call made while the block has its slot mapped moves the latch. The linker keeps fixed everything a call inside a block reaches, so in compiled code that far call is an interrupt handler's; `test_bbc_bank.py`'s program makes one through an address taken in asm, which the linker does not follow, and with the slot alone put back it returns into the wrong bank.
- **The module's slot** is `define MODULE_SLOT 4` in the environment, which must match the socket (the emulator's `--bbc-module-slot`). Since the ROM form it is the variable `rt_bbc.mslot`, which `start` sets from the define, or in the ROM form from the stub (below); a cycle more for each switch to a bank of the module.
- **Start-up** loads each bank's file, into the module or a sideways slot, through `bbc.lth`'s `open`, `read` and `close`, with that bank selected: the MOS is called with the module in the window, which `--bbc-strict` allows because `$F4` says the same as ROMSEL.
- **A fault found in `bbc.lth`**: the MOS's BRK handler selects the language's slot (slot 15 here) before it enters BRKV, so after a filing system error that `open` catches (`Bad name`) the window no longer held the code or region that called it. `caught` now selects again the slot that was in the window (11 bytes). The test opens a name the filing system refuses from a bank of the module and inside a block.
- **The cases of `e2e-config`** that run on the BBC, with their outputs on Wendy 2: `farcall.lth` (code in banks 1 and 2 of the module), `bankdata.lth` (a module's constants and its variable in bank 3), `regions.lth` (variables in sideways slot 12, constants in slot 13, loaded at start-up), and a missing bank file is status 255. Not run: `farirq.lth` and `withirq.lth` need a timer interrupt (the emulator's BBC has none, and their `timer` is Wendy 2's VIA); `inbank.lth` switches Wendy 2's port and loads its bank through `disk` by itself.
- **Sixteen banks**: sixteen modules, one in each bank of the module, in a chain of far calls.

Measured (2026-11-15, `test_bbc_bank.py`, two runs of 110 and 10 calls against the same objects all in one; with the slot in a variable since the ROM form, where it was 186, 195 and 78 with the slot a constant):

| | Cycles | Wendy 2 |
|---|---|---|
| A far call, fixed code into a bank | 187 more than a call | 182 |
| A far call between two banks of the module | 197 more | |
| A `with` block, the function's last statement, entered from fixed code | 64 (24 all in one) | 90 |
| The same, entered from a bank of the module | 79 | |

The compiler's banked test programs (`lathe/src/compiler-bbc-bank.env`, small build): code in five banks of the module (1, the drivers and the test's main module; 2, `gen`; 3, `reg`, `typetab`, `slotview`; 4, `cond`, `fold`; 5, `out`, `decl`, `asmblock`), the name heap in slot 12, err's messages and fbuf's, lex's and kernel's tables in slot 13; `err`, `kernel`, `fbuf`, `lex` and `src` fixed (most of their code has `with` blocks or runs inside one). Every section of each script gives what its twin gives at the small capacities. Fixed memory is code `$1900-$4BFF` and variables `$4C00-$7BFF` and `$0401-$06FF`:

| Program | Fixed code, constants, stubs | Fixed variables | Bank 1 | 2 | 3 | 4 | 5 | Slot 12 | Slot 13 |
|---|---|---|---|---|---|---|---|---|---|
| outtest | 8,159 (to `$38DF`) | 6,803 (to `$66AC`) | 1,672 + 250 | | | | 2,135 + 1,101 | 1,536 | 5,494 + 1,920 |
| regtest | 9,607 (to `$3E87`) | 7,997 (to `$6B67`) | 3,410 + 252 | | 7,671 + 1,769 | | 1,066 + 260 | 1,536 | 5,494 + 1,920 |
| condtest | 9,770 (to `$3F2A`) | 7,999 (to `$6B6A`) | 3,567 + 252 | | 7,671 + 1,769 | 2,580 + 1 | 1,070 + 260 | 1,536 | 5,494 + 1,920 |
| gentest | 11,210 (to `$44CA`) | 9,165 (to `$704B`) | 4,673 + 252 | 12,666 + 755 | 8,348 + 618 | 3,752 + 1 | 2,016 + 1,100 | 1,536 | 5,494 + 1,920 |

A bank's numbers are code and constants (its file) + variables, of 16,352 bytes; fixed variables are those outside zero page, `more data` included; the variables' last address counts the frames too. (Measured before the ROM form, whose support in `bbc.lth` and `rt_bbc` adds 76 or 77 bytes of fixed code to each: gentest's now ends at `$4516`; `test_bbc_bank_src.py`'s splits at the full capacities moved to `$3940` for outtest and `$3F80` for condtest.)

- **All four fit**, gentest with 1.8 KB of fixed code range and 2.9 KB of variables left.
- **At the full capacities** (SMALL 0), with the fixed variables moved down to just above each program's fixed code, outtest (variables from `$3900`, to `$6E64`), regtest (from `$3F00`, to `$795F`) and condtest (from `$3F40`, to `$79A2`) fit too, and their scripts give what the twins give at their own capacities. gentest does not: its variables are 1,344 bytes too many for `$44D0-$7BFF` and `$0401-$06FF`.
- **Kept functions on the BBC.** With `kernel`, `lex` and `src` placed in bank 4 and `fbuf` and `err` in bank 5 as well, the linker keeps fixed only their functions that have a block or run inside one: gentest's fixed code ends at `$4125`, 933 bytes less (banks 4 and 5 grow to 4,371 and 2,474 bytes of file), and every section of gen.txt still agrees with the twin. At the full capacities gentest is then 576 bytes over (variables from `$4130`). The small build's environment keeps the five modules fixed, which saves those far calls.
- **The design's budget held for the small build**: what stands in main RAM is the fixed modules with `with` blocks and their tables, about 11 KB of code and 9 KB of variables for gentest. The full compiler needs the symbol table behind accessors as well (above).
- **Since the symbol table is in a region** (2026-11-15, [`configurations.md`](configurations.md), "The symbol table in a region"): `compiler-bbc-bank.env` puts `SYMS` in sideways slot 0 (bank 34, value `$00`) and `OUTTAB` and `WANTS` in slot 1 (bank 35), and places `parts` in bank 3; OUT's functions with a block of `OUTTAB` are kept fixed (DECL's with `WANTS` too, where linked). gentest's fixed code now ends at `$4866` and its variables at `$5CCF` in the small build. At the full capacities **all four fit**, with the fixed variables from `$3C30` (outtest), `$4080` (regtest), `$4130` (condtest) and `$4870` (gentest; `$43B0` with the kept modules placed), and every section of their scripts gives what the twin gives at its own capacities (`test_bbc_bank_src.py`, `FULL_SPLIT`). `rt_bbc.map` has no test for the value 0, which `rt_bank` treats as a fixed region: on the BBC it is slot 0.
- `MAX_BANKS` in the linker is 16, banks of all windows together. The sixteen-bank test uses all of them; the whole compiler on the BBC, with sixteen banks of the module and two or three sideways slots, needs it raised (step 4).

## Step 3, as built: the ROM form

`lathe/rt/bbc/module.asm` (the header, the service code and bank 0), `lathe/host/driver/bbcrom.py` (the image tool and `rom_env`), `lathe/rt/bbc/loadmod.asm` (the loader), `lathe/env/bbc-rom.env`, `boards.run_module`, the ROM form's few lines in `lathe/rt/bbc.lth` and `rt_bbc.lth`, and the tests `lathe/tests/test_bbc_rom.py` and `test_bbc_rom_src.py`; the recipe is in [`boards.md`](boards.md), "The ROM module". In the emulator: `--bbc-command` repeatable, `*HELP` as service call 9, OSBYTE 252 (`emulator/README.md`).

**The image.** 262,144 bytes, sixteen banks of 16 KB, scheme `direct16`, in one slot. Every bank:

| Bytes | What |
|---|---|
| `$8000-$8002` | `00 00 00`: no language entry |
| `$8003-$8005` | `JMP service` (`4C 22 80`) |
| `$8006` | type `$82`: a service entry, 6502 code |
| `$8007` | `$0E`, the copyright's offset |
| `$8008` | version 1 |
| `$8009-$800D` | the title, `Lathe` |
| `$800E-$8021` | `00 "(C) 6502-workbench" 00` |
| `$8022-$8035` | `service`: `CMP #4`, `BEQ`, `CMP #9`, `BEQ`, `RTS`; for 4 and 9 `PHA` (the call), `LDA number`, `PHA` (the bank), `LDA $BFF0` (bank 0: the next instruction is bank 0's, the same), `JMP bank0` |
| `$8036-$803E` | `back`: `PLA`, `TAX`, `LDA $BFF0,X` (the bank of entry), `PLA` (A the call), `LDX $F4`, `RTS`: unclaimed, A, X and Y as given |
| `$803F-$8048` | `claim`: the same with `LDA #0` |
| `$8049-$804E` | 0 |
| `$804F` | `number`: the bank's own number, the one byte that differs |

So the reserved bytes are 80; a program's banks are linked with the window `$8050-$BFDF` (`bbc-rom.env`), and `$BFE0-$BFFF` of every bank hold nothing ($FF). For any service call but 4 and 9 the code changes only the flags; for 4 and 9 a command the module does not know, and `*HELP`, go back to the bank they came in, so an unknown command a tool passes to OSCLI from a bank of the module returns there. Bank 0 holds, from `$8050`, its code (416 bytes), the command table, the `*HELP` text and each command's copy list, then the programs' resident parts and their regions' constants as far as they fit; the rest goes in the banks no program's code is in, in order.

**Bank numbers.** A program's banks of the module are the banks of the image its environment names (`bank WIN N $8n FILE`, and `rom WIN N`); bank 0 is the module's. `bbcrom.rom_env(SOURCE, OUT, FIRST)` makes a program's ROM environment from its `*RUN` one (`bbc-bank.env` and its lines): the window `$8050-$BFDF`, its banks of the module renumbered from FIRST in the order of their `bank` lines, each `rom`; it returns the next number, so programs numbered one after the other never collide. The tool checks it: every bank of the module `rom` (else the linker would have put variables there), numbered 1 to 15, used by one program only (the error names both), its file within `$8050-$BFDF`; regions in sideways RAM slots (0, 1, 12, 13); the window; `exit return $0400` and `output raw`; the resident part in the code range from `$0800`; no code, data or `more data` range over `$0700-$07FF`; commands of capitals and digits, each once; and that the resident parts and region constants fit the banks left (saying by how many bytes they do not). Resident parts are placed after the links, so no program's bank number can collide with them.

**The start**, for `*FIRST a b`: the MOS offers service call 4 to each ROM, slot 15 down; the module's `service` (in whichever bank) goes to bank 0, which matches the command word against its table (capitals, or small letters; the word must end at a space or CR; no abbreviations). For a command it knows:

1. the tail, after the spaces, from `($F2),Y` to `$0700`, ended by CR (at most 239 bytes; copied from the end down if the line is below `$0700`);
2. the stub, 16 bytes at `$07F0`: `JSR start`, `LDA #slot` (the slot at `$07F4`, from `$F4`, which the MOS set for the service call), `STA $F4`, `STA $FE30`, `LDA $BFF0`, `JMP ended`;
3. the copier (62 bytes) to `$0400`, run for each entry of the command's copy list: a block of the image (bank, address, length) to main RAM or to a sideways RAM slot, a byte at a time, the source bank latched and the slot selected for each, about 60 cycles a byte to main RAM and 80 to a slot (gentest's 11,217 and 5,494 bytes: about 1.1 million cycles, 0.6 s);
4. `JMP $07F0`.

Why there: once the command is matched, the language that was running cannot go on (the tool takes its zero page `$00-$8F`, its workspace `$0400-$07FF` and the memory from PAGE), so the module uses them. The copier is needed only before the program starts, and the program's `more data $0401-$06FF` may lie over it. The tail and the stub must last while the program runs: `$0700-$07FF` is outside every ROM program's ranges, as it is for `*RUN` (where the command line is), and the tool checks it. The walk of the copy list uses `$8C-$8E`, the copier `$A8-$AF` (the MOS's workspace for `*` commands).

**What the program learns.** The start-up code keeps S at `$0400`; `bbc.from_rom()` reads the return address above it: `$07F2`, the stub's `JSR`, in the ROM form, an address in the MOS or the language for `*RUN`. In the ROM form `argc` and `argv` read the tail at `$0700` (OSARGS 1 knows only `*RUN`'s tail), and `rt_bbc.start` takes the slot from `$07F4` into `mslot` and loads nothing: its banks are in the image and its regions' constants were copied. Otherwise the tail is OSARGS's and the slot `MODULE_SLOT`. So **the same objects link for both**: the ROM environment has the same `define` lines, and `test_bbc_rom.py` checks that every object is the same bytes. What it costs: `from_rom` and the choice in `tail_address`, 49 bytes of every BBC program, and 28 in `rt_bbc` (its `start`, and `mslot` an absolute operand where zero page has no room), with a cycle a switch: 77 bytes in gentest.

**The end.** Status 0 (`main` returns, or `exit(0)` from any depth through the kept S) returns to `$07F3`, which selects the module and bank 0 and goes to `ended`: OSBYTE 252 gives the current language and OSBYTE 170 the ROM type table; if that slot's type has bit 6 (a language), OSBYTE 142 enters it again, and it does not return, which is what a ROM tool that has used the language's memory must do on a real machine (BASIC starts again empty). With no language ROM (the emulator without `--bbc-rom`) the service call returns claimed, through `claim`. A status other than 0 is the MOS error `Exit N` as before: the MOS's BRK handler goes to the language's error handler, and the module is not returned to (its header in every bank is why that is safe).

**`*HELP`** (service call 9) with no argument (spaces skipped) prints the title and the commands, `Lathe` and `  FIRST` ... one a line; with an argument, nothing. It never claims, and returns to the bank it came in.

**The developer's form.** `*RUN LOADMOD IMAGE [SLOT]` (`loadmod.asm`, 407 bytes at `$1900`; `bbcrom.py --loader FILE` writes it and its `.inf`): for each bank, OSGBPB reads 16 KB into `$2000-$5FFF` (on a real machine the filing system is a ROM in the window while it runs, so it cannot write the module), then the module's slot is selected, the bank latched and `$8000-$BFDF` copied by pages (so that no `STA (zp),Y` makes its dummy read in the switching addresses), and `$F4` and ROMSEL put back; at the end bank 0's type (`$8006`) goes into the ROM type table (from OSBYTE 170) at the slot. The MOS then offers the module service calls without a reset. A missing file, a short one (`Not a module image`) and a slot over 15 are errors.

**Tested** (`test_bbc_rom.py`, 4 seconds; every run `--bbc-strict`): one image of three programs, `*FIRST` (farcall, bankdata and regions: far calls between banks 1 and 2, libbkd's constants in bank 3 and its variable in main RAM, regions in slots 12 and 13 with constants copied there), `*SECOND` (`test_bbc_bank.py`'s program: banks 4 and 5, two regions at the same addresses, files from a bank and inside a block) and `*THIRD` (all in one): each with its arguments gives what it gives with `*RUN` banked and all in one; in all sixteen power-on banks; in slots 7 and 2; through LOADMOD in the RAM form (slots 4 and 7, power-on banks 0, 9 and 13); `*THIRD fail` is `Exit 9`; with a language ROM (one made in the test, in slot 15) each command ends in the language, without one it returns claimed; `*NOSUCH`, `*FIRSTX`, `*FIRS` and `*SECOND.` are `Bad command` with the latch back where it was; `*HELP`; service calls 50 and 6 from a program leave the latch alone; the image tool's checks and its command line.

**The compiler's test programs as ROM programs** (`test_bbc_rom_src.py`, 11 seconds): `outtest`, `regtest`, `condtest` and `gentest` in the small build, each alone in an image (`compiler-bbc-bank.env` through `rom_env`: banks 1 to 5 `rom`), started by `*GENTEST SCRIPT OUT` and so on: every section of every script gives what the twin gives, files included. In a ROM bank nothing can be a variable, so the placed modules' variables join the fixed ones in main RAM. Measured (2026-11-15), bytes:

| Program | Resident (fixed code, constants, stubs) | Fixed variables, ROM form | The same, banked in RAM | Banks 1-5 (files) |
|---|---|---|---|---|
| outtest | 8,165 (to `$38E4`) | 8,155 (to `$6BF3`) | 6,804 (to `$66AC`) | 1,672, -, -, -, 2,135 |
| regtest | 9,614 (to `$3E8D`) | 10,279 (to `$7450`) | 7,998 (to `$6B67`) | 3,410, -, 7,671, -, 1,066 |
| condtest | 9,777 (to `$3F30`) | 10,282 (to `$7454`) | 8,000 (to `$6B6A`) | 3,567, -, 7,671, 2,580, 1,070 |
| gentest | 11,217 (to `$44D0`) | 11,892 (to `$7AF1`) | 9,166 (to `$704B`) | 4,673, 12,666, 8,348, 3,752, 2,016 |

- **All four fit** in the small build, with variables `$4C00-$7BFF` and `$0401-$06FF`: gentest with 270 bytes of the main range left (and `more data`'s 767). The resident part is 70 bytes smaller than banked: the ROM banks are not in `$banks`. Slot 12 holds the name heap (1,536 bytes), slot 13 5,494 bytes of constants (copied from the image) and 1,920 of variables.
- **At the full capacities none fits** in the ROM form: with the splits of the banked runs, outtest is 768 bytes of variables over, regtest 1,122, condtest 1,198; gentest 7,827 at `$44D0`. The variables of the banks' modules (2,726 bytes for gentest in the small build) are what a ROM costs main RAM; the symbol table behind accessors (above) is what the full compiler needs.
- **Since the symbol table is in a region** (above), gentest fits at the full capacities in the ROM form too, with the split of the banked run (`$4870`), and its script gives what the twin gives (`test_bbc_rom_src.py`, `GenRomFull`); the other three fit so as well.
- gentest's image: bank 0 the module's code and tables, then gentest's region constants and resident part to `$BFDF` and on into bank 6.

**What it showed.** The design held. Three things were added to the emulator, each with a C test: `--bbc-command` repeatable (each line run when the one before returns, as a language's prompt would; the loader and then a command), `*HELP` as service call 9 (it was offered as an unknown command), and OSBYTE 252 (the current language; it went to the ROMs as service call 7). No fault was found in the emulator's MOS. Two numbers moved: the slot in a variable costs a cycle a switch, and `test_bbc_bank_src.py`'s full-capacity splits moved for the 70 bytes the ROM form adds.

## Open, for the owner

- **File names.** DFS allows seven characters and uses `.` to separate the directory, so `asmblock.lth` cannot exist there. ADFS allows ten. The first version uses names as the emulator's directory takes them. A scheme is needed for real discs, for example `L.EXPR` for source, `O.EXPR` for the object file and `I.EXPR` for the interface, with module names kept to seven characters.
- **How a tool ends.** As a command it uses the language's zero page and the memory from PAGE, so the language that was running (BASIC) cannot be returned to as it was. ~~The tool should end by starting the current language again (OSBYTE 142).~~ Done so in step 3 (ROM form); a program run with `*RUN` still returns into the language, which may not survive it.
- **The command's tail** is copied to `$0700`, at most 239 bytes: the linker's longest command lines must fit that (the MOS's own line is 255 at most).
- **Sideways RAM** slots a program's regions name are taken without asking: whatever the owner had loaded in them (a ROM image in sideways RAM) is overwritten at the command.
- **Other filing systems and screen modes** move PAGE and HIMEM; the layout is fixed at link time. One build per case, or one build for the smallest case.

## What the emulator cannot show

- That the header and service code live with the real MOS: its scan of the ROMs at reset (with its duplicate check, which compares ROMs, and the service calls 1 and 2 it makes, which the code returns unclaimed), service calls made during interrupts while the tool runs in another bank (the emulator has no interrupts; the test makes such calls with OSBYTE 143 from a program), `*HELP`'s own lines and its argument as the real MOS passes it, and OSBYTE 252's and 170's answers, which are from memory (`emulator/NOTES-bbcbplus.md`).
- That OSBYTE 142 from inside a service call leaves the real MOS in order (it resets the stack, which the emulator models, and prints the language's title, which it does not), and that BASIC entered so starts cleanly.
- The dummy reads of a real NMOS 6502. The module's code, the copier and the loader are written to keep them out of `$BFF0-$BFFF` (no instruction ends near it, indexed accesses there stay in their page, `$BFE0-$BFFF` are never read or written by a copy), but the emulator's core makes none, so that is by inspection only.
- A real DFS: LOADMOD's OSGBPB of 16 KB at a time, and the seven-character names.
- Timing against real discs. The compiler compiling itself is about 780 million cycles on Wendy 2, six and a half minutes at 2 MHz, before the cost of reading and writing each byte through a real filing system.
- The real module's electrical behaviour. MAME models the SpellMaster carrier, so the eight-bank form (the compiler alone) could be tried there against the real MOS by someone who has the ROMs.
