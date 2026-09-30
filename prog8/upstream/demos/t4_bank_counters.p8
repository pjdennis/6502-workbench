%output raw
%launcher none
%import textio
%import banking
; T4 -- per-bank counters: each of 8 banks keeps its own counter at $A010;
; increment every bank 3 times -> all read back 3 (independent state).
main {
    sub start() {
        txt.clear()
        ubyte b
        for b in 0 to 7 {
            banking.bank_poke(b, $a010, 0)
        }
        ubyte pass
        for pass in 0 to 2 {
            for b in 0 to 7 {
                ubyte c = banking.bank_peek(b, $a010)
                banking.bank_poke(b, $a010, c + 1)
            }
        }
        txt.print("counters:")
        txt.line2()
        for b in 0 to 7 {
            txt.chrout($30 + banking.bank_peek(b, $a010))   ; '0'+count
        }
    }
}
