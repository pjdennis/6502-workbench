# Prog8 self-hosting plan -- status and roadmap

This file is the **strategic plan** for the Prog8 bootstrap. It's
the document you read when you want to know *where this project is
going* and *what's left*. For the tactical "what changed last
session and what should I do this push" view, see
[`RESUME_NOTES.md`](./RESUME_NOTES.md). For the per-feature
language-surface checklist, see [`README.md`](./README.md).

**Side investigations (analysis only, not on the critical path):**

* [`ASM_MIGRATION_PLAN.md`](./ASM_MIGRATION_PLAN.md) -- gap analysis +
  plan for swapping vasm out for the in-tree on-host assembler
  (`toolchain/asm2/17/`), so pass 1 + pass 2 + assembler all run on target.
* [`CODEGEN_SIZE_COMPARISON.md`](./CODEGEN_SIZE_COMPARISON.md) -- measured
  p8c vs. upstream prog8 binary sizes (p8c emits ~1.5-1.65x the code).
* [`CODEGEN_LOW_HANGING_FRUIT.md`](./CODEGEN_LOW_HANGING_FRUIT.md) -- ranked
  peephole/branch-relaxation wins (~2.4 KB cheap) for the p8c backend.
* [`WENDY2_BANKING_TARGET_PLAN.md`](./WENDY2_BANKING_TARGET_PLAN.md) -- custom
  external Prog8 target exposing wendy2 upper-bank memory banking (M0-M4+M6
  built: code/data banking demos green on the emulator).
* [`WENDY2_DISK_BOOT_DESIGN.md`](./WENDY2_DISK_BOOT_DESIGN.md) -- design for an
  alternate monitor boot ROM + simulated SPI storage that loads/runs programs
  over the file-I/O OS calls (with autoexec); folds in the M5 OS-call ABI.
* [`WENDY2_SELFHOST_BANKING_PLAN.md`](./WENDY2_SELFHOST_BANKING_PLAN.md) -- plan
  to self-host `p1.p8` on wendy2c using a mapped RAM bank as high RAM (the two
  passes' code fits the 32K fixed region; only data overflows into the bank).

When you finish a feature, update this file. When you finish a
session, update `RESUME_NOTES.md`.

---

## Goal -- *** REACHED (2026-06) ***

Bring up a Prog8 compiler that runs natively on the 6502, mirroring
the asm00..asm17 bootstrap pattern. The end-state is:

* A Prog8 compiler whose source is itself written in Prog8.
* It compiles its own source on a 6502 (in our case, in the
  emulator's nmos-default machine, with file I/O via the
  `$F006..$F03C` stubs).
* The output is byte-identical to its host-compiled binary --
  the strict self-hosting test, copied from the asm chain.

**STATUS: achieved.** The two-pass self-host pipeline
(`p1/p1_pass1_sh.p8` parse+symbols+AST-dump, then `p1/p1_pass2_sh.p8`
AST-load+codegen) running on the emulator compiles `p1/p1.p8` to
output **byte-identical** to `p8c -o p1/p1.p8` (545 KB), the only
difference being the `; source:` comment line that `test_p1.py`
normalizes (the on-target compiler has no host realpath to echo --
the same normalization the snapshot tests use). The monolith p1.p8
didn't fit one 64 KB binary (front-end ~22 KB + codegen ~33 KB +
program-wide arenas ~15 KB), so the front-end and back-end were split
across two passes that exchange the AST through a file -- the same
<=64 KB pipeline pattern as the asm00..asm17 chain. See RESUME_NOTES.md
for the closing fixes (str_pool transient overflow, binop word-typing,
byte-context binop array index, single-arg call high-byte store).

We pursue this in two parallel tracks that meet in the middle:

1. **Host p8c** (Python) grows wide language coverage. Goal: rich
   enough to express a real on-target compiler in.
2. **tinyp8** (a tiny compiler that itself runs on the 6502)
   grows. First as a hand-written asm proof of concept
   (`tinyp8.s`); then ported to Prog8 (`tinyp8.p8`) and proven
   byte-equivalent; then progressively extended to accept more
   of Prog8 itself.

