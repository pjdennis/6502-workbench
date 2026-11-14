; module asm_block, cpu 6502
; imports: host

abs_0300 = $0300
abs_1234 = $1234
abs_d020 = $D020
abs_f009 = $F009
zp_12 = $12
zp_fe = $FE

; function asm_block.helper
;   no slots
asm_block__helper
    RTS

; function asm_block.main: exported
;   no slots
;   calls asm_block.helper
asm_block__main
    LDA #$41
    JSR abs_f009
    LDA #$41
.L0007
    LDX #$10
    STX abs_d020
    STA zp_12,X
    LDA (zp_fe),Y
    DEX
    BNE .L0007
    JSR asm_block__helper
    LDA #<asm_block__helper+$01
    LDY #>asm_block__helper
    JSR abs_f009
    LDA #$01
    BNE .L0024
    JMP .L00A5
.L0024
    JMP .L00A6
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    NOP
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
    LDA abs_1234
.L00A5
    NOP
.L00A6
    LDA #$41
    JSR abs_f009
.L00AB
    INC abs_0300
    BCS .L00AB
    RTS
