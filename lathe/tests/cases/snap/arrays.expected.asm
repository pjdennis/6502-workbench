; module arrays, cpu 6502

; function arrays.constant_index
;   no slots
arrays__constant_index
    LDA #$01
    STA arrays__a
    LDA arrays__a+$03
    STA arrays__a+$0F
    RTS

; function arrays.variable_index
;   no slots
arrays__variable_index
    LDX arrays__i
    LDA arrays__b,X
    STA arrays__a,X
    CLC
    LDA arrays__a,X
    ADC arrays__b,X
    STA arrays__n
    RTS

; function arrays.folded
;   no slots
arrays__folded
    LDX arrays__i
    LDA arrays__a-$01,X
    STA arrays__a+$01,X
    RTS

; function arrays.computed
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
arrays__computed
    CLC
    LDA arrays__i
    ADC arrays__j
    STA arrays__computed__St1
    TAX
    LDA arrays__a,X
    STA arrays__n
    LDX arrays__i
    LDA arrays__b,X
    STA arrays__computed__St1
    TAX
    LDA arrays__a,X
    STA arrays__n
    RTS

; function arrays.in_place
;   no slots
arrays__in_place
    LDX arrays__i
    INC arrays__a,X
    LDX arrays__j
    DEC arrays__b,X
    LDX arrays__i
    ASL arrays__a,X
    RTS

; function arrays.forgetting
;   no slots
arrays__forgetting
    LDA arrays__a+$03
    STA arrays__n
    LDA #$00
    LDX arrays__i
    STA arrays__a,X
    LDA arrays__a+$03
    STA arrays__n
    STX arrays__j
    STA arrays__a,X
    RTS

; function arrays.search
;   slot 0 v: size 1, class 1 (either), param, weight 5
;   slot 1 k: size 1, class 1 (either), local, weight 9
arrays__search
    STA arrays__search__v
    LDA #$00
    STA arrays__search__k
.L0008
    LDA arrays__search__k
    CMP #$10
    BCS .L0020
    TAX
    LDA arrays__a,X
    CMP arrays__search__v
    BNE .L001A
    TXA
    RTS
.L001A
    INC arrays__search__k
    JMP .L0008
.L0020
    LDA #$FF
    RTS

; function arrays.sizes
;   no slots
arrays__sizes
    LDA #$10
    STA arrays__n
    LDA #$08
    STA arrays__n
    RTS

; variable arrays.a: size 16, class 2 (not zp), weight 19

; variable arrays.b: size 16, class 2 (not zp), weight 4

; variable arrays.i: size 1, class 1 (either), weight 7

; variable arrays.j: size 1, class 1 (either), weight 3

; variable arrays.n: size 1, class 1 (either), weight 7
