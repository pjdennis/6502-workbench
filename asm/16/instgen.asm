; instgen19.asm - Instruction table generator for new conventional syntax
; Written in new syntax (assembled by asm18)
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
;   $FF = terminator (end of mode list)

; Addresses
TOKEN      = $1E00      ; Buffer for the current token being read
IHASHTAB   = $1F00      ; Instruction hash table
SCOPE_STACK = $0400     ; Scope stack (needed by hash_table21.asm, not used by instgen)
*          = $2000      ; Code generates here


  .zeropage

TEMP      .data $00     ; 1 byte temporary value
TEMP2     .data $00     ; 1 byte temporary value (for Y save)
HEX1      .data $00     ; 1 byte
HEX2      .data $00     ; 1 byte
MEMPL     .data $00     ; 2 byte heap pointer
MEMPH     .data $00     ; "
PL        .data $00     ; 2 byte pointer
PH        .data $00     ; "
P2L       .data $00     ; 2 byte pointer
P2H       .data $00     ; "
CURR_GLOBAL_HEAP_L .data $00 ; Required by hash_table (unused here)
CURR_GLOBAL_HEAP_H .data $00 ; "


  .code

; Include files
  .include environment.asm
  .include common.asm


; Instruction table with mode:opcode pairs
; Format: "MNEMONIC" $00 [mode opcode]... $FF
MNTAB
  ; Load/Store instructions
  .data "LDA" $00  <MODE_IMM  $A9  <MODE_ZP   $A5  <MODE_ZPX  $B5  <MODE_ABS  $AD
  .data            <MODE_ABSX $BD  <MODE_ABSY $B9  <MODE_INDX $A1  <MODE_INDY $B1
  .data            $FF
  .data "LDX" $00  <MODE_IMM  $A2  <MODE_ZP   $A6  <MODE_ZPY  $B6
  .data            <MODE_ABS  $AE  <MODE_ABSY $BE
  .data            $FF
  .data "LDY" $00  <MODE_IMM  $A0  <MODE_ZP   $A4  <MODE_ZPX  $B4
  .data            <MODE_ABS  $AC  <MODE_ABSX $BC
  .data            $FF
  .data "STA" $00  <MODE_ZP   $85  <MODE_ZPX  $95  <MODE_ABS  $8D  <MODE_ABSX $9D
  .data            <MODE_ABSY $99  <MODE_INDX $81  <MODE_INDY $91
  .data            $FF
  .data "STX" $00  <MODE_ZP   $86  <MODE_ZPY  $96  <MODE_ABS  $8E
  .data            $FF
  .data "STY" $00  <MODE_ZP   $84  <MODE_ZPX  $94  <MODE_ABS  $8C
  .data            $FF

  ; Arithmetic instructions
  .data "ADC" $00  <MODE_IMM  $69  <MODE_ZP   $65  <MODE_ZPX  $75  <MODE_ABS  $6D
  .data            <MODE_ABSX $7D  <MODE_ABSY $79  <MODE_INDX $61  <MODE_INDY $71
  .data            $FF
  .data "SBC" $00  <MODE_IMM  $E9  <MODE_ZP   $E5  <MODE_ZPX  $F5  <MODE_ABS  $ED
  .data            <MODE_ABSX $FD  <MODE_ABSY $F9  <MODE_INDX $E1  <MODE_INDY $F1
  .data            $FF

  ; Logical instructions
  .data "AND" $00  <MODE_IMM  $29  <MODE_ZP   $25  <MODE_ZPX  $35  <MODE_ABS  $2D
  .data            <MODE_ABSX $3D  <MODE_ABSY $39  <MODE_INDX $21  <MODE_INDY $31
  .data            $FF
  .data "ORA" $00  <MODE_IMM  $09  <MODE_ZP   $05  <MODE_ZPX  $15  <MODE_ABS  $0D
  .data            <MODE_ABSX $1D  <MODE_ABSY $19  <MODE_INDX $01  <MODE_INDY $11
  .data            $FF
  .data "EOR" $00  <MODE_IMM  $49  <MODE_ZP   $45  <MODE_ZPX  $55  <MODE_ABS  $4D
  .data            <MODE_ABSX $5D  <MODE_ABSY $59  <MODE_INDX $41  <MODE_INDY $51
  .data            $FF

  ; Compare instructions
  .data "CMP" $00  <MODE_IMM  $C9  <MODE_ZP   $C5  <MODE_ZPX  $D5  <MODE_ABS  $CD
  .data            <MODE_ABSX $DD  <MODE_ABSY $D9  <MODE_INDX $C1  <MODE_INDY $D1
  .data            $FF
  .data "CPX" $00  <MODE_IMM  $E0  <MODE_ZP   $E4  <MODE_ABS  $EC
  .data            $FF
  .data "CPY" $00  <MODE_IMM  $C0  <MODE_ZP   $C4  <MODE_ABS  $CC
  .data            $FF

  ; Bit test
  .data "BIT" $00  <MODE_ZP   $24  <MODE_ABS  $2C
  .data            $FF

  ; Increment/Decrement
  .data "INC" $00  <MODE_ZP   $E6  <MODE_ZPX  $F6  <MODE_ABS  $EE  <MODE_ABSX $FE
  .data            $FF
  .data "DEC" $00  <MODE_ZP   $C6  <MODE_ZPX  $D6  <MODE_ABS  $CE  <MODE_ABSX $DE
  .data            $FF
  .data "INX" $00  <MODE_NONE $E8
  .data            $FF
  .data "INY" $00  <MODE_NONE $C8
  .data            $FF
  .data "DEX" $00  <MODE_NONE $CA
  .data            $FF
  .data "DEY" $00  <MODE_NONE $88
  .data            $FF

  ; Shift/Rotate
  .data "ASL" $00  <MODE_NONE $0A  <MODE_ZP   $06  <MODE_ZPX  $16
  .data            <MODE_ABS  $0E  <MODE_ABSX $1E
  .data            $FF
  .data "LSR" $00  <MODE_NONE $4A  <MODE_ZP   $46  <MODE_ZPX  $56
  .data            <MODE_ABS  $4E  <MODE_ABSX $5E
  .data            $FF
  .data "ROL" $00  <MODE_NONE $2A  <MODE_ZP   $26  <MODE_ZPX  $36
  .data            <MODE_ABS  $2E  <MODE_ABSX $3E
  .data            $FF
  .data "ROR" $00  <MODE_NONE $6A  <MODE_ZP   $66  <MODE_ZPX  $76
  .data            <MODE_ABS  $6E  <MODE_ABSX $7E
  .data            $FF

  ; Branch instructions
  .data "BCC" $00  <MODE_REL  $90
  .data            $FF
  .data "BCS" $00  <MODE_REL  $B0
  .data            $FF
  .data "BEQ" $00  <MODE_REL  $F0
  .data            $FF
  .data "BMI" $00  <MODE_REL  $30
  .data            $FF
  .data "BNE" $00  <MODE_REL  $D0
  .data            $FF
  .data "BPL" $00  <MODE_REL  $10
  .data            $FF
  .data "BVC" $00  <MODE_REL  $50
  .data            $FF
  .data "BVS" $00  <MODE_REL  $70
  .data            $FF

  ; Jump instructions
  .data "JMP" $00  <MODE_ABS  $4C  <MODE_IND  $6C
  .data            $FF
  .data "JSR" $00  <MODE_ABS  $20
  .data            $FF

  ; Stack instructions
  .data "PHA" $00  <MODE_NONE $48
  .data            $FF
  .data "PHP" $00  <MODE_NONE $08
  .data            $FF
  .data "PLA" $00  <MODE_NONE $68
  .data            $FF
  .data "PLP" $00  <MODE_NONE $28
  .data            $FF

  ; Transfer instructions
  .data "TAX" $00  <MODE_NONE $AA
  .data            $FF
  .data "TAY" $00  <MODE_NONE $A8
  .data            $FF
  .data "TSX" $00  <MODE_NONE $BA
  .data            $FF
  .data "TXA" $00  <MODE_NONE $8A
  .data            $FF
  .data "TXS" $00  <MODE_NONE $9A
  .data            $FF
  .data "TYA" $00  <MODE_NONE $98
  .data            $FF

  ; Flag instructions
  .data "CLC" $00  <MODE_NONE $18
  .data            $FF
  .data "CLD" $00  <MODE_NONE $D8
  .data            $FF
  .data "CLI" $00  <MODE_NONE $58
  .data            $FF
  .data "CLV" $00  <MODE_NONE $B8
  .data            $FF
  .data "SEC" $00  <MODE_NONE $38
  .data            $FF
  .data "SED" $00  <MODE_NONE $F8
  .data            $FF
  .data "SEI" $00  <MODE_NONE $78
  .data            $FF

  ; Other
  .data "BRK" $00  <MODE_NONE $00
  .data            $FF
  .data "NOP" $00  <MODE_NONE $EA
  .data            $FF
  .data "RTI" $00  <MODE_NONE $40
  .data            $FF
  .data "RTS" $00  <MODE_NONE $60
  .data            $FF

  ; End of table
  .data $00


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
  LDY #$01
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
  LSR
  LSR
  LSR
  LSR
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
  .data $00              ; Success


msg_data
  .data ".data" $00

msg_instprefix
  .data "." $00

msg_IHASHTAB
  .data "IHASHTAB" $00

msg_hash_table_comment
  .data "; Instructions hash table (pointers)" $00

msg_heap_comment
  .data "; Instructions heap data" $00


HEAP                  ; Heap goes after the program code


  .data start ; Emulation environment jumps to address in last 2 bytes
