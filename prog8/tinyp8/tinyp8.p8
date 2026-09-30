; tinyp8.p8 -- a port of tinyp8.s to Prog8.
;
; This is the self-host milestone for the host p8c compiler: a real,
; working compiler written in our language and compiled by us. The
; compiled output is meant to be byte-equivalent (or behaviorally
; equivalent) to the hand-written tinyp8.s.
;
; All file I/O syscalls are bound as asmsubs targeting the nmos-default
; emulator stubs at $F006..$F03C. The carry-flag EOF signal from `read`
; is captured via a small inline-asm helper that stashes the EOF state
; in a module-level `src_eof` byte.

%address $0200
%output raw
%launcher none
main {

; Load address constant -- used to compute absolute addresses for the
; in-output __hex_print helper that v2 emits when a variable is
; referenced from print_ub.
const uword LOAD_ADDR = $0200

; ---- v7: comparison-operator decoding + branch emission ----
;
; Op codes used by read_cmp_op and emit_skip_branch:
;   0 = ==    skip body on !=    -> bne +N
;   1 = !=    skip body on ==    -> beq +N
;   2 = <     skip body on >=    -> bcs +N
;   3 = <=    skip body on >     -> beq +2; bcs +N    (2-step)
;   4 = >     skip body on <=    -> beq +(N+2); bcc +N (2-step)
;   5 = >=    skip body on <     -> bcc +N
const ubyte OP_EQ = 0
const ubyte OP_NE = 1
const ubyte OP_LT = 2
const ubyte OP_LE = 3
const ubyte OP_GT = 4
const ubyte OP_GE = 5

; Branch-emission opcode constants.
const ubyte OPC_BNE = $d0
const ubyte OPC_BEQ = $f0
const ubyte OPC_BCC = $90
const ubyte OPC_BCS = $b0

; read_cmp_op: skips whitespace then reads a 1- or 2-char comparison
; operator from the source. Returns the OP_* code. On EOF, returns 0
; (caller should re-check src_eof).
sub read_cmp_op() -> ubyte {
    ubyte c
    ; skip whitespace
    repeat {
        c = peek_src()
        if src_eof != 0 {
            return 0
        }
        if c == $20 {                                    ; space
            c = read_src()
        } else {
            if c == $09 {                                ; tab
                c = read_src()
            } else {
                break
            }
        }
    }
    c = read_src()
    if src_eof != 0 {
        return 0
    }
    if c == $3d {                                        ; '=' -> "=="
        c = read_src()                                   ; consume second '='
        return OP_EQ
    }
    if c == $21 {                                        ; '!' -> "!="
        c = read_src()                                   ; consume '='
        return OP_NE
    }
    if c == $3c {                                        ; '<' or "<="
        c = peek_src()
        if c == $3d {
            c = read_src()
            return OP_LE
        }
        return OP_LT
    }
    if c == $3e {                                        ; '>' or ">="
        c = peek_src()
        if c == $3d {
            c = read_src()
            return OP_GE
        }
        return OP_GT
    }
    return 0                                             ; unknown -- fallback to ==
}

; emit_skip_branch: emits the conditional branch sequence that BRANCHES
; OVER `skip_size` bytes when the comparison is FALSE. Used by both
; parse_if (over the then-block) and parse_while (over body+jmp).
; Single-op variants emit 2 bytes; LE/GT emit 4 bytes (two branches).
sub emit_skip_branch(ubyte op, ubyte skip_size) {
    when op {
        OP_EQ -> {
            write_dst(OPC_BNE)
            write_dst(skip_size)
        }
        OP_NE -> {
            write_dst(OPC_BEQ)
            write_dst(skip_size)
        }
        OP_LT -> {
            write_dst(OPC_BCS)
            write_dst(skip_size)
        }
        OP_GE -> {
            write_dst(OPC_BCC)
            write_dst(skip_size)
        }
        OP_LE -> {
            ; A <= B  ==  (A == B) || (A < B). Skip body iff A > B,
            ; i.e. !Z && C set. We branch to the body on equality
            ; (jump over the bcs that would skip), then bcs the body.
            write_dst(OPC_BEQ)
            write_dst($02)                               ; over the bcs
            write_dst(OPC_BCS)
            write_dst(skip_size)
        }
        OP_GT -> {
            ; A > B  ==  !Z && C set. Skip body on Z OR !C.
            ; First branch over the second branch + body on equality.
            write_dst(OPC_BEQ)
            write_dst(skip_size + 2)                     ; over bcc + body
            write_dst(OPC_BCC)
            write_dst(skip_size)
        }
        else -> {
            ; Unknown op -- emit a hard skip (jmp +N) to be safe.
            write_dst(OPC_BNE)
            write_dst(skip_size)
        }
    }
}


; ---- syscall asmsubs (register ABI; emulator $F006+ stubs) ----
extsub $F00F = sys_exit(ubyte code @A)
extsub $F015 = sys_close(ubyte handle @A)

; ---- module-level state ----
ubyte src_hand
ubyte dst_hand
ubyte peek_buf
ubyte peek_ok
ubyte src_eof
ubyte tmp_byte

; v2/v9 (variables) state -- a small symbol table that supports
; multi-character variable names (v9; up to 8 chars each, 16 vars max).
;   sym_names[]  = packed name bytes, 16 entries x 8 bytes each. The
;                  name for slot i lives at sym_names[i*8 .. i*8+len-1].
;   sym_lens[i]  = length of the name in slot i (1..8).
;   sym_addrs[i] = ZP address allocated for the variable in slot i.
;   sym_count    = number of live slots.
;   name_buf[]   = scratch for the identifier currently being read.
;   name_len     = its length (set by read_ident).
;   next_var_addr = next free ZP slot, starts at $60 (above tinyp8's
;                   own state which lives below $40 in compiled
;                   programs that use this scheme).
;   helper_emitted = 0 until __hex_print is emitted into the output;
;                    then 1, and helper_addr is its absolute address.
;   bytes_emitted  = count of bytes written to the output file so far;
;                    load_addr + bytes_emitted is the current output PC.
ubyte[128] sym_names
ubyte[16] sym_lens
ubyte[16] sym_addrs
ubyte sym_count
ubyte[8] name_buf
ubyte name_len
ubyte next_var_addr
ubyte helper_emitted
uword bytes_emitted
uword helper_addr

; ---- v9: identifier reading + symbol-table lookup/declare ----
;
; read_ident: skip leading whitespace, then read a run of lowercase
; letters [a-z]+ into name_buf, setting name_len. The terminating
; non-letter is left unconsumed (peeked), so callers' existing skip
; loops still see it. Names longer than 8 chars are truncated in the
; buffer but fully consumed from the source.
sub read_ident() {
    ubyte c
    name_len = 0
    ; skip whitespace (space, tab, newline, cr)
    repeat {
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $20 {
            c = read_src()
        } else {
            if c == $09 {
                c = read_src()
            } else {
                if c == $0a {
                    c = read_src()
                } else {
                    if c == $0d {
                        c = read_src()
                    } else {
                        break
                    }
                }
            }
        }
    }
    ; read the run of lowercase letters
    repeat {
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c >= $61 {                                    ; 'a'
            if c <= $7a {                                ; 'z'
                if name_len < 8 {
                    name_buf[name_len] = c
                    name_len = name_len + 1
                }
                c = read_src()
            } else {
                return
            }
        } else {
            return
        }
    }
}

; find_var: linear scan of the symbol table for the name currently in
; name_buf[0..name_len-1]. Returns the variable's ZP address, or 0 if
; the name is not declared (0 is never a real address -- allocation
; starts at $60).
sub find_var() -> ubyte {
    ubyte i
    ubyte off
    i = 0
    off = 0
    repeat {
        if i >= sym_count {
            return 0
        }
        if sym_lens[i] == name_len {
            ubyte j
            ubyte match
            match = 1
            j = 0
            repeat {
                if j >= name_len {
                    break
                }
                if sym_names[off + j] != name_buf[j] {
                    match = 0
                    break
                }
                j = j + 1
            }
            if match != 0 {
                return sym_addrs[i]
            }
        }
        off = off + 8
        i = i + 1
    }
}

; declare_var: return the existing ZP address for the name in name_buf,
; or allocate a fresh slot (and ZP byte) if it is new. Returns the
; address either way.
sub declare_var() -> ubyte {
    ubyte a
    a = find_var()
    if a != 0 {
        return a
    }
    ; allocate a new slot: copy name_buf into sym_names[sym_count*8].
    ubyte off
    off = sym_count << 3
    ubyte j
    j = 0
    repeat {
        if j >= name_len {
            break
        }
        sym_names[off + j] = name_buf[j]
        j = j + 1
    }
    sym_lens[sym_count] = name_len
    sym_addrs[sym_count] = next_var_addr
    a = next_var_addr
    next_var_addr = next_var_addr + 1
    sym_count = sym_count + 1
    return a
}

; ---- low-level I/O helpers (inline asm wrappers) ----
;
; Each wrapper is a Prog8 sub whose body is one %asm{{...}} block.
; We deliberately reference the mangled p8v_<sub>_arg_<name> slots
; so the wrappers see the same parameter values the caller wrote.

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

extsub $f01b = sys_argc() -> ubyte @A

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


; ---- source I/O ----

sub read_src() -> ubyte {
    if peek_ok != 0 {
        peek_ok = 0
        return peek_buf
    }
    return sys_read(src_hand)
}

sub peek_src() -> ubyte {
    if peek_ok == 0 {
        ubyte b
        b = sys_read(src_hand)
        if src_eof != 0 {
            return 0
        }
        peek_buf = b
        peek_ok = 1
    }
    return peek_buf
}


; ---- destination I/O ----

sub write_dst(ubyte b) {
    sys_write(b, dst_hand)
    bytes_emitted = bytes_emitted + 1
}


; ---- skip helpers ----

sub skip_to_nl() {
    ubyte c
    repeat {
        c = read_src()
        if src_eof != 0 {
            break
        }
        if c == $0a {
            break
        }
    }
}

sub skip_ws_comments() {
    repeat {
        ubyte c
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $20 {
            ; eat
            c = read_src()
        } else {
            if c == $09 {
                c = read_src()
            } else {
                if c == $0a {
                    c = read_src()
                } else {
                    if c == $0d {
                        c = read_src()
                    } else {
                        if c == $3b {                    ; ';'
                            skip_to_nl()
                        } else {
                            return
                        }
                    }
                }
            }
        }
    }
}


; ---- nibble helpers ----

sub nibble_to_ascii(ubyte n) -> ubyte {
    if n >= $0a {
        return n + $57                                   ; 'a' - 10
    }
    return n + $30                                       ; '0'
}

sub hex_nibble(ubyte c) -> ubyte {
    if c >= $61 {                                        ; 'a'
        return c - $57
    }
    if c >= $41 {                                        ; 'A'
        return c - $37
    }
    return c - $30
}


; ---- emitters ----
;
; Each "print one char" sequence is 7 bytes:
;   lda #ch        ; A9 ch
;   jsr write_b    ; 20 09 F0   (write_b = $F009)

sub emit_print_char(ubyte ch) {
    write_dst($a9)                                       ; LDA #
    write_dst(ch)
    write_dst($20)                                       ; JSR
    write_dst($09)                                       ; low byte of $F009
    write_dst($f0)                                       ; high byte
}

sub emit_print_ub_seq(ubyte b) {
    ubyte hi
    ubyte lo
    hi = b >> 4
    lo = b & $0f
    emit_print_char(nibble_to_ascii(hi))
    emit_print_char(nibble_to_ascii(lo))
}

sub emit_exit_seq() {
    write_dst($a9)                                       ; LDA #
    write_dst($00)                                       ; 0
    write_dst($20)                                       ; JSR
    write_dst($0f)                                       ; low byte of $F00F
    write_dst($f0)                                       ; high byte
}


; ---- parse helpers ----

sub parse_print_string() {
    ubyte c
    ; Find the opening quote.
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $22 {                                    ; '"'
            break
        }
    }
    ; Read string chars until closing quote.
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $22 {
            break
        }
        emit_print_char(c)
    }
    ; Trailing newline.
    emit_print_char($0a)
    skip_to_nl()
}

