; module inline_params, cpu 6502

abs_d000 = $D000

; function inline_params.tick
;   no slots
inline_params__tick
    INC inline_params__h
    RTS

; function inline_params.cases
;   slot 0 k: size 1, class 1 (either), param, weight 4
;   slot 1 local: size 1, class 1 (either), local, weight 2
;   slot 2 $t1: size 1, class 1 (either), temp, weight 24
;   slot 3 $t2: size 1, class 1 (either), temp, weight 12
;   calls inline_params.tick
inline_params__cases
    STA inline_params__cases__k
    LDA #$01
    STA inline_params__cases__local
    LDA inline_params__cases__k
    STA inline_params__cases__St1
    LDA #$00
    STA inline_params__cases__St2
.L0013
    LDA inline_params__cases__St1
    CMP #$01
    BCC .L0023
    DEC inline_params__cases__St1
    INC inline_params__cases__St2
    JMP .L0013
.L0023
    LDA inline_params__cases__St2
    STA inline_params__g
    LDA #$05
    STA inline_params__cases__St1
    LDA #$00
    STA inline_params__cases__St2
.L0033
    LDA inline_params__cases__St1
    CMP #$01
    BCC .L0043
    DEC inline_params__cases__St1
    INC inline_params__cases__St2
    JMP .L0033
.L0043
    LDA inline_params__cases__St2
    STA inline_params__g
    LDA inline_params__cases__local
    LDY inline_params__cases__k
    STA inline_params__t,Y
    LDA inline_params__h
    LDY inline_params__g
    STA inline_params__t,Y
    LDA abs_d000
    STA inline_params__cases__St1
    STA inline_params__t+$01
    STY inline_params__cases__St1
    STY inline_params__g
    STY inline_params__h
    STY inline_params__cases__St1
    STY inline_params__g
    LDA inline_params__cases__St1
    STA inline_params__h
    JSR inline_params__tick
    LDA inline_params__cases__k
    STA inline_params__h
    LDA inline_params__g
    STA inline_params__cases__St1
    JSR inline_params__tick
    LDA inline_params__cases__St1
    STA inline_params__h
    RTS

; function inline_params.later
;   slot 0 k: size 1, class 1 (either), param, weight 4
;   slot 1 $t1: size 1, class 1 (either), temp, weight 24
;   slot 2 $t2: size 1, class 1 (either), temp, weight 12
inline_params__later
    STA inline_params__later__k
    CLC
    ADC #$01
    STA inline_params__later__St1
    CLC
    LDA inline_params__h
    ADC inline_params__later__St1
    STA inline_params__g
    LDA inline_params__later__k
    STA inline_params__later__St1
    LDA #$00
    STA inline_params__later__St2
.L001E
    LDA inline_params__later__St1
    CMP #$01
    BCC .L002E
    DEC inline_params__later__St1
    INC inline_params__later__St2
    JMP .L001E
.L002E
    LDA inline_params__later__St2
    STA inline_params__later__St1
    CLC
    LDA inline_params__h
    ADC inline_params__later__St1
    STA inline_params__g
    LDA inline_params__later__k
    STA inline_params__later__St1
    LDA #$00
    STA inline_params__later__St2
.L0049
    LDA inline_params__later__St1
    CMP #$01
    BCC .L0059
    DEC inline_params__later__St1
    INC inline_params__later__St2
    JMP .L0049
.L0059
    LDA inline_params__later__St2
    STA inline_params__later__St1
    CLC
    LDA inline_params__later__k
    ADC inline_params__later__St1
    STA inline_params__g
    RTS

; variable inline_params.g: size 1, class 1 (either), weight 9

; variable inline_params.h: size 1, class 1 (either), weight 8

; variable inline_params.t: size 8, class 2 (not zp), weight 3
