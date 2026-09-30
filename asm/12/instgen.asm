; instgen17.asm - Instruction table generator for new conventional syntax
;
; New table format: each instruction has mode:opcode pairs
;   [mnemonic string] $00 [mode1 opcode1] [mode2 opcode2] ... $FF
;
; Mode encoding:
;   MODE_NONE = $00  ; Implied (no operand)
;   MODE_ACC  = $01  ; Accumulator
;   MODE_IMM  = $02  ; Immediate
;   MODE_ZP   = $03  ; Zero page
;   MODE_ZPX  = $04  ; Zero page, X
;   MODE_ZPY  = $05  ; Zero page, Y
;   MODE_ABS  = $06  ; Absolute
;   MODE_ABSX = $07  ; Absolute, X
;   MODE_ABSY = $08  ; Absolute, Y
;   MODE_INDX = $09  ; Indirect, X - ($zp,X)
;   MODE_INDY = $0A  ; Indirect, Y - ($zp),Y
;   MODE_REL  = $0B  ; Relative (branches)
;   MODE_IND  = $0C  ; Indirect - JMP ($xxxx)
;   MODE_DATA = $FE  ; Pseudo-instruction (DATA)
;   $FF = terminator (end of mode list)

; Addresses
TOKEN      = $1E00      ; Buffer for the current token being read
IHASHTAB   = $1F00      ; Instruction hash table
*          = $2000      ; Code generates here


  .zeropage

TEMP      DATA $00     ; 1 byte temporary value
TEMP2     DATA $00     ; 1 byte temporary value (for Y save)
HEX1      DATA $00     ; 1 byte
HEX2      DATA $00     ; 1 byte
MEMPL     DATA $00     ; 2 byte heap pointer
MEMPH     DATA $00     ; "
PL        DATA $00     ; 2 byte pointer
PH        DATA $00     ; "
P2L       DATA $00     ; 2 byte pointer
P2H       DATA $00     ; "
CURR_GLOBAL_HEAP_L DATA $00 ; Required by hash_table17.asm (unused here)
CURR_GLOBAL_HEAP_H DATA $00 ; "


  .code

; Include files
  .include environment.asm
  .include common.asm


; Mode constants (for documentation)
MODE_NONE = $00
MODE_ACC  = $01
MODE_IMM  = $02
MODE_ZP   = $03
MODE_ZPX  = $04
MODE_ZPY  = $05
MODE_ABS  = $06
MODE_ABSX = $07
MODE_ABSY = $08
MODE_INDX = $09
MODE_INDY = $0A
MODE_REL  = $0B
MODE_IND  = $0C
MODE_DATA = $FE


