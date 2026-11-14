; module enums, cpu 6502

; data enums.names: 12 bytes
enums__names
    .byte $52, $47, $3F, $3F, $3F, $3F, $3F, $3F, $3F, $3F, $42, $43

; function enums.next
;   no slots
enums__next
    LDA #$0B
    STA enums__c
    STA enums__d
    LDA enums__b
    STA enums__c
    CLC
    ADC #$01
    STA enums__b
    LDX enums__c
    LDA enums__names,X
    STA enums__b
    LDA #$0A
    LDX enums__s
    STA enums__table,X
    RTS

; function enums.tests
;   no slots
enums__tests
    LDA enums__c
    CMP enums__d
    BEQ .L000C
    CMP #$01
    BEQ .L0012
.L000C
    LDA #$09
    CMP enums__c
    RTS
.L0012
    SEC
    RTS

; function enums.letter
;   no slots
enums__letter
    LDA enums__c
    BNE .L0008
    LDA #$52
    RTS
.L0008
    CMP #$01
    BEQ .L0010
    CMP #$0A
    BNE .L0013
.L0010
    LDA #$58
    RTS
.L0013
    LDA #$3F
    RTS

; variable enums.c: size 1, class 1 (either), weight 6

; variable enums.d: size 1, class 1 (either), weight 2

; variable enums.s: size 1, class 1 (either), weight 1

; variable enums.b: size 1, class 1 (either), weight 3

; variable enums.table: size 4, class 2 (not zp), weight 1
