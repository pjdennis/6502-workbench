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

Because there is no syntax tree, memory holds only tables, and each lives no longer than it must: the module's symbols and names for the whole module, the current function's symbols, names and instructions until the function ends, a string or a constant table until it is written. Source size is unlimited. The limits are the number of names a module has and imports, and the size of one function; both are raised by splitting a module.

`lathe/tests/memory_report.py` counts every module-level array of the compiler's host modules as Lathe lays it out (2 bytes an element of a list, 1 of a `bytearray` or a list of `bool`; `test_memory.py` checks that the Lathe twins agree), adds the text memory, and with `--corpus` compiles every module under `lathe/src/`, `lathe/rt/` and `lathe/tests/cases/` and reports each table's peak use. Revised 2026-11-14 after that measurement:

| Table | Owner | Rows × bytes | Bytes | Peak on the corpus | Why this size |
|---|---|---|---|---|---|
| Name heap: names, frozen imports | kernel | 14,848 × 1 | 14,848 | 14,149 (`gen.lth`, 8 imports) | `gen.lth`, with 5 % to spare; `regcmd` 11,923, `reg.lth` 11,085. A name is 6 + its length; a frozen import is 8 + its length (+ 2 + 2 a member for a function) |
| Symbol columns | kernel | 480 × 17 | 8,160 | 462 (`gen.lth`) | own symbols, locals, and the imported symbols the module names; `reg.lth` 298 |
| Members (parameters, results) | kernel | 432 × 2 | 864 | 409 (`gen.lth`) | `reg.lth` 285 |
| Name buckets, streams, modules | kernel | | 252 | | |
| Text memory: file name, arguments, saved tokens | kernel | 4,096 × 1 | 4,096 | 3,383 (saved tokens 520 of 2,048) | host only: the Lathe twin has 1,024 until INLINE is ported |
| String being read | lex | 2,048 × 1 | 2,048 | 2,048 | the language allows a 2,048-byte string |
| Function buffer | fbuf | 4,096 × 1 | 4,096 | 3,357 (`kernel.lth`) | about 1.3 bytes an instruction byte |
| Labels (offset, alias, uses / loop end, note) | fbuf | 192 × 6 | 1,152 | 115 | a label is one byte; `label_uses` is the loop ends once the layout is settled |
| Weights of other functions' slots | fbuf | 64 × 4 | 261 | 23 | |
| Constant table and its fix-ups | out | 2,048 + 256 × 8 | 4,096 | 600; 244 fix-ups (`err.MESSAGES`) | the language allows a 2,048-byte table |
| Calls, class members | out | 64 × 5 + 64 × 4 | 576 | 56, 6 | |
| Operand stack, frame, register state | reg | | 2,569 | slots 136 of 192 | locals below 128, then 64 temporaries |
| Types | typetab | 64 × 7 + 16 × 3 | 496 | 35 | |
| Initial values, stubs, saving calls | gen | | 744 | 22 inits of 32 | |
| ASM labels; inline expansions; `case` values; interface entry | asmblock, inline, expr, decl | | 1,408 | | |
| **Total** | | | **45,751** | | at the start of this revision **71,843** (55,715 without the 16,128 bytes of host text memory) |

What changed, and what each change saved:

