; module asm_arrays, cpu 6502

; data asm_arrays.digits: 16 bytes
asm_arrays__digits
    .byte $30, $31, $32, $33, $34, $35, $36, $37, $38, $39, $41, $42, $43, $44, $45, $46

; function asm_arrays.copy_digits
;   slot 0 local: size 4, class 2 (not zp), local, weight 2
asm_arrays__copy_digits
    LDX #$07
.L0002
    LDA asm_arrays__digits,X
    STA asm_arrays__buffer,X
    DEX
    BPL .L0002
    LDA asm_arrays__digits+$0F
    STA asm_arrays__words+$04
    STA asm_arrays__copy_digits__local+$03
    LDA asm_arrays__copy_digits__local+$03
    RTS

; variable asm_arrays.buffer: size 8, class 2 (not zp), weight 1

; variable asm_arrays.words: size 8, class 2 (not zp), weight 1
