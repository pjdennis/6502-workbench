%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

  sub start() {
    lcd.clear()

    ubyte i
    for i in 0 to 3 {
        txt.print_ub(i)
    }

    uword w = $1234
    txt.print(" ")
    txt.print_uw(w)

    txt.print(" ")
    txt.print_ub(peek($8000))
  }
}
