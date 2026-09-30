%output raw
%launcher none
%import textio
%import banking
; D5 -- a banked program whose upper-bank routines are placed by the LOADER
; from a single packaged .w2x image (no self-install, no runtime file loading).
; The loader put a routine into banks 1/2/3 at $A000 before this main ran;
; main just far-calls across them. Each routine: inc $0200 ; lda #'N' ; rts.
main {
    sub start() {
        txt.clear()
        @($0200) = 0
        txt.chrout(banking.bank_call(1, $a000))
        txt.chrout(banking.bank_call(2, $a000))
        txt.chrout(banking.bank_call(3, $a000))
        txt.print(" n=")
        txt.chrout($30 + @($0200))
    }
}
