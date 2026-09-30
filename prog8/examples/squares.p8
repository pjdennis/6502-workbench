; ubyte multiplication: print i*i for i in 0..7.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

  sub start() {
    lcd.clear()
    ubyte i
    for i in 0 to 7 {
        txt.print_ub(i * i)
    }
  }
}