sub parse_print_ub() {
    ubyte c
    ; Skip whitespace. The next non-ws byte is either '$' for a literal
    ; byte value or a lowercase letter for a variable reference (v9:
    ; multi-character names).
    repeat {
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $20 {                                    ; space
            c = read_src()
        } else {
            if c == $09 {                                ; tab
                c = read_src()
            } else {
                break
            }
        }
    }
    if c != $24 {                                        ; not '$' -> var ref
        ; Look up the variable's ZP address and emit a runtime hex-print
        ; sequence against it. If the variable was never declared
        ; (find_var == 0) we emit nothing, but the parse stays well-formed.
        read_ident()
        ubyte addr
        addr = find_var()
        if addr != 0 {
            emit_print_ub_var(addr)
        }
        skip_to_nl()
        return
    }
    c = read_src()                                       ; consume '$'
    ; Two hex digits (literal form).
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = hex_nibble(c) << 4
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = tmp_byte | hex_nibble(c)
    emit_print_ub_seq(tmp_byte)
    emit_print_char($0a)
    skip_to_nl()
}

sub parse_print_uw() {
    ubyte c
    ; Find the '$' sigil.
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $24 {                                    ; '$'
            break
        }
    }
    ; Four hex digits -- emit one print_char per nibble (no need to
    ; reassemble into a uword; each digit is independently printable).
    ubyte i
    for i in 0 to 3 {
        c = read_src()
        if src_eof != 0 {
            return
        }
        emit_print_char(nibble_to_ascii(hex_nibble(c)))
    }
    emit_print_char($0a)
    skip_to_nl()
}

