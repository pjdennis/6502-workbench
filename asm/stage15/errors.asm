; Error handling and messages
;
; Requires:
;   TEMP                 - zero page location for temporary storage
;   TABPL;TABPH          - zero page locations for table pointer
;   CURLINEL;CURLINEH    - zero page locations for current line number
;   FS_PL;FS_PH          - zero page locations for file stack pointer
;   file_stack_empty     - function to check if file stack is empty
;   write_d              - function to write character to stderr
;   exit                 - function to exit program

  .include to_decimal.asm

; Error labels - each triggers BRK with inline error code and message
err_label_not_found
  BRK
  .data $01 "Label not found" $00

err_duplicate_label
  BRK
  .data $02 "Duplicate label" $00

err_opcode_not_found
  BRK
  .data $03 "Opcode not found" $00

err_branch_out_of_range
  BRK
  .data $05 "Branch out of range" $00

err_value_out_of_range
  BRK
  .data $06 "Value out of range" $00

err_invalid_hex
  BRK
  .data $07 "Invalid hex" $00

err_pc_value_expected
  BRK
  .data $08 "PC value expected" $00

err_closing_quote_not_found
  BRK
  .data $09 "Closing quote not found" $00

err_cannot_move_pc_backwards
  BRK
  .data $0A "Cannot move PC backwards" $00

err_unknown_directive
  BRK
  .data $0B "Unknown directive" $00

err_filename_expected
  BRK
  .data $0C "Filename expected" $00

err_too_many_forward_refs
  BRK
  .data $13 "Too many forward references" $00

err_usage
  BRK
  .data $0D "Usage <assembler> <input> <output> [debug]" $00

err_no_file
  BRK
  .data $0E "Attempt to read with no file open" $00

err_invalid_arg
  BRK
  .data $10 "Invalid argument" $00

err_no_global_for_local
  BRK
  .data $0F "No global label for local" $00

err_invalid_addressing_mode
  BRK
  .data $11 "Invalid addressing mode for instruction" $00

err_invalid_char_literal
  BRK
  .data $12 "Invalid character literal" $00

err_invalid_operand
  BRK
  .data $14 "Invalid operand" $00

err_unexpected_text
  BRK
  .data $15 "Unexpected text after operand" $00

err_fwdref_tracking
  BRK
  .data $16 "Internal error - reference tracking" $00

err_endif_without_ifdef
  BRK
  .data $17 ".endif without .ifdef" $00

err_unclosed_ifdef
  BRK
  .data $18 "Unclosed .ifdef" $00

err_too_many_ifdefs
  BRK
  .data $1A "Too many .ifdef directives" $00

err_conditional_nesting_too_deep
  BRK
  .data $1B "Conditional nesting exceeds 16 levels" $00

err_label_expected
  BRK
  .data $19 "Label expected" $00


; Interrupt handler - processes BRK for error display
interrupt
; Retrieve pointer to error code
  TSX
  INX
  INX
  SEC
  LDA $0100,X
  SBC #$01
  STA TABPL
  INX
  LDA $0100,X
  SBC #$00
  STA TABPH
; Retrieve error code and skip diagnostics if no error
  LDY #$00
  LDA (TABPL),Y
  BEQ .done
; Save error code
  STA TEMP
; Print the "Error " message
  LDA #<msg_error
  STA TABPL
  LDA #>msg_error
  STA TABPH
  JSR show_message
; Print the error code in decimal
  LDA TEMP
  STA TO_DECIMAL_VALUE_L
  LDA #$00
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
; Print the current file and line if any file is open
  JSR file_stack_empty
  BEQ .location_done
; Print the " in file " message
  LDA #<msg_error_file
  STA TABPL
  LDA #>msg_error_file
  STA TABPH
  JSR show_message
; Print the filename
  LDA FS_PL
  STA TABPL
  LDA FS_PH
  STA TABPH
  JSR show_message
; Print the " at line " message
  LDA #<msg_error_line
  STA TABPL
  LDA #>msg_error_line
  STA TABPH
  JSR show_message
; Print the current line in decimal
  LDA CURLINEL
  STA TO_DECIMAL_VALUE_L
  LDA CURLINEH
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
.location_done
; Print the ": " message
  LDA #':'
  JSR write_d
  LDA #' '
  JSR write_d
; Retrieve pointer to the error message and show it
  TSX
  LDA $0102,X
  STA TABPL
  LDA $0103,X
  STA TABPH
  JSR show_message
; Print the final newline
  LDA #'\n'
  JSR write_d
; Load the error code so that it is returned
  LDA TEMP
.done
  JMP exit

msg_error
  .data "Error " $00
msg_error_line
  .data " at line " $00
msg_error_file
  .data " in file " $00


; Show a decimal value to the error output
; On entry TO_DECIMAL_VALUE_L;TO_DECIMAL_VALUE_H contains the value to show
; On exit X, Y are preserved
;         A is not preserved
;         Decimal number string stored at TO_DECIMAL_RESULT
show_decimal
  JSR to_decimal
  LDA #<TO_DECIMAL_RESULT
  STA TABPL
  LDA #>TO_DECIMAL_RESULT
  STA TABPH
  JMP show_message ; tail call


; Show message to the error output
; On entry TABPL;TABPH points to the zero-terminated message
; On exit X is preserved
;         A, Y are not preserved
show_message
  LDY #$00
.loop
  LDA (TABPL),Y
  BEQ .done
  JSR write_d
  INY
  JMP .loop
.done
  RTS
