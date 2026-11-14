# Lathe: spikes

Status (2026-11-14): the small spikes S1 to S7 and the larger spikes L4 and L5 are done; results are at the end. L1 and L2 were folded into building the compiler and the linker. L3 (shrinking in the linker) is answered by the linker itself, which shrinks in one streaming pass and matches the assembler byte for byte.

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
- **Projection for the whole compiler.** The six modules still to do have 4,563 lines of code. At 6.9 to 8.4 bytes per line they are 31 to 38 KB, so the compiler would be **55 to 61 KB of code, with 54 KB of tables**. The target was 32 KB. It cannot run in 64 KB as it stands.
- **The host compiler cannot compile `reg.lth` within its own limits**, because an import brings in every exported name.
- **Where the code is bigger than it should be**, by estimated saving in the six middle modules: arrays of more than 256 entries (142 address computations of about 13 bytes; rows reached through a pointer would save 550 bytes here and several KB overall); the function buffer walked by an index, not a pointer (740); the address of `buffer[e + k]` recomputed each time (260); a word built from two bytes through a temporary (25 bytes a time against 10); index registers reloaded when two indexes alternate (250); chains of tests that could be tables; loops tested at the top (29 loops).

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
