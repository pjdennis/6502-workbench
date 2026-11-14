; module arith_calls, cpu 6502
; imports: rt_math

; function arith_calls.bytes
;   no slots
;   calls rt_math.mul8
;   calls rt_math.div8
;   calls rt_math.mod8
;   calls rt_math.sdiv8
;   calls rt_math.smod8
arith_calls__bytes
    LDX arith_calls__b
    LDA arith_calls__a
    JSR rt_math__mul8
    STA arith_calls__a
    TAX
    LDA arith_calls__b
    JSR rt_math__div8
    STA arith_calls__a
    LDX #$07
    JSR rt_math__mod8
    STA arith_calls__a
    LDX arith_calls__b
    LDA #$64
    JSR rt_math__div8
    STA arith_calls__a
    LDX arith_calls__t
    LDA arith_calls__s
    JSR rt_math__mul8
    STA arith_calls__s
    LDX arith_calls__t
    JSR rt_math__sdiv8
    STA arith_calls__s
    LDX arith_calls__t
    JSR rt_math__smod8
    STA arith_calls__s
    LDX #$04
    JSR rt_math__sdiv8
    STA arith_calls__s
    RTS

; function arith_calls.words
;   no slots
;   calls rt_math.mul16
;   calls rt_math.div16
;   calls rt_math.mod16
;   calls rt_math.mul8x8
;   calls rt_math.sdiv16
;   calls rt_math.smod16
arith_calls__words
    LDA arith_calls__v
    STA rt_math__mul16__1
    LDX arith_calls__v+$01
    STX rt_math__mul16__1+$01
    LDX arith_calls__u+$01
    LDA arith_calls__u
    JSR rt_math__mul16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA arith_calls__v
    STA rt_math__div16__1
    LDX arith_calls__v+$01
    STX rt_math__div16__1+$01
    LDX arith_calls__u+$01
    LDA arith_calls__u
    JSR rt_math__div16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA #$E8
    STA rt_math__mod16__1
    LDA #$03
    STA rt_math__mod16__1+$01
    LDA arith_calls__u
    JSR rt_math__mod16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA #$03
    STA rt_math__mul16__1
    LDA #$00
    STA rt_math__mul16__1+$01
    LDA arith_calls__u
    JSR rt_math__mul16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA arith_calls__a
    STA rt_math__mul16__1
    LDA #$00
    STA rt_math__mul16__1+$01
    LDA arith_calls__u
    JSR rt_math__mul16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA arith_calls__a
    STA rt_math__mul16__1
    LDA #$00
    STA rt_math__mul16__1+$01
    LDA arith_calls__u
    JSR rt_math__mul16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDX arith_calls__b
    LDA arith_calls__a
    JSR rt_math__mul8x8
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA arith_calls__a
    STA rt_math__mul16__1
    LDA #$00
    STA rt_math__mul16__1+$01
    LDX #$01
    LDA #$2C
    JSR rt_math__mul16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA #$2C
    STA rt_math__mul16__1
    LDA #$01
    STA rt_math__mul16__1+$01
    LDA arith_calls__u
    JSR rt_math__mul16
    STA arith_calls__u
    STX arith_calls__u+$01
    LDA arith_calls__j
    STA rt_math__mul16__1
    LDX arith_calls__j+$01
    STX rt_math__mul16__1+$01
    LDX arith_calls__i+$01
    LDA arith_calls__i
    JSR rt_math__mul16
    STA arith_calls__i
    STX arith_calls__i+$01
    LDA arith_calls__j
    STA rt_math__sdiv16__1
    LDX arith_calls__j+$01
    STX rt_math__sdiv16__1+$01
    LDX arith_calls__i+$01
    LDA arith_calls__i
    JSR rt_math__sdiv16
    STA arith_calls__i
    STX arith_calls__i+$01
    LDA arith_calls__j
    STA rt_math__smod16__1
    LDX arith_calls__j+$01
    STX rt_math__smod16__1+$01
    LDX arith_calls__i+$01
    LDA arith_calls__i
    JSR rt_math__smod16
    STA arith_calls__i
    STX arith_calls__i+$01
    LDA #$02
    STA rt_math__sdiv16__1
    LDA #$00
    STA rt_math__sdiv16__1+$01
    LDA arith_calls__i
    JSR rt_math__sdiv16
    STA arith_calls__i
    STX arith_calls__i+$01
    RTS

; function arith_calls.used
;   slot 0 $t1: size 1, class 1 (either), temp, weight 3
;   calls rt_math.mul8
;   calls rt_math.mod8
;   calls rt_math.div8
arith_calls__used
    LDX arith_calls__b
    LDA arith_calls__a
    JSR rt_math__mul8
    STA arith_calls__used__St1
    LDX arith_calls__a
    LDA arith_calls__b
    JSR rt_math__mul8
    CLC
    ADC arith_calls__used__St1
    STA arith_calls__a
    LDX #$0B
    JSR rt_math__mul8
    LDX #$0A
    JSR rt_math__mod8
    STA arith_calls__used__St1
    TAX
    LDA arith_calls__tab,X
    STA arith_calls__a
    LDX arith_calls__b
    JSR rt_math__div8
    CMP #$02
    BNE .L0043
    LDX arith_calls__b
    LDA arith_calls__a
    JMP rt_math__mod8
.L0043
    CLC
    LDA arith_calls__a
    ADC arith_calls__b
    TAX
    LDA arith_calls__a
    JMP rt_math__mul8

; variable arith_calls.a: size 1, class 1 (either), weight 16

; variable arith_calls.b: size 1, class 1 (either), weight 9

; variable arith_calls.s: size 1, class 1 (either), weight 5

; variable arith_calls.t: size 1, class 1 (either), weight 3

; variable arith_calls.u: size 2, class 1 (either), weight 27

; variable arith_calls.v: size 2, class 1 (either), weight 4

; variable arith_calls.i: size 2, class 1 (either), weight 15

; variable arith_calls.j: size 2, class 1 (either), weight 6

; variable arith_calls.tab: size 10, class 2 (not zp), weight 1