sub parse_print() {
    ubyte c
    ; Skip "rint"
    c = read_src()
    c = read_src()
    c = read_src()
    c = read_src()
    if src_eof != 0 {
        return
    }
    ; Peek the next char: '_' means print_ub/print_uw, else string form.
    c = read_src()
    if src_eof != 0 {
        return
    }
    if c == $5f {                                        ; '_'
        c = read_src()                                   ; 'u'
        c = read_src()                                   ; 'b' or 'w'
        if src_eof != 0 {
            return
        }
        if c == $77 {                                    ; 'w'
            parse_print_uw()
        } else {
            parse_print_ub()
        }
    } else {
        ; The byte we already consumed should be ws or the leading
        ; quote; parse_print_string will scan forward to '"' so
        ; that's fine.
        parse_print_string()
    }
}


; ---- v2: variable declarations + the runtime hex-print helper ----
;
; emit_hex_helper writes a position-relative byte-to-2-hex-chars
; routine inline into the output, wrapped in a JMP that branches over
; it so it isn't executed by accident. After this runs:
;   helper_addr = absolute address (load_addr + offset) callable via JSR
;   helper_emitted = 1
; The helper itself only uses BCC/BNE for branching and JSR/JMP $F009
; (write_b) for output, so its bytes are position-independent except
; for the wrapping JMP.

