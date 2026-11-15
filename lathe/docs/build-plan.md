# Lathe: incremental build plan

Status (2026-11-15): stages 0 to 6 done on the host, with the linker (host side of stages 3 and 9), the embedded assembler (stage 10) and object format version 4 (interface format version 2). The whole language in `language.md` is implemented, with arguments in registers and the operators calling the run-time library, and with optional import lists (`import m (a, b)`), which brought the compiler's name heap from 18,944 to 9,216 bytes. The linker places code in banks and overlays, and data in banked regions (stage 11, steps 1 to 9 of [`configurations.md`](configurations.md); the form of banked data, `in REGION` and `with REGION do`, is provisional). The compiler written in Lathe is done (stage 7: sixteen modules, `inline`'s twin being `inlines.lth` because `inline` is a keyword; 72.7 KB of code): banked on Wendy 2 with its big tables in data banks at full size, `lathec.lth` compiles its own sixteen modules and `sys` to object and interface files byte-identical to the host compiler's (`test_src_selfhost.py`), and compiles the whole corpus as the host does (`test_src_lathec.py`), with 14,588 bytes of code and stubs resident (stage 11, steps 10 and 11). Not done, and waiting for the owner: the linker written in Lathe (stage 8: all nineteen modules are written and tested against the host modules, and the whole linker, 45.4 KB of code, runs banked on emulated Wendy 2 with files and links every program of the end-to-end corpus, byte for byte as the host linker does, at the capacities of its small build, about a third of the compiler; it cannot link the compiler, whose tables do not fit beside the code that reads them: [`spikes.md`](spikes.md), "The whole linker in Lathe, banked on Wendy 2, measured"), so the banked compiler that compiles itself is linked by the host linker; and the two other forms of stage 11's gate, which cannot be met as written: all in one the compiler does not fit 64 KB (72.7 KB of code and 51 KB of tables), and chained means the compiler and the linker as separate programs, which they are. Stage 12's gate is met on the first period machine (2026-11-15): in the ROM module of an emulated BBC Model B+128, started by `*LATHE`, the compiler compiles its own modules byte-identically to the host, in 7.8 minutes at 2 MHz, with 1.7 KB of main RAM to spare ([`bbc.md`](bbc.md), "Step 4, as built"); what the emulator cannot show (the real MOS's ROM scan and interrupts, real discs) is listed there. The linker is `*LLINK` in the same module image, so a program is compiled, linked and run on the B+128 with every file identical to the host tools' (68 of the 69 corpus programs the BBC runs; "Step 5, as built"); the linker there cannot link the compiler, for the same reason as on Wendy 2: its work area does not fit main RAM. Then a measured pass to reduce size.

**Order of work, changed after spike S2.** asm17 runs out of symbol memory at about 15 to 20 KB of compiler-shaped code, so it cannot assemble the Lathe-written compiler on the target. The stages keep their numbers but run in this order: 0 to 6, then 9 and 10 on the host, then 7, 8 and 11. The compiler written in Lathe then emits object code from its first day, and the on-target tool chain is the compiler and the linker with no assembler. On the host, large programs in stage A are assembled with `asm/pyasm.py`, the Python work-alike of asm17, which has no such limit.

## Principles

- **Always have something that runs.** Stage 1 compiles and runs a one-line program end to end. Every later stage widens what works; none is a rewrite.
- **Host first, then target.** Each feature is built in the Python reference compiler, then written in Lathe. The host version is the oracle for the target version.
- **The same structure in both.** The Python follows the component boundaries and one-pass order of [`architecture.md`](architecture.md), so the Lathe version is a transliteration.
- **Spikes before commitments.** Each larger spike in [`spikes.md`](spikes.md) runs before the stage that depends on its answer.
- **Every stage ends at a gate**: a test that passes only if the stage is done.

## Working method

Each change follows refactor, green, red, green, refactor, green:

1. Refactor to make room for the change. Tests stay green.
2. Write a test for the new behaviour and see it fail.
3. Make it pass.
4. Refactor. Tests stay green.

