; module byte_arith, cpu 6502

; function byte_arith.direct
;   no slots
byte_arith__direct
    CLC
    LDA byte_arith__a
    ADC byte_arith__b
    STA byte_arith__r
    SEC
    LDA byte_arith__a
    SBC byte_arith__b
    STA byte_arith__r
    LDA byte_arith__a
    AND byte_arith__b
    STA byte_arith__r
    LDA byte_arith__a
    ORA byte_arith__b
    STA byte_arith__r
    LDA byte_arith__a
    EOR byte_arith__b
    STA byte_arith__r
    CLC
    LDA byte_arith__a
    ADC #$05
    STA byte_arith__r
    SEC
    LDA #$05
    SBC byte_arith__a
    STA byte_arith__r
    RTS

; function byte_arith.chain
;   no slots
byte_arith__chain
    CLC
    LDA byte_arith__a
    ADC byte_arith__b
    SEC
    SBC byte_arith__c
    STA byte_arith__r
    LDA byte_arith__a
    AND #$0F
    ORA #$30
    STA byte_arith__r
    RTS

; function byte_arith.right_computed
;   no slots
byte_arith__right_computed
    LDA byte_arith__b
    AND byte_arith__c
    CLC
    ADC byte_arith__a
    STA byte_arith__r
    CLC
    LDA byte_arith__b
    ADC byte_arith__c
    AND byte_arith__a
    STA byte_arith__r
    RTS

; function byte_arith.right_computed_minus
;   no slots
byte_arith__right_computed_minus
    LDA byte_arith__b
    AND byte_arith__c
    EOR #$FF
    SEC
    ADC byte_arith__a
    STA byte_arith__r
    CLC
    LDA byte_arith__b
    ADC byte_arith__c
    EOR #$FF
    SEC
    ADC #$05
    STA byte_arith__r
    RTS

; function byte_arith.both_computed
;   slot 0 $t1: size 1, class 1 (either), temp, weight 4
byte_arith__both_computed
    CLC
    LDA byte_arith__a
    ADC byte_arith__b
    STA byte_arith__both_computed__St1
    SEC
    LDA byte_arith__b
    SBC byte_arith__c
    AND byte_arith__both_computed__St1
    STA byte_arith__r
    CLC
    LDA byte_arith__a
    ADC byte_arith__b
    STA byte_arith__both_computed__St1
    LDA byte_arith__b
    AND byte_arith__c
    EOR #$FF
    SEC
    ADC byte_arith__both_computed__St1
    STA byte_arith__r
    RTS

; function byte_arith.nothing
;   no slots
byte_arith__nothing
    LDA byte_arith__a
    STA byte_arith__r
    STA byte_arith__r
    STA byte_arith__r
    STA byte_arith__r
    LDA #$00
    STA byte_arith__r
    LDA byte_arith__a
    STA byte_arith__r
    RTS

; function byte_arith.unary
;   no slots
byte_arith__unary
    SEC
    LDA #$00
    SBC byte_arith__a
    STA byte_arith__r
    LDA byte_arith__a
    EOR #$FF
    STA byte_arith__r
    CLC
    LDA byte_arith__a
    ADC byte_arith__b
    EOR #$FF
    SEC
    ADC #$00
    STA byte_arith__r
    CLC
    LDA byte_arith__a
    ADC byte_arith__b
    EOR #$FF
    STA byte_arith__r
    RTS

; function byte_arith.powers
;   no slots
byte_arith__powers
    LDA byte_arith__a
    ASL
    ASL
    STA byte_arith__r
    LDA byte_arith__a
    ASL
    ASL
    ASL
    STA byte_arith__r
    LDA byte_arith__a
    LSR
    STA byte_arith__r
    LDA byte_arith__a
    AND #$0F
    STA byte_arith__r
    RTS

; variable byte_arith.a: size 1, class 1 (either), weight 24

; variable byte_arith.b: size 1, class 1 (either), weight 16

; variable byte_arith.c: size 1, class 1 (either), weight 7

; variable byte_arith.r: size 1, class 1 (either), weight 29
