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
| Name heap: names, frozen imports | kernel | 12,800 × 1 | 12,800 | 11,923 (`regcmd`, 9 imports) | `reg.lth` 11,036. A name is 6 + its length; a frozen import is 8 + its length (+ 2 + 2 a member for a function) |
| Symbol columns | kernel | 384 × 17 | 6,528 | 295 (`reg.lth`) | own symbols, locals, and the imported symbols the module names |
| Members (parameters, results) | kernel | 320 × 2 | 640 | 285 (`reg.lth`) | |
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
| Initial values, stubs, saving calls | gen | | 920 | 22 inits of 32 | |
| ASM labels; inline expansions; `case` values; interface entry | asmblock, inline, expr, decl | | 1,408 | | |
| **Total** | | | **42,023** | | at the start of this revision **71,843** (55,715 without the 16,128 bytes of host text memory) |

What changed, and what each change saved:

- **FBUF keeps no code.** It held a function as entries and then built `code` (4 KB) and five fix-up columns (8 KB) before OUT wrote them. Now `finish()` settles the branches and counts the code, the fix-ups and the weights in one walk of the entries; OUT walks them twice more (`walk_begin()`, `walk_next()`, one instruction at a time), once for the FIX record and once for the CODE record, which the object format wants in that order. Saved 12.8 KB. The buffer was then sized to its use (8 KB to 4 KB).
- **Imports are frozen.** Reading an interface used to make every exported name a symbol: `reg` needed 578 symbols, 367 of them imported, of which it named 75. Now a module's types and inline functions are still entered as symbols when the interface is read (they are few, and their order and the type table's must not change), but each function, constant and variable is a *frozen entry* in the name heap: a name entry not yet in its hash bucket, on its module's list, whose symbol, token and following bytes hold the symbol's kind, flags, type, value and members (`kernel.freeze()`). `kernel.sym_find(module, name)`, which every `module.name` goes through, thaws an entry the first time it is named: the entry becomes the name, in its bucket, and the symbol is numbered down from the top of the table, so it outlives the function it was first named in. Later uses find it on the name's chain, or on the chain of the other entry of the same spelling when the name was made before the thaw. The cost of an import is now about 8 bytes plus the name per exported constant or variable (an import of `err`, 136 names: 2.8 KB, where it was 4.8 KB) and a symbol row only for what is named. `reg.lth` compiles with the real compiler: 295 symbols, 11 KB of names.
- **Capacities sized to the corpus**, with a margin: symbols 512 to 384, members 1,024 to 320, labels 256 to 192, slots 256 to 192, types 128 to 64, initial values 64 to 32, saved tokens 4 KB to 2 KB, host text memory 16 KB to 4 KB.

**The 20 KB budget is not met** (`test_memory.py` keeps the budget test as an expected failure, and fails if the total grows). What remains is the name text: every name a module has, and every name its imports export, frozen or not, about 16 bytes each. Sized by the twins: `reg` (1,196 lines of Python, 5 imports with 6.1 KB of interfaces) peaks at 11.0 KB of names and 295 symbols; `gen` has as many top-level names as `reg` and imports nine modules whose twins' interfaces hold 10.0 KB, so it would need about 15.5 KB of names and 500 symbols; `expr` (12 imports, about 12 KB of interfaces) about 16 KB and 480; `decl` about 16 KB and 360. At those sizes the tables would take about 48 KB, and the twins' test programs, whose code is 28 KB, would not fit the emulator's 60 KB, so the capacities are set by the corpus and the larger modules wait for one of these:

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

**Pass 1** never reads code. It reads the files twice: once for the tables (of the Fix-ups it notes only what each function or table names), and once, after allocation, for the sizes (step 5), from the Fix-ups alone.

1. Build the call graph, with one node per pointer class standing for its parameter block. Find the functions reachable from `main` and from each interrupt handler, and the variables, constants and functions whose address what is kept names ([`object-format.md`](object-format.md), "What the linker keeps"), and drop the rest.
2. Check cycles against the `recursive` attribute.
3. Find functions used by more than one context and plan their copies. Check that each pointer class is called through pointers from one context only.
4. Allocate frames and module-level variables in zero page and main memory ([`code-model.md`](code-model.md)).
5. Compute each function's final size: its written size less one byte for each fix-up marked "can shrink" whose address is in zero page. Place code and constants in their regions, and create stubs for calls that cross windows.

