; module regmem, cpu 6502
; imports: host

abs_f009 = $F009

; function regmem.constants
;   no slots
regmem__constants
    LDA #$00
    STA regmem__a
    STA regmem__b
    STA regmem__w
    STA regmem__w+$01
    LDA #$01
    STA regmem__c
    STA regmem__v
    STA regmem__v+$01
    RTS

; function regmem.copies
;   no slots
regmem__copies
    LDA regmem__b
    STA regmem__a
    STA regmem__c
    STA regmem__c
    CLC
    ADC #$01
    STA regmem__b
    STA regmem__c
    RTS

; function regmem.stores
;   no slots
regmem__stores
    LDA regmem__b
    STA regmem__a
    LDA #$05
    STA regmem__b
    STA regmem__c
    LDA regmem__a
    STA regmem__c
    RTS

; function regmem.changed
;   no slots
regmem__changed
    LDA regmem__b
    STA regmem__a
    INC regmem__b
    LDA regmem__b
    STA regmem__c
    BNE .L0016
    LDA #$01
    STA regmem__c
.L0016
    RTS

; function regmem.flags
;   no slots
regmem__flags
    LDA regmem__b
    AND #$07
    STA regmem__a
    BNE .L000F
    LDA #$01
    STA regmem__c
.L000F
    LDA regmem__a
    BEQ .L0019
    LDA #$02
    STA regmem__c
.L0019
    RTS

; function regmem.no_flags
;   no slots
regmem__no_flags
    LDA regmem__b
    STA regmem__a
    LDA regmem__c
    CMP #$03
    BNE .L0012
    LDA #$00
    STA regmem__c
.L0012
    LDA regmem__a
    BNE .L001C
    LDA #$01
    STA regmem__c
.L001C
    RTS

; function regmem.transfers
;   no slots
regmem__transfers
    LDA #$00
    STA regmem__a
    TAX
    RTS

; function regmem.forgotten
;   no slots
regmem__forgotten
    LDA regmem__b
    STA regmem__a
    JSR abs_f009
    LDA regmem__b
    STA regmem__c
    LDA regmem__a
    CMP #$01
    BNE .L001B
    LDA #$02
    STA regmem__c
.L001B
    LDA regmem__b
    STA regmem__c
    RTS

; function regmem.kept
;   no slots
regmem__kept
    LDA regmem__b
    STA regmem__a
    STA regmem__c
    STA regmem__c
    RTS

; variable regmem.a: size 1, class 1 (either), weight 13

; variable regmem.b: size 1, class 1 (either), weight 14

; variable regmem.c: size 1, class 1 (either), weight 18

; variable regmem.w: size 2, class 1 (either), weight 2

; variable regmem.v: size 2, class 1 (either), weight 2