- **FBUF keeps no code.** It held a function as entries and then built `code` (4 KB) and five fix-up columns (8 KB) before OUT wrote them. Now `finish()` settles the branches and counts the code, the fix-ups and the weights in one walk of the entries; OUT walks them twice more (`walk_begin()`, `walk_next()`, one instruction at a time), once for the FIX record and once for the CODE record, which the object format wants in that order. Saved 12.8 KB. The buffer was then sized to its use (8 KB to 4 KB).
- **Imports are frozen.** Reading an interface used to make every exported name a symbol: `reg` needed 578 symbols, 367 of them imported, of which it named 75. Now a module's types and inline functions are still entered as symbols when the interface is read (they are few, and their order and the type table's must not change), but each function, constant and variable is a *frozen entry* in the name heap: a name entry not yet in its hash bucket, on its module's list, whose symbol, token and following bytes hold the symbol's kind, flags, type, value and members (`kernel.freeze()`). `kernel.sym_find(module, name)`, which every `module.name` goes through, thaws an entry the first time it is named: the entry becomes the name, in its bucket, and the symbol is numbered down from the top of the table, so it outlives the function it was first named in. Later uses find it on the name's chain, or on the chain of the other entry of the same spelling when the name was made before the thaw. The cost of an import is now about 8 bytes plus the name per exported constant or variable (an import of `err`, 136 names: 2.8 KB, where it was 4.8 KB) and a symbol row only for what is named. `reg.lth` compiles with the real compiler: 295 symbols, 11 KB of names.
- **Capacities sized to the corpus**, with a margin: symbols 512 to 384, members 1,024 to 320, labels 256 to 192, slots 256 to 192, types 128 to 64, initial values 64 to 32, saved tokens 4 KB to 2 KB, host text memory 16 KB to 4 KB.
- **Raised for `gen.lth`** (2026-11-14), the twin of GEN and the largest module so far: the name heap 12,800 to 14,848 bytes, symbols 384 to 480, members 320 to 432, 3,904 bytes in all. Before that, `string()` moved from GEN to EXPR, so that GEN does not import LEX, whose names took 2.0 KB of its heap (16,147 to 14,149); and GEN's byte columns became bytearrays (920 to 744 bytes). Of `gen.lth`'s 14.1 KB of names, 12.5 KB are its eight imports.

**The 20 KB budget is not met** (`test_memory.py` keeps the budget test as an expected failure, and fails if the total grows). What remains is the name text: every name a module has, and every name its imports export, frozen or not, about 16 bytes each. Sized by the twins: `reg` (1,196 lines of Python, 5 imports with 6.1 KB of interfaces) peaks at 11.0 KB of names and 295 symbols; `gen` has as many top-level names as `reg` and imports nine modules whose twins' interfaces hold 10.0 KB, so it would need about 15.5 KB of names and 500 symbols (measured on `gen.lth`, once `string()` had moved to EXPR: 14.1 KB and 462); `expr` (12 imports, about 12 KB of interfaces) about 16 KB and 480; `decl` about 16 KB and 360. At those sizes the tables would take about 48 KB, and the twins' test programs, whose code is 28 KB, would not fit the emulator's 60 KB, so the capacities are set by the corpus and the larger modules wait for one of these:

