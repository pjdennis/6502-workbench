%output raw
%launcher none
%import textio
%import banking
; T5 -- load code into MULTIPLE banks and execute across them (self-installing
; model: the compiled binary carries the routines as byte blobs and installs
; them into banks 1/2/3, then far-calls each in turn).
;
; Each routine (position-correct for $A000) is:  inc $0200 ; lda #'N' ; rts
; -- it bumps a shared counter at $0200 (fixed lower RAM) and returns its bank's tag.
main {
    ubyte[6] r1 = [$ee, $00, $02, $a9, $31, $60]   ; inc $0200 ; lda #'1' ; rts
    ubyte[6] r2 = [$ee, $00, $02, $a9, $32, $60]   ; ... lda #'2' ...
    ubyte[6] r3 = [$ee, $00, $02, $a9, $33, $60]   ; ... lda #'3' ...

    sub start() {
        txt.clear()
        @($0200) = 0                                ; shared counter

        banking.bank_store(1, $a000, &r1, 6)        ; install routine into each bank
        banking.bank_store(2, $a000, &r2, 6)
        banking.bank_store(3, $a000, &r3, 6)

        txt.chrout(banking.bank_call(1, $a000))     ; execute across the banks
        txt.chrout(banking.bank_call(2, $a000))
        txt.chrout(banking.bank_call(3, $a000))

        txt.print(" n=")
        txt.chrout($30 + @($0200))                  ; shared counter -> '3'
    }
}