## Tests

| Kind | What it checks | Form |
|---|---|---|
| Unit | One component of the host compiler: lexer, operand descriptions, allocator rules. | Python tests. |
| Snapshot | Source in, assembler text out. Reviewed by hand when first recorded and whenever it changes. | `.lth` beside `.expected.asm`. |
| Error | Source in, expected error number, line and column out. | `.lth` with the expectation in a comment. |
| End to end | Compile, assemble, run on the emulator, compare output. | `.lth` beside `.expected.out`. |
| Identity | Host and target compilers give the same bytes; stage A and stage B give the same bytes. | Script comparing files. |
| Size | Code size of benchmark routines and of the compiler, kept in a table in the repository. A change in either direction shows in review. | Generated table, compared in the test. |

The suite joins `tools/check_all.sh` as `lathe` when stage 1 lands, and CI with it.

## Stages

### Stage 0. Small spikes

- **Work:** Run S1 to S7. Write the results into the design documents and settle the open questions in [`goals.md`](goals.md).
- **Gate:** The documents are revised and the owner agrees the language and code model.

### Stage 1. Walking skeleton

- **Work:** The host compiler with every component present and almost empty. It compiles a module with one `extern` declaration and a `main` that calls it with a constant. Output is asm17 text, assembled and run on the emulator's default machine. All six kinds of test exist with one case each.
- **Gate:** A program that prints one character runs end to end under `tools/check_all.sh lathe`.

### Stage 2. Core language

- **Spike first:** L1 (code generator).
- **Work:** `byte`, `word`, `bool` and the signed types. Constants and constant folding. Expressions with lazy operands, destination passing and register tracking. Assignment and compound assignment. `if`, `while`, `loop`, `for`, `break`, `continue`. Functions with parameters and results. Byte arrays, strings, `^byte` and indexing. The function buffer with short-first branches. Inline `asm` blocks, copied through. Storage is allocated naively: every slot gets its own address.
- **Gate:** The benchmark routines from S3 compile and run, and meet the code size target against the hand-written originals.

### Stage 3. Allocator

- **Spike first:** L2 (storage allocation).
- **Work:** The compiler writes frame and call records. A host allocator builds the call graph, shares frames, chooses zero page and writes the allocation file and a map file. Errors for cycles and for zero page that does not fit.
- **Gate:** A test program's storage equals its deepest call chain, and the same program links with zero page budgets of 16 and 224 bytes with different results that both run correctly.

### Stage 4. Data structures and modules

- **Work:** Records, enumerations, named types, pointers to records. Column-stored and `rows` arrays. `case`. `static`, `at`, `zp`, `nozp`, initialised data and constant tables. Modules: `import`, `pub`, interface files, name prefixes, a build driver that compiles modules in order. `#if` and environment constants.
- **Gate:** The symbol table example from [`language.md`](language.md) and a three-module program compile, link and run.

### Stage 5. Function features

- **Work:** `interrupt` functions and contexts, with copies for shared functions. `critical`. `recursive` with frame save and restore. Function pointers: classes, shared parameter blocks, `recursive` function types, the one-context rule. `inline` with token replay. Status results. `asm` functions and register-bound `extern` declarations in full.
- **Gate:** End-to-end tests for each: a timer interrupt on emulated Michael or Wendy 2; a recursive evaluator; a dispatch table of function pointers; a link error for an unmarked cycle. A function used by both the main program and a handler is reported as an error in stage A, because assembler text cannot hold two copies of one function; the copies arrive with the linker in stage 9.

### Stage 6. Run-time library and environments

- **Work:** Multiply, divide and shift routines, start-up code, and the frame stack, each linked only when used. Environment modules and descriptions for the emulator's default machine, Michael and Wendy 2 (without banking).
- **Gate:** The same example programs run on all three machines in the emulator.

### Stage 7. The compiler in Lathe

Runs after stages 9 and 10.

