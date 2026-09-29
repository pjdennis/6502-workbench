; Phase 3: @(addr) memory access + &var address-of.
; - Fill a buffer via @() writes using a moving pointer.
; - Read it back via @() reads.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

ubyte[6] buf

  sub start() {
    lcd.clear()

    ; Get the buffer's address into a uword "pointer".
    uword p = &buf

    ; Write $a0..$a5 by stepping p one byte at a time.
    ubyte i
    for i in 0 to 5 {
        @(p + i) = $a0 + i
    }

    ; Print each byte by reading via @(p + i).
    for i in 0 to 5 {
        txt.print_ub(@(p + i))
    }
  }
}
