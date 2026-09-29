; p1_pass1_sh.p8 -- PASS 1 of the self-hosting Prog8 pipeline (hand-maintained).
; Reads a .p8 program (argv[0]); lexes + parses + allocates symbols and writes
; the AST/symbol dump (argv[1]) that p1_pass2_sh.p8 consumes. Built into
; pass1.bin. Self-host check: /tmp/verify.sh + p1/tests/test_p1.py. The
; front-end below is the stmt.p8 lexer/parser (its banner follows).


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
%memtop $8c52
%import strings

; scratch global for the call-argument hoist out of new_node()/cons_prepend():
; upstream writes args left-to-right into the callee's STATIC param vars before
; evaluating the call, so a `parse_*()` last-arg must be hoisted to its own line.

%output raw
%launcher none

main {
uword hoist_arg

; ---- token kinds ----
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
const ubyte TK_KEXTSUB= 65
const ubyte TK_KAS    = 66
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
ubyte tk0_kind
uword tk0_val
ubyte tk1_kind
uword tk1_val
ubyte ntok_kind
uword ntok_val

; pending-token queue: a raw `%asm {{ ... }}` block is lexed in one shot (the
; body captured + normalized into a STR), then the synthesized `{ { STR } }`
; tokens are emitted from here so parse_inline_asm's `{{ STR }}` path is reused
; unchanged (mirrors p8c's lexer normalization). pend_i >= pend_n => empty.
ubyte[6] pendk
uword[6] pendv
ubyte pend_i
ubyte pend_n

; identifier text pool (reset per top-level unit while streaming)
const uword ident_pool = $8c52
uword ident_count
uword ident_pool_len

; string literal pool (null-terminated; a string's id is its start offset).
; Cap must exceed the TRANSIENT peak, not just the final deduped size: the
; lexer appends a literal's bytes at str_pool_len BEFORE the dedup scan rolls
; str_pool_len back for a duplicate. So re-lexing a long duplicate (e.g. the
; ~671-byte emit_prologue header, encountered when str_pool_len is already at
; its full ~3381) transiently writes to ~4052 -- which must stay inside the
; array, or it clobbers str_pool_len / name_buf / path_buf and corrupts the
; just-read callee ident (the "out_text -> garbage" self-host bug).
const uword str_pool = $a252
uword str_pool_len

ubyte[65] name_buf       ; 64 chars + room for a NUL terminator (classify_name)
ubyte[96] path_buf       ; parser's dotted-path buffer (lexer owns name_buf)
uword path_len
uword name_len

uword int_val

; node arena
const uword node_kind = $b252
const uword node_op = $b40f
const uword node_a = $b5cc
const uword node_b = $b946
const uword node_c = $bcc0
const uword node_d = $c03a
uword node_count

; expression stacks
uword[16] operand_stack
uword operand_sp
ubyte[16] op_kind
ubyte[16] op_op
ubyte[16] op_prec
uword[16] op_a
uword[16] op_b
uword[16] op_floor
uword op_sp

; cons cells
const uword cons_val = $c3b4
const uword cons_next = $c65c
uword cons_count

; statement frame stack
ubyte[18] fr_kind
ubyte[18] fr_mode        ; 0=stmts, 1=choices
uword[18] fr_stmts       ; cons head (reversed)
ubyte[18] fr_defer       ; 1 if defer-prefixed
uword[18] fr_cond        ; cond / when-expr / repeat-count
uword[18] fr_then        ; saved then block (else frame)
uword[18] fr_var
uword[18] fr_lo
uword[18] fr_hi
uword[18] fr_choices     ; when: choices cons head
uword[18] fr_values      ; when_choice: values cons head
ubyte fr_sp
ubyte pending_defer
uword parse_result       ; parse_block's completed-root block (set by close_frame)

; program structure
uword prog_address
ubyte prog_target        ; 0=wendy2c, 1=nmos
uword prog_imports       ; cons of ident ids (reversed)
uword prog_vars          ; cons of vardecl node ids (reversed)
uword prog_enums         ; cons of enum node ids (reversed)
uword prog_structs       ; cons of struct node ids (reversed)
uword prog_subs          ; cons of sub node ids (reversed)

; ---- codegen symbol table (persistent across passes) ----
const uword sym_ident = $c904      ; var name ident id
const uword sym_type = $cf1c       ; type tag (TY_UBYTE / TY_BYTE / TY_UWORD)
const uword sym_addr = $d228       ; ZP address
const uword sym_scope = $d840      ; owning sub name ident (0 = module scope)
const uword sym_mkind = $de58      ; 0 = module var, 1 = param, 2 = local
const uword sym_is_const = $e164   ; 1 = compile-time const (no storage); folded
const uword sym_cval = $e470       ; const value (when sym_is_const)
const uword sym_arr_size = $ea88   ; element count if an array (0 = scalar); the
                         ; element type is in sym_type; mangle is p8a_
uword sym_count
uword zp_next            ; ZP bump allocator (from $40)
uword cur_scope          ; the sub being codegen'd (for var resolution)
; call-arg scratch (push args -> pop into param slots before the jsr).
uword[16] call_slot      ; param sym index per arg
ubyte[16] call_isw       ; 1 if that arg/param is uword
ubyte call_n
; sub table (registered in source order before codegen, so calls
; resolve and pass B emits non-main subs in p8c's order).
uword[232] sub_name       ; sub name ident id
ubyte[232] sub_kind       ; SUBK_SUB / MAIN / INLINE / ASMSUB / ASMSUB_BODY
ubyte[232] sub_ret        ; return type tag
uword[232] sub_addr       ; asmsub target address ($F0xx); else 0
uword sub_count
; builtin-call node stack: emit_builtin is non-reentrant (static
; locals), but a builtin arg may itself be a builtin, so the callnode
; is stacked and args re-derived after each nested codegen.
uword[8] bi_cn
ubyte bi_sp
; word-context call widening flag stack (word_dispatch is re-entered
; by a ubyte-returning call's own arg eval, clobbering its locals).
ubyte[8] wdn_stack
ubyte wdn_sp
; the sub currently being codegen'd -- its return type + name ident,
; for `return` (the per-sub .Lp8s_<name>_ret label).
ubyte cur_ret            ; current sub's return type tag
uword cur_ret_name       ; current sub's name ident id
; string pool: one label per string-literal *occurrence*, numbered
; in codegen encounter order (matching p8c's sema-walk order); the
; recorded str id indexes the parser's str_pool for the trailer.
uword[48] strpool_sid    ; str id for label N (p8c_str_N)
uword strpool_count
; byte-expression codegen work stack (replaces p8c's recursion):
; per entry a task -- 0 eval node, 1 binop-leaf, 2 pha, 3 sta tmp1,
; 4 pla, 5 binop-tmp1.
ubyte[36] cws_type
uword[36] cws_node
ubyte[36] cws_op
ubyte cws_sp
; word-expression codegen work stack (separate from the byte stack so
; a byte expression's @() address can drive a word eval without
; corrupting the byte stack -- the two never share state).
ubyte[36] wws_type
uword[36] wws_node
ubyte[36] wws_op
ubyte wws_sp
; statement work stack (control flow without recursion): a task is
; 0=emit stmt node, 1=emit label .L<kind>_<id>:, 2=emit jmp to it,
; 3=pop the loop-label stack.
ubyte[64] sws_type
uword[64] sws_a
uword[64] sws_b
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
uword label_seq          ; global local-label counter (p8c's _label_id)

uword[2] sub_snode
uword resident_sym_count
uword rec_kind
uword rec_snode
; serializer work stack
ubyte[2] ws_type       ; 0=node,1=close,2=newline,3=field line,4=literal text
uword[2] ws_node
ubyte[2] ws_depth
uword ws_sp

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

sub peek_src() -> ubyte {
    if peek_ok != 0 {
        return peek_buf
    }
    if src_eof != 0 {
        return 0
    }
    ubyte b
    b = sys_read(src_hand)
    if src_eof != 0 {
        return 0
    }
    peek_buf = b
    peek_ok = 1
    return peek_buf
}

sub out_byte(ubyte b) {
    sys_write(b, dst_hand)
}

; ---- character classes ----

sub is_digit(ubyte c) -> ubyte {
    if c >= $30 {
        if c <= $39 {
            return 1
        }
    }
    return 0
}

sub is_alpha_us(ubyte c) -> ubyte {
    if c >= $61 {
        if c <= $7a {
            return 1
        }
    }
    if c >= $41 {
        if c <= $5a {
            return 1
        }
    }
    if c == $5f {
        return 1
    }
    return 0
}

sub is_alnum_us(ubyte c) -> ubyte {
    if is_alpha_us(c) != 0 {
        return 1
    }
    return is_digit(c)
}

sub is_hexdig(ubyte c) -> ubyte {
    if is_digit(c) != 0 {
        return 1
    }
    if c >= $61 {
        if c <= $66 {
            return 1
        }
    }
    if c >= $41 {
        if c <= $46 {
            return 1
        }
    }
    return 0
}

sub hex_nibble(ubyte c) -> ubyte {
    if c >= $61 {
        return c - $57
    }
    if c >= $41 {
        return c - $37
    }
    return c - $30
}

; ---- decimal output ----

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

sub read_hex() {
    int_val = 0
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $5f {
            c = read_src()
        } else {
            if is_hexdig(c) != 0 {
                c = read_src()
                int_val = (int_val << 4) + hex_nibble(c)
            } else {
                return
            }
        }
    }
}

sub read_bin() {
    int_val = 0
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $5f {
            c = read_src()
        } else {
            if c == $30 {
                c = read_src()
                int_val = int_val << 1
            } else {
                if c == $31 {
                    c = read_src()
                    int_val = (int_val << 1) + 1
                } else {
                    return
                }
            }
        }
    }
}

sub read_dec() {
    int_val = 0
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $5f {
            c = read_src()
        } else {
            if is_digit(c) != 0 {
                c = read_src()
                int_val = (int_val << 3) + (int_val << 1) + (c - $30)
            } else {
                return
            }
        }
    }
}

sub decode_escape_val(ubyte e) -> ubyte {
    if e == 'n' { return '\n' }
    if e == 'r' { return '\r' }
    if e == 't' { return '\t' }
    if e == '0' { return $00 }
    if e == '\'' { return '\'' }
    if e == '\\' { return '\\' }
    if e == '"' { return '"' }
    if e == 'x' {
        ubyte h1
        ubyte h2
        h1 = read_src()
        h2 = read_src()
        return (hex_nibble(h1) << 4) + hex_nibble(h2)
    }
    return e
}

; ---- identifier + interning ----

sub read_ident() {
    name_len = 0
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if is_alnum_us(c) != 0 {
            c = read_src()
            if name_len < 64 {
                name_buf[(name_len as ubyte)] = c
                name_len = name_len + 1
            }
        } else {
            return
        }
    }
}

sub intern_name() -> uword {
    ; null-terminated ident pool: each name is bytes + a $00; the "id" is the
    ; pool OFFSET where the name starts (same name dedups to the same offset).
    uword off
    off = 0
    repeat {
        if off >= ident_pool_len {
            break
        }
        uword j
        ubyte match
        match = 1
        j = 0
        repeat {
            if j >= name_len {
                break
            }
            if peek($8c52 + (off + j)) != name_buf[(j as ubyte)] {
                match = 0
                break
            }
            j = j + 1
        }
        if match != 0 {
            if peek($8c52 + (off + name_len)) == 0 {
                return off
            }
        }
        repeat {
            if peek($8c52 + (off)) == 0 {
                off = off + 1
                break
            }
            off = off + 1
        }
    }
    uword id
    id = ident_pool_len
    uword k
    k = 0
    repeat {
        if k >= name_len {
            break
        }
        poke($8c52 + (ident_pool_len), name_buf[(k as ubyte)])
        ident_pool_len = ident_pool_len + 1
        k = k + 1
    }
    poke($8c52 + (ident_pool_len), 0)
    ident_pool_len = ident_pool_len + 1
    return id
}
; length of the null-terminated ident at pool offset `id`.

sub ident_len_at(uword id) -> uword {
    uword n
    n = 0
    repeat {
        if peek($8c52 + (id + n)) == 0 {
            break
        }
        n = n + 1
    }
    return n
}

; classify_name: is the just-lexed identifier (name_buf, name_len bytes) a
; keyword? A parallel pair of initialized tables -- the keyword strings and
; their token codes -- replaces the old per-length if-chains; kw_match does the
; counted-buffer compare (name_buf has a length, the keyword is
; null-terminated). Behaviour is identical (no match -> TK_IDENT). The tables
; are static data the host compiler lays down once, so this is far smaller than
; the ~50 inline byte compares it replaces.

; keyword recognition as an if-chain of strings.compare (matching p1.p8). A
; data-initialized lookup table can't be used: the pipeline reserves every
; array as zero-filled storage (emit_array_zeros), so it cannot self-host a
; table whose contents matter. The if-chain uses only string literals, which
; the pipeline does emit.
sub kw_is(uword kw) -> ubyte {
    if strings.compare(&name_buf, kw) == 0 {
        return 1
    }
    return 0
}

sub classify_name() -> ubyte {
    name_buf[(name_len as ubyte)] = 0                  ; NUL-terminate for strings.compare
    if kw_is("if") != 0 { return TK_KIF }
    if kw_is("in") != 0 { return TK_KIN }
    if kw_is("or") != 0 { return TK_KOR }
    if kw_is("to") != 0 { return TK_KTO }
    if kw_is("and") != 0 { return TK_KAND }
    if kw_is("for") != 0 { return TK_KFOR }
    if kw_is("not") != 0 { return TK_KNOT }
    if kw_is("str") != 0 { return TK_KSTR }
    if kw_is("sub") != 0 { return TK_KSUB }
    if kw_is("xor") != 0 { return TK_KXOR }
    if kw_is("bool") != 0 { return TK_KBOOL }
    if kw_is("byte") != 0 { return TK_KBYTE }
    if kw_is("else") != 0 { return TK_KELSE }
    if kw_is("enum") != 0 { return TK_KENUM }
    if kw_is("main") != 0 { return TK_KMAIN }
    if kw_is("true") != 0 { return TK_TRUE }
    if kw_is("void") != 0 { return TK_KVOID }
    if kw_is("when") != 0 { return TK_KWHEN }
    if kw_is("break") != 0 { return TK_KBREAK }
    if kw_is("const") != 0 { return TK_KCONST }
    if kw_is("defer") != 0 { return TK_KDEFER }
    if kw_is("false") != 0 { return TK_FALSE }
    if kw_is("ubyte") != 0 { return TK_KUBYTE }
    if kw_is("uword") != 0 { return TK_KUWORD }
    if kw_is("while") != 0 { return TK_KWHILE }
    if kw_is("asmsub") != 0 { return TK_KASMSUB }
    if kw_is("inline") != 0 { return TK_KINLINE }
    if kw_is("repeat") != 0 { return TK_KREPEAT }
    if kw_is("return") != 0 { return TK_KRETURN }
    if kw_is("struct") != 0 { return TK_KSTRUCT }
    if kw_is("continue") != 0 { return TK_KCONTINUE }
    if kw_is("extsub") != 0 { return TK_KEXTSUB }
    if kw_is("as") != 0 { return TK_KAS }
    return TK_IDENT
}

; classify a directive name (already copied into name_buf):
; 0=address, 1=output, 2=import, 4=other.
sub dir_classify() -> ubyte {
    name_buf[(name_len as ubyte)] = 0                  ; NUL-terminate for strings.compare
    if kw_is("address") != 0 { return 0 }
    if kw_is("output") != 0 { return 1 }
    if kw_is("import") != 0 { return 2 }
    return 4
}

; ---- token storage + lexer ----

sub push_token(ubyte kind, uword val) {
    ntok_kind = kind
    ntok_val = val
}

; intern the candidate bytes at [start, str_pool_len) into the null-terminated
; string pool: if they match an existing entry, roll str_pool_len back and
; return its offset; else NUL-terminate the new entry and return start.
sub intern_strpool(uword start) -> uword {
    uword slen
    slen = str_pool_len - start
    uword off
    off = 0
    repeat {
        if off >= start { break }
        uword sk
        ubyte sm
        sm = 1
        sk = 0
        repeat {
            if sk >= slen { break }
            if peek($a252 + (off + sk)) != peek($a252 + (start + sk)) { sm = 0 break }
            sk = sk + 1
        }
        if sm != 0 {
            if peek($a252 + (off + slen)) == 0 {
                str_pool_len = start
                return off
            }
        }
        repeat {
            if peek($a252 + (off)) == 0 { off = off + 1 break }
            off = off + 1
        }
    }
    poke($a252 + (str_pool_len), 0)
    str_pool_len = str_pool_len + 1
    return start
}

; is c an asm-line "horizontal whitespace" byte (stripped at line ends)?
sub asm_ws(ubyte c) -> ubyte {
    if c == ' ' { return 1 }
    if c == '\t' { return 1 }
    if c == '\r' { return 1 }
    return 0
}

; capture a raw `%asm {{ ... }}` body (the leading `{{` already consumed) up to
; the closing `}}` (consumed), normalize it (strip each line, drop blank lines,
; join with '\n') into the string pool at [start..), and return the interned
; offset. Mirrors p8c's lexer normalization so a raw block emits the same asm
; as the equivalent quoted one. Streamed (no line buffer): leading whitespace is
; skipped, intra-line whitespace runs are deferred (emitted only before the next
; content byte), and a deferred run dropped at end-of-line strips trailing ws.
sub build_asm_body() -> uword {
    uword start
    start = str_pool_len
    ubyte started      ; any content byte emitted overall (for the '\n' joiner)
    ubyte sol          ; before any content byte on the current line
    uword sp           ; deferred intra-line whitespace count
    started = 0
    sol = 1
    sp = 0
    repeat {
        ubyte c
        c = read_src()
        if src_eof != 0 { break }
        if c == '}' {
            if peek_src() == '}' { c = read_src()  break }    ; closing `}}`
        }
        if c == '\n' { sol = 1  sp = 0  continue }
        if c == '\r' { continue }
        if asm_ws(c) != 0 {
            if sol == 0 { sp = sp + 1 }                       ; defer (skip if leading)
            continue
        }
        if sol != 0 {
            if started != 0 {
                poke($a252 + (str_pool_len), '\n')
                str_pool_len = str_pool_len + 1
            }
            sol = 0
        } else {
            repeat {
                if sp == 0 { break }
                poke($a252 + (str_pool_len), ' ')
                str_pool_len = str_pool_len + 1
                sp = sp - 1
            }
        }
        poke($a252 + (str_pool_len), c)
        str_pool_len = str_pool_len + 1
        started = 1
    }
    return intern_strpool(start)
}

; lex `%asm` whose body is `{{ ... }}`: skip to and consume `{{`; if the body is
; a quoted string (legacy form) queue just `{ {` and let the normal lexer read
; the STR + `}}`; otherwise capture the raw body and queue `{ { STR } }`. The
; DIRECTIVE token itself is returned by this call (ntok_*).
sub skip_asm_ws() {
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 { break }
        if asm_ws(c) == 0 {
            if c != '\n' { break }
        }
        c = read_src()
    }
}

sub lex_asm_directive(uword nameid) {
    ntok_kind = TK_DIRECTIVE
    ntok_val = nameid
    skip_asm_ws()                           ; up to `{{`
    ubyte b
    b = read_src()                          ; first '{'
    b = read_src()                          ; second '{'
    skip_asm_ws()                           ; to the raw body
    pend_i = 0
    pendk[0] = TK_LBRACE  pendv[0] = 0
    pendk[1] = TK_LBRACE  pendv[1] = 0
    uword off
    off = build_asm_body()
    pendk[2] = TK_STR     pendv[2] = off
    pendk[3] = TK_RBRACE  pendv[3] = 0
    pendk[4] = TK_RBRACE  pendv[4] = 0
    pend_n = 5
}

; produce one token into ntok_kind / ntok_val (TK_EOF at end of input).

; lex a `%...` token (the leading '%' already seen): %0.../%1... binary int,
; %asm -> inline-asm directive, %name -> TK_DIRECTIVE, else TK_OTHER. Split out
; of next_raw_token to keep its node count under the per-sub arena cap.
sub lex_directive() {
    ubyte c
    c = read_src()
    ubyte c2
    c2 = peek_src()
    if src_eof == 0 {
        if c2 == '0' { read_bin()  push_token(TK_INT, int_val)  return }
        if c2 == '1' { read_bin()  push_token(TK_INT, int_val)  return }
        if is_alpha_us(c2) != 0 {
            read_ident()
            ubyte is_asm
            is_asm = 0
            if name_len == 3 {
                if name_buf[0] == 'a' {
                    if name_buf[1] == 's' {
                        if name_buf[2] == 'm' { is_asm = 1 }
                    }
                }
            }
            uword nameid
            nameid = intern_name()
            if is_asm != 0 {
                lex_asm_directive(nameid)
                return
            }
            push_token(TK_DIRECTIVE, nameid)
            return
        }
    }
    push_token(TK_OTHER, 0)
}

; lex a `"..."` string literal (the opening quote already seen) into the
; null-terminated string pool; a literal's "id" is the pool OFFSET where it
; starts, so identical content dedups to that same offset and the pool holds
; each distinct value once (no str_off/len index arrays). The emitted
; p8c_str_N label is still assigned at codegen-encounter order by
; intern_str_label, so this is transparent to output. Split out of
; next_raw_token for the per-sub arena cap.
sub lex_strlit() {
    ubyte c
    c = read_src()
    uword start
    start = str_pool_len
    repeat {
        c = read_src()
        if src_eof != 0 { break }
        if c == '"' { break }
        ubyte rb
        if c == '\\' {
            ubyte se
            se = read_src()
            rb = decode_escape_val(se)
        } else {
            rb = c
        }
        poke($a252 + (str_pool_len), rb)
        str_pool_len = str_pool_len + 1
    }
    push_token(TK_STR, intern_strpool(start))
}

sub next_raw_token() {
    if pend_i < pend_n {
        ntok_kind = pendk[(pend_i as ubyte)]
        ntok_val = pendv[(pend_i as ubyte)]
        pend_i = pend_i + 1
        return
    }
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            ntok_kind = TK_EOF
            ntok_val = 0
            return
        }
        if c == ' ' { c = read_src()  continue }
        if c == '\t' { c = read_src()  continue }
        if c == '\n' { c = read_src()  continue }
        if c == '\r' { c = read_src()  continue }
        if c == ';' {
            repeat {
                c = read_src()
                if src_eof != 0 { break }
                if c == '\n' { break }
            }
            continue
        }
        if c == '%' { lex_directive()  return }    ; '%'
        if c == '$' {
            c = read_src()
            read_hex()
            push_token(TK_INT, int_val)
            return
        }
        if is_digit(c) != 0 {
            read_dec()
            push_token(TK_INT, int_val)
            return
        }
        if c == '\'' {
            c = read_src()
            c = read_src()
            if c == '\\' {
                ubyte e
                e = read_src()
                int_val = decode_escape_val(e)
            } else {
                int_val = c
            }
            c = read_src()
            push_token(TK_INT, int_val)
            return
        }
        if c == '"' {
            lex_strlit()
            return
        }
        if is_alpha_us(c) != 0 {
            read_ident()
            ubyte k
            k = classify_name()
            if k == TK_IDENT {
                push_token(TK_IDENT, intern_name())
            } else {
                push_token(k, 0)
            }
            return
        }
        c = read_src()
        lex_operator(c)
        return
    }
}

sub lex_operator(ubyte c) {
    ubyte c2
    if c == '*' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_OTHER, 0)  return }   ; *=
        push_token(TK_STAR, 0)
        return
    }
    if c == '+' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_PLUSEQ, 0)  return }
        if c2 == '+' { c2 = read_src()  push_token(TK_OTHER, 0)  return }
        push_token(TK_PLUS, 0)
        return
    }
    if c == '&' {
        c2 = peek_src()
        if c2 == '&' { c2 = read_src()  push_token(TK_OTHER, 0)  return }
        if c2 == '=' { c2 = read_src()  push_token(TK_ANDEQ, 0)  return }
        push_token(TK_AMP, 0)
        return
    }
    if c == '|' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_OREQ, 0)  return }
        push_token(TK_PIPE, 0)
        return
    }
    if c == '^' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_XOREQ, 0)  return }
        push_token(TK_CARET, 0)
        return
    }
    if c == '-' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_MINUSEQ, 0)  return }
        if c2 == '>' { c2 = read_src()  push_token(TK_ARROW, 0)  return }
        if c2 == '-' { c2 = read_src()  push_token(TK_OTHER, 0)  return }
        push_token(TK_MINUS, 0)
        return
    }
    lex_operator2(c)
}

