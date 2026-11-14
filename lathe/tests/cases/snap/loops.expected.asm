; module loops, cpu 6502

; function loops.down
;   no slots
loops__down
    LDA loops__n
    STA loops__i
.L0006
    CLC
    LDA loops__r
    ADC loops__i
    STA loops__r
    DEC loops__i
    BNE .L0006
    RTS

; function loops.forever
;   no slots
loops__forever
.L0000
    INC loops__r
    JMP .L0000

; function loops.leaving
;   no slots
loops__leaving
.L0000
    LDA loops__i
    CMP loops__n
    BEQ .L000E
    INC loops__i
    JMP .L0000
.L000E
    RTS

; function loops.skipping
;   no slots
loops__skipping
    LDA #$00
    STA loops__i
.L0005
    LDA loops__i
    CMP loops__n
    BCS .L0024
    INC loops__i
    LDA loops__i
    CMP #$03
    BEQ .L0005
    CLC
    LDA loops__r
    ADC loops__i
    STA loops__r
    JMP .L0005
.L0024
    RTS

; function loops.skipping_until
;   no slots
loops__skipping_until
.L0000
    DEC loops__i
    LDA loops__i
    CMP #$03
    BEQ .L0014
    CLC
    LDA loops__r
    ADC loops__i
    STA loops__r
.L0014
    LDA loops__i
    BNE .L0000
    RTS

; function loops.until_both
;   no slots
loops__until_both
.L0000
    INC loops__i
    LDA loops__i
    CMP loops__n
    BEQ .L0010
    LDA loops__r
    BNE .L0000
.L0010
    RTS

; function loops.inner
;   no slots
loops__inner
.L0000
    LDA loops__r
    BEQ .L000B
    DEC loops__r
    JMP .L0000
.L000B
    DEC loops__i
    BNE .L0000
    RTS

; variable loops.i: size 1, class 1 (either), weight 62

; variable loops.n: size 1, class 1 (either), weight 13

; variable loops.r: size 1, class 1 (either), weight 64
