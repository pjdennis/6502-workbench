; module named_types, cpu 6502
; imports: libtypes

; function named_types.names
;   slot 0 $t1: size 2, class 0 (zp), temp, weight 4
named_types__names
    LDA #$03
    STA named_types__b
    LDA named_types__q
    STA named_types__p
    LDA named_types__q+$01
    STA named_types__p+$01
    LDA named_types__p
    STA named_types__t+$01
    LDA named_types__p+$01
    STA named_types__t+$04
    LDA named_types__w
    STA named_types__p
    LDA named_types__w+$01
    STA named_types__p+$01
    CLC
    LDA named_types__p
    ADC #$06
    TAY
    LDA named_types__p+$01
    ADC #$00
    TAX
    TYA
    CLC
    ADC #$04
    STA named_types__w
    TXA
    ADC #$00
    STA named_types__w+$01
    LDA #<named_types__s
    STA named_types__s+$02
    LDA #>named_types__s
    STA named_types__s+$03
    LDA named_types__s+$02
    STA named_types__names__St1
    LDA named_types__s+$03
    STA named_types__names__St1+$01
    LDA #$00
    TAY
    STA (named_types__names__St1),Y
    LDY #$01
    STA (named_types__names__St1),Y
    RTS

; function named_types.imported
;   no slots
;   calls libtypes.count_of
named_types__imported
    LDA #<libtypes__first
    STA named_types__it
    LDA #>libtypes__first
    STA named_types__it+$01
    LDY #$00
    LDA (named_types__it),Y
    STA named_types__m
    LDA #$01
    LDX named_types__b
    STA named_types__items,X
    LDA named_types__it
    STA named_types__items+$18,X
    LDA named_types__it+$01
    STA named_types__items+$20,X
    LDA #<libtypes__first
    STA libtypes__count_of__p
    LDA #>libtypes__first
    STA libtypes__count_of__p+$01
    JSR libtypes__count_of
    CLC
    ADC named_types__counts+$03
    STA named_types__w
    TXA
    ADC named_types__counts+$07
    STA named_types__w+$01
    LDA libtypes__first
    BNE .L0064
    LDX named_types__b
    LDA named_types__items,X
    STA libtypes__first
    LDA named_types__items+$08,X
    STA libtypes__first+$01
    LDA named_types__items+$10,X
    STA libtypes__first+$02
    LDA named_types__items+$18,X
    STA libtypes__first+$03
    LDA named_types__items+$20,X
    STA libtypes__first+$04
.L0064
    LDA named_types__w
    STA named_types__it
    LDA named_types__w+$01
    STA named_types__it+$01
    RTS

; variable named_types.b: size 1, class 1 (either), weight 3

; variable named_types.p: size 2, class 1 (either), weight 8

; variable named_types.q: size 2, class 1 (either), weight 2

; variable named_types.t: size 6, class 2 (not zp), weight 2

; variable named_types.w: size 2, class 1 (either), weight 8

; variable named_types.s: size 4, class 2 (not zp), weight 4

; variable named_types.items: size 40, class 2 (not zp), weight 8

; variable named_types.it: size 2, class 0 (zp), weight 7

; variable named_types.counts: size 8, class 2 (not zp), weight 2

; variable named_types.m: size 1, class 1 (either), weight 1
