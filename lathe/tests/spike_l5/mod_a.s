; Spike L5, module A. Placed in fixed memory, in bank 1 or in overlay 1 by the configuration.
; far: a_leaf a_entry a_rec a_ptrcall

; a_leaf(n in A): A = n + 1, X = A's mark, carry set. Three result registers to carry back.
a_leaf
    CLC
    ADC #$01
    LDX a_sig
    SEC
    RTS

; a_entry(n in A): A -> B -> A. Returns what b_mid returns, through two return paths.
a_entry
    JSR b_mid
    RTS

; a_rec(n in A): n + b_rec(n - 1), 0 for n = 0; word result in A and X.
; Recursion across modules: n is saved on the stack, as a saving call saves the frame.
a_rec
    CMP #$00
    BNE .go
    LDX #$00
    RTS
.go
    PHA
    SEC
    SBC #$01
    JSR b_rec
    STA a_rt
    PLA
    CLC
    ADC a_rt
    BCC .done
    INX
.done
    RTS

; a_ptrcall(x in A): calls the function fp points at, with x, and returns its results.
a_ptrcall
    JSR .call
    RTS
.call
    JMP (fp)

a_sig
    .byte $A1
