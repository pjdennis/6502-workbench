; module const_width, cpu 6502
; imports: rt_math

; function const_width.f
;   no slots
;   calls rt_math.mul16
const_width__f
    LDA #$DF
    STA const_width__b
    AND #$DF
    STA const_width__b
    LDA #$DE
    STA const_width__b
    LDA #$9F
    STA const_width__b
    LDA #$FF
    STA const_width__b
    CLC
    ADC #$FE
    STA const_width__b
    SEC
    LDA #$FF
    SBC const_width__b
    STA const_width__b
    LDA #$07
    STA const_width__a+$03
    LDA #$DF
    STA const_width__w
    LDA #$FF
    STA const_width__w+$01
    STA const_width__w
    STA const_width__w+$01
    LDA #$DF
    STA const_width__s
    STA const_width__i
    LDA #$FF
    STA const_width__i+$01
    SEC
    SBC const_width__digit
    STA const_width__w
    LDA #$FF
    SBC #$00
    STA const_width__w+$01
    CLC
    LDA const_width__digit
    ADC #$E8
    STA const_width__w
    LDA #$00
    ADC #$03
    STA const_width__w+$01
    LDA const_width__digit
    STA rt_math__mul16__1
    LDA #$00
    STA rt_math__mul16__1+$01
    LDX #$01
    LDA #$2C
    JSR rt_math__mul16
    STA const_width__w
    STX const_width__w+$01
    LDA const_width__digit
    CMP #$2C
    LDA #$00
    SBC #$01
    BCS .L0090
    LDA #$01
    STA const_width__b
.L0090
    RTS

; variable const_width.b: size 1, class 1 (either), weight 9

; variable const_width.w: size 2, class 1 (either), weight 10

; variable const_width.digit: size 1, class 1 (either), weight 4

; variable const_width.s: size 1, class 1 (either), weight 1

; variable const_width.i: size 2, class 1 (either), weight 2

; variable const_width.a: size 4, class 2 (not zp), weight 1
