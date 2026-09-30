%output raw
%launcher none
%import textio
%import banking
; T2 -- banked arrays bigger than one 32K map: bank 0 holds i, bank 1 holds
; 255-i across $A000..$A0FF. Verify a+b==255 everywhere; show sum(bank0).
main {
    sub start() {
        txt.clear()
        uword i
        for i in 0 to 255 {
            banking.bank_poke(0, $a000+i, lsb(i))
            banking.bank_poke(1, $a000+i, 255 - lsb(i))
        }
        bool ok = true
        uword sum = 0
        for i in 0 to 255 {
            ubyte a = banking.bank_peek(0, $a000+i)
            ubyte b = banking.bank_peek(1, $a000+i)
            ubyte want = 255 - b
            if a != want {
                ok = false
            }
            sum += a
        }
        txt.print("sum=")
        txt.print_ub(msb(sum))
        txt.print_ub(lsb(sum))
        txt.line2()
        if ok {
            txt.print("a+b=255 OK")
        } else {
            txt.print("FAIL")
        }
    }
}
