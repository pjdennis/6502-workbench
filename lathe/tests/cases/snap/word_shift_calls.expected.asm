; module word_shift_calls, cpu 6502
; imports: rt_math

; function word_shift_calls.f
;   no slots
;   calls rt_math.shl16
;   calls rt_math.shr16
;   calls rt_math.sar16
word_shift_calls__f
    LDY word_shift_calls__n
    LDX word_shift_calls__w+$01
    LDA word_shift_calls__w
    JSR rt_math__shl16
    STA word_shift_calls__w
    STX word_shift_calls__w+$01
    LDY word_shift_calls__n
    JSR rt_math__shr16
    STA word_shift_calls__w
    STX word_shift_calls__w+$01
    LDY word_shift_calls__n
    LDX word_shift_calls__i+$01
    LDA word_shift_calls__i
    JSR rt_math__sar16
    STA word_shift_calls__i
    STX word_shift_calls__i+$01
    LDY word_shift_calls__n
    JSR rt_math__shl16
    STA word_shift_calls__i
    STX word_shift_calls__i+$01
    LDY word_shift_calls__n
    LDX #$00
    LDA word_shift_calls__b
    JSR rt_math__shl16
    STA word_shift_calls__w
    STX word_shift_calls__w+$01
    CLC
    LDA word_shift_calls__n
    ADC #$01
    TAY
    LDA word_shift_calls__w
    JSR rt_math__shl16
    STA word_shift_calls__w
    STX word_shift_calls__w+$01
    LDY word_shift_calls__n
    JSR rt_math__shr16
    CLC
    ADC #$01
    BCC .L006C
    INX
.L006C
    RTS

; variable word_shift_calls.n: size 1, class 1 (either), weight 7

; variable word_shift_calls.w: size 2, class 1 (either), weight 11

; variable word_shift_calls.i: size 2, class 1 (either), weight 6

; variable word_shift_calls.b: size 1, class 1 (either), weight 1
