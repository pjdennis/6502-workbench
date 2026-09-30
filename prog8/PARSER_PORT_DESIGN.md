# Design: porting the iterative parser to Prog8 (Phase 6, step 5)

Status: **design** -- no code yet. This is the document PLAN.md's
Phase 6 asks for "before the first push" of the Prog8 port.

For the strategic context see [`PLAN.md`](./PLAN.md) (Phase 6/7) and
[`RESUME_NOTES.md`](./RESUME_NOTES.md) (Option D). The Python side of
the rewrite is done: `p8c/iter_parse.py` (expressions) and
`Parser.parse_block_iter` in `p8c/parse.py` (statements) are the
default parser and are proven equivalent to the recursive descent.
This doc plans porting **that** parser -- and the lexer it depends on
-- to Prog8, so it can run on the 6502 and become part of `p1.p8`
(Phase 7).

---

## 1. Goal and success criterion

A Prog8 program (call the directory `p1/`) that, running on the
emulator's nmos-default machine, reads a `.p8` source file and emits a
**canonical AST serialization** byte-identical to the one the Python
parser produces for the same input, across a growing corpus.

This mirrors the existing tinyp8 methodology exactly: compile/run on
the emulator, diff stdout against a golden. The Python iterative parser
is the oracle; the golden is its serialized output.

Non-goals here: sema and codegen. Those are later Phase-7 work. But the
AST representation chosen here is shared infrastructure the whole
Phase-7 compiler will reuse, so it is designed with that in mind.

---

## 2. The core problem

Python leans on three things the 6502 port cannot: recursion,
heap-allocated heterogeneous records (the AST dataclasses + the
operator-stack/frame dicts), and growable lists. The algorithm is
*already* non-recursive (that was the whole point of step 1-2), so the
work is purely **data-representation**: replace every Python object and
list with fixed-layout arrays in 6502 RAM.

Prog8 subs are non-reentrant, so the port must keep the iterative
shape -- no parser sub may call itself or form a call cycle. The
explicit stacks below are what make that possible.

---

## 3. Data representations

All sizes below are first-cut budgets to be tuned once we measure
against real inputs. The nmos-default machine has RAM from `$0200`
upward; arrays live in main memory (not ZP), as in tinyp8.p8.

### 3.1 Interned text pool (identifiers + string literals)

Identifiers (`foo`, `a.b.c`) and string-literal contents are stored
once in a byte pool; everything else refers to them by a small id.

    ubyte[POOL]  text_pool        ; raw bytes, append-only
    uword[NIDENT] ident_off       ; start offset of ident i
    ubyte[NIDENT] ident_len       ; its length
    uword         ident_count

`intern(start,len) -> id`: linear scan for an existing match (same
idiom as tinyp8 v9 `find_var`), else append. Dotted paths (`a.b`) are
interned as the full dotted text, exactly as the Python parser stores
`Ident.name = "a.b"` -- so the serializer prints them identically.

String literals get their own parallel pool (`str_off/str_len`) so an
`StrLit`'s id namespace is distinct from idents.

### 3.2 AST node arena (struct-of-arrays)

One arena, indexed by a 16-bit node id. Id 0 is the null node.

    ubyte[NNODE]  node_kind       ; tag -- see kinds below
    ubyte[NNODE]  node_op         ; operator id (BinOp/UnaryOp), else 0
    uword[NNODE]  node_a          ; first field (child id / value / text id)
    uword[NNODE]  node_b          ; second field
    uword[NNODE]  node_c          ; third field
    uword         node_count      ; bump allocator; new_node() returns id

Per-kind field meaning (mirrors `p8c/ast.py`):

