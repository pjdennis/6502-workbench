; Enum: a set of named ubyte constants.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

enum Token {
    NONE,             ; 0
    NUMBER,           ; 1
    IDENT,            ; 2
    OP = $10,         ; 16
    LPAREN,           ; 17
    RPAREN,           ; 18
}

sub kind_to_letter(ubyte k) -> ubyte {
    when k {
        Token.NONE   -> { return 'n' }
        Token.NUMBER -> { return 'N' }
        Token.IDENT  -> { return 'I' }
        Token.OP     -> { return 'O' }
        Token.LPAREN -> { return '(' }
        Token.RPAREN -> { return ')' }
        else -> { return '?' }
    }
}

  sub start() {
    lcd.clear()
    txt.print_ub(kind_to_letter(Token.NONE))
    txt.print_ub(kind_to_letter(Token.NUMBER))
    txt.print_ub(kind_to_letter(Token.IDENT))
    txt.print(" ")
    txt.print_ub(kind_to_letter(Token.OP))
    txt.print_ub(kind_to_letter(Token.LPAREN))
    txt.print_ub(kind_to_letter(Token.RPAREN))
    txt.print(" ")
    txt.print_ub(kind_to_letter(99))      ; -> '?'
  }
}
