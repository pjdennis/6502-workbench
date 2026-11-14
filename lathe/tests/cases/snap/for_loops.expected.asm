; module for_loops, cpu 6502

; function for_loops.constant_bounds
;   no slots
for_loops__constant_bounds
    LDA #$01
    STA for_loops__i
.L0005
    CLC
    LDA for_loops__r
    ADC for_loops__i
    STA for_loops__r
    LDA for_loops__i
    CMP #$0A
    BEQ .L001B
    INC for_loops__i
    BNE .L0005
.L001B
    RTS

; function for_loops.to_the_top
;   no slots
for_loops__to_the_top
    LDA #$00
    STA for_loops__i
.L0005
    INC for_loops__r
    LDA for_loops__i
    CMP #$FF
    BEQ .L0014
    INC for_loops__i
    BNE .L0005
.L0014
    RTS

; function for_loops.to_a_variable
;   no slots
for_loops__to_a_variable
    LDA #$00
    STA for_loops__i
.L0005
    CLC
    LDA for_loops__r
    ADC for_loops__i
    STA for_loops__r
    LDA for_loops__i
    CMP for_loops__n
    BEQ .L001C
    INC for_loops__i
    BNE .L0005
.L001C
    RTS

; function for_loops.from_a_variable
;   no slots
for_loops__from_a_variable
    LDA for_loops__n
    STA for_loops__i
    CMP #$C9
    BCS .L0020
.L000A
    CLC
    LDA for_loops__r
    ADC for_loops__i
    STA for_loops__r
    LDA for_loops__i
    CMP #$C8
    BEQ .L0020
    INC for_loops__i
    BNE .L000A
.L0020
    RTS

; function for_loops.to_an_expression
;   slot 0 $t1: size 1, class 1 (either), temp, weight 5
for_loops__to_an_expression
    LDA for_loops__r
    STA for_loops__i
    SEC
    LDA for_loops__n
    SBC #$01
    STA for_loops__to_an_expression__St1
    CMP for_loops__i
    BCC .L0024
.L0014
    INC for_loops__r
    LDA for_loops__i
    CMP for_loops__to_an_expression__St1
    BEQ .L0024
    INC for_loops__i
    BNE .L0014
.L0024
    RTS

; function for_loops.down_to_zero
;   no slots
for_loops__down_to_zero
    LDA for_loops__n
    STA for_loops__i
.L0006
    CLC
    LDA for_loops__r
    ADC for_loops__i
    STA for_loops__r
    LDA for_loops__i
    BEQ .L001B
    DEC for_loops__i
    JMP .L0006
.L001B
    RTS

; function for_loops.down_to_one
;   no slots
for_loops__down_to_one
    LDA for_loops__n
    STA for_loops__i
    CMP #$01
    BCC .L0020
.L000A
    CLC
    LDA for_loops__r
    ADC for_loops__i
    STA for_loops__r
    LDA for_loops__i
    CMP #$01
    BEQ .L0020
    DEC for_loops__i
    BNE .L000A
.L0020
    RTS

; function for_loops.signed_byte
;   no slots
for_loops__signed_byte
    LDA #$FB
    STA for_loops__s
.L0005
    INC for_loops__r
    LDA for_loops__s
    CMP #$05
    BEQ .L0015
    INC for_loops__s
    JMP .L0005
.L0015
    LDA #$0A
    STA for_loops__s
.L001A
    DEC for_loops__r
    LDA for_loops__s
    CMP #$F6
    BEQ .L002A
    DEC for_loops__s
    JMP .L001A
.L002A
    RTS

; function for_loops.words
;   slot 0 $t1: size 2, class 1 (either), temp, weight 12
for_loops__words
    LDA #$00
    STA for_loops__w
    STA for_loops__w+$01
.L0008
    INC for_loops__r
    LDA for_loops__w
    CMP #$E8
    BNE .L0019
    LDA for_loops__w+$01
    CMP #$03
    BEQ .L0023
.L0019
    INC for_loops__w
    BNE .L0008
    INC for_loops__w+$01
    BNE .L0008
.L0023
    LDA for_loops__v
    STA for_loops__w
    LDX for_loops__v+$01
    STX for_loops__w+$01
    CMP #$01
    TXA
    SBC #$00
    BCC .L0053