**Pass 2** reads each file once more, in order, with one stream: it holds a function's Fix-ups until its Code arrives (a table's until its bytes arrive), applies the addresses, shrinks, and writes the image or images and the map file. A function copied for several contexts has its Code read again for each further copy.

### Shrinking instructions

The compiler does not know whether an "either" slot will land in zero page, so it does not know whether `LDA slot` is two bytes or three. In stage A asm17 decides, because the allocation is assembled first. In stage B:

- The compiler emits the three-byte form, and marks its fix-up as one that can shrink (kind 5) when the instruction has a zero page form; `JSR`, `JMP`, `JMP (v)` and `LDA v,Y` cannot.
- Branch lengths are fixed assuming three bytes everywhere. Shrinking only brings a branch and its target closer, so a branch that reached still reaches.
- The linker, knowing the allocation, removes the extra byte at each such fix-up whose address landed in zero page, and adjusts the branches and labels that cross it. The fix-ups are all it needs: the sizes in pass 1 come from them without reading code, and in pass 2 they are held before the code they patch arrives.

A slot declared `zp`, and every dereferenced pointer, is two bytes from the start and never appears as a site.

This is the largest piece of new mechanism in stage B and has its own spike (L3). The fallback, if it proves too heavy for the target, is to fix the class of every slot at compile time and let the linker only assign addresses within each class.

### Memory in the linker

**Budget.** The linker must run beside its own code (about 12 KB in Lathe) and a stack on a machine with less than 60 KB free, linking the compiler itself: about 700 functions, 3,500 slots and 3,000 calls in 30 to 40 object files. Its tables together get at most 24 KB. `lathe/tests/lk_memory_report.py` prints what the host linker's tables would take laid out as Lathe lays them out (2 bytes a row for a word column, 1 for a byte column), and the peak use of each over the corpus and over `lk_synthetic.py`, the stand-in for the compiler; `test_lk_memory.py` keeps the total within the limit it states.

**Rules the design follows.**

- *A table lives only in the phases that use it.* Scratch of one phase shares storage with the scratch of another: the work area holds Tarjan's columns while the graph is built, the layout's columns while storage is allocated, and the fix-ups of one function while the image is written.
- *Reading a file again is cheap; memory is not.* What can be found again in the object files is read again when it is needed, not held: what fix-ups name, now; most names, in the plan below.
- *Rows are as narrow as their values*: byte columns where a value fits a byte, flags packed beside small numbers, columns derived instead of stored.

**Passes over the object files, and what each holds.** Each pass reads each object file once, from start to end (`lk_rec`); a function linked for several contexts has its `CODE` read again for each further copy, in the image pass, which reopens the file and skips to it.

| Pass | Reads | Holds besides the tables |
|---|---|---|
| 1 Tables (`lk_scan`) | every record; `FIX` and `DFIX` only checked | — |
| 2 What is kept (`lk_graph.keep_referenced`) | `FUNC`, `FIX`, `DFIX`, the symbol of `DATA`; once per reading until one keeps nothing new | one `DFIX` record's entries until its `DATA` |
| 3 Sizes and placement (`lk_place`) | `FUNC`, `FIX`, `CODE` length, `DATA` | — |
| 4 Image and map (`lk_emit`) | every record | one function's or table's fix-ups |

`lextest` reads each of its 8 files 6 times (3 readings in pass 2); `lk_synthetic`'s 30 files are opened 212 times in all (2 readings in pass 2, 62 reopenings for copies). Every pass is linear in the size of the files. The graph and the layouts are linear in nodes and calls, as before; pass 2 replaces a table of references by readings.

