; Phase 3 cont: const + lsb/msb/mkword/len/sizeof.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

const ubyte LO = $cd
const ubyte HI = $ab
const uword ADDR = $4080

ubyte[10] tab

  sub start() {
    lcd.clear()

    ; const folding: txt.print_uw(mkword(HI, LO)) -> "ABCD"
    txt.print_uw(mkword(HI, LO))

    ; lsb / msb on a uword: prints "AB CD".
    txt.print(" ")
    txt.print_ub(msb(ADDR))
    txt.print(" ")
    txt.print_ub(lsb(ADDR))

    ; len of an array: prints " A" (10 -> $0A).
    txt.print(" ")
    txt.print_ub(len(tab))
  }
}
