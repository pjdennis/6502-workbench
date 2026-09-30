; lexer.p8 -- the Prog8 lexer port (Phase 6, M1, on-target).
;
; Reads a .p8 source file (argv[0]) and writes the canonical token-stream
; dump (argv[1]) -- the exact format frozen by p8c/serialize.py's
; serialize_tokens() and `p8c --dump-tokens`. One token per line:
;
;     INT <decimal>            ; value normalized ($ff/%1010/'A' -> decimal)
;     STR "<escaped>"          ; same escape set as the AST string contract
;     IDENT <text>   KW <text>   DIRECTIVE <text>
;     PUNCT <spelling>         ; punctuation / operator (kind == value)
;     EOF
;
; This is the M1 on-target milestone: it must byte-match the Python
; token-dump for the same input. It runs on the emulator's nmos-default
; machine and uses the same file-I/O shim as tinyp8 (syscalls at
; $F006..$F03C). Source line/col are not emitted -- positions are not
; part of the structural contract (see PARSER_PORT_DESIGN.md section 4).
;
; Integer values are accumulated into a uword, so literals must fit in
; 16 bits (the realistic corpus does); decimal output uses power-of-ten
; subtraction because host p8c has no '/' or '%'. The decimal accumulator
; `(int_val << 3) + (int_val << 1) + (c - '0')` doubles as a regression
; test for the host-p8c codegen fix that lets both operands of a binary
; op each use scratch without clobbering each other.

%address $0200
%import strings
%output raw
%launcher none
main {

; ---- module-level state ----
ubyte src_hand
ubyte dst_hand
ubyte peek_buf
ubyte peek_ok
ubyte src_eof

ubyte[41] name_buf      ; current identifier / directive name (+1 for NUL term)
ubyte name_len

uword int_val           ; accumulated value of the current numeric literal

uword dec_v             ; out_dec scratch
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


; ---- source / destination I/O ----

; NB: the emulator REWINDS the input file to offset 0 when a read hits
; EOF (it supports two-pass tools re-reading their input). So EOF is not
; sticky at the syscall level -- read again and you get the file from the
; top. We make it sticky in software: once src_eof is set, never call
; _read again. Without this, a token that ends exactly at EOF (e.g. a
; file with no trailing newline) loops forever re-reading the rewound
; source.
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

sub out_nl() {
    out_byte('\n')
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


; ---- character-class helpers (return 1/0) ----

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
        return c - $57                                   ; 'a'-10
    }
    if c >= 'A' {
        return c - $37                                   ; 'A'-10
    }
    return c - '0'
}


; ---- decimal output (power-of-ten subtraction; no '/' in host p8c) ----

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
    out_byte(lsb(dec_v) + '0')                           ; ones place (dec_v < 10)
}


; ---- numeric literal scanners (accumulate into int_val) ----

