; Struct: named fields stored in main memory.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

struct Point {
    ubyte x
    ubyte y
    uword tag
}

Point p

  sub start() {
    lcd.clear()
    p.x = $1a
    p.y = $b2
    p.tag = $cafe

    txt.print("x=")
    txt.print_ub(p.x)
    txt.print(" y=")
    txt.print_ub(p.y)
    txt.print(" t=")
    txt.print_uw(p.tag)
  }
}