inline sub emit_hex_helper() {
    if helper_emitted != 0 {
        return
    }
    ; Compute where the helper will live and where to branch around
    ; it: JMP-around starts at the current position, the helper proper
    ; starts 3 bytes later (after the JMP), the user code resumes 38
    ; bytes after that.
    uword start = LOAD_ADDR + bytes_emitted
    helper_addr = start + 3                              ; helper starts here
    uword after = helper_addr + 38                       ; user code resumes here
    ; JMP <after>
    write_dst($4c)
    write_dst(lsb(after))
    write_dst(msb(after))
    ; --- the 38-byte helper itself (position-independent) ---
    write_dst($48)                                       ; pha
    write_dst($4a)                                       ; lsr a
    write_dst($4a)                                       ; lsr a
    write_dst($4a)                                       ; lsr a
    write_dst($4a)                                       ; lsr a
    write_dst($c9)                                       ; cmp #
    write_dst($0a)                                       ;   #$0a
    write_dst($90)                                       ; bcc
    write_dst($05)                                       ;   +5 -> digit1
    write_dst($18)                                       ; clc
    write_dst($69)                                       ; adc #
    write_dst($57)                                       ;   'a' - 10
    write_dst($d0)                                       ; bne
    write_dst($03)                                       ;   +3 -> print1
    write_dst($18)                                       ; clc        (.digit1)
    write_dst($69)                                       ; adc #
    write_dst($30)                                       ;   '0'
    write_dst($20)                                       ; jsr        (.print1)
    write_dst($09)                                       ;   low byte of $F009
    write_dst($f0)                                       ;   high byte
    write_dst($68)                                       ; pla
    write_dst($29)                                       ; and #
    write_dst($0f)                                       ;   $0f -- low nibble
    write_dst($c9)                                       ; cmp #
    write_dst($0a)                                       ;   #$0a
    write_dst($90)                                       ; bcc
    write_dst($05)                                       ;   +5 -> digit2
    write_dst($18)                                       ; clc
    write_dst($69)                                       ; adc #
    write_dst($57)                                       ;   'a' - 10
    write_dst($d0)                                       ; bne
    write_dst($03)                                       ;   +3 -> print2
    write_dst($18)                                       ; clc        (.digit2)
    write_dst($69)                                       ; adc #
    write_dst($30)                                       ;   '0'
    write_dst($4c)                                       ; jmp        (.print2 -- tail call)
    write_dst($09)                                       ;   $F009
    write_dst($f0)
    helper_emitted = 1
}

