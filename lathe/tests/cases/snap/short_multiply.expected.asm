; module short_multiply, cpu 6502
; imports: rt_math

abs_d000 = $D000

; function short_multiply.f
;   slot 0 i: size 1, class 1 (either), param, weight 3
;   slot 1 $t1: size 1, class 1 (either), temp, weight 2
;   calls rt_math.mul8
;   calls rt_math.mul16
short_multiply__f
    STA short_multiply__f__i
    LDA short_multiply__a
    ASL
    CLC
    ADC short_multiply__a
    STA short_multiply__a
    LDX #$05
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$06
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$07
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$09
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$0A
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$0C
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDA short_multiply__s
    ASL
    CLC
    ADC short_multiply__s
    STA short_multiply__s
    LDX short_multiply__f__i
    LDA short_multiply__tab,X
    STA short_multiply__f__St1
    LDX #$0A
    JSR rt_math__mul8
    STA short_multiply__a
    CLC
    ADC short_multiply__b
    LDX #$05
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$0B
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$0E
    LDA short_multiply__b
    JSR rt_math__mul8
    STA short_multiply__a
    LDX #$03
    LDA abs_d000
    JSR rt_math__mul8
    STA short_multiply__a
    LDY short_multiply__f__i
    LDA (short_multiply__p),Y
    STA short_multiply__f__St1
    LDX #$03
    JSR rt_math__mul8
    STA short_multiply__a
    LDA #$03
    STA rt_math__mul16__1
    LDA #$00
    STA rt_math__mul16__1+$01
    LDX short_multiply__w+$01
    LDA short_multiply__w
    JSR rt_math__mul16
    STA short_multiply__w
    STX short_multiply__w+$01
    RTS

; variable short_multiply.a: size 1, class 1 (either), weight 15

; variable short_multiply.b: size 1, class 1 (either), weight 9

; variable short_multiply.s: size 1, class 1 (either), weight 3

; variable short_multiply.tab: size 8, class 2 (not zp), weight 1

; variable short_multiply.p: size 2, class 0 (zp), weight 1

; variable short_multiply.w: size 2, class 1 (either), weight 4
