# Lathe

A high-level language and compiler for the 6502, meant to compile on the machine it targets: the boards in this repository, and period machines such as the BBC Micro, Apple II and Commodore 64.

**Status (2026-11-13): design only.** Nothing is implemented. The documents below are the proposal to review before the first line of the compiler is written.

## In one paragraph

Lathe is a small typed language whose constructs map directly onto 6502 instructions. Variables have fixed addresses, so there are no stack frames; a linker shares that storage between functions that are never active together and gives zero page to the variables that gain most from it. The compiler makes one pass over the source and keeps no syntax tree, so the source can be larger than memory. It is built to be relinked for different machines: all in memory, with its phases in memory banks, or as phases run one after another from disk. It will be written in Lathe and must compile itself to a byte-identical binary.

## Documents

Read them in this order.

| Document | What it covers |
|---|---|
| [`docs/goals.md`](docs/goals.md) | Goals, targets to measure against, non-goals, the decisions already taken and the questions still open. |
| [`docs/language.md`](docs/language.md) | The proposed language: lexical rules, types, declarations, statements, grammar and examples. |
| [`docs/code-model.md`](docs/code-model.md) | How a compiled program runs: storage, calls, interrupts, recursion, zero page, banking, and the code the compiler should produce. |
| [`docs/architecture.md`](docs/architecture.md) | How the compiler is built: phases, object files, the linker, environment configuration, memory budgets, and the constraints of starting on asm17. |
| [`docs/spikes.md`](docs/spikes.md) | Experiments to run before and during implementation, each with the question it answers and the decision it informs. |
| [`docs/build-plan.md`](docs/build-plan.md) | The incremental build: stages, the test gate for each, and how the tests are organised. |

## Planned layout

Only `docs/` exists today.

```
lathe/
    docs/       these documents
    host/       reference compiler and linker in Python: the test oracle
    src/        the compiler and linker written in Lathe
    rt/         run-time library and environment modules
    env/        environment descriptions (emulator, Michael, Wendy 2, period machines)
    examples/   sample programs
    tests/      unit, snapshot and end-to-end tests
```

## Background in this repository

- [`asm/`](../asm/): asm17, the assembler the first versions of Lathe will emit text for.
- [`prog8/`](../prog8/): the self-hosting Prog8 compiler `p1`. Its notes record the problems Lathe is designed around: the 60 KB window, zero page overflow, and code about 1.6 times the size an optimising compiler produces.
- [`editor/`](../editor/): the editor a compile-from-the-editor workflow would use.
