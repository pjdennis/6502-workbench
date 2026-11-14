; module for_until, cpu 6502

; function for_until.f
;   slot 0 i: size 1, class 1 (either), local, weight 18
;   slot 1 $t1: size 1, class 1 (either), temp, weight 2
for_until__f
    LDA #$00
    STA for_until__f__i
.L0005
    LDA for_until__f__i
    CMP for_until__n
    BCS .L0022
    TAX
    LDA for_until__a,X
    CLC
    ADC for_until__total
    STA for_until__total
    BCC .L001D
    INC for_until__total+$01
.L001D
    INC for_until__f__i
    BNE .L0005
.L0022
    LDA #$02
    STA for_until__f__i
.L0027
    LDA for_until__f__i
    CMP #$0A
    BCS .L0045
    TAX
    LDA for_until__a,X
    BEQ .L0040
    LDA for_until__a,X
    CMP #$09
    BEQ .L0045
    LDA #$01
    STA for_until__a,X
.L0040
    INC for_until__f__i
    BNE .L0027
.L0045
    LDA for_until__n
    STA for_until__f__i
    CLC
    ADC #$03
    STA for_until__f__St1
.L0051
    LDA for_until__f__i
    CMP for_until__f__St1
    BCS .L0066
    INC for_until__total
    BNE .L0061
    INC for_until__total+$01
.L0061
    INC for_until__f__i
    BNE .L0051
.L0066
    RTS

; function for_until.g
;   no slots
for_until__g
    LDA #$00
    STA for_until__w
    STA for_until__w+$01
.L0008
    LDA for_until__w
    CMP for_until__total
    LDA for_until__w+$01
    SBC for_until__total+$01
    BCS .L0023
    INC for_until__n
    INC for_until__w
    BNE .L0008
    INC for_until__w+$01
    BNE .L0008
.L0023
    LDA #$FB
    STA for_until__k
    LDA #$FF
    STA for_until__k+$01
.L002D
    LDA for_until__k
    CMP #$05
    LDA for_until__k+$01
    SBC #$00
    BVC .L003B
    EOR #$80
.L003B
    BPL .L004B
    INC for_until__n
    INC for_until__k
    BNE .L002D
    INC for_until__k+$01
    JMP .L002D
.L004B
    LDA #$FD
    STA for_until__s
.L0050
    LDA for_until__s
    SEC
    SBC #$03
    BVC .L005A
    EOR #$80
.L005A
    BPL .L0065
    INC for_until__n
    INC for_until__s
    JMP .L0050
.L0065
    RTS

; variable for_until.n: size 1, class 1 (either), weight 14

; variable for_until.total: size 2, class 1 (either), weight 22

; variable for_until.a: size 10, class 2 (not zp), weight 16

; variable for_until.w: size 2, class 1 (either), weight 12

; variable for_until.k: size 2, class 1 (either), weight 12

; variable for_until.s: size 1, class 1 (either), weight 6
