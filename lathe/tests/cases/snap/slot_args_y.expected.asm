; module slot_args_y, cpu 6502

; function slot_args_y.four
;   slot 0 x: size 1, class 1 (either), param, weight 0
;   slot 1 y: size 1, class 1 (either), param, weight 2
;   slot 2 z: size 1, class 1 (either), param, weight 2
;   slot 3 q: size 1, class 1 (either), param, weight 1
slot_args_y__four
    STX slot_args_y__four__y
    STY slot_args_y__four__z
    EOR slot_args_y__four__y
    EOR slot_args_y__four__z
    EOR slot_args_y__four__q
    STA slot_args_y__got
    RTS

; function slot_args_y.pair
;   slot 0 x: size 2, class 1 (either), param, weight 0
;   slot 1 y: size 2, class 1 (either), param, weight 2
slot_args_y__pair
    EOR slot_args_y__pair__y
    STA slot_args_y__u
    TXA
    EOR slot_args_y__pair__y+$01
    STA slot_args_y__u+$01
    RTS

; function slot_args_y.wide
;   slot 0 x: size 2, class 1 (either), param, weight 0
;   slot 1 y: size 1, class 1 (either), param, weight 0
;   slot 2 z: size 1, class 1 (either), param, weight 1
;   slot 3 q: size 2, class 1 (either), param, weight 2
slot_args_y__wide
    EOR slot_args_y__wide__q
    STA slot_args_y__u
    TXA
    EOR slot_args_y__wide__q+$01
    STA slot_args_y__u+$01
    TYA
    EOR slot_args_y__wide__z
    STA slot_args_y__got
    RTS

; function slot_args_y.one
;   slot 0 x: size 1, class 1 (either), param, weight 0
slot_args_y__one
    CLC
    ADC #$01
    RTS

; function slot_args_y.plain
;   no slots
;   calls slot_args_y.four
;   calls slot_args_y.pair
;   calls slot_args_y.wide
slot_args_y__plain
    CLC
    LDA slot_args_y__b
    ADC #$01
    LDY #$07
    STY slot_args_y__four__q
    LDY #$03
    LDX #$02
    JSR slot_args_y__four
    CLC
    LDA slot_args_y__b
    ADC #$01
    LDY slot_args_y__e
    STY slot_args_y__four__q
    LDY slot_args_y__d
    LDX slot_args_y__c
    JSR slot_args_y__four
    CLC
    LDA slot_args_y__b
    ADC #$01
    LDY #$09
    STY slot_args_y__four__q
    LDX #$09
    JSR slot_args_y__four
    CLC
    LDA slot_args_y__v
    ADC slot_args_y__w
    TAY
    LDA slot_args_y__v+$01
    ADC slot_args_y__w+$01
    TAX
    TYA
    LDY #$34
    STY slot_args_y__pair__y
    LDY #$12
    STY slot_args_y__pair__y+$01
    JSR slot_args_y__pair
    CLC
    LDA slot_args_y__v
    ADC slot_args_y__w
    TAY
    LDA slot_args_y__v+$01
    ADC slot_args_y__w+$01
    TAX
    TYA
    LDY slot_args_y__u
    STY slot_args_y__pair__y
    LDY slot_args_y__u+$01
    STY slot_args_y__pair__y+$01
    JSR slot_args_y__pair
    CLC
    LDA slot_args_y__v
    ADC slot_args_y__w
    TAY
    LDA slot_args_y__v+$01
    ADC slot_args_y__w+$01
    TAX
    TYA
    LDY slot_args_y__e
    STY slot_args_y__pair__y
    LDY #$00
    STY slot_args_y__pair__y+$01
    JSR slot_args_y__pair
    CLC
    LDA slot_args_y__v
    ADC slot_args_y__w
    TAY
    LDA slot_args_y__v+$01
    ADC slot_args_y__w+$01
    TAX
    TYA
    LDY #$05
    STY slot_args_y__wide__z
    LDY #$00
    STY slot_args_y__wide__q
    LDY #$FF
    STY slot_args_y__wide__q+$01
    LDY slot_args_y__b
    JMP slot_args_y__wide

