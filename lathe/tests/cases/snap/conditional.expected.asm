; module conditional, cpu 6502

; function conditional.f
;   no slots
conditional__f
    CLC
    LDA conditional__n
    ADC #$04
    STA conditional__n
    CMP #$04
    BNE .L0013
    LDA #$01
    STA conditional__n
    RTS
.L0013
    CMP #$03
    BNE .L001C
    LDA #$03
    STA conditional__n
.L001C
    RTS

; variable conditional.n: size 1, class 1 (either), weight 4
