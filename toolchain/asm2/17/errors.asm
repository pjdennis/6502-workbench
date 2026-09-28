; Error handling and messages
;
; Requires:
;   TEMP                 - zero page location for temporary storage (asm.asm)
;   TABP16               - zero page location for table pointer (hash_table.asm)
;   CURR_LINE16          - zero page location for current line number (asm.asm alias)
;   CURR_OUT_FILE        - output file handle (asm.asm)
;   SS_P16               - source stack pointer (source_stack.asm)
;   SS_SRC_TYPE          - source type (source_stack.asm)
;   source_stack_empty     - check if source stack is empty (source_stack.asm)
;   pop_source       - pop source stack entry (source_stack.asm)
;   close                - close file handles (environment.asm)
;   write_d              - write character to stderr (environment.asm)
;   exit                 - exit program (environment.asm)

  .include to_decimal.asm

; ============================================================================
; ERROR HANDLERS - Grouped by category with sequential error codes
; ============================================================================

; --- Label errors (1-4) ---
err_label_not_found:
  BRK
  .asciiz 1, "Label not found"

err_duplicate_label:
  BRK
  .asciiz 2, "Duplicate label"

err_no_global_for_local:
  BRK
  .asciiz 3, "No global label for local"

err_label_expected:
  BRK
  .asciiz 4, "Label expected"

; --- Symbol/Opcode errors (5) ---
err_opcode_not_found:
  BRK
  .asciiz 5, "Opcode not found"

; --- Value/Expression errors (6-13) ---
err_value_out_of_range:
  BRK
  .asciiz 6, "Value out of range"

err_invalid_hex:
  BRK
  .asciiz 7, "Invalid hex"

err_branch_out_of_range:
  BRK
  .asciiz 8, "Branch out of range"

err_invalid_operand:
  BRK
  .asciiz 9, "Invalid operand"

err_unexpected_text:
  BRK
  .asciiz 10, "Unexpected text after operand"

err_expected_shift:
  BRK
  .asciiz 11, "Expected << or >>"

err_invalid_char_literal:
  BRK
  .asciiz 12, "Invalid character literal"

err_invalid_addressing_mode:
  BRK
  .asciiz 13, "Invalid addressing mode"

; --- Directive errors (14-18) ---
err_unknown_directive:
  BRK
  .asciiz 14, "Unknown directive"

err_pc_value_expected:
  BRK
  .asciiz 15, "PC value expected"

err_cannot_move_pc_backwards:
  BRK
  .asciiz 16, "Cannot move PC backwards"

err_filename_expected:
  BRK
  .asciiz 17, "Filename expected"

err_closing_quote_not_found:
  BRK
  .asciiz 18, "Closing quote not found"

; --- Conditional assembly errors (19-21) ---
err_endif_without_ifdef:
  BRK
  .asciiz 19, ".endif without .ifdef"

err_unclosed_ifdef:
  BRK
  .asciiz 20, "Unclosed .ifdef"

err_too_many_ifdefs:
  BRK
  .asciiz 21, "Too many .ifdef directives"

err_else_without_ifdef:
  BRK
  .asciiz 22, ".else without .ifdef"

err_duplicate_else:
  BRK
  .asciiz 23, "Duplicate .else in conditional block"

err_conditional_nesting_too_deep:
  BRK
  .asciiz 24, "Conditional nesting exceeds 16 levels"

; --- Macro errors (25-34) ---
err_macro_name_expected:
  BRK
  .asciiz 25, "Macro name expected"

err_macro_shadows_instruction:
  BRK
  .asciiz 26, "Macro name shadows instruction"

err_duplicate_macro:
  BRK
  .asciiz 27, "Duplicate macro definition"

err_endmacro_without_macro:
  BRK
  .asciiz 28, ".endmacro without .macro"

err_unclosed_macro:
  BRK
  .asciiz 29, "Unclosed .macro"

err_nested_macro_definition:
  BRK
  .asciiz 30, "Nested macro definition"

err_recursive_macro:
  BRK
  .asciiz 31, "Recursive macro invocation"

err_too_few_arguments:
  BRK
  .asciiz 32, "Too few macro arguments"

err_too_many_arguments:
  BRK
  .asciiz 33, "Too many macro arguments"

; (error code 34 retired in Phase 3.6: deep macro nesting now reaches
; out-of-memory naturally rather than tripping a separate limit)

; --- Resource limit errors (35-37) ---
err_out_of_memory:
  BRK
  .asciiz 35, "Out of memory"

err_token_too_long:
  BRK
  .asciiz 36, "Token too long"

err_too_many_forward_refs:
  BRK
  .asciiz 37, "Too many forward references"

; --- Memory section errors (38) ---
err_zeropage_overflow:
  BRK
  .asciiz 38, "Zero page overflow"

; --- File I/O errors (39) ---
err_file_not_found:
  BRK
  .asciiz 39, "File not found"

; --- Syntax errors (40) ---
err_comma_expected:
  BRK
  .asciiz 40, "Comma expected"

; --- Zeropage directive errors (41-42) ---
err_asciiz_in_zeropage:
  BRK
  .asciiz 41, ".asciiz not allowed in .zeropage"

