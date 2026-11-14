; module asm_vars_zp, cpu 6502

; function asm_vars_zp.first: registers
;   no slots
asm_vars_zp__first
    LDY #$00
    LDA (asm_vars_zp__table),Y
    STA asm_vars_zp__low
    RTS

; function asm_vars_zp.walk
;   slot 0 count: size 1, class 1 (either), param, weight 1
;   slot 1 cursor: size 2, class 0 (zp), local, weight 6
;   calls asm_vars_zp.first
asm_vars_zp__walk
    LDA asm_vars_zp__table
    STA asm_vars_zp__walk__cursor
    LDA asm_vars_zp__table+$01
    STA asm_vars_zp__walk__cursor+$01
    LDA asm_vars_zp__walk__count
    STA asm_vars_zp__low
    LDX #$00
    STY asm_vars_zp__walk__cursor,X
    CLC
    LDA asm_vars_zp__walk__cursor
    ADC asm_vars_zp__low
    STA asm_vars_zp__walk__cursor
    BCC .L0020
    INC asm_vars_zp__walk__cursor+$01
.L0020
    JSR asm_vars_zp__first
    STA asm_vars_zp__low
    RTS

; function asm_vars_zp.main: exported
;   no slots
;   calls asm_vars_zp.walk
asm_vars_zp__main
    LDA #$02
    STA asm_vars_zp__walk__count
    JSR asm_vars_zp__walk
    INC asm_vars_zp__low
    RTS

; variable asm_vars_zp.low: size 1, class 1 (either), weight 5

; variable asm_vars_zp.table: size 2, class 0 (zp), weight 3
