; module inline_results, cpu 6502

; function inline_results.conditions
;   slot 0 k: size 1, class 1 (either), param, weight 9
inline_results__conditions
    LDA inline_results__conditions__k
    CMP #$01
    BCC .L0010
    CMP #$80
    BCS .L0010
    LDA #$01
    STA inline_results__g
.L0010
    LDA inline_results__g
    CMP #$01
    BCC .L001F
    CMP #$80
    BCS .L001F
    LDA #$01
    BNE .L0021
.L001F
    LDA #$00
.L0021
    STA inline_results__ok
.L0024
    LDA inline_results__conditions__k
    CMP #$01
    BCC .L002F
    CMP #$80
    BCC .L0035
.L002F
    INC inline_results__conditions__k
    JMP .L0024
.L0035
    RTS

; function inline_results.several
;   slot 0 s: size 1, class 1 (either), param, weight 2
inline_results__several
    LDA inline_results__several__s
    BPL .L000A
    LDA #$FF
    JMP .L0015
.L000A
    CMP #$00
    BNE .L0013
    LDA #$00
    JMP .L0015
.L0013
    LDA #$01
.L0015
    STA inline_results__g
    LDA inline_results__several__s
    BPL .L0022
    LDA #$FF
    JMP .L002D
.L0022
    CMP #$00
    BNE .L002B
    LDA #$00
    JMP .L002D
.L002B
    LDA #$01
.L002D
    CMP #$01
    BNE .L0036
    LDA #$02
    STA inline_results__g
.L0036
    RTS

; function inline_results.pairs
;   slot 0 k: size 1, class 1 (either), param, weight 8
;   slot 1 $t1: size 1, class 1 (either), temp, weight 27
inline_results__pairs
    LDA #$00
    STA inline_results__pairs__St1
.L0005
    LDA inline_results__pairs__St1
    CMP #$08
    BCS .L0020
    TAX
    LDA inline_results__data,X
    CMP inline_results__pairs__k
    BNE .L001A
    SEC
    TXA
    JMP .L0023
.L001A
    INC inline_results__pairs__St1
    JMP .L0005
.L0020
    CLC
    LDA #$00
.L0023
    STA inline_results__g
    LDA #$00
    ROL
    STA inline_results__ok
    LDA #$00
    STA inline_results__pairs__St1
.L0031
    LDA inline_results__pairs__St1
    CMP #$08
    BCS .L004B
    TAX
    LDA inline_results__data,X
    CMP #$03
    BNE .L0045
    SEC
    TXA
    JMP .L004E
.L0045
    INC inline_results__pairs__St1
    JMP .L0031
.L004B
    CLC
    LDA #$00
.L004E
    STA inline_results__g
    BCC .L0056
    INC inline_results__g
.L0056
    LDA #$00
    STA inline_results__pairs__St1
.L005B
    LDA inline_results__pairs__St1
    CMP #$08
    BCS .L0074
    TAX
    LDA inline_results__data,X
    CMP inline_results__pairs__k
    BNE .L006E
    SEC
    TXA
    RTS
.L006E
    INC inline_results__pairs__St1
    JMP .L005B
.L0074
    CLC
    LDA #$00
    RTS

; function inline_results.words
;   slot 0 k: size 1, class 1 (either), param, weight 1
;   slot 1 $t1: size 2, class 1 (either), temp, weight 6
inline_results__words
    LDA inline_results__words__k
    STA inline_results__words__St1
    LDA #$00
    STA inline_results__words__St1+$01
    CLC
    LDA inline_results__words__St1
    ADC inline_results__words__St1
    TAY
    LDA inline_results__words__St1+$01
    ADC inline_results__words__St1+$01
    TAX
    TYA
    CLC
    ADC #$01
    STA inline_results__w
    TXA
    ADC #$00
    STA inline_results__w+$01
    RTS

; variable inline_results.g: size 1, class 1 (either), weight 7

; variable inline_results.w: size 2, class 1 (either), weight 2

; variable inline_results.ok: size 1, class 1 (either), weight 2

; variable inline_results.data: size 8, class 2 (not zp), weight 12