- **Spikes first:** L4 (compiler size), L6 (recursion), L7 (symbol heap).
- **Work:** Write the compiler in Lathe under `lathe/src/`, component by component in the order kernel, SRC, LEX, DECL, STMT, EXPR, GEN, FBUF, ASM, OUT. It writes object files only; the assembler-text writer stays a host tool. Each component is tested against the host component it mirrors. The host compiler and linker build it.
- **Gate:** The Lathe-written compiler, running on the emulator, compiles itself, and the result is byte-identical to the host compiler's output. The whole snapshot suite passes through it.
- **State (2026-11-14):** all sixteen modules written and each tested against its host module; `lathec.lth` links them into the compiler, 72.7 KB of code ([`spikes.md`](spikes.md), "L4 revised"), which runs banked on emulated Wendy 2 with files ([`configurations.md`](configurations.md), "The compiler itself, banked") and gives the host compiler's object files, interfaces, errors and status byte for byte on every input `lathe/tests/test_src_lathec.py` gives it: 681, among them 55 of the 56 snapshot cases. It runs with the small build's tables (a name heap of 1,536 bytes), because every table is in fixed memory, so of its own sixteen modules none fits: each stops at the name heap (error 70), and does so as the host compiler at those capacities does. What is left for the gate: the name heap, the function buffer and the error messages in the data bank (stage 11, step 10), then the tables at full size (`expr.lth` needs 17,875 bytes of names and 539 symbols), and a test that compiles the sixteen twins on the emulator.
- **Expect:** Changes to the language. This is the first large program written in it.

### Stage 8. The linker in Lathe

- **Work:** Write the linker in Lathe. The whole tool chain now runs on the target, with no assembler.
- **Done (2026-11-14):** the ten lower layers (`lk_err`, `lk_op`, `lk_file`, `lk_rec`, `lk_sym`, `lk_envf`, `lk_tab`, `lk_name`, `lk_scan`, `lk_out`), 17.8 KB of code, through `lathe/src/lktest1.lth` and `lktest2.lth` against the host modules (`lathe/tests/test_src_lk.py`), at the capacities of a small build (`LKSMALL`, `lathe/src/linker.env`) that fits the emulator's default machine; then the call graph, the stubs, the start-up code and storage (`lk_graph`, `lk_win`, `lk_boot`, `lk_alloc`), 16.4 KB, through `lktest3.lth` and `lktest4.lth`, with the small build cut to two fifths of the full capacities so that storage fits beside them.
- **Done (2026-11-14):** the last five, `lk_fix`, `lk_place`, `lk_map`, `lk_emit` and `link` (9.7 KB), and the whole linker running: `lathe/src/link.lth`, 45.4 KB of code, built with `lathe/src/linker-bank.env` runs on emulated Wendy 2 with `--disk`, fixed code and stubs 9.9 KB, the phases in three banks, the small build's tables (22.2 KB) in fixed memory. `lathe/tests/test_src_link.py` links with it every program of the end-to-end corpus (the default machine, Michael, Wendy 2, the configurations with banks, overlays, regions and interrupts), every link of the linker's tests and links made by hand, good and bad, and `lk_synthetic` at the largest size it takes and one larger: error output, status, image, map and bank files identical to the host linker's. Linking lextest takes 109 million cycles, the synthetic program at 30% of the compiler 242 million; far calls cost about 3% ([`spikes.md`](spikes.md), "The whole linker in Lathe, banked on Wendy 2, measured").
- **Still to do:** the gate. At the capacities that link the compiler the tables take 54 KB, and Wendy 2 has 24 KB of fixed memory beside the resident code; one window means a data bank is seen only by fixed code, so they cannot fit as the linker is built. It needs a second window, the chained configuration, or every access to a large table through a fixed function that maps its bank; and `disk.lth`'s 256 bytes of arguments must grow for the compiler's 30 to 40 object files. Promotion at full size would take about half an hour at 1 MHz.
- **Gate:** Compiler and linker, both running on the emulator, rebuild the compiler and linker byte for byte.

