; module pointers, cpu 6502
; imports: host

abs_f009 = $F009

; function pointers.length
;   slot 0 s: size 2, class 0 (zp), param, weight 6
;   slot 1 i: size 1, class 1 (either), local, weight 9
pointers__length
    STA pointers__length__s
    STX pointers__length__s+$01
    LDA #$00
    STA pointers__length__i
.L000B
    LDY pointers__length__i
    LDA (pointers__length__s),Y
    BEQ .L0018
    INC pointers__length__i
    JMP .L000B
.L0018
    TYA
    RTS

; function pointers.sum
;   slot 0 q: size 2, class 0 (zp), param, weight 6
;   slot 1 count: size 1, class 1 (either), param, weight 5
;   slot 2 total: size 2, class 1 (either), local, weight 16
;   slot 3 i: size 1, class 1 (either), local, weight 9
pointers__sum
    STA pointers__sum__q
    STX pointers__sum__q+$01
    STY pointers__sum__count
    LDA #$00
    STA pointers__sum__total
    STA pointers__sum__total+$01
    STA pointers__sum__i
.L0014
    LDA pointers__sum__i
    CMP pointers__sum__count
    BCS .L0031
    TAY
    LDA (pointers__sum__q),Y
    CLC
    ADC pointers__sum__total
    STA pointers__sum__total
    BCC .L002B
    INC pointers__sum__total+$01
.L002B
    INC pointers__sum__i
    JMP .L0014
.L0031
    LDX pointers__sum__total+$01
    LDA pointers__sum__total
    RTS

; function pointers.word_at
;   slot 0 q: size 2, class 0 (zp), param, weight 6
;   slot 1 i: size 1, class 1 (either), param, weight 1
;   slot 2 $t1: size 1, class 1 (either), temp, weight 2
;   slot 3 $t2: size 2, class 1 (either), temp, weight 3
pointers__word_at
    STA pointers__word_at__q
    STX pointers__word_at__q+$01
    STY pointers__word_at__i
    TYA
    ASL
    STA pointers__word_at__St1
    CLC
    TAY
    LDA (pointers__word_at__q),Y
    LDY #$00
    ADC (pointers__word_at__q),Y
    STA pointers__word_at__St2
    LDY pointers__word_at__St1
    INY
    LDA (pointers__word_at__q),Y
    LDY #$01
    ADC (pointers__word_at__q),Y
    STA pointers__word_at__St2+$01
    TAX
    LDA pointers__word_at__St2
    RTS

; function pointers.stores
;   slot 0 q: size 2, class 0 (zp), param, weight 6
pointers__stores
    STA pointers__stores__q
    STX pointers__stores__q+$01
    LDA #$05
    STA pointers__n
    LDY #$00
    STA (pointers__stores__q),Y
    TYA
    LDY #$01
    STA (pointers__stores__q),Y
    LDY #$02
    LDA (pointers__stores__q),Y
    STA pointers__n
    LDA #$07
    LDY pointers__n
    STA (pointers__stores__q),Y
    RTS

; function pointers.copies
;   slot 0 i: size 1, class 1 (either), param, weight 2
;   slot 1 $t1: size 2, class 0 (zp), temp, weight 6
pointers__copies
    STA pointers__copies__i
    LDA pointers__far
    STA pointers__copies__St1
    LDX pointers__far+$01
    STX pointers__copies__St1+$01
    LDY #$00
    LDA (pointers__copies__St1),Y
    STA pointers__n
    LDX pointers__copies__i
    LDA pointers__table,X
    STA pointers__copies__St1
    LDA pointers__table+$04,X
    STA pointers__copies__St1+$01
    LDY #$01
    LDA (pointers__copies__St1),Y
    STA pointers__n
    RTS

; data pointers.$1: 5 bytes
pointers__S1
    .byte $74, $65, $78, $74, $00

; function pointers.arithmetic
;   no slots
pointers__arithmetic
    LDA #<pointers__buffer
    STA pointers__p
    LDA #>pointers__buffer
    STA pointers__p+$01
    LDA #<pointers__buffer+$03
    STA pointers__p
    LDA #>pointers__buffer+$03
    STA pointers__p+$01
    INC pointers__p
    BNE .L001C
    INC pointers__p+$01
.L001C
    CLC
    LDA pointers__p
    ADC pointers__n
    STA pointers__p
    BCC .L002B
    INC pointers__p+$01
.L002B
    SEC
    SBC #<pointers__buffer
    STA pointers__w
    LDA pointers__p+$01
    SBC #>pointers__buffer
    STA pointers__w+$01
    LDA pointers__p
    ORA pointers__p+$01
    BNE .L004B
    LDA #<pointers__S1
    STA pointers__p
    LDA #>pointers__S1
    STA pointers__p+$01
.L004B
    LDA pointers__p
    CMP #<pointers__buffer+$10
    LDA pointers__p+$01
    SBC #>pointers__buffer+$10
    BCC .L0061
    LDA #$00
    STA pointers__p
    LDA #$C0
    STA pointers__p+$01
.L0061
    LDA pointers__p
    STA pointers__w
    LDX pointers__p+$01
    STX pointers__w+$01
    RTS

; function pointers.through_module
;   no slots
pointers__through_module
    LDY pointers__n
    LDA (pointers__p),Y
    STA pointers__n
    LDY #$00
    LDA (pointers__p),Y
    CLC
    ADC #$01
    STA (pointers__p),Y
    RTS

; data pointers.$2: 4 bytes
pointers__S2
    .byte $61, $62, $63, $00

; function pointers.main: exported
;   no slots
;   calls pointers.length
;   calls pointers.sum
;   calls pointers.word_at
pointers__main
    LDX #>pointers__S2
    LDA #<pointers__S2
    JSR pointers__length
    JSR abs_f009
    LDY #$04
    LDX #>pointers__buffer
    LDA #<pointers__buffer
    JSR pointers__sum
    STA pointers__w
    STX pointers__w+$01
    LDY #$02
    LDX #>pointers__words+$02
    LDA #<pointers__words+$02
    JSR pointers__word_at
    STA pointers__w
    STX pointers__w+$01
    RTS

; variable pointers.buffer: size 32, class 2 (not zp), weight 0

; variable pointers.words: size 16, class 2 (not zp), weight 0

; variable pointers.p: size 2, class 0 (zp), weight 23

; variable pointers.far: size 2, class 2 (not zp), weight 2

; variable pointers.table: size 8, class 2 (not zp), weight 2

; variable pointers.n: size 1, class 1 (either), weight 8

; variable pointers.w: size 2, class 1 (either), weight 8
