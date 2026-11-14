; module conditional, cpu 6502

; function conditional.f
;   no slots
conditional__f
    CLC
    LDA conditional__n
    ADC #$04
    STA conditional__n
    CMP #$04
    BNE .L0015
    LDA #$01
    STA conditional__n
    JMP .L0021
.L0015
    LDA conditional__n
    CMP #$03
    BNE .L0021
    LDA #$03
    STA conditional__n
.L0021
    RTS

; variable conditional.n: size 1, class 1 (either), weight 5
