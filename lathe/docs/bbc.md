# Lathe on a BBC Model B+128

Status (2026-11-15): design, with the measurements it rests on. Built: the emulator's machine (`emulator/`, `--machine bbcbplus`), step 2, programs all in one run with `*RUN` through the MOS ([`boards.md`](boards.md), "The BBC Micro"; "Step 2, as built", below), and step 3: banked programs with the module in its developer's form ("Step 3, as built") and the ROM form, programs of a module image started by `*` commands ("Step 3, as built: the ROM form"), and step 4: the compiler compiles itself on the B+128 at its full capacities, from the ROM and from the RAM module ("Step 4, as built"), and step 5: the linker in the same image, started by `*LLINK`, so that a program is compiled, linked and run on the B+128 with every file the host's tools write ("Step 5, as built"), and file names for the DFS: with `define BBCFS 1` the BBC's build maps every name the tools give to an Acorn DFS name, and the chain and the self-compile run so under the emulator's DFS rules ("File names on the BBC", 2026-11-16); and ADFS as a second filing system: with `define BBCFS 2` ADFS's names and with `define ADFS 1` the tools at ADFS's PAGE, `$1F00`, so that the compiler is rebuilt on two ADFS discs with readable sources and every file the host's ("ADFS", 2026-11-17); and the module's eight-bank form for one 128 KB EPROM, with the gate that says by how many bytes the two tools do not fit it yet ("The 128 KB module", 2026-11-17). This is the first period machine of stage 12 in [`build-plan.md`](build-plan.md).

## The idea

The owner's proposal: the compiler and the linker in **one sideways ROM socket**, in a module that carries its own bank switching, with the compiler's tables in the B+128's 64 KB of sideways RAM and the rest in main RAM. A developer uses a module that holds RAM in place of the ROM, loaded from disk, so that nothing is burned while the tools change.

## The hardware assumed

| Part | What it is |
|---|---|
| CPU | 6512A, an NMOS 6502, 2 MHz |
| Main RAM | `$0000-$7FFF`. Zero page `$00-$8F` belongs to the current language; `$0400-$07FF` is the language's workspace; a program has PAGE to HIMEM, `$1900-$7BFF` with DFS in mode 7 (25,344 bytes) |
| Sideways window | `$8000-$BFFF`, one of sixteen slots chosen by ROMSEL at `$FE30`, with its copy at `$F4` |
| Sideways RAM | four 16 KB slots (0, 1, 12, 13 on the B+128) |
| The module | one slot; sixteen 16 KB banks of ROM (256 KB) behind it, or eight (one 128 KB EPROM: "The 128 KB module") |

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
4. The compiler: `expr` split, the placement, the budget measured. The symbol table behind accessors if that is what stands between. The test programs, then the compiler compiling itself. **Done (2026-11-15)**: "Step 4, as built".
5. The linker in the same module, at the capacities that fit. **Done (2026-11-15)**: "Step 5, as built".

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
- **Since the symbol table is in a region** (2026-11-15, [`configurations.md`](configurations.md), "The symbol table in a region"): `compiler-bbc-bank.env` puts `SYMS` in sideways slot 0 (bank 34, value `$00`) and `OUTTAB` and `WANTS` in slot 1 (bank 35), and places `parts` in bank 3; OUT's functions with a block of `OUTTAB` are kept fixed (DECL's with `WANTS` too, where linked). gentest's fixed code now ends at `$4866` and its variables at `$5CCF` in the small build. At the full capacities **all four fit**, with the fixed variables from `$3C30` (outtest), `$4080` (regtest), `$4130` (condtest) and `$4870` (gentest, `$48B0` since 2026-11-18, when FBUF's pass that leaves out the stores nothing reads made its fixed code 47 bytes longer; `$43B0` with the kept modules placed), and every section of their scripts gives what the twin gives at its own capacities (`test_bbc_bank_src.py`, `FULL_SPLIT`). `rt_bbc.map` has no test for the value 0, which `rt_bank` treats as a fixed region: on the BBC it is slot 0.
- `MAX_BANKS` in the linker is 16, banks of all windows together. The sixteen-bank test uses all of them; the whole compiler on the BBC was expected to need it raised; as built in step 4 it uses nine (five banks of the module and the four slots).

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

So the reserved bytes are 80; a program's banks are linked with the window `$8050-$BFDF` (`bbc-rom.env`), and `$BFE0-$BFFF` of every bank hold nothing ($FF) in this image (in the eight-bank one, pieces copied may run to `$BFEF`: "The 128 KB module"). For any service call but 4 and 9 the code changes only the flags; for 4 and 9 a command the module does not know, and `*HELP`, go back to the bank they came in, so an unknown command a tool passes to OSCLI from a bank of the module returns there. Bank 0 holds, from `$8050`, its code (416 bytes), the command table, the `*HELP` text and each command's copy list, then the programs' resident parts and their regions' constants as far as they fit; the rest goes in the banks no program's code is in, in order.

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

**The developer's form.** `*RUN LOADMOD IMAGE [SLOT]` (`loadmod.asm`, 459 bytes at `$1900`, 407 until it took the short image; `bbcrom.py --loader FILE` writes it and its `.inf`): for each bank, OSGBPB reads 16 KB into `$2000-$5FFF` (on a real machine the filing system is a ROM in the window while it runs, so it cannot write the module), then the module's slot is selected, the bank latched and `$8000-$BFDF` copied by pages (so that no `STA (zp),Y` makes its dummy read in the switching addresses), and `$F4` and ROMSEL put back; at the end bank 0's type (`$8006`) goes into the ROM type table (from OSBYTE 170) at the slot. The MOS then offers the module service calls without a reset. A missing file, a slot over 15, and a file that is empty or ends inside a bank (`Not a module image (too short)`) are errors.