**The work area.** `lk_tab.work`, eight words per node, holds what one phase needs and the next does not: while the graph is built, Tarjan's columns (stack, edge cursor, found, discovery, low), the set number and the order of each node; while storage is allocated, the layout's columns (base, end of set, size of set, depth below, call chain for an error), the set number, the order and the zero page size; while code is placed and written, the fix-ups held and each node's address and length.

**Rows, before and after** (bytes per row; the capacity in brackets). The capacities are now the compiler's sizing.

| Table | Before (main, 2026-11-14) | Now |
|---|---|---|
| symbols | 11 (2,048) + names 16,384 | 11 (1,600) + names 12,288 |
| symbols in object files | 2 (4,096) | 2 (4,000) |
| functions | 10 (1,024) | 10 (800) |
| slots | 4 (8,192) | 3: size in a byte, 255 and over aside (4,000, and 64 large) |
| calls | 5 (8,192) | 4: the flags in the top three bits of the callee (3,600) |
| nodes | 15 fixed + 12 graph + 10 storage (1,280) | 6 fixed + 16 in the work area (900) |
| references named by fix-ups | 4 (2,048) | none: read again (pass 2) |
| fix-ups held | 9 (1,024) | 12 in the work area (512) |
| variables and constants | 2 (1,024) | 2 (800) |
| classes, parameters, members | 12 (64), 8 (256), 4 (256) | the same rows (32, 128, 128) |
| weights waiting | 5 (256) | 5 (64) |
| **total** | **204,338** | **97,442** |

Peak use over the 77 programs of the corpus (the end-to-end cases on the three machines and `lextest`): objects 8, symbols in object files 376, symbols 312, names 3,736 bytes, functions 220, slots 1,085, calls 419, nodes 215, defs 200, classes 3, class parameters 8, members 7, contexts 3, weights waiting 7, fix-ups held 348. `lk_synthetic` (30 files, 703 functions): 3,430 symbols in object files, 827 symbols, 6,564 bytes of names, 3,644 slots, 3,225 calls, 727 nodes, 121 defs, 210 fix-ups held; the host linker takes 0.44 s.

**The rest of the way to 24 KB.** In order of what each saves at the capacities above:

1. *Names only where another module needs them.* A flag in `SYM` (format version 3; `out.symbol` writes it for `pub` names and for the names it imports) says whether another module can name the symbol. Only those names, and `MAIN.main`, go into the heap; `$init` becomes a function flag found while the name is read. The map's F, D and V lines are written by a reading each, which holds the names of the object being read; a name in an error message is read from the first object file that has the symbol. Saves about 15 KB (the heap, `sym_name`, `sym_next`).
2. *Symbols dissolved into references.* Once every file is read, each entry of `local` holds what its symbol is (kind, defined, and a row of `fn_`, `cls_` or a table of variables and constants), and the symbol columns go: about 8 KB.
3. *Calls as a run per function*, filled from the end so that a walk sees them newest first as the chains do now, with the calls made while another function's arguments wait, the calls into class blocks and the merged classes' runs placed where the chains put them: `edge_next` goes, 7 KB.
4. *Slots in two bytes*: the size in a nibble with an escape, and the zero page class, the kind and the choice in the other: 4 KB. *Pending weights* go once a first reading counts each function's slots.
5. *A function's first copy is the node of the same number*, extra copies and class blocks after them: `node_own` and `fn_node`, 3.4 KB; the zero page layout in 9-bit values, 2.7 KB.

That brings the tables at the compiler's size (the synthetic program) to about 30 KB while storage is allocated, which is the peak: zero page promotion needs every candidate's weight and size and every call, because it lays the program out again after each accepted item. The last 6 KB need one of: dropping the symbol tables while storage is allocated and rebuilding them afterwards from a table of hashed exported names (the few hashes that collide keep their names); or reading the candidates of promotion from the files in bands of weights, each band a reading. Choosing what goes in zero page still lays the program out again after each item accepted when zero page is short: one layout per item (`lextest` with 64 bytes of zero page: 108 layouts). A cheaper step would update the layout in place: the item's node grows, the nodes below it move up and the chains above it get deeper, but each is a walk over the graph from that node, which costs nearly as much as laying out the whole again.

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
