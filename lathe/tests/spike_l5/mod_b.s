; Spike L5, module B. Placed in fixed memory, in bank 2 or in overlay 2 by the configuration.
; far: b_mid b_dbl b_rec b_irq

; b_mid(n): its parameter is a static slot in fixed memory, stored by b_mid itself here
; (a caller could store it as well: fixed memory is seen from every bank). Calls back into A.
b_mid
    STA b_mid_n
    LDA b_mid_n
    JSR a_leaf
    RTS

; b_dbl(x in A): A = 2x, X = B's mark, carry clear.
b_dbl
    ASL
    LDX b_sig
    CLC
    RTS

; b_rec(n in A): n + a_rec(n - 1), 0 for n = 0.
b_rec
    CMP #$00
    BNE .go
    LDX #$00
    RTS
.go
    PHA
    SEC
    SBC #$01
    JSR a_rec
    STA b_rt
    PLA
    CLC
    ADC b_rt
    BCC .done
    INX
.done
    RTS

; b_irq(): called by the interrupt handler. A = B's mark, read from B's own memory, so a
; wrong bank in the window shows.
b_irq
    LDA b_sig
    RTS

b_sig
    .byte $B2
