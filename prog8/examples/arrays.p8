; Phase 3: byte arrays with indexed read + write.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

ubyte[8] buf

  sub start() {
    lcd.clear()

    ; Fill buf[i] = $10 + i.
    ubyte i
    for i in 0 to 7 {
        buf[i] = $10 + i
    }

    ; Print them.
    for i in 0 to 7 {
        txt.print_ub(buf[i])
    }
  }
}
