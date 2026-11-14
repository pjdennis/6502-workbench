; module word_arith, cpu 6502

; function word_arith.to_variable
;   no slots
word_arith__to_variable
    CLC
    LDA word_arith__y
    ADC word_arith__z
    STA word_arith__x
    LDA word_arith__y+$01
    ADC word_arith__z+$01
    STA word_arith__x+$01
    SEC
    LDA word_arith__y
    SBC word_arith__z
    STA word_arith__x
    LDA word_arith__y+$01
    SBC word_arith__z+$01
    STA word_arith__x+$01
    LDA word_arith__y
    AND word_arith__z
    STA word_arith__x
    LDA word_arith__y+$01
    AND word_arith__z+$01
    STA word_arith__x+$01
    RTS

; function word_arith.to_registers
;   no slots
word_arith__to_registers
    CLC
    LDA word_arith__y
    ADC word_arith__z
    TAY
    LDA word_arith__y+$01
    ADC word_arith__z+$01
    TAX
    TYA
    RTS

; function word_arith.larger
;   slot 0 $t1: size 2, class 1 (either), temp, weight 4
word_arith__larger
    CLC
    LDA word_arith__y
    ADC word_arith__z
    TAY
    LDA word_arith__y+$01
    ADC word_arith__z+$01
    TAX
    TYA
    CLC
    ADC word_arith__x
    STA word_arith__x
    TXA
    ADC word_arith__x+$01
    STA word_arith__x+$01
    CLC
    LDA word_arith__z
    ADC word_arith__x
    STA word_arith__larger__St1
    LDA word_arith__z+$01
    ADC word_arith__x+$01
    STA word_arith__larger__St1+$01
    SEC
    LDA word_arith__y
    SBC word_arith__larger__St1
    STA word_arith__x
    LDA word_arith__y+$01
    SBC word_arith__larger__St1+$01
    STA word_arith__x+$01
    RTS

; function word_arith.with_byte
;   no slots
word_arith__with_byte
    CLC
    LDA word_arith__y
    ADC word_arith__b
    STA word_arith__x
    LDA word_arith__y+$01
    ADC #$00
    STA word_arith__x+$01
    CLC
    LDA word_arith__b
    ADC word_arith__y
    STA word_arith__x
    LDA #$00
    ADC word_arith__y+$01
    STA word_arith__x+$01
    SEC
    LDA word_arith__y
    SBC word_arith__b
    STA word_arith__x
    LDA word_arith__y+$01
    SBC #$00
    STA word_arith__x+$01
    LDA word_arith__b
    STA word_arith__x
    LDA #$00
    STA word_arith__x+$01
    RTS

; function word_arith.with_constant
;   no slots
word_arith__with_constant
    CLC
    LDA word_arith__y
    ADC #$01
    STA word_arith__x
    LDA word_arith__y+$01
    ADC #$00
    STA word_arith__x+$01
    LDA word_arith__y
    STA word_arith__x
    CLC
    LDA word_arith__y+$01
    ADC #$01
    STA word_arith__x+$01
    CLC
    LDA word_arith__y
    ADC #$34
    STA word_arith__x
    LDA word_arith__y+$01
    ADC #$12
    STA word_arith__x+$01
    LDA #$00
    STA word_arith__x
    LDA word_arith__y+$01
    STA word_arith__x+$01
    LDA word_arith__y
    STA word_arith__x
    LDA #$00
    STA word_arith__x+$01
    LDA word_arith__y
    STA word_arith__x
    LDA word_arith__y+$01
    ORA #$80
    STA word_arith__x+$01
    LDA word_arith__y
    EOR #$FF
    STA word_arith__x
    LDA word_arith__y+$01
    EOR #$FF
    STA word_arith__x+$01
    RTS

; function word_arith.in_place
;   no slots
word_arith__in_place
    CLC
    LDA word_arith__x
    ADC word_arith__y
    STA word_arith__x
    LDA word_arith__x+$01
    ADC word_arith__y+$01
    STA word_arith__x+$01
    CLC
    LDA word_arith__x
    ADC word_arith__b
    STA word_arith__x
    BCC .L0022
    INC word_arith__x+$01
.L0022
    SEC
    LDA word_arith__x
    SBC word_arith__b
    STA word_arith__x
    BCS .L0031
    DEC word_arith__x+$01
.L0031
    CLC
    LDA word_arith__x+$01
    ADC #$01
    STA word_arith__x+$01
    AND #$7F
    STA word_arith__x+$01
    RTS

; function word_arith.unary
;   no slots
word_arith__unary
    SEC
    LDA #$00
    SBC word_arith__y
    STA word_arith__x
    LDA #$00
    SBC word_arith__y+$01
    STA word_arith__x+$01
    LDA word_arith__y
    EOR #$FF
    STA word_arith__x
    LDA word_arith__y+$01
    EOR #$FF
    STA word_arith__x+$01
    SEC
    LDA #$00
    SBC word_arith__n
    STA word_arith__n
    LDA #$00
    SBC word_arith__n+$01
    STA word_arith__n+$01
    RTS

; function word_arith.of_result
;   slot 0 $t1: size 2, class 1 (either), temp, weight 4
;   calls word_arith.to_registers
word_arith__of_result
    JSR word_arith__to_registers
    CLC
    ADC #$01
    STA word_arith__x
    TXA
    ADC #$00
    STA word_arith__x+$01
    JSR word_arith__to_registers
    CLC
    ADC word_arith__y
    STA word_arith__x
    TXA
    ADC word_arith__y+$01
    STA word_arith__x+$01
    JSR word_arith__to_registers
    STA word_arith__of_result__St1
    STX word_arith__of_result__St1+$01
    SEC
    LDA word_arith__y
    SBC word_arith__of_result__St1
    STA word_arith__x
    LDA word_arith__y+$01
    SBC word_arith__of_result__St1+$01
    STA word_arith__x+$01
    RTS

; variable word_arith.x: size 2, class 1 (either), weight 59

; variable word_arith.y: size 2, class 1 (either), weight 40

; variable word_arith.z: size 2, class 1 (either), weight 12

; variable word_arith.b: size 1, class 1 (either), weight 6

; variable word_arith.n: size 2, class 1 (either), weight 4
