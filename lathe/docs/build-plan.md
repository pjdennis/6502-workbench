# Lathe: incremental build plan

Status (2026-11-14): stages 0 to 6 done on the host, with the linker (host side of stages 3 and 9), the embedded assembler (stage 10) and object format version 2. The whole language in `language.md` is implemented, with arguments in registers and the operators calling the run-time library. In progress: the linker written in Lathe (stage 8) and the compiler written in Lathe (stage 7: the middle layers `typetab`, `out`, `fbuf`, `fold`, `reg`, `cond`, and `gen`, the first of the upper layers; the lowest layers are done). Still to come: the compiler's other upper layers in Lathe (`asmblock`, `inline`, `expr`, `decl`, `lathec`) and the self-compilation gate, a measured pass to reduce size, and the banked and chained configurations (stage 11).

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
- **Expect:** Changes to the language. This is the first large program written in it.

### Stage 8. The linker in Lathe

- **Work:** Write the linker in Lathe. The whole tool chain now runs on the target, with no assembler.
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
- **Still to do:** step 9 (banked data, `in REGION` and `with … do`, which waits for the owner), step 10 (the compiler's own placement) and step 11 (the gate).
- **Work:** Regions, windows and `place` in the environment description. Stubs for calls that cross windows. Far-call routines for Wendy 2 banks and for overlays loaded from disk. Banked data regions. The compiler linked all in one, banked and chained.
- **Gate:** The compiler, linked each of the three ways, rebuilds itself identically. In the banked and chained forms no more than 16 KB of compiler code is resident at once.

### Stage 12. A period machine

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

- **Parameter names of function types.** Version 2 of the object format has a name for each parameter in `CLAS`, but the compiler writes them empty: DECL reads a function type's parameter names and drops them, and the interface file has no place for them. To fill them in, DECL keeps the names with the type's members, the interface entry of a function type carries them, and `reg.class_symbol` passes each to `out.class_parameter`. Until then the map names a class's parameters after its first member's, and `lo2asm` writes `pN`.
- **Linker speed on the target.** Zero page promotion judges most items from bounds and lays the program out again only for an item the bounds cannot decide, with the same choices: `lextest` in 64 bytes takes 13 layouts (from 108), the synthetic program in 128 bytes 106 (from 869). Each layout is linear in nodes and calls; at 1 MHz the synthetic program's 106 are still most of a minute ([`architecture.md`](architecture.md), "Memory in the linker").
- **Memory for tables (measured 2026-11-14): the main obstacle to self-hosting.** Laid out as Lathe would lay them out, the host linker's tables took 204 KB at their capacities and the compiler's 72 KB, beside about 55 KB of compiler code. Neither fits a 64 KB machine. State now:
  - *Linker:* 53 KB at capacities that can link the compiler (about 800 functions), against a budget of 24 KB that cannot be met while every table of storage allocation is held at once ([`architecture.md`](architecture.md), "Memory in the linker", "Why not 24 KB, or 30"). Names are kept only where two files name them, and a symbol is a reference, not a table row. With about 12 KB of code the linker fits a 64 KB machine for a program of the compiler's size only if its tables or its code go in a bank.
  - *Compiler:* 42 KB, against a budget of 20 KB that is not met (`lathe/tests/test_memory.py` keeps it as an expected failure and fails if the total grows). The function buffer keeps no code array, and an import costs a symbol only for what the module names. What is left is the text of names, a module's own and its imports'. At these capacities every module written so far compiles, but `gen`, `expr` and `decl` would need about 48 KB, and the test programs of the Lathe twins nearly fill the emulator's 60 KB. The ways on are listed in [`architecture.md`](architecture.md), "What stays in memory": import only what is named, fewer exports, one shared heap, symbols as rows, messages on disk.
- **Compiler size (spike L4, revised 2026-11-14).** See [`spikes.md`](spikes.md), "L4 revised". With ten of sixteen modules written in Lathe, the projection is 55 to 61 KB of code for the compiler, against a target of 32 KB. The owner's decision is needed on how to close the gap: banks, a compact code form for the parts that need not be fast, or a smaller compiler. Spike L5 measured the bank option: 13.9 KB resident and about 6 far calls a source line on Wendy 2 ([`configurations.md`](configurations.md)). It also showed that chaining phases inside the compiler does not help, so a machine without banks needs one of the other two.
- **Gaps found by the board modules:** no 65C02 instructions in `asm` (`TSB`, `TRB`, `STZ`, `PHX`, `PHY`, `BRA`, `STP`) and no way to write a byte in a block, so `STP` is a jump to a one-byte constant; a module's constant tables are always linked, used or not.
- **`#if NAME` and a module of the same name.** After `import disk`, `#if DISK` names the module, because names fold case, and the compiler reports error 36 (`"." expected`). An environment name must differ from every imported module's name until the compiler looks up `#if` names among the defines only.
- **Found by the disk and far-call modules:** `#if NAME` with `NAME` not defined is error 40, so every environment must define every name a module tests; a module imported only inside an untaken `#if` branch is still compiled and its `$init` and variables linked; a name that differs from a type or constant only by case gives an error far from the cause (a variable `head` hides the type `Head`).
- **Found by the arithmetic library:** the linker keeps a module variable nothing uses; uses inside an `asm` loop get no loop weight; an `asm` block cannot name another function's parameter slots.
- **Recursion depth.** The software stack for saved frames is 256 bytes, and each level also uses two bytes of the 6502's own stack, so about 120 levels is the limit whatever the frame size.
- **Addresses given with `at`** are in no object record, so the linker cannot check that the environment's ranges avoid them.
- **Spikes L1 and L2** were folded into building the compiler and the linker. Their measurements (code size against `p8c`, promotion rules compared) are still to be recorded in `spikes.md`.
- **vasm** cannot be downloaded in the development container, so only the `lathe` and `asm` suites run there; CI runs the rest.
