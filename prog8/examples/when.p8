; Phase 3: when statement -- ubyte switch with literal cases.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

sub classify(ubyte c) {
    when c {
        $61 -> {                ; 'a'
            txt.print("A ")
        }
        $62, $63 -> {           ; 'b' or 'c'
            txt.print("BC ")
        }
        else -> {
            txt.print("? ")
        }
    }
}

  sub start() {
    lcd.clear()
    classify($61)               ; -> "A "
    classify($62)               ; -> "BC "
    classify($63)               ; -> "BC "
    classify($7a)               ; -> "? "
  }
}
