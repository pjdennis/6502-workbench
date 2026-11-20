; module compare_low_zero, cpu 6502

; function compare_low_zero.below
;   slot 0 x: size 2, class 1 (either), param, weight 4
compare_low_zero__below
    STA compare_low_zero__below__x
    STX compare_low_zero__below__x+$01
    LDA #$FF
    CMP compare_low_zero__below__x
    LDA #$00
    SBC compare_low_zero__below__x+$01
    RTS

; function compare_low_zero.at_least
;   slot 0 x: size 2, class 1 (either), param, weight 0
compare_low_zero__at_least
    TXA
    CMP #$80
    RTS

; function compare_low_zero.negative_enough
;   slot 0 x: size 2, class 1 (either), param, weight 0
compare_low_zero__negative_enough
    TXA
    SEC
    SBC #$FF
    BVC .L0008
    EOR #$80
.L0008
    BMI .L000D
    CLC
    BCC .L000E
.L000D
    SEC
.L000E
    RTS

; function compare_low_zero.main: exported
;   no slots
;   calls compare_low_zero.below
;   calls compare_low_zero.at_least
;   calls compare_low_zero.negative_enough
compare_low_zero__main
    LDA compare_low_zero__w+$01
    CMP #$01
    BCS .L000C
    LDA #$01
    STA compare_low_zero__b
.L000C
    LDA compare_low_zero__w+$01
    CMP #$FF
    BCC .L0018
    LDA #$02
    STA compare_low_zero__b
.L0018
    LDA compare_low_zero__w+$01
    CMP #$01
    BCC .L0024
    LDA #$03
    STA compare_low_zero__b
.L0024
    LDA compare_low_zero__w+$01
    CMP #$80
    BCS .L0030
    LDA #$04
    STA compare_low_zero__b
.L0030
    LDA compare_low_zero__w+$01
    CMP #$81
    LDA #$00
    ROL
    EOR #$01
    STA compare_low_zero__flag
    LDA compare_low_zero__i+$01
    SEC
    SBC #$01
    BVC .L0047
    EOR #$80
.L0047
    BPL .L004E
    LDA #$05
    STA compare_low_zero__b
.L004E
    LDA compare_low_zero__i+$01
    SEC
    SBC #$80
    BVC .L0058
    EOR #$80
.L0058
    BMI .L005F
    LDA #$06
    STA compare_low_zero__b
.L005F
    LDA compare_low_zero__i+$01
    SEC
    SBC #$FF
    BVC .L0069
    EOR #$80
.L0069
    BMI .L0070
    LDA #$07
    STA compare_low_zero__b
.L0070
    LDA compare_low_zero__i+$01
    SEC
    SBC #$01
    BVC .L007A
    EOR #$80
.L007A
    BMI .L0080
    LDA #$01
    BNE .L0082
.L0080
    LDA #$00
.L0082
    STA compare_low_zero__flag
    LDX compare_low_zero__w+$01
    LDA compare_low_zero__w
    JSR compare_low_zero__below
    BCC .L00AA
    LDX compare_low_zero__w+$01
    LDA compare_low_zero__w
    JSR compare_low_zero__at_least
    BCC .L00AA
    LDX compare_low_zero__i+$01
    LDA compare_low_zero__i
    JSR compare_low_zero__negative_enough
    BCC .L00AA
    LDA #$01
    BNE .L00AC
.L00AA
    LDA #$00
.L00AC
    STA compare_low_zero__flag
    RTS

; variable compare_low_zero.w: size 2, class 1 (either), weight 9

; variable compare_low_zero.i: size 2, class 1 (either), weight 6

; variable compare_low_zero.b: size 1, class 1 (either), weight 7

; variable compare_low_zero.flag: size 1, class 1 (either), weight 3
