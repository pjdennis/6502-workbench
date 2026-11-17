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
- **Since the symbol table is in a region** (2026-11-15, [`configurations.md`](configurations.md), "The symbol table in a region"): `compiler-bbc-bank.env` puts `SYMS` in sideways slot 0 (bank 34, value `$00`) and `OUTTAB` and `WANTS` in slot 1 (bank 35), and places `parts` in bank 3; OUT's functions with a block of `OUTTAB` are kept fixed (DECL's with `WANTS` too, where linked). gentest's fixed code now ends at `$4866` and its variables at `$5CCF` in the small build. At the full capacities **all four fit**, with the fixed variables from `$3C30` (outtest), `$4080` (regtest), `$4130` (condtest) and `$4870` (gentest; `$43B0` with the kept modules placed), and every section of their scripts gives what the twin gives at its own capacities (`test_bbc_bank_src.py`, `FULL_SPLIT`). `rt_bbc.map` has no test for the value 0, which `rt_bank` treats as a fixed region: on the BBC it is slot 0.
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

The owner wants the compiler and the linker in one 128 KB EPROM: eight banks of 16 KB. This is the layout's part of that: an eight-bank form of the module that can use every byte of the eight banks, and a gate that says how far the tools are from fitting it. The tools themselves are being made smaller elsewhere. Built: the scheme `direct8` in the emulator, `bbcrom.py --banks 8`, the home bank, the packing, LOADMOD for both schemes, the `ROM128` layouts in `lathec-bbc.env` and `linker-bbc.env`, `lathe/tests/test_bbc_rom128.py` (the gate) and `lathe/tests/farcall_matrix.py` (the far calls between modules, counted on the BBC).

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

The chosen layout is in `linker-bbc.env` under `when ROM128`. Fixing lk_out and lk_op (803 bytes as placed) uses the room the code range `$1900-$3FFF` had left (972 bytes) and takes 881 bytes as judged out of the banks; it saves only 1,288 far calls, since lk_emit, their caller, shares their bank. The resident part is 9,767 bytes (9,012 in five banks: lk_out and lk_op, and fewer stubs). With `BBCFS 1` the ROM form puts `bbcfs` in bank 1 as well (`when ROMFORM`), which that build must also make room for.

**The compiler in five banks** fits as it is; the search over every assignment of its 11 groups to five banks that fit found a better one, which `lathec-bbc.env` gives under `when ROM128`: bank 1 expr; 2 gen and lathec; 3 decl and asmblock; 4 parts, out, inlines, kernel, lex, fbuf, src and err; 5 reg, cond, fold and typetab (reg's and gen's calls of fold and typetab were the most of any pair, 98,212 and 71,079). Measured from the eight-bank image, the 18 compiles of the self-compile, every file the host's:

| Layout | Banks as judged | Resident | Far calls (18 compiles) | Cycles (18 compiles, ROM form) |
|---|---|---|---|---|
| five banks as in `lathec-bbc.env` | 15,717 / 15,154 / 15,441 / 14,367 / 14,309 | 13,989 | 733,977 | 945,267,054 |
| **`when ROM128`** | 15,717 / 15,154 / 15,714 / 14,716 / 13,687 | 13,959 | 551,124 | 901,564,042 (-4.6 %) |

### The account (the gate)

`test_bbc_rom128.py` links both tools for the eight-bank image (the compiler in banks 0 to 4, the linker in 5 to 7) with `lk_judged.py`, so that a tool that does not link is measured too, and lays the image out from what the links give. `test_both_tools_fit_the_128k_image` is an expected failure whose message gives the bytes over; `LATHE_BBC_ROM128_REPORT=1` prints the whole account. On 2026-11-17:

| Bank | Tool | Judged | Placed | Over as judged | Left to `$BFEF` | Modules |
|---|---|---|---|---|---|---|
| 0 | LATHE | 15,717 | 14,756 | | 1,532 | expr |
| 1 | LATHE | 15,154 | 13,533 | | 2,755 | gen, lathec |
| 2 | LATHE | 15,714 | 13,768 | | 2,520 | decl, asmblock |
| 3 | LATHE | 14,716 | 12,550 | | 3,738 | inlines, parts, out, lex, kernel, fbuf, src, err |
| 4 | LATHE | 13,687 | 11,992 | | 4,296 | reg, cond, fold, typetab |
| 5 | LLINK | 16,844 | 14,961 | **572** | 1,327 | lk_envf, lk_err, lk_emit, lk_place, lk_fix, lk_win, lk_file, link |
| 6 | LLINK | 16,471 | 13,772 | **199** | 2,516 | lk_scan, lk_name, lk_map, lk_boot |
| 7 | LLINK | 16,688 | 13,572 | **416** | 2,716 | lk_alloc, lk_graph |

Copied at the commands: the compiler's messages for slot 13 (5,494 bytes), its resident part (13,959) and the linker's (9,767). In use: 108,904 bytes of code banks and 29,220 copied, 138,124 of the 130,304 the eight banks hold to `$BFEF`; with the module's code and tables (about 500 bytes) and the copy entries, **8,363 bytes over**. The linker does not link yet: link error 45, its bank 1 (the image's 5) 572 bytes over.

