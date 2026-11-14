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