; comparison/shift/assign operators, split out of lex_operator to keep each
; sub's node count under the per-sub arena cap.
sub lex_operator2(ubyte c) {
    ubyte c2
    if c == '(' { push_token(TK_LPAREN, 0)  return }
    if c == ')' { push_token(TK_RPAREN, 0)  return }
    if c == '[' { push_token(TK_LBRACK, 0)  return }
    if c == ']' { push_token(TK_RBRACK, 0)  return }
    if c == '{' { push_token(TK_LBRACE, 0)  return }
    if c == '}' { push_token(TK_RBRACE, 0)  return }
    if c == ',' { push_token(TK_COMMA, 0)  return }
    if c == '@' { push_token(TK_AT, 0)  return }
    if c == '.' { push_token(TK_DOT, 0)  return }
    if c == '~' { push_token(TK_TILDE, 0)  return }
    if c == '<' {
        c2 = peek_src()
        if c2 == '<' {
            c2 = read_src()
            c2 = peek_src()
            if c2 == '=' { c2 = read_src()  push_token(TK_SHLEQ, 0)  return }
            push_token(TK_SHL, 0)
            return
        }
        if c2 == '=' { c2 = read_src()  push_token(TK_LE, 0)  return }
        push_token(TK_LT, 0)
        return
    }
    if c == '>' {
        c2 = peek_src()
        if c2 == '>' {
            c2 = read_src()
            c2 = peek_src()
            if c2 == '=' { c2 = read_src()  push_token(TK_SHREQ, 0)  return }
            push_token(TK_SHR, 0)
            return
        }
        if c2 == '=' { c2 = read_src()  push_token(TK_GE, 0)  return }
        push_token(TK_GT, 0)
        return
    }
    if c == '=' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_EQ, 0)  return }
        push_token(TK_ASSIGN, 0)
        return
    }
    if c == '!' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_NE, 0)  return }
        push_token(TK_OTHER, 0)
        return
    }
    push_token(TK_OTHER, 0)
}