.L0036
    INC for_loops__r
    LDA for_loops__w
    CMP #$01
    BNE .L0045
    LDA for_loops__w+$01
    BEQ .L0053
.L0045
    LDA for_loops__w
    BNE .L004D
    DEC for_loops__w+$01
.L004D
    DEC for_loops__w
    JMP .L0036
.L0053
    LDA #$01
    STA for_loops__w
    LDA #$00
    STA for_loops__w+$01
    CLC
    LDA for_loops__v
    ADC #$0A
    STA for_loops__words__St1
    LDA for_loops__v+$01
    ADC #$00
    STA for_loops__words__St1+$01
    LDA for_loops__words__St1
    CMP #$01
    LDA for_loops__words__St1+$01
    SBC #$00
    BCC .L0097
.L007A
    INC for_loops__r
    LDA for_loops__w
    CMP for_loops__words__St1
    BNE .L008D
    LDA for_loops__w+$01
    CMP for_loops__words__St1+$01
    BEQ .L0097
.L008D
    INC for_loops__w
    BNE .L007A
    INC for_loops__w+$01
    BNE .L007A
.L0097
    RTS

; function for_loops.word_with_a_byte_limit
;   no slots
for_loops__word_with_a_byte_limit
    LDA #$2C
    STA for_loops__w
    LDA #$01
    STA for_loops__w+$01
    LDA for_loops__n
    CMP #$2D
    LDA #$00
    SBC #$01
    BCS .L0033
.L0015
    INC for_loops__r
    LDA for_loops__w
    CMP for_loops__n
    BNE .L0025
    LDA for_loops__w+$01
    BEQ .L0033
.L0025
    LDA for_loops__w
    BNE .L002D
    DEC for_loops__w+$01
.L002D
    DEC for_loops__w
    JMP .L0015
.L0033
    RTS

; function for_loops.ints
;   no slots
for_loops__ints
    LDA #$9C
    STA for_loops__k
    LDA #$FF
    STA for_loops__k+$01
.L000A
    INC for_loops__r
    LDA for_loops__k
    CMP #$64
    BNE .L0019
    LDA for_loops__k+$01
    BEQ .L0024
.L0019
    INC for_loops__k
    BNE .L000A
    INC for_loops__k+$01
    JMP .L000A
.L0024
    RTS

; function for_loops.leaving
;   no slots
for_loops__leaving
    LDA #$00
    STA for_loops__i
.L0005
    LDA for_loops__i
    CMP #$07
    BEQ .L0014
    LDA for_loops__r
    BEQ .L0021
    DEC for_loops__r
.L0014
    LDA for_loops__i
    CMP for_loops__n
    BEQ .L0021
    INC for_loops__i
    BNE .L0005
.L0021
    RTS

; function for_loops.nested
;   slot 0 top: size 1, class 1 (either), param, weight 25
;   slot 1 j: size 1, class 1 (either), local, weight 56
for_loops__nested
    STA for_loops__nested__top
    LDA #$00
    STA for_loops__i
.L0008
    LDA for_loops__i
    STA for_loops__nested__j
    LDA for_loops__nested__top
    CMP for_loops__nested__j
    BCC .L002D
.L0016
    CLC
    LDA for_loops__r
    ADC for_loops__nested__j
    STA for_loops__r
    LDA for_loops__nested__j
    CMP for_loops__nested__top
    BEQ .L002D
    INC for_loops__nested__j
    BNE .L0016
.L002D
    LDA for_loops__i
    CMP for_loops__nested__top
    BEQ .L003A
    INC for_loops__i
    BNE .L0008
.L003A
    RTS

; function for_loops.empty
;   no slots
for_loops__empty
    LDA #$05
    STA for_loops__i
    RTS
.L0006
    INC for_loops__r
    LDA for_loops__i
    CMP #$04
    BEQ .L0015
    INC for_loops__i
    BNE .L0006
.L0015
    RTS

; variable for_loops.i: size 1, class 1 (either), weight 119

; variable for_loops.n: size 1, class 1 (either), weight 17

; variable for_loops.r: size 1, class 1 (either), weight 121

; variable for_loops.s: size 1, class 1 (either), weight 18

; variable for_loops.w: size 2, class 1 (either), weight 80

; variable for_loops.v: size 2, class 1 (either), weight 4

; variable for_loops.k: size 2, class 1 (either), weight 18
