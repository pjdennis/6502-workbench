# Prog8 compiler for wendy2c

Bootstrap chain for a Prog8 compiler that eventually self-hosts on
wendy2c, mirroring the asm00..asm17 chain.

**Three companion documents:**

* [`PLAN.md`](./PLAN.md) -- strategic plan: goal, phase map, what's
  done, what remains, critical-path summary. Read this first when
  picking the project up.
* [`RESUME_NOTES.md`](./RESUME_NOTES.md) -- session-handoff notes:
  exactly where the last session stopped, ready-to-pick-up next
  pushes, pitfalls observed, quick-resume cheatsheet.
* This file (README) -- per-feature language-surface checklist and
  layout reference.

## Layout

    prog8/
        p8c/                  # Phase-1 "p0" host compiler (Python)
            __main__.py       # CLI driver: `python3 -m p8c`
            lex.py
            parse.py
            sema.py
            codegen.py
            stdlib_decls.py   # symbols the stdlib modules export
        stdlib/               # Prog8 + inline-asm stdlib modules (Phase 2+)
        examples/             # demo programs
            hello.p8
        tests/
            test_lex.py       # lexer unit tests
            test_parse.py
            test_sema.py
            test_codegen.py
            test_snapshots.py # .p8 -> .s text diffs (host oracle)
            test_e2e_lcd.py   # compile + assemble + emulate + LCD diff
            goldens/          # .p8 + matching .expected.lcd
            snapshots/        # .p8 + matching .expected.s

## Building / running

    # Build the emulator (needed by the e2e golden test):
    make emulator/emulator.out        # from the repository root

    # Run the test suite:
    make -C toolchain/prog8 prog8-test

    # Compile a .p8 by hand and inspect the .s:
    python3 -m p8c toolchain/prog8/examples/hello.p8 -o /tmp/hello.s

    # Compile + assemble + run on the emulator (prints the LCD frame):
    python3 -m p8c toolchain/prog8/examples/hello.p8 --run

## Phase status

**Phase 0** (scaffolding) and **Phase 1** (walking skeleton) -- done:

  * lex/parse/sema/codegen for `main { ... }`, `%address`, `%import`,
    `%output`, `txt.print("...")`, `lcd.clear()`.
  * Test pyramid wired up: unit, snapshot, end-to-end LCD golden.
  * `hello.p8` compiles, lands at `$4000` via the wendy2c boot ROM,
    prints to the HD44780.

**Phase 2** (start) -- done in this commit:

  * Module-level + sub-local `ubyte` variable declarations with
    optional initializers; ZP allocator starting at `$40` (variables)
    with `$20/$21` reserved as codegen scratch.
  * Assignment + augmented assignment (`+=`, `-=`, `&=`, `|=`, `^=`,
    `<<=`, `>>=`).
  * Binary expressions on `ubyte`: `+`, `-`, `&`, `|`, `^`, `<<`, `>>`
    plus comparison (`==`, `!=`, `<`, `<=`, `>`, `>=`) and logical
    (`and`, `or`, `xor`, `not`) operators with C-like precedence.
  * Unary `~`, `-`, `not`.
  * Control flow: `if`/`else`, `while`, `repeat N`, `repeat` (forever),
    `break`, `continue`. Comparison conditions branch directly --
    no 0/1 materialization.
  * `txt.print_ub(byte)` -- prints two hex chars via the existing
    `display_hex.inc` helper.
  * Demo `examples/counter.p8` exercises all of the above:
    `total=0606 OK` on the LCD.

**Phase 2** (continued):

  * `uword` type with 2-byte ZP storage; literals + var load/store +
    ubyte-widens-to-uword.
  * `for var in lo to hi { ... }` -- inclusive range over a ubyte var.
  * `peek($addr)` and `poke($addr, byte_expr)` builtins.
  * `txt.print_uw(uword)` -- 4 hex chars, high byte first.
  * Module-level var initializers run at the top of `main()`.
  * `examples/peek_demo.p8` -> `00010203 1234 4C` on the LCD.

**Phase 2.5 -- uword arithmetic + subs with params/returns:**

  * Full uword arithmetic: + - & | ^ << >> with carry chains, ==
    != < <= > >= via the 16-bit unsigned-compare idiom.
  * `sub foo(ubyte x, uword y) -> ubyte { ... }` with parameter
    passing (caller stores into mangled ZP slot, then JSR) and
    `return value` (jmp to per-sub epilogue).
  * `asmsub name(...) -> rt = $ADDR` -- declare bindings to existing
    6502 routines; codegen JSRs the literal address.
  * Char literals: `'h'` lexes as an INT token.
  * `examples/uword_arith.p8`, `examples/subs.p8`.

