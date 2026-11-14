; module results, cpu 6502

; function results.byte_value
;   no slots
results__byte_value
    LDA results__a
    RTS

; function results.word_value
;   no slots
results__word_value
    LDX results__w+$01
    LDA results__w
    RTS

; function results.widened
;   no slots
results__widened
    LDX #$00
    LDA results__a
    RTS

; function results.constant
;   no slots
results__constant
    LDX #$03
    LDA #$E8
    RTS

; function results.at_least
;   no slots
results__at_least
    LDA results__a
    CMP results__b
    RTS

; function results.less
;   no slots
results__less
    LDA results__b
    CLC
    SBC results__a
    RTS

; function results.less_than_ten
;   no slots
results__less_than_ten
    LDA #$09
    CMP results__a
    RTS

; function results.equal
;   no slots
results__equal
    LDA results__a
    CMP results__b
    BEQ .L0009
    CLC
.L0009
    RTS

; function results.in_range
;   no slots
results__in_range
    LDA results__a
    CMP #$30
    BCC .L000E
    LDA #$39
    CMP results__a
    BCS .L000F
.L000E
    CLC
.L000F
    RTS

; function results.flag
;   no slots
results__flag
    LDA results__ok
    LSR
    RTS

; function results.yes
;   no slots
results__yes
    SEC
    RTS

; function results.next
;   no slots
results__next
    LDA results__a
    BNE .L0009
    CLC
    LDA #$00
    RTS
.L0009
    DEC results__a
    SEC
    LDA results__a
    RTS

; function results.checked
;   slot 0 $t1: size 1, class 1 (either), temp, weight 2
results__checked
    CLC
    LDA results__a
    ADC #$01
    STA results__checked__St1
    LDA results__b
    CLC
    SBC results__a
    LDA results__checked__St1
    RTS

; function results.word_and_status
;   no slots
results__word_and_status
    LDA results__ok
    LSR
    LDX results__w+$01
    LDA results__w
    RTS

; function results.passed
;   no slots
;   calls results.next
results__passed
    JMP results__next

; function results.passed_value
;   no slots
;   calls results.byte_value
results__passed_value
    JMP results__byte_value

; function results.callers
;   no slots
;   calls results.next
;   calls results.at_least
;   calls results.less
results__callers
    JSR results__next
    STA results__r
    LDA #$00
    ROL
    STA results__ok
    JSR results__next
    STA results__r
    BCC .L0017
    STA results__b
.L0017
    JSR results__next
    STA results__r
    BCC .L002C
    CLC
    LDA results__b
    ADC results__r
    STA results__b
    JMP .L0017
.L002C
    JSR results__at_least
    BCC .L0036
    LDA #$01
    STA results__r
.L0036
    JSR results__less
    LDA #$00
    ROL
    STA results__ok
    JMP results__next

; variable results.a: size 1, class 1 (either), weight 13

; variable results.b: size 1, class 1 (either), weight 13

; variable results.w: size 2, class 1 (either), weight 4

; variable results.ok: size 1, class 1 (either), weight 4

; variable results.r: size 1, class 1 (either), weight 11