; Instruction table with mode:opcode pairs
; Format: "MNEMONIC" $00 [mode opcode]... $FF
MNTAB
  ; Load/Store instructions
  DATA "LDA" $00 $02 $A9 $03 $A5 $04 $B5 $06 $AD $07 $BD $08 $B9 $09 $A1 $0A $B1 $FF
  DATA "LDX" $00 $02 $A2 $03 $A6 $05 $B6 $06 $AE $08 $BE $FF
  DATA "LDY" $00 $02 $A0 $03 $A4 $04 $B4 $06 $AC $07 $BC $FF
  DATA "STA" $00 $03 $85 $04 $95 $06 $8D $07 $9D $08 $99 $09 $81 $0A $91 $FF
  DATA "STX" $00 $03 $86 $05 $96 $06 $8E $FF
  DATA "STY" $00 $03 $84 $04 $94 $06 $8C $FF

  ; Arithmetic instructions
  DATA "ADC" $00 $02 $69 $03 $65 $04 $75 $06 $6D $07 $7D $08 $79 $09 $61 $0A $71 $FF
  DATA "SBC" $00 $02 $E9 $03 $E5 $04 $F5 $06 $ED $07 $FD $08 $F9 $09 $E1 $0A $F1 $FF

  ; Logical instructions
  DATA "AND" $00 $02 $29 $03 $25 $04 $35 $06 $2D $07 $3D $08 $39 $09 $21 $0A $31 $FF
  DATA "ORA" $00 $02 $09 $03 $05 $04 $15 $06 $0D $07 $1D $08 $19 $09 $01 $0A $11 $FF
  DATA "EOR" $00 $02 $49 $03 $45 $04 $55 $06 $4D $07 $5D $08 $59 $09 $41 $0A $51 $FF

  ; Compare instructions
  DATA "CMP" $00 $02 $C9 $03 $C5 $04 $D5 $06 $CD $07 $DD $08 $D9 $09 $C1 $0A $D1 $FF
  DATA "CPX" $00 $02 $E0 $03 $E4 $06 $EC $FF
  DATA "CPY" $00 $02 $C0 $03 $C4 $06 $CC $FF

  ; Bit test
  DATA "BIT" $00 $03 $24 $06 $2C $FF

  ; Increment/Decrement
  DATA "INC" $00 $03 $E6 $04 $F6 $06 $EE $07 $FE $FF
  DATA "DEC" $00 $03 $C6 $04 $D6 $06 $CE $07 $DE $FF
  DATA "INX" $00 $00 $E8 $FF
  DATA "INY" $00 $00 $C8 $FF
  DATA "DEX" $00 $00 $CA $FF
  DATA "DEY" $00 $00 $88 $FF

  ; Shift/Rotate
  DATA "ASL" $00 $01 $0A $03 $06 $04 $16 $06 $0E $07 $1E $FF
  DATA "LSR" $00 $01 $4A $03 $46 $04 $56 $06 $4E $07 $5E $FF
  DATA "ROL" $00 $01 $2A $03 $26 $04 $36 $06 $2E $07 $3E $FF
  DATA "ROR" $00 $01 $6A $03 $66 $04 $76 $06 $6E $07 $7E $FF

  ; Branch instructions
  DATA "BCC" $00 $0B $90 $FF
  DATA "BCS" $00 $0B $B0 $FF
  DATA "BEQ" $00 $0B $F0 $FF
  DATA "BMI" $00 $0B $30 $FF
  DATA "BNE" $00 $0B $D0 $FF
  DATA "BPL" $00 $0B $10 $FF
  DATA "BVC" $00 $0B $50 $FF
  DATA "BVS" $00 $0B $70 $FF

  ; Jump instructions
  DATA "JMP" $00 $06 $4C $0C $6C $FF
  DATA "JSR" $00 $06 $20 $FF

  ; Stack instructions
  DATA "PHA" $00 $00 $48 $FF
  DATA "PHP" $00 $00 $08 $FF
  DATA "PLA" $00 $00 $68 $FF
  DATA "PLP" $00 $00 $28 $FF

  ; Transfer instructions
  DATA "TAX" $00 $00 $AA $FF
  DATA "TAY" $00 $00 $A8 $FF
  DATA "TSX" $00 $00 $BA $FF
  DATA "TXA" $00 $00 $8A $FF
  DATA "TXS" $00 $00 $9A $FF
  DATA "TYA" $00 $00 $98 $FF

  ; Flag instructions
  DATA "CLC" $00 $00 $18 $FF
  DATA "CLD" $00 $00 $D8 $FF
  DATA "CLI" $00 $00 $58 $FF
  DATA "CLV" $00 $00 $B8 $FF
  DATA "SEC" $00 $00 $38 $FF
  DATA "SED" $00 $00 $F8 $FF
  DATA "SEI" $00 $00 $78 $FF

  ; Other
  DATA "BRK" $00 $00 $00 $FF
  DATA "NOP" $00 $00 $EA $FF
  DATA "RTI" $00 $00 $40 $FF
  DATA "RTS" $00 $00 $60 $FF

  ; Pseudo-instruction (DATA directive)
  ; Mode $FE is a special marker for pseudo-instructions (DATA)
  ; ($FF is reserved as the mode list terminator)
  DATA "DATA" $00 $FE $00 $FF

  ; End of table
  DATA $00


populate_instruction_hash_table
  LDA #<MNTAB
  STA P2L
  LDA #>MNTAB
  STA P2H
.entry_loop
  LDY #$00
  LDA (P2L),Y
  BEQ .done
  ; Copy mnemonic to TOKEN
