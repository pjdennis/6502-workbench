; module convert, cpu 6502

; function convert.word_result
;   no slots
convert__word_result
    LDX convert__w+$01
    LDA convert__w
    RTS

; function convert.narrowing
;   no slots
;   calls convert.word_result
convert__narrowing
    LDA convert__w
    STA convert__b
    STA convert__b
    LDA convert__w+$01
    STA convert__b
    LDA convert__i
    STA convert__b
    LDA convert__w
    STA convert__s
    JSR convert__word_result
    STA convert__b
    JSR convert__word_result
    TXA
    STA convert__b
    RTS

; function convert.i_as_word
;   no slots
convert__i_as_word
    LDX convert__i+$01
    LDA convert__i
    RTS

; function convert.narrowed_operations
;   slot 0 $t1: size 2, class 1 (either), temp, weight 3
;   calls convert.i_as_word
convert__narrowed_operations
    CLC
    LDA convert__w
    ADC #$01
    STA convert__b
    JSR convert__i_as_word
    STA convert__narrowed_operations__St1
    STX convert__narrowed_operations__St1+$01
    SEC
    LDA convert__w
    SBC convert__narrowed_operations__St1
    STA convert__b
    LDA convert__w
    AND #$F0
    STA convert__b
    RTS

; function convert.widening
;   no slots
convert__widening
    LDA convert__b
    STA convert__w
    LDA #$00
    STA convert__w+$01
    LDA convert__b
    STA convert__w
    LDA #$00
    STA convert__w+$01
    LDA convert__b
    STA convert__i
    LDA #$00
    STA convert__i+$01
    CLC
    LDA convert__b
    ADC convert__c
    STA convert__w
    LDA #$00
    STA convert__w+$01
    CLC
    LDA convert__b
    ADC convert__c
    STA convert__w
    LDA #$00
    ADC #$00
    STA convert__w+$01
    RTS

; function convert.sign_extension
;   no slots
convert__sign_extension
    LDX #$00
    LDA convert__s
    BPL .L0008
    DEX
.L0008
    STA convert__i
    STX convert__i+$01
    LDX #$00
    LDA convert__s
    BPL .L0016
    DEX
.L0016
    CLC
    ADC #$01
    STA convert__i
    TXA
    ADC #$00
    STA convert__i+$01
    LDX #$00
    LDA convert__s
    BPL .L002A
    DEX
.L002A
    STA convert__w
    STX convert__w+$01
    RTS

; function convert.reinterpreting
;   no slots
convert__reinterpreting
    LDA convert__b
    STA convert__s
    STA convert__b
    LDA convert__w
    STA convert__i
    LDA convert__w+$01
    STA convert__i+$01
    LDA convert__i
    STA convert__w
    LDA convert__i+$01
    STA convert__w+$01
    RTS

; function convert.bools
;   no slots
convert__bools
    LDA convert__f
    STA convert__b
    CMP convert__c
    LDA #$00
    ROL
    EOR #$01
    STA convert__b
    LDA convert__f
    STA convert__w
    LDA #$00
    STA convert__w+$01
    LDA convert__b
    BEQ .L0025
    LDA #$01
    BNE .L0027
.L0025
    LDA #$00
.L0027
    STA convert__f
    LDA convert__w
    ORA convert__w+$01
    BEQ .L0036
    LDA #$01
    BNE .L0038
.L0036
    LDA #$00
.L0038
    STA convert__f
    LDA convert__b
    AND #$01
    BEQ .L0047
    LDA #$00
    STA convert__c
.L0047
    RTS

; function convert.mixing
;   no slots
convert__mixing
    CLC
    LDA convert__i
    ADC convert__b
    STA convert__i
    BCC .L000F
    INC convert__i+$01
.L000F
    CLC
    LDA convert__w
    ADC convert__i
    STA convert__w
    LDA convert__w+$01
    ADC convert__i+$01
    STA convert__w+$01
    LDA convert__w
    CMP convert__i
    LDA convert__w+$01
    SBC convert__i+$01
    BVC .L0032
    EOR #$80
.L0032
    BPL .L0039
    LDA #$00
    STA convert__b
.L0039
    LDA convert__s
    SEC
    SBC convert__b
    BVC .L0044
    EOR #$80
.L0044
    BPL .L004B
    LDA #$01
    STA convert__b
.L004B
    RTS

; variable convert.b: size 1, class 1 (either), weight 24

; variable convert.c: size 1, class 1 (either), weight 4

; variable convert.s: size 1, class 1 (either), weight 6

; variable convert.w: size 2, class 1 (either), weight 32

; variable convert.i: size 2, class 1 (either), weight 20

; variable convert.f: size 1, class 1 (either), weight 4
