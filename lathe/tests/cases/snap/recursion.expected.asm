; module recursion, cpu 6502
; imports: rt_frame

; function recursion.twice
;   slot 0 n: size 1, class 1 (either), param, weight 2
recursion__twice
    CLC
    LDA recursion__twice__n
    ADC recursion__twice__n
    RTS

; function recursion.down: recursive
;   slot 0 n: size 1, class 1 (either), param, weight 4
;   slot 1 w: size 2, class 1 (either), param, weight 12
;   slot 2 keep: size 1, class 1 (either), local, weight 4
;   slot 3 $t1: size 1, class 1 (either), temp, weight 2
;   slot 4 $t2: size 2, class 1 (either), temp, weight 4
;   calls rt_frame.push
;   calls recursion.down (saves frame)
;   calls rt_frame.pop_y
recursion__down
.L0000
    LDA recursion__down__n
    STA recursion__down__keep
    BNE .L000F
    LDX recursion__down__w+$01
    LDA recursion__down__w
    RTS
.L000F
    SEC
    SBC #$01
    STA recursion__down__St1
    CLC
    LDA recursion__down__w
    ADC recursion__down__keep
    STA recursion__down__St2
    LDA recursion__down__w+$01
    ADC #$00
    STA recursion__down__St2+$01
    LDA recursion__down__n
    JSR rt_frame__push
    LDA recursion__down__w
    JSR rt_frame__push
    LDA recursion__down__w+$01
    JSR rt_frame__push
    LDA recursion__down__keep
    JSR rt_frame__push
    LDA recursion__down__St1
    STA recursion__down__n
    LDA recursion__down__St2
    STA recursion__down__w
    LDA recursion__down__St2+$01
    STA recursion__down__w+$01
    JSR .L0000
    JSR rt_frame__pop_y
    STY recursion__down__keep
    JSR rt_frame__pop_y
    STY recursion__down__w+$01
    JSR rt_frame__pop_y
    STY recursion__down__w
    JSR rt_frame__pop_y
    STY recursion__down__n
    CLC
    ADC recursion__down__w
    STA recursion__total
    TXA
    ADC recursion__down__w+$01
    STA recursion__total+$01
    TAX
    LDA recursion__total
    RTS

; function recursion.nest: recursive
;   slot 0 a: size 1, class 1 (either), param, weight 8
;   slot 1 b: size 1, class 1 (either), param, weight 8
;   slot 2 $t1: size 1, class 1 (either), temp, weight 4
;   slot 3 $t2: size 1, class 1 (either), temp, weight 4
;   slot 4 $t3: size 1, class 1 (either), temp, weight 2
;   slot 5 $t4: size 1, class 1 (either), temp, weight 2
;   calls rt_frame.push
;   calls recursion.nest (saves frame)
;   calls rt_frame.pop_y
recursion__nest
.L0000
    LDA recursion__nest__a
    BNE .L0009
    LDA recursion__nest__b
    RTS
.L0009
    SEC
    SBC #$01
    STA recursion__nest__St1
    SEC
    LDA recursion__nest__a
    SBC #$01
    STA recursion__nest__St3
    LDA recursion__nest__b
    STA recursion__nest__St4
    LDA recursion__nest__a
    JSR rt_frame__push
    LDA recursion__nest__b
    JSR rt_frame__push
    LDA recursion__nest__St1
    JSR rt_frame__push
    LDA recursion__nest__St2
    JSR rt_frame__push
    LDA recursion__nest__St3
    STA recursion__nest__a
    LDA recursion__nest__St4
    STA recursion__nest__b
    JSR .L0000
    JSR rt_frame__pop_y
    STY recursion__nest__St2
    JSR rt_frame__pop_y
    STY recursion__nest__St1
    JSR rt_frame__pop_y
    STY recursion__nest__b
    JSR rt_frame__pop_y
    STY recursion__nest__a
    STA recursion__nest__St2
    LDA recursion__nest__a
    JSR rt_frame__push
    LDA recursion__nest__b
    JSR rt_frame__push
    LDA recursion__nest__St1
    STA recursion__nest__a
    LDA recursion__nest__St2
    STA recursion__nest__b
    JSR .L0000
    JSR rt_frame__pop_y
    STY recursion__nest__b
    JSR rt_frame__pop_y
    STY recursion__nest__a
    RTS

; class recursion.simple: parameter sizes 1

; class recursion.stepper: parameter sizes 1; recursive

; function recursion.both: recursive
;   slot 0 n: size 1, class 1 (either), param, weight 3
;   slot 1 x: size 1, class 1 (either), local, weight 5
;   slot 2 $t1: size 1, class 1 (either), temp, weight 2
;   calls recursion.twice
;   calls recursion.simple (through pointer)
;   calls rt_frame.push
;   calls recursion.stepper (saves frame, through pointer)
;   calls rt_frame.pop_y
recursion__both
    LDA recursion__both__n
    STA recursion__twice__n
    JSR recursion__twice
    STA recursion__both__x
    STA recursion__simple__p0
    JSR .L003E
    STA recursion__both__x
    STA recursion__both__St1
    LDA recursion__both__n
    JSR rt_frame__push
    LDA recursion__both__x
    JSR rt_frame__push
    LDA recursion__both__St1
    STA recursion__stepper__p0
    JSR .L0041
    JSR rt_frame__pop_y
    STY recursion__both__x
    JSR rt_frame__pop_y
    STY recursion__both__n
    CLC
    ADC recursion__both__x
    RTS
.L003E
    JMP (recursion__plain)
.L0041
    JMP (recursion__step)

; function recursion.empty: recursive
;   no slots
;   calls recursion.empty (saves frame)
recursion__empty
.L0000
    JMP .L0000

; function recursion.outside
;   no slots
;   calls recursion.down
recursion__outside
    LDA #$03
    STA recursion__down__n
    LDA #$04
    STA recursion__down__w
    LDA #$00
    STA recursion__down__w+$01
    JMP recursion__down

; variable recursion.step: size 2, class 1 (either), weight 1

; variable recursion.plain: size 2, class 1 (either), weight 1

; variable recursion.total: size 2, class 1 (either), weight 3
