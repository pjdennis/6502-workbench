; Phase 2: 16-bit arithmetic across page boundary.
; Walks a uword counter +1, +$00FF, -1; prints each value (4 hex digits).

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

  sub start() {
    lcd.clear()

    uword w = $00FE
    txt.print_uw(w)              ; 00FE

    w = w + $0001                ; -> 00FF
    txt.print(" ")
    txt.print_uw(w)              ; 00FF

    w += $0001                   ; -> 0100 (carry into high byte)
    txt.print(" ")
    txt.print_uw(w)              ; 0100

    w = w + $00FF                ; -> 01FF
    txt.print(" ")
    txt.print_uw(w)              ; 01FF
  }
}
