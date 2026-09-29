; A small tokenizer written entirely in Prog8.
;
; Tokenizes a hard-coded source string (hex digits + plus/minus separators
; + spaces) into a Token array, then walks the array and prints each
; token's kind and value.
;
; Demonstrates: enum + struct + struct array + while + when + for-loop,
; all interacting like a real compiler's tokenizer would. The "source"
; is held as a ubyte buffer.
;
; Source: "12+34-56 ab"
; Expected output: "N:12 +:00 N:34 -:00 N:56 N:AB"

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

enum TK {
    NUM = $4E,      ; 'N'
    PLUS = $2B,     ; '+'
    MINUS = $2D,    ; '-'
    END = $24,      ; '$'
}

struct Token {
    ubyte kind
    ubyte value
}

Token[8] tokens

ubyte n_tokens
ubyte[12] source

inline sub is_hex_digit(ubyte c) -> ubyte {
    if c >= $30 {
        if c <= $39 { return 1 }     ; '0'..'9'
    }
    if c >= $61 {
        if c <= $66 { return 1 }     ; 'a'..'f'
    }
    return 0
}

inline sub hex_value(ubyte c) -> ubyte {
    if c >= $61 {
        return c - $57               ; 'a'..'f' -> 10..15
    }
    return c - $30                   ; '0'..'9'
}

  sub start() {
    lcd.clear()

    ; Hard-code the source: "12+34-56 ab" + terminator
    source[0]  = $31
    source[1]  = $32
    source[2]  = $2B
    source[3]  = $33
    source[4]  = $34
    source[5]  = $2D
    source[6]  = $35
    source[7]  = $36
    source[8]  = $20
    source[9]  = $61
    source[10] = $62
    source[11] = $00

    ; ---- Tokenize ----
    n_tokens = 0
    ubyte i
    i = 0
    while source[i] != 0 {
        ubyte c
        c = source[i]
        when c {
            $20 -> {                 ; space: skip
                i = i + 1
            }
            $2B -> {                 ; '+'
                tokens[n_tokens].kind = TK.PLUS
                tokens[n_tokens].value = 0
                n_tokens = n_tokens + 1
                i = i + 1
            }
            $2D -> {                 ; '-'
                tokens[n_tokens].kind = TK.MINUS
                tokens[n_tokens].value = 0
                n_tokens = n_tokens + 1
                i = i + 1
            }
            else -> {
                ; Number: collect hex digits until non-hex.
                if is_hex_digit(c) != 0 {
                    ubyte v
                    v = 0
                    while is_hex_digit(source[i]) != 0 {
                        v = (v << 4) | hex_value(source[i])
                        i = i + 1
                    }
                    tokens[n_tokens].kind = TK.NUM
                    tokens[n_tokens].value = v
                    n_tokens = n_tokens + 1
                } else {
                    i = i + 1                ; skip unknown
                }
            }
        }
    }

    ; ---- Print ----
    for i in 0 to n_tokens - 1 {
        txt.print_ub(tokens[i].kind)
        txt.print(":")
        txt.print_ub(tokens[i].value)
        txt.print(" ")
    }
  }
}
