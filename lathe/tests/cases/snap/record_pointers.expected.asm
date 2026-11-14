; module record_pointers, cpu 6502

; function record_pointers.through
;   slot 0 $t1: size 2, class 0 (zp), temp, weight 10
;   slot 1 $t2: size 2, class 0 (zp), temp, weight 3
;   slot 2 $t3: size 1, class 1 (either), temp, weight 3
record_pointers__through
    LDY #$04
    LDA (record_pointers__p),Y
    STA record_pointers__b
    STA (record_pointers__p),Y
    LDY #$02
    LDA (record_pointers__p),Y
    STA record_pointers__w
    LDY #$03
    LDA (record_pointers__p),Y
    STA record_pointers__w+$01
    CLC
    LDA record_pointers__w
    ADC #$01
    LDY #$02
    STA (record_pointers__p),Y
    LDA record_pointers__w+$01
    ADC #$00
    LDY #$03
    STA (record_pointers__p),Y
    LDY #$02
    LDA (record_pointers__p),Y
    CLC
    ADC #$01
    STA (record_pointers__p),Y
    BNE .L003E
    LDY #$03
    LDA (record_pointers__p),Y
    CLC
    ADC #$01
    STA (record_pointers__p),Y
.L003E
    LDY #$00
    LDA (record_pointers__p),Y
    STA record_pointers__q
    LDY #$01
    LDA (record_pointers__p),Y
    STA record_pointers__q+$01
    LDY #$00
    LDA (record_pointers__p),Y
    STA record_pointers__through__St1
    LDY #$01
    LDA (record_pointers__p),Y
    STA record_pointers__through__St1+$01
    LDY #$04
    LDA (record_pointers__through__St1),Y
    STA record_pointers__b
    LDY #$00
    LDA (record_pointers__p),Y
    STA record_pointers__through__St1
    LDY #$01
    LDA (record_pointers__p),Y
    STA record_pointers__through__St1+$01
    LDY #$00
    LDA (record_pointers__through__St1),Y
    STA record_pointers__through__St2
    LDY #$01
    LDA (record_pointers__through__St1),Y
    STA record_pointers__through__St2+$01
    LDA #$00
    LDY #$04
    STA (record_pointers__through__St2),Y
    LDA record_pointers__far
    STA record_pointers__through__St1
    LDX record_pointers__far+$01
    STX record_pointers__through__St1+$01
    LDA (record_pointers__through__St1),Y
    STA record_pointers__b
    LDA record_pointers__i
    ASL
    ASL
    ASL
    STA record_pointers__through__St3
    TAY
    INY
    INY
    INY
    INY
    LDA (record_pointers__p),Y
    STA record_pointers__b
    LDY #$0F
    LDA (record_pointers__p),Y
    STA record_pointers__b
    CLC
    LDA record_pointers__i
    ADC #$05
    STA record_pointers__through__St3
    LDY #$05
    LDA (record_pointers__p),Y
    LDY record_pointers__through__St3
    STA (record_pointers__p),Y
    RTS

; function record_pointers.in_rows
;   slot 0 $t1: size 2, class 1 (either), temp, weight 32
;   slot 1 $t2: size 2, class 0 (zp), temp, weight 21
record_pointers__in_rows
    LDA record_pointers__i
    ASL
    STA record_pointers__in_rows__St1
    LDA #$00
    ROL
    STA record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    CLC
    LDA record_pointers__in_rows__St1
    ADC #<record_pointers__nodes
    STA record_pointers__in_rows__St2
    LDA record_pointers__in_rows__St1+$01
    ADC #>record_pointers__nodes
    STA record_pointers__in_rows__St2+$01
    LDA record_pointers__b
    LDY #$04
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__i
    ASL
    STA record_pointers__in_rows__St1
    LDA #$00
    ROL
    STA record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    CLC
    LDA record_pointers__in_rows__St1
    ADC #<record_pointers__nodes
    STA record_pointers__in_rows__St2
    LDA record_pointers__in_rows__St1+$01
    ADC #>record_pointers__nodes
    STA record_pointers__in_rows__St2+$01
    LDA record_pointers__in_rows__St2
    STA record_pointers__p
    LDX record_pointers__in_rows__St2+$01
    STX record_pointers__p+$01
    LDA record_pointers__nodes+$1A
    STA record_pointers__w
    LDX record_pointers__nodes+$1B
    STX record_pointers__w+$01
    LDA record_pointers__i
    ASL
    STA record_pointers__in_rows__St1
    LDA #$00
    ROL
    STA record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    CLC
    LDA record_pointers__in_rows__St1
    ADC #<record_pointers__nodes
    STA record_pointers__in_rows__St2
    LDA record_pointers__in_rows__St1+$01
    ADC #>record_pointers__nodes
    STA record_pointers__in_rows__St2+$01
    LDA #<record_pointers__nodes+$10
    LDY #$00
    STA (record_pointers__in_rows__St2),Y
    LDA #>record_pointers__nodes+$10
    LDY #$01
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__i
    ASL
    STA record_pointers__in_rows__St1
    LDA #$00
    ROL
    STA record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    ASL record_pointers__in_rows__St1
    ROL record_pointers__in_rows__St1+$01
    CLC
    LDA record_pointers__in_rows__St1
    ADC #<record_pointers__nodes
    STA record_pointers__in_rows__St2
    LDA record_pointers__in_rows__St1+$01
    ADC #>record_pointers__nodes
    STA record_pointers__in_rows__St2+$01
    LDA record_pointers__nodes+$18
    LDY #$00
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__nodes+$19
    LDY #$01
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__nodes+$1A
    LDY #$02
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__nodes+$1B
    LDY #$03
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__nodes+$1C
    LDY #$04
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__nodes+$1D
    LDY #$05
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__nodes+$1E
    LDY #$06
    STA (record_pointers__in_rows__St2),Y
    LDA record_pointers__nodes+$1F
    LDY #$07
    STA (record_pointers__in_rows__St2),Y
    RTS

; function record_pointers.copy_through
;   no slots
record_pointers__copy_through
    LDY #$00
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    LDY #$01
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    LDY #$02
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    LDY #$03
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    LDY #$04
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    LDY #$05
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    LDY #$06
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    LDY #$07
    LDA (record_pointers__p),Y
    STA (record_pointers__q),Y
    RTS

; function record_pointers.count
;   slot 0 n: size 1, class 1 (either), local, weight 6
record_pointers__count
    LDA #$00
    STA record_pointers__count__n
.L0005
    LDA record_pointers__p
    ORA record_pointers__p+$01
    BEQ .L001E
    INC record_pointers__count__n
    LDY #$01
    LDA (record_pointers__p),Y
    TAX
    LDY #$00
    LDA (record_pointers__p),Y
    STA record_pointers__p
    STX record_pointers__p+$01
    JMP .L0005
.L001E
    LDA record_pointers__count__n
    RTS

; variable record_pointers.p: size 2, class 0 (zp), weight 54

; variable record_pointers.q: size 2, class 0 (zp), weight 10

; variable record_pointers.far: size 2, class 2 (not zp), weight 2

; variable record_pointers.nodes: size 128, class 2 (not zp), weight 10

; variable record_pointers.b: size 1, class 1 (either), weight 6

; variable record_pointers.w: size 2, class 1 (either), weight 6

; variable record_pointers.i: size 1, class 1 (either), weight 6