The eventual self-host is when tinyp8.p8 grows to "Prog8 compiler
size" and can compile itself.

---

## Phase map

The original Phase 0..6 plan from session #1 is below, marked
with `[done]`, `[partial]`, or `[todo]`. Subsequent phases reflect
how the work actually evolved -- the on-target compiler grew via
its own version series (v2..v8) rather than being a single Phase
5 push.

### Phase 0 -- Scaffolding `[done]`

* Directory layout under `toolchain/prog8/`.
* Host compiler driver (`python3 -m p8c`).
* Test harness: unit / snapshot / golden tiers.

### Phase 1 -- Walking skeleton `[done]`

* Lex / parse / sema / codegen for `main { txt.print("...") }`.
* `%address`, `%import`, `%output`.
* End-to-end golden: `hello.p8` -> LCD shows "hi from prog8".

### Phase 2 -- Useful subset (host) `[done]`

* `ubyte` / `uword` types, arithmetic (`+ - & | ^ << >>`), comparison
  (`== != < <= > >=`), augmented assigns.
* `if / else / while / for in lo to hi / repeat / break / continue`.
* Sub with params + return value; `asmsub` declarations; inline
  `%asm{{ ... }}` blocks.
* `peek` / `poke` and the `%target nmos` switch.
* Module-level var initializers; for-loop range; `char` literals.

### Phase 3 -- Self-host milestone (the bootstrap pattern works) `[done]`

* `tinyp8.s` -- a 6502-native tinyp8 compiler, hand-written.
* `tinyp8.p8` -- the same compiler ported to Prog8.
* **Byte equivalence** between the two for the v0/v1 corpus
  (5 inputs in `tinyp8/tests/goldens/`).
* `runtime_io.p8` shim equivalent baked in: source from
  `--serial-input`, compiled output via `--output`.

### Phase 4 -- Language built out for compiler-shaped code (host) `[done]`

Added to host p8c after the Phase-3 milestone:

* `byte` (signed) with signed-aware comparisons.
* `enum` declarations.
* `struct` declarations + struct arrays with
  `arr[i].field` indexing.
* `defer` statement.
* `when` statement.
* `inline sub`.
* `const` declarations.
* Builtins: `lsb` / `msb` / `mkword` / `len` / `sizeof`.
* Long-branch handling (inverted-branch + JMP pattern).
* `*` multiplication via a `__p8c_mul_u8` runtime helper.
* `@(uword_expr)` runtime-address memory access; `&var` operator.

Result: the host language is now comfortably wide enough to express
a real compiler. Tokenizer demo (`examples/tokenizer.p8`) proves
the shape.

### Phase 5 -- tinyp8 grows beyond the reference `[in progress]`

Each tinyp8.p8 version adds one capability:

* `v2` `[done]` -- variable declarations + var refs in
  `print_ub`. 38-byte in-output hex helper.
* `v3` `[done]` -- `if X == \$YY then print_ub Z`.
* `v4` `[done]` -- `let X = Y` (variable copy).
* `v5` `[done]` -- arithmetic in let RHS.
* `v6` `[done]` -- `while X != \$YY` with fixed-shape body.
* `v7` `[done]` -- full comparison ops (`< <= > >= == !=`).
* `v8` `[done]` -- while body can include `print_ub Y` before the
  let increment.
* `v9` `[done]` -- multi-character variable names (symbol table with
  `read_ident` / `find_var` / `declare_var`; up to 8 chars, 16 vars).
* `v10` `[todo]` -- input from stdin via `$F006`.
* `v11`..`vN` `[todo]` -- progressively more of Prog8's surface
  (multi-statement if-then bodies, expressions deeper than two
  terms, then `sub`/`asmsub` for on-target user-defined
  subroutines, etc.).

Open question for Phase 5: at what version does tinyp8.p8 cross
the line from "tiny" to "real Prog8 subset"? Probably when it can
parse its own grammar without restrictions on control-flow body
shape and expression depth. (The identifier-length restriction is
gone as of v9.)