- **Import only what is named.** Read the source once before compiling, collecting each `module.name`, and freeze only those entries (about half the name heap of `reg` or `gen`), at the cost of reading the source twice. An exported `inline` function's body can name what the importer does not, so the interface would have to list what each body names: a change to the interface format.
- **Fewer exports.** The twins export what other modules use, and `err`'s 125 error numbers are a fifth of every importer's names: numbering errors by module, or passing a small number with a module prefix, would leave each module a few names.
- **One heap for the name heap, the function buffer, the string and the constant table**, which are rarely all full at once: names growing up, the function buffer down, so that one module's many names and another's long function share the slack.
- **Symbols as rows reached through a pointer**, not 384-row columns: the same memory, but `LDY #offset` / `LDA (row),Y` for each field where a column access now computes a 16-bit address (`kernel.thaw`, which fills a row, is 631 bytes of code; the twins of KERNEL and FBUF already reach the entries of the name heap and the function buffer through a pointer in the functions that read them most).
- **Messages on disk.** `err`'s 122 message texts are 5.1 KB of constant data with their table; kept in a file read only when an error is reported, they would leave about 5 KB of code space.
- **Stream buffers.** On the target each open stream needs a buffer (the emulator's host calls need none): the files open at once are the source, the object file and an interface (two while an interface brings in a module it names), so about 1 KB of text memory at 256 bytes each.

## Configurations

One source, three ways to link the compiler (goal 16).

| Configuration | For | Arrangement |
|---|---|---|
| **All in one** | 64 KB of RAM, small or medium programs | Compiler, allocator and linker are one program. For a small program the object stream is a memory buffer, so nothing touches the disk between source and image, as in Turbo Pascal. |
| **Banked** | Wendy 2, a BBC Micro with sideways RAM, an Apple IIe with 128 KB | The kernel and data are in fixed memory. Phases, and if needed the parts of the front end, are in banks. The symbol heap can be a banked data region. |
| **Chained** | 32 KB machines with a disk | Compiler, linker pass 1 and linker pass 2 are separate programs run in order. They share nothing in memory; the files are the interface. The compiler itself is not divided further: banks make that pointless, and on a machine without banks it does not save enough ([`configurations.md`](configurations.md)). |

All three use the far-call mechanism of [`code-model.md`](code-model.md), so the compiler is its own test of banking and overlays.

Dividing the front end in time was the fallback of L4; [`configurations.md`](configurations.md) shows it would save about 4.5 KB, not enough to matter.

The linker builds the banked form from the environment file alone: a module's code goes in a bank or an overlay by a `place` entry, calls that cross go through 6-byte stubs in fixed memory, and the same object files link all in one when there is no such entry ([`configurations.md`](configurations.md), section 5, "As built").

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

A stream of records, each a type byte, a length and a body; the format as built is [`object-format.md`](object-format.md) (version 2). The order is fixed so that what the linker needs about a function or a table comes before its bytes: each pass reads each file once, in order.

| Record | Contents |
|---|---|
| Module | Name, CPU variant, format version. |
| Import | A module this one refers to. |
| Symbol | The name and kind of each module-level symbol the module defines or uses. |
| Variable | A module-level variable: size, zero page class, weight. No initial value: initialisers are code. |
| Data | A constant table or string, its fix-ups first. |
| Function header | Name, attributes (`recursive`, `interrupt`). |
| Class | A pointer class: the sizes and names of its parameters, whether it is `recursive`; and the functions this module adds to it. |
| Slots | For each slot of the frame: size, zero page class, weight. |
| Calls | For each call: the callee or, for a call through a pointer, the class; whether it saves the caller's frame; and any call made while its arguments were pending. |
| Fix-ups | Offsets in the code to fill with the address of a symbol, slot or function, with an addend and a part (low byte, high byte, or both); a two-byte one says whether its instruction can shrink to the zero page form. Before the code. |
| Code | The instruction bytes. |
| Weights | Weight this module adds to other modules' variables and to slots of functions other than the one using them. |
| End | End of module. |

In stage A the Slots and Calls records were to be written to the `.lfm` file in the same form, so the allocator is the first half of the linker.

## The linker

**Pass 1** never reads code. It reads the files quietly for the names worth keeping, once for the tables (of the Fix-ups it only checks the entries), again for what kept code and data name, and once, after allocation, for the sizes (step 5), from the Fix-ups alone ("Memory in the linker" lists the readings).

1. Build the call graph, with one node per pointer class standing for its parameter block. Find the functions reachable from `main` and from each interrupt handler, and the variables, constants and functions whose address what is kept names ([`object-format.md`](object-format.md), "What the linker keeps"), and drop the rest.
2. Check cycles against the `recursive` attribute.
3. Find functions used by more than one context and plan their copies. Check that each pointer class is called through pointers from one context only.
4. Allocate frames and module-level variables in zero page and main memory ([`code-model.md`](code-model.md)).
5. Compute each function's final size: its written size less one byte for each fix-up marked "can shrink" whose address is in zero page. Place code and constants in their regions, and create stubs for calls that cross windows.

**Pass 2** reads each file once more, in order, with one stream: it holds a function's Fix-ups until its Code arrives (a table's until its bytes arrive), applies the addresses, shrinks, and writes the image or images and the map file's slot lines. A function copied for several contexts has its Code read again for each further copy. The map's other lines are written by readings of their own, which read the names again.

