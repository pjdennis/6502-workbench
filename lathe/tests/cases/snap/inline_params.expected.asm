; module inline_params, cpu 6502

abs_d000 = $D000

; function inline_params.tick
;   no slots
inline_params__tick
    INC inline_params__h
    RTS

; function inline_params.cases
;   slot 0 k: size 1, class 1 (either), param, weight 3
;   slot 1 local: size 1, class 1 (either), local, weight 2
;   slot 2 $t1: size 1, class 1 (either), temp, weight 24
;   slot 3 $t2: size 1, class 1 (either), temp, weight 12
;   calls inline_params.tick
inline_params__cases
    LDA #$01
    STA inline_params__cases__local
    LDA inline_params__cases__k
    STA inline_params__cases__St1
    LDA #$00
    STA inline_params__cases__St2
.L0010
    LDA inline_params__cases__St1
    CMP #$01
    BCC .L0020
    DEC inline_params__cases__St1
    INC inline_params__cases__St2
    JMP .L0010
.L0020
    LDA inline_params__cases__St2
    STA inline_params__g
    LDA #$05
    STA inline_params__cases__St1
    LDA #$00
    STA inline_params__cases__St2
.L0030
    LDA inline_params__cases__St1
    CMP #$01
    BCC .L0040
    DEC inline_params__cases__St1
    INC inline_params__cases__St2
    JMP .L0030
.L0040
    LDA inline_params__cases__St2
    STA inline_params__g
    LDA inline_params__cases__local
    LDX inline_params__cases__k
    STA inline_params__t,X
    LDA inline_params__h
    LDX inline_params__g
    STA inline_params__t,X
    LDA abs_d000
    STA inline_params__cases__St1
    STA inline_params__t+$01
    STX inline_params__cases__St1
    STX inline_params__g
    STX inline_params__h
    STX inline_params__cases__St1
    STX inline_params__g
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
    CLC
    LDA inline_params__later__k
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
