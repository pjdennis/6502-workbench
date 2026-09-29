%output raw
%launcher none
%import textio
%import banking
; T1 -- prove 8 distinct upper RAM banks: write a sentinel into $A000 in each
; bank, then read all back. Distinct banks => each keeps its own value.
main {
    sub start() {
        txt.clear()
        ubyte b
        for b in 0 to 7 {
            banking.bank_poke(b, $a000, $41 + b)   ; 'A'+bank into this bank's $A000
        }
        bool ok = true
        for b in 0 to 7 {
            ubyte want = $41 + b
            if banking.bank_peek(b, $a000) != want {
                ok = false
            }
        }
        txt.print("8 banks: ")
        if ok {
            txt.print("OK")
        } else {
            txt.print("FAIL")
        }
        txt.line2()
        for b in 0 to 7 {
            txt.chrout(banking.bank_peek(b, $a000))   ; expect A B C D E F G H
        }
    }
}