### Shrinking instructions

The compiler does not know whether an "either" slot will land in zero page, so it does not know whether `LDA slot` is two bytes or three. In stage A asm17 decides, because the allocation is assembled first. In stage B:

- The compiler emits the three-byte form, and marks its fix-up as one that can shrink (kind 5) when the instruction has a zero page form; `JSR`, `JMP`, `JMP (v)` and `LDA v,Y` cannot.
- Branch lengths are fixed assuming three bytes everywhere. Shrinking only brings a branch and its target closer, so a branch that reached still reaches.
- The linker, knowing the allocation, removes the extra byte at each such fix-up whose address landed in zero page, and adjusts the branches and labels that cross it. The fix-ups are all it needs: the sizes in pass 1 come from them without reading code, and in pass 2 they are held before the code they patch arrives.

A slot declared `zp`, and every dereferenced pointer, is two bytes from the start and never appears as a site.

This is the largest piece of new mechanism in stage B and has its own spike (L3). The fallback, if it proves too heavy for the target, is to fix the class of every slot at compile time and let the linker only assign addresses within each class.

### Memory in the linker

**Budget.** The linker must run beside its own code (about 12 KB in Lathe) and a stack on a machine with less than 60 KB free, linking the compiler itself: about 700 functions, 3,500 slots and 3,000 calls in 30 to 40 object files. Its tables together were given 24 KB. `lathe/tests/lk_memory_report.py` prints what the host linker's tables take laid out as Lathe lays them out (2 bytes a row for a word column, 1 for a byte column), the peak use of each over the corpus and over `lk_synthetic.py`, the stand-in for the compiler, and how often each file is opened; `test_lk_memory.py` keeps the total within the ceiling it states, which only comes down.

**Rules the design follows.**

- *A table lives only in the phases that use it.* Scratch of one phase shares storage with the scratch of another, in one work area (`lk_tab.work`).
- *Reading a file again is cheap; memory is not.* What can be found again in the object files is read again when it is needed, not held: what fix-ups name, names, the sizes of copies.
- *Rows are as narrow as their values*: byte columns where a value fits a byte, flags packed beside small numbers, columns derived instead of stored.

**Symbols and names.** There is no table of symbols. A symbol is a reference (`lk_sym`): its kind in the top three bits and the row of what defines it, in the functions, the variables and constants, or the classes; a symbol nothing defines has `UNDEF` and a number of its own. `lk_name.local` holds, for each object file, the reference each of its symbol numbers stands for. Names are held only while the files are first read, and only those that more than one `SYM` record names. The first reading of all (`lk_name.mark_all`) is quiet, so that every error is still found by the reading that found it before; it marks in 8,192 bits the hash of every name some file has a `SYM` record for and does not define, of every class, and of every name two definitions share (32,768 bits of names defined, for that). While the files are read for the tables a marked name is kept in a heap and found through chains, compared in full, and an unmarked one makes a new symbol and is forgotten; a false match only keeps a name that need not have been. Every symbol has a number and two words at the top of the work area: what it stands for so far, and the weight given to a variable before it is defined. Once the files are read, every number in `local`, the calls and the members is replaced by what it stands for (`lk_name.resolve`), and heap and words are dropped. The compiler and the object format are unchanged: a flag in `SYM` saying a name is exported would only save the first reading, and the test for names that two files define would still be needed. A name that is written is read again from the files: for an error message from the first file with a `SYM` record for the symbol (`lk_name.error_name`); for the map by a reading of each file, which holds the names its lines need (`lk_map`).

