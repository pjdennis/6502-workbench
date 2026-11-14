; module shift_bytes, cpu 6502

; function shift_bytes.up
;   slot 0 x: size 2, class 1 (either), param, weight 1
;   slot 1 $t1: size 2, class 1 (either), temp, weight 3
shift_bytes__up
    LDA shift_bytes__up__x
    STA shift_bytes__up__St1+$01
    LDA #$00
    STA shift_bytes__up__St1
    LDX shift_bytes__up__St1+$01
    RTS

; function shift_bytes.down
;   slot 0 x: size 2, class 1 (either), param, weight 1
;   slot 1 $t1: size 2, class 1 (either), temp, weight 4
shift_bytes__down
    LDA shift_bytes__down__x+$01
    LSR
    LSR
    STA shift_bytes__down__St1
    LDA #$00
    STA shift_bytes__down__St1+$01
    CLC
    LDA shift_bytes__down__St1
    ADC #$01
    TAY
    LDA shift_bytes__down__St1+$01
    ADC #$00
    TAX
    TYA
    RTS

; function shift_bytes.plain
;   slot 0 $t1: size 2, class 1 (either), temp, weight 3
shift_bytes__plain
    LDA shift_bytes__v
    STA shift_bytes__w+$01
    LDA #$00
    STA shift_bytes__w
    LDA shift_bytes__v+$01
    STA shift_bytes__w
    LDA #$00
    STA shift_bytes__w+$01
    LDA shift_bytes__b
    STA shift_bytes__w+$01
    LDA #$00
    STA shift_bytes__w
    ASL
    STA shift_bytes__w+$01
    LDA #$00
    STA shift_bytes__w
    LDA shift_bytes__v+$01
    LSR
    LSR
    LSR
    LSR
    STA shift_bytes__w
    LDA #$00
    STA shift_bytes__w+$01
    LDA shift_bytes__j
    STA shift_bytes__i+$01
    LDA #$00
    STA shift_bytes__i
    LDA shift_bytes__j+$01
    CMP #$80
    ROR
    STA shift_bytes__i+$01
    LDA shift_bytes__j
    ROR
    STA shift_bytes__i
    LDA shift_bytes__i+$01
    ASL
    ROR shift_bytes__i+$01
    ROR shift_bytes__i
    LDA shift_bytes__i+$01
    ASL
    ROR shift_bytes__i+$01
    ROR shift_bytes__i
    LDA shift_bytes__i+$01
    ASL
    ROR shift_bytes__i+$01
    ROR shift_bytes__i
    LDA shift_bytes__i+$01
    ASL
    ROR shift_bytes__i+$01
    ROR shift_bytes__i
    LDA shift_bytes__i+$01
    ASL
    ROR shift_bytes__i+$01
    ROR shift_bytes__i
    LDA shift_bytes__i+$01
    ASL
    ROR shift_bytes__i+$01
    ROR shift_bytes__i
    LDA shift_bytes__i+$01
    ASL
    ROR shift_bytes__i+$01
    ROR shift_bytes__i
    LDX shift_bytes__k
    LDA shift_bytes__aw+$01,X
    STA shift_bytes__aw+$04,X
    LDA #$00
    STA shift_bytes__aw,X
    LDA shift_bytes__v+$01
    STA shift_bytes__plain__St1
    LDA #$00
    STA shift_bytes__plain__St1+$01
    LDA shift_bytes__plain__St1
    STA shift_bytes__b
    RTS

; variable shift_bytes.v: size 2, class 1 (either), weight 4

; variable shift_bytes.w: size 2, class 1 (either), weight 10

; variable shift_bytes.b: size 1, class 1 (either), weight 2

; variable shift_bytes.i: size 2, class 1 (either), weight 25

; variable shift_bytes.j: size 2, class 1 (either), weight 3

; variable shift_bytes.aw: size 8, class 2 (not zp), weight 3

; variable shift_bytes.k: size 1, class 1 (either), weight 1
