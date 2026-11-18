; module inline_basic, cpu 6502

; function inline_basic.inlined
;   slot 0 k: size 1, class 1 (either), param, weight 10
;   slot 1 v: size 1, class 1 (either), local, weight 0
inline_basic__inlined
    STA inline_basic__inlined__k
    TAX
    LDA inline_basic__table,X
    CLC
    LDA inline_basic__table+$03
    ADC inline_basic__g
    LDA inline_basic__words,X
    STA inline_basic__w
    LDA inline_basic__words+$10,X
    STA inline_basic__w+$01
    CLC
    LDA inline_basic__w
    ADC #$E8
    STA inline_basic__w
    LDA inline_basic__w+$01
    ADC #$03
    STA inline_basic__w+$01
    LDY #$00
    LDA (inline_basic__ptr),Y
    STA inline_basic__g
    STA inline_basic__table,X
    LDA #$07
    STA inline_basic__table+$02
    LDA inline_basic__g
    CMP inline_basic__inlined__k
    BCS .L0045
    STY inline_basic__g
.L0045
    LDA inline_basic__inlined__k
    CMP #$09
    BCS .L0052
    INC inline_basic__inlined__k
    JMP .L0045
.L0052
    RTS

; function inline_basic.in_place
;   slot 0 k: size 1, class 1 (either), param, weight 10
;   slot 1 v: size 1, class 1 (either), local, weight 0
inline_basic__in_place
    STA inline_basic__in_place__k
    TAX
    LDA inline_basic__table,X
    CLC
    LDA inline_basic__table+$03
    ADC inline_basic__g
    LDA inline_basic__words,X
    STA inline_basic__w
    LDA inline_basic__words+$10,X
    STA inline_basic__w+$01
    CLC
    LDA inline_basic__w
    ADC #$E8
    STA inline_basic__w
    LDA inline_basic__w+$01
    ADC #$03
    STA inline_basic__w+$01
    LDY #$00
    LDA (inline_basic__ptr),Y
    STA inline_basic__g
    STA inline_basic__table,X
    LDA #$07
    STA inline_basic__table+$02
    LDA inline_basic__g
    CMP inline_basic__in_place__k
    BCS .L0045
    STY inline_basic__g
.L0045
    LDA inline_basic__in_place__k
    CMP #$09
    BCS .L0052
    INC inline_basic__in_place__k
    JMP .L0045
.L0052
    RTS

; function inline_basic.not_plain
;   slot 0 k: size 1, class 1 (either), param, weight 0
;   slot 1 $t1: size 1, class 1 (either), temp, weight 0
;   slot 2 $t2: size 2, class 1 (either), temp, weight 0
inline_basic__not_plain
    TAX
    LDA inline_basic__table,X
    TAY
    LDA inline_basic__table,Y
    STA inline_basic__g
    CLC
    LDA inline_basic__w
    ADC #$01
    TAY
    LDA inline_basic__w+$01
    ADC #$00
    TAX
    TYA
    CLC
    ADC inline_basic__w
    TAY
    TXA
    ADC inline_basic__w+$01
    TAX
    TYA
    STA inline_basic__w
    STX inline_basic__w+$01
    RTS

; variable inline_basic.table: size 16, class 2 (not zp), weight 10

; variable inline_basic.words: size 32, class 2 (not zp), weight 4

; variable inline_basic.ptr: size 2, class 0 (zp), weight 2

; variable inline_basic.g: size 1, class 1 (either), weight 9

; variable inline_basic.w: size 2, class 1 (either), weight 18