**Phase 3 -- nmos target + self-host milestone:**

  * `%target nmos` switches the prologue: no wendy2c-specific includes,
    reset vector emitted at `$FFFC`, `main()` ends with `jsr $F00F`
    (exit syscall) on the nmos-default machine.
  * `tinyp8/tinyp8.p8` -- the hand-written `tinyp8.s` rewritten in
    Prog8, using asmsubs for the file-I/O stubs and a small inline-asm
    helper for the `read` carry-EOF signal.
  * **Self-host equivalence test**: for every `.tp8` in
    `tinyp8/tests/goldens/`, both `tinyp8.s` (hand-asm) and
    `tinyp8.p8` (compiled by p8c) produce **byte-identical** output.
    5/5 cases pass: a real working compiler, written in Prog8,
    compiled by our own host compiler, agrees bit-for-bit with the
    reference assembly version.

**Phase 4 -- tinyp8.p8 grows beyond the reference (v2..v9):**

  * v2: `let X = $XX` declarations + `print_ub X` references. The
    on-target compiler tracks declared variables in a symbol table and
    emits a 38-byte position-independent hex-print helper lazily on
    first variable reference.
  * v3: `if X == $YY then print_ub Z` -- restricted conditional that
    hard-codes the BNE displacement.
  * v4: `let X = Y` -- variable copy.
  * v5: `let X = Y + Z` / `let X = Y - $ZZ` -- arithmetic with mixed
    variable and literal operands.
  * v6: `while X != $YY` loop with fixed-shape body `let X = X + $ZZ`.
    The loop-top is recorded as `bytes_emitted` so the back-jump
    target is known when needed.
  * v7: full comparison ops (`<`, `<=`, `>`, `>=`, plus existing
    `==` and `!=`) via a shared op-code decoder + branch emitter.
    `<=` and `>` use two-step branch sequences (4 bytes) where
    `==`/`!=`/`<`/`>=` use single-step (2 bytes).
  * v8: while body can include `print_ub Y` before the let increment.
    Detected by peeking the first char of the next line; emits
    the right `skip_size` to the conditional branch and ensures the
    hex helper is in place before `loop_top` is captured.
  * v9: **multi-character variable names** (up to 8 chars, 16 vars).
    The single-char-indexed `var_addrs[26]` table is replaced by a
    small symbol table (`sym_names`/`sym_lens`/`sym_addrs`); a shared
    `read_ident` reads `[a-z]+` into a scratch buffer and
    `find_var`/`declare_var` do a linear-scan lookup/allocate. Names
    only exist at compile time, so emitted code size is unchanged and
    every hard-coded branch displacement stays valid.

  v0/v1 byte-equivalence with `tinyp8.s` stays intact because new
  syntax/state only activates when the new constructs appear. Combined
  corpus is 5 e2e + 5 equivalence + 12 v2..v9 = 22 tinyp8 cases,
  all green.

  Programs the on-target compiler accepts now:

      let i = $00
      while i < $10
          print_ub i
          let i = i + $02
      end
      -> 00 02 04 06 08 0a 0c 0e

      let s = $42
      if s == $42 then print_ub s
      if s >= $40 then print_ub s
      -> 42 42

      let count = $00
      while count < $06
          print_ub count
          let count = count + $02
      end
      -> 00 02 04

      ...etc. Real loops, real conditionals, real arithmetic, named
      variables, all compiled by a Prog8 program running inside the
      emulator.

**Phase 3 cont -- language built out toward Prog8 parity:**

  * Fixed-size `ubyte[N]` and `uword[N]` arrays (1..8192) with indexed
    read/write. Arrays <=256 ubyte elements with a ubyte index use the
    tight `lda label,y` path; uword elements, >256 arrays, or a uword
    index use a ZP element pointer (`label + index*esize`, then
    `(ptr),y`). ubyte elements widen to uword on read.
  * Scalars that overflow the ZP variable window ($40..$ff) spill into
    main memory as labeled reservations (absolute addressing) -- a big
    program's locals no longer hit "out of ZP variable space".
  * Sub calls pass arguments via the hardware stack into the callee's
    (non-reentrant) param slots, so `f(.., g())` where `g` transitively
    calls `f` is correct.
  * `*` ubyte multiplication via a runtime helper (shift-and-add).
  * `@(addr_expr)` byte read/write at arbitrary addresses (via the
    `__p8c_ptr0` indirect-Y pointer in ZP); literal addresses use
    direct absolute load/store.
  * `&name` address-of operator (returns a uword).
  * `const ubyte/uword NAME = LITERAL` -- compile-time constants
    folded to immediate loads at every use site.
  * Builtins: `lsb`, `msb`, `mkword`, `len`, `sizeof` (all
    statically lowered).
  * `when expr { v1, v2 -> body; else -> body }` -- linear
    cmp-and-branch dispatch, ubyte or uword.
  * `inline sub` -- body spliced at each call site; per-callsite
    return label so `return` jumps locally.
  * **Long-branch handling**: all forward conditional branches in
    if/while/for/repeat now emit as `invert-branch + JMP` so they
    work at any distance. Costs +3 bytes per branch; always-safe.