### Phase 6 -- Host p8c iterative-parser rewrite `[in progress: steps 1-4 done; only the Prog8 port remains]` (THE strategic item)

Host `p8c/parse.py` is recursive-descent in Python. Prog8 forbids
recursion (subs are non-reentrant by design), so the host parser
cannot be directly ported. To self-host the *real* p8c (not just
its tinyp8 cousin), the parser must be rewritten around an
explicit AST stack.

tinyp8.p8 already demonstrates the iterative shape -- a flat
dispatcher over tokens with no recursion. The pattern is well-
understood; the work is mechanical but voluminous.

Recommended approach:

1. `[done]` Write `p8c/iter_parse.py` next to `parse.py`. Expression
   parsing via shunting-yard over explicit operand/operator stacks
   (no recursion): binary precedence ladder, prefix unary, parens,
   calls with comma args, and postfix `arr[idx]` / `.field`. Each
   nested marker records its operand-stack floor so reductions stay
   within their sub-expression. `tests/test_iter_parse.py` proves AST
   + stop-position equivalence with the recursive parser over a
   hand-written corpus, trailer cases, and 4000 randomized
   differential samples. Also wired into `parse.py` behind an
   `iter_expr` flag; `tests/test_iter_parse_integration.py` compiles
   the whole example/snapshot corpus (22 files incl. tinyp8.p8) under
   both parsers and asserts byte-identical codegen.
2. `[done]` Extend to statements. `parse.py` now has `parse_block_iter`,
   a frame-stack driver that replaces the recursive block-nesting:
   each open block / compound is a frame on an explicit stack, leaf
   statements reuse the existing (non-recursive) helpers, and `defer`
   is handled as a modifier that attaches to the next statement
   (simple or compound). `if/else`, `while`, `for`, `repeat`, and
   `when` (choice list + else) are all built on close. Gated by an
   `iter_stmt` flag (which implies `iter_expr`).
3. `[done]` Wire in via flags, run the host suite under both parsers.
   `tests/test_iter_parse_integration.py` compiles the whole corpus
   (22 files incl. tinyp8.p8) under `iter_expr=True` and `iter_stmt=True`
   and asserts byte-identical codegen; `tests/test_iter_parse.py` also
   diffs full-program ASTs under `iter_stmt`.
4. `[done]` Make the iterative parser the **default**. `parse()` now
   defaults to `iter_expr=True, iter_stmt=True`, so the CLI, every
   existing test tier (parse/sema/codegen/snapshots), and the tinyp8
   self-host build all run on the iterative parser. The recursive
   descent is *retained* (selectable via `iter_expr=False,
   iter_stmt=False`) as the equivalence oracle the tests check against
   and as the reference for the Prog8 port -- it is NOT deleted yet on
   purpose: deleting it would remove that oracle. Drop it only once the
   Prog8 port is itself the working reference.
