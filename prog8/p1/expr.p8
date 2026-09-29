; expr.p8 -- the Prog8 expression parser port (Phase 6, M2, on-target).
;
; Reads a .p8 source containing a single expression (argv[0]) and writes
; the canonical AST S-expression (argv[1]), byte-identical to the Python
; oracle (p8c/serialize.py::ser applied to IterParser.parse_expr).
; Verified against the EXPRESSIONS corpus.
;
; Pipeline, all on the 6502:
;   1. lex the source into in-memory token arrays (+ text/string pools),
;   2. parse via the shunting-yard algorithm (port of iter_parse.py) over
;      explicit operand/operator stacks, building nodes in a struct-of-
;      arrays arena -- no recursion (Prog8 forbids it),
;   3. serialize the arena with an explicit work-stack tree walk.
;
; See ../PARSER_PORT_DESIGN.md sections 3 and 4.
;
; Representation note: host p8c arrays are <=256 ubyte elements with a
; ubyte index, which is plenty for ONE expression. The two arrays that
; hold 16-bit values (a token's value and a node's value-field) are split
; into _lo/_hi byte arrays; everything else (ids, counters, indices) fits
; in a byte. Whole-program parsing (M3/M4) will need real 16-bit arrays
; added to p8c -- tracked in PARSER_PORT_DESIGN / RESUME_NOTES.

