; p1_pass2_sh.p8 -- PASS 2 of the self-hosting Prog8 pipeline (hand-maintained).
; Reads the AST/symbol dump from p1_pass1_sh.p8 (argv[0]) and writes 6502
; assembly (argv[1]), byte-identical to `p8c -o`. Built into pass2.bin; with
; pass1.bin it self-compiles p1.p8 at 0 diff (the SELF-HOST milestone). The
; codegen back half mirrors build_p1.py -- feature work is applied to both.
; The front-end banner below is the spliced stmt.p8 lexer/parser.


; stmt.p8 -- the Prog8 statement + whole-program parser port (Phase 6, M3).
;
; Reads a whole .p8 program (argv[0]) and writes its canonical AST
; serialization -- the full `(program ...)` form (argv[1]), byte-identical
; to the Python oracle (p8c/serialize.py::serialize). Verified against the
; STMT_PROGRAMS corpus.
;
; Builds on expr.p8: same no-recursion design (shunting-yard expression
; parser, struct-of-arrays node arena, explicit work-stack serializer),
; but now with uword arenas/indices (p8c gained 16-bit arrays), the full
; keyword set, a top-level program parser, and the frame-stack statement
; driver (port of parse.py::parse_block_iter).

%address $0200
%memtop $a9e8

; ---- token kinds ----

%output raw
%launcher none