; ---- token cursor (over the streaming 2-token window) ----

sub cur_kind() -> ubyte {
    return tk0_kind
}

sub cur_val() -> uword {
    return tk0_val
}

sub peek1_kind() -> ubyte {
    return tk1_kind
}

sub advance() {
    tk0_kind = tk1_kind
    tk0_val = tk1_val
    next_raw_token()
    tk1_kind = ntok_kind
    tk1_val = ntok_val
}

sub lex_init() {
    pend_i = 0
    pend_n = 0
    next_raw_token()
    tk0_kind = ntok_kind
    tk0_val = ntok_val
    next_raw_token()
    tk1_kind = ntok_kind
    tk1_val = ntok_val
}

; ---- node arena ----

sub new_node(ubyte kind, ubyte op, uword a, uword b) -> uword {
    uword id
    id = node_count
    poke($b252 + (id), kind)
    poke($b40f + (id), op)
    pokew($b5cc + ((id) << 1), a)
    pokew($b946 + ((id) << 1), b)
    pokew($bcc0 + ((id) << 1), 0)
    pokew($c03a + ((id) << 1), 0)
    node_count = node_count + 1
    return id
}

; ---- cons cells ----

sub cons_prepend(uword head, uword val) -> uword {
    uword c
    c = cons_count
    pokew($c3b4 + ((c) << 1), val)
    pokew($c65c + ((c) << 1), head)
    cons_count = cons_count + 1
    return c
}

; ---- operator precedence ----

sub bin_prec(ubyte k) -> ubyte {
    if k == TK_KOR { return 0 }
    if k == TK_KXOR { return 0 }
    if k == TK_KAND { return 1 }
    if k == TK_EQ { return 2 }
    if k == TK_NE { return 2 }
    if k == TK_LT { return 3 }
    if k == TK_LE { return 3 }
    if k == TK_GT { return 3 }
    if k == TK_GE { return 3 }
    if k == TK_PIPE { return 4 }
    if k == TK_CARET { return 5 }
    if k == TK_AMP { return 6 }
    if k == TK_SHL { return 7 }
    if k == TK_SHR { return 7 }
    if k == TK_PLUS { return 8 }
    if k == TK_MINUS { return 8 }
    if k == TK_STAR { return 9 }
    return 255
}

sub is_binop(ubyte k) -> ubyte {
    if bin_prec(k) == 255 {
        return 0
    }
    return 1
}

; ---- shunting-yard ----

sub push_operand(uword node) {
    operand_stack[(operand_sp as ubyte)] = node
    operand_sp = operand_sp + 1
}

sub push_op(ubyte k, ubyte op, ubyte prec) {
    op_kind[(op_sp as ubyte)] = k
    op_op[(op_sp as ubyte)] = op
    op_prec[(op_sp as ubyte)] = prec
    op_sp = op_sp + 1
}

sub push_marker(ubyte k, uword floor) {
    op_kind[(op_sp as ubyte)] = k
    op_floor[(op_sp as ubyte)] = floor
    op_b[(op_sp as ubyte)] = 0
    op_sp = op_sp + 1
}

sub apply_top() {
    op_sp = op_sp - 1
    ubyte k
    k = op_kind[(op_sp as ubyte)]
    if k == OPK_BINOP {
        operand_sp = operand_sp - 1
        uword rhs
        rhs = operand_stack[(operand_sp as ubyte)]
        operand_sp = operand_sp - 1
        uword lhs
        lhs = operand_stack[(operand_sp as ubyte)]
        operand_stack[(operand_sp as ubyte)] = new_node(ND_BINOP, op_op[(op_sp as ubyte)], lhs, rhs)
        operand_sp = operand_sp + 1
    } else {
        operand_sp = operand_sp - 1
        uword operand
        operand = operand_stack[(operand_sp as ubyte)]
        operand_stack[(operand_sp as ubyte)] = new_node(ND_UNOP, op_op[(op_sp as ubyte)], operand, 0)
        operand_sp = operand_sp + 1
    }
}

sub top_prec() -> ubyte {
    if op_kind[(op_sp - 1 as ubyte)] == OPK_UNOP {
        return UNARY_PREC
    }
    return op_prec[(op_sp - 1 as ubyte)]
}

sub reduce_to_marker() {
    repeat {
        if op_sp == 0 {
            return
        }
        if op_kind[(op_sp - 1 as ubyte)] >= OPK_LPAREN {
            return
        }
        apply_top()
    }
}

sub append_ident_to_namebuf(uword id) {
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
        name_buf[(name_len as ubyte)] = peek($8c52 + (off + j))
        name_len = name_len + 1
        j = j + 1
    }
}
; append the (possibly dotted) ident currently at the cursor into path_buf.

sub append_ident_to_pathbuf(uword id) {
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
        path_buf[(path_len as ubyte)] = peek($8c52 + (off + j))
        path_len = path_len + 1
        j = j + 1
    }
}
; Read IDENT (DOT IDENT)* at the cursor, returning the interned id of the
; full (possibly dotted) text. Builds into path_buf, NOT name_buf: each
; advance() lexes a token ahead, and the lexer reuses name_buf, so using
; name_buf across the advances would intern a clobbered (wrong) name.

sub read_dotted_path() -> uword {
    path_len = 0
    append_ident_to_pathbuf(cur_val())
    advance()
    repeat {
        if cur_kind() != TK_DOT {
            break
        }
        if peek1_kind() != TK_IDENT {
            break
        }
        advance()
        path_buf[(path_len as ubyte)] = $2e
        path_len = path_len + 1
        append_ident_to_pathbuf(cur_val())
        advance()
    }
    ; copy into name_buf right before interning (now immune to lookahead)
    name_len = path_len
    uword i
    i = 0
    repeat {
        if i >= path_len {
            break
        }
        name_buf[(i as ubyte)] = path_buf[(i as ubyte)]
        i = i + 1
    }
    return intern_name()
}

sub close_index() {
    op_sp = op_sp - 1
    operand_sp = operand_sp - 1
    uword index
    index = operand_stack[(operand_sp as ubyte)]
    operand_sp = operand_sp - 1
    uword array
    array = operand_stack[(operand_sp as ubyte)]
    advance()
    uword node
    node = new_node(ND_INDEX, 0, array, index)
    if cur_kind() == TK_DOT {
        if peek1_kind() == TK_IDENT {
            advance()
            pokew($bcc0 + ((node) << 1), cur_val())
            poke($b40f + (node), 1)
            advance()
        }
    }
    push_operand(node)
}

sub close_call() {
    uword head
    uword path
    uword floor
    head = op_b[(op_sp - 1 as ubyte)]
    path = op_a[(op_sp - 1 as ubyte)]
    floor = op_floor[(op_sp - 1 as ubyte)]
    if operand_sp > floor {
        operand_sp = operand_sp - 1
        head = cons_prepend(head, operand_stack[(operand_sp as ubyte)])
    }
    op_sp = op_sp - 1
    uword node
    node = new_node(ND_CALL, 0, path, head)
    push_operand(node)
}