.token_loop
  STA TOKEN,Y
  BEQ .token_loop_done
  INY
  LDA (P2L),Y
  JMP .token_loop
.token_loop_done
  ; Y now points at null terminator
  ; Save Y for later (start of mode data is at Y+1)
  INY
  STY TEMP        ; Save offset to mode data
  ; Add entry to hash table (this copies the mnemonic to heap)
  JSR hash_add
  ; Now copy all mode:opcode pairs to the heap
  LDY TEMP        ; Restore offset to mode data
.copy_modes
  LDA (P2L),Y     ; Get mode byte
  CMP #$FF
  BEQ .copy_done
  ; Store mode byte
  JSR store_byte_to_heap
  INY
  ; Store opcode byte
  LDA (P2L),Y
  JSR store_byte_to_heap
  INY
  JMP .copy_modes
.copy_done
  ; Store the $FF terminator
  LDA #$FF
  JSR store_byte_to_heap
  INY              ; Skip past $FF in source
  ; Advance P2L:P2H to next entry
  TYA
  CLC
  ADC P2L
  STA P2L
  LDA #$00
  ADC P2H
  STA P2H
  JMP .entry_loop
.done
  RTS


; Store byte A to heap and advance heap pointer
; On entry: A = byte to store
; On exit: Y is preserved, A is not preserved
store_byte_to_heap
  STY TEMP2       ; Save Y
  LDY #$00
  STA (MEMPL),Y   ; Store byte at (MEMPL)
  INY
  JSR advance_heap ; Advance heap by 1
  LDY TEMP2       ; Restore Y
  RTS


display_hex_char
  CMP #$0A
  BCS .low
  ; Carry already clear
  ADC #'0'
  JMP write_b          ; Tail call
.low
  ; C already set
  SBC #$0A ; Subtract 10
  CLC
  ADC #'A'
  JMP write_b ; Tail call


display_hex
  PHA
  LSR A
  LSR A
  LSR A
  LSR A
  JSR display_hex_char
  PLA
  AND #$0F
  JMP display_hex_char ; Tail call


display_byte
  PHA
  LDA #'$'
  JSR write_b
  PLA
  JMP display_hex


display_newline
  LDA #'\n'
  JMP write_b


display_data_prefix
  LDA #' '
  JSR write_b
  JSR write_b
  LDA #<msg_data
  STA PL
  LDA #>msg_data
  STA PH
  JMP display_text


; On entry PL;PH points to the text
; On exit Y points to the terminating 0
display_text
  LDY #$00
.loop
  LDA (PL),Y
  BEQ .done
  JSR write_b
  INY
  JMP .loop
.done
  RTS


display_table
  LDA #$00
  STA HASH
.loop
  ; Display line start
  JSR display_data_prefix
  ; Display line
  LDA #$00
  STA TEMP
.lineloop
  LDA #' '
  JSR write_b
  JSR hash_entry_empty
  BNE .not_empty
  ; empty
  LDA #'$'
  JSR write_b
  LDA #$00
  JSR display_hex
  LDA #$00
  JSR display_hex
  JMP .next
.not_empty
  ; Display instruction label prefix
  LDA #<msg_instprefix
  STA PL
  LDA #>msg_instprefix
  STA PH
  JSR display_text
  ; Display hash entry
  JSR load_hash_entry
  CLC
  LDA TABPL
  ADC #$02
  STA PL
  LDA TABPH
  ADC #$00
  STA PH
  JSR display_text
.next
  LDA HASH
  CLC
  ADC #$02
  STA HASH
  LDA TEMP
  CLC
  ADC #$01
  STA TEMP
  CMP #$08
  BEQ .next1
  JMP .lineloop
.next1
  JSR display_newline
  LDA HASH
  BEQ .done
  JMP .loop
.done
  RTS