5. `[in progress]` Port `iter_parse.py` + `parse_block_iter` to Prog8
   itself. Design doc: [`PARSER_PORT_DESIGN.md`](./PARSER_PORT_DESIGN.md)
   -- node-arena AST, parallel-array stacks/frames, a canonical AST
   serialization as the equivalence contract, and milestones M0
   (Python serializer) through M5 (capacity/streaming).
   * `[done]` **M0 -- serializer + format freeze (Python only).**
     `p8c/serialize.py` emits the canonical AST S-expression;
     `p8c --dump-ast` exposes it (parser-only, the golden the on-target
     parser is diffed against). `tests/test_serialize.py` freezes it
     with format assertions, a recursive-vs-iterative serialization
     equivalence gate over the whole corpus, and on-disk goldens
     (`tests/goldens_sexp/`).
   * `[done]` **M1 -- lexer port.** Oracle: `serialize_tokens()` +
     `p8c --dump-tokens` define the canonical token-dump, frozen by
     `test_serialize.py`. On-target: `p1/lexer.p8` emits that dump on
     the 6502, verified byte-identical over examples + snapshots +
     `tinyp8.p8` + the lexer lexing its own source + the edge-case
     corpus (`p1/tests/test_lexer.py`, `make p1-test`).
   * `[done]` **M2 -- expression parser port.** `p1/expr.p8` lexes one
     expression to token arrays, parses it (shunting-yard over explicit
     stacks into a struct-of-arrays node arena), and serializes it
     (explicit work-stack walk) byte-identical to the oracle over the
     ENTIRE `EXPRESSIONS` corpus + a randomized-fuzz sample: atoms,
     unary, binary ladder, parens, calls (nested/dotted), indexing
     (`arr[i]` / `.field`), `@()`, `&name` (`p1/tests/test_expr.py`).
     Two host-p8c bugs fixed en route (mkword Y-clobber; I/O
     EOF-stickiness vs the emulator's rewind-on-EOF); one gap worked
     around (ubyte array element -> uword widening).
   * `[done]` **M3 -- statement parser port.** `p1/stmt.p8` ports the
     top-level program parser + the frame-stack statement driver +
     the full `(program ...)` serializer (uword arenas), byte-identical
     to the oracle over the whole `STMT_PROGRAMS` corpus
     (`p1/tests/test_stmt.py`). Three host enhancements made en route:
     ZP-overflow scalars -> main memory; reentrant-safe sub calling
     convention (args via the stack); a serializer ordering-bug fix.
   * `[done]` **M4 -- whole-program parse on-target.** stmt.p8 extended
     to the full top-level surface (directives + imports, const, enum,
     struct + struct instances/arrays, asmsub, inline sub), byte-identical
     to the oracle over the ENTIRE `examples/` corpus (18 files incl.
     tokenizer.p8). `p1/tests/test_stmt.py::test_examples`.
   * `[done]` **M5 -- capacity / streaming.** The on-target parser
     streams per top-level unit (streaming lexer + 2-token window,
     rewind-free statement parse, two passes over the rewound source,
     node-arena reset between subs), so the whole 1289-line `tinyp8.p8`
     (~2300 AST lines) parses byte-identical to the host
     (`p1/tests/test_stmt.py::test_tinyp8_capacity`).

   **Step 5 (the Prog8 parser port) is COMPLETE: M0-M5 all done.** The
   parser runs on the 6502 and is byte-identical to the host across the
   token / expression / whole-program contracts, including a real
   compiler-sized program. Phase 7 can begin.

Estimated remaining effort: the Prog8 port (step 5) is the last piece,
and it feeds directly into Phase 7. The iterative parser is now the
production path; the recursive descent survives only as a test oracle.
M0 is done (the format is frozen); M1 (the lexer port) is next.

### Phase 7 -- Self-hosting bootstrap proof `[in progress: design done]`

The Phase 6 parser port is complete (`p1/` M0..M5: lexer, expression
parser, statement/whole-program parser, streaming -- parses the whole
tinyp8.p8 byte-identically on the 6502). Phase 7 adds the back half:
**sema + codegen**, so `p1.p8` compiles `.p8` -> `.s` on the 6502,
byte-identical to host `p8c`.

Design doc: [`PHASE7_DESIGN.md`](./PHASE7_DESIGN.md) -- the contract is
`p8c -o` (no freeze step); the real `p1.p8` drops the AST serializer
(parser-verification scaffolding) and reuses the streaming front-end; a
multi-pass driver (pass S builds the whole-program symbol table with
byte-exact ZP allocation, then prologue, then main, then the other subs,
then trailers) reconciles streaming with the global symbol table and
main-first emission; milestones P7-M1 (`main { }` skeleton) .. P7-M6
(corpus + `p0(p1.p8)==p1(p1.p8)`). 64 KB capacity is the main risk
(mitigated by dropping the serializer + table-driving the literal text).

Original plan:

1. Port host p8c to Prog8. Call it `p1.p8`.
2. Aim for ≤32 KiB compiled so it fits in one wendy2c bank, OR
   target nmos-default with file I/O and forget banking.
3. Verification gates:
   * **Binary equivalence**: `p0(p1.p8) == p1(p1.p8)` after
     re-running through the same downstream assembler. The
     classic asm17 self-host check, in 6502-Prog8 form.
   * **Output equivalence on a test corpus**: for every
     `.p8` in a curated set, p0's output equals p1's output.
   * **End-to-end golden runs**: each corpus `.p8` compiled by p1
     and run on the emulator produces the expected LCD / stdout.

### Phase 8 -- Chain growth `[todo]`

Mirror the asm00..asm17 chain. `p2.p8` adds features that `p1`
couldn't express, compiled by `p1`. `p3.p8` adds more, compiled by
`p2`. Etc. Each stage:

* Lives in its own `pN/` directory.
* Adds one or two language categories.
* Has its own three verification gates.
* The corpus from every earlier `pK` (K < N) reruns against pN.

This is the long-term steady-state.

---

## Where we are right now

Branch `claude/prog8-bootstrap-continue-6Pzo0` (continues the
`claude/review-wendy2-plan-MOfnA` work).

* Phases 0-4: **done**.
* Phase 5 (tinyp8.p8 growth): at **v9**. Real loops, conditionals,
  arithmetic, comparisons, and now **multi-character variable names**
  via a symbol table. Next surface items: stdin input (v10),
  multi-statement bodies, deeper expressions.
* Phase 6 (iterative parser rewrite): **steps 1-4 done** -- the
  iterative parser handles both expressions and statements and is now
  the DEFAULT path (CLI + all test tiers + the tinyp8 self-host build
  run on it). Proven equivalent to the recursive descent (unit +
  4000-sample fuzz + full-program AST diff + whole-corpus
  byte-identical codegen); the recursive parser is kept as the test
  oracle. Step 5 (the Prog8 port) is **in progress**: M0 done -- the
  canonical AST serializer (`p8c/serialize.py` + `--dump-ast`) is
  written and the format is frozen by `tests/test_serialize.py` +
  on-disk goldens. M1 (lexer port to `p1/`) is next.
* Phase 7-8: blocked on the rest of the Phase 6 Prog8 port (M1-M4).

153 tests green (host p8c 104, tinyp8 22, p1 27). Self-host equivalence holds for the v0/v1 corpus.

---

## Critical-path summary (what gates full self-host)

Of all the work above, only TWO items truly block the end-state:

1. **Phase 6** -- host parser rewrite. This is the one big design
   item left. Without it, host p8c can't be ported to Prog8.
2. **Phase 7** -- writing p1.p8 itself and getting the equivalence
   gates green.

Everything else (Phase 5 continued tinyp8 growth, more upstream
Prog8 features in the host) makes the project *better* but isn't
on the critical path. If you only had time for one thing, do
Phase 6.

That said, Phase 5 work has value beyond the bootstrap: it keeps
the on-target compiler real, exercises the language under load,
and surfaces friction that would otherwise only appear in the
Phase 7 grind.

---

## Recommended cadence (per fresh session)

* Take **one** of the next-push options from `RESUME_NOTES.md`,
  or the next sub-step from the Phase 6 plan above.
* Stay within a single feature. Commit at the green test boundary;
  push every commit.
* At end of session, refresh `RESUME_NOTES.md` and this file's
  status markers. Push the README too if any user-facing
  surface changed.

---

## How a fresh session should orient itself

1. Read `toolchain/prog8/PLAN.md` (this file) -- gives you the
   strategic map.
2. Read `toolchain/prog8/RESUME_NOTES.md` -- tells you what
   landed in the most recent session and what the concrete
   ready-to-pick-up next pushes are.
3. (Optional) Skim `toolchain/prog8/README.md` -- the per-feature
   language-surface checklist.
4. `make -C toolchain/prog8 prog8-test tinyp8-test` -- confirm
   everything's actually green before you start changing things.
5. Pick one push from RESUME_NOTES.md, work it, commit, push.
   Update RESUME_NOTES.md (and this file's status markers if a
   phase or sub-phase completed).
