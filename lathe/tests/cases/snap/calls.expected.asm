; module calls, cpu 6502
; imports: host

abs_f009 = $F009
abs_ff00 = $FF00
abs_ff03 = $FF03
abs_ff06 = $FF06

; function calls.one
;   slot 0 n: size 1, class 1 (either), param, weight 1
calls__one
    LDA calls__one__n
    STA calls__r
    RTS

; function calls.three
;   slot 0 p: size 1, class 1 (either), param, weight 1
;   slot 1 q: size 2, class 1 (either), param, weight 2
;   slot 2 on: size 1, class 1 (either), param, weight 0
calls__three
    LDA calls__three__p
    STA calls__r
    LDA calls__three__q
    STA calls__w
    LDA calls__three__q+$01
    STA calls__w+$01
    RTS

; function calls.double
;   slot 0 n: size 1, class 1 (either), param, weight 2
calls__double
    CLC
    LDA calls__double__n
    ADC calls__double__n
    RTS

; function calls.sum
;   slot 0 p: size 2, class 1 (either), param, weight 2
;   slot 1 q: size 2, class 1 (either), param, weight 2
calls__sum
    CLC
    LDA calls__sum__p
    ADC calls__sum__q
    TAY
    LDA calls__sum__p+$01
    ADC calls__sum__q+$01
    TAX
    TYA
    RTS

; function calls.arguments
;   no slots
;   calls calls.one
;   calls calls.three
calls__arguments
    LDA #$05
    STA calls__one__n
    JSR calls__one
    LDA calls__a
    STA calls__one__n
    JSR calls__one
    CLC
    LDA calls__a
    ADC calls__b
    STA calls__one__n
    JSR calls__one
    LDA calls__a
    STA calls__three__p
    CLC
    LDA calls__w
    ADC #$01
    STA calls__three__q
    LDA calls__w+$01
    ADC #$00
    STA calls__three__q+$01
    LDA calls__a
    CMP calls__b
    LDA #$00
    ROL
    EOR #$01
    STA calls__three__on
    JSR calls__three
    LDA #$01
    STA calls__three__p
    LDA calls__a
    STA calls__three__q
    LDA #$00
    STA calls__three__q+$01
    LDA #$01
    STA calls__three__on
    JMP calls__three

; function calls.nested
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
;   calls calls.double
;   calls calls.one
;   calls calls.sum; outer calls.three
;   calls calls.three
calls__nested
    LDA calls__a
    STA calls__double__n
    JSR calls__double
    STA calls__one__n
    JSR calls__one
    LDA calls__a
    STA calls__three__p
    LDA calls__w
    STA calls__sum__p
    LDA calls__w+$01
    STA calls__sum__p+$01
    LDA #$01
    STA calls__sum__q
    LDA #$00
    STA calls__sum__q+$01
    JSR calls__sum
    STA calls__three__q
    STX calls__three__q+$01
    LDA #$00
    STA calls__three__on
    JSR calls__three
    LDA calls__a
    STA calls__double__n
    JSR calls__double
    STA calls__double__n
    JSR calls__double
    STA calls__nested__St1
    LDA calls__b
    STA calls__double__n
    JSR calls__double
    CLC
    ADC calls__nested__St1
    STA calls__r
    RTS

; function calls.results
;   no slots
;   calls calls.double
;   calls calls.sum
calls__results
    LDA calls__a
    STA calls__double__n
    JSR calls__double
    STA calls__r
    LDA calls__w
    STA calls__sum__p
    LDA calls__w+$01
    STA calls__sum__p+$01
    LDA calls__w
    STA calls__sum__q
    LDA calls__w+$01
    STA calls__sum__q+$01
    JSR calls__sum
    STA calls__w
    STX calls__w+$01
    LDA calls__a
    STA calls__double__n
    JSR calls__double
    STA calls__w
    LDA #$00
    STA calls__w+$01
    LDA calls__a
    STA calls__double__n
    JSR calls__double
    CLC
    ADC #$01
    STA calls__r
    LDA calls__a
    STA calls__double__n
    JSR calls__double
    CMP #$04
    BNE .L005F
    LDA #$00
    STA calls__r
.L005F
    RTS

; function calls.kept
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
;   calls calls.double
calls__kept
    LDA calls__a
    STA calls__double__n
    JSR calls__double
    STA calls__kept__St1
    LDA calls__b
    STA calls__double__n
    JSR calls__double
    CLC
    ADC calls__kept__St1
    STA calls__r
    LDA calls__b
    STA calls__double__n
    JSR calls__double
    CLC
    ADC calls__a
    STA calls__r
    RTS

; function calls.externs
;   no slots
calls__externs
    LDX #$02
    LDA #$01
    JSR abs_ff00
    LDX calls__b
    LDA calls__a
    JSR abs_ff00
    CLC
    LDA calls__a
    ADC #$01
    LDX calls__b
    JSR abs_ff00
    CLC
    LDA calls__b
    ADC #$01
    TAX
    LDA calls__a
    JSR abs_ff00
    SEC
    LDY calls__a
    LDX calls__w+$01
    LDA calls__w
    JSR abs_ff03
    LDA calls__a
    CMP calls__b
    BEQ .L003F
    CLC
.L003F
    LDY #$00
    LDX #$12
    LDA #$34
    JSR abs_ff03
    CLC
    LDA calls__a
    ADC #$30
    JSR abs_f009
    JSR abs_ff06
    TXA
    PHA
    TYA
    TAX
    PLA
    STA calls__w
    STX calls__w+$01
    RTS

; function calls.last
;   no slots
;   calls calls.one
calls__last
    LDA #$01
    STA calls__one__n
    JSR calls__one
    LDA #$02
    STA calls__one__n
    JMP calls__one

; variable calls.a: size 1, class 1 (either), weight 20

; variable calls.b: size 1, class 1 (either), weight 9

; variable calls.w: size 2, class 1 (either), weight 18

; variable calls.r: size 1, class 1 (either), weight 8
