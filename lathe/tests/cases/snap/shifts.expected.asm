; module shifts, cpu 6502

; function shifts.byte_constant
;   no slots
shifts__byte_constant
    LDA shifts__a
    ASL
    ASL
    ASL
    STA shifts__b
    LDA shifts__a
    LSR
    LSR
    STA shifts__b
    CLC
    LDA shifts__a
    ADC shifts__n
    ASL
    STA shifts__b
    RTS

; function shifts.byte_in_place
;   no slots
shifts__byte_in_place
    ASL shifts__a
    ASL shifts__a
    ASL shifts__a
    LSR shifts__a
    RTS

; function shifts.signed_byte
;   no slots
shifts__signed_byte
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    ASL shifts__s
    RTS

; function shifts.byte_variable
;   no slots
shifts__byte_variable
    LDA shifts__a
    LDX shifts__n
    BEQ .L000C
.L0008
    ASL
    DEX
    BNE .L0008
.L000C
    STA shifts__b
    LDA shifts__a
    LDX shifts__n
    BEQ .L001B
.L0017
    LSR
    DEX
    BNE .L0017
.L001B
    STA shifts__b
    LDA shifts__s
    LDX shifts__n
    BEQ .L002C
.L0026
    CMP #$80
    ROR
    DEX
    BNE .L0026
.L002C
    STA shifts__s
    CLC
    LDA shifts__n
    ADC #$01
    TAX
    LDA shifts__a
    CPX #$00
    BEQ .L0041
.L003D
    ASL
    DEX
    BNE .L003D
.L0041
    STA shifts__b
    RTS

; function shifts.word_constant
;   no slots
shifts__word_constant
    LDA shifts__w
    ASL
    STA shifts__v
    LDA shifts__w+$01
    ROL
    STA shifts__v+$01
    LDA shifts__w+$01
    LSR
    STA shifts__v+$01
    LDA shifts__w
    ROR
    STA shifts__v
    LDA shifts__w
    ASL
    STA shifts__v
    LDA shifts__w+$01
    ROL
    STA shifts__v+$01
    ASL shifts__v
    ROL shifts__v+$01
    ASL shifts__v
    ROL shifts__v+$01
    RTS

; function shifts.word_in_place
;   no slots
shifts__word_in_place
    ASL shifts__w
    ROL shifts__w+$01
    ASL shifts__w
    ROL shifts__w+$01
    ASL shifts__w
    ROL shifts__w+$01
    LSR shifts__w+$01
    ROR shifts__w
    LDA shifts__i+$01
    ASL
    ROR shifts__i+$01
    ROR shifts__i
    RTS

; function shifts.word_result
;   slot 0 $t1: size 2, class 1 (either), temp, weight 6
shifts__word_result
    LDA shifts__w
    ASL
    STA shifts__word_result__St1
    LDA shifts__w+$01
    ROL
    STA shifts__word_result__St1+$01
    ASL shifts__word_result__St1
    ROL shifts__word_result__St1+$01
    LDX shifts__word_result__St1+$01
    LDA shifts__word_result__St1
    RTS

; function shifts.out
;   no slots
shifts__out
    LDA #$00
    STA shifts__b
    STA shifts__b
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA shifts__s
    ASL
    ROR shifts__s
    LDA #$00
    STA shifts__v
    STA shifts__v+$01
    RTS

; function shifts.narrow
;   no slots
shifts__narrow
    LDA shifts__w
    ASL
    ASL
    STA shifts__b
    LDA shifts__w
    LSR
    LSR
    STA shifts__b
    RTS

; variable shifts.a: size 1, class 1 (either), weight 10

; variable shifts.b: size 1, class 1 (either), weight 10

; variable shifts.n: size 1, class 1 (either), weight 5

; variable shifts.s: size 1, class 1 (either), weight 23

; variable shifts.w: size 2, class 1 (either), weight 18

; variable shifts.v: size 2, class 1 (either), weight 12

; variable shifts.i: size 2, class 1 (either), weight 3
