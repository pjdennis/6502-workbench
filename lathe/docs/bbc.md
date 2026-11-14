# Lathe on a BBC Model B+128

Status (2026-11-14): design, with the measurements it rests on. Nothing here is built yet except the emulator's machine, which is in progress (`emulator/`, `--machine bbcbplus`). This is the first period machine of stage 12 in [`build-plan.md`](build-plan.md).

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

So main RAM has to hold 24,093 bytes of variables, the stubs (1,230 bytes), and every function that must be in RAM. A function must be in RAM if it has a `with` block or is called inside one, because the sideways RAM and the module share the window: while a table is mapped, the module is not there. That is roughly 9 KB of `kernel`, `lex`, `fbuf` and `err`, with the far-call routine and the MOS interface.

**24.1 + 1.2 + about 9 = about 34 KB, against 26.4 KB (PAGE to HIMEM, and the language workspace). It does not fit as the compiler stands**, by about 8 KB.

The symbol table is the piece that decides it: twelve columns, 9,520 bytes, fixed, read directly by most modules. Behind accessor functions in `kernel` it can go to a third sideways slot, which brings main RAM to about 25 KB. The accessors may also make the code smaller, because every access to a column of more than 256 rows now computes a 16-bit address in line (about 13 bytes each).

## Design

**Memory.**

| Where | What |
|---|---|
| Zero page `$00-$8F` | the linker's zero page |
| `$0400-$07FF` | data (`more data`) |
| `$1900-$7BFF` | data, then the resident code and the stubs |
| Module banks | code and constants; the image of the resident code, copied to RAM when the tool starts |
| Sideways slot A | the name heap |
| Sideways slot B | function buffer, labels, string, saved tokens |
| Sideways slot C | the symbol table, if it moves |

**The environment file.** One window, `$8000-$BFDF` (the last 32 bytes of every bank are left for the switching addresses and the read an instruction makes of the byte after it). A bank's value says what it is: bit 7 set is a bank of the module (the low bits its number), otherwise a sideways slot. The far-call module turns a value into the writes and reads that select it.

**Changes to the linker.**

1. A bank can be marked as ROM: it takes code and constants and never variables.
2. A function with a `with` block, and a function called inside one, stays in fixed memory when its module is placed in a bank. Today that is link error 55 or 56, and the whole module has to be fixed. The map lists what was kept.

**The far-call module, `rt_bbc`.** The same interface as `rt_bank` (`call`, `back`, `map`, `unmap`, `start`). Selecting a module bank writes the module's slot to `$F4` and `$FE30` and reads `$BFF0+n`; selecting a sideways slot writes the slot. The module's latch keeps its bank while a sideways slot is in the window, so leaving a `with` block is one write. Both should cost far less than Wendy 2's 182 and 90 cycles; to be measured.

**The MOS interface, `bbc.lth`.** The interface of `host.lth` and `disk.lth` over OSFIND, OSBGET, OSBPUT and OSWRCH. The arguments are the tail of the `*` command.

**The module image.** A host tool packs the bank files of the compiler and of the linker into one image. Every bank begins with the same sideways ROM header and the same few bytes of service code, so the MOS finds a valid ROM whichever bank the latch holds. That code answers only unknown commands and `*HELP`, selects bank 0 and goes on there. Bank 0 knows `*LATHE` and `*LLINK`: it copies the tool's resident code to main RAM and enters it.

**The developer's flow.** `*RUN LOADMOD` reads the image from disk into the RAM module, bank by bank. After that the commands work as from the ROM.

## Order of work

1. The emulator's machine (in progress).
2. Programs all in one on the BBC: `bbc.lth`, the environment file, the board in the test driver, the end-to-end cases.
3. Banked: `rt_bbc`, ROM banks and the kept functions in the linker, the image tool, the header and service code, the loader. The far-call and banked-data cases run on the BBC.
4. The compiler: `expr` split, the placement, the budget measured. The symbol table behind accessors if that is what stands between. The test programs, then the compiler compiling itself.
5. The linker in the same module, at the capacities that fit.

## Open, for the owner

- **File names.** DFS allows seven characters and uses `.` to separate the directory, so `asmblock.lth` cannot exist there. ADFS allows ten. The first version uses names as the emulator's directory takes them. A scheme is needed for real discs, for example `L.EXPR` for source, `O.EXPR` for the object file and `I.EXPR` for the interface, with module names kept to seven characters.
- **How a tool ends.** As a command it uses the language's zero page and the memory from PAGE, so the language that was running (BASIC) cannot be returned to as it was. The tool should end by starting the current language again (OSBYTE 142).
- **Other filing systems and screen modes** move PAGE and HIMEM; the layout is fixed at link time. One build per case, or one build for the smallest case.

## What the emulator cannot show

- That the header and service code live with the real MOS: its scan of the ROMs at reset, and service calls made during interrupts while the tool runs in another bank.
- Timing against real discs. The compiler compiling itself is about 780 million cycles on Wendy 2, six and a half minutes at 2 MHz, before the cost of reading and writing each byte through a real filing system.
- The real module's electrical behaviour. MAME models the SpellMaster carrier, so the eight-bank form (the compiler alone) could be tried there against the real MOS by someone who has the ROMs.