; parser shunting-yard state shared with parse_operand (promoted from
; parse_expr locals so the operand cases can live in their own sub, keeping
; each sub's node count under the per-sub arena cap).
ubyte expect_operand
ubyte index_ok

; the operand-position cases of parse_expr's shunting yard (leaf operands and
; prefix operators). Returns 1 if the current token is not a valid operand
; start (caller breaks the expression loop), else 0 (caller continues).
sub parse_operand(ubyte t) -> ubyte {
    index_ok = 0
    if t == TK_INT {
        push_operand(new_node(ND_INT, 0, cur_val(), 0))
        advance()
        expect_operand = 0
        return 0
    }
    if t == TK_STR {
        push_operand(new_node(ND_STR, 0, cur_val(), 0))
        advance()
        expect_operand = 0
        return 0
    }
    if t == TK_TRUE {
        push_operand(new_node(ND_BOOL, 0, 1, 0))
        advance()
        expect_operand = 0
        return 0
    }
    if t == TK_FALSE {
        push_operand(new_node(ND_BOOL, 0, 0, 0))
        advance()
        expect_operand = 0
        return 0
    }
    if t == TK_KNOT {
        push_op(OPK_UNOP, UN_NOT, 0)
        advance()
        return 0
    }
    if t == TK_TILDE {
        push_op(OPK_UNOP, UN_INV, 0)
        advance()
        return 0
    }
    if t == TK_MINUS {
        push_op(OPK_UNOP, UN_NEG, 0)
        advance()
        return 0
    }
    if t == TK_AMP {
        advance()
        if cur_kind() == TK_IDENT {
            uword nid
            nid = cur_val()
            advance()
            push_operand(new_node(ND_ADDROF, 0, nid, 0))
            expect_operand = 0
        }
        return 0
    }
    if t == TK_AT {
        advance()
        if cur_kind() == TK_LPAREN {
            advance()
        }
        push_marker(OPK_MEMAT, operand_sp)
        return 0
    }
    if t == TK_LPAREN {
        push_marker(OPK_LPAREN, operand_sp)
        advance()
        return 0
    }
    if t == TK_IDENT {
        uword path
        path = read_dotted_path()
        if cur_kind() == TK_LPAREN {
            advance()
            push_marker(OPK_CALL, operand_sp)
            op_a[(op_sp - 1 as ubyte)] = path
        } else {
            push_operand(new_node(ND_IDENT, 0, path, 0))
            expect_operand = 0
            index_ok = 1
        }
        return 0
    }
    return 1
}

; handle a `)` in the shunting-yard loop: reduce to the open marker and close
; it (grouping paren / @() memat / call arglist). Returns 1 if parse_expr should
; stop (unbalanced / not our paren), 0 to continue. Split out for the arena cap.
sub pe_rparen() -> ubyte {
    reduce_to_marker()
    if op_sp == 0 {
        return 1
    }
    ubyte mk
    mk = op_kind[(op_sp - 1 as ubyte)]
    if mk == OPK_LPAREN {
        op_sp = op_sp - 1
        advance()
        expect_operand = 0
        index_ok = 0
        return 0
    }
    if mk == OPK_MEMAT {
        op_sp = op_sp - 1
        operand_sp = operand_sp - 1
        push_operand(new_node(ND_MEMAT, 0, operand_stack[(operand_sp as ubyte)], 0))
        advance()
        expect_operand = 0
        index_ok = 0
        return 0
    }
    if mk == OPK_CALL {
        close_call()
        advance()
        expect_operand = 0
        index_ok = 0
        return 0
    }
    return 1
}

; handle `expr as TYPE` in the shunting-yard loop: lowest precedence -- reduce
; everything down to the enclosing marker, then wrap the resulting operand in an
; ND_CAST. Split out of parse_expr for the per-sub arena cap.
sub pe_cast() {
    repeat {
        if op_sp == 0 { break }
        if op_kind[(op_sp - 1 as ubyte)] >= OPK_LPAREN { break }
        apply_top()
    }
    advance()                              ; 'as'
    ubyte tt
    tt = type_tag(cur_kind())
    advance()                              ; type keyword
    operand_sp = operand_sp - 1
    push_operand(new_node(ND_CAST, tt, operand_stack[(operand_sp as ubyte)], 0))
    expect_operand = 0
    index_ok = 0
}

sub parse_expr() -> uword {
    operand_sp = 0
    op_sp = 0
    expect_operand = 1
    index_ok = 0

    repeat {
        ubyte t
        t = cur_kind()

        if t == TK_RPAREN {
            if pe_rparen() != 0 { break }
            continue
        }
        if t == TK_RBRACK {
            reduce_to_marker()
            if op_sp == 0 {
                break
            }
            if op_kind[(op_sp - 1 as ubyte)] != OPK_LBRACK {
                break
            }
            close_index()
            expect_operand = 0
            index_ok = 0
            continue
        }
        if t == TK_COMMA {
            reduce_to_marker()
            if op_sp == 0 {
                break
            }
            if op_kind[(op_sp - 1 as ubyte)] != OPK_CALL {
                break
            }
            operand_sp = operand_sp - 1
            op_b[(op_sp - 1 as ubyte)] = cons_prepend(op_b[(op_sp - 1 as ubyte)], operand_stack[(operand_sp as ubyte)])
            advance()
            expect_operand = 1
            index_ok = 0
            continue
        }

        if expect_operand != 0 {
            if parse_operand(t) != 0 {
                break
            }
            continue
        }

        if t == TK_KAS {
            pe_cast()
            continue
        }
        if is_binop(t) != 0 {
            ubyte prec
            prec = bin_prec(t)
            repeat {
                if op_sp == 0 {
                    break
                }
                if op_kind[(op_sp - 1 as ubyte)] >= OPK_LPAREN {
                    break
                }
                if top_prec() < prec {
                    break
                }
                apply_top()
            }
            push_op(OPK_BINOP, t, prec)
            advance()
            expect_operand = 1
            index_ok = 0
            continue
        }
        if t == TK_LBRACK {
            if index_ok != 0 {
                push_marker(OPK_LBRACK, operand_sp)
                advance()
                expect_operand = 1
                index_ok = 0
                continue
            }
            break
        }
        break
    }

    repeat {
        if op_sp == 0 {
            break
        }
        apply_top()
    }
    operand_sp = operand_sp - 1
    return operand_stack[(operand_sp as ubyte)]
}


; ---- type keyword -> type tag ----

sub type_tag(ubyte k) -> ubyte {
    if k == TK_KUBYTE { return TY_UBYTE }
    if k == TK_KBYTE { return TY_BYTE }
    if k == TK_KUWORD { return TY_UWORD }
    if k == TK_KBOOL { return TY_BOOL }
    if k == TK_KVOID { return TY_VOID }
    if k == TK_KSTR { return TY_STR }
    return TY_UBYTE
}

sub is_type_kw(ubyte k) -> ubyte {
    if k == TK_KUBYTE { return 1 }
    if k == TK_KBYTE { return 1 }
    if k == TK_KUWORD { return 1 }
    return 0
}

sub assign_code(ubyte k) -> ubyte {
    return k
}

; ---- leaf statements ----
uword last_simple

; parse a var decl (type kw already current). Returns vardecl node.

sub parse_var_decl() -> uword {
    ubyte tag
    tag = type_tag(cur_kind())
    advance()
    uword arrsize
    arrsize = 0
    if cur_kind() == TK_LBRACK {
        advance()                           ; consume '['
        if cur_kind() == TK_RBRACK {
            arrsize = 0                     ; `[]` -- size inferred from initializer
        } else {
            arrsize = cur_val()             ; INT
            advance()                       ; consume INT
        }
        advance()                           ; consume ']'
    }
    uword nameid
    nameid = cur_val()
    advance()                               ; consume name IDENT
    uword init
    init = 0
    ubyte init_arr
    init_arr = 0
    if cur_kind() == TK_ASSIGN {
        advance()
        if cur_kind() == TK_LBRACK {
            init = parse_array_lit()
            init_arr = 1
        } else {
            init = parse_expr()
        }
    }
    ; `type[] name = [...]` -- size omitted: infer the element count from the
    ; initializer's cons list so build_symbols treats it as an array (not a
    ; scalar) and reserves the right storage.
    if arrsize == 0 {
        if init_arr != 0 {
            uword cc
            cc = peekw($b5cc + ((init) << 1))      ; ND_ARRAYLIT node_a = cons head
            repeat {
                if cc == 0 { break }
                arrsize = arrsize + 1
                cc = peekw($c65c + ((cc) << 1))    ; cons_next
            }
        }
    }
    uword node
    node = new_node(ND_VARDECL, tag, nameid, init)
    pokew($bcc0 + ((node) << 1), arrsize)
    return node
}

; parse a data-initialized array literal `[e0, e1, ...]` (cursor on '[') into an
; ND_ARRAYLIT whose node_a is the element cons head (reversed -- emit reverses).
; Elements are const expressions (int / string literal / const ident).
sub parse_array_lit() -> uword {
    advance()                               ; '['
    uword head
    head = 0
    repeat {
        if cur_kind() == TK_RBRACK {
            break
        }
        head = cons_prepend(head, parse_expr())
        if cur_kind() == TK_COMMA {
            advance()
        } else {
            break
        }
    }
    advance()                               ; ']'
    return new_node(ND_ARRAYLIT, 0, head, 0)
}

; parse `%asm{{ "text" }}` -> inline asm node.

sub parse_inline_asm() -> uword {
    advance()                               ; consume DIRECTIVE asm
    advance()                               ; {
    advance()                               ; {
    uword sid
    sid = cur_val()                         ; STR
    advance()
    advance()                               ; }
    advance()                               ; }
    return new_node(ND_INLINEASM, 0, sid, 0)
}

; parse assignment-or-expression statement -> node (Assign or ExprStmt).
; Rewind-free: parse the whole LHS as an expression (which already yields
; an Ident / Index / MemAt target, or a Call etc.), then check whether an
; assignment operator follows. Assignment operators are not expression
; operators, so parse_expr stops right before them -- no backtracking
; needed (the streaming lexer has no rewind).

sub parse_assign_or_expr() -> uword {
    uword e
    e = parse_expr()
    ubyte k
    k = cur_kind()
    if k == TK_ASSIGN {
        advance()
        hoist_arg = parse_expr()
        return new_node(ND_ASSIGN, TK_ASSIGN, e, hoist_arg)
    }
    if k >= TK_PLUSEQ {
        if k <= TK_SHREQ {
            advance()
            hoist_arg = parse_expr()
            return new_node(ND_ASSIGN, k, e, hoist_arg)
        }
    }
    return new_node(ND_EXPRSTMT, 0, e, 0)
}

; ---- frame stack ----

sub fr_attach(uword node) {
    fr_stmts[(fr_sp - 1 as ubyte)] = cons_prepend(fr_stmts[(fr_sp - 1 as ubyte)], node)
}

sub fr_push_block(ubyte kind, ubyte deferflag) {
    fr_kind[(fr_sp as ubyte)] = kind
    fr_mode[(fr_sp as ubyte)] = 0
    fr_stmts[(fr_sp as ubyte)] = 0
    fr_defer[(fr_sp as ubyte)] = deferflag
    fr_sp = fr_sp + 1
}

; dispatch one statement; returns 1 if it opened a compound (pushed a
; frame), else parses a leaf into last_simple and returns 0.

; parse a `for VAR in LO to HI {` header and push its FR_FOR frame. Split out
; of stmt_dispatch for the per-sub arena cap.
sub sd_for(ubyte deferflag) {
    advance()
    uword varid
    varid = cur_val()
    advance()                           ; IDENT
    advance()                           ; 'in'
    uword lo
    lo = parse_expr()
    advance()                           ; 'to'
    uword hi
    hi = parse_expr()
    advance()                           ; '{'
    fr_push_block(FR_FOR, deferflag)
    fr_var[(fr_sp - 1 as ubyte)] = varid
    fr_lo[(fr_sp - 1 as ubyte)] = lo
    fr_hi[(fr_sp - 1 as ubyte)] = hi
}