%address $0200
%import strings
%output raw
%launcher none
main {

; ---- token kinds ----
const ubyte TK_EOF    = 0
const ubyte TK_INT    = 1
const ubyte TK_STR    = 2
const ubyte TK_IDENT  = 3
const ubyte TK_TRUE   = 5
const ubyte TK_FALSE  = 6
const ubyte TK_KNOT   = 7         ; 'not'
const ubyte TK_KAND   = 8         ; 'and'
const ubyte TK_KOR    = 9         ; 'or'
const ubyte TK_KXOR   = 10        ; 'xor'
const ubyte TK_LPAREN = 11
const ubyte TK_RPAREN = 12
const ubyte TK_DOT    = 13
const ubyte TK_COMMA  = 14
const ubyte TK_LBRACK = 15
const ubyte TK_RBRACK = 16
const ubyte TK_AT     = 17        ; @
; binary/unary operator punctuation -- the value is also the op-id used
; by the serializer's spelling table.
const ubyte TK_PLUS   = 20
const ubyte TK_MINUS  = 21
const ubyte TK_STAR   = 22
const ubyte TK_AMP    = 23        ; &
const ubyte TK_PIPE   = 24        ; |
const ubyte TK_CARET  = 25        ; ^
const ubyte TK_SHL    = 26        ; <<
const ubyte TK_SHR    = 27        ; >>
const ubyte TK_EQ     = 28        ; ==
const ubyte TK_NE     = 29        ; !=
const ubyte TK_LT     = 30        ; <
const ubyte TK_LE     = 31        ; <=
const ubyte TK_GT     = 32        ; >
const ubyte TK_GE     = 33        ; >=
const ubyte TK_TILDE  = 34        ; ~
const ubyte TK_OTHER  = 60        ; any other punctuation (stops an expr)

; ---- node kinds ----
const ubyte ND_INT   = 1
const ubyte ND_STR   = 2
const ubyte ND_BOOL  = 3
const ubyte ND_IDENT = 4
const ubyte ND_BINOP = 5
const ubyte ND_UNOP  = 6
const ubyte ND_CALL  = 7    ; node_a_lo=path id, node_b=arg cons head (reversed)
const ubyte ND_INDEX = 8    ; node_a_lo=array, node_b=index, node_op=has_field, node_a_hi=field id
const ubyte ND_MEMAT = 9    ; node_a_lo=addr node
const ubyte ND_ADDROF= 10   ; node_a_lo=name id

; ---- unary op-ids ----
const ubyte UN_NEG = 0    ; u-
const ubyte UN_NOT = 1    ; not
const ubyte UN_INV = 2    ; ~

; ---- op-stack record kinds (markers are >= OPK_LPAREN) ----
const ubyte OPK_BINOP  = 0
const ubyte OPK_UNOP   = 1
const ubyte OPK_LPAREN = 2
const ubyte OPK_MEMAT  = 3
const ubyte OPK_CALL   = 4
const ubyte OPK_LBRACK = 5

const ubyte UNARY_PREC = 110

; ---- module state ----
ubyte src_hand
ubyte dst_hand
ubyte peek_buf
ubyte peek_ok
ubyte src_eof

; token arrays (value split lo/hi; INT holds a 16-bit value, IDENT/STR
; hold a small id in the low byte)
ubyte[256] tok_kind
ubyte[256] tok_val_lo
ubyte[256] tok_val_hi
ubyte tok_count
ubyte tok_pos

; identifier text pool
ubyte[256] ident_pool
ubyte[64]  ident_off
ubyte[64]  ident_len
ubyte ident_count
ubyte ident_pool_len

; string literal pool (decoded bytes)
ubyte[256] str_pool
ubyte[32]  str_off
ubyte[32]  str_len
ubyte str_count
ubyte str_pool_len

; scratch for the identifier / dotted path currently being built
ubyte[65] name_buf      ; +1 for the NUL terminator classify_name writes
ubyte name_len

uword int_val            ; current numeric literal value

; node arena (struct of arrays; value-field split lo/hi)
ubyte[256] node_kind
ubyte[256] node_op
ubyte[256] node_a_lo
ubyte[256] node_a_hi
ubyte[256] node_b
ubyte node_count

; expression stacks
ubyte[128] operand_stack
ubyte operand_sp
ubyte[128] op_kind
ubyte[128] op_op
ubyte[128] op_prec
ubyte[128] op_a         ; marker: call path ident id
ubyte[128] op_b         ; marker: call arg cons-list head (0 = nil)
ubyte[128] op_floor     ; marker: operand_sp when the marker was opened
ubyte op_sp

; cons cells for call argument lists (index 0 = nil; built by prepend,
; so a list is in reverse argument order -- the serializer accounts for
; that by walking head->tail and emitting via the work stack)
ubyte[256] cons_val
ubyte[256] cons_next
ubyte cons_count

; serializer work stack (parallel arrays)
ubyte[256] ws_type       ; 0=node, 1=close-paren, 2=newline
ubyte[256] ws_node
ubyte[256] ws_depth
ubyte ws_sp

uword dec_v              ; out_dec scratch
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


; ---- source / dest I/O ----
; The emulator rewinds the input to offset 0 on EOF (to support two-pass
; readers), so EOF must be made sticky in software -- otherwise a token
; ending exactly at EOF (no trailing newline) re-reads the rewound file
; forever. See p1/lexer.p8 for the same shim.
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

; write every byte of the NUL-terminated string at `p`.
sub out_text(uword p) {
    uword q
    q = p
    while @(q) != 0 {
        out_byte(@(q))
        q = q + 1
    }
}


; ---- character classes ----
sub is_digit(ubyte c) -> ubyte {
    if c >= '0' {
        if c <= '9' {
            return 1
        }
    }
    return 0
}
sub is_alpha_us(ubyte c) -> ubyte {
    if c >= 'a' {
        if c <= 'z' {
            return 1
        }
    }
    if c >= 'A' {
        if c <= 'Z' {
            return 1
        }
    }
    if c == '_' {
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
    if c >= 'a' {
        if c <= 'f' {
            return 1
        }
    }
    if c >= 'A' {
        if c <= 'F' {
            return 1
        }
    }
    return 0
}
sub hex_nibble(ubyte c) -> ubyte {
    if c >= 'a' {
        return c - $57
    }
    if c >= 'A' {
        return c - $37
    }
    return c - '0'
}


; ---- decimal output (power-of-ten subtraction) ----
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
        out_byte(d + '0')
    }
}
sub out_dec(uword v) {
    dec_v = v
    dec_started = 0
    out_dec_place(10000)
    out_dec_place(1000)
    out_dec_place(100)
    out_dec_place(10)
    out_byte(lsb(dec_v) + '0')
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
        if c == '_' {
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
        if c == '_' {
            c = read_src()
        } else {
            if c == '0' {
                c = read_src()
                int_val = int_val << 1
            } else {
                if c == '1' {
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
        if c == '_' {
            c = read_src()
        } else {
            if is_digit(c) != 0 {
                c = read_src()
                int_val = (int_val << 3) + (int_val << 1) + (c - '0')
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


; ---- identifier read + keyword classification ----
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
                name_buf[name_len] = c
                name_len = name_len + 1
            }
        } else {
            return
        }
    }
}

; intern name_buf[0..name_len-1] into the ident pool, returning its id.
sub intern_name() -> ubyte {
    ubyte i
    i = 0
    repeat {
        if i >= ident_count {
            break
        }
        if ident_len[i] == name_len {
            ubyte off
            ubyte j
            ubyte match
            off = ident_off[i]
            match = 1
            j = 0
            repeat {
                if j >= name_len {
                    break
                }
                if ident_pool[off + j] != name_buf[j] {
                    match = 0
                    break
                }
                j = j + 1
            }
            if match != 0 {
                return i
            }
        }
        i = i + 1
    }
    ; append
    ident_off[ident_count] = ident_pool_len
    ident_len[ident_count] = name_len
    ubyte k
    k = 0
    repeat {
        if k >= name_len {
            break
        }
        ident_pool[ident_pool_len] = name_buf[k]
        ident_pool_len = ident_pool_len + 1
        k = k + 1
    }
    ubyte id
    id = ident_count
    ident_count = ident_count + 1
    return id
}

; the operator/literal keywords the expression grammar recognizes, paired with
; their token kinds; anything else is an identifier.
uword[6] kw_strs = ["or", "and", "not", "xor", "true", "false"]
ubyte[6] kw_toks = [TK_KOR, TK_KAND, TK_KNOT, TK_KXOR, TK_TRUE, TK_FALSE]

; classify name_buf as a token kind (operator/literal keywords get their
; own kinds; everything else -> identifier, which simply stops the expr
; if it isn't a valid operand here).
sub classify_name() -> ubyte {
    name_buf[name_len] = 0                  ; NUL-terminate for strings.compare
    ubyte i
    i = 0
    repeat {
        if i >= 6 { break }
        if strings.compare(&name_buf, kw_strs[i]) == 0 { return kw_toks[i] }
        i = i + 1
    }
    return TK_IDENT
}


; ---- token storage ----
sub push_token(ubyte kind, uword val) {
    tok_kind[tok_count] = kind
    tok_val_lo[tok_count] = lsb(val)
    tok_val_hi[tok_count] = msb(val)
    tok_count = tok_count + 1
}


; ---- the lexer: source -> token arrays ----
sub lex_all() {
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            break
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
        if c == '%' {                              ; '%'
            c = read_src()
            ubyte c2
            c2 = peek_src()
            if src_eof == 0 {
                if c2 == '0' { read_bin()  push_token(TK_INT, int_val)  continue }
                if c2 == '1' { read_bin()  push_token(TK_INT, int_val)  continue }
            }
            push_token(TK_OTHER, 0)
            continue
        }
        if c == '$' {                              ; '$' hex
            c = read_src()
            read_hex()
            push_token(TK_INT, int_val)
            continue
        }
        if is_digit(c) != 0 {
            read_dec()
            push_token(TK_INT, int_val)
            continue
        }
        if c == '\'' {                              ; char literal -> INT
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
            continue
        }
        if c == '"' {                              ; string literal
            c = read_src()
            str_off[str_count] = str_pool_len
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
                str_pool[str_pool_len] = rb
                str_pool_len = str_pool_len + 1
            }
            str_len[str_count] = str_pool_len - str_off[str_count]
            push_token(TK_STR, str_count)
            str_count = str_count + 1
            continue
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
            continue
        }
        c = read_src()
        lex_operator(c)
    }
    push_token(TK_EOF, 0)
}

sub lex_operator(ubyte c) {
    ubyte c2
    if c == '(' { push_token(TK_LPAREN, 0)  return }
    if c == ')' { push_token(TK_RPAREN, 0)  return }
    if c == '[' { push_token(TK_LBRACK, 0)  return }
    if c == ']' { push_token(TK_RBRACK, 0)  return }
    if c == ',' { push_token(TK_COMMA, 0)  return }
    if c == '@' { push_token(TK_AT, 0)  return }
    if c == '.' { push_token(TK_DOT, 0)  return }
    if c == '+' { push_token(TK_PLUS, 0)  return }
    if c == '*' { push_token(TK_STAR, 0)  return }
    if c == '~' { push_token(TK_TILDE, 0)  return }
    if c == '&' {
        c2 = peek_src()
        if c2 == '&' { c2 = read_src()  push_token(TK_OTHER, 0)  return }
        push_token(TK_AMP, 0)
        return
    }
    if c == '|' { push_token(TK_PIPE, 0)  return }
    if c == '^' { push_token(TK_CARET, 0)  return }
    if c == '-' {
        c2 = peek_src()
        if c2 == '-' { c2 = read_src()  push_token(TK_OTHER, 0)  return }
        if c2 == '>' { c2 = read_src()  push_token(TK_OTHER, 0)  return }
        if c2 == '=' { c2 = read_src()  push_token(TK_OTHER, 0)  return }
        push_token(TK_MINUS, 0)
        return
    }
    if c == '<' {
        c2 = peek_src()
        if c2 == '<' { c2 = read_src()  push_token(TK_SHL, 0)  return }
        if c2 == '=' { c2 = read_src()  push_token(TK_LE, 0)  return }
        push_token(TK_LT, 0)
        return
    }
    if c == '>' {
        c2 = peek_src()
        if c2 == '>' { c2 = read_src()  push_token(TK_SHR, 0)  return }
        if c2 == '=' { c2 = read_src()  push_token(TK_GE, 0)  return }
        push_token(TK_GT, 0)
        return
    }
    if c == '=' {
        c2 = peek_src()
        if c2 == '=' { c2 = read_src()  push_token(TK_EQ, 0)  return }
        push_token(TK_OTHER, 0)
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


; ---- token cursor ----
sub cur_kind() -> ubyte {
    return tok_kind[tok_pos]
}
sub cur_val_word() -> uword {
    return mkword(tok_val_hi[tok_pos], tok_val_lo[tok_pos])
}
sub advance() {
    tok_pos = tok_pos + 1
}


; ---- node arena ----
sub new_node(ubyte kind, ubyte op, uword a, ubyte b) -> ubyte {
    ubyte id
    id = node_count
    node_kind[id] = kind
    node_op[id] = op
    node_a_lo[id] = lsb(a)
    node_a_hi[id] = msb(a)
    node_b[id] = b
    node_count = node_count + 1
    return id
}
sub node_a_word(ubyte id) -> uword {
    return mkword(node_a_hi[id], node_a_lo[id])
}


; ---- operator precedence (matches p8c._OP_PRECEDENCE) ----
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
sub push_operand(ubyte node) {
    operand_stack[operand_sp] = node
    operand_sp = operand_sp + 1
}
sub push_op(ubyte k, ubyte op, ubyte prec) {
    op_kind[op_sp] = k
    op_op[op_sp] = op
    op_prec[op_sp] = prec
    op_sp = op_sp + 1
}
sub push_marker(ubyte k, ubyte floor) {
    op_kind[op_sp] = k
    op_floor[op_sp] = floor
    op_b[op_sp] = 0                ; nil arg list (call)
    op_sp = op_sp + 1
}
sub cons_prepend(ubyte head, ubyte val) -> ubyte {
    ubyte c
    c = cons_count
    cons_val[c] = val
    cons_next[c] = head
    cons_count = cons_count + 1
    return c
}

sub apply_top() {
    op_sp = op_sp - 1
    ubyte k
    k = op_kind[op_sp]
    if k == OPK_BINOP {
        operand_sp = operand_sp - 1
        ubyte rhs
        rhs = operand_stack[operand_sp]
        operand_sp = operand_sp - 1
        ubyte lhs
        lhs = operand_stack[operand_sp]
        operand_stack[operand_sp] = new_node(ND_BINOP, op_op[op_sp], lhs, rhs)
        operand_sp = operand_sp + 1
    } else {
        operand_sp = operand_sp - 1
        ubyte operand
        operand = operand_stack[operand_sp]
        operand_stack[operand_sp] = new_node(ND_UNOP, op_op[op_sp], operand, 0)
        operand_sp = operand_sp + 1
    }
}

sub top_prec() -> ubyte {
    if op_kind[op_sp - 1] == OPK_UNOP {
        return UNARY_PREC
    }
    return op_prec[op_sp - 1]
}

sub reduce_to_marker() {
    repeat {
        if op_sp == 0 {
            return
        }
        if op_kind[op_sp - 1] >= OPK_LPAREN {     ; any marker
            return
        }
        apply_top()
    }
}


; build a dotted identifier node from IDENT (DOT IDENT)* at the cursor.
sub append_ident_to_namebuf(ubyte id) {
    ubyte off
    ubyte n
    ubyte j
    off = ident_off[id]
    n = ident_len[id]
    j = 0
    repeat {
        if j >= n {
            break
        }
        name_buf[name_len] = ident_pool[off + j]
        name_len = name_len + 1
        j = j + 1
    }
}
; consume IDENT (DOT IDENT)* at the cursor, returning the interned id of
; the (possibly dotted) full text.
sub read_dotted_path() -> ubyte {
    name_len = 0
    append_ident_to_namebuf(lsb(cur_val_word()))
    advance()
    repeat {
        if cur_kind() != TK_DOT {
            break
        }
        if tok_kind[tok_pos + 1] != TK_IDENT {
            break
        }
        advance()                                  ; consume '.'
        name_buf[name_len] = $2e
        name_len = name_len + 1
        append_ident_to_namebuf(lsb(cur_val_word()))
        advance()                                  ; consume IDENT
    }
    return intern_name()
}


; close an Index: pop the lbracket marker, pop index + array operands,
; consume an optional `.field`, push the ND_INDEX node.
sub close_index() {
    op_sp = op_sp - 1                              ; drop the lbracket marker
    operand_sp = operand_sp - 1
    ubyte index
    index = operand_stack[operand_sp]
    operand_sp = operand_sp - 1
    ubyte array
    array = operand_stack[operand_sp]
    advance()                                      ; consume ']'
    ubyte fieldflag
    ubyte fieldid
    fieldflag = 0
    fieldid = 0
    if cur_kind() == TK_DOT {
        if tok_kind[tok_pos + 1] == TK_IDENT {
            advance()                              ; '.'
            fieldid = lsb(cur_val_word())
            advance()                              ; IDENT
            fieldflag = 1
        }
    }
    ubyte node
    node = new_node(ND_INDEX, fieldflag, array, index)
    node_a_hi[node] = fieldid
    push_operand(node)
}

; close a Call: pop the trailing operand (if any) as the last arg, pop
; the call marker, push the ND_CALL node (args are a reversed cons list).
sub close_call() {
    ubyte head
    ubyte path
    ubyte floor
    head = op_b[op_sp - 1]
    path = op_a[op_sp - 1]
    floor = op_floor[op_sp - 1]
    if operand_sp > floor {
        operand_sp = operand_sp - 1
        head = cons_prepend(head, operand_stack[operand_sp])
    }
    op_sp = op_sp - 1
    push_operand(new_node(ND_CALL, 0, path, head))
}

sub parse_expr() -> ubyte {
    operand_sp = 0
    op_sp = 0
    ubyte expect_operand
    ubyte index_ok
    expect_operand = 1
    index_ok = 0

    repeat {
        ubyte t
        t = cur_kind()

        ; ---- closing / separator tokens ----
        if t == TK_RPAREN {
            reduce_to_marker()
            if op_sp == 0 {
                break
            }
            ubyte mk
            mk = op_kind[op_sp - 1]
            if mk == OPK_LPAREN {
                op_sp = op_sp - 1                  ; group value stays on operand stack
                advance()
                expect_operand = 0
                index_ok = 0
                continue
            }
            if mk == OPK_MEMAT {
                op_sp = op_sp - 1
                operand_sp = operand_sp - 1
                push_operand(new_node(ND_MEMAT, 0, operand_stack[operand_sp], 0))
                advance()
                expect_operand = 0
                index_ok = 0
                continue
            }
            if mk == OPK_CALL {
                close_call()
                advance()
                expect_operand = 0
                index_ok = 0
                continue
            }
            break
        }
        if t == TK_RBRACK {
            reduce_to_marker()
            if op_sp == 0 {
                break
            }
            if op_kind[op_sp - 1] != OPK_LBRACK {
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
            if op_kind[op_sp - 1] != OPK_CALL {
                break
            }
            operand_sp = operand_sp - 1
            op_b[op_sp - 1] = cons_prepend(op_b[op_sp - 1], operand_stack[operand_sp])
            advance()
            expect_operand = 1
            index_ok = 0
            continue
        }

        if expect_operand != 0 {
            index_ok = 0
            if t == TK_INT {
                push_operand(new_node(ND_INT, 0, cur_val_word(), 0))
                advance()
                expect_operand = 0
                continue
            }
            if t == TK_STR {
                push_operand(new_node(ND_STR, 0, cur_val_word(), 0))
                advance()
                expect_operand = 0
                continue
            }
            if t == TK_TRUE {
                push_operand(new_node(ND_BOOL, 0, 1, 0))
                advance()
                expect_operand = 0
                continue
            }
            if t == TK_FALSE {
                push_operand(new_node(ND_BOOL, 0, 0, 0))
                advance()
                expect_operand = 0
                continue
            }
            if t == TK_KNOT {
                push_op(OPK_UNOP, UN_NOT, 0)
                advance()
                continue
            }
            if t == TK_TILDE {
                push_op(OPK_UNOP, UN_INV, 0)
                advance()
                continue
            }
            if t == TK_MINUS {
                push_op(OPK_UNOP, UN_NEG, 0)
                advance()
                continue
            }
            if t == TK_AMP {                       ; &name -- address-of
                advance()
                if cur_kind() == TK_IDENT {
                    ubyte nid
                    nid = lsb(cur_val_word())
                    advance()
                    push_operand(new_node(ND_ADDROF, 0, nid, 0))
                    expect_operand = 0
                }
                continue
            }
            if t == TK_AT {                        ; @( expr )
                advance()
                if cur_kind() == TK_LPAREN {
                    advance()
                }
                push_marker(OPK_MEMAT, operand_sp)
                continue
            }
            if t == TK_LPAREN {
                push_marker(OPK_LPAREN, operand_sp)
                advance()
                continue
            }
            if t == TK_IDENT {
                ubyte path
                path = read_dotted_path()
                if cur_kind() == TK_LPAREN {
                    advance()                      ; consume '('
                    push_marker(OPK_CALL, operand_sp)
                    op_a[op_sp - 1] = path
                    ; expect_operand stays 1 (first arg)
                } else {
                    push_operand(new_node(ND_IDENT, 0, path, 0))
                    expect_operand = 0
                    index_ok = 1
                }
                continue
            }
            break
        }

        ; ---- infix position ----
        if is_binop(t) != 0 {
            ubyte prec
            prec = bin_prec(t)
            repeat {
                if op_sp == 0 {
                    break
                }
                if op_kind[op_sp - 1] >= OPK_LPAREN {   ; stop at any marker
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
    return operand_stack[operand_sp]
}


; ---- serialization (iterative tree walk over the arena) ----
sub ws_push_node(ubyte node, ubyte depth) {
    ws_type[ws_sp] = 0
    ws_node[ws_sp] = node
    ws_depth[ws_sp] = depth
    ws_sp = ws_sp + 1
}
sub ws_push_simple(ubyte typ) {
    ws_type[ws_sp] = typ
    ws_sp = ws_sp + 1
}
; type 3: a ".field" line -- indent(depth) then '.' then the ident text.
sub ws_push_field(ubyte field_id, ubyte depth) {
    ws_type[ws_sp] = 3
    ws_node[ws_sp] = field_id
    ws_depth[ws_sp] = depth
    ws_sp = ws_sp + 1
}

sub out_indent(ubyte depth) {
    ubyte i
    i = 0
    repeat {
        if i >= depth {
            break
        }
        out_byte(' ')
        out_byte(' ')
        i = i + 1
    }
}

sub out_binop_spelling(ubyte op) {
    if op == TK_PLUS  { out_byte('+')  return }
    if op == TK_MINUS { out_byte('-')  return }
    if op == TK_STAR  { out_byte('*')  return }
    if op == TK_AMP   { out_byte('&')  return }
    if op == TK_PIPE  { out_byte('|')  return }
    if op == TK_CARET { out_byte('^')  return }
    if op == TK_SHL   { out_text("<<")  return }
    if op == TK_SHR   { out_text(">>")  return }
    if op == TK_EQ    { out_text("==")  return }
    if op == TK_NE    { out_text("!=")  return }
    if op == TK_LT    { out_byte('<')  return }
    if op == TK_LE    { out_text("<=")  return }
    if op == TK_GT    { out_byte('>')  return }
    if op == TK_GE    { out_text(">=")  return }
    if op == TK_KAND  { out_text("and")  return }
    if op == TK_KOR   { out_text("or")  return }
    if op == TK_KXOR  { out_text("xor")  return }
}

sub out_unop_spelling(ubyte op) {
    if op == UN_NEG { out_text("u-")  return }
    if op == UN_INV { out_byte('~')  return }
    if op == UN_NOT { out_text("not")  return }
}

sub out_ident_text(ubyte id) {
    ubyte off
    ubyte n
    ubyte j
    off = ident_off[id]
    n = ident_len[id]
    j = 0
    repeat {
        if j >= n {
            break
        }
        out_byte(ident_pool[off + j])
        j = j + 1
    }
}

sub out_str_escaped(ubyte id) {
    ubyte off
    ubyte n
    ubyte j
    off = str_off[id]
    n = str_len[id]
    j = 0
    repeat {
        if j >= n {
            break
        }
        ubyte rb
        rb = str_pool[off + j]
        if rb == '\\' { out_text("\\\\") }
        else {
            if rb == '"' { out_text("\\\"") }
            else {
                if rb == '\n' { out_text("\\n") }
                else {
                    if rb == '\r' { out_text("\\r") }
                    else {
                        if rb == '\t' { out_text("\\t") }
                        else { out_byte(rb) }
                    }
                }
            }
        }
        j = j + 1
    }
}

sub emit_node(ubyte node, ubyte depth) {
    out_indent(depth)
    out_byte('(')                                  ; '('
    ubyte k
    k = node_kind[node]
    if k == ND_INT {
        out_text("int ")   ; "int "
        out_dec(node_a_word(node))
        out_byte(')')
        return
    }
    if k == ND_BOOL {
        out_text("bool ")  ; "bool "
        if node_a_lo[node] != 0 {
            out_text("true")
        } else {
            out_text("false")
        }
        out_byte(')')
        return
    }
    if k == ND_IDENT {
        out_text("id ")                  ; "id "
        out_ident_text(node_a_lo[node])
        out_byte(')')
        return
    }
    if k == ND_STR {
        out_text("str \"")  ; str "
        out_str_escaped(node_a_lo[node])
        out_byte('"')
        out_byte(')')
        return
    }
    if k == ND_BINOP {
        out_binop_spelling(node_op[node])
        ws_push_simple(1)                          ; close paren
        ws_push_node(node_b[node], depth + 1)      ; rhs
        ws_push_simple(2)                          ; newline
        ws_push_node(node_a_lo[node], depth + 1)   ; lhs
        ws_push_simple(2)                          ; newline
        return
    }
    if k == ND_UNOP {
        out_unop_spelling(node_op[node])
        ws_push_simple(1)
        ws_push_node(node_a_lo[node], depth + 1)   ; operand
        ws_push_simple(2)
        return
    }
    if k == ND_ADDROF {
        out_text("addr ")  ; "addr "
        out_ident_text(node_a_lo[node])
        out_byte(')')
        return
    }
    if k == ND_MEMAT {
        out_text("mem")                  ; "mem"
        ws_push_simple(1)
        ws_push_node(node_a_lo[node], depth + 1)   ; addr
        ws_push_simple(2)
        return
    }
    if k == ND_INDEX {
        out_text("idx")                  ; "idx"
        ws_push_simple(1)                          ; close paren
        if node_op[node] != 0 {                    ; has .field
            ws_push_field(node_a_hi[node], depth + 1)
            ws_push_simple(2)                      ; newline
        }
        ws_push_node(node_b[node], depth + 1)      ; index
        ws_push_simple(2)
        ws_push_node(node_a_lo[node], depth + 1)   ; array
        ws_push_simple(2)
        return
    }
    if k == ND_CALL {
        out_text("call ")  ; "call "
        out_ident_text(node_a_lo[node])
        ws_push_simple(1)                          ; close paren
        ; args are a reversed cons list (head = last arg); walking
        ; head->tail and pushing node+newline yields forward pop order.
        ubyte cell
        cell = node_b[node]
        repeat {
            if cell == 0 {
                break
            }
            ws_push_node(cons_val[cell], depth + 1)
            ws_push_simple(2)                      ; newline
            cell = cons_next[cell]
        }
        return
    }
}

sub serialize(ubyte root) {
    ws_sp = 0
    ws_push_node(root, 0)
    repeat {
        if ws_sp == 0 {
            break
        }
        ws_sp = ws_sp - 1
        ubyte typ
        typ = ws_type[ws_sp]
        if typ == 0 {
            emit_node(ws_node[ws_sp], ws_depth[ws_sp])
        } else {
            if typ == 1 {
                out_byte(')')
            } else {
                if typ == 2 {
                    out_byte('\n')
                } else {
                    out_indent(ws_depth[ws_sp])        ; type 3: ".field"
                    out_byte('.')
                    out_ident_text(ws_node[ws_sp])
                }
            }
        }
    }
    out_byte('\n')
}


; ---- main ----
  sub start() {
    uword fn
    fn = sys_argv(0)
    src_hand = sys_open(fn)
    fn = sys_argv(1)
    dst_hand = sys_openout(fn)

    peek_ok = 0
    src_eof = 0
    tok_count = 0
    tok_pos = 0
    ident_count = 0
    ident_pool_len = 0
    str_count = 0
    str_pool_len = 0
    node_count = 1                                 ; node 0 = null
    operand_sp = 0
    op_sp = 0
    cons_count = 1                                 ; cons 0 = nil

    lex_all()
    ubyte root
    root = parse_expr()
    serialize(root)

    sys_close(src_hand)
    sys_close(dst_hand)
  }
}
