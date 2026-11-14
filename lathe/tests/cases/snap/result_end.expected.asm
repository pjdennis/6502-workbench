; module result_end, cpu 6502

; function result_end.both
;   slot 0 a: size 1, class 1 (either), param, weight 1
result_end__both
    STA result_end__both__a
    CMP #$04
    BCC .L000A
    LDA #$01
    RTS
.L000A
    LDA #$02
    RTS

; function result_end.chain
;   slot 0 a: size 1, class 1 (either), param, weight 1
result_end__chain
    STA result_end__chain__a
    CMP #$00
    BNE .L000A
    LDA #$01
    RTS
.L000A
    CMP #$01
    BNE .L0011
    LDA #$02
    RTS
.L0011
    LDA #$03
    RTS

; function result_end.cases
;   slot 0 a: size 1, class 1 (either), param, weight 1
result_end__cases
    STA result_end__cases__a
    CMP #$01
    BNE .L000A
    LDA #$0A
    RTS
.L000A
    LDA #$14
    RTS

; function result_end.forever
;   no slots
result_end__forever
.L0000
    INC result_end__n
    LDA result_end__n
    CMP #$0A
    BNE .L000B
    RTS
.L000B
    JMP .L0000

; function result_end.by_hand
;   slot 0 a: size 1, class 1 (either), param, weight 2
result_end__by_hand
    STA result_end__by_hand__a
    LDA result_end__by_hand__a
    ASL
    RTS

; function result_end.status
;   no slots
result_end__status
    LDA result_end__n
    CMP #$03
    RTS

; variable result_end.n: size 1, class 1 (either), weight 9
