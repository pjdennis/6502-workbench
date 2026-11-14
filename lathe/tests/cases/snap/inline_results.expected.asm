; module inline_results, cpu 6502

; function inline_results.conditions
;   slot 0 k: size 1, class 1 (either), param, weight 9
inline_results__conditions
    STA inline_results__conditions__k
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
    STA inline_results__several__s
    CMP #$00
    BPL .L000C
    LDA #$FF
    JMP .L0017
.L000C
    CMP #$00
    BNE .L0015
    LDA #$00
    JMP .L0017
.L0015
    LDA #$01
.L0017
    STA inline_results__g
    LDA inline_results__several__s
    BPL .L0024
    LDA #$FF
    JMP .L002F
.L0024
    CMP #$00
    BNE .L002D
    LDA #$00
    JMP .L002F
.L002D
    LDA #$01
.L002F
    CMP #$01
    BNE .L0038
    LDA #$02
    STA inline_results__g
.L0038
    RTS

; function inline_results.pairs
;   slot 0 k: size 1, class 1 (either), param, weight 9
;   slot 1 $t1: size 1, class 1 (either), temp, weight 27
inline_results__pairs
    STA inline_results__pairs__k
    LDA #$00
    STA inline_results__pairs__St1
.L0008
    LDA inline_results__pairs__St1
    CMP #$08
    BCS .L0023
    TAX
    LDA inline_results__data,X
    CMP inline_results__pairs__k
    BNE .L001D
    SEC
    TXA
    JMP .L0026
.L001D
    INC inline_results__pairs__St1
    JMP .L0008
.L0023
    CLC
    LDA #$00
.L0026
    STA inline_results__g
    LDA #$00
    ROL
    STA inline_results__ok
    LDA #$00
    STA inline_results__pairs__St1
.L0034
    LDA inline_results__pairs__St1
    CMP #$08
    BCS .L004E
    TAX
    LDA inline_results__data,X
    CMP #$03
    BNE .L0048
    SEC
    TXA
    JMP .L0051
.L0048
    INC inline_results__pairs__St1
    JMP .L0034
.L004E
    CLC
    LDA #$00
.L0051
    STA inline_results__g
    BCC .L0059
    INC inline_results__g
.L0059
    LDA #$00
    STA inline_results__pairs__St1
.L005E
    LDA inline_results__pairs__St1
    CMP #$08
    BCS .L0077
    TAX
    LDA inline_results__data,X
    CMP inline_results__pairs__k
    BNE .L0071
    SEC
    TXA
    RTS
.L0071
    INC inline_results__pairs__St1
    JMP .L005E
.L0077
    CLC
    LDA #$00
    RTS

; function inline_results.words
;   slot 0 k: size 1, class 1 (either), param, weight 1
;   slot 1 $t1: size 2, class 1 (either), temp, weight 6
inline_results__words
    STA inline_results__words__k
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
