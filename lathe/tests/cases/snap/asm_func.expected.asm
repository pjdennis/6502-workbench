; module asm_func, cpu 6502
; imports: host

abs_f009 = $F009

; function asm_func.swap_nibbles: registers
;   no slots
asm_func__swap_nibbles
    ASL
    ADC #$80
    ROL
    ASL
    ADC #$80
    ROL
    RTS

; function asm_func.plot: exported, registers
;   no slots
asm_func__plot
    JMP abs_f009

; function asm_func.ends_with_rts: registers
;   no slots
asm_func__ends_with_rts
    RTS

; function asm_func.pair: registers
;   no slots
asm_func__pair
    BCC .L0003
    TXA
.L0003
    RTS

; function asm_func.calls_another: registers
;   no slots
;   calls asm_func.swap_nibbles
;   calls asm_func.pair
asm_func__calls_another
    LDA #$21
    JSR asm_func__swap_nibbles
    JMP asm_func__pair

; function asm_func.main: exported
;   no slots
;   calls asm_func.swap_nibbles
;   calls asm_func.plot
;   calls asm_func.pair
;   calls asm_func.ends_with_rts
;   calls asm_func.calls_another
asm_func__main
    LDA #$12
    JSR asm_func__swap_nibbles
    LDY #$02
    LDX #$01
    LDA #$78
    JSR asm_func__plot
    SEC
    LDX #$12
    LDA #$34
    JSR asm_func__pair
    JSR asm_func__ends_with_rts
    JMP asm_func__calls_another