### Stage 9. Object code and the linker

- **Spike first:** L3 (shrinking in the linker).
Runs after stage 6, on the host only.

- **Work:** The object file format. A second OUT component that writes object records. The linker's two passes, growing out of the allocator: placement, fix-ups, shrinking, removal of unused functions, one copy of a function per context, image output.
- **Gate:** For every test program, the linker's image is byte-identical to the assembler's. Programs with no inline assembly no longer need an assembler. A function shared by the main program and an interrupt handler links and runs.

### Stage 10. Embedded assembler

Runs after stage 9, on the host only.

- **Work:** The ASM component assembles inline blocks and `asm` functions into object records, with Lathe names resolved by the compiler.
- **Gate:** No assembler is needed to build anything in `lathe/`. Identity with stage A still holds for the whole suite.

### Stage 11. Configurations

- **Spike first:** L5 (done): [`spikes.md`](spikes.md), "Result of L5".
- **Design and order of work:** [`configurations.md`](configurations.md), eleven steps, each ending in a test. The banked configuration now comes before the gate of stage 7, because the Lathe-written compiler does not fit 64 KB all in one.
- **Done (2026-11-14), steps 1 to 8:** files on Wendy 2 (`lathe/rt/disk.lth`); the far-call run-time modules `rt_bank` and `rt_ovl`; environment version 2 (`window`, `switch`, `bank`, `overlay`, `place`, `more`, `farcall`, and `region` read but not yet used); placement of a module's code in a bank or overlay, with sizes judged before shrinking, a file per bank and the map's `b=`, `W` and `T` lines; stubs, `@f` as the stub, `$banks` and `$overlays`; the interrupt rules; constants and variables of a module in its bank. The same objects link all in one, banked on Wendy 2 and in overlays on the default machine (`lathe/tests/cases/e2e-config/`, `test_farcall.py`, `test_lk_windows.py`).
- **Done (2026-11-14), code half of step 10:** the test programs of `outtest`, `regtest`, `condtest` and `gentest` run banked on Wendy 2 (`lathe/src/compiler-bank.env`, placement E, small tables) and match the Python section by section (`test_src_banked.py`); measured in [`configurations.md`](configurations.md), "Measured on the compiler's test programs".
- **Done (2026-11-14), step 9:** banked data. `in REGION` on variables and constant tables, `with REGION do … end` (provisional, awaiting the owner's agreement), object format version 3 (`RGN`, fix-up kind 6, `CALL` flag bit 2), interfaces that carry `in REGION`, the linker's region placement and checks (link errors 54 to 59), `rt_bank.map` and `unmap`, `lathe/rt/rt_with.lth` for links all in one ([`configurations.md`](configurations.md), "As built: banked data"; `test_banked_data.py`, `test_lk_windows.py`, `e2e-config/regions.lth` and `withirq.lth`).
- **Done (2026-11-14), step 10:** the compiler's big tables in data banks (`in` regions used inside `with` blocks of fixed functions: the name heap in bank 4; err's messages, the function buffer and its labels, LEX's string and INLINE's saved tokens in bank 6), so that the banked build has the full capacities (`compiler-bank.env`, `SMALL 0`); the test programs pass banked at full size, the resident code and stubs of the compiler are 14,588 bytes ([`configurations.md`](configurations.md), "Step 10: the tables in data banks, and the compiler compiling itself").
- **Done (2026-11-14), step 11, the gate of stage 7:** the Lathe-written compiler, banked on Wendy 2 at full capacities, compiles its own sixteen modules and `sys` to object and interface files byte-identical to the host compiler's, in 782 million cycles (`test_src_selfhost.py`, all with `LATHE_SELFHOST=1`), and all 687 inputs of `test_src_lathec.py` at full size (`LATHE_LATHEC_FULL=1`).
- **Done (2026-11-14), after step 11:** the two rough edges of banked data that step 10 found. A `with` block need not use a name of its region: a block that uses none names its bank by the module's first variable or table of the region (error 183 retired; 184 for a region the module declares nothing in), so `kernel.token_byte` reads `p[0]`. Object format version 4: fix-up kinds 7 and 8 for an address formed only to reach an element, which no longer keeps a table out of its module's bank, so `out.table` is in bank 5 and the compiler has 3,744 bytes of fixed memory free, against 1,620 ([`configurations.md`](configurations.md), "out.table in OUT's bank").
- **How the gate stands (2026-11-14):** banked, met: the compiler rebuilds its own object files identically with 14,588 bytes of code and stubs resident (under 16 KB), linked by the host linker, since the Lathe-written linker cannot yet link a program of the compiler's size (stage 8). All in one, cannot be met: the compiler is 72.7 KB of code and 51 KB of tables, more than 64 KB before any table. Chained, nothing further to build: the compiler and the linker are separate programs, and chaining inside a one-pass compiler was dropped after L5 ([`configurations.md`](configurations.md), "The chained configuration"). A machine with no banks needs a smaller compiler or a compact code form, which is the owner's decision.
- **Work:** Regions, windows and `place` in the environment description. Stubs for calls that cross windows. Far-call routines for Wendy 2 banks and for overlays loaded from disk. Banked data regions. The compiler linked all in one, banked and chained.
- **Gate:** The compiler, linked each of the three ways, rebuilds itself identically. In the banked and chained forms no more than 16 KB of compiler code is resident at once.