**What must still shrink for the gate to pass**: 8,363 bytes anywhere in the two tools (code of a bank, a resident part or the messages copied to slot 13: a byte saved is a byte saved), and of that, as the linker judges them, 572 bytes in the linker's bank 1 (lk_envf, lk_err, lk_emit, lk_place, lk_fix, lk_win, lk_file, link), 199 in its bank 2 (lk_scan, lk_name, lk_map, lk_boot) and 416 in its bank 3 (lk_alloc, lk_graph). The compiler's banks fit as they are. Moving the compiler's 5,494 bytes of messages out of the ROM removes them from the copy (and the slot-13 copy at every `*LATHE`). When the account is 0, `test_both_tools_fit_the_128k_image` succeeds unexpectedly: remove its `expectedFailure`, and the same file runs the tool chain on two small programs (`hello`, and `farcall` banked through LOADMOD) from the 128 KB image; `LATHE_BBC_ROM128_SELFHOST=1` the self-compile from it in the ROM and loader forms, `LATHE_BBC_ROM128_SELFLINK=1` the linker linking the compiler, `LATHE_BBC_ROM128_LOOP=1` the rebuild loop.

What the packing recovered: the sixteen-bank image of both tools left 53,013 bytes unused at the ends of its ten code banks; in the eight-bank layout every one of those bytes can take a piece, and `$BFE0-$BFEF` of each bank (128 bytes in eight banks) is room it did not have. What the eight banks cannot use: the reserved bytes (80 a bank), 16 bytes at the top of each, 8 bytes an entry, and gaps of 8 bytes or fewer.

### Start-up

Each command copies its pieces a byte at a time with a bank switch a byte, as before; a piece more costs an entry's walk (about 150 cycles). `*LATHE` and `*LLINK` with no arguments, before (2026-11-17, the sixteen-bank image) and after:

| Image | `*LATHE` | `*LLINK` |
|---|---|---|
| sixteen banks, before | 1,467,942 | 554,928 |
| sixteen banks, now (the same bytes) | 1,467,942 | 554,928 |
| sixteen banks with `--tails` (banks 0 to 10; `*LLINK` copies 2 pieces, not 1) | 1,467,942 | 555,088 |
| eight banks, the compiler alone (`when ROM128` layout, banks 0 to 4) | 1,466,112 | |
| eight banks, the linker alone in its five banks (banks 0 to 4) | | 554,975 |

The linker in three banks has 755 bytes more to copy (9,767), about 45,000 cycles more at 60 a byte; it cannot be measured until it links.

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

**The choice, in the environment file.** `define BBCFS 0` (every BBC environment now says it): names as given, the emulator's directory as before. `define BBCFS 1`: the DFS's names; `lathe/env/bbc-dfs.env` is `bbc.env` so. `define BBCFS 2`: ADFS's names ("ADFS", below).

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

### The `*` commands

`*LATHE OPTIONS expr.lth .` and `*LLINK ...` work as they are: the arguments are the host's, mapped when each file is opened. A shorter BBC form, `*LATHE EXPR` for `*LATHE EXPR.lth .`, would be bank 0 (`module.asm`) adding `.lth` and ` .` to a tail of one word with no `.`: a few dozen bytes of bank 0, which has room; but then the command line would differ from the host's, and the tests replay the host's. Not built.

### Measured for a real disc

From `LATHE_BBC_DFS=1 LATHE_BBC_SELFHOST=1 LATHE_BBC_DFS_REPORT=1 python3 -m unittest test_bbc_dfs` (2026-11-16), the emulator's `dfs: most-open most-writing` and the files left on the disc. A side is 204,800 bytes (80 tracks; 40 tracks: half); a double-sided 80-track disc 409,600.

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

**A fault found and fixed: the developer's forms under `BBCFS 1` could not start.** Their start-up loads the banks through `bbc.open`, which calls `bbcfs.map`, and `bbcfs` was placed in a bank (`WIN 5` in `lathec-bbc.env`, `WIN 1` in `linker-bbc.env`), which is not there before it is loaded: status 255, the bank's file not found. Nothing else `bbc.open` calls is in a bank (`bbcfs.map` calls only its own functions; `bbc` and `rt_bbc` are fixed). Now `bbcfs` is fixed in the developer's forms and in its bank only in the ROM forms, whose banks are always there: each environment defines `ROMFORM` as 0, which `bbcrom.rom_env` changes to 1, and the entries that differ between the forms are conditional: `when ROMFORM place bbcfs WIN 5` is an entry of the ROM form only, `unless ROMFORM code $1900 $519F` of the developer's form only ([`configurations.md`](configurations.md), "The environment file"). (Until 2026-11-17 a special comment did this, which only `bbcrom.rom_env` read.) The compiler's developer form has its own split, `$51A0`, 416 bytes up, and its ROM form keeps `$5000`; the linker keeps `$4000` in both. `test_bbc_dfs.DeveloperForms` (`LATHE_BBC_DFS=1`) has both developer's forms start with `BBCFS 1` from the environments as committed and compile and link hello as the host does.

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
