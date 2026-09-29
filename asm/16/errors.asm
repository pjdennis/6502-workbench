; Error handling and messages
;
; Requires:
;   TEMP                 - zero page location for temporary storage
;   TABP16               - zero page location for table pointer
;   CURR_LINE16          - zero page location for current line number
;   FS_P16               - zero page locations for file stack pointer
;   FS_SRC_TYPE          - zero page location for source type (0=file, 1=memory)
;   file_stack_empty     - function to check if file stack is empty
;   pop_file_stack       - function to pop file stack entry
;   write_d              - function to write character to stderr
;   exit                 - function to exit program

  .include to_decimal.asm

; ============================================================================
; ERROR HANDLERS - Grouped by category with sequential error codes
; ============================================================================

; --- Label errors ($01-$04) ---
err_label_not_found:
  BRK
  .data $01 "Label not found" $00

err_duplicate_label:
  BRK
  .data $02 "Duplicate label" $00

err_no_global_for_local:
  BRK
  .data $03 "No global label for local" $00

err_label_expected:
  BRK
  .data $04 "Label expected" $00

; --- Symbol/Opcode errors ($05) ---
err_opcode_not_found:
  BRK
  .data $05 "Opcode not found" $00

; --- Value/Expression errors ($06-$0C) ---
err_value_out_of_range:
  BRK
  .data $06 "Value out of range" $00

err_invalid_hex:
  BRK
  .data $07 "Invalid hex" $00

err_branch_out_of_range:
  BRK
  .data $08 "Branch out of range" $00

err_invalid_operand:
  BRK
  .data $09 "Invalid operand" $00

err_unexpected_text:
  BRK
  .data $0A "Unexpected text after operand" $00

err_expected_shift:
  BRK
  .data $0B "Expected << or >>" $00

err_invalid_char_literal:
  BRK
  .data $0C "Invalid character literal" $00

err_invalid_addressing_mode:
  BRK
  .data $0D "Invalid addressing mode" $00

; --- Directive errors ($0E-$12) ---
err_unknown_directive:
  BRK
  .data $0E "Unknown directive" $00

err_pc_value_expected:
  BRK
  .data $0F "PC value expected" $00

err_cannot_move_pc_backwards:
  BRK
  .data $10 "Cannot move PC backwards" $00

err_filename_expected:
  BRK
  .data $11 "Filename expected" $00

err_closing_quote_not_found:
  BRK
  .data $12 "Closing quote not found" $00

; --- Conditional assembly errors ($13-$15) ---
err_endif_without_ifdef:
  BRK
  .data $13 ".endif without .ifdef" $00

err_unclosed_ifdef:
  BRK
  .data $14 "Unclosed .ifdef" $00

err_too_many_ifdefs:
  BRK
  .data $15 "Too many .ifdef directives" $00

; --- Macro errors ($16-$1F) ---
err_macro_name_expected:
  BRK
  .data $16 "Macro name expected" $00

err_macro_shadows_instruction:
  BRK
  .data $17 "Macro name shadows instruction" $00

err_duplicate_macro:
  BRK
  .data $18 "Duplicate macro definition" $00

err_endmacro_without_macro:
  BRK
  .data $19 ".endmacro without .macro" $00

err_unclosed_macro:
  BRK
  .data $1A "Unclosed .macro" $00

err_nested_macro_definition:
  BRK
  .data $1B "Nested macro definition" $00

err_recursive_macro:
  BRK
  .data $1C "Recursive macro invocation" $00

err_too_few_arguments:
  BRK
  .data $1D "Too few macro arguments" $00

err_too_many_arguments:
  BRK
  .data $1E "Too many macro arguments" $00

err_macro_nesting_too_deep:
  BRK
  .data $1F "Macro nesting too deep" $00

; --- Resource limit errors ($20-$22) ---
err_out_of_memory:
  BRK
  .data $20 "Out of memory" $00

err_token_too_long:
  BRK
  .data $21 "Token too long" $00

err_too_many_forward_refs:
  BRK
  .data $22 "Too many forward references" $00

; --- Memory section errors ($23) ---
err_zeropage_overflow:
  BRK
  .data $23 "Zero page overflow" $00

; --- File I/O errors ($24) ---
err_file_not_found:
  BRK
  .data $24 "File not found" $00

; --- Zeropage directive errors ($25) ---
err_operand_in_zeropage:
  BRK
  .data $25 "Operand not allowed on .byte/.word in .zeropage" $00

; --- Command line/usage errors ($F0-$F1) ---
err_usage:
  BRK
  .data $F0 "Usage: <assembler> <input> <output> [debug]" $00

err_invalid_arg:
  BRK
  .data $F1 "Invalid argument" $00

; --- Debug/internal errors ($FE-$FF, debug build only) ---
  .ifdef enable_debug
err_no_file:
  BRK
  .data $FE "Attempt to read with no file open" $00