### Stage 12. A period machine

- **Chosen machine and design (2026-11-14):** a BBC Model B+128, with the compiler and linker in a banked ROM module in one sideways socket and the tables in sideways RAM: [`bbc.md`](bbc.md), with the measurements that say what fits. The emulator has the machine (`--machine bbcbplus`, `emulator/README.md`): the memory map, ROMSEL, sideways RAM, the module in ROM and in RAM form, and the MOS's documented calls implemented by the emulator, with no Acorn ROM and no interrupts.
- **Programs all in one on the BBC (2026-11-14):** step 2 of [`bbc.md`](bbc.md) is done: `lathe/rt/bbc.lth` over the MOS, `lathe/env/bbc.env`, the `bbc` board of the test driver (`*RUN` with `--bbc-strict`); 67 of the 69 end-to-end cases and `lextest`, `errtest`, `kerneltest` and `srctest` in the small build run there and agree with the default machine and the twins.
- **Done (2026-11-14), the linker's part of the BBC design:** read-only banks (`rom WIN N`: no variables, not loaded at start-up) and functions kept in fixed memory when their module is placed, those with a `with` block and all that runs inside one (link errors 55 and 56 retired, 60 new); with kernel, lex, fbuf, err and src placed as well, the compiler needs 11.8 KB of code in fixed memory, 8.9 KB of it kept ([`configurations.md`](configurations.md), "Functions kept in fixed memory, and read-only banks").
- **Banked programs on the BBC (2026-11-15):** the first half of step 3 of [`bbc.md`](bbc.md): `lathe/rt/rt_bbc.lth` with code in banks of the module (its developer's form, RAM) and regions in sideways RAM; the far-call and banked-data cases, sixteen banks, and `outtest`, `regtest`, `condtest` and `gentest` banked in the small build run there and agree with Wendy 2 and the twins. A far call costs 186 cycles, a `with` block 64 to 78.
- **The ROM module on the BBC (2026-11-15):** the second half of step 3 of [`bbc.md`](bbc.md): `lathe/host/driver/bbcrom.py` puts programs linked on their own with read-only banks into one 256 KB image whose every bank carries the header and service code, each program started by a `*` command with its arguments and ending in the language again (OSBYTE 142); `LOADMOD` loads the image into the module's RAM form. Three programs in one image, and `outtest`, `regtest`, `condtest` and `gentest` in the small build, give what they give with `*RUN` and what the twins give; at the full capacities none fits main RAM once its banks hold no variables.
- **Done (2026-11-15), the compiler's tables for the BBC:** kernel's symbol and member columns, OUT's constant table and DECL's import rows are in regions, reached through functions of their modules (`kernel.byte_of()` and the rest), and EXPR's functions that reach no cycle of its calls are a module of their own, `parts`, so that every module fits a bank; with kernel, lex, fbuf, err and src placed, main memory must hold 23,358 bytes (38,406 before) of the 26,111, and the self-compile on Wendy 2 takes 7.7 % more cycles ([`configurations.md`](configurations.md), "The symbol table in a region").
- **The compiler compiles itself on the BBC (2026-11-15):** step 4 of [`bbc.md`](bbc.md): the Lathe-written compiler at full capacities (`lathe/src/lathec-bbc.env`: five banks of the module, its tables in the four sideways RAM slots, 1.7 KB of main RAM left) compiles its own modules and `sys` on the B+128 to the host compiler's files, started by `*LATHE` from the ROM image, from the RAM module through `LOADMOD`, and by `*RUN` (`test_bbc_selfhost.py`); 933 million cycles, 7.8 minutes at 2 MHz (Wendy 2: 838 million), 654,341 bytes read and 398,290 written; 705 of the corpus's 708 inputs give the host's output there, the other three need directories or a longer command line. On the way, seven of EXPR's functions moved to `parts`, `sys` lost a table that relied on memory being 0, and the emulator takes a leading `./` and counts the file traffic.
- **The whole tool chain on the BBC (2026-11-15):** step 5 of [`bbc.md`](bbc.md): the Lathe-written linker is `*LLINK` in the same module image as the compiler (banks 6 to 10; `lathe/src/linker-bbc.env`, the BBC's capacities `LKSMALL 2`, its tables that only `lk_tab` and `lk_name` read in sideways slot 0 behind their functions), so a program's modules are compiled there by `*LATHE`, linked there by `*LLINK` and run there by `*RUN`, with every file identical to the host tools' (`test_bbc_toolchain.py`): 68 of the corpus's 69 programs the BBC runs, three of them banked, and `outtest` of the compiler's test programs; `for_ranges` and `regtest` need more of the work area than main RAM has, and linking the compiler there would need the work area out of main RAM, a redesign. A link takes 0.05 to 0.3 minutes at 2 MHz for the corpus, 2.35 for `outtest`. On the way: rows of five of the linker's tables were read before they were set, which memory that is not 0 showed (`test_lk_unset.py`), and the function limit went from 800 to 896, the compiler filling 799.
- **Spike first:** L8 (disk traffic).
- **Work:** An environment module and description for the first period machine, with its file interface and output format. A way to test it, which the emulator here does not yet provide.
- **Gate:** The compiler runs on that machine and compiles a program there.

### Later, in no fixed order

- Compile from the editor, with the cursor placed at the first error.
- Finding a run-time address by recompiling.
- Further period machines.
- 32-bit `long`.
- A seed chain from asm17, if a line of trust with no host tool is wanted.

## What can run in parallel

- Stage 6 can proceed alongside stages 4 and 5.
- The host linker of stage 9 can start any time after stage 3, since it extends the allocator.
- The linker in Lathe (stage 8) can be written alongside the compiler in Lathe (stage 7).
- Environment descriptions for period machines can be drafted from stage 4 on, to test that the format is general enough.

## Checkpoints for the owner

Points where a decision is needed before work continues.

| After | Decision |
|---|---|
| Stage 0 | Agree the language, the code model and the open questions. |
| L1 | Accept the code size reached, or change the code model. |
| Stage 5 | Freeze the language for the self-hosting work, apart from what that work itself shows. |
| L4 | Accept the compiler's projected size, or cut features, or plan the front-end split. |
| L3 | Automatic zero page in stage B, or classes fixed at compile time. |
| Stage 10 | Choose the first period machine. |

## Open items

Things found during the work that are not part of a stage's gate. Remove each when done.

- **What a variable with no initial value holds** is not said in [`language.md`](language.md), and nothing clears memory at start-up. Two faults came from it on the BBC, where memory is not 0 when a program starts (`sys.files`, and rows of five linker tables), and corpus programs rely on 0 (`calls`): `test_bbc_toolchain.py` clears memory before it runs them. To decide: undefined, with the tests run in memory that is not 0 on every machine, or cleared by the start-up code. The item below waits for it.
- **`sys.files` on Wendy 2 and the default machine** (`lathe/src/sys.lth`, `PORTS` 0 and 1): the table of open files is read before anything sets it, so a program started in memory that is not zero can open no file. The emulators start with zeroed memory, which hides it; the BBC's choice keeps no table. Found by the BBC's loader form (2026-11-15).
- **Parameter names of function types.** Version 2 of the object format has a name for each parameter in `CLAS`, but the compiler writes them empty: DECL reads a function type's parameter names and drops them, and the interface file has no place for them. To fill them in, DECL keeps the names with the type's members, the interface entry of a function type carries them, and `reg.class_symbol` passes each to `out.class_parameter`. Until then the map names a class's parameters after its first member's, and `lo2asm` writes `pN`.
- **Linker speed on the target.** Zero page promotion judges most items from bounds and lays the program out again only for an item the bounds cannot decide, with the same choices: `lextest` in 64 bytes takes 13 layouts (from 108), the synthetic program in 128 bytes 106 (from 869). Each layout is linear in nodes and calls; at 1 MHz the synthetic program's 106 are still most of a minute ([`architecture.md`](architecture.md), "Memory in the linker").
- **Memory for tables (measured 2026-11-14): the main obstacle to self-hosting.** Laid out as Lathe would lay them out, the host linker's tables took 204 KB at their capacities and the compiler's 72 KB, beside about 55 KB of compiler code. Neither fits a 64 KB machine. State now:
  - *Linker:* 53 KB at capacities that can link the compiler (about 800 functions), against a budget of 24 KB that cannot be met while every table of storage allocation is held at once ([`architecture.md`](architecture.md), "Memory in the linker", "Why not 24 KB, or 30"). Names are kept only where two files name them, and a symbol is a reference, not a table row. With about 12 KB of code the linker fits a 64 KB machine for a program of the compiler's size only if its tables or its code go in a bank.
  - *Compiler:* 42 KB, against a budget of 20 KB that is not met (`lathe/tests/test_memory.py` keeps it as an expected failure and fails if the total grows). The function buffer keeps no code array, and an import costs a symbol only for what the module names. What is left is the text of names, a module's own and its imports'. At these capacities every module written so far compiles, but `gen`, `expr` and `decl` would need about 48 KB, and the test programs of the Lathe twins nearly fill the emulator's 60 KB. The ways on are listed in [`architecture.md`](architecture.md), "What stays in memory": import only what is named, fewer exports, one shared heap, symbols as rows, messages on disk.
- **Import lists (2026-11-14).** `import m (a, b)` reads only what is listed and what listed inline functions name ([`language.md`](language.md), "Import lists"); the twins, their test programs, the linker's twins and the run-time modules have the lists `lathe/tests/import_lists.py` writes (`test_import_lists.py` keeps them so), and the name heap went from 18,944 to 9,216 bytes ([`architecture.md`](architecture.md), "What stays in memory"). Open: the lists add 38 KB of source, and a module whose names an import list could keep smaller still (`err`'s error numbers) is the next candidate.
- **Compiler size (spike L4, revised 2026-11-14).** See [`spikes.md`](spikes.md), "L4 revised". With ten of sixteen modules written in Lathe, the projection was 55 to 61 KB of code for the compiler, against a target of 32 KB; with all sixteen it measures 72.7 KB. The owner's decision is needed on how to close the gap: banks, a compact code form for the parts that need not be fast, or a smaller compiler. Spike L5 measured the bank option: 13.9 KB resident and about 6 far calls a source line on Wendy 2 ([`configurations.md`](configurations.md)). It also showed that chaining phases inside the compiler does not help, so a machine without banks needs one of the other two.
- **Gaps found by the board modules:** no 65C02 instructions in `asm` (`TSB`, `TRB`, `STZ`, `PHX`, `PHY`, `BRA`, `STP`) and no way to write a byte in a block, so `STP` is a jump to a one-byte constant; a module's constant tables are always linked, used or not.
- **`#if NAME` and a module of the same name.** After `import disk`, `#if DISK` names the module, because names fold case, and the compiler reports error 36 (`"." expected`). An environment name must differ from every imported module's name until the compiler looks up `#if` names among the defines only.
- **Found by the disk and far-call modules:** `#if NAME` with `NAME` not defined is error 40, so every environment must define every name a module tests; a module imported only inside an untaken `#if` branch is still compiled and its `$init` and variables linked; a name that differs from a type or constant only by case gives an error far from the cause (a variable `head` hides the type `Head`).
- **Found by the first large banked link** (the test programs on Wendy 2, [`configurations.md`](configurations.md), "Measured on the compiler's test programs"): placement D does not fit, because the linker judges a bank as written, before shrinking, and gen, reg, out and cond judge 30,109 bytes against 25,795 placed; the test programs use E (cond in bank 3). `place` of a module not linked is error 44, so a program that links part of the compiler needs its own environment (`src_support.banked_env` writes one). `sys` now links `disk`'s `$init` and four bytes of its variables (one in zero page) on the default machine too, because a module imported in an untaken `#if` branch is linked (the item above). Fixed memory beside the small tables has 4 KB left in gentest, before `lex` and `src` (2.5 KB) join it.
- **Found by the arithmetic library:** the linker keeps a module variable nothing uses; uses inside an `asm` loop get no loop weight; an `asm` block cannot name another function's parameter slots.
- **Found by banked data (step 9):** A program whose only use of the far-call module is a data bank keeps `call` and `back` (about 100 bytes), because `lk_graph` roots them whenever `lk_envf.placed()`. A define named `with` (or any keyword) is now refused by the compiler: `-dWITH` is error 41.
- **Step 10 (done) needed:** `kernel.names`, `fbuf.buffer` and `label_offset`/`label_uses`, and `err`'s messages declared `in` regions and every use of them inside `with` blocks of fixed functions (`kernel`, `fbuf` and `err` are fixed in placement D), `lex.name_or_keyword` mapping around a whole name; the twins compiled with `in`/`with`, which the Lathe compiler (`expr.lth`, `decl.lth`) cannot yet parse, and the rename in `lk_name.lth`; a `region` for each in `compiler-bank.env`; an error message read from a region by `err.fatal`, which must map and unmap around its loop (its callers may be in banks: fine, `err` is fixed). Not there yet: a check that a pointer into a region does not leave its block, and an inline accessor cannot contain the block (see the item above), so each accessor is a call.
- **Found by step 10:** a region read from an interface and an exported variable of the same spelling were two name entries once the variable was thawed, so a second `with` block of that region was error 118 (fixed: regions are compared by spelling, `reg.same_region()`). A table of more than 256 bytes indexed by a `word` stays in fixed memory even when only its bank's code names it, because the index takes its address (fix-up kinds 2 and 3, which the linker's rule counts as an address taken): `out.table` could not follow OUT into its bank. A `with` block must name its region's variable even when it reaches the region through a pointer (error 183). A variable that fits neither the data range nor `more` is an error even when moving a smaller one would make room: `out.table` (2,048 bytes) does not fit `$F810-$FFF9` (2,026).
- **Recursion depth.** The software stack for saved frames is 256 bytes, and each level also uses two bytes of the 6502's own stack, so about 120 levels is the limit whatever the frame size.
- **Addresses given with `at`** are in no object record, so the linker cannot check that the environment's ranges avoid them.
- **Spikes L1 and L2** were folded into building the compiler and the linker. Their measurements (code size against `p8c`, promotion rules compared) are still to be recorded in `spikes.md`.
- **vasm** cannot be downloaded in the development container, so only the `lathe` and `asm` suites run there; CI runs the rest.