Real-program demos in examples/:
  * arrays.p8, memptr.p8, squares.p8, consts.p8, when.p8,
    inline_demo.p8, **sieve.p8** (Sieve of Eratosthenes, exercises
    arrays + multiplication + nested loops + when -- prints primes
    < 64 in hex).

Self-host equivalence (tinyp8.s == tinyp8.p8) still 4/4 -- new
features are additive, the tinyp8 corpus uses the original v0
language and remains byte-identical to the reference asm.

**Phase 5 -- the language gap to upstream Prog8 mostly closed:**

  * `byte` signed type (Phase 4 push, host) with signed-aware compare
  * `enum` declarations
  * `defer` statement
  * `struct` declarations (single instance)
  * Arrays of structs with indexed field access (`arr[i].field`)
  * Plus everything else from prior phases.

  Combined with the language built out earlier (uword arithmetic,
  arrays, @() / &var, sub/asmsub/inline-sub, when, for-in-to, peek/
  poke, lsb/msb/mkword/len/sizeof, long-branch handling, char
  literals, ...) the host p8c surface is now wide enough to express
  a non-trivial compiler. Tokenizer demo (`examples/tokenizer.p8`)
  proves the shape.

**Still ahead for *full* p8c-in-Prog8 self-host:**

  * Pointer-to-struct (`^^Token`) and struct-as-param.
  * String operations as proper iterable buffers (strlen, strcmp,
    slicing). Building on what we have wouldn't be hard.
  * Multi-file `%import` with namespacing.
  * Iterative parser architecture -- the host p8c was recursive-descent
    in Python; Prog8 forbids recursion, so the *real* self-host needs
    that parser rebuilt around explicit stacks. **Done (Python side):**
    `p8c/iter_parse.py` is an iterative *expression* parser
    (shunting-yard over operand/operator stacks), and
    `Parser.parse_block_iter` is an iterative *statement* parser (a
    frame stack replacing block-nesting recursion). This is now the
    **default** parser -- the CLI, every test tier, and the tinyp8
    self-host build all run on it. It is proven equivalent to the
    recursive descent by unit tests, a 4000-sample randomized
    expression fuzzer, full-program AST diffs, and a whole-corpus
    codegen diff (byte-identical assembly on all 22 example/snapshot
    programs); the recursive parser is retained as that equivalence
    oracle (`parse(..., iter_expr=False, iter_stmt=False)`). Remaining:
    port the iterative parser to Prog8 itself -- planned in
    [`PARSER_PORT_DESIGN.md`](./PARSER_PORT_DESIGN.md), milestones
    M0..M5. **M0 done:** `p8c/serialize.py` + `p8c --dump-ast` /
    `--dump-tokens` emit the canonical AST and token serializations
    (the on-target equivalence contracts), frozen by
    `tests/test_serialize.py` and on-disk goldens. **M1 done:**
    `p1/lexer.p8` is the on-target lexer -- it runs on the 6502 and
    produces a token-stream dump byte-identical to the host lexer over
    examples + snapshots + tinyp8.p8 + its own source (`make p1-test`;
    see [`p1/README.md`](./p1/README.md)). M2 (the expression parser
    port) is next.

See the plan in conversation history for Phases 3-6, including the
on-emulator emit-equivalence test tier that activates at Phase 5 when
the compiler first runs on wendy2c.

## ABI notes (Phase 1)

  * Symbol prefixing per upstream Prog8: `p8v_` vars, `p8s_` subs,
    `p8c_` constants/strings, `p8l_` labels. Right now we only emit
    `p8s_` and `p8c_str_*`.
  * Default load address is `$4000` -- matches every existing
    serial-upload demo (`hello_ram_4000_wendy2c.s` etc).
  * Emitted .s uses asm17-compatible syntax that is also accepted by
    `vasm6502_oldstyle`. Phase 1 assembles with vasm for iteration
    speed; Phase 5 switches the bootstrap-verification path to asm17.
