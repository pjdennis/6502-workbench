; module asm_lib, cpu 6502

; function asm_lib.twice: exported, registers
;   no slots
asm_lib__twice
    ASL
    RTS
