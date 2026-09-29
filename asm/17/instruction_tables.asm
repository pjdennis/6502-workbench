; Instruction table with mode:opcode pairs
; Format: .asciiz "MNEMONIC", [mode, opcode]..., MODE_END
MNTAB:
  ; Load/Store instructions
  .asciiz "LDA", MODE_IMM, $A9, MODE_ZP, $A5, MODE_ZPX, $B5, MODE_ABS, $AD
  .byte MODE_ABSX, $BD, MODE_ABSY, $B9, MODE_INDX, $A1, MODE_INDY, $B1
  .byte MODE_END

  .asciiz "LDX", MODE_IMM, $A2, MODE_ZP, $A6, MODE_ZPY, $B6
  .byte MODE_ABS, $AE, MODE_ABSY, $BE
  .byte MODE_END

  .asciiz "LDY", MODE_IMM, $A0, MODE_ZP, $A4, MODE_ZPX, $B4
  .byte MODE_ABS, $AC, MODE_ABSX, $BC
  .byte MODE_END

  .asciiz "STA", MODE_ZP, $85, MODE_ZPX, $95, MODE_ABS, $8D, MODE_ABSX, $9D
  .byte MODE_ABSY, $99, MODE_INDX, $81, MODE_INDY, $91
  .byte MODE_END

  .asciiz "STX", MODE_ZP, $86, MODE_ZPY, $96, MODE_ABS, $8E, MODE_END

  .asciiz "STY", MODE_ZP, $84, MODE_ZPX, $94, MODE_ABS, $8C, MODE_END

  ; Arithmetic instructions
  .asciiz "ADC", MODE_IMM, $69, MODE_ZP, $65, MODE_ZPX, $75, MODE_ABS, $6D
  .byte MODE_ABSX, $7D, MODE_ABSY, $79, MODE_INDX, $61, MODE_INDY, $71
  .byte MODE_END

  .asciiz "SBC", MODE_IMM, $E9, MODE_ZP, $E5, MODE_ZPX, $F5, MODE_ABS, $ED
  .byte MODE_ABSX, $FD, MODE_ABSY, $F9, MODE_INDX, $E1, MODE_INDY, $F1
  .byte MODE_END

  ; Logical instructions
  .asciiz "AND", MODE_IMM, $29, MODE_ZP, $25, MODE_ZPX, $35, MODE_ABS, $2D
  .byte MODE_ABSX, $3D, MODE_ABSY, $39, MODE_INDX, $21, MODE_INDY, $31
  .byte MODE_END

  .asciiz "ORA", MODE_IMM, $09, MODE_ZP, $05, MODE_ZPX, $15, MODE_ABS, $0D
  .byte MODE_ABSX, $1D, MODE_ABSY, $19, MODE_INDX, $01, MODE_INDY, $11
  .byte MODE_END

  .asciiz "EOR", MODE_IMM, $49, MODE_ZP, $45, MODE_ZPX, $55, MODE_ABS, $4D
  .byte MODE_ABSX, $5D, MODE_ABSY, $59, MODE_INDX, $41, MODE_INDY, $51
  .byte MODE_END

  ; Compare instructions
  .asciiz "CMP", MODE_IMM, $C9, MODE_ZP, $C5, MODE_ZPX, $D5, MODE_ABS, $CD
  .byte MODE_ABSX, $DD, MODE_ABSY, $D9, MODE_INDX, $C1, MODE_INDY, $D1
  .byte MODE_END

  .asciiz "CPX", MODE_IMM, $E0, MODE_ZP, $E4, MODE_ABS, $EC, MODE_END

  .asciiz "CPY", MODE_IMM, $C0, MODE_ZP, $C4, MODE_ABS, $CC, MODE_END

  ; Bit test
  .asciiz "BIT", MODE_ZP, $24, MODE_ABS, $2C, MODE_END

  ; Increment/Decrement
  .asciiz "INC", MODE_ZP, $E6, MODE_ZPX, $F6, MODE_ABS, $EE, MODE_ABSX, $FE, MODE_END
  .asciiz "DEC", MODE_ZP, $C6, MODE_ZPX, $D6, MODE_ABS, $CE, MODE_ABSX, $DE, MODE_END
  .asciiz "INX", MODE_NONE, $E8, MODE_END
  .asciiz "INY", MODE_NONE, $C8, MODE_END
  .asciiz "DEX", MODE_NONE, $CA, MODE_END
  .asciiz "DEY", MODE_NONE, $88, MODE_END

  ; Shift/Rotate
  .asciiz "ASL", MODE_NONE, $0A, MODE_ZP, $06, MODE_ZPX, $16, MODE_ABS, $0E
  .byte MODE_ABSX, $1E
  .byte MODE_END

  .asciiz "LSR", MODE_NONE, $4A, MODE_ZP, $46, MODE_ZPX, $56, MODE_ABS, $4E
  .byte MODE_ABSX, $5E
  .byte MODE_END

  .asciiz "ROL", MODE_NONE, $2A, MODE_ZP, $26, MODE_ZPX, $36, MODE_ABS, $2E
  .byte MODE_ABSX, $3E
  .byte MODE_END

  .asciiz "ROR", MODE_NONE, $6A, MODE_ZP, $66, MODE_ZPX, $76, MODE_ABS, $6E
  .byte MODE_ABSX, $7E
  .byte MODE_END

  ; Branch instructions
  .asciiz "BCC", MODE_REL, $90, MODE_END
  .asciiz "BCS", MODE_REL, $B0, MODE_END
  .asciiz "BEQ", MODE_REL, $F0, MODE_END
  .asciiz "BMI", MODE_REL, $30, MODE_END
  .asciiz "BNE", MODE_REL, $D0, MODE_END
  .asciiz "BPL", MODE_REL, $10, MODE_END
  .asciiz "BVC", MODE_REL, $50, MODE_END
  .asciiz "BVS", MODE_REL, $70, MODE_END

  ; Jump instructions
  .asciiz "JMP", MODE_ABS, $4C, MODE_IND, $6C, MODE_END
  .asciiz "JSR", MODE_ABS, $20, MODE_END

  ; Stack instructions
  .asciiz "PHA", MODE_NONE, $48, MODE_END
  .asciiz "PHP", MODE_NONE, $08, MODE_END
  .asciiz "PLA", MODE_NONE, $68, MODE_END
  .asciiz "PLP", MODE_NONE, $28, MODE_END

  ; Transfer instructions
  .asciiz "TAX", MODE_NONE, $AA, MODE_END
  .asciiz "TAY", MODE_NONE, $A8, MODE_END
  .asciiz "TSX", MODE_NONE, $BA, MODE_END
  .asciiz "TXA", MODE_NONE, $8A, MODE_END
  .asciiz "TXS", MODE_NONE, $9A, MODE_END
  .asciiz "TYA", MODE_NONE, $98, MODE_END

  ; Flag instructions
  .asciiz "CLC", MODE_NONE, $18, MODE_END
  .asciiz "CLD", MODE_NONE, $D8, MODE_END
  .asciiz "CLI", MODE_NONE, $58, MODE_END
  .asciiz "CLV", MODE_NONE, $B8, MODE_END
  .asciiz "SEC", MODE_NONE, $38, MODE_END
  .asciiz "SED", MODE_NONE, $F8, MODE_END
  .asciiz "SEI", MODE_NONE, $78, MODE_END

  ; Other
  .asciiz "BRK", MODE_NONE, $00, MODE_END
  .asciiz "NOP", MODE_NONE, $EA, MODE_END
  .asciiz "RTI", MODE_NONE, $40, MODE_END
  .asciiz "RTS", MODE_NONE, $60, MODE_END

  ; End of table
  .byte 0


; Directive table - just directive names
; Handler label is computed as "dir_" + name
; Format: "directive" $00 ... $00 (end of table)
DIRTAB:
  .asciiz "include"
  .asciiz "zeropage"
  .asciiz "code"
  .asciiz "byte"
  .asciiz "word"
  .asciiz "asciiz"
  .asciiz "reserve"
  .asciiz "ifdef"
  .asciiz "ifndef"
  .asciiz "else"
  .asciiz "endif"
  .asciiz "macro"
  .asciiz "endmacro"
  .byte 0 ; End of table