; parse_let -- handles a single `let X = $YY` statement. The 'l' has
; already been read; we expect "et " then the variable name (one
; lowercase letter) then ' = $XX'. Emits code that stores $YY into
; the variable's ZP slot.
sub parse_let() {
    ubyte c
    ; skip "et"
    c = read_src()
    c = read_src()
    if src_eof != 0 {
        return
    }
    ; Read the variable name (v9: multi-character) and declare it,
    ; allocating a ZP slot on first sight.
    read_ident()
    if src_eof != 0 {
        return
    }
    ubyte addr
    addr = declare_var()
    ; skip ws + '='
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $3d {                                    ; '='
            break
        }
    }
    ; ---- RHS: parse first operand and emit its load. Then check for
    ;       an optional `+` or `-` followed by a second operand.
    parse_let_emit_load_first()
    if src_eof != 0 {
        return
    }
    ; Skip whitespace; if next non-ws is '+' or '-', emit arithmetic.
    repeat {
        c = peek_src()
        if src_eof != 0 {
            break
        }
        if c == $20 {                                    ; space
            c = read_src()
        } else {
            if c == $09 {                                ; tab
                c = read_src()
            } else {
                break
            }
        }
    }
    c = peek_src()
    if src_eof == 0 {
        if c == $2b {                                    ; '+'
            c = read_src()
            parse_let_emit_arith($18)                    ; CLC/ADC path
        } else {
            if c == $2d {                                ; '-'
                c = read_src()
                parse_let_emit_arith($38)                ; SEC/SBC path
            }
        }
    }
    write_dst($85)                                       ; STA zp
    write_dst(addr)
    skip_to_nl()
}

; Helper: parse + emit the LDA for the first RHS operand. The value
; ends up in A at runtime; the caller then either stores it directly
; (no arithmetic) or chains an ADC/SBC against the second operand.
sub parse_let_emit_load_first() {
    ubyte c
    ; skip whitespace to the operand
    repeat {
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $20 {                                    ; space
            c = read_src()
        } else {
            if c == $09 {                                ; tab
                c = read_src()
            } else {
                break
            }
        }
    }
    if c == $24 {                                        ; '$' literal
        c = read_src()                                   ; consume '$'
        c = read_src()
        if src_eof != 0 {
            return
        }
        tmp_byte = hex_nibble(c) << 4
        c = read_src()
        if src_eof != 0 {
            return
        }
        tmp_byte = tmp_byte | hex_nibble(c)
        write_dst($a9)                                   ; LDA #
        write_dst(tmp_byte)
        return
    }
    ; variable (v9: multi-character)
    read_ident()
    write_dst($a5)                                       ; LDA zp
    write_dst(find_var())
}