write_label_and_modes
  ; Display the mnemonic string
  LDA #' '
  JSR write_b
  LDA #'"'
  JSR write_b
  ; Set PL:PH to point to mnemonic (TABPL+2)
  CLC
  LDA TABPL
  ADC #$02
  STA PL
  LDA TABPH
  ADC #$00
  STA PH
  ; Display mnemonic text
  JSR display_text
  ; Y now points to null terminator in mnemonic
  LDA #'"'
  JSR write_b
  LDA #' '
  JSR write_b
  LDA #$00
  JSR display_byte
  ; Now display mode:opcode pairs
  ; Y still valid from display_text, pointing at null
  INY                  ; Skip past null terminator to first mode byte
.mode_loop
  LDA (PL),Y
  CMP #$FF
  BEQ .mode_done
  PHA                  ; Save mode byte
  LDA #' '
  JSR write_b
  PLA                  ; Restore mode byte
  JSR display_byte
  INY
  LDA #' '
  JSR write_b
  LDA (PL),Y           ; Opcode byte
  JSR display_byte
  INY
  JMP .mode_loop
.mode_done
  LDA #' '
  JSR write_b
  LDA #'$'
  JSR write_b
  LDA #'F'
  JSR write_b
  JSR write_b
  JSR display_newline
  RTS


display_data
  LDA #$00
  STA HASH
.loop
  JSR hash_entry_empty
  BNE .not_empty
  JMP .next
.not_empty
  ; Load pointer to hash entry
  JSR load_hash_entry
.entry_loop
  ; Display instruction label prefix
  LDA #<msg_instprefix
  STA PL
  LDA #>msg_instprefix
  STA PH
  JSR display_text
  CLC
  LDA TABPL
  ADC #$02
  STA PL
  LDA TABPH
  ADC #$00
  STA PH
  JSR display_text
  JSR display_newline
  JSR display_data_prefix
  LDA #' '
  JSR write_b
  ; Display next pointer
  LDY #$00
  LDA (TABPL),Y
  BNE .not_zero
  INY
  LDA (TABPL),Y
  BNE .not_zero
  ; Zero - no collision chain
  LDA #'$'
  JSR write_b
  LDA #'0'
  JSR write_b
  JSR write_b
  JSR write_b
  JSR write_b
  JSR write_label_and_modes
  JMP .next
.not_zero
  ; Has collision chain - display pointer to next entry
  LDA #<msg_instprefix
  STA PL
  LDA #>msg_instprefix
  STA PH
  JSR display_text
  CLC
  LDY #$00
  LDA (TABPL),Y
  ADC #$02
  STA PL
  INY
  LDA (TABPL),Y
  ADC #$00
  STA PH
  JSR display_text
  JSR write_label_and_modes
  LDY #$00
  LDA (TABPL),Y
  STA PL
  INY
  LDA (TABPL),Y
  STA PH
  LDA PL
  STA TABPL
  LDA PH
  STA TABPH
  JMP .entry_loop
.next
  LDA HASH
  CLC
  ADC #$02
  STA HASH
  BEQ .done
  JMP .loop
.done
  RTS


; Entry point
start
; Initialization
  LDA #$00
  STA IS_LOCAL_LABEL    ; Clear flag before using hash table
  JSR init_heap
  JSR select_instruction_hash_table
  JSR init_hash_table
  JSR populate_instruction_hash_table

; Show the instructions hash table
  LDA #<msg_hash_table_comment
  STA PL
  LDA #>msg_hash_table_comment
  STA PH
  JSR display_text
  JSR display_newline
  LDA #<msg_IHASHTAB
  STA PL
  LDA #>msg_IHASHTAB
  STA PH
  JSR display_text
  JSR display_newline
  JSR display_table
  JSR display_newline

; Show the instructions heap data
  LDA #<msg_heap_comment
  STA PL
  LDA #>msg_heap_comment
  STA PH
  JSR display_text
  JSR display_newline
  JSR display_data

  BRK
  DATA $00              ; Success


msg_data
  DATA "DATA" $00

msg_instprefix
  DATA "." $00

msg_IHASHTAB
  DATA "IHASHTAB" $00

msg_hash_table_comment
  DATA "; Instructions hash table (pointers)" $00

msg_heap_comment
  DATA "; Instructions heap data" $00


HEAP                  ; Heap goes after the program code


  DATA start ; Emulation environment jumps to address in last 2 bytes
