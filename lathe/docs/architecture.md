# Lathe: compiler architecture

Status (2026-11-13): proposal. Sizes are estimates until measured ([`spikes.md`](spikes.md)). The run-time model this architecture serves is in [`code-model.md`](code-model.md).

## Two stages of output

**Revised after spike S2 (2026-11-13).** The compiler always writes object files, from stage 1 on, and assembles inline assembly itself. "Stage A" is now a host-side path: the tool `lo2asm` renders object files and the linker's map as asm17 text, and an assembler turns that into an image. It gives readable output for the snapshot tests and an independent check on the linker, whose own image must be byte-identical. The format is in [`object-format.md`](object-format.md). The two diagrams below show the original plan, in which the compiler itself wrote text; the components, the linker and the constraints that follow are unchanged except that OUT has one form, there is no `.lfm` file, and ASM is the embedded assembler from the start.

The compiler was to be built twice over, on purpose (decision D4 in [`goals.md`](goals.md)).

**Stage A: assembler text.** The compiler writes asm17 source. asm17 does the work of an assembler and of the final link step.

```
module.lth ──► compiler ──► module.asm        code as asm17 text
                       ├──► module.lfm        frames, call graph, weights
                       └──► module.li         interface for importers

all .lfm ────► allocator ─► alloc.asm         name = address for every slot and variable

alloc.asm + all module.asm + run-time ──► asm17 ──► program image
```

**Stage B: object code.** The compiler writes object files and a linker replaces both the allocator and asm17.

```
module.lth ──► compiler ──► module.lo         code, fix-ups, frames, call graph
                       └──► module.li

all .lo ─────► linker pass 1 ─► allocation and placement (in memory)
all .lo ─────► linker pass 2 ─► program image, map file
```

The front of the compiler is the same in both stages. Only the last component, which turns a finished function into output, differs. Stage B is checked against stage A: both must produce the same bytes for every test program, the compiler included.

## Components

```
              ┌────────────────────────── kernel ───────────────────────────┐
              │ streams · symbol heap · names · errors · configuration      │
              └─────────────────────────────────────────────────────────────┘
 source ─► SRC ─► LEX ─► DECL ─┐
                          STMT ─┼─► EXPR ─► GEN ─► FBUF ─► OUT ─► text or object
                                │
                               ASM (inline assembly)
```

| Component | Job |
|---|---|
| **Kernel** | Services every phase needs: byte streams, the symbol heap, name hashing, error reporting, the environment constants. |
| **SRC** | A stack of sources: the file being read, an imported interface, the saved tokens of an `inline` function being replayed. asm17's source stack is the model. |
| **LEX** | Characters to tokens. Case folding, line continuation, `#if` skipping. |
| **DECL** | Declarations: constants, types, variables, function headers, imports. Writes the interface file. |
| **STMT** | Statements and control flow. |
| **EXPR** | Expressions, using lazy operand descriptions. |
| **GEN** | Chooses instructions for an operation on described operands. Tracks register contents. |
| **FBUF** | Holds the current function as a list of instructions with symbolic operands. Fixes branch lengths when the function ends. |
| **OUT** | Writes a finished function: as text and frame records in stage A, as an object record in stage B. |
| **ASM** | Inline assembly. In stage A it copies the lines, replacing Lathe names. In stage B it is the embedded assembler. |

Two rules keep this configurable:

- **Phases talk through streams.** A stream is a sequence of bytes read or written in order. It can be backed by a file, by a memory buffer or by a bank. No phase knows which.
- **Nothing outside the kernel is called across phases.** A phase can then be placed in a bank or loaded from disk without the others noticing.

## What stays in memory

Because there is no syntax tree, memory holds only:

| Item | Lifetime | Estimate |
|---|---|---|
| Symbol heap: module-level names, types, imported interfaces | whole module | 8–16 KB |
| Symbols of the current function | until the function ends, then released | under 1 KB |
| Function buffer | until the function ends | 2–4 KB |
| Saved tokens of `inline` functions | whole module | small (the host compiler keeps 4 KB, `inline.SAVED_SIZE`: about 20 bytes a line) |
| Stream buffers | — | 256 bytes each |

Source size is unlimited. The limits are the number of module-level names, and the size of one function. Both are raised by splitting a module.

## Configurations

One source, three ways to link the compiler (goal 16).

| Configuration | For | Arrangement |
|---|---|---|
| **All in one** | 64 KB of RAM, small or medium programs | Compiler, allocator and linker are one program. For a small program the object stream is a memory buffer, so nothing touches the disk between source and image, as in Turbo Pascal. |
| **Banked** | Wendy 2, a BBC Micro with sideways RAM, an Apple IIe with 128 KB | The kernel and data are in fixed memory. Phases, and if needed the parts of the front end, are in banks. The symbol heap can be a banked data region. |
| **Chained** | 32 KB machines with a disk | Compiler, linker pass 1 and linker pass 2 are separate programs run in order. They share nothing in memory; the files are the interface. |

