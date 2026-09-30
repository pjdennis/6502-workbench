; Phase 2 follow-up: exercise uword, `for in lo to hi`, peek, and
; txt.print_uw. Output is sized to fill exactly one 16-char LCD line.
;
; for-loop prints       "00010203"        (8 chars)
; uword literal prints  " 1234"           (5 chars)
; peek of ROM start     " 4C"             (3 chars)
;                        ----------------
;                        16 chars total

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