err_fwdref_tracking:
  BRK
  .data $FF "Internal error - reference tracking" $00
  .endif


  .macro SHOW_MESSAGEI addr
  SET16 addr TABP16
  JSR show_message
  .endmacro

  .macro SHOW_MESSAGE ptr
  CP16 ptr TABP16
  JSR show_message
  .endmacro

  .macro SHOW_CHAR val
  LDA #val
  JSR write_d
  .endmacro


; Interrupt handler - processes BRK for error display
interrupt:
; Retrieve pointer to error code
  TSX
  SEC
  LDA $0102,X
  SBC #$01
  STA TABP16
  LDA $0103,X
  SBC #$00
  STA TABP16+$01
; Retrieve error code and skip diagnostics if no error
  LDY #$00
  LDA (TABP16),Y
  BNE .error
  JMP exit ; Done
.error:
; Save error code
  STA TEMP
; Close the ouptut file if open
  LDA CURR_OUT_FILE
  BEQ .output_not_open
  JSR close
  LDA #$00
  STA CURR_OUT_FILE
.output_not_open:
; Print the "Error " message
  SHOW_MESSAGEI msg_error
; Print the error code in decimal
  LDA TEMP
  STA TO_DECIMAL_VALUE16
  LDA #$00
  STA TO_DECIMAL_VALUE16+$01
  JSR show_decimal
; Print the current file and line if any file is open
  JSR file_stack_empty
  BEQ .location_done
; Print " in file " or " in macro " based on source type
  LDA FS_SRC_TYPE
  BNE .in_macro
  SHOW_MESSAGEI msg_error_file
  JMP .show_source_name
.in_macro:
  SHOW_MESSAGEI msg_error_macro
.show_source_name:
; Print the filename (at FS_P16)
  SHOW_MESSAGE FS_P16
; Print the " at line " message
  SHOW_MESSAGEI msg_error_line
; Print the current line in decimal
  CP16 CURR_LINE16 TO_DECIMAL_VALUE16
  JSR show_decimal
.location_done:
; Print the ": " message
  SHOW_CHAR ':'
  SHOW_CHAR ' '
; Retrieve pointer to the error message and show it
  TSX
  LDA $0102,X
  STA TABP16
  LDA $0103,X
  STA TABP16+$01
  JSR show_message
; Print include traceback (if any files open)
  JSR file_stack_empty
  BEQ .traceback_done
  JSR show_include_traceback
.traceback_done:
; Print the final newline
  SHOW_CHAR '\n'
; Load the error code so that it is returned
  LDA TEMP
  JMP exit ; Done

msg_error:
  .data "Error " $00
msg_error_line:
  .data " at line " $00
msg_error_file:
  .data " in file " $00


; Show a decimal value to the error output
; On entry TO_DECIMAL_VALUE16 contains the value to show
; On exit X, Y are preserved
;         A is not preserved
;         Decimal number string stored at TO_DECIMAL_RESULT
show_decimal:
  JSR to_decimal
  SET16 TO_DECIMAL_RESULT TABP16
  JMP show_message ; tail call


; Show message to the error output
; On entry TABP16 points to the zero-terminated message
; On exit (TABP16),Y points to the zero terminator
;         X is preserved
;         A is not preserved
show_message:
  LDY #$00
.loop:
  LDA (TABP16),Y
  BEQ .done
  JSR write_d
  INY
  BNE .loop
  INC TABP16+$01
  BNE .loop        ; Always taken
.done:
  RTS


; Show traceback - uses file stack API to walk include/expansion chain
; On entry FS_P16 points to current file stack entry
; On exit A, X, Y not preserved
;         TABP16;TABP16+$01 not preserved
;         All files in stack are closed
show_include_traceback:
.loop:
  ; Save child source type before popping
  LDA FS_SRC_TYPE
  PHA
  ; Pop current entry (closes file, restores parent's handle and line)
  JSR pop_file_stack
  ; Check if stack is now empty (no more parents)
  JSR file_stack_empty
  BEQ .done_cleanup
  ; Print newline
  SHOW_CHAR '\n'
  ; Print verb based on child type (saved on stack)
  PLA
  BEQ .verb_included
  ; Child was macro -> "expanded from"
  SHOW_MESSAGEI msg_expanded_from
  JMP .show_parent
.verb_included:
  ; Child was file -> "included from"
  SHOW_MESSAGEI msg_included_from
.show_parent:
  ; Check parent type for "macro " prefix
  LDA FS_SRC_TYPE
  BEQ .parent_is_file
  SHOW_MESSAGEI msg_macro_prefix
.parent_is_file:
  ; Print name (FS_P16 points to parent entry's name)
  SHOW_MESSAGE FS_P16
  ; Print ":"
  SHOW_CHAR ':'
  ; Print line number (CURR_LINE16 has line where include was)
  CP16 CURR_LINE16 TO_DECIMAL_VALUE16
  JSR show_decimal
  ; Continue to next parent
  JMP .loop
.done_cleanup:
  PLA                    ; Clean up saved child type from stack
.done:
  RTS

msg_error_macro:
  .data " in macro " $00
msg_included_from:
  .data "  included from " $00
msg_expanded_from:
  .data "  expanded from " $00
msg_macro_prefix:
  .data "macro " $00