; parse a `return [value]` statement into last_simple. A value follows unless
; the next token is '}' or a keyword other than true/false. Split out of
; stmt_dispatch for the per-sub arena cap.
sub sd_return() {
    advance()
    uword val
    val = 0
    ubyte nk
    nk = cur_kind()
    if nk == TK_RBRACE {
        last_simple = new_node(ND_RETURN, 0, 0, 0)
        return
    }
    if nk == TK_TRUE {
        val = parse_expr()
    } else {
        if nk == TK_FALSE {
            val = parse_expr()
        } else {
            if nk >= TK_KUBYTE {
                ; a keyword that isn't true/false ends the return
                last_simple = new_node(ND_RETURN, 0, 0, 0)
                return
            }
            val = parse_expr()
        }
    }
    last_simple = new_node(ND_RETURN, 0, val, 0)
}

sub stmt_dispatch(ubyte deferflag) -> ubyte {
    ubyte t
    t = cur_kind()
    if t == TK_DIRECTIVE {
        last_simple = parse_inline_asm()
        return 0
    }
    if is_type_kw(t) != 0 {
        last_simple = parse_var_decl()
        return 0
    }
    if t == TK_KIF {
        advance()
        uword cond
        cond = parse_expr()
        advance()                           ; '{'
        fr_push_block(FR_THEN, deferflag)
        fr_cond[(fr_sp - 1 as ubyte)] = cond
        return 1
    }
    if t == TK_KWHILE {
        advance()
        uword wcond
        wcond = parse_expr()
        advance()
        fr_push_block(FR_WHILE, deferflag)
        fr_cond[(fr_sp - 1 as ubyte)] = wcond
        return 1
    }
    if t == TK_KWHEN {
        advance()
        uword wexpr
        wexpr = parse_expr()
        advance()                           ; '{'
        fr_kind[(fr_sp as ubyte)] = FR_WHEN
        fr_mode[(fr_sp as ubyte)] = 1
        fr_defer[(fr_sp as ubyte)] = deferflag
        fr_cond[(fr_sp as ubyte)] = wexpr
        fr_choices[(fr_sp as ubyte)] = 0
        fr_sp = fr_sp + 1
        return 1
    }
    if t == TK_KREPEAT {
        advance()
        uword count
        count = 0
        if cur_kind() != TK_LBRACE {
            count = parse_expr()
        }
        advance()                           ; '{'
        fr_push_block(FR_REPEAT, deferflag)
        fr_cond[(fr_sp - 1 as ubyte)] = count
        return 1
    }
    if t == TK_KFOR {
        sd_for(deferflag)
        return 1
    }
    if t == TK_KBREAK {
        advance()
        last_simple = new_node(ND_BREAK, 0, 0, 0)
        return 0
    }
    if t == TK_KCONTINUE {
        advance()
        last_simple = new_node(ND_CONTINUE, 0, 0, 0)
        return 0
    }
    if t == TK_KRETURN {
        sd_return()
        return 0
    }
    last_simple = parse_assign_or_expr()
    return 0
}

; the frame-stack block driver: parse a `{ ... }` block (and everything
; nested) into a Block node; returns its node id.

; one iteration of a `when` body (mode 1): close the when on '}', else parse a
; choice's value list and push its FR_CHOICE frame. Split out of parse_block to
; keep each sub's node count under the per-sub arena cap.
sub parse_when_choice(ubyte fi) {
    ubyte t
    uword node
    t = cur_kind()
    if t == TK_RBRACE {
        advance()
        node = new_node(ND_WHEN, 0, fr_cond[(fi as ubyte)], fr_choices[(fi as ubyte)])
        ubyte df
        df = fr_defer[(fi as ubyte)]
        fr_sp = fr_sp - 1
        if df != 0 {
            node = new_node(ND_DEFER, 0, node, 0)
        }
        fr_attach(node)
        return
    }
    uword vals
    vals = 0
    if t == TK_KELSE {
        advance()
    } else {
        hoist_arg = parse_expr()
        vals = cons_prepend(vals, hoist_arg)
        repeat {
            if cur_kind() != TK_COMMA {
                break
            }
            advance()
            hoist_arg = parse_expr()
            vals = cons_prepend(vals, hoist_arg)
        }
    }
    advance()                       ; '->'
    advance()                       ; '{'
    fr_kind[(fr_sp as ubyte)] = FR_CHOICE
    fr_mode[(fr_sp as ubyte)] = 0
    fr_stmts[(fr_sp as ubyte)] = 0
    fr_defer[(fr_sp as ubyte)] = 0
    fr_values[(fr_sp as ubyte)] = vals
    fr_sp = fr_sp + 1
}

; close the top block frame on `}`: build its ND_BLOCK and fold it into the
; enclosing construct (root result / when-choice / if-then-else / while / for /
; repeat), honoring a pending defer wrapper. Extracted from parse_block to keep
; that sub's node count under the per-sub arena cap.
sub close_frame(ubyte fi) {
    uword block
    block = new_node(ND_BLOCK, 0, fr_stmts[(fi as ubyte)], 0)
    ubyte kind
    kind = fr_kind[(fi as ubyte)]
    fr_sp = fr_sp - 1
    if kind == FR_ROOT {
        parse_result = block
        return
    }
    if kind == FR_CHOICE {
        uword chvals
        chvals = fr_values[(fi as ubyte)]
        uword ch
        ch = new_node(ND_WHENCHOICE, 0, chvals, block)
        uword pch
        pch = cons_prepend(fr_choices[(fr_sp - 1 as ubyte)], ch)
        fr_choices[(fr_sp - 1 as ubyte)] = pch
        return
    }
    uword node
    node = 0
    if kind == FR_THEN {
        if cur_kind() == TK_KELSE {
            advance()
            advance()               ; '{'
            fr_kind[(fr_sp as ubyte)] = FR_ELSE
            fr_mode[(fr_sp as ubyte)] = 0
            fr_stmts[(fr_sp as ubyte)] = 0
            fr_defer[(fr_sp as ubyte)] = fr_defer[(fi as ubyte)]
            fr_cond[(fr_sp as ubyte)] = fr_cond[(fi as ubyte)]
            fr_then[(fr_sp as ubyte)] = block
            fr_sp = fr_sp + 1
            return
        }
        node = new_node(ND_IF, 0, fr_cond[(fi as ubyte)], block)
    } else {
        if kind == FR_ELSE {
            node = new_node(ND_IF, 0, fr_cond[(fi as ubyte)], fr_then[(fi as ubyte)])
            pokew($bcc0 + ((node) << 1), block)
        } else {
            if kind == FR_WHILE {
                node = new_node(ND_WHILE, 0, fr_cond[(fi as ubyte)], block)
            } else {
                if kind == FR_FOR {
                    node = new_node(ND_FOR, 0, fr_var[(fi as ubyte)], fr_lo[(fi as ubyte)])
                    pokew($bcc0 + ((node) << 1), fr_hi[(fi as ubyte)])
                    pokew($c03a + ((node) << 1), block)
                } else {
                    ; FR_REPEAT
                    node = new_node(ND_REPEAT, 0, fr_cond[(fi as ubyte)], block)
                }
            }
        }
    }
    if fr_defer[(fi as ubyte)] != 0 {
        node = new_node(ND_DEFER, 0, node, 0)
    }
    fr_attach(node)
}

sub parse_block() -> uword {
    advance()                               ; consume opening '{'
    fr_sp = 0
    pending_defer = 0
    fr_kind[(fr_sp as ubyte)] = FR_ROOT
    fr_mode[(fr_sp as ubyte)] = 0
    fr_stmts[(fr_sp as ubyte)] = 0
    fr_defer[(fr_sp as ubyte)] = 0
    fr_sp = fr_sp + 1
    parse_result = 0

    repeat {
        if fr_sp == 0 {
            break
        }
        ubyte fi
        fi = fr_sp - 1
        ubyte t
        uword node

        if fr_mode[(fi as ubyte)] == 1 {               ; when body (choices)
            parse_when_choice(fi)
            continue
        }

        t = cur_kind()
        if t == TK_RBRACE {
            advance()
            close_frame(fi)
            continue
        }

        if t == TK_KDEFER {
            advance()
            pending_defer = 1
            continue
        }
        ubyte mod
        mod = pending_defer
        pending_defer = 0
        ubyte opened
        opened = stmt_dispatch(mod)
        if opened == 0 {
            node = last_simple
            if mod != 0 {
                node = new_node(ND_DEFER, 0, node, 0)
            }
            fr_attach(node)
        } else {
            ; the freshly pushed frame inherits the defer flag via
            ; fr_push_block(.., mod) already; nothing to do here.
        }
    }
    return parse_result
}


; ---- top-level program parser ----

; map a register-ABI annotation ident (A / X / Y / AY) to a code:
; 0=none, 1=A, 2=X, 3=Y, 4=AY.
sub reg_code(uword id) -> ubyte {
    ubyte b0
    b0 = peek($8c52 + (id))
    if b0 == 'A' {
        if peek($8c52 + (id + 1)) == 'Y' { return 4 }
        return 1
    }
    if b0 == 'X' { return 2 }
    if b0 == 'Y' { return 3 }
    return 0
}

; parse one parameter: `type name` with an optional `@REG` annotation. The reg
; code rides ND_PARAM's node_b (0 = no register / static-param slot).
sub parse_param() -> uword {
    ubyte ptag
    ptag = type_tag(cur_kind())
    advance()                               ; type
    uword pname
    pname = cur_val()
    advance()                               ; name
    uword reg
    reg = 0
    if cur_kind() == TK_AT {
        advance()                           ; @
        reg = reg_code(cur_val())
        advance()                           ; REG ident
    }
    return new_node(ND_PARAM, ptag, pname, reg)
}

; parse a `( p, p, ... )` parameter list -> cons head (reversed source order,
; matching cons_prepend); cursor left just past the `)`.
sub parse_param_list() -> uword {
    advance()                               ; '('
    uword params
    params = 0
    repeat {
        if cur_kind() == TK_RPAREN {
            break
        }
        params = cons_prepend(params, parse_param())
        if cur_kind() != TK_COMMA {
            break
        }
        advance()
    }
    advance()                               ; ')'
    return params
}

; parse an optional `-> rt @REG` return annotation -> the return type tag. The
; `@REG` is consumed but not stored: an asmsub returns its value by the standard
; convention (ubyte -> A, uword -> A:Y), so the return register is implied by rt.
sub parse_ret() -> uword {
    uword tag
    tag = TY_VOID
    if cur_kind() == TK_ARROW {
        advance()                           ; ->
        tag = type_tag(cur_kind())
        advance()                           ; rt
        if cur_kind() == TK_AT {
            advance()                       ; @
            advance()                       ; REG ident
        }
    }
    return tag
}

; is this interned ident the entry sub name "start"? The on-target descends into
; the program's `main { }` block and treats the inner `sub start()` as the entry
; (SUBK_MAIN), matching upstream/p8c. ($8c52 = ident_pool base.)
sub id_is_start(uword id) -> ubyte {
    if peek($8c52 + (id)) != $73 { return 0 }       ; 's'
    if peek($8c52 + (id + 1)) != $74 { return 0 }   ; 't'
    if peek($8c52 + (id + 2)) != $61 { return 0 }   ; 'a'
    if peek($8c52 + (id + 3)) != $72 { return 0 }   ; 'r'
    if peek($8c52 + (id + 4)) != $74 { return 0 }   ; 't'
    if peek($8c52 + (id + 5)) != 0 { return 0 }     ; exact length 5
    return 1
}

sub parse_sub(ubyte kind) -> uword {
    ; current token is the name (IDENT or main keyword handled by caller)
    uword nameid
    nameid = cur_val()
    advance()                               ; consume name
    uword params
    params = parse_param_list()
    uword retpacked
    retpacked = parse_ret()
    uword body
    body = parse_block()
    uword node
    node = new_node(ND_SUB, kind, nameid, params)
    pokew($bcc0 + ((node) << 1), body)
    pokew($c03a + ((node) << 1), retpacked)
    return node
}

