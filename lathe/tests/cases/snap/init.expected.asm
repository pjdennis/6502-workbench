; module init, cpu 6502

abs_d020 = $D020
abs_d021 = $D021
zp_fe = $FE
zp_ff = $FF

; function init.placements
;   no slots
init__placements
    LDA init__plain
    STA init__fast
    STA init__slow
    LDA #$00
    STA init__slow+$01
    INC init__quick
    BNE .L0013
    INC init__quick+$01
.L0013
    STA abs_d020
    LDA init__slow
    STA zp_fe
    LDX init__slow+$01
    STX zp_ff
    RTS

; function init.locals
;   slot 0 n: size 1, class 1 (either), param, weight 1
;   slot 1 i: size 1, class 1 (either), local, weight 1
;   slot 2 w: size 2, class 1 (either), local, weight 3
;   slot 3 p: size 1, class 0 (zp), local, weight 1
init__locals
    STA init__locals__n
    CLC
    ADC #$01
    STA init__locals__i
    STA init__locals__w
    LDA #$00
    STA init__locals__w+$01
    LDA init__locals__w
    STA init__locals__p
    RTS

; function init.counter
;   no slots
init__counter
    CLC
    LDA init__counter__calls
    ADC init__counter__step
    STA init__counter__calls
    RTS

; variable init.counter.calls: size 1, class 1 (either), weight 2

; variable init.counter.step: size 1, class 1 (either), weight 1

; variable init.plain: size 1, class 1 (either), weight 1

; variable init.fast: size 1, class 0 (zp), weight 1

; variable init.slow: size 2, class 2 (not zp), weight 4

; variable init.count: size 1, class 1 (either), weight 0

; variable init.total: size 2, class 1 (either), weight 0

; variable init.limit: size 2, class 1 (either), weight 0

; variable init.ready: size 1, class 1 (either), weight 0

; variable init.offset: size 2, class 1 (either), weight 0

; variable init.quick: size 2, class 0 (zp), weight 2

; variable init.shared: size 1, class 1 (either), weight 0

; function init.$init
;   no slots
init__Sinit
    LDA #$05
    STA init__count
    LDA #$00
    STA init__total
    STA init__total+$01
    LDA #$E8
    STA init__limit
    LDA #$03
    STA init__limit+$01
    LDA #$01
    STA init__ready
    LDA #$FE
    STA init__offset
    LDA #$FF
    STA init__offset+$01
    LDA #$00
    STA init__quick
    STA init__quick+$01
    LDA #$05
    STA init__shared
    LDA #$00
    STA abs_d021
    STA init__counter__calls
    LDA #$01
    STA init__counter__step
    RTS