; Helper: emit CLC/SEC + ADC/SBC against the second operand.
; first_op = $18 (CLC) for ADD path, $38 (SEC) for SUB path.
sub parse_let_emit_arith(ubyte first_op) {
    write_dst(first_op)
    ubyte zp_op
    ubyte imm_op
    if first_op == $18 {
        zp_op = $65                                      ; ADC zp
        imm_op = $69                                     ; ADC #
    } else {
        zp_op = $e5                                      ; SBC zp
        imm_op = $e9                                     ; SBC #
    }
    ubyte c
    repeat {
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $20 {
            c = read_src()
        } else {
            if c == $09 {
                c = read_src()
            } else {
                break
            }
        }
    }
    if c == $24 {                                        ; '$' literal
        c = read_src()                                   ; consume '$'
        c = read_src()
        if src_eof != 0 {
            return
        }
        tmp_byte = hex_nibble(c) << 4
        c = read_src()
        if src_eof != 0 {
            return
        }
        tmp_byte = tmp_byte | hex_nibble(c)
        write_dst(imm_op)
        write_dst(tmp_byte)
        return
    }
    ; variable (v9: multi-character)
    read_ident()
    write_dst(zp_op)
    write_dst(find_var())
}

; Emit a print_ub call against a variable reference (single letter).
; The byte at `addr` is loaded into A and then JSR'd to the in-output
; hex-print helper, which writes 2 ASCII hex chars. A trailing newline
; matches the literal-form output.
sub emit_print_ub_var(ubyte addr) {
    emit_hex_helper()
    write_dst($a5)                                       ; LDA zp
    write_dst(addr)
    write_dst($20)                                       ; JSR
    write_dst(lsb(helper_addr))
    write_dst(msb(helper_addr))
    ; trailing newline
    emit_print_char($0a)
}