**Calls.** The calls of a function or class are a run of rows, from its `fn_edge` or `cls_edge` to the next one's, in the order the chains of the earlier design walked them, newest first. While the files are read a function's own calls are a run in the order read, and a call made while another function's arguments wait takes two rows at the top of the table, with whether its caller's own calls were read before it. Once they are read, runs and waiting calls become chains in the work area, the classes' calls are added, and the chains become runs again (`lk_tab.build_chains`, `chains_to_runs`).

**Nodes.** Node f is the first copy of function f, a hole if f is not kept; the further copies follow the functions, in function then context order, and the class blocks follow them. Every walk that chooses a root or can report an error goes in the order the copies are placed in (`lk_tab.first_in_order`, `next_in_order`).

**Passes over the object files, and what each holds.** Each reading reads a file from start to end (`lk_rec`); a function linked for several contexts has its `CODE` read again for each further copy, in the image pass, which reopens the file and skips to it.

| Pass | Reads | Holds besides the tables |
|---|---|---|
| 0 Names to keep (`lk_name.mark_all`), quiet | `SYM` and the symbol of `FUNC`, `VAR` and `DATA` | a hash of each name of the file being read, in `local`; the marks, in the work area |
| 1 Tables (`lk_scan`) | every record; `FIX` and `DFIX` only checked | the names marked and the symbols' words, in the work area |
| 2 What is kept (`lk_graph.keep_referenced`) | `FUNC`, `FIX`, `DFIX`, the symbol of `DATA`: every file, then again each file with something kept after a reading passed it | one `DFIX` record's entries until its `DATA` |
| 3 Sizes and placement (`lk_place`) | `FUNC`, `FIX`, `CODE` length, `DATA` | — |
| 4 Map: F, D and V lines (`lk_map`) | `SYM`, and `FUNC`, `FIX` and the length of `CODE`, or `DATA`, or `VAR`: a reading for each kind of line, of the files that have such lines | the names the file's lines need |
| 5 Image and map: S lines (`lk_emit`) | every record | one function's or table's fix-ups; the names of the file's kept functions that have slots |
| 6 Map: C lines (`lk_map.cparams`), if a class is live | `SYM`, `CLAS`, `FUNC`, `SLOT` of the files that name a class or have the function that names a class's parameters | the names of classes and their parameters |

`lextest` opens its 8 files 62 times in all, 5 to 10 times each (before: 48, 6 each); `lk_synthetic`'s 30 files are opened 340 times (before: 212), 62 of them reopenings for copies. By pass, before and after, `lextest`: tables 8 and 8, what is kept 24 and 13, placement 8 and 8, image 8 and 8, and new, names 8, map F 7, map D and V 10. `lk_synthetic`: what is kept 60 and 55, image 92 and 92, and new, names 30, map F 30, map D and V 55, map C 18. Every pass is linear in the size of the files; the graph and the layouts are linear in nodes and calls.

**The work area.** `lk_tab.work`, seven words per node and three node columns, holds what one phase needs and the next does not. While the files are read: the weights waiting, the marks, the chains and heap of kept names, and the symbols' words at the top. Once they are read: the waiting calls and the chains (`lk_tab.W_WCALLER`...). While the graph is built: the stack of `reach`, the entries of a `DFIX` record, the files a reading of what is kept must read, then Tarjan's columns (stack, edge cursor, found, discovery, low), the set number and the order of each node. While storage is allocated: the layout's columns (base, end of set, size of set, depth below, which holds the call chain of an error), the zero page size, the set number and the order; promotion's count of candidates of each weight and its list of what was taken since the last layout, in the column of main memory bases, which nothing has yet. While code is placed and written: the fix-ups held, each copy's address, a slot name and the names of one file; for the C lines, the names of classes and their parameters. From `lk_graph.make_nodes` on: each node's function or class, its context and zero page base, and its main memory base.

**Rows, before and after** (bytes per row; the capacity in brackets). The capacities are the compiler's sizing.