**The short image** (2026-11-16). `bbcrom.py --short FILE` (`image(..., short=FILE)`) also writes banks 0 to the last one in use (bank 0, a program's code, or what bank 0 copies), and the listing ends with `banks in use: 0 to N`. LOADMOD takes it: when OSGBPB reads nothing at the start of a bank after bank 0, the file has ended, and each bank from there to 15 gets the reserved bytes alone (`$8000-$804E` as the last bank read had them, its own number at `$804F`), so that every bank still holds the header and service code whichever bank the latch is at; the rest of such a bank is left as it was. The EPROM's image stays 256 KB. `test_bbc_rom.py` loads the short image (banks 0 to 5 there) with the latch at bank 13 at power on, runs the three commands, and latches bank 14 from a program and makes a service call, which bank 14's header passes on (with the header left out, that run fails).

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

## Step 4, as built: the compiler compiles itself

`lathe/src/lathec-bbc.env` and `lathe/tests/test_bbc_selfhost.py`; the recipe is in [`boards.md`](boards.md), "The compiler on the BBC". **Done (2026-11-15)**: the Lathe-written compiler, at its full capacities (`SMALL 0`), compiles its own seventeen modules and `sys` on the emulated B+128 with `--bbc-strict`, each to object and interface files byte-identical to the host compiler's, with the same status and output, in all three forms: the ROM form (`*LATHE OPTIONS NAME.lth .` from a module image), the same image in the module's RAM form through `*RUN LOADMOD MODULE`, and the developer's form (`*RUN LATHEC ...`, the banks loaded at start-up). Before each run `*LOAD` fills zero page, `$0400-$06FF` and `$1900-$7BFF` with bytes that are not 0.

### The layout

One environment for both forms; `bbcrom.rom_env` makes the ROM form's (banks 1 to 5 of the image, `rom`, the window `$8050-$BFDF`). Measured from the maps (2026-11-15); a bank's code and constants are its file, its variables are in the bank only in the RAM forms (in the ROM form they are in main RAM):

| Where | What | Bytes used | Free |
|---|---|---|---|
| Bank 1 | `expr` alone | 14,756 (+ 411 of variables in RAM) | 1,516 ROM, 1,185 RAM. As the linker judges it, before zero page shrinks the code: 15,717 of 16,272 (ROM), 16,133 of 16,352 (RAM) |
| Bank 2 | `gen` 12,405, `lathec` 1,022; constants 186 | 13,613 (+ 755) | 2,659 ROM, 1,984 RAM |
| Bank 3 | `decl` 9,406, `parts` 1,988, `out` 1,646; constants 82 | 13,122 (+ 783) | 3,150, 2,447 |
| Bank 4 | `reg` 7,233, `inlines` 5,278; constants 22 | 12,533 (+ 733) | 3,739, 3,086 |
| Bank 5 | `asmblock` 3,623, `cond` 2,479, `lex` 1,417, `kernel` 1,384, `fold` 1,299, `typetab` 947, `fbuf` 451, `src` 289, `err` 52; constants 502 | 12,443 (+ 1,084) | 3,829, 2,825 |
| Slot 12 | the name heap (`NAMES`) | 9,216 | 7,136 |
| Slot 13 | err's messages (constants, 5,494), fbuf's buffer and labels, lex's string, kernel's saved tokens (`MSGS`, `FUNCBUF`, `STRING`, `TOKENS`, 8,960) | 14,454 | 1,898 |
| Slot 0 | kernel's symbol and member columns (`SYMS`) | 10,384 | 5,968 |
| Slot 1 | OUT's table and its fix-ups, DECL's import rows (`OUTTAB`, `WANTS`) | 5,696 | 10,656 |
| Main RAM, ROM form | code `$1900-$4FA0`: functions 11,863 (10,237 of them kept fixed: kernel 4,220, fbuf 3,188, lex 1,023, decl 675, err 556, out 487, src 88; the rest `bbc` 670, `rt_bbc` 402, `rt_math` 353, `sys` 76, `rt_frame` 42, start-up and `$init` 68, `disk` 15), stubs 1,752 (292), constants 370; variables `$5000-$7893` (10,388, frames included); `$0401-$06FF` unused | 24,373 of 26,111 | **1,738** |
| Main RAM, RAM forms | code to `$4FE6` (the loading and `$banks` add 70 bytes); variables `$5000-$69DD` (6,622) | 20,677 | 5,434 |
| Zero page | `$00-$8F` | all 144 bytes | 0 |
| Image | bank 0: the module's code (468 bytes), slot 13's constants (5,494) and the first 10,310 bytes of the resident part; bank 6: the rest of it (3,675); banks 7 to 15 empty | | 158,931 bytes |

The split between code and variables is `$5000`, set by the developer's form, whose code is longest (25 bytes left there).

**What stood in the way, and what was done.**

1. *The symbol table in main RAM*: done before this step ([`configurations.md`](configurations.md), "The symbol table in a region"); this step gives `SYMS` slot 0 and `OUTTAB` and `WANTS` slot 1 (step 3's test programs too: "Step 3, as built").
2. *`expr` did not fit a bank as the linker judges it.* The linker judges a bank by its code as written, before zero page promotion shrinks it, and counts every variable placed there ("Sizes" in `configurations.md`), so that whether a program links does not depend on what zero page took. `expr` was 15,229 bytes as placed but 16,299 as written: 27 bytes over the ROM form's 16,272, and with its variables 375 over the RAM form's 16,352. Seven functions of EXPR that reach no cycle of its calls and are called seldom moved to `parts`, in host and twin, with their four variables: the six DECL called (`new_name`, `region_name`, `not_in_region`, `zp_class`, `no_record`, `layout`) and `lasting_variable`, which now takes the name of the function a `static` variable is of (0 for a module's) instead of reading `expr.function`. `expr` is 15,717 as written. The compiler's output is unchanged: every identity test, the self-compile on Wendy 2 and on the BBC, and the corpus give the same files.
3. *A fault: `sys.files` was used before it was set.* The table of open files has no initial value, and memory holds whatever was there: after `LOADMOD` (whose buffer is `$2000-$5FFF`), or on a real machine after BASIC, every entry was taken, so `sys.open_in` refused the source (error 62) and `sys.exit` closed handles that were not open (`Channel`). Found by the loader form; the test now fills memory before every run. The initial value `[0]` would cost a function (`sys.$init`), and the compiler then links 801, one over the linker's limit (`lk_tab.MAX_FUNCS`, 800, link error 11). On the BBC the table is not needed: the MOS keeps the handles (15, as the table held) and `bbc.exit` closes every file (OSFIND 0, Y=0), so with `PORTS 2` `sys` has no table, `open_in` and `open_out` give the MOS's handle, and `close` and `exit` call `bbc`'s: 114 bytes less, two functions fewer. On the other machines the table now starts empty by its initial value `[0]` (2026-11-16, when every test began to run on memory that is not 0: `sys.$init`, on Wendy 2 and the default machine, where the compiler links fewer functions than the limit).
4. *The emulator's names*: the compiler joins its directory and a name with `/` (`./err.lo`), which the emulator's filing system refused as `Bad name`. It now drops a leading `./` (`emulator/README.md`, with a C test); any other `/` is still refused.

**The linker's function limit.** The compiler on the BBC links 798 functions of 800. Not raised: the first try of the fault above reached 801, and the fix that was chosen removes two. The next three functions anywhere in the compiler need it raised first: each function costs the linker 7 bytes of tables (`fn_flags`, `fn_ctx`, `fn_class` 1 each, `fn_slot`, `fn_edge` 2 each), and its tables are at their ceiling (54,144 bytes, `test_lk_memory.py`). (Raised in step 5 to 896, 672 bytes: [`architecture.md`](architecture.md), "Memory in the linker".)

### Measured: the self-compile

`LATHE_BBC_SELFHOST=1 LATHE_BBC_SELFHOST_REPORT=1 python3 -m unittest test_bbc_selfhost` (2026-11-15): CPU cycles of each compile in the ROM form, from the `*` command to the end; far calls and `with` blocks from the counting copy (the developer's form with rt_bbc's `call` and `map` counting); file traffic from the emulator's exit report; Wendy 2's from `bank_report.py --selfhost` on the same sources (`compiler-bank.env`, `SYMS` fixed there).

| Module | BBC cycles | Wendy 2 cycles | | BBC far calls | Wendy 2 | Blocks (BBC; Wendy 2's are 7 fewer in each) | Files opened | Bytes read | Bytes written |
|---|---|---|---|---|---|---|---|---|---|
| err | 18,534,177 | 19,903,901 | −6.9 % | 9,599 | 4,063 | 26,605 | 5 | 17,907 | 11,322 |
| kernel | 57,732,061 | 51,208,121 | +12.7 % | 47,024 | 12,815 | 54,100 | 6 | 41,655 | 31,603 |
| src | 9,688,684 | 12,028,360 | −19.5 % | 4,831 | 1,678 | 12,869 | 7 | 10,243 | 2,986 |
| lex | 38,007,169 | 35,498,855 | +7.1 % | 30,041 | 10,988 | 43,018 | 8 | 29,247 | 13,347 |
| typetab | 14,457,295 | 15,773,838 | −8.3 % | 10,511 | 3,805 | 16,199 | 4 | 11,253 | 5,602 |
| fold | 17,110,035 | 18,036,053 | −5.1 % | 12,657 | 4,392 | 18,560 | 5 | 10,894 | 7,040 |
| fbuf | 43,120,735 | 39,607,241 | +8.9 % | 34,113 | 11,008 | 40,964 | 7 | 36,340 | 19,696 |
| out | 28,682,769 | 27,663,925 | +3.7 % | 20,447 | 6,531 | 34,333 | 8 | 21,813 | 13,281 |
| reg | 90,352,752 | 77,079,699 | +17.2 % | 80,786 | 24,628 | 99,365 | 10 | 59,455 | 37,259 |
| cond | 35,055,822 | 32,345,725 | +8.4 % | 29,013 | 8,522 | 42,140 | 8 | 25,060 | 12,304 |
| gen | 149,435,671 | 125,189,871 | +19.4 % | 129,573 | 37,379 | 168,783 | 13 | 88,189 | 60,666 |
| asmblock | 53,541,164 | 48,227,347 | +11.0 % | 42,739 | 13,603 | 60,232 | 14 | 41,357 | 19,217 |
| inlines | 67,229,333 | 59,358,737 | +13.3 % | 53,495 | 16,355 | 77,987 | 13 | 48,019 | 26,123 |
| parts | 35,417,799 | 33,721,893 | +5.0 % | 22,705 | 7,386 | 52,303 | 16 | 29,999 | 11,708 |
| expr | 121,311,645 | 105,328,923 | +15.2 % | 84,337 | 24,108 | 142,228 | 19 | 72,971 | 67,590 |
| decl | 125,951,683 | 106,795,823 | +17.9 % | 104,185 | 30,559 | 148,816 | 17 | 80,128 | 51,206 |
| lathec | 20,421,858 | 21,259,525 | −3.9 % | 12,541 | 4,368 | 29,112 | 18 | 20,891 | 5,872 |
| sys | 6,895,683 | 9,299,830 | −25.9 % | 3,862 | 1,463 | 5,439 | 4 | 8,920 | 1,468 |
| **total** | **932,946,335** | **838,327,667** | **+11.3 %** | **732,459** | **223,651** | **1,073,053** | **182** | **654,341** | **398,290** |

- **7.8 minutes at 2 MHz** for the whole self-compile in the ROM form (Wendy 2: 7.0 at the same clock), before what the filing system costs. The developer's form takes 1,024 million cycles: each run loads the five banks and slot 13's constants through `bbc.read` (71,961 bytes, about 5 million cycles); through `LOADMOD`, 1,009 million (the loader reads 262,144 bytes, about 4.2 million cycles, then the start is the ROM form's).
- **Far calls**: 3.3 times Wendy 2's. On Wendy 2 `gen` and `reg` share a bank of 28 KB, `parts` sits beside `expr`, and `kernel`, `lex`, `fbuf`, `src` and `err` are fixed; here a bank is 16 KB, so GEN's calls of REG, EXPR's of PARTS and everyone's of LEX's and FBUF's functions in bank 5 are far. At about 190 cycles each, the 508,800 more far calls are 97 million cycles, more than the whole difference: the small compiles (`src`, `sys`, `err`) are faster than on Wendy 2, because a block of a sideways slot costs 64 to 79 cycles where one of a data bank costs 94, and the start does not load banks.
- **One placement tried for speed**: with `lex` fixed and `fbuf` beside `reg` in bank 4, compiling `gen.lth` makes 108,438 far calls instead of 129,573 and takes 144.8 million cycles instead of 149.4 (−3 %); it fits, but leaves 266 bytes of main RAM instead of 1,738. Not taken: the room is worth more than 3 %.
- **Blocks** are Wendy 2's and 7 more in each compile (the compiler's own work); the BBC's `rt_bbc.map` has no test for a fixed region, and none is fixed here.

**The start-up of the ROM form.** `*LATHE` with no arguments (the usage error) takes 1,467,524 cycles from the command to the end, 0.73 s at 2 MHz; most of it is bank 0's copier: 13,985 bytes of the resident part to main RAM at about 60 cycles a byte and 5,494 bytes of messages to slot 13 at about 80, about 1.28 million cycles. The developer's form's start takes 6,596,519 cycles (the loading through `bbc.read`), the loader's 5,680,443 (`LOADMOD`'s copy, then the ROM form's start).

**What the emulator's MOS does not charge for.** A file call costs the 6502 code around it and 2 cycles of the MOS's own; a real MOS and DFS spend hundreds of cycles a byte through OSBGET and OSBPUT, and the disc its own time. The table above gives the traffic of each compile (the exit report's `files:` line, `emulator/README.md`): the self-compile opens 182 files and reads 654,341 bytes and writes 398,290, byte by byte through OSBGET and OSBPUT. At 1,000 cycles a byte that would be another 1.05 billion cycles, 8.8 minutes, more than the compiling; a real figure needs a real DFS (below).

### The corpus on the BBC

`LATHE_LATHEC_BBC=1 python3 -m unittest test_src_lathec.OnTheBBC` (30 s): every input `test_src_lathec.py` has, compiled in the ROM form against `lathec.py` at full size, with the host's error output joined to its output. **705 of the 708 agree.** The three that cannot are the BBC's: a source in a directory and an import directory (`sub/m.lth`, `lib/k.li`: the filing system has no directories, a name with `/` is `Bad name`, caught as a file that is not there), and the input whose command line is 248 bytes, more than the 239 `*LATHE` copies.

## Step 5, as built: the whole tool chain on the BBC

`lathe/src/linker-bbc.env`, the two tools in one image (`bbcrom.py`, unchanged), and the tests `lathe/tests/test_bbc_toolchain.py` and `test_lk_unset.py`; the recipe is in [`boards.md`](boards.md), "The tool chain on the BBC". **Done (2026-11-15)**: one module image holds the Lathe-written compiler (`*LATHE`, banks 1 to 5) and the Lathe-written linker (`*LLINK`, banks 6 to 10). On the emulated B+128, `--bbc-strict`, in one run of the emulator, every module of a program (its own, `lathe/rt/bbc/host.lth`, `bbc`, `sys` and the run-time modules its code calls, in the order and with the options `build.py` uses) is compiled by `*LATHE`, the objects are linked by `*LLINK ENV MAIN IMAGE IMAGE.map OBJECTS...` with the environment file read from the disc, and the image is run with `*RUN`: the output is the expected one, and every object file, interface file, image, bank file and map is byte for byte what `lathec.py` and `link.py` write from the same inputs.

- **The corpus**: 68 of the 69 programs the BBC runs (66 cases of `e2e`, and `farcall`, `bankdata` and `regions` of `e2e-config` with `bbc-bank.env`, which run from the module's RAM form: `*RUN LOADMOD MODULE` first, and the program's start-up code loads its banks over the tools'). The 69th, `for_ranges`, is refused by the linker on the BBC with link error 10, as the host linker refuses it at the same capacities (below). `test_bbc_toolchain.py` runs four by default (15 s, with outtest's link) and all with `LATHE_BBC_TOOLCHAIN=1` (90 s).
- **The compiler's test programs**, compiled by the host as `test_bbc_bank_src.py` builds them, linked on the BBC: `outtest` as the host links it (image, map and five bank files); `regtest` is refused with link error 10, as by the host at the BBC's capacities.
- **The image's addresses.** The linker writes the image's bytes, as the host linker does; the load and execution addresses are the filing system's (the `.inf` file `build.py` writes on the host). On the BBC `*LOAD IMAGE 1900` and `*SAVE IMAGE 1900 +LENGTH 1900` give them, as on a real DFS, and `*RUN IMAGE` runs it.
- **Memory.** The emulator starts with RAM filled with bytes that are not 0 (`--fill-ram`, which the tests pass to every run); the first tool runs on that, and each tool, and the program, on what the one before left. (Until 2026-11-16 `*LOAD` filled it, and the corpus's programs, some of which then relied on 0, ran on 0s loaded before `*RUN`; they now give their variables initial values.)

### The layout

The image (2026-11-15; `bbcrom.py`'s listing), 69,254 bytes free:

| Bank | What | Bytes |
|---|---|---|
| 0 | the module's code and tables (both commands); the compiler's slot 13 constants; the first part of the compiler's resident part | 495 + 5,494 + 10,283 |
| 1 to 5 | the compiler (step 4) | 14,756, 13,613, 13,122, 12,533, 12,443 |
| 6 | `link`, `lk_err` (its messages, 2,946, are constants of the bank: only `lk_err` reads them), `lk_file`, `lk_envf` | 7,825 |
| 7 | the reading: `lk_scan`, `lk_name` | 9,432 |
| 8 | `lk_graph`, `lk_win`, `lk_boot` | 8,122 |
| 9 | `lk_alloc` | 8,671 |
| 10 | placement and output: `lk_place`, `lk_fix`, `lk_map`, `lk_emit`, `lk_out`, `lk_op` | 10,514 |
| 11 | the rest of the compiler's resident part, 3,702; the linker's resident part, 8,404 | 4,166 free |
| 12 to 15 | empty | 65,088 free |

A bank is 16 KB where Wendy 2's are 28: `lk_graph` and `lk_alloc`, which share bank 2 on Wendy 2, are 17.6 KB as the linker judges them (before shrinking), so the linker takes five banks. `lk_alloc` calls `lk_graph`'s edge functions across banks in its layouts.

Main RAM while `*LLINK` runs (the ROM form):

| Where | What | Bytes |
|---|---|---|
| `$1900-$39D3` | code: `lk_tab` 5,591, `bbc` 673, `lk_rec` 407, `rt_bbc` 402, `rt_math` 290, `lk_sym` 214, `lk_name` 187 (`local_at`, `set_local` and `global_sym`, kept fixed: they have `with` blocks), `sys` 78, `$init` 46, `$start` 19, `disk` 15; 77 stubs (462); constants 20 | 8,404 |
| `$3A20-$7BFF`, `$0401-$05B9` | variables: the work area (9,440), the functions' columns but `fn_edge` (2,240), the variables' and constants' (1,600), the classes', members' and class parameters' (about 1,400), `lk_envf.text` (384), `lk_file.path` and `bbc.arg_text` (256 each), the rest | 17,305 |
| | free: 76 bytes below the variables, 326 at `$05BA-$06FF` | 402 |
| zero page | `$00-$8F` | all |

The developer's form (`*RUN LLINK`, banks loaded into the RAM module) sets the split: its code ends at `$3A19`, 6 bytes below the variables, and the banks' 439 bytes of variables are in the banks. Sideways slot 0 holds the regions, 13,952 of 16,352 bytes: `lk_name.local` 4,000, `lk_tab.edge_word` 4,000, `slot_sz` and `slot_weight` 2,400 each, `fn_edge` 896, `big_slot` and `big_size` 256. Slots 1, 12 and 13 are not used by the linker; slot 13's constants are the compiler's, copied again at each `*LATHE`.

### What stood in the way, and what was done

1. *The linker as it was did not fit.* At the small build's capacities (`LKSMALL 1`) its tables in main RAM and its resident part need 30,694 bytes in the ROM form, 4,583 more than the 26,111 there are (the developer's form, whose banks hold their modules' variables, 1,414 more). Measured in a copy with only the capacities changed, the linker as it was fits at 260 functions, 640 slots, 600 calls, 340 nodes, 260 variables and constants and 700 symbols in object files, with 415 bytes to spare; that would not link `for_ranges` and four other cases of the corpus, and the work area cannot be much smaller (the names some file defines are 32,768 bits of it while the files are first read: 333 nodes at least). Not committed.
2. *The tables only `lk_tab` and `lk_name` read went into regions.* `lk_name.local` (region `LKLOCAL`), `lk_tab.edge_word` and `fn_edge` (`LKCALLS`), `slot_sz`, `slot_weight`, `big_slot` and `big_size` (`LKSLOTS`). Other modules reach them only through functions, in host and twin: `lk_name.local_at`, `set_local`; `lk_tab.edge_at`, `set_edge_at`, `slot_weight_of`, `set_slot_weight`, `set_slot_zp`, `flip_slot_zp`. `lk_tab` is fixed, and `lk_name`'s three functions with blocks are kept fixed by the linker's rule; `global_sym`, which the later phases call once a fix-up, is then a plain call where it was the largest share of the far calls. The linker's output is unchanged (`test_src_lk.py`, `test_src_link.py` with `LATHE_LK_ALL=1`). On Wendy 2 (`linker-bank.env`) the regions are fixed, since no `region` entry names them, and the layout still fits; on the default machine (`linker.env`) `lktest4`'s code grew by 254 bytes, so the split moved up and `$F240-$FDFF`, the RAM between the host services' routines and the arguments, holds variables.
3. *The BBC's capacities*, `define LKSMALL 2`, a third set of the twins' capacities (`#if LKSMALL == 2` before the small build's), which `lk_small.load('bbc')` gives the host modules: 448 functions, 2,400 slots, 2,000 calls, 472 nodes, 320 variables and constants, 360 fix-ups of one function, 2,000 symbols in object files, promotion's list 64. They fill main RAM (402 bytes left). The work area's phases bound them: below the node columns the fix-ups held and then the names of one file while the image is written, `6 × (472 − 360) − 128 = 544` words, at least the small build's 496; the calls' chains, `256 + 2 × 2,000 + 448 ≤ 10 × 472`; `test_src_lk.py` checks both for the three builds. A first choice, 448 fix-ups, left 16 words for one file's names and refused all but two programs of the corpus (link error 10, on the host at the same capacities too).
4. *A fault: rows of the linker's tables were read before anything wrote them.* Python's tables start as 0s; the twin's hold what memory held. On the BBC, after the compiler, the first link looped in `lk_tab.class_of` through a junk `fn_class`. `fn_ctx` and `fn_class` (a new function), `cls_reach` and `cls_namer` (a new class) and `cp_weight` (a new class parameter) are now set when their row is made, in host and twin (no output changes: the host's were 0 already). `test_lk_unset.py` runs the host linker with every table wrapped over the links made by hand and the synthetic program, and fails on any read of a row nothing wrote (1 s); over the whole corpus and the linker tests' links (568 links) nothing else is read so, but for the byte of a work word that `lk_name.put_b` keeps. Wendy 2's emulator cleared memory then, so it never showed; every test now runs on memory that is not 0 (`--fill-ram`), and three more such rows showed in the twins' test drivers (2026-11-16: `lk_win.obj_stub` with nothing placed, a window's `win_reg` and `win_mask` without a bank switch, `lk_tab.cp_addr`).
5. *The emulator*: `--bbc-command` takes 64 lines, not 9 (a run of the tool chain is a line for each compile, the link, `*LOAD`, `*SAVE` and `*RUN`), with its C test.
6. *A fault in a report*: `lk_bank_report.py` counted no far calls since `bank_report.py` began to name the counting file by an argument; it now writes them to a file of a fixed name.

### Capacities, and the largest program linked

(Superseded on 2026-11-16: the linker on the BBC has the full capacities, and links every program of the corpus, `regtest` and the compiler: "The linker links the compiler", below.)

| Capacity | BBC | Bytes | Where | Small build | Full |
|---|---|---|---|---|---|
| functions | 448 | 2,240 + 896 | main RAM (`fn_flags`, `fn_ctx`, `fn_class`, `fn_slot`), slot 0 (`fn_edge`) | 320 | 896 |
| nodes, the work area | 472 | 9,440 | main RAM | 360 | 900 |
| slots | 2,400 | 4,800 | slot 0 | 1,280 | 4,000 |
| calls | 2,000 | 4,000 | slot 0 | 1,200 | 3,600 |
| symbols in object files | 2,000 | 4,000 | slot 0 | 1,400 | 4,000 |
| variables and constants | 320 | 1,600 | main RAM | 320 | 800 |
| fix-ups of one function | 360 | in the work area | | 256 | 512 |
| names kept and the symbols' words, reading | 6,880 bytes | in the work area | | 4,640 | 15,440 |
| one file's names, the image | 544 words | in the work area | | 496 | 2,200 |

- **The largest of the corpus** linked is any but `for_ranges`, which is refused: its one file has 220 functions, whose names the image pass holds at once, about 1,800 words of the work area's 544.
- **The largest of `lathe/src`** linked is `outtest` (239 functions, 640 slots, 491 calls, 351 fix-ups of one function, 366 words of one file's names, 3,161 bytes of names kept). `regtest` (378 functions, 996 slots, 851 calls) is refused: its `reg.lo` needs 787 words of names in the image pass, and a function 380 fix-ups; both are the work area, which would need 533 nodes, 10,660 bytes, 1,220 more than now, where 402 are free. The next cheapest step would be `fn_slot` through functions too (896 bytes) and fewer functions (448 is more than any program the work area takes needs): about enough for `regtest`, not for `condtest`, `gentest` or the compiler.
- **Measured with the host linker at the BBC's capacities** on each program as it is built for the BBC (`lk_small.load('bbc')`): `copytest`, `errtest`, `srctest`, `typetest`, `foldtest`, `lextest`, `fbuftest`, `kerneltest`, `outtest` and `lktest1` link; `regtest`, `condtest`, `lktest2` (one file's names in the image), `gentest`, `inlinetest`, `exprtest`, `lktest3`, `lktest4`, `lathec` and `link` (the names kept while reading), `asmtest` (454 functions) do not.

### What linking the compiler there would take

(Done on 2026-11-16 by the second way, the work area split into two tables in regions: "The linker links the compiler", below. What follows is as it was written.)

The compiler's link (`lathec.lth` with `lathec-bbc.env`, measured by the host linker): 799 functions, 2,438 slots, 3,255 calls, 799 nodes, 374 variables and constants, 2,014 symbols in object files, 361 fix-ups of one function, 13,977 bytes of names kept and symbols' words, 1,019 words of one file's names in the image pass. The regions take the slots, calls and symbols (25 KB at the full capacities: two sideways slots). The work area does not fit: it would need 827 nodes at least (16.5 KB), and with the functions' and variables' columns (8.5 KB at the full capacities) main RAM would hold 25 KB of tables beside 8.4 KB of resident code. So the work area would have to leave main RAM, and it is read in about 200 places in ten modules, from code in every bank of the linker: in a region, each of those would go through a fixed function that maps it, the restructuring `spikes.md` describes ("What stands before the gate of stage 8") for the whole linker, or the work area would be split by phase into tables of their own (the names heap of the reading, the names of the image pass, the graph's and storage's columns), each in a region behind its own module's functions. Besides that, the link's command line is 247 bytes after `LLINK `, more than the 239 the module copies (24 object files; for the linker's own link, 289), and the promotion of zero page for the compiler, which takes about half an hour at 1 MHz on Wendy 2 ([`spikes.md`](spikes.md)), would take a quarter of an hour or more at 2 MHz (the BBC's zero page is smaller, so there are more layouts). That is a redesign; not started.

### Measured: the linker on the BBC

`LATHE_BBC_TOOLCHAIN=1 LATHE_BBC_TOOLCHAIN_REPORT=1 python3 -m unittest test_bbc_toolchain` (2026-11-15): each link alone in the ROM form, from `*LLINK` to its end; far calls and `with` blocks from the counting copy (the developer's form with `rt_bbc`'s `call` and `map` counting); file traffic from the emulator's exit report; the whole run, from the first `*LOAD` to the program's end, for the default four.

| Link | Cycles | Minutes at 2 MHz | Far calls | Blocks | Files opened | Bytes read | Bytes written | The whole run |
|---|---|---|---|---|---|---|---|---|
| hello (3 objects) | 5,669,711 | 0.05 | 364 | 978 | 21 | 23,543 | 130 | 23,428,203 |
| calls (4) | 19,239,629 | 0.16 | 4,534 | 8,943 | 28 | 65,702 | 2,919 | 51,645,000 |
| rec_tree | 21,335,173 | 0.18 | 3,578 | 11,246 | 38 | 77,983 | 2,722 | 52,078,081 |
| reg_args, the longest of `e2e` | 36,260,082 | 0.30 | 7,628 | 18,485 | 38 | 130,243 | 6,488 | |
| farcall, banked | 29,345,992 | 0.24 | 6,427 | 11,374 | 91 | 99,451 | 4,924 | 85,180,040 (with LOADMOD) |
| bankdata, banked | 20,970,776 | 0.17 | 3,921 | 7,479 | 57 | 76,942 | 3,188 | |
| regions, banked | 25,641,869 | 0.21 | 5,069 | 10,156 | 59 | 92,273 | 3,993 | |
| outtest (12 objects, 5 banks) | 282,359,899 | 2.35 | 97,198 | 232,382 | 104 | 753,382 | 40,610 | |

- **The 65 links of `e2e` all in one** take 5.7 to 36.3 million cycles, 14 million at the median: 0.05 to 0.3 minutes at 2 MHz, 8.3 minutes for all of them. A link opens 21 to 44 files and reads 23 to 130 KB.
- **The start-up**: `*LLINK` with no arguments (link error 1) takes 518,031 cycles, 0.26 s, most of it bank 0's copy of the 8,404 bytes of the resident part at about 60 cycles a byte; no region has constants, so nothing is copied to slot 0.
- **Far calls** are 1 to 7 % of a link's cycles at about 190 each (outtest's 97,198: 18 million of 282). `global_sym` is fixed, so what is left is `lk_alloc` calling `lk_graph`'s edge functions in each layout, the later phases calling `lk_scan`'s and `lk_alloc`'s, and `lk_win` calling `lk_envf`. A `with` block of a slot from fixed code costs 64 cycles; outtest's 232,382 are 15 million.
- **What the emulator's MOS does not charge for**: a file call costs the 6502 code around it and 2 cycles of the MOS's own. A real MOS and DFS spend hundreds of cycles a byte; at 1,000 cycles a byte, outtest's 794 KB of traffic would add 794 million cycles, 6.6 minutes, nearly three times the link, and the 104 files it opens their seeks. The linker reads each object file several times (the passes of [`architecture.md`](architecture.md), "Memory in the linker"), so on a real disc reading, not linking, would be most of the time.
- **On Wendy 2** (`lk_bank_report.py`, the regions fixed there): linking lextest takes 114.7 million cycles (109.4 before, +4.8 %: a block of a fixed region costs 32 cycles), with 7,468 far calls (18,159 before: `global_sym` is kept fixed); `lk_synthetic` 247.5 million (242.4, +2.1 %), 20,466 far calls (45,926); `farcall.lth` 22.3 million (22.1), 1,979 far calls (4,027). Its resident part is 8,020 bytes (9,895 when `spikes.md` measured it: `lk_err`'s messages are now in bank 1), with 28 bytes free below the code and 2,028 above it.

## The linker links the compiler (2026-11-16)

The redesign that "What linking the compiler there would take" (step 5) asked for: every large table of the linker is in a region, read only by fixed functions ([`architecture.md`](architecture.md), "The large tables in regions"). The tests are `lathe/tests/test_bbc_selflink.py` (and `test_bbc_toolchain.py`, which now links every program of the corpus).

- **The work area in sideways RAM.** It is two tables, `lk_tab.work` in slot 12 and the node columns `lk_tab.nodes` in slot 1, read through `lk_tab.wk` and `set_wk` and a few functions with blocks of their own, which the linker keeps in main RAM. So main RAM holds 12,936 bytes of the linker's variables, not 17,305, beside 9,006 bytes of resident code (8,404 before), and about 4 KB is free (402 before), room for the DFS build of `bbcfs`.
- **The full capacities.** The BBC's own (`LKSMALL 2`: 448 functions, 472 nodes...) are dropped; `linker-bbc.env` says `define LKSMALL 0`. `for_ranges` and `regtest`, which they refused, now link as the host links them.
- **The slots.** Slot 0: `lk_name.local` and the slots' columns (16,256 of 16,352 bytes). Slot 1: the calls and the node columns (12,592). Slot 12: the work area (14,400). Slot 13 is not used. The slots are free while the linker runs: the compiler's tables are there only while `*LATHE` runs, and its constants in slot 13 are copied again at each `*LATHE`.
- **The command line.** `*LLINK @FILE` takes the arguments from FILE, a word each, separated by spaces or line ends: the compiler's link is 247 bytes, the linker's 283, and the module copies 239.
- **One file written at a time.** The linker writes the image, then each bank's file, then the map: a DFS gives a new file the room up to the next file on the disc, so a map kept open while the others were written could not grow (outtest's is 22,946 bytes). The map's slot lines take a reading of the files of their own.

**The gates**, each in one run of the emulator with `--bbc-strict` on memory filled with bytes that are not 0:

1. `*LLINK @LINKARG` links the compiler as `lathec-bbc.env` describes it (the developer's form, which `*RUN` loads) from the host compiler's object files on the disc: the image, its six bank files and the map are the host linker's (`LATHE_BBC_SELFLINK=1`). The same for the linker itself, as `linker-bbc.env` describes it.
2. The loop (`LATHE_BBC_LOOP=1`): `*RUN LOADMOD MODULE`, then `*LATHE` compiles the compiler's 24 modules from their sources, `*LLINK @LINKARG` links them, `*LOAD` and `*SAVE` give the new image its addresses, and `*RUN LATHEC` (its start-up loads its banks into the module's RAM form, over the tools') compiles `err` and `kernel` again. Every object file, interface, image, bank file and map is what the host tools write. That is the compiler rebuilt on the machine from nothing but its sources and the module image.

| Run | Cycles | Minutes at 2 MHz | Far calls | Blocks | Files opened | Bytes read | Bytes written |
|---|---|---|---|---|---|---|---|
| the compiler's link | 3,404,414,645 | 28.4 | 1,276,282 | 8,704,892 | 234 | 4,009,214 | 210,872 |
| the linker's own link | 1,820,594,317 | 15.2 | 542,247 | 4,618,703 | 231 | 2,483,041 | 135,089 |
| the loop: 24 compiles, the link, 2 compiles | 4,470,843,206 | 37.3 | | | 460 | 5,167,935 | 665,374 |

Far calls are about 7 % of the compiler's link (at about 190 cycles), blocks about 16 % (at 64). The emulator's MOS charges nothing for the 4 MB the link reads; at 1,000 cycles a byte on a real DFS that would be another 33 minutes ("Measured: the linker on the BBC" above).

**Small links cost more.** Against step 5, the corpus's links take 15 to 26 % more cycles, 19 % at the median: `hello` 6.52 million (5.67), `calls` 23.2 (19.2), `reg_args` 43.0 (36.3), `farcall` 34.7 (29.3), `outtest` 330 (282). Blocks are most of it (`hello`: 6,998 blocks, 978 before), the map's own reading of the S lines about 4 points; far calls halved (`outtest` 42,983, 97,198 before), since the functions with blocks are fixed. `*LLINK` with no arguments takes 554,564 cycles (518,031).

**A packer on the BBC.** The ROM image is still made on the host by `bbcrom.py`. A packer on the BBC would read each tool's resident file, bank files and map, and write the sixteen banks: every bank starts with the 80 bytes of header and service code, bank 0 holds the module's code and its tables of commands, resident parts and copies, then the parts as far as they fit. It needs: the module's code from `lathe/rt/bbc/module.asm` as a file of bytes (assembled once on the host, or by a Lathe program, since nothing on the BBC assembles), with the places its tables go known; a buffer of one bank, which a sideways slot is; the map, to find the resident part's length and entry; and somewhere to put 256 KB. A DFS disc holds 100 or 200 KB, so the image would be written as sixteen bank files, or straight into the module's RAM form (as `LOADMOD` fills it) and saved by a ROM programmer. The packer itself would be small, a few KB of Lathe: copying bytes and filling tables. It is not built.

## The 128 KB module (2026-11-17)

The owner wants the compiler and the linker in one 128 KB EPROM: eight banks of 16 KB. This is the layout's part of that: an eight-bank form of the module that can use every byte of the eight banks, and a gate that says how far the tools are from fitting it. **Since 2026-11-17 both tools fit it**, with 5,815 bytes to spare (4,610 in the ADFS build), once their errors' texts went to a file on the disc ("The message file", below; since 2026-11-18 the texts are back in the module, which writes them, and the image has 2,295 bytes free, 1,107 in the ADFS build: "The texts in the module"), the linker was refactored to fit three banks ("The linker in three banks, as built") and the compiler's own code was made smaller ("The tools' banks", "Built instead"). Built: the scheme `direct8` in the emulator, `bbcrom.py --banks 8`, the home bank, the packing, LOADMOD for both schemes, the `ROM128` layouts in `lathec-bbc.env` and `linker-bbc.env`, `lathe/tests/test_bbc_rom128.py` (the gate) and `lathe/tests/farcall_matrix.py` (the far calls between modules, counted on the BBC).

### The form: direct8

The project's own direct scheme, cut to eight banks of one 128 KB EPROM (a 27C010): **a read of `$BFF0+n` selects bank n, n = 0 to 7, from any bank; `$BFF8-$BFFF` mirror `$BFF0-$BFF7`** (a read of `$BFF0+n` selects bank n AND 7). The mirror is the simplest hardware: the latch takes A0-A2 and the decode ignores A3, so the board is the EPROM, a three-bit latch and the comparator of A4-A13 that `direct16` needs anyway. Nothing else switches, so `$8050-$BFEF` of every bank can hold bytes that are read (`$BFE0-$BFEF` only as data: an instruction must not end within a byte of `$BFF0`).

Why this and not `cc128`: the same code as `direct16` works unchanged (`rt_bbc`'s `LDA LATCH-$80,Y` and the module's `LDA $BFF0+n`), every bank has the same room, and every bank can be reached in one read from every other. What `cc128` would take is below.

The emulator: `--bbc-module-scheme direct8` (`emulator/chips/bbc_module.c`; its C tests are in `emulator/tests/test_chip_bbc_module.c`: every address from every bank, the mirror, `$BFEF` and the `cc128` zones not switching, the RAM form, an image of eight banks and one of nine refused; `--bbc-module-bank` is 0 to 7 for it, in `test_cli.c`). `boards.run_module` takes the scheme (`boards.MODULE_SCHEME` when none is given).

### What changed in the module

- **The home bank.** The module's own code and tables (the command table, the copy lists, the `*HELP` text) are in one bank, the home bank, after the code of the program there, at any address. `module.asm` is assembled with two constants before it, `home` and `home_at`: the service code selects the home bank with `LDA $BFF0+home` (an instruction of the reserved bytes, which are the same in every bank), the stub at `$07F0` and the copier end with the same read. So bank 0 can hold a tool's code. In the sixteen-bank image the home bank is bank 0 at `$8050`, as before, and the image is byte for byte what it was (no program may use bank 0 there). In the eight-bank one it is the bank with the most room after its code among the banks the image holds anyway, or the first bank no program uses.
- **The packing.** In the eight-bank image (and in the sixteen-bank one with `--tails`) the resident parts and the regions' constants go in pieces in the room left at the end of every bank, to `$BFEF`: first in the banks the image holds anyway, the one with the most room first, then in the banks after them in order, so that the image uses as few banks as it can. Each piece is an entry of the command's copy list (8 bytes in the home bank; the copier already takes any number, and reads its source with `LDA (zp),Y` with Y = 0, which makes no dummy read, so pieces can run to `$BFEF`). A gap of 8 bytes or fewer is left empty, since its entry would cost what it holds. When things do not fit, `ImageError.over` is the bytes over, counting the entries. The sixteen-bank image keeps its old way (bank 0 to `$BFDF`, then the banks no program uses) so that every existing test passes unchanged; with `--tails` both tools' image takes banks 0 to 10, not 0 to 11 (`test_bbc_dfs.py` checks for twelve).
- **LOADMOD** finds the module's size: it writes 0 at `$804F` of bank 0 and 8 at `$804F` of bank 8, and reads bank 0's again (8 on an eight-bank module, where bank 8 is bank 0). It loads that many banks, copies `$8000-$BFEF` of each (it copied to `$BFDF`), and refuses a file with more banks than the module (`Image too large for the module`). It is 591 bytes (459).
- **rom_env** takes the image's size: `rom_env(SOURCE, OUT, FIRST, 8)` numbers from FIRST (0 allowed), refuses a bank past 7, and sets a source's `define ROM128 0` to 1, so `when ROM128` and `unless ROM128` entries give what differs in the eight-bank form (a `bank` entry under them is renumbered if it is an entry of the result). `rt_bbc.lth` needed no change.

**Tested** (`test_bbc_rom128.py`; every run `--bbc-strict` on filled memory): `bbcrom.layout()` on made-up programs (the home bank, pieces to `$BFEF` in the order of their destination, the bytes over to the byte, the sixteen-bank layout kept unless asked); `test_bbc_rom.py`'s three programs in an eight-bank image numbered from bank 0 (so bank 0 holds `*FIRST`'s code and the home bank is bank 2, after `*FIRST`'s bank 3): each command in every power-on bank, through LOADMOD whole and short in slots 4 and 7, a nine-bank file refused, bank `$88` refused; and the compiler alone in an eight-bank image (banks 0 to 4, the home bank 4 after its code), which compiles modules of `lathe/src` from the ROM and through LOADMOD as the host compiler does (`err`, `src` and `fold` by default; all 18 with `LATHE_BBC_ROM128_SELFHOST=1`).

### The tools' banks

A module of a tool must fit a bank whole as the linker judges it (before zero page shrinks code). Eight banks give the compiler five and the linker three: the compiler is 74,988 bytes as judged (4.61 banks), the linker 50,884 (3.13). So the linker needs a new layout, and it does not fit yet.

**Far calls decide the layout.** `farcall_matrix.py` links a counting copy of a tool with each group of modules in a bank of its own (13 groups for the linker, 11 for the compiler, the developer's form) and counts each pair (where the call comes from, the bank called) in `rt_bbc.call`, fixed memory counted apart. A layout that keeps each group whole has as its far calls the pairs it splits and the calls from fixed memory. Checked against the counting copy that counts all far calls together ("The linker links the compiler" above: 1,276,282 for the compiler's link, 42,983 for outtest's), the five-bank layout's sum is 1,276,580 and 43,015. A far call costs 211 cycles more than a `JSR` and `RTS`: the compiler's link takes 3,410,932,750 cycles in the developer's form in five banks and 3,479,179,312 in thirteen, for 323,378 far calls more (outtest's: 212.9).

In the compiler's link, lk_alloc calls lk_graph 1,150,365 times: 90 % of its far calls, because the five-bank layout has them in banks 4 and 3. Together they are 16,688 bytes as judged, 416 over a bank by themselves.

**The linker in three banks**, all layouts with every module whole, searched over every assignment of the 13 groups (and lk_out and lk_op fixed or not); cycles measured for five banks and estimated for three from the far calls at 211 cycles each, since no three-bank layout links yet:

| Layout | Banks as judged (over) | Far calls, the compiler's link | Cycles, the compiler's link | Far calls, outtest | Cycles, outtest |
|---|---|---|---|---|---|
| five banks (`linker-bbc.env`) | 9,225 / 10,714 / 9,176 / 10,285 / 11,484 | 1,276,580 | 3,410,932,750 measured | 43,015 | 335,198,852 measured |
| **chosen**: link, lk_err, lk_file, lk_envf, lk_win, lk_place, lk_fix, lk_emit / lk_scan, lk_name, lk_boot, lk_map / lk_graph, lk_alloc; lk_out and lk_op fixed | 16,844 (572) / 16,471 (199) / 16,688 (416) | 100,512 | 3,162,800,000 (-7.3 %) | 17,021 | 329,700,000 (-1.6 %) |
| the most even: link, lk_err, lk_file, lk_scan, lk_map, lk_emit / lk_envf, lk_name, lk_win, lk_boot, lk_place, lk_fix / lk_graph, lk_alloc; lk_out and lk_op fixed | 16,696 (424) / 16,619 (347) / 16,688 (416) | 271,898 | 3,198,900,000 | 58,935 | 338,600,000 |
| by phase, lk_graph and lk_alloc apart: link, lk_err, lk_file, lk_envf, lk_scan, lk_win / lk_name, lk_graph, lk_boot, lk_place, lk_fix / lk_alloc, lk_map, lk_emit, lk_out, lk_op | 16,258 / 16,779 (507) / 17,847 (1,575) | 1,429,290 | 3,443,100,000 | 80,893 | 343,200,000 |

The chosen layout is in `linker-bbc.env` under `when ROM128`, with lk_boot moved to bank 1 since ("The linker in three banks, as built"). Fixing lk_out and lk_op (803 bytes as placed) uses the room the code range `$1900-$3FFF` had left (972 bytes) and takes 881 bytes as judged out of the banks; it saves only 1,288 far calls, since lk_emit, their caller, shares their bank. The resident part is 9,767 bytes (9,012 in five banks: lk_out and lk_op, and fewer stubs). With `BBCFS 1` the ROM form puts `bbcfs` in bank 1 as well (`when ROMFORM`), which that build must also make room for.

**The compiler in five banks** fits as it is; the search over every assignment of its 11 groups to five banks that fit found a better one, which `lathec-bbc.env` gives under `when ROM128`: bank 1 expr; 2 gen and lathec; 3 decl and asmblock; 4 parts, out, inlines, kernel, lex, fbuf, src and err; 5 reg, cond, fold and typetab (reg's and gen's calls of fold and typetab were the most of any pair, 98,212 and 71,079). Measured from the eight-bank image, the 18 compiles of the self-compile, every file the host's:

| Layout | Banks as judged | Resident | Far calls (18 compiles) | Cycles (18 compiles, ROM form) |
|---|---|---|---|---|
| five banks as in `lathec-bbc.env` | 15,717 / 15,154 / 15,441 / 14,367 / 14,309 | 13,989 | 733,977 | 945,267,054 |
| **`when ROM128`** | 15,717 / 15,154 / 15,714 / 14,716 / 13,687 | 13,959 | 551,124 | 901,564,042 (-4.6 %) |

(2026-11-17, later: with kernel's sym_find, thaw and freeze in its bank, kernel's bank was over, and `lathec-bbc.env` now has one layout for both images, `parts` and `out` beside `expr` and `asmblock` beside `decl`: banks of 15,466, 15,396, 15,343, 12,342 and 13,648 bytes as judged, 529,452 far calls counted; [`configurations.md`](configurations.md), "Kernel's functions out of fixed memory, and accessors of one column".)

### The account (the gate)

`test_bbc_rom128.py` links both tools for the eight-bank image (the compiler in banks 0 to 4, the linker in 5 to 7) with `lk_judged.py`, so that a tool that does not link is measured too, and lays the image out from what the links give. `test_both_tools_fit_the_128k_image` must pass, and its message says by how many bytes, in all and bank by bank, if it does not; `LATHE_BBC_ROM128_REPORT=1` prints the account. On 2026-11-17, after the message file, the linker's refactoring and the compiler's smaller code (`BBCFS 0`):

| Bank | Tool | Judged | Placed | Left as judged | Left to `$BFEF` | Modules |
|---|---|---|---|---|---|---|
| 0 | LATHE | 15,466 | 14,101 | 806 | 2,187 | expr, parts, out |
| 1 | LATHE | 15,396 | 13,685 | 876 | 2,603 | gen, lathec |
| 2 | LATHE | 15,343 | 13,100 | 929 | 3,188 | decl, asmblock |
| 3 | LATHE | 12,342 | 10,512 | 3,930 | 5,776 | inlines, kernel, lex, fbuf, src, err |
| 4 | LATHE | 13,648 | 12,030 | 2,624 | 4,258 | reg, cond, fold, typetab |
| 5 | LLINK | 15,309 | 13,248 | 963 | 3,040 | lk_envf, lk_emit, lk_place, lk_fix, lk_boot, lk_win, lk_file, lk_err, link |
| 6 | LLINK | 15,079 | 12,556 | 1,193 | 3,732 | lk_scan, lk_name, lk_map |
| 7 | LLINK | 16,031 | 13,060 | **241** | 3,228 | lk_alloc, lk_graph |

Copied at the commands: the resident parts, the compiler's 11,849 bytes and the linker's 9,829 (nothing for slot 13: its messages are in the file). In use: 102,292 bytes of code banks and 21,678 copied, **123,970 of the 130,304** the eight banks hold to `$BFEF`; with the module's code and tables (519 bytes, in bank 3) and seven pieces, **5,815 bytes free**. The fullest bank as the linker judges it is the linker's bank 3, lk_alloc and lk_graph, 241 bytes below the 16,272 a bank holds.

**The ADFS build** (`BBCFS 2`, `ADFS 1`, the owner's): `bbcfs` goes in the compiler's bank 5 (14,273 judged) and the linker's bank 1 (15,934 judged, **338 left**: the fullest in that build), the resident parts are 11,909 and 9,897; in use 125,167, **4,610 free**.

**Since 2026-11-18, the texts in the module** ("The texts in the module", below): the linker's bank 1 is 15,225 bytes as judged (1,047 left; 15,850 and 422 left in the ADFS build), the other banks as above; the resident parts are 11,686 and 9,811 bytes (11,746 and 9,877 in the ADFS build); the module's code and tables, now with the packed texts of both tools' errors, 4,291 bytes in bank 3, and eight pieces: in use 123,718 and the module's code, **2,295 bytes free** (**1,107** in the ADFS build).

(With the message file and the linker's work alone, on 05824fd's compiler: 125,254 in use, 4,523 free, 3,326 with ADFS.)

Before (2026-11-17, 05824fd): 134,224 bytes in use, 4,463 over, the linker's banks 572, 199 and 416 over as judged, so it did not link (link error 45).

What the packing recovered: the sixteen-bank image of both tools left 53,013 bytes unused at the ends of its ten code banks; in the eight-bank layout every one of those bytes can take a piece, and `$BFE0-$BFEF` of each bank (128 bytes in eight banks) is room it did not have. What the eight banks cannot use: the reserved bytes (80 a bank), 16 bytes at the top of each, 8 bytes an entry, and gaps of 8 bytes or fewer.

### The linker in three banks, as built

With `lk_err`'s texts in the file, the linker's bank 1 was 13,917 bytes as judged, 2,355 below a bank; banks 2 and 3 were still 199 and 416 over. In host and twin alike, the output unchanged (`test_src_lk.py`, `test_src_link.py`, the linker's host tests, and the gates that compare every file the Lathe-written linker writes with the host's), judged bytes of the bank:

| Change | Bank | Judged |
|---|---|---|
| `lk_tab.add_wk` and `sub_wk` for the seven read-modify-writes of work words in `lk_alloc` (`lk_tab` is fixed: 56 bytes of main RAM) | 3 | -224 |
| `lk_alloc.each_candidate(weight, how)`, one walk over the candidates of a weight that moves them in, out, or tries them, for `move_weight` and `try_slots`, `try_cparams` and `try_vars`, which walked the same three sets | 3 | -280 |
| `lk_alloc.larger` for `deepest`'s three maxima, each of which worked its sum out twice, and the second word of a list entry read once | 3 | -89 |
| `layout_set`: `larger` for its start, and each node read from `order` once a loop | 3 | -27 |
| `keep_in_object`: a fix-up's symbol read from the work area once, not three times | 3 | -33 |
| `lk_boot` in bank 1 (`when ROM128 place lk_boot WIN 1`): its callers are lk_emit and lk_place, there, and it calls lk_win and lk_envf, there too | 2, 1 | -1,392, +1,392 |

Bank 3 went from 16,688 to 16,031, bank 2 from 16,471 to 15,079, bank 1 from 13,917 to 15,309. Not needed: merging `lk_map.decimal` into `lk_err.put_word` (they write to different places, the map and the error output, so one would take where to write, and lk_map is in another bank: a far call for every number of the map).

**Cycles, from the eight-bank image** (`LATHE_BBC_ROM128_SELFHOST=1`, `_SELFLINK=1`, `_LOOP=1`, `_ADFS=1`; every file the host tools'), against the sixteen-bank image's of 05824fd, and before and after the compiler's smaller source was merged (2026-11-17):

| What | Sixteen banks (05824fd) | Eight banks, the message file and the linker's work | Eight banks, merged |
|---|---|---|---|
| the self-compile, the ROM form (18 compiles) | 946.6 million | 897.7 million (935.7 through LOADMOD) | **877.0 million** (915.0 through LOADMOD) |
| the linker links the compiler | 3,407 million | 2,961 million | **3,463 million** |
| the rebuild loop (25 compiles, the link, two compiles by the new compiler) | 4,345 to 4,481 million | 4,008 million | **4,484 million** |
| the rebuild on two ADFS discs, `BBCFS 2` and `ADFS 1`, the message file on drive 0 | 4,510 million | 4,026 million | **4,504 million**, 37.5 minutes at 2 MHz |

The eight-bank image is faster for the far calls its layout keeps in one bank (lk_alloc's calls of lk_graph, and now lk_boot's) and for the shorter start-up (below). The merged tree's compiler is a larger program to link: kernel's column accessors and name functions are hundreds of short functions and thousands of calls more for the linker to read, place and promote, so its link costs 502 million cycles more than before them (the merged tree's loops in the sixteen-bank image: 4,814 million under DFS names, 4,822 million on two ADFS discs). On the two ADFS discs from the 128 KB image: at most 2 files open and 1 written, at most 25 entries in a directory.

### Start-up

Each command copies its pieces a byte at a time with a bank switch a byte, as before; a piece more costs an entry's walk (about 150 cycles). `*LATHE` and `*LLINK` with no arguments, before (2026-11-17, the sixteen-bank image) and after:

| Image | `*LATHE` | `*LLINK` |
|---|---|---|
| sixteen banks, before | 1,467,942 | 554,928 |
| sixteen banks, now (the same bytes) | 1,467,942 | 554,928 |
| sixteen banks with `--tails` (banks 0 to 10; `*LLINK` copies 2 pieces, not 1) | 1,467,942 | 555,088 |
| eight banks, the compiler alone (`when ROM128` layout, banks 0 to 4) | 1,466,112 | |
| eight banks, the linker alone in its five banks (banks 0 to 4) | | 554,975 |
| sixteen banks, the messages in the file (2026-11-17; the usage read from it) | 978,160 | 563,528 |
| the same with the compiler's smaller code (the merged tree) | 861,628 | 563,532 |
| eight banks, both tools, the merged tree | 861,934 | 607,461 |
| eight banks, both tools, the texts in the module (2026-11-18; the usage from the module) | 852,232 | 651,777 |
| sixteen banks, the same | 852,082 | 610,315 |

The compiler's start-up is 495,310 cycles shorter without the 5,494 bytes it copied to slot 13 ("The message file"). The linker in three banks copies its larger resident part (9,829 bytes: lk_out and lk_op are fixed there).

### What `cc128` would take

The Computer Concepts carrier (the emulator's `cc128`, as MAME models it): a read of `$BFE0` selects bank 0 from any bank; only while bank 0 is selected, a read in `$BFC0-$BFDF` selects bank 1, `$BFA0-$BFBF` bank 2, ... `$BF00-$BF1F` bank 7. It is a real board, which `direct8` is not. For Lathe:

- **Switching.** Bank n from any bank is two reads: `$BFE0`, then `$BF00 + (7 - n) * 32` (for n = 0 that is `$BFE0` again, so one formula serves every bank, and `LDA $BF00,X` with X = (7 - n) * 32 stays in its page). `rt_bbc`'s three switches (call, back and select/unmap) would be `LDA $BFE0` and `LDX`/`LDA $BF00,X` from a table of eight bytes: about 8 bytes and 8 cycles a switch more, a `define` of the scheme for the resident parts of both tools. The service code's entry and its `back` and `claim` likewise, in the reserved bytes; the copier's switch of a byte's source bank too (about 6 cycles a byte more, 10 % of the start-up's copying). LOADMOD likewise; a RAM form with that decode does not exist outside the emulator.
- **Room.** Bank 0 can hold nothing at `$BF00-$BFDF` that is ever read, and its code must end below `$BF00` with no indexed read reaching that page: 224 bytes lost, so bank 0 has `$8050-$BEFF` (16,048 bytes). Banks 1 to 7 keep `$8050-$BFDF` (16,272; `$BFE1-$BFFF` could hold copied data, 31 bytes each, not counted). In all 129,952 bytes against `direct8`'s 130,304: 352 bytes less for the tools to lose.
- **Which bank 0 holds.** All eight banks hold code, so one of the compiler's banks would be bank 0 with `bbcrom.py` checking that its code ends by `$BEFF` (its bank 5, 11,992 bytes as placed, has room to spare); the linker's window stays `$8050-$BFDF`.

Not built: the owner can choose `cc128` for its existing hardware at 352 bytes and a few cycles a switch, or `direct8` for its single-read switching on a board of our own.

## File names on the BBC

**Built (2026-11-16)** for the Acorn DFS: `lathe/rt/bbc/bbcfs.lth` (the mapping), `lathe/rt/bbcfs.lth` (the same module for every other machine), the call in `lathe/rt/bbc.lth`, `define BBCFS` in every BBC environment, `lathe/env/bbc-dfs.env`, `lathe/host/driver/bbcfs.py` (the host's twin), the emulator's `--bbc-fs dfs` (`emulator/README.md`, "bbcbplus"), and the tests `lathe/tests/test_bbc_dfs.py`. The recipe is in [`boards.md`](boards.md), "The tool chain on the BBC".

The tools name their files as on every other machine: `expr.lth`, `./expr.lo`, `./expr.li`, `LATHEC1.BIN`, `prog.map`. A DFS name is at most seven characters with a one-character directory before a `.`, and `.` is never part of a name, so `asmblock.lth` cannot exist on a DFS disc. The owner's decision: the BBC is targeted without making any other machine follow its naming. So the sources, the module names and the command lines stay as they are everywhere; only the BBC's build maps a name, when it opens a file.

### The mapping, as built

`bbc.open` and `bbc.open_out` copy the name, as before, and with `BBCFS 1` give the copy to `bbcfs.map`, which writes the DFS's name over it. Every file a Lathe program on the BBC opens goes through them (through `sys` for the tools): the compiler's sources, interfaces and objects, the linker's environment file, objects, image, map and bank files, and the bank files `rt_bbc` loads at start-up in the developer's form. The `*` commands the user types (`*LOAD`, `*SAVE`, `*RUN`, `*RUN LOADMOD MODULE`) are the MOS's and take DFS names as they are.

| The tools' name | DFS name | Why |
|---|---|---|
| `expr.lth` | `L.EXPR` | a source |
| `./expr.lo`, `expr.lo` | `O.EXPR` | an object file; every leading `./` is dropped |
| `./expr.li` | `I.EXPR` | an interface |
| `asmblock.lth`, `lk_alloc.lo` | `L.ASMBLOC`, `O.LK_ALLO` | the stem in capitals, its first seven characters |
| `OUTTEST.map` | `M.OUTTEST` | the linker's map |
| `outtest.env` | `E.OUTTEST` | an environment file |
| `LATHE1.BIN`, `lathe33.bin` | `B.LATHE1`, `B.LATHE33` | a bank file (any `.bin`) |
| `gen.txt`, `a.lthx` | `X.GEN`, `X.A` | any other extension |
| `HELLO`, `LOADMOD`, `JUNKZ` | as given (`$.HELLO`) | no `.`: as it is, so an image keeps the name `*RUN` uses |
| `2/expr.lo`, `./1/x.li`, `3/IMAGE` | `:2.O.EXPR`, `:1.I.X`, `:3.IMAGE` | a first directory that is one digit 0 to 3 is the drive |
| `lib/k.li`, `4/x.lo`, `a.b.lth`, `.lth`, a result over 12 characters | none | no name: `map` gives the empty name, which the DFS refuses (Bad name), so `open` gives 0, as for a file that is not there |

The extensions are compared without regard to case. The letters follow Acorn's own compilers, which kept `c.name`, `h.name` and `o.name` in directories named by the kind of file.

**Where it lives.** `bbcfs` is a module of its own so that the tools can place it in a bank: `place bbcfs WIN 5` in `lathec-bbc.env` and `place bbcfs WIN 1` in `linker-bbc.env`, which change nothing with `BBCFS 0`. `bbc.open_mode` calls it only under `#if bbcfs.MAPS`, so with `BBCFS 0` the code is what it was: the compiler, the linker and every BBC program built with `BBCFS 0` are byte for byte what they were before `bbcfs` (images, bank files and maps compared), and so are the `PORTS` 0 and 1 builds. `lathe/rt/bbcfs.lth` exists because `build.py` compiles every module an `import` line names, so the other machines compile `bbc.lth` and need a `bbcfs` with the same names; it is never linked there. `build.py` finds `lathe/rt/bbc/bbcfs.lth` first for the BBC.

**The choice, in the environment file.** `define BBCFS 0` (every BBC environment now says it): names as given, the emulator's directory as before. `define BBCFS 1`: the DFS's names; `lathe/env/bbc-dfs.env` is `bbc.env` so. `define BBCFS 2`: ADFS's names ("ADFS", below). `define BBCFS 3`: the DFS's or ADFS's, as the MOS names the current filing system when the tool runs ("The filing system asked when a tool runs", below).

### Drives

A host directory `0/` to `3/` at the front of a name is a drive. So the user chooses drives on the command line, in a form that reads the same on the host, where `1/` is a subdirectory: `*LATHE expr.lth 1` writes `:1.O.EXPR` and `:1.I.EXPR` and finds the interfaces of its imports there; `*LLINK env.env main IMAGE IMAGE.map 1/a.lo 1/b.lo` reads the objects from drive 1; the linker writes bank files beside the image, so `2/IMAGE` puts them on drive 2 as well. Any other directory is no name.

Not chosen: a drive fixed by the extension (sources on 0, objects on 1, interfaces on 2). The compiler writes the object and the interface into the same directory, and a self-compile's 58 files of three kinds would need three sides that way; with the drive on the command line two sides hold them by count (31 + 27). It costs nothing in `map` beyond the two characters, and the user does what a DFS user does anyway.

### When two names meet

Two stems that agree in their first seven characters (`averylongone`, `averylongtwo`) name the same file, `L.AVERYLO`, `O.AVERYLO`, `I.AVERYLO`. The disc keeps nothing more of a name, so `map` cannot tell them apart; the files can, because each records its module:

- **a source**: compiling `averylongtwo.lth` opens `averylongone`'s source, whose `module` line is not the file's name: error 49;
- **an interface**: a module that imports `averylongtwo` reads `averylongone`'s interface, which names its module: error 51;
- **an object**: a link given both reads `averylongone`'s object twice: link error 17, a symbol defined twice (a module with nothing public would get through: none of the tools' modules is such);
- and the compile that error 49 refuses leaves `averylongone`'s object as it was: the compiler creates its object file only once the module line and the imports are read (2026-11-16, below). Until then it was created first, so the refused compile emptied `averylongone`'s object, and a link then said link error 6, "object file is damaged", until `averylongone` was compiled again.

Each is what the host's tools say of the same files (`test_bbc_dfs.py`). The tools' own modules and test programs map apart today (`asmblock`, `lk_alloc`, `lk_graph`, `lk_place`, `rt_frame`, `kerneltest` and the rest; the test checks every `.lth` of `lathe/src`, `lathe/rt` and `lathe/rt/bbc`), so the clash is a user's. Not chosen: a hashed suffix (`ASMBL3F`), which only makes a clash rarer, and makes the names unreadable on a catalogue.

### What it costs

Measured from the maps (2026-11-16), the ROM forms of the module image:

| | Compiler, `BBCFS 0` | `BBCFS 1` | Linker, `BBCFS 0` | `BBCFS 1` |
|---|---|---|---|---|
| Fixed code: `bbc.open_mode` | 60 | 67 | 60 | 76 |
| Fixed code: the stub of `bbcfs.map` | | 6 | | 6 |
| Main RAM: `bbcfs.out` (13 bytes; in the bank in the RAM forms) | | 13 | | 13 |
| In a bank: `made` 346, `map` 40 or 43, the table 30 | | 416 (bank 5) | | 419 (bank 6) |
| Main RAM free | 1,738 | **1,712** | 402 | **365** |
| Developer form, fixed code left below the split | 25 | 12 | 6 | 0, with the split moved |

- The compiler fits as it is: 26 bytes of main RAM and 416 of bank 5, which had 3,829 free.
- (Superseded on 2026-11-16, "The linker links the compiler": the linker's split is `$4000`, which suits `BBCFS 0` and `BBCFS 1` in both forms, and the DFS build no longer moves it. Main RAM free in the ROM form: about 4,160 bytes with `BBCFS 0`, about 4,130 with `BBCFS 1`; fixed code left below the split in the developer's form: 902 and 881 bytes.) The linker does not fit its developer form, whose split (`$3A20`) sets the ROM form's: 22 bytes of fixed code where 6 were free. Its DFS build moves the split up 16 bytes, to `$3A30` (`test_bbc_dfs.LINKER_ROOM`): the developer form then has 0 bytes left below it and the ROM form 365 of main RAM. `linker-bbc.env` is left at `$3A20`, so that `BBCFS 0` builds what it built; the redesign of the linker's work area will free main RAM, and the split should then move for both.
- Zero page: none more (`bbcfs`'s locals share the frames' zero page, which is full in both tools as before).

### ADFS

Built on 2026-11-17: "ADFS", below. (Until then `BBCFS 2` stopped the compiler with `#error`.)

### The filing system asked when a tool runs

**Built (2026-11-20).** The owner's decision: a ROM image must work with either the DFS or ADFS, so the mapping is chosen when the tool runs, not when it is linked. `define BBCFS 3` (`lathe/rt/bbc/bbcfs.lth`, its last section; the twin is `bbcfs.asked_name` and `asked_host_file` in `lathe/host/driver/bbcfs.py`): each time `map()` is called (each `bbc.open` and `open_out`) it asks the MOS which filing system is current, by OSARGS with A = 0 and Y = 0, which gives its number in A, keeps the number for `cdir()`, and maps by it:

| OSARGS gives | The filing system | The name |
|---|---|---|
| 4 | the disc filing system, the DFS | `BBCFS 1`'s: `L.EXPR`, drives `0/` to `3/`, seven characters, 12 at most |
| 8 | ADFS | `BBCFS 2`'s: `lth.expr`, drives `0/` and `1/`, ten characters, 24 at most, and `open_out`'s `*CDIR` of a directory that is not there |
| any other | none it knows: 0 no filing system, 1 and 2 the cassette, 3 the ROM filing system, 5 the network, 6 Telesoftware, 7 IEEE, and any later one | as given, `BBCFS 0`'s rule: the name is the filing system's to take or refuse |

**Any other number: the name as given, not a refusal.** A name the filing system cannot take is refused by it (Bad name, Not found), which `bbc.open` catches, and the tool says what it says of any file it cannot open, naming the host's name; a filing system that does take such names (a host filing system on an emulator or a second processor) works as the emulator's own directory does. A refusal at the start would cost a message and a check in fixed memory or the module for a case no gate has, and would stop a filing system that works. Not chosen either: asking once at the start of a tool (`map()` asks at each name: OSARGS is a vector call of a few dozen cycles, against the hundreds a disc spends a byte, and it needs no start-up code, which in the developer's form would be fixed and in the ROM form in `rt_bbc`).

**What is from memory, not checked:** that OSARGS A = 0, Y = 0 gives 4 for the DFS is BeebWiki's (`emulator/NOTES-bbcbplus.md`) and 8 for ADFS the ADFS guide's; the other numbers in the table are memory, as is that third-party DFSs (Watford, Opus, Solidisk and the 1770 DFS of the B+) answer 4 and keep the DFS's names; a DFS that answered otherwise would get the names as given.

**The emulator** answers OSARGS for the filing system it emulates: 4 under `--bbc-fs dfs` (and the default, `host`), 8 under `--bbc-fs adfs`; `--bbc-fs-number N` makes it give N instead, a filing system the tools do not know (`emulator/README.md`; the C tests `osargs_gives_the_number_of_the_filing_system` and `test_cli.c`'s). The default's 4 is as before, so the goldens are unchanged.

**One `made()` for both.** The two rules differ in the last drive, the room in `out`, the stem's length, the directory (the table's letter or the extension as it is), an empty extension (the DFS's `X.A`, none for ADFS) and capitals; `made()` takes each from the number, and `cdir()` and its `*CDIR` are one function for `BBCFS 2` and `3`, which under any number but 8 gives false. `BBCFS 1` and `2` keep their own `made()`, so that their builds are the bytes they were: the images, bank files, maps, objects and interfaces of both tools in the developer's, sixteen- and eight-bank ROM forms with `BBCFS` 0, 1 and 2 (`ADFS 1` with 2), the 32K forms with `BBCFS` 0 and 1, and hello with `BBCFS` 0, 1 and 2, compared before and after.

**What it costs**, measured from the links (`lk_judged.py`, as `test_bbc_rom128.Account` reads them), the eight-bank image:

| | `BBCFS 0` | `BBCFS 1` | `BBCFS 2`, `ADFS 1` | `BBCFS 3`, `ADFS 1` |
|---|---|---|---|---|
| `bbcfs` in a bank, judged / placed | | 490 / 416 | 616 / 521 | 909 / 775 |
| image bank 4 as judged, the compiler's fifth (of 16,272) | 13,360 | 13,850 | 13,976 | 14,269 |
| the linker's bank 1 (image bank 5) as judged | 15,529 | 16,019 | 15,945 (`link` in bank 2) | **16,238: 34 left** (`link` in bank 2) |
| resident parts, the compiler / the linker | 11,886 / 9,601 | 11,899 / 9,618 | 11,946 / 9,694 | 11,946 / 9,699 |
| the image's free bytes | 4,715 | 3,853 | 3,507 | **2,989** |
| main RAM free at `$1F00`, the compiler / the linker, ROM form | | | 2,161 / 1,733 | 2,158 / 1,727 |
| the same, developer's form (`bbcfs` fixed) | | | 5,266 / 2,946 | 5,011 / 2,681 |

Nothing moved between banks: with `ADFS 1` the linker's `link` is already in its bank 2 (`when ADFS when ROM128 place link WIN 2`), which leaves `bbcfs` room in bank 1. Without it (`BBCFS 3` with `ADFS 0`) the linker's bank 1 is 166 bytes over (16,438 judged), and in the 32K form (`RAM32 1`, `ADFS 0` only) 198 over: neither is built. (Measured again on 2026-11-20, after the code generator's changes: the 32K form's bank 1 with `BBCFS 3` is 16,291 judged, **19 bytes over**; with `link` in bank 2 the three banks are 16,091, 16,086 and 15,428, and it fits: "The image for machines with no sideways RAM".) Neither would serve ADFS anyway, whose PAGE is `$1F00` with the DFS beside it, so a build from `$1900` would write over ADFS's workspace; once the tools find PAGE when they start (another agent's work), the linker's `link` should go to bank 2 whatever `ADFS` says, and `BBCFS 3` then fits the eight-bank linker as it does here; the 32K linker's bank 1 needs 198 bytes more for it.

**Tested** (`lathe/tests/test_bbc_asked_fs.py`, by default, about 20 s): the twin for every number; `map()` and `cdir()` on the BBC giving the twin's names under `--bbc-fs dfs`, `--bbc-fs adfs` and `--bbc-fs host` with nine other numbers; and the 128 KB image of both tools built with `BBCFS 3` and `ADFS 1`, which fits with the compiler in banks 0 to 4 and the linker in 5 to 7 and has main RAM free at `$1F00`, compiling each module of hello and of a program of two modules (`longname` and `averylongone`, `AVERYLO` on the DFS and `averylongo` on ADFS), linking them and running the result under `--bbc-fs dfs` and under `--bbc-fs adfs` (on a disc with only the sources: the directories made by the tools), every file the host tools' under that disc's names, and the same under `--bbc-fs-number 5` with the names as given. `LATHE_BBC_ASKED_FS_REPORT=1` prints the account.

**What it makes redundant** (nothing removed): the separate ROM images built with `BBCFS 1` and with `BBCFS 2` (`test_bbc_dfs.build_image`, `test_bbc_adfs.build_image`, `test_bbc_rom128.Adfs128`'s and `AdfsMainRam`'s builds), since one `BBCFS 3` image serves both machines; their tests could run that image instead, `test_bbc_dfs.Toolchain` under `--bbc-fs dfs` and `test_bbc_adfs.Toolchain`, `SelfHost`, `Loop` and `Adfs128` under `--bbc-fs adfs`. The compile-time values still serve the developer's forms (whose `bbcfs` is fixed, 255 to 265 bytes of main RAM more with `BBCFS 3`), user programs (`lathe/env/bbc-dfs.env`) and the 32K form, which serves the DFS alone. The environments still say `define BBCFS 0`: making `BBCFS 3` the ROM forms' own (an entry `when ROMFORM`) would change the ROM builds every gate makes with `BBCFS 0` and runs under the emulator's default, where OSARGS gives 4: they would then need `--bbc-fs dfs`, or the default an answer of its own.

### The `*` commands

`*LATHE OPTIONS expr.lth .` and `*LLINK ...` work as they are: the arguments are the host's, mapped when each file is opened. A shorter BBC form, `*LATHE EXPR` for `*LATHE EXPR.lth .`, would be bank 0 (`module.asm`) adding `.lth` and ` .` to a tail of one word with no `.`: a few dozen bytes of bank 0, which has room; but then the command line would differ from the host's, and the tests replay the host's. Not built.

### Measured for a real disc

From `LATHE_BBC_DFS=1 LATHE_BBC_SELFHOST=1 LATHE_BBC_DFS_REPORT=1 python3 -m unittest test_bbc_dfs` (2026-11-16; the self-compile under DFS names was dropped on 2026-11-18: "The loop under DFS names"), the emulator's `dfs: most-open most-writing` and the files left on the disc. A side is 204,800 bytes (80 tracks; 40 tracks: half); a double-sided 80-track disc 409,600.

**Files open at once.**

- *The compiler*: **2** at most since 2026-11-16, in every module of the self-compile and in an import chain six interfaces deep (`test_bbc_dfs.py` asserts both, and 3 for each run of the chain, which is the linker's): the source and one interface while the imports are read, then the source and the object file. It was 5, the DFS's limit, in twelve of the eighteen modules: the source, the object file, and three interfaces read inside one another (for `src` and `expr`: `kernel.li`, whose inline functions name `sys`, so `sys.li`, which names `host`, so `host.li`), and one level more was `Too many open`, which `bbc.open` catches as a file not there: error 50 (the six-deep chain failed so, in compiling `d2.lth`). Below, "When the compiler opens its files".
- *The linker*: 3, the map, the image (or a bank file) and an object file; 2 since it writes the map after the image (2026-11-16), by its command line or a command file.
- *Written at once*: the compiler 1 (`out` closes the object file before `decl` creates the interface); the linker 1 since 2026-11-16, and at most 2 open (an image or bank file, or the map, and an object file), by its command line or by a command file, which is read and closed first (`test_bbc_dfs.py`, outtest). Before: the linker 2: `lk_emit.write` creates the map, writes its functions and symbols, and keeps it open while it creates and writes the image and then each bank file.

**What a real DFS would do with that.** A new file opened for output is given 16 KB of the disc, and a file is one run of sectors that cannot grow into the file after it ("Can't extend"; `emulator/NOTES-bbcbplus.md`). The map is created first, the image right after it: once the image exists the map cannot grow past its 16 KB. outtest's map is 22,946 bytes, so **linking outtest on a real DFS would fail with "Can't extend"** on the map; hello's map is 153 bytes. The image and the bank files are each the last file while they grow, and the compiler's object file (67,288 bytes for `expr`) is the only file it writes, so those grow freely if the DFS puts a new file after the last one; if it puts it in a gap between files (not checked), a large object can hit the next file, and `*COMPACT` before a compile avoids it. (Built on 2026-11-16: the map is written after the image and the bank files are closed, its S lines by a reading of their own, so outtest links on a DFS as the host links it.) The fix in the linker, then not built: write the map when the image and the bank files are closed (the lines emission adds, `lk_map.mark_functions`, kept in a table or made by a second pass), or create the image before the map. Until then a user can make room: a file written over keeps its space, so `*SAVE M.OUTTEST 0 +6000` before the link gives the map 24 KB.

**What a link leaves.** A program of the corpus on one disc, every file under its DFS name (sources, objects and interfaces of its modules, the environment, the image and the map): 15 to 24 files and 29 to 58 KB; the banked ones (`farcall`, `bankdata`, `regions`), with their objects and interfaces on drive 1 (`1/`): 12 to 17 files and 48 to 54 KB on drive 0, 16 to 24 files and 13 to 16 KB on drive 1. outtest's link: 22 files, 137,374 bytes (13 objects, 93,258; the image 8,894; the map 22,946; six bank files, 8,770). All fit a side.

**A self-compile.** Each module's compile as `test_bbc_selfhost.py` lays it out (its source, the interfaces it imports, then its object and interface) fits one side: 7 to 24 files, at most 149,237 bytes (`gen`). All of them on one disc would be 58 files and **918,081 bytes**: 18 sources 519,064 bytes, 18 objects 384,182, 22 interfaces 14,835. That is 4.5 sides of 80 tracks, 2.3 double-sided discs, and the sources alone do not fit one double-sided disc. By count two sides would do (31 + 27); by size a self-compile on a real BBC is several discs and a swap between compiles: the source and interfaces in, the object out. The largest file, `L.GEN`, is 77,996 bytes.

**The module image.** The whole image is 262,144 bytes, more than a side holds. Since 2026-11-16 `bbcrom.py --short` writes the banks in use alone, and `LOADMOD` takes it ("Step 3, as built: the ROM form", "The short image"): the two tools use banks 0 to 11, **196,608 bytes**, 768 sectors; with `LOADMOD` (459 bytes, 2 sectors) and the catalogue (2) that is 772 of an 80-track side's 800 sectors, 7,168 bytes left. `test_bbc_dfs.py` checks it and runs the tools from it through `LOADMOD` (the DFS tests' RAM form now always loads the short image). A 40-track side (100 KB) cannot hold it. A real ROM module needs no file.

### When the compiler opens its files

Built 2026-11-16, in the host compiler and its twin alike (`decl.unit`, `decl.imported_module`, `kernel.get`; `lathe/host/README.md`, "Command lines").

- **The object file** is created once the module line and the imports are read, no longer before the source is read; its first records, the module's and one for each import, are written then from the symbol table, in the order of the import lines. The interface is written, as before, only once the module has compiled.
- **On an error, on every machine** (the host, Wendy 2, the default machine and the BBC behave the same, because the same code decides): an error in the module line or the imports (49, 50, 51, 102 and the rest) leaves the object file and the interface of before as they were; an error later leaves the object file cut short (the linker's link error 6 says so) and the interface of before. Going further, so that no error leaves a cut object in place of a good one, needs a file to be written under another name and renamed, or deleted on an error, and no machine's services can do either (`host.lth`, `disk.lth`, the emulator's host services; the BBC's OSFILE 6 could delete): a change to every machine's services for a case the linker already reports. Not made.
- **Error 63** (the object file cannot be created) comes after the imports, and a missing output directory with an import found in no directory is now error 50 first.
- **The interfaces are read one at a time.** An interface's `LI_MODULE` entry that names a module to read closes the interface, reads the other one, opens the first again and reads past the bytes it had read (`kernel.get` counts the bytes read of a file in `stream_next`, which only memory streams used). The order of reading is exactly what it was, so the name heap, the symbols and every record are the same: every file a successful compile writes is the same bytes (the corpus compiled by the host compiler before and after, 653 programs: the only files that differ are the objects that refused compiles no longer write; the identity tests, the self-compile on Wendy 2 and on the BBC). Error 80, too many streams, is no longer reachable: the source, the object file and six nested inline expansions are 8 of 10.
- **What it costs.** On the BBC (ROM form, `BBCFS 1`): resident part 13,998 to 14,002 bytes, variables 10,401 to 10,404, **main RAM free 1,712 to 1,705**; the developer's form 12 to 8 bytes below its split; bank 2 80 bytes smaller (`lathec` 1,022 to 945: the object file's name is `decl.file_path`'s, which also makes the interfaces'), bank 3 192 larger (`decl` 9,406 to 9,599), bank 5 8 larger (`kernel`); one function fewer. On Wendy 2 (`compiler-bank.env`): fixed code and constants 15,662 to 15,680 bytes (to `$7E07`), fixed variables the same. The self-compile in the ROM form takes 945.3 million cycles, 933.5 before (+1.3 %), and opens 214 files where it opened 182 (the interfaces opened again), reading 2,107 bytes more; on Wendy 2 849.2 million, 837.7 before (+1.4 %). Most of the cycles are the count in `kernel.get`, which every byte of the source pays too. A single counter of all files' bytes instead of a column was tried: 7 bytes more main RAM and bank 3 8 bytes over in the developer's form, so not kept.

### The loop under DFS names (2026-11-16)

**Dropped (2026-11-18), the owner's decision**: self-hosting on the BBC is on ADFS ("ADFS", `test_bbc_adfs.py`), so `test_bbc_dfs.py` no longer has this loop or the self-compile under DFS names (`LATHE_BBC_DFS_LOOP`, and `LATHE_BBC_SELFHOST` there, are gone); its name mapping, limits and tool chain stay, which the 32K Model B relies on ("The 32K Model B"). What follows is how it stood when it ran.

`LATHE_BBC_DFS_LOOP=1 python3 -m unittest test_bbc_dfs.Loop`: the loop of "The linker links the compiler" with both tools and the compiler they make built with `BBCFS 1` from the environments as committed, under `--bbc-fs dfs`. `*RUN LOADMOD :3.MODULE` fills the module's RAM form from the short image (`bbcrom.image(..., short=)`, banks 0 to 11, 196,608 bytes), `*LATHE` compiles the compiler's 25 modules (`bbcfs` among them), `*LLINK @LINKARG` links them, and the new compiler, `*RUN LATHEC`, compiles `err` and `kernel` again. Every file is the host tools' under its DFS name. 4,505 million cycles, 37.5 minutes at 2 MHz. At most 2 files are open at once and 1 is written: the compiler sets it (a source or an interface, and the object file) and the linker matches it (an object file, and the image, a bank file or the map).

A catalogue holds 31 files, and the compiler writes a module's object and interface in one directory, so the files are spread over the four drives, each as near an 80-track side (204,800 bytes, 204,288 beside the catalogue) as they allow:

| Drive | What | Files | Bytes | A side? |
|---|---|---|---|---|
| 0 | the environment, `LINKARG`, `LOADMOD`, the image and its six bank files (the developer's form loads its banks from the drive it runs on) | 10 | 91,536 | fits |
| 1 | the objects and interfaces of the smallest modules and of the largest that fit beside them | 20 | 209,604 | 5 KB over |
| 2 | the objects and interfaces of the others (each compile names the other drive as its directory of interfaces: `*LATHE ... 3/expr.lth 2 1`) | 30 | 203,770 | fits |
| 3 | the 25 sources (569,705 bytes), the map (126,260) and the short image | 27 | 892,573 | no |

The objects and interfaces are 413 KB, more than two sides, so one of drives 1 and 2 is over; the sources alone are nearly three sides. The emulator does not limit a drive's size.

**On a real BBC with two double-sided 80-track drives** (four sides, 817 KB, against 1.4 MB here) the work does not fit at once, and the user changes discs: the sources on discs of their own, a few modules' sources at a time in drive 3 while their objects and interfaces collect on drives 1 and 2 (an interface must be there when a module that imports it is compiled, so the order is `build.py`'s, and the interfaces, 15 KB in all, could be kept on one side apart from the objects); then, for the link, the objects on drives 1 and 2 and drive 3 cleared for the map; the module image on a disc of its own, loaded once by `LOADMOD` before the compiles and not needed again while the machine is on. Not built.

**A fault found and fixed: the developer's forms under `BBCFS 1` could not start.** Their start-up loads the banks through `bbc.open`, which calls `bbcfs.map`, and `bbcfs` was placed in a bank (`WIN 5` in `lathec-bbc.env`, `WIN 1` in `linker-bbc.env`), which is not there before it is loaded: status 255, the bank's file not found. Nothing else `bbc.open` calls is in a bank (`bbcfs.map` calls only its own functions; `bbc` and `rt_bbc` are fixed). Now `bbcfs` is fixed in the developer's forms and in its bank only in the ROM forms, whose banks are always there: each environment defines `ROMFORM` as 0, which `bbcrom.rom_env` changes to 1, and the entries that differ between the forms are conditional: `when ROMFORM place bbcfs WIN 5` is an entry of the ROM form only, `unless ROMFORM code $1900 $519F` of the developer's form only ([`configurations.md`](configurations.md), "The environment file"). (Until 2026-11-17 a special comment did this, which only `bbcrom.rom_env` read.) The compiler's developer form has its own split, `$51A0`, 416 bytes up (`$5200` since 2026-11-17, for `rt_frame`'s list routines, and the ROM form's `$5020`: [`spikes.md`](spikes.md), "Built: saving calls through a list"), and its ROM form kept `$5000`; the linker keeps `$4000` in both. `test_bbc_dfs.DeveloperForms` (`LATHE_BBC_DFS=1`) has both developer's forms start with `BBCFS 1` from the environments as committed and compile and link hello as the host does.

Main RAM free with `BBCFS 1` (26,111 bytes less the fixed code, constants and variables the map places in main RAM, 2026-11-16):

| | ROM form | Developer's form |
|---|---|---|
| the compiler | 2,211 (code to `$4FB2`) | 5,497 (code to `$5192`, 13 bytes below its split) |
| the linker | 4,129 (code to `$3C49`) | 4,594 (code to `$3E29`) |

The developer's forms have more free because their banks hold their modules' variables.

### What a user waits, at 2 MHz

From the emulator's cycles in the ROM form (2026-11-16). The time of the disc is not in it: the emulator's MOS charges nothing for a file call, and a real DFS spends hundreds of cycles a byte ("Measured: the linker on the BBC").

| What | Cycles | At 2 MHz |
|---|---|---|
| one module compiled: `src`, `kernel`, `gen` (the largest) | 9.7, 57.7, 149.4 million | 5 s, 29 s, 1.2 minutes |
| a small program linked: `hello`, `calls` | 6.5, 23.2 million | 3 s, 12 s |
| `outtest` linked (12 objects, 5 banks) | 330 million | 2.8 minutes |
| the compiler compiled, all its modules | 933 million | 7.8 minutes |
| the compiler linked | 3,404 million | 28.4 minutes |
| the whole loop: compiled, linked, two modules compiled again | 4,471 million | 37.3 minutes |

## ADFS (2026-11-17)

The rebuild's files are 1.2 MB, which no arrangement fits on two double-sided DFS discs with readable sources ([`spikes.md`](spikes.md), "Disc space for the rebuild on two DFS discs, measured"). The owner's decision: assume the compiler's developer has dual ADFS drives, which the B+ supports. So the BBC port has a second filing system beside the DFS, which stays. Nothing outside the BBC port changes: sources, module names and command lines are the same on every machine.

Built: `define BBCFS 2` in `lathe/rt/bbc/bbcfs.lth` and its twin `lathe/host/driver/bbcfs.py` (`adfs_name`); the directory rule in `lathe/rt/bbc.lth`'s `open_mode`; `define ADFS` in `lathec-bbc.env`, `linker-bbc.env`, `lathe/env/bbc.env` and `bbc-bank.env`, which moves main RAM to ADFS's PAGE; `bbcrom.loader(OUT, page)`, LOADMOD for another page; the emulator's `--bbc-fs adfs` (`emulator/README.md`, "bbcbplus"); the tests `lathe/tests/test_bbc_adfs.py`. The recipe is in [`boards.md`](boards.md), "On two ADFS discs".

### The facts

From Acorn's *Advanced Disc Filing System User Guide* and a few third parties, each marked with how sure it is in `emulator/NOTES-bbcbplus.md`, "ADFS on the B+". What the design rests on:

- ADFS runs on a B or a B+ with a 1770 controller (the guide); 1.30 is the last version for the BBC (a ROM archive's list); it can be fitted beside a DFS, and entered with CTRL A BREAK or `*ADFS` (the guide).
- **PAGE is `&1D00` with ADFS** (the guide, four times) and **`&1F00` with ADFS and a DFS both** (two third parties, one for the Electron, one for a Model B; not checked for the B+). The tools are built for `$1F00`, which serves both.
- Names of ten characters, any but `# * . : $ & @` and space; `.` separates directories; `$` the root, `^` the parent, `@` the current directory; `:D.` a drive's root. Drives 0 and 1, one number a disc ("ADFS does not assign a separate drive number to each side"). Case not significant: memory, not checked.
- A directory holds 47 entries and takes 5 sectors; the map takes sectors 0 and 1, the root 2 to 6; an L disc is 2,560 sectors of 256 bytes, 640 KB.
- Ten files open. OPENOUT of a new file reserves 256 sectors (64 KB), or the space of the file it replaces, and fails if they are not there; a file that outgrows its space is moved whole to a free space that holds it, else "Compaction required". There is no "Can't extend" in ADFS. That reserved space not used is given back at the close is inferred, not read.
- Zero page: the filing systems' `$A0-$A7` and `$B0-$CF` for ADFS as for the DFS, from a memory map of disc systems in general; the tools use `$00-$8F` only, so it does not matter to them.

### The mapping, as built

With `define BBCFS 2`, `bbc.open` and `bbc.open_out` give each name to `bbcfs.map`, which makes ADFS's:

| The tools' name | ADFS name | Why |
|---|---|---|
| `expr.lth` | `lth.expr` | a source: in the directory named by its extension |
| `./expr.lo`, `expr.lo` | `lo.expr` | an object; every leading `./` is dropped |
| `./expr.li` | `li.expr` | an interface |
| `OUTTEST.map`, `outtest.env` | `map.OUTTEST`, `env.outtest` | the linker's map, an environment |
| `LATHE1.BIN` | `BIN.LATHE1` | a bank file |
| `gen.txt`, `a.abcdefghij` | `txt.gen`, `abcdefghij.a` | any other extension, as it is, up to ten characters |
| `abcdefghijk.lth` | `lth.abcdefghij` | a stem's first ten characters |
| `HELLO`, `LOADMOD` | as given | no `.`: as it is, so that an image keeps the name `*RUN` uses |
| `1/expr.lo`, `./1/x.li`, `0/a.lth`, `1/IMAGE` | `:1.lo.expr`, `:1.li.x`, `:0.lth.a`, `:1.IMAGE` | a first directory `0` or `1` is the drive: its root |
| `2/x.lo`, `lib/k.li`, `a.b.lth`, `.lth`, `a.`, `a.abcdefghijk`, a result over 24 characters | none | the empty name, which ADFS refuses (Bad name), so `open` gives 0 |

Case is kept: ADFS keeps it and matches without it.

**A directory for each kind of file, named by its extension**, as Acorn's own C compilers on ADFS kept `c.name`, `h.name` and `o.name`. Chosen over the DFS's letters (`L.EXPR`) because it needs no table (the extension is copied as it is, so any extension works, and the twin is three lines), because a catalogue reads plainly (`lth`, `lo`, `li`, `map`, `bin`), and because a source and its object then never share a directory: each kind has its own 47 entries, and the compiler's 25 modules fit one directory of each.

**Long stems.** Every module of the compiler and the linker fits ten characters (`test_bbc_adfs.Names` checks the modules the two tools link), and so does every `.lth` of `lathe/src`, `lathe/rt` and `lathe/rt/bbc`: the longest test programs, `inlinetest` and `kerneltest`, are ten. Of the 578 sources of `lathe/tests/cases` many are longer (`args_and_call`, `address_of_function`; among the programs the chain runs about two dozen, `bigarray_pages`, `inline_mix_plain`, `string_library` and others); they are cut to ten, the DFS's rule with ten for seven: two stems that agree in their first ten characters name the same file, and the files' own module names catch it as for the DFS ("When two names meet": errors 49 and 51, link error 17). No program the chain runs has two modules that meet so.

**Drives.** `0/` and `1/` at the front, as the DFS's `0/` to `3/`: `:D.` and the path from that drive's root. ADFS has two floppy drives and gives a disc one number, so `2/` and `3/` are no name. A name without a drive is in the current directory (`*DIR`), as a name without a directory is on the host.

**Directories must exist before a file is created in them, and the port makes them.** Before it creates a file, `open_mode` asks `bbcfs.cdir`: if the name is in a directory (not a root), `cdir` writes `*CDIR` of it in `name_buf`, looks for it with OSFILE 5 (which gives 0, and no error, for an object that is not there), and if it is there gives the name back and false; if not, true, and `open_mode` runs the command through OSCLI, an error caught as OSFIND's are (BRKV for the call), and has the name back (`bbcfs.again`). So a blank disc needs nothing done to it: the compiler makes `lo` and `li` as it writes its first object and interface, the linker `map` and `bin`. If the directory cannot be made (the parent's 47 entries, a full disc), the OSFIND that follows fails, `open_out` gives 0 and the tool says what it says of any file it cannot create: the compiler's error 63 (`test_a_directory_that_cannot_be_made`). Chosen over a clear error because the error a tool can give names the host's file (`./hello.lo`), not the directory, and because it saves the user a `*CDIR` for each kind on each drive. The directory is looked for first, not left to OSFIND's "Not found", for the fault below. Reading is as before: a file that is not there, for any reason, is 0.

### What it costs

Measured from the maps (2026-11-17), the ROM forms, against `BBCFS 1`:

| | `BBCFS 1` | `BBCFS 2` |
|---|---|---|
| Fixed code: `bbc.open_mode` | 67 (the compiler), 76 (the linker) | 94, 96 |
| Fixed code: `bbc.find` | 59 | 67 (its mode 0 is OSCLI) |
| Fixed code: stubs of `bbcfs` | 6 (`map`) | 18 (`map`, `cdir`, `again`) |
| Main RAM: `bbcfs.out` | 13 | 25 |
| In a bank (the compiler's 5, the linker's 1) | 416: `made` 346, `map` 40, the table 30 | 527: `made` 282, `cdir` 185, `again` 32, `map` 23, "CDIR " 5 |

So 60 bytes of main RAM more than the DFS's in the compiler and 57 in the linker, and 111 more of the bank. In the developer's forms `bbcfs` is fixed, as for the DFS.

### PAGE, and what each tool has free

`define ADFS 1` moves the tools' and the programs' main RAM to `$1F00`: `when ADFS` entries give the code and data ranges, `unless ADFS` the ones of before, which every `BBCFS 0` and `BBCFS 1` build still reads. Its images, bank files and maps are byte for byte what they were: compared on 2026-11-17 for both tools in both forms with `BBCFS 0` and `1`, the module images, and hello on `bbc`, `bbc-dfs`, `host`, `wendy2`, `wendy2disk` and `michael`; only `bbcfs.li` differs, by the new constant `DIRS`. The emulator runs ADFS builds with `--bbc-page 1F00`, so that `--bbc-strict` makes any write below PAGE a fault.

Measured (2026-11-17) on the tree this work started from (5de87c8), with `BBCFS 2`; free is `$1F00-$7BFF` and `$0401-$06FF` (24,575 bytes) less the code, constants, stubs and variables the map places in main RAM:

| | Split | Code ends | Variables | Free |
|---|---|---|---|---|
| the compiler, ROM form | `$5600` | `$55E5` | `$5600-$7BFF` and `$0401-$06B1` | **104** |
| the compiler, developer's form | `$5880` | `$5828` | `$5880-$7278` | 3,293 |
| the linker, ROM form | `$4600` | `$427A` | `$4600-$7922` | 2,401 |
| the linker, developer's form | `$4600` | `$44BD` | `$4600-$7540` | 2,816 |
| the compiler, eight-bank ROM form | | | | 134 |
| the linker, eight-bank ROM form | | | | 1,646 |

(After the merge of the 128 KB module and the fix of the fault below, 5 bytes of `rt_bbc` more; the eight-bank figures are `test_bbc_rom128.AdfsMainRam`'s, by a link that lets a bank be over as judged, since neither tool fits eight banks yet: the linker's three banks are 1,197, 199 and 416 bytes over with `BBCFS 2`, whose `bbcfs` is in its bank 1.)

Against `$1900` with `BBCFS 1` the compiler's ROM form had 1,700 free and the linker's 3,994: the 1,536 bytes of PAGE are nearly all of it, ADFS's names the 60 and 57 above. **Everything fits, the compiler's ROM form by 104 bytes**: 26 below its split and 78 of `$0401-$06FF`. That is too close (a change to the code generator due next adds about 110 bytes to `rt_frame`): "Room for the compiler at ADFS's PAGE", below, has the options. Nothing had to move to a sideways slot and no capacity was cut. The other agents' work on the code generator will move these figures: if the compiler's resident part grows by more than 26 bytes its ROM split moves up, and its variables have the 78 bytes of `more data` to take what they lose. With ADFS alone (PAGE `$1D00`) each has 512 bytes more, but the environments are built for `$1F00`. `BBCFS 2` with `ADFS 0` does not fit the compiler's developer's form (132 bytes over its `$51A0` split); it is a case no machine has.

A program of the corpus at `$1F00` (`bbc.env` with `ADFS 1`: code `$1F00-$6BFF`, the same 4 KB data range): every one but `for_ranges` fits, whose code ends at `$68E7` from `$1900` and so 743 bytes past `$6BFF` from `$1F00`. No split fits both: `for_ranges` needs the code range to `$6EE7` at least (more with `BBCFS 2`), and `bigarray_pages` needs 3,700 bytes of variables from the split to `$7BFF` (its big array cannot go in `$0401-$06FF`), so a split at `$6D8C` or below: 348 bytes apart. The data range stays as it was, and `for_ranges` is the one program of the chain that does not fit at ADFS's PAGE.

### Room for the compiler at ADFS's PAGE

Options, measured or counted on 2026-11-17 (none built but the fault's fix, which cost 5 bytes):

| Option | Bytes of main RAM | What it costs |
|---|---|---|
| **The shadow screen** (`*SHADOW`, or a mode with bit 7 set: the B+'s screen in its own 20 KB, HIMEM `$8000`) | **1,024** (`$7C00-$7FFF`) | the environments' data ranges to `$7FFF` under a define, and a check at the start (OSBYTE 132, HIMEM, about 15 bytes of fixed code) so that a tool run in a screen mode without shadow stops with an error instead of writing over the screen; the user selects the shadow screen first. The B+'s shadow RAM is checked (MAME); that HIMEM is then `$8000` is memory, and the emulator models only OSBYTE 132's answer (`--bbc-shadow`). The cheapest and largest |
| `kernel.text` (2,048 bytes, the largest table in main RAM) in a region, slot 1 (10,656 free) or slot 12 (7,136 free) | about 1,850 (2,048 less accessors in fixed code, estimated 150 to 200) | a change to the compiler's `kernel` and its twin: it is read through pointers in many places (step 3's table of what can leave main RAM) |
| `reg`'s slot columns (`slot_size`, `slot_name`, `slot_weight`, `slot_kind`, `slot_class`, `slot_busy`: 1,536 bytes) in a region | about 1,300 (estimated) | `reg` and its twin; `reg` is in a bank and reads them in its hottest loops, so each read would be a block or an accessor: cycles as well as bytes |
| `bbc.arg_text` (256): split the tail in place where it lies, at `$0700` or OSARGS's address, instead of copying it | about 230 | `bbc.lth` (every BBC program); the tail is read again at each `argc` and `argv`, so it would be split once and marked |
| A build for `$1D00`: ADFS without the DFS | 512 | a second set of `when` entries. But the B+'s DFS is fitted on the board as standard (a third party's page, bbcelite.com, seen only as a search engine's summary: "The B+ comes with the DFS disc filing system fitted as standard"), so ADFS is added beside it: `&1F00` is the case a B+ owner has, and `$1D00` only with the DFS ROM taken out |
| The eight-bank layout's choice of what is resident | 30 (the compiler's resident part is 14,024 bytes there against 14,054) | nothing: it is what the layout gives today; the compiler's kept functions (kernel 4,220, fbuf 3,188, lex 1,023...) are fixed because they have `with` blocks or run in one, and cannot be banked without restructuring |

The shadow screen is the option worth building: 1 KB for an environment entry and a check, no change to the compiler.

**Built instead (2026-11-17): the compiler's own code made smaller and less of it fixed** ([`configurations.md`](configurations.md), "Kernel's functions out of fixed memory, and accessors of one column"; [`spikes.md`](spikes.md), "Built: the compiler's source made smaller"). None of the options above was needed, and the shadow screen is still the owner's to decide. Main RAM free, of the bytes each form has (`$1F00` or `$1900` to `$7BFF`, and `$0401-$06FF`), the code, constants, stubs and variables of the compiler's map counted against it whatever the split (`lk_mainram.py` as `test_bbc_rom128.AdfsMainRam` links it):

| The compiler | Before (05824fd) | After |
|---|---|---|
| **eight-bank ROM form at `$1F00`, `BBCFS 2`** | **51** | **2,166** |
| sixteen-bank ROM form at `$1F00`, `BBCFS 2` | 15 | 2,166 |
| developer's form at `$1F00`, `BBCFS 2` | 3,199 | 5,526 |
| sixteen-bank ROM form at `$1900`, `BBCFS 0` / `1` | 1,636 / 1,610 | 3,787 / 3,760 |
| eight-bank ROM form at `$1900`, `BBCFS 0` / `1` | 1,672 / 1,646 | 3,787 / 3,760 |
| developer's form at `$1900`, `BBCFS 0` / `1` | 5,329 / 4,893 | 7,655 / 7,219 |

The two images now have one layout, so their ROM forms are alike. The splits in `lathec-bbc.env` moved to about halfway between the end of the code and where the variables must start: ROM form `$5020` to `$4F00`, developer's form `$5200` to `$57A0`, and at ADFS's PAGE `$5640` to `$5220` and `$58A0` to `$5B00`. `BBCFS 2` with `ADFS 0` now fits the developer's form too.

LOADMOD is assembled at PAGE, its buffer for a bank from PAGE + `$0700`: `bbcrom.loader(OUT, 0x1F00)` makes it for `$1F00` (buffer `$2600-$65FF`); with the default page it is the same 459 bytes as before. That is the only change in `bbcrom.py`.

### The emulator

`--bbc-fs adfs` (`emulator/README.md`; the code is `bbc_mos.c`, "--bbc-fs adfs", with six C tests in `emulator/tests/test_bbc_mos.c`): paths of ten-character parts, directories as host directories (drive 1 is `--disk`'s `:1`), the CSD and `*DIR`, `*CDIR`, `*DELETE`, ten files open, a file open for output not opened again, 47 entries a directory, and each drive an L disc of 2,560 sectors whose sectors are counted: the map and the root, 5 for each directory, each file's length in whole sectors, and 256 reserved by each new file open for output until it is closed. A file that outgrows its space takes the sectors after it or moves, or the call is "Compaction required" or "Disc full"; "Map full" past 80 free spaces. Errors are ADFS's numbers and texts, raised through BRKV; OSARGS gives 8 for the filing system, and the handles are `$30-$39`. The exit report gives, for each drive, the sectors in use at the end and at most, and the most entries in a directory. The new errors are at the end of the MOS ROM, so nothing in it moved, and `--bbc-fs dfs` and the default are as they were (`make bbcbplus-goldens`, every C test).

**Where it is looser than a real ADFS**: which free space a file is given (the first; ADFS's rule was not found), how far a growing file reaches at a time (the sector it needs), that reserved space comes back at the close (inferred), and that each run of the emulator starts on a compacted disc (the layout is made again from the host files, in the order of their names; holes do not last from one run to the next). None of the gates deletes anything, and each loop is one run, so the last does not touch them. Not modelled: attributes, the library, `*COMPACT`, `*MAP`, `*FREE`, changing discs.

### The gates

`lathe/tests/test_bbc_adfs.py`, every run `--bbc-strict` on memory that is not 0, with `--bbc-fs adfs --bbc-page 1F00`, the tools built with `BBCFS 2` and `ADFS 1`:

- by default (13 s): the names and the twin; `map`, `cdir` and `again` on the BBC giving the twin's names for 29 names; both tools' ROM forms linked from `$1F00`, with what is free; hello compiled, linked and run on a disc that holds only its sources and environment, the directories made by the tools, every file the host's and the emulator's count of sectors the disc's; the directory that cannot be made (error 63); LOADMOD for `$1F00` loading the short image from drive 1, and the tools then compiling, linking and running hello;
- `LATHE_BBC_ADFS=1`: every program of the chain but `for_ranges`, 68 of the 69, every file the host's, at most 2 files open and 1 written (a disc of 12 to 24 files and 180 to 299 sectors; the banked ones' objects and interfaces on drive 1, 16 to 24 files and 78 to 95 sectors); outtest's link (22 files, 572 sectors); both developer's forms, and the fault below;
- `LATHE_BBC_SELFHOST=1`: the compiler compiles each of its 18 modules in the ROM form, every file the host's: 943.0 million cycles, 7.9 minutes at 2 MHz, at most 2 files open and 1 written; the largest disc a compile needs is `gen`'s, 16 files, 610 sectors;
- `LATHE_BBC_ADFS_LOOP=1`: the rebuild on two discs (below);
- `LATHE_BBC_ADFS_REPORT=1` prints each run's files, sectors and entries.

### The rebuild on two ADFS discs

`test_bbc_adfs.Loop` (2026-11-17): the loop of "The linker links the compiler", with both tools and the compiler they make built with `BBCFS 2` and `ADFS 1`, in one run of the emulator under `--bbc-fs adfs`: `*LATHE` compiles the compiler's 25 modules from their sources on drive 0 to drive 1 (`*LATHE ... 0/err.lth 1`), `*LLINK @LINKARG` links them into `1/LATHEC`, `*DIR :1`, `*LOAD` and `*SAVE` give the image its addresses, and the new compiler, `*RUN LATHEC`, compiles `err` and `kernel` again. Every file is the host tools' under its ADFS name. **4,510 million cycles, 37.6 minutes at 2 MHz** (after the merge of the 128 KB module; 4,508 before); at most 2 files open and 1 written; at most 25 entries in a directory.

| Drive | What | Files | Bytes | Sectors of 2,560 | Free |
|---|---|---|---|---|---|
| 0 | the 25 sources (`lth`), the environment (`env`), `LINKARG` | 27 | 584,430 | 2,313 | 247 sectors, 63,232 bytes |
| 1 | the 25 objects (`lo`) and interfaces (`li`), the image `LATHEC`, its six bank files (`BIN`), the map (`map`) | 58 | 626,379 | 2,500 | 60 sectors, 15,360 bytes |

The emulator's count of each drive at the end is the disc's as ADFS counts it, and the most in use at once was the same: the 256 sectors each new file reserves were always there, the map's last (it is 491 sectors, and 551 were free when it was made). **A user's two discs hold the whole rebuild, readable sources and the full map, with 307 sectors (77 KB) to spare.** Drive 0 cannot take objects beside the sources: after the first, less than 256 sectors would be free for the next new file. The module image is not on them ("Not built", below).

A second rebuild on the same discs writes every file over its old one in its own space, which holds unless a file grows past the file after it and no free space holds it: drive 1's 60 free sectors are less than a new file needs, so a file that is not there yet (a new module) needs room made first (`*DELETE` the map, which is written last and made again).

### Faults found

- **A service call in a developer's form after LOADMOD ran the program's bank as a ROM. Fixed.** LOADMOD enters the module's type in the MOS's ROM table; the developer's forms (`*RUN LATHEC`, `*RUN LLINK`, a user's banked program) then load their own banks, which have no header, over the module's. The MOS offers every service call to each slot the table marks, so an error the filing system raised while such a program ran (service call 6, made before BRKV) called `$8003` of whatever bank was latched: its code, at random. It was never seen before because the DFS's tools raise no error in normal use (a missing file is 0); ADFS raises "Not found" for a file in a directory that is not there, which is why `open_out` looks for the directory with OSFILE 5 first. **The fix**: `rt_bbc.start`, in the developer's form, sets the slot's entry in the ROM table to 0 before it loads a bank (`rom_types[SLOT] = 0`, the table at `$02A1`; 5 bytes of fixed code), and leaves it so: the module no longer holds the image (its banks are the program's), so it must not be called as a ROM again until LOADMOD loads the image and enters it once more, as the tools already needed. Chosen over putting it back at the end, which would mark a module whose banks have no header (a `*HELP` after the program would run its code), and over the ROM form's header in every bank of the developer's form, which costs every bank 80 bytes of its window (the compiler's bank 1 has 219 bytes free as the linker judges it) and still needs bank 0's service code loaded. `$02A1` is the table OSBYTE 170 gives on MOS 1.20 (memory, `emulator/NOTES-bbcbplus.md`; LOADMOD asks OSBYTE 170). Tests: `test_bbc_adfs.AfterLoadmod` (by default) runs a user's banked program after LOADMOD under the host's names, the DFS's and ADFS's, in the sixteen- and the eight-bank module: it opens a bad name from code in its bank (an error, caught) and makes service calls 9 and 4 through OSBYTE 143, and ends with its output; with the fix taken out every run fails (a strict fault at `$8008`, or the cycle cap). `test_bbc_adfs.DeveloperForms`: the compiler's developer's form given a bad source name says error 62 with the RAM empty and with the image in it (until the fix the second run did not end well).
  Which service calls reach the ROMs while a program runs: the emulator makes 6 (an error), 4 (a command the MOS does not know, which on a real MOS includes `*CDIR`, offered to the ROMs before the filing system: the emulator gives its ADFS commands to the filing system first) and 9 (`*HELP`), and 7 and 8 (an OSBYTE or OSWORD it does not know). A real MOS makes those too (6 and 4 checked against the MOS 1.20 reassembly, 7 and 8 against BeebWiki; 9 for `*HELP` is memory), and also 5 for an interrupt no handler takes, which the emulator has no interrupts to make, and filing systems make calls of their own (10, claiming the static workspace, when another filing system is selected; 18, selecting a filing system): memory, not checked, and not made while a tool runs unless it changes filing system. All of them go only to slots the table marks, so the fix covers every one.
- **`enum_table` read `counts` before setting it** (a case of the corpus, `lathe/tests/cases/e2e/enum_table.lth`): it relied on 0 in memory, and on what the tools leave below `$7C00` at ADFS's PAGE two entries were `$FF`. It now sets the counts first; the output is the same.
- **`dfs_has_five_files_open_at_most`'s code buffer was 61 bytes for 67** (`emulator/tests/test_bbc_mos.c`): six OSFIND calls of 11 bytes and an RTS written past the end of a stack array; the ADFS test of ten files, with the same pattern, failed with the stack's guard. Both are sized for 11 bytes a call now.

### Not built

- **The module image on the two discs.** The short image is 768 sectors and LOADMOD 2: with them the loop needs more than two discs hold. The loop's module RAM holds the image from power on, standing for LOADMOD run from a disc of its own before the work (which `test_loadmod_at_adfs_page` does run, from drive 1): a disc change before the loop, not in it. A real ROM module needs no file.
- **`*COMPACT`, `*MAP`, `*FREE`, a disc used for months.** The emulator lays each run out as if the disc had just been compacted.
- **A shorter BBC command line** (`*LATHE EXPR`), as for the DFS: the tests replay the host's command lines.
- **A build for `$1D00`** (ADFS without the DFS): a second set of `when` entries would give 512 bytes; one build serves both.

## The texts in the module (2026-11-18)

The module holds the texts of both tools' errors and writes them: the 128 KB EPROM stands alone, with nothing on the disc, and on a machine with no sideways RAM too, since nothing is copied anywhere. It replaced the message file of 2026-11-17 (below), whose `LATHERR` the tools' ROM forms read from the disc. Chosen from the schemes and places measured in [`spikes.md`](spikes.md), "Error messages back in the ROM, measured". Built: `lathe/host/driver/msgpack.py`, the routine `text` of `lathe/rt/bbc/module.asm` and the service call `$4C`, `bbcrom.py` putting the texts in every image, `bbc.error_text` (`lathe/rt/bbc.lth`) with `sys.error_text` (`lathe/src/sys.lth`, the BBC only), `define TEXTS_IN_MODULE`, and the tests `lathe/tests/test_msgpack.py` and `lathe/tests/test_bbc_texts.py`.

### The texts, packed

`msgpack.py` packs the tables the host tools print from (`err.MESSAGES`, `lk_err.MESSAGES`, the one source of the texts) into 256 texts: text n is the compiler's error n, text 255 - n the linker's error n, every other an empty one. It refuses texts where the two ranges meet (the compiler's numbers can grow to 193 before they meet the linker's 61) or a byte is outside `$20-$7E`. The packing is byte pairs: a text is its codes ended by a zero; a code is a character, or one of 159 pairs of codes (the codes `$80-$FF` and `$01-$1F`), each a character or a pair again, chosen as the commonest pair of all the texts until none is used three times; the choice is deterministic. 3,673 bytes: two tables of 160 bytes (the first and second code of each pair, at the code plus `$80`) and 3,353 of texts, against 8,297 as the tools held them.

### The module writes them

- **The call.** A tool's ROM form asks for text Y with OSBYTE 143 (a service call to the ROMs) and X = `$4C`. The MOS pages each ROM in, from slot 15 down, and calls its service entry; the module's service code (the reserved bytes, the same in every bank: 78 of 79 now) takes `$4C` as it takes 4 and 9: it pushes the call and the bank it came in on and selects the home bank, whose code writes `: ` and the text with OSWRCH and returns through `claim`, which selects the bank of entry again; the MOS then selects again the slot that was selected. So the call works from any bank, and from fixed code inside a `with` block of a sideways RAM slot (the MOS puts that slot back: `rt_bbc` keeps `$F4` right).
- **The routine** (`module.asm`, "An error's text"): it passes Y texts, each to its zero, and writes the codes of the next; a pair is written by `put_code`, which pushes the second code and calls itself for the first (the pairs nest at most 6 deep, 3 bytes of stack a level; `msgpack.py` refuses more than 8). It uses `$A8`/`$A9`, the MOS's workspace for * commands, not the tools' zero page. 91 bytes of the home bank and 4 of the reserved bytes, assembled with the rest by `asm/pyasm.py`.
- **Where.** `bbcrom.py` puts the texts in every image it writes, of sixteen banks and of eight (since 2026-11-18 in parts, wherever there is room: "In parts, in any bank", below).
- **If no ROM claims the call** (no module, or one whose service code is not this), nothing is written, and the error is its number alone with the rest of its line, the status the same.

### In parts, in any bank (2026-11-18)

Until then the texts had to be in the home bank with the module's code, 4,227 bytes in one bank after its program's code, which the 32K image's eight banks did not have although they had more than that free in all ("The 32K Model B", "The image"). Now the texts are one or more **parts**, each the code of `lathe/rt/bbc/texts.asm` (the walk past the texts before the one asked for and the pairs' writer, 81 bytes) with its own tables, packed by `msgpack.py` from its own run of texts (`msgpack.split`: runs of about the same length, text 0 in the first), and `bbcrom.layout` puts each whole wherever there is room:

- **As few parts as fit** (`bbcrom.MOST_PARTS`, 4), each the largest first in the home bank's room if it holds it, else in the first area the pieces would take; then the pieces of the resident parts in what is left, as before. `layout(parts=N)` and `image(parts=N)` ask for N or more (the tests do).
- **How the home bank enters a part.** The home bank's `text` writes `: `; then, for a part in another bank, it finds the part of text Y in the table of the parts (each part's first text, bank and entry less 1), pushes the entry and a byte, and jumps to `switch`, the `LDA $BFF0,X` of `back` in the reserved bytes: the next bytes of the part's bank pull the byte and return into the part, which passes the texts before Y in it, writes the text and ends through `claim`, which selects the bank of entry again. A label, no byte of the reserved bytes more. One part in the home bank (`part_at_home`) is entered with a `JMP` and needs no table; `bbcrom.py` defines `several_parts` or `one_part_away` for the others (`pyasm` has `.ifdef` and no `.else`).
- **What it costs.** In the B+128's 128 KB image (one part, in the home bank after the module's code, as before) the `JMP`: **1,957 bytes free** (1,960; 769 in the ADFS build, 772). Two parts cost a second copy of the part's code and of its tables of pairs, and their texts packed apart: in the 32K image 2,070 and 1,803 bytes (3,873, against 3,754 in one part: 81 bytes of code and 38 of tables more), and the home bank's search and table of the parts (its code and tables 639 bytes there).
- **The 32K image** now fits the 128 KB EPROM: the compiler's 32K form in banks 0 to 4, the linker's in 5 to 7, the module's code and tables (639 bytes) and texts 0 to 153 in bank 7 after lk_alloc and lk_graph, texts 154 to 255 in bank 3; the resident parts 5,345 and 8,434 bytes in pieces; **1,879 bytes free** of the 131,072 (with `BBCFS 1`; the sixteen-bank image of before used 192 KB). Its default (`test_bbc_ram32.BANKS`) is the eight-bank image.
- **Tested** (every run `--bbc-strict` on filled memory): `test_bbc_rom128.Layout` (two parts where no bank holds the texts whole, each whole in its bank to `$BFEF`; one part in the home bank where it has room; `parts=3`); every one of the 256 texts from an image of `test_bbc_rom.py`'s programs in three parts, from banks 0 and 7 and through LOADMOD (`RomModule8.test_the_texts_in_three_parts`); both tools' errors from the B+128's 128 KB image with the texts in three parts, error 5 inside `with STRING` among them, and the number alone when no ROM claims the call (`Rom128.test_errors_from_the_128k_image_with_the_texts_in_three_parts`); the 32K image's 256 texts on the Model B from banks 0 and 7 and through LOADMOD (`test_bbc_ram32.EightBanks`), and both tools' errors there (`Ram32`).
- **For a loader that carries the module's code as a file** (MODLOAD's HOME, on another branch): the home bank's code now refers to its texts only through the table of the parts after its tables (or `part_at_home`), and each part is assembled for its bank and address (`bbcrom.text_part(first, last, at, claim)`, `claim` from the module's labels). The simplest for such a loader: one part in the home bank right after the module's code and tables, `module_code(..., parts=[(0, home, home_at + size)])` and the part's bytes appended to the HOME file, which then ends at the part's end; a part elsewhere would be a file of its own with its bank and address.

### The tools

`define TEXTS_IN_MODULE`, a name no module has: `lathec-bbc.env` and `linker-bbc.env` say `unless ROMFORM define TEXTS_IN_MODULE 0` and `when ROMFORM define TEXTS_IN_MODULE 1`, so the BBC's ROM forms (sixteen banks and eight, and the same images through LOADMOD) hold no texts and every other build holds them as before; `compiler-bbc.env` and `compiler-bbc-bank.env` say 0. `err.lth` and `lk_err.lth` test it inside `#if PORTS == 2`. With it, `err.fatal_start` calls `sys.error_text(number)` after the number, and `lk_err.begin` `sys.error_text(255 - n)`; `bbc.error_text` is `LDA #143`, `LDX #$4C`, `JMP OSBYTE`, 7 bytes of fixed code. The developer's forms (`*RUN LATHEC`, `*RUN LLINK`) keep their texts, as before: they do not run from the module image, and their main RAM has room.

**What an error looks like** with nothing on the disc: exactly what the host tools print, from both images (`test_bbc_texts.py` from the tool chain's sixteen-bank image, `test_bbc_rom128.test_errors_from_the_128k_image` from the eight-bank one; `test_src_lathec.OnTheBBC`, `test_bbc_dfs`'s names that meet and `test_bbc_adfs`'s directory that cannot be made): a position, a value after the text (`error 136: ... its size is 3`), `#error`'s text after it, the usage, error 5 raised inside lex's `with STRING` (slot 13), the longest text (182), a link error's name after its text. Every one of the 256 texts the module writes is the host's, in every power-on bank and through LOADMOD in the RAM form, whole and short, in both images (`test_bbc_rom.py`, `test_bbc_rom128.RomModule8`). When no ROM claims the call (an image whose service code answers `$4D` in its place), the number alone: `undefined.lth:3:3: error 40`, `link error 2: none.env`.

### What it costs

Measured by the gate (`test_bbc_rom128.py`, the eight-bank image), against the message file's tree (8dd784a):

| | The message file | The texts in the module |
|---|---|---|
| Free in the image, `BBCFS 0` | 5,815 | **2,295** |
| Free in the ADFS build (`BBCFS 2`, `ADFS 1`) | 4,610 | **1,107** |
| The module's code and tables | 519 | 4,291 (the texts 3,673, the routine 91) |
| Resident parts, `BBCFS 0`: compiler, linker | 11,849, 9,829 | 11,686, 9,811 |
| The linker's bank 1 as judged, `BBCFS 0` / ADFS | 15,309 / 15,934 | 15,225 / 15,850 |
| Main RAM free, eight-bank ROM form, `BBCFS 0`: compiler, linker | 3,874, 3,215 | 4,037, 3,233 |
| Main RAM free at ADFS's PAGE, `BBCFS 2`: compiler, linker | 2,253, 1,581 | 2,416, 1,607 |

So the texts cost 3,520 bytes of the image with `BBCFS 0` (3,503 with ADFS): 3,673 of texts and 91 of routine, less the readers of the file the tools no longer have (the compiler's 168 bytes of fixed code and the linker's 84 in its bank and 25 fixed). The tools' code banks are as they were but the linker's bank 1. The compiler gains 163 bytes of main RAM and the linker 18 (26 at ADFS's PAGE).

Since FBUF leaves out the stores nothing reads (2026-11-18, [`spikes.md`](spikes.md), "Built: stores that nothing reads"): **3,008 bytes free** with `BBCFS 0` and **1,844** in the ADFS build; resident parts 11,907 and 9,675; the linker's bank 1 15,018 as judged; main RAM free at ADFS's PAGE 2,140 for the compiler (its pass is fixed code) and 1,747 for the linker.

**Cycles** (the emulator; `*LATHE` and `*LLINK` with no arguments write the usage, error 60 and link error 1):

| | The message file, with it on the disc | without it | The texts in the module |
|---|---|---|---|
| `*LATHE`, eight banks | 861,934 | 850,191 | 852,232 |
| `*LLINK`, eight banks | 607,461 | 599,297 | 651,777 |
| `*LATHE`, sixteen banks | 861,628 | 849,885 | 852,082 |
| `*LLINK`, sixteen banks | 563,532 | 555,308 | 610,315 |
| `*LATHE e.lth .` (an empty module, no error), eight / sixteen banks | 887,524 / 887,218 | | 877,871 / 877,407 |

A start-up is about 9,700 cycles shorter (146 bytes less resident part to copy). Writing a text costs the routine's walk past the texts before it: about 11,700 cycles for error 60 (80 characters), 28,400 for error 136, 53,500 for the linker's error 1, whose text is the last but one (27 ms at 2 MHz, the most a text takes); the file cost about 11,700 in the emulator, whose MOS reads a file in no time, and three sectors of a real disc, about half a second. From the eight-bank image, every file the host tools' (`test_bbc_rom128.py` with `_SELFHOST`, `_SELFLINK`, `_LOOP` and `_ADFS`): the self-compile 874.0 million cycles in the ROM form (877.0 million with the message file) and 912.0 million through LOADMOD (915.0), the linker's link of the compiler 3,462.8 million (3,463), the rebuild loop 4,478.2 million (4,484), the rebuild on two ADFS discs 4,499.5 million (4,504), 37.5 minutes at 2 MHz.

The disc no longer holds `LATHERR` (9,258 bytes, 37 sectors).

### Before it: the message file (2026-11-17)

Replaced on 2026-11-18 by the texts in the module (above): `msgfile.py`, `LATHERR`, the readers and `define MESSAGE_FILE` are gone. As it was built and measured:

The texts of the errors are 5,494 bytes in the compiler (`err`'s three strings, in the region `MSGS`, copied to sideways slot 13 at every `*LATHE`) and 2,803 in the linker (`lk_err`'s two, in its first bank): 6 % of the 128 KB image, and in the linker's fullest bank. The BBC's ROM forms of both tools now hold none: an error prints its text from a file on the disc if it can open it, and otherwise its number alone, with everything else as before. Turbo Pascal 3 did the same with its optional `TURBO.MSG`. Built: `lathe/host/driver/msgfile.py`, `put_text()` in `lathe/src/err.lth` and `lathe/src/lk_err.lth` under `define MESSAGE_FILE`, `bbc.seek` and `bbc.open_unmapped` (`lathe/rt/bbc.lth`) with `sys.seek` and `sys.open_unmapped` (`lathe/src/sys.lth`, the BBC only), and the tests `lathe/tests/test_msgfile.py`.

#### The choice, in the environment

`define MESSAGE_FILE`, a name no module has: `lathec-bbc.env` and `linker-bbc.env` say `unless ROMFORM define MESSAGE_FILE 0` and `when ROMFORM define MESSAGE_FILE 1`, so it is 1 in every ROM form (sixteen banks and eight) and 0 in the developer's forms; `compiler-bbc.env` and `compiler-bbc-bank.env` (the compiler's test programs on the BBC) say 0. `err.lth` and `lk_err.lth` test it inside `#if PORTS == 2`, so no other machine's environment needs it. Every other build keeps its texts and is the same: the images, bank files and maps of both tools' developer's forms with `BBCFS` 0, 1 and 2, of `errtest` and `kerneltest` on the BBC and on the default machine, and the objects of `err` and `lk_err` everywhere, compared before and after. The objects of `bbc` differ in every build (the two new functions, linked only where they are called) and `sys.li` in the BBC's (the two inline functions).

The developer's forms keep their texts: they load their banks from the disc anyway, and their main RAM has room (5,329 and 4,952 bytes free with `BBCFS 0`).

#### The file

One file for both tools, `LATHERR`, written from the tables the host tools print from (`err.MESSAGES`, `lk_err.MESSAGES`), so it says what they say:

| Bytes | What |
|---|---|
| 0-255 | the compiler's index: byte n is the low byte of the place of error n's text |
| 256-511 | the high bytes |
| 512-1023 | the linker's index, the same |
| 1024- | the texts, each as it follows the number in the error's line, `: ` and the text, ended by a zero: first `: ` alone, where every number with no text points; then the compiler's, then the linker's |

9,258 bytes, 37 sectors. An entry for every byte, so the reader checks nothing; the zero ends a text and the end of the file reads as one, so a file cut short ends the text. The tools find a text by number with three seeks (OSARGS 1, `PTR#`) and no arithmetic: the low byte, the high byte, the text. A seek costs no disc time of its own: a filing system reads the sector that holds the byte asked for, so an error reads three sectors (one more if the text runs into the next), about half a second on a real DFS at a revolution a sector, where reading forward through the file to its last text would read 37, several seconds. That is why the index is at the front and why there is a seek.

**The name.** `LATHERR` has no `.`, which the BBC's mapping of names leaves as it is ("File names on the BBC"): it is `$.LATHERR` on the DFS (`X.LATHE` it would have been as `lathe.msg`), `LATHERR` in the current directory on ADFS, and `LATHERR` in the emulator's directory, seven characters, legal under both. That matters for the compiler: an error can be raised inside a `with` block, so everything the error path reaches is kept in fixed memory (`lk_tab.F_FIXED`), and `bbc.open` would reach `bbcfs.map`, which the ROM forms place in a bank; kept fixed, `bbcfs` cost the compiler 454 bytes of main RAM with `BBCFS 2` (412 bytes over at ADFS's PAGE in the eight-bank form). So the compiler opens the file with `bbc.open_unmapped`, which copies the name and calls OSFIND, and the linker, whose `lk_err` is in a bank, with `sys.open_in`; a name without `.` makes both open the same file under every filing system.

**Where it is looked for**: in the current directory and drive, as every name without a drive is. In the rebuild on two ADFS discs, in the root of drive 0 beside the sources.

**Files open at once.** At an error the compiler has its source and perhaps an interface open, the linker an object file and perhaps the image or a bank file: the message file is the third, of the DFS's five and ADFS's ten, and it is closed again before the line ends.

#### What an error looks like

With the file on the disc, exactly what the host tools print (`test_src_lathec.OnTheBBC`, `test_bbc_dfs`'s names that meet, `test_bbc_adfs`'s directory that cannot be made, and `test_msgfile.py`, each against the host). Without it:

| With `LATHERR` | Without |
|---|---|
| `rows_record_size.lth:7:8: error 136: a record in an array declared rows must be padded to a size that is a power of two; its size is 3` | `rows_record_size.lth:7:8: error 136 3` |
| `error_directive.lth:4:1: error 181: #error: this configuration is not supported` | `error_directive.lth:4:1: error 181: this configuration is not supported` |
| `undefined.lth:3:3: error 40: undefined name` | `undefined.lth:3:3: error 40` |
| `lathec: error 60: usage: lathec [-c6502\|-c65c02] ...` | `lathec: error 60` |
| `link error 1: usage: link ENV MAINMODULE OUT.bin OUT.map OBJECT.lo...` | `link error 1` |
| `link error 2: cannot open file: none.env` | `link error 2: none.env` |

The status is the same either way. `lathe/host/err.py` and `lathe/host/lk_err.py` list what each number means.

#### What it costs and what it saves

Bytes as placed, the eight-bank ROM forms with `BBCFS 0`:

| | The compiler | The linker |
|---|---|---|
| Texts out | 5,494 (slot 13's constants, copied at every `*LATHE`) | 2,803 (bank 1) |
| Code out | `message_start` 130, `fatal_start` 191 to 72: 249 (fixed) | `begin` 220 to 33: 187 (bank 1) |
| Reader in | `put_text` 89, its name 8, `bbc.open_unmapped` 54, `bbc.seek` 17: 168 (all fixed: the error path runs inside `with` blocks) | `put_text` 77 (bank 1); its name 8 and `bbc.seek` 17 (fixed) |
| Net | 5,575 less; resident part 14,046 to 13,973 (with the compiler's smaller code: 11,932 to 11,849) | 2,913 less in bank 1 (judged 3,506 to 579 for `lk_err`), 25 more fixed; resident part 9,772 to 9,797 |

The reader is in fixed memory in the compiler, not in a bank: `err.fatal` is called inside `with` blocks (kernel's, fbuf's, lex's), so the linker keeps it and all it reaches fixed, and before this `message_start` and `fatal_start` were fixed for the same reason. It is smaller than what left fixed memory with it, so main RAM gains in every ROM form (below); its buffers are none (it writes each byte as it reads it) and its variables are three bytes of frame.

**The sideways slots** of the compiler's ROM form (16,352 bytes each, `$8000-$BFDF`): slot 12 (the name heap) 7,136 free, as before; **slot 13 7,392 free, 1,898 before** (`fbuf`'s buffer and labels, `lex.string`, `kernel.tokens`: 8,960 bytes of variables, and no constants, so no bank file: `when ROMFORM bank WIN 33 $0D`); slot 0 5,968; slot 1 10,656. The linker's (0, 1 and 12) are as they were.

**The start-up.** `*LATHE` no longer copies 5,494 bytes into slot 13, one bank switch a byte. `*LATHE` and `*LLINK` with no arguments (the usage, read from the file; then without it), in cycles:

| Image | `*LATHE` before | after, with the file | without | `*LLINK` before | after, with | without |
|---|---|---|---|---|---|---|
| sixteen banks, both tools | 1,473,470 | 978,160 | 966,417 | 555,228 | 563,528 | 555,304 |
| eight banks, the compiler alone | 1,472,011 | 976,503 | 964,760 | | | |
| eight banks, both tools | (did not link) | 976,509 | 964,766 | | 607,460 | 599,296 |
| sixteen banks, with the compiler's smaller code: before (that work alone) and after | 1,358,051 | 861,628 | 849,885 | 555,228 | 563,532 | 555,308 |
| eight banks, both tools, the merged tree | | 861,934 | 850,191 | | 607,461 | 599,297 |

So **495,310 cycles less at every `*LATHE`** (a quarter of a second at 2 MHz), and about 11,700 more for reading a text, which the emulator's MOS charges nearly nothing for (a real disc adds its three sectors). The linker's start-up in eight banks copies its larger resident part (lk_out and lk_op are fixed there).

#### Main RAM

Free of `PAGE-$7BFF` and `$0401-$06FF` (26,111 bytes at `$1900`, 24,575 at `$1F00`) less what the map places there; the eight-bank forms linked as `test_bbc_rom128.AdfsMainRam` links them, so that a form that did not link before is measured too. Before is 05824fd; "compiler's work" is the branch that made the compiler's code smaller ("The tools' banks"), alone; after is both together (with the linker's refactorings below, whose `add_wk` and `sub_wk` are 56 bytes of `lk_tab`, which is fixed):

| Form | The compiler: before | compiler's work | after | The linker: before | after |
|---|---|---|---|---|---|
| developer's, `BBCFS 0` | 5,329 | 7,658 | 7,658 | 4,952 | 4,899 |
| ROM, sixteen banks, `BBCFS 0` | 1,637 | 3,787 | 3,874 | 4,027 | 3,946 |
| ROM, eight banks, `BBCFS 0` | 1,672 | 3,787 | 3,874 | 3,272 | 3,215 |
| developer's, `BBCFS 1` | 4,893 | 7,222 | 7,222 | 4,508 | 4,455 |
| ROM, sixteen banks, `BBCFS 1` | 1,611 | 3,760 | 3,847 | 3,994 | 3,904 |
| developer's, `BBCFS 2`, `$1F00` | 3,200 | 5,526 | 5,526 | 2,816 | 2,762 |
| ROM, sixteen banks, `BBCFS 2`, `$1F00` | 16 | 2,168 | **2,254** | 2,401 | 2,312 |
| ROM, eight banks, `BBCFS 2`, `$1F00` | 51 | 2,166 | **2,253** | 1,646 | 1,581 |

The message file gives the compiler 75 to 87 bytes in every ROM form and nothing in the developer's forms, which are the same; the linker loses 53 to 90 (the reader's 25 fixed bytes, `add_wk` and `sub_wk`, and in the ROM forms stubs that moved). The splits in `lathec-bbc.env` stay where the compiler's work put them: the ROM form's code ends at `$4756` with `BBCFS 1` (`$47A9` before the message file) below the split at `$4F00`, and at `$4D85` with `BBCFS 2` below `$5220`.

## The 32K Model B (2026-11-18)

The owner asked for a variant for a 32K BBC Model B: no sideways RAM, no shadow screen, the Acorn DFS (PAGE `$1900`, 7-character stems, 31 files a side, 5 open), mode 7 (HIMEM `$7C00`). It cannot compile itself there, but it should compile and link programs. This section is the compiler's part and the machine's; the linker's 32K form is being built apart.

### The variant, as built

- **The switch**: `define RAM32` in the tools' environments, 0 by default; `bbcrom.rom_env(SOURCE, OUT, FIRST, 8, settings={'RAM32': 1})` makes the 32K ROM form (the new `settings` sets any `define` of the source, and refuses one the source does not have). In `lathe/src/lathec-bbc.env` the `unless RAM32` entries are the B+128's, as before, and the `when RAM32` entries the 32K form's: its own split (code `$1900-$2E2F`, data `$2E30-$7BFF`, `more data $0401-$06FF`), no sideways RAM bank, every region `fixed`, `define FIXED_REGIONS 1`, `SMALL 1`, and its placement. Every other environment of the compiler says `define RAM32 0`, so that the twins' `#if RAM32` has a value everywhere. Only the ROM form with `ADFS 0` is given: there is no 32K developer's form and no 32K ADFS layout.
- **The machine**: the emulator's `--bbc-model b` (no sideways RAM unless given, no private RAM, ROMSEL at every address of `$FE30-$FE3F` holding four bits, OSBYTE 0 giving 1, `--bbc-shadow` refused) and `--bbc-mode N` (HIMEM is where that mode's screen starts; a program's write from there to `$7FFF` is a failed check, `screen-writes` in the report). `boards.BOARDS['bbc32']` is that machine with `--bbc-fs dfs` and `--bbc-strict`. C tests: `test_chip_bbc_memory.c` (`model_b_romsel_is_fe30_to_fe3f_of_four_bits_and_has_no_private_ram`: a write anywhere in `$8000-$BFFF` changes nothing read there, the module's ROM included), `test_bbc_mos.c` (`model_b_os_version_and_himem_by_mode`, `writes_to_the_screen_are_counted`), `test_cli.c` (`cli_bbcbplus_model_b_and_mode`). What the emulator still does not show of a real Model B: MOS 1.20's own code and timing (the MOS is the emulator's, behind MOS 1.20's entry points), interrupts, a `VDU 22` that changes the mode while a program runs (HIMEM is the mode at power on), the 8271 or 1770 and a real DFS's catalogue and timing (the DFS is the host directory with the DFS's names and limits), and the rest of "What the emulator cannot show" below.
- **The regions in main RAM, and the compiler told so.** A region is put in fixed memory by `region NAME fixed` (or no entry). That alone was not enough: the linker keeps a function with a `with` block, and all that runs inside one, in fixed memory whatever the region is (it marks them from the kind 6 fix-ups and the calls flagged inside blocks, before it places anything), and a block of a fixed region maps bank 0, which on the BBC is sideways slot 0. With the regions fixed and nothing else, the compiler kept 8,022 bytes of functions in main RAM (`fbuf` 3,184, `kernel` 2,169, `lex` 1,025, `decl` 669, `out` 487, `err` 404, `src` 88), and even the small build's capacities were 4,106 bytes over main RAM. So the compiler now takes `-fREGION` (`lathe/host/README.md`, "Command lines"; host and twin): a block of such a region is its body alone (no `rt_with.map`, no temporary, no kind 6 fix-up) and its calls are not flagged unless a block around it maps a bank, so the linker keeps nothing for it. `build.py` gives `-fNAME` for every `region NAME fixed` of an environment with `define FIXED_REGIONS 1`; no other environment has it, so no other build changed. The linker needed no change. What it costs the other builds: only the compiler's own code changes (the option, `parts.is_fixed`, the block), and every object it writes for an input without `-f` is the same; in the B+128's 128 KB image the compiler's bank 0 is 15,652 bytes as judged (15,466), its resident part 11,855 (11,849), the image's free bytes 5,543 (5,815), the self-compile 881.0 million cycles (877.0), and at ADFS's PAGE 2,225 bytes of the compiler's main RAM are free (2026-11-18). With the texts in the module merged too ("The texts in the module"): the 128 KB image has 2,023 bytes free (1,960 with the check of HIMEM, which every image has since: "Started in another screen mode") (`BBCFS 0`; the module's code and tables 4,291 bytes in bank 3), the compiler's resident part is 11,692 bytes and the linker's 9,811, with 4,009 and 3,233 bytes of main RAM free in the eight-bank ROM form (3,982 and 3,931 in the sixteen-bank one with `BBCFS 1`), and at ADFS's PAGE (`BBCFS 2`) 2,388 and 1,607. Tests: `test_banked_data.py` (four), `test_build.py`, `test_src_lathec.py` (eight inputs, so the twin is compared with the host), `cases/e2e-config/fixedblk.lth` (the same output with the region in a bank, fixed and told, and all in one), `test_farcall.py` (where its functions went).
- **The layout** (`when RAM32` in `lathec-bbc.env`): with nothing kept fixed every module of the compiler must fit a bank whole as the linker judges it, and they total 80,814 bytes (with `bbcfs`, 81,304) of the 81,360 five banks hold: they do not pack. `fold` (1,654 judged, 1,301 placed, the module the others call most) stays in main RAM, and the rest packs so:

| Bank | Modules | Judged (of 16,272) | Placed |
|---|---|---|---|
| 0 | expr, parts, out | 16,170 | 14,700 |
| 1 | gen, lathec, err | 15,988 | 14,234 |
| 2 | decl, asmblock | 16,007 | 13,693 |
| 3 | kernel, lex, src, fbuf, cond | 15,667 | 13,508 |
| 4 | reg, inlines, typetab, bbcfs | 15,818 | 13,830 |

Since FBUF leaves out the stores nothing reads (2026-11-18), judged 16,071, 15,650, 15,788, 15,829 and 15,476, placed 14,627, 13,969, 13,517, 13,675 and 13,584 (the pass is in bank 3, with `fbuf`); the resident part 5,303 bytes, 193 bytes free.

- **Main RAM** (`BBCFS 1`, measured from the map; the figures of 2026-11-18 before the texts went into the module, which took 74 bytes of `err` out: since then the resident part is 5,345 bytes and **184 bytes are free**): resident 5,419 bytes, against 11,849 in the B+128's eight-bank form: fixed code 3,106 (`fold` 1,301, `bbc` 748, `rt_bbc` 377, `rt_math` 348, `rt_frame` 171, `sys` 78, `$init` 49, `$start` 19, `disk` 15), 329 stubs 1,974, constants 339. Variables and frames 20,582, of which the tables: the name heap 3,072, the symbol columns 4,488 (264 rows of 17 bytes), the members 528, the text memory 768, the token memory 384, FBUF's buffer 1,536 and labels 768, LEX's string 264, OUT's table and fix-ups 520, DECL's import rows 560, the types 328; the rest are tables of every build (REG's slots and operands 2,578, GEN's 769, ASMBLOCK's labels 564, `bbc`'s 483, `rt_frame`'s stack 256 and so on). **Free: 110 bytes** of `$1900-$7BFF` and `$0401-$06FF` (the variables end at `$7BFD`, `more data` at `$0699`).
- **The capacities**: the small build's (`SMALL 1`) with four of RAM32's own (`#if RAM32` inside `#if SMALL` in the twins; `script_host.RAM32`, checked by `test_memory.py`), chosen by the corpus's peaks (`memory_report.py`'s gauges, module by module) to compile the most modules of `lathe/src` and `lathe/rt` in the room the layout leaves: what ran out first in each refused module was, in order of how often, the name heap, an import's rows, the function buffer and the types, so the room went there and nowhere else:

| Table | Full | Small build | 32K form | Why |
|---|---|---|---|---|
| Name heap | 9,216 | 1,536 | **3,072** | a module with nothing but `host` takes about 1,300; `fbuf.lth` needs 2,579, `lk_map.lth` 2,876 |
| Function buffer | 4,096 | 1,024 | **1,536** | about 1,180 bytes of code in one function; `lk_map.lth` needs 1,275, `lk_name.lth` 1,281 |
| Types | 64 | 32 | **40** | the linker's modules need 33 to 36 (imported records count) |
| Import rows (`MAX_WANTS`) | 160 | 48 | **56** | `cond.lth`'s longest import list names 50; 64 did not fit main RAM by 256 bytes, a table being too large for what `more data` had left |
| Symbols, members | 560, 512 | 264, 264 | 264, 264 | above 256, which a word index needs; the modules that fit use 180 at most |
| Text, tokens, string, constant table, labels, weights | | | as small | no module of the corpus that fits the rest needs more |

### What the 32K form compiles

`LATHE_BBC_RAM32=1 python3 -m unittest test_bbc_ram32` (`Assessment`, 2 minutes): every module of `lathe/src` and `lathe/rt` that the host compiler compiles, with its options, compiled by `*LATHE` on the Model B (`bbc32`, DFS names, `--fill-ram`, `--bbc-strict`) from the eight-bank image; the oracle is the host compiler at the 32K form's capacities (`lathe/tests/lathec_ram32.py`). Every compile gives the host's files, or the host's error. **52 of 75 compile** (2026-11-18), in 750.6 million cycles, 6.3 minutes at 2 MHz. (Corrected 2026-11-21: since the linker's code under `LKDYN` grew on 2026-11-20, `lk_name.lth`, compiled with `-dLKDYN=1` as here, needs 3,110 bytes of names, measured by a real compile at the 32K form's capacities, and is refused there, error 70; its row below is of 2026-11-18. On 2026-11-21 53 of 79 modules compiled at these capacities, by the host oracle; Image B's compiler takes 54 of them at both pages, `lk_name` among them: "The compiler: the name heap begun at PAGE".)

| Module | Lines | Names (of 3,072) | Symbols (264) | Members (264) | Largest function, buffer bytes (1,536) | Labels (128) | Cycles | At 2 MHz |
|---|---|---|---|---|---|---|---|---|
| `lathec.lth` | 276 | 1,691 | 97 | 56 | 507 | 16 | 25.7 million | 13 s |
| `typetab.lth` | 278 | 1,546 | 70 | 69 | 495 | 9 | 15.7 million | 8 s |
| `out.lth` | 461 | 2,576 | 137 | 81 | 874 | 24 | 32.6 million | 16 s |
| `cond.lth` | 575 | 2,086 | 127 | 123 | 645 | 15 | 38.7 million | 19 s |
| `lk_map.lth` | 628 | 2,876 | 178 | 126 | 1,275 | 28 | 50.1 million | 25 s |
| `lk_name.lth` | 738 | 2,754 | 166 | 122 | 1,281 | 32 | 50.0 million | 25 s |
| **`fbuf.lth`**, the largest that compiles | 917 | 2,579 | 143 | 86 | 937 | 16 | 47.0 million | 23 s |
| `rt/bbc.lth` | 476 | 1,542 | 70 | 44 | 366 | 18 | 14.2 million | 7 s |

Refused, with the limit reached first: the name heap (error 70) for `err`, `expr`, `lex`, `reg`, `inlines`, `parts`, `asmblock`, `kernel`, `lk_scan`, `lk_envf` (3,206 to 6,993 bytes of names); an import list of more than 56 names (89) for `gen`, `decl`, `lk_alloc`, `lk_graph` and four test programs; a function too large (75) for `lk_tab`, `outtest`, `asmtest`, `inlinetest`; a string over 264 bytes (7) for `lk_err`. So the shape it takes: a module of up to about 900 lines that imports a few modules with lists (up to 3 KB of names, its own and its imports' together), up to about 260 symbols, functions of up to about 1,200 bytes of code, strings and constant tables of up to 264 bytes, up to 40 types, up to 56 names in one import list. Of the tools' own modules the compiler's `fbuf.lth` (917 lines), `cond.lth`, `out.lth`, `typetab.lth`, `fold.lth`, `src.lth` and `lathec.lth`, and the linker's `lk_name`, `lk_map`, `lk_fix`, `lk_emit`, `lk_place`, `lk_win`, `lk_boot` and the smaller ones.

**Against the B+128**: `src.lth` takes 11.6 million cycles here and 9.2 million from the B+128's eight-bank image, `fold.lth` 18.3 against 16.0 (`test_bbc_rom128.Compiler8`, `BBCFS 0`): the 32K form maps every name to the DFS's and makes more far calls (kernel's functions are in a bank now). A program of several modules: `test_bbc_ram32.Ram32` compiles `cases/e2e-config/farcall.lth`'s twelve modules (the program, five libraries, the run-time modules) on the Model B, each file the host's, in 59.4 million cycles, 30 seconds at 2 MHz, before the disc's own time.

### The image

`test_bbc_ram32.build_image` (2026-11-18, with the linker's 32K form and the texts in the module merged): the compiler's 32K form in banks 1 to 5 and the linker's in 6 to 10, both with `BBCFS 1`, in the module's **sixteen-bank form** (scheme `direct16`), banks 0 to 11 in use (192 KB), 80,134 bytes free; bank 0 holds the module's code and tables with the texts of both tools' errors (4,314 bytes) and both resident parts (the compiler's 5,345 bytes, the linker's 7,839), bank 11 the rest of the linker's. On the Model B with nothing on the disc each tool's errors are the host's, word for word (`Ram32.test_errors_have_their_texts_with_nothing_on_the_disc`).

(Since 2026-11-18 the 32K image is the module's eight-bank form, the 128 KB EPROM: the texts of the errors are in two parts in two banks, and the image has 1,879 bytes free: "The texts in the module", "In parts, in any bank". What follows is why it could not be before.)

**Why not the 128 KB eight-bank form.** The module's code and tables with the texts are 4,227 bytes (in the eight-bank layout), and must be in one bank, the home bank, after that bank's code: the text code reads them there. With both 32K forms in eight banks (the compiler in 0 to 4, the linker's eight-bank form in 5 to 7) the most room after a bank's code is 3,230 bytes (bank 7, lk_alloc and lk_graph), so the image is refused (`EightBanks`), although the eight banks have about 2,100 bytes free in all. Before the texts, with the linker of the B+128 beside the 32K compiler, it fitted with 5,192 bytes free. To have both 32K forms and the texts in 128 KB the module needs one of: the texts in two parts in two banks (the compiler's and the linker's, each with a copy of the reader, the home bank passing the call on by a read of `$BFF0+n` at an address that is the reader's in the other bank); or the tools reading the texts themselves through `rt_bbc` from a bank and address the module gives them (each tool's resident part about 60 bytes larger, which the compiler's 184 free bytes would allow); or about 1,000 bytes of the tools' code out of one bank, which main RAM does not have. Not built: the owner's choice, against a 256 KB EPROM (a 27C020, 192 KB of it used).

### The linker told of its fixed regions

`linker-bbc.env` under `when RAM32` now says `define FIXED_REGIONS 1` and `region NAME fixed` for `LKLOCAL`, `LKCALLS`, `LKSLOTS` and `LKNODES`, and for `LKWORK` too in the sixteen-bank form (`unless ROM128`), so the linker's twins are compiled with `-f` for them and their blocks map nothing. Measured (`BBCFS 1`, from the maps):

| Form | Kept fixed for blocks | Resident part | Banks as judged |
|---|---|---|---|
| eight banks, before (the other agent's) | 721 (lk_name 191, lk_alloc 184, lk_graph 180, lk_fix 166) | 9,095 | 15,793 / 15,983 / 16,031 |
| eight banks, `-f` for all five regions | 0 | 7,821 | 15,961 / 16,159 / **16,327: 55 over** |
| **eight banks, as built** (`LKWORK` not told) | 530 (lk_alloc, lk_graph, lk_fix) | **8,434** | 15,793 / 16,159 / 16,031 |
| **sixteen banks, as built** (all five told) | 0 | **7,839** | room to spare |

Besides the kept functions, `lk_tab`'s own blocks (it is fixed) are 526 bytes shorter. The split of the code and data ranges is `$3A12`, where the eight-bank form's code ends, so the data range is 648 bytes longer; the linker's capacities are as they were (`LKSMALL 2`): in the sixteen-bank form 1,708 bytes of main RAM are free (629 of them below the split, the rest in `more data` and at the top), in the eight-bank form 1,113. Giving them to the capacities, about 40 bytes a function at the proportions of "The linker on a 32K BBC" (some 16 functions, nodes and their share of slots, calls and symbols more), is left to the linker's agent: it changes `LKSMALL 2` in host and twin. `lk_ram32.py`'s assessment (`test_lk_ram32.py` with `LATHE_LK_RAM32_ALL=1`) is the host linker at the same capacities, so what it links is unchanged but for one program (srctest, typetest and copytest, which the texts' leaving `err` brought from 297 functions to 296: it links now; the test's program stopped by too many functions has errtest too, 310). On the BBC, from the eight-bank image with this linker (and the texts in the module), its links are 3 to 9 % faster: lextest 152.2 million cycles (157.3), fbuftest 177.2 (183.8), kerneltest 166.5 (176.0), the 25 KB program 215.6 (222.8), kerneltest + copytest + compare 262.7 (289.4); the files read and written are as before but for a few KB less read (the objects of `err` and `lk_err` are smaller without their texts).

### Both tools on the Model B

`test_bbc_ram32.Ram32` (2026-11-18): on `boards.BOARDS['bbc32']` (the Model B, the DFS's names, `--fill-ram`, `--bbc-strict`), from the 32K image, each module of a program compiled by `*LATHE` (the objects and interfaces on drive 1: a catalogue holds 31 files), `*LLINK @LINKARG`, the image `*SAVE`d with its addresses and run; every file written is the host tools' of its name and the output the case's. A banked program runs with the module's RAM form, filled by `LOADMOD` from the image first, as on a developer's machine; one with regions in sideways RAM (`regions.lth`) is compiled and linked but not run, as a Model B has none. By default `farcall` (twelve compiles, six of the program's modules: 98.8 million cycles for the compiles and the link, 49 s at 2 MHz; the image's fixed part 1,806 bytes and five banks; drive 1 24 files, 16,117 bytes; drive 0 the sources, `LINKARG`, the image and its banks, 263,172 bytes with `LOADMOD` and the image of the module, which a ROM machine does not need on the disc). With `LATHE_BBC_RAM32=1` every program of `test_bbc_toolchain`'s corpus that the host's tools take at the 32K capacities: **57 programs**, 3,080 million cycles (25.7 minutes at 2 MHz) for their compiles and links, the longest farcall (above), then `reg_args` (6 compiles, 89.7 million, 45 s; its image 1,905 bytes, the largest) and `regions`.

**Where the two tools' limits meet.** Refused, 13 of 70: by the 32K compiler, `arith_ops`, `bigarray_pages`, `compare`, `for_until`, `record_copy` and `shared_types` (a function too large, 75: the function buffer of 1,536 bytes), `import_lists`, `inline_flow`, `inline_mix` and `inline_modules` (165, the inline functions' saved tokens, 384 bytes), `inits` (87, a table over 264 bytes), `strings_long` (7, a string over 264); by the 32K linker, `for_ranges` (link error 12, too many slots: 20 KB of code). The linker's own assessment ("The linker on a 32K BBC") links programs of 16 and 25 KB, but every one of those is made of the compiler's and the linker's test programs, whose modules (`err`, `kernel`, `lex` and the rest: "What the 32K form compiles") the 32K compiler refuses, almost all by the name heap; of the real programs it measures, the largest whose every module the 32K compiler takes are 2 KB (`reg_args`, `control`, `farcall`). So the gap is in the compiler: the linker would link a 25 KB program, and the compiler compiles modules of up to about 900 lines, so such a program needs some ten modules of that size, none of which the corpus has. A program of the user's own, written as modules of a few hundred lines with import lists, is what the pair takes.

### Started in another screen mode

What the tools did: nothing looks at HIMEM, so started in mode 4 (HIMEM `$5800` on a Model B) the compiler puts every table from `$5800` up in the screen, and the MOS writes its text over them (and mode 4 scrolls the screen's start through them); the B+128's builds, with their variables from `$4F00`, alike. On the emulator, `--bbc-mode 4 --bbc-strict` ends the run at the first such write (`test_bbc_ram32.ScreenMode`).

What happens now: `bbcrom.image(..., check_himem=True)`, the default (`bbcrom.py --no-check-himem` for none), gives each command's entry the top of its program's memory (the end of its highest `code`, `data` or `more` range below `$8000`, + 1: `$7C00`), and the module's command code (`module.asm`, step 0, under `.ifdef check_himem`) reads HIMEM with OSBYTE 132 before it copies or writes anything and, if HIMEM is below that, raises the MOS error `Mode 7 needed` from `$0100`, as a sideways ROM must. Refusing, not selecting mode 7: a `VDU 22` would clear the user's screen, and a B+ or a Master in a shadow mode has HIMEM `$8000` and passes. **Since 2026-11-18 every image checks** (the owner's request): `bbcrom.image` checks by default, in the sixteen- and eight-bank forms, for the B+128's builds and the 32K ones (`bbcrom.py --no-check-himem` leaves it out; `test_bbc_ram32.ScreenMode` builds one so, to show what the tool does without it). Tested (`test_bbc_rom.py`'s and `test_bbc_rom128.py`'s images, `RomImage.test_a_command_is_refused_where_himem_is_below_its_memory`): in mode 4 without the shadow screen each command is refused, with nothing written; in mode 7, and in mode 4 with the shadow screen (HIMEM `$8000`), it runs as before; the same through `LOADMOD` in the module's RAM form; every other BBC test runs in mode 7, the emulator's default. What it costs: none of the reserved bytes (the check is in the home bank's code, after the command is matched, with the error's text there too), 59 bytes of code and text and 2 bytes in each command's entry: 63 bytes in each image of the two tools (the 128 KB image 1,960 bytes free, 2,023 without; with ADFS 772, 835 without; the sixteen-bank images 72,546, 72,512 with `BBCFS 1` and 72,420 with ADFS). **The developer's forms** (`*RUN LATHEC`, `*RUN LLINK`) are not the module's: their start-up code does not look at HIMEM, so in mode 4 they write their tables through the screen as the image's tools did; a check there would be in the start-up code of every BBC program (`rt_bbc.start` and `bbc.lth`), which does not know where the program's memory ends without the linker telling it, so it is not equally small: left as it is.

### Suggestions, ranked

1. **RAM on the module's board** (best, hardware): a 32 KB static RAM behind the module's latch as two more banks would hold every region at the full capacities, as the B+128's sideways RAM does: the 32K form would then compile what the B+128 build does, itself included. A ROM socket has no write line, so the board needs R/W from a flying lead or a write-by-read scheme; the software is a `region` entry per table (the developer's form already writes the module's RAM). Cost: the board; about 8 KB of main RAM back too, since `fold` and some stubs could go.
2. **Keywords and predeclared names out of the name heap** (medium, software): a trivial module already takes about 1,300 of the 3,072 bytes, about 700 of them the keywords and predeclared names, which are the same in every compile. A table of them in a bank's constants would give every module about 700 bytes more of names (23 %): `lex.lth` (3,734) and `err.lth` (3,636) would still be over, `parts.lth` (3,601) and the like close. Cost: the lexer's and `kernel.sym_find`'s look-up of a keyword, host and twin.
3. **Symbol rows of fewer bytes, or 256 at most** (medium): 4,488 bytes for 264 rows that the modules which fit use 180 of. A table of at most 256 rows needs the twins' symbol numbers to stay words while the arrays are indexed by bytes; at 200 rows, 1,088 bytes for the name heap (+35 %). Cost: care in every `kernel` accessor, host and twin.
4. **Fewer stubs** (cheap to try, small): 329 stubs are 1,974 bytes; a layout chosen to keep the most-called functions' callers in their bank (`farcall_matrix.py` with the 32K form's groups, which need a counting copy with the regions fixed) might save 200 to 400.
5. **REG's slots** (small): 192 slots of 8 bytes and GEN's saved slots, 1,728 bytes; the modules that fit use at most 136; 160 would give 288 bytes. Cost: the split of locals and temporaries at 128 is in the code.
6. **Tables on the disc** (large redesign): the name heap paged from a file would lift the limit that matters most, at a cost of time the DFS makes high. Not recommended before 1 to 3.

## The linker on a 32K BBC (2026-11-18)

The owner asked for a form of the tools for a 32K BBC Model B: RAM `$0000-$7FFF` only, no sideways RAM, no shadow screen, the module (the 128 KB EPROM, scheme `direct8`) in one socket. It cannot rebuild the tools, but it should compile and link programs: ideally one that takes most of the memory free in mode 7 (`$1900-$7BFF`, about 25 KB), at least one for a mode 4 screen (`$1900-$57FF`, about 16 KB). This is the linker's part; the compiler's is beside it (`lathec-bbc.env`), and both read the same switch, `define RAM32`.

### The build

`lathe/src/linker-bbc.env` with `define RAM32 1` (0 in the file; every build of `RAM32 0` is byte for byte what it was: the images, bank files and maps of the developer's, sixteen-bank and eight-bank forms with `BBCFS` 0, 1 and 2 and `ADFS`, of `linker-full.env`, `linker-bank.env` and `lktest1` to `lktest4`, and the compiler's, compared before and after):

- *No sideways RAM.* `unless RAM32` before the three `bank` entries of slots 0, 1 and 12 and the five `region` entries, so the regions `LKLOCAL`, `LKCALLS`, `LKSLOTS`, `LKNODES` and `LKWORK` have no entry and are fixed memory, as on Wendy 2's small build: nothing else was needed for that. The functions with `with` blocks stay fixed (the linker keeps them so whatever region they name), and a block of a fixed region maps slot 0 for nothing, which is harmless since all that runs inside it is fixed code (`rt_bbc.lth`); on a Model B slot 0 is a ROM socket, maybe empty, and the same holds.
- *Main RAM.* (Since 2026-11-18 the split is `$3A12`, with the linker told of its fixed regions: "The 32K Model B", "The linker told of its fixed regions"; the figures here are of before.) `when RAM32 code $1900 $3C9A` and `data $3C9B $7BFF`, with `more data $0401 $06FF` as before: the split is where the code ends with `BBCFS 1`, the build for a real DFS disc.
- *Code out of main RAM.* In the eight-bank form `lk_out` and `lk_op`, which `ROM128` keeps fixed to save 1,288 far calls, go in bank 2 (`when RAM32 when ROM128 place`): 803 bytes of main RAM for 881 bytes as judged of that bank, the one with room for them with every `BBCFS` (bank 1 holds `bbcfs` with `BBCFS` 1 and 2).
- *Its capacities*, `LKSMALL 2` (`when RAM32 define LKSMALL 2`), a third set of the twins' values under `#if LKSMALL == 2` before the small build's, which `lk_small.load(2)` gives the host modules (`lathe/host/README.md`, "The linker in Lathe").

What does not build: `RAM32` with `ADFS 1` (the code range is given twice, link error 43: ADFS's PAGE leaves 1.5 KB less), with `BBCFS 2` at `$1900` (45 bytes over the code range), and the developer's form (28 bytes over; it needs the module's RAM board, which a 32K machine does not have).

### Main RAM

The eight-bank ROM form, `BBCFS 1` (with `BBCFS 0` the code is 23 bytes shorter and those bytes are left below the split):

| What | Bytes |
|---|---|
| resident part: code, constants and stubs, `$1900-$3C9A` (9,829 in the `RAM32 0` form) | 9,115 |
| the work area, `lk_tab.work` and `nodes`: 10 words a node, 300 nodes | 6,000 |
| the slots' columns, 800 slots (and 16 large slots, 64) | 1,664 |
| the functions' columns, 296 functions (`fn_edge` among them) | 2,072 |
| the calls, 576 | 1,152 |
| the symbols in object files, `lk_name.local`, 592 | 1,184 |
| the variables and constants, 257 | 1,285 |
| the classes, their parameters and members (8, 32, 32) | 432 |
| buffers: `lk_file.arg_text` 512, `lk_envf.text` 384, `bbc.arg_text` 256, `lk_file.path` 256, `bbc.name_buf` 128 | 1,536 |
| the rest: the linker's frames, the small tables and variables of every module | 1,247 |
| free: `$0558-$06FF`, room only for variables of less than 424 bytes | 424 |

The data range is full to `$7BFF`: the linker places variables in their order, each in `data` while it fits there and else in `more`, and `lk_name.local`, the last large one, ends 46 bytes below HIMEM. The banks as judged: 15,387 (with `bbcfs` 15,877), 15,983 and 16,031 of 16,272; with the compiler in banks 0 to 4 the eight banks have 5,648 bytes free (5,815 with `RAM32 0`).

### The capacities, and why these

The tables are what real programs need, not the full ones cut evenly. Measured with the host linker over the real programs below, a program of 16 to 25 KB uses about 1.0 node, 2.5 slots, 1.9 calls and 2.0 symbols in object files a function, and 0.5 variables or constants; so functions, nodes, slots, calls and symbols were given the same share of what is left, and the rest the least it can be:

| Capacity | `LKSMALL 2` | small build | full | Why |
|---|---|---|---|---|
| functions | 296 | 320 | 896 | |
| nodes (the work area, 20 bytes a node) | 300 | 360 | 900 | a node a function; the reading's names need about as much |
| slots | 800 | 1,280 | 4,000 | |
| calls | 576 | 1,200 | 3,600 | |
| symbols in object files | 592 | 1,400 | 4,000 | |
| variables and constants | 257 | 320 | 800 | the least a word column can have; programs use 100 to 170 |
| fix-ups held at once (a run; a function may have any number since 2026-11-18) | 278 | 256 | 512 | as many as the work area holds below its node columns (no bytes of their own) |
| promotion's list | 18 | 32 | 128 | as long as its column holds (no bytes of its own) |
| large slots; classes, parameters, members | 16; 8, 32, 32 | 64; 32, 128, 128 | as small | the corpus uses at most 1; 3, 8 and 7 |

A word column of 256 rows or fewer would need a byte index in the twins, so the word columns have 257 rows or more. Three things the 32K build does differently, in host and twin, under constants that the other builds give their old values (so their code is unchanged), each to let the work area be 300 nodes and not 333 or more:

- *The S lines' names.* The map's reading of each file's slots held its names above the slot name, `6 × (MAX_NODES − MAX_FIXES) − 128` words, where the image's own reading held them until 2026-11-16; once the image is closed the fix-ups' words below `W_ADDR` are free, and the 32K build holds them there as the F, D and V lines do (`lk_map.SLOTS_LOW`). Without it kerneltest, whose `kernel.lo` needs 692 words, would allow 163 fix-ups to a function; it needs 204.
- *The first reading's floor.* `mark_all` keeps a bit for each of 32,768 hashes of the names some file defines (`lk_name.DEFS`), 2,048 words above 1,280 others: a work area of 333 nodes at least. The 32K build keeps 16,384 (`DEFS_HASH $3FFF`); a false match only keeps a name that need not have been (no output changes: the corpus links as at full capacities, every file the same).
- *Room for the names.* The words below the reading's heap: 16 weights waiting (`lk_scan.MAX_PENDING`; the programs here wait for at most 7), so `MARKS` at 64, and 256 chains of kept names: 896 bytes more for the names than the layout of the full build would leave.

### What it links

`lathe/tests/lk_ram32.py` (`real`, `series`, `shape`, and the links on the BBC that `test_lk_ram32.py` makes). The real programs are the test programs of `lathe/src` (each a set of the compiler's or the linker's own modules with a driver) and the end-to-end cases, compiled for the BBC all in one; a larger program is made of real ones (`glue`: each piece's modules renamed, the run-time modules once, a main that calls each piece's main, so that each piece keeps what it kept), grown a piece at a time until the 32K build refuses it. Whether it links is the host linker at the 32K build's capacities, which refuses exactly where the Lathe-written build does; the links on the BBC check that.

**Real programs:** 77 of the 81 link: every end-to-end case but `for_ranges` (one file of 1,124 slots), and copytest, errtest, srctest, typetest, foldtest, lextest (15.4 KB), fbuftest (16.4 KB), lktest1, kerneltest (22.7 KB) and outtest (28.5 KB, too large for the machine). regtest, condtest and asmtest (40 to 43 KB, link error 10) do not fit a 32K BBC anyway. (Until the fix-ups were held in runs, below, three test mains of 344 fix-ups each and outtest's of 351 were refused too.)

**Grown** (program: its code and constants and its variables, which in mode 7 must be at most 26,111 bytes, and in mode 4 16,895):

| Program | Objects (bytes) | Program | Tightest tables | Result |
|---|---|---|---|---|
| fbuftest (mode 4) | 14 (76,809) | 16,447 | names read 4,468 of 6,000 (26 % left), functions 218 (26 %), calls 408 (29 %) | links |
| lextest + errtest | 15 (77,671) | 22,001 | | links |
| lextest + errtest + copytest + compare (mode 7) | 18 (89,280) | 25,034 | symbols 472 (20 %), functions 230 (22 %), calls 439 (24 %) | links |
| kerneltest + copytest + compare | 14 (74,586) | 25,730 | names read 4,446 (26 %), calls 378 (34 %) | links |
| lextest + ... + reg_args + record_copy (a main of 344 fix-ups) | 23 (109,130) | 29,412 | | links (too large for the machine) |
| lextest + ... + record_copy + control | 25 (115,747) | 31,132 | functions 310 | link error 11 (too large for the machine) |
| fbuftest + errtest + copytest + compare | 19 (98,577) | 26,125 | | links (14 bytes too large for mode 7) |
| lktest1 + srctest + copytest | 20 (96,534) | 22,457 | symbols 590 (0 %), names read (2 %), calls (2 %) | links |
| lktest1 + srctest + copytest + compare | 22 (106,969) | 25,082 | symbols 624 | link error 33 |
| srctest + typetest + copytest | 18 (107,002) | 21,764 | functions 296 (0 %), slots 790 (1 %) | links (297 functions until the texts left `err`, 2026-11-18) |
| srctest + typetest + copytest + compare | 20 (117,437) | 24,347 | functions 316 | link error 11 |
| kerneltest + ... + signed | 23 (106,212) | 32,540 | calls 578 | link error 13 (too large for the machine) |

So **a 16 KB program for mode 4 links with a quarter of every table to spare, and a 25 KB program for mode 7 links with a fifth to spare** when its code is of the tools' usual shape (100 bytes or more a function). Programs of very small functions run out of functions first (typetest's average 59 bytes a function: about 18 KB of code at 296 functions), and the linker's own shape (more calls and symbols a function) of symbols, calls and names at about 22.5 KB. No function is refused for its number of fix-ups (since 2026-11-18, below); until then one of more than 278 (about 900 bytes of code) was, whatever the program's size.

**On the BBC** (the eight-bank image, the compiler in banks 0 to 4 and the 32K linker in 5 to 7, `*LLINK @LINKARG`, `--bbc-strict` on filled memory; every file the host linker's; with `BBCFS 1` under `--bbc-fs dfs` too, 2 files open at most, 1 for writing):

| Program | Objects | Program | Cycles | Minutes at 2 MHz | Files opened | Read | Written |
|---|---|---|---|---|---|---|---|
| lextest | 13 | 15,403 | 158,079,033 | 1.32 | 105 | 601,837 | 22,639 |
| fbuftest, for mode 4 | 14 | 16,447 | 184,725,056 | 1.54 | 112 | 682,001 | 25,271 |
| kerneltest | 11 | 22,699 | 177,218,554 | 1.48 | 85 | 536,781 | 31,883 |
| lextest + errtest + copytest + compare | 18 | 25,034 | 223,921,313 | 1.87 | 147 | 792,559 | 35,546 |
| kerneltest + copytest + compare | 14 | 25,730 | 286,675,440 | 2.39 | 109 | 628,265 | 36,732 |
| record_copy (a main of 344 fix-ups: two runs) | 6 | 2,209 | 34,648,613 | 0.29 | 46 | 121,610 | 3,421 |
| arith_ops (344 fix-ups) | 8 | 1,997 | 50,963,170 | 0.42 | 67 | 162,024 | 4,467 |
| bigarray_pages (344 fix-ups) | 7 | 4,782 | 33,746,145 | 0.28 | 55 | 124,451 | 2,168 |
| a function of 1,006 fix-ups in two contexts (test_lk_fixup_runs.py) | 1 | 5,171 | 218,033,414 | 1.82 | 81 | 756,856 | 5,532 |

(The first five before the runs, earlier on 2026-11-18: 157,316,136, 183,807,919, 175,997,536, 222,815,376 and 289,370,215 cycles.)

The emulator's MOS charges nearly nothing for the disc; at 1,000 cycles a byte a real DFS would add 4.5 to 6.6 minutes to these (the 600 to 800 KB the passes read), more than the link itself.

**The disc.** A 25 KB program is 14 to 22 object files of 75 to 110 KB (4.5 bytes of object file a byte of code); the link reads them, the environment and LINKARG, and writes the image and a map of about 10 KB, 22 to 26 files and 110 to 150 KB in all. That fits the 31 files of a side, but not the 100 KB of a 40-track single-density Acorn DFS side: an 80-track side (200 KB), a double-density DFS, or the objects on one drive and the outputs on another (`:1.`, "Drives"). The sources and interfaces are another side's. The 16 KB program's 14 objects are 77 KB.

### What would raise it, ranked

Each is measured or worked out from the account above; a table byte is worth about one fortieth of a function (40.6 bytes of tables a function at this balance), so 1 KB of main RAM is about 25 functions, 2.5 KB of program.

1. **RAM on the module's own board.** A 32 KB static RAM beside the EPROM, as banks 8 to 9 of the latch (`direct8` decoding A3, or `direct16`'s scheme), takes the large tables as the B+128's sideways slots do: all of `LKSMALL 2`'s 13 KB and room for twice it, and 12 KB of main RAM back. Then any program the machine holds links, with every table at twice what it now has. Cost: an SRAM and its write enable on the board; `rt_bbc` already maps a bank of the module in a block; the environment gives the regions bank values `$88` and `$89`; LOADMOD and `bbcrom` unchanged. The cheapest large step, and hardware.
2. ~~**Fix-ups held in runs.**~~ Built (2026-11-18, the owner's choice; "Fix-ups held in runs" below): no function is refused for its number of fix-ups. It took 384 bytes of bank 1 as judged where this estimated 300, and 16 bytes of main RAM.
3. **`with` blocks of a fixed region cost nothing.** In the 32K build every block maps slot 0 and back for nothing: 64 cycles and 12 bytes of fixed code a block, which on the B+128 were 4.5 % of outtest's link and 16 % of the compiler's ("The linker links the compiler"). And 721 bytes of functions are fixed only because they have a block (`lk_name.local_at`, `set_local`, `global_sym` 191, `lk_graph`'s four readers 180, `lk_alloc`'s four 184, `lk_fix.shrinks` and `removed_before` 166), of which the banks have room as judged for those of `lk_name` and `lk_fix`, 357 bytes. Needed: the linker not keeping a function fixed for a block of a region that is fixed, and giving such a block's kind 6 fix-up the value of the function's own bank (re-selecting it is harmless) where it now gives 0 (slot 0); an environment entry to ask for it, so that no other build changes; host and twin, about 40 lines. Better still, the compiler leaving out the block's calls when the region is fixed, which it cannot know today.
4. **More code out of the resident part.** lk_tab's functions that only the reading calls (`build_chains` 792, `chains_to_runs` 380, `add_waiting` 315, `add_edge` 258, `add_own` 251 and the `new_` functions, about 2.5 KB) would leave main RAM in `lk_scan`'s bank, which has 289 bytes as judged left; so it needs a fourth bank for the linker, which the 128 KB EPROM does not have with the compiler's five (5,648 bytes free in all, in pieces). 2.5 KB is about 60 functions more.
5. **Narrower or fewer rows.** The variables and constants have 257 rows where 25 KB programs use 170 at most: byte-indexed columns would save up to 485 bytes but need a second form of every access in the twins. The work area's names (37 % of the tables) are 4 bytes a symbol and the kept names; keeping a symbol's second word (its weight and flags) in `local` would save about 900 bytes for 450 symbols, a redesign of the reading.
6. **Not worth it:** making zero-page promotion optional saves no memory (its columns are the graph's, in the work area) and only time; keeping more on the disc saves little (what can be read again already is: names, what fix-ups name, sizes of copies).

### Fix-ups held in runs (2026-11-18)

The image pass held all of one function's fix-ups in the work area while its code was written (12 bytes each, `lk_tab.MAX_FIXES` of them: 278 in the 32K build, 256 in the small one, 512 at full capacities), and a function with more was link error 28. The owner chose to have no such limit. Now, in host and twin (`lk_fix`, `lk_emit`), a function's fix-ups are held in **runs** of `MAX_FIXES`:

- `hold` holds the first run and notes where the FIX record is (its object file and record number) and how many entries it has. A function of no more entries than a run holds is written as before, every byte the same.
- When the code reaches the end of a run (`next_fix`), what the run's instructions lose in each context is added to `run_lost`, the record is read again (the stream's only way back is to read the file from its start, `lk_rec.goto`) to the next run's first entry, the run is held, and the stream goes back to the CODE record and the byte it had reached (`away`, `back`). A second copy of the function, for another context, starts again from the first run (`rewind`).
- What the code loses before an offset (`removed`, for a branch and for a label of the function, which may be anywhere in it) is `run_lost` and what the run held loses before it, when the run covers the offset (every entry before the run is before it, every one after the run after it); else it is counted from the record itself, read again up to the offset (`from_record`, by `count_before`, which pass 1's `count_shrinks` now calls with no offset). The bytes a whole copy loses (`lost`) are counted so too.
- The order of two fix-ups on either side of the end of a run is not compared by `next_fix`; an instruction finds a fix-up behind it bad, as before.

**What bound remains.** None for a function: a FIX record is at most 65,535 bytes, 8,191 entries, which is the object format's own limit (and needs a CODE record of 16 KB or more), not the linker's. Constant data is still held whole, and a table of more entries than a run holds is link error 28, now "too many fix-ups in one table"; the compiler writes at most 256 addresses in a table (`out.MAX_TABLE_FIXES`), and every build of the linker holds at least that many, so no compiled table is refused (the entries a kept `DFIX` record names, `lk_graph`, have the same bound).

**What it costs**, measured against the commit before:

| Build | Bank 1 as judged | Main RAM | Linking the compiler |
|---|---|---|---|
| eight banks, `RAM32 0`, `BBCFS 0` | 15,309 to 15,693 (579 left) | resident 9,829 to 9,827; 16 bytes of tables (`run_lost`) | from the 128 KB image 3,463,370,865 to 3,473,194,730 cycles (+0.28 %) |
| eight banks, `BBCFS 1` | 16,183 (89 left) | 9,850 | |
| eight banks, ADFS (`BBCFS 2`, `ADFS 1`) | 16,112 (160 left), with `link`, called once, moved to bank 2 (`when ADFS when ROM128`; else 46 bytes over); since the texts of the errors left `lk_err` (merged the same day) it fitted in bank 1 again, at 16,234 (38 left), until link error 62 (below) took 139 more and `link` went back to bank 2: 16,167 | 9,926 (9,897: the stubs of the phases `link` calls); merged, 9,875, then 9,906 | |
| 32K, `BBCFS 0` and `1` | 15,725 and 16,215 (57 left) | 9,090 and 9,113, as before | |
| Wendy 2 at full size (`linker-full.env`) | | | 2,513,831,206 to 2,524,931,333 cycles (+0.44 %) |

The eight-bank image has 5,348 bytes free (5,815). `lk_fix` is 2,485 bytes as judged (1,905) and `lk_emit` 2,120 (2,316): an accessor of the column at the cursor (`lk_fix.held`) took 196 bytes out of `lk_emit`, without which bank 1 did not fit with `bbcfs`. The links of the 32K table above take about 0.5 % more cycles; a function that needs runs costs a reading of its file up to the record for each run and for each offset outside the run (the function of 1,006 fix-ups: 81 files opened, 218 million cycles for 5 KB of code). The developer's and sixteen-bank forms have `lk_fix` in a bank with room.

**Tests.** `lathe/tests/test_lk_fixup_runs.py`: functions of more fix-ups than a run holds (266 to 2,300), with instructions that shrink and some that do not, one-byte fix-ups, branches back and forward across the ends of runs, jumps to labels far behind and far ahead, calls, slots of their own in zero page, and a second copy for an interrupt context: at full capacities the image is what the assembler path reckons on its own; at the small and the 32K build's capacities and with runs of 16, every file is what a link that holds all of them at once writes; a table of more than a run is still refused. `test_lk_errors.py`: a function of 1,025 fix-ups links. On the BBC (`test_lk_ram32.py`): the three test mains of 344 and the function of 1,006 link at the 32K capacities, every file the host's.

### Link error 62 (2026-11-18)

Since the compiler may be told that a region is in fixed memory (`-fREGION`, from `define FIXED_REGIONS 1` and `region NAME fixed`: "The 32K Model B"), a `with` block of that region compiles to its body alone. An object so compiled and then linked with an environment that puts the region in a bank linked silently, and its code read and wrote whatever the window held. Now it is **link error 62, "code uses a region in a bank where it maps none"**, with the symbol and the function named, in host and twin.

**The rule.** The compiler allows a variable or constant of a region only inside a `with` block of it, and a block starts with `LDA #bank(REGION)`, a fix-up of kind 6, before the code it holds. So, in the image pass, a fix-up of a function's code (any kind but 6: an address, its low or high byte, an address formed only to reach an element) that names a variable or constant of a region in bank B is good only if a kind 6 fix-up of the same function, earlier in its code, named a symbol of bank B (`lk_fix.check_mapped`, called by `lk_emit.value`; `bank_value`, which resolves kind 6, notes the bank in `mapped`, a bit a bank, cleared at each function by `begin`). This is stricter than the rule first proposed (the function has some kind 6 fix-up, `F_WITH`): it also refuses a function that maps one region's bank and uses another region of another bank, which `-f` for one of two regions would give. Two regions in one bank (the B+128 linker's `LKLOCAL` and `LKSLOTS`) are one bank here, as they are to the hardware.

**What it covers**: variables and constants of a region named from code, the initial values a module's `$init` writes into a region, and an address of a region's variable formed in code (`@v`, `LDA #<v`). **What it does not look at, on purpose**: constant data that holds such an address (a table of pointers into a region, used inside a block elsewhere: legitimate), and code that reaches a region through a pointer it is given (`kept.lth`'s `add8`: the block is its caller's, and the caller names the region). **What can slip through**: (1) a function compiled with `-fR` that names R only through constant data holding R's addresses, and dereferences them outside a block; (2) a use after the block that mapped its bank has ended, in the same function (the linker sees where a block starts, not where it ends: the calls of `unmap` are not marked), which the compiler does not write. And one it refuses that may be right: `asm` that maps a bank itself, with no kind 6 fix-up (none in the corpus). None of the 161 cases of `test_cases.py` or the linker's own links is refused.

**Tests** (written first): `lathe/tests/test_lk_unmapped.py`: objects by hand (a use after a block of its bank links, of the other region of the same bank too; a use with no block, with a block of another bank, a constant, an address's low byte: refused, naming symbol and function; the regions in fixed memory, with an entry or none: no block needed; a constant table holding a region's address: links); `fixedblk.lth` compiled with `fixedblk_fixed.env` (`-ffwork`) and linked with `fixedblk_banks.env`: refused by the host linker and by the Lathe-written one (Wendy 2, `lk_banked.py`), the same text. The two harmless combinations are configurations of `tests/cases/e2e-config/fixedblk.lth`: `fixedblk_fixed.env` (told, fixed) and the new `fixedblk_untold.env` (not told, fixed: the blocks map nothing), each giving the program's output. `test_lk_windows.py`'s module `t`, which used a constant of bank 5 with only bank 4 mapped, maps both now, as the compiler would have it.

**What it costs**, bank 1 as judged (of 16,272), against the merged tree before it:

| Build | Before | After | Left |
|---|---|---|---|
| eight banks, `BBCFS 0` | 15,609 | 15,748 | 524 |
| eight banks, `BBCFS 1` | 16,099 | 16,238 | 34 |
| eight banks, ADFS (`BBCFS 2`, `ADFS 1`) | 16,234 | 16,373, 101 over; so `link`, called once, is in bank 2 again there (`when ADFS when ROM128`): **16,167** (bank 2 15,079 to 15,290; resident 9,875 to 9,906, the stubs of the phases it calls) | 105 |
| 32K, eight banks, `BBCFS 0` and `1` | 15,641 and 16,131 | 15,780 and 16,270 | 492 and 2 |

139 bytes: `check_mapped` and `bank_of` (which `bank_value` shares) in `lk_fix`, and the call in `lk_emit`. The 128 KB image (`test_bbc_rom128.py`, `BBCFS 0`) has 1,336 bytes free (1,495 before; the module's code and texts 4,385 bytes in bank 3), and the linker links the compiler from it in 3,559,557,177 cycles (3,548,476,259 before, +0.31 %). The 32K image (`test_bbc_ram32.build_image`, sixteen banks, `BBCFS 1`) has 80,111 bytes free, the linker's five banks 5,917 to 10,542 bytes as placed, and leaves the linker 1,655 bytes of main RAM free (resident 7,839, variables 16,617): room the 32K capacities could grow into, which this does not do. The sixteen-bank and developer's forms have `lk_fix` in a bank with room, and the 32K image is the sixteen-bank form. Main RAM: 2 bytes of variables (`mapped`). Time: a fix-up of a variable or constant now looks for its region (`lk_scan.region_of`, a walk of the regions' definitions, none in most programs).

### Capacities retuned (2026-11-18)

Programs generated with the tools' measured shape ("A program of real size on the 32K Model B") showed what the real programs above did not: at about 130 bytes and 2.8 calls a function the linker's **calls** fill first (link error 13 from about 21 KB), then the slots and the functions. The eight-bank 32K image (the 128 KB EPROM, the texts of the errors in parts, `BBCFS 1`) left the linker 1,292 bytes of main RAM (1,062 before the compiler's source refactorings, which made its code smaller too), but of them only what follows `lk_name.local`, the last large table, in the data range (680 bytes) can take more rows: the variables after it move to `$0401-$06FF`, which was empty. So the capacities grew by 576 bytes, the calls most:

| Capacity (`LKSMALL 2`) | Before | After | Bytes |
|---|---|---|---|
| calls | 576 | **768** | +384 |
| slots | 800 | **848** | +96 |
| symbols in object files | 592 | **640** | +96 |
| functions, nodes, variables and constants | 296, 300, 257 | the same | |

`lk_name.local` now ends at `$7B99` (`$769A` and 1,280 bytes), 102 bytes below HIMEM, and the linker has 721 bytes of main RAM free in all (its resident code 8,193 bytes, its variables 17,197), most of them at `$0401-$06FF`. What else was weighed, against both kinds of evidence (the host linker at the capacities, `lathe/tests/lk_ram32.py` and gen_program):

- *More functions and nodes* (296 and 300 to 312 each, 432 bytes, as first proposed): the generated 25 KB program needs 290 of each, so they buy nothing at mode 7's size, only for programs of small functions (srctest and typetest's, 59 bytes a function, refused at 24.3 KB by 316 functions) or larger than the machine.
- *A larger work area for the linker's own shape*: lktest1 + srctest + copytest + compare (25.1 KB) needs 624 symbols and 6,080 bytes of names read, more than 304 nodes give; it would cost about 200 bytes more than there are.
- *Fewer variables and constants*: they use 45 to 170 of 257 rows, but a word column of 256 rows or fewer needs a byte index in the twins, so the 257 rows (1,285 bytes) cannot pay for anything.

| Program | Code (since the compiler's source refactorings: 2 to 3 % smaller, the tables' use the same) | Before | After |
|---|---|---|---|
| generated, 8 modules of 20 (usual shape: 129 bytes, 2.8 calls a function) | 19,385 | links (calls 560 of 576) | links |
| generated, 8 of 23 | 21,266 | calls 614: error 13 | links |
| **generated, 8 of 26** (mode 7) | **24,296** | calls 726: error 13 | **links** (calls 726 of 768, slots 807 of 848, functions 290 of 296) |
| generated, 8 of 27 | 26,404 (too large for mode 7) | error 13 | slots 864: error 12 |
| generated, 8 of 17, larger (187 bytes a function) | 24,397 | links | links |
| generated, tools' shape: 8 of 20 (144 bytes, 3.4 calls) | 21,666 | calls 675: error 13 | links |
| generated, tools' shape: 8 of 23 (147, 3.4) | 24,855 | error 13 | links (calls 765 of 768) |
| generated, tools' shape: 8 of 21 (157, 3.7) | 24,447 | calls 760: error 13 | links |
| generated, tools' shape: 7 of 25 (157, 3.7) | 25,705 (too large for mode 7) | error 13 | calls 797: error 13 |
| real: lextest + errtest + copytest + compare | 25,034 | links | links |
| real: kerneltest + ... + signed | 32,540 (too large) | calls 578: error 13 | links |
| real: lktest1 + srctest + copytest + compare | 25,082 | symbols 624: error 33 | names: error 10 |
| real: srctest + typetest + copytest + compare | 24,347 | functions 316: error 11 | the same |
| real programs of the corpus and `lathe/src` | | 77 of 81 | 77 of 81 |

So a 25 KB program of the usual shape, and of the tools' own shape up to 3.7 calls a function, links for mode 7; the next limits are the slots and the functions, at about 26 KB, past what the machine holds. On the Model B (`LATHE_BBC_RAM32_PROGRAMS=1 ... test_gen_program`) the 25 KB program of the usual shape is now a target of its own: 8 modules of 26 functions and a main, 2,879 lines, 250 functions of its own (125 bytes and 2.8 calls a function), 24,296 bytes of code and constants and 343 of variables, 705 bytes left below HIMEM (since the compiler's source refactorings; 358 before them); from the eight-bank 32K image its 13 compiles take 261.6 million cycles (2.2 minutes at 2 MHz) and the link 399.5 million (3.3 minutes), the linker's tightest tables its functions and nodes (290 of 296 and 300), then its slots (807 of 848), every file the host tools' and the output the generator's; the disc holds 17 files, 172 KB on drive 0 and 26, 138 KB on drive 1. The other targets' links: 8 KB 135.9 million cycles, 16 KB 254.8, 20 KB 315.9, 25 KB of larger functions 384.3.

### The order of the object files (2026-11-18)

A module's WGT record weights the parameters of the functions it calls in other modules. For a function the linker has not read yet the weight waits in a table (`lk_scan.MAX_PENDING`: 16 in the 32K build, 64 in the others), and a weight more was link error 41, so the same objects linked or not by the order they were named in: `build.py` lists `rt_math` last, which every module that multiplies or divides calls, and a 16 KB generated program failed so on the 32K build, an 8-module one at full capacities too.

**Now** (host and twin, `lk_scan`): a weight that does not fit the table is not held; the file that gave it is marked (`OBJ_WEIGHTS` in `obj_cpu`), and once every file is read, if any did not fit, none is taken from the table: the WGT records of the marked files are read again (`reread_weights`), and each weight for a slot of a function read after its record, one that waited, is added then (`rec_wgt` again, with `late_before` the first function after the record). They are read before `lk_name.resolve`, while `local` still holds the symbols: once it holds what they stand for, `lk_name.now` read another symbol's entry, and on the BBC a 16 KB program in `build.py`'s order put a different variable in zero page from the host's full linker (the tests' zero page had been large enough for every slot, so no weight showed; it is one byte now). A weight is a saturating sum, the same in any order, so the output is what a linker that held them all writes; an order that linked before reads nothing again and writes the same bytes. **No limit remains** for the order; link error 41 is retired. Its text stays in the tables for its number.

**What it costs.** Bank 2 of the eight-bank forms (lk_scan, lk_name, lk_map) as judged, 103 bytes: 14,872 to 14,975 (`RAM32 0`, `BBCFS` 0 and 1), 15,077 to 15,180 (ADFS), 15,922 to 16,025 in the 32K eight-bank form (**247 bytes left** of 16,272; 7 before the compiler's source refactorings gave some back; `add_weight`, shared by the three places that add a slot's weight, paid for most of it). Bank 1 is unchanged (15,529, 16,019 with `BBCFS 1`, 15,945 ADFS; 15,561 and 16,051 in the 32K form). Main RAM: 3 bytes. Time: nothing for a link whose weights fit the table; for one whose do not, a reading of each file that gave a weight that waited: the generated 16 KB program (6 modules of 21 functions, 15,635 bytes) in `build.py`'s order on the BBC 265,729,605 cycles against 255,209,076 with `rt_math` first (+4.1 %, 104 files and 933,768 bytes read against 98 and 855,072), both every file the host's. So the run-time modules first is still the faster order, and `LINKARG` on the BBC is best written so; it is no longer needed.

**Tests** (written first): `lathe/tests/test_lk_weights.py` (more weights waiting than the table holds link as with a table that holds them all, at full, small and 32K capacities, in one byte of zero page that each function's slots compete for, and with functions whose rows are not their symbols'; weights for functions nothing defines are dropped; a weight for a slot its function lacks is still link error 6 naming the file); `test_lk_errors.py` (257 weights for undefined functions link); `test_lk_ram32.py` (`OnTheBBC`: a generated program of 6 modules in `build.py`'s order on the 32K build, every file the host's).

### Tests

`lathe/tests/test_lk_ram32.py`: the 32K build in the eight-bank ROM form with `BBCFS` 0 and 1 links, puts every table in main RAM and nothing in a sideways slot, and fits the 128 KB image beside the compiler; the host at its capacities links the corpus as at full capacities, every file the same, and the 16 KB and 25 KB programs; what stops larger ones; on the emulated BBC lextest, and with `LATHE_LK_RAM32_ALL=1` the programs of the table above, linked as the host links them, under the DFS's names too (`LATHE_LK_RAM32_REPORT=1` prints the cycles). `test_src_lk.py` checks the 32K build's capacities and its work area's rules with the other builds'. The end-to-end run from the image on the Model B emulation waits for the compiler's half and the emulator's Model B.

## A program of real size on the 32K Model B (2026-11-18)

The owner asked how large a program of several modules the 32K pair can compile and link, ideally one that takes most of mode 7's memory (`$1900-$7BFF`, 25 KB), at least one for a mode 4 screen (`$1900-$57FF`, 16 KB). The linker's 32K form links programs of 16 and 25 KB ("The linker on a 32K BBC"), but those are made of the tools' own modules, which the 32K compiler refuses; the largest program of the corpus compiled and linked end to end on the Model B was 2 KB. So the programs here are made to measure.

### The programs

`lathe/tests/gen_program.py` writes a program of N modules of F functions each and a main, with what it prints. Its shape is taken from real Lathe code, measured from the objects (`lk_ram32.shape`) and sources of the tools: 109 to 127 bytes of code a function (median 67), 3.2 to 3.6 slots, 1.0 to 1.3 parameters and 1.4 locals, 3.7 to 4.2 calls (the run-time library's among them), 23 to 44 functions and about 7 imports a module, about 4 names an import list; the end-to-end cases have 119 bytes and 2.2 calls a function. A generated function has a word parameter (and a byte one in 4 of 10), one or two locals, arithmetic on words (`*`, `/` and `mod` call `rt_math`, as in real code), a loop over the module's constant table, a test, an update of the module's variables and about 2.7 calls (the run-time's among them) of functions of a lower level declared before it, in its module or in one it imports with a list of the names it uses; a third of the functions are one-liners, as accessors are. Names are `VERB_NOUN` for functions and `NOUN`, `new_NOUN` and the like for parameters and locals, so that a module has about as many names as real ones (`lathec.lth`, 276 lines, 1,691 bytes of names; a generated module of 300 lines 1,200 to 1,600). Each module's `run` calls its functions in turn and returns the sum of their results, and the main prints each module's sum and the sum of all in hexadecimal; the generator evaluates every statement as the 6502 does, which gives the expected output. As measured (`test_gen_program.py`, by default): 129 to 134 bytes, 2.6 to 2.8 calls and 3.3 slots a function, 33 fix-ups.

### On the Model B

`LATHE_BBC_RAM32_PROGRAMS=1 python3 -m unittest test_gen_program` (`OnTheModelB`): on `boards.BOARDS['bbc32']` (the Model B, the DFS's names, `--fill-ram`, `--bbc-strict`), from the 32K image (the 128 KB EPROM), every module compiled by `*LATHE` (the sources on drive 0, the objects and interfaces on drive 1), linked by `*LLINK @LINKARG`, the image `*SAVE`d and run. Every file written is the host tools' (byte for byte, of the name it maps) and the output is the generator's. The tightest tables are the host's at the same capacities (`lathec_ram32.py`, `lk_ram32.host_link`), which refuse exactly where the Lathe-written tools do. Each program is linked with `rt_math` first in `LINKARG` (below, "Pending weights").

| Program | Modules (and main) | Lines | Functions | Bytes a function | Code and constants | Left below HIMEM | The compiler's tightest table | The linker's tightest tables | Compiles (cycles, at 2 MHz) | Link (cycles, at 2 MHz) | Drive 0 / drive 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 KB, mode 4 | 3 (8 compiles) | 913 | 80 | 132 | 8,268 | 7,860 | names 1,350 of 3,072 | functions 120 of 296, slots 321 of 800 | 104.6 million, 0.9 min | 144.9 million, 1.2 min | 12 files, 81 KB / 16, 52 KB |
| **16 KB, mode 4** | 6 (11) | 1,802 | 152 | 134 | 15,816 | 312 | names 1,560 of 3,072 | **calls 446 of 576**, functions 192 of 296, nodes 192 of 300 | 174.6 million, 1.5 min | 270.7 million, 2.3 min | 15, 120 KB / 22, 93 KB |
| 20 KB, mode 7 | 7 (12) | 2,228 | 191 | 133 | 19,727 | 5,617 | names 1,604 of 3,072 | **calls 542 of 576**, slots 642 of 800, functions 231 of 296 | 212.0 million, 1.8 min | 335.4 million, 2.8 min | 16, 143 KB / 24, 113 KB |
| **25 KB, mode 7**, fewer and larger functions | 8 (13) | 2,469 | 170 | 189 | 24,633 | 711 | function buffer 891 of 1,536 | **calls 528 of 576**, slots 654 of 800, functions 210 of 296 | 235.4 million, 2.0 min | 403.2 million, 3.4 min | 17, 151 KB / 26, 134 KB |

"Left below HIMEM" is what the program leaves of `$1900` to HIMEM for its data and its stack's needs beyond zero page (its variables are all in zero page here); `$0401-$06FF` (767 bytes) is there besides. The cycles are the emulator's, whose MOS charges nearly nothing for the disc: on a real DFS the link's reading of 300 to 600 KB adds minutes ("The linker on a 32K BBC").

**What does not link.** The 25 KB program of the usual shape (8 modules of 28 functions, 26.7 KB, 266 functions of its own) needs more calls than the linker's 576 (link error 13, the host's at the same capacities; at full capacities it uses 757 calls, 874 slots, 306 functions and 306 nodes); with fewer calls a function (1.2 and 0.8 a function besides the run-time's) it runs out of slots (800, link error 12), at 282 to 290 functions of 296. A 24.6 KB program links when its functions are fewer and larger (17 a module, about 190 bytes each: the table's last row). So:

### The answer

- **The largest program the pair compiles and links**, end to end on the Model B: **about 20 KB of code of the usual shape** (7 modules and a main, 2,200 lines, 190 functions of 130 bytes), and **about 25 KB, mode 7's memory with 711 bytes to spare**, when its functions are fewer and larger (190 bytes each). A mode 4 program (16 KB) links with a fifth of the calls to spare. The compiles take about 2 minutes and the link 3 at 2 MHz, before the disc's time.
- **What limits it first.** On the linker's side, its calls table (576 call edges): at the usual 2.7 calls a function it is full at about 20 KB; then its slots (800, about 3 a function) and its functions (296, the run-time's among them). With the tools' own shape (3.7 to 4.2 calls a function) the calls would be full at about 16 KB. On the compiler's side nothing here came near: a generated module's tightest table is its name heap at about half (1,350 to 1,600 of 3,072) or the function buffer (891 of 1,536 for the largest functions). The 32K compiler takes modules of up to about 900 lines of real code ("What the 32K form compiles", the name heap first); a generated module of 90 functions (1,100 lines) still compiles, with 2,465 bytes of names, since its names repeat more than real ones do. On the disc: 31 files a side, so the objects and interfaces of at most 15 modules (the program's, the main and the 4 run-time modules) on one side, 10 of the program's own; and 134 KB on drive 1 and 151 KB on drive 0 for the 25 KB program, more than a 40-track side (100 KB) holds: two 80-track sides (200 KB each), a double-sided 80-track disc in one drive (drives 0 and 2) or two drives.
- **How to shape the modules to get there**: modules of 250 to 400 lines (20 to 30 functions), with import lists of the names used (a list of 3 to 8 names; at most 56); functions of 100 to 300 bytes rather than many one-liners or many calls of small helpers (each function costs the linker a function row, about 3 slots and its calls, whatever its size: 25 KB of 190-byte functions fits where 25 KB of 130-byte ones does not); `rt_math` (and any module that every other calls) first in `LINKARG`; and at most 10 modules of the program's own on one side for the objects.
- **Pending weights.** A module's WGT record weights the parameters of the functions it calls in other modules; for a function not read yet the weight waits in a table of 16 in the linker's 32K build (`lk_scan.MAX_PENDING`; 64 in the others). A program whose every module multiplies or divides calls `rt_math`, which `build.py` lists last, from every module: the 16 KB program in build.py's order is link error 41 (and the 26 KB one is in the host's full linker too, with 64). With `rt_math` first nothing waits. On the BBC the user writes `LINKARG`, so the order is the user's: the documentation should say "the run-time modules first". (Since 2026-11-18 the order decides nothing: the weights that do not fit the table are read again, "The order of the object files"; and the capacities were retuned to the calls, so the 25 KB program of the usual shape links: "Capacities retuned".)

### Suggestions, ranked

1. **Give the 32K linker's free main RAM to its calls, slots and functions** (small, and right). The eight-bank form has 1,113 bytes of main RAM free ("The linker told of its fixed regions"), and these programs leave the variables' rows and the symbols nearly empty (the 20 KB program: 45 of 257 variables and constants). The usual shape at 26.7 KB needs 757 calls, 874 slots, 306 functions and 306 nodes: at 2 bytes a call and a slot, about 7 a function (its columns) and 20 a node, calls 576 to 770, slots 800 to 880 and functions and nodes 296 and 300 to 312 take about 860 bytes, and would take the usual shape from about 20 KB to mode 7's 25 KB. It is `LKSMALL 2`'s values in host and twin (`lk_small.py` and the twins' `#if LKSMALL == 2`), with `test_lk_ram32.py`'s account; nothing else changes. Estimated, not built.
2. **Pending weights**: say in `bbc.md` and `boards.md` that `LINKARG` lists the run-time modules first (nothing to build); or 32 pending weights in the 32K build (4 words each in the work area: 128 bytes of nodes, about 6 nodes).
3. **Two drives for the objects** (nothing to build, not tried: each object is named in `LINKARG` with its drive, so `2/NAME.lo` beside `1/NAME.lo` should be read the same): more than 15 modules a program; worth a test and a line in `boards.md`.
4. **The compiler's names** (the compiler's agent's first suggestion, keywords and predeclared names out of the name heap, about 700 bytes): it lets real modules be about a quarter longer, so fewer modules and so fewer files on the disc, but it does not raise the size of a program, which the linker limits first.
5. **Fewer symbol rows, fewer stubs, fewer REG slots** (the compiler's agent's others): main RAM for the compiler's tables, none of which was the limit here.

## The developer's cycle (2026-11-18)

The owner's aim: a developer working on the compiler on the B+128, with the module's RAM form (sixteen banks, `direct16`) in its socket, compiles the tools, links them in their ROM forms and makes the new ones the live `*LATHE` and `*LLINK`, with no host in the loop and no disc changed. The owner chose (2026-11-20) one tool at a time, each on a pair of floppies of its own: the compiler's developer has the compiler's pair, the linker's developer the linker's.

### MODLOAD, as built

`lathe/src/modload.lth`, a `*RUN` program in Lathe (`modload-bbc.env`: `bbc.env`'s machine in main RAM, with `define MODULE_SLOT 4`), independent of the module, which it overwrites:

    *RUN MODLOAD [-sSLOT] HOME ENV MAP IMAGE [ENV MAP IMAGE]...     the whole module, from nothing
    *RUN MODLOAD [-sSLOT] ENV MAP IMAGE [ENV MAP IMAGE]...          these tools, into the module there

For each tool it takes the ROM environment the tool was linked with, the linker's map and the resident image (`LATHE`, `LLINK`), and the bank files named in the environment from the image's directory: exactly what `*LLINK` writes for a ROM-form link. It reads the environment as the linker does (`define`, `when` and `unless`) for the `code` range and the `bank` lines of the module (value `$80` and up), and the map for each bank file's size (its `W` lines) and the end of the fixed code (its `F`, `D` and `T` lines without `b=`).

**The layout it loads is bbcrom.py's whole layout** (`bbcrom.layout(..., whole=True)`, `bbcrom.py --whole --home HOME`): the tools' banks where their environments put them (the eight-bank ROM forms: the compiler 0 to 4, the linker 5 to 7, unchanged), the home bank next (8), its code and tables at `$8050`, and each tool's resident part whole in a bank of its own after it (9, 10), at `$8050`. Each command's copy list is one entry, the whole bank (16,288 bytes) to the tool's load address, so the copy list does not depend on the resident image's length, and a new tool of another length needs no new module code. Copying the whole bank costs only bytes copied past the resident part, into the tool's variables below `$7C00` (checked when the layout is made).

**HOME** is the home bank's bytes from `$8000` to `$BFEF`, which bbcrom.py writes: the reserved bytes, the service code, the tables, the texts of the errors (one part, after the tables) and, at `$BFE0`, the layout's **description**, 16 bytes: `LW`, version 1, the home bank, the number of tools, 1 if the commands' entries have a top (the check of HIMEM), the command table's address, and each tool's banks of the module as a word, a bit a bank (the compiler `$001F`, the linker `$00E0`). MODLOAD carries HOME unchanged. So a change to the compiler or the linker needs nothing from the host; a change to the error texts, `*HELP` or `module.asm` does (the texts are packed by `msgpack`, the code assembled by the host's assembler).

**One tool into the module there** (no HOME): the module's home bank holds nothing that depends on a tool's link. Its command table has, for each command, its name, its copy list, the tool's start (its `code` range's first byte) and, with the check of HIMEM, its top (the end of its highest range in main RAM, + 1); the copy list is the whole resident bank; the texts and the service code are the tools' both. So a new link of a tool leaves the home bank as it is if its start and top are where they were, which they are unless its environment's ranges change, and only its own banks are written: its bank files at `$8050` of the banks its environment names, its resident image at `$8050` of its resident bank. **How MODLOAD knows the module there**: bank 0's reserved bytes, the same in all sixteen banks but for each bank's own number at `$804F`; the home bank from the service code's `LDA $BFF0+home` in them (the bytes `AD 4F 80 48 AD nn BF`); and the home bank's description. A tool's banks (from its environment) must be the banks of one of the described tools, which gives its resident bank (home + 1 + its place in the table), and that command's entry must have the tool's start and top. Refused: a slot that is not such a module (`no module MODLOAD knows in the slot`: an empty RAM form, a home bank with no description), a tool whose banks are no tool's of the module, a tool whose start or top moved (`... a new HOME is needed`: the home bank's tables would copy it to the wrong place or check the wrong HIMEM). With HOME, HOME's description is checked against the tools in the same way, the tools in the table's order.

**The checks, all made before anything is written:** every file opens; each bank file is the size its map gives; each resident image is the length its map gives (the end of its fixed code less the start of its `code` range); each piece fits a bank (`$8050-$BFEF`); no two pieces share a bank; HOME's own bank number (its byte `$4F`) is the bank the layout gives, and HOME is the length to its description; the description and the command table, HOME's or the module's, fit the tools as above. A failure prints `modload: WHAT NAME` and ends with `Exit 2`, and the module is as it was.

**The load:** the slot is marked no ROM in the MOS's table (`$02A1`, as the developer's form does); with HOME, HOME's reserved bytes are written to all sixteen banks, each with its own number at `$804F`; HOME to the home bank, the bank files to their banks, the residents to theirs; then the slot is entered in the table with HOME's ROM type. A failure while writing (a read error, Escape) leaves the slot marked no ROM, so a half-written module is never called: running MODLOAD again with good files mends it. MODLOAD writes every bank's reserved bytes, so it starts from an empty RAM form too: **LOADMOD could retire** for the tools (the first load from a host-made disc, `*RUN MODLOAD HOME ...` with the host's link outputs on it), and stays for a user's own module images, which have no maps.

**What differs from the EPROM image**: the tool binaries are the same eight-bank ROM forms, byte for byte; the module's code differs only in its home bank (8, not 0) and its copy lists (one whole bank for each command, from banks 9 and 10, where the EPROM's copies the resident part's own length from the ends of the tools' banks). The whole layout needs sixteen banks, so it is the RAM form's only.

**The emulator**: `--bbc-module-dump FILE` writes the module's banks at the end of a run, for the tests to compare.

**Tests**: `lathe/tests/test_modload.py`: the whole layout and its description on made-up programs; HOME is the image's home bank to its description; on the B+128 with ADFS and an empty RAM form, MODLOAD loads both tools, `*LATHE` then compiles a module as the host does and `*LLINK` gives the host's usage; what it writes is bbcrom.py's whole image bank for bank; a bank file of another size, an image of another length, a HOME of another bank and a missing file are each refused with `Exit 2`, and the module is left as the load before left it. Without HOME: into a module whose compiler's banks (0 to 4 and 9) or linker's (5 to 7 and 10) are cleared, the tool's load gives the whole image again, and `*LLINK` runs after it; an empty slot, a home bank without its description, a command whose start is another and a description whose tools have other banks are each refused, the module as it was. `lathe/tests/test_bbc_cycle.py` is the cycle (below).

### The discs: a pair for each tool

Both tools and their link outputs on two floppies do not fit (measured 2026-11-18: about 7,250 sectors of 256 bytes for both tools' sources, objects and ROM-form link outputs, against 5,120 on two L discs). One tool's do, with the other tool loaded already in the module and left there, which MODLOAD without HOME allows. Each developer has a pair of L discs (640 KB each, `*AFORM 0 L`):

| | The compiler's pair | The linker's pair |
|---|---|---|
| Drive 0 | the compiler's 25 sources (`lth`), its ROM environment (`env.lathec-bbc`), `LINKARG`, `MODLOAD`: 28 files, 606,178 bytes, **2,397 of 2,560 sectors, 163 free** | the linker's 26 sources, `env.linker-bbc`, `LINKARG`, `MODLOAD`: 29 files, 372,290 bytes, **1,484 sectors, 1,076 free** |
| Drive 1 | its 25 objects and interfaces (`lo`, `li`), the resident image `LATHEC`, its five bank files (`BIN`), its map (`map`): 57 files, 577,524 bytes, **2,311 sectors, 249 free** | its objects and interfaces, `LINK`, its three bank files, its map: 57 files, 402,772 bytes, **1,627 sectors, 933 free** |

(Counted as ADFS counts them, the emulator's count at the end and at most the same: the map and the root 7 sectors, a directory 5, a file its length in whole sectors.) The modules both tools import (`bbc`, `bbcfs`, `disk`, `host`, `sys` and the run-time modules) are on both pairs, each compiled with its tool's defines; they must not share a disc, since the two tools build them with other defines. The second and later turns write each file over its old one in its own space; a file that is not there yet (a new module) needs the 256 sectors ADFS gives at OPENOUT free, which the compiler's drive 1 (249 free) has not: the developer deletes the map (written last, and made again) before such a turn. HOME is not on either pair: the first load of the module (at power on, the RAM form being empty) is from a third disc, which the host makes once: `MODLOAD`, `HOME` and both tools' ROM environments, maps, resident images and bank files, about 1,500 sectors, `*RUN MODLOAD HOME ...`.

### The cycle, as built

`lathe/tests/test_bbc_cycle.py` (opt-in, `LATHE_BBC_CYCLE=1`; `LATHE_BBC_CYCLE_TOOL=LATHE` or `LLINK` for one): for each tool on its pair, the module's RAM form holding the host's first load from power on (bbcrom.py's whole image of both tools, as MODLOAD writes it from the third disc: test_modload shows it), each turn in one run of the emulator with no disc changed:

1. `*LATHE OPTIONS 0/NAME.lth 1` for each of the tool's modules in build.py's order, the host's command lines;
2. `*LLINK @LINKARG`: the tool's ROM form, `1/LATHEC` (or `1/LINK`), its bank files and its map;
3. `*RUN MODLOAD ENV 1/MAP 1/IMAGE`: the tool into its own banks of the module, the other tool and the home bank as they were.

The second turn runs on the module the first left (dumped at its end), so its `*LATHE` (or `*LLINK`) is the one the first turn linked. The sources carry a change in copies only, to show which tool runs: for the compiler the version byte of the interface files, 2 to 3 (`decl.lth` and its twin), so the second turn's `li` files have 3 where the first's have 2; for the linker the mark of a read-only bank in the map, ` rom` to ` ROM` (`lk_map.lth` and its twin), so the second turn's map has ` ROM`. At each turn every file on both drives is the host's of the same commands (the first turn's by the host's tools, the second's by the host's twins with the change), and the module's sixteen banks are bbcrom.py's whole image of the host's link outputs and the other tool.

| Turn | The compiler's pair | The linker's pair |
|---|---|---|
| 1 | 3,979 million cycles, **33.2 minutes at 2 MHz** | 2,230 million cycles, **18.6 minutes** |
| 2 | 3,979 million cycles, 33.2 minutes | 2,230 million cycles, 18.6 minutes |

At most two files open and one written at a time; at most 26 entries in a directory. As elsewhere the emulator's MOS charges nothing for the discs' own time.

### Is the developer's form still needed?

Not for the cycle: with MODLOAD the tools are worked on in their ROM forms only, and a new link is live after one `*RUN MODLOAD`. The developer's form of the tools (`ROMFORM 0`, `*RUN LATHEC`, `*RUN LLINK`, which load their banks into the module's RAM at start) is still what the tests use for the corpus and the self-compile in a single `*RUN`, and its loader in `rt_bbc` stays in any case: a user's own banked program (`bbc-bank.env`, `*RUN PROG`) loads its banks so. What removing the tools' developer's form would save (counted 2026-11-20, nothing removed): in `lathec-bbc.env` the `define ROMFORM` line and 7 `unless ROMFORM` entries (its code and data ranges for each PAGE, its `bank 33` with the texts' constants, its place of `out`, `TEXTS_IN_MODULE 0`) and the `when ROMFORM` conditions on 9 more, which would lose their condition; in `linker-bbc.env` the `define`, 1 `unless` and 2 `when` entries; the texts-in-the-tool build of `err` and `lk_err` for the BBC (`TEXTS_IN_MODULE 0`, which the host builds keep); and the tests that build or run it: `test_bbc_selfhost` (the run under `*RUN LATHEC`), `test_bbc_selflink` and `test_bbc_adfs`'s `Loop` and `test_bbc_rom128`'s loop (the new compiler run as `*RUN LATHEC`; the cycle covers that now in the ROM form), `DeveloperForms` in `test_bbc_dfs` and `test_bbc_adfs`, and the developer's-form cases of `test_bbc_rom`, `test_bbc_rom128` and `test_bbc_ram32` that compare the two forms' environments. The developer's form also needs the fault fix of 2026-11-17 (the slot unmarked when a developer's form loads its banks), which the user's banked programs need too. Those loops would move to the ROM form and MODLOAD, as the cycle does.

## The texts' packer on the BBC (2026-11-20)

The owner's goal: that all coding can be done on the BBC. The texts of the tools' errors are packed into the module by `lathe/host/driver/msgpack.py`; `lathe/src/txtpack.lth` (TXTPACK) is its twin in Lathe, built with `lathe/src/txtpack-bbc.env` and run with `*RUN`:

    *RUN TXTPACK [-pK/N] ERR LKERR OUT

**What it reads.** The tools' own error modules as Lathe source, `err.lth` and `lk_err.lth`: every string of the constants whose names start with `MESSAGES` (in `err.lth` `MESSAGES_1` to `MESSAGES_3`, a line `number text` each; in `lk_err.lth` `MESSAGES` and `MESSAGES2`, line n the linker's error n), a constant running from its `const MESSAGES...` line through the lines after it that start with a string, with the language's escapes. Chosen over a plain text file of the texts because on the BBC those two files are what the developer edits and compiles: the ROM forms leave the texts out (`TEXTS_IN_MODULE 1`) but every other build holds them from there, so a changed wording is in one place on the BBC, as `err.py` and `lk_err.py` are on the host; `test_msgpack` checks that the twins hold the host's texts, so the host's packer and TXTPACK read the same texts.

**What it writes.** Part K of N of the texts (as `msgpack.split(N)` cuts them; 1/1, all of them, if not given): `text_first` (160 bytes), `text_second` (160) and `text_texts` (each text's codes ended by a zero), the bytes bbcrom.py assembles after `texts.asm`'s code for a part. The whole layout of the developer's module has one part.

**The same tables.** The texts are numbered as msgpack numbers them (the compiler's error n is text n, the linker's 255 - n, an empty text for a number without one) and refused where it refuses them (`txtpack: ...`, `Exit 2`): the compiler's numbers reaching the linker's, a number below 1, a byte outside `$20-$7E`, and pairs nesting deeper than eight levels. The pairs are chosen as msgpack chooses them: each turn the pair of codes used most often in the part's texts, of pairs used as often the one with the smaller first code and then the smaller second (msgpack's `max` by count, then `-first`, then `-second`), a run of three equal codes counting its first pair and going on from its third; until 159 codes are taken or no pair is used three times.

**Memory and time.** The texts in place (8.5 KB, each packed where it lies; the real ones 7,883 bytes), a table of the pairs counted (2,048 slots, 8 KB: the real texts reach 1,446 different pairs), the tables: code to `$2B1B` at the DFS's PAGE (`$311B` at ADFS's), data `$3200-$7AB8`, 18,617 bytes. For the real texts **560 million cycles, 4.7 minutes at 2 MHz** (every pair counted again each turn: 159 turns of 8 KB).

**Tests**: `lathe/tests/test_txtpack.py`: on the emulated BBC, every part of every split into one to four parts of the real texts is msgpack's, byte for byte; texts added to each tool pack as msgpack packs them; the compiler's numbers reaching the linker's, a byte outside `$20-$7E` and pairs nesting nine deep are refused as msgpack refuses them, and eight levels packed as it packs them (`LATHE_TXTPACK_REPORT=1` prints the time and the memory).

## The module's own code in Lathe: what stands in the way (2026-11-20)

Asked: `module.asm`, `texts.asm` (and `loadmod.asm`) as Lathe source, `asm` functions and constant tables, compiled and linked by the Lathe tools into the bytes `asm/pyasm.py` gives. Measured on small programs linked with a window `$8000-$BFDF`, a `rom` bank with a file and the module `place`d in it (nothing built yet; the owner chooses):

- **Order.** A placed module's constants go first in its bank, in declaration order, then its functions in source order, the modules in the order of the object files: data and code can alternate only module by module (the reserved bytes are data, code, data; the home bank code, data, code, data, code, tables), so the image would be some twelve modules linked in a fixed order.
- **Addresses of its own items.** The module's code needs the bank addresses of its own items in data and in immediates: `JMP service` in the ROM header, the `.word`s of the command table (each command's copy list) and of the stub (`ended`), `#<text_texts`. The linker gives a function's address taken anywhere but a `JSR`/`JMP` the address of its stub in fixed memory (`#<back` gave `$1910`, not `$8000`), and a constant whose address is taken (`@T` in a table, or `#<T`) goes to fixed memory; both are right for a banked program, whose pointers may be used with the bank not mapped, and wrong for a sideways ROM's own code.
- **What is kept.** A constant nothing kept names, and a function nothing reaches, get no address: the header's bytes and the service entry, named by no code, would be dropped.
- **Exact addresses.** Nothing places an item at an address: `number` at `$804F`, the home code at `$8050`, the description at `$BFE0` (pads of counted sizes would do for the first two, not for the last, which moves with the texts).
- **The embedded assembler** (the compiler's, which this work must leave alone): no `#if` inside an `asm` block (module.asm's `.ifdef`s would be whole functions twice), an operand is a term plus or minus a number (no `copier_end-copier`, no `latch+home` with `home` a name: constants worked out by hand), no byte in a block (known, `build-plan.md`).

The options put to the owner (2026-11-20): linker entries for a bank that is the module's own (addresses of its items as they are, kept whether named or not, a module placed at an address), or an assembler for asm17's subset that `module.asm`, `texts.asm` and `loadmod.asm` use, in Lathe, which assembles those files themselves on the BBC.

## One image for every machine with sideways RAM (2026-11-20)

(Since "The ROM plan" below, a region moves as one block by whole pages, the list has no calls of
map and unmap, and blocks of a region in main RAM are not turned into nothing; what follows up to
there is the first build, as it was measured.)

The owner's decision, after the study ([`spikes.md`](spikes.md), "One ROM for every BBC: a study"):
one 128 KB image for a machine with at least one bank of free sideways RAM, one for a machine
with none, each working with the DFS or ADFS by PAGE and using the room the DFS leaves. This is
the first of them, **Image A**, at its first stage: the mechanism, and the B+128 with its four
banks at PAGE `$1900` and `$1F00` from one image. Built: `region NAME WIN N dynamic` and `placer
MODULE` in the linker (host and twin; [`configurations.md`](configurations.md), "Regions placed at
run time"), the placer `lathe/rt/rt_place.lth`, `define ADAPT` in `lathec-bbc.env` and
`linker-bbc.env`, the tests `test_lk_dynamic.py`, `test_bbc_place.py` and `test_bbc_adapt.py`.

### The image

`bbcrom.rom_env(..., settings={'ADFS': 1, 'ADAPT': 1})` for both tools (`test_bbc_adapt.build_image`):
the ROM forms linked from `$1F00`, the highest PAGE served, as the ADFS build was, with `BBCFS 0`
(names as given; the run-time choice of names, `BBCFS 3`, is another branch's, below). Every region
of both tools is `dynamic`, in the order its `when ADAPT` entries give: the compiler's `STRING`,
`WANTS`, `OUTTAB`, `TOKENS`, `FUNCBUF`, `NAMES`, `SYMS` (and `MSGS`, empty in the ROM form); the
linker's `LKNODES`, `LKSLOTS`, `LKLOCAL`, `LKCALLS`, `LKWORK`; small and often mapped first. Each is
linked in its slot as before (12, 13, 0 and 1), at full capacity. `rt_place` is in the compiler's
bank 4 and the linker's bank 2; `link` is in the linker's second bank (it was so already with
`ADFS 1`). The splits: the compiler's code `$1F00-$523F` and data from `$5240`, the linker's
`$1F00-$47DF` and `$47E0`, so that the list fits after the code.

### At the start

The module copies each tool's resident part, the list with it, to `$1F00` as before (nothing in
`module.asm` or `bbcrom.py` changed). `$start` calls `rt_place.place` after `rt_bbc.start`:

1. PAGE (OSBYTE 131) above `$1F00`: `PAGE too high`; HIMEM (OSBYTE 132) below the end of the
   tool's ranges (`$7C00`): `Mode 7 needed`. Both MOS errors raised from `$0100`, as the module
   raises its own.
2. The free areas: PAGE to `$1EFF`; what the link left (the code range from the list on, since the
   list is read once; `data` and `more` after their variables); `$7C00` to HIMEM in a shadow mode.
3. Each region in order: in main RAM if every one of its variables fits there, each in the first
   area that holds it; else where it is linked.
4. The places: each address of a moved variable moved; each block's bank of a region in main RAM
   the module's own slot (any slot would do: what runs in a block reads only main RAM); and the
   calls of map and unmap of every function copy whose blocks all map regions in main RAM three
   NOPs (a `JMP unmap` an RTS), so those blocks cost nothing (the study measured 67 cycles a block).

With every region where it is linked nothing is written. It is assembly (1,031 bytes; the same in
Lathe was 1,332) using the MOS's `$A8-$AF`, and its 127 bytes of variables are the tool's.

What goes where, from the lists (`places.py`'s model of the placer, which `test_bbc_place.py`
checks against the real one on the BBC):

| Machine | PAGE, HIMEM | Free main RAM | The compiler's regions there | The linker's |
|---|---|---|---|---|
| B+128, DFS | `$1900`, `$7C00` | 3,645 | `WANTS` (1,600 bytes; 15 calls of map and unmap nothing) | none (1,679 free at most in one area) |
| B+128, DFS, shadow mode | `$1900`, `$8000` | 4,669 | `WANTS` | none |
| ADFS alone | `$1D00`, `$7C00` | 2,621 | `WANTS` | none |
| B+128, ADFS and DFS | `$1F00`, `$7C00` | 2,109 | `WANTS` | none |
| Master 128 (not run: the emulator has no Master) | `$0E00`, `$8000` | 7,485 / 7,055 | `STRING`, `WANTS` (3,648; 23 calls) | `LKNODES` (3,600; 8 calls) |

The tables are whole variables at full size: `STRING`, `TOKENS` and OUTTAB's table are 2,048 bytes
each, more than any one free area holds below a Master, so at PAGE `$1900` 2,045 of the 3,645 free
bytes stay unused. Sizing the tables at start-up, the next stage, is what uses them.

### Measured

From Image A on the emulated B+128 (four banks), `--bbc-strict` on filled memory, every file the
host tools' (`test_bbc_adapt.py`):

| | PAGE `$1900` | PAGE `$1F00` | The B+128 image today |
|---|---|---|---|
| the self-compile, 18 compiles | **876.3 million** | **876.4 million** | 874.0 million |
| the linker links the compiler | **3,024.5 million** | **3,024.5 million** | 3,023 million |
| the rebuild loop | **4,045.7 million** | | 4,478.2 million (2026-11-18) |
| `*LATHE`, `*LLINK` with no arguments | 1,045,256, 754,204 | 1,044,396, 753,410 | 852,232, 651,777 |

The start-up is about 190,000 cycles longer for the compiler and 100,000 for the linker (the
list copied a byte at a time with the rest, 1,183 and 799 bytes, then read), about a tenth of a
second at 2 MHz a command; the 15 blocks of `WANTS` saved do not make it up in a compile.

### The account

The image: **414 bytes free** of the 131,072 (`BBCFS 0`), against 4,715 in the B+128 image of today
built the same way. Where the 4,301 went: the lists, 1,982 (1,183 and 799, copied at each
command); `rt_place` twice, 2,062; the linker's own code for the new entries, about 110 as judged
(`lk_envf` 89, the rest `lk_name` and `lk_emit`), the rest of it being left out by `LKDYN 0`; the
resident parts' `$start` and stubs, 13 and a few; the rest the pieces' entries. With `BBCFS 3`, whose `bbcfs` is
909 bytes as judged in each tool, the image does not fit: about 1,190 bytes over (measured after
the merge of `BBCFS 3`: 795 bytes free before the lists' 1,982, and both tools' code ranges 22 and
47 bytes short), so Image A is built with `BBCFS 0` for now and its tests cannot yet run under
`--bbc-fs dfs` or `--bbc-fs adfs`. What would bring it
back, ranked: (1) the placer once, in the module's home bank, for both tools (about 1,000 bytes; a
change to `module.asm`: a routine the tools call with the list's address); (2) the lists packed
tighter (a byte a place in runs of one kind; about 500); (3) the lists in a bank, not copied, read
by the placer through `rt_bbc` (no ROM saved, the start-up's copying saved).

The linker of the ROM forms leaves dynamic regions out (`define LKDYN 0`, about 2.7 KB of its banks),
so the 128 KB image's `*LLINK` cannot link a program with a dynamic region (`dynamic` is a bad entry,
link error 3); the developer's form, Wendy 2's builds and the host's can.

### The ROM plan: the lists by whole pages, the placer smaller (2026-11-20, later)

Image A as first built did not fit with `BBCFS 3` (about 1,190 bytes over) and its `*LLINK`
could not link it (`LKDYN 0`). So, measured with `BBCFS 3`, `ADFS 1`, judged and placed by the
links, free as `bbcrom.image` lays the image out:

| | The lists | The placer | Free in the image (`LKDYN 0`) |
|---|---|---|---|
| Today's B+128 image, no `ADAPT` | | | 2,903 |
| Image A as first built | 1,982 (1,183 and 799) | 1,031 twice | about 1,190 over |
| **Image A now** | **623** (382 and 241) | **591 twice** | **1,072** |

What changed (host and twin, byte for byte; `test_lk_dynamic.py`, `test_bbc_place.py`):

- **A region moves as one block, by whole pages.** The low byte of every address in it stays as
  it is, so the low bytes are not listed, and a word or a high byte is changed by adding one
  number to one byte: no kind, no linked low byte, no variable table, one byte a place in most
  cases. The block wastes at most 255 bytes where it goes, and no two-byte variable can come to
  lie across a page (the refusal of them went).
- **No list of the calls of map and unmap.** Their 254 places (146 and 108, in 112 function
  copies) cost about 600 bytes of lists and 200 of code; what they bought is 67 cycles a block of
  a region in main RAM. A region in main RAM keeps its blocks, mapping the module's own slot. On a
  B+ nothing moves at all now (below); on a Master the blocks of `STRING`, `WANTS` and `LKNODES`
  stay, about 74 million cycles of the linker's link of the compiler (2.4 %, the study's count of
  `LKNODES`' blocks at 67 cycles) and little in a compile.
- So the list is, for each region, its bank's value, its block, its high bytes and its blocks'
  banks (161 and 75 high bytes, 69 and 51 banks), and `rt_place` is 591 bytes.

What goes to main RAM now (the model of the placer over the lists): on a B+ at PAGE `$1900` or
`$1F00`, shadow mode or not, nothing (the smallest blocks are 1,600 and 2,048 bytes, and a block
needs its own low byte); on a Master (`$0E00`, `$8000`) the compiler's `STRING` and `WANTS` and the
linker's `LKNODES`. The DFS's room is the next stage's, the capacities set at start-up.

Tested: `test_bbc_adapt.ImageAWithEitherFilingSystem`, Image A with `BBCFS 3`, compiles, links and
runs a program of several modules under `--bbc-fs dfs` (PAGE `$1900`), `--bbc-fs adfs` (`$1F00`)
and a filing system that is neither, every file the host tools'.

**The linker in the image with `LKDYN 1`**, so that the image's `*LLINK` can link the image's own
tools: about 2,612 bytes of the linker's banks as judged (`lk_dyn` 1,938; `lk_emit` 266, `lk_envf`
116, `lk_name` 109, `lk_boot` 69, `lk_alloc` 41, `lk_graph` 34, `lk_win` 20, `lk_place` 19), banks 5
and 6 then 463 and 1,559 over as judged, the image 581 over before the lists: **about 1,160 bytes
over** in all. The loop test of the first build linked the compiler's developer's form
(`lathec-bbc.env` with `ROMFORM 0`, no `dynamic` regions), not Image A's ROM form.

**Ranked, what would bring `LKDYN 1` in** (estimated from these measurements):

1. One placer in the module's home bank for both tools: 591 bytes (a change to `module.asm`,
   `bbcrom.py` and `MODLOAD`'s HOME file; not built: it waits for the loader's work to land).
2. `lk_dyn` written smaller (its 1,938 bytes judged are three readings of the region definitions a
   place; one table of each definition's dynamic number, kept as they are read, would take most
   of them out): 600 to 900 bytes (estimated).
3. Then the banks rebalanced: `link` and `lk_dyn` in the linker's third bank, which has 313
   judged left.
4. If still short: one of the shelved savings of `spikes.md`, `BRK n` for the error calls (0.75 KB)
   or the bank on the stack in `with` blocks (0.5 KB).

On top of that, stage 2 needs the probe and the capacities (estimated 300 to 500 bytes of the
placer, and the twins' capacity variables, about 40 bytes of main RAM and a few hundred of the
compiler's banks), and Image B (1,900 free, its linker's first bank 198 short with `BBCFS 3`; 19 short when measured again, and it fits with `link` in bank 2: "The image for machines with no sideways RAM") needs
the placer and the lists for main RAM only, without `lk_dyn` in its linker unless the owner wants
the 32K machine to rebuild its own image.

### One placer in the module, and the PAGE check (2026-11-20, later)

- **The placer is the module's** (`module.asm`, `place`, under `.ifdef placer`, which `bbcrom.py`
  defines when a program of the image has dynamic regions: 536 bytes of the home bank, once for
  both tools). A tool's `rt_place.place` is 13 bytes of fixed code: the list's address to
  `$A8/$A9` and OSBYTE 143 for the module's service call `$4C` with Y = 255, a text no error has,
  so the reserved bytes did not grow. The placer's variables are at `$0100-$012C`, which nothing
  uses while a tool starts. A program not started from such an image is not claimed and keeps its
  regions where they are linked. `MODLOAD`'s whole layout carries the module's code as built by
  `module_code`, so its HOME has the placer too.
- **The module refuses PAGE above a command's start address** (step 0 of a command, with the
  HIMEM check: `PAGE too high`, raised from `$0100` before anything is copied), in every image
  that checks HIMEM: about 50 bytes more in each (the B+128's `BBCFS 3` image without `ADAPT`
  2,903 to 2,853 free). `test_bbc_place.py` runs its program as the command of a module image of
  its own, so the placer is the module's there too, and PAGE `$2100` is refused with
  `--bbc-strict` on.
- **`lk_dyn` smaller**: a region numbered by its entry (the list has every region, one that is
  not dynamic with no block and no places), one call from `lk_emit` reading the fix-up itself, the
  constants refused as the list is written, the end of `data` as the top: 1,799 bytes as judged
  (1,938), the linker's other changes for it 477 (743).

**The account, `BBCFS 3`, `ADFS 1`** (bank by bank as the linker judges them, of 16,272; free as
`bbcrom.image` lays the image out):

| Bank | Tool | Today, no `ADAPT` | Image A, `LKDYN 0` | Image A, `LKDYN 1` |
|---|---|---|---|---|
| 0 | LATHE | 13,759 | 13,759 | 13,759 |
| 1 | LATHE | 15,271 | 15,271 | 15,271 |
| 2 | LATHE | 14,007 | 14,007 | 14,007 |
| 3 | LATHE | 12,173 | 12,173 | 12,173 |
| 4 | LATHE | 14,269 | 14,269 | 14,269 |
| 5 | LLINK | 16,245 | 16,245 | **16,537 (265 over)** |
| 6 | LLINK | 15,193 | 15,193 | **17,101 (829 over)** |
| 7 | LLINK | 15,884 | 15,884 | 15,959 |
| free in the image | | 2,853 | **1,654** | does not link |

With `LKDYN 1` the linker's three banks hold 49,597 bytes as judged where they have 48,816: **781
bytes over** however its modules are arranged (bank 7 has 313 to give), and the image would have
about 200 bytes too few besides. So Image A cannot yet link itself on the BBC: its `*LLINK` has no
`lk_dyn`, and the developer's cycle and the rebuild loop with Image A's own ROM-form environment are
not run. What remains, for the owner: 781 bytes of the linker's banks, from `BRK n` for the error
calls (0.75 KB, of both tools: the linker's share is not measured) or the bank on the stack in
`with` blocks (0.5 KB), or `lk_dyn` written in assembly in the twin (its 1,799 bytes are about 230
lines of Lathe; an assembly version would be about 700, estimated), and about 200 bytes of the
image.

### Stage 2, first part: finding the sideways RAM (2026-11-20, later)

The module's placer now finds the free sideways RAM before it places anything (`p_find`): every
slot that is not the module's, that the MOS's table of ROM types (OSBYTE 170) does not mark, that
holds no ROM header (one loaded since the last BREAK: `0`, `(C` at the copyright offset) and that
keeps two patterns written at `$8008` (`$55` and `$AA`, neither of which an empty socket's open bus,
the high byte of the address, gives), its own byte put back after. The probe runs from `$014F`,
copied there, with interrupts off, since it selects each slot in the window. Then each region that
stays in sideways RAM goes in the slot it is linked in if that is free RAM, else in the first free
slot, one slot for all regions linked in one; its blocks' banks are changed to it. If there are
fewer free slots than the tool is linked with: `Too little sideways RAM`.

So Image A runs on a machine with four banks wherever they are: tested on a Model B
(`--bbc-model b`) with sideways RAM in slots 8 to 11 (`test_bbc_adapt.ImageA.test_a_model_b_with_four_banks_elsewhere`:
hello compiled, linked and run, and two of the compiler's modules compiled, every file the host
tools'); with two banks it is refused (`test_too_little_sideways_ram_is_refused`). The policy's
other rules are not built: no special case for the B+ or the Master by OSBYTE 0 (the probe finds
the B+128's slots 0, 1, 12 and 13 as well), no guard against a board that writes into another bank
than the one selected (Solidisk's and some Watford boards, from memory), and no way for the user
to name the slots. The module's code and tables are now 1,464 bytes (804 of them the placer and
the probe); the image has **1,386 bytes free** with `BBCFS 3` (the same image without `ADAPT`
2,837).

**Not built yet then** (since built for the name heap: "Capacities set at start-up", below): **the capacities set at start-up**, which a machine with one or two banks needs
(and which is how the DFS's 1,536 bytes would be used: on a B+ no region fits main RAM whole). The
design, from the study and this work: each table's limit a variable under `#if DYNAMIC` in the
twins (the compiler's name heap first), the placer giving each region the bytes its slot or area
has, and the tool reading its share at `$init`.

### Capacities set at start-up: the name heap (2026-11-20, later)

The first of the compiler's limits, the name heap, now takes the room its machine has. Built
(host and twin together; `test_lk_dynamic.py`, `test_bbc_place.py`, `test_bbc_rooms.py`):

- **The linker lists the capacity, the placer writes it.** `region NAMES WIN 32 dynamic
  kernel.name_room`: the last word names a word variable in main memory and in no region (else
  link error 3, a bad entry, with the name: no new message, so that no image's texts change).
  The linker looks the name up as it reads the objects, as it does the placer's `place`
  (`lk_name.note_room_names`, `bind_room`), and adds to the region's entry in the list the
  variable's address and where the region's last variable starts in its block
  ([`configurations.md`](configurations.md), "Regions placed at run time"). The placer writes
  there, before `$init` runs, the bytes it gave the block less that: the room the last variable
  has. So the variable that grows must be the last of its block: the one the linker puts highest
  in the bank, which is the first its module defines (a bank is filled top-down). For `NAMES`,
  `kernel.names` is the only one.
- **In the twin**, under `#if ROOMS` (`define ROOMS 1` with `ADAPT 1` in `lathec-bbc.env`, `0`
  in every other compiler environment): `var name_room: word`, which the placer sets; else
  `const name_room = NAME_HEAP_SIZE`. The two tests of the heap's end compare with `name_room`
  in every build, so every build but Image A's compiles to the same bytes as before. The host
  keeps its constant.
- **The placer packs the regions.** It no longer keeps a region where it is linked in a slot
  mapped onto one found: after main RAM's free areas, each slot of free sideways RAM the probe
  finds is an area too, the window `$8000-$BFDF` (`$BFE0-$BFFF` are the module's latch and its
  mirror), in the order of the slots. Each region, in the environment's order, goes in the first
  area that holds its block at the low byte it is linked at (main RAM's first, as before); one
  with a capacity variable gets instead the area that gives it the most bytes, if that is at
  least its size as linked (its floor, for now), and all of it. A region no area holds is
  refused, `Too little sideways RAM`. `NAMES` is the last entry of the compiler's, so it gets the
  largest area that is left. Twelve areas at most (five of main RAM, the rest slots: a machine
  with more free slots uses the first ones). The module's code and tables are 1,630 bytes (1,464;
  the placer 921 of them, 755 before, with the probe's 75; the image 1,174 bytes free with `BBCFS 3`, 1,386 before), the placer's variables
  `$0100-$015B` and the probe copied to `$015C-$01A6` (`$014F-$0199` before), deeper into the
  stack's page by 13 bytes: by inspection only, as before, nothing the MOS does while a command
  starts goes that deep.
- `places.plan` (`lathe/tests/places.py`) is the model of the placer: where each region goes and
  the capacity it gets on a machine; `test_bbc_place.py` checks it against the placer on the BBC.

**What the name heap gets** (the model, over Image A's list):

| Machine | PAGE, HIMEM, free sideways RAM | The name heap | The other regions |
|---|---|---|---|
| B+128, DFS | `$1900`, `$7C00`, 0 1 12 13 | **16,128** (slot 12, from `$80E0`) | slot 0 (`STRING` to `FUNCBUF`, 14,592 bytes), slot 1 (`SYMS`); slot 13 unused |
| B+128, DFS, shadow mode | `$1900`, `$8000`, the same | 16,128 | the same |
| B+128, ADFS and DFS | `$1F00`, `$7C00`, the same | 16,128 | the same |
| Model B, sideways RAM 8 to 11 | `$1900`, `$7C00` | 16,128 (slot 10) | slots 8 and 9; slot 11 unused |
| three banks | `$1900`, `$7C00`, 8 9 10 | 16,128 (slot 10) | slots 8 and 9 |
| Master 128 (model only) | `$0E00`, `$8000`, 4 to 7 | 16,128 (slot 6) | `STRING` and `WANTS` in main RAM, the rest in slots 4 and 5 |
| two banks, one bank | | refused | |

9,216 bytes was the heap as linked: 75 % more. With three banks the compiler now runs (four were
needed; the linker's five regions, 43,248 bytes at full size, do not pack into three slots in
their order, so `*LLINK` still needs four); with two its fixed regions take both slots and the heap's floor is its linked size, so
it is refused until the other tables can shrink (the next part). The memory below `$1F00` (1,536
bytes on a DFS-only machine) and a shadow screen's 1,024 still hold nothing on a B+: no table but
the name heap has a capacity yet, and none of the fixed-size ones fits them as a block.

**What compiles now that did not**: a module whose names need 12,923 bytes of the heap
(`test_bbc_rooms.big_names_source`, 330 variables with names of 31 characters) is refused by the
compiler with a fixed heap (error 70, too many names) and compiles with Image A on the B+128 at
PAGE `$1900`, `$1F00` and in a shadow mode, on a Model B with four banks and with three, every
file the host compiler's with a heap of 16,128. The host compiler with the heap at any size from
the least a module needs up gives the same files: `test_bbc_rooms.SameObjects`, every module of
the compiler, the five of a generated program and that one, each at six sizes from its least
(`lathec_heap.py` runs the host compiler with the heap given). The least: from 974 (`sys`) to
7,177 (`decl`) for the compiler's own modules, so the self-compile is far from the heap's end.

### Two banks: floors, ceilings and packing (2026-11-20, later)

- **Floors and ceilings.** `region TOKENS WIN 33 dynamic kernel.token_room from 768 to 2048`:
  the room of the region's last variable at least 768 bytes (without `from`, its size as linked)
  and at most 2,048 (without `to`, no limit); a ceiling below the floor, or anything else after
  them, is a bad entry. The linker holds the two numbers in the environment's text after the
  variable's name (no table of its own: Wendy 2's linker has no data to spare) and lists, after
  where the last variable starts, the least and the most bytes of the block
  ([`configurations.md`](configurations.md), "Regions placed at run time").
- **The placer, by kind of region, in the environment's order**: one of fixed size goes in the
  first area that holds it (main RAM's first); one with a capacity and no ceiling in the area
  that gives the most, all of it, if that holds its floor; one with a ceiling in main RAM's
  area that gives the most if one holds its floor, else in the free sideways RAM's area that
  gives the least that holds it (so that it fills a gap and leaves the large areas whole), and
  at most its ceiling of it. The module's code and tables are 1,785 bytes (1,630); the
  placer's variables to `$0160` and the probe at `$0161-$01AB`.
- **The compiler's entries** (`lathec-bbc.env`, `ADAPT`): the regions of fixed size by size,
  the largest first (`SYMS` 10,544, `FUNCBUF` 4,864, `OUTTAB` 4,096, `STRING` 2,048, `WANTS`
  1,600), so that they pack; then INLINE's saved tokens, `kernel.token_room from 768 to 2048`
  (the corpus's peak is 520; INLINE tests `kernel.token_room` under `#if ROOMS` where it tested
  `SAVED_SIZE`); then the name heap, `kernel.name_room from 4096`, which takes the largest area
  left.

**What the compiler gets** (the model of the placer over Image A's lists; the emulator ran the
machines marked so):

| Machine | Name heap | Saved tokens | The rest |
|---|---|---|---|
| B+128, DFS, `$1900` (run), and in a shadow mode (run) | 16,128 (slot 12) | **1,312, below `$1F00`** | full; slot 13 unused |
| B+128, ADFS and DFS, `$1F00` (run) | 16,128 | 1,120, in the code range after the list | full |
| Model B, sideways RAM 8 to 11 (run); three banks (run) | 16,128 | 1,312 | full |
| Master 128 (model only) | 16,128 | 1,120 | full; `OUTTAB` in main RAM |
| **Model B, two banks, DFS (run)** | **8,192** | 1,312 | full |
| **Model B, two banks, ADFS (run)** | **8,192** | 1,120 | full |
| one bank | refused | | |

With two banks the compiler compiles its own modules (`decl`'s names need 7,177 bytes of the
heap, the most of any), every file the host compiler's, under the DFS and under ADFS
(`test_bbc_rooms.OnTheBBC.test_the_compiler_compiles_itself_with_two_banks`); the module of
12,923 bytes of names gives there what the host compiler gives with a heap of 8,192, error 70.
The linker's five regions (43,248 bytes) still need four banks: with fewer `*LLINK` is refused
until its tables can shrink (the next group of work).

**The memory below `$1F00`.** On a B+128 (four banks) every table has its full size and a slot
is left over, so no table gains from the DFS's 1,312 bytes (1,536 less the 224 its place's low
byte costs): they hold the saved tokens there, which frees nothing that is short. They count
where the banks are few: with two banks the saved tokens' 1,312 come out of the second slot, the
name heap's. A shadow mode's 1,024 bytes (`$7C00-$7FFF`) are an area the placer has, but no
region with a floor of 1,024 or less fits a gap that the others do not fill first; they are
unused.

### One bank: planes, wants, and the tables set at start-up (2026-11-20, later)

(The evaluation that came before this, "what one bank needs", was decided by the coordinator:
steps of 256 rows, and the symbol table's rows set by the machine, 768 where they fit, 512 where
768 does not, 256 with one bank.) Built (host and twin byte for byte for the linker;
`test_lk_dynamic.py`, `test_bbc_place.py`, `test_bbc_rooms.py`):

- **Regions of planes.** `region SYMS WIN 34 dynamic kernel.sym_rows rows 256 want 512 to 768`:
  every variable of the region is planes of 256 bytes, one a row, one after another (a byte
  array of 256, `sym_bytes`'s seven columns, `sym_words`' ten planes with `rows`); with R rows
  each plane is R bytes. The linker holds each place's target and lists after each high byte its
  plane, (target - first) / 256; the placer adds to the high byte, besides the pages the block
  moved, the block's steps for each plane before the byte's own. No accessor changes: the
  columns' constant offsets (`KIND_AT` and the rest) are the planes the places name, and
  `byte_base` and `word_base`, the offsets of `byte_of()` and its kin, are made at `init()` from
  `sym_rows` under `#if ROOMS`; `thaw_top` starts at `sym_rows` and OUT walks to it. The members'
  type and register are two planes of one array in Image A (`member_columns`: an array of 256
  takes a byte index), so the members have the symbols' rows. Nothing of it is the compiler's in
  the module: any region whose variables are planes can use it, the linker's in group 3 too.
- **Capacities as steps above a least.** The list's entry for a region with a capacity is now
  what the variable holds at the least, the least bytes of the block, what a step adds (256, or
  the block's planes times 256), the steps to the most (255: no most), the steps to the want and
  whether it is planes ([`configurations.md`](configurations.md), "Regions placed at run time").
- **The placer tries and gives up steps.** Every region with a most starts at it, and all are
  placed in the list's order, each in the first area that holds it, main RAM's first (one with
  no most in the area that gives the most, all of it). If one does not fit, the last region with
  steps over its `want` gives up half of them, then the one before it, round and round, and the
  walk is tried again; when no region has steps over its want, they give up half of what they
  have, the same way, to their least. When a walk fits, it is made once more, writing. Nothing
  is written until then, so a walk can be tried again at no cost but time; the free areas and
  the probe of the slots are made afresh for each walk.
- **The compiler's tables** in Image A, under `#if ROOMS` (each a constant of the same value in
  every other build, so that they compile to the same bytes): `kernel.name_room` from 3,072
  want 7,680 to 16,128; `kernel.sym_rows` 256 to 768 want 512; `fbuf.buffer_room` from 1,024 to
  4,096 (want 4,096); `out.table_room` and `lex.string_room` from 512 to 2,048 (want 2,048);
  `kernel.token_room` from 768 want 1,024 to 2,048; in that order, the order of how much a table
  matters when memory is short (the name heap first) and about that of their sizes. `WANTS`
  stays at its size. The wants are what the machine with two banks had (the compiler's own
  modules need the name heap 7,177, 475 symbols, a function buffer of 3,402 and a constant table
  of 2,038).
- **The linker's environment text** is 512 bytes with `LKDYN 1` (384 without): the six capacity
  variables' names and words did not fit. So Wendy 2's banked linker has its code from `$5940`
  (`$58C0`), and `test_lk_memory`'s ceiling is 128 bytes higher.

**What each machine gets** (the model of the placer over Image A's list; the emulator ran every
machine but the Master; `test_bbc_rooms.OnTheBBC.test_what_the_compiler_gets_on_each_machine`):

| Machine | Name heap | Symbols and members | Function buffer | Constant table | String | Saved tokens |
|---|---|---|---|---|---|---|
| B+128, DFS, ADFS, shadow mode; Model B with 4 or 3 banks; Master (model) | 16,128 | **768** | 4,096 | 2,048 | 2,048 | 2,048 |
| two banks, DFS or ADFS | **8,704** | 512 | 4,096 | 2,048 | 2,048 | 1,024 |
| **one bank, DFS** | **4,096** | **256** | **1,792** | **768** | **768** | 768 |
| **one bank, ADFS** | **4,096** | **256** | **1,280** | **512** | **512** | 768 |
| the 32K Model B's build, for comparison | 3,072 | 264 | 1,536 | 264 | 264 | 384 |

The labels (192), the fix-ups of a constant table (256) and the rows of what an import wants
(160) are at their full sizes everywhere. A B+128 gains 768 symbols (560 before) and the saved
tokens' 2,048 (1,312 since group 2), at no cost to the name heap's slot: the symbols take the
fourth slot, idle before. A shadow mode's 1,024 bytes are an area the placer has, but no
region fits it before the others do, so they are not used; nor can the name heap use main RAM
as well as a slot (a region is one block): both are noted, not built.

**What one bank compiles**: twelve of the compiler's eighteen modules under the DFS (`kernel`,
`src`, `lex`, `typetab`, `fold`, `fbuf`, `out`, `cond`, `asmblock`, `parts`, `lathec`, `sys`),
eleven under ADFS (not `kernel`); `err` is refused (its message table is a string of 2,038
bytes: error 7), and `reg`, `gen`, `inlines`, `expr` and `decl` for their names, symbols or
functions ([`spikes.md`](spikes.md), "One bank, measured"). Of a generated program
(`gen_program.py`), modules of up to 82 functions (about 1,050 lines each), under
both filing systems; at 84 the members are full (error 72). The 32K Model B's build compiles
modules of about 30 functions.

### The linker's tables (2026-11-20, later): three banks, and what fewer need

**Built.** Image A's linker regions are in an order that packs them into three slots
(`linker-bbc.env`, `ADAPT`): `LKWORK` (14,400 bytes) alone, `LKLOCAL` (8,000, from `$8060`) and
`LKSLOTS` (8,256, from `$9FA0` to `$BFDF` exactly) together, `LKCALLS` (8,992) and `LKNODES`
(3,600) together. So a Model B with three banks runs `*LLINK` at full capacities and links the
compiler, every file the host linker's, in 3,024.3 million cycles, as on the B+128
(`test_bbc_rooms.TheLinkerOnThreeBanks`). No code changed for it.

And the placer finds the region that gives up steps in one walk (the last before the one that
gave up last that can, else the last of all that can) and probes no slots for that walk: the
start-up with two banks 1.55 million cycles (2.34 million before), with one bank 2.6 million (7.8).
That is what had made the self-compile with two banks 905.3 million cycles: each of its 18
commands started in 1.33 million cycles more than with four banks, the halvings of the name
heap's 51 steps each costing up to eight walks of the list. Now 891.1 million (877.4 with group
2's placer, which tried far less: the rest is the walks that remain, about 0.54 million a command,
and 512 symbols' rows against 560).

**Not built: fewer than three banks** (`*LLINK` refused, `Too little sideways RAM`). What it needs
(since built for two banks, by planes beside variables of a fixed size: "The linker's tables on
two banks", below):

- The linker's tables are not planes of one size a region. `LKWORK` and `LKNODES` are one word
  array, the work area, split at `W_SPLIT`, whose columns are at offsets in its index made of
  `MAX_NODES`, `MAX_FIXES`, `MAX_EDGES` and `MAX_FUNCS` (`W_ADDR = 6 * MAX_FIXES`, `W_OWN = 7 *
  MAX_NODES`, `W_WCALL`, `W_START`...): constants in the index arithmetic of `wk()` and its
  callers, not addends of fix-ups, so the placer's planes cannot move them. Its 18,000 bytes stay
  whole, and one bank (16,352 bytes and little main RAM: the linker's variables take main RAM
  to `$7B23`) cannot hold them. One bank needs the work area's offsets made at start-up from
  capacity variables: about 115 uses of the `W_` offsets in the linker's code (51 of them in
  `lk_tab`), an estimated 300 to 500 bytes of its banks, which have 27, 1,079 and 388 free as
  judged.
- With two banks (32,704 bytes) the regions must give up about 10.5 KB of their 43,248. The work
  area cannot; the others could: `lk_name.local` (8,000, a word array with `rows`: two planes),
  `LKCALLS` (`edge_word`, 3,600 rows of a word, and `fn_edge`, 896 rows), `LKSLOTS`
  (`slot_sz` and `slot_weight`, 4,000 rows of a byte, and `big_slot` and `big_size`, 64 rows of
  a word). Two of these regions hold variables of different row counts, which the planes as built
  (one row count a region) cannot shrink. The options: (a) the planes per variable, each variable
  of a region its own plane size and steps (the list a header a variable, the placer's layout of
  the block a variable at a time: an estimated 100 to 150 bytes of the module's code, of the 636
  free); (b) more regions in the linker's source (`fn_edge` and the big slots each a region of
  their own), which changes every linker build's environment and layout; (c) half the rows of
  each table in Image A as linked, so that two banks hold them without shrinking (a loss for four
  banks: the compiler's link needs 799 functions of 896). With (a) or (b) the capacity tests of
  `MAX_LOCALS`, `MAX_EDGES`, `MAX_FUNCS` and `MAX_SLOTS` read variables, an estimated 30 to 40
  bytes of the linker's banks, in `lk_scan` and `lk_name` (bank 6, 1,079 free) and `lk_alloc` and
  `lk_graph` (bank 7, 388). With half of those tables two banks would link programs of about the
  32K build's size or more (functions about 448, slots 2,000, calls 1,800), not the compiler
  (799 functions).

### The linker's tables on two banks (2026-11-20, later)

**Built** (host and twin byte for byte for the linker; `test_lk_dynamic.py`, `test_bbc_place.py`,
`test_bbc_rooms.TheLinker`): `*LLINK` runs on a Model B with two banks of sideways RAM, under the
DFS and ADFS, with its symbols of the object files, its slots and its calls sized as it starts.

- **Not planes per variable: planes beside variables of a fixed size.** The design handed over was
  planes per variable (each variable of a region its own plane size and steps, the list a header a
  variable, the placer's layout of the block a variable at a time: an estimated 100 to 150 bytes
  of the module). Measured, one capacity a region is enough: the variables of other row counts
  are `lk_tab.fn_edge` (896 rows of a word, 1,792 bytes) in `LKCALLS` and `big_slot` and
  `big_size` (64 rows each, 256 bytes) in `LKSLOTS`, and neither needs to shrink. `fn_edge`
  cannot usefully: `MAX_FUNCS` also sizes four columns of the functions in main RAM (4,480 bytes,
  which stay), its rows would have to be whole pages (768 is below the compiler's 799 functions;
  1,024 would need 640 more bytes of main RAM, where the linker has about 220), and two banks hold
  it at its size. So a region of planes may hold variables that keep their size: `dynamic VARIABLE
  rows N planes P ...` (configurations.md, "Regions placed at run time"), P the planes in all,
  which its variables of a whole number of planes of N have; the others are fixed. The linker
  lists after each high byte, as before, the planes below its address, now counted by the
  variables below it (`lk_dyn.planes_below`: a fixed variable has none), so a fixed variable
  between planes moves with the planes below it. **The list's format and the placer do not
  change**: no byte of the module (2,061 bytes of code and tables, as before).
- **The linker's twins** under `define LKROOMS` (1 in `linker-bbc.env` with `ADAPT`, 0 in every
  other linker environment and in `lk_ram32`'s measuring one; the 16th of `linker-bbc.env`'s 16
  defines): `lk_name.local` is linked with `LINKED_LOCALS` (768) rows, `slot_sz` and `slot_weight`
  with `LINKED_SLOTS` (1,024), `edge_word` with `LINKED_EDGES` (768), and the placer writes the
  rows they get in `lk_name.local_rows`, `lk_tab.slot_rows` and `lk_tab.edge_rows`, which the
  tests of those capacities and the calls kept at the top of `edge_word` (`edge_rows - 1 - 2 *
  i`) read where every other build reads `MAX_LOCALS`, `MAX_SLOTS` and `MAX_EDGES`; in every other
  build each is a constant of that value, so those builds compile to the same bytes. The work
  area's columns keep `MAX_EDGES` (3,600) and `MAX_FUNCS` rows, the most `edge_rows` can be; the
  work area (`LKWORK` and `LKNODES`, 18,000 bytes) stays whole.
- **The entries** (`linker-bbc.env`, `ADAPT`), in the order that packs three banks: `LKWORK`;
  `LKLOCAL ... dynamic lk_name.local_rows rows 768 want 4096 to 4096`; `LKSLOTS ... dynamic
  lk_tab.slot_rows rows 1024 planes 2 want 3840 to 4096`; `LKCALLS ... dynamic lk_tab.edge_rows rows
  768 planes 2 want 3584 to 3584`; `LKNODES`. The floors are the 32K build's capacities rounded up
  to whole pages (640 symbols, 848 slots, 768 calls). The mosts: three banks hold the symbols and
  the slots in one slot, 16,128 bytes with 4,096 and 3,840 rows (4,096 and 4,096 would be 16,640),
  so the slots want 3,840 and give up their last step first; on four banks both have 4,096 (4,000
  before), the calls 3,584 (3,600: whole pages).

**What each machine's linker gets** (the model of the placer over Image A's list,
`test_bbc_rooms.TheLinker.test_what_the_linker_gets_on_each_machine`; the emulator ran every
machine but the Master; the start-up, `*LLINK` with no arguments, at PAGE `$1900`):

| Machine | Symbols of the object files | Slots | Calls | Functions, nodes, the rest | `*LLINK`'s start-up, cycles |
|---|---|---|---|---|---|
| B+128 (DFS, ADFS, shadow mode), Model B with four banks, Master (model) | **4,096** (4,000) | **4,096** (4,000) | 3,584 (3,600) | full (896 functions, 900 nodes) | 743,805 (722,309) |
| three banks | **4,096** | 3,840 (4,000) | 3,584 | full | 791,266 (722,071) |
| **two banks, DFS or ADFS** | **1,536** | **2,304** | **1,280** | full | **1,164,924** (refused) |
| one bank | refused | | | | 1,468,029 to the refusal |
| the 32K Model B's build, for comparison | 640 | 848 | 768 | 296 functions, 300 nodes | |

With two banks the work area takes one slot (14,400 bytes) and everything else the other: the
placer halves the three tables' steps in turn (no table has steps over its want but the slots'
last) until they fit beside `LKNODES`, 15,888 of its 16,352 bytes. Main RAM below `$1F00` (the
DFS's 1,536 bytes) holds none of them at those sizes, so the DFS and ADFS get the same.

**What it links.** On two banks, under the DFS and ADFS, every file what the host linker writes at
those capacities (`lk_rooms.py` gives the host linker them) and at its own: a program of the
end-to-end cases (`TheLinker.test_the_linker_links_a_program_on_two_banks`) and the largest
generated programs that run in mode 7 (`test_gen_program.OnTwoBanks`, opt-in, below). The compiler
does not link there: link error 13, too many calls, on the BBC and from the host at those
capacities alike, after 134.6 million cycles (it needs 3,255 calls). With three banks the linker
links the compiler in 3,025.3 million cycles (3,024.3 before), every file the host's.

**The largest program on two banks** (`LATHE_BBC_TWO_BANKS_PROGRAMS=1 ... test_gen_program`):
from PAGE `$1900`, 8 modules of 26 functions and a main (the 32K Model B's 25 KB target: 2,879
lines, 250 functions, 24,296 bytes of code and constants and 343 of variables, 705 bytes left
below HIMEM); from `$1F00`, 8 modules of 24 (2,699 lines, 226 functions, 23,392 and 311, 105 left).
Each is compiled by `*LATHE`, linked by `*LLINK` and run on the Model B with two banks: the output
what the generator computed, every file the host tools' at the capacities Image A's tools get there
(`test_bbc_rooms.host_files_at`) and at their own; 13 compiles, the link and the run in 668.7 and
644.6 million cycles. **Neither tool's capacities limit a program there; the memory it runs in
does**: one more function a module does not fit below HIMEM. On the host at the two-bank
capacities, with no limit of memory on the program, 10 modules of 33 functions (392 functions,
37,265 bytes of code) compile and link; the linker's tightest table is then its calls (1,091 of
1,280), so the calls limit a program of about 42 KB of code, more than the BBC's code range below
`$C000` takes.

**The account** (`BBCFS 3`, `ADFS 1`, as `bbcrom.image` lays it out): **410 bytes free** (636
before). The module's code and tables 2,061 bytes, unchanged. The linker's banks as judged 16,245,
15,217 (15,193: the tests of `local_rows` in `lk_scan` and `lk_name`, 24 bytes) and 15,884. Its
resident part 205 bytes more: `lk_tab` 125 (the calls kept at the top of `edge_word` addressed
from a variable, in `add_waiting` and `build_chains`, and the two tests of capacity) and the list
of places 80 (331 bytes, 251 before: a plane byte after each of the three regions' 53 high bytes
and their capacities' entries). Byte for byte the same as before: every image without `ADAPT`
(the B+128's DFS, ADFS and tool-chain images, the eight-bank ROM and its asked-filing-system
image, the 32K image, the self-host ROM) and Wendy 2's banked compiler; Wendy 2's two banked
linkers change (`LKDYN 1`: `lk_dyn` and `lk_envf`'s `planes`), and not by `LKROOMS`.

Since then (2026-11-20, later) three changes of the generated code and the linker's source, every
image's bytes changed by them: **1,218 bytes free** with `BBCFS 3`; the linker's banks as judged
16,054, 15,060 and 15,423, the compiler's 13,710, 15,202, 13,934, 12,104 and 14,395; with `LKDYN 1`
the linker 2,595 bytes over ([`spikes.md`](spikes.md), "The linker's ROM space, measured").

### The linker on one bank: measured, not built (2026-11-20, later)

With one bank `*LLINK` still stops with `Too little sideways RAM`: the work area (`LKWORK` and
`LKNODES`, 18,000 bytes) has one size, and with the other tables at their floors (10,768 bytes
with `LKNODES`) it does not fit 16,352 bytes and the little main RAM the linker leaves. One bank
needs fewer rows in the node columns, so the work area's offsets set as the tool starts. That was
designed, built as a prototype and measured; it needs about twice the ROM it was given (about 600
bytes, with a stop at 800) and would make the link of the compiler on four banks slower by more
than 1 %, so it was not built out. The prototype is kept outside the repository. The choice is
the owner's (below).

**The design measured.** Under `#if LKROOMS` every offset of the work area that depends on the
node rows is a variable of the same name, which every other build has as the constant it is
(those builds compile to the same bytes): in `lk_tab` `W_SCC` to `WORK_SIZE`, `W_SPLIT`, `W_SNAME`
and the chains' `W_WCALL`, `W_START`, `W_NEXT` (from `edge_rows`); `lk_graph`'s `STACK_EDGE`,
`FOUND`, `SEEN`, `LOW`, `NAMED`, `NOW`, `LATER`; `lk_alloc`'s `LAY_END`, `LAY_SIZE`, `LAY_DOWN`,
`CHAIN`, `WEIGHT_COUNT`, `CAND`, `LIST` and `MAX_TAKEN` (what the column of main memory bases leaves
after `LIST`); `lk_name`'s heap end. `lk_tab.size_work`, called first by `link.main`, and a
`size_columns` at the start of `lk_graph.build` and `lk_alloc.allocate`, make them from the bytes the
placer gives the two tables (`region LKWORK WIN 22 dynamic lk_tab.work_room from 4928 to 14400`,
`LKNODES` likewise): node rows the smaller of `work_room / 16` and `nodes_room / 4`, and the
functions no more than the nodes (node f is function f's first copy). `MAX_FIXES` is a constant
366 in Image A, what the least work area leaves below `W_OWN` for the fix-ups, `W_ADDR`'s column
and the slot's name, so the fix-ups' columns and `W_ADDR` stay constants (making them vary too cost
about 370 bytes more); no function of the compiler has more than 258 fix-ups and the compiler
writes at most 256 in a table, so it changes no output and no run of the corpus, but it is a
capacity of four banks (512) made smaller, and the names of an object file for the map's F, D and
V lines have 2,196 words (3,072). The S lines' names are held below `W_ADDR`, as in the 32K build
(`SLOTS_LOW` 1).

**What it costs** (the code of each module as compiled, against the tree before; `BBCFS 0`):

| Module | More bytes | Of them, the offsets made at start-up |
|---|---|---|
| `lk_tab` (resident) | 462 | 357 (`size_work`) |
| `lk_alloc` | 304 | 168 |
| `lk_graph` | 236 | 94 |
| `lk_name` | 50 | |
| `lk_map`, `lk_fix`, `lk_boot`, `lk_emit`, `lk_place`, `lk_scan`, `link` | 66 | |
| **in all** | **1,118** | **619** |

The banks as judged 15,182, 15,139 and 15,886 (15,145, 15,060, 15,423: bank 3 386 left); the
resident part does not fit main RAM (link error 27, the code range 159 bytes over), and with
`BBCFS 3` the first bank is 5 bytes over. Each offset made at start-up compiles to about 19 bytes;
each use of one costs 2 bytes more as a number (`ADC abs` for `ADC #`), about 11 more where a
column was reached directly (`work[W_SCC + n]` folds a constant offset into the address, a variable
one is added at run time), and branches lengthen.

**What it would cost in time** (an estimate, not run): the host linker linking the compiler calls
`wk` 4.73 million times (0.98 million of them in the node columns) and `set_wk` 0.73 million; 1 %
of the link (3,006 million cycles) is about 5 cycles a call. The split compared with a variable
alone is 4 cycles more a call (about 22 million), the node columns' index taken from a variable
about 12 million, the offsets added from variables about 20 million, and the direct readers
(`scc_of`, `order_at`, `end_of` and their kin) more: about 2 to 3 % in all.

**The placer needs a third tier** whatever the design. With today's rule a capacity on `LKWORK`
and `LKNODES` changes what two banks get: in the model their work area gives up steps while the
others are halved below their wants (work 644 rows, symbols 2,304, slots 2,304, calls 2,048). With
regions marked to give up last (a new word in the entry, the want byte `$FF` in the list; about 15
bytes of `module.asm`, estimated, and `places.py`), which give up steps only when no other region
can, four, three and two banks keep what they have, and one bank (under the DFS and ADFS alike)
would get, by the model:

| | Nodes and functions | Symbols of the object files | Slots | Calls |
|---|---|---|---|---|
| one bank (byte capacities) | **420** | 768 | 1,024 | 768 |
| one bank (planes of 256 rows) | 388 | 768 | 1,024 | 768 |
| the 32K Model B's build | 300 and 296 | 640 | 848 | 768 |

About 1.4 KB of the bank stays unused there; main RAM below `$1F00` holds no table at those sizes.

**The options, for the owner:**

- **A, as measured:** about 1,100 bytes and 2 to 3 % slower (estimated). `size_work` in a bank
  would bring the resident part's growth to about 105 bytes, not the whole.
- **B, A with `LKWORK` and `LKNODES` as planes** linked at their least (388 rows): the columns
  reached directly keep constant offsets, which the placer moves with the planes. It needs `rows N`
  allowed when N is not a whole number of pages (`lk_envf`, host and twin, under `LKDYN`), and the
  nodes then come in steps of 256 (388, 644, 900). About 950 bytes and 1.5 % slower (estimated).
- **C, B with the node columns at a constant index** (7,200) whatever the rows, so that `wk`,
  `set_wk` and the node columns' functions do not change: the index then has a gap below 7,200 on
  a machine with fewer rows, and the name heap must end with `work` there, which the host linker
  must be told by a constant of its own. 750 to 800 bytes and about 0.7 % slower (estimated); the
  only one near both limits, and the most intricate.
- **Room found elsewhere first**: the bank on the stack in `with` blocks (0.5 KB, estimated), or
  the candidates not built of [`spikes.md`](spikes.md), "The linker's ROM space, measured" (about
  440 bytes estimated outside `lk_dyn`, which the ROM forms do not link; `BRK n` for the error calls
  was counted there at 87 bytes and rejected), would pay for A or B in bytes, not in time.
- **One bank compiles, does not link**: Image A's `*LLINK` stays refused with one bank, and a
  program is linked elsewhere (or with the 32K image, a separate EPROM).

### What is not done

- The linker with one bank: measured, not built, the choice the owner's ("The linker on one bank:
  measured, not built"). The Master, and the rest of the probing policy: stage 2's next parts.
- Image B, the bare 32K Model B: stage 3.
- The module's own check: it copies the resident part to `$1F00` before the tool's `PAGE too high`;
  with PAGE above `$1F00` that copy writes below PAGE. The module should refuse PAGE above a
  command's load address as it refuses HIMEM (the module's agent's; `test_bbc_adapt` runs the
  refusal without `--bbc-strict` so that the tool's message is seen).
- Nothing is redundant yet: the B+128 builds of today (`$1900` with `BBCFS` 0 and 1, the ADFS
  build with `BBCFS 2`) stay until Image A carries the names chosen at run time and fits with them.

## The image for machines with no sideways RAM (2026-11-20, later)

The owner asked for two images, one that needs sideways RAM (Image A, above) and one that does
not, **Image B**, each working with the DFS or ADFS by PAGE and using what the DFS leaves free.
Image B is the 32K build made adaptive. **Built: both halves.** The linker's on a DFS machine
gives every table at least the 32K build's (2026-11-20, later: "Every block on a page" and "The
tenth block", below); the compiler's (2026-11-21: "The compiler: the name heap begun at PAGE",
below) runs at PAGE `$1900` and `$1F00` with its heap begun at PAGE.

### Why not the placer for every table

A dynamic region can be moved only where every place that names it is in fixed code, which the
module copies into main RAM; a bank is ROM, and a place there is link error 64. With
`FIXED_REGIONS` the code that names a table stays in the banks. Measured from the 32K build's
objects and map: **4,553 bytes of the compiler's banked code** name its tables (fbuf 1,659,
kernel 1,267, lex 672, decl 574, out 381), but only **142 bytes of the linker's** (`lk_name`'s three
accessors of `local`); the rest of the linker's namers are `lk_tab`'s, which is fixed. So the
linker's tables can move and the compiler's cannot.

### The linker

`linker-bbc.env` with `define RAM32 1` and `define ADAPT 1` (`bbcrom.rom_env(..., settings={'RAM32':
1, 'ADAPT': 1, 'ADFS': 1, 'BBCFS': 3})`; the `RAM32` and `ADAPT` entries of every other build are
now guarded by `unless ADAPT` and `unless RAM32`, which changes none of them):

- Linked from `$1F00`: code `$1F00-$3EDF`, data `$3EE0-$6DFF`, `more data $0401-$06FF` (code
  `$1F00-$3FDF` and data `$3FE0-$6EFF` before the tenth block, below). The data range
  ends at a page below HIMEM so that the variables that do not fit it go to `more`, and what is
  free is one area, `$6E00` to HIMEM, on a page as the regions' blocks are (below).
- `LKSMALL 2`'s capacities for everything but three tables. The work area (`LKWORK`, `LKNODES`) is
  fixed and told (`-f`); `LKWORK`'s blocks, which the 32K eight-bank build still keeps fixed (530
  bytes), are left out, since its bank 3 now has room for their readers (15,676 judged).
- `LKCALLS`, `LKLOCAL` and `LKSLOTS` are dynamic regions of planes (`LKROOMS 1`), in that order,
  each in a bank of its own (`WIN 22`, `20`, `21`): `edge_rows rows 512 want 768 to 768`,
  `local_rows rows 512 want 512 to 768`, `slot_rows rows 512 want 1024 to 1024`. Under `LKROOMS`
  with `LKSMALL 2` the twins link them at 512 rows, and `fn_edge` and the large slots are out of
  them, in main RAM: so each region is its planes alone. Each bank's variables end at `$BEFF`
  (`top WIN N $BEFF`, an entry of 2026-11-20, later: [`configurations.md`](configurations.md)),
  so every block starts on a page; the placer packs them with nothing between.
- `LKCALLS` and `LKSLOTS` are `dynamic main` (2026-11-20, later): in main RAM alone, so with
  `FIXED_REGIONS` they are told fixed (`-f`), their blocks are their bodies, and `lk_tab`'s
  accessors of them map nothing; the linker refuses no such use with error 62 for a `main` region.
  `LKLOCAL` is not: `lk_name`'s accessors of it, compiled so, would stay in bank 2 and name the
  region from ROM (link error 64), so its blocks map the module's own slot as in Image A and the
  three accessors are kept fixed (191 bytes).
- `link` in the linker's second bank (`when ADFS when ROM128 place link WIN 2`, as before): the
  banks are 16,253, 15,946 and 15,676 bytes as judged of 16,272. The resident part is 8,196 bytes
  (the list of places 183 of them), against 8,260 in the 32K form with `BBCFS 3` (8,634 before the
  slots and calls were `main`).
- **The placer for main RAM alone.** `bbcrom.py` assembles the module with `main_only` (not `probe`)
  when every program of the image with dynamic regions says `define FIXED_REGIONS 1`
  ([`configurations.md`](configurations.md), "Regions placed at run time"): `p_find` gives main RAM's
  areas only, the probe's code is left out, and a tool whose floors do not fit says `Too little
  memory`. Image A's module is assembled with `probe`, the same bytes as before.

**What the linker gets** (rows; the model of the placer, `places.plan`, over the list; the
emulator ran the first two):

| Machine | PAGE, HIMEM | Symbols of the object files | Slots | Calls | Functions, nodes |
|---|---|---|---|---|---|
| Model B, DFS | `$1900`, `$7C00` | **768** (`$6E00`) | **1,024** (`$7400`) | **768** (`$1900`, below `$1F00`) | 296, 300 |
| Model B, ADFS and DFS | `$1F00`, `$7C00` | 512 | 768 | 512 | 296, 300 |
| B+ in a shadow mode, DFS | `$1900`, `$8000` | 768 | 1,024 | 768 | 296, 300 |
| B+ in a shadow mode, ADFS | `$1F00`, `$8000` | 512 | 1,024 | 768 | 296, 300 |
| the 32K build, for comparison | `$1900`, `$7C00` | 640 | 848 | 768 | 296, 300 |

(Before the blocks were on a page, 2026-11-20: 512, 768 and 768 on the DFS machine, 512 each on
ADFS, 512, 768 and 768 in either shadow mode. With nine blocks, before the tenth: 512, 1,024 and
768 on the DFS machine, 512 each on ADFS, 768, 1,024, 768 and 512, 1,024, 512 in a shadow mode.)

**On a DFS machine every table is at least the 32K build's: the symbols of an object file 128
rows above (768 of 640), the slots 176 above (1,024 of 848)**, the calls, functions and nodes the
same. The free main RAM comes in blocks of 512 bytes (256 rows of two bytes): three below
`$1F00`, seven above the data, ten in all. **The generated 25 KB program (8 modules of 26
functions), which needs 502 symbols, 807 slots and 726 calls, links and runs on the DFS
machine.** On an ADFS machine the seven blocks above the data give the symbols and the calls 512
each and the slots 768: the largest generated program it links is 7 modules of 22 functions
(17.9 KB; 389 symbols, 623 slots, 499 calls), and one of 23 (542 calls) is refused there and
links with the DFS. (With nine blocks the ADFS machine's largest was 6 modules of 21 functions,
15.5 KB, and one of 22, 528 slots, was refused.)

### Every block on a page (2026-11-20, later)

Measured on the model of the placer over the list, then built. Each bank's variables went down
from the window's end, `$BFDF`, so a block of whole pages started at the low byte `$E0`, which
costs a block in each area that is a whole number of pages: below `$1F00` 1,536 bytes held two
blocks, from `$19E0`. The environment entry `top WIN N ADDR` ([`configurations.md`](configurations.md),
"Regions placed at run time"; host and twin, the twin's under `LKDYN`) puts a bank's variables
below ADDR instead; with `$BEFF` each block starts on a page, the area below `$1F00` holds three,
and the data range ends at a page (`$6EFF`). That gives the DFS machine nine blocks.

The tenth: the 32K build's capacities need ten blocks. `dynamic main` for the slots and the calls
takes 391 bytes off the resident part (and 47 off the list), so 438 bytes more of main RAM are
free; but the data range must end at `$6DFF` for a seventh block above it, and the data then lack
4 bytes: the variables go to `data` in order while they fit, and `more` takes only those after the
last that fits; `lk_tab`'s work area and nodes (6,000 bytes) are the last of the linker's own, so
`more` holds the run-time modules' 610 bytes and no more, and 157 of its bytes stay free. Four
bytes would give the DFS machine ten blocks (768 symbols, 1,024 slots and 768 calls, each at least
the 32K build's) and an ADFS machine seven. Not taken then: they would come
from a table's capacity (a function or a node fewer than the 32K build's) or from the order of the
object files, which every image shares. What `dynamic main` gives is speed (the slots' and calls'
accessors map nothing: see the cycles below) and 434 bytes of the 128 KB image (3,207 free, from
2,773; 3,176 measured at the commit that built it, 77f5c64).

### The tenth block (2026-11-20, later)

Taken once `build.py` stopped linking what an `#if` branch not taken imports (`imports_of`;
`lathe/host/README.md`, "build.py"): `sys.lth`'s `import disk`, under `#if PORTS`, had linked
`disk.$init` (15 bytes of code) and its 4 bytes of variables into every BBC tool, and `lk_emit`'s
`import lk_dyn`, under `#if LKDYN`, `lk_dyn`'s `$init` and variables into every ROM form of the
linker (their `place lk_dyn` lines are now under `when LKDYN`). That took 42 bytes off Image B's
resident linker (8,154, from 8,196), and the code then ends at `$3ED9`: the code range is now
`$1F00-$3EDF` and the data `$3EE0-$6DFF`, the same length as before a page lower, so that the
variables fit as they did and a seventh block is free above the data (before, the code was 36
bytes over `$3EDF`). The images' free bytes, before and after (the listings): Image B 3,176 and
3,225, the plain 128 KB image 5,408 and 5,460, the 32K image 5,422 and 5,474, Image A 2,869 and
2,926, the image of `test_bbc_asked_fs` 3,682 and 3,742, the sixteen-bank images 72,317 and 72,353
(ADFS), 72,409 and 72,445 (DFS), 72,439 and 72,475 (`test_bbc_toolchain`'s), the self-hosting
image 162,696 and 162,722; main RAM free in Image B's compiler 138 and 160 bytes, in its linker
(by its map) 529 and 575 before the split moved. Wendy 2's builds are the same bytes (their
`PORTS 1` links `disk`, and `bbc` and `host` have no `$init`).

**Tested** (`lathe/tests/test_bbc_image_b.py`, by default, about 25 s): the image fits the 128 KB
module (3,225 bytes free with the 32K compiler) and its placer is the one for main RAM alone; the
model's capacities on the four machines, the DFS machine's each at least the 32K build's; on a Model B with no sideways RAM at PAGE `$1900` and
`$1F00` a program of the end-to-end cases (`calls`, the host compiler's objects) linked by
`*LLINK`, every file the host linker's at that machine's capacities (`lk_rooms.py` with
`LATHE_LK_SMALL=2`) and at its own; a generated program of 7 modules of 23 functions (542 calls)
linked at `$1900` and refused at `$1F00`, each as the host linker at that machine's capacities
does it, so the real placer tells the machines apart as the model does; a `dynamic main` program
refused by `bbcrom.py` with the placer that probes; PAGE `$2100` refused (`PAGE too high`) and mode
4 (`Mode 7 needed`). `*LLINK`'s start-up: 552,928 cycles at `$1900`, 642,257 at `$1F00` with ten
blocks (577,353 and 678,564 with nine; 646,312 and 733,069 before the slots and calls were `main`);
the `calls` link 20.3 million cycles at `$1900`, 20.4 at `$1F00` (20.4 and 20.5 with nine, 21.1
before). With `LATHE_BBC_IMAGE_B_PROGRAMS=1` (a minute): under the emulator's
DFS at `$1900` the 25 KB program (8 modules of 26 functions, 2,879 lines) compiled by `*LATHE`
module by module (13 compiles, 262.7 million cycles), linked by `*LLINK @LINKARG` (364.3 million;
365.9 with nine blocks), `*SAVE`d and run, as `test_gen_program`'s 32K test does it; under its ADFS
at `$1F00` the largest program there (7 modules of 22, 2,112 lines, 17,904 bytes; 6 of 21 with nine
blocks) from the host compiler's objects, since the compiler's form in the image runs at `$1900`
only, linked and run (270.3 million cycles);
every file the host tools' under that filing system's names (`BBCFS 3`), and the host linker at
that machine's capacities linking it to the same image.

### The compiler: the name heap begun at PAGE (2026-11-21)

The compiler's tables cannot move (its banked code names them), but the name heap can start late:
it is reached only by offsets from its base, `name_top` starts at 1, 0 is no name, and nothing
reads below the first entry. So, built:

- **The layout** (`when RAM32 when ADAPT` in `lathec-bbc.env`): `kernel.names` lowest in main RAM,
  `$1900-$2B25` (4,646 bytes), by the environment's new form `region NAMES fixed $1900` (a fixed
  region's variables from an address of their own, outside the ranges:
  [`configurations.md`](configurations.md), "Regions placed at run time"); the code range
  `$2B26-$3FFB` (5,334 bytes resident, all of it), data `$3FFC-$7BFF`, `more data $0401-$06FF`:
  **6 bytes of main RAM free** (in `more`). BBCFS 3, the 32K form's placement of the modules in five
  banks, every region fixed (`-f`), `SMALL 1`, `ROOMS 0`.
- **At the start** `kernel.init` asks the MOS for PAGE (OSBYTE 131, `extern func osbyte_xy`) and,
  when PAGE is above the heap's address, begins `name_top` (and so `local_names`) at PAGE less it:
  the bytes below PAGE are the filing system's and are never written. On a DFS machine the heap is
  4,646 bytes, on an ADFS machine (`$1F00`) 3,110: 1,536 less. 40 bytes of code in kernel's bank.
- **The module refuses `*LATHE` at a PAGE above `$1F00`**: `define HIGHEST_PAGE $1F00` in the
  compiler's environment, which `bbcrom.py` reads; an image with such a program has the highest PAGE
  in each command's entry (the linker's, its start, `$1F00`), and `module.asm`'s PAGE check reads it
  there instead of the start address (`page_limit`, an offset in the entry; every other image is
  assembled as before, the same bytes). `PAGE too high`, as before.
- **Capacities, Image B's own** (`#if ADAPT` inside `#if RAM32` in the twins; `script_host.IMAGE_B`,
  checked by `test_memory.py`; the 32K build's are unchanged):

| Table | 32K build | Image B, DFS machine (PAGE `$1900`) | Image B, ADFS machine (PAGE `$1F00`) |
|---|---|---|---|
| Name heap | 3,072 | **4,646** | **3,110** |
| Symbols | 264 | 226 | 226 |
| Members | 264 | 264 | 264 |
| Labels of a function | 128 | 64 | 64 |
| Text memory | 768 | 672 | 672 |
| Token memory, saved tokens | 384, 384 | 304, 304 | 304, 304 |
| Function buffer | 1,536 | 1,472 | 1,472 |
| Import rows (`MAX_WANTS`) | 56 | 52 | 52 |
| Fix-ups of a constant table | 32 | 28 | 28 |
| Types | 40 | 38 | 38 |
| Weights of a function | 32 | 16 | 16 |
| String, constant table, others | | as the 32K build's | as the 32K build's |

So on a DFS machine the name heap is 1,574 bytes above the 32K build's and **nine capacities are
below it: symbols, labels, text, tokens and saved tokens, function buffer, import rows, table
fix-ups, types and weights**. How they were chosen: the census of 517 compiles (every module of
`lathe/src` and `lathe/rt`, every compile of `test_bbc_toolchain`'s corpus, the modules of the
generated programs of 8 modules of 26 functions and 6 of 21) with each table's peak use; the rule,
in order: the DFS machine compiles everything the 32K build compiles; the ADFS machine as much as
can be; the DFS machine keeps as much of the 32K build's capacities as it can. A split of
4,470 bytes of heap (symbols 232, text 704, tokens 320) gave the DFS machine 476 and the ADFS
machine 474: `lk_map` and `lk_name` lacked 18 and 176 bytes of heap there. The heap of 4,646 takes
them both, from 102 bytes of symbols (232 to 226), 32 of text and 16 of tokens; each is still above
the most any census compile that fits otherwise uses (225 symbols, 662 of text, 295 of saved
tokens). The members stay at 264: at 256 or fewer their arrays take a byte index (error 120).

**What compiles** (real compiles, by the host oracle `lathe/tests/lathec_image_b.py` at each
machine's capacities and heap start; the predictions from the peaks were all right): of the census,
**the 32K build 475, Image B on a DFS machine 476 and on an ADFS machine 476**, every one of the
32K build's among them; the largest module of each is `for_ranges.lth` of the corpus (3,756 lines),
of `lathe/src` and `lathe/rt` `fbuf.lth` (1,018 lines). The rest are refused for a function too large,
an import list, saved tokens, a string, labels or a constant table on both machines, and at ADFS's
PAGE 8 of them for names first. On the emulated Model B (`test_bbc_image_b.Assessment`,
`LATHE_BBC_IMAGE_B_ALL=1`, 3.4 minutes): 54 of the 79 modules of `lathe/src` and `lathe/rt` at both
pages, each the oracle's files or error, the same files at both pages. A module of variables of 31
characters: 106 compile on the DFS machine, 64 on the ADFS machine, one more is error 70.

**The heap may begin anywhere**: `test_bbc_rooms.SameObjects` compiles each module with the heap
begun at offsets 2, 1,537 and 3,001 (the room above the same: the same files; 16 bytes less: error
70); on the emulated Model B `lk_name`, `typetab` and the 54 give the same files at `$1900` and
`$1F00`, the host compiler's at full size.

**The largest programs, end to end, with Image B's own tools** (`LATHE_BBC_IMAGE_B_PROGRAMS=1`):
under the emulator's DFS at `$1900` the 25 KB program (8 modules of 26 functions, 2,879 lines, 24,296
bytes): 13 compiles 263.1 million cycles (the 32K image: 261.6), the link 364.3 million (399.5), run;
under its ADFS at `$1F00` the 17.9 KB program (7 modules of 22 functions, 2,112 lines): 12 compiles
202.1 million cycles, the link and the run 270.3 million; every file the host tools' under that
filing system's names.

**Cycles**: `*LATHE` starts in 454,163 cycles at `$1900` and 454,182 at `$1F00` (the 32K image's:
451,267); `typetab.lth` compiles in 15.70 million at both pages (15.69 from the 32K image, DFS names);
`lk_name.lth` in 54.4 million; `*LLINK` starts in 552,932 and 642,261 and links `calls` in 20.3 and
20.4 million, as before.

**The ROM account**: Image B fits the 128 KB module with **3,181 bytes free** (3,225 before: the
compiler's init and the module's page limits); the compiler's banks as the linker judges them
14,186, 15,616, 14,592, 15,861 and 15,978 bytes of 16,272 (placed 13,120, 13,849, 12,742, 13,638,
13,926), the linker's as before.

### What Image B would make redundant (nothing removed)

The 32K image (`test_bbc_ram32.build_image`) and the 32K forms of both tools (`RAM32 1` without
`ADAPT`): Image B serves the 32K Model B under the DFS with the linker's calls, functions and nodes
the same, 176 slots more and 128 symbols more, and the compiler's name heap 1,574 bytes larger, but
nine of the compiler's capacities lower (above), and it serves ADFS's PAGE too. It compiles every
census compile the 32K form compiles. So `test_bbc_ram32` (`Ram32`, `Assessment`), `test_lk_ram32`'s
BBC runs and `test_gen_program.OnTheModelB` could run Image B instead (its `Assessment` and
`LargestPrograms` already cover the same ground at both pages); the 32K form's own capacities
(`#if RAM32` without `ADAPT`, `script_host.RAM32`, `lathec_ram32.py`) would then serve nothing but
the comparison. Nothing is removed: the owner decides, having the cost of the nine capacities.

## Open, for the owner

- ~~**File names.** The compiler joins a directory and a name with `/`, which the emulator now accepts only as a leading `./` (step 4); a real filing system needs its own scheme. DFS allows seven characters and uses `.` to separate the directory, so `asmblock.lth` cannot exist there. ADFS allows ten. The first version uses names as the emulator's directory takes them. A scheme is needed for real discs, for example `L.EXPR` for source, `O.EXPR` for the object file and `I.EXPR` for the interface, with module names kept to seven characters.~~ Closed (2026-11-16): the BBC's build maps the names, and module names are not limited ("File names on the BBC"). What a real disc still asks for is listed there: the linker's map against "Can't extend" (five files open and the image larger than a side were dealt with on 2026-11-16).
- **How a tool ends.** As a command it uses the language's zero page and the memory from PAGE, so the language that was running (BASIC) cannot be returned to as it was. ~~The tool should end by starting the current language again (OSBYTE 142).~~ Done so in step 3 (ROM form); a program run with `*RUN` still returns into the language, which may not survive it.
- **The command's tail** is copied to `$0700`, at most 239 bytes: the linker's longest command lines must fit that (the MOS's own line is 255 at most). The corpus's links fit; the compiler's own link is 247 bytes (step 5). The linker reads its arguments from a file, `*LLINK @FILE` (2026-11-16); the compiler has no such form yet, and its command lines are short.
- **The image's addresses.** The linker writes an image's bytes and not its catalogue entry; on the BBC `*SAVE` gives it its load and execution addresses (step 5). The linker could set them with OSFILE when its environment says `output raw` on the BBC, at the cost of a call the host linker does not have.
- **The 128 KB module's hardware**: `direct8`, a board of our own (an EPROM, a three-bit latch, a comparator), or the Computer Concepts carrier `cc128`, which exists, at 352 bytes less room and a second read a switch ("The 128 KB module", "What `cc128` would take").
- **Sideways RAM** slots a program's regions name are taken without asking: whatever the owner had loaded in them (a ROM image in sideways RAM) is overwritten at the command.
- **Other filing systems and screen modes** move PAGE and HIMEM; the layout is fixed at link time. One build per case, or one build for the smallest case. For ADFS answered so (2026-11-17, "ADFS"): `define ADFS 1` builds for `$1F00`, ADFS's PAGE with the DFS beside it, which serves ADFS alone (`$1D00`) too; everything of the tools fits, the compiler's ROM form with 104 bytes to spare. A shadow screen mode (HIMEM `$8000`) would give 1 KB more and is not used ("Room for the compiler at ADFS's PAGE").
- ~~**A MOS error in a developer's form after LOADMOD** goes to the module's bank (service call 6) before BRKV.~~ Fixed (2026-11-17, "ADFS", "Faults found"): the developer's form unmarks the slot in the ROM table.

## What the emulator cannot show

- That the header and service code live with the real MOS: its scan of the ROMs at reset (with its duplicate check, which compares ROMs, and the service calls 1 and 2 it makes, which the code returns unclaimed), service calls made during interrupts while the tool runs in another bank (the emulator has no interrupts; the test makes such calls with OSBYTE 143 from a program), `*HELP`'s own lines and its argument as the real MOS passes it, and OSBYTE 252's and 170's answers, which are from memory (`emulator/NOTES-bbcbplus.md`).
- That OSBYTE 142 from inside a service call leaves the real MOS in order (it resets the stack, which the emulator models, and prints the language's title, which it does not), and that BASIC entered so starts cleanly.
- The dummy reads of a real NMOS 6502. The module's code, the copier and the loader are written to keep them out of `$BFF0-$BFFF` (no instruction ends near it, indexed accesses there stay in their page, `$BFE0-$BFFF` are never read or written by a copy), but the emulator's core makes none, so that is by inspection only.
- A real DFS: LOADMOD's OSGBPB of 16 KB at a time, and how the DFS lays files out on the disc, so "Can't extend" and a full disc.
- A real ADFS: which free space it gives a file, how a growing file is moved, whether reserved space comes back at the close, `*COMPACT`, and a disc used for months; the emulator's model of them (`--bbc-fs adfs`) is from Acorn's user guide where the guide speaks and its own choice where it does not ("ADFS", "The emulator"). PAGE with ADFS and the DFS both on a B+ (`&1F00`) is from third parties, and ADFS's zero page from a memory map of disc systems in general. The names, five files open and 31 a drive are shown with `--bbc-fs dfs` ("File names on the BBC"), against rules read in third parties' documents, not Acorn's (`emulator/NOTES-bbcbplus.md`).
- Timing against real discs. The compiler compiling itself is 933 million cycles on the BBC ("Step 4, as built"), 7.8 minutes at 2 MHz, before the cost of reading 654,341 bytes and writing 398,290 through a real filing system, which the emulator's MOS does not charge.
- The `direct8` board: it is this project's design, and nothing has been built; the mirror of `$BFF8-$BFFF` is what the simplest decode would give, not a measured fact. The `cc128` carrier exists, but Lathe is not built for it.
- The real module's electrical behaviour. MAME models the SpellMaster carrier, so the eight-bank form (the compiler alone) could be tried there against the real MOS by someone who has the ROMs.
