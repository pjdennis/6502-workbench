; module inline_basic, cpu 6502

; function inline_basic.inlined
;   slot 0 k: size 1, class 1 (either), param, weight 10
;   slot 1 v: size 1, class 1 (either), local, weight 2
inline_basic__inlined
    LDX inline_basic__inlined__k
    LDA inline_basic__table,X
    STA inline_basic__inlined__v
    CLC
    LDA inline_basic__table+$03
    ADC inline_basic__g
    STA inline_basic__inlined__v
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
    BCS .L004A
    STY inline_basic__g
.L004A
    LDA inline_basic__inlined__k
    CMP #$09
    BCS .L0057
    INC inline_basic__inlined__k
    JMP .L004A
.L0057
    RTS

; function inline_basic.in_place
;   slot 0 k: size 1, class 1 (either), param, weight 10
;   slot 1 v: size 1, class 1 (either), local, weight 2
inline_basic__in_place
    LDX inline_basic__in_place__k
    LDA inline_basic__table,X
    STA inline_basic__in_place__v
    CLC
    LDA inline_basic__table+$03
    ADC inline_basic__g
    STA inline_basic__in_place__v
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
    BCS .L004A
    STY inline_basic__g
.L004A
    LDA inline_basic__in_place__k
    CMP #$09
    BCS .L0057
    INC inline_basic__in_place__k
    JMP .L004A
.L0057
    RTS

; function inline_basic.not_plain
;   slot 0 k: size 1, class 1 (either), param, weight 1
;   slot 1 $t1: size 1, class 1 (either), temp, weight 1
;   slot 2 $t2: size 2, class 1 (either), temp, weight 2
inline_basic__not_plain
    LDX inline_basic__not_plain__k
    LDA inline_basic__table,X
    STA inline_basic__not_plain__St1
    TAX
    LDA inline_basic__table,X
    STA inline_basic__g
    CLC
    LDA inline_basic__w
    ADC #$01
    TAY
    LDA inline_basic__w+$01
    ADC #$00
    TAX
    TYA
    STA inline_basic__not_plain__St2
    STX inline_basic__not_plain__St2+$01
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
