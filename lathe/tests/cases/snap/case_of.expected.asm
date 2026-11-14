; module case_of, cpu 6502

abs_d000 = $D000

; function case_of.kinds
;   no slots
case_of__kinds
    LDA case_of__k
    CMP #$01
    BNE .L000D
    LDA #$0A
    STA case_of__r
    RTS
.L000D
    CMP #$02
    BEQ .L0019
    CMP #$03
    BEQ .L0019
    CMP #$04
    BNE .L001F
.L0019
    LDA #$14
    STA case_of__r
    RTS
.L001F
    LDA #$1E
    STA case_of__r
    RTS

; function case_of.pick
;   no slots
case_of__pick
    LDA case_of__k
    BNE .L0008
    LDA #$07
    RTS
.L0008
    CMP #$61
    BEQ .L0010
    CMP #$62
    BNE .L0013
.L0010
    INC case_of__r
.L0013
    LDA #$00
    RTS

; function case_of.worked_out
;   slot 0 $t1: size 1, class 1 (either), temp, weight 1
case_of__worked_out
    LDA case_of__k
    AND #$07
    STA case_of__worked_out__St1
    BNE .L0010
    LDA #$01
    STA case_of__r
    RTS
.L0010
    CMP #$07
    BNE .L0019
    LDA #$02
    STA case_of__r
.L0019
    RTS

; function case_of.device
;   slot 0 $t1: size 1, class 1 (either), temp, weight 1
case_of__device
    LDA abs_d000
    STA case_of__device__St1
    CMP #$80
    BNE .L0010
    LDA #$01
    STA case_of__r
    RTS
.L0010
    CMP #$40
    BNE .L0019
    LDA #$02
    STA case_of__r
.L0019
    RTS

; function case_of.reload
;   no slots
case_of__reload
    LDA case_of__k
    CMP #$01
    BNE .L000D
    LDA #$05
    STA case_of__r
    RTS
.L000D
    CMP #$02
    BNE .L0015
    STA case_of__r
    RTS
.L0015
    CMP #$03
    BNE .L001F
    LDA #$00
    STA case_of__k
    RTS
.L001F
    CMP #$04
    BNE .L0028
    LDA #$01
    STA case_of__r
.L0028
    RTS

; function case_of.signs
;   no slots
case_of__signs
    LDA case_of__s
    CMP #$FF
    BNE .L000F
    LDA #$01
    STA case_of__r
    JMP .L001C
.L000F
    CMP #$80
    BEQ .L0017
    CMP #$7F
    BNE .L001C
.L0017
    LDA #$02
    STA case_of__r
.L001C
    LDA case_of__f
    CMP #$01
    BNE .L0029
    LDA #$03
    STA case_of__r
    RTS
.L0029
    LDA #$04
    STA case_of__r
    RTS

; function case_of.runs_on
;   no slots
case_of__runs_on
    LDA case_of__k
    CMP #$01
    BNE .L000C
    LDA #$05
    STA case_of__r
.L000C
    LDA case_of__k
    STA case_of__r
    RTS

; function case_of.empty
;   no slots
case_of__empty
    LDA case_of__k
    CMP #$01
    BEQ .L0010
    CMP #$02
    BEQ .L0010
    LDA #$01
    STA case_of__r
.L0010
    RTS

; function case_of.nested
;   no slots
case_of__nested
.L0000
    LDA case_of__k
    CMP #$01
    BNE .L001A
    LDA case_of__r
    CMP #$01
    BEQ .L0029
    CMP #$02
    BEQ .L0000
    LDA #$00
    STA case_of__k
    JMP .L0023
.L001A
    CMP #$02
    BNE .L0023
    LDA #$00
    STA case_of__r
.L0023
    INC case_of__k
    JMP .L0000
.L0029
    RTS

; variable case_of.k: size 1, class 1 (either), weight 20

; variable case_of.r: size 1, class 1 (either), weight 26

; variable case_of.s: size 1, class 1 (either), weight 1

; variable case_of.f: size 1, class 1 (either), weight 1
