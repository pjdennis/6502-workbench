# Lathe: incremental build plan

Status (2026-11-14): stages 0 and 1 done. Stage 2 so far: scalars, expressions, control flow, calls, initial values and the embedded assembler (the former stage 10). The linker is done on the host (the storage part of stage 3 and the image part of stage 9), with raw images and environments for Michael and Wendy 2. In progress: arrays, strings and pointers; `for`, `case`, `critical` and `#if`.

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

- **Spike first:** L5 (far calls three ways).
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

- **Object format, next version.** Suggested by the linker work: a fix-up kind meaning "two bytes, and the opcode has a zero page form", so the linker's first pass need not read code to know final sizes; `DFIX` before `DATA`; parameter names in `CLAS`; drop the unused `CLAS` flags.
- **Linker speed on the target.** Zero page promotion lays the program out again after each success (639 layouts for a 34 KB program). Fine on the host; the Lathe version needs an incremental layout.
- **Compiler size, first reading (2026-11-14).** The test programs compile to about 10 bytes of code per source line. The compiler is about 7,000 lines of host Python (roughly 5,000 without comments and blank lines) before arrays, records and the function features, and the linker about 3,200. At that rate the compiler written in Lathe would be 50 KB or more, well over the 32 KB target and too large to run beside its data in 64 KB. Spike L4 will measure this properly on the lexer rewritten in Lathe once arrays and pointers are in; the owner decides then between a larger compiler that depends on banking, a simpler code generator, or denser generated code.
- **Weights across modules.** Uses of an imported variable, and stores into a callee's parameter slots, are not counted in the weight the linker sees.
- **Addresses given with `at`** are in no object record, so the linker cannot check that the environment's ranges avoid them.
- **Spikes L1 and L2** were folded into building the compiler and the linker. Their measurements (code size against `p8c`, promotion rules compared) are still to be recorded in `spikes.md`.
- **vasm** cannot be downloaded in the development container, so only the `lathe` and `asm` suites run there; CI runs the rest.
