; module pointer_calls, cpu 6502

abs_c800 = $C800

; function pointer_calls.mix
;   slot 0 a: size 1, class 1 (either), param, weight 1
;   slot 1 w: size 2, class 1 (either), param, weight 0
pointer_calls__mix
    STA pointer_calls__mix__a
    RTS

; class pointer_calls.handler: parameter sizes 1, 2

; function pointer_calls.through_variables
;   slot 0 h: size 2, class 1 (either), param, weight 3
;   slot 1 local: size 2, class 1 (either), local, weight 3
;   calls pointer_calls.handler (through pointer)
pointer_calls__through_variables
    STA pointer_calls__through_variables__h
    STX pointer_calls__through_variables__h+$01
    STA pointer_calls__through_variables__local
    STX pointer_calls__through_variables__local+$01
    LDA #$02
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA #$01
    JSR .L0076
    LDA #$00
    ROL
    STA pointer_calls__ok
    LDA #$04
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA #$03
    JSR .L0076
    LDA #$00
    ROL
    STA pointer_calls__ok
    LDA #$06
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA #$05
    JSR .L0079
    LDA #$00
    ROL
    STA pointer_calls__ok
    LDA #$08
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA #$07
    JSR .L007C
    LDA #$00
    ROL
    STA pointer_calls__ok
    LDA #$0A
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA #$09
    JSR .L007F
    LDA #$00
    ROL
    STA pointer_calls__ok
    RTS
.L0076
    JMP (pointer_calls__on_key)
.L0079
    JMP (pointer_calls__through_variables__h)
.L007C
    JMP (pointer_calls__through_variables__local)
.L007F
    JMP (abs_c800)

; class pointer_calls.pick: parameter sizes 1

; function pointer_calls.through_copies
;   slot 0 i: size 1, class 1 (either), param, weight 1
;   slot 1 n: size 2, class 0 (zp), param, weight 4
;   slot 2 $t1: size 2, class 0 (zp), temp, weight 10
;   slot 3 $t2: size 2, class 1 (either), temp, weight 3
;   calls pointer_calls.pick (through pointer)
pointer_calls__through_copies
    STA pointer_calls__through_copies__i
    TAX
    LDA pointer_calls__table,X
    STA pointer_calls__through_copies__St1
    LDA pointer_calls__table+$04,X
    STA pointer_calls__through_copies__St1+$01
    TXA
    JSR .L0062
    STA pointer_calls__b
    LDA #$00
    ROL
    STA pointer_calls__ok
    LDY #$02
    LDA (pointer_calls__through_copies__n),Y
    STA pointer_calls__through_copies__St1
    LDY #$03
    LDA (pointer_calls__through_copies__n),Y
    STA pointer_calls__through_copies__St1+$01
    LDA #$02
    JSR .L0062
    STA pointer_calls__b
    BCC .L003A
    LDA #$01
    STA pointer_calls__ok
.L003A
    LDY #$00
    LDA (pointer_calls__through_copies__n),Y
    STA pointer_calls__through_copies__St1
    LDY #$01
    LDA (pointer_calls__through_copies__n),Y
    STA pointer_calls__through_copies__St1+$01
    LDY #$02
    LDA (pointer_calls__through_copies__St1),Y
    STA pointer_calls__through_copies__St2
    LDY #$03
    LDA (pointer_calls__through_copies__St1),Y
    STA pointer_calls__through_copies__St2+$01
    TYA
    JSR .L0065
    STA pointer_calls__b
    LDA #$00
    ROL
    STA pointer_calls__ok
    RTS
.L0062
    JMP (pointer_calls__through_copies__St1)
.L0065
    JMP (pointer_calls__through_copies__St2)

; function pointer_calls.in_arguments
;   slot 0 i: size 1, class 1 (either), param, weight 3
;   slot 1 $t1: size 1, class 1 (either), temp, weight 4
;   calls pointer_calls.handler (through pointer)
;   calls pointer_calls.mix
pointer_calls__in_arguments
    STA pointer_calls__in_arguments__i
    STA pointer_calls__in_arguments__St1
    LDA #$01
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA pointer_calls__in_arguments__i
    JSR .L0054
    LDA #$00
    ROL
    STA pointer_calls__mix__w
    LDA #$00
    STA pointer_calls__mix__w+$01
    LDA pointer_calls__in_arguments__St1
    JSR pointer_calls__mix
    STA pointer_calls__b
    LDA pointer_calls__in_arguments__i
    STA pointer_calls__in_arguments__St1
    LDA #$03
    STA pointer_calls__mix__w
    LDA #$00
    STA pointer_calls__mix__w+$01
    LDA #$02
    JSR pointer_calls__mix
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA pointer_calls__in_arguments__St1
    JSR .L0054
    LDA #$00
    ROL
    STA pointer_calls__ok
    RTS
.L0054
    JMP (pointer_calls__on_key)

; function pointer_calls.passed_on
;   slot 0 i: size 1, class 1 (either), param, weight 1
;   slot 1 $t1: size 2, class 1 (either), temp, weight 3
;   calls pointer_calls.pick (through pointer)
pointer_calls__passed_on
    STA pointer_calls__passed_on__i
    TAX
    LDA pointer_calls__table,X
    STA pointer_calls__passed_on__St1
    LDA pointer_calls__table+$04,X
    STA pointer_calls__passed_on__St1+$01
    TXA
    JMP (pointer_calls__passed_on__St1)

; function pointer_calls.last
;   slot 0 h: size 2, class 1 (either), param, weight 3
;   calls pointer_calls.handler (through pointer)
pointer_calls__last
    STA pointer_calls__last__h
    STX pointer_calls__last__h+$01
    LDA #$02
    STA pointer_calls__handler__p1
    LDA #$00
    STA pointer_calls__handler__p1+$01
    LDA #$01
    JMP (pointer_calls__last__h)

; variable pointer_calls.on_key: size 2, class 1 (either), weight 4

; variable pointer_calls.table: size 8, class 2 (not zp), weight 4

; variable pointer_calls.ok: size 1, class 1 (either), weight 9

; variable pointer_calls.b: size 1, class 1 (either), weight 4
