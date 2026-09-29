; Phase 4: signed `byte` type with signed comparison.
;
; Compares -1 vs 1 -- with unsigned compare, -1 (=$ff) reads as 255
; which is > 1 (=$01) so the answer would be "GT". With signed compare,
; -1 < 1 so the answer is "LT".

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

  sub start() {
    lcd.clear()

    byte a = -1
    byte b = 1

    txt.print("a<b ")
    if a < b {
        txt.print("LT")
    } else {
        txt.print("GE")
    }

    txt.print(" a>b ")
    if a > b {
        txt.print("GT")
    } else {
        txt.print("LE")
    }
  }
}
