%output raw
%launcher none
%import textio
%import banking
; T3 -- banked CODE via far-call: copy a tiny routine (lda #$2A ; rts) into
; bank 3's window at $A000, then far-call it. Control crosses into the banked
; window and returns with the previous bank restored.
main {
    ubyte[3] routine = [$a9, $2a, $60]      ; lda #$2A ; rts
    sub start() {
        txt.clear()
        ubyte i
        for i in 0 to 2 {
            banking.bank_poke(3, $a000 + i, routine[i])
        }
        ubyte result = banking.bank_call(3, $a000)
        txt.print("far ret=")
        txt.print_ub(result)
        txt.line2()
        if result == $2a {
            txt.print("banked code OK")
        } else {
            txt.print("FAIL")
        }
    }
}
