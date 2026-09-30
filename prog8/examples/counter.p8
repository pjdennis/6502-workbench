; Phase 2 demo: a small ubyte counter, an `if` on a comparison, and a
; conditional message via while + repeat. Output fits on the 16x2 LCD.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

ubyte total

  sub start() {
    lcd.clear()

    ; -- loop 1: count 0..3 via while, accumulate into `total`.
    ubyte i
    i = 0
    while i < 4 {
        total = total + i
        i = i + 1
    }

    ; -- loop 2: print total twice using a counted repeat. (total = 6)
    txt.print("total=")
    repeat 2 {
        txt.print_ub(total)
    }

    ; -- if/else with a comparison condition.
    if total == 6 {
        txt.print(" OK")
    } else {
        txt.print(" NO")
    }
  }
}
