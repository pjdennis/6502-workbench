; module consts, cpu 6502

; function consts.numbers
;   no slots
consts__numbers
    LDA #$0A
    STA consts__b
    LDA #$78
    STA consts__b
    LDA #$FA
    STA consts__b
    LDA #$43
    STA consts__b
    LDA #$F6
    STA consts__b
    LDA #$2C
    STA consts__b
    LDA #$46
    STA consts__b
    LDA #$03
    STA consts__b
    LDA #$05
    STA consts__b
    LDA #$0D
    STA consts__b
    RTS

; function consts.words
;   no slots
consts__words
    LDA #$FF
    STA consts__w
    STA consts__w+$01
    LDA #$35
    STA consts__w
    LDA #$75
    STA consts__w+$01
    LDA #$00
    STA consts__w
    LDA #$04
    STA consts__w+$01
    LDA #$9A
    STA consts__w
    LDA #$3A
    STA consts__w+$01
    LDA #$03
    STA consts__w
    LDA #$00
    STA consts__w+$01
    LDA #$95
    STA consts__w
    LDA #$15
    STA consts__w+$01
    RTS

; function consts.signed
;   no slots
consts__signed
    LDA #$F6
    STA consts__s
    LDA #$80
    STA consts__s
    LDA #$18
    STA consts__i
    LDA #$FC
    STA consts__i+$01
    LDA #$00
    STA consts__i
    LDA #$80
    STA consts__i+$01
    LDA #$FD
    STA consts__i
    LDA #$FF
    STA consts__i+$01
    STA consts__i
    STA consts__i+$01
    STA consts__i
    STA consts__i+$01
    STA consts__i
    STA consts__i+$01
    RTS

; function consts.bools
;   no slots
consts__bools
    LDA #$01
    STA consts__f
    STA consts__f
    STA consts__f
    STA consts__f
    STA consts__f
    STA consts__b
    RTS

; function consts.decided
;   no slots
consts__decided
    LDA #$01
    RTS

; variable consts.b: size 1, class 1 (either), weight 11

; variable consts.s: size 1, class 1 (either), weight 2

; variable consts.w: size 2, class 1 (either), weight 12

; variable consts.i: size 2, class 1 (either), weight 12

; variable consts.f: size 1, class 1 (either), weight 5
