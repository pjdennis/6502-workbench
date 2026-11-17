; module recursion, cpu 6502
; imports: rt_frame

; function recursion.twice
;   slot 0 n: size 1, class 1 (either), param, weight 2
recursion__twice
    STA recursion__twice__n
    CLC
    ADC recursion__twice__n
    RTS

; function recursion.down: recursive
;   slot 0 n: size 1, class 1 (either), param, weight 1
;   slot 1 w: size 2, class 1 (either), param, weight 8
;   slot 2 keep: size 1, class 1 (either), local, weight 2
;   slot 3 $t1: size 1, class 1 (either), temp, weight 2
;   slot 4 $t2: size 2, class 1 (either), temp, weight 4
;   calls rt_frame.push
;   calls recursion.down (saves frame)
;   calls rt_frame.pop
recursion__down
.L0000
    STA recursion__down__n
    STA recursion__down__keep
    CMP #$00
    BNE .L0011
    LDX recursion__down__w+$01
    LDA recursion__down__w
    RTS
.L0011
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
    JSR rt_frame__push
.L002C
    LDA #$04
    LDA recursion__down__n-$05,Y
    ORA recursion__down__w-$08,Y
    LDA recursion__down__keep-$0B,Y
    LDA recursion__down__St2
    STA recursion__down__w
    LDA recursion__down__St2+$01
    STA recursion__down__w+$01
    LDA recursion__down__St1
    JSR .L0000
    JSR rt_frame__pop
    JSR .L002C
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
;   slot 0 a: size 1, class 1 (either), param, weight 2
;   slot 1 b: size 1, class 1 (either), param, weight 1
;   slot 2 $t1: size 1, class 1 (either), temp, weight 2
;   slot 3 $t2: size 1, class 1 (either), temp, weight 2
;   slot 4 $t3: size 1, class 1 (either), temp, weight 2
;   slot 5 $t4: size 1, class 1 (either), temp, weight 2
;   calls rt_frame.push
;   calls recursion.nest (saves frame)
;   calls rt_frame.pop
recursion__nest
.L0000
    STA recursion__nest__a
    STX recursion__nest__b
    CMP #$00
    BNE .L000C
    TXA
    RTS
.L000C
    SEC
    SBC #$01
    STA recursion__nest__St1
    SEC
    LDA recursion__nest__a
    SBC #$01
    STA recursion__nest__St3
    STX recursion__nest__St4
    JSR rt_frame__push
.L0021
    LDA #$04
    LDA recursion__nest__a-$05,Y
    LDA recursion__nest__b-$08,Y
    LDA recursion__nest__St1-$0B,Y
    LDA recursion__nest__St2-$0E,Y
    LDX recursion__nest__St4
    LDA recursion__nest__St3
    JSR .L0000
    JSR rt_frame__pop
    JSR .L0021
    STA recursion__nest__St2
    JSR rt_frame__push
.L0044
    LDA #$02
    LDA recursion__nest__a-$05,Y
    LDA recursion__nest__b-$08,Y
    LDX recursion__nest__St2
    LDA recursion__nest__St1
    JSR .L0000
    JSR rt_frame__pop
    JSR .L0044
    RTS

; class recursion.simple: parameter sizes 1

; class recursion.stepper: parameter sizes 1; recursive

; function recursion.both: recursive
;   slot 0 n: size 1, class 1 (either), param, weight 1
;   slot 1 x: size 1, class 1 (either), local, weight 3
;   slot 2 $t1: size 1, class 1 (either), temp, weight 2
;   calls recursion.twice
;   calls recursion.simple (through pointer)
;   calls rt_frame.push
;   calls recursion.stepper (saves frame, through pointer)
;   calls rt_frame.pop
recursion__both
    STA recursion__both__n
    JSR recursion__twice
    STA recursion__both__x
    JSR .L002E
    STA recursion__both__x
    STA recursion__both__St1
    JSR rt_frame__push
.L0015
    LDA #$02
    LDA recursion__both__n-$05,Y
    LDA recursion__both__x-$08,Y
    LDA recursion__both__St1
    JSR .L0031
    JSR rt_frame__pop
    JSR .L0015
    CLC
    ADC recursion__both__x
    RTS
.L002E
    JMP (recursion__plain)
.L0031
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
    LDA #$04
    STA recursion__down__w
    LDA #$00
    STA recursion__down__w+$01
    LDA #$03
    JMP recursion__down

; variable recursion.step: size 2, class 1 (either), weight 1

; variable recursion.plain: size 2, class 1 (either), weight 1

; variable recursion.total: size 2, class 1 (either), weight 3