All three use the far-call mechanism of [`code-model.md`](code-model.md), so the compiler is its own test of banking and overlays.

If the front end alone exceeds what a chained configuration can hold, it has to be divided in time: a first program turns source into a token file and a second compiles the tokens. That is a fallback, not the plan; L4 in [`spikes.md`](spikes.md) decides whether it is needed.

### Size estimates

| Part | Estimate |
|---|---|
| Kernel | 3 KB |
| SRC and LEX | 2 KB |
| DECL | 4 KB |
| STMT, EXPR, GEN, FBUF, OUT | 10 KB |
| ASM (embedded assembler) | 3 KB |
| Linker pass 1 | 3 KB |
| Linker pass 2 | 2 KB |
| **Total** | **27 KB** |

For comparison: Turbo Pascal 3 for CP/M was about 30 KB with its editor and run-time library, in hand-written assembly (a figure recalled, not checked). `p1` is about 55 KB of code compiled by `p8c`, which an optimising compiler would bring to about 34 KB. These numbers say 27 KB is plausible and not safe; measuring it early is the purpose of L4.

## The interface file

Written when a module is compiled, read by `import`. It lists each exported name with its kind and type, the value of each exported constant, the layout of each exported type, the signature and attributes of each exported function, and the saved tokens of each exported `inline` function. It is a compact binary stream that loads straight into the symbol heap without parsing.

## The object file (stage B)

A stream of records, each a type byte, a length and a body. The order is fixed so the linker's first pass can stop reading a function before its code.

| Record | Contents |
|---|---|
| Module | Name, CPU variant, format version. |
| Import | A module this one refers to. |
| Symbol | A module-level variable, constant table or string: segment, size, zero page class, weight, region if any, and initial bytes for data. |
| Function header | Name, attributes (`recursive`, `interrupt`), code size. |
| Class | A pointer class: its signature, whether it is `recursive`, and the functions this module adds to it. |
| Slots | For each slot of the frame: size, zero page class, weight. |
| Calls | For each call: the callee or, for a call through a pointer, the class; whether it saves the caller's frame; and any call made while its arguments were pending. |
| Sites | Offsets in the code where an operand may shrink from absolute to zero page, and the positions of branches that cross them. |
| Code | The instruction bytes. |
| Fix-ups | Offsets in the code to fill with the address of a symbol, slot or function, with an addend and a part (low byte, high byte or both). |
| End | End of module. |

In stage A the Slots and Calls records are written to the `.lfm` file in the same form, so the allocator is the first half of the future linker.

## The linker

**Pass 1** reads every record except Code and Fix-ups.

1. Build the call graph, with one node per pointer class standing for its parameter block. Find the functions reachable from `main` and from each interrupt handler, and drop the rest.
2. Check cycles against the `recursive` attribute.
3. Find functions used by more than one context and plan their copies. Check that each pointer class is called through pointers from one context only.
4. Allocate frames and module-level variables in zero page and main memory ([`code-model.md`](code-model.md)).
5. Compute each function's final size, place code and constants in their regions, and create stubs for calls that cross windows.

**Pass 2** reads the Code and Fix-up records, applies the addresses, and writes the image or images and the map file.

### Shrinking instructions

The compiler does not know whether an "either" slot will land in zero page, so it does not know whether `LDA slot` is two bytes or three. In stage A asm17 decides, because the allocation is assembled first. In stage B:

- The compiler emits the three-byte form and records the site.
- Branch lengths are fixed assuming three bytes everywhere. Shrinking only brings a branch and its target closer, so a branch that reached still reaches.
- The linker, knowing the allocation, removes the extra byte at each site that landed in zero page, and adjusts the offsets of branches that cross it using the Sites record.

A slot declared `zp`, and every dereferenced pointer, is two bytes from the start and never appears as a site.

This is the largest piece of new mechanism in stage B and has its own spike (L3). The fallback, if it proves too heavy for the target, is to fix the class of every slot at compile time and let the linker only assign addresses within each class.

### Memory in the linker

Pass 1 holds one entry per function and per module-level symbol across the whole program, with names hashed. At about 20 bytes each, 800 functions and symbols need 16 KB. Code is never held in memory: pass 2 streams it.

## The environment description

A text file per machine and configuration, read by the linker and, for a few constants, by the compiler. A sketch for Wendy 2:

```
cpu       65c02
zeropage  $10-$EF
region    LOW    $0200-$7FFF  ram  fixed
region    WIN    $8000-$EFFF  ram  window  banks 1-15
region    HIGH   $F800-$FFF9  ram  fixed
define    HAS_LCD

place     code           LOW
place     data           LOW
place     module symtab  code  WIN 1
place     region SYMBANK       WIN 2

farcall   wendy2_farcall
output    binary
stack     $FF
exit      loop
```

| Entry | Meaning |
|---|---|
| `cpu` | 6502 or 65C02. Sets the `bool` constant `cpu_65c02` that the source can test with `#if`. |
| `zeropage` | The ranges the linker may allocate. |
| `region` | A named address range: RAM or ROM, fixed or a window, and its banks. |
| `define` | A constant for `#if`: `define NAME` is the `bool` `true`, `define NAME VALUE` a number. |
| `place` | Where a segment goes, by default or for one module. |
| `farcall` | The run-time routine for calls that cross windows: a bank switch or an overlay loader. |
| `output` | The image format: raw binary, a Commodore `PRG`, one file per bank, and so on. |
| `stack`, `exit` | What the start-up code the linker writes does before and after `main`. |

A period machine with little zero page, no banks and a disk is the same file with different numbers and an overlay loader in place of the bank switch.

## Errors and debugging

- **Compile errors.** The compiler stops at the first error and reports file, line, column and a message. Message texts can be kept in a separate file, leaving only numbers in the compiler, when memory is tight.
- **Link errors** name the functions involved and, for storage problems, the call chain.
- **Map file.** Lists every function, variable and slot with its address, and every function copy and stub the linker created.
- **Finding a run-time address.** Given an address, the map file gives the function and offset. The compiler, run in a "find" mode, recompiles that module and stops when the function's code reaches that offset, which gives the line. No line tables are stored. This is Turbo Pascal's method.

## The host reference compiler

A Python implementation in `lathe/host/`, written first.

- It is the first compiler, the test oracle, and the tool that builds the Lathe-written compiler until that can build itself.
- **It must have the same structure as the Lathe-written compiler**: the same components, the same one-pass order, no syntax tree, no use of Python features that have no cheap equivalent on a 6502. Byte-identical output then follows from doing the same steps, and porting is transliteration. `p8c` needed a second, iterative parser for this reason.
- The allocator and linker have host versions under the same rule.

## Constraints of starting on asm17

Read from `asm/17/` and measured by spike S2 on 2026-11-13.

**The limit that shapes the plan:** asm17 keeps every label on a heap of about 45 KB, at the length of the name plus 5 bytes for a global label and plus 8 for a local one, and never releases local labels. Compiler output has about one label per 8 bytes of code, so asm17 on the target assembles 15 to 20 KB of it with readable names and no more than 30 KB with very short ones. The Lathe-written compiler will be larger than that. Stage A is therefore a host stage: `asm/pyasm.py` gives the same bytes as asm17 and assembled a 45 KB test in a third of a second. On the target, the compiler emits object code from the start ([`build-plan.md`](build-plan.md)).

| Constraint | Effect on stage A |
|---|---|
| No relocatable output and no linker. | The whole program is assembled at once from a top-level file that includes the allocation and every module. Names are prefixed with the module name. |
| Zero page addressing is chosen by value, and a label used before its definition is assumed absolute. | The allocation file is included first. Constant tables are emitted before the code that indexes them. |
| At most about 255 instructions may refer forward to a label where a zero page form exists (`FWDREF_LIST` is 512 bytes). `JSR`, `JMP` and branches do not count. | Follows from the row above if the ordering is kept. |
| A branch out of range is an error, not widened. | The compiler fixes branch lengths itself, from the function buffer, as it must in stage B anyway. |
| At most 256 conditional blocks in a program. | Unused functions cannot each be wrapped in `.ifdef`. In stage A only the run-time library is trimmed, by including one file per routine. Full trimming arrives with the linker. |
| Expressions have `+`, `-`, `<<`, `>>` only, evaluated left to right. | The compiler folds everything else itself and emits simple expressions. |
| Label names can be 127 characters. A `.` is not allowed inside a name. | Names are module, function and slot joined by `__`. Branch targets are local labels `.L1`, `.L2`. |
| After a forward `JSR`, `JMP` or branch, an instruction with a literal address is treated as a forward reference and forced to three bytes. | Operands are always names, never literal addresses. A variable declared `at` an address gets an equate. |
| `*` cannot be used in an operand. | Branches always name a label. |
| `.include` paths are relative to the working directory. Directives must be indented. The file must end with a newline. | The build driver runs the assembler from one directory and writes files accordingly. |
| The origin is set with `* = address`. | Written by the top-level file from the environment description. |