| kind        | node_op | node_a            | node_b        | node_c          |
|-------------|---------|-------------------|---------------|-----------------|
| INTLIT      | --      | value (uword)     | --            | --              |
| STRLIT      | --      | str id            | --            | --              |
| BOOLLIT     | --      | 0/1               | --            | --              |
| IDENT       | --      | ident id          | --            | --              |
| BINOP       | op id   | lhs node          | rhs node      | --              |
| UNARYOP     | op id   | operand node      | --            | --              |
| ADDRESSOF   | --      | ident id          | --            | --              |
| MEMAT       | --      | addr node         | --            | --              |
| INDEX       | --      | array node        | index node    | field ident id  |
| CALL        | --      | path ident id     | arg list head | --              |
| EXPRSTMT    | --      | expr node         | --            | --              |
| ASSIGN      | op id   | target node       | rhs node      | --              |
| VARDECL     | --      | type tag          | name ident id | init node       |
| INLINEASM   | --      | str id            | --            | --              |
| IF          | --      | cond node         | then list     | else list       |
| WHILE       | --      | cond node         | body list     | --              |
| FOR         | --      | var ident id      | lo node | hi  | body list (see 3.4) |
| REPEAT      | --      | count node (0=∞)  | body list     | --              |
| WHEN        | --      | expr node         | choice list   | --              |
| WHENCHOICE  | --      | value list        | body list     | --              |
| BREAK       | --      | --                | --            | --              |
| CONTINUE    | --      | --                | --            | --              |
| RETURN      | --      | value node (0=none)| --           | --              |
| DEFER       | --      | stmt node         | --            | --              |
| BLOCK       | --      | stmt list head    | --            | --              |

`FOR` needs four operands (var, lo, hi, body); it overflows the three
field slots. Options: (a) widen the arena to `node_d`, or (b) give FOR
a side-record `for_lo[]/for_hi[]` indexed by a small for-id stored in
node_b. Recommend (a) `node_d` -- one extra `uword[NNODE]` is cheap and
keeps everything uniform. (Decision to confirm at implementation; the
table above assumes node_d exists for FOR.)

`type tag` for VARDECL is a small enum byte (ubyte/byte/uword/... and
the `const-`/array variants); the Python side encodes these as strings,
so the serializer maps tag -> the same string.

Loc (line/col) is **dropped** from AST nodes. The Python serializer
ignores loc already (see `tests/test_iter_parse.py::dump`), so parity
holds. Error messages on-target can recover position from the current
token (tokens keep line/col -- see 3.3), which is enough for a first
port.

### 3.3 Token stream

The lexer (ported separately -- it is already a non-recursive `while`
loop, the easy part) fills parallel arrays:

    ubyte[NTOK]  tok_kind         ; enum: EOF/INT/STR/IDENT/KW/DIRECTIVE
                                  ;       + one tag per punctuation/op token
    uword[NTOK]  tok_val          ; INT: value; IDENT/KW/DIRECTIVE: ident id;
                                  ; STR: str id; operators: 0
    uword[NTOK]  tok_line
    ubyte[NTOK]  tok_col

The parser holds a cursor `pos` and the helpers `peek/eat/match` over
these arrays -- a direct transcription of `IterParser.peek/eat/match`.

Token-kind enum: assign a fixed ubyte to each kind the Python lexer
emits, including every punctuation/multi-char operator token
(`"+","==","<<=", ...`). This is a flat table; the lexer port and the
parser port must agree on it. Keep it in one shared `.p8` include.

### 3.4 Lists (block stmts, call args, when choices/values)

Variable-length sequences are built as singly-linked cons cells:

    uword[NCONS]  cons_val        ; a node id
    uword[NCONS]  cons_next       ; next cons, 0 = nil
    uword         cons_count

A "list" is the id of its head cell (0 = empty). The parser builds each
list by **prepending** (O(1), head-only -- no tail bookkeeping needed),
then **reverses it in place** at finalize (walk re-linking `cons_next`;
no allocation). Prepend+reverse keeps each accumulator down to a single
`uword` head, which matters because frames (3.6) carry several.

Nested lists are independent (each has its own head), so nesting -- a
block inside a when-choice inside a for body -- just works; contrast
with a single shared span pool, which breaks under interleaving.