; ---- v6: `while X != $YY` loop with a fixed-shape increment body ----
;
; The body is restricted to `let X = X + $ZZ` (variable += literal),
; which compiles to a known 7 bytes; that lets us hard-code both the
; BEQ skip displacement (10 bytes = body + jmp) and the JMP-back
; target (recorded as bytes_emitted at the loop top).
;
;   while X != $YY
;       let X = X + $ZZ
;
; Compiled output (14 bytes per while):
;   loop_top: lda <X>        ; 2
;             cmp #$YY       ; 2
;             beq +10        ; 2  -- skip body + jmp on equal
;             lda <X>        ; 2
;             clc            ; 1
;             adc #$ZZ       ; 2
;             sta <X>        ; 2
;             jmp loop_top   ; 3
;   loop_exit:
sub parse_while() {
    ubyte c
    ; skip 'h','i','l','e'
    c = read_src()
    c = read_src()
    c = read_src()
    c = read_src()
    if src_eof != 0 {
        return
    }
    ; Read the loop variable name (v9: multi-character).
    read_ident()
    if src_eof != 0 {
        return
    }
    ubyte x_addr
    x_addr = find_var()
    ; Read the comparison operator: ==, !=, <, <=, >, >=.
    ubyte op
    op = read_cmp_op()
    if src_eof != 0 {
        return
    }
    ; skip ws to '$'
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $24 {
            break
        }
    }
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = hex_nibble(c) << 4
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = tmp_byte | hex_nibble(c)
    ubyte cmp_val
    cmp_val = tmp_byte
    skip_to_nl()
    ; ---- v8: optional `print_ub Y` body statement before the let ----
    ; Peek the first non-ws byte of the next line. 'p' -> print + let
    ; body; 'l' -> let-only body (v6 behavior).
    ubyte has_print
    has_print = 0
    ubyte print_addr
    print_addr = 0
    repeat {
        c = peek_src()
        if src_eof != 0 {
            return
        }
        if c == $20 {
            c = read_src()
        } else {
            if c == $09 {
                c = read_src()
            } else {
                if c == $0a {
                    c = read_src()
                } else {
                    if c == $0d {
                        c = read_src()
                    } else {
                        break
                    }
                }
            }
        }
    }
    c = peek_src()
    if c == $70 {                                        ; 'p' of "print_ub Y"
        has_print = 1
        ; Consume "print_ub"
        c = read_src()                                   ; 'p'
        c = read_src()                                   ; 'r'
        c = read_src()                                   ; 'i'
        c = read_src()                                   ; 'n'
        c = read_src()                                   ; 't'
        c = read_src()                                   ; '_'
        c = read_src()                                   ; 'u'
        c = read_src()                                   ; 'b'
        if src_eof != 0 {
            return
        }
        ; read the variable name (v9: multi-character)
        read_ident()
        if src_eof != 0 {
            return
        }
        print_addr = find_var()
        skip_to_nl()
    }
    ; ---- Read the let body: `let X = X + $ZZ` ----
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $6c {                                    ; 'l' of "let"
            break
        }
    }
    c = read_src()                                       ; 'e'
    c = read_src()                                       ; 't'
    ; loop var
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c >= $61 {
            if c <= $7a {
                break
            }
        }
    }
    ; '='
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $3d {
            break
        }
    }
    ; loop var on RHS (not validated)
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c >= $61 {
            if c <= $7a {
                break
            }
        }
    }
    ; '+'
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $2b {
            break
        }
    }
    ; '$'
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $24 {
            break
        }
    }
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = hex_nibble(c) << 4
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = tmp_byte | hex_nibble(c)
    ubyte incr
    incr = tmp_byte
    skip_to_nl()
    ; ---- Emit the loop ----
    ; If the body includes print_ub Y, ensure the hex helper exists
    ; in the output BEFORE we capture loop_top so the back-jump
    ; targets the loop header, not the (already-emitted) helper.
    if has_print != 0 {
        emit_hex_helper()
    }
    ubyte skip_size
    if has_print != 0 {
        skip_size = $14                                  ; 10 print + 7 let + 3 jmp
    } else {
        skip_size = $0a                                  ; 7 let + 3 jmp
    }
    uword loop_top
    loop_top = LOAD_ADDR + bytes_emitted
    write_dst($a5)                                       ; LDA zp <X>
    write_dst(x_addr)
    write_dst($c9)                                       ; CMP #
    write_dst(cmp_val)
    emit_skip_branch(op, skip_size)
    ; --- optional print_ub Y body (10 bytes) ---
    if has_print != 0 {
        write_dst($a5)                                   ; LDA zp
        write_dst(print_addr)
        write_dst($20)                                   ; JSR
        write_dst(lsb(helper_addr))
        write_dst(msb(helper_addr))
        write_dst($a9)                                   ; LDA #
        write_dst($0a)                                   ;   '\n'
        write_dst($20)                                   ; JSR
        write_dst($09)                                   ;   $F009
        write_dst($f0)
    }
    ; --- let X = X + $ZZ body (7 bytes) ---
    write_dst($a5)                                       ; LDA zp
    write_dst(x_addr)
    write_dst($18)                                       ; CLC
    write_dst($69)                                       ; ADC #
    write_dst(incr)
    write_dst($85)                                       ; STA zp
    write_dst(x_addr)
    write_dst($4c)                                       ; JMP
    write_dst(lsb(loop_top))
    write_dst(msb(loop_top))
}