; function slot_args_y.indexed
;   slot 0 $t1: size 2, class 1 (either), temp, weight 6
;   slot 1 $t2: size 1, class 1 (either), temp, weight 4
;   slot 2 $t3: size 1, class 1 (either), temp, weight 2
;   slot 3 $t4: size 1, class 1 (either), temp, weight 0
;   calls slot_args_y.wide
;   calls slot_args_y.four
slot_args_y__indexed
    CLC
    LDA slot_args_y__v
    ADC slot_args_y__w
    TAY
    LDA slot_args_y__v+$01
    ADC slot_args_y__w+$01
    TAX
    TYA
    LDY slot_args_y__c
    STY slot_args_y__wide__z
    LDY slot_args_y__u
    STY slot_args_y__wide__q
    LDY slot_args_y__u+$01
    STY slot_args_y__wide__q+$01
    STA slot_args_y__indexed__St1
    STX slot_args_y__indexed__St1+$01
    LDY slot_args_y__c
    LDA slot_args_y__table,Y
    STA slot_args_y__indexed__St2
    TAY
    LDA slot_args_y__indexed__St1
    JSR slot_args_y__wide
    CLC
    LDA slot_args_y__v
    ADC slot_args_y__w
    TAY
    LDA slot_args_y__v+$01
    ADC slot_args_y__w+$01
    TAX
    TYA
    LDY slot_args_y__e
    STY slot_args_y__wide__z
    STA slot_args_y__indexed__St1
    STX slot_args_y__indexed__St1+$01
    LDY slot_args_y__c
    LDA slot_args_y__words,Y
    STA slot_args_y__wide__q
    LDA slot_args_y__words+$04,Y
    STA slot_args_y__wide__q+$01
    LDA (slot_args_y__p),Y
    STA slot_args_y__indexed__St2
    TAY
    LDA slot_args_y__indexed__St1
    JSR slot_args_y__wide
    CLC
    LDA slot_args_y__b
    ADC #$01
    LDY slot_args_y__d
    STY slot_args_y__four__q
    STA slot_args_y__indexed__St2
    LDY slot_args_y__e
    LDA (slot_args_y__p),Y
    STA slot_args_y__indexed__St3
    LDX slot_args_y__c
    LDA slot_args_y__table,X
    TAY
    LDX slot_args_y__indexed__St3
    LDA slot_args_y__indexed__St2
    JMP slot_args_y__four

; class slot_args_y.quad: parameter sizes 1, 1, 1, 1

; slot_args_y.four is a member of class slot_args_y.quad

; function slot_args_y.calls
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
;   slot 1 $t2: size 1, class 1 (either), temp, weight 2
;   slot 2 $t3: size 1, class 1 (either), temp, weight 2
;   slot 3 $t4: size 2, class 1 (either), temp, weight 4
;   calls slot_args_y.one
;   calls slot_args_y.four
;   calls slot_args_y.wide
;   calls slot_args_y.quad (through pointer)
slot_args_y__calls
    CLC
    LDA slot_args_y__b
    ADC #$01
    LDY slot_args_y__c
    STY slot_args_y__calls__St1
    LDY slot_args_y__d
    STY slot_args_y__calls__St2
    STA slot_args_y__calls__St3
    LDA slot_args_y__e
    JSR slot_args_y__one
    STA slot_args_y__four__q
    LDY slot_args_y__calls__St2
    LDX slot_args_y__calls__St1
    LDA slot_args_y__calls__St3
    JSR slot_args_y__four
    SEC
    LDA slot_args_y__u
    SBC slot_args_y__v
    TAY
    LDA slot_args_y__u+$01
    SBC slot_args_y__v+$01
    TAX
    TYA
    STA slot_args_y__calls__St4
    STX slot_args_y__calls__St4+$01
    LDA slot_args_y__b
    JSR slot_args_y__one
    LDY slot_args_y__e
    STY slot_args_y__wide__z
    LDY slot_args_y__w
    STY slot_args_y__wide__q
    LDY slot_args_y__w+$01
    STY slot_args_y__wide__q+$01
    TAY
    LDX slot_args_y__calls__St4+$01
    LDA slot_args_y__calls__St4
    JSR slot_args_y__wide
    LDA #<slot_args_y__four
    STA slot_args_y__h
    LDA #>slot_args_y__four
    STA slot_args_y__h+$01
    CLC
    LDA slot_args_y__b
    ADC #$01
    LDY slot_args_y__d
    STY slot_args_y__quad__p3
    LDY #$03
    LDX #$02
    JMP (slot_args_y__h)

; function slot_args_y.main: exported
;   no slots
;   calls slot_args_y.plain
;   calls slot_args_y.indexed
;   calls slot_args_y.calls
slot_args_y__main
    JSR slot_args_y__plain
    JSR slot_args_y__indexed
    JMP slot_args_y__calls

; variable slot_args_y.b: size 1, class 1 (either), weight 8

; variable slot_args_y.c: size 1, class 1 (either), weight 6

; variable slot_args_y.d: size 1, class 1 (either), weight 4

; variable slot_args_y.e: size 1, class 1 (either), weight 6

; variable slot_args_y.got: size 1, class 1 (either), weight 2

; variable slot_args_y.u: size 2, class 1 (either), weight 10

; variable slot_args_y.v: size 2, class 1 (either), weight 14

; variable slot_args_y.w: size 2, class 1 (either), weight 14

; variable slot_args_y.table: size 8, class 2 (not zp), weight 2

; variable slot_args_y.words: size 8, class 2 (not zp), weight 2

; variable slot_args_y.p: size 2, class 0 (zp), weight 2

; variable slot_args_y.h: size 2, class 1 (either), weight 3
