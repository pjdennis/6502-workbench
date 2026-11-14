; module asm_user, cpu 6502
; imports: asm_lib

; function asm_user.main: exported
;   no slots
;   calls asm_lib.twice
asm_user__main
    LDA #$15
    JSR asm_lib__twice
    LDA #$04
    JSR asm_lib__twice
    RTS