; ---- v3: conditional `if X == $YY then print_ub Z` ----
;
; Restricted form: the then-clause must be exactly `print_ub <letter>`
; which compiles to a known 10-byte sequence. That lets us hard-code
; the BNE displacement and avoid any forward-reference back-patching.
;
; Compiled output for `if X == $YY then print_ub Z`:
;   lda <X_addr>      ; 2 bytes
;   cmp #$YY          ; 2 bytes
;   bne +10           ; 2 bytes  -- skip over the then-block
;   lda <Z_addr>      ; 2  (print_ub var)
;   jsr <hex_helper>  ; 3
;   lda #$0a; jsr write_b ; 5 (newline)
; Total: 16 bytes per if.
sub parse_if() {
    ubyte c
    ; skip 'f' (the 'i' was consumed by the dispatcher)
    c = read_src()
    if src_eof != 0 {
        return
    }
    ; Read the variable name (v9: multi-character).
    read_ident()
    if src_eof != 0 {
        return
    }
    ubyte x_addr
    x_addr = find_var()
    ; Read the comparison operator: ==, !=, <, <=, >, >=.
    ubyte op
    op = read_cmp_op()
    if src_eof != 0 {
        return
    }
    ; skip ws to '$'
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $24 {                                    ; '$'
            break
        }
    }
    ; two hex digits -> compare value
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = hex_nibble(c) << 4
    c = read_src()
    if src_eof != 0 {
        return
    }
    tmp_byte = tmp_byte | hex_nibble(c)
    ubyte cmp_val
    cmp_val = tmp_byte
    ; skip ws then "then"
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $74 {                                    ; 't'
            break
        }
    }
    ; consume "hen"
    c = read_src()
    c = read_src()
    c = read_src()
    if src_eof != 0 {
        return
    }
    ; skip ws to "print_ub <z>"
    repeat {
        c = read_src()
        if src_eof != 0 {
            return
        }
        if c == $70 {                                    ; 'p'
            break
        }
    }
    ; consume "rint_ub"
    c = read_src()  ; r
    c = read_src()  ; i
    c = read_src()  ; n
    c = read_src()  ; t
    c = read_src()  ; _
    c = read_src()  ; u
    c = read_src()  ; b
    if src_eof != 0 {
        return
    }
    ; Read the variable name (v9: multi-character).
    read_ident()
    if src_eof != 0 {
        return
    }
    ubyte z_addr
    z_addr = find_var()
    ; Ensure the helper exists in the output before we emit the
    ; conditional, so its size doesn't shift our hard-coded displacements.
    emit_hex_helper()
    ; Emit: lda <X>; cmp #YY; <conditional skip over 10-byte body>.
    write_dst($a5)                                       ; LDA zp x_addr
    write_dst(x_addr)
    write_dst($c9)                                       ; CMP #
    write_dst(cmp_val)
    emit_skip_branch(op, $0a)                            ; skip 10-byte body on false
    ; then-block: print_ub Z (10 bytes)
    write_dst($a5)                                       ; LDA zp z_addr
    write_dst(z_addr)
    write_dst($20)                                       ; JSR
    write_dst(lsb(helper_addr))
    write_dst(msb(helper_addr))
    write_dst($a9)                                       ; LDA #
    write_dst($0a)                                       ;   '\n'
    write_dst($20)                                       ; JSR
    write_dst($09)                                       ;   $F009
    write_dst($f0)
    skip_to_nl()
}


; ---- main compile loop ----

  sub start() {
    ; arg[0] = input file, arg[1] = output file
    uword fn
    fn = sys_argv(0)
    src_hand = sys_open(fn)
    fn = sys_argv(1)
    dst_hand = sys_openout(fn)

    peek_ok = 0
    src_eof = 0
    next_var_addr = $60
    helper_emitted = 0
    bytes_emitted = 0
    sym_count = 0
    ; The symbol table grows on demand; only slots < sym_count are read,
    ; so the sym_* arrays need no explicit zeroing.

    repeat {
        skip_ws_comments()
        if src_eof != 0 {
            break
        }
        ubyte c
        c = read_src()
        if src_eof != 0 {
            break
        }
        if c == $70 {                                    ; 'p'
            parse_print()
        } else {
            if c == $6c {                                ; 'l' -- "let"
                parse_let()
            } else {
                if c == $69 {                                ; 'i' -- "if"
                    parse_if()
                } else {
                    if c == $77 {                                ; 'w' -- "while"
                        parse_while()
                    } else {
                        if c == $65 {                                ; 'e' -- "end"
                            skip_to_nl()
                            break
                        } else {
                            skip_to_nl()
                        }
                    }
                }
            }
        }
    }

    emit_exit_seq()

    sys_close(src_hand)
    sys_close(dst_hand)
  }
}