sub read_hex() {                                         ; '$' already consumed
    int_val = 0
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == '_' {                                    ; '_' separator
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

sub read_bin() {                                         ; '%' already consumed
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

sub read_dec() {                                         ; first digit still peeked
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


; ---- escape decoding (shared by char + string literals) ----
;
; Decodes the char AFTER a backslash to its byte value, mirroring the
; host lexer. For '\xHH' it consumes the two hex digits from the source.

sub decode_escape_val(ubyte e) -> ubyte {
    if e == 'n' { return '\n' }                           ; \n
    if e == 'r' { return '\r' }                           ; \r
    if e == 't' { return '\t' }                           ; \t
    if e == '0' { return $00 }                           ; \0
    if e == '\'' { return '\'' }                           ; \'
    if e == '\\' { return '\\' }                           ; backslash
    if e == '"' { return '"' }                           ; \"
    if e == 'x' {                                        ; \xHH
        ubyte h1
        ubyte h2
        h1 = read_src()
        h2 = read_src()
        return (hex_nibble(h1) << 4) + hex_nibble(h2)
    }
    return e                                             ; fallback: literal
}


; ---- identifier reading ----

sub read_ident() {                                       ; next peeked char starts an ident
    name_len = 0
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if is_alnum_us(c) != 0 {
            c = read_src()
            if name_len < 40 {
                name_buf[name_len] = c
                name_len = name_len + 1
            }
        } else {
            return
        }
    }
}

; The Prog8 reserved words (from p8c.lex.KEYWORDS). kw_match tests membership
; against this table with strings.compare, so adding a keyword is a one-line
; table edit rather than a hand-written char-by-char compare.
uword[40] keywords = [
    "as", "do", "if", "in", "or", "to",
    "and", "for", "not", "str", "sub", "xor",
    "bool", "byte", "else", "enum", "goto", "main", "step", "true", "void",
    "when", "word",
    "break", "const", "defer", "false", "ubyte", "until", "uword", "while",
    "asmsub", "downto", "extsub", "inline", "repeat", "return", "struct",
    "private", "continue" ]

; kw_match: returns 1 if name_buf[0..name_len-1] is a Prog8 keyword, else 0.
sub kw_match() -> ubyte {
    name_buf[name_len] = 0                  ; NUL-terminate for strings.compare
    ubyte i
    i = 0
    repeat {
        if i >= 40 { break }
        if strings.compare(&name_buf, keywords[i]) == 0 { return 1 }
        i = i + 1
    }
    return 0
}


; ---- tag emitters ----

sub emit_int_head() {                                    ; "INT "
    out_text("INT ")
}

sub emit_str_head() {                                    ; "STR \""
    out_text("STR \"")
}

sub emit_ident_head() {                                  ; "IDENT "
    out_text("IDENT ")
}

sub emit_kw_head() {                                     ; "KW "
    out_text("KW ")
}

sub emit_dir_head() {                                    ; "DIRECTIVE "
    out_text("DIRECTIVE ")
}

; PUNCT <spelling>\n -- spelling is a string ("<<=", "==", "+", ...).
sub emit_punct(uword s) {
    out_text("PUNCT ")
    out_text(s)
    out_nl()
}

sub emit_eof() {                                         ; "EOF\n"
    out_text("EOF") out_nl()
}

sub out_ident() {
    ubyte i
    i = 0
    repeat {
        if i >= name_len {
            break
        }
        out_byte(name_buf[i])
        i = i + 1
    }
}

; out_escaped: write one real byte using the canonical output escape set.
sub out_escaped(ubyte rb) {
    if rb == '\\' {
        out_text("\\\\")                      ; backslash -> \\
        return
    }
    if rb == '"' {
        out_text("\\\"")                      ; " -> \"
        return
    }
    if rb == '\n' {
        out_text("\\n")                      ; nl -> \n
        return
    }
    if rb == '\r' {
        out_text("\\r")                      ; cr -> \r
        return
    }
    if rb == '\t' {
        out_text("\\t")                      ; tab -> \t
        return
    }
    out_byte(rb)
}

; ---- raw %asm normalization (mirrors the Python oracle) ----
; is c asm-line horizontal whitespace (stripped at line ends)?
sub asm_ws(ubyte c) -> ubyte {
    if c == ' ' { return 1 }
    if c == '\t' { return 1 }
    if c == '\r' { return 1 }
    return 0
}

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

; A raw `%asm {{ ... }}` block (the `DIRECTIVE asm` token already emitted): skip
; to and consume `{{`, emit the two `{` puncts, then -- if the body is a quoted
; string (legacy form) -- return and let the main loop lex the STR + `}}`;
; otherwise capture the body, normalize it (strip each line, drop blank lines,
; join with '\n'), and emit it as one STR token followed by the two `}` puncts.
sub lex_asm_raw() {
    skip_asm_ws()
    if peek_src() != '{' { return }          ; bare `%asm` (no body): just the directive
    ubyte b
    b = read_src()                           ; first '{'
    if peek_src() != '{' {                   ; a lone `{`: emit it as a normal punct
        emit_punct("{")
        return
    }
    b = read_src()                           ; second '{'
    emit_punct("{")
    emit_punct("{")
    skip_asm_ws()
    if peek_src() == '"' {
        return                               ; legacy quoted body: main loop lexes it
    }
    emit_str_head()
    ubyte started
    ubyte sol
    uword sp
    started = 0
    sol = 1
    sp = 0
    repeat {
        ubyte c
        c = read_src()
        if src_eof != 0 { break }
        if c == '}' {
            if peek_src() == '}' { c = read_src()  break }
        }
        if c == '\n' { sol = 1  sp = 0  continue }
        if c == '\r' { continue }
        if asm_ws(c) != 0 {
            if sol == 0 { sp = sp + 1 }
            continue
        }
        if sol != 0 {
            if started != 0 { out_escaped('\n') }
            sol = 0
        } else {
            repeat {
                if sp == 0 { break }
                out_escaped(' ')
                sp = sp - 1
            }
        }
        out_escaped(c)
        started = 1
    }
    out_byte('"')
    out_nl()
    emit_punct("}")
    emit_punct("}")
}


; ---- composite literal lexers ----

sub lex_char() {                                         ; opening ' already consumed
    ubyte c
    c = read_src()
    if src_eof != 0 {
        return
    }
    if c == '\\' {                                        ; escape
        ubyte e
        e = read_src()
        int_val = decode_escape_val(e)
    } else {
        int_val = c
    }
    c = read_src()                                       ; consume closing '
    emit_int_head()
    out_dec(int_val)
    out_nl()
}

sub lex_string() {                                       ; opening " already consumed
    emit_str_head()
    repeat {
        ubyte c
        c = read_src()
        if src_eof != 0 {
            break
        }
        if c == '"' {                                    ; closing "
            break
        }
        ubyte rb
        if c == '\\' {
            ubyte e
            e = read_src()
            rb = decode_escape_val(e)
        } else {
            rb = c
        }
        out_escaped(rb)
    }
    out_byte('"')
    out_nl()
}

sub skip_to_nl() {
    repeat {
        ubyte c
        c = read_src()
        if src_eof != 0 {
            break
        }
        if c == '\n' {
            break
        }
    }
}

; lex_operator: emit the longest punctuation/operator token whose first
; char is `c` (already consumed). At EOF the peeked char reads back as 0,
; so every multi-char test fails and we fall through to the single form.
sub lex_operator(ubyte c) {
    ubyte c2
    if c == '<' {                                        ; <  <=  <<  <<=
        c2 = peek_src()
        if c2 == '<' {
            c2 = read_src()
            c2 = peek_src()
            if c2 == '=' {
                c2 = read_src()
                emit_punct("<<=")
            } else {
                emit_punct("<<")
            }
        } else {
            if c2 == '=' {
                c2 = read_src()
                emit_punct("<=")
            } else {
                emit_punct("<")
            }
        }
        return
    }
    if c == '>' {                                        ; >  >=  >>  >>=
        c2 = peek_src()
        if c2 == '>' {
            c2 = read_src()
            c2 = peek_src()
            if c2 == '=' {
                c2 = read_src()
                emit_punct(">>=")
            } else {
                emit_punct(">>")
            }
        } else {
            if c2 == '=' {
                c2 = read_src()
                emit_punct(">=")
            } else {
                emit_punct(">")
            }
        }
        return
    }
    if c == '=' {                                        ; =  ==
        c2 = peek_src()
        if c2 == '=' {
            c2 = read_src()
            emit_punct("==")
        } else {
            emit_punct("=")
        }
        return
    }
    if c == '!' {                                        ; !  !=
        c2 = peek_src()
        if c2 == '=' {
            c2 = read_src()
            emit_punct("!=")
        } else {
            emit_punct("!")
        }
        return
    }
    if c == '+' {                                        ; +  ++  +=
        c2 = peek_src()
        if c2 == '+' {
            c2 = read_src()
            emit_punct("++")
        } else {
            if c2 == '=' {
                c2 = read_src()
                emit_punct("+=")
            } else {
                emit_punct("+")
            }
        }
        return
    }
    if c == '-' {                                        ; -  --  -=  ->
        c2 = peek_src()
        if c2 == '-' {
            c2 = read_src()
            emit_punct("--")
        } else {
            if c2 == '=' {
                c2 = read_src()
                emit_punct("-=")
            } else {
                if c2 == '>' {
                    c2 = read_src()
                    emit_punct("->")
                } else {
                    emit_punct("-")
                }
            }
        }
        return
    }
    if c == '*' {                                        ; *  *=
        c2 = peek_src()
        if c2 == '=' {
            c2 = read_src()
            emit_punct("*=")
        } else {
            emit_punct("*")
        }
        return
    }
    if c == '/' {                                        ; /  /=
        c2 = peek_src()
        if c2 == '=' {
            c2 = read_src()
            emit_punct("/=")
        } else {
            emit_punct("/")
        }
        return
    }
    if c == '&' {                                        ; &  &&  &=
        c2 = peek_src()
        if c2 == '&' {
            c2 = read_src()
            emit_punct("&&")
        } else {
            if c2 == '=' {
                c2 = read_src()
                emit_punct("&=")
            } else {
                emit_punct("&")
            }
        }
        return
    }
    if c == '|' {                                        ; |  |=
        c2 = peek_src()
        if c2 == '=' {
            c2 = read_src()
            emit_punct("|=")
        } else {
            emit_punct("|")
        }
        return
    }
    if c == '^' {                                        ; ^  ^=
        c2 = peek_src()
        if c2 == '=' {
            c2 = read_src()
            emit_punct("^=")
        } else {
            emit_punct("^")
        }
        return
    }
    ; pure single-char punctuation: ( ) [ ] { } , . : ~ @ ?
    out_text("PUNCT ")
    out_byte(c)
    out_nl()
}


; ---- main lex loop ----

  sub start() {
    uword fn
    fn = sys_argv(0)
    src_hand = sys_open(fn)
    fn = sys_argv(1)
    dst_hand = sys_openout(fn)

    peek_ok = 0
    src_eof = 0

    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            break
        }

        ; whitespace
        if c == ' ' {
            c = read_src()
            continue
        }
        if c == '\t' {
            c = read_src()
            continue
        }
        if c == '\n' {
            c = read_src()
            continue
        }
        if c == '\r' {
            c = read_src()
            continue
        }
        ; ';' line comment
        if c == ';' {
            skip_to_nl()
            continue
        }

        ; '%' -- directive, binary literal, or bare '%'
        if c == '%' {
            c = read_src()                               ; consume '%'
            ubyte c2
            c2 = peek_src()
            if src_eof != 0 {
                emit_punct("%")
                continue
            }
            if is_alpha_us(c2) != 0 {
                read_ident()
                emit_dir_head()
                out_ident()
                out_nl()
                ; raw `%asm {{ ... }}` -> one normalized STR (Python-oracle parity)
                if name_len == 3 {
                    if name_buf[0] == 'a' {
                        if name_buf[1] == 's' {
                            if name_buf[2] == 'm' { lex_asm_raw() }
                        }
                    }
                }
                continue
            }
            if c2 == '0' {
                read_bin()
                emit_int_head()
                out_dec(int_val)
                out_nl()
                continue
            }
            if c2 == '1' {
                read_bin()
                emit_int_head()
                out_dec(int_val)
                out_nl()
                continue
            }
            emit_punct("%")
            continue
        }

        ; '$' hex literal
        if c == '$' {
            c = read_src()                               ; consume '$'
            read_hex()
            emit_int_head()
            out_dec(int_val)
            out_nl()
            continue
        }

        ; decimal literal
        if is_digit(c) != 0 {
            read_dec()
            emit_int_head()
            out_dec(int_val)
            out_nl()
            continue
        }

        ; char literal
        if c == '\'' {
            c = read_src()                               ; consume opening '
            lex_char()
            continue
        }

        ; string literal
        if c == '"' {
            c = read_src()                               ; consume opening "
            lex_string()
            continue
        }

        ; identifier / keyword
        if is_alpha_us(c) != 0 {
            read_ident()
            if kw_match() != 0 {
                emit_kw_head()
            } else {
                emit_ident_head()
            }
            out_ident()
            out_nl()
            continue
        }

        ; operator / punctuation
        c = read_src()
        lex_operator(c)
    }

    emit_eof()

    sys_close(src_hand)
    sys_close(dst_hand)
  }
}