| Table | Before (main, 2026-11-14) | Now |
|---|---|---|
| symbols | 11 (2,048) + names 16,384 | none: a symbol is a reference to the row of what defines it; while the files are read, two words each and the names more than one `SYM` record names, in the work area (1,600 symbols) |
| symbols in object files | 2 (4,096) | 2 (4,000) |
| functions | 10 (1,024) | 9: the first call instead of the symbol; the number of slots from the next function's first (800) |
| slots | 4 (8,192) | 2: size in four bits, 15 bytes and over aside, beside the class, whether a parameter and whether in zero page; the weight (4,000, and 64 large) |
| calls | 5 (8,192) | 2: the flags in the top three bits of the callee; a function's or class's calls are a run (3,600) |
| nodes | 15 fixed + 12 graph + 10 storage (1,280) | 6 + 14 in the work area (900) |
| references named by fix-ups | 4 (2,048) | none: read again |
| fix-ups held | 9 (1,024) | 12 in the work area (512) |
| variables and constants | 2 (1,024) | 5: address (a variable's weight until it has one), size, flags (800) |
| classes, parameters, members | 12 (64), 8 (256), 4 (256) | 14 (32), 6 (128), 4 (128) |
| weights waiting | 5 (256) | none: in the work area while the files are read (64) |
| candidates by weight | 512 | none: in the work area while promotion works |
| windows, banks, places (stage 11) | | 834, below |
| **total** | **204,338** | **53,952** (53,118 before stage 11) |

**What stage 11 added**, 834 bytes, all sized by the environment and none by the program, beside the work area that the earlier phases already share: the environment's names (`lk_envf.text`, 384 bytes: window, module, region and file names as length and characters, enough for placement D's 9 modules, 4 file names and some regions); 4 windows at 10 bytes (name, first, last, register, switch kind, mask: 40); 16 banks or overlays at 5 (window, number, value, file name: 80); 32 places at 3 (module name, bank: 96); 16 regions at 3 (48); the bank each object file's code is in (`lk_scan.obj_bank`, 40) and the first stub of each object's functions (`lk_win.obj_stub`, 82); and for each bank, the bytes given out and the bytes judged for the fit check (`lk_place.bank_used`, `bank_judged`: 64). There is no table of stubs: a function that has them has a flag in `fn_flags`, and a stub's place is counted from the functions of its object file. Which function is in which bank is found from its object file, and whether a constant or variable may go in its bank is a flag in `def_f`.

The work area is 18,000 bytes of it: 7 × 900 + 3 × 900 words. Peak use over the 78 programs of the corpus (the end-to-end cases on the three machines and `lextest`): objects 8, symbols in object files 376, symbols 312, names kept 856 bytes, functions 220, slots 1,085, calls 419, nodes 220, defs 200, classes 3, class parameters 8, members 7, contexts 3, weights waiting 7, fix-ups held 348. `lk_synthetic` (30 files, 703 functions): 3,430 symbols in object files, 827 symbols, 8,474 bytes of names kept, 3,644 slots, 3,225 calls, 768 nodes, 121 defs, 210 fix-ups held; the host linker takes 0.7 s.

**Choosing what goes in zero page.** The rule ([`code-model.md`](code-model.md), "What goes in zero page") is greedy: candidates heaviest first, each taken if the deepest chain still fits with it. If they all fit, one layout shows it. Otherwise `lk_alloc.judge` decides most items without a new layout. After a layout L it keeps a list of the copies taken since, each with the longest chain through its node in L. A chain through copies x1..xk is no longer than the shortest of their chains plus the sum of their sizes, so the deepest chain of a context is now at most the largest, over the chains t of the list, of t plus the sizes of the copies whose chain is t or more. An item fits if zero page fits with it at that bound; it does not fit if it does not fit with L alone, since more in zero page never makes a chain need less. Only an item between the two takes a new layout, after which it is judged exactly. The choices are those of laying out after every item taken (`test_lk_promotion.py` links both ways and compares). Layouts, before and after: `lextest` with 16, 32, 48, 64 and 96 bytes of zero page 103, 109, 120, 108, 80 and 23, 18, 17, 13, 10; `lk_synthetic` with 112, 128, 160, 192 and 224 bytes 927, 869, 759, 616, 280 and 123, 106, 61, 41, 29. Judging an item reads the list, which a layout empties when it reaches 128 entries (more saved no layouts on the corpus or the synthetic program).