sub const_type_tag(ubyte k) -> ubyte {
    if k == TK_KBYTE { return TY_CONST_BYTE }
    if k == TK_KUWORD { return TY_CONST_UWORD }
    return TY_CONST_UBYTE
}

sub parse_const_decl() -> uword {
    advance()                               ; 'const'
    ubyte ctag
    ctag = const_type_tag(cur_kind())
    advance()                               ; type
    uword nameid
    nameid = cur_val()
    advance()                               ; name
    advance()                               ; '='
    hoist_arg = parse_expr()
    return new_node(ND_VARDECL, ctag, nameid, hoist_arg)
}

sub parse_enum_decl() -> uword {
    advance()                               ; 'enum'
    uword ename
    ename = cur_val()
    advance()                               ; name
    advance()                               ; '{'
    uword members
    members = 0
    repeat {
        if cur_kind() == TK_RBRACE {
            break
        }
        uword mname
        mname = cur_val()
        advance()                           ; member name
        ubyte hasval
        uword mval
        hasval = 0
        mval = 0
        if cur_kind() == TK_ASSIGN {
            advance()
            mval = cur_val()
            advance()
            hasval = 1
        }
        members = cons_prepend(members, new_node(ND_ENUMMEMBER, hasval, mname, mval))
        if cur_kind() != TK_COMMA {
            break
        }
        advance()
    }
    advance()                               ; '}'
    return new_node(ND_ENUM, 0, ename, members)
}

sub parse_struct_decl() -> uword {
    advance()                               ; 'struct'
    uword sname
    sname = cur_val()
    advance()                               ; name
    advance()                               ; '{'
    uword fields
    fields = 0
    repeat {
        if cur_kind() == TK_RBRACE {
            break
        }
        ubyte ftag
        ftag = type_tag(cur_kind())
        advance()                           ; field type
        uword fname
        fname = cur_val()
        advance()                           ; field name
        fields = cons_prepend(fields, new_node(ND_FIELD, ftag, fname, 0))
        if cur_kind() == TK_COMMA {         ; ';' is a comment in the lexer
            advance()
        }
    }
    advance()                               ; '}'
    return new_node(ND_STRUCT, 0, sname, fields)
}

; `asmsub name(params @REG) -> rt @REG = $ADDR`  (decl: jsr $ADDR), or
; `asmsub name(params @REG) -> rt @REG { %asm {{ ... }} }`  (inline body).
sub parse_asmsub() -> uword {
    advance()                               ; 'asmsub'
    uword nameid
    nameid = cur_val()
    advance()                               ; name
    uword params
    params = parse_param_list()
    uword retpacked
    retpacked = parse_ret()
    ; inline-body form only (an address decl uses `extsub $ADDR = name(...)`);
    ; the block holds one ND_INLINEASM.
    uword body
    body = parse_block()
    uword bnode
    bnode = new_node(ND_SUB, SUBK_ASMSUB_BODY, nameid, params)
    pokew($bcc0 + ((bnode) << 1), body)
    pokew($c03a + ((bnode) << 1), retpacked)
    return bnode
}

; `extsub $ADDR = name(params @REG) -> rt @REG`  (address-first decl form).
sub parse_extsub() -> uword {
    advance()                               ; 'extsub'
    uword addr
    addr = cur_val()                        ; $ADDR (INT)
    advance()
    advance()                               ; '='
    uword nameid
    nameid = cur_val()
    advance()                               ; name
    uword params
    params = parse_param_list()
    uword retpacked
    retpacked = parse_ret()
    uword node
    node = new_node(ND_SUB, SUBK_ASMSUB, nameid, params)
    pokew($bcc0 + ((node) << 1), addr)
    pokew($c03a + ((node) << 1), retpacked)
    return node
}

sub is_struct_name(uword id) -> ubyte {
    uword cell
    cell = prog_structs
    repeat {
        if cell == 0 {
            return 0
        }
        if peekw($b5cc + ((peekw($c3b4 + ((cell) << 1))) << 1)) == id {
            return 1
        }
        cell = peekw($c65c + ((cell) << 1))
    }
}

sub parse_struct_var() -> uword {
    uword sname
    sname = cur_val()                       ; struct type name (IDENT)
    advance()
    uword arrsize
    arrsize = 0
    if cur_kind() == TK_LBRACK {
        advance()
        arrsize = cur_val()
        advance()                           ; INT
        advance()                           ; ']'
    }
    uword nameid
    nameid = cur_val()
    advance()                               ; instance name
    uword node
    node = new_node(ND_VARDECL, TY_STRUCT, nameid, 0)
    pokew($bcc0 + ((node) << 1), arrsize)
    pokew($c03a + ((node) << 1), sname)
    return node
}

; ---- streaming support ----
; Full reset (between passes): node arena + cons + text pools.

sub reset_arena() {
    reset_nodes()
    ident_count = 0
    ident_pool_len = 0
    str_pool_len = 0
}
; Per-unit reset (between subs in pass B): only the node arena + cons
; cells. The text pools are NOT reset -- the 2-token lookahead window
; holds tokens whose ident/str ids were interned during the previous
; unit, so resetting the pools would invalidate them. The pools persist
; across pass B (their total fits; idents dedupe).

sub reset_nodes() {
    node_count = 1
    cons_count = 1
}

sub reset_source() {
    ; the emulator rewinds the input to offset 0 on EOF, so clearing the
    ; sticky-EOF / peek flags makes the next read start over from the top.
    peek_ok = 0
    src_eof = 0
}

; process one directive (cursor on the DIRECTIVE token), updating program
; header state.

sub handle_directive() {
    name_len = 0
    append_ident_to_namebuf(cur_val())
    ubyte dk
    dk = dir_classify()
    advance()                               ; consume the directive
    if dk == 0 {                            ; %address
        prog_address = cur_val()
        advance()
        return
    }
    if dk == 2 {                            ; %import
        prog_imports = cons_prepend(prog_imports, cur_val())
        advance()
        return
    }
    ; %output / %memtop / other: consume a single ident-or-int arg if present
    if cur_kind() == TK_IDENT {
        advance()
    } else {
        if cur_kind() == TK_INT {
            advance()
        }
    }
}

; skip a `{ ... }` block (cursor on the opening '{'), brace-matched.

sub skip_braced_block() {
    advance()                               ; consume '{'
    uword depth
    depth = 1
    repeat {
        ubyte t
        t = cur_kind()
        if t == TK_EOF {
            return
        }
        if t == TK_LBRACE {
            depth = depth + 1
        }
        if t == TK_RBRACE {
            depth = depth - 1
            if depth == 0 {
                advance()                   ; consume the matching '}'
                return
            }
        }
        advance()
    }
}
; skip a sub: advance to its body '{', then skip the braced block.

sub skip_sub_body() {
    repeat {
        ubyte t
        t = cur_kind()
        if t == TK_EOF {
            return
        }
        if t == TK_LBRACE {
            break
        }
        advance()
    }
    skip_braced_block()
}
; skip an asmsub: the `= $ADDR` decl form (advance past '=' and the address),
; or the inline-body form (skip the braced `{ %asm {{ ... }} }` block).
sub skip_asmsub() {
    advance()                               ; 'asmsub'
    repeat {
        ubyte t
        t = cur_kind()
        if t == TK_EOF {
            return
        }
        if t == TK_ASSIGN {
            break
        }
        if t == TK_LBRACE {
            skip_braced_block()             ; body form
            return
        }
        advance()
    }
    advance()                               ; '='
    advance()                               ; $ADDR
}

; skip an `extsub $ADDR = name(params)` declaration (no body).
sub skip_extsub() {
    repeat {
        ubyte t
        t = cur_kind()
        if t == TK_EOF {
            return
        }
        if t == TK_RPAREN {
            break
        }
        advance()
    }
    advance()                               ; ')'
    ; optional `-> rt @REG`
    if cur_kind() == TK_ARROW {
        advance()                           ; ->
        advance()                           ; rt
        if cur_kind() == TK_AT {
            advance()                       ; @
            advance()                       ; REG
        }
    }
}

; PASS A: collect directives + module decls into the program lists;
; skip sub / main / inline-sub / asmsub bodies.

sub parse_decls_pass() {
    repeat {
        ubyte t
        t = cur_kind()
        if t == TK_EOF {
            break
        }
        if t == TK_DIRECTIVE {
            handle_directive()
            continue
        }
        if is_type_kw(t) != 0 {
            hoist_arg = parse_var_decl()
            prog_vars = cons_prepend(prog_vars, hoist_arg)
            continue
        }
        if t == TK_KCONST {
            hoist_arg = parse_const_decl()
            prog_vars = cons_prepend(prog_vars, hoist_arg)
            continue
        }
        if t == TK_KENUM {
            hoist_arg = parse_enum_decl()
            prog_enums = cons_prepend(prog_enums, hoist_arg)
            continue
        }
        if t == TK_KSTRUCT {
            hoist_arg = parse_struct_decl()
            prog_structs = cons_prepend(prog_structs, hoist_arg)
            continue
        }
        if t == TK_KMAIN {
            advance()                   ; 'main'
            advance()                   ; '{'  -- descend into the program block
            continue
        }
        if t == TK_RBRACE {
            advance()                   ; the program block's closing '}'
            continue
        }
        if t == TK_KSUB {
            skip_sub_body()
            continue
        }
        if t == TK_KINLINE {
            skip_sub_body()
            continue
        }
        if t == TK_KASMSUB {
            skip_asmsub()
            continue
        }
        if t == TK_KEXTSUB {
            skip_extsub()
            continue
        }
        if t == TK_IDENT {
            if is_struct_name(cur_val()) != 0 {
                hoist_arg = parse_struct_var()
                prog_vars = cons_prepend(prog_vars, hoist_arg)
                continue
            }
        }
        advance()                           ; skip an unknown token
    }
}

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
        out_byte(peek($8c52 + (off + j)))
        j = j + 1
    }
}
; emit a symbol's mangled name from its table entry: module -> p8v_<name>,
; param -> p8v_<sub>_arg_<name>, local -> p8v_<sub>_<name>.

sub emit_sym_mangled(uword si) {
    ; arrays live in main memory under a p8a_ label; everything else is p8v_.
    if peekw($ea88 + ((si) << 1)) != 0 {
        out_text("p8a_")
        out_ident_text(peekw($c904 + ((si) << 1)))
        return
    }
    out_text("p8v_")
    if peek($de58 + (si)) == 0 {
        out_ident_text(peekw($c904 + ((si) << 1)))
        return
    }
    out_ident_text(peekw($d840 + ((si) << 1)))
    if peek($de58 + (si)) == 1 {
        out_text("_arg_")
    } else {
        out_byte('_')
    }
    out_ident_text(peekw($c904 + ((si) << 1)))
}
; emit a var reference by ident, resolved in the current scope.

sub o_nl()    { out_byte('\n') }

sub reverse_cons(uword head) -> uword {
    uword rev
    rev = 0
    uword cell
    cell = head
    repeat {
        if cell == 0 {
            break
        }
        rev = cons_prepend(rev, peekw($c3b4 + ((cell) << 1)))
        cell = peekw($c65c + ((cell) << 1))
    }
    return rev
}