### 3.5 Expression stacks (port of `iter_parse.py`)

Two stacks. Operands are node ids; operators/markers are a
struct-of-arrays indexed by `op_sp`:

    uword[ESTK]  operand_stack    ; node ids;  operand_sp
    ubyte[OSTK]  op_kind          ; binop/unop/lparen/memat/call/lbracket
    ubyte[OSTK]  op_op            ; operator id (binop/unop)
    ubyte[OSTK]  op_prec          ; precedence (binop)
    ubyte[OSTK]  op_floor         ; operand_sp when a marker opened
    uword[OSTK]  op_path          ; call: path ident id
    uword[OSTK]  op_args          ; call: arg-list head (prepend; reverse on close)
    uword        op_sp

This is a transcription of the dict entries in `IterParser.parse_expr`.
`_is_op/_is_marker/_op_prec` become trivial comparisons on `op_kind`.
The `index_ok` flag and `expect_operand` state become two ubytes. The
precedence table `_OP_PRECEDENCE` becomes a const `ubyte[]` indexed by
operator id; unary precedence is the `_UNARY_PREC` constant.

`apply()`, `reduce_to_marker()` and the main dispatch loop port
one-to-one; "pop two operands, push BinOp" becomes
`new_node(BINOP, op, operand_stack[--sp], operand_stack[--sp]...)`.

### 3.6 Statement frame stack (port of `parse_block_iter`)

Frames become parallel arrays indexed by `fr_sp`, sized for the widest
frame kind (the RESUME_NOTES caveat made concrete):

    ubyte[FSTK]  fr_kind          ; root/then/else/while/for/repeat/when/when_choice
    ubyte[FSTK]  fr_mode          ; stmts / choices
    uword[FSTK]  fr_stmts         ; accumulated-stmt list head (stmts mode)
    ubyte[FSTK]  fr_defer         ; 1 if this stmt was `defer`-prefixed
    uword[FSTK]  fr_cond          ; cond / when-expr / repeat-count node
    uword[FSTK]  fr_then          ; saved then-list (else frame)
    uword[FSTK]  fr_var           ; for: loop var ident id
    uword[FSTK]  fr_lo            ; for: lo node
    uword[FSTK]  fr_hi            ; for: hi node
    uword[FSTK]  fr_choices       ; when: choice list head
    uword[FSTK]  fr_values        ; when_choice: value list head
    uword        fr_sp

`pending_defer` is a single ubyte (+ no loc, since loc is dropped). The
main loop, the `mode == choices` branch, the close-and-attach logic,
and `_iter_stmt_dispatch` port directly. "Attach to parent" =
prepend the built node onto `fr_stmts[fr_sp-1]` after popping.

### 3.7 Memory budget (first cut, to measure)

