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
    LDX columns__i
    STA columns__w,X
    LDX columns__j
    LDA columns__w+$0A,X
    ADC columns__total+$01
    LDX columns__i
    STA columns__w+$0A,X
    LDA columns__w,X
    CLC
    ADC columns__total
    STA columns__total
    LDA columns__total+$01
    ADC columns__w+$0A,X
    STA columns__total+$01
    SEC
    LDA columns__w,X
    SBC #$01
    STA columns__w+$03
    LDA columns__w+$0A,X
    SBC #$00
    STA columns__w+$0D
    INC columns__w,X
    BNE .L004B
    INC columns__w+$0A,X
.L004B
    LDA columns__b
    LDX columns__j
    STA columns__w,X
    LDA #$00
    STA columns__w+$0A,X
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
    LDX columns__j
    CMP columns__s,X
    LDX columns__i
    LDA columns__s+$0A,X
    LDX columns__j
    SBC columns__s+$0A,X
    BVC .L0026
    EOR #$80
.L0026
    BMI .L002B
    CLC
    BCC .L002C
.L002B
    SEC
.L002C
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
    LDX columns__i
    STA columns__grid+$06,X
    LDA columns__grid+$0B
    STA columns__b
    RTS

; function columns.same
;   slot 0 v: size 2, class 1 (either), param, weight 2
columns__same
    LDX columns__same__v+$01
    LDA columns__same__v
    RTS

; function columns.in_registers
;   slot 0 $t1: size 2, class 1 (either), temp, weight 10
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
    LDX columns__i
    STA columns__w,X
    LDA columns__in_registers__St1+$01
    ADC columns__total+$01
    STA columns__w+$0A,X
    LDA columns__total
    STA columns__same__v
    LDX columns__total+$01
    STX columns__same__v+$01
    JSR columns__same
    STA columns__in_registers__St1
    STX columns__in_registers__St1+$01
    LDX columns__j
    LDA columns__w,X
    CLC
    ADC columns__in_registers__St1
    STA columns__total
    LDA columns__in_registers__St1+$01
    ADC columns__w+$0A,X
    STA columns__total+$01
    LDA columns__total
    STA columns__same__v
    LDX columns__total+$01
    STX columns__same__v+$01
    JSR columns__same
    STA columns__in_registers__St1
    STX columns__in_registers__St1+$01
    LDX columns__i
    CMP columns__w,X
    BNE .L0073
    LDA columns__in_registers__St1+$01
    CMP columns__w+$0A,X
    BEQ .L0076
.L0073
    CLC
    BCC .L0077
.L0076
    SEC
.L0077
    RTS

; variable columns.w: size 20, class 2 (not zp), weight 27

; variable columns.s: size 20, class 2 (not zp), weight 4

; variable columns.ptrs: size 8, class 2 (not zp), weight 2

; variable columns.grid: size 12, class 2 (not zp), weight 3

; variable columns.i: size 1, class 1 (either), weight 11

; variable columns.j: size 1, class 1 (either), weight 7

; variable columns.total: size 2, class 1 (either), weight 14

; variable columns.b: size 1, class 1 (either), weight 4