; in-place list reversal (flips next pointers, allocates no cons cells). Only
; safe where the original list is not read again after the call -- used for the
; one big spike (build_symbols reversing prog_vars, ~250 cells), which would
; otherwise double the cons high-water during pass 1.
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
        nxt = peekw($c65c + ((cell) << 1))
        pokew($c65c + ((cell) << 1), prev)
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
        if peekw($c904 + ((i) << 1)) == identid {
            if peekw($d840 + ((i) << 1)) == cur_scope {
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
        if peekw($c904 + ((i) << 1)) == identid {
            if peekw($d840 + ((i) << 1)) == 0 {
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

; ---- data-initialized array tables (extracted from ND_ARRAYLIT inits before
; register_subs resets the node/cons arena; dumped after the str pool) --------
uword[8] ai_sym          ; sym index of each data-initialized array
ubyte[8] ai_isstr        ; 1 if elements are string ids, else int values
uword[8] ai_n            ; element count
uword[8] ai_off          ; offset into ai_vals
uword[64] ai_vals        ; flat pool of element values (int value or str id)
uword ai_count
uword ai_voff

; record the elements of one data-init array (sym index `symidx`, ND_ARRAYLIT
; cons head `head`) into the ai_* tables, in source order.
sub ai_record(uword symidx, uword head) {
    head = reverse_cons(head)
    ai_sym[(ai_count as ubyte)] = symidx
    ai_off[(ai_count as ubyte)] = ai_voff
    ubyte isstr
    isstr = 0
    uword n
    n = 0
    uword cell
    cell = head
    repeat {
        if cell == 0 {
            break
        }
        uword e
        e = peekw($c3b4 + ((cell) << 1))               ; cons_val = element node
        if peek($b252 + (e)) == ND_STR {
            isstr = 1
        }
        ai_vals[(ai_voff as ubyte)] = peekw($b5cc + ((e) << 1))   ; node_a = value / str id
        ai_voff = ai_voff + 1
        n = n + 1
        cell = peekw($c65c + ((cell) << 1))            ; cons_next
    }
    ai_isstr[(ai_count as ubyte)] = isstr
    ai_n[(ai_count as ubyte)] = n
    ai_count = ai_count + 1
}

; register one module-scalar / const vardecl in the symbol table (continuing
; zp_next). Split out of build_symbols to keep its node count under the arena cap.
sub bs_scalar(uword vd) {
    ubyte tag
    tag = peek($b40f + (vd))
    if tag <= TY_UWORD {           ; ubyte / byte / uword
        ubyte sz
        sz = 1
        if tag == TY_UWORD { sz = 2 }
        pokew($c904 + ((sym_count) << 1), peekw($b5cc + ((vd) << 1)))
        poke($cf1c + (sym_count), tag)
        pokew($d840 + ((sym_count) << 1), 0)
        poke($de58 + (sym_count), 0)
        poke($e164 + (sym_count), 0)
        pokew($ea88 + ((sym_count) << 1), 0)
        ; ZP runs $40..$FF; a scalar that won't fit overflows into
        ; main memory (sentinel $FFFF -> emit_memvars), matching p8c.
        if zp_next + sz > $ff {
            pokew($d228 + ((sym_count) << 1), $ffff)
        } else {
            pokew($d228 + ((sym_count) << 1), zp_next)
            zp_next = zp_next + sz
        }
        sym_count = sym_count + 1
    } else {
        ; const ubyte/byte/uword: TY_CONST_* (6/7/8) -> base type.
        ; No ZP storage; the int-literal init (node_b) is folded in
        ; at every use site, matching p8c. (Map the tag with explicit
        ; compares, not arithmetic: p8c only folds a const in leaf /
        ; comparison positions, not as a `-` operand.) Tags above
        ; TY_CONST_UWORD (e.g. TY_STRUCT) are not consts -> skip.
        if tag <= TY_CONST_UWORD {
            ubyte bt
            bt = TY_UBYTE
            if tag == TY_CONST_BYTE { bt = TY_BYTE }
            if tag == TY_CONST_UWORD { bt = TY_UWORD }
            pokew($c904 + ((sym_count) << 1), peekw($b5cc + ((vd) << 1)))
            poke($cf1c + (sym_count), bt)
            pokew($d228 + ((sym_count) << 1), 0)
            pokew($d840 + ((sym_count) << 1), 0)
            poke($de58 + (sym_count), 0)
            poke($e164 + (sym_count), 1)
            pokew($e470 + ((sym_count) << 1), peekw($b5cc + ((peekw($b946 + ((vd) << 1))) << 1)))
            pokew($ea88 + ((sym_count) << 1), 0)
            sym_count = sym_count + 1
        }
    }
}

; register one module-array vardecl: storage is a labeled .byte block
; (p8a_<name>) in main memory, not ZP. Element type tag in node_op, count in
; node_c (only ubyte/uword element types). A `[...]` initializer is recorded
; for the data-init section. Split out of build_symbols for the arena cap.
sub bs_array(uword vd) {
    ubyte etag
    etag = peek($b40f + (vd))
    if etag <= TY_UWORD {
        pokew($c904 + ((sym_count) << 1), peekw($b5cc + ((vd) << 1)))
        poke($cf1c + (sym_count), etag)
        pokew($d228 + ((sym_count) << 1), 0)
        pokew($d840 + ((sym_count) << 1), 0)
        poke($de58 + (sym_count), 0)
        poke($e164 + (sym_count), 0)
        pokew($ea88 + ((sym_count) << 1), peekw($bcc0 + ((vd) << 1)))
        uword aini
        aini = peekw($b946 + ((vd) << 1))              ; node_b = init
        if aini != 0 {
            if peek($b252 + (aini)) == ND_ARRAYLIT {
                ai_record(sym_count, peekw($b5cc + ((aini) << 1)))
            }
        }
        sym_count = sym_count + 1
    }
}

sub build_symbols() {
    sym_count = 0
    ai_count = 0
    ai_voff = 0
    zp_next = $40
    uword head
    head = reverse_cons_ip(prog_vars)
    uword cell
    cell = head
    repeat {
        if cell == 0 {
            break
        }
        uword vd
        vd = peekw($c3b4 + ((cell) << 1))
        if peek($b252 + (vd)) == ND_VARDECL {
            if peekw($bcc0 + ((vd) << 1)) == 0 {               ; scalar (not an array)
                bs_scalar(vd)
            } else {
                bs_array(vd)
            }
        }
        cell = peekw($c65c + ((cell) << 1))
    }
}

; ---- prologue / ZP bindings / trailers ----------------------

sub emit_zp_bindings() {
    ; consts have no storage (folded at use sites), so they get no binding --
    ; only the ZP scalars do. Emit nothing (not even the header) if every
    ; module symbol is a const, matching p8c's empty zp_scalars case.
    ubyte any
    any = 0
    uword j
    j = 0
    repeat {
        if j >= sym_count {
            break
        }
        if peek($e164 + (j)) == 0 {
            if peekw($ea88 + ((j) << 1)) == 0 {
                if peekw($d228 + ((j) << 1)) < $0100 {     ; real ZP only
                    any = 1
                    break
                }
            }
        }
        j = j + 1
    }
    if any == 0 {
        return
    }
    out_byte('\n')
    out_text("; ---- ZP variable allocations ----\n")
    uword i
    i = 0
    repeat {
        if i >= sym_count {
            break
        }
        if peek($e164 + (i)) == 0 {
            if peekw($ea88 + ((i) << 1)) == 0 {
                if peekw($d228 + ((i) << 1)) < $0100 {     ; skip $ffff overflow + $fffe reg
                    emit_sym_mangled(i)
                    out_text(" = $")
                    out_hex2(lsb(peekw($d228 + ((i) << 1))))
                    o_nl()
                }
            }
        }
        i = i + 1
    }
}
; emit the `; ---- scalars overflowed from ZP into main memory ----` block:
; one `p8v_<name>:` label + `.byte 0`(ubyte) / `.byte 0, 0`(uword) per scalar
; that did not fit ZP (sym_addr == $FFFF), source order. Between arrays and the
; string pool (matching p8c). Empty -> none.

sub emit_memvars() {
    ubyte any
    any = 0
    uword j
    j = 0
    repeat {
        if j >= sym_count {
            break
        }
        if peekw($ea88 + ((j) << 1)) == 0 {
            if peek($e164 + (j)) == 0 {
                if peekw($d228 + ((j) << 1)) == $ffff {
                    any = 1
                    break
                }
            }
        }
        j = j + 1
    }
    if any == 0 {
        return
    }
    out_byte('\n')
    out_text("; ---- scalars overflowed from ZP into main memory ----")
    o_nl()
    uword i
    i = 0
    repeat {
        if i >= sym_count {
            break
        }
        if peekw($ea88 + ((i) << 1)) == 0 {
            if peek($e164 + (i)) == 0 {
                if peekw($d228 + ((i) << 1)) == $ffff {
                    emit_sym_mangled(i)
                    out_byte(':')
                    o_nl()
                    out_text("  .byte 0")
                    if peek($cf1c + (i)) == TY_UWORD {
                        out_text(", 0")
                    }
                    o_nl()
                }
            }
        }
        i = i + 1
    }
}

sub cg_skip_decl() {
    ubyte t
    uword dummy
    t = cur_kind()
    if t == TK_DIRECTIVE {
        advance()
        ubyte a
        a = cur_kind()
        if a == TK_INT {
            advance()
        } else {
            if a == TK_IDENT {
                advance()
            }
        }
        return
    }
    if is_type_kw(t) != 0 {
        dummy = parse_var_decl()
        reset_nodes()
        return
    }
    if t == TK_KCONST {
        dummy = parse_const_decl()
        reset_nodes()
        return
    }
    if t == TK_KENUM {
        dummy = parse_enum_decl()
        reset_nodes()
        return
    }
    if t == TK_KSTRUCT {
        dummy = parse_struct_decl()
        reset_nodes()
        return
    }
    advance()
}
; "p8s_<name>" -- the mangled label for a user sub.

sub push_walk_block(uword blk) {
    if blk == 0 {
        return
    }
    uword cell
    cell = peekw($b5cc + ((blk) << 1))
    repeat {
        if cell == 0 {
            break
        }
        sws_a[(sws_sp as ubyte)] = peekw($c3b4 + ((cell) << 1))
        sws_sp = sws_sp + 1
        cell = peekw($c65c + ((cell) << 1))
    }
}

sub push_walk_when(uword st) {
    uword cell
    cell = peekw($b946 + ((st) << 1))
    repeat {
        if cell == 0 {
            break
        }
        push_walk_block(peekw($b946 + ((peekw($c3b4 + ((cell) << 1))) << 1)))
        cell = peekw($c65c + ((cell) << 1))
    }
}
; allocate a sub's local vardecls (p8v_<sub>_<name>), in p8c's _walk_block
; order: depth-first, source order, recursing into if (then/else), while, for,
; repeat, and when (per-arm) bodies. Continues the ZP bump.

sub walk_locals(uword body, uword subname) {
    sws_sp = 0
    push_walk_block(body)
    repeat {
        if sws_sp == 0 {
            break
        }
        sws_sp = sws_sp - 1
        uword st
        st = sws_a[(sws_sp as ubyte)]
        ubyte k
        k = peek($b252 + (st))
        if k == ND_VARDECL {
            if peekw($bcc0 + ((st) << 1)) == 0 {               ; scalar (not an array)
                ubyte tag
                tag = peek($b40f + (st))
                if tag <= TY_UWORD {
                    ubyte sz
                    sz = 1
                    if tag == TY_UWORD { sz = 2 }
                    pokew($c904 + ((sym_count) << 1), peekw($b5cc + ((st) << 1)))
                    poke($cf1c + (sym_count), tag)
                    pokew($d840 + ((sym_count) << 1), subname)
                    poke($de58 + (sym_count), 2)
                    poke($e164 + (sym_count), 0)
                    pokew($ea88 + ((sym_count) << 1), 0)
                    if zp_next + sz > $ff {
                        pokew($d228 + ((sym_count) << 1), $ffff)
                    } else {
                        pokew($d228 + ((sym_count) << 1), zp_next)
                        zp_next = zp_next + sz
                    }
                    sym_count = sym_count + 1
                }
            }
        }
        if k == ND_IF {
            push_walk_block(peekw($bcc0 + ((st) << 1)))         ; else (bottom)
            push_walk_block(peekw($b946 + ((st) << 1)))         ; then (top)
        }
        if k == ND_WHILE {
            push_walk_block(peekw($b946 + ((st) << 1)))
        }
        if k == ND_FOR {
            push_walk_block(peekw($c03a + ((st) << 1)))
        }
        if k == ND_REPEAT {
            push_walk_block(peekw($b946 + ((st) << 1)))
        }
        if k == ND_WHEN {
            push_walk_when(st)
        }
    }
}
; register every sub (in source order) so calls resolve and pass B emits the
; non-main subs in p8c's order. Streaming dispatch, mirroring stmt.p8's pass B.


sub d16(uword v) { out_byte(lsb(v)) out_byte(lsb(v >> 8)) }

; allocate a sub's params (source order) into the symbol table, continuing
; zp_next. A register-ABI param (reg code in ND_PARAM node_b) gets NO storage
; (the call passes it in a register); the reg code rides sym_cval. Extracted
; from register_subs to keep that sub's node count under the per-sub arena cap.
sub alloc_sub_params(uword snode) {
    uword phead
    phead = reverse_cons(peekw($b946 + ((snode) << 1)))
    uword pcell
    pcell = phead
    repeat {
        if pcell == 0 {
            break
        }
        uword pnode
        pnode = peekw($c3b4 + ((pcell) << 1))
        ubyte ptag
        ptag = peek($b40f + (pnode))
        ubyte preg
        preg = lsb(peekw($b946 + ((pnode) << 1)))
        ubyte psz
        psz = 1
        if ptag == TY_UWORD { psz = 2 }
        pokew($c904 + ((sym_count) << 1), peekw($b5cc + ((pnode) << 1)))
        poke($cf1c + (sym_count), ptag)
        pokew($d840 + ((sym_count) << 1), peekw($b5cc + ((snode) << 1)))
        poke($de58 + (sym_count), 1)
        poke($e164 + (sym_count), 0)
        pokew($e470 + ((sym_count) << 1), preg)
        pokew($ea88 + ((sym_count) << 1), 0)
        if preg != 0 {
            pokew($d228 + ((sym_count) << 1), $fffe)   ; reg param: no storage
        } else {
            if zp_next + psz > $ff {
                pokew($d228 + ((sym_count) << 1), $ffff)
            } else {
                pokew($d228 + ((sym_count) << 1), zp_next)
                zp_next = zp_next + psz
            }
        }
        sym_count = sym_count + 1
        pcell = peekw($c65c + ((pcell) << 1))
    }
}

sub register_subs() {
    sub_count = 0
    reset_source()
    reset_nodes()
    lex_init()
    repeat {
        ubyte t
        t = cur_kind()
        if t == TK_EOF {
            break
        }
        if t == TK_KMAIN {
            advance()
            advance()
            continue
        }
        if t == TK_RBRACE {
            advance()
            continue
        }
        uword snode
        ubyte issub
        issub = 1
        if t == TK_KSUB {
            advance()
            if id_is_start(cur_val()) != 0 {
                snode = parse_sub(SUBK_MAIN)
            } else {
                snode = parse_sub(SUBK_SUB)
            }
        } else {
            if t == TK_KINLINE {
                advance()
                advance()
                snode = parse_sub(SUBK_INLINE)
            } else {
                if t == TK_KASMSUB {
                    snode = parse_asmsub()
                } else {
                    if t == TK_KEXTSUB {
                        snode = parse_extsub()
                    } else {
                        issub = 0
                        cg_skip_decl()
                    }
                }
            }
        }
        if issub != 0 {
            ubyte sk
            sk = peek($b40f + (snode))
            sub_name[(sub_count as ubyte)] = peekw($b5cc + ((snode) << 1))
            sub_kind[(sub_count as ubyte)] = sk
            sub_ret[(sub_count as ubyte)] = lsb(peekw($c03a + ((snode) << 1)))
            sub_addr[(sub_count as ubyte)] = 0
            if sk == SUBK_ASMSUB {
                sub_addr[(sub_count as ubyte)] = peekw($bcc0 + ((snode) << 1))   ; node_c is the $F0xx addr
            }
            sub_count = sub_count + 1
            alloc_sub_params(snode)
            ; then this sub's locals (walk the body), continuing zp_next.
            ; (asmsubs have no var locals -- raw asm body / address -- so skip.)
            if sk != SUBK_ASMSUB {
                if sk != SUBK_ASMSUB_BODY {
                    walk_locals(peekw($bcc0 + ((snode) << 1)), peekw($b5cc + ((snode) << 1)))
                }
            }
            reset_nodes()
        }
    }
}
; emit one non-main sub: header, body, per-sub return label + rts.


; pass 1: program-wide state (no nodes -- those stream per-sub afterwards).
; serialize one symbol-table entry's 8 fields (name ident, type, ZP addr, owner
; sub, mkind, is_const, cval/reg, arr_size). Shared by dump_global (module syms)
; and dump_record (per-sub locals) -- split out for the per-sub arena cap.
sub dump_sym(uword i) {
    d16(peekw($c904 + ((i) << 1))) out_byte(peek($cf1c + (i))) d16(peekw($d228 + ((i) << 1))) d16(peekw($d840 + ((i) << 1)))
    out_byte(peek($de58 + (i))) out_byte(peek($e164 + (i))) d16(peekw($e470 + ((i) << 1))) d16(peekw($ea88 + ((i) << 1)))
}

; serialize the data-initialized array tables: count, then per array
; { sym index, is_str flag, element count, element values }. Split out of
; dump_global for the per-sub arena cap.
sub dump_array_init() {
    d16(ai_count)
    uword i
    i = 0
    repeat {
        if i >= ai_count { break }
        d16(ai_sym[(i as ubyte)])
        out_byte(ai_isstr[(i as ubyte)])
        d16(ai_n[(i as ubyte)])
        uword j
        j = 0
        repeat {
            if j >= ai_n[(i as ubyte)] { break }
            d16(ai_vals[((ai_off[(i as ubyte)] + j) as ubyte)])
            j = j + 1
        }
        i = i + 1
    }
}

sub dump_global() {
    d16(prog_address)
    out_byte(prog_target)
    uword i
    uword rc
    rc = 0
    i = 0
    repeat { if i >= sym_count { break } if peekw($d840 + ((i) << 1)) == 0 { rc = rc + 1 } else { if peek($de58 + (i)) == 1 { rc = rc + 1 } } i = i + 1 }
    d16(rc)
    i = 0
    repeat {
        if i >= sym_count { break }
        ubyte keep
        keep = 0
        if peekw($d840 + ((i) << 1)) == 0 { keep = 1 }
        if peek($de58 + (i)) == 1 { keep = 1 }
        if keep != 0 {
            dump_sym(i)
        }
        i = i + 1
    }
    d16(sub_count)
    i = 0
    repeat {
        if i >= sub_count { break }
        d16(sub_name[(i as ubyte)]) out_byte(sub_kind[(i as ubyte)]) out_byte(sub_ret[(i as ubyte)]) d16(sub_addr[(i as ubyte)])
        i = i + 1
    }
    d16(ident_pool_len)
    i = 0
    repeat { if i >= ident_pool_len { break } out_byte(peek($8c52 + (i))) i = i + 1 }
    d16(str_pool_len)
    i = 0
    repeat { if i >= str_pool_len { break } out_byte(peek($a252 + (i))) i = i + 1 }
    dump_array_init()
}
; one sub's AST record: kind(1) snode(2) node_count(2) nodes cons_count(2) cons.
sub dump_record(ubyte kind, uword snode) {
    out_byte(kind)
    d16(snode)
    uword i
    uword nm
    nm = peekw($b5cc + ((snode) << 1))
    uword lc
    lc = 0
    i = 0
    repeat { if i >= sym_count { break } if peekw($d840 + ((i) << 1)) == nm { if peek($de58 + (i)) == 2 { lc = lc + 1 } } i = i + 1 }
    d16(lc)
    i = 0
    repeat {
        if i >= sym_count { break }
        if peekw($d840 + ((i) << 1)) == nm {
            if peek($de58 + (i)) == 2 {
                dump_sym(i)
            }
        }
        i = i + 1
    }
    d16(node_count)
    i = 0
    repeat {
        if i >= node_count { break }
        out_byte(peek($b252 + (i))) out_byte(peek($b40f + (i)))
        d16(peekw($b5cc + ((i) << 1))) d16(peekw($b946 + ((i) << 1))) d16(peekw($bcc0 + ((i) << 1))) d16(peekw($c03a + ((i) << 1)))
        i = i + 1
    }
    d16(cons_count)
    i = 0
    repeat {
        if i >= cons_count { break }
        d16(peekw($c3b4 + ((i) << 1))) d16(peekw($c65c + ((i) << 1)))
        i = i + 1
    }
}


sub start() {
    uword fn
    fn = sys_argv(0)
    src_hand = sys_open(fn)
    fn = sys_argv(1)
    dst_hand = sys_openout(fn)
    reset_arena()
    prog_address = $0200            ; nmos default load address (no %target needed)
    prog_target = 1                 ; this pipeline only ever targets nmos
    prog_imports = 0
    prog_vars = 0
    prog_enums = 0
    prog_structs = 0
    prog_subs = 0
    reset_source()
    lex_init()
    parse_decls_pass()
    build_symbols()
    register_subs()
    dump_global()
    emit_zp_bindings()
    out_byte(0)
    emit_memvars()
    out_byte(0)
    ; re-parse from a clean arena so the record ids match the dumped pool.
    reset_arena()
    reset_source()
    lex_init()
    parse_decls_pass()
    uword snode
    ubyte t
    reset_source()
    lex_init()
    repeat {
        t = cur_kind()
        if t == TK_EOF { break }
        if t == TK_KMAIN {
            advance()
            advance()
            continue
        }
        if t == TK_RBRACE {
            advance()
            continue
        }
        if t == TK_KSUB {
            advance()
            reset_nodes()
            if id_is_start(cur_val()) != 0 {
                snode = parse_sub(SUBK_MAIN)
                dump_record(0, snode)
            } else {
                snode = parse_sub(SUBK_SUB)
                dump_record(1, snode)
            }
        } else {
            if t == TK_KINLINE {
                advance()
                advance()
                reset_nodes()
                snode = parse_sub(SUBK_INLINE)
            } else {
                if t == TK_KASMSUB {
                    reset_nodes()
                    snode = parse_asmsub()
                    ; inline-body asmsubs stream a record (emitted in pass B);
                    ; the `= $ADDR` decl form has no body, so no record.
                    if peek($b40f + (snode)) == SUBK_ASMSUB_BODY {
                        dump_record(1, snode)
                    }
                } else {
                    if t == TK_KEXTSUB {
                        reset_nodes()
                        snode = parse_extsub()
                    } else {
                        cg_skip_decl()
                    }
                }
            }
        }
    }
    out_byte($ff)
    sys_close(src_hand)
    sys_close(dst_hand)
}
}