main {
const ubyte TK_EOF    = 0
const ubyte TK_INT    = 1
const ubyte TK_STR    = 2
const ubyte TK_IDENT  = 3
const ubyte TK_DIRECTIVE = 4
const ubyte TK_TRUE   = 5
const ubyte TK_FALSE  = 6
const ubyte TK_KNOT   = 7
const ubyte TK_KAND   = 8
const ubyte TK_KOR    = 9
const ubyte TK_KXOR   = 10
const ubyte TK_LPAREN = 11
const ubyte TK_RPAREN = 12
const ubyte TK_DOT    = 13
const ubyte TK_COMMA  = 14
const ubyte TK_LBRACK = 15
const ubyte TK_RBRACK = 16
const ubyte TK_AT     = 17
const ubyte TK_LBRACE = 18
const ubyte TK_RBRACE = 19
const ubyte TK_ARROW  = 20        ; ->
; keyword kinds
const ubyte TK_KUBYTE = 40
const ubyte TK_KBYTE  = 41
const ubyte TK_KUWORD = 42
const ubyte TK_KBOOL  = 43
const ubyte TK_KVOID  = 44
const ubyte TK_KSTR   = 45
const ubyte TK_KSUB   = 46
const ubyte TK_KASMSUB= 47
const ubyte TK_KINLINE= 48
const ubyte TK_KMAIN  = 49
const ubyte TK_KIF    = 50
const ubyte TK_KELSE  = 51
const ubyte TK_KWHILE = 52
const ubyte TK_KFOR   = 53
const ubyte TK_KIN    = 54
const ubyte TK_KTO    = 55
const ubyte TK_KREPEAT= 56
const ubyte TK_KBREAK = 57
const ubyte TK_KCONTINUE = 58
const ubyte TK_KRETURN= 59
const ubyte TK_KDEFER = 60
const ubyte TK_KWHEN  = 61
const ubyte TK_KCONST = 62
const ubyte TK_KENUM  = 63
const ubyte TK_KSTRUCT= 64
; operator punctuation
const ubyte TK_PLUS   = 70
const ubyte TK_MINUS  = 71
const ubyte TK_STAR   = 72
const ubyte TK_AMP    = 73
const ubyte TK_PIPE   = 74
const ubyte TK_CARET  = 75
const ubyte TK_SHL    = 76
const ubyte TK_SHR    = 77
const ubyte TK_EQ     = 78
const ubyte TK_NE     = 79
const ubyte TK_LT     = 80
const ubyte TK_LE     = 81
const ubyte TK_GT     = 82
const ubyte TK_GE     = 83
const ubyte TK_TILDE  = 84
; assignment operators
const ubyte TK_ASSIGN = 90        ; =
const ubyte TK_PLUSEQ = 91
const ubyte TK_MINUSEQ= 92
const ubyte TK_ANDEQ  = 93
const ubyte TK_OREQ   = 94
const ubyte TK_XOREQ  = 95
const ubyte TK_SHLEQ  = 96
const ubyte TK_SHREQ  = 97
const ubyte TK_OTHER  = 120

; ---- node kinds ----
const ubyte ND_INT   = 1
const ubyte ND_STR   = 2
const ubyte ND_BOOL  = 3
const ubyte ND_IDENT = 4
const ubyte ND_BINOP = 5
const ubyte ND_UNOP  = 6
const ubyte ND_CALL  = 7
const ubyte ND_INDEX = 8
const ubyte ND_MEMAT = 9
const ubyte ND_ADDROF= 10
const ubyte ND_BLOCK = 11   ; a=stmt cons head
const ubyte ND_EXPRSTMT = 12 ; a=expr
const ubyte ND_VARDECL = 13 ; op=type tag, a=name id, b=init(0=none), c=arrsize(0=scalar)
const ubyte ND_ASSIGN = 14  ; op=assign code, a=target, b=rhs
const ubyte ND_IF    = 15   ; a=cond, b=then block, c=else block(0=none)
const ubyte ND_WHILE = 16   ; a=cond, b=body
const ubyte ND_FOR   = 17   ; a=var id, b=lo, c=hi, d=body
const ubyte ND_REPEAT= 18   ; a=count(0=forever), b=body
const ubyte ND_WHEN  = 19   ; a=expr, b=choices cons head
const ubyte ND_WHENCHOICE = 20 ; a=values cons head (0=else), b=body
const ubyte ND_BREAK = 21
const ubyte ND_CONTINUE = 22
const ubyte ND_RETURN= 23   ; a=value(0=none)
const ubyte ND_DEFER = 24   ; a=stmt
const ubyte ND_INLINEASM = 25 ; a=str id
const ubyte ND_SUB   = 26   ; op=kind, a=name id, b=params cons head, c=body, d=ret tag
const ubyte ND_PARAM = 27   ; op=type tag, a=name id
const ubyte ND_ENUM  = 28   ; a=name id, b=members cons head
const ubyte ND_ENUMMEMBER = 29 ; op=has_value, a=name id, b=value
const ubyte ND_STRUCT= 30   ; a=name id, b=fields cons head
const ubyte ND_FIELD = 31   ; op=type tag, a=field name id
const ubyte ND_CAST  = 32   ; op=target type tag, a=operand node (expr as TYPE)
const ubyte ND_ARRAYLIT = 33 ; a=element cons head (data-initialized array)

; type tags
const ubyte TY_UBYTE = 0
const ubyte TY_BYTE  = 1
const ubyte TY_UWORD = 2
const ubyte TY_BOOL  = 3
const ubyte TY_VOID  = 4
const ubyte TY_STR   = 5
const ubyte TY_CONST_UBYTE = 6
const ubyte TY_CONST_BYTE  = 7
const ubyte TY_CONST_UWORD = 8
const ubyte TY_STRUCT      = 9   ; struct-typed var; struct name id in node_d

; sub kinds
const ubyte SUBK_SUB    = 0
const ubyte SUBK_MAIN   = 1
const ubyte SUBK_INLINE = 2
const ubyte SUBK_ASMSUB = 3        ; `= $ADDR` / extsub decl (no body; jsr $ADDR)
const ubyte SUBK_ASMSUB_BODY = 4   ; inline-body asmsub (emit label + raw asm)

; unary op-ids
const ubyte UN_NEG = 0
const ubyte UN_NOT = 1
const ubyte UN_INV = 2

; op-stack record kinds (markers >= OPK_LPAREN)
const ubyte OPK_BINOP  = 0
const ubyte OPK_UNOP   = 1
const ubyte OPK_LPAREN = 2
const ubyte OPK_MEMAT  = 3
const ubyte OPK_CALL   = 4
const ubyte OPK_LBRACK = 5

const ubyte UNARY_PREC = 110

; frame kinds
const ubyte FR_ROOT   = 0
const ubyte FR_THEN   = 1
const ubyte FR_ELSE   = 2
const ubyte FR_WHILE  = 3
const ubyte FR_FOR    = 4
const ubyte FR_REPEAT = 5
const ubyte FR_WHEN   = 6
const ubyte FR_CHOICE = 7

; ---- module state ----
ubyte src_hand
ubyte dst_hand
ubyte peek_buf
ubyte peek_ok
ubyte src_eof

; streaming lexer: a 2-token lookahead window (tk0 = current, tk1 = next)
; instead of a whole-program token array, so arbitrarily large programs
; fit. next_raw_token() produces one token into ntok_*.

; identifier text pool (reset per top-level unit while streaming)
const uword ident_pool = $a9e8
uword ident_pool_len

; string literal pool (null-terminated; a string's id is its start offset)
const uword str_pool = $beb0
uword str_pool_len

ubyte[64] name_buf


; node arena
const uword node_kind = $ccf0
const uword node_op = $ce26
const uword node_a = $cf5c
const uword node_b = $d1c8
const uword node_c = $d434
const uword node_d = $d6a0
uword node_count

; expression stacks

; cons cells
uword[232] cons_val
uword[232] cons_next
uword cons_count

; statement frame stack

; program structure
uword prog_address
ubyte prog_target        ; 0=wendy2c, 1=nmos
uword prog_imports       ; cons of ident ids (reversed)
uword prog_vars          ; cons of vardecl node ids (reversed)
uword prog_enums         ; cons of enum node ids (reversed)
uword prog_structs       ; cons of struct node ids (reversed)
uword prog_subs          ; cons of sub node ids (reversed)

; ---- codegen symbol table (persistent across passes) ----
const uword sym_ident = $d90c      ; var name ident id
const uword sym_type = $dc94       ; type tag (TY_UBYTE / TY_BYTE / TY_UWORD)
const uword sym_addr = $de58       ; ZP address
const uword sym_scope = $e1e0      ; owning sub name ident (0 = module scope)
const uword sym_mkind = $e568      ; 0 = module var, 1 = param, 2 = local
const uword sym_is_const = $e72c   ; 1 = compile-time const (no storage); folded
const uword sym_cval = $e8f0       ; const value (when sym_is_const)
const uword sym_arr_size = $ec78   ; element count if an array (0 = scalar); the
                         ; element type is in sym_type; mangle is p8a_
uword sym_count
uword zp_next            ; ZP bump allocator (from $40)
uword cur_scope          ; the sub being codegen'd (for var resolution)
uword cg_arr_si          ; fast-path array sym index, parked across the
                         ; recursive byte-index codegen (see emit_byte_leaf_load)
; call-arg scratch (push args -> pop into param slots before the jsr).
uword[16] call_slot      ; param sym index per arg
ubyte[16] call_isw       ; 1 if that arg/param is uword
ubyte call_n
; register-ABI asmsub call scratch (captured before evaluating args, since the
; args are loaded out of source order: X/Y first, A/AY last).
uword[8] rb_arg          ; arg expr node per param (source order)
ubyte[8] rb_reg          ; param register code (1=A 2=X 3=Y 4=AY)
ubyte[8] rb_isw          ; 1 if uword param
; codegen_call's locals (callee/callnode) live in static ZP, so a nested call
; arg (e.g. out_byte(lsb(x))) would clobber them; save them on this stack
; across each arg evaluation. call_slot/call_n are re-derived (collect_params)
; after the args, so they need no saving.
uword[16] ccs_callee
uword[16] ccs_node
ubyte[16] ccs_j
ubyte ccs_sp
; emit_cond_branch is de-recursed onto this explicit task stack (reusing the
; arrays the old reentrancy frame used -- no extra RAM). Per entry: cb_cond =
; condition node; cb_tkind = target/label kind; cb_tid = target/label id;
; cb_skip = task discriminator (0 = eval node jit 0, 1 = eval node jit 1,
; 2 = emit a skip label).
uword[16] cb_cond
ubyte[16] cb_tkind
uword[16] cb_tid
uword[16] cb_skip
ubyte cb_sp
; sub table (registered in source order before codegen, so calls
; resolve and pass B emits non-main subs in p8c's order).
uword[222] sub_name       ; sub name ident id
ubyte[222] sub_kind       ; SUBK_SUB / MAIN / INLINE / ASMSUB / ASMSUB_BODY
ubyte[222] sub_ret        ; return type tag
uword[222] sub_addr       ; asmsub target address ($F0xx); else 0
uword sub_count
uword entry_nm           ; name id of the entry sub (the SUBK_MAIN one: `start`
                         ; in a `main { ... sub start() }` block, else `main`)
; builtin-call node stack: emit_builtin is non-reentrant (static
; locals), but a builtin arg may itself be a builtin, so the callnode
; is stacked and args re-derived after each nested codegen.
uword[8] bi_cn
ubyte bi_sp
; saved folded base for emit_addr_into_aptr across its re-entrant
; codegen_word_expr call (locals are static, so a nested peekw would clobber it).
uword[8] eai_base
ubyte eai_sp
; word-context call widening flag stack (word_dispatch is re-entered
; by a ubyte-returning call's own arg eval, clobbering its locals).
ubyte[8] wdn_stack
ubyte wdn_sp
; explicit operand stack for expr_is_word's iterative OR-walk (de-recursed:
; an arith/bitwise/shift binop is word if EITHER operand is word).
uword[24] eiw_stk
ubyte eiw_sp
; the sub currently being codegen'd -- its return type + name ident,
; for `return` (the per-sub .Lp8s_<name>_ret label).
ubyte cur_ret            ; current sub's return type tag
uword cur_ret_name       ; current sub's name ident id
; string pool: one label per string-literal *occurrence*, numbered
; in codegen encounter order (matching p8c's sema-walk order); the
; recorded str id indexes the parser's str_pool for the trailer.
uword[256] strpool_sid    ; str id for label N (p8c_str_N)
uword strpool_count
; byte-expression codegen work stack (replaces p8c's recursion):
; per entry a task -- 0 eval node, 1 binop-leaf, 2 pha, 3 sta tmp1,
; 4 pla, 5 binop-tmp1.
ubyte[16] cws_type
uword[16] cws_node
ubyte[16] cws_op
ubyte cws_sp
; word-expression codegen work stack (separate from the byte stack so
; a byte expression's @() address can drive a word eval without
; corrupting the byte stack -- the two never share state).
ubyte[16] wws_type
uword[16] wws_node
ubyte[16] wws_op
ubyte wws_sp
; statement work stack (control flow without recursion): a task is
; 0=emit stmt node, 1=emit label .L<kind>_<id>:, 2=emit jmp to it,
; 3=pop the loop-label stack.
ubyte[48] sws_type
uword[48] sws_a
uword[48] sws_b
ubyte sws_sp
; loop-label stack for break/continue (break -> bk kind/id, continue
; -> ck kind/id), pushed per loop.
ubyte[16] lp_bk
uword[16] lp_bi
ubyte[16] lp_ck
uword[16] lp_ci
ubyte lp_sp
; short-circuit and/or label stack: a label-id pair is allocated mid-
; evaluation (after the lhs) and consumed by the tail (after the rhs);
; LIFO nesting matches the work-stack task order.
uword[32] lstk_id1
uword[32] lstk_id2
ubyte lstk_sp
; codegen scratch flags/counters (reset before pass M):
ubyte mul_used           ; `*` was emitted -> emit __p8c_mul_u8 trailer
ubyte strcmp_used        ; strings.compare used -> emit __p8c_strcmp trailer
uword label_seq          ; global local-label counter (p8c's _label_id)

uword[2] sub_snode
uword resident_sym_count
uword rec_kind
uword rec_snode
; serializer work stack

uword dec_v
ubyte dec_started


; ---- syscall asmsubs (register ABI; emulator $F006+ stubs) ----
extsub $F00F = sys_exit(ubyte code @A)
extsub $F015 = sys_close(ubyte handle @A)

asmsub sys_argv(ubyte i @A) -> uword @AY {
    %asm {{
        jsr  $f01e
        pha
        txa
        tay
        pla
        rts
    }}
}

asmsub sys_open(uword filename @AY) -> ubyte @A {
    %asm {{
        pha
        tya
        tax
        pla
        jsr  $f012
        rts
    }}
}

asmsub sys_openout(uword filename @AY) -> ubyte @A {
    %asm {{
        pha
        tya
        tax
        pla
        jsr  $f021
        rts
    }}
}

; sys_read_raw returns A=byte, Y=EOF flag (Y!=0 => EOF). The prog8 wrapper
; sys_read sets src_eof from Y, so no asm body references the (per-compiler
; mangled) src_eof symbol -- one source form both compilers build.
asmsub sys_read_raw(ubyte handle @A) -> uword @AY {
    %asm {{
        jsr  $f018
        bcc  sys_read_ok
        lda  #0
        ldy  #1
        rts
        sys_read_ok:
        ldy  #0
        rts
    }}
}

sub sys_read(ubyte handle) -> ubyte {
    uword r
    r = sys_read_raw(handle)
    src_eof = msb(r)
    return lsb(r)
}

asmsub sys_write(ubyte b @A, ubyte handle @X) {
    %asm {{
        jsr  $f024
        rts
    }}
}

; ---- I/O (sticky-EOF; emulator rewinds on EOF) ----

sub read_src() -> ubyte {
    if peek_ok != 0 {
        peek_ok = 0
        return peek_buf
    }
    if src_eof != 0 {
        return 0
    }
    return sys_read(src_hand)
}

sub out_byte(ubyte b) {
    sys_write(b, dst_hand)
}

; ---- character classes ----

sub out_dec_place(uword p) {
    ubyte d
    d = 0
    repeat {
        if dec_v < p {
            break
        }
        dec_v = dec_v - p
        d = d + 1
    }
    if d != 0 {
        dec_started = 1
    }
    if dec_started != 0 {
        out_byte(d + $30)
    }
}

sub out_dec(uword v) {
    dec_v = v
    dec_started = 0
    out_dec_place(10000)
    out_dec_place(1000)
    out_dec_place(100)
    out_dec_place(10)
    out_byte(lsb(dec_v) + $30)
}

; ---- numeric scanners ----

sub ident_len_at(uword id) -> uword {
    uword n
    n = 0
    repeat {
        if peek($a9e8 + (id + n)) == 0 {
            break
        }
        n = n + 1
    }
    return n
}

; classify_name dispatches by length to a per-length helper. Splitting the
; keyword if-chains out of one big `when` keeps every sub's node count well
; under the per-unit node arena, so the self-host front-end (pass 1) can parse
; this file itself without overflowing. (Behaviour is identical; the helpers
; return TK_IDENT when no keyword matches, which classify_name passes through.)

sub new_node(ubyte kind, ubyte op, uword a, uword b) -> uword {
    uword id
    id = node_count
    poke($ccf0 + (id), kind)
    poke($ce26 + (id), op)
    pokew($cf5c + ((id) << 1), a)
    pokew($d1c8 + ((id) << 1), b)
    pokew($d434 + ((id) << 1), 0)
    pokew($d6a0 + ((id) << 1), 0)
    node_count = node_count + 1
    return id
}

; ---- cons cells ----

sub cons_prepend(uword head, uword val) -> uword {
    uword c
    c = cons_count
    cons_val[(c as ubyte)] = val
    cons_next[(c as ubyte)] = head
    cons_count = cons_count + 1
    return c
}

; ---- operator precedence ----

sub reset_source() {
    ; the emulator rewinds the input to offset 0 on EOF, so clearing the
    ; sticky-EOF / peek flags makes the next read start over from the top.
    peek_ok = 0
    src_eof = 0
}

; process one directive (cursor on the DIRECTIVE token), updating program
; header state.

sub out_text(uword p) {
    uword q
    q = p
    repeat {
        ubyte c
        c = @(q)
        if c == 0 {
            break
        }
        out_byte(c)
        q = q + 1
    }
}

sub out_hex2(ubyte v) {
    out_hex_nib(lsb(v >> 4))
    out_hex_nib(v)
}

sub out_hex4(uword v) {
    out_hex_nib(lsb(v >> 12))
    out_hex_nib(lsb(v >> 8))
    out_hex_nib(lsb(v >> 4))
    out_hex_nib(lsb(v))
}

sub out_hex_nib(ubyte n) {
    n = n & $0f
    if n >= $0a {
        out_byte(n + $57)
    } else {
        out_byte(n + $30)
    }
}

sub out_ident_text(uword id) {
    uword off
    uword n
    uword j
    off = id
    n = ident_len_at(id)
    j = 0
    repeat {
        if j >= n {
            break
        }
        out_byte(peek($a9e8 + (off + j)))
        j = j + 1
    }
}
; emit a symbol's mangled name from its table entry: module -> p8v_<name>,
; param -> p8v_<sub>_arg_<name>, local -> p8v_<sub>_<name>.

sub emit_sym_mangled(uword si) {
    ; arrays live in main memory under a p8a_ label; everything else is p8v_.
    if peekw($ec78 + ((si) << 1)) != 0 {
        out_text("p8a_")
        out_ident_text(peekw($d90c + ((si) << 1)))
        return
    }
    out_text("p8v_")
    if peek($e568 + (si)) == 0 {
        out_ident_text(peekw($d90c + ((si) << 1)))
        return
    }
    out_ident_text(peekw($e1e0 + ((si) << 1)))
    if peek($e568 + (si)) == 1 {
        out_text("_arg_")
    } else {
        out_byte('_')
    }
    out_ident_text(peekw($d90c + ((si) << 1)))
}
; emit a var reference by ident, resolved in the current scope.

sub emit_mangled(uword identid) {
    emit_sym_mangled(find_sym(identid))
}

; shared instruction-prefix fragments (leading 2-space indent included)

sub o_nl()    { out_byte('\n') }
sub o_ldy0()  { out_text("  ldy #$00") o_nl() }
sub o_ldy1()  { out_text("  ldy #$01") o_nl() }
sub o_aptr_ld() { out_text("  lda (__p8c_aptr),y") o_nl() }
sub o_aptr_st() { out_text("  sta (__p8c_aptr),y") o_nl() }

sub o_lda()   { out_text("  lda ") }

sub o_ldy()   { out_text("  ldy ") }

sub o_sta()   { out_text("  sta ") }

sub o_sty()   { out_text("  sty ") }

sub o_imm()   { out_text("#$") }

sub o_plus1() { out_text("+1") }
; common single-instruction emitters (a 3-byte jsr beats an 8-byte out_text
; call at each of the many sites that push/pop or shuffle A/Y).

sub o_pha()   { out_text("  pha") o_nl() }

sub o_pla()   { out_text("  pla") o_nl() }

sub o_tay()   { out_text("  tay") o_nl() }

sub o_tya()   { out_text("  tya") o_nl() }

sub o_clc()   { out_text("  clc") o_nl() }

sub o_sec()   { out_text("  sec") o_nl() }

sub o_sta_wtmp0() { out_text("  sta __p8c_wtmp0") o_nl() }

sub o_lda_wtmp0() { out_text("  lda __p8c_wtmp0") o_nl() }

sub o_sty_wtmp0h() { out_text("  sty __p8c_wtmp0+1") o_nl() }

sub o_sta_tmp0()  { out_text("  sta __p8c_tmp0") o_nl() }

sub o_lda_tmp0()  { out_text("  lda __p8c_tmp0") o_nl() }

sub o_sta_tmp1()  { out_text("  sta __p8c_tmp1") o_nl() }

sub o_lda_imm0()  { out_text("  lda #$00") o_nl() }

sub o_lda_imm1()  { out_text("  lda #$01") o_nl() }

sub o_eor_ff()    { out_text("  eor #$ff") o_nl() }

sub o_tax()       { out_text("  tax") o_nl() }

sub o_txa()       { out_text("  txa") o_nl() }

sub o_ror_wtmp0() { out_text("  ror __p8c_wtmp0") o_nl() }

sub o_ldy_wtmp0h(){ out_text("  ldy __p8c_wtmp0+1") o_nl() }

; in-place list reversal (flips next pointers, allocates no cons cells). Safe
; in codegen where each arg/value list is reversed exactly once and not read
; again -- avoids growing cons_count past the per-record load during emission
; of call-heavy subs (which would overflow the cons arena into the sym table).
sub reverse_cons_ip(uword head) -> uword {
    uword prev
    prev = 0
    uword cell
    cell = head
    repeat {
        if cell == 0 {
            break
        }
        uword nxt
        nxt = cons_next[(cell as ubyte)]
        cons_next[(cell as ubyte)] = prev
        prev = cell
        cell = nxt
    }
    return prev
}

; ---- pass S: the symbol table -------------------------------
; A persistent (across passes) struct-of-arrays mapping a module var's
; ident id to its type tag + ZP address. Built from prog_vars right after
; pass A, BEFORE the arena is reset for pass M -- so the ident ids stay
; valid (the ident pool persists; pass M re-lexes the same names and
; intern_name dedups them to the same ids).
; resolve a var: the current sub's param/local (shadows) first, else module.

sub find_sym(uword identid) -> uword {
    uword i
    i = 0
    repeat {
        if i >= sym_count {
            break
        }
        if peekw($d90c + ((i) << 1)) == identid {
            if peekw($e1e0 + ((i) << 1)) == cur_scope {
                return i
            }
        }
        i = i + 1
    }
    i = 0
    repeat {
        if i >= sym_count {
            break
        }
        if peekw($d90c + ((i) << 1)) == identid {
            if peekw($e1e0 + ((i) << 1)) == 0 {
                return i
            }
        }
        i = i + 1
    }
    return $ffff
}
; A compile-time const folds to its literal value at every use site (p8c does
; this in its Ident codegen; p1 mirrors it). ident_is_const tells a use site to
; emit an immediate; ident_const_val gives the value.

sub ident_is_const(uword identid) -> ubyte {
    uword si
    si = find_sym(identid)
    if si == $ffff {
        return 0
    }
    return peek($e72c + (si))
}

sub ident_const_val(uword identid) -> uword {
    return peekw($e8f0 + ((find_sym(identid)) << 1))
}
; allocate ZP for every scalar module var, in declaration order, exactly
; as p8c's sema does (bump from $40; ubyte/byte = 1 byte, uword = 2).

sub emit_prologue() {
    out_text("; ---- generated by p8c -- DO NOT EDIT ----\n; source: SRC\n; target: nmos (vasm builds a self-contained 6502 binary, reset vector\n;               at $FFFC points to p8s_main; intended for the emulator'")
    out_text("s\n;               nmos-default machine with file-I/O stubs at $F006-$F03C).\n\n__p8c_tmp0 = $20                     ; codegen scratch (byte)\n__p8c_tmp1 = $21                     ; codegen scratch (byte)")
    out_text("\n__p8c_wtmp0 = $22                   ; codegen scratch (word)\n__p8c_wtmp1 = $24                   ; codegen scratch (word)\n__p8c_ptr0  = $26                    ; indirect-Y pointer (2 bytes)\n__p8c_apt")
    out_text("r  = $28                    ; array element pointer (2 bytes)\n\n  .org $")
    out_hex4(prog_address)
    out_text("\n  jmp ") emit_sub_label(entry_nm) o_nl()
}

; Emit the `; ---- ZP variable allocations ----` block + one
; `p8v_<name> = $XX` line per ZP scalar. Leading blank line, no trailing
; blank -- emit_main's leading "\n\n" supplies the two-blank gap. (Empty
; when there are no module vars, matching p8c.)

sub emit_main(uword body) {
    out_text("\n\n; ---- sub ") out_ident_text(entry_nm) out_text(" ----\n")
    emit_sub_label(entry_nm) out_text(":\n")
    codegen_body(body)
    out_text(".L") emit_sub_label(entry_nm)
    out_text("_ret:\n  lda #$00\n  jsr $f00f\n  brk\n")
}

sub emit_trailers() {
    out_text("\n  ; ---- reset vector ----\n  .org $FFFC\n  .word ") emit_sub_label(entry_nm)
    out_text("\n  .word $0000\n\n")
}

; emit the `; ---- arrays ----` storage block: one `p8a_<name>:` label + a
; `.byte 0, 0, ...` reservation (count*esize zero bytes) per module array, in
; source order. Goes between the mul helper and the string pool (matching p8c).
; Empty -> nothing (not even the header).

sub emit_array_zeros(uword count) {
    out_text("  .byte ")
    uword b
    b = 0
    repeat {
        if b >= count {
            break
        }
        if b != 0 {
            out_text(", ")
        }
        out_byte('0')
        b = b + 1
    }
    o_nl()
}

; ---- data-initialized array tables (loaded from the dump's array section) ----
uword[8] ai_sym
ubyte[8] ai_isstr
uword[8] ai_n
uword[8] ai_off
uword[64] ai_vals
uword ai_count

; ai_* index for sym `symidx`, +1; 0 if the array has no data initializer.
sub ai_find(uword symidx) -> uword {
    uword i
    i = 0
    repeat {
        if i >= ai_count { break }
        if ai_sym[(i as ubyte)] == symidx { return i + 1 }
        i = i + 1
    }
    return 0
}

; emit one `.byte` storage row of a data-init array. mode 0 = ubyte (`v`),
; 1 = uword lo (`<v`), 2 = uword hi (`>v`); v is a decimal int value, or
; p8c_str_N for a string element.
sub emit_array_init(uword ai, ubyte mode) {
    out_text("  .byte ")
    uword off
    off = ai_off[(ai as ubyte)]
    uword n
    n = ai_n[(ai as ubyte)]
    ubyte isstr
    isstr = ai_isstr[(ai as ubyte)]
    uword j
    j = 0
    repeat {
        if j >= n { break }
        if j != 0 { out_text(", ") }
        if mode == 1 { out_byte('<') }
        if mode == 2 { out_byte('>') }
        uword v
        v = ai_vals[((off + j) as ubyte)]
        if isstr != 0 {
            out_text("p8c_str_")
            out_dec(intern_str_label(v))
        } else {
            out_dec(v)
        }
        j = j + 1
    }
    o_nl()
}

sub emit_arrays() {
    ubyte any
    any = 0
    uword j
    j = 0
    repeat {
        if j >= sym_count {
            break
        }
        if peekw($ec78 + ((j) << 1)) != 0 {
            any = 1
            break
        }
        j = j + 1
    }
    if any == 0 {
        return
    }
    out_byte('\n')
    out_text("; ---- arrays ----")
    o_nl()
    uword i
    i = 0
    repeat {
        if i >= sym_count {
            break
        }
        if peekw($ec78 + ((i) << 1)) != 0 {
            uword count
            count = peekw($ec78 + ((i) << 1))
            uword ai
            ai = ai_find(i)
            if peek($dc94 + (i)) == TY_UWORD {
                ; split lo/hi byte storage (upstream @split model)
                emit_sym_mangled(i)
                out_text("_lo:")
                o_nl()
                if ai != 0 { emit_array_init(ai - 1, 1) } else { emit_array_zeros(count) }
                emit_sym_mangled(i)
                out_text("_hi:")
                o_nl()
                if ai != 0 { emit_array_init(ai - 1, 2) } else { emit_array_zeros(count) }
            } else {
                emit_sym_mangled(i)
                out_byte(':')
                o_nl()
                if ai != 0 { emit_array_init(ai - 1, 0) } else { emit_array_zeros(count) }
            }
        }
        i = i + 1
    }
}

; the ubyte*ubyte helper, emitted only when `*` codegen set mul_used. Goes
; between the last sub and the string pool (matching p8c's tail order).

sub emit_mul_helper() {
    if mul_used == 0 {
        return
    }
    out_text("\n; ---- runtime: ubyte * ubyte -> A ----\n__p8c_mul_u8:\n  lda #0\n  ldx #8\n.__mul_loop:\n  lsr __p8c_tmp1\n  bcc .__mul_skip\n  clc\n  adc __p8c_tmp0\n.__mul_skip:\n  asl __p8c_tmp0\n  dex\n  bne .__mul_loop\n  rts\n")
}

; the strings.compare helper (port of p8c's _strcmp_used trailer). Goes between
; the mul helper and the arrays block, matching p8c's emission order.
sub emit_strcmp_helper() {
    if strcmp_used == 0 {
        return
    }
    out_text("\n__p8c_strcmp:\n  ldy #0\n.__sc_loop:\n  lda (__p8c_wtmp0),y\n  cmp (__p8c_wtmp1),y\n  bne .__sc_diff\n  lda (__p8c_wtmp0),y\n  beq .__sc_eq\n  iny\n  bne .__sc_loop\n.__sc_eq:\n  lda #0\n  rts\n.__sc_diff:\n  bcc .__sc_less\n  lda #1\n  rts\n.__sc_less:\n  lda #$ff\n  rts\n")
}

; ---- string pool trailer (port of p8c/codegen.py::_escape) ----
; A "plain" char goes inside a "..." run; everything else (control chars,
; `"`, `\`) is emitted as $XX; parts are joined by ", "; an empty string
; emits the single part "0".

sub str_char_plain(ubyte c) -> ubyte {
    if c < ' ' {
        return 0
    }
    if c >= $7f {                    ; DEL and above: not printable
        return 0
    }
    if c == '"' {
        return 0
    }
    if c == '\\' {
        return 0
    }
    return 1
}

; length of the null-terminated string at pool offset `off`.
sub str_len_at(uword off) -> uword {
    uword n
    n = 0
    repeat {
        if peek($beb0 + (off + n)) == 0 { break }
        n = n + 1
    }
    return n
}

sub emit_string_byte_list(uword sid) {
    uword off
    uword n
    off = sid
    n = str_len_at(sid)
    ubyte in_run        ; inside an open "..." run
    ubyte any           ; emitted at least one part (need ", " before next)
    in_run = 0
    any = 0
    uword j
    j = 0
    repeat {
        if j >= n {
            break
        }
        ubyte c
        c = peek($beb0 + (off + j))
        if str_char_plain(c) != 0 {
            if in_run == 0 {
                if any != 0 {
                    out_text(", ")
                }
                out_byte('"')           ; open "
                in_run = 1
                any = 1
            }
            out_byte(c)
        } else {
            if in_run != 0 {
                out_byte('"')           ; close "
                in_run = 0
            }
            if any != 0 {
                out_text(", ")
            }
            out_byte('$')               ; $
            out_hex2(c)
            any = 1
        }
        j = j + 1
    }
    if in_run != 0 {
        out_byte('"')
    }
    if any == 0 {
        out_byte('0')                   ; "0" for the empty string
    }
}
; two string-pool ids are equal iff same length and same bytes.

sub str_sid_equal(uword a, uword b) -> ubyte {
    repeat {
        ubyte ca
        ubyte cb
        ca = peek($beb0 + (a))
        cb = peek($beb0 + (b))
        if ca != cb {
            return 0
        }
        if ca == 0 {
            return 1
        }
        a = a + 1
        b = b + 1
    }
}
; intern a string id into the pool, returning its p8c_str_N label number.
; Identical string content reuses an existing label (matches p8c's value
; dedup), so the pool holds each distinct string once.

sub intern_str_label(uword sid) -> uword {
    uword di
    di = 0
    repeat {
        if di >= strpool_count {
            break
        }
        if str_sid_equal(strpool_sid[(di as ubyte)], sid) != 0 {
            return di
        }
        di = di + 1
    }
    strpool_sid[(strpool_count as ubyte)] = sid
    di = strpool_count
    strpool_count = strpool_count + 1
    return di
}
; emit `; ---- string pool ----` + one `p8c_str_N:` / `.byte ..., 0` per
; label, in encounter order. Goes between the last sub and the reset vector
; (matching p8c). Empty -> nothing.

sub emit_string_pool() {
    if strpool_count == 0 {
        return
    }
    out_byte('\n')
    out_text("; ---- string pool ----")
    o_nl()
    ; park the read-only pool above the emulator's I/O stub routines (~$F0B0)
    ; and below its argv window / ports, freeing the low $0200..$F006 window
    ; for code + arenas. p1 only targets nmos, so this is unconditional.
    out_text("  .org $F0C0")
    o_nl()
    uword i
    i = 0
    repeat {
        if i >= strpool_count {
            break
        }
        out_text("p8c_str_")
        out_dec(i)
        out_byte(':')                   ; :
        o_nl()
        out_text("  .byte ")
        emit_string_byte_list(strpool_sid[(i as ubyte)])
        out_text(", 0")
        o_nl()
        i = i + 1
    }
}

; ---- control-flow labels + long branches -------------------
; control label kinds: 0 else, 1 endif, 2 while_top, 3 while_end,
; 4 for_top, 5 for_cont, 6 for_end, 7 rep_top, 8 rep_dec, 9 rep_end,
; 10 rep_break.

uword[] ctrl_label_strs = [
    ".Lelse_", ".Lendif_", ".Lwhile_top_", ".Lwhile_end_", ".Lfor_top_",
    ".Lfor_cont_", ".Lfor_end_", ".Lrep_top_", ".Lrep_dec_", ".Lrep_end_",
    ".Lrep_break_", ".Lwhen_end_", ".Lwhen_body_", ".Lwhen_next_",
    ".Lwhen_skip_", ".Land_skip_", ".Lor_skip_" ]
sub emit_ctrl_label_ref(ubyte kind, uword id) {
    out_text(ctrl_label_strs[(kind as ubyte)])
    out_dec(id)
}
; branch mnemonics by code: 0 bne 1 beq 2 bcc 3 bcs 4 bmi 5 bpl 6 bvc 7 bvs.

uword[] br_mnems = ["bne", "beq", "bcc", "bcs", "bmi", "bpl", "bvc", "bvs"]
sub out_br_mnem(ubyte code) {
    out_text(br_mnems[(code as ubyte)])
}
; _br: branch to a (possibly distant) control label when `brcode` is TRUE,
; via the inverted-branch + jmp pattern (works at any distance).

sub emit_br(ubyte brcode, ubyte tkind, uword tid) {
    ubyte inv
    inv = brcode ^ 1
    uword sk
    sk = label_seq
    label_seq = label_seq + 1
    out_text("  ")
    out_br_mnem(inv)
    out_text(" .Lbrs_")
    out_dec(sk)
    o_nl()
    out_text("  jmp ")
    emit_ctrl_label_ref(tkind, tid)
    o_nl()
    out_text(".Lbrs_")
    out_dec(sk)
    out_byte(':')
    o_nl()
}

; ---- condition codegen (branch to target if FALSE) ----------
; is this expression a uword (for the word-compare condition path)? Leaf
; idents resolve via the symbol table; &name is a uword. (Nested expr typing
; is a tracked gap, as in the byte comparison signedness.)

sub expr_is_word(uword e) -> ubyte {
    ; iterative OR-walk (no recursion): the expression is word-typed if the
    ; node itself is word, or -- for an arith/bitwise/shift binop -- if either
    ; operand is. Operands to still-visit are held on eiw_stk.
    eiw_sp = 0
    eiw_stk[eiw_sp] = e
    eiw_sp = eiw_sp + 1
    repeat {
        if eiw_sp == 0 {
            break
        }
        eiw_sp = eiw_sp - 1
        uword n
        n = eiw_stk[eiw_sp]
        if peek($ccf0 + (n)) == ND_CAST {
            ; (operand as TYPE): the cast's target type (node_op) decides.
            if peek($ce26 + (n)) == TY_UWORD {
                return 1
            }
        }
        if peek($ccf0 + (n)) == ND_ADDROF {
            return 1
        }
        if peek($ccf0 + (n)) == ND_CALL {
            ; a call's result type is its return type (peekw -> uword, peek/lsb ->
            ; ubyte). p8c types call operands this way for compares/widening.
            if call_returns_ubyte(n) == 0 {
                return 1
            }
        }
        if peek($ccf0 + (n)) == ND_IDENT {
            uword si
            si = find_sym(peekw($cf5c + ((n) << 1)))
            if si != $ffff {
                if peek($dc94 + (si)) == TY_UWORD {
                    return 1
                }
            }
        }
        if peek($ccf0 + (n)) == ND_INDEX {
            ; arr[i] has the array's element type; a uword[] element is a word.
            uword ai
            ai = find_sym(peekw($cf5c + ((peekw($cf5c + ((n) << 1))) << 1)))
            if ai != $ffff {
                if peek($dc94 + (ai)) == TY_UWORD {
                    return 1
                }
            }
        }
        if peek($ccf0 + (n)) == ND_BINOP {
            ; arith/bitwise/shift binop (TK_PLUS..TK_SHR) widens to word if either
            ; operand is word (e.g. zp_next + sz -> uword); comparison ops stay
            ; bool. Matches p8c's `result type is UWORD` typing of the condition.
            if peek($ce26 + (n)) >= TK_PLUS {
                if peek($ce26 + (n)) <= TK_SHR {
                    eiw_stk[eiw_sp] = peekw($cf5c + ((n) << 1))
                    eiw_sp = eiw_sp + 1
                    eiw_stk[eiw_sp] = peekw($d1c8 + ((n) << 1))
                    eiw_sp = eiw_sp + 1
                }
            }
        }
    }
    return 0
}
; the negated (branch-if-false) sequence for an UNSIGNED compare op.

sub emit_neg_unsigned(ubyte op, ubyte tkind, uword tid) {
    if op == TK_EQ { emit_br(0, tkind, tid) return }      ; bne
    if op == TK_NE { emit_br(1, tkind, tid) return }      ; beq
    if op == TK_LT { emit_br(3, tkind, tid) return }      ; bcs
    if op == TK_GE { emit_br(2, tkind, tid) return }      ; bcc
    if op == TK_GT {                                        ; beq + bcc
        emit_br(1, tkind, tid)
        emit_br(2, tkind, tid)
        return
    }
    ; TK_LE: beq <skip> (short); bcs target; skip:
    uword sk
    sk = label_seq
    label_seq = label_seq + 1
    out_text("  beq .Lle_skip_")
    out_dec(sk)
    o_nl()
    emit_br(3, tkind, tid)
    out_text(".Lle_skip_")
    out_dec(sk)
    out_byte(':')
    o_nl()
}
; the negated (branch-if-false) sequence for a SIGNED compare op (after the
; overflow-corrected SBC has set N/Z).

; evaluate `cond` as bool and branch to the control label (tkind,tid) if it
; is FALSE. Comparison conditions emit the compare straight into the branch
; (no 0/1 materialized); anything else evaluates to A and branches on zero.

; the positive (branch-if-TRUE) sequence for an UNSIGNED compare op.
sub emit_pos_unsigned(ubyte op, ubyte tkind, uword tid) {
    if op == TK_EQ { emit_br(1, tkind, tid) return }      ; beq
    if op == TK_NE { emit_br(0, tkind, tid) return }      ; bne
    if op == TK_LT { emit_br(2, tkind, tid) return }      ; bcc
    if op == TK_GE { emit_br(3, tkind, tid) return }      ; bcs
    if op == TK_GT {                                        ; beq <skip>; bcs target; skip:
        uword sk
        sk = label_seq
        label_seq = label_seq + 1
        out_text("  beq .Lgt_no_")
        out_dec(sk)
        o_nl()
        emit_br(3, tkind, tid)
        out_text(".Lgt_no_")
        out_dec(sk)
        out_byte(':')
        o_nl()
        return
    }
    ; TK_LE: beq target; bcc target
    emit_br(1, tkind, tid)
    emit_br(2, tkind, tid)
}
sub emit_cmp_u(ubyte op, ubyte tkind, uword tid, ubyte jit) {
    if jit != 0 { emit_pos_unsigned(op, tkind, tid) } else { emit_neg_unsigned(op, tkind, tid) }
}

; compare cond.lhs vs cond.rhs and branch to (tkind,tid) on the wanted truth
; value (jit), without materializing a 0/1 byte. Port of p8c _emit_cmp_cond.
; (p1.p8 has only ubyte/uword -- no signed types -- so the signed compare arm
; of p8c is omitted here.)
sub emit_cmp_cond(uword cond, ubyte tkind, uword tid, ubyte jit) {
    ubyte op
    op = peek($ce26 + (cond))
    uword lhs
    uword rhs
    lhs = peekw($cf5c + ((cond) << 1))
    rhs = peekw($d1c8 + ((cond) << 1))
    ubyte isw
    isw = 0
    if expr_is_word(lhs) != 0 { isw = 1 }
    if expr_is_word(rhs) != 0 { isw = 1 }
    if isw != 0 {
        ; 16-bit compare (always unsigned)
        codegen_word_expr(lhs)
        o_sta_wtmp0()
        o_sty_wtmp0h()
        codegen_word_expr(rhs)
        out_text("  sta __p8c_wtmp1")
        o_nl()
        out_text("  sty __p8c_wtmp1+1")
        o_nl()
        out_text("  lda __p8c_wtmp0+1")
        o_nl()
        out_text("  cmp __p8c_wtmp1+1")
        o_nl()
        uword wlo
        wlo = label_seq
        label_seq = label_seq + 1
        out_text("  bne .Lwcmp_lo_")
        out_dec(wlo)
        o_nl()
        o_lda_wtmp0()
        out_text("  cmp __p8c_wtmp1")
        o_nl()
        out_text(".Lwcmp_lo_")
        out_dec(wlo)
        out_byte(':')
        o_nl()
        emit_cmp_u(op, tkind, tid, jit)
        return
    }
    ; byte compare (unsigned only)
    if is_cmp_leaf_rhs(rhs) != 0 {
        ; leaf rhs (literal / var): no tmp0/tmp1 spill -- eval lhs into A and
        ; compare directly. (Matches p8c's _emit_cmp_cond.)
        codegen_byte_expr(lhs)
        out_text("  cmp ")
        emit_byte_operand(0, rhs)
        o_nl()
        emit_cmp_u(op, tkind, tid, jit)
        return
    }
    codegen_byte_expr(lhs)
    o_sta_tmp0()
    codegen_byte_expr(rhs)
    o_sta_tmp1()
    o_lda_tmp0()
    out_text("  cmp __p8c_tmp1")
    o_nl()
    emit_cmp_u(op, tkind, tid, jit)
}

sub cb_push(uword cond, ubyte kind, uword id, uword disc) {
    cb_cond[(cb_sp as ubyte)] = cond
    cb_tkind[(cb_sp as ubyte)] = kind
    cb_tid[(cb_sp as ubyte)] = id
    cb_skip[(cb_sp as ubyte)] = disc
    cb_sp = cb_sp + 1
}
; branch to (tkind,tid) when `cond` is (jit ? true : false). and/or/not are
; short-circuited per-operand (no 0/1 byte). Port of p8c _emit_cond_branch,
; de-recursed onto the cb_* task stack: disc 0/1 = evaluate a condition node
; with that polarity, disc 2 = emit a trailing skip label. The eval logic is
; in ecb_eval (kept a separate sub so neither overruns pass2's 256-node
; per-sub arena when the pipeline compiles its own source).
sub emit_cond_branch(uword cond, ubyte tkind, uword tid, ubyte jit) {
    cb_sp = 0
    uword jw
    jw = jit
    cb_push(cond, tkind, tid, jw)
    repeat {
        if cb_sp == 0 {
            break
        }
        cb_sp = cb_sp - 1
        uword c
        ubyte tk
        uword ti
        uword disc
        c = cb_cond[(cb_sp as ubyte)]
        tk = cb_tkind[(cb_sp as ubyte)]
        ti = cb_tid[(cb_sp as ubyte)]
        disc = cb_skip[(cb_sp as ubyte)]
        if disc == 2 {
            ; skip-label task: tk = label kind (15 and / 16 or), ti = label id.
            emit_ctrl_label_ref(tk, ti)
            out_byte(':')
            o_nl()
        } else {
            ecb_eval(c, tk, ti, lsb(disc))
        }
    }
}
; evaluate one condition node: push the branch tasks for it (no recursion).
sub ecb_eval(uword c, ubyte tk, uword ti, ubyte ji) {
    ubyte k
    uword skip
    k = peek($ccf0 + (c))
    if k == ND_UNOP {
        if peek($ce26 + (c)) == UN_NOT {
            ubyte nj
            nj = ji ^ 1
            uword njw
            njw = nj
            cb_push(peekw($cf5c + ((c) << 1)), tk, ti, njw)
            return
        }
    }
    if k == ND_BINOP {
        ubyte bop
        bop = peek($ce26 + (c))
        if bop == TK_KAND {
            if ji != 0 {
                ; jump iff both true: lhs false -> skip; else jump iff rhs true.
                skip = label_seq
                label_seq = label_seq + 1
                cb_push(0, 15, skip, 2)
                cb_push(peekw($d1c8 + ((c) << 1)), tk, ti, 1)
                cb_push(peekw($cf5c + ((c) << 1)), 15, skip, 0)
            } else {
                ; jump iff and is false: either operand false -> target.
                cb_push(peekw($d1c8 + ((c) << 1)), tk, ti, 0)
                cb_push(peekw($cf5c + ((c) << 1)), tk, ti, 0)
            }
            return
        }
        if bop == TK_KOR {
            if ji != 0 {
                ; jump iff either true.
                cb_push(peekw($d1c8 + ((c) << 1)), tk, ti, 1)
                cb_push(peekw($cf5c + ((c) << 1)), tk, ti, 1)
            } else {
                ; jump iff both false: lhs true -> skip; else jump iff rhs false.
                skip = label_seq
                label_seq = label_seq + 1
                cb_push(0, 16, skip, 2)
                cb_push(peekw($d1c8 + ((c) << 1)), tk, ti, 0)
                cb_push(peekw($cf5c + ((c) << 1)), 16, skip, 1)
            }
            return
        }
        if is_cmp_op(bop) != 0 {
            emit_cmp_cond(c, tk, ti, ji)
            return
        }
    }
    ; generic: evaluate to A and branch on (non)zero. A uword is true iff
    ; either byte is nonzero, so OR the two halves together first.
    if expr_is_word(c) != 0 {
        codegen_word_expr(c)
        out_text("  sty __p8c_tmp0")
        o_nl()
        out_text("  ora __p8c_tmp0")
        o_nl()
    } else {
        codegen_byte_expr(c)
    }
    if ji != 0 {
        emit_br(0, tk, ti)
    } else {
        emit_br(1, tk, ti)
    }
}

sub emit_cond_branch_if_false(uword cond, ubyte tkind, uword tid) {
    emit_cond_branch(cond, tkind, tid, 0)
}

; ---- statement codegen (work stack; control flow w/o recursion) ----

sub sws_push(ubyte ty, uword a, uword b) {
    sws_type[(sws_sp as ubyte)] = ty
    sws_a[(sws_sp as ubyte)] = a
    sws_b[(sws_sp as ubyte)] = b
    sws_sp = sws_sp + 1
}
; push a block's statements so they pop in source order. node_a[blk] is the
; reversed cons (last stmt first), so pushing it directly puts the first stmt
; on top.

sub push_block_stmts(uword blk) {
    if blk == 0 {
        return
    }
    uword cell
    cell = peekw($cf5c + ((blk) << 1))
    repeat {
        if cell == 0 {
            break
        }
        sws_push(0, cons_val[(cell as ubyte)], 0)
        cell = cons_next[(cell as ubyte)]
    }
}
; the statement-driver entry: emit a whole block (and everything nested) with
; no recursion.

sub codegen_body(uword body) {
    sws_sp = 0
    lp_sp = 0
    push_block_stmts(body)
    repeat {
        if sws_sp == 0 {
            break
        }
        sws_sp = sws_sp - 1
        ubyte ty
        uword a
        uword b
        ty = sws_type[(sws_sp as ubyte)]
        a = sws_a[(sws_sp as ubyte)]
        b = sws_b[(sws_sp as ubyte)]
        if ty == 0 {
            codegen_stmt(a)
        } else {
            if ty == 1 {
                emit_ctrl_label_ref(lsb(a), b)
                out_byte(':')
                o_nl()
            } else {
                if ty == 2 {
                    out_text("  jmp ")
                    emit_ctrl_label_ref(lsb(a), b)
                    o_nl()
                } else {
                    if ty == 3 {
                        lp_sp = lp_sp - 1
                    } else {
                        if ty == 5 {
                            emit_rep_tail(b)          ; counted-repeat tail
                        } else {
                            if ty == 6 {
                                emit_for_cont(a, b)   ; for cont/test/inc tail
                            } else {
                                emit_when_choice(a, b) ; ty == 7: a when arm
                            }
                        }
                    }
                }
            }
        }
    }
}

sub codegen_stmt(uword st) {
    ubyte k
    k = peek($ccf0 + (st))
    if k == ND_ASSIGN {
        codegen_assign(st)
        return
    }
    if k == ND_IF {
        codegen_if(st)
        return
    }
    if k == ND_WHILE {
        codegen_while(st)
        return
    }
    if k == ND_REPEAT {
        codegen_repeat(st)
        return
    }
    if k == ND_FOR {
        codegen_for(st)
        return
    }
    if k == ND_WHEN {
        codegen_when(st)
        return
    }
    if k == ND_BREAK {
        out_text("  jmp ")
        emit_ctrl_label_ref(lp_bk[(lp_sp - 1 as ubyte)], lp_bi[(lp_sp - 1 as ubyte)])
        o_nl()
        return
    }
    if k == ND_CONTINUE {
        out_text("  jmp ")
        emit_ctrl_label_ref(lp_ck[(lp_sp - 1 as ubyte)], lp_ci[(lp_sp - 1 as ubyte)])
        o_nl()
        return
    }
    if k == ND_EXPRSTMT {
        uword e
        e = peekw($cf5c + ((st) << 1))
        if peek($ccf0 + (e)) == ND_CALL {
            codegen_call(e)
        }
        return
    }
    if k == ND_RETURN {
        codegen_return(st)
        return
    }
    if k == ND_INLINEASM {
        codegen_inline_asm(st)
        return
    }
    if k == ND_VARDECL {
        ; a local declaration is storage only; an initializer lowers to a
        ; store. (p8c: UBYTE -> byte path, everything else -> word path.)
        uword init
        init = peekw($d1c8 + ((st) << 1))
        if init != 0 {
            uword si
            si = find_sym(peekw($cf5c + ((st) << 1)))
            if peek($dc94 + (si)) == TY_UBYTE {
                codegen_byte_expr(init)
                emit_sta_sym(si)
            } else {
                codegen_word_expr(init)
                emit_sta_sym(si)
                emit_sty_sym_hi(si)
            }
        }
        return
    }
    ; other statement kinds arrive at later milestones.
}

sub codegen_if(uword st) {
    uword cond
    uword thenb
    uword elseb
    uword endif_id
    cond = peekw($cf5c + ((st) << 1))
    thenb = peekw($d1c8 + ((st) << 1))
    elseb = peekw($d434 + ((st) << 1))
    if elseb != 0 {
        uword else_id
        else_id = label_seq
        label_seq = label_seq + 1
        endif_id = label_seq
        label_seq = label_seq + 1
        emit_cond_branch_if_false(cond, 0, else_id)
        sws_push(1, 1, endif_id)          ; endif label (bottom)
        push_block_stmts(elseb)
        sws_push(1, 0, else_id)           ; else label
        sws_push(2, 1, endif_id)          ; jmp endif
        push_block_stmts(thenb)           ; then stmts (top)
        return
    }
    endif_id = label_seq
    label_seq = label_seq + 1
    emit_cond_branch_if_false(cond, 1, endif_id)
    sws_push(1, 1, endif_id)
    push_block_stmts(thenb)
}

sub codegen_while(uword st) {
    uword cond
    uword body
    cond = peekw($cf5c + ((st) << 1))
    body = peekw($d1c8 + ((st) << 1))
    uword top_id
    uword end_id
    top_id = label_seq
    label_seq = label_seq + 1
    end_id = label_seq
    label_seq = label_seq + 1
    emit_ctrl_label_ref(2, top_id)
    out_byte(':')
    o_nl()
    lp_bk[(lp_sp as ubyte)] = 3
    lp_bi[(lp_sp as ubyte)] = end_id
    lp_ck[(lp_sp as ubyte)] = 2
    lp_ci[(lp_sp as ubyte)] = top_id
    lp_sp = lp_sp + 1
    emit_cond_branch_if_false(cond, 3, end_id)
    sws_push(3, 0, 0)                     ; pop loop stack (bottom)
    sws_push(1, 3, end_id)               ; while_end label
    sws_push(2, 2, top_id)               ; jmp while_top
    push_block_stmts(body)               ; body (top)
}
; `repeat` (port of _emit_repeat). Forever (count 0) is a plain top/jmp/end
; loop. Counted pushes the count on the CPU stack, decrements per iteration,
; exits at 0; break pops the saved counter first. The 4 counted labels are
; allocated sequentially (rep_top, rep_dec, rep_end, rep_break) so the tail
; recovers them from rep_top alone.

sub codegen_repeat(uword st) {
    uword count
    uword body
    count = peekw($cf5c + ((st) << 1))
    body = peekw($d1c8 + ((st) << 1))
    uword top_id
    uword end_id
    top_id = label_seq
    label_seq = label_seq + 1
    end_id = label_seq
    label_seq = label_seq + 1
    if count == 0 {
        ; forever: break -> rep_end, continue -> rep_top
        emit_ctrl_label_ref(7, top_id)
        out_byte(':')
        o_nl()
        lp_bk[(lp_sp as ubyte)] = 9
        lp_bi[(lp_sp as ubyte)] = end_id
        lp_ck[(lp_sp as ubyte)] = 7
        lp_ci[(lp_sp as ubyte)] = top_id
        lp_sp = lp_sp + 1
        sws_push(3, 0, 0)                 ; pop loop
        sws_push(1, 9, end_id)           ; rep_end label
        sws_push(2, 7, top_id)           ; jmp rep_top
        push_block_stmts(body)
        return
    }
    ; counted. top_id, end_id already allocated; allocate dec + break so the
    ; four are top, end, dec, break -- but the tail wants them sequential from
    ; rep_top. Re-derive: we use top_id (=N), dec=N+1, end=N+2, break=N+3.
    ; (Undo the end_id we took as N+1 and re-allocate in the canonical order.)
    label_seq = top_id + 1               ; rewind to just after rep_top
    uword dec_id
    uword break_id
    dec_id = label_seq
    label_seq = label_seq + 1
    end_id = label_seq
    label_seq = label_seq + 1
    break_id = label_seq
    label_seq = label_seq + 1
    codegen_byte_expr(count)
    o_pha()
    emit_ctrl_label_ref(7, top_id)
    out_byte(':')
    o_nl()
    lp_bk[(lp_sp as ubyte)] = 10                    ; break -> rep_break
    lp_bi[(lp_sp as ubyte)] = break_id
    lp_ck[(lp_sp as ubyte)] = 8                     ; continue -> rep_dec
    lp_ci[(lp_sp as ubyte)] = dec_id
    lp_sp = lp_sp + 1
    sws_push(3, 0, 0)                    ; pop loop
    sws_push(5, 0, top_id)              ; rep tail (dec/pla/.../break/end)
    push_block_stmts(body)
}
; counted-repeat tail: dec_id=top+1, end_id=top+2, break_id=top+3.

sub emit_rep_tail(uword top_id) {
    uword dec_id
    uword end_id
    uword break_id
    dec_id = top_id + 1
    end_id = top_id + 2
    break_id = top_id + 3
    emit_ctrl_label_ref(8, dec_id)
    out_byte(':')
    o_nl()
    o_pla()
    o_sec()
    out_text("  sbc #1")
    o_nl()
    emit_br(1, 9, end_id)               ; beq rep_end
    o_pha()
    out_text("  jmp ")
    emit_ctrl_label_ref(7, top_id)
    o_nl()
    emit_ctrl_label_ref(10, break_id)
    out_byte(':')
    o_nl()
    o_pla()
    emit_ctrl_label_ref(9, end_id)
    out_byte(':')
    o_nl()
}
; `for v in lo to hi` (inclusive, ubyte; port of _emit_for). The loop var must
; be pre-declared (it is already in the symbol table). Init v=lo; for_top:; body;
; for_cont:; compare v to hi, exit if equal; inc v; jmp for_top; for_end:.
; The 3 labels are allocated top, end, cont (matching p8c) so the deferred cont
; tail derives top=end-1, cont=end+1 from end_id.

sub codegen_for(uword st) {
    uword var
    uword lo
    uword body
    var = peekw($cf5c + ((st) << 1))
    lo = peekw($d1c8 + ((st) << 1))
    body = peekw($d6a0 + ((st) << 1))
    uword si
    si = find_sym(var)
    uword top_id
    uword end_id
    top_id = label_seq
    label_seq = label_seq + 1
    end_id = label_seq
    label_seq = label_seq + 1
    uword cont_id
    cont_id = label_seq
    label_seq = label_seq + 1
    ; init: v = lo
    codegen_byte_expr(lo)
    emit_sta_sym(si)
    ; for_top:
    emit_ctrl_label_ref(4, top_id)
    out_byte(':')
    o_nl()
    lp_bk[(lp_sp as ubyte)] = 6                     ; break -> for_end
    lp_bi[(lp_sp as ubyte)] = end_id
    lp_ck[(lp_sp as ubyte)] = 5                     ; continue -> for_cont
    lp_ci[(lp_sp as ubyte)] = cont_id
    lp_sp = lp_sp + 1
    sws_push(3, 0, 0)                    ; pop loop
    sws_push(1, 6, end_id)             ; for_end label
    sws_push(6, st, end_id)            ; cont/test/inc tail
    push_block_stmts(body)
}
; for-loop continue/test/increment tail. labels: top=end-1, cont=end+1.

sub emit_for_cont(uword st, uword end_id) {
    uword top_id
    uword cont_id
    top_id = end_id - 1
    cont_id = end_id + 1
    uword si
    si = find_sym(peekw($cf5c + ((st) << 1)))
    uword hi
    hi = peekw($d434 + ((st) << 1))
    emit_ctrl_label_ref(5, cont_id)
    out_byte(':')
    o_nl()
    out_text("  lda ")
    emit_mangled(peekw($cf5c + ((st) << 1)))
    o_nl()
    if peek($ccf0 + (hi)) == ND_INT {
        out_text("  cmp #$")
        out_hex2(lsb(peekw($cf5c + ((hi) << 1))))
        o_nl()
    } else {
        if peek($ccf0 + (hi)) == ND_IDENT {
            out_text("  cmp ")
            emit_mangled(peekw($cf5c + ((hi) << 1)))
            o_nl()
        } else {
            o_sta_tmp0()
            codegen_byte_expr(hi)
            o_sta_tmp1()
            o_lda_tmp0()
            out_text("  cmp __p8c_tmp1")
            o_nl()
        }
    }
    emit_br(1, 6, end_id)               ; beq for_end
    out_text("  inc ")
    emit_mangled(peekw($cf5c + ((st) << 1)))
    o_nl()
    out_text("  jmp ")
    emit_ctrl_label_ref(4, top_id)
    o_nl()
}
; `when` (port of _emit_when): when expr, a list of value-arms and an optional
; else arm. The expr is evaluated once (byte -> __p8c_tmp0, word -> __p8c_wtmp0);
; each arm compares
; its value(s) and jumps to its body on a match, else to the next arm. Each arm
; is a deferred sws task (ty 7) so its body (a nested block) and trailers
; interleave per-arm exactly as p8c emits them. is_word is packed into the high
; bit of the task's end_id field (whens may nest; a global would be clobbered).

sub codegen_when(uword st) {
    uword endw_id
    endw_id = label_seq
    label_seq = label_seq + 1
    uword expr
    expr = peekw($cf5c + ((st) << 1))
    ubyte isw
    isw = expr_is_word(expr)
    if isw != 0 {
        codegen_word_expr(expr)
        o_sta_wtmp0()
        o_sty_wtmp0h()
    } else {
        codegen_byte_expr(expr)
        o_sta_tmp0()
    }
    uword packed
    packed = endw_id
    if isw != 0 {
        packed = endw_id | $8000
    }
    ; end label (bottom), then choices. node_b[st] is the reversed cons (last
    ; arm first); pushing it directly pops the arms in source order.
    sws_push(1, 11, endw_id)            ; when_end label
    uword cell
    cell = peekw($d1c8 + ((st) << 1))
    repeat {
        if cell == 0 {
            break
        }
        sws_push(7, cons_val[(cell as ubyte)], packed)
        cell = cons_next[(cell as ubyte)]
    }
}
; emit one when arm. Allocates body+next labels (always, even for else, to
; match p8c's label numbering); emits the value matches immediately, then
; defers the body + trailers.

sub emit_when_choice(uword choice, uword packed) {
    ubyte isw
    uword endw_id
    isw = 0
    endw_id = packed
    if (packed & $8000) != 0 {
        isw = 1
        endw_id = packed & $7fff
    }
    uword body_id
    uword next_id
    body_id = label_seq
    label_seq = label_seq + 1
    next_id = label_seq
    label_seq = label_seq + 1
    uword values
    uword body
    values = peekw($cf5c + ((choice) << 1))
    body = peekw($d1c8 + ((choice) << 1))
    if values == 0 {
        ; else arm: body, jmp when_end (no next label).
        sws_push(2, 11, endw_id)        ; jmp when_end
        push_block_stmts(body)
        return
    }
    ; value matches (source order -> reverse the cons).
    uword head
    head = reverse_cons_ip(values)
    uword cell
    cell = head
    repeat {
        if cell == 0 {
            break
        }
        uword v
        v = cons_val[(cell as ubyte)]
        if isw != 0 {
            codegen_word_expr(v)
            out_text("  sta __p8c_wtmp1")
            o_nl()
            out_text("  sty __p8c_wtmp1+1")
            o_nl()
            out_text("  lda __p8c_wtmp0+1")
            o_nl()
            out_text("  cmp __p8c_wtmp1+1")
            o_nl()
            uword skip_id
            skip_id = label_seq
            label_seq = label_seq + 1
            emit_br(0, 14, skip_id)     ; bne when_skip
            o_lda_wtmp0()
            out_text("  cmp __p8c_wtmp1")
            o_nl()
            emit_br(1, 12, body_id)     ; beq when_body
            emit_ctrl_label_ref(14, skip_id)
            out_byte(':')
            o_nl()
        } else {
            codegen_byte_expr(v)
            out_text("  cmp __p8c_tmp0")
            o_nl()
            emit_br(1, 12, body_id)     ; beq when_body
        }
        cell = cons_next[(cell as ubyte)]
    }
    out_text("  jmp ")
    emit_ctrl_label_ref(13, next_id)    ; jmp when_next
    o_nl()
    emit_ctrl_label_ref(12, body_id)    ; when_body:
    out_byte(':')
    o_nl()
    ; deferred: body stmts, jmp when_end, when_next label.
    sws_push(1, 13, next_id)            ; when_next label (bottom)
    sws_push(2, 11, endw_id)           ; jmp when_end
    push_block_stmts(body)             ; body (top)
}

; ---- byte expression codegen (work-stack; no recursion) -----
; p8c's _emit_byte_expr_into_a recurses on operands; p1 can't recurse, so
; the tree walk runs on an explicit work stack of tasks (cws_*). The
; leaf-RHS fast path (left-nested chains like a+b+c) needs no spill; a
; non-leaf RHS holds the LHS on the CPU stack across the RHS's evaluation
; (-> __p8c_tmp1), matching the host's dual-scratch-safe sequence.

sub cws_push(ubyte ty, uword nd, ubyte op) {
    cws_type[(cws_sp as ubyte)] = ty
    cws_node[(cws_sp as ubyte)] = nd
    cws_op[(cws_sp as ubyte)] = op
    cws_sp = cws_sp + 1
}
; a binop RHS that needs no evaluation (matches p8c's isinstance(rhs,
; (IntLit, Ident)) leaf-path test -- note: NOT BoolLit).

sub is_leaf_rhs(uword e) -> ubyte {
    ubyte k
    k = peek($ccf0 + (e))
    if k == ND_INT {
        return 1
    }
    if k == ND_IDENT {
        return 1
    }
    return 0
}
; a comparison RHS that p8c's _cmp_leaf_operand treats as a no-spill leaf:
; an int literal or a *non-const* var. A const is NOT a cmp leaf in p8c (it
; returns None -> the spill path, where the const folds during full byte-expr
; eval), so we exclude it here to stay byte-identical.

sub is_cmp_leaf_rhs(uword e) -> ubyte {
    ubyte k
    k = peek($ccf0 + (e))
    if k == ND_INT {
        return 1
    }
    if k == ND_IDENT {
        if ident_is_const(peekw($cf5c + ((e) << 1))) != 0 {
            return 0
        }
        return 1
    }
    return 0
}
; byte expression leaf -> A.

sub emit_byte_leaf_load(uword e) {
    ubyte k
    k = peek($ccf0 + (e))
    if k == ND_INT {
        o_lda() o_imm()
        out_hex2(lsb(peekw($cf5c + ((e) << 1))))
        o_nl()
        return
    }
    if k == ND_BOOL {
        o_lda() o_imm()
        out_hex2(lsb(peekw($cf5c + ((e) << 1))))
        o_nl()
        return
    }
    if k == ND_IDENT {
        if ident_is_const(peekw($cf5c + ((e) << 1))) != 0 {
            o_lda() o_imm()
            out_hex2(lsb(ident_const_val(peekw($cf5c + ((e) << 1)))))
            o_nl()
            return
        }
        o_lda()
        emit_mangled(peekw($cf5c + ((e) << 1)))
        o_nl()
        return
    }
    if k == ND_INDEX {
        ; byte-context array read. Fast `,y` path for ubyte element, <=256
        ; elems, byte index (matches p8c _array_fast_byte): const index ->
        ; absolute; simple byte-var index -> lda idx / tay / lda arr,y.
        ; Everything else (uword[], >256, word index) -> __p8c_aptr pointer
        ; path, loading the low byte.
        uword asi
        asi = find_sym(peekw($cf5c + ((peekw($cf5c + ((e) << 1))) << 1)))
        uword idx
        idx = peekw($d1c8 + ((e) << 1))
        if peek($dc94 + (asi)) == TY_UWORD {
            ; uword[] read in byte context: low half only (split lo array).
            codegen_word_expr(idx)
            o_tay()
            o_lda()
            emit_sym_mangled(asi)
            out_text("_lo,y")
            o_nl()
            return
        }
        if array_fast(asi, idx) != 0 {
            if peek($ccf0 + (idx)) == ND_INT {
                o_lda()
                emit_sym_mangled(asi)
                out_byte('+')
                out_dec(peekw($cf5c + ((idx) << 1)))
                o_nl()
                return
            }
            ; general byte index (ident / binop / ...): evaluate it to A, then
            ; `lda arr,y` (matches p8c _array_fast_byte, which accepts any
            ; UBYTE/BYTE-typed index, not just a bare var). For an ND_IDENT this
            ; is byte-identical to the old `lda idx / tay` special case.
            cg_arr_si = asi          ; survive codegen_byte_expr (asi is a
            codegen_byte_expr(idx)   ; static local; the recursive byte-expr
            o_tay()                  ; codegen can reuse its storage)
            o_lda()
            emit_sym_mangled(cg_arr_si)
            out_text(",y")
            o_nl()
            return
        }
        ; ubyte element, uword index (<=256): byte-index load.
        codegen_word_expr(idx)
        o_tay()
        o_lda()
        emit_sym_mangled(asi)
        out_text(",y")
        o_nl()
        return
    }
}
; emit the right-hand operand text of a byte binop. mode 0: a leaf rhs node
; ("#$XX" for an ND_INT, "p8v_<name>" for a var); mode 1: the __p8c_tmp1
; spill slot (the rhs node is ignored).

sub emit_byte_operand(ubyte mode, uword rhs) {
    if mode == 0 {
        if peek($ccf0 + (rhs)) == ND_INT {
            o_imm()
            out_hex2(lsb(peekw($cf5c + ((rhs) << 1))))
        } else {
            emit_mangled(peekw($cf5c + ((rhs) << 1)))
        }
    } else {
        out_text("__p8c_tmp1")
    }
}
; one shift label: ".Lshl_top_<id>" / ".Lshr_end_<id>" etc. (matching p8c's
; _new_label format `.L<prefix>_<id>`). is_left selects shl/shr; is_top top/end.

sub emit_shift_label(ubyte is_left, ubyte is_top, uword id) {
    if is_left != 0 {
        if is_top != 0 {
            out_text(".Lshl_top_")
        } else {
            out_text(".Lshl_end_")
        }
    } else {
        if is_top != 0 {
            out_text(".Lshr_top_")
        } else {
            out_text(".Lshr_end_")
        }
    }
    out_dec(id)
}
; A << / >> by a count. Immediate count -> unrolled asl/lsr (count & 7);
; otherwise a runtime loop over the operand (var or __p8c_tmp1), allocating a
; top/end label pair (label_seq, in alloc order top-then-end, like p8c).

sub emit_shift_op(ubyte is_left, ubyte is_imm, ubyte imm_val, ubyte mode, uword rhs) {
    if is_imm != 0 {
        ubyte cnt
        cnt = imm_val & 7
        ubyte i
        i = 0
        repeat {
            if i >= cnt {
                break
            }
            if is_left != 0 {
                out_text("  asl a")
            } else {
                out_text("  lsr a")
            }
            o_nl()
            i = i + 1
        }
        return
    }
    uword top_id
    uword end_id
    top_id = label_seq
    label_seq = label_seq + 1
    end_id = label_seq
    label_seq = label_seq + 1
    o_pha()
    o_lda()
    emit_byte_operand(mode, rhs)
    o_nl()
    o_tay()
    o_pla()
    out_text("  cpy #0")
    o_nl()
    out_text("  beq ")
    emit_shift_label(is_left, 0, end_id)
    o_nl()
    emit_shift_label(is_left, 1, top_id)
    out_byte(':')
    o_nl()
    if is_left != 0 {
        out_text("  asl a")
    } else {
        out_text("  lsr a")
    }
    o_nl()
    out_text("  dey")
    o_nl()
    out_text("  bne ")
    emit_shift_label(is_left, 1, top_id)
    o_nl()
    emit_shift_label(is_left, 0, end_id)
    out_byte(':')
    o_nl()
}
; the byte-binop core: A op <operand>, where the operand is selected by `mode`
; (0 = leaf rhs node, 1 = __p8c_tmp1 spill). Covers + - & | ^ (carry-correct
; add/sub, bitwise), * (the __p8c_mul_u8 helper -- sets mul_used), and the
; shifts << >>. p8c recurses on operands; p1 reaches this via the work stack.

sub emit_byte_binop_core(ubyte op, ubyte mode, uword rhs) {
    if op == TK_PLUS {
        o_clc()
        out_text("  adc ")
        emit_byte_operand(mode, rhs)
        o_nl()
        return
    }
    if op == TK_MINUS {
        o_sec()
        out_text("  sbc ")
        emit_byte_operand(mode, rhs)
        o_nl()
        return
    }
    if op == TK_AMP {
        out_text("  and ")
        emit_byte_operand(mode, rhs)
        o_nl()
        return
    }
    if op == TK_PIPE {
        out_text("  ora ")
        emit_byte_operand(mode, rhs)
        o_nl()
        return
    }
    if op == TK_CARET {
        out_text("  eor ")
        emit_byte_operand(mode, rhs)
        o_nl()
        return
    }
    if op == TK_STAR {
        o_sta_tmp0()
        o_lda()
        emit_byte_operand(mode, rhs)
        o_nl()
        o_sta_tmp1()
        out_text("  jsr __p8c_mul_u8")
        o_nl()
        mul_used = 1
        return
    }
    ; shifts: an immediate count (leaf ND_INT) unrolls; everything else loops.
    ubyte is_imm
    ubyte imm_val
    is_imm = 0
    imm_val = 0
    if mode == 0 {
        if peek($ccf0 + (rhs)) == ND_INT {
            is_imm = 1
            imm_val = lsb(peekw($cf5c + ((rhs) << 1)))
        }
    }
    if op == TK_SHL {
        emit_shift_op(1, is_imm, imm_val, mode, rhs)
    } else {
        emit_shift_op(0, is_imm, imm_val, mode, rhs)
    }
}
; emit a byte binop against a leaf operand rhs ("#$XX" or "p8v_<name>").

sub emit_byte_binop_leaf(ubyte op, uword rhs) {
    emit_byte_binop_core(op, 0, rhs)
}
; same op against the __p8c_tmp1 spill slot.

sub emit_byte_binop_zp(ubyte op) {
    emit_byte_binop_core(op, 1, 0)
}
; apply a unary op to A (operand already evaluated): ~ (eor #$ff), - (two's
; complement), not (bool 0->1 else 0, with a label pair allocated end-first
; to match p8c's _new_label order: .Lnot_end_N then .Lnot_zero_N+1). The
; `not` path is a faithful port but not yet test-reachable: its operand must
; be bool, and the only bool sources (comparisons / logical ops) arrive with
; the next M3 slice -- exercised then.

sub emit_unary_apply(ubyte uncode) {
    if uncode == UN_INV {
        o_eor_ff()
        return
    }
    if uncode == UN_NEG {
        o_eor_ff()
        o_clc()
        out_text("  adc #$01")
        o_nl()
        return
    }
    ; UN_NOT
    uword end_id
    uword zero_id
    end_id = label_seq
    label_seq = label_seq + 1
    zero_id = label_seq
    label_seq = label_seq + 1
    out_text("  beq .Lnot_zero_")
    out_dec(zero_id)
    o_nl()
    o_lda_imm0()
    out_text("  jmp .Lnot_end_")
    out_dec(end_id)
    o_nl()
    out_text(".Lnot_zero_")
    out_dec(zero_id)
    out_byte(':')
    o_nl()
    o_lda_imm1()
    out_text(".Lnot_end_")
    out_dec(end_id)
    out_byte(':')
    o_nl()
}

; ---- comparison codegen (port of _emit_cmp_into_a) -----------
; A comparison op token (TK_EQ..TK_GE are contiguous 78..83).

sub is_cmp_op(ubyte op) -> ubyte {
    if op < TK_EQ {
        return 0
    }
    if op > TK_GE {
        return 0
    }
    return 1
}
; the short-circuit logical operators `and` / `or` (the keyword tokens).

sub is_logical_op(ubyte op) -> ubyte {
    if op == TK_KAND {
        return 1
    }
    if op == TK_KOR {
        return 1
    }
    return 0
}
; Is a byte operand signed? p8c marks a comparison signed only when BOTH
; operands are exactly the BYTE type; here we resolve a leaf ident's type via
; the symbol table (literals are unsigned). NOTE: nested byte-arith operands
; that p8c would infer as BYTE are treated as unsigned here -- a known gap
; until p1 does full expression typing; the corpus uses leaf operands.

sub is_byte_signed(uword nd) -> ubyte {
    if peek($ccf0 + (nd)) == ND_IDENT {
        uword si
        si = find_sym(peekw($cf5c + ((nd) << 1)))
        if si == $ffff {
            return 0
        }
        if peek($dc94 + (si)) == TY_BYTE {
            return 1
        }
    }
    return 0
}

sub cmp_is_signed(uword e) -> ubyte {
    if is_byte_signed(peekw($cf5c + ((e) << 1))) == 0 {
        return 0
    }
    if is_byte_signed(peekw($d1c8 + ((e) << 1))) == 0 {
        return 0
    }
    return 1
}
; emit a branch-to-cmp_true line: "  <mnem> .Lcmp_true_<id>".

sub emit_br_true(uword mnem, uword true_id) {
    out_text("  ")
    out_text(mnem)
    out_byte(' ')
    out_text(".Lcmp_true_")
    out_dec(true_id)
    o_nl()
}
; The comparison tail (operands already in __p8c_tmp0 / __p8c_tmp1): compare
; and materialize 0/1 in A. Labels are allocated here (after the operand eval),
; matching p8c's _new_label order: cmp_true, cmp_end, then any op-specific
; extra (gt_no / sgn_ok / sgt_no).
; value-context comparison materializing 0/1 in A (lhs in __p8c_tmp0, rhs in
; __p8c_tmp1; result in A).

sub emit_cmp_tail(uword e, ubyte op) {
    ubyte is_signed
    is_signed = cmp_is_signed(e)
    o_lda_tmp0()
    uword true_id
    uword end_id
    uword no_id
    true_id = label_seq
    label_seq = label_seq + 1
    end_id = label_seq
    label_seq = label_seq + 1
    if is_signed == 0 {
        out_text("  cmp __p8c_tmp1")
        o_nl()
        if op == TK_EQ {
            emit_br_true("beq", true_id)
        }
        if op == TK_NE {
            emit_br_true("bne", true_id)
        }
        if op == TK_LT {
            emit_br_true("bcc", true_id)
        }
        if op == TK_GE {
            emit_br_true("bcs", true_id)
        }
        if op == TK_GT {
            no_id = label_seq
            label_seq = label_seq + 1
            out_text("  beq .Lgt_no_")
            out_dec(no_id)
            o_nl()
            emit_br_true("bcs", true_id)
            out_text(".Lgt_no_")
            out_dec(no_id)
            out_byte(':')
            o_nl()
        }
        if op == TK_LE {
            emit_br_true("beq", true_id)
            emit_br_true("bcc", true_id)
        }
    } else {
        if op == TK_EQ {
            out_text("  cmp __p8c_tmp1")
            o_nl()
            emit_br_true("beq", true_id)
        } else {
            if op == TK_NE {
                out_text("  cmp __p8c_tmp1")
                o_nl()
                emit_br_true("bne", true_id)
            } else {
                o_sec()
                out_text("  sbc __p8c_tmp1")
                o_nl()
                uword skip_id
                skip_id = label_seq
                label_seq = label_seq + 1
                out_text("  bvc .Lsgn_ok_")
                out_dec(skip_id)
                o_nl()
                out_text("  eor #$80")
                o_nl()
                out_text(".Lsgn_ok_")
                out_dec(skip_id)
                out_byte(':')
                o_nl()
                if op == TK_LT {
                    emit_br_true("bmi", true_id)
                }
                if op == TK_GE {
                    emit_br_true("bpl", true_id)
                }
                if op == TK_GT {

                    no_id = label_seq
                    label_seq = label_seq + 1
                    out_text("  beq .Lsgt_no_")
                    out_dec(no_id)
                    o_nl()
                    emit_br_true("bpl", true_id)
                    out_text(".Lsgt_no_")
                    out_dec(no_id)
                    out_byte(':')
                    o_nl()
                }
                if op == TK_LE {
                    emit_br_true("beq", true_id)
                    emit_br_true("bmi", true_id)
                }
            }
        }
    }
    o_lda_imm0()
    out_text("  jmp .Lcmp_end_")
    out_dec(end_id)
    o_nl()
    out_text(".Lcmp_true_")
    out_dec(true_id)
    out_byte(':')
    o_nl()
    o_lda_imm1()
    out_text(".Lcmp_end_")
    out_dec(end_id)
    out_byte(':')
    o_nl()
}

; ---- logical and/or (short-circuit, port of _emit_logical_into_a) -----
; emit the open-label name for the current op (and -> .Land_false_, or ->
; .Lor_true_) and the close-label name (and -> .Land_end_, or -> .Lor_end_).

sub emit_logic_open_name(ubyte op, uword id) {
    if op == TK_KAND {
        out_text(".Land_false_")
    } else {
        out_text(".Lor_true_")
    }
    out_dec(id)
}

sub emit_logic_end_name(ubyte op, uword id) {
    if op == TK_KAND {
        out_text(".Land_end_")
    } else {
        out_text(".Lor_end_")
    }
    out_dec(id)
}
; the short-circuit branch on a freshly-evaluated operand in A: `and` falls
; through on true and bails to false on zero (beq); `or` bails to true on
; non-zero (bne).

sub emit_logic_branch(ubyte op, uword id) {
    if op == TK_KAND {
        out_text("  beq ")
    } else {
        out_text("  bne ")
    }
    emit_logic_open_name(op, id)
    o_nl()
}
; mid task: after the lhs, allocate the label pair (matching p8c's order --
; after lhs eval) and emit the lhs short-circuit branch.

sub emit_logic_mid(ubyte op) {
    uword id1
    uword id2
    id1 = label_seq
    label_seq = label_seq + 1
    id2 = label_seq
    label_seq = label_seq + 1
    lstk_id1[(lstk_sp as ubyte)] = id1
    lstk_id2[(lstk_sp as ubyte)] = id2
    lstk_sp = lstk_sp + 1
    emit_logic_branch(op, id1)
}
; tail task: after the rhs, emit the rhs short-circuit branch and materialize
; 0/1 (and -> rhs true => 1; or -> rhs false => 0).

sub emit_logic_tail(ubyte op) {
    lstk_sp = lstk_sp - 1
    uword id1
    uword id2
    id1 = lstk_id1[(lstk_sp as ubyte)]
    id2 = lstk_id2[(lstk_sp as ubyte)]
    emit_logic_branch(op, id1)
    if op == TK_KAND {
        o_lda_imm1()
    } else {
        o_lda_imm0()
    }
    out_text("  jmp ")
    emit_logic_end_name(op, id2)
    o_nl()
    emit_logic_open_name(op, id1)
    out_byte(':')
    o_nl()
    if op == TK_KAND {
        o_lda_imm0()
    } else {
        o_lda_imm1()
    }
    emit_logic_end_name(op, id2)
    out_byte(':')
    o_nl()
}
; evaluate a byte expression into A.

; decompose a byte-context ND_BINOP onto the codegen_byte_expr work stack
; (cmp / logical / xor / leaf-rhs / general). Split out to keep
; codegen_byte_expr's per-sub node count under the arena cap.
sub cbe_binop(uword nd) {
    uword lhs
    uword rhs
    lhs = peekw($cf5c + ((nd) << 1))
    rhs = peekw($d1c8 + ((nd) << 1))
    if is_cmp_op(peek($ce26 + (nd))) != 0 {
        cws_push(7, nd, peek($ce26 + (nd)))
        cws_push(3, 0, 0)
        cws_push(0, rhs, 0)
        cws_push(8, 0, 0)
        cws_push(0, lhs, 0)
    } else {
        if is_logical_op(peek($ce26 + (nd))) != 0 {
            cws_push(10, 0, peek($ce26 + (nd)))
            cws_push(0, rhs, 0)
            cws_push(9, 0, peek($ce26 + (nd)))
            cws_push(0, lhs, 0)
        } else {
            if peek($ce26 + (nd)) == TK_KXOR {
                cws_push(11, 0, 0)
                cws_push(4, 0, 0)
                cws_push(8, 0, 0)
                cws_push(0, rhs, 0)
                cws_push(2, 0, 0)
                cws_push(0, lhs, 0)
            } else {
                if is_leaf_rhs(rhs) != 0 {
                    cws_push(1, rhs, peek($ce26 + (nd)))
                    cws_push(0, lhs, 0)
                } else {
                    cws_push(5, 0, peek($ce26 + (nd)))
                    cws_push(4, 0, 0)
                    cws_push(3, 0, 0)
                    cws_push(0, rhs, 0)
                    cws_push(2, 0, 0)
                    cws_push(0, lhs, 0)
                }
            }
        }
    }
}

; the non-binop byte-context leaf cases (cast / unop / @() / call / leaf load),
; split out of codegen_byte_expr to keep its per-sub node count under the cap.
sub cbe_leaf(uword nd) {
    if peek($ccf0 + (nd)) == ND_CAST {
        ; (operand as TYPE) in byte context: low byte of operand -> A.
        uword cop
        cop = peekw($cf5c + ((nd) << 1))
        if expr_is_word(cop) != 0 {
            codegen_word_expr(cop)
        } else {
            cws_push(0, cop, 0)
        }
    } else {
        if peek($ccf0 + (nd)) == ND_UNOP {
            cws_push(6, 0, peek($ce26 + (nd)))
            cws_push(0, peekw($cf5c + ((nd) << 1)), 0)
        } else {
            if peek($ccf0 + (nd)) == ND_MEMAT {
                emit_memat_read(nd)
            } else {
                if peek($ccf0 + (nd)) == ND_CALL {
                    codegen_call(nd)
                } else {
                    emit_byte_leaf_load(nd)
                }
            }
        }
    }
}

sub codegen_byte_expr(uword root) {
    ; the work stack must nest: evaluating a call arg re-enters this sub. A
    ; per-invocation base sp can't live in a (static-ZP) local without being
    ; clobbered by the re-entry, so mark the bottom of this frame with a
    ; sentinel entry (ty 255) and unwind until it is popped.
    cws_push(255, 0, 0)
    cws_push(0, root, 0)
    repeat {
        cws_sp = cws_sp - 1
        ubyte ty
        uword nd
        ubyte op
        ty = cws_type[(cws_sp as ubyte)]
        nd = cws_node[(cws_sp as ubyte)]
        op = cws_op[(cws_sp as ubyte)]
        if ty == 255 {
            break
        }
        if ty == 0 {
            if peek($ccf0 + (nd)) == ND_BINOP {
                cbe_binop(nd)
            } else {
                cbe_leaf(nd)
            }
        } else {
            if ty == 1 {
                emit_byte_binop_leaf(op, nd)
            } else {
                if ty == 2 {
                    o_pha()
                } else {
                    if ty == 3 {
                        o_sta_tmp1()
                    } else {
                        if ty == 4 {
                            o_pla()
                        } else {
                            if ty == 5 {
                                emit_byte_binop_zp(op)
                            } else {
                                if ty == 6 {
                                    emit_unary_apply(op)
                                } else {
                                    if ty == 7 {
                                        emit_cmp_tail(nd, op)
                                    } else {
                                        if ty == 8 {
                                            o_sta_tmp0()
                                        } else {
                                            if ty == 9 {
                                                emit_logic_mid(op)
                                            } else {
                                                if ty == 10 {
                                                    emit_logic_tail(op)
                                                } else {
                                                    out_text("  eor __p8c_tmp0")
                                                    o_nl()
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
; map an augmented-assignment token to its binop token.

sub aug_to_binop(ubyte op) -> ubyte {
    if op == TK_PLUSEQ {
        return TK_PLUS
    }
    if op == TK_MINUSEQ {
        return TK_MINUS
    }
    if op == TK_ANDEQ {
        return TK_AMP
    }
    if op == TK_OREQ {
        return TK_PIPE
    }
    if op == TK_XOREQ {
        return TK_CARET
    }
    if op == TK_SHLEQ {
        return TK_SHL
    }
    return TK_SHR       ; TK_SHREQ
}
; word expression leaf -> A (low) / Y (high), widening ubyte to uword.

sub codegen_word_leaf(uword e) {
    ubyte k
    k = peek($ccf0 + (e))
    if k == ND_INT {
        o_lda() o_imm()
        out_hex2(lsb(peekw($cf5c + ((e) << 1))))
        o_nl()
        o_ldy() o_imm()
        out_hex2(lsb(peekw($cf5c + ((e) << 1)) >> 8))
        o_nl()
        return
    }
    if k == ND_IDENT {
        uword si
        si = find_sym(peekw($cf5c + ((e) << 1)))
        if peek($e72c + (si)) != 0 {
            ; const folds to its literal (lo in A, hi in Y), matching p8c.
            uword cv
            cv = peekw($e8f0 + ((si) << 1))
            o_lda() o_imm() out_hex2(lsb(cv)) o_nl()
            o_ldy() o_imm() out_hex2(lsb(cv >> 8)) o_nl()
            return
        }
        o_lda()
        emit_mangled(peekw($cf5c + ((e) << 1)))
        o_nl()
        if peek($dc94 + (si)) == TY_UWORD {
            o_ldy()
            emit_mangled(peekw($cf5c + ((e) << 1)))
            o_plus1()
            o_nl()
        } else {
            o_ldy() o_imm()
            out_text("00")
            o_nl()
        }
        return
    }
    if k == ND_STR {
        ; a string literal is its pool address. Intern its content (dedup),
        ; getting the p8c_str_N label number for the pool trailer.
        uword lbl
        lbl = intern_str_label(peekw($cf5c + ((e) << 1)))
        out_text("  lda #<p8c_str_")
        out_dec(lbl)
        o_nl()
        out_text("  ldy #>p8c_str_")
        out_dec(lbl)
        o_nl()
        return
    }
}

sub wws_push(ubyte ty, uword nd, ubyte op) {
    wws_type[(wws_sp as ubyte)] = ty
    wws_node[(wws_sp as ubyte)] = nd
    wws_op[(wws_sp as ubyte)] = op
    wws_sp = wws_sp + 1
}
; &name (address-of) -> a uword value (lda #< / ldy #> the mangled label).

sub emit_addrof(uword e) {
    out_text("  lda #<")
    emit_mangled(peekw($cf5c + ((e) << 1)))
    o_nl()
    out_text("  ldy #>")
    emit_mangled(peekw($cf5c + ((e) << 1)))
    o_nl()
}
; the combine tail of a word + / - / & | ^ binop: LHS in A:Y, RHS in
; __p8c_wtmp0; result back into A:Y. (Port of _emit_word_binop_into_ay's
; arithmetic/bitwise arms.)

sub emit_word_combine(ubyte op) {
    if op == TK_PLUS {
        o_clc()
        out_text("  adc __p8c_wtmp0")
        o_nl()
        o_pha()
        o_tya()
        out_text("  adc __p8c_wtmp0+1")
        o_nl()
        o_tay()
        o_pla()
        return
    }
    if op == TK_MINUS {
        o_sec()
        out_text("  sbc __p8c_wtmp0")
        o_nl()
        o_pha()
        o_tya()
        out_text("  sbc __p8c_wtmp0+1")
        o_nl()
        o_tay()
        o_pla()
        return
    }
    ; bitwise & | ^ : and / ora / eor on both bytes.
    out_text("  ")
    emit_bitwise_mnem(op)
    out_text(" __p8c_wtmp0")
    o_nl()
    o_pha()
    o_tya()
    out_text("  ")
    emit_bitwise_mnem(op)
    out_text(" __p8c_wtmp0+1")
    o_nl()
    o_tay()
    o_pla()
}

sub emit_bitwise_mnem(ubyte op) {
    if op == TK_AMP {
        out_text("and")
    } else {
        if op == TK_PIPE {
            out_text("ora")
        } else {
            out_text("eor")
        }
    }
}
; apply a word unary op (~ or -) to A:Y (operand already evaluated).

sub emit_word_unary(ubyte uncode) {
    o_eor_ff()
    o_sta_wtmp0()
    o_tya()
    o_eor_ff()
    o_tay()
    o_lda_wtmp0()
    if uncode == UN_NEG {
        o_clc()
        out_text("  adc #$01")
        o_nl()
        out_text("  bcc *+3")
        o_nl()
        out_text("  iny")
        o_nl()
    }
}
; dispatch a word-expression node onto the word work stack.
; ---- word shifts (port of _emit_word_shl / _emit_word_shr) ----
; one A:Y<<1 step (lo in A, hi in Y): asl low, rol high, through wtmp0.

sub emit_wshl_step() {
    out_text("  asl a")
    o_nl()
    o_sta_wtmp0()
    o_tya()
    out_text("  rol a")
    o_nl()
    o_tay()
    o_lda_wtmp0()
}
; A:Y << n for a constant n (operand already in A:Y). n is value & $0f.

sub emit_wshl_const(ubyte n) {
    if n == 0 {
        return
    }
    ubyte i
    if n >= 8 {
        out_text("  tay")              ; low -> high
        o_nl()
        out_text("  lda #$00")         ; new low = 0
        o_nl()
        i = 8
        repeat {
            if i >= n {
                break
            }
            emit_wshl_step()
            i = i + 1
        }
        return
    }
    i = 0
    repeat {
        if i >= n {
            break
        }
        emit_wshl_step()
        i = i + 1
    }
}
; one A:Y>>1 step for the 1<=n<8 case (sty wtmp0+1; sta wtmp0; lsr/ror; reload).

sub emit_wshr_step_lo() {
    o_sty_wtmp0h()
    o_sta_wtmp0()
    out_text("  lsr __p8c_wtmp0+1")
    o_nl()
    o_ror_wtmp0()
    o_lda_wtmp0()
    o_ldy_wtmp0h()
}
; one A:Y>>1 step for the n>=8 case (note p8c's swapped sty/sta order here).

sub emit_wshr_step_hi() {
    out_text("  sty __p8c_wtmp0")
    o_nl()
    out_text("  sta __p8c_wtmp0+1")
    o_nl()
    out_text("  lsr __p8c_wtmp0+1")
    o_nl()
    o_ror_wtmp0()
    o_lda_wtmp0()
    o_ldy_wtmp0h()
}
; A:Y >> n for a constant n (operand already in A:Y). Logical shift right.

sub emit_wshr_const(ubyte n) {
    if n == 0 {
        return
    }
    ubyte i
    if n >= 8 {
        out_text("  tya")              ; high -> low
        o_nl()
        o_ldy0()
        i = 8
        repeat {
            if i >= n {
                break
            }
            emit_wshr_step_hi()
            i = i + 1
        }
        return
    }
    i = 0
    repeat {
        if i >= n {
            break
        }
        emit_wshr_step_lo()
        i = i + 1
    }
}
; ".Lwshl_top_N" / ".Lwshr_end_N" etc.

sub emit_wshift_label(ubyte is_left, ubyte is_top, uword id) {
    if is_left != 0 {
        if is_top != 0 {
            out_text(".Lwshl_top_")
        } else {
            out_text(".Lwshl_end_")
        }
    } else {
        if is_top != 0 {
            out_text(".Lwshr_top_")
        } else {
            out_text(".Lwshr_end_")
        }
    }
    out_dec(id)
}
; variable-count shift tail: LHS already in __p8c_wtmp0 (lo,hi). Evaluate the
; count into A (-> X) and loop. NOTE: the count goes through codegen_byte_expr,
; which resets the byte work stack -- safe at top level, but a word shift with
; a non-leaf count nested inside a byte expr's @() address would corrupt it.

sub emit_wshift_var_tail(uword nd, ubyte is_left) {
    codegen_byte_expr(peekw($d1c8 + ((nd) << 1)))
    o_tax()
    uword top_id
    uword end_id
    top_id = label_seq
    label_seq = label_seq + 1
    end_id = label_seq
    label_seq = label_seq + 1
    out_text("  cpx #$00")
    o_nl()
    out_text("  beq ")
    emit_wshift_label(is_left, 0, end_id)
    o_nl()
    emit_wshift_label(is_left, 1, top_id)
    out_byte(':')
    o_nl()
    if is_left != 0 {
        out_text("  asl __p8c_wtmp0")
        o_nl()
        out_text("  rol __p8c_wtmp0+1")
        o_nl()
    } else {
        out_text("  lsr __p8c_wtmp0+1")
        o_nl()
        o_ror_wtmp0()
    }
    out_text("  dex")
    o_nl()
    out_text("  bne ")
    emit_wshift_label(is_left, 1, top_id)
    o_nl()
    emit_wshift_label(is_left, 0, end_id)
    out_byte(':')
    o_nl()
    o_lda_wtmp0()
    o_ldy_wtmp0h()
}
; dispatch a word shift: const count (IntLit 0..16) unrolls; else loop. The
; const path evaluates the lhs then unrolls; the variable path stashes the lhs
; into wtmp0 first (STA_WTMP0 task), then the tail evaluates the count + loops.

sub word_dispatch_shift(uword nd, ubyte is_left) {
    uword rhsn
    rhsn = peekw($d1c8 + ((nd) << 1))
    if peek($ccf0 + (rhsn)) == ND_INT {
        if peekw($cf5c + ((rhsn) << 1)) <= 16 {
            ubyte n
            n = lsb(peekw($cf5c + ((rhsn) << 1))) & $0f
            if is_left != 0 {
                wws_push(5, 0, n)
            } else {
                wws_push(6, 0, n)
            }
            wws_push(0, peekw($cf5c + ((nd) << 1)), 0)
            return
        }
    }
    if is_left != 0 {
        wws_push(7, nd, 0)
    } else {
        wws_push(8, nd, 0)
    }
    wws_push(4, 0, 0)
    wws_push(0, peekw($cf5c + ((nd) << 1)), 0)
}

; ---- array element addressing (port of p8c _array_fast_byte and the Index
; read/write arms) ----------------------------------------------------------
; A ubyte `arr[i]` uses the tight `lda label,y` path with a byte-typed index
; (matches _array_fast_byte). A uword index is truncated to its low byte (the
; array is <=256 elements); uword arrays use split lo/hi byte arrays.

sub array_fast(uword asi, uword idx) -> ubyte {
    if peek($dc94 + (asi)) != TY_UBYTE { return 0 }
    if peekw($ec78 + ((asi) << 1)) > 256 { return 0 }
    if expr_is_word(idx) != 0 { return 0 }
    return 1
}

; continuation (word work stack): A:Y = index -> load uword element into A:Y.
sub emit_word_arr_load(uword e) {
    uword asi
    asi = find_sym(peekw($cf5c + ((peekw($cf5c + ((e) << 1))) << 1)))
    ; split lo/hi: A:Y holds the index; low byte -> Y, byte-indexed load.
    o_tay()
    out_text("  lda ") emit_sym_mangled(asi) out_text("_lo,y") o_nl()
    o_pha()
    out_text("  lda ") emit_sym_mangled(asi) out_text("_hi,y") o_nl()
    o_tay()
    o_pla()
}

; continuation (word work stack): A:Y = index -> ubyte element, byte-indexed
; (low byte of index), widened to uword.
sub emit_byte_arr_load_widened(uword e) {
    uword asi
    asi = find_sym(peekw($cf5c + ((peekw($cf5c + ((e) << 1))) << 1)))
    o_tay()
    out_text("  lda ") emit_sym_mangled(asi) out_text(",y") o_nl()
    o_ldy0()
}

; fast ubyte[] read in word context (byte index -> A, widen). Self-contained:
; the byte index runs on the byte work stack, separate from wws.
sub emit_word_arr_fast(uword asi, uword idx) {
    codegen_byte_expr(idx)
    o_tay()
    out_text("  lda ") emit_sym_mangled(asi) out_text(",y") o_nl()
    o_ldy0()
}

sub word_dispatch(uword nd) {
    ubyte k
    k = peek($ccf0 + (nd))
    if k == ND_CAST {
        ; (operand as TYPE) in word context (port of p8c's word-ctx Cast).
        uword cop
        cop = peekw($cf5c + ((nd) << 1))
        if peek($ce26 + (nd)) == TY_UWORD {
            codegen_word_expr(cop)             ; widen / identity to uword
        } else {
            if expr_is_word(cop) != 0 {
                codegen_word_expr(cop)         ; narrow uword -> low byte
            } else {
                codegen_byte_expr(cop)         ; byte operand -> A
            }
            o_ldy0()      ; high byte = 0
        }
        return
    }
    if k == ND_INDEX {
        uword asi
        asi = find_sym(peekw($cf5c + ((peekw($cf5c + ((nd) << 1))) << 1)))
        if peek($dc94 + (asi)) == TY_UWORD {
            wws_push(12, nd, 0)
            wws_push(0, peekw($d1c8 + ((nd) << 1)), 0)
            return
        }
        if array_fast(asi, peekw($d1c8 + ((nd) << 1))) != 0 {
            emit_word_arr_fast(asi, peekw($d1c8 + ((nd) << 1)))
            return
        }
        wws_push(13, nd, 0)
        wws_push(0, peekw($d1c8 + ((nd) << 1)), 0)
        return
    }
    if k == ND_ADDROF {
        emit_addrof(nd)
        return
    }
    if k == ND_CALL {
        ; word-returning call -> A:Y; a ubyte-returning call widens (ldy #0).
        ; codegen_call re-enters word_dispatch (the call's own arg eval), so
        ; stack the widen flag rather than re-reading the clobbered `nd`.
        wdn_stack[(wdn_sp as ubyte)] = call_returns_ubyte(nd)
        wdn_sp = wdn_sp + 1
        codegen_call(nd)
        wdn_sp = wdn_sp - 1
        if wdn_stack[(wdn_sp as ubyte)] != 0 {
            o_ldy() o_imm()
            out_text("00")
            o_nl()
        }
        return
    }
    if k == ND_BINOP {
        ubyte bop
        bop = peek($ce26 + (nd))
        if bop == TK_SHL {
            word_dispatch_shift(nd, 1)
            return
        }
        if bop == TK_SHR {
            word_dispatch_shift(nd, 0)
            return
        }
        ; arithmetic / bitwise: eval lhs; save; eval rhs; stash; combine.
        wws_push(3, 0, bop)
        wws_push(2, 0, 0)
        wws_push(0, peekw($d1c8 + ((nd) << 1)), 0)
        wws_push(1, 0, 0)
        wws_push(0, peekw($cf5c + ((nd) << 1)), 0)
        return
    }
    if k == ND_UNOP {
        wws_push(11, 0, peek($ce26 + (nd)))
        wws_push(0, peekw($cf5c + ((nd) << 1)), 0)
        return
    }
    ; leaf: int / ident / string
    codegen_word_leaf(nd)
}
; evaluate a uword expression into A (low) / Y (high), on the word work stack
; (no recursion). Port of _emit_word_expr_into_ay + _emit_word_binop_into_ay.
; Covers leaves, `&name`, the arithmetic/bitwise binops (+ - & | ^), and the
; word unary ~ / -. (Shifts, comparison, indexing, calls arrive next.)

sub codegen_word_expr(uword root) {
    ; nestable work stack (see codegen_byte_expr): a call arg re-enters this
    ; evaluator, so frame it with a sentinel (ty 255) and unwind to it.
    wws_push(255, 0, 0)
    wws_push(0, root, 0)
    repeat {
        wws_sp = wws_sp - 1
        ubyte ty
        uword nd
        ubyte op
        ty = wws_type[(wws_sp as ubyte)]
        nd = wws_node[(wws_sp as ubyte)]
        op = wws_op[(wws_sp as ubyte)]
        if ty == 255 {
            break
        }
        if ty == 0 {
            word_dispatch(nd)
        } else {
            if ty == 1 {
                ; save LHS (A:Y) on the CPU stack across the RHS eval
                o_pha()
                o_tya()
                o_pha()
            } else {
                if ty == 2 {
                    ; RHS -> wtmp0; restore LHS to A:Y
                    o_sta_wtmp0()
                    o_sty_wtmp0h()
                    o_pla()
                    o_tay()
                    o_pla()
                } else {
                    if ty == 3 {
                        emit_word_combine(op)
                    } else {
                        if ty == 4 {
                            ; LHS -> wtmp0 (for the variable-shift loop)
                            o_sta_wtmp0()
                            o_sty_wtmp0h()
                        } else {
                            if ty == 5 {
                                emit_wshl_const(op)
                            } else {
                                if ty == 6 {
                                    emit_wshr_const(op)
                                } else {
                                    if ty == 7 {
                                        emit_wshift_var_tail(nd, 1)
                                    } else {
                                        if ty == 8 {
                                            emit_wshift_var_tail(nd, 0)
                                        } else {
                                            if ty == 12 {
                                                emit_word_arr_load(nd)
                                            } else {
                                                if ty == 13 {
                                                    emit_byte_arr_load_widened(nd)
                                                } else {
                                                    emit_word_unary(op)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

; ---- @() memory read (byte) ---------------------------------
; @(IntLit) -> a direct absolute load; @(<word expr>) -> evaluate the address
; into __p8c_ptr0 and load via (ptr0),y.

sub emit_memat_read(uword nd) {
    uword addr
    addr = peekw($cf5c + ((nd) << 1))
    if peek($ccf0 + (addr)) == ND_INT {
        out_text("  lda $")
        out_hex4(peekw($cf5c + ((addr) << 1)))
        o_nl()
        return
    }
    codegen_word_expr(addr)
    out_text("  sta __p8c_ptr0")
    o_nl()
    out_text("  sty __p8c_ptr0+1")
    o_nl()
    o_ldy0()
    out_text("  lda (__p8c_ptr0),y")
    o_nl()
}

; sym-addressed loads/stores (the sym index is already resolved).

sub emit_lda_sym(uword si) {
    o_lda()
    emit_sym_mangled(si)
    o_nl()
}

sub emit_sta_sym(uword si) {
    o_sta()
    emit_sym_mangled(si)
    o_nl()
}

sub emit_sty_sym_hi(uword si) {
    o_sty()
    emit_sym_mangled(si)
    o_plus1()
    o_nl()
}

; ---- @() memory write (byte): @(addr) = byteexpr -----------
; @(IntLit) = e  -> eval e, sta absolute. @(<word expr>) = e -> eval e into
; __p8c_tmp0, evaluate the address into __p8c_ptr0, sta (ptr0),y.

sub codegen_assign_memat(uword st, uword target) {
    uword rhs
    uword addr
    rhs = peekw($d1c8 + ((st) << 1))
    addr = peekw($cf5c + ((target) << 1))
    if peek($ccf0 + (addr)) == ND_INT {
        codegen_byte_expr(rhs)
        out_text("  sta $")
        out_hex4(peekw($cf5c + ((addr) << 1)))
        o_nl()
        return
    }
    codegen_byte_expr(rhs)
    o_sta_tmp0()
    codegen_word_expr(addr)
    out_text("  sta __p8c_ptr0")
    o_nl()
    out_text("  sty __p8c_ptr0+1")
    o_nl()
    o_ldy0()
    o_lda_tmp0()
    out_text("  sta (__p8c_ptr0),y")
    o_nl()
}

; ---- assignment codegen -------------------------------------
; target is a plain (module) var or @(addr). `=` of a byte expression
; (arithmetic + - & | ^ * << >> cmp logical, leaf or nested) with
; ubyte->uword widening on word stores; `=` of a word expr; byte augmented
; (+= -= &= |= ^= <<= >>=) with a leaf operand.

; arr[idx] = expr  (port of _emit_assign's Index-target arm; plain `=` only).
sub codegen_assign_index(uword target, uword rhs) {
    uword asi
    asi = find_sym(peekw($cf5c + ((peekw($cf5c + ((target) << 1))) << 1)))
    uword idx
    idx = peekw($d1c8 + ((target) << 1))
    if peek($dc94 + (asi)) == TY_UWORD {
        ; split lo/hi uword[] write: rhs (widened) -> A:Y, parked on the CPU
        ; stack while the byte index is computed, then stored hi then lo.
        codegen_word_expr(rhs)
        o_pha()
        o_tya()
        o_pha()
        codegen_word_expr(idx)
        o_tay()
        o_pla()
        out_text("  sta ") emit_sym_mangled(asi) out_text("_hi,y") o_nl()
        o_pla()
        out_text("  sta ") emit_sym_mangled(asi) out_text("_lo,y") o_nl()
        return
    }
    if array_fast(asi, idx) != 0 {
        if peek($ccf0 + (idx)) == ND_INT {
            codegen_byte_expr(rhs)
            out_text("  sta ") emit_sym_mangled(asi) out_byte('+') out_dec(peekw($cf5c + ((idx) << 1))) o_nl()
            return
        }
        codegen_byte_expr(rhs)
        o_sta_tmp0()
        codegen_byte_expr(idx)
        o_tay()
        o_lda_tmp0()
        out_text("  sta ") emit_sym_mangled(asi) out_text(",y") o_nl()
        return
    }
    ; ubyte element, uword index (<=256): byte-index store.
    codegen_byte_expr(rhs)
    o_pha()
    codegen_word_expr(idx)
    o_tay()
    o_pla()
    out_text("  sta ") emit_sym_mangled(asi) out_text(",y") o_nl()
}

sub codegen_assign(uword st) {
    uword target
    uword rhs
    ubyte op
    target = peekw($cf5c + ((st) << 1))
    op = peek($ce26 + (st))
    rhs = peekw($d1c8 + ((st) << 1))
    if peek($ccf0 + (target)) == ND_MEMAT {
        codegen_assign_memat(st, target)
        return
    }
    if peek($ccf0 + (target)) == ND_INDEX {
        codegen_assign_index(target, rhs)
        return
    }
    uword si
    si = find_sym(peekw($cf5c + ((target) << 1)))
    ubyte ttype
    ttype = peek($dc94 + (si))
    if op == TK_ASSIGN {
        if ttype == TY_UWORD {
            codegen_word_expr(rhs)
            emit_sta_sym(si)
            emit_sty_sym_hi(si)
        } else {
            codegen_byte_expr(rhs)
            emit_sta_sym(si)
        }
        return
    }
    ; augmented. For a uword target, p8c rewrites `w op= e` to `w = w op e`
    ; and runs the word evaluator on that synthetic binop (matching its
    ; _emit_assign); build the same node and store the A:Y result.
    if ttype == TY_UWORD {
        uword synth
        synth = new_node(ND_BINOP, aug_to_binop(op), target, rhs)
        codegen_word_expr(synth)
        emit_sta_sym(si)
        emit_sty_sym_hi(si)
        return
    }
    ; byte augmented: lda LHS; <op> leaf-operand; sta LHS.
    emit_lda_sym(si)
    emit_byte_binop_leaf(aug_to_binop(op), rhs)
    emit_sta_sym(si)
}

; ---- subs + calls -------------------------------------------
; consume one non-sub top-level unit without emitting it (the parser's
; skip_decl_pass_b lives past the splice boundary, so it is replicated here).

sub emit_sub_label(uword identid) {
    out_text("p8s_")
    out_ident_text(identid)
}

sub find_sub(uword identid) -> uword {
    uword i
    i = 0
    repeat {
        if i >= sub_count {
            break
        }
        if sub_name[(i as ubyte)] == identid {
            return i
        }
        i = i + 1
    }
    return $ffff
}
; does ident `identid` spell the NUL-terminated string at `s`?

sub ident_eq(uword identid, uword s) -> ubyte {
    uword off
    uword n
    off = identid
    n = ident_len_at(identid)
    uword j
    j = 0
    repeat {
        ubyte ch
        ch = @(s + j)
        if ch == 0 {
            if j == n {
                return 1
            }
            return 0
        }
        if j >= n {
            return 0
        }
        if peek($a9e8 + (off + j)) != ch {
            return 0
        }
        j = j + 1
    }
}
; builtin code for a callee name: 0 = not a builtin, 1 lsb, 2 msb, 3 peek,
; 4 poke, 5 mkword. (len / sizeof arrive with arrays.)

sub builtin_kind(uword identid) -> ubyte {
    if ident_eq(identid, "lsb") != 0 { return 1 }
    if ident_eq(identid, "msb") != 0 { return 2 }
    if ident_eq(identid, "peek") != 0 { return 3 }
    if ident_eq(identid, "poke") != 0 { return 4 }
    if ident_eq(identid, "mkword") != 0 { return 5 }
    if ident_eq(identid, "strings.compare") != 0 { return 6 }
    if ident_eq(identid, "peekw") != 0 { return 7 }
    if ident_eq(identid, "pokew") != 0 { return 8 }
    return 0
}
; the 1st / 2nd argument of the builtin whose callnode is on top of bi_cn.
; node_b is the reversed args cons (last pushed = head), so for f(x,y) the
; head is y and head.next is x. Re-derived fresh each call so re-entrant
; nested-builtin codegen can't leave a stale node id.

sub bi_arg0() -> uword {
    uword h
    h = peekw($d1c8 + ((bi_cn[(bi_sp - 1 as ubyte)]) << 1))
    if cons_next[(h as ubyte)] == 0 {
        return cons_val[(h as ubyte)]              ; single arg
    }
    return cons_val[(cons_next[(h as ubyte)] as ubyte)]       ; first of two
}

sub bi_arg1() -> uword {
    return cons_val[(peekw($d1c8 + ((bi_cn[(bi_sp - 1 as ubyte)]) << 1)) as ubyte)]   ; second (= head)
}
; compute a uword address expression into __p8c_aptr. Recognizes the slab form
; `<int base> + <offset>` and folds the base into the final adc (matching p8c's
; _emit_addr_into_aptr), so peek/poke/peekw/pokew on a fixed-base arena are tight.

sub emit_addr_into_aptr(uword addr) {
    if peek($ccf0 + (addr)) == ND_BINOP {
        if peek($ce26 + (addr)) == TK_PLUS {
            uword lhs
            lhs = peekw($cf5c + ((addr) << 1))
            if peek($ccf0 + (lhs)) == ND_INT {
                ; stack the base: codegen_word_expr below may recurse into this
                ; sub (nested peekw) and clobber the static-local base.
                eai_base[(eai_sp as ubyte)] = peekw($cf5c + ((lhs) << 1))
                eai_sp = eai_sp + 1
                codegen_word_expr(peekw($d1c8 + ((addr) << 1)))   ; offset -> A:Y
                eai_sp = eai_sp - 1
                uword base
                base = eai_base[(eai_sp as ubyte)]
                o_clc()
                out_text("  adc #<$") out_hex4(base) o_nl()
                out_text("  sta __p8c_aptr") o_nl()
                o_tya()
                out_text("  adc #>$") out_hex4(base) o_nl()
                out_text("  sta __p8c_aptr+1") o_nl()
                return
            }
        }
    }
    codegen_word_expr(addr)
    out_text("  sta __p8c_aptr") o_nl()
    out_text("  sty __p8c_aptr+1") o_nl()
}
; lower a builtin call to inline asm (port of _emit_builtin_call).

sub emit_builtin(uword callnode, ubyte bk) {
    bi_cn[(bi_sp as ubyte)] = callnode
    bi_sp = bi_sp + 1
    if bk == 1 {                       ; lsb(uword) -> low byte in A
        codegen_word_expr(bi_arg0())
    } else {
        if bk == 2 {                   ; msb(uword) -> high byte in A
            codegen_word_expr(bi_arg0())
            o_tya()
        } else {
            if bk == 3 {               ; peek(addr) -> ubyte in A
                if peek($ccf0 + (bi_arg0())) == ND_INT {
                    out_text("  lda $")
                    out_hex4(peekw($cf5c + ((bi_arg0()) << 1)))
                    o_nl()
                } else {
                    emit_addr_into_aptr(bi_arg0())
                    o_ldy0()
                    o_aptr_ld()
                }
            } else {
                if bk == 4 {           ; poke(addr, byteexpr)
                    if peek($ccf0 + (bi_arg0())) == ND_INT {
                        codegen_byte_expr(bi_arg1())
                        out_text("  sta $")
                        out_hex4(peekw($cf5c + ((bi_arg0()) << 1)))
                        o_nl()
                    } else {
                        codegen_byte_expr(bi_arg1())
                        o_pha()
                        emit_addr_into_aptr(bi_arg0())
                        o_pla()
                        o_ldy0()
                        o_aptr_st()
                    }
                } else {
                    if bk == 5 {
                        ; mkword(msb, lsb) -> A=low, Y=high (Y-safe via X).
                        codegen_byte_expr(bi_arg0())
                        o_pha()
                        codegen_byte_expr(bi_arg1())
                        o_tax()
                        o_pla()
                        o_tay()
                        o_txa()
                    } else {
                        if bk == 6 {
                        ; strings.compare(a, b) -> A = -1/0/1. Park both pointers
                        ; in __p8c_wtmp0/1 (stack-shuffling the first so arg1's
                        ; eval can't clobber it), then jsr the shared helper.
                        codegen_word_expr(bi_arg0())
                        o_pha()
                        o_tya()
                        o_pha()
                        codegen_word_expr(bi_arg1())
                        out_text("  sta __p8c_wtmp1\n  sty __p8c_wtmp1+1\n")
                        o_pla()
                        out_text("  sta __p8c_wtmp0+1\n")
                        o_pla()
                        out_text("  sta __p8c_wtmp0\n  jsr __p8c_strcmp\n")
                        strcmp_used = 1
                        } else {
                            if bk == 7 {
                                ; peekw(addr) -> uword, A=lo Y=hi
                                emit_addr_into_aptr(bi_arg0())
                                o_ldy0()
                                o_aptr_ld()
                                o_pha()
                                o_ldy1()
                                o_aptr_ld()
                                o_tay()
                                o_pla()
                            } else {
                                ; pokew(addr, wordexpr): value lo=A hi=Y, stack
                                ; it, addr -> aptr, store hi then lo.
                                codegen_word_expr(bi_arg1())
                                o_pha()
                                o_tya()
                                o_pha()
                                emit_addr_into_aptr(bi_arg0())
                                o_pla()
                                o_ldy1()
                                o_aptr_st()
                                o_pla()
                                o_ldy0()
                                o_aptr_st()
                            }
                        }
                    }
                }
            }
        }
    }
    bi_sp = bi_sp - 1
}
; does a call's result type widen as ubyte in word context?

sub call_returns_ubyte(uword callnode) -> ubyte {
    uword callee
    callee = peekw($cf5c + ((callnode) << 1))
    ubyte bk
    bk = builtin_kind(callee)
    if bk != 0 {
        if bk == 5 {                   ; mkword -> uword
            return 0
        }
        if bk == 7 {                   ; peekw -> uword
            return 0
        }
        return 1                        ; lsb / msb / peek -> ubyte
    }
    uword si
    si = find_sub(callee)
    if si != $ffff {
        if sub_ret[(si as ubyte)] == TY_UBYTE {
            return 1
        }
    }
    return 0
}
; collect the callee's params (sym indices, in source order) into call_slot,
; setting call_n. Params are the syms with scope == callee and mkind == param,
; stored in allocation (source) order.

sub collect_params(uword callee) {
    call_n = 0
    uword i
    i = 0
    repeat {
        if i >= sym_count {
            break
        }
        if peekw($e1e0 + ((i) << 1)) == callee {
            if peek($e568 + (i)) == 1 {
                call_slot[(call_n as ubyte)] = i
                if peek($dc94 + (i)) == TY_UWORD {
                    call_isw[(call_n as ubyte)] = 1
                } else {
                    call_isw[(call_n as ubyte)] = 0
                }
                call_n = call_n + 1
            }
        }
        i = i + 1
    }
}
; codegen a call. Regular sub: evaluate every arg onto the CPU stack (so a
; later arg's evaluation can't clobber an earlier arg's param slot -- the slots
; are not reentrant), then pop them into the param slots in reverse and jsr.
; asmsub call ABI (port of _emit_call's asmsub arm): 0 args -> just jsr; 1 arg
; -> load it into A (ubyte) or A:Y (uword); then jsr the $F0xx target.

; load each reg-ABI arg whose register's "is A/AY" classification matches
; want_a (0 => emit the X/Y args, 1 => emit the A/AY args). p8c loads the
; A/AY-bound arg LAST so the evaluator's use of A can't clobber X/Y.
sub emit_regabi_pass(ubyte n, ubyte want_a) {
    ubyte j
    j = 0
    repeat {
        if j >= n { break }
        ubyte r
        r = rb_reg[(j as ubyte)]
        ubyte is_a
        is_a = 0
        if r == 1 { is_a = 1 }
        if r == 4 { is_a = 1 }
        if is_a == want_a {
            if r == 4 {
                codegen_word_expr(rb_arg[(j as ubyte)])
            } else {
                codegen_byte_expr(rb_arg[(j as ubyte)])
                if r == 2 { out_text("  tax")  o_nl() }
                if r == 3 { out_text("  tay")  o_nl() }
            }
        }
        j = j + 1
    }
}

sub codegen_asmsub_call(uword callnode, uword cs) {
    uword callee
    callee = peekw($cf5c + ((callnode) << 1))
    collect_params(callee)
    ubyte n
    n = call_n
    ; capture each arg's expr + its param's register/width (source order).
    uword acell
    acell = reverse_cons_ip(peekw($d1c8 + ((callnode) << 1)))
    ubyte j
    j = 0
    repeat {
        if j >= n { break }
        rb_arg[(j as ubyte)] = cons_val[(acell as ubyte)]
        rb_reg[(j as ubyte)] = lsb(peekw($e8f0 + ((call_slot[(j as ubyte)]) << 1)))
        rb_isw[(j as ubyte)] = call_isw[(j as ubyte)]
        acell = cons_next[(acell as ubyte)]
        j = j + 1
    }
    ubyte regabi
    regabi = 0
    if n != 0 { if rb_reg[0] != 0 { regabi = 1 } }
    if regabi != 0 {
        emit_regabi_pass(n, 0)              ; X / Y args first
        emit_regabi_pass(n, 1)              ; A / AY arg last
    } else {
        if n == 1 {                         ; legacy ABI: one arg into A / A:Y
            if rb_isw[0] != 0 {
                codegen_word_expr(rb_arg[0])
            } else {
                codegen_byte_expr(rb_arg[0])
            }
        }
    }
    if sub_kind[(cs as ubyte)] == SUBK_ASMSUB_BODY {
        out_text("  jsr ")
        emit_sub_label(callee)
        o_nl()
    } else {
        out_text("  jsr $")
        out_hex4(sub_addr[(cs as ubyte)])
        o_nl()
    }
}
; Result: A (ubyte/byte) or A:Y (uword). (NOTE: call_slot is global, so an arg
; that is itself a call would corrupt it -- not yet handled; args are simple.)

; push a multi-arg call's args onto the CPU stack (source order) then pop them
; into the callee's param slots (reverse order). Split out of codegen_call to
; keep its per-sub node count under the arena cap.
sub codegen_call_args(uword callnode, uword callee) {
    uword acell
    acell = reverse_cons_ip(peekw($d1c8 + ((callnode) << 1)))
    ubyte j
    j = 0
    repeat {
        if acell == 0 {
            break
        }
        uword arg
        arg = cons_val[(acell as ubyte)]
        ccs_callee[(ccs_sp as ubyte)] = callee
        ccs_node[(ccs_sp as ubyte)] = acell
        ccs_j[(ccs_sp as ubyte)] = j
        ccs_sp = ccs_sp + 1
        if call_isw[(j as ubyte)] != 0 {
            codegen_word_expr(arg)
            o_pha()
            o_tya()
            o_pha()
        } else {
            codegen_byte_expr(arg)
            o_pha()
        }
        ccs_sp = ccs_sp - 1
        callee = ccs_callee[(ccs_sp as ubyte)]
        acell = ccs_node[(ccs_sp as ubyte)]
        j = ccs_j[(ccs_sp as ubyte)]
        collect_params(callee)
        j = j + 1
        acell = cons_next[(acell as ubyte)]
    }
    repeat {
        if j == 0 {
            break
        }
        j = j - 1
        uword psi
        psi = call_slot[(j as ubyte)]
        if call_isw[(j as ubyte)] != 0 {
            out_text("  pla")
            o_nl()
            o_sta()
            emit_sym_mangled(psi)
            o_plus1()
            o_nl()
            out_text("  pla")
            o_nl()
            emit_sta_sym(psi)
        } else {
            o_pla()
            emit_sta_sym(psi)
        }
    }
}

sub codegen_call(uword callnode) {
    uword callee
    callee = peekw($cf5c + ((callnode) << 1))
    ubyte bk
    bk = builtin_kind(callee)
    if bk != 0 {
        emit_builtin(callnode, bk)
        return
    }
    uword cs
    cs = find_sub(callee)
    if cs != $ffff {
        if sub_kind[(cs as ubyte)] == SUBK_ASMSUB {
            codegen_asmsub_call(callnode, cs)
            return
        }
        if sub_kind[(cs as ubyte)] == SUBK_ASMSUB_BODY {
            codegen_asmsub_call(callnode, cs)
            return
        }
    }
    collect_params(callee)
    if call_n == 1 {
        ; single arg: evaluate it (result in A / A:Y), then store into the slot
        ; and jsr. The arg may itself be a call, which clobbers codegen_call's
        ; static-ZP locals (callee, call_slot, ...), so save callee across the
        ; eval and re-derive the slot afterwards (collect_params is pure).
        uword arg1
        arg1 = cons_val[(reverse_cons_ip(peekw($d1c8 + ((callnode) << 1))) as ubyte)]
        ubyte isw1
        isw1 = call_isw[0]
        ccs_callee[(ccs_sp as ubyte)] = callee
        ccs_sp = ccs_sp + 1
        if isw1 != 0 {
            codegen_word_expr(arg1)
        } else {
            codegen_byte_expr(arg1)
        }
        ccs_sp = ccs_sp - 1
        callee = ccs_callee[(ccs_sp as ubyte)]
        collect_params(callee)
        ; the arg eval may have been a nested call that clobbered the static-ZP
        ; local isw1; re-derive it from the just-refilled call_isw so the high-
        ; byte store matches THIS callee's param width (e.g. out_hex2 is ubyte).
        isw1 = call_isw[0]
        uword psi1
        psi1 = call_slot[0]
        emit_sta_sym(psi1)
        if isw1 != 0 {
            emit_sty_sym_hi(psi1)
        }
        out_text("  jsr ")
        emit_sub_label(callee)
        o_nl()
        return
    }
    if call_n != 0 {
        ; a multi-arg eval may be a nested call that clobbers codegen_call's
        ; static-ZP `callee`/`callnode` (codegen_call_args only preserves its own
        ; param copies); save callee on the ccs stack across the arg evaluation.
        ccs_callee[(ccs_sp as ubyte)] = callee
        ccs_sp = ccs_sp + 1
        codegen_call_args(callnode, callee)
        ccs_sp = ccs_sp - 1
        callee = ccs_callee[(ccs_sp as ubyte)]
    }
    out_text("  jsr ")
    emit_sub_label(callee)
    o_nl()
}
; inline `%asm{ "..." }` -> emit each line of the (str-pooled) text with a
; 2-space indent (port of _emit_stmt's InlineAsm; splitlines semantics).

sub codegen_inline_asm(uword st) {
    uword sid
    sid = peekw($cf5c + ((st) << 1))
    uword off
    uword n
    off = sid
    n = str_len_at(sid)
    uword j
    j = 0
    repeat {
        if j >= n {
            break
        }
        out_text("  ")
        repeat {
            if j >= n {
                break
            }
            ubyte c
            c = peek($beb0 + (off + j))
            j = j + 1
            if c == $0a {
                break
            }
            out_byte(c)
        }
        o_nl()
    }
}
; `return [value]` (port of _emit_stmt's Return). With a value, evaluate it
; (byte -> A, word -> A:Y) and run the pha/pla dance p8c emits (defers go
; between -- none yet), then jmp the per-sub return label.

sub codegen_return(uword st) {
    uword value
    value = peekw($cf5c + ((st) << 1))
    if value != 0 {
        if cur_ret == TY_UWORD {
            codegen_word_expr(value)
            o_pha()
            o_tya()
            o_pha()
            o_pla()
            o_tay()
            o_pla()
        } else {
            codegen_byte_expr(value)
            o_pha()
            o_pla()
        }
    }
    out_text("  jmp .Lp8s_")
    out_ident_text(cur_ret_name)
    out_text("_ret")
    o_nl()
}
; push a block's statements onto the (pass-S-only) walk stack -- reuses sws_a,
; which is free until codegen.

sub emit_sub(uword snode) {
    label_seq = 0
    uword nm
    nm = peekw($cf5c + ((snode) << 1))
    ; an inline-body asmsub emits `; ---- asmsub NAME ----` + label + the raw
    ; %asm lines (the body has its own rts); no prologue/epilogue.
    uword acs
    acs = find_sub(nm)
    if acs != $ffff {
        if sub_kind[(acs as ubyte)] == SUBK_ASMSUB_BODY {
            o_nl()
            out_text("; ---- asmsub ")
            out_ident_text(nm)
            out_text(" ----")
            o_nl()
            emit_sub_label(nm)
            out_byte(':')
            o_nl()
            cur_scope = nm
            codegen_body(peekw($d434 + ((snode) << 1)))
            return
        }
    }
    cur_ret = lsb(peekw($d6a0 + ((snode) << 1)))
    cur_ret_name = peekw($cf5c + ((snode) << 1))
    cur_scope = peekw($cf5c + ((snode) << 1))
    o_nl()
    out_text("; ---- sub ")
    out_ident_text(peekw($cf5c + ((snode) << 1)))
    out_text(" ----")
    o_nl()
    emit_sub_label(peekw($cf5c + ((snode) << 1)))
    out_byte(':')
    o_nl()
    codegen_body(peekw($d434 + ((snode) << 1)))
    out_text(".Lp8s_")
    out_ident_text(peekw($cf5c + ((snode) << 1)))
    out_text("_ret:")
    o_nl()
    out_text("  rts")
    o_nl()
}
; pass B: re-scan the source and codegen every non-main regular sub in source
; order (main was emitted by pass M; asmsub has no body; inline is spliced at
; the call site, handled later).


sub d16(uword v) { out_byte(lsb(v)) out_byte(lsb(v >> 8)) }


sub l16() -> uword {
    uword lo
    lo = read_src()
    uword hi
    hi = read_src()
    return lo | (hi << 8)
}
sub load_global() {
    prog_address = l16()
    prog_target = read_src()
    uword i
    sym_count = l16()
    i = 0
    repeat {
        if i >= sym_count { break }
        pokew($d90c + ((i) << 1), l16()) poke($dc94 + (i), read_src()) pokew($de58 + ((i) << 1), l16()) pokew($e1e0 + ((i) << 1), l16())
        poke($e568 + (i), read_src()) poke($e72c + (i), read_src()) pokew($e8f0 + ((i) << 1), l16()) pokew($ec78 + ((i) << 1), l16())
        i = i + 1
    }
    resident_sym_count = sym_count
    sub_count = l16()
    i = 0
    repeat {
        if i >= sub_count { break }
        sub_name[(i as ubyte)] = l16() sub_kind[(i as ubyte)] = read_src() sub_ret[(i as ubyte)] = read_src() sub_addr[(i as ubyte)] = l16()
        if sub_kind[(i as ubyte)] == SUBK_MAIN { entry_nm = sub_name[(i as ubyte)] }
        i = i + 1
    }
    ident_pool_len = l16()
    i = 0
    repeat { if i >= ident_pool_len { break } poke($a9e8 + (i), read_src()) i = i + 1 }
    str_pool_len = l16()
    i = 0
    repeat { if i >= str_pool_len { break } poke($beb0 + (i), read_src()) i = i + 1 }
    ; data-initialized array tables
    ai_count = l16()
    uword vo
    vo = 0
    i = 0
    repeat {
        if i >= ai_count { break }
        ai_sym[(i as ubyte)] = l16()
        ai_isstr[(i as ubyte)] = read_src()
        ai_n[(i as ubyte)] = l16()
        ai_off[(i as ubyte)] = vo
        uword j
        j = 0
        repeat {
            if j >= ai_n[(i as ubyte)] { break }
            ai_vals[(vo as ubyte)] = l16()
            vo = vo + 1
            j = j + 1
        }
        i = i + 1
    }
}
; load one record's nodes into the (reset) node arena; returns the snode.
sub load_record() {
    rec_kind = read_src()
    if rec_kind == $ff { return }
    rec_snode = l16()
    uword i
    sym_count = resident_sym_count
    uword lc
    lc = l16()
    i = 0
    repeat {
        if i >= lc { break }
        pokew($d90c + ((sym_count) << 1), l16()) poke($dc94 + (sym_count), read_src()) pokew($de58 + ((sym_count) << 1), l16()) pokew($e1e0 + ((sym_count) << 1), l16())
        poke($e568 + (sym_count), read_src()) poke($e72c + (sym_count), read_src()) pokew($e8f0 + ((sym_count) << 1), l16()) pokew($ec78 + ((sym_count) << 1), l16())
        sym_count = sym_count + 1
        i = i + 1
    }
    node_count = l16()
    i = 0
    repeat {
        if i >= node_count { break }
        poke($ccf0 + (i), read_src()) poke($ce26 + (i), read_src())
        pokew($cf5c + ((i) << 1), l16()) pokew($d1c8 + ((i) << 1), l16()) pokew($d434 + ((i) << 1), l16()) pokew($d6a0 + ((i) << 1), l16())
        i = i + 1
    }
    cons_count = l16()
    i = 0
    repeat {
        if i >= cons_count { break }
        cons_val[(i as ubyte)] = l16() cons_next[(i as ubyte)] = l16()
        i = i + 1
    }
}


sub copy_zp_text() {
    repeat { ubyte b
        b = read_src()
        if b == 0 { break }
        out_byte(b)
    }
}
sub skip_zp_text() {
    repeat { ubyte b
        b = read_src()
        if b == 0 { break }
    }
}
sub copy_memvar_text() {
    repeat { ubyte b
        b = read_src()
        if b == 0 { break }
        out_byte(b)
    }
}
sub skip_memvar_text() {
    repeat { ubyte b
        b = read_src()
        if b == 0 { break }
    }
}


sub register_subs() { return }
sub cg_skip_decl() { return }
sub emit_subs() { return }


sub start() {
    uword fn
    fn = sys_argv(0)
    src_hand = sys_open(fn)
    fn = sys_argv(1)
    dst_hand = sys_openout(fn)
    load_global()
    strpool_count = 0
    mul_used = 0
    strcmp_used = 0
    label_seq = 0
    ccs_sp = 0
    cb_sp = 0
    lstk_sp = 0
    emit_prologue()
    copy_zp_text()
    skip_memvar_text()
    ; stream 1: main
    repeat {
        load_record()
        if rec_kind == $ff { break }
        if rec_kind == 0 {
            cur_ret = TY_VOID
            cur_ret_name = peekw($cf5c + ((rec_snode) << 1))
            cur_scope = peekw($cf5c + ((rec_snode) << 1))
            emit_main(peekw($d434 + ((rec_snode) << 1)))
        }
    }
    ; drain to EOF so the emulator rewinds the dump to offset 0, then re-read
    ; (and discard) the global block to reach the records again.
    ubyte junk
    repeat {
        junk = read_src()
        if src_eof != 0 { break }
    }
    reset_source()
    load_global()
    skip_zp_text()
    skip_memvar_text()
    repeat {
        load_record()
        if rec_kind == $ff { break }
        if rec_kind == 1 {
            emit_sub(rec_snode)
        }
    }
    emit_mul_helper()
    emit_strcmp_helper()
    emit_arrays()
    repeat {
        junk = read_src()
        if src_eof != 0 { break }
    }
    reset_source()
    load_global()
    skip_zp_text()
    copy_memvar_text()
    emit_string_pool()
    emit_trailers()
    sys_close(src_hand)
    sys_close(dst_hand)
}
}