For a tinyp8.p8-sized input (~1300 lines): tokens dominate. Rough
order-of-magnitude per arena element x count -> bytes; we will measure,
but the plan is to keep each arena independently sized and bump-checked
(like tinyp8's ZP allocator guard) so overflow is a clean error, not
corruption. If a single input won't fit, the parser streams per-sub
(parse one sub, hand its AST to the next stage, reset arenas) -- the
asm-chain already proves per-unit streaming works. Capacity tuning is
its own milestone (M5 below).

---

## 4. Canonical serialization (the equivalence contract)

**Implemented (M0): `p8c/serialize.py`.** Both parsers emit the AST as a
deterministic, indented prefix S-expression; the Python serializer is
the reference and the Prog8 serializer must match it byte-for-byte. The
format below is the one frozen by `serialize.py` and the goldens in
`tests/goldens_sexp/`; the snippets show the *flat* shape, but the real
output puts one head per line with children indented two spaces and
closing parens trailing (see the goldens for exact whitespace).

Expressions:

    (int 42)                 (str "hi")          (bool true)
    (id foo)                 (id a.b.c)
    (+ E E)  (== E E)  ...   (u- E)  (~ E)  (not E)
    (addr foo)               (mem E)
    (idx E E)                (idx E E .field)
    (call a.b E E ...)       (call f)            ; zero args

Statements:

    (block S S ...)          (block)             ; empty
    (var ubyte x E?)         (var ubyte[4] arr)  (var const-ubyte K E)
    (assign = T E)           (assign += T E)     (exprstmt E)
    (asm "...")
    (if E (block...) (block...)?)
    (while E (block...))     (for x E E (block...))
    (repeat (block...))      (repeat E (block...))
    (when E (choice (vals E E ...) (block...)) (choice (vals) (block...)) ...)
    (break) (continue) (return E?) (defer S)

Top level (what the parser, pre-sema, actually produces):

    (program
      (address $XXXX) (output FMT) (target TGT)
      (imports (import NAME) ...)
      (vars VARDECL ...)
      (enums (enum NAME (members (M VAL) (M -) ...)) ...)
      (structs (struct NAME (fields (TYPE FN) ...)) ...)
      (subs SUBDEF ...))

    SUBDEF := (subdef NAME KIND RET (params (param TYPE NAME) ...) BODY)
              KIND := sub | main | inline | asmsub
              BODY := (block ...)            for sub/main/inline
                    | (asmtarget $XXXX)      for asmsub

Operator tokens print as their source spelling (`+`, `<<`, `and`, ...);
unary `-` prints as `u-` to stay distinct from binary `-`. String
literals are escaped with a tiny, 6502-reproducible escape set (`\\`,
`\"`, `\n`, `\r`, `\t`). Sema-assigned fields (`sym`/`type`/`mangled`/
addresses/labels) and source `Loc` are **not** serialized -- the
contract describes exactly what *parsing* yields, which is what the
on-target parser will have.

A `serialize(node)` walk is itself recursion in Python; on-target it is
a second iterative tree-walk over the node arena using an explicit
work stack (same toolkit as the parser). It is small and can come
after M3. The Python CLI exposes it as `p8c --dump-ast` (parser-only),
the command later milestones diff their on-target output against.

---

## 5. Milestones (each is one or a few pushes, each with a golden tier)

* **M0 -- serializer + format freeze (Python only). DONE.**
  `p8c/serialize.py` + `p8c --dump-ast` + `tests/test_serialize.py`
  (format assertions, a recursive-vs-iterative serialization
  equivalence gate over the whole corpus, and on-disk goldens in
  `tests/goldens_sexp/`). The contract is frozen. *(pure Python; runs
  without vasm.)*

* **M1 -- lexer port.** `p1/lexer.p8`: source bytes -> token arrays +
  text pools. Golden: dump the token stream for a corpus and diff
  against a Python token-dump. The lexer is non-recursive already, so
  this is mostly transcription + the pools.
  * `[done]` **M1 oracle.** `serialize_tokens()` + `p8c --dump-tokens`
    define the canonical token-dump (one token per line: `INT n`,
    `STR "..."`, `IDENT/KW/DIRECTIVE text`, `PUNCT spelling`, `EOF`;
    positions dropped, like the AST contract). Frozen by
    `tests/test_serialize.py` (`TokenDumpFormat` + the `LEXER_CORPUS`
    golden `tests/goldens_sexp/tokens.dump`, exercising every numeric
    base, char/string escape, keyword-vs-identifier trap, and
    multi-char-operator maximal munch).
  * `[done]` **M1 on-target.** `p1/lexer.p8` emits that dump, built +
    diffed through the emulator like `tinyp8/`. Verified byte-identical
    over every `examples/*.p8`, the snapshot corpus, `tinyp8.p8` (1289
    lines), `lexer.p8` lexing its own source, and the edge-case corpus
    (`p1/tests/test_lexer.py`, wired as `make p1-test`). Reuses the
    tinyp8 file-I/O shim; decimal output via power-of-ten subtraction
    (host p8c has no `/`). Porting this surfaced and fixed a host-p8c
    codegen bug: a binary op whose two operands each need a scratch temp
    (e.g. `(v<<3)+(v<<1)`) clobbered itself; the fix holds the first
    operand on the CPU stack (`p8c/codegen.py::_emit_word_operands`),
    guarded by `tests/test_codegen_arith_e2e.py`.

* **M2 -- expression parser port. DONE.** `p1/expr.p8` lexes a single
  expression into in-memory token arrays, parses it with the
  shunting-yard engine over explicit operand/operator stacks into a
  struct-of-arrays node arena, and serializes the arena with an explicit
  work-stack tree walk -- all no-recursion. Covers the full expression
  grammar: atoms (int/str/bool/ident incl. dotted), prefix unary
  (`- ~ not`), the binary precedence ladder, parentheses, function calls
  (nested + dotted, via a reversed cons-cell arg list -- 3.4), indexing
  `arr[i]` / `arr[i].field`, `@()`, and `&name`. Verified byte-identical
  to the Python oracle over the **entire** `EXPRESSIONS` corpus plus a
  randomized-fuzz sample (`p1/tests/test_expr.py`, `make p1-test`).
  Three host-p8c issues found + handled doing M2: `mkword(hi, lo)`
  stashed the high byte in Y, which an array-read low arg clobbered
  (fixed in codegen); the I/O shim looped forever on a token ending at
  EOF because the emulator rewinds the input on EOF (now EOF is made
  sticky in software); and a ubyte *array element* can't be widened to
  uword by codegen, so expr.p8 copies such values through a ubyte local
  before passing them where a uword is expected (a clean p8c codegen fix
  -- teaching `_emit_word_expr_into_ay` to handle plain array reads --
  is a good future cleanup).
  **Representation note:** M2 (`p1/expr.p8`) holds one expression's
  arenas in <=256-element byte arrays (16-bit values split lo/hi)
  because that was all p8c supported at the time. Since then p8c gained
  real 16-bit arrays (`uword[N]`, up to 8192 elements, uword index --
  see `_emit_array_addr_into_aptr`), plus ubyte-element->uword widening,
  so M3+ can use full uword arenas/indices without the <=256 cap or the
  lo/hi split.


* **M3 -- statement parser port. DONE.** `p1/stmt.p8`: the top-level
  program parser + the frame-stack statement driver (3.6) + the full
  `(program ...)` serializer, all no-recursion, with uword arenas (p8c's
  16-bit arrays) so node/token counts exceed 256. Covers module var
  decls, subs (sub/main with params + return), blocks, if/else, while,
  for-in-to, repeat, when (multi-value choices + else), defer,
  break/continue/return, assignments (incl. augmented, `@()=`,
  `arr[i]=`), call statements, and inline `%asm`. Byte-identical to the
  oracle over the entire `STMT_PROGRAMS` corpus (`p1/tests/test_stmt.py`,
  `make p1-test`). Three host enhancements were needed and made: scalars
  overflow ZP into main memory (the global ZP allocator can't hold a big
  program's locals); the sub calling convention evaluates args onto the
  stack before filling the (non-reentrant) param slots, so `f(.., g())`
  with `g` transitively calling `f` is correct; and a serializer
  `ws_sp`-increment ordering bug was fixed. Directives, const/enum/
  struct, and asmsub are not yet handled -- that is M4 (the `examples/`
  corpus).

* **M4 -- whole-program parse on-target. DONE.** `p1/stmt.p8` extended
  to the full top-level surface: directives (`%address` / `%output` /
  `%import` -> the imports list / `%target` -> target + nmos address
  default), `const` decls, `enum` decls (members with optional values),
  `struct` decls + struct instances/arrays (`Point p`, `Token[4] toks`),
  `asmsub` (`(asmtarget $XXXX)`), and `inline sub`. Byte-identical to the
  oracle over the **entire `examples/` corpus** (18 files, incl.
  `tokenizer.p8` = enum + struct + inline), `p1/tests/test_stmt.py`.
  tinyp8.p8 itself (1289 lines, ~2300 AST lines) does not yet fit the
  arenas / 64 KB -- that is M5.

* **M5 -- capacity + streaming. DONE.** The on-target parser streams
  per top-level unit so a compiler-sized program fits in the 64 KB
  address space (whole-program token + node arenas would not). The
  lexer became a streaming source with a 2-token lookahead window (no
  token array); `parse_assign_or_expr` was made rewind-free (parse the
  LHS as an expression, then check for an assignment operator) so the
  streaming lexer needs no backtracking. Two passes over the (rewound)
  source: pass A collects directives + module decls (skipping sub
  bodies by brace-matching) and emits the program head + vars/enums/
  structs; pass B streams each sub -- parse, serialize, reset the node
  arena -- so only the biggest single sub's nodes ever coexist. The
  text pools persist across pass B (their union fits; ids dedupe),
  which the lookahead window relies on. Result: the **whole 1289-line
  `tinyp8.p8`** (~2300 AST lines) parses byte-identically to the host
  (`p1/tests/test_stmt.py::test_tinyp8_capacity`). NB a streaming pitfall
  fixed here: the lexer and parser share `name_buf`, and the parser's
  dotted-path read must use a separate `path_buf`, since each `advance()`
  lexes a lookahead token that clobbers `name_buf`.

  Arena sizes are tuned for tinyp8.p8 + the examples (biggest sub ~470
  nodes). p1's own larger sources (`stmt.p8`: 415 idents / 1083-node
  sub) need bigger arenas than fit alongside the current code; shrinking
  the serializer's per-byte string emission (table-driven) would buy the
  room -- a later refinement, not on the critical path.

**Phase 6 step 5 is COMPLETE.** The Prog8 parser exists on-target,
proven byte-identical to the host across the token, expression, and
whole-program contracts (M1-M5) and transitively back to the recursive
grammar (M0). Phase 7 (porting sema+codegen, assembling `p1.p8`) can
begin on top of this AST representation.

---

## 6. Verification strategy (why this is trustworthy)

Three independent oracles already guard the Python iterative parser
(unit equivalence, 4000-sample fuzz, whole-corpus codegen diff). The
Prog8 port adds a fourth gate of the same kind: **serialization diff
against the Python parser** at every milestone (M1-M4). Because the
Python parser is the default production parser and is itself checked
against the recursive descent, a green serialization diff transitively
ties the on-target parser back to the original recursive grammar.

The randomized differential fuzzer (3.x in the test) can be reused: it
already emits valid expression strings; feed the same strings to the
on-target parser via a batch driver and diff serializations. That gives
the Prog8 expression parser the same fuzz coverage the Python one has.

---

## 7. Open questions / risks

* **`node_d` for FOR.** Confirm widening the arena vs. a side-record.
  Leaning to widen (uniform, cheap).
* **Arena sizing for real p8c.** tinyp8.p8 is ~1300 lines; the eventual
  p1.p8 is larger. M5 decides fixed sizes vs. per-sub streaming. This
  is the biggest unknown and is deliberately last.
* **Token-kind enum sharing.** The lexer and parser ports must share
  one kind table; keep it in a single include both `%import`.
* **Operator-id encoding.** Map each operator token-kind to a small id
  with a const lookup; the precedence table indexes by that id.
* **Where this lives.** Proposed `assembler2/prog8/p1/`, built and
  tested through the emulator exactly like `tinyp8/` (vasm -> bin ->
  emulator -> diff golden). Reuses the tinyp8 runtime-I/O shim.
* **Self-reference.** Eventually p1.p8 must parse *its own* source.
  Nothing here precludes it, but the grammar subset p1 accepts must
  cover the subset p1 is written in -- track that as the parser grows,
  the same way tinyp8's versions did.

---

## 8. What to do first

M0: add the Python `serialize()` and freeze the format. It is pure
Python (no vasm/emulator needed), it pins down the contract every later
milestone diffs against, and it is small. Then M1 (lexer) is the first
on-target push.
