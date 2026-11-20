# Lathe: spikes

Status (2026-11-14): the small spikes S1 to S7 and the larger spikes L4 and L5 are done; results are at the end, with the first measurement of the linker in Lathe. L1 and L2 were folded into building the compiler and the linker. L3 (shrinking in the linker) is answered by the linker itself, which shrinks in one streaming pass and matches the assembler byte for byte.

A spike is a short experiment that answers one question and is then thrown away. Its output is a number or a yes or no, written back into the design documents. Spike code does not become the compiler.

## Small spikes

Each is a few hours on the host, needs nothing that does not exist today, and could be run now.

| # | Question | Method | Decides |
|---|---|---|---|
| S1 | How much storage does sharing frames save on a real program? | Use `p8c`'s parser on `prog8/p1/p1.p8` to get every function's parameters and locals and the call graph. Compare the sum of all frames with the deepest chain. Count the bytes that must be in zero page along the deepest chain. | Whether automatic allocation earns its cost. The smallest zero page Lathe can support (goals table). |
| S2 | Can asm17 assemble what a compiler emits? | Generate asm17 source shaped like stage A output: 30 KB of code, 3,000 labels, long prefixed names, an allocation file included first. Assemble it on the emulator. Record time, heap use and which limits are hit. | Whether stage A works as planned or asm17 needs changes first. The name-mangling scheme. |
| S3 | Does the syntax read well and does the code model give the code it claims? | Take four routines that exist as hand-written assembly: one each from the editor, asm17, the firmware library and `p1`. Write each in Lathe and compile it by hand following [`code-model.md`](code-model.md). Compare bytes and cycles with the original. | The first evidence for the code size target. Changes to syntax before anything depends on it. |
| S4 | Is the grammar really LL(1)? | Enter the grammar from [`language.md`](language.md) into a small first-and-follow checker. | Fixes to the grammar. Confidence that a one-token parser is enough. |
| S5 | How often does a forward branch not reach? | In `p8c`'s output for `p1`, measure the distance of every forward conditional branch. | Whether "short first, widen the few" is right, and how large the function buffer must be. |
| S6 | Which characters can each period machine type and display? | A table for the Commodore 64, Apple II+, Apple IIe, BBC Micro and this repository's boards against every character the syntax uses. | The alternate spellings question in [`goals.md`](goals.md). |
| S7 | What do the larger functions of a compiler need in temporaries and frame size? | From the same `p1` data as S1: the distribution of frame sizes, and the size of the largest function's code. | The function buffer size and the cost of a recursive call. |

S1, S5 and S7 share one script. S2 is the one most likely to change the plan, because it tests the tool stage A depends on.

## Larger spikes

Each is days, not hours, and each guards a decision that would be expensive to reverse. They are listed in the order they should run. The build plan ([`build-plan.md`](build-plan.md)) says which stage each one precedes.

### L1. One-pass code generator

- **Question:** Do lazy operands, destination passing and register tracking reach the code size target without an optimiser?
- **Method:** A Python prototype of EXPR and GEN for assignments, arithmetic, comparisons, conditions, array and pointer access, on bytes and words. Feed it 30 or so functions rewritten from `p1` and the editor. Compare with `p8c` and with upstream `prog8c` on the same logic. As part of this, repeat `p1`'s measurement of passing one argument in A.
- **Decides:** The targets in [`goals.md`](goals.md). The set of operand kinds. Whether register arguments join the calling convention.
- **Before:** Stage 2.

### L2. Storage allocation

- **Question:** Which rule for giving zero page to "either" slots works best, and is the whole allocation cheap enough to run on the target?
- **Method:** A Python allocator run on the S1 call graph and on synthetic graphs, with zero page budgets of 16, 32, 144 and 224 bytes. Try at least two rules: callers first, and heaviest first across the program. Count the zero page accesses each gives, weighted by loop depth. Include an interrupt context, a function used from two contexts, a recursive group, calls inside arguments, and pointer classes with their shared parameter blocks. Estimate the memory and time of the same algorithm on a 6502.
- **Decides:** The allocation rule. The frame and call records. The smallest supported zero page.
- **Before:** Stage 3.

### L3. Shrinking in the linker

- **Question:** Can the linker shrink instructions for slots that land in zero page, in one streaming pass, within the memory a target has?
- **Method:** Define the Sites record. Write a host linker that shrinks and fixes branches. Check its output against asm17's for the same program, byte for byte. Measure the largest table it must hold.
- **Decides:** Whether stage B keeps automatic zero page for "either" slots, or falls back to classes fixed at compile time.
- **Before:** Stage 9.

### L4. Size of the compiler

- **Question:** How large is the compiler when compiled by itself?
- **Method:** As soon as stage 2 exists, write the lexer and one full path through declarations, statements and expressions in Lathe. Measure bytes per component and scale to the full feature list.
- **Decides:** The 16 KB and 32 KB targets. How the front end is divided between banks. Whether the chained configuration needs a separate tokenising program.
- **Before:** Stage 7.

### L5. Far calls three ways

- **Question:** Does one stub mechanism serve fixed memory, banks and disk overlays, and what does each cost per call?
- **Method:** A small test program with three modules, linked three ways from the same objects: all fixed on the emulator's default machine, banked on emulated Wendy 2, and as overlays loaded through the host file interface. Measure cycles per far call and, for overlays, loads per run.
- **Decides:** The `farcall` and `place` entries of the environment description. How the compiler's phases may call each other.
- **Before:** Stage 11.

### L6. Recursion by saving frames

- **Question:** What does a recursive call cost, and is the rule easy to get right?
- **Method:** Write a recursive-descent expression evaluator in Lathe once stage 5 allows it. Measure bytes and cycles per call against the same evaluator written with an explicit stack.
- **Decides:** Whether the compiler's own expression parser recurses or loops. The size of the recursion stack.
- **Before:** Stage 7.

### L7. Symbol heap capacity

- **Question:** How many module-level names fit, and what does an import cost?
- **Method:** Define the symbol entry layout. Load the interface files of a program the size of the compiler into a heap of 8 KB and of 16 KB.
- **Decides:** Limits to document. Whether the symbol heap needs to be a banked region. Guidance on module size.
- **Before:** Stage 7.

### L8. Disk traffic on a slow drive

- **Question:** On a drive that reads a few hundred bytes a second, how long does a build take in each configuration?
- **Method:** Count the bytes read and written per source line by the compiler and linker for a medium program. Apply the transfer rates of a 1541, a BBC DFS drive and an Apple Disk II.
- **Decides:** Buffer sizes. Whether object files need to be more compact. Whether the all-in-one configuration should link in memory by default.
- **Before:** Stage 12.

## Risks the spikes do not remove

- **The language is new.** No amount of measurement shows whether it is pleasant to write a 10,000-line compiler in. Writing the compiler is the test, and stage 7 is where changes to the language will be found.
- **Two implementations must stay identical.** Every feature is written twice, in Python and in Lathe. The rule that the Python follows the target's structure keeps this cheap; breaking that rule once makes it expensive for good.
- **Period machines are not in the emulator.** The first period port needs either an outside emulator in the test suite or a new machine model here.

## Results of the small spikes (2026-11-13)

### S1 and S7: storage in `p1`

Measured exactly from the syntax tree of the three `p1` sources.

| | `p1.p8` | `p1_pass1_sh.p8` | `p1_pass2_sh.p8` |
|---|---|---|---|
| Functions | 240 | 121 | 171 |
| Sum of all frames, bytes | 1003 | 444 | 688 |
| Deepest chain, bytes | 159 | 89 | 218 |
| Deepest chain as a share of the sum | 16% | 20% | 32% |
| Pointer bytes on the deepest chain (estimate) | 18 | 22 | 90 |
| Frame size: median / 90th percentile / largest | 3 / 10 / 23 | 3 / 9 / 12 | 3 / 11 / 23 |
| Recursive groups | none | none | one of 14 functions, 94 bytes |

- **Sharing pays.** Storage falls to between a sixth and a third of the unshared total.
- **Frames are small.** A recursive call that saves a frame copies about 10 bytes each way.
- **Zero page floor.** A compiler-sized program needs 20 to 90 bytes of zero page for dereferenced pointers alone. The 16-byte target in [`goals.md`](goals.md) holds only for small programs, or with pointers declared `nozp`.
- **The recursive group** is the expression code generator, as expected.

### S2: asm17 capacity

asm17 assembles compiler-shaped text correctly and identically to `asm/pyasm.py`, but its label heap is the limit. The details are in [`architecture.md`](architecture.md), "Constraints of starting on asm17". The consequence is the changed order of work in [`build-plan.md`](build-plan.md).

| Program | Result on asm17 |
|---|---|
| 5 KB of code, 836 labels | Assembles: 20 million cycles. |
| 15 KB, 2500 labels | Assembles: 65 million cycles, heap 32 KB of 45 KB. |
| 30 KB, 5000 labels | Out of memory. Fits only with one-letter module names and three branch labels per function. |
| 45 KB | Out of memory in every arrangement tried. |

### S3: four routines compiled by hand

Routines from the editor's search, asm17's hash table, the firmware's decimal conversion and `p1`'s name interning were written in Lathe and compiled by hand, using only the techniques in [`code-model.md`](code-model.md).

| Routine | Original bytes | Lathe bytes | Ratio | Inner loop cycles, ratio |
|---|---|---|---|---|
| Editor search | 107 | 166 | 1.55 | 1.64 |
| asm17 hash table | 130 | 192 | 1.48 | 1.09 to 1.40 |
| Decimal conversion | 101 | 161 | 1.59 | 1.30 to 1.85 |
| `p1` name interning | 125 | 163 | 1.30 | 1.38 |
| **Total** | **463** | **682** | **1.47** | |

The target of 1.5 is met, with little margin. Changes made to the language as a result:

- A `bool` result travels in the carry flag; a status can be tested directly with `f() -> v`; `return f()` passes results on as a jump.
- `p[i]` works for pointers to elements of 2, 4 or 8 bytes; `nil`; `^T(x)`.
- `lo(x)` and `hi(x)` can be assigned to.
- `loop … until`.
- The meaning of `for` at the ends of the range is defined.

The further code generation refinements it identified are listed in [`code-model.md`](code-model.md), "Generating the code".

### S4: the grammar

The grammar as first written had two real LL(1) conflicts and three gaps. All are fixed in [`language.md`](language.md).

| Finding | Fix |
|---|---|
| A function type's `, bool` result clashed with the comma between parameters. | A function type can be written only in a `type` declaration, so it always has a name. |
| `initialiser` listed `string` twice, once through `constExpr`. | The separate alternative is removed. |
| `byte(w)` and `sizeof(byte)` were not accepted, because type keywords are not names. | A type keyword followed by arguments is a conversion; `sizeof` takes a type. |
| `constExpr` was not defined. | It is an `expression` that the compiler must be able to evaluate. |
| `#if` and the end of an `asm` block were not specified. | Both are lexer rules, now stated. |

### S5: forward branches

Estimated from `p8c`'s assembly for `p1` with a size calculator, not an assembler listing.

- Between 88% and 94% of forward conditional branches reach their target as a two-byte branch.
- The median distance is 9 to 18 bytes; the longest is 1840.
- The largest function is about 2 KB of `p8c` code, so a function buffer of 4 KB is enough.

"Short first, widen the few" is confirmed.

### S6: characters