**Why not 24 KB, or 30.** While storage is allocated nearly everything above is live at once, and at the compiler's capacities that is 53 KB (54 KB with stage 11's tables): the symbols in object files (8,000 bytes, needed again by placement and the image, and only names could rebuild them), calls (7,200), slots (8,000), functions (7,200), variables and constants (4,000), classes and the rest (2,000), and the work area (18,000: the layout's seven columns and the node columns). The steps left that keep every choice and every text the same are small: the zero page layout in 9-bit values and Tarjan's discovery number kept in the set column (two columns, 3,600 bytes, with the S lines read by a pass of their own to leave room for one file's names while the image is written); the members in the work area (512). Going further means giving something up: dropping `local` while storage is allocated and rebuilding it afterwards, which needs the names again; reading the slots that promotion judges from the files in bands of weights, a reading per band; or lower capacities.

## The environment description

A text file per machine and configuration, read by the linker and, for a few constants, by the compiler (`lathe/host/README.md`, "The environment file", has every entry as built). For the compiler on Wendy 2, banked:

```
; wendy2bank.env: the compiler on Wendy 2, banked
cpu       65c02
zeropage  $00 $FF
code      $0200 $3DFF            ; fixed: code, stubs, the far-call routine, fixed constants
data      $3E00 $7FFF            ; fixed: variables, frames, fixed tables
more      data $F810 $FFF9       ; a second fixed range for variables
stack     $FF
exit      stop
output    raw

window    WIN $8000 $EFFF        ; an address range whose contents are switched
switch    WIN bank $F000 $1F     ; switched by the bank register at $F000, bits $1F
bank      WIN 1 $11 LATHE1.BIN   ; bank 1: the register's value, and the file written for it
bank      WIN 2 $12 LATHE2.BIN
bank      WIN 3 $13 LATHE3.BIN
place     lathec WIN 1           ; a module's code goes in bank 1 of WIN
place     decl WIN 1
place     expr WIN 1
place     inline WIN 1
place     gen WIN 2
place     reg WIN 2
place     cond WIN 2
place     out WIN 2
place     asmblock WIN 3
farcall   rt_bank                ; the run-time module for far calls and for loading banks
define    BOARD 2
define    DISK 1
```

| Entry | Meaning |
|---|---|
| `cpu` | 6502 or 65C02. Sets the `bool` constant `cpu_65c02` that the source can test with `#if`. |
| `zeropage`, `code`, `data` | The ranges the linker may allocate in: zero page, fixed code and constants, fixed variables. |
| `more data FIRST LAST` | A second range for variables, used when the first is full. |
| `define` | A constant for `#if`: `define NAME` is the `bool` `true`, `define NAME VALUE` a number. |
| `window NAME FIRST LAST` | An address range whose contents change. It must not overlap `code`, `data`, `more` or another window. |
| `switch NAME bank ADDR MASK`, `switch NAME overlay` | How the window is switched: by the bits `MASK` of the register at `ADDR`, or by loading a file. |
| `bank NAME N VALUE [FILE]`, `overlay NAME N FILE` | Bank or overlay `N` of the window, the register value, and the file the linker writes with its contents. |
| `place MODULE NAME N` | The module's code goes in bank or overlay `N`. By module only. |
| `farcall MODULE` | The run-time module for calls that cross windows: `rt_bank` (a bank switch) or `rt_ovl` (an overlay loader). |
| `output` | The image format: `image` (to `$FFFF`, with the reset vector) or `raw`. Each bank or overlay is a raw file of its own. |
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
