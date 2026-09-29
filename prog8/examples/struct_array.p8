; Struct array: a small token table.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

struct Token {
    ubyte kind
    uword value
}

Token[4] toks

  sub start() {
    lcd.clear()

    ubyte i
    for i in 0 to 3 {
        toks[i].kind = i + $a0
        toks[i].value = $1000 + i
    }

    for i in 0 to 3 {
        txt.print_ub(toks[i].kind)
        txt.print(":")
        txt.print_uw(toks[i].value)
        txt.print(" ")
    }
  }
}