| Machine | Characters of the syntax that cannot be typed or shown |
|---|---|
| Commodore 64 | `\|` and `~` have no key and no glyph. `\` shows as £, `^` as ↑, `_` as ←. |
| Apple II+ | `\|` and `~` are impossible. `[`, `\` and `_` have no key. |
| Apple IIe | None known. |
| BBC Micro | None in modes 0 to 6. Mode 7 shows `# [ \ ] ^ _ ~` as other glyphs. |

This matches decision Q3: only `|` and `~` need alternate spellings, and only for the first two machines.

## Result of L4: the size of the compiler (2026-11-14)

The compiler's lowest layers were rewritten in Lathe under `lathe/src/` (system interface, errors, kernel, source stack, lexer), function for function from the host Python, and compiled by the host compiler. The Lathe lexer on the emulator and the Python lexer give identical output over all 367 `.lth` files in the repository.

| Module | Code bytes | Constant data | Variables | Bytes of code per line of host code |
|---|---|---|---|---|
| sys | 172 | 0 | 16 | 2.9 |
| err | 488 | 3388 (messages) | 11 | 1.8 |
| kernel | 1052 | 0 | 20182 (tables) | 3.7 |
| src | 230 | 0 | 46 | 3.2 |
| lex | 1937 | 300 | 267 | 4.2 |
| **err, kernel, src, lex** | **3707** | | | **3.4** (5.8 per line inside functions) |

- **Projection.** The compiler has about 6,100 lines of code, 5,100 of them inside functions: 21 KB at 3.4 bytes per line, 30 KB at 5.8 per function line. The later modules use word tables of 512 entries and calls with several arguments, which cost more per line than the lexer's character handling. Estimate: **25 to 35 KB for the compiler, 8 to 11 KB for the linker**, before the improvements below. Confidence is low to moderate.
- **Storage sharing works as designed.** The frames of every function sum to 212 bytes; shared through the call graph they take 49, all in zero page.
- **Speed.** 553 emulated cycles per source byte for the lexer: about 0.6 seconds per kilobyte of source at 1 MHz.
- **Memory for tables is the tighter limit.** The kernel's tables need 20 KB, which is why the test uses its own environment (`lathe/src/compiler.env`) with more room for data.
- **No fault in the compiler was found** by this first 2,000-line program.

Where the bytes go in the three largest functions, and what would save them:

| Improvement | Saving seen |
|---|---|
| Keep what is known about A across a label reached only by forward branches | 40 of 355 bytes in `lex.mark`, 18 of 221 in `lex.scan` |
| Pass byte arguments in registers | 48 bytes in `lex.mark` (eight calls with three constant arguments) |
| A jump table for a dense `case` | about 60 bytes in `lex.mark` |
| `JMP` to an `RTS` becomes `RTS`; a value just stored is not reloaded | 24 bytes in `lex.scan` |
| A shift by 8 as a byte move | 28 bytes in `kernel.name_word` |
| Symbol tables of at most 256 entries, so every access is `LDA table,X` | 13 to 22 bytes at each access to a 512-entry table |

Together these are estimated to recover 10 to 25%.

**Measured (2026-11-14).** Four of them are now in the host compiler (`codegen.md` has the rules), measured on `lextest` with `lathe/tests/size_report.py`. Bytes are of code; "layers" is err, kernel, src and lex (3,707 before), "program" all of `lextest` (4,824 before). Compiler lines are lines of code in `lathe/host`, without comments and docstrings.

| Improvement | Layers saved | Program saved | Compiler lines |
|---|---|---|---|
| Register memory across a label that only forward branches reach | 80 (2.2%) | 96 (2.0%) | +79 |
| `JMP` to an `RTS` becomes `RTS` (a `JMP` to a `JMP` saved nothing) | 16 (0.4%) | 16 (0.3%) | +21 |
| A word copied between variables keeps its low byte in A (its high byte goes through X) | 15 (0.4%) | 15 (0.3%) | +4 |
| A word shifted by 8 to 15 places moves a byte | 31 (0.8%) | 82 (1.7%) | +12 |
| **All four** | **142 (3.8%): 3,565** | **209 (4.3%): 4,615** | **+116** |

- **"A value just stored is not reloaded"** was already true. Nothing in `lextest` loads a value a register still holds from its store; the reloads that looked like it (`STA lex__line` … `LDA lex__line` in `lex.scan`) come from A being used for the next byte of a word, which the copy through X answers where the word is used next.
- **A pointer into a big array built again** for a neighbouring element (`names[offset]`, `names[offset + 1]`) happens 5 times in `lextest` (in `kernel.name_word`, `name_set_word`, `name_end`, `sym_lookup`), each 15 bytes where `LDY #1` would do: about 65 bytes. It needs a memory of what a pointer temporary holds, with its own rules for when that ends and for sharing the temporary between operands, so it is left for now. The 512-entry tables cost more in the same way: the index is shifted again for every table (`s << 1` five times in `kernel.sym_add`).
- **Byte arguments in registers** (done since: see "Arguments in registers, measured" below; `lathe/tests/arg_report.py` counts it from the object files). `lextest` has 137 calls of functions with parameters, which spend 480 bytes storing arguments. Against that, with each callee storing the registers into its slots on entry: the first byte parameter in A saves 144 net; the first three byte parameters in A, X, Y 180; the first parameter in A, or A and X for a word or pointer, 200; that and A, X, Y for bytes when the first parameter is a byte, 236 (6.6% of the layers). A callee whose first instruction loads that parameter gains 2 more each (+28 to +46). `err.fatal` (25 calls), `lex.followed_by` (10 calls of three constants) and `err.position` (8 calls of two words) are most of it.

**Arguments in registers, measured (2026-11-14).** Convention (d) above, as `code-model.md` ("Convention") now has it: a first byte parameter in A, a second and third byte directly after it in X and Y; a first word in A and X, and a byte directly after it in Y; each function stores them in its slots on entry. Measured with `lathe/tests/size_report.py` against the compiler as it was just before (layers 3,734, program 4,759):

| Module | Before | After | Saved |
|---|---|---|---|
| err | 512 | 477 | 35 (6.8%) |
| kernel | 965 | 946 | 19 (2.0%) |
| src | 254 | 240 | 14 (5.5%) |
| lex | 2003 | 1849 | 154 (7.7%) |
| **layers** | **3734** | **3512** | **222 (5.9%)** |
| lextest | 619 | 559 | 60 |
| sys | 153 | 155 | -2 |
| num | 225 | 233 | -8 |
| **program** | **4759** | **4487** | **272 (5.7%)** |

- `arg_report.py` predicted 209 net for the layers' code, 249 with the callee's first load credited; the result, 222, is in between. `lex.mark` (62 bytes), `lex.scan` (20) and `err.fatal` (10) gain most; functions with three byte parameters, such as `lex.followed_by`, grow by the stores on entry (5 bytes) and save them back at each call.
- The first parameter alone (A, or A and X) gives 184 (4.9%) of the 222: the rest of the convention is a few lines more in the compiler, so it was kept whole.
- Compiler: 65 lines of code more in `gen.py`, 1 each in `decl.py` and `inline.py` (without comments and docstrings). Arguments still run from left to right: one waiting for a register is copied to a temporary before a call in a later argument (exempting the caller's own slots saved nothing on `lextest`).
- `rt_math`'s functions, ordinary Lathe functions written in `asm`, grow by 4 bytes (6 for the shifts) for their stores on entry; the signed divides shrink by 1 to 4, since they call the unsigned ones with registers.

## L4 revised: ten modules measured (2026-11-14)

With the middle layers also written in Lathe (types, constant folding, the function buffer, the object writer, register memory, conditions), the first projection was too low.

| Modules | Code bytes | Tables | Bytes of code per line of host code |
|---|---|---|---|
| err, kernel, src, lex | 5,435 | 22,375 | 4.4 |
| typetab, fold, fbuf, out, reg, cond | 17,244 | 31,523 | 7.4 to 9.5 |
| **The ten** | **22,679** | **53,898** | 6.9 |

- **The middle layers cost twice as much per line as the lowest ones.** They are word arithmetic, tables of more than 256 entries, and calls with several arguments, where the lexer is byte handling.
- **Projection for the whole compiler.** The six modules still to do have 4,563 lines of code. At 6.9 to 8.4 bytes per line they are 31 to 38 KB, so the compiler would be **55 to 61 KB of code, with 54 KB of tables**. The target was 32 KB. It cannot run in 64 KB as it stands. Measured since: `gen` (1,418 lines of code) is 12,322 bytes, 8.7 a line, just above that range; its ten largest functions are 3.8 KB of it (`array_index` 538, `save_frame` 515, `math_function` 462).
- **`asmblock` measured (2026-11-14).** 569 lines of code (769 in all) are 3,512 bytes of code, 6.2 a line of code (4.6 a line), and 465 bytes of constant data, the instruction table's 462: the cheapest of the upper layers, because like the lexer it is byte handling. Its largest functions are `name_operand` 435, `direct` 285 and `indirect` 247. It compiles with 132 bytes of the name heap to spare, after `object_symbol` moved from `gen` to `reg` so that it need not import `gen`.
- **`inline` measured (2026-11-14):** `inlines.lth`, the twin of `inline.py` (456 lines of code), is 4,589 bytes, 10.1 a line of code (7.4 a line), the highest of the twelve: it works on records in text memory through pointers, `word_at()` and `param()` (a multiply by 3 through `rt_math`) at nearly every step; its ten largest functions are 3.5 KB of it (`save` 712, `write` 559, `argument_symbol` 499, `read` 422). The twelve modules are 41,210 bytes of code, 5.5 a line.
- **`expr` measured (2026-11-14):** `expr.lth`, the twin of `expr.py` (1,236 lines of code, 1,598 in all), is 15,207 bytes of code placed (16,771 as written, before zero page forms), 12.3 a line of code (9.5 a line), 50 % above the estimate of `configurations.md` (8,761 to 10,182): 45 of its 77 functions are on cycles of calls and so `recursive`, and the 482 bytes that their saving calls push and pop cost about 5,800 bytes, a third of the module. Its ten largest functions are 6.8 KB of it (`for_statement` 1,069, `variable` 1,000, `case_statement` 702, `return_statement` 644, `designator` 638). With the twelve above, 56,417 bytes of code.
- **The whole compiler measured (2026-11-14).** With `decl` and `lathec` written in Lathe, all sixteen modules are twins, and `lathec.lth` links them into the compiler, which runs banked on Wendy 2 (`configurations.md`, "The compiler itself, banked"). Measured by `size_report.py --report` (a function's size is the largest any test program's map gives it, the compiler's own map among them): **72,685 bytes of code** for the sixteen modules, 6.4 a line of host Python and 8.7 a line of code; 72,653 of them in the compiler's own link, 74,092 with `sys`, `disk` and the run-time modules. That is 11 to 17 KB above the 55 to 61 KB projected here when ten modules were written, because `expr` (16,638 bytes now, with `with`: 12.0 a line of code) and `inline` (10.4) cost far more a line than the ten did (6.9). `decl` is 8,543 bytes for 889 lines of code (9.6 a line, 7.6 a line in all, within the range projected for it in `configurations.md`) and 65 of constant data; `lathec` 1,052 bytes for 147 (7.2, 5.4). Their largest functions: `decl.constant_declaration` 537, `write_interface` 436, `write_named_type` 382, `init` 339; the compiler's ten largest are `expr.for_statement` 1,122, `expr.variable` 1,035, `inlines.save` 734, `expr.case_statement` 702, `expr.designator` 698, `kernel.thaw` 667, `expr.return_statement` 654, `gen.array_index` 622, `expr.with_statement` 588, `inlines.write` 559.
- **The host compiler cannot compile `reg.lth` within its own limits**, because an import brings in every exported name.
- **Where the code is bigger than it should be**, by estimated saving in the six middle modules: arrays of more than 256 entries (142 address computations of about 13 bytes; rows reached through a pointer would save 550 bytes here and several KB overall); the function buffer walked by an index, not a pointer (740); the address of `buffer[e + k]` recomputed each time (260); a word built from two bytes through a temporary (25 bytes a time against 10); index registers reloaded when two indexes alternate (250); chains of tests that could be tables; loops tested at the top (29 loops).
- **First improvements (2026-11-14).** Four changes to code generation took the ten from 24,257 bytes (the measure after the cut tables) to 23,835: a word against `$FFFF` as the AND of its bytes (71), absolute,Y for an element whose index X does not hold while X holds another (68 for stores, 67 more for loads), and big arrays of bytes and words reached with Y the low byte of the index (216). A fault fix, `w = t[lo(w)]`, then cost 35 (23,870). What was tried and did not pay is listed in `codegen.md`, "Tried and dropped".

## The linker's lower layers in Lathe, measured (2026-11-14)

Stage 8 began with the linker's ten lowest modules written in Lathe (`lathe/src/lk_*.lth`), each tested against its host module by `lathe/tests/test_src_lk.py` (`lathe/host/README.md`, "The linker in Lathe"). Measured by `lathe/tests/size_report.py --linker` over the two test programs, which between them keep every function of the ten; "code" lines are those of the Python without blank lines, comments and docstrings.

| Module | Code bytes | Python lines | Code lines | Bytes per line | Bytes per code line |
|---|---|---|---|---|---|
| lk_err | 418 (and 2,505 of messages) | 221 | 179 | 1.9 | 2.3 |
| lk_op | 122 (and the 256-byte table) | 71 | 45 | 1.7 | 2.7 |
| lk_file | 127 | 60 | 34 | 2.1 | 3.7 |
| lk_rec | 356 | 149 | 98 | 2.4 | 3.6 |
| lk_sym | 198 | 69 | 35 | 2.9 | 5.7 |
| lk_envf | 3,340 | 688 | 527 | 4.9 | 6.3 |
| lk_tab | 4,865 | 649 | 410 | 7.5 | 11.9 |
| lk_name | 3,952 | 493 | 321 | 8.0 | 12.3 |
| lk_scan | 4,036 | 540 | 405 | 7.5 | 10.0 |
| lk_out | 402 | 81 | 52 | 5.0 | 7.7 |
| **The ten** | **17,816** | **3,021** | **2,106** | **5.9** | **8.5** |

The ten largest functions: `lk_tab.build_chains` 915, `lk_envf.check_windows` 662, `lk_scan.rec_wgt` 568, `lk_name.symbol` 509, `lk_name.mark_object` 410, `lk_tab.chains_to_runs` 393, `lk_name.resolve` 310, `lk_envf.check` 305, `lk_tab.add_waiting` 287, `lk_scan.add_far_edges` 281.

- **Projection.** The modules still to write (`lk_win`, `lk_boot`, `lk_graph`, `lk_alloc`, `lk_fix`, `lk_place`, `lk_map`, `lk_emit`, `link`) have 2,003 lines of code. At 8.5 bytes a line they are about 17 KB, so the linker would be **about 35 KB of code** and 2.8 KB of constant data, three times the 12 KB that "Memory in the linker" ([`architecture.md`](architecture.md)) assumed and the 8 to 11 KB of the first projection of L4. The upper layers are more like `lk_tab` and `lk_scan` (walks of the tables and the work area) than like `lk_err` and `lk_rec`, so the figure is more likely low than high.
- **Where the bytes go.** The tables of more than 256 rows. Each access to an element of a `rows` table of words (`lk_tab.work`, `edge_word`, `fn_edge`, `local`...) computes a 16-bit address, base plus twice the index, into a zero page pointer before the `LDA (p),Y`: about 30 of the 50 bytes of `lk_tab.chain_next` (`work[W_NEXT + e - 1]`). The ten have 166 such accesses, about 5 KB, more than a quarter of their code. Keeping the pointer of an element that is read and then written (`x[i] |= v`; `work[W_START + f] = fn_edge[f]` and then `fn_edge[f] = 0`) would take perhaps 10 to 15% of those 5 KB; folding the constants of an index together (`W_NEXT + e - 1` adds `W_NEXT` and then subtracts 1) only 6 bytes in each of 6 places. The rest is what tables of more than 256 rows cost on a 6502, as the twins are written: line for line from the Python, which indexes; a twin free to walk a table with a pointer (`p = @work[i]`, then `p[0]`, `p[1]`) would pay the address once per walk.
- **Memory.** The test program `lktest2` has 20.0 KB of code and 2.7 KB of constant data, and 28.5 KB of variables at the small build's capacities (half of what grows with the program: `lathe/host/README.md`). At full capacities the tables are 53,952 bytes, so the linker with 35 KB of code cannot hold them in 64 KB: its code must be banked or chained (passes 1 and 2 apart), or its capacities cut to about the small build's, which links a program half the compiler's size.
- **No fault in the compiler was found** by these 3,000 lines: every twin behaved as its host module the first time it ran. The host compiler's own capacities sufficed: `lk_scan`, which imports seven of the others, needs 7,946 bytes of names of 12,800 and 201 symbols of 384 (`lktest2` 8,461 and 201).

## The linker's graph, storage, stubs and start-up in Lathe, measured (2026-11-14)

The next four layers, `lk_win`, `lk_boot`, `lk_graph` and `lk_alloc`, are written in Lathe too, each tested against its host module by `test_src_lk.py` through two more test programs: `lktest3` runs `link.py`'s phases to the stubs and writes the start-up code for made-up code addresses, `lktest4` runs them through storage (`lathe/host/README.md`, "The linker in Lathe"). The test runs reach every line of the four host modules but six that nothing can reach (a fallback after a loop that always returns, the check of a stack that cannot overflow, the second check that promotion's choices fit): `lk_win` 77 of 78 statement lines, `lk_boot` 95 of 96, `lk_graph` 360 of 362, `lk_alloc` 426 of 428. Measured by `size_report.py --linker` over the four programs:

| Module | Code bytes | Python lines | Code lines | Bytes per line | Bytes per code line |
|---|---|---|---|---|---|
| lk_win | 1,078 | 167 | 102 | 6.5 | 10.6 |
| lk_boot | 1,213 | 160 | 119 | 7.6 | 10.2 |
| lk_graph | 5,549 | 642 | 443 | 8.6 | 12.5 |
| lk_alloc | 8,521 | 752 | 531 | 11.3 | 16.0 |
| **The four** | **16,361** | **1,721** | **1,195** | **9.5** | **13.7** |
| **The fourteen** | **34,217** | **4,742** | **3,301** | **7.2** | **10.4** |

The ten largest functions of the fourteen: `lk_tab.build_chains` 915, `lk_alloc.start_choices` 824, `lk_envf.check_windows` 662, `lk_graph.keep_in_object` 584, `lk_scan.rec_wgt` 568, `lk_graph.fail_cycle` 554, `lk_name.symbol` 509, `lk_alloc.take` 505, `lk_alloc.deepest` 503, `lk_graph.search` 455.

- **Projection.** What is left (`lk_fix`, `lk_place`, `lk_map`, `lk_emit`, `link`) has 820 lines of code. At the fourteen's 10.4 bytes a line that is 8.5 KB, and the linker **43 KB of code**; at the four's 13.7, 11.2 KB and 45 KB. The earlier projection, 35 KB, was low, as it said it might be: the graph and storage are walks of the work area, two or three of its columns in each statement, `work[LAY_BASE + work[W_ORDER + i]]`, and each column access is an address worked out into a zero page pointer, 25 to 35 bytes, so a statement with two is 60 to 70.
- **Reading a column through a function.** The Python of `lk_graph` and `lk_alloc` reads its most used columns through a function each (`scc_of`, `order_at`, `seen_of`, `low_of`; `base_of`, `end_of`, `size_of`, `down_of`): a call with the index in A and X is 9 bytes. That took 946 bytes off the two (5%), less than hoped, because most of their bytes are the other tables of more than 256 rows (`fn_slot`, `slot_sz`, `def_f`...) and the arguments and results of calls. A compiler that kept an element's address for the next access of the same element, or of the next row of the same column, would take much more: the largest functions access one row of several columns in turn.
- **Memory.** `lktest2` and the three lower ones did not fit beside the graph and storage: with both in one test program the code and constant data were 38.9 KB and the variables 29.2 KB, 7 KB more than the machine has. So there are two programs, and the small build takes two fifths of what grows with the program instead of half (320 functions, 1,600 slots, 1,440 calls, 360 nodes, 320 definitions, 1,600 symbols in object files; promotion's list `lk_alloc.MAX_TAKEN` 32, which at 360 nodes must not be above 48 to end inside the work area), with the split in `linker.env` moved from `$6000` to `$9100`. `lktest4` has 33.1 KB of code, 2.8 KB of constant data and 23.3 KB of variables, which end at `$ED84`; each range has about 650 bytes to spare. The small build links `lk_synthetic` with 7 functions a module (239 functions, 1,086 slots, 1,038 calls, about a third of the compiler), where it took 11 before; the names kept in the work area are what runs out. The work area's columns of these layers were checked at the new capacities: the graph's (stack, edge cursors, the objects to read at `2 × 360`, found, seen, low; `lk_graph.NAMED` up to `360 + 256`, below the objects) and storage's (base, end, size, depth, zero page size; the weight counts, candidates and list from `9 × 360` up to `9 × 360 + 264 + 64 = 3,568` of 3,600 words) do not overlap each other or the node columns.
- **Speed.** Storage allocation in `lktest4`, measured as the emulator's CPU cycles to the end of `lk_alloc.allocate` less those to its start: `lextest` (76 copies kept of 133 functions, 203 calls) 5.4 million cycles when everything fits (105 bytes of zero page or more: three layouts), 17.5 million at 104 bytes, 19.5 million at 64 and 25.6 million at 16 (10, 14 and 23 layouts); `lk_synthetic` with 7 functions a module (227 copies and blocks, 1,038 calls) 28 million when everything fits (244 bytes), 162 million at 243 bytes, 262 million at 96 and 295 million at 64 (25, 49 and 57 layouts). A layout of that program costs about 5 million cycles, five seconds at 1 MHz, most of it in following edges: each layout turns every edge of every node into the node it calls (`lk_graph.edge_node`, through `edge_sym`, `edge_target`, `has_copy` and `copy_node`) twice, to raise the callees and in `deepen`, and walks the whole order once for each context. The compiler's whole program, three times the calls and 123 layouts at 112 bytes of zero page on the host, would take about half an hour. A table of each node's callees as nodes, made once after the sets are found, would make a layout a walk of words; at full size it would take about 7 KB of the work area, which storage does not have.
- **No fault in the compiler was found**: all four twins behaved as their host modules the first time they ran. The host compiler's capacities sufficed: the largest, `lktest4`, needs 8,954 bytes of names of 14,848, 196 symbols of 480 (`lk_graph`) and 173 members of 432 (`lk_alloc`).

## The whole linker in Lathe, banked on Wendy 2, measured (2026-11-14)

The last five modules, `lk_fix`, `lk_place`, `lk_map`, `lk_emit` and `link`, are written in Lathe, and `lathe/src/link.lth` is the linker: built with `lathe/src/linker-bank.env` it runs on emulated Wendy 2 with `--disk`, its code in three banks, and links real programs. `lathe/tests/test_src_link.py` runs it beside the host linker at the same capacities on every program of the end-to-end corpus that the small build takes, every link the linker's tests make and links made by hand, and requires the error output, the exit status and every file written (image, map, bank and overlay files) to be identical, byte for byte (`lathe/host/README.md`, "The linker in Lathe"). With `LATHE_LK_ALL=1`: 532 links made identically, 246 of them refused with the same link error and status. By kind: lextest 1; the default machine's end-to-end cases 67 (4 refused: the cases that test link errors through `build.py`); Michael 8, Wendy 2 8, Wendy 2 with files 4; the configurations 16 (banks, overlays, regions and data banks, interrupts in banks and in `with` blocks, all in one); the link error cases 5; the links of the linker's own tests 358 (193 refused); links made by hand 63 (43 refused), 20 of them new (`edge_links`); `lk_synthetic` at 7 functions a module, and at 8, refused with error 10 on both sides. Two links of the linker's tests are left out because the board cannot be given their command line: one names files in directories, which the file ports do not have, and one has 41 object files, whose names are more than the 256 bytes of arguments `disk.lth` holds. The whole run takes 160 s; the default part, 58 s.

The host runs reach, of the statement lines of the five (`LATHE_LK_COVERAGE=lines`), `lk_fix` 129 of 132, `lk_place` 119 of 119, `lk_map` 247 of 247, `lk_emit` 168 of 171, `link` 27 of 27. The six left cannot be reached: in `lk_fix`, too many fix-ups of constant data and a fix-up naming what nothing defines (`lk_graph` reports both first) and `@f` of a function not kept (`lk_graph` keeps it); in `lk_emit`, the check of a function's planned size, a fix-up of constant data behind the one before (`next_fix` finds it first) and kind 6 in constant data (`lk_scan` refuses it).

**Code.** Measured by `size_report.py --linker` over the four test programs and the banked linker:

| Module | Code bytes | Python lines | Code lines | Bytes per code line |
|---|---|---|---|---|
| lk_fix | 1,836 | 295 | 191 | 9.6 |
| lk_place | 1,877 | 205 | 148 | 12.7 |
| lk_map | 3,455 | 415 | 304 | 11.4 |
| lk_emit | 2,400 | 251 | 198 | 12.1 |
| link | 179 | 72 | 44 | 4.1 |
| **The five** | **9,747** | **1,238** | **885** | **11.0** |
| **The whole linker** | **45,398** | **6,157** | **4,330** | **10.5** |

The projection, 43 to 45 KB, was right, at its top. `lk_err` is 568 bytes now, 150 more: its messages are two texts of lines, as the Python has them, walked by `begin`, instead of a table of 59 strings (2,703 bytes of constant data instead of 2,863). The largest functions of the five: `lk_emit.instruction` 597, `lk_map.class_names_object` 542, `lk_emit.emit_data` 527.

**The banked layout** (`lathe/tests/lk_bank_report.py`):

| | What | Bytes |
|---|---|---|
| fixed code | lk_tab 4,889, disk 477, lk_rec 386, rt_bank 303, rt_math 261, lk_sym 198, sys 192, `$start` and `$init` 64 | 6,770 |
| stubs | 58: the functions called from another bank or from fixed code | 348 |
| fixed constants | lk_err's messages 2,703, `$banks` and disk's names | 2,777 |
| bank 1, reading | link, lk_err, lk_file, lk_envf, lk_scan, lk_name: code 13,389, constants 212, variables 370 | 13,601 in its file |
| bank 2, graph and storage | lk_graph, lk_alloc: code 14,105, constants 51, variables 36 | 14,156 |
| bank 3, placement and output | lk_place, lk_fix, lk_map, lk_emit, lk_out, lk_boot, lk_win, lk_op: code 12,431, constants 298, variables 169 | 12,729 |
| fixed variables | the tables, `$0200-$58A4`, and 64 bytes at `$F810` | 22,206 |

Resident code, stubs and constants are 9,895 bytes, at `$58C0-$7F66`; 27 bytes are free between the variables and the code, 153 above the code and 1,962 at `$F810` and up, and each bank has 14 to 16 KB of its 28 KB free. The split is tight because a table of more than 256 bytes is always fixed: it is reached through its address (fix-ups of kinds 2 and 3), which keeps it out of its module's bank even when one bank's code alone uses it, and the variables are laid out in object order, each in `data` if it fits, else at `$F810`, so the last large table, `lk_name.local`, must end below the code. To fit, the small build's `MAX_LOCALS` (symbols in object files) went from 1,600 to 1,400; the rest of `LKSMALL` is unchanged. What every phase calls many times is fixed: `lk_tab`, `lk_rec`, `lk_sym`, `sys`, `disk`, the run-time. `lk_err` (only on the way out), `lk_file` (only when a file is opened) and `link` (which calls each phase once) are in bank 1, to make room for the tables. `lk_name` is in bank 1, with the reading it mostly serves: its `global_sym` is called from the later phases once a fix-up entry, and that is the largest share of the far calls. `lk_alloc` is in `lk_graph`'s bank because it reads the graph's columns through `lk_graph`'s functions in its inner loops.

**Cycles and far calls.** The start-up loads the three bank files, 40.5 KB, in 2.85 million cycles. Then, against the host linker at the same capacities:

| Link | Cycles | At 1 MHz | Far calls | Their cost | Host linker |
|---|---|---|---|---|---|
| lextest (8 files, 133 functions) | 109.4 million | 109 s | 18,159 | 3.0% | 0.15 s |
| `lk_synthetic`, 7 functions a module (30 files, 239 functions, 1,086 slots, 1,038 calls) | 242.4 million | 242 s | 45,926 | 3.4% | 0.22 s |
| `farcall.lth` banked (`e2e-config`) | 22.1 million | 22 s | 4,027 | 3.3% | 0.04 s |

By phase, in millions of cycles, lextest and the synthetic program: the environment 0.2 and 0.1, the first reading 24.6 and 47.4, the graph 19.8 and 32.4, storage 5.5 and 28.3, placement 9.7 and 22.1, the image and the map 46.9 and 109.3. The image of the default machine is 64 KB written a byte at a time through `sys.write` and the file ports, which is about half of the last phase for lextest. Where the far calls go (the host run's calls between modules in different banks, counted with `sys.setprofile`, which agree with the counting `rt_bank` within the start-up's dozen): for lextest, into `lk_name` 12,148 (`global_sym`, from lk_fix, lk_graph, lk_map, lk_emit and lk_place), `lk_scan` 2,944 (`fn_bank`, `cpu_of`), `lk_alloc` 2,331 (`slot_addr`, from lk_fix and lk_map), `lk_envf` 495 (from lk_win), the rest under 150. No placement of whole modules removes most of them: `global_sym` serves every pass, and putting `lk_name` in fixed memory costs 4.6 KB that the tables need.

**Capacities.** The small build's: 40 object files (and 48 arguments, 256 bytes of them, which `disk.lth` holds), 1,400 symbols in object files, 320 functions, 1,280 slots, 1,200 calls, 360 nodes, 320 variables and constants, 256 fix-ups of one function. It links `lk_synthetic`'s program at 7 functions a module, 239 functions, 1,086 slots and 1,038 calls: about 30% of the compiler (800 functions; `lk_synthetic` at full size, 703 functions, 3,644 slots and 3,225 calls), and lextest, whose 133 functions are a sixth.

**Banked data.** A table that only fixed code reads could go in a data bank, `in REGION`, mapped by `with REGION do` in `lk_tab`'s functions. Today only `lk_tab.fn_edge` (640 bytes), `big_slot` and `big_size` (256) are read by `lk_tab` alone, and `edge_word` (2,400) by `lk_tab` and `lk_name`; with `lk_name`'s reads of `edge_word` going through `lk_tab`'s accessors, 3.3 KB would leave fixed memory, room for about twice the calls or a third more symbols in object files. The large tables, the work area (7,200 bytes), `local` (2,800), the slots', functions' and definitions' columns, are read in banked code, which cannot see a data bank in the same window.

**What stands before the gate of stage 8.** At the compiler's capacities the linker's tables take 54,144 bytes; Wendy 2's fixed memory is 34,282 bytes, of which the resident part takes 9,895, so 24.4 KB is left. The tables needed to link the compiler cannot fit the one-window layout, whatever is banked: a data bank is seen only by fixed code, and the code that reads the large tables (the graph, storage, placement and output, 30 KB) cannot be fixed beside them. One of these would have to change: a second window, so that a bank of code and a bank of data are mapped at once (Wendy 2 has one bank register; an emulated board, or a board change); the chained configuration (`configurations.md`), the phases run one after another as programs of their own, each with only the tables it needs, the rest passed on in files; or every access to a large table through a fixed function that maps its bank, a restructuring of most of the linker that would make each column access a call and two bank switches. Besides that: `disk.lth` holds 256 bytes of arguments, and the compiler's command line of 30 to 40 object files needs about 400; promotion at full size would take about half an hour at 1 MHz (above); and the compiler written in Lathe lacks `expr`, `decl` and `lathec`.

**Done (2026-11-16): the third of these.** Every access to the work area goes through `lk_tab.wk` and `set_wk`, fixed functions that map its region, and the other large tables were already reached so; the hottest readers of the work area's columns have blocks of their own and are kept fixed. A block costs 32 cycles with its region in fixed memory and about 94 with it in a data bank, so the cost is less than feared: the small build's links take 7 to 10 % more cycles on Wendy 2. The 256 bytes of `disk.lth` are met by a command file (`link @FILE`). Built with `linker-full.env`, the linker links the compiler and itself on Wendy 2 ([`architecture.md`](architecture.md), "The large tables in regions"; `test_src_selflink.py`).

**No fault in the compiler was found**: all five twins behaved as their host modules the first time they ran, and so did the whole linker, banked, on its first link. One fault of the run-time was found and fixed: `disk.lth` kept 16 arguments and dropped the rest, so a link of more than 12 object files lost its last ones; it keeps 48 (`test_disk.py`, `test_the_linkers_44_arguments_are_all_given`). The host compiler's capacities sufficed.

## Result of L5: far calls three ways (2026-11-14)

The question: does one stub mechanism serve fixed memory, banks and disk overlays, and what does each cost? **Yes.** One stub form, written by the linker, serves banks and overlays; only the run-time routine differs. In the all-fixed case the stub disappears and the call is a plain `JSR`.

**Method.** Three modules written by hand in assembler (`lathe/tests/spike_l5/`): M (main, always fixed), A and B. The same module text is placed four ways by `l5build.py`, the spike's stand-in for the linker: all fixed on the emulator's default machine and on Wendy 2; A and B in banks 1 and 2 of Wendy 2 (`--machine wendy2c --disk DIR`, with each bank loaded from its own file at start-up through the `$F800` file ports); A and B in overlays 1 and 2 of a 4 KB window at `$8000` on the default machine, loaded through the host file services (`$F012`, `$F018`). `asm/pyasm.py` assembles each image, again until no address changes. `lathe/tests/test_spike_l5.py` builds and runs all of them and checks the output and the numbers below.

Every configuration prints the same results, and Wendy 2 adds two lines:

| Case | What it checks |
|---|---|
| nest | M → A → B → A: the result in A, X and carry comes back through three return paths. |
| rec | Mutual recursion between A and B, 20 levels, the argument saved on the stack. |
| ptr1, ptr2, ptr3 | Calls through a function pointer: M to B, A to B, and A to A through A's own stub. |
| irq (Wendy 2) | A VIA timer interrupt every 307 cycles, 512 times through a loop of far calls; the handler makes a far call of its own into bank B. No call comes back wrong. |
| port (Wendy 2) | Port B bits 5-7 (the LCD's E, an LED, PB7) are as set before the far calls. |
| loads (overlays) | 49 loads for the run. |

Arguments in static slots need nothing: `b_mid` keeps its parameter at `$0200`, in fixed memory, seen from every bank.

**The stub** (6 bytes, in fixed memory, one per function in a window that is called from outside its bank or whose address is taken):

```
STUB_f  JSR fc_call
        .byte BANK          ; port B bits 0-4 for a bank; the overlay's number for an overlay
        .word f-1
```

**The bank routine** (`rt_bank.s`, NMOS instructions only, 101 bytes). `fc_call` reads the stub's three bytes through its return address, puts on the stack the address of `fc_back` and the bank now in the window, switches port B (keeping bits 5-7) and enters `f` by `RTS` with A, X, Y and the flags as the caller left them. `fc_back` puts the old bank back and returns with A, X and the carry as `f` left them. The bank to restore is on the stack, never in a variable, so nesting, recursion and far calls from an interrupt handler are safe. Its scratch bytes are used only between `PHP` / `SEI` and `PLP`.

**A faster stub** (`rt_bankf.s`, 12 bytes: `PHA` / `LDA #BANK` / `JSR fc_enter` / `JSR f` / `JMP fc_leave`) makes the call itself, so the routine reads nothing through the return address (62 bytes).

**The overlay routine** (`rt_ovl.s`, 107 bytes and a 30-byte loader). If the overlay is in the window already, it enters `f` directly and `f` returns straight to the caller. Otherwise it loads the overlay and `f` returns into `fc_back`, which loads again the overlay that was in the window at the call. The loader is not reentrant: an interrupt handler must not reach an overlay.

**Measured** (exact CPU cycles from the emulator; "far call" is the cost over a plain `JSR` and `RTS`, which cost 12):

| | All fixed | Banks, 6-byte stub | Banks, 12-byte stub | Overlays |
|---|---|---|---|---|
| Bytes per stub | 0 | 6 | 12 | 6 |
| Bytes of the routine | 0 | 101 | 62 | 107 + 30 (loader) + the board's file reader |
| Cycles a far call and its return add | 0 | 182 | 130 | 82 with the overlay in the window |
| Two nested far calls (M → B → A) | 0 | 364 | 260 | 2 loads |
| Loading | none | 21 cycles a byte at start-up (`$F800` ports) | the same | 43 cycles a byte at each load (host services), about 200 more a load |
| Extra hardware stack per far call | 0 | 3 bytes | 3 bytes | 3 bytes (0 when in the window) |

- **The stub mechanism is one mechanism.** The program text is identical in all four builds; only the linker's choice of what a name means (the function or its stub) changes.
- **The 6-byte stub is the better choice for the compiler.** It costs 52 cycles more a call than the 12-byte one, but the compiler needs about 95 stubs (`configurations.md`): 570 + 101 bytes resident against 1,140 + 62. At about 6 far calls a source line the difference is about 300 cycles a line.
- **Overlays are cheap only while the window holds the right overlay.** A call into the other overlay and back costs two loads: 2,100 cycles for 45 bytes here, about a million for a 24 KB overlay. Overlays suit code used rarely, never code called from the other side of the window several times a line.
- **Interrupts and banks work together** with the reentrant routine: in the timer test the handler ran, and made its far call, at least 256 times (the test requires it; the run's 3.9 million cycles at one interrupt every 307 suggest about 12,000), at many different points inside the main loop's far calls, without a fault. A 65C02-only routine (`PHX`, `PLY`) would save perhaps 10 to 15 cycles a call *(estimate)*; the NMOS routine was kept so that one routine serves every board.
- **The emulator needs no change** for this: Wendy 2 with `--disk` has the file ports, and the default machine has host files ([`configurations.md`](configurations.md), "Where the banked compiler can run").
- **Decided by this spike:** the `farcall` entry of the environment names a routine of one of two kinds, bank or overlay, with this 6-byte stub; `place` is by module. How the compiler's modules may call each other across banks is in [`configurations.md`](configurations.md).

## Size for a 128 KB ROM: the source side, measured (2026-11-17)

The goal: the compiler and the linker in one 128 KB ROM, eight banks of the module of 16,272 bytes each (`$8050-$BFDF`), 130,176 bytes, with each tool's resident part and constants stored there too. Measured with `lathe/tests/rom_report.py`, which builds the image as `test_bbc_toolchain.build_image` does (the tools' ROM forms, `BBCFS 0`) with `lathe/tests/lk_judged.py` as the linker (it links as `link.py` does and notes each bank's contents as the linker judges them, before zero page shrinks the code, and as placed). The image it builds is the one the tests build, byte for byte. What follows is the source side: what the tools' own source holds; what the compiler emits for each construct is not here.

**The budget.** The image holds 138,512 bytes: the module's code and tables 495; the compiler 86,082 (banks 66,599, resident part 13,989 of which 1,746 are 291 stubs, `err`'s messages in slot 13 5,494); the linker 51,935 (banks 42,923, resident part 9,012 of which 456 are stubs). Eight banks are 8,336 bytes too few however they are packed, seven 24,608. The DFS build (`BBCFS 1`) adds about 880 more (`bbc.md`, "What it costs").

**The packing.** A tool's bank file must fit a bank whole, and the linker judges it as written: the compiler's banks are 74,988 bytes so judged (66,599 placed: 4.61 banks), the linker's 50,684 (42,923: 3.11 banks). `bbcrom.py` puts the resident parts and the slot constants only in bank 0 and in banks no program's code is in, so the 53,198 bytes at the ends of the ten code banks hold nothing; the image takes banks 0 to 11.

| Bank | Judged | Placed | Left, as judged |
|---|---|---|---|
| compiler 1: `expr` | 15,717 | 14,756 | 555 |
| compiler 2: `gen`, `lathec` | 15,154 | 13,533 | 1,118 |
| compiler 3: `decl`, `parts`, `out` | 15,441 | 13,314 | 831 |
| compiler 4: `reg`, `inlines` | 14,367 | 12,533 | 1,905 |
| compiler 5: the rest | 14,309 | 12,463 | 1,963 |
| linker 1: `lk_envf`, `lk_err`, `lk_file`, `link` | 9,025 | 8,292 | 7,247 |
| linker 2: `lk_scan`, `lk_name` | 10,714 | 8,910 | 5,558 |
| linker 3: `lk_graph`, `lk_boot`, `lk_win` | 9,176 | 7,605 | 7,096 |
| linker 4: `lk_alloc` | 10,285 | 8,307 | 5,987 |
| linker 5: `lk_map`, `lk_emit`, `lk_place`, `lk_fix`, `lk_out`, `lk_op` | 11,484 | 9,809 | 4,788 |

- *Measured:* letting `bbcrom.py` put the resident parts in the ends of the code banks too (the copy list has a bank for each entry, and the copier reads any bank) takes the image from twelve banks to eleven; the module's tables grow by 32 bytes, and `test_bbc_toolchain.py` passes. Not committed.
- So eight banks need the linker's code in three banks and the module's own code in the end of a code bank (its service code reaches bank 0 by `LDA latch`; another bank would do as well). Three banks hold 48,816 judged bytes: the linker is 1,868 over before any packing loss. Ten banks of code would remain otherwise.
- *Counted:* without the bytes it judges before shrinking (the rule of `lk_place` and [`configurations.md`](configurations.md), "Sizes": whether a program links cannot depend on what zero page promotion chose), the compiler's banks would have 8,389 bytes more room and the linker's 7,761.

**The largest modules** (bytes in the ROM; code per line of code, not blank and not only a comment): `expr` 14,816 (9.7), `gen` 12,969 (6.3), `decl` 10,385 (6.3), `reg` 7,660 (6.3), `err` 6,140 (5,494 of it messages), `kernel` 5,742 (6.9), `inlines` 5,392 (6.7), `asmblock` 4,106 (4.9); `lk_alloc` 8,511 (9.8), `lk_tab` 5,661 (8.3, all resident), `lk_graph` 5,475 (8.0), `lk_scan` 4,794 (6.0), `lk_name` 4,449 (7.7), `lk_envf` 4,186 (5.2), `lk_map` 3,674 (7.1), `lk_err` 3,460 (2,839 of it messages). The functions most costly for their lines: `expr.variable` 1,093 bytes for 59 lines (18.5 a line), `expr.initial_value` 495 (17.7), `expr.name_statement` 422 (16.9), `expr.for_statement` 1,154 (13.4), `kernel.sym_find` 608 (14.1, resident), `kernel.thaw` 822 (11.9, resident); `lk_tab.add_waiting` 315 (19.7), `lk_alloc.take` 426 (18.5), `lk_alloc.start_choices` 798 (17.0), `lk_envf.check` 515 (17.2), `lk_tab.build_chains` 792 (16.5, resident).

**What both tools hold** (resident, code, constants and stubs): `bbc` 671 and 674, `rt_bbc` 402 and 402, `rt_math` 353 and 290, `sys` 76 and 82, `disk` 15 and 15, start-up 86 and 71: 1,603 and 1,534. The copies differ in their addresses (each tool's slots, variables and zero page are its own), so no copy can serve both as it is. Beyond the libraries the tools share little: two decimal printers in each (`err.put_decimal` 84 and `lathec.decimal`, a reader, 130; `lk_err.put_word` 125 and `lk_map.decimal` 99), number readers (`lex.number` 121, `lk_envf.token_number` 138). The object format is written by one and read by the other.

**Messages.** *Counted:* the compiler's are 5,494 bytes (132 lines), the linker's 2,839 (62 lines and its fixed texts): 8,333, 6 % of the image. A table of the words used more than once, each written as one byte, would make them 5,329 bytes in all with the tables (128 words; 2,736 bytes less, the two tools each with its own table) before the code that expands them.

**Recursion.** *Counted, by a copy of the host compiler noting each saving call:* `expr` makes 97 saving calls, which push 464 bytes of frame (12 bytes of code a byte: about 5.5 KB); `decl` 2, 17 bytes. 92 of the bytes pushed are of locals and parameters that no later line of the function names (about 1.1 KB of code); others are locals declared, or state saved, before a call that does not need them.

**Changes measured** in the twins only, one at a time against the image above (bytes of the whole image; the twins were then not byte-identical with the host, and nothing was committed):

| Change | Bytes | Where it shows |
|---|---|---|
| `expr.here()` for the 28 `err.position(lex.line, lex.col)` of `expr` | −327 | bank 1 (−489 judged) |
| `for_statement` saves its loop state after the limit, not before the first expression | −144 | bank 1 |
| `case_statement`'s selector in a function of its own, so its position and type are not saved at each body | −134 | bank 1 (−161 judged) |
| `kernel.flags_of`, `kind_of`, `value_of`, `params_of`, `type_of` for the 184 calls of `byte_of`/`word_of` with those columns (placed in bank 5: far calls from the other banks) | −321 | banks; resident +22 (stubs) |
| the same accessors, each with its own `with` block (fixed: no far call) | −148 | resident +240: the compiler's code range is then 149 bytes over |
| `kernel.name_word` and `name_set_word` plain functions, not `inline` (each with a block of `NAMES`) | −332 | resident −424; banks +92 |
| `lk_tab.add_wk` and `sub_wk` for the 7 read-modify-writes of work words in `lk_alloc` | −133 | bank 4 −189 (−224 judged), resident +56 |
| all of them but the fixed accessors, together | −1,394 | compiler −1,261 (resident −402, banks −1,127 judged), linker −133 |

Together they build an image with which `test_bbc_toolchain.py` passes.

**Features**, *counted* as the code of the functions that serve only them (a lower bound: the code inside shared functions and their messages are not counted): `inline` 6,881 in the compiler; the embedded assembler 3,795 (with its tables, 4,106 is the module); conditional compilation 771; banked data in the compiler 1,241; records, enumerations and function types in the compiler 2,047, function classes in the linker 3,281; interrupt functions 123 in the compiler and their contexts 1,553 in the linker; zero page promotion 5,204 of `lk_alloc`, of which the bounds that spare layouts 519; windows, banks, far calls and overlays 6,252 in the linker; the map 3,622, of which its slot and class parameter lines 1,472; the start-up and stubs written by `lk_boot` 1,194; the command file and arguments 430. The DFS name mapping is 0 in this image (`BBCFS 0`); 65C02 support about 100 (a few tables and an option).

**What follows.** Eight banks need about 8.4 KB less in all, the linker's code in three banks, and the module's code and the resident parts at the ends of code banks. Only the messages are near that size alone: kept in a file on the disc, they free 8,333 bytes of the ROM, 2,839 of them in the linker's first bank, after which its code packs into three banks (a search over the module sizes as judged, with 971 bytes to spare in all, 129 in the fullest bank). The refactorings above and more of their kind are worth about 2 to 3 KB; sharing the libraries' resident copies at most 1.5 KB, less what the mechanism would cost. Seven banks would need about 25 KB less and the compiler's code in four banks: that is not reached without cutting `inline` and the embedded assembler as well.

### Built: the compiler's source made smaller (2026-11-17)

Four of the changes measured above, built in host and twin with every compile byte for byte as before, and two more; bytes of the compiler for the eight-bank image (its banks as placed, slot 13's constants and its resident part, `test_bbc_rom128.build_tools`), main RAM free in the eight-bank ROM form at ADFS's PAGE with `BBCFS 2`:

| Change (commit) | Compiler | Resident | Main RAM free |
|---|---|---|---|
| before (05824fd) | 82,147 | 14,046 | 51 |
| `kernel.name_word` and `name_set_word` plain functions with a block each (9f5ada5) | 81,692 (−455) | 13,605 | 492 |
| `expr.here()` for the 28 `err.position(lex.line, lex.col)` (d7d6d3b) | 81,362 (−330) | | |
| `line_end()` in EXPR and DECL for the 28 `lex.expect(lex.T_NL, err.E_NL_EXPECTED)` (3d4c852) | 81,264 (−98) | | |
| `name_symbol` and `name_set_symbol` without a block; `name_end`'s walk reads the link in line (713d244) | 81,278 (+14) | | 547 |
| `sym_find`, `thaw`, `freeze` and the `built_` walks through `name_byte` and the rest, out of fixed memory; one layout for both images (ff50d27) | 81,091 (−187) | 11,740 | 2,357 |
| `kernel.flags_of()` and five more accessors of one column, fixed (da24c33) | 80,838 (−253) | 11,932 | 2,166 |

In all 1,309 bytes, and the gate's account (`test_bbc_rom128.py`) from 4,463 bytes over to 3,154; the compiler's banks as judged 15,466, 15,396, 15,343, 12,342 and 13,648. The cycles of each step are in [`configurations.md`](configurations.md), "Kernel's functions out of fixed memory, and accessors of one column": the self-compile 2.0 % faster on Wendy 2 and 6.8 % on the BBC (most of that the layout's fewer far calls). `name_word` as a plain function alone cost 2.5 % on Wendy 2 and 1.7 % on the BBC, which `name_end`'s walk, the hottest of its calls, reading the link in its own block took back.

Looked at and left, each under about 60 bytes: `here()` in PARTS (3 calls) and DECL (1); `lex.expect` with the other tokens (at most 7 calls of one pair); helpers for the commonest `err.fatal` numbers (23 calls of error 44 across eight modules, 2 bytes a call); `expr.variable`'s three `set_word` of a slot and two `lasting_variable` calls (about 50); a pointer in `name_word` and its kin for the second byte (22, fixed). The pairs `line = lex.line` / `col = lex.col` and `err.position(line, col)` (35 and 37 in EXPR, about 24 and 12 bytes each) are the largest pattern left, but a position kept for an error belongs to ERR. The accessors placed in kernel's bank, with no block, would save more bytes but make most of the column reads far calls.

### Built: the messages in a file, the linker in three banks (2026-11-17)

The first line of "What follows", built ([`bbc.md`](bbc.md), "The message file" and "The 128 KB module"). The BBC's ROM forms of both tools read the texts of their errors from `LATHERR` on the disc (9,258 bytes, written by `lathe/host/driver/msgfile.py` from the host's tables), and give the number alone without it. Out of the ROM: the compiler's 5,494 bytes (slot 13's constants) and 249 of fixed code, the linker's 2,803 bytes and 187 of code of its bank 1; in: a reader of 168 bytes in the compiler (fixed, with `bbc.open_unmapped` and `bbc.seek`) and of 77 in the linker's bank 1 with 25 fixed. Then the linker's banks 2 and 3, 199 and 416 bytes over as judged, by refactoring in host and twin (`lk_tab.add_wk`, `lk_alloc.each_candidate`, `larger`: 653 bytes of bank 3) and by lk_boot in bank 1. The gate passes: **125,254 bytes in use of 130,304, 4,523 free** (3,326 in the ADFS build) on 05824fd's compiler, and with the compiler's source made smaller (above) **123,970 in use, 5,815 free** (4,610 in the ADFS build); the fullest bank 241 bytes below a bank as judged (338 in the ADFS build). Both tools from the eight-bank image: the self-compile 897.7 million cycles, the compiler's link 2,961 million, the rebuild loop 4,008 million, on two ADFS discs 4,026 million; main RAM at ADFS's PAGE in the eight-bank form 127 bytes free for the compiler (51 before), 1,581 for the linker (1,646). Merged with the compiler's smaller source: the self-compile 877.0 million, the compiler's link 3,463 million (the compiler is a larger program to link), the loop 4,484 million, on two ADFS discs 4,504 million; main RAM at ADFS's PAGE 2,253 bytes free for the compiler.

## Size for a 128 KB ROM: the generated code, measured (2026-11-17)

The question: how much of the two tools' code is more than the code model needs, and which changes to the code generator, the code model or the run-time would pay for themselves when the compiler (which is in the ROM too) compiles itself and the linker. Measured on the compiler as `lathec-bbc.env` builds it and the linker as `linker-bbc.env` builds it, from `main` at d92d442. "Measured" is a build; "counted" is a scan of the code as built; "estimated" says how.

**The tools** (in `lathe/tests/`): `code_listing.py` lists a linked program's code instruction by instruction from its object files and map, with each operand's symbol and slot and its size as placed (zero page shrinking applied; every function's total is checked against its F line). `construct_lathec.py` stands in for `lathec.py` (through `LATHE_COMPILER`) and records, for every entry of the function buffer, which compiler functions were on the stack when it was added; the files it writes are the host compiler's. `construct_report.py` builds both tools so and gives every placed byte a construct, with a table of calls by callee. `idiom_report.py` counts wasteful patterns, `frame_report.py` the saving calls' pushes and pops and other forms of them, `stub_report.py` the far-call stubs, `c02_report.py` what the 65C02's instructions would save.

**What the ROM would hold today**: the compiler's five bank files, 66,599 bytes, its slot 13 constants, 5,494, and its resident part, 14,059; the linker's five bank files, 42,923, and its resident part, 9,082; the module's own code, about 500: 138,650 bytes, where eight banks hold 130,176 (16,272 each between the 80-byte header and `$BFE0`). Code is 77,684 bytes in the compiler (76,058 of its own modules, the rest `bbc`, `rt_bbc`, `rt_math`, `rt_frame`, `sys`, `disk`) and 48,100 in the linker (46,570 of its own); stubs 1,746 (291 of them) and 456 (76); constant data 6,722 (5,494 of it err's messages) and 3,449 (2,795 of it lk_err's).

### Where the bytes are, by construct (counted)

Bytes as placed of the tools' own modules (not the run-time modules), by the compiler function that emitted them (`construct_report.py`):

| Construct | Compiler | % | Linker | % |
|---|---|---|---|---|
| call: the `JSR` (or the `JMP` of a tail call) | 11,307 | 14.9 | 6,198 | 13.3 |
| call: register arguments loaded before the `JSR` | 10,903 | 14.3 | 4,589 | 9.9 |
| call: arguments worked out into the callee's slots | 6,928 | 9.1 | 3,218 | 6.9 |
| function entry: register parameters stored | 2,076 | 2.7 | 1,183 | 2.5 |
| saving calls: the frame pushed and popped | 5,851 | 7.7 | 0 | 0 |
| call: values saved before a call | 172 | 0.2 | 199 | 0.4 |
| return: the result into A, X or C, `RTS` | 1,397 | 1.8 | 1,091 | 2.3 |
| moves: assignments and other stores | 9,573 | 12.6 | 4,090 | 8.8 |
| arithmetic: `+ - & \| ^`, shifts, `INC`, `DEC` | 6,326 | 8.3 | 7,888 | 16.9 |
| arithmetic: `rt_math` call set-up | 249 | 0.3 | 128 | 0.3 |
| comparisons `==` `!=` | 5,995 | 7.9 | 2,115 | 4.5 |
| comparisons `<` `<=` `>` `>=` | 2,241 | 2.9 | 2,715 | 5.8 |
| conditions: their branches | 4,824 | 6.3 | 2,616 | 5.6 |
| conditions: a `bool` as a value or in C | 1,454 | 1.9 | 695 | 1.5 |
| branches: the `JMP` of a long branch (108 and 231 of them) | 324 | 0.4 | 693 | 1.5 |
| loops: `for`, `while`, `loop` | 1,849 | 2.4 | 2,585 | 5.6 |
| `if`, `case`, `break`: jumps and selectors | 820 | 1.1 | 466 | 1.0 |
| arrays: the element address of a big array (a zero page pointer) | 1,081 | 1.4 | 4,003 | 8.6 |
| arrays: an index register loaded | 914 | 1.2 | 387 | 0.8 |
| pointers: Y loaded for `(zp),Y`, or a pointer copied to zero page | 289 | 0.4 | 514 | 1.1 |
| `with` blocks: map and unmap | 916 | 1.2 | 662 | 1.4 |
| initial values (`$init`) | 567 | 0.7 | 531 | 1.1 |
| **total** | **76,058** | | **46,570** | |

- **Calls are half the compiler and a third of the linker**: 3,794 call sites in the compiler (303 of them already tail `JMP`s), 2,093 in the linker. With the entry stores, the slot stores and the saving calls they are 37,237 bytes of the compiler's 76,058 (49 %) and 15,387 of the linker's 46,570 (33 %). The callees with the most bytes at their calls (call sites, then the bytes of the `JSR`s, the register set-up, the slot stores and the entry stores): `kernel.byte_of` 198 (594, 1,182, 0, 6: 1,782 in all; most often `LDY #2 / LDX s+1 / LDA s`), `err.fatal` 265 (1,327; `LDA #n`), `err.position` 101 (1,192), `kernel.word_of` 89 (804), `kernel.set_byte` 58 (663), `kernel.put` 75 (562), `kernel.set_word` 33 (461), `lex.expect` 65 (459); in the linker `lk_tab.set_wk` 90 (939), `lk_sym.row_of` 66 (484), `lk_tab.wk` 121 (423), `lk_tab.add16` 29 (345).
- **The saving calls**: 74 in 43 functions of `expr`, 5,578 bytes of `LDA slot / JSR rt_frame.push` and `JSR rt_frame.pop_y / STY slot`, 1 to 21 bytes saved a call (4 to 7 at most calls); `expr.for_statement` alone has 624.
- **Zero page is not what makes it large.** Built with a larger `zeropage` range (measured; the BBC's is `$00-$8F`, and full): 8 bytes more (`$97`) saves 290 bytes of code over both tools, 16 more 453, 32 more 833, the whole page (`$FF`) 2,752 (2.2 %). Of the BBC's zero page outside `$00-$8F`, only `$A8-$AF`, the workspace of a `*` command, might be taken, for the 290.
- **Far calls.** 291 stubs in the compiler, all but 19 for a function called from another bank, with 1,204 call sites through them; 76 in the linker (233 call sites from banks, 13 from fixed code). A 5-byte stub that calls an entry of its bank (`PHA / LDA #bank / JMP`, 6 bytes a bank) would save 261 and 46 bytes (counted), for about 10 cycles more a far call. A table, or a shared trampoline with an index, needs the same 3 bytes of bank and address for each function and a way to find them, so it is not smaller. Fewer banks cut stubs only where a module's callers come to share its bank.

### Patterns larger than they need be (counted)

`idiom_report.py`, over every function both maps keep (run-time modules included): occurrences, with their bytes in brackets. The code generator is already tight at the level of single instructions: a load of what a register holds was found once in 125,648 bytes, a store then a load of the same into another register 16 times.

| Pattern | Compiler | Linker | Bytes each |
|---|---|---|---|
| a long branch (Bxx over `JMP`) that could branch to a `JMP` to the same place within reach | 32 (96) | 102 (306) | 3 |
| a word worked out in A and X (`TAY` ... `TAX` / `TYA`) and then stored to memory | 31 (93) | 95 (285) | 3 |
| the same tail twice in one function, ending in `RTS` or `JMP` (cross-jumping) | 95 (520) | 31 (154) | its length less 3 |
| a store into a temporary that no instruction reads | 103 (240) | 60 (124) | 2 or 3 |
| a register parameter stored on entry and never read | 120 (253) | 41 (90) | 2 or 3 |
| `JSR` then `RTS` after a join (a `JMP` to a `JMP` made `RTS`) | 93 | 30 | 1 |
| a word compared with a constant whose low byte is 0 (`LDA lo / CMP #0` before `SBC`) | 12 (53) | 12 (51) | 4 or 5 |
| `CMP #0` after a `JSR` whose byte result is tested (it needs a convention: Z of a byte result) | 23 (46) | 25 (50) | 2 |
| `CLC` with the carry known clear, `SEC` with it known set | 41 | 87 | 1 |
| the same element pointer of a big array set up again in a function | 3 (33) | 5 (55) | 11 |
| repeated straight-line sequences inside one function that a subroutine of the function could hold (an upper bound, the saving calls' pushes and pops left out) | 2,055 | 1,994 | |
| repeated sequences across functions: the commonest is the call `err.position(lex.line, lex.col)`, 24 to 35 times, 12 to 15 bytes each | about 300 | | |

### Experiments (measured)

Made in the host compiler only (the twins do not follow), each behind an environment variable, on the side branch `experiment-codegen-size-a6fb85`. Correctness: `test_cases.py` (every run of the corpus right; the snapshot cases differ, as they must), and `test_src_selfhost.py` with `LATHE_SELFHOST=1` run with the compiler built by the changed host: the Lathe compiler so built compiles all eighteen of its modules on Wendy 2 to the files the unchanged host writes.

| Change | Compiler | Linker | Python lines | Cycles of the self-compile on Wendy 2 |
|---|---|---|---|---|
| saving calls push and pop through a list of the slot bytes' addresses in constant data: `LDA #<list / LDX #>list / JSR rt_frame.push_list` before the call, `JSR rt_frame.pop_list` after it (`LATHE_X_LIST`) | code −5,073, constant data +1,036, variables +6: **−4,037** (bank 1, `expr`, −3,720; the two routines, 109 bytes, in the resident part) | 0 | about 30 in `gen` | 884.2 million against 849.2 (+4.1 %: the routines call `push` and `pop_y` for each byte; written to store directly they would be about as fast as now, estimated) |
| a long branch goes to a `JMP` to the same place within reach (`LATHE_X_CHAIN`) | −51 | −144 | about 45 in `fbuf` | |
| stores into temporaries nothing reads are taken out (`LATHE_X_DEADTEMP`) | −246 | −124 | about 28 in `fbuf` | |
| a word compared with a constant whose low byte is 0 compares the high bytes only (`LATHE_X_CMP0`) | −77 | −88 | about 14 in `cond` | |
| a `JSR` before a `JMP` made `RTS` becomes a `JMP` (`LATHE_X_JOIN`) | −67 | −25 | about 10 in `fbuf` | |
| the four above together | −438 | −387 | | 846.7 million (−0.3 %) |

At about 9 bytes of compiled twin a line of Python, the four small changes cost about what they save: 825 bytes saved for about 850 of compiler. Only the frame lists pay clearly, about 3.8 KB net with the compiler's growth counted. The list is constant data of the caller's bank, named by fix-ups of kinds 7 and 8 (with kinds 2 and 3 the lists were fixed and the resident part did not fit by 663 bytes); the routines need two zero page pointers, which as written are variables of the module, shared by an interrupt handler that makes saving calls (a real version would give them to the routines' own frames).

**The 65C02.** The compiler uses the 65C02's instructions only in the entry and exit of interrupt functions: built with `cpu 65c02` both tools are the same size as for the NMOS 6502 (measured). Counted on the NMOS code, `STZ` for `LDA #0 / STA` would save 858 and 670 bytes, `BRA` for a near `JMP` 287 and 124, `INC A` and `(zp)` a few more: about 2.0 KB of both, 1.6 %.

### A denser form for cold code (estimated)

Three functions of `lk_map` translated by hand into a compact interpreted code (a 16-bit accumulator; a one-byte opcode with the slot number in it for loads and stores of the function's own slots, which would have to be contiguous and outside zero page; two-byte calls through a table of callees; three-byte loads of a word element of a big table; a five-byte header at the entry): `symbol_line`, 96 bytes of 6502 code, would be about 40; `decimal`, 99, about 42; `begin`, 39, about 28: 0.4 to 0.7 of the native size, call-heavy code at the top of the range. The cold code of both tools (the environment reader, the map, errors, the main programs, the embedded assembler, the interface writer) is about 18 to 20 KB, so about 8 KB less at best, for an interpreter of 600 to 900 bytes in each tool and 3 to 10 times the cycles in that code. But the compiler would need a second code generator beside GEN, REG and COND, in host and twin, of several KB of compiled code in the same ROM: more than the saving. Not worth it while the compiler must compile itself.

### What the code generator can give

Taking only what pays with the compiler's growth counted, in order: the saving calls' lists (measured, about 3.8 KB net); an error call as `BRK n` for the functions that never return and take one constant (`err.fatal`'s 265 calls, `lk_err.fail`'s 35, and the 48 calls of `lk_envf.bad` and `lk_scan.damaged`, which take none), with `BRK` decoded as two bytes by the linker (counted 950 bytes, against about 200 of compiler and handler: about 0.75 KB net); the bank a `with` block replaces kept on the 6502's stack by `rt_with.map` and taken back by `unmap` instead of a temporary (counted about 520, for about 20 cycles more a block); subroutines of a function for its repeated sequences (counted at most 4 KB, perhaps half of it found by a pass the 6502 can afford, for about 1 KB of compiler: 1 to 1.4 KB net); the 5-byte stubs (about 0.3 KB). In all **4.4 KB (the first two) to 6.5 KB**: the ROM's contents would go from about 138.7 KB to 132 to 134 KB, still above the 130.2 KB of eight banks, before any loss to packing modules into banks. The generated code is near what this code model allows: half the compiler is calls, and the rest of the size is in what the sources ask for (tables of more than 256 rows, accessor calls, recursion in EXPR, 8.3 KB of messages). The rest of the way to 128 KB must come from the sources and the layout.

### Built: saving calls through a list (2026-11-17)

The first change above, in the host compiler and its twin, byte for byte alike ([`code-model.md`](code-model.md), "Recursion"). A saving call is `JSR rt_frame.push` and the list, the call, then `JSR rt_frame.pop` and a `JSR` to the list. The list follows `push`'s `JSR` in the caller's code, as instructions that nothing runs: `LDA #n` (the frame's bytes; the label the last `JSR` goes to), then `ORA slot-i,Y` for each word of the frame and `LDA slot-i,Y` for a slot's odd last byte, i the entry's index, so that `rt_frame` reads the slot through `(pointer),Y` with the index it already has in Y; at most 84 entries a list. `push` takes the bytes of the frame stack at once and returns past the list; `pop` reads the list's address from the operand of the `JSR` after its own and returns past that. 11 + 3 bytes an entry, against 12 bytes a byte before.

**The forms considered** (counted on the compiler's 74 saving calls that save something, 481 bytes in 306 slots, 131 of one byte and 175 of two):

| Form | Lists | At the calls | Note |
|---|---|---|---|
| in line, as before | | 5,772 | 12 bytes a byte |
| the experiment: constant data, 2 bytes a byte and a count, `LDA #<l / LDX #>l` | 1,036 | 740 | the list's address on the frame stack |
| constant data, words then bytes, 2 bytes a slot and 2 counts | 760; 580 shared | 740 | 31 calls push the same set as another call of their function: 55 lists |
| the same, the two counts as nibbles of one byte | 686; 525 shared | 740 | at most 15 of each |
| code at the function's end, 3 bytes an entry and `LDA #n`, `LDA #<l / LDX #>l` | 815 shared | 740 | the compiler's function buffer would need a label as an immediate operand |
| code after `push`'s `JSR`, the list's address on the frame stack | 1,066 | 444 | built first: 134,339 bytes in the image |
| **code after `push`'s `JSR`, and a `JSR` to it after `pop`'s, as built** | 1,066 | 666 | |

Constant data is in the image once: a recursive function linked for two contexts (the main program and an interrupt handler) has two copies, and a list in constant data could name only one copy's slots. Code is copied with its function and lives in its function's bank, so a list in the code is right in every case without a change to the linker or the object format (its operands are fix-ups of kind 1 to the function's own slots, with negative addends, and `abs,Y` instructions never shrink). The first form built kept the list's address on the frame stack, 2 bytes a saving call, as the experiment did; then the compiler on the BBC (`test_src_lathec.py`, `LATHE_LATHEC_BBC=1`) overflowed the frame stack on `tests/cases/err/nested_calls.lth` before it reached error 88, eight calls deep, each level 4 saving calls that save something; so `pop` finds the list through the `JSR` after its own, 3 bytes more a call (269 bytes in the image), and the frame stack holds the frames and nothing else, as before. In line, a frame of one byte would be 2 bytes smaller (12 against 14), but the compiler has two such calls, and keeping the in-line form beside the list would cost it about 150 bytes, so it is gone, with `rt_frame`'s routines of one byte. A frame of more than 84 entries has a list for each 84 (`tests/cases/e2e/rec_big_frame.lth`).

**What it gave** (`rom_report.py`, against the figures at the top of the source side's section): the image 138,512 bytes to **134,608** (−3,904), 4,432 more than eight banks hold; the compiler 86,082 to 82,178; the linker 51,935, unchanged (it has no saving calls). The compiler's banks, judged and placed: bank 1 (`expr`) 15,717 and 14,756 to 11,778 and 10,972; bank 2 15,154 and 13,533 to 15,444 and 13,725 (`gen`'s twin: what the change adds to the compiler, 290 bytes judged, 192 placed); bank 3 15,441 and 13,314 to 15,298 and 13,095 (`decl`'s two saving calls); bank 4 12,533 placed to 12,415 and bank 5 12,463 to 12,400, judged the same (zero page chosen otherwise, now that the lists' entries are not uses of the slots). Resident, 13,989 to 14,077 bytes: `rt_frame` 42 to 171 (`push` 70, `pop` 92), the code kept fixed 45 smaller, a stub more (`fbuf.keep_as_written`), `gen`'s two names 2 bytes shorter.

**The 128 KB module** (`test_bbc_rom128.py`, merged after this was built): the tools are 4,453 bytes over the eight-bank image, from 8,363; the compiler's five banks there, as judged, 11,778, 15,444, 15,571, 14,716 and 13,687 bytes of 16,272 (`expr` 3,939 smaller, `gen`'s bank 290 larger, all fitting); the linker's three are still 572, 199 and 416 bytes over. Main RAM free in the eight-bank ROM form: 1,678 (`BBCFS 1` 1,652). At ADFS's PAGE (`$1F00`, `BBCFS 2`, merged after this too) the compiler's ROM form has 16 bytes of main RAM free, 104 before, its split moved from `$5600` to `$5640`, and the developer's form's from `$5880` to `$58A0` (it was 1 byte over); in the eight-bank ROM form there it has 51 bytes free, 134 before.

**Cycles of the self-compile**: on Wendy 2 849.6 million to 850.1 (+0.06 %; `expr` −5.2 % for its smaller output; the fifteen modules whose source and output did not change +0.26 %); on the BBC in the ROM form 945.7 million to 946.6 (+0.10 %). The rebuild under DFS names (`test_bbc_dfs.Loop`) 4,504.9 million to 4,338.6 (−3.7 %, not broken down: the objects it compiles and links are smaller). The compiler makes about 57,700 saving calls that save something in the self-compile, of 5.35 bytes on average (counted with a routine of known cycles added to each, and to the old `push`); the in-line form spent about 22.8 million cycles on them, at about 75 a byte (estimated from its instructions).

**Memory.** The BBC, main RAM free of 26,111: ROM form 1,731 to 1,642 (`BBCFS 1` 1,705 to 1,616); developer's form 5,427 to 5,334 (`BBCFS 1` 4,991 to 4,898). The splits moved in `lathec-bbc.env` (its `code` and `data` lines, the two `;rom` lines and the comment that names them): the ROM form's from `$5000` to `$5020`, its code ending 35 bytes below it (22 with `BBCFS 1`, where it would have been 10 bytes over), the developer's form's from `$51A0` to `$5200`, its code ending 445 bytes below it (22 with `BBCFS 1`, where it would have been 74 over). Zero page `$00-$8F` is full before and after: `push` and `pop` each have two pointers and a byte in zero page in their own frames, which they share with functions not active with them, and `sp` is declared `zp`, so that the routines' instructions on them are judged as two bytes. Wendy 2 (`compiler-bank.env`): fixed code, stubs and constants 16,904 to 16,959 bytes, to `$7E3E` (449 left below `$8000`).

**Found:** `rt_frame.push` wrote a byte before it took it, and `pop_y` gave a byte back before it read it, so an interrupt handler that made saving calls between the two instructions changed the main program's frame (`tests/cases/e2e-michael/irq_recursive.lth`, on Michael and Wendy 2: 11 values lost in 68 rounds; with the two instructions of each routine the other way round it passes). `push` and `pop` take before they write and give back after they read.

**Not built.** A saving call in tail position need not save anything, but neither tool has one that saves a frame: `expr` has no `return f(...)` of a recursive function, and its three saving calls just before a `return` save nothing already. Bytes dead at the call: 97 bytes of locals and parameters, in 66 entries, that no later line of their function names (an upper bound: in a loop a name before the call may be read after it), 198 bytes of lists, and 4 calls whose lists would go, 44 more; knowing it at the call needs what comes after it, which the compiler, reading the source once with no tree, does not have: a second pass over each recursive function's text, in host and twin, larger than the 240 bytes it could save.

## Generated code, a second look (measured) (2026-11-18)

The question: which changes to the code generator would free ROM for features and for the messages, cheaply, after the first look above (whose peepholes netted about 0, and whose saving calls through a list were built). Measured on 8dd784a, the eight-bank image as `test_bbc_rom128.build_tools` builds it: **123,970 bytes in use of 130,304, 5,815 free**; the compiler's code 72,490 bytes (resident part 11,849), the linker's 47,698 (resident part 9,829). "Free" below is that account's free bytes, which takes every change in the compiler's and the linker's banks, resident parts and the module's own tables. "Measured" is a build; "counted" is a scan of the code as built; "estimated" says how.

**The tool**: `lathe/tests/codegen_report.py WORK MAP ...` counts, on any linked program's listing (`code_listing.py`), the four things below that it can see in the code: stores that nothing reads, repeated runs a subroutine of the function could hold, big-array element reads a routine could do, and `JSR` / `RTS` pairs (`test_codegen_report.py`). Its counts are within 5 % of the experiments' measured savings, except the big-array reads, whose knock-on effects (zero page freed, rt_math's two routines) make the measured saving 15 % larger.

### Reading the code

Listings of hot and cold functions of both tools (`reg.load`, `reg.direct`, `expr.variable`, `typetab.is_array`, `err.position`, `lk_tab.wk` and `set_wk`, `lk_err.begin`, `lk_sym.kind_of`, `lk_graph.scc_of`) show what the counts below say: single instructions are tight (register tracking leaves almost no load of a value already held), and what a 6502 programmer would not write is at a larger scale: (1) values stored that nothing reads, mostly the status half of `x, ok = f()` and register parameters that are never read again; (2) the same five to thirty instructions twice or three times in one function, an argument set-up, an element address, a copy; (3) arrays of more than 256 bytes reached through a zero page pointer worked out in line at each use, 15 to 35 bytes a use, 4,877 bytes of the linker and 664 of the compiler (counted); `lk_tab.wk` is 111 bytes for two such reads.

### Experiments (measured)

Each made in the host compiler only, behind an environment variable, as a diff in the scratchpad (not committed); the twins do not follow. Correctness: `test_cases.py` with the change (every end-to-end run right; only snapshot cases differ, as they must); `test_src_selfhost.py` with `LATHE_SELFHOST=1`: the Lathe compiler built by the changed host compiles all eighteen of its modules on Wendy 2 to the files the unchanged host writes (the changes were made to apply only to a source named by an absolute path, as `build.py` names them, so that the test's reference compile is the unchanged host's); `test_src_selflink.py` with `LATHE_SELFLINK=1`: the Lathe linker built by the changed host links hello, lextest, itself and the compiler on Wendy 2 to what the host linker writes. Cycles are Wendy 2's: the self-compile (`LATHE_SELFHOST_REPORT=1`, 834.3 million before) and the links of the linker and of the compiler (`LATHE_SELFLINK_REPORT=1`, 1,375.9 and 2,513.8 million before).

| Change | Free (from 5,815) | Compiler code | Linker code | Self-compile | Linking the linker / the compiler | Host lines |
|---|---|---|---|---|---|---|
| **A.** stores into a slot of the function that nothing in the function reads are left out (`LATHE_X_DEAD`) | 7,212 (**+1,397**) | −885 | −512 | 806.5 M (**−3.3 %**) | −4.2 % / −4.4 % | 30 in `fbuf` |
| the same, temporaries only (the first look's `LATHE_X_DEADTEMP`) | 6,166 (+351) | | | | | |
| **B.** repeated runs of a function become subroutines of it (`LATHE_X_SUBS`) | 8,487 (**+2,672**) | −860 | −1,804 | 849.9 M (+1.9 %) | +2.4 % / +4.2 % | 95 in `fbuf` |
| **C.** a big-array element read for its value is `JSR rt_math.elem8` or `elem16` with the array's address in line (`LATHE_X_ELEM`) | 7,732 (**+1,917**) | −74 (rt_math +103) | −1,843 | not measured (the compiler has 21 such reads) | **+22.9 % / +24.6 %** | 35 in `gen` and `expr`, 2 routines of 26 and 31 instructions |
| A and B | 9,835 (+4,020) | −1,711 | −2,301 | | | |
| A, B and C | 11,467 (**+5,652**) | −1,772 | −3,872 | | | |

**A. Stores nothing reads.** At `fbuf.finish()` the whole function is in the buffer, so a pass sees every instruction that names a slot of the function: a slot named by nothing but `STA`, `STX` or `STY` (absolute or zero page) is never read, and those stores go. Anything else that names the slot counts as a read: an indexed or indirect use, `INC`, an `@` (`#<`, `#>`), a saving call's list entry, an `asm` block (functions with an `asm` block are left alone). Of the 1,932 bytes the build dropped (as written, both tools and the run-time), 474 were stores into temporaries and 1,458 into parameters and locals: the status of `length, at_end = kernel.get(stream)` that the function never tests (`inlines.read` drops eight such stores), `found` in `gen.math_function`, a register parameter stored on entry and not read again (the first look counted 357 bytes of those alone). The program is no different but for the stores; a variable that is never read keeps whatever it held, which only someone reading memory in a debugger would see. *Estimated in the twin:* about 30 lines of `fbuf.lth` (two walks of the buffer and a 32-byte set of slots read), about 160 to 210 bytes at fbuf's 5.3 bytes a line: **net about +1.2 KB**, and faster.

**B. Subroutines of a function.** Also at `finish()`, before `thread()`: a run of entries that comes twice or more in the function, with no label inside it (one may be just before it), no branch, jump, return or stack instruction, not ending in a `JSR` and not starting just after one (a routine such as `rt_math.elem16` or `rt_frame.push` reads what follows its `JSR`), becomes one copy after the function's last instruction, ended by an `RTS`, and a `JSR` to it at each place, when k copies of L bytes save (k − 1) L − 3k − 1 bytes; the largest saving first, again until none is left. Functions with an `asm` block or a JSR to a label of their own (a saving call's list, a call through a pointer) are left alone, which leaves out `expr`. 562 runs were made subroutines in the build (as written: 1,439 bytes saved by runs of up to 10 bytes, 1,626 by 11 to 20, 1,527 by longer); the largest gains are `lk_tab.build_chains` (134), `lk_alloc.take`, `lk_alloc.deepest`, `kernel.thaw`. Each run's copy is its function's code, labelled like any of its labels, so a listing still reads, with one `JSR` more to follow. *Estimated in the twin:* the search and the rewrite of the buffer, about 120 to 150 lines of `fbuf.lth`, 650 to 800 bytes, and a table of where each entry starts (up to about 600 entries: 600 to 1,200 bytes of main RAM while a function is finished, which the BBC's ADFS build does not have free today: 2,253 bytes; the table would have to share space with the function buffer or be recomputed); its search, run on the 6502, about 36,000 pairs of instructions to compare for both tools (counted on the listings), about 10 to 20 million cycles of the self-compile (estimated): **net about +1.8 KB**, the cycles about +3 % with the search.

**C. Big-array reads through a routine.** An element of an array of more than 256 bytes (a byte array, or a `rows` array of words) that is read for its value (the designator is in an expression, not followed by `[`, `.` or `(`, not under `@`, a byte or word that is not a `bool`) is read by `JSR rt_math.elem8` or `elem16` with the index in A and X, followed by `LDA array,Y`, an instruction that nothing runs and which the routine reads through its return address and returns past (as `rt_frame.push` reads its list; the listing shows the array's name). The value is then in A, or A and X, like a call's result. A word read of `work[i]` goes from about 29 bytes to 10. Writes, `+=` and elements used as operands of `ADC` or `CMP` keep the pointer (counted: writes would save about 500 bytes more with a routine of their own, the value passed in the routine's slot). The cost is the routine's time: about 80 cycles a read against about 30 in line, and the linker reads its tables in its innermost loops, so linking is about a quarter slower. *Estimated in the twin:* about 35 lines of `gen.lth` and `expr.lth`, 250 to 300 bytes (`designator`, a recursive function, keeps one byte more across its saving calls): **net about +1.6 KB, for about 23 % more cycles in every link**. Limiting it to code outside the hot paths would need knowledge the one-pass compiler does not have (which functions loops call).

### Looked at and not worth it (counted)

- **Loads of a temporary after an indexed or indirect store** (register knowledge kept for the function's own temporaries across `STA (p),Y` and `STA a,X`, which cannot change them): 78 bytes in both tools.
- **`JSR` then an `RTS` that nothing branches to**, made a `JMP`: 99 and 31 bytes (the first look's `LATHE_X_JOIN`, −92 for about 10 lines); a `JSR` before an `RTS` that a branch reaches can be a `JMP` too, 82 places, for cycles only.
- **A bool made in C at a return** (`CLC / BCC *+3 / SEC / RTS` that could be `CLC / RTS / SEC / RTS`): 59 places, 1 byte each.
- **The element pointer of a big array made more cleverly in line** (the shifted index into Y by `TAY` instead of a temporary, the high byte not stored, `DEY` for the second byte): about 5 bytes at each of 70 word sites, 350 bytes, most of which A and C take anyway.
- **`case` by table**: the tools have 3 `case` statements (`lk_envf`, `lk_scan`); everything else is `if` chains on tokens, `CMP #k / BNE` at 6 bytes each.
- **`inline` functions larger in line than a call**: 16 in all, `sys`'s wrappers and two one-liners: nothing.
- **`mod` through `div16` and `remainder`**: saves 87 and 71 bytes of `mod8` / `mod16`, costs about 6 bytes at each of 7 and 6 calls, and the operator `mod` would lose its safety against an interrupt handler that divides (`code-model.md`, "Run-time arithmetic").
- **Variables copied to a temporary before a call because a later argument calls** (`exposed()`): a local or parameter of the caller cannot be changed by a callee unless its address is taken, but the one-pass compiler cannot know that an `@` later in a loop does not reach it; "values saved before a call" is 172 and 189 bytes in all.
- **A word shifted and narrowed** (`byte(r >> 13)` worked out as a word in a temporary, then its low byte): `lk_sym.kind_of` and a few more, under 50 bytes.

### What I would build

A first (net about 1.2 KB, faster, a small pass, and the program reads the same), then B (net about 1.8 KB, a few per cent slower; its search must fit the BBC's main RAM). Together, measured, 4,020 bytes more free in the eight-bank image, about 3 KB net of their twins. C frees about 1.6 KB net more but makes every link about a quarter slower; it is worth it only if the ROM must have the room. With all three, measured, the image has 11,467 bytes free (about 9 KB net of the twins), more than the compiler's 5,494 and the linker's 2,803 bytes of messages need to come back into the ROM uncompressed (8,297), though not their reader's removal and the bank packing, which the messages' own study must settle.

### Built: stores that nothing reads (2026-11-18)

A, in host and twin, byte for byte alike, always on ([`code-model.md`](code-model.md), "Stores that nothing reads"; [`language.md`](language.md), "Declarations"). At `fbuf.finish()`, before `thread()`, `drop_unread_stores()` walks the function's entries twice: first it sets a bit in `slots_read` (32 bytes, a bit for each slot number) for each slot of the function that an entry names other than by a plain store (`opcode & $F4 == $84`: `STA`, `STX`, `STY`, absolute or zero page, the only such opcodes that take an address), then it moves the entries down over each plain store into a slot whose bit is clear. In a function with an `asm` block every bit is set. `gen.slots()` gives a slot that nothing reads a weight of 0 in its SLOT record, so zero page goes to slots that are used. The slots are the function's parameters, locals and temporaries; statics, variables `at` an address or in a region, and module variables are symbols, not slots, so their stores always stay; a callee's parameters are named under the callee's symbol and never looked at. A slot named by a saving call's list counts as read, so a list never names a slot whose stores went. Only the store goes: the instructions that work the value out stay (in `unread_stores.lth`, `spare = word(v) + 300`'s `CLC / LDA / ADC` stay with nothing to store; leaving those out too would need what the one pass does not have, the uses of A after them). In the twin, 322 bytes of code, all fixed (it runs inside `finish()`'s block of `FUNCBUF`): `own_slot` 38, `is_read` 26, `drop_unread_stores` 258; and 40 bytes of variables and tables. The first try was 447 bytes; the host's first version also tested a bit as `x & (1 << n) != 0`, which Python reads as `x & ((1 << n) != 0)`: the scripts agreed with the twin by luck, and `test_fbuf.py` now has a test that each slot is its own bit.

**Tests** (written first): `test_fbuf.py`'s `UnreadStoresTest` (plain stores go, absolute and zero page; a load of either byte of a word keeps both; every other use is a read: indexed, indirect, `INC`, `DEC`, `ASL`, `ROR`, `CMP`, `BIT`, `#<`, `#>`, a reach address, a list entry `LDA abs,Y` or `ORA abs,Y`, `JMP (slot)`; another function's slot, the function's own symbol and a variable are kept; an `asm` block keeps everything, and the next function is looked at again; labels and branches round a dropped store stay right; each slot its own bit); `scripts/fbuf.txt`, four sections run by the twin against the host (`test_src_fbuf.py`, with a new command `read SLOT`); `test_gen.py`, a slot nothing reads has no stores and weighs nothing; `cases/e2e/unread_stores.lth` (a status never tested, a parameter never read and one passed on in A, a local array by index, `INC` and `DEC`, a local reached only through `@`, a word with one byte read, an `asm` block, a recursive function whose local lives across the call, a `static`), run on every machine of the corpus; `cases/snap/unread_stores.lth`, which shows the stores that go and those that stay, with a variable `at` an address. The tests that look at the code GEN, REG and COND write (`gen_support.GenTest.listing()`) mark their function as one with an `asm` block, so that they still see every store; `listing(drop=True)` shows FBUF's result.

**What changed in the snapshots** (17 regenerated, read one by one): only stores went, and with them the label offsets after them and the weights of the slots: register parameters stored on entry and never read (`calls.one.n`, `calls.sum.p`, `reg_args`' twelve, `pointer_calls.mix.a`, `func_types`' three, `result_end`'s three `a`, `shift_bytes`' `x`), locals written and read only from a register (`init.locals`' `i`, `n`, `p`, `records.copy.local`, `columns.same.v`), temporaries (`arrays.computed.$t1`, `short_multiply`'s, `inline_basic.not_plain`'s two), the status of `v = next()` in `status_ignored`, and an interrupt handler's local (`interrupts.handler.n`). No instruction other than a store changed.

**Other tests changed**: `test_out.py`'s function reads its slot (a store alone would go); `test_memory.py`'s ceiling is 32 bytes higher (`slots_read`, in [`architecture.md`](architecture.md)'s table); `test_bbc_bank.py`'s cost of a `with` block is 3 cycles more (67 and 27, 82 and 27), because the version without the block no longer stores its parameter, which the block's version reads after `rt_with.map`; `test_bbc_bank_src.py`'s gentest at the full capacities had 47 bytes more fixed code than its split, moved from `$4870` to `$48B0` ([`bbc.md`](bbc.md)).

**Measured** against 8dd784a (the eight-bank account, `test_bbc_rom128.py` with `LATHE_BBC_ROM128_REPORT=1`):

| | Before | Now |
|---|---|---|
| bytes free in the eight-bank image, BBCFS 0 | 5,815 | **6,865** (+1,050) |
| bytes free, the ADFS build (BBCFS 2, ADFS 1) | 4,610 | **5,688** (+1,078) |
| the compiler's code / resident part | 72,490 / 11,849 | 71,948 / 12,056 (fbuf +307, all fixed) |
| the linker's code / resident part | 47,698 / 9,829 | 47,182 / 9,693 |
| the compiler's banks as judged | 15,466, 15,396, 15,343, 12,342, 13,648 | 15,382, 15,201, 15,130, 12,138, 13,360 |
| the linker's banks as judged | 15,309, 15,079, 16,031 | 15,099, 14,929, **15,884** (388 below a bank, 241 before) |
| main RAM free at ADFS's PAGE, eight-bank ROM form, compiler / linker | 2,253 / 1,581 | 2,013 / 1,717 |
| self-compile on Wendy 2 (`test_src_selfhost.py`) | 834.3 M | 824.1 M (−1.2 %) |
| the Lathe linker links itself / the compiler on Wendy 2 (`test_src_selflink.py`) | 1,375.9 M / 2,513.8 M | 1,279.0 M (−7.0 %) / 2,298.8 M (−8.6 %) |
| the self-compile from the 128 KB image on the BBC, ROM form | 877.0 M | 875.2 M (−0.2 %) |
| the linker links the compiler there | 3,463 M | 3,135.9 M (−9.4 %) |
| the rebuild loop there | 4,484 M | 4,152.4 M (−7.4 %) |
| the rebuild loop on two ADFS discs from the ADFS build of the image | 4,504 M | 4,167.4 M (−7.5 %) |

The image gains 1,050 bytes where the experiment gave 1,397: the twin's 322 bytes of fixed code are most of the difference. The links are faster both because the linker's code stores less and because it links smaller objects. The compiler's fixed code is in main RAM in the ROM forms, which is why its main RAM at ADFS's PAGE is 240 bytes smaller while the linker's grew by 136. No bank layout or split of an environment file needed to move; the linker's third bank, the fullest, has 147 bytes more room.

**Merged with the 32K forms and the texts in the module** (2026-11-18, measured on the merged tree): the eight-bank image has **3,008 bytes free** (2,295 on that branch without the pass, +713), the ADFS build **1,844** (1,107, +737); the resident parts 11,907 and 9,675; the linker's banks as judged 15,018, 14,929 and 15,884; main RAM free at ADFS's PAGE in the eight-bank ROM form 2,140 for the compiler (2,416 without the pass: its 322 bytes are fixed) and 1,747 for the linker (1,607). From the 128 KB image on the BBC: the self-compile 878.6 million cycles, the linker's link of the compiler 3,176.9 million, the rebuild loop 4,195.9 million; on Wendy 2 the self-compile 827.5 million, the links of the linker and the compiler 1,278.7 and 2,327.1 million. With `-fREGION` a `with` block of a fixed region is its body alone: no `rt_with.map`, no temporary for the bank, so nothing changes in what counts as a read, and a parameter that the block's map used to make the body load again is now more often read from its register, its store left out. In the 32K form nothing is kept fixed for a block, so `drop_unread_stores` is in the compiler's fourth bank (`LATHE4.BIN`) with the rest of `fbuf`; the five banks as judged are 16,071, 15,650, 15,788, 15,829 and 15,476 (16,170, 15,988, 16,007, 15,667 and 15,818 without the pass: the fourth grew by the pass, the others shrank), the resident part 5,303 bytes, 193 bytes of main RAM free (184 before), and it still compiles 52 of the 75 modules of `lathe/src` and `lathe/rt`. The 32K image still needs sixteen banks: the most room after a bank's code in the eight-bank form is 3,357 bytes (3,230 before), and the module's code and texts need 4,227.

### B, subroutines of a function: where its memory would come from (a design study, 2026-11-18)

The owner's question: B must not much reduce the size of module that can be compiled. Measured with A built, on the scratch tree's host compiler (`exp2`'s pass with statistics, the same choice of runs).

**What limits a module today** (`memory_report.py --corpus`; peak on the corpus, the largest of the tools' own modules where it is one of them): the name heap, 9,216 bytes, 6,993 used by `decl.lth` (76 %: the limit the owner names); the symbols, 560, 470 used (`gen.lth`); the members, 512, 439 (`gen.lth`); the function buffer, 4,096 bytes, 3,149 (`regcmd.lth`; of the tools' own functions with B's pass looked at, at most 2,237, `inlines`); the labels, 192 of which 114; the fix-ups of a function, 512; its code, 4,096. Where they are: in the eight-bank ROM form the name heap is in sideways slot 12, the symbols and members in slot 0, OUT's table in slot 1, and the function buffer with its labels in slot 13 (`FUNCBUF`), beside LEX's string and the saved tokens: 8,960 bytes of slot 13's 16,384, so about 7.4 KB of it is free (the developer's form keeps err's 5,494 bytes of messages there too: about 1.9 KB free). Main RAM holds the code that runs inside a `with` block (all of FBUF's passes), the other variables and the stack: 2,013 bytes free at ADFS's PAGE now. On Wendy 2 `FUNCBUF` is bank 6. In the `RAM32` form another agent is building every table is in main RAM, so there anything B adds competes with the name heap and the symbols.

**What B needs.** A table of where each entry of the function starts (the entries are 2 to 7 bytes), 2 bytes an entry, for the search to compare runs at two places; marks for the entries a run has taken (a bit each, or a spare bit of the kind byte, which needs none); and the runs chosen, at most 14 in any function of the tools (16 would do). The tools' functions have at most 450 entries (`lk_tab.build_chains`, 2,212 bytes of buffer); a full buffer could have 2,048. And its code, about 120 to 150 lines of `fbuf.lth`, 650 to 850 bytes (estimated at fbuf's 5.3 bytes a line), which runs inside `finish()`'s block of `FUNCBUF` and so is fixed: in the BBC's ROM forms that is main RAM whatever the design. The saving, measured on top of A: **+2,624 bytes free in the eight-bank image** with every function looked at (6,865 to 9,489).

| Design | New RAM for the table | Saving kept (bytes free) | Compile time, search (estimated) | Largest function and module | Same object on every machine |
|---|---|---|---|---|---|
| 1. a table of 512 entries in main RAM | 1,024 bytes of main RAM (ADFS ROM form: 2,013 free to about 990, with the code below) | 100 % (+2,624) | about 1.5 % | unchanged in the banked forms; in `RAM32` 1 KB less for the tables (the name heap at 8 KB would still hold `decl`'s 6,993) | yes, if a function of more than 512 entries skips the pass in every build |
| 2. the table in the `FUNCBUF` region | none in the banked forms (slot 13 has 7.4 KB free in the ROM form, 1.9 KB in the developer's); main RAM in `RAM32` | 100 % | about 1.5 % | unchanged in the banked forms | yes, with a fixed limit as in 1 |
| **3. the table in the buffer's own free part** (after the last entry: 2 bytes an entry fit when the entries take at most half the buffer) | **none, in any build** | **95 %** (+2,483) with the limit 2,048 bytes of entries; 87 % at 1,536; 59 % at 1,024 (+1,555); 24 % at 512 (+640) | about 1.5 % | **unchanged**: B never needs room the function did not already take, never lengthens the buffer (each place shrinks to a 2-byte JSR entry), and needs at most 16 labels, which every function of the tools has spare (at most 49 with B's) | yes, if the limit is a constant (2,048 bytes) and every build that compiles real modules has the 4,096-byte buffer; a smaller buffer (the test programs' `SMALL` build, 1,024) cannot hold the table for a function of more than 512 bytes, and must then give the same object as the host, so its tests must not compile such a function, or the limit must be 512 everywhere |
| 4. no table: the two places walked by pointers, every pair compared | none | 100 % | **+14 % to +34 %** (4.7 million pairs to look at for the compiler's own modules, at 25 to 60 cycles each) | unchanged | yes |
| 5. B off in `RAM32` (a define) | none | 0 % there | 0 | unchanged | **no**: the same source would give other object files on a 32K machine than on the B+128 and the host, and the rebuild's files are compared with the host's |

The search, measured on the compiler's own modules (716 functions looked at, those with a saving call or an `asm` block left out as in the experiment): 27,168 pairs of places that start with the same entry, 37,195 entries compared beyond the first, 962 passes of the greedy choice, 29,973 entries; at 100 cycles a pair, 60 an entry compared and 80 an entry put in its bucket each pass, about 10 to 15 million cycles, 1.2 to 1.8 % of the self-compile; the code B makes runs 1.9 % slower (the self-compile measured with the host's pass, before the twin) and the links 2.4 % and 4.2 % slower.

**Recommendation.** Design 3, with the limit a constant of 2,048 bytes of entries, at most 16 runs a function, and no run for a function whose label count leaves fewer than 16 below the smallest build's 128: it takes no memory from what limits a module, in any build, keeps the same object for the same source on every machine whose buffer is 4,096 bytes, and keeps 95 % of B's saving: about **+2.5 KB** in the eight-bank image before its twin, **about +1.7 KB net** of 650 to 850 bytes of fixed code. What it does cost is that fixed code: in the ROM forms it is main RAM, the compiler's 2,013 bytes free at ADFS's PAGE going to about 1,200, and the self-compile about 3 % slower (search and subroutines), the links 2 to 4 %. If the `RAM32` form needs a buffer smaller than 4,096 bytes, the limit should be half of the smallest, at 1,024 bytes (59 %, about +1.55 KB before the twin, +0.8 KB net). Before building it: check that no test compiles a function of more than 512 bytes of entries in the `SMALL` build and compares it with the host.

## Disc space for the rebuild on two DFS discs, measured (2026-11-17)

The question: can the sources and the build artifacts of the compiler's rebuild on the BBC (the loop of `test_bbc_dfs.Loop`, [`bbc.md`](bbc.md), "The loop under DFS names") live on two double-sided 80-track Acorn DFS discs, four sides of 798 sectors (204,288 bytes) and 31 files each, 3,192 sectors and 124 files in all, without changing discs in the middle; and if not, what it would take. The tools are in the ROM form unless said otherwise. Nothing in the tools was changed for this.

**How it was measured.** `lathe/tests/disc_report.py` builds the loop's files with the host's tools, as `test_bbc_dfs.Loop` lays them out (that test, run again for this on 2026-11-17, passes: every file the BBC writes in the loop is the host's, 4,504,887,211 cycles), and reports from the real files. Every re-encoding below is done by a script on the existing files and decoded back to the same bytes (`encode` and `decode`; LZSS and the word table likewise), except the two marked as leaving something out. `--fit` packs each case into four sides in whole sectors. Labels: *measured* (from the files, or by a run), *counted* (from a tally of the files' contents), *estimated* (reasoning given). ROM costs are estimates throughout: nothing was built.

### The inventory

Measured, the compiler's loop (`lathec-bbc.env` with `BBCFS 1`), bytes:

| Module | Source | Object | Interface | | Module | Source | Object | Interface |
|---|---|---|---|---|---|---|---|---|
| bbcfs | 5,150 | 1,571 | 30 | | asmblock | 29,639 | 19,176 | 41 |
| bbc | 13,939 | 3,482 | 203 | | fold | 7,660 | 6,839 | 201 |
| disk | 8,457 | 2,795 | 149 | | cond | 18,884 | 12,062 | 242 |
| host | 1,426 | 142 | 784 | | gen | 77,996 | 59,536 | 1,130 |
| sys | 8,768 | 751 | 434 | | inlines | 36,013 | 25,427 | 696 |
| err | 16,963 | 8,964 | 2,520 | | parts | 16,459 | 11,159 | 549 |
| kernel | 38,418 | 29,567 | 2,135 | | expr | 58,636 | 67,288 | 302 |
| fbuf | 30,682 | 18,935 | 761 | | decl | 68,061 | 51,896 | 68 |
| src | 4,585 | 2,781 | 205 | | lathec | 8,172 | 5,322 | 20 |
| lex | 23,384 | 11,867 | 1,480 | | rt_math | 8,624 | 3,134 | 249 |
| out | 15,394 | 12,644 | 637 | | rt_bbc | 11,103 | 1,746 | 138 |
| typetab | 8,777 | 4,932 | 714 | | rt_frame | 1,861 | 332 | 49 |
| reg | 51,685 | 35,279 | 1,980 | | **25 modules** | **570,736** | **397,627** | **15,717** |

| Other files (DFS name) | Bytes | Files |
|---|---|---|
| the environment `lathec-bbc.env` (`E.LATHEC-`) | 4,197 | 1 |
| the command file `LINKARG` | 257 (305 with the loop's drive prefixes) | 1 |
| the image `LATHEC` and its banks `B.LATHE1` to `B.LATHE5`, `B.LATHE33` | 14,482 + 72,093 = 86,575 | 7 |
| the map `M.LATHEC` | 125,229 | 1 |
| **all** | **1,200,338 bytes, 4,729 sectors** | **85** |
| the RAM form adds: the short module image `MODULE`, and `LOADMOD` | 196,608 + 459 | 2 (770 sectors) |

The loop's report gives drive 3 as 892,573 bytes: the sources, the map and the short image, 570,736 + 125,229 + 196,608. ([`bbc.md`](bbc.md) splits that as 569,705 and 126,260; the files are as above.) Whole sectors add 10,286 bytes to the 1,200,338.

**What each step needs on line** (measured; a compile reads its source and the interfaces of its imports, and of the modules their `LI_MODULE` entries name, and writes its object and interface):

- A compile: at most 148,489 bytes in 13 files (`gen`); the most files, 18 (`expr`, 139,912 bytes).
- The link: the environment, the command file and the 25 objects, and it writes the image, the six bank files and then the map: 613,885 bytes, 35 files. It reads no source and no interface.
- The two compiles again (`err`, `kernel`): the image and its banks (the developer's form loads them at its start, by bare names, from the current drive), the source, the interfaces of `bbc`, `sys` (and `err`), and the object and interface written over.
- So the whole loop, without changing discs, needs every file at once at the end of the link: the sources stay for the two compiles again, and the map, written last, is made by reading the objects again. **4,729 sectors against 3,192**: 1,537 over (1.9 sides), with the ROM form. The file count, 85, is not the limit.

### The sources: 570,736 bytes

Counted, all 25 modules (a comment runs from `;` outside a string or character to the end of the line):

| Part | Bytes | Share |
|---|---|---|
| comments | 213,541 | 37.4 % |
| of them, the header comment of each module (before its `module` line) | 80,822 | 14.2 % |
| code (without indentation and import lines) | 285,674 | 50.1 % |
| import lines, with their continuation lines | 18,194 | 3.2 % |
| of them, the lists (the same imports written bare would be 1,237) | 16,957 | 3.0 % |
| indentation (two spaces a level) | 32,279 | 5.7 % |
| spaces before a comment after code | 6,616 | 1.2 % |
| line ends | 13,347 | 2.3 % |
| blank lines | 1,085 | 0.2 % |
| trailing space | 0 | |

By module the shares are alike, but the run-time and machine modules are mostly comment: `rt_bbc` 69 %, `rt_frame` 79 %, `bbcfs` 56 % (`disc_report.py` prints the table by module). The import lists are what keeps a compile's name heap small ([`language.md`](language.md), "Import lists"; the commit that brought them took the heap from 18,944 to 9,216 bytes), so a copy without them is not an option. In these 25 modules they are 16,957 bytes (the 38 KB quoted for them when they came is not this set's figure; not checked which files it counted).

The options, measured on the 25 sources:

| Form on the disc | Bytes | Saves | What the compiler makes of it | Cost in the tools |
|---|---|---|---|---|
| as in the repository | 570,736 | | | |
| **disc copy**: comments removed, every line kept, indentation as it is | 352,607 | 218,129 (38.2 %) | measured: every object, interface, image, bank file and the map are the same bytes as from the readable sources; an error's line and column are the same | none (a host tool) |
| disc copy, indentation as tabs | 321,935 | 248,801 | measured: objects, image, banks and map the same; four interfaces differ (`host`, `kernel`, `lex`, `sys`: the columns saved with inline bodies); errors give the right line, a column counted with a tab as one | none |
| disc copy, no indentation | 319,035 | 251,701 | as with tabs | none |
| comments kept, indentation as tabs | 539,499 | 31,237 | as with tabs | none |
| header comments moved to a document (a change to the repository) | 489,914 | 80,822 | the same, but the lines move in the repository too | none |
| **word table**: bytes `$80`-`$FF` stand for 112 words (a word and its space counting as one) and runs of 2 to 17 spaces, from a fixed table; decoded and compared | 396,225 | 174,511 (30.6 %) | the same text, byte for byte, expanded as it is read: lines and columns right | estimated about 1 KB of a bank: the table 689 bytes, an index of 128 entries, about 100 bytes of code in `src`; no RAM to speak of |
| **LZSS**, 1 KB window (a flag byte for eight items, a match two bytes); decoded and compared | 259,820 | 310,916 (54.5 %) | the same text, byte for byte | estimated 150 to 250 bytes of code; **1 KB of RAM** for the window (the compiler's ROM form has 2,211 bytes of main RAM free) |
| LZSS, 2 KB window | 229,360 | 341,376 | | 2 KB of RAM |
| deflate, 1 KB window | 208,182 | 362,554 | | estimated about 1 KB of code and 1 to 2 KB of tables, besides the window: the RAM is not there |
| deflate, 32 KB window (zlib -9) | 158,090 | 412,646 | | not possible |

A disc copy is honest only if it is called what it is: the code is all there and every error points at the right line, but the explanations are not on the disc; the readable source is the repository's. A coded copy (word table, LZSS) is the readable text itself, but `*TYPE` on the BBC shows codes: it is read through the compiler (or a small expander) only. Deflate's last 52 KB over LZSS cost RAM the compiler does not have: poor value.

### The objects: 397,627 bytes for 89,288 bytes of code

Counted, all 25 objects (records' type and length, 3 bytes each, apart):

| Part | Bytes | Share |
|---|---|---|
| `FIX` entries: 23,514 fix-ups at 8 bytes | 188,080 | 47.3 % |
| `CODE`: the written layout | 89,288 | 22.5 % |
| of it (and of `DATA`), the bytes under fix-ups, all 0, which the linker writes over | 46,185 | 11.6 % |
| record headers: 11,522 records (3,007 `CALL`, 2,452 `SLOT`, 2,012 `SYM`, 800 each of `FUNC`, `FIX`, `CODE`, `ENDF` ...) | 34,566 | 8.7 % |
| `SYM` names (`module.name`, a length byte each) | 29,659 | 7.5 % |
| `CALL` bodies (5 bytes each) | 15,035 | 3.8 % |
| `SLOT` fields (5 bytes each) | 12,260 | 3.1 % |
| `SLOT` names | 10,877 | 2.7 % |
| `DATA` bytes | 6,689 | 1.7 % |
| `WGT` | 3,348 | 0.8 % |
| `FUNC`, `VAR`, `SYM` kinds, `IMP`, `MOD`, `RGN`, `DFIX` and the rest | 7,825 | 2.0 % |

**Why five times the code.** Every 3.8 bytes of written code have a fix-up, and a fix-up is 8 bytes; half of the code bytes are zeros that the fix-ups fill; and every slot and every call is a record of its own with a 3-byte header. Of the fix-ups (counted): 16,607 are kind 5 and 6,064 kind 1; 12,256 name the function being defined (11,774 of them its own slots); 17,895 have no addend; every one is less than 128 bytes after the one before it; 18,831 name a symbol below 127.

**What a plain link does not need.** The `SLOT` names (the map's S lines and `lo2asm` use them): 8,425 bytes. Nothing else: the names of symbols are how files meet, `WGT` decides zero page (4,191 bytes), `CALL`'s outer symbol is needed for calls inside arguments, and `CLAS` parameter names are already empty. A separate file for 8 KB would be another file for the linker to open: not worth it.

**Re-encoded** (measured: each option alone, then added one after another; every one decoded back to the original bytes but the slot names):

| Option | Alone | Together | Set |
|---|---|---|---|
| as written | | | 397,627 |
| leave out the bytes under fix-ups (`holes`): the reader puts the fix-up's bytes where they were | -46,185 | -46,185 | 351,442 |
| a fix-up as a byte of kind and flags, then the offset, the symbol only if not the function being defined, the slot only if not `$FF`, the addend only if not 0 | -70,430 | -116,615 | 281,012 |
| numbers as variable-length (7 bits a byte; a symbol as n + 1, `$FFFF` as 0; addends zigzagged), a fix-up's offset as the distance from the one before | -75,134 | -164,878 | 232,749 |
| a record header of 2 bytes when the body is below 255 bytes | -10,870 | -176,226 | 221,401 |
| `ENDF` left out (it always follows `CODE`); a function's `SLOT` records as one record, and its `CALL` records as one | -13,357 | -184,679 | 212,948 |
| a `SYM` name as the number of its module among the `MOD` and `IMP` records, and the rest of the name | -8,890 | **-193,569 (48.7 %)** | **204,058** |
| leave out the slot names (loses them for the map) | -8,425 | -201,994 | 195,633 |
| for scale: deflate -9 of each object as written | | | 153,326 |
| for scale: LZSS (1 KB window) of each object as written; of the 204,058 | | | 216,815; 140,834 |

What it would cost, estimated against the sizes of what is there now (the maps): `lk_rec.get_word` is 26 bytes, `lk_rec.advance` 91, `lk_fix.read_entry` 51, `out.begin_record` 21, `out.table_end` 275.

- **The linker** reads fix-ups in five places now, 8 bytes at a time (`lk_fix` twice, `lk_graph` twice, `lk_scan`); one decoder in `lk_rec` replacing them, with a variable-length number reader, is perhaps 150 to 250 bytes more than what it replaces; the holes, 100 to 250 (the emitter writes the fix-up's bytes instead of reading them, and a function's written length becomes `CODE`'s length and the bytes its fix-ups cover, in `lk_place`, `lk_map`, `lk_emit`); short headers and runs, a few dozen; module numbers for names, about 150 and room for one file's module names. About 400 to 800 bytes in all, and `lk_rec` is resident: part of it comes out of the linker's main RAM (4,129 bytes free). Reading stays one pass from the start of a file, which is what the linker's several readings and `lk_rec.goto` need.
- **The compiler** writes a record's length before its body, from counts it holds; with variable lengths it needs a pass over the fix-ups it holds to size the record first, and to skip the bytes under fix-ups as it writes code: perhaps 400 to 700 bytes, mostly in bank 3 (`out`), some in fixed code (`out.table_end` is fixed).
- **The host tools** (`lk_rec.py`, `out.py`, `lo2asm`, `lodump`) change with them; the format would be version 5.
- **Time.** The compiler's link reads 4,009,214 bytes ([`bbc.md`](bbc.md)), nearly all of it object files read again and again; objects half the size are about 2 MB less to read, which at the 1,000 cycles a byte [`bbc.md`](bbc.md) estimates for a real DFS is about 16 minutes at 2 MHz (estimated; the emulator charges nothing for a byte read). The decoding costs cycles of its own, not measured.
- **A general compressor in the linker** (deflate) saves 50,732 bytes over the set of 204,058 for perhaps 1 KB of code, 1 to 2 KB of tables and a window in RAM the linker does not have, and it would run once for every reading of every file: not worth it. LZSS on top of the re-encoding (140,834) would need 1 KB of the linker's RAM: possible, not needed for the fit.

### The interfaces: 15,717 bytes

Counted: 427 function entries (7,824 bytes), 410 constants (5,752; `err.li`'s error numbers are 2,520 bytes alone), 112 variables (1,465), 15 `LI_USES` entries (339), 7 module entries, 2 records; the names of entries are 9,047 bytes of it, inline bodies 893. At 1.3 % of the loop's files there is nothing worth changing here.

### The map: 125,229 bytes

Counted, by line kind: S (slots) 2,412 lines, 82,402 bytes (65.8 %); F 779 lines, 24,113; V 317, 9,417; T 291, 7,608; D 50, 1,486; W 9, 203. The module prefixes of the names are 20,563 bytes of it.

- **Who reads it.** Nothing on the BBC. On the host: `bbcrom.py` reads its V lines for the listing only (it builds the image from the resident file, the bank files and the environment); `build.py --asm` (`lo2asm.render_program`) needs the F, D, V, S and C lines; the tests compare it byte for byte with the host's; people read it.
- **A link without a map is not possible today.** The map is the fourth argument (`lk_file.ARG_MAP`), always opened; a name that cannot be opened is a link error. Allowing none (a name such as `-`, and the host's twin the same) is perhaps 30 to 60 bytes, and the link would also skip the map's own readings of the objects (estimated).
- **Sizes**: none, 0; without the S lines, 42,827 (what `bbcrom.py`'s listing needs, and the functions' addresses); the W lines alone, 203; the full map, 125,229, on request.

### The image and bank files: 86,575 bytes

They are the product and must be written. The command line places them already: `2/LATHEC` writes the image and its six bank files on drive 2 (the bank files go beside the image), the map has its own name (`3/LATHEC.map`), and the objects are read from any drive. The new compiler in the developer's form loads its banks by bare names from the current drive, so `*DRIVE` to the image's drive before `*RUN LATHEC`, or keep it on drive 0.

### Fitting four sides

Measured by packing whole files into four sides of 798 sectors and 31 files (`disc_report.py --fit`); a module's object and interface are on one side (one compile writes both into one directory), the image and its banks on one side. "64 free" means each side keeps at least 16 KB free (below). Sectors, the compiler's loop, ROM form:

| Sources | Objects | Map | Sectors | Spare | Fits | 64 free a side | With the RAM form |
|---|---|---|---|---|---|---|---|
| readable | as written | full | 4,729 | -1,537 | no | no | no |
| readable | as written | none | 4,239 | -1,047 | no | no | no |
| readable | re-encoded | none | 3,484 | -292 | no | no | no |
| readable | re-encoded, no slot names | none | 3,451 | -259 | no | no | no |
| comments kept, tabs | re-encoded | none | 3,364 | -172 | no | no | no |
| header comments moved out | re-encoded | none | 3,169 | 23 | packed full only | no | no |
| header comments moved out, tabs | re-encoded | none | 3,047 | 145 | packed full only | no | no |
| word table | as written | none | 3,577 | -385 | no | no | no |
| word table | re-encoded | full | 3,312 | -120 | no | no | no |
| word table | re-encoded | without S | 2,990 | 202 | yes | no | no |
| word table | re-encoded | none | 2,822 | 370 | yes | yes | no |
| LZSS 1 KB | as written | none | 3,022 | 170 | yes | no | no |
| **LZSS 1 KB** | **re-encoded** | **full** | **2,757** | **435** | **yes** | **yes** | no |
| LZSS 1 KB | re-encoded | without S | 2,435 | 757 | yes | yes | no |
| LZSS 1 KB | re-encoded | none | 2,267 | 925 | yes | yes | yes (3,037) |
| disc copy | as written | full | 3,874 | -682 | no | no | no |
| disc copy | as written | none | 3,384 | -192 | no | no | no |
| disc copy | re-encoded | full | 3,119 | 73 | yes | no | no |
| **disc copy** | **re-encoded** | **without S** | **2,797** | **395** | **yes** | **yes** | no |
| disc copy | re-encoded | none | 2,629 | 563 | yes | yes | no |
| disc copy, tabs | re-encoded | without S | 2,682 | 510 | yes | yes | no |
| disc copy, tabs | re-encoded | none | 2,514 | 678 | yes | yes | no |

**Readable sources do not fit four sides under any arrangement measured.** With them on the disc as text (2,242 sectors) and the image, banks, environment and interfaces (433 sectors), 517 sectors (132,352 bytes) are left for 25 objects, whose code without the bytes under fix-ups (43,103) and constant data (6,689) are 49,792 bytes before a single fix-up or name; the best lossless re-encoding is 809 sectors, and deflate of the objects as written about 600. Moving the header comments into documents gets within 23 sectors, packed to the last sector of every side: no room for the next change to the compiler.

Two arrangements that fit with room, from the packer (each side: files, sectors used of 798):

| Side | LZSS sources, re-encoded objects, full map | Disc copy, re-encoded objects, map without S lines |
|---|---|---|
| 0 | the map; 5 modules' objects and interfaces; 5 sources: 16 files, 689 | the image and banks; 8 modules' objects and interfaces; 4 sources: 27 files, 700 |
| 1 | the image and banks, the command file; 7 modules' objects and interfaces; 4 sources: 26 files, 690 | the environment; 3 modules' objects and interfaces; 10 sources: 17 files, 700 |
| 2 | the environment; 6 modules' objects and interfaces; 8 sources: 21 files, 689 | the command file; 6 modules' objects and interfaces; 7 sources: 20 files, 699 |
| 3 | 7 modules' objects and interfaces; 8 sources: 22 files, 689 | the map; 8 modules' objects and interfaces; 4 sources: 21 files, 698 |

A compile names its source's drive, its own side as the output directory and the other sides as directories of interfaces (`*LATHE ... 3/gen.lth 1 0 2 3`); the command file names each object's drive.

**The RAM form** adds 770 sectors, nearly a side (`bbc.md`: 772 of an 80-track side's 800 with the catalogue). It fits beside the work only with LZSS sources, re-encoded objects and no map (3,037 sectors). Otherwise the module image is best on a disc of its own: `LOADMOD` reads it once, before the first compile, and it is not needed again while the machine is on, so that is a change of disc before the loop, not in it.

**The linker's own rebuild** (measured the same way, 26 modules, 87 files): sources 335,269, objects 262,481, interfaces 9,901, environment and command file 4,753, image and banks 52,436 (6 files), map 83,499 (S lines 59,338); 748,339 bytes, 2,967 sectors. **It fits four sides as it is**, readable and with the full map, though packed (225 sectors spare, not 64 a side); without its map, 2,640 sectors, with 64 free a side; with the RAM form only with re-encoded objects. On the same four sides as the compiler's loop it adds 675,264 bytes, 2,671 sectors as it is (seven modules, `bbcfs`, `bbc`, `disk`, `host`, `sys`, `rt_math`, `rt_bbc`, are shared: their sources, objects and interfaces are the same bytes in both loops, 73,075 bytes); both together are 7,400 sectors, and even the smallest case measured (LZSS sources, re-encoded objects, no maps) is 3,540, 348 over. The linker's rebuild needs discs of its own, and they need no change at all.

**The DFS's other limits.** From `emulator/NOTES-bbcbplus.md` (third parties' documents, not Acorn's): a new file opened for output is given 16 KB, a file written over keeps its old space, and a file is one run of sectors that cannot grow into the next file ("Can't extend"). Not checked: whether a new file goes after the last file or into the first gap that holds 16 KB, whether an OPENOUT fails when less than 16 KB is free, and what `*COMPACT` uses for its buffer.

- In the loop as measured nothing is deleted, the tools write one file at a time (most writing 1, `test_bbc_dfs.Loop`), and each file is written to its end and closed before the next is created. If the read-only files (sources, environment, command file) are put on each side first, the free space of a side is one run after its last file, and every file the loop creates is the last on its side while it grows, wherever the DFS puts new files: no arrangement above is at risk of "Can't extend".
- The 16 KB a new file is given: if an OPENOUT fails with less than 16 KB free (not checked), a side must keep 64 sectors free when its last file is created; the column "64 free a side" is that case. The largest single file a side must take is the map (490 sectors, full) or `L.GEN` (305 as text).
- The two compiles again write `O.ERR`, `I.ERR`, `O.KERNEL` and `I.KERNEL` over files of the same length: they keep their space.
- **A second rebuild on the same discs** is where it would bite: an object that grows after a change to its source cannot pass the file after it. Before rebuilding, `*DELETE` the objects and interfaces and `*COMPACT` the side, which then has its free space in one run again. Between the steps of one loop `*COMPACT` is not needed.

### What I would do, in order

1. **Re-encode the objects** (object format version 5: the holes, packed fix-ups, variable-length numbers and deltas, short headers, runs, module numbers): 397,627 to 204,058 bytes, nothing lost. Every arrangement that fits needs it, and it halves what each link reads. Cost estimated at 400 to 800 bytes of the linker (part of it resident) and 400 to 700 of the compiler, and the host twins.
2. **Make the map optional** in the linker (no map, or the map without S lines; the full map on request and on the host): 125,229 to 0 or 42,827 bytes, about 30 to 60 bytes of the linker for none.
3. **Then the sources, which is the owner's choice** (the four sides cannot hold them as plain text):
   - **LZSS-coded sources** (the repository's text, comments and all, byte for byte; a host tool writes them, the compiler decodes as it reads): 259,820 bytes; fits with the full map and 64 sectors free a side, and with no map even the RAM form. It costs 150 to 250 bytes of the compiler and 1 KB of RAM for the window (of the 2,211 bytes of main RAM the ROM form has free, or a sideways RAM slot if one has 1 KB to spare: not checked). The disc's files are not readable with `*TYPE`.
   - **Word-table sources**: 396,225 bytes, no RAM, about 1 KB of a bank; fits only without the map (with 64 free a side), or with the map without S lines packed full. The same text, also not readable with `*TYPE`.
   - **A disc copy without comments**: 352,607 bytes, no change to the compiler at all (a host tool), every file the compiler and linker write the same as from the readable sources, every error at the right line and column; fits with the map without S lines and 64 sectors free a side. The disc is then not the readable source.
   - **More discs, readable sources as text**: three discs and one change. With the objects re-encoded and the map without S lines, one disc in drive 1 holds every file the loop writes, the environment and the command file (1,410 sectors of 1,596, more than 64 free a side); drive 0 takes a disc of the sources of `bbcfs` to `inlines` (1,563 sectors), then, when `parts` is to be compiled (the 19th of 25), a disc of `parts` to `rt_frame` with copies of `err`'s and `kernel`'s sources (897 sectors) for the two compiles again. The link needs drive 1 only. With today's formats (no change to the tools) the objects and interfaces alone are 1,637 sectors, more than one disc, and it takes more changes.
   - **ADFS** (from memory, not checked: 640 KB a disc, 2,560 sectors, about 2,553 free of the map and root directory; 47 entries a directory; directories of 5 sectors): two discs, 5,106 sectors, hold the loop as it is today (4,729 sectors and four directories) with about 350 sectors spare, readable and with the full map, but not the RAM form as well (5,519) unless the map goes. It needs `BBCFS 2` built (about 40 bytes, and `*CDIR` for each directory first, [`bbc.md`](bbc.md), "ADFS: what it would take"), an ADFS ROM in the machine and a free ROM socket for it (not checked for the B+128), and an ADFS mode in the emulator. ADFS's own rules for a file that grows were not checked.
4. **Not**: shortening names or deleting comments in the repository; dropping the import lists in a disc copy (the compiler's tables need them); dropping the slot names (8,425 bytes, and the map loses them); a separate file of debugging records (8 KB); deflate in either tool.

If the owner wants the sources on the disc readable as they are in the repository, the measured answer is: LZSS-coded copies on two DFS discs (with the format change and the optional map), which keeps the text but not `*TYPE`; or three DFS discs and one change in the middle of the compiles; or two ADFS discs and no change to the formats.

Not done here: anything on a real disc or a real DFS; the decoders and the format change themselves (every ROM cost above is an estimate); the BBC runs of the disc copies (the host's tools compiled and linked them, and `test_bbc_dfs.Loop` shows the BBC's tools write what the host's write); the linker's rebuild on the BBC under DFS names (its files were measured from the host's tools only).

## The compiler in a 32K Model B, measured (2026-11-18)

The compiler's 32K form ([`bbc.md`](bbc.md), "The 32K Model B"), `BBCFS 1`, the eight-bank ROM form, linked by a stand-in for the host linker that lets a bank be over as judged and puts the variables where they all fit (`lathe/tests/lk_mainram.py`'s way), so that what does not fit is measured too. Main RAM is `$1900-$7BFF` and `$0401-$06FF`, 26,111 bytes.

| Build | Resident (code, stubs, constants) | Variables and frames | Free | Banks as judged (over) |
|---|---|---|---|---|
| The B+128's layout, regions fixed, small capacities, the linker keeping functions with blocks fixed | 11,853 (8,026 of it kept) | 18,364 | **-4,106** | fit |
| The same, nothing kept (a measuring linker that ignores the marks: blocks would map slot 0 over the running bank, so not a build) | 4,057 | 18,364 | 3,690 | bank 4 over by 4,107 |
| `-fREGION` for every region (the compiler told), small capacities, the B+128's layout | 4,033 | 18,386 | 3,692 | bank 4 over by 3,239 |
| `-fREGION`, the 32K layout (`fold` fixed), small capacities | 5,419 | 18,400 | 2,292 | fit: 16,170 / 15,988 / 16,007 / 15,667 / 15,818 |
| **as built**: names 3,072, buffer 1,536, types 40, import rows 56 | 5,419 | 20,582 | **110** | the same |
| import rows 64 instead of 56 | 5,419 | 20,664 | 28 in all, but link error 26, 256 bytes over: a table did not fit what `more data` had left | |

The choice of capacities: each module of the corpus compiled by the host compiler with `memory_report.py`'s gauges, its peak in each table noted, and every set of capacities within the 2,292 bytes searched for the most modules of `lathe/src` and `lathe/rt` that fit (names 2,048 to 4,352 by 256, buffer 1,024 to 2,048 by 256, types 32 to 48, import rows 48 to 80, string and table 264 or 512): names 3,072 with a buffer of 1,536 and 40 types fit 45 of 70 modules there, and as many cases (155 of 179) as any other; a larger name heap with the small buffer fits fewer (names 3,584, buffer 1,024: 25 of the 61 of `lathe/src`), as do longer strings. On the Model B the 32K form compiles 52 of the 75 modules the assessment takes (`test_bbc_ram32.Assessment`), the first limit reached being the name heap in 11 of the 23 refused, an import list's rows in 8, the function buffer in 4 and the string in 1.

The linker's 32K form told of its fixed regions (2026-11-18, `BBCFS 1`, the same measuring linker): in the eight-bank form, `-f` for all five regions leaves nothing kept and the resident part 7,821 bytes (9,095 before), but bank 3 (lk_alloc and lk_graph) is 16,327 bytes as judged, 55 over; without `LKWORK` 530 bytes stay kept (lk_alloc 184, lk_graph 180, lk_fix 166), the resident part is 8,434 bytes and bank 3 16,031; in the sixteen-bank form all five are told and the resident part is 7,839. One region left out at a time, only `LKWORK` brings bank 3 back: `LKNODES`, `LKSLOTS` and `LKCALLS` each leave it at 16,327 and only shorten `lk_tab`'s blocks.

The 32K image, both tools' 32K forms and the texts of the errors (merged 2026-11-18): the module's code and tables with the texts are 4,227 bytes, which must be in one bank after its code; in the eight-bank form the most room after a bank's code is 3,230 (the linker's bank 3), so the image is the sixteen-bank form, banks 0 to 11 in use, 80,134 bytes free. On the emulated Model B: 57 programs of the corpus compiled, linked and run (one, `regions`, not run: its regions are in sideways RAM), 3,080 million cycles for the compiles and the links, 25.7 minutes at 2 MHz; farcall's 98.8 million (49 s), `reg_args`'s 89.7 million.

Cycles, from the image on the emulated Model B: the 52 compiles 750.6 million (6.3 minutes at 2 MHz), the largest, `lk_map.lth` and `lk_name.lth`, 50 million each (25 s), `fbuf.lth` 47 million; `farcall.lth`'s twelve modules 59.4 million. `src.lth` 11.6 million against 9.2 million from the B+128's eight-bank image (`BBCFS 0`), `fold.lth` 18.3 against 16.0.

## The tools' source, a second look (measured)

The question: which changes to the tools' own Lathe source (and the host modules they are twins of) make the compiled code smaller without making it harder to read, after "Built: the compiler's source made smaller" above. Measured from 8dd784a: the eight-bank account of `test_bbc_rom128.build_tools` (123,970 bytes in use, **5,815 free**), each tool's bytes as placed by module from its map, main RAM free at ADFS's PAGE in the eight-bank ROM form (`adfs_main_ram`: 2,253 bytes for the compiler, 1,581 for the linker), and for the changes kept together the cycles of the self-compile on Wendy 2 (`bank_report.py --selfhost`). "Measured" is a build of the change in host and twin; "estimated" is a count of sites times bytes a site measured on a like change. Nothing here is committed but the finder: each experiment was a diff against 8dd784a, kept out of the tree.

**The finder.** `lathe/tests/dup_report.py` cuts each function of the tools' twins into statements, numbers each function's own locals and parameters in order of use, and lists (1) runs of K statements written N times or more across a tool, with an estimate of their bytes from the map (`--map`), and (2) pairs of functions alike by difflib's ratio over their statements. What it shows: the tools' source is already well factored. The commonest run in the compiler that is not structure (`return` / `end`) is `line = lex.line` / `col = lex.col` (44 times, 35 in EXPR), then `if lex.tok != lex.T_NAME then err.fatal(err.E_NAME_EXPECTED)` (13); in the linker nothing above `damaged()` and `bad()`, which are helpers already. Of the near copies, one pair is identical (`lk_tab.run_start` and `head_of`); the others are small, or alike by the shape of the language (`expr.term` and `addition`, `while_statement` and `loop_statement`). A second scan, of parameters passed on unchanged to calls (a script, not kept), found DECL's `stream` handed down 111 times through 22 functions, INLINES's 48, and LK_SCAN's `obj` 25.

**Changes measured** (each alone against 8dd784a; bytes of the image, so the free figure grows by them; main RAM free at ADFS's PAGE):

| Change | Modules | Sites | Compiler | Linker | Main RAM | Reads |
|---|---|---|---|---|---|---|
| A token's position as one record, `err.Place`: `lex.mark_place(@place)` for the pair `line = lex.line` / `col = lex.col`, `err.position_at(@place)` for `err.position(line, col)`, and `parts.field`, `apply`, `test_operator` given `^err.Place`, in the 36 functions of EXPR and DECL whose `line` and `col` are locals | err, lex, parts, expr, decl | 44 marks, 55 reports, 9 passes | **−1,126** (expr −827; gen −85 and reg −93 from zero page freed) | 0 | compiler +15 | better: one name for one place |
| DECL's interface stream a module variable (`stream`, "one is open at a time", as `imported_module` already ensured), not a parameter of 22 functions | decl | 111 | −169 | 0 | −1 | same |
| OUT's `put` and `put_word` of its own stream, for the 43 `kernel.put(stream, …)` | out | 43 | −166 | 0 | +16 | same |
| `enter_loop(@outer)` / `leave_loop(@outer)` with a record `Outer` for the state that `while`, `loop` and `for` keep and give back | expr | 3 | −96 | 0 | 0 | better |
| `lex.need_name()` for the 13 checks that the token is a name | lex, parts, decl, expr | 13 | −92 | 0 | −6 | better |
| `lk_tab.head_of` is `run_start` (the two bodies were the same) | lk_tab | 1 | 0 | −68 (resident) | linker +68 | better |
| LK_SCAN's object being read a module variable `cur_obj`, beside `cur_fn`, not a parameter of 12 record readers | lk_scan | 25 | 0 | −38 | −1 | same |
| setters of one column, `set_type`, `set_value`, `set_flags`, for 138 `set_byte`/`set_word` (fixed, with a `with` block each, as the readers) | kernel and its callers | 138 | −80 (kernel resident +118) | 0 | **−115** | same |
| readers of one more column each, `results_of`, `name_of`, `obj_of`, `members_of` (fixed) | kernel and its callers | 147 | **+21** (kernel resident +166) | 0 | **−163** | same |

Correctness: for every change kept below, `test_src_lathec.py` (the compiler's twin against the host over the corpus), `test_src_expr.py`, `test_src_lk.py` (the linker's lower layers), the host's `test_errors.py`, `test_decl.py`, `test_lex.py`, `test_err.py`, `test_out.py`, `test_import_lists.py`, `test_cases.py` and the gate class `test_bbc_rom128.Rom128` pass (124 and 167 tests); every self-compile below gives the host's files.

**The first seven together** (all but the accessors; the diffs applied one after another, the import lists written again by `import_lists.py`): the compiler 1,687 bytes smaller (its banks as placed 63,428 to 61,781, resident 11,849 to 11,827), the linker 106 (resident 9,829 to 9,761): the account from 5,815 bytes free to **7,590** (1,775 more). The compiler's banks as judged 13,967, 15,396, 14,771, 12,425 and 13,648 (bank 1 1,499 smaller); the linker's unchanged but bank 3 judged the same (16,031: the 241 bytes left there are not helped by these). Main RAM free at ADFS's PAGE: compiler 2,253 to 2,277, linker 1,581 to 1,648. Cycles of the self-compile on Wendy 2, over the twelve modules whose source none of the changes touch (kernel, src, typetab, fold, fbuf, reg, cond, gen, asmblock, inlines, lathec, sys): 512,750,037 to 513,481,550, **+0.14 %** (gen +0.26 %, the small ones a little faster from the layout); `expr`, whose source is changed, 96.2 million to 92.1 (−4.3 %, its source and output being smaller too).

**Estimated, not built** (sites counted; bytes a site from the measured change most like it):

| Change | Sites | Bytes, estimated | Reads |
|---|---|---|---|
| `Place` in ASMBLOCK (`at_line`, `at_col` passed to `fail_at`, `label_find`, `label_define`, `mnemonic_here`, `label_line_rest`) and PARTS's `in_line`/`in_col` | about 14 | 80 to 100 | better |
| `Place` for the five functions of EXPR that take `line, col` as parameters (`call_value`, `conversion`, `assignment`, `pair_assignment`, `target`): they are recursive, and a pointer to the caller's record would see a deeper activation's position after a nested call, so each would copy it into a record of its own first | about 20 calls | 50 to 80 | same |
| `err.fatal_at(@place, number)` for `err.position_at(@place)` then `err.fatal` | 18 | about 70 | same |
| INLINES's stream (read_name, skip_name, skip, read, write, write_uses) the decl's one variable: it needs the variable in INLINES or KERNEL, below DECL | 48 | about 100 | slightly worse (a variable another module sets) |
| `expr.term`, `addition` (and `relation`) as one function of a precedence level | 2 to 3 | about 80 | slightly worse |

**Looked at, not worth it:** the readers of one more column each (+21 bytes, 163 of main RAM: one byte saved a call, and a resident function of about 40 bytes each with its block); the setters (−80 for 115 bytes of main RAM; placed in kernel's bank instead they would be far calls from four banks); the three operator functions of PARTS as a table indexed by token (127 bytes of `CMP / BNE / LDA / RTS`; a table over the token numbers is about as large); `lk_tab.wk`/`set_wk` with a base and an index (the addition moves into an argument store: larger); a `reg.pop2()` for `reg.pop(); reg.pop()` (11 sites, about 25); `lk_sym.row_of` in line (66 calls of 7 bytes against about 10 in line); `case` and `if` chains mapping a value to a value (one found, in `lk_envf`, of three arms); `inline` (two functions in the tools, both right as they are); the embedded assembler's tables (already tables of bytes); dead functions (the linker keeps only what is reached). The linker's storage walks (`lk_alloc`: slots, class parameters, variables) are factored already (`each_candidate`).

**Large features**, for the owner to know (bytes of code as placed in the eight-bank image; none recommended for cutting): `inline` (INLINES 5,152, and the code for it in EXPR and DECL, 6,881 counted before); the embedded assembler (ASMBLOCK 3,527 and 465 of tables); constant folding (FOLD 1,301); conditional compilation (about 770); the linker's zero page promotion (LK_ALLOC 7,834 and 184 resident, of which the choice of what goes in zero page is most); the environment file reader (LK_ENVF 4,139 and 172 of tables); the map (LK_MAP 3,606); windows, banks and stubs (LK_WIN 1,146, LK_BOOT 1,194, with more in LK_PLACE and LK_EMIT).

**What I would build first:** the position record (1,126 bytes alone, reads better), then DECL's stream, OUT's `put`, `need_name`, the loop state, `head_of` and LK_SCAN's object: **1,793 bytes of the image**, measured together, for +0.14 % of the self-compile's cycles, with main RAM a little up for both tools. With the estimated changes after them (the rest of `Place`, `fatal_at`), about 2.0 to 2.1 KB in all. They help the compiler's banks; the linker's third bank, the fullest (241 bytes left as judged), gains nothing from them, and needs its own work (`lk_alloc`, `lk_graph`) if it is to hold more.

### Built: the tools' source, a second look (2026-11-18)

The figures of this section, but for those of "After the merge" at its end, were measured on 8dd784a, before the merge into the integration branch.

Rows 1 to 7 of the first table above, and two of the estimated rows (`Place` in ASMBLOCK and PARTS, and `Place` for EXPR's five functions that took `line, col`), built in host and twin with every compile byte for byte as before. `err.fatal_at` was built too and measured 13 bytes: once `Place` was in, the pairs `err.position_at` then `err.fatal` were 9, 3 bytes a site against a function of 14. It was left out. Bytes of the eight-bank image's account (`test_bbc_rom128.build_tools`, `BBCFS 0`) after each change, against 8dd784a's 5,815 free:

| Change (commits) | Compiler | Linker | Free |
|---|---|---|---|
| `lk_tab.head_of` is `run_start` (93b9c46) | | −68 (resident) | |
| LK_SCAN's `cur_obj` (bf903a7) | | −38 | 5,921 |
| `need_name()` (65a0594, 909b0c5; in PARTS since bee17a9) | −92 | | |
| `err.Place`, `mark_place()` and `err.position_at()` (dd0ae6d; `mark_place` in PARTS since bee17a9), used in EXPR, DECL and PARTS (2db2da8) | −1,108 | | 7,121 |
| DECL's interface stream a module variable (6683125) | −183 | | 7,304 |
| OUT's `put` and `put_word` (0dbe1e0) | −179 | | 7,483 |
| `enter_loop` and `leave_loop` (68c64c7) | −107 | | 7,590 |
| ASMBLOCK's positions as `err.Place` (fb01763) | −403 | | 7,993 |
| PARTS's `in_place` (2c9037d) | −37 | | 8,030 |
| EXPR's `target`, `call_value`, `conversion`, `assignment` and `pair_assignment` take an `err.Place` (e1e30ba) | −276 | | 8,306 |

In all, the compiler is 2,385 bytes smaller and the linker 106. The eight-bank image has **8,306 bytes free** (in use 121,479 of 130,304), and 7,109 in the build for ADFS (4,610 before).

- **The banks as judged.** The compiler's are 13,648, 15,396, 14,223, 12,377 and 13,648 (bank 1, EXPR's, 1,818 smaller; bank 3, DECL's and ASMBLOCK's, 1,120). The linker's are 15,309, 15,016 and 16,031: its third bank, the fullest, still has 241 bytes left.
- **Main RAM free** (before, after), measured by the tests' reports:
  - eight-bank ROM form at ADFS's PAGE: compiler 2,253 to 2,274, linker 1,581 to 1,648;
  - sixteen-bank ROM form with `BBCFS 1`: compiler 3,874 to 3,895;
  - developer's form: compiler 7,658 to 7,652;
  - at ADFS's PAGE, ROM form: compiler 2,254 to 2,275, linker 2,312 to 2,379;
  - at ADFS's PAGE, developer's form: compiler 5,526 to 5,521, linker 2,762 to 2,830.

  The compiler's developer's forms lose 5 or 6 bytes: its fixed code is a little larger there. No split in `lathec-bbc.env` or `linker-bbc.env` needs to move.
- **Two estimates were low.** ASMBLOCK's positions saved 403 bytes (estimated 80 to 100): its 25 calls of `fail_at` with two words became a pointer each. EXPR's five functions saved 276 (estimated 50 to 80). `call_value` and `conversion` copy the caller's place first, `place = start[0]`, because a nested call may use the caller's record again; `target`, `assignment` and `pair_assignment` use it before any call.
- **Where the helpers live.** `need_name()` and `mark_place()` were first in LEX. On the BBC LEX is in another bank than EXPR (`lathec-bbc.env`), so each mark became a far call: the self-compile from the eight-bank image took 890.1 million cycles against 877.7 million before. Each of the twelve modules whose source was unchanged was 2 to 4 % slower. In PARTS, beside EXPR, the bytes are the same and the self-compile takes 873.2 million (−0.5 %).
- **The host** follows the Python subset (`test_shape.py`). Its place is a list `[line, col]` (`err.PLACE_LINE`, `PLACE_COL`) where the twin's is a record. A place kept at module level is two numbers in the host, because a list there would count as a table (`test_memory.py`). Each module's table "Where the Lathe differs" says so.

**Cycles.**
- **Wendy 2, the self-compile** (`bank_report.py --selfhost`, all eighteen modules): 834.5 million to 824.1 million (−1.25 %). Over the eleven modules whose source did not change, +0.12 %; EXPR −5.1 %, OUT −5.1 %, ASMBLOCK −3.2 %, DECL −2.6 %.
- **Wendy 2, the self-link** (`test_src_selflink.py`): the compiler's link 2,514 million to 2,398 million (−4.6 %: there is less of it); the linker's own +0.4 %.
- **The BBC, from the eight-bank image:** the self-compile 877.7 million to 873.2 million (−0.5 %), and the link of the compiler 3,463 million to 3,240 million (−6.4 %).
- **The BBC, the sixteen-bank form:** the self-compile 877.7 million to 873.2 million; the rebuild loop 4,802 million to 4,549 million (−5.3 %), and on two ADFS discs 4,822 million to 4,560 million (−5.4 %).
- **The BBC, small programs:** compiling, linking and running the 71 small programs of `test_bbc_toolchain.py` takes 0.46 % more in all, their links 0.43 % less. DECL's marks of a position are far calls to PARTS where they were copies in line.

**After the merge (2026-11-18).** The changes were merged with the integration branch (the 32K forms, the texts of the errors in the module, the Mode 7 check, FBUF's stores that nothing reads) and with the linker's fix-ups held in runs and link error 62 (commit c6f9140). Measured against c6f9140, built as each test builds it:

- **The 128 KB module, `BBCFS 0`:** 2,400 bytes free to **4,823** (+2,423). The module's code and the texts of the errors are 4,369 bytes in bank 3.
- **The 128 KB module, `BBCFS 1`:** 1,530 to 3,961.
- **The 128 KB module, the ADFS build:** 1,192 to 3,615.
- **The 32K image, the sixteen-bank form:** 80,323 to 80,370 bytes free.
- **The 32K image, the eight-bank form:** it still does not fit. The module's code and texts need 4,250 bytes at the end of one bank; the most room after a bank's code is 3,357 before, 3,472 now: 778 bytes short.

The banks as the linker judges them, before and after (`lk_judged.py` through each build's environment); nothing was moved, and every build links:

| Build | The compiler's five banks | The linker's banks |
|---|---|---|
| 128 KB, `BBCFS 0` | 15,568, 15,271, 15,130, 12,138, 13,360 to 13,759, 15,271, 14,007, 12,173, 13,360 | 15,529, 14,929, 15,884 to 15,529, 14,872, 15,884 |
| 128 KB, `BBCFS 1` | the same, bank 5 13,850 to 13,850 | 16,019, 14,929, 15,884 to 16,019, 14,872, 15,884 |
| 128 KB, ADFS | the same, bank 5 13,976 to 13,976 | 15,945, 15,134, 15,884 to 15,945, 15,077, 15,884 |
| 32K, eight banks | 16,071, 15,650, 15,788, 15,829, 15,476 to 14,239, 15,685, 14,665, 15,829, 15,476 | 16,051, 15,979, 15,884 to 16,051, 15,922, 15,884 |
| 32K, sixteen banks | as in eight | 6,572, 10,782, 9,168, 9,732, 12,070 to 6,572, 10,725, 9,168, 9,732, 12,070 |

The 32K compiler's bank 1 has 2,033 bytes left as judged, where it had 201. The linker's first bank is unchanged by these changes in every build (253 bytes left with `BBCFS 1`, 221 in the 32K eight-bank build).

**Main RAM free, after the merge** (before, after):

| Form | Compiler | Linker |
|---|---|---|
| Eight-bank ROM form at ADFS's PAGE | 2,140 to 2,161 | 1,665 to 1,736 |
| Sixteen-bank ROM form, `BBCFS 1` | 3,761 to 3,781 | |
| The developer's form | 7,397 to 7,390 | |
| ADFS, the ROM forms | 2,141 to 2,161 | 2,415 to 2,486 |
| ADFS, the developer's forms | 5,272 to 5,266 | 2,876 to 2,948 |
| The 32K form | 193 to 178 | |

The 32K form compiles 52 of the 75 modules of `lathe/src` and `lathe/rt` on the Model B, where it compiled 51: `copytest` fits now.

**Cycles, after the merge:**

| Run | Before | After | Change |
|---|---|---|---|
| Wendy 2, the self-compile (eighteen modules) | 828.0 million | 817.8 million | −1.23 % |
| BBC, the self-compile from the 128 KB image | 879.1 million | 874.7 million | −0.5 % |
| BBC, the link of the compiler | 3,194.6 million | 3,023.1 million | −5.4 % |
| BBC, the rebuild loop | 4,213.6 million | 4,039.8 million | −4.1 % |
| BBC, the rebuild on two ADFS discs | 4,218.7 million | 4,075.2 million | −3.4 % |
| BBC sixteen-bank form, the rebuild loop | 4,498.9 million | 4,316.3 million | −4.1 % |
| BBC sixteen-bank form, the rebuild on ADFS | 4,506.8 million | 4,349.6 million | −3.5 % |
| Wendy 2, the compiler's link | 2,343.0 million | 2,208.0 million | −5.8 % |
| Wendy 2, the linker's link | 1,326.2 million | 1,321.2 million | −0.4 % |

- On Wendy 2, the eleven modules whose source is unchanged take +0.14 %.
- The 72 small programs of `test_bbc_toolchain.py` take +0.51 % in all, and their links −0.17 %.
- For Wendy 2, `bank_report.py --selfhost` needs its counting copy given four options, now that the compiler is built with `-dRAM32` (a copy so changed measured this; the tool is unchanged).
## The linker on a 32K BBC, measured (2026-11-18)

What the linker's build for a 32K Model B (`linker-bbc.env` with `define RAM32 1`, every table in main RAM; [`bbc.md`](bbc.md), "The linker on a 32K BBC") links, and the shape of Lathe code it was balanced on. All by `lathe/tests/lk_ram32.py` (`shape`, `real`, `series`) and `test_lk_ram32.py` (the links on the BBC).

### The shape of Lathe code (counted)

The object files of the tools' own modules (the run-time modules left out), as build.py compiles them for `linker-bbc.env` and `lathec-bbc.env`, and of two of the real programs the assessment uses, compiled for the BBC all in one; code as the object files hold it, before zero page shrinks it:

| | the linker | the compiler | lextest | kerneltest |
|---|---|---|---|---|
| modules, functions | 19, 436 | 17, 744 | 5, 131 | 3, 98 |
| code bytes | 55,161 | 81,020 | 10,845 | 9,668 |
| code a function (median) | 126.5 (67) | 108.9 (67) | 82.8 (46) | 98.7 (55) |
| slots, of them parameters, a function | 3.64, 1.05 | 3.16, 1.33 | 2.91, 1.11 | 3.38, 1.27 |
| calls (CALL records) a function | 3.69 | 4.16 | 2.63 | 3.15 |
| fix-ups a function (most) | 33.9 (255) | 28.4 (263) | 21.8 (204) | 27.9 (204) |
| functions, symbols, symbols from outside, imports a module | 23.0, 69.4, 35.8, 7.0 | 43.8, 114.5, 50.8, 6.8 | 26.2, 56.4, 15.6, 3.6 | 32.7, 78.3, 23.3, 3.0 |
| variables a module (bytes) | 9.5 (2,938) | 17.2 (2,565) | 12.4 (1,678) | 11.0 (2,671) |
| bytes of object file a byte of code | 4.49 | 4.54 | 5.12 | 5.27 |

The test programs' functions are smaller than the tools' (83 to 99 bytes a function against 109 to 127), so as programs of a given size they have more functions: the assessment on them is the harder case. What the linker's tables hold of them, a function: about 1.0 node, 2.5 slots, 1.9 calls (the linker's rows, a call between two functions once), 2.0 symbols in object files and 0.5 variables or constants; the capacities of `LKSMALL 2` are in those proportions.

### The synthetic programs

Made of real programs (`lk_ram32.glue`): each piece's own modules renamed (`g1lex`...), the run-time modules once, a main that calls each piece's main, so that the shape is the real one and each piece keeps what it kept. Six series, each a real program with pieces added in order (errtest, copytest, srctest or typetest, then end-to-end cases of 1 to 2.6 KB) until the 32K build refuses it (the host linker at its capacities, which refuses where the Lathe-written build does):

| Series from | Largest that links, and fits mode 7 | Refused next | By |
|---|---|---|---|
| lextest | 25,034 (+ errtest, copytest, compare); up to 29,412 links, too large for mode 7 | 31,132 | functions, 310 (601 symbols in object files before the texts left `err`; until the fix-ups were held in runs: 29,412, by a test main's 344 fix-ups) |
| fbuftest | 26,125 links (14 bytes over mode 7); 23,509 fits | 30,049 | functions, 319 |
| kerneltest | 25,730; up to 31,066 links | 32,540 | calls, 578 |
| srctest | 21,764 (+ typetest, copytest: 296 functions, all there are) | 24,347 | functions, 316 (typetest's 59 bytes a function; 21,764 was refused, 297 functions, until the texts left `err`) |
| lktest1 | 22,457 (+ srctest, copytest) | 25,082 | symbols in object files, 624 |
| errtest | 25,988 (+ srctest, copytest, compare, reg_args, record_copy, control) | 27,380 | functions, 297 (until the runs: 24,272, by 344 fix-ups) |

The time of a link on the emulated BBC, 158 to 287 million cycles (1.3 to 2.4 minutes at 2 MHz) for 15 to 26 KB programs, and the files, are in [`bbc.md`](bbc.md). Since 2026-11-18 a function's fix-ups are held in runs ([`bbc.md`](bbc.md), "Fix-ups held in runs"): no series stops at a function's fix-ups any more; the cost of the runs was 384 bytes of the linker's bank 1 as judged, +0.28 % of the cycles of linking the compiler on the BBC (3,463,370,865 to 3,473,194,730) and +0.44 % on Wendy 2 (2,513,831,206 to 2,524,931,333), and for a function of 1,006 fix-ups in two contexts a reading of its file for each run and each offset outside the run (81 files opened, 218 million cycles on the BBC).

Link error 62 (an object compiled for a region in fixed memory, `-fREGION`, linked with the region in a bank; [`bbc.md`](bbc.md), "Link error 62") costs the linker's bank 1 139 bytes as judged in every eight-bank build (the ADFS build's `link` moved to bank 2 again to make room), 2 bytes of variables, and a look for the region of each variable and constant a fix-up of code names.

The 32K linker's capacities retuned to its free main RAM (2026-11-18; [`bbc.md`](bbc.md), "Capacities retuned"): calls 576 to 768, slots 800 to 848, symbols 592 to 640, 576 bytes; generated programs of 25 KB of the usual shape (2.8 calls a function) and of the tools' (3.4 to 3.7) link where calls refused them, the real programs as before. Weights that wait beyond the table read again from their WGT records ([`bbc.md`](bbc.md), "The order of the object files"): link error 41 retired, 103 bytes of bank 2 as judged, +4.1 % of cycles for a 16 KB generated program in `build.py`'s order (255,209,076 to 265,729,605 against `rt_math` first), nothing for an order whose weights fit.

## Error messages back in the ROM, measured (2026-11-18)

The owner's request: the texts of both tools' errors back in the 128 KB module, so that it stands alone without `LATHERR`, at as little cost as can be had, on a machine with sideways RAM (the B+128) and on one without (the `RAM32` build for a 32K Model B: nothing may be copied to a sideways RAM slot). From 8dd784a, where the gate (`test_bbc_rom128.py`) has 5,815 bytes free with `BBCFS 0` and 4,610 in the ADFS build. "Measured" is a build or a run; "estimated" says how.

### The schemes, on the real texts

`lathe/tests/msg_pack_report.py` packs `err.MESSAGES` and `lk_err.MESSAGES` (the compiler's 131 texts, 4,915 bytes, numbers 1 to 184; the linker's 61, 2,740 bytes) by each scheme, to the byte. Each text is in number order with an end of its own (a number with no text is an empty one), so a reader finds text n by passing n - 1 ends and needs no index; "apart" is each tool with its own tables, "both" one table for both tools. Data bytes (texts and the scheme's tables):

| Scheme | Compiler | Linker | Apart | Both |
|---|---|---|---|---|
| raw, each text ended by a zero (the numbers dropped) | 5,099 | 2,801 | 7,900 | 7,900 |
| packed 5-bit alphabet (30 codes, an escape to a byte) | 3,306 | 1,821 | 5,127 | 5,108 |
| packed 6-bit | 3,890 | 2,151 | 6,041 | 5,992 |
| Huffman of the characters | 2,884 | 1,602 | 4,486 | 4,442 |
| words 128 (a dictionary the tool chooses, a word one byte) | 2,613 | 1,400 | 4,013 | 3,712 |
| words 64 + Huffman | 2,343 | 1,277 | 3,620 | 3,359 |
| words 96 + Huffman | 2,361 | 1,296 | 3,657 | 3,309 |
| byte pairs (BPE), 128 pairs | 2,563 | 1,321 | 3,884 | 3,873 |
| **BPE, 159 pairs** (codes $80-$FF and $01-$1F) | **2,432** | **1,270** | **3,702** | **3,660** |
| BPE 159 + Huffman | 2,393 | 1,297 | 3,690 | 3,468 |

Against 5,494 + 2,803 = 8,297 as the tools held them (`number text` lines; the linker's with its fixed texts). Sharing the tables between the tools saves little for byte pairs (42 bytes) and about 300 for a word dictionary.

**The decoders, written in Lathe and compiled** (the compiler's, in fixed memory, reading the texts in the region `MSGS` inside `with MSGS`, its two tables of at most 2,048 bytes chosen by the error's number; bytes as placed in the eight-bank ROM form):

| Scheme | Decoder | Main RAM | Data (as built) | Total |
|---|---|---|---|---|
| **BPE 159** (`put_text`, a stack of 8 bytes for the pairs; run on the BBC) | **158** | 8 of frame | 2,434 | **2,592** |
| words 128 (`put_text`, the dictionary walked for each word) | 186 | 0 | 2,613 | 2,799 |
| Huffman, canonical (`symbol` 203, `put_text` 77) | 280 | 4 | 2,885 | 3,165 |
| words 64 + Huffman (`symbol` 176, `put_word` 79, `put_text` 90) | 345 | 4 | 2,344 | 2,689 |

The linker's BPE decoder in its bank 1, reading its tables by a word index so that they stay in the bank (a table whose address is taken is kept fixed): 141 bytes. Only the BPE decoders were run; the others were compiled and placed, not run. Byte pairs win in Lathe and are the plainest decoder: a code is a character, or a pair of two codes written in turn. The Huffman schemes save at most 250 bytes of data over them and lose it again in decoder, and their reader must decode every text before the one wanted (estimated: up to about 1.4 million cycles, against at most 55,000 below).

In assembly the 6502's own stack makes the pairs plainer still: one routine of 27 bytes, which pushes the second code and calls itself for the first (at most 6 levels, 3 bytes each).

### Where the texts live

**(a) Constants of each tool in a bank of the module, read in place.** Built: a generated module `errtext.lth` (the packed tables, written from `err.py` by a host tool, compiled like any other source) with its tables `in MSGS`, and `region MSGS WIN 4` in the ROM form (the compiler's fourth bank, image bank 3, which had 3,930 bytes left as judged); `err.put_text` reads them in a `with MSGS` block, which is right inside the `with` blocks of other regions that `err.fatal` is called in (there is one window: the block maps bank 3 and puts back the slot or bank it replaced). The linker's `lk_errtext.lth` is placed with `lk_err` in its bank 1 and read with no block. Measured: errors from the ROM with no file, the host's texts, one of them raised inside `with STRING` (sideways slot 13). But the linker's bank 1 had 963 bytes left as judged and needs 1,410: `lk_file` (651, few calls) had to move to bank 2, and the ADFS build, whose `bbcfs` is in that bank too, is then **357 bytes over**, with no other module small enough to move (the linker's three banks have 426 bytes left as judged in all in that build). Image: 2,063 bytes free with `BBCFS 0`. It also costs two generated sources (11 KB and 5.6 KB of text on the rebuild's discs), a module more in the self-compile, and texts in three places (`err.py`, `err.lth`'s copy for the other builds, the generated file).

**(b) The texts in the module, written by the module's own code (recommended).** The tools hold no texts in their ROM forms, as with the message file. `bbcrom.py` appends the packed tables of both tools (one table of pairs, written by a host tool from `err.py` and `lk_err.py` when the image is made) to the module's code in the home bank, and the module writes a text when a tool asks for it:

- The tool calls OSBYTE 143 (a service call to the ROMs) with X = `$4C` and Y = which text: the compiler's error n is text n, the linker's error n text 255 - n (one byte, one service call; the host tool checks that the two ranges do not meet: the compiler's numbers can grow to 193 before they would). `bbc.error_text` is 7 bytes of fixed code; `err.put_text` writes `: ` and calls it (17 bytes, fixed); `lk_err.put_text` likewise (23, in its bank).
- The MOS pages each ROM in and calls its service entry; the module's service code (the reserved bytes, the same in every bank, now 78 of 79) takes `$4C` as it takes 4 and 9: it pushes the bank it came in on and selects the home bank, which passes Y texts (each ended by a zero), writes the codes with OSWRCH, the pairs by the 27-byte routine above, and returns claimed through `claim`, which selects the bank of entry again. The MOS then selects again the slot that was selected before. So it works from any bank, from fixed code inside a `with` block of a sideways RAM slot (the MOS puts that slot back, since `rt_bbc` keeps `$F4` right), and on a machine with no sideways RAM. The routine uses `$A8`/`$A9` (the MOS's workspace for * commands, not the tools') and at most 21 bytes of stack.
- The code: 81 bytes in the home bank and 4 of the reserved bytes, assembled by `asm/pyasm.py` as `bbcrom.py` assembles `module.asm` (vasm is not used for it), and run on the emulated B+128. The data: 3,673 bytes (the 256 texts, the empty ones too; 320 of them the tables).

**(c) Looked at and left**: a reader in each tool that switches to a blob `bbcrom.py` places (fixed code in both tools, so main RAM in the linker too); a region both tools share (a bank file belongs to one program); copying a text to main RAM before writing it (a buffer of 160 bytes in each tool for nothing, since the module can write the text itself).

**Self-hosting.** In (b) the objects, interfaces, images and bank files of both tools are what they are today (no texts in the ROM forms), so the rebuild on the BBC gives the host's files as before; the texts come into the image where the image is made, on the host, from the tables the host tools print from. If the texts change and only the tools are rebuilt on the BBC, the module says the old texts until the image is made again, as `LATHERR` did until it was written again. In (a) the generated sources are compiled on the BBC like the rest and give the host's files too, but must be generated again (and tested to be current) whenever a text changes. The texts stay plain in one place, `err.py` and `lk_err.py`, in both designs (the twins keep their copy for every other build, as now).

### The fall-back

Drop `LATHERR` once the texts are in the ROM: it is the simplest and the smallest. The file's readers go (the compiler's 168 bytes of fixed code: `put_text` 89, the file's name 8, `bbc.open_unmapped` 54, `bbc.seek` 17; the linker's 77 in its bank and 25 fixed), and so do `msgfile.py` and the 9,258 bytes on every disc; `MESSAGE_FILE` becomes two-valued, the texts in the tool or in the module. Keeping the file as an override would cost those bytes again and a test for each way. On a machine where another ROM claims service call `$4C` first, an error prints its number and `: ` alone, with the same status.

### The experiment (b), measured

Built on 8dd784a and not committed (`messages-in-module.diff`, below): `lathe/host/driver/msgpack.py`, `module.asm`'s routine, `bbcrom.py` appending the tables (with `LATHE_MODULE_TEXTS=1`, for the experiment), `bbc.error_text`, `sys.error_text`, and `MESSAGE_FILE 2` in both tools' ROM forms.

| | Before (the message file) | After (the texts in the module) |
|---|---|---|
| The gate, `BBCFS 0`: free | **5,815** | **2,271** (the module's code and tables 4,281 bytes, 519 before) |
| The ADFS build (`BBCFS 2`, `ADFS 1`): free | **4,610** | **1,083** (the fullest bank as judged: the linker's bank 1, 403 left, 338 before) |
| The tools' banks as judged | | as before, but the linker's bank 1: 15,309 to 15,244 (15,869 with ADFS) |
| Resident parts, the compiler and the linker | 11,849 and 9,829 | 11,703 and 9,811 |
| Main RAM free, eight-bank ROM form, `BBCFS 0` | 3,874 and 3,215 | 4,020 and 3,233 |
| Main RAM free at ADFS's PAGE, `BBCFS 2` | 2,253 and 1,581 | 2,399 and 1,607 |

So the texts cost 3,544 bytes of the image (3,527 in the ADFS build): 3,673 of data, 81 of code and an entry of 8 more in a copy list, less the readers of the file; and they give the compiler 146 bytes of main RAM and the linker 18 (26 at ADFS's PAGE).

**On the emulated B+128, no file on the disc** (`--bbc-strict`, direct8): every case of `test_msgfile`'s (errors 136 with its value, 181 with `#error`'s text, 40, the usage 60; link errors 1 and 2, with the file's name) and two more, error 5 raised inside `with STRING` (slot 13) and error 182 (the longest text), print exactly what the host tools print; with `LATHERR` on the disc the same (the file is not read). From the eight-bank image the tool chain passes (`test_the_tool_chain_from_the_128k_image`), and the self-compile gives every file the host's, in 874.6 million cycles in the ROM form (877.0 before) and 912.5 million through LOADMOD (915.0). The gate's `test_errors_from_the_128k_image` fails as it must, in its cases without the file only: they expect the number alone. Not run: the linker's link of the compiler, the rebuild loops (the linker's code is the same but `lk_err.put_text`), the sixteen-bank image.

**Cycles.** `*LATHE` compiling an empty module, with no error: 878,957 (887,524 before: the resident part is 146 bytes shorter). Writing a text, with the start-up's difference taken out: error 60, 80 characters, about 11,600 cycles (11,700 from the file in the emulator, whose file reads cost nothing; on a real DFS the file's three sectors add about half a second); error 136, about 28,200; the linker's error 1, which passes every text before it, about 53,000 (27 ms at 2 MHz), the most any text takes.

**Readability.** 60 lines of `module.asm`, commented, the host tool (about 150 lines), and 4 to 7 lines in each of `err.lth`, `lk_err.lth`, `bbc.lth` and `sys.lth`; no generated source, and no texts in the tools' ROM forms.

**What remains to land it**: `bbcrom.py` holding the texts always (the module is Lathe's) or as an option the tools' images take, with its tests (`test_bbc_rom128.Layout` and `test_bbc_rom.py` check the home bank and the image's bytes, which change); `module.asm`'s header and `bbcrom.py`'s docstring; `MESSAGE_FILE` renamed and the file's path taken out of both twins (and their tables of "Where the Lathe differs"), with `bbc.open_unmapped`, `bbc.seek` and their `sys` wrappers if nothing else wants them; `msgfile.py` and `test_msgfile.py` replaced by a test of `msgpack.py` (every text unpacks to the host's, the numbering, the depth) and an emulator test that asks the module for every text; the cases without the file in `test_msgfile`, `test_bbc_dfs` and `test_bbc_adfs` (the loops' `message_file=True`); `bbc.md` ("The message file", "The 128 KB module", the gate's numbers); and the owner's choice of the service call's number (`$4C` is a guess at one no other ROM uses).

### Rewording, proposals for the owner (not applied)

Packed, a character saves about 0.46 bytes, so rewording pays little:

- The texts of link errors 38, 55 and 56, which are no longer reported (`lk_err.py`): left out, 60 bytes.
- The longest texts, if the owner finds shorter forms that are as clear: link error 40 (160 characters, 59 bytes packed), compiler 182 (123, 57), link 54 (109), compiler 136 (95), 184 (92) and 173 (90). I found nothing that says the same in fewer words without making it worse.
- No near-duplicates are worth merging: compiler 71 and link 9 are the same text (`too many symbols`), and the pairs share it already; 134 and 150 differ in one word; the linker's 19 prefixes `environment file: ` cost about 2 bytes each.

### Built: the texts in the module (2026-11-18)

The owner chose (b), with the service call `$4C`; built in place of the message file, which is gone ([`bbc.md`](bbc.md), "The texts in the module"; `define TEXTS_IN_MODULE`). The module writes `: ` as well as the text, so that an error is its number alone when no ROM answers; its routine is 91 bytes. The gate: **2,295 bytes free** with `BBCFS 0`, **1,107** in the ADFS build; main RAM free in the eight-bank ROM form 4,037 and 3,233 with `BBCFS 0`, 2,416 and 1,607 at ADFS's PAGE. Every build that is not a ROM form is byte for byte as before (images, bank files, maps, objects and interfaces) but `bbc`'s object and interface and `sys`'s interface, which lost `open_unmapped` and `seek` and gained `error_text`.

### Recommendation

(b): byte pairs, both tools' texts in one table in the home bank, written by the module at a service call, and `LATHERR` dropped. The module stands alone, nothing is copied to a sideways RAM slot, the tools lose code and gain main RAM, and the image keeps 2,271 bytes free (1,083 in the ADFS build). (a) fits the `BBCFS 0` build with 2,063 free but not the ADFS build, and costs generated sources.

The experiment's files are in the session's scratchpad, in `research-messages/`: `messages-in-module.diff` (design (b); it applies to 8dd784a), `design-a.diff` with `errtext.lth` and `lk_errtext.lth` (design (a)), `variants.py` (the decoders compiled), `errruns.py` (the errors on the BBC) and their logs.

## One ROM for every BBC: a study (measured) (2026-11-18)

The owner's question: can the 128 KB ROM that is shipped adapt to the RAM it finds, so that one image serves a B+128, a Master 128 and a Model B with one of the common sideways RAM boards, with tables sized and placed at run time, `with` blocks that cost nothing when no bank is switched, and the bank switching kept for those who have sideways RAM; and, for code that loops over a table inside a block, whether that code can stay in main RAM while single accesses go through accessors that switch or not. This is a study: nothing in the tools changed. What was measured is said so; what was worked out from measurements is *extrapolated*; what rests on memory of the machines is *from memory, unverified*.

**In short.** One ROM for every BBC *with* sideways RAM pays, and costs little: the tables that are in regions are touched only by code in main RAM (the resident part, which the module copies from the ROM at every command), so every place that names a region is in that copy and can be patched as it is copied: the slot of each region found at run time, each table placed where there is room (sideways RAM, the RAM below a fixed base for the machines whose PAGE is lower, the shadow screen's kilobyte), its capacity chosen then, and the blocks of a region in main RAM turned into nothing. That costs no cycles on any machine, no main RAM, and about 2.5 KB of the ROM, and it changes neither the compiler nor any object file. Measured: a Model B with two banks of sideways RAM runs the full compiler (the self-compile, every file the host's, 877.0 million cycles, as on the B+128), and on a machine with no sideways RAM a block patched to nothing saves 67 cycles (7.7 % of a link). What does not pay is the same ROM for the bare 32K Model B: there the 8 KB of the compiler's code kept in main RAM for its blocks, and the linker's function and variable columns, which banked code reads directly, leave too little for tables; every way round it costs the machines with sideways RAM speed (6 to 38 %) or the ROM a second copy of that code, and still gives the bare Model B less than the 32K images do. So: one adaptive ROM for every machine with at least one bank, and the 32K images for the bare Model B (or RAM on the module's board, which makes it a machine with banks).

### How it was measured

- **The census**: `lathe/tests/with_census.py` (new, with `test_with_census.py`), from the links of the eight-bank ROM forms (`test_bbc_rom128.build_tools`, `BBCFS 0`, the tree at a46df62): every function in fixed memory that is kept for a block, has one, or runs inside one; its bytes (the map), its regions (the RGN records behind each kind 6 fix-up; for a function that runs inside another's block, the regions of the blocks it runs in), why it is fixed, and whether it loops while a region is mapped (the twin's source: a `loop`, `for` or `while` inside a block, or anywhere in a function that runs inside one, or a call inside a block of one that does).
- **Calls and cycles**: a copy of the emulator (`emulator/bbc_mos.c`, a scratch diff, not committed) that counts, for every PC, the instructions run and their cycles, the window's PCs by the module's bank, and writes them at the end of a run (`LATHE_PCHIST`). The self-compile (18 compiles) and the linker's link of the compiler, from the eight-bank image as `test_bbc_rom128.py` runs them, every file the host's: 876,992,789 and 3,463,370,865 cycles, as `bbc.md` has them; the histograms hold 99.8 % of them. A function's calls are the times its first instruction ran.
- **Accesses**: the host compiler over the same 18 compiles, every region table wrapped to count each read and write by the host function that made it (the twins' functions are the host's, so the counts are the twin's accesses at the source level). Checked against the first experiment below, where every such access became an accessor call: the host counts 607,344 reads of a byte in the functions it converted and 350,784 bytes read as words, the experiment's emulator 606,949 calls of `name_byte` and 175,392 of `name_word`.
- **Experiments**, each a diff in the scratchpad (paths in the hand-back), on the emulated B+128 from the eight-bank image, every file of every compile the host's; the converted compiler compiled the *unchanged* sources, so its inputs were those of the baseline.

### The census (measured)

`python3 lathe/tests/with_census.py WORK MAP [--hist FILE...]` prints the tables below from a link's objects and map.

| | The compiler (`*LATHE`) | The linker (`*LLINK`) |
|---|---|---|
| Resident part (code, stubs, constants copied to main RAM) | **11,849** | **9,829** |
| Functions with a block whose block loops (or calls, inside it, one that loops) | 30: 3,777 bytes, 534 lines of source | 7: 2,248 bytes, 169 lines (6 of them `lk_tab`'s, which runs its chains once a link) |
| Functions with a block, one access or a few, no loop | 37: 1,970 | 37: 2,362 |
| Fixed only because they run inside a block, looping | 10: 844 (`fbuf.widen`, `count_use`, `walk_step`, `err.put_*`, `kernel.name_is_new`, `spelling_hash`...) | none |
| Fixed only because they run inside a block, no loop | 31: 1,431 (`fbuf.emit_entry` 373, `src.advance`, `lex.fold`, `is_letter`...) | none |
| So: "loop" functions, single-access functions | **4,621** and **3,401** (all 8,022 kept by the linker's rule) | **2,248** and **2,362** (721 kept by the rule; 3,889 are `lk_tab`'s, fixed because every phase calls it) |
| The rest of the resident part | 3,827: stubs 1,638 (273), `bbc` 741, `rt_bbc` 407, constants 361, `rt_math` 348, `rt_frame` 171, `sys` 78, start-up 83 | 5,219 besides `lk_tab`'s blocks: the rest of `lk_tab` 1,828, `bbc` 690, `lk_out` 425, `lk_rec` 407, `rt_bbc` 407, stubs 384 (64), `rt_math` 290, constants 284, `lk_sym` 217, `lk_op` 122, `sys` 82, start-up 83 |
| Blocks entered (the self-compile / the compiler's link) | 1,091,279: `rt_bbc.map` and `unmap` 76.9 million cycles, 8.8 % | 9,646,936: 681.4 million cycles, **19.7 %** |
| Far calls | 505,751: `call` and `back` 104.2 million cycles, 11.9 % | 94,714: 19.5 million, 0.6 % |
| Cycles in the resident part's own code | kept functions 384.7 million (44 % of the self-compile), `rt_bbc` 181.0, `bbc` 31.8, `rt_frame` 30.9, `rt_math` 20.6, `sys` 16.6 | `lk_tab` 858.3 million (25 %), `rt_bbc` 700.9, `lk_sym` 335.5, kept 284.0, `lk_rec` 270.3, `bbc` 158.3, `sys` 89.5 |

The owner's count from the source (69 and 25 functions, about 490 lines; 44 and 7, 160 lines) is close: the linked build has 67 functions with a block in the compiler, 30 of them looping, and 44 and 7 in the linker. A block from fixed code costs about 88 cycles on the B+128 (70 in `rt_bbc`, the rest the `LDA #bank`, the two calls and the temporary), as against 24 all in one.

Every function, with the calls and the cycles of its own code (not its callees') in the self-compile and in the compiler's link. *Region* is the region of its own blocks, or for a function kept only for running inside blocks, every region of the blocks it is reached inside (the error path, `err`, is reached inside four). *Loops (all of it inside)*: kept only for running inside a block, and loops. A count of 0: never entered in that run.


**The compiler** (the self-compile, 18 compiles):

| Function | Bytes | Region | Kept for | Loop | Calls | Own cycles |
|---|---|---|---|---|---|---|
| `err.position` | 21 | STRING, WANTS | inside | - | 146,184 | 4,970,256 |
| `err.put_decimal` | 92 | FUNCBUF, NAMES, STRING, WANTS | inside | loops (all of it inside) | 0 | 0 |
| `err.put_place` | 106 | FUNCBUF, NAMES, STRING, WANTS | inside | loops (all of it inside) | 0 | 0 |
| `err.put_text` | 89 | FUNCBUF, NAMES, STRING, WANTS | inside | loops (all of it inside) | 0 | 0 |
| `err.put_char` | 5 | STRING | inside | - | 0 | 0 |
| `err.fatal_end` | 10 | FUNCBUF, NAMES, STRING, WANTS | inside | - | 0 | 0 |
| `err.fatal_start` | 72 | FUNCBUF, NAMES, STRING, WANTS | inside | loops (all of it inside) | 0 | 0 |
| `err.fatal` | 9 | FUNCBUF, NAMES, STRING, WANTS | inside | - | 0 | 0 |
| `kernel.token_start` | 16 | TOKENS | block | - | 18 | 378 |
| `kernel.token_byte` | 20 | TOKENS | block | - | 1,187 | 35,610 |
| `kernel.set_token_byte` | 24 | TOKENS | block | - | 678 | 25,086 |
| `kernel.path_add` | 38 | NAMES | inside | - | 1,794 | 98,670 |
| `kernel.get` | 121 | TOKENS | block+inside | - | 663,021 | 49,750,473 |
| `kernel.put` | 16 | FUNCBUF, NAMES, OUTTAB | inside | - | 382,888 | 8,806,424 |
| `kernel.put_word` | 14 | FUNCBUF, OUTTAB | inside | - | 85,954 | 1,805,034 |
| `kernel.name_word` | 69 | NAMES | block+inside | - | 47,073 | 4,742,646 |
| `kernel.name_set_word` | 58 | NAMES | block+inside | - | 21,911 | 1,862,435 |
| `kernel.name_byte` | 31 | NAMES | block | - | 26 | 1,220 |
| `kernel.name_set_byte` | 35 | NAMES | block | - | 30 | 1,590 |
| `kernel.name_begin` | 37 | NAMES | inside | - | 60,273 | 2,900,621 |
| `kernel.name_add` | 80 | NAMES | block | - | 147,066 | 18,236,326 |
| `kernel.name_is_new` | 62 | NAMES, WANTS | inside | loops (all of it inside) | 168,379 | 17,261,561 |
| `kernel.name_end` | 250 | NAMES | block+inside | loops | 44,687 | 23,665,428 |
| `kernel.name_length` | 31 | NAMES | block | - | 12,190 | 572,022 |
| `kernel.name_char` | 54 | NAMES | block | - | 26,242 | 2,123,573 |
| `kernel.name_token` | 31 | NAMES | block | - | 42,685 | 2,002,222 |
| `kernel.name_set_token` | 35 | NAMES | block+inside | - | 900 | 47,700 |
| `kernel.names_release` | 86 | NAMES | block | loops | 824 | 3,556,498 |
| `kernel.path_add_name` | 56 | NAMES | block | loops | 196 | 44,159 |
| `kernel.put_name` | 71 | NAMES | block | loops | 3,502 | 1,090,877 |
| `kernel.byte_of` | 52 | SYMS | block | - | 14,055 | 1,118,557 |
| `kernel.word_of` | 60 | SYMS | block | - | 83,070 | 7,998,082 |
| `kernel.set_byte` | 59 | SYMS | block | - | 57,561 | 5,065,368 |
| `kernel.set_word` | 71 | SYMS | block | - | 35,788 | 3,900,892 |
| `kernel.scope_of` | 31 | SYMS | block | - | 41,933 | 1,943,017 |
| `kernel.kind_of` | 31 | SYMS | block | - | 128,354 | 5,985,641 |
| `kernel.flags_of` | 31 | SYMS | block | - | 94,128 | 4,414,997 |
| `kernel.type_of` | 31 | SYMS | block | - | 18,509 | 851,928 |
| `kernel.params_of` | 31 | SYMS | block | - | 17,847 | 828,456 |
| `kernel.value_of` | 45 | SYMS | block | - | 16,865 | 1,198,203 |
| `kernel.member_type_of` | 31 | SYMS | block | - | 55,721 | 2,588,872 |
| `kernel.member_value_of` | 31 | SYMS | block | - | 2,864 | 132,958 |
| `kernel.chain_walk` | 80 | SYMS | block | loops | 15,171 | 972,945 |
| `kernel.spelling_hash` | 57 | NAMES | inside | loops (all of it inside) | 3,106 | 1,941,116 |
| `kernel.same_spelling` | 102 | NAMES | block | loops | 4,637 | 377,844 |
| `kernel.built_is` | 56 | NAMES | block+inside | calls one that loops | 2,332 | 185,818 |
| `kernel.name_hash` | 33 | NAMES | block | calls one that loops | 3,106 | 152,194 |
| `kernel.member_add` | 100 | SYMS | block | - | 2,610 | 347,322 |
| `fbuf.entry_runs_on` | 65 | FUNCBUF | inside | - | 35,083 | 2,770,660 |
| `fbuf.end_entry` | 174 | FUNCBUF | block | loops | 34,492 | 13,252,983 |
| `fbuf.set_symbol` | 41 | FUNCBUF | block | - | 71 | 4,473 |
| `fbuf.new_label` | 73 | FUNCBUF | block | - | 3,009 | 291,873 |
| `fbuf.same` | 21 | FUNCBUF | inside | loops (all of it inside) | 32,206 | 779,060 |
| `fbuf.join` | 63 | FUNCBUF | block | - | 70 | 7,210 |
| `fbuf.is_used` | 32 | FUNCBUF | block | calls one that loops | 2,579 | 118,645 |
| `fbuf.use_label` | 30 | FUNCBUF | block | calls one that loops | 3,518 | 154,792 |
| `fbuf.skips_jump` | 51 | FUNCBUF | inside | - | 5,836 | 167,332 |
| `fbuf.skips_nothing` | 59 | FUNCBUF | inside | - | 2,902 | 125,595 |
| `fbuf.tidy` | 281 | FUNCBUF | block | calls one that loops | 2,929 | 567,938 |
| `fbuf.tail_call` | 95 | FUNCBUF | block | - | 1,083 | 97,850 |
| `fbuf.runs_on` | 45 | FUNCBUF | block | - | 4,064 | 264,160 |
| `fbuf.thread` | 283 | FUNCBUF | block+inside | loops | 752 | 5,362,526 |
| `fbuf.entry_size` | 34 | FUNCBUF | inside | - | 288,958 | 6,107,806 |
| `fbuf.code_size` | 65 | FUNCBUF | inside | - | 116,863 | 5,938,296 |
| `fbuf.layout` | 126 | FUNCBUF | block+inside | loops | 797 | 4,358,384 |
| `fbuf.target` | 47 | FUNCBUF | block+inside | calls one that loops | 13,663 | 833,443 |
| `fbuf.reaches` | 61 | FUNCBUF | inside | - | 3,469 | 197,905 |
| `fbuf.widen` | 147 | FUNCBUF | inside | loops (all of it inside) | 797 | 4,500,051 |
| `fbuf.has_zero_page_form` | 59 | FUNCBUF | inside | - | 60,291 | 1,536,204 |
| `fbuf.find_loops` | 231 | FUNCBUF | block+inside | loops | 752 | 5,050,260 |
| `fbuf.use_weight` | 88 | FUNCBUF | block+inside | loops | 1,565 | 786,913 |
| `fbuf.count_use` | 127 | FUNCBUF | inside | loops (all of it inside) | 1,565 | 254,947 |
| `fbuf.emit` | 20 | FUNCBUF | inside | - | 243,765 | 8,045,640 |
| `fbuf.fix` | 50 | FUNCBUF | inside | - | 63,495 | 4,635,135 |
| `fbuf.emit_jump` | 13 | FUNCBUF | inside | - | 1,305 | 22,185 |
| `fbuf.emit_to` | 42 | FUNCBUF | inside | - | 1,527 | 93,147 |
| `fbuf.emit_entry` | 373 | FUNCBUF | inside | - | 103,257 | 21,151,254 |
| `fbuf.walk_begin` | 13 | FUNCBUF | inside | - | 2,256 | 49,632 |
| `fbuf.walk_step` | 71 | FUNCBUF | inside | loops (all of it inside) | 97,335 | 10,722,372 |
| `fbuf.put_fixups` | 95 | FUNCBUF | block | loops | 752 | 2,716,084 |
| `fbuf.put_code` | 56 | FUNCBUF | block | loops | 752 | 3,986,553 |
| `fbuf.finish` | 153 | FUNCBUF | block | loops | 752 | 1,147,631 |
| `src.next_byte` | 20 | STRING | inside | - | 888 | 31,080 |
| `src.advance` | 68 | NAMES, STRING | inside | - | 522,618 | 31,546,240 |
| `lex.string_byte` | 31 | STRING | block | - | 6,164 | 288,722 |
| `lex.init` | 179 | NAMES | block | loops | 18 | 609,804 |
| `lex.fail_here` | 22 | STRING | inside | - | 0 | 0 |
| `lex.fold` | 15 | NAMES, STRING | inside | - | 560,316 | 9,940,654 |
| `lex.is_letter` | 19 | NAMES | inside | - | 345,787 | 9,859,659 |
| `lex.digit_value` | 40 | STRING | inside | - | 7,118 | 207,648 |
| `lex.name_or_keyword` | 144 | NAMES | block | loops | 42,649 | 32,955,934 |
| `lex.hex_digit` | 25 | STRING | inside | - | 0 | 0 |
| `lex.escape` | 129 | STRING | inside | - | 159 | 14,954 |
| `lex.literal_char` | 30 | STRING | inside | - | 6,164 | 212,242 |
| `lex.string_token` | 82 | STRING | block | loops | 158 | 455,275 |
| `lex.error_directive` | 122 | STRING | block | loops | 0 | 0 |
| `lex.saved_token` | 185 | STRING | block | loops | 348 | 36,897 |
| `out.data_byte` | 8 | OUTTAB | inside | - | 6,647 | 73,117 |
| `out.table_begin` | 78 | OUTTAB | block | loops | 46 | 309,681 |
| `out.table_byte` | 35 | OUTTAB | block | - | 6,346 | 336,338 |
| `out.table_fix` | 91 | OUTTAB | block | - | 4 | 508 |
| `out.table_end` | 275 | OUTTAB | block | loops | 46 | 335,821 |
| `decl.add_want` | 167 | WANTS | block | loops | 1,515 | 1,543,377 |
| `decl.listed` | 31 | WANTS | block+inside | - | 9,371 | 296,353 |
| `decl.not_exported` | 42 | WANTS | block+inside | - | 0 | 0 |
| `decl.wanted` | 174 | WANTS | block | loops | 7,854 | 5,830,732 |
| `decl.pending` | 214 | WANTS | block | - | 30 | 66,280 |
| `decl.check_found` | 41 | WANTS | block | loops | 96 | 48,522 |

**The linker** (its link of the compiler; `lk_tab`'s functions are fixed with their module, the rest kept by the rule):

| Function | Bytes | Region | Kept for | Loop | Calls | Own cycles |
|---|---|---|---|---|---|---|
| `lk_tab.wk` | 111 | LKNODES, LKWORK | block+inside, fixed module | - | 732,362 | 65,911,554 |
| `lk_tab.set_wk` | 99 | LKNODES, LKWORK | block+inside, fixed module | - | 808,258 | 68,734,731 |
| `lk_tab.new_func` | 166 | LKCALLS | block, fixed module | - | 816 | 204,849 |
| `lk_tab.new_slot` | 172 | LKSLOTS | block, fixed module | - | 2,474 | 366,247 |
| `lk_tab.run_start` | 79 | LKCALLS | block, fixed module | - | 284,862 | 27,271,892 |
| `lk_tab.run_end` | 118 | LKCALLS | block, fixed module | - | 814,201 | 104,795,332 |
| `lk_tab.add_own` | 251 | LKCALLS | block, fixed module | loops | 3,146 | 1,918,670 |
| `lk_tab.add_waiting` | 315 | LKCALLS | block, fixed module | loops | 21 | 23,265 |
| `lk_tab.head_of` | 75 | LKCALLS | block, fixed module | - | 5,543 | 508,402 |
| `lk_tab.set_head` | 82 | LKCALLS | block, fixed module | - | 3,372 | 354,060 |
| `lk_tab.build_chains` | 792 | LKCALLS | block, fixed module | loops | 1 | 457,052 |
| `lk_tab.add_edge` | 258 | LKCALLS | block, fixed module | loops | 255 | 255,965 |
| `lk_tab.chains_to_runs` | 380 | LKCALLS | block, fixed module | loops | 1 | 829,934 |
| `lk_tab.edge_at` | 45 | LKCALLS | block, fixed module | - | 3,135 | 227,233 |
| `lk_tab.set_edge_at` | 48 | LKCALLS | block, fixed module | - | 3,135 | 241,395 |
| `lk_tab.edge_sym` | 62 | LKCALLS | block, fixed module | - | 1,322,574 | 124,976,946 |
| `lk_tab.edge_flag` | 53 | LKCALLS | block, fixed module | - | 12,078 | 999,458 |
| `lk_tab.slot_bytes` | 141 | LKSLOTS | block, fixed module | loops | 245,278 | 19,230,908 |
| `lk_tab.slot_weight_of` | 31 | LKSLOTS | block, fixed module | - | 699,685 | 32,618,184 |
| `lk_tab.set_slot_weight` | 35 | LKSLOTS | block, fixed module | - | 690 | 36,570 |
| `lk_tab.set_slot_zp` | 35 | LKSLOTS | block, fixed module | - | 96 | 5,204 |
| `lk_tab.flip_slot_zp` | 35 | LKSLOTS | block, fixed module | - | 6,297 | 341,549 |
| `lk_tab.slot_class` | 37 | LKSLOTS | block, fixed module | - | 11,990 | 674,280 |
| `lk_tab.slot_in_zp` | 35 | LKSLOTS | block, fixed module | - | 171,700 | 8,619,741 |
| `lk_tab.new_node` | 118 | LKNODES, LKWORK | block, fixed module | - | 0 | 0 |
| `lk_tab.own_of` | 59 | LKWORK | block, fixed module | - | 1,666,674 | 41,666,850 |
| `lk_tab.ctx_of` | 43 | LKNODES | block, fixed module | - | 915,503 | 59,204,404 |
| `lk_tab.zbase_of` | 42 | LKNODES | block, fixed module | - | 49,935 | 3,131,145 |
| `lk_tab.set_zbase` | 82 | LKNODES | block, fixed module | - | 789 | 102,314 |
| `lk_tab.mbase_of` | 49 | LKNODES | block, fixed module | - | 49,935 | 3,817,833 |
| `lk_tab.slot_is_param` | 41 | LKSLOTS | block, fixed module | - | 0 | 0 |
| `lk_name.local_at` | 45 | LKLOCAL | block | - | 5,329 | 381,281 |
| `lk_name.set_local` | 48 | LKLOCAL | block | - | 7,397 | 569,569 |
| `lk_name.global_sym` | 98 | LKLOCAL | block | - | 139,833 | 19,125,578 |
| `lk_graph.scc_of` | 45 | LKWORK | block | - | 1,275,083 | 92,554,277 |
| `lk_graph.order_at` | 45 | LKWORK | block | - | 748,641 | 54,340,133 |
| `lk_graph.seen_of` | 45 | LKWORK | block | - | 4,997 | 362,239 |
| `lk_graph.low_of` | 45 | LKWORK | block | - | 1,242 | 90,024 |
| `lk_alloc.base_of` | 45 | LKWORK | block | - | 393,846 | 28,432,518 |
| `lk_alloc.end_of` | 47 | LKWORK | block | - | 17,821 | 1,326,931 |
| `lk_alloc.size_of` | 45 | LKWORK | block | - | 312,480 | 22,606,944 |
| `lk_alloc.down_of` | 47 | LKWORK | block | - | 330,301 | 24,630,965 |
| `lk_fix.shrinks` | 55 | LKWORK | block+inside | - | 252,073 | 18,710,463 |
| `lk_fix.removed_before` | 111 | LKWORK | block | loops | 6,585 | 20,848,602 |

### Experiments (measured)

On the emulated B+128 from the eight-bank image, the self-compile (18 compiles, ROM form) or a link, every file the host's:

| Experiment | What changed | Result |
|---|---|---|
| Baseline | the tree at a46df62 | self-compile **876,992,789** cycles; the compiler's link 3,463,370,865 |
| E1: per-access accessors for kernel's name heap and symbol table | the twin's `name_end`, `name_is_new`, `names_release`, `path_add_name`, `put_name`, `spelling_hash`, `same_spelling`, `built_is`, `name_hash` and `chain_walk` read the heap and the columns only through `name_byte`, `name_word`, `name_set_*`, `name_length`, `name_char`, `scope_of`, `word_of` (as the host does already), and LEX's name loop calls `name_add` a character instead of one block a name: none has a block, so all of them are code of kernel's and LEX's bank | **989,214,227 (+12.8 %)**; blocks 1,091,279 to 1,962,909 (+871,630), so **129 cycles for each access that becomes an accessor's block**; resident part 11,849 to 11,145 (−704); the image's free bytes 5,815 to 6,045 |
| E1b: the same, the hot two kept | E1 with `name_end`, `name_is_new`, `built_is` and LEX's loop as they were: the eight cold functions only | **885,407,353 (+0.96 %)**; resident part 11,358 (−491) |
| Two banks | `lathec-bbc.env` with the regions in two slots (12: `NAMES`, `FUNCBUF`, `STRING`, 16,128 bytes; 13: `SYMS`, `OUTTAB`, `WANTS`, 16,240) and `TOKENS` in main RAM, the split at `$4900`; the emulator with `--bbc-sideways-ram 12,13` | the full compiler on a machine with **32 KB of sideways RAM: 876,983,721**, the same as with four; every file the host's |
| E2: blocks patched to nothing | the linker's 32K build (every region in main RAM; each block maps slot 0 for nothing), its resident part patched as a copier would for a machine with no sideways RAM: each `JSR rt_with.map` and `JSR unmap` three NOPs, each `JMP unmap` an RTS (109 places); lextest linked | 157,323,854 to **145,231,950 (−7.7 %)**, the host linker's files; 180,743 blocks, so **67 cycles saved a block** |
| Capacities and objects | the host compiler at full size and at the small build's capacities, on every module the end-to-end cases import that both compile | **62 modules, every object and interface the same**: what a machine's capacities decide is whether a module compiles, not what it compiles to |

**Extrapolated from them.** With every access of the compiler's loops through an accessor (design (a) below), the host's counts give 3.68 million accessor blocks where there are 1.09 million: E1 measured 0.87 million of the 2.59 million more, and the rest at E1's 129 cycles is about 222 million: **about 1,211 million for the self-compile, +38 %** (FUNCBUF 1.47 million blocks more, WANTS 0.22, the rest little; the symbol table nothing, since every access of it is through an accessor already). Kept by size of what they save (cycles saved a byte of main RAM, from the same counts), the compiler's looping functions are steeply unequal:

| Kept in main RAM with its block (and what runs inside it) | Bytes | Blocks it saves | Cumulative bytes | What is left of the +38 % |
|---|---|---|---|---|
| `kernel.name_end` with `name_is_new` | 312 | 538,000 | 312 | |
| LEX's name loop (`name_or_keyword` with `src.advance`, `fold`, `is_letter`) | 246 | 319,000 | 558 | |
| `decl.wanted` | 174 | 165,000 | 732 | |
| `fbuf.layout` with `entry_size`, `code_size` | 225 | 205,000 | 957 | |
| `fbuf.put_fixups` with `emit_entry` and nine more | 877 | 531,000 | 1,834 | |
| `fbuf.thread` | 283 | 145,000 | 2,117 | about +6 % |
| `decl.add_want`, `kernel.name_hash`, `fbuf.finish`, `end_entry` (with the error path) | 1,019 | 318,000 | 3,136 | about +2.4 % |
| the other 18 | 2,916 | 78,000 | 6,052 | 0 |

E1b measured the cold end of this: eight functions, 491 bytes of main RAM for +1 %.

### What decides the designs

1. **Every reference to a region is in the resident part.** A region's names may appear only inside its blocks (error 118), and the linker keeps in fixed memory every function with a block and all that runs inside one, so no code in a ROM bank names a region (checked on the links: the only such fix-ups outside fixed code are three in `fbuf.walk_next`, which the compiler's link does not keep). The places: the compiler **291** fix-ups that name a variable of a region, and 145 block calls (`JSR rt_with.map` 69, `JSR unmap` 22, `JMP unmap` 54); the linker 194 and 109. The module copies the resident part from the ROM at every command, so all of these can be set as it is copied: that is the mechanism of everything below, and costs no cycles after the start.
2. **What cannot move**: code, and every variable that banked code names: the ROM's code has their addresses. In the compiler that is `kernel.text` (2,048), REG's slot columns (1,536) and every other table not in a region (9,874 bytes of variables, 10,388 with the frames); in the linker the functions', variables' and classes' columns (about 10.5 KB at full size: `fn_slot` 1,792, `def_a` and `def_b` 1,600 each, `fn_flags`, `fn_ctx`, `fn_class` 896 each, `def_f` 800, the classes' 1.2 KB), read directly by nine modules in four banks.
3. **Code with a block must run from main RAM when its region is in sideways RAM**, and on a machine with none, the 8 KB of the compiler's kept code is 8 KB of tables lost. That one fact separates the bare Model B from every machine with a bank.

### The designs, machine by machine

Main RAM for tables is what is left of PAGE to HIMEM and `$0401-$06FF` once the fixed part (the resident part, and the variables and frames that cannot move, 10,388 bytes for the compiler and 13,067 for the linker) is placed; the fixed part is linked from `$1F00` in every design here, so that one image serves PAGE `$1900` and `$1F00` ("PAGE", below). Capacities are each region table at the same fraction of its full size, packed whole into the room there is (worked out; the full compiler needs 34,416 bytes of region tables, the full linker 43,248). Machines (from memory, unverified: PAGE `$1900` with the DFS on a Model B and a B+, `$1F00` with ADFS and the DFS, `$0E00` on a Master, whose filing systems use its own hidden RAM; HIMEM `$7C00` in mode 7, `$8000` in a shadow mode on a B+ or a Master): **B** a 32K Model B with the DFS; **B1**, **B2** the same with one and two 16 KB banks; **B+** the B+128, four banks, the DFS; **M** a Master 128, four banks (4 to 7), shadow screen.

**The compiler.**

| Design | | B (no SWR) | B1 | B2 | B+ (DFS; ADFS+DFS) | M (shadow) |
|---|---|---|---|---|---|---|
| **(b) Today's structure, placed at run time** (the owner's hybrid as it stands: every loop in main RAM, single accesses through the accessors there are, each switching or not) | main RAM: code / for tables | 11,849 / 3,874 | 11,849 / 3,874 | 11,849 / 3,874 | 11,849 / 3,874; 2,338 | 11,849 / 7,714 |
| | sideways RAM for tables | 0 | 16,352 | 32,704 | 65,408 | 65,408 |
| | capacities (fraction of full: names, symbols, function buffer) | 0.11: 1,017, 61, 452 (nothing useful) | 0.57: 5,248, 318, 2,332 | **1.00** (measured, above) | 1.00, 34.9 KB to spare | 1.00, 38.7 KB to spare |
| | cycles, the self-compile | (a compile, had it the room: blocks patched, about −8 %) | about 877 million | **877.0 million (measured)** | **877.0 million (measured)** | about 870 million (the tables that fit main RAM unbanked) |
| **(a) Thin accessors in main RAM for every access, all logic in the ROM** | main RAM: code / for tables | about 6,100 / 9,623 | 6,100 / 9,623 | / 9,623 | / 9,623; 8,087 | / 13,463 |
| | capacities | 0.28: 2,545, 154, 1,131 (the 32K image: 3,072, 264, 1,536) | 0.73: 6,772, 411, 3,009 | 1.00 | 1.00 | 1.00 |
| | cycles | a compile about 10 % slower than on the B+128 today (blocks patched; 960 million for the 18, had they fitted) | **about 1,211 million (+38 %)**: 112 measured, 222 extrapolated | 1,211 | 1,211 | 1,211 |
| **(b′) The hybrid as costed: (a), with the six hottest loops kept** (2.1 KB) | main RAM: code / for tables | about 8,200 / 7,523 | / 7,523 | / 7,523 | / 7,523; 5,987 | / 11,363 |
| | capacities | 0.22: 2,006, 121, 891 | 0.68: 6,272, 381, 2,787 | 1.00 | 1.00 | 1.00 |
| | cycles | | about 935 million (+6.6 %) | 935 | 935 | 935 |
| **(c) Hot tables fixed in main RAM on every machine, the bulk adaptive** | | The hot tables of the compiler are the large ones: by blocks, `SYMS` 584,000 (10.5 KB), `NAMES` 400,000 (9.2 KB), `FUNCBUF` 72,000 (4.9 KB); the small ones are cold (`WANTS` 19,000, `OUTTAB` 6,400, `STRING` 6,700, `TOKENS` about 3,000). Fixing the four small ones (9.8 KB) in main RAM would let 2.0 KB of their functions leave it: 7.8 KB lost. **Does not pay as a rule.** As a policy of (b) it is free: the start-up puts in main RAM whatever fits, hottest first, and its blocks become nothing (on M with (b), `FUNCBUF` and `WANTS`: about 6 million cycles, 0.7 %; with (a), `SYMS`: about 39 million of its 1,211) | | | | |

**The linker.**

| Design | | B (no SWR) | B1 | B2 | B+ (DFS; ADFS+DFS) | M (shadow) |
|---|---|---|---|---|---|---|
| **(b) Today's structure, placed at run time** | main RAM: code / for tables | 9,829 / 3,215 | 9,829 / 3,215 | 9,829 / 3,215 | 9,829 / 3,215; 1,679 | 9,829 / 7,055 |
| | sideways RAM for tables | 0 | 16,352 | 32,704 | 65,408 | 65,408 |
| | capacities (nodes, symbols in objects, slots, calls) | 0.07 (nothing useful; the 32K build has 300 nodes) | 0.43: 391, 1,739, 1,739, 1,565 (outtest, regtest) | 0.74: 668, 2,973, 2,973, 2,675 in proportion; the compiler's own link needs 799 nodes but only 2,014 symbols and 2,438 slots, and with the start-up's balance set for it, about 33.4 KB of the 35.9 (worked out) | 1.00, 25 KB to spare | 1.00 |
| | cycles, the compiler's link | (a link, had it the room: blocks patched, about −19 %) | | | **3,463 million (measured)** | 3,463; about 74 million fewer with `LKNODES` (3.6 KB, 1.1 million blocks) in main RAM, which fits a Master's or a shadow B+'s |
| **(a) / (b′)** | | The linker is (a) already: its loops in blocks are `lk_tab`'s chains (once a link) and two small ones, and its accessors are what is hot (`own_of` 1.67 million calls, `edge_sym` 1.32 million, `scc_of` 1.28 million, `wk` and `set_wk` 1.54 million). Nothing to gain. | | | | |
| **For B, its columns placed at run time too** | | the functions', variables' and classes' columns (10.5 KB) behind accessors or a base: about 13.7 KB for 53.7 KB of tables, 0.26: about 229 functions, against the 32K build's 296 | | | | |

**ROM, against the 128 KB.** The image has 5,815 bytes free on the tree measured (with the error texts in a file; about 2,000 once the texts are in the module, the other branch). Every design needs the lists for the copier, about 740 entries (436 for the compiler, 303 for the linker), 2 bytes each packed, about 1.5 KB, and the start-up's placement and probing, about 1 KB (estimated): **about 2.5 KB for (b)**, which fits the 5,815 and needs the lists packed tighter (about 1.2 bytes an entry) to fit the 2,000. (a) moves about 6 KB of code from the resident part's copy into the banks, which E1 shows costs nothing in bytes (−230 net there), but the compiler's banks then need the 32K form's packing (the other branch: 80.8 of 81.4 KB as judged, with `fold` resident; about 2 KB less with the accessors resident). (b′) is (b) plus a few hundred bytes.

**Two forms, or the ROM run in place.** Code linked to run in main RAM cannot run from the ROM, and the ROM cannot be patched, so code that is resident on one machine and in a bank on another is two copies: about 8 KB more for the compiler's kept code (the image does not have it), or about 2.1 KB for (b′)'s hot loops alone, kept in a bank as well and reached through vectors in main RAM that the start-up points at one or the other (3 cycles a call; a far call from another bank on B). That gives B (a)'s capacities and the others (b′)'s speed, for new machinery in the linker (one function in two forms, with and without its blocks, and the vectors). Not worth it for 0.06 of capacity on B.

**What is better than all of them for B: RAM on the module's board** (`bbc.md`, "The linker on a 32K BBC", suggestion 1): a 32 KB RAM behind the latch makes the bare Model B a machine with two banks, which (b) serves at full size. With it, one ROM is every BBC.

### Placed and sized at run time

**How a table gets its place.** Two ways, both measured from the census's sites:

| | Relocation as the resident part is copied (chosen) | A base in a variable |
|---|---|---|
| The code | unchanged: the same object files | the compiler, with an option like `-f` (`-dREGION`), forms each address from a base variable: `ADC base+1` for `ADC #>table`, `LDA slot` for `LDA #bank` |
| Cycles an access | **0** | +2 a high byte (kind 8, 1.45 million in the self-compile, 10.1 million in the link), +2 a slot (1.09 and 9.65 million), +2 a pointer made (kinds 2 and 3, 0.82 million); a table of 256 rows or fewer read `LDA table,X` (kinds 1 and 5, 0.42 million, 42 places in the compiler) needs `(zp),Y`, a zero-page pointer each, which must not be what decides whether it links: about 7 million cycles for the compiler (0.8 %), 40 million for the linker (1.2 %) |
| Bytes | the lists in the ROM (about 1.5 KB) | about 300 bytes of resident code a tool |
| What it needs | the linker to list, for the resident part, every fix-up naming a variable of a `dynamic` region and every block call; the copier (or the tool's start) to apply them | the compiler option and the variables |

Which tables are already reached cheaply: all the large ones. A table of more than 256 rows is read through a pointer that the code forms as `LDA #<t`, `STA p`, `LDA i+1`, `CLC`, `ADC #>t`, `STA p+1`, `LDY i`, `LDA (p),Y` (kinds 7 and 8, the commonest sites above): its base is two immediate bytes, whichever way it is set. The symbol table's columns are found through `byte_base` and `word_base`, which `kernel.init` fills, so their row count can be a variable at no cost; the name heap, the function buffer, the string, the saved tokens and OUT's table are one array each, indexed by 16-bit offsets. The small ones (`fbuf`'s labels, OUT's fix-up columns, DECL's import rows: 2,368 bytes) are read `LDA t,X`, so they keep their row counts and move whole.

**Which should be dynamic**: every region of both tools (the compiler's 22 variables, the linker's 9), each placed by the start-up. Fixed: everything banked code names (above). On B that is the limit (b) runs into; making `kernel.text` dynamic (main RAM only, since the MOS reads names from it) would give the compiler about 1.3 KB there, and the linker's columns would need what the last row of its table says.

**What the source looks like.** The declarations stay (`var names: [NAME_HEAP_SIZE]byte in NAMES`, at the largest size the image allows); the regions are given in the environment as `region NAMES dynamic` (a new form, for the BBC's environments only). The capacities reach the checks through variables: each limit a check reads (`NAME_HEAP_SIZE`, `MAX_SYMS`, `BUFFER_SIZE`, `MAX_STRING`, `MAX_TABLE`, `MAX_MEMBERS`, `MAX_WANTS` in the compiler, 57 lines of the twins; `MAX_NODES` and what is derived from it, `MAX_EDGES`, `MAX_SLOTS`, `MAX_FIXES` in the linker, 81 lines, where the work area's column offsets `W_*` are products of `MAX_NODES` and become variables `lk_tab.init` sets) is a variable set from a table the start-up fills before `$init`, under `#if DYNAMIC` in the twin, with the host's variables set to the constants so that the two stay alike; a check then costs `CMP abs` for `CMP #`, a byte and two cycles. Nothing about it changes an object file, so the same source gives the same object whichever machine compiled it (and the capacities do not change it either: the experiment above).

**What the linker and the environment need**: `region NAME dynamic` (placed at link time in the window as now, at its largest, so that every check of the link still holds); a list in the resident part of every fix-up there that names a variable of a dynamic region (offset, kind, which variable, addend) and every block call; and a table of the dynamic variables (size, row count, the capacity variable, whether main RAM only). The map would show them (`R` lines). Wendy 2's and the host's environments have no `dynamic` region, so their images and maps are byte for byte what they are, and so is every object file everywhere; only the BBC's images grow by the lists.

**At the start**, for `*LATHE` and `*LLINK`, before the copy: read PAGE and HIMEM (OSBYTE 131 and 132), find the free sideways RAM (below), place the tables (the largest first, each whole: in a bank, or below the fixed base, or above the fixed part), set each one's capacity, then copy the resident part patching its sites: a table's address, a region's slot (`LDA #bank`), and for a region in main RAM its block calls (NOPs, or RTS for the tail `JMP`). About 740 sites at 40 cycles and the probing: about 50,000 cycles, against the 850,000 a start takes now (estimated).

**PAGE, and HIMEM.** The fixed part is linked from `$1F00`, the highest PAGE the tools are built for; what is below it on a machine whose PAGE is lower, and what is above the fixed part to HIMEM, are areas the start-up places tables in:

| Machine | PAGE | Below `$1F00` | Above the fixed part to HIMEM (compiler (b) / linker (b)) | With a shadow mode |
|---|---|---|---|---|
| Model B or B+, DFS | `$1900` | 1,536 | 2,338 / 1,679 | +1,024 (a B+, or a Model B with a shadow board) |
| Model B or B+, ADFS and the DFS | `$1F00` | 0 | 2,338 / 1,679 | +1,024 |
| ADFS alone | `$1D00` | 512 | 2,338 / 1,679 | +1,024 |
| Master 128 | `$0E00` | **4,352** | 2,338 / 1,679 | +1,024 |

So **one image serves `$1900` and `$1F00`**, and the separate ADFS build goes: the DFS machine loses nothing but the fragmentation of having its 3,874 bytes in two pieces (1,536 and 2,338), which tables of 2,048 and less fill (`TOKENS`, `STRING`, OUT's table, the import rows: worked out, nothing left unplaced on any machine above); a Master gains 2,816 bytes that no build uses today; the shadow screen's kilobyte comes for nothing, with no build of its own. The start-up refuses PAGE above `$1F00` with an error, as the 32K image refuses a mode without enough HIMEM.

### Finding the RAM at start-up

*From memory, unverified, but where the emulator shows it.* The MOS's ROM type table (OSBYTE 170 gives its address, `$02A1` on MOS 1.20) has a byte for each slot, 0 where no ROM was found at the last BREAK; OSBYTE 0 with X=1 gives the MOS (1 a Model B, 2 a B+, 3 a Master 128). The B+128's sideways RAM is slots 0, 1, 12 and 13, written through the window when its slot is selected; its 12 KB private RAM (`$8000-$AFFF`, ROMSEL bit 7) is for the MOS's and other ROMs' use, and not to be taken. The Master 128's is banks 4 to 7; MOS 3.20 marks a bank as data or as a ROM image with `*SRDATA` and `*SRROM`, and moves bytes with OSWORD &42 and &43 (`*SRREAD`, `*SRWRITE`, `*SRLOAD`); its hidden RAM (`$8000-$8FFF`, `$C000-$DFFF`) is the MOS's. The Model B's boards differ in how a write reaches their RAM: most take the write when their slot is selected (a RAM chip in a socket with a write line, or a board decoding ROMSEL); some (Solidisk's, some of Watford's) direct every write in the window to a bank chosen by a latch of their own, whatever is selected; some have write-protect switches. A probe through ROMSEL alone is safe on the first kind, finds nothing on the third, and on the second may write into another bank.

**The policy proposed:**

1. Never touch a slot the ROM type table marks, or one that holds a ROM header now (an image `*SRLOAD`ed since the last BREAK), or the module's own slot.
2. On a Master, take banks 4 to 7 that pass 1, and if any are marked `*SRDATA`, only those. On a B+ (OSBYTE 0), slots 0, 1, 12 and 13 that pass 1.
3. On a Model B, probe the slots that pass 1, from main RAM with interrupts off (the copier's room at `$0400`), `$F4` kept with ROMSEL: at one address, save the byte, write `$55` and read it, write `$AA` and read it, put the byte back. Two patterns, neither in `$80-$BF`, because an empty socket reads the open bus, which is often the high byte of the address just fetched. Before each write, read the same address in every slot the table marks; after it, read them again: if one changed, the board writes elsewhere, so put that byte back (writing it there again, where such a board sends it) and stop, with a message that the slots must be named.
4. A user may name the slots (and so forbid probing), for instance with a word in a file the tools read at the start, or a `*` command of the module that keeps it until BREAK in a byte of the MOS's user workspace; on a Master the `*SRDATA` marks are that already.
5. Say what was taken: `*LATHE` with no arguments (the usage) can print the slots and the capacities.

What it cannot protect: data in a bank that holds no header and no mark (a user's own tables in sideways RAM). Today's tools take their four slots without asking (`bbc.md`, "Open, for the owner"); this is strictly safer.

**What the emulator shows and does not.** It has `--bbc-sideways-ram LIST` (any slots of RAM; the two-bank run above used it), `--bbc-rom SLOT=FILE` (a ROM image, also in a slot of RAM), the ROM type table at `$02A1`, OSBYTE 170, `--bbc-page` (OSBYTE 131) and `--bbc-shadow` (OSBYTE 132 answers `$8000`), and the open bus as the last byte the data bus carried; so the policy's rules 1 to 3 for boards of the first kind, PAGE and HIMEM can all be tested there. It has no board of the second or third kind, no Master and its MOS, nothing of the B+'s private RAM's other users, and its MOS's table is what the tests and LOADMOD put in it.

### The plan, and what I recommend

| Stage | What | Machines it serves, and how | Cost |
|---|---|---|---|
| **1** | Run-time placement: `region NAME dynamic` in the linker and its twin, the relocation and block lists, the start-up's probing and placement, the copier's patching, capacities as variables (host and twin), the fixed part from `$1F00` | **one image for B1, B2, the B+128 (DFS or ADFS), the Master 128 (shadow or not)**: B2 and up at full capacities for the compiler (measured for B2), the linker full from three banks and about 0.74 to 0.83 of full with two; B1 at 0.57 and 0.43; the Master and the shadow screen's RAM used | ROM about 2.5 KB; main RAM 0 (the start-up is in a bank; the capacity variables about 40 bytes); cycles 0 after the start (about +50,000 at it); source: the capacities in about 140 lines of the twins and as many of the host, the linker's new output, a start-up module of a few hundred lines. **The ADFS build goes.** The 32K builds stay |
| **2** | The compiler's cold loops through accessors, coldest first, each step measured (E1b is the first): of the 6,052 bytes of looping code and what runs inside it, all but the 3.1 KB that save the most (the table under "Experiments") | every machine gains about 2.9 KB of main RAM (B1 from 0.57 to about 0.65 of full), for about +2.4 % on the machines that bank, and nothing where blocks are patched away | source: blocks out of functions in `fbuf`, `decl`, `out`, `lex`, `kernel`, host and twin alike (the host is that way already in kernel's case); ROM about the same |
| 3 (not recommended) | the bare Model B in the same image: the compiler at (a) or (b′), `kernel.text` and the linker's columns made dynamic | B at 0.22 to 0.28 of the compiler's tables and 0.26 of the linker's, below the 32K images' (about 0.35 and 0.33) | +6 to +38 % on every other machine, a large change to nine of the linker's modules |
| instead of 3 | RAM on the module's board | the bare Model B as a machine with two banks, under stage 1 | hardware |

**Recommended: stage 1, then stage 2 as far as it pays.** Stage 1 is the owner's idea where it is right: the tables find their own room, blocks cost nothing where nothing is banked, the banks are still used where they are, PAGE and HIMEM are read, and nothing in the language or the object format changes; its cost is ROM, which the image has. The owner's hybrid (loops in main RAM, single accesses through accessors that switch or not) is what the tools already are, so it needs no restructuring: stage 1 gives it the run-time half. Where the idea does not pay is the bare 32K Model B: the code that must be in main RAM wherever there is a bank is the code that must not be there when there is none, and only a second copy of it in the ROM, or slower code everywhere, reconciles the two; the 32K images are better for that machine than anything one image can give it.

**Measured, extrapolated, from memory.** Measured: the census, its calls and cycles, the blocks and far calls, E1, E1b, the two-bank self-compile, E2, the capacities that do not change an object, the sites. Extrapolated: the cost of (a) and (b′) beyond E1 (from the host's access counts at E1's 129 cycles an access), the savings of patched blocks in the compiler and in the compiler's link (at E2's 67 cycles a block), the capacities of the designs (from the maps' sizes, packed in proportion), the ROM bytes of the lists and the start-up code, the start-up's cycles. From memory: PAGE and HIMEM on each machine, the MOS calls, the B+128's slots and private RAM, the Master's banks and commands, the Model B boards.

## The 32K pair on programs of real size, measured (2026-11-18)

The owner's question, how large a program of several modules the 32K Model B's compiler and linker take ([`bbc.md`](bbc.md), "A program of real size on the 32K Model B", has the account). Programs made by `lathe/tests/gen_program.py` to the measured shape of the tools' code (about 130 bytes, 3.3 slots and 2.7 calls a function, modules of 20 to 30 functions with import lists), compiled and linked on the emulated Model B from the 32K image, every file the host's and the output right: 8 KB (3 modules), 16 KB for mode 4 (6 modules, 312 bytes left below `$5800`), 20 KB (7 modules), and 24.6 KB for mode 7 (8 modules of fewer, larger functions of about 190 bytes; 711 bytes left below `$7C00`), in 5.3 minutes at 2 MHz for the 25 KB one's 13 compiles and link before the disc's time. The first limit is the linker's: its calls table (576) is full at about 20 KB of the usual shape, then its slots (800) and functions (296); the compiler's tables stay at about half (its name heap 1,350 to 1,600 of 3,072 in modules of 300 lines). Then the disc: 31 files a side (at most 10 modules of the program's own with their objects and interfaces on one side), and 134 and 151 KB on the two drives for the 25 KB program, two 80-track sides. Ranked: give the linker's 1,113 free bytes of main RAM to calls, slots, functions and nodes (about 860 bytes: the usual shape to 25 KB); `rt_math` first in `LINKARG` (else 16 pending weights fill: link error 41); objects on two drives for more modules; the compiler's names out of its heap only after these.

To get the 32K image into the 128 KB EPROM the texts of the errors are now in parts placed wherever there is room ([`bbc.md`](bbc.md), "The texts in the module", "In parts, in any bank"): 1,879 bytes free there; the B+128's image 1,957 (1,960).

## Image A, stage 1, measured (2026-11-20)

The study's stage 1 built ([`bbc.md`](bbc.md), "One image for every machine with sideways RAM"):
from one 128 KB image, linked from `$1F00`, on the emulated B+128 with its four banks, every file
the host tools', `--bbc-strict` on filled memory. The self-compile 876.3 million cycles at PAGE
`$1900` and 876.4 million at `$1F00` (874.0 million from today's B+128 image); the linker's link
of the compiler 3,024.5 million at both (3,023); the rebuild loop at `$1900` 4,045.7 million. The
placer puts the compiler's `WANTS` (1,600 bytes, 15 calls of map and unmap made nothing) in main
RAM at every PAGE of the B+ and the Master's `STRING` too and the linker's `LKNODES` (worked out
from the lists by the placer's model, `lathe/tests/places.py`; the emulator has no Master). The
start-up: `*LATHE` 1,045,256 cycles, `*LLINK` 754,204 (852,232 and 651,777 today): the lists, 1,183
and 799 bytes, copied and read. The image has 414 bytes free with `BBCFS 0`; with `BBCFS 3` it is
about 1,190 over. The study estimated 2.5 KB of ROM for lists and code: they took 4.0 KB (the
lists 2.0 KB, close to its 1.5 KB; the placer 1.0 KB a tool, not 0.5 KB once).

Later the same day (`bbc.md`, "The ROM plan"): a region moved as one block by whole pages, and no
list of the calls of map and unmap, the lists are 623 bytes and the placer 591; Image A then fits
with `BBCFS 3` (1,072 bytes free, against 2,903 for the same image without `ADAPT`), but not with
the linker's `lk_dyn` in it (`LKDYN 1`, about 2,612 bytes as judged: about 1,160 over).

## Image A with the name heap set at start-up, measured (2026-11-20)

([`bbc.md`](bbc.md), "Capacities set at start-up: the name heap".) On the emulated B+128 with
its four banks, `--bbc-strict` on filled memory, every file the host tools' (`test_bbc_adapt.py`,
`BBCFS 0`): the self-compile 877.0 million cycles at PAGE `$1900` and at `$1F00` (876.3 and 876.4
before; 874.0 from the B+128 image of today); the linker's link of the compiler 3,024.2 million
at both (3,024.5); the rebuild loop at `$1900` 4,048.0 million (4,045.7). The start-up: `*LATHE`
with no arguments 938,993 cycles, `*LLINK` 691,779 at `$1900` (1,045,256 and 754,204 measured at
stage 1, before the lists became a third of their size; 852,232 and 651,777 for today's image).
The placer now moves every region (packed from the bottom of the free slots), which costs little.
A module of 12,923 bytes of names (`test_bbc_rooms.big_names_source`) compiles in 24.2 million
cycles on every machine it was run on.

The account, `BBCFS 3`, `ADFS 1` (as `bbcrom.image` lays the image out, and the banks as the
linker judges them): **1,174 bytes free** (1,386 before). The module's code and tables 1,630
bytes (1,464: the placer packs, takes the largest area and writes a capacity); the compiler's bank
4 12,186 judged (12,173: `kernel`'s two tests read a variable), its other banks unchanged
(13,759, 15,271, 14,007, 14,269); the lists 18 and 10 bytes longer (a capacity word for each
region, and for `NAMES` where its last variable starts). The linker's banks are unchanged: 16,245,
15,193 and 15,884 (its new code is under `LKDYN`, off in the ROM forms; with `LKDYN 1` it adds to
the 781 bytes already over, by an amount not measured).

The least name heap each module of the compiler compiles with (the host compiler, `lathec_heap.py`):
`sys` 974, `src` 1,259, `fold` 1,322, `typetab` 1,635, `lathec` 1,944, `cond` 2,175, `out` 2,684,
`fbuf` 2,786, `err` 3,723, `parts` 3,794, `lex` 3,804, `asmblock` 3,855, `kernel` 3,963, `inlines`
3,964, `reg` 5,041, `expr` 7,002, `gen` 7,007, `decl` 7,177; a generated program's modules
(gen_program.py, 20 functions each) 1,035 to 1,418. At each of six sizes from the least up to
30,000 every module gives the same files.

## Image A with two banks, measured (2026-11-20)

([`bbc.md`](bbc.md), "Two banks: floors, ceilings and packing".) `--bbc-strict` on filled memory,
every file the host tools': the self-compile, 18 compiles, 877.4 million cycles on a Model B with
two banks of sideways RAM under the DFS (PAGE `$1900`) and under ADFS (`$1F00`), as on the B+128
with four (877.5 million at `$1900`, 877.4 at `$1F00`; 877.0 with the name heap alone); the
linker's link of the compiler 3,024.2 million and the rebuild loop 4,048.7 million on the B+128
(the linker still needs four banks). The start-up: `*LATHE` 940,836 cycles, `*LLINK` 690,694 at
`$1900`. The module of long names: 24.2 million cycles where it compiles, 11.7 million to error 70
with two banks (a heap of 8,192). At every heap size tried, and with 768, 1,120 and 1,312 bytes of
saved tokens, every module gives the same files (`test_bbc_rooms.SameObjects`).

The account, `BBCFS 3`, `ADFS 1`, as `bbcrom.image` lays it out: **1,005 bytes free** (1,174 with
the name heap alone, 1,386 before capacities): the module's code and tables 1,785 bytes (1,630: the
floor and the ceiling, and the choice of main RAM's largest or sideways RAM's closest area); the
compiler's bank 4 12,190 as judged (12,186: INLINE's test); its other banks and the linker's three
unchanged (13,759, 15,271, 14,007, 14,269; 16,245, 15,193, 15,884); the compiler's list 14 bytes
longer (`TOKENS`' capacity, and the floor and ceiling words of both).

## One bank, measured (2026-11-20)

([`bbc.md`](bbc.md), "One bank: planes, wants, and the tables set at start-up".) `--bbc-strict` on
filled memory, every file what the host compiler gives with the machine's capacities
(`test_bbc_rooms.py`, `lathec_heap.py` giving the host those capacities):

| | B+128, four banks | two banks | one bank, DFS | one bank, ADFS |
|---|---|---|---|---|
| the self-compile, 18 compiles | 881.4 million (877.5 before) | 905.3 (877.4 before) | | |
| the compiler's own modules that compile | all 18 | all 18 | 12: `kernel`, `src`, `lex`, `typetab`, `fold`, `fbuf`, `out`, `cond`, `asmblock`, `parts`, `lathec`, `sys` (896 million with a generated program's five) | 11 (`kernel`'s names do not fit 4,096 with ADFS's tokens; 923 million) |
| refused, and by what | | | `err` (a string of 2,038), `reg`, `gen`, `inlines`, `expr`, `decl` (names, symbols, the buffer) | the same and `kernel` |
| generated modules (gen_program.py) | | | up to 82 functions a module (84: members full, error 72) | the same |
| the module of long names | 24.3 million | 14.0 million to error 70 | 12.3 million to error 71 | 13.8 million to error 71 |

The linker's link of the compiler 3,024.3 million and the rebuild loop 4,053.8 million on the
B+128. The start-up: `*LATHE` 1,009,717 cycles, `*LLINK` 721,660 at `$1900` (940,836 and 690,694
with two banks' placer): two walks at least, each with the slots probed afresh.

The account, `BBCFS 3`, `ADFS 1`, as `bbcrom.image` lays it out: **696 bytes free** (1,005 before
the planes): the module's code and tables 2,001 bytes (1,785: the walks, the giving up of steps,
the planes); the compiler's banks as judged 13,763, 15,271, 14,007, 12,188, 14,269 (bank 1 and 4:
the capacities' tests, and the symbols' columns made at `init()`); the linker's three unchanged
(16,245, 15,193, 15,884); the compiler's list longer by the planes of `SYMS`' places and the new
capacities' entries.

## The linker on two banks, measured (2026-11-20)

([`bbc.md`](bbc.md), "The linker's tables on two banks".) Image A, `--bbc-strict` on filled memory,
every file what the host linker gives at the machine's capacities (`lk_rooms.py`):

| | four banks | three banks | two banks, DFS | two banks, ADFS |
|---|---|---|---|---|
| symbols of the object files, slots, calls | 4,096, 4,096, 3,584 | 4,096, 3,840, 3,584 | 1,536, 2,304, 1,280 | the same |
| `*LLINK`'s start-up | 743,805 (722,309 before) | 791,266 (722,071) | 1,164,924 (refused) | 1,160,371 at `$1F00` |
| the compiler's link | | 3,025.3 million (3,024.3) | link error 13 at 134.6 million, as the host's | the same |
| the largest generated program that runs in mode 7 | | | 250 functions, 24,296 bytes; 668.7 million for 13 compiles, the link and the run | 226 functions, 23,392 bytes; 644.6 million |

The start-up costs 21,000 cycles more with four banks (a plane byte after each of the 53 high
bytes of the three regions, and their capacities written) and three banks one walk more (the
slots give up their last step). What was weighed: planes per variable (the design handed over,
an estimated 100 to 150 bytes of the module) against planes beside variables of a fixed size (no
byte of the module): the only variables of other row counts, `fn_edge` and the large slots, need
not shrink, since `MAX_FUNCS` sizes 4,480 bytes of main RAM as well and its rows cannot be whole
pages at 896. The account with `BBCFS 3`: 410 bytes free (636): the linker's resident part 205 more
(`lk_tab` 125, the list 80), its bank 2 24 more as judged.

## The linker's ROM space, measured (2026-11-20)

([`bbc.md`](bbc.md), "One image for every machine with sideways RAM".) Image A (`ADAPT 1`, `ADFS 1`,
`BBCFS 3`), every figure the linker's own judgement of its banks (`lk_judged.py`), which counts each
module before shrinking with every variable that may go in the bank.

**Where it stood.** On `c38e2ba` the ROM linker with `LKDYN 1` (the support for `dynamic` regions,
module `lk_dyn`) needed 51,879 judged bytes in its three banks, which hold 48,816: **3,063 over**. It
had been 781 over before the capacities work; since then `lk_dyn` had grown to 3,029 judged, and
`LKDYN` added 946 to `lk_envf` and 331 to `lk_name`. No arrangement of the modules in three banks
fits. On `1647a34`, after the
planes, it was 52,506 judged (**3,690 over**).

**Built** (each in host and twin, byte for byte; `LKDYN 0` in every ROM form as before):

| Change | The linker's three banks (`LKDYN 0`) | `LKDYN 1` | The compiler's five banks |
|---|---|---|---|
| A constant, an address or a plain variable stored into a slot through Y while an argument waits in A, or A and X (`reg.put`, `put_const`; [`codegen.md`](codegen.md), "Calls") | 47,346 to 46,773: **573** | (with the next) | 69,498 to 69,358: **140** (`reg` 89 more) |
| A big array's element read once into a named local, `check_windows`' range named once, `lk_dyn`'s place index stepping by 3 (the twins of `lk_place`, `lk_envf`, `lk_alloc`, `lk_dyn`; the host the same) | 46,773 to 46,644: **129** | 51,909 to 51,527: **382** | none |
| A word compared with a constant whose low byte is 0 compares the high bytes alone (`cond.subtract`; [`codegen.md`](codegen.md), "Comparisons and conditions") | 46,644 to 46,537: **107** | 51,527 to 51,411: **116** | 69,358 to 69,345: **13** (`cond` 64 more) |
| All three | **809** | 52,506 to 51,411: **1,095** | **153** |

The first went further than the study's form of it, which stored only plain variables through Y
and measured 384 and 172: constants and addresses go through Y too. Building it found a fault of
long standing: a value waiting in A where a loop's label is placed (an `inline` function whose body
starts with a loop, in an expression) was stored in its temporary inside the loop, so every pass
after the first stored what the loop left in A. `reg.loop_label` now stores it first
(`cases/e2e/inline_loop_owner.lth`); the stores through Y made it show in `inline_locals`.

With `LKDYN 1` the linker is now 51,411 judged against 48,816: **2,595 over** (a measurement only:
nothing with `LKDYN 1` is built into a ROM form).

**The account after** (with `BBCFS 3`): Image A **1,218 bytes free** (410 before): the compiler's
banks 13,710, 15,202, 13,934, 12,104, 14,395 (13,763, 15,271, 14,007, 12,188, 14,269), the linker's
16,054, 15,060, 15,423 (16,245, 15,217, 15,884), the resident parts 12,449 and 10,161 bytes (12,475
and 10,175), their variables in main RAM unchanged. The image without `ADAPT`: 5,439 free with
`BBCFS 0` (4,563), 3,713 with `BBCFS 3` (2,837). The 32K image: 5,453 free (4,587), the compiler's
main RAM 198 free (178). Cycles: the self-compile from the eight-bank image 875.3 million (877.2),
Image A's 879.7 million at PAGE `$1900` (881.8); the linker's link of the compiler 3,006.0 million
(3,024.8), Image A's 3,006.4 (3,025.3).

**Candidates not built** (estimated): a long branch made a short one to a nearby `JMP` to the same
place, about 140 bytes; a spilled word's low byte stored at once, before the high byte is worked
out, about 150; `lk_envf.room_entry` through a table, about 150; more of `lk_dyn` (its three
readings of the region definitions), 100 to 200.

**Rejected**: a `JSR` and the `RTS` after it joined, 27 bytes measured; `BRK n` for the error
calls, 87 bytes counted; repacking the banks, no gain.

## The linker on one bank, measured (2026-11-20)

([`bbc.md`](bbc.md), "The linker on one bank: measured, not built".) The work area's offsets made
variables under `LKROOMS`, set as the tool starts from the bytes the placer gives `LKWORK` and
`LKNODES` (a prototype, kept outside the repository; `MAX_FIXES` a constant 366 in Image A, the S
lines' names held below `W_ADDR`): **about 1,100 bytes** of the linker's code more, as compiled
(`lk_tab` 462, of which 357 its `size_work`; `lk_alloc` 304, `lk_graph` 236, `lk_name` 50, the rest
66); 619 of them make the offsets at start-up (about 19 bytes an offset), the rest are their uses
(2 bytes a use as a number, about 11 where a column was reached directly). With the fix-ups'
columns made to vary too: 1,521. The banks as judged (`BBCFS 0`) 15,182, 15,139, 15,886 (15,145,
15,060, 15,423); the resident part 159 bytes over the code range; with `BBCFS 3` bank 1 5 bytes
over. Not built: the budget was about 600 bytes, with a stop at 800.

Time, estimated from counts of the host linker linking the compiler: `wk` 4.73 million calls (0.98
million in the node columns), `set_wk` 0.73 million; the split compared with a variable about 22
million cycles, the node columns' index about 12 million, the offsets from variables about 20
million, the direct readers more: 2 to 3 % of the 3,006 million, against a limit of 1 %.

The placer's model (`places.plan`) with a capacity on `LKWORK` and `LKNODES`: as the placer is,
two banks would get a work area of 644 rows and symbols 2,304, slots 2,304, calls 2,048 (now 900,
1,536, 2,304, 1,280); with a third tier, regions that give up steps only when no other can, four,
three and two banks keep theirs and one bank gets 420 nodes (byte capacities; 388 with planes of
256 rows), symbols 768, slots 1,024, calls 768.
