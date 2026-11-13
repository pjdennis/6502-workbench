# Lathe: goals, decisions and open questions

Status (2026-11-13): proposal. Targets marked *(to measure)* are estimates until the spikes in [`spikes.md`](spikes.md) confirm or replace them.

## Goals

**The language**

1. **No hidden costs.** The programmer can predict the code from the source. Bytes stay bytes: there is no implicit promotion to 16 bits. The only operators that call the run-time library are listed in [`language.md`](language.md).
2. **Static storage by default.** Parameters and locals have fixed addresses. Recursion is available only where a function asks for it.
3. **Good at writing compilers.** Records, pointers to records, tables indexed by a byte, strings, enumerations and file I/O are core features, because the compiler is written in Lathe.
4. **Works with interrupt code.** Interrupt handlers are a kind of function. They need no save and restore of zero page, and add no cost to ordinary calls.
5. **Assembly when needed.** Inline assembly can name Lathe variables directly. Routines at fixed addresses, with arguments in registers, can be declared and called without wrappers.
6. **Explicit inlining.** A function marked `inline` is expanded at each call.
7. **Typeable on period machines.** Keywords and names are not case sensitive, and the syntax avoids characters that period keyboards lack where it can (see the open questions).

**The compiled program**

8. **Efficient code.** Close to hand-written assembly in size and speed, without an optimiser.
9. **Effective, automatic use of zero page.** The linker decides what goes in zero page, sharing it between functions that are never active together. The programmer can override it.
10. **ROMable output.** Code and constants are separate from variables. No self-modifying code.
11. **Banking and overlays.** Code can be placed in memory banks or loaded from disk on demand, chosen when linking, with no change to the source.
12. **Pay for what you use.** Only the functions a program reaches are linked, the run-time library included.

**The compiler**

13. **Efficient compilation.** One pass over the source and no syntax tree. On disk machines the measure is the number of passes over the disk.
14. **Source larger than memory.** Source is read as a stream. Programs are split into modules compiled separately.
15. **Small.** At most 16 KB of compiler code resident at once, and about 32 KB in total *(to measure)*.
16. **Configurable for the environment.** Zero page ranges, memory regions, banks, output format and CPU variant come from an environment description. The compiler itself can be linked as one program, with its phases in banks, or as phases chained from disk.
17. **Self-hosting.** The compiler is written in Lathe and compiles itself on the target to a byte-identical binary.
18. **Direct object code.** The first versions emit asm17 text. The planned end state emits object code with no assembler pass, with an embedded assembler for inline assembly.
19. **A host reference compiler.** A Python implementation produces byte-identical output and serves as the test oracle.
20. **Usable diagnostics.** Stop at the first error with file, line and column. The linker writes a map file, and a run-time address can be traced back to a source line.

## Targets to measure against

| Target | Value | Basis |
|---|---|---|
| Code size against hand-written assembly | at most 1.5 times on a set of benchmark routines *(to measure)* | Action! ran the sieve in 1.8 times the time of assembly with no optimiser |
| Code size against `p8c` on equivalent source | at most 0.65 times *(to measure)* | `prog8/CODEGEN_SIZE_COMPARISON.md`: an optimising compiler reaches 0.62 |
| Compiler code resident at once | at most 16 KB *(to measure)* | Action! fitted editor, compiler and monitor in 16 KB of assembly |
| Passes over the disk | source read once, object written once, objects read twice by the linker | — |
| Self-hosting | byte-identical output from the host and target compilers | as the asm and Prog8 chains |
| Smallest zero page that still works | 16 bytes *(to measure)* | a Commodore 64 with BASIC in place has very little free |

## Non-goals

- Floating point.
- Heap allocation and garbage collection in the language. A program can write its own allocator.
- Compatibility with C, Pascal or Prog8.
- Optimisation beyond what one pass and the call graph give: no common subexpression elimination, no loop transformations, no register allocation across statements.
- Transparent access to banked data. Banked data is explicit.
- 32-bit integers in the first version. The name `long` is reserved.
- Self-modifying code.

## Decisions taken

| # | Decision | Reason |
|---|---|---|
| D1 | The name is Lathe. | Workbench tool; five letters fits period file systems. |
| D2 | Recursion is opt-in per function. | Static storage is what makes code small and calls cheap. Turbo Pascal 3 on CP/M worked this way. |
| D3 | A linker owns storage allocation. | Sharing storage needs the whole call graph, which a one-pass compiler never sees. |
| D4 | Emit asm17 text first, direct object code later. | asm17 exists, and inline assembly is then free. The code generator is built so the change is a new output stage, not a rewrite. |
| D5 | The embedded assembler is part of the language. | It can refer to variables by name and lets the compiler add any entry and exit code a block needs. |
| D6 | One compiler source, several link configurations. | All in memory, banked phases or chained phases are choices of placement, not different compilers. |
| D7 | Explicit `inline` functions. | An efficiency tool that costs little in a one-pass compiler: the saved tokens are replayed. |
| D8 | One pass, no syntax tree, operands described lazily. | The technique of Wirth's one-pass compilers: small, fast, and good enough code without an optimiser. |
| D9 | Arrays of records are stored by column. | An indexed access needs no multiply. `p1` already does this by hand with parallel arrays. |
| D10 | Banking and disk overlays use one mechanism. | Both fill a window of memory before a call; only the run-time routine differs. |

## What the prior art taught

- **Action!** showed that fixed-address locals and constructs that match the 6502 give good code with no optimiser, and that a fixed kernel plus switched blocks fits a compiler in 16 KB. It had no linker, no recursion at all, and its run-time library stayed in the cartridge.
- **PLASMA** showed one module format serving static linking and loading on demand, and a host compiler kept beside the self-hosted one. Its two types are too few, and interpreted bytecode is slow.
- **Turbo Pascal 3** showed opt-in recursion by saving a function's storage, finding a run-time error by recompiling to an address, chained programs sharing a library, and inline code that names variables. It put the whole run-time library in every program and had no separate compilation.
- **`p1`** (this repository) showed the costs to avoid: a syntax tree that does not fit, every expression spilled through scratch storage, a long branch on every forward condition, and zero page that overflows without a plan.

## Open questions for the owner

These are choices the design has made provisionally. Each can be changed before implementation starts at little cost.

1. **Bootstrap seed.** The plan uses a Python host compiler as oracle and first compiler, as `p8c` was for `p1`. The alternative is a chain from asm17 with no host tool in the line of trust, as the assembler was built. Recommendation: Python first; add a seed chain later only if that line of trust matters.
2. **Case.** Names are not case sensitive, so `Sym` and `sym` are the same name. This is needed for upper-case-only machines. It could be made a per-environment option instead.
3. **Characters outside `$20`–`$5F`.** The operators `|` and `~` cannot be typed on a stock Commodore 64 or Apple II+. The proposal keeps them and leaves alternate spellings open until an editor on one of those machines is a real target.
4. **First period machine.** The emulator, Michael and Wendy 2 come first. Recommendation for the first period port: the BBC Micro, which has full ASCII, 32 or more bytes of free zero page, sideways RAM for banking and a simple file API.
5. **Calling convention details.** Arguments go straight into the callee's storage and results come back in registers. Passing one argument in a register is left as a measured experiment, because `p1`'s notes put the gain at about 0.5%.
