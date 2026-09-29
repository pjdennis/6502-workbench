%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

ubyte total

  sub start() {
    lcd.clear()

    ubyte i
    i = 0
    while i < 4 {
        total = total + i
        i = i + 1
    }

    txt.print("total=")
    repeat 2 {
        txt.print_ub(total)
    }

    if total == 6 {
        txt.print(" OK")
    } else {
        txt.print(" NO")
    }
  }
}
