; module columns, cpu 6502

; function columns.read
;   no slots
columns__read
    LDX columns__i
    LDA columns__w,X
    LDY columns__i
    LDX columns__w+$0A,Y
    RTS

; function columns.arithmetic
;   no slots
columns__arithmetic
    CLC
    LDX columns__j
    LDA columns__w,X
    ADC columns__total
    LDY columns__i
    STA columns__w,Y
    LDA columns__w+$0A,X
    ADC columns__total+$01
    STA columns__w+$0A,Y
    LDA columns__w,Y
    CLC
    ADC columns__total
    STA columns__total
    LDA columns__total+$01
    ADC columns__w+$0A,Y
    STA columns__total+$01
    SEC
    LDA columns__w,Y
    SBC #$01
    STA columns__w+$03
    LDA columns__w+$0A,Y
    SBC #$00
    STA columns__w+$0D
    LDX columns__i
    INC columns__w,X
    BNE .L0048
    INC columns__w+$0A,X
.L0048
    LDA columns__b
    LDY columns__j
    STA columns__w,Y
    LDA #$00
    STA columns__w+$0A,Y
    RTS

; function columns.halves
;   no slots
columns__halves
    LDX columns__i
    LDA columns__w+$0A,X
    STA columns__b
    STA columns__w+$01,X
    LDA #$00
    STA columns__w+$13
    RTS

; function columns.compare
;   no slots
columns__compare
    LDX columns__i
    LDA columns__w,X
    ORA columns__w+$0A,X
    BNE .L000D
    CLC
    RTS
.L000D
    LDA columns__s,X
    LDY columns__j
    CMP columns__s,Y
    LDA columns__s+$0A,X
    SBC columns__s+$0A,Y
    BVC .L0020
    EOR #$80
.L0020
    BMI .L0025
    CLC
    BCC .L0026
.L0025
    SEC
.L0026
    RTS

; function columns.through
;   slot 0 $t1: size 2, class 0 (zp), temp, weight 3
columns__through
    LDX columns__i
    LDA columns__ptrs,X
    STA columns__through__St1
    LDA columns__ptrs+$04,X
    STA columns__through__St1+$01
    LDY columns__j
    LDA (columns__through__St1),Y
    RTS

; function columns.arrays_of_arrays
;   no slots
columns__arrays_of_arrays
    LDA columns__grid+$0A
    LDY columns__i
    STA columns__grid+$06,Y
    LDA columns__grid+$0B
    STA columns__b
    RTS

; function columns.same
;   slot 0 v: size 2, class 1 (either), param, weight 2
columns__same
    STA columns__same__v
    STX columns__same__v+$01
    RTS

; function columns.in_registers
;   slot 0 $t1: size 2, class 1 (either), temp, weight 7
;   calls columns.same
columns__in_registers
    LDA columns__b
    TAY
    LDA #$00
    EOR #$80
    TAX
    TYA
    STA columns__in_registers__St1
    STX columns__in_registers__St1+$01
    CLC
    ADC columns__total
    LDY columns__i
    STA columns__w,Y
    TXA
    ADC columns__total+$01
    STA columns__w+$0A,Y
    LDX columns__total+$01
    LDA columns__total
    JSR columns__same
    STA columns__in_registers__St1
    STX columns__in_registers__St1+$01
    LDY columns__j
    LDA columns__w,Y
    CLC
    ADC columns__in_registers__St1
    STA columns__total
    TXA
    ADC columns__w+$0A,Y
    STA columns__total+$01
    TAX
    LDA columns__total
    JSR columns__same
    STA columns__in_registers__St1
    STX columns__in_registers__St1+$01
    LDY columns__i
    CMP columns__w,Y
    BNE .L005F
    TXA
    CMP columns__w+$0A,Y
    BEQ .L0062
.L005F
    CLC
    BCC .L0063
.L0062
    SEC
.L0063
    RTS

; variable columns.w: size 20, class 2 (not zp), weight 27

; variable columns.s: size 20, class 2 (not zp), weight 4

; variable columns.ptrs: size 8, class 2 (not zp), weight 2

; variable columns.grid: size 12, class 2 (not zp), weight 3

; variable columns.i: size 1, class 1 (either), weight 10

; variable columns.j: size 1, class 1 (either), weight 5

; variable columns.total: size 2, class 1 (either), weight 13

; variable columns.b: size 1, class 1 (either), weight 4