err_operand_in_zeropage:
  BRK
  .asciiz 42, "Operand not allowed on .byte/.word in .zeropage"

; --- Pass consistency errors (43-44) ---
err_assignment_of_later_label:
  BRK
  .asciiz 43, "Assignment uses a label defined later"

err_address_differs:
  BRK
  .asciiz 44, "Address differs between passes"

; --- Command line/usage errors (240-241) ---
err_usage:
  BRK
  .asciiz 240, "Usage: <assembler> <input> <output> [define:label ...]"

err_invalid_arg:
  BRK
  .asciiz 241, "Invalid argument"

; --- Debug/internal errors (254-255, debug build only) ---
  .ifdef enable_debug
err_no_file:
  BRK
  .asciiz 254, "Attempt to read with no file open"

err_fwdref_tracking:
  BRK
  .asciiz 255, "Internal error - reference tracking"
  .endif


  .macro SHOW_MESSAGEI addr
  SET16 addr, TABP16
  JSR show_message
  .endmacro

  .macro SHOW_MESSAGE ptr
  CP16 ptr, TABP16
  JSR show_message
  .endmacro

  ; Show the name of a source-stack frame whose start address lives at ptr.
  ; Frame layout is [size, curr_type, prev_type, line_L, line_H,
  ; prev_data_L, prev_data_H, name\0, payload], so the null-terminated
  ; name starts at offset 7.
  .macro SHOW_FRAME_NAME ptr
  CLC
  ADCI16 ptr, $07, TABP16
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
  SBC #1
  STA TABP16
  LDA $0103,X
  SBC #0
  STA TABP16 + 1
; Retrieve error code and skip diagnostics if no error
  LDY #0
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
  STA TO_DECIMAL_VALUE16 + 1
  JSR show_decimal
; Print the current file and line if any file is open
  JSR source_stack_empty
  BEQ .location_done
; Print " in file " or " in macro " based on source type
  LDA SS_SRC_TYPE
  CMP #SS_SRC_TYPE_FILE
  BNE .in_macro
  SHOW_MESSAGEI msg_error_file
  JMP .show_source_name
.in_macro:
  SHOW_MESSAGEI msg_error_macro
.show_source_name:
; Print the source name (frame at SS_P16)
  SHOW_FRAME_NAME SS_P16
; Print the " at line " message
  SHOW_MESSAGEI msg_error_line
; Print the current line in decimal
  CP16 CURR_LINE16, TO_DECIMAL_VALUE16
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
  STA TABP16 + 1
  JSR show_message
; Print include traceback (if any files open)
  JSR source_stack_empty
  BEQ .traceback_done
  JSR show_include_traceback
.traceback_done:
; Print the final newline
  SHOW_CHAR '\n'
; Load the error code so that it is returned
  LDA TEMP
  JMP exit ; Done

msg_error:
  .asciiz "Error "
msg_error_line:
  .asciiz " at line "
msg_error_file:
  .asciiz " in file "


; Show a decimal value to the error output
; On entry TO_DECIMAL_VALUE16 contains the value to show
; On exit X, Y are preserved
;         A is not preserved
;         Decimal number string stored at TO_DECIMAL_RESULT
show_decimal:
  JSR to_decimal
  SET16 TO_DECIMAL_RESULT, TABP16
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
  INC TABP16 + 1
  BNE .loop        ; Always taken
.done:
  RTS


; Show traceback - uses source stack API to walk include/expansion chain
; On entry SS_P16 points to current source stack entry
; On exit A, X, Y not preserved
;         TABP16;TABP16 + 1 not preserved
;         All files in stack are closed
show_include_traceback:
.loop:
  ; Save child source type before popping
  LDA SS_SRC_TYPE
  PHA
  ; Pop current entry (closes file, restores parent's handle and line)
  JSR pop_source
  ; Check if stack is now empty (no more parents)
  JSR source_stack_empty
  BEQ .done_cleanup
  ; Print newline
  SHOW_CHAR '\n'
  ; Print verb based on child type (saved on stack)
  PLA
  CMP #SS_SRC_TYPE_FILE
  BEQ .verb_included
  ; Child was macro -> "expanded from"
  SHOW_MESSAGEI msg_expanded_from
  JMP .show_parent
.verb_included:
  ; Child was file -> "included from"
  SHOW_MESSAGEI msg_included_from
.show_parent:
  ; Check parent type for "macro " prefix
  LDA SS_SRC_TYPE
  CMP #SS_SRC_TYPE_FILE
  BEQ .parent_is_file
  SHOW_MESSAGEI msg_macro_prefix
.parent_is_file:
  ; Print parent frame's name
  SHOW_FRAME_NAME SS_P16
  ; Print ":"
  SHOW_CHAR ':'
  ; Print line number (CURR_LINE16 has line where include was)
  CP16 CURR_LINE16, TO_DECIMAL_VALUE16
  JSR show_decimal
  ; Continue to next parent
  JMP .loop
.done_cleanup:
  PLA                    ; Clean up saved child type from stack
.done:
  RTS

msg_error_macro:
  .asciiz " in macro "
msg_included_from:
  .asciiz "  included from "
msg_expanded_from:
  .asciiz "  expanded from "
msg_macro_prefix:
  .asciiz "macro "
