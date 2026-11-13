; init.asm - CLI argument processing, input file opening, debug support
;
; Provides: open_input, match_command_line_arg, handle_define,
;           copy_string_to_token, show_macros (debug only),
;           COMMAND_LINE_ARGS table
;
; Requires:
;   TOKEN (asm.asm), TABP16 (hash_table.asm), ARG_COUNT (init.asm)
;   DEBUG_FLAG, SHOW_MACROS, SMALL_HEAP_FLAG (asm.asm)
;   argv, write_d (environment.asm)
;   init_heap (common.asm), init_hash_table (hash_table.asm)
;   select_label_hash_table (common.asm)
;   hash_add (hash_table.asm), store_hash_value (common.asm)
;   push_file_source (source_stack.asm)
;   show_message (errors.asm, debug output)

  .zeropage

ARG_COUNT:       .byte        ; Total command line argument count
JUMP_TARGET16:   .word        ; Target for indirect jumps
ARG_PTR16:       .word        ; Pointer into COMMAND_LINE_ARGS table

  .code


; Opens the file with name from the first command line argument, pushing
; to the source stack
; On exit X is preserved
open_input:
  TXA
  PHA
  LDA #$00
  JSR argv
  STAX16 TABP16
  PLA
  TAX
  JSR copy_string_to_token
  JMP push_file_source ; tail call


MATCH_PARTIAL = 0
MATCH_FULL    = 1

COMMAND_LINE_ARGS:
  .ifdef enable_debug
  .asciiz "debug", MATCH_FULL
  .word handle_debug
  .asciiz "small_heap", MATCH_FULL
  .word handle_small_heap
  .asciiz "show_captured_macros", MATCH_FULL
  .word handle_show_captured_macros
  .endif
  .asciiz "define:", MATCH_PARTIAL
  .word handle_define
  .byte 0 ; End of list


  .ifdef enable_debug

; Handle the 'debug' command line argument
handle_debug:
  LDA #$FF
  STA DEBUG_FLAG
  RTS

; Handle the 'small_heap' command line argument
handle_small_heap:
  LDA #$FF
  STA SMALL_HEAP_FLAG
  JMP init_heap          ; Tail call

; Handle the 'show_captured_macros' command line argument
handle_show_captured_macros:
  LDA #$FF
  STA SHOW_MACROS
  .endif

; Handle the 'define:' command line argument
; On entry TABP16 points past "define:" to label name
handle_define:
  JSR copy_string_to_token
  SET16 $0001, HEX16
  LDA #LABEL_TYPE_GLOBAL
  STA LABEL_TYPE
  JSR select_label_hash_table
  JSR hash_add
  JMP store_hash_value   ; Store value and advance heap


; Match command line argument against table
; On entry TABP16 points to the argument string
; Calls the handler if match found (with TAB16 pointed to remainder of argument for partial)
; On exit C = 0 if match found
;         C = 1 if no match
;         X, Y are preserved
;         A is not preserved
match_command_line_arg:
  TYA
  PHA
  SET16 COMMAND_LINE_ARGS, ARG_PTR16
.try_entry:
  ; Check for end of table (first byte = 0)
  LDY #$00
  LDA (ARG_PTR16),Y
  BEQ .no_match
  ; Compare strings
.compare_loop:
  LDA (ARG_PTR16),Y
  BEQ .string_end        ; End of table string
  CMP (TABP16),Y
  BNE .next_entry        ; Mismatch, try next
  INY
  BNE .compare_loop      ; Always taken
.string_end:
  ; Table string ended - check match type
  ; Y = length of matched string (points to null terminator)
  INY                    ; Skip null terminator
  LDA (ARG_PTR16),Y      ; Load match type
  BNE .check_full_match  ; MATCH_FULL (non-zero)
  ; MATCH_PARTIAL - prefix matched, advance TABP16
  DEY                    ; Back up to the match position
  TYA                    ; Y is pointing at the text following the match
  CLC
  ADCA16 TABP16, TABP16
  INY                    ; Skip forwards to the handler position
  JMP .load_handler
.check_full_match:
  ; MATCH_FULL - argument string must also end here
  DEY                    ; Undo the INY to check at same position as null
  LDA (TABP16),Y
  BNE .next_entry        ; Arg string continues, not a match
  INY                    ; Skip past the match type
.load_handler:
  ; Load handler address (Y points to match type byte)
  INY                    ; Skip match type
  LDA (ARG_PTR16),Y
  STA JUMP_TARGET16
  INY
  LDA (ARG_PTR16),Y
  STA JUMP_TARGET16 + 1
  JSR do_jump            ; Call handler
  CLC                    ; Match found
  PLA                    ; Restore Y
  TAY
  RTS
.next_entry:
  ; Advance ARG_PTR16 to next entry
  ; Find null terminator
.find_null:
  LDA (ARG_PTR16),Y
  BEQ .found_null
  INY
  BNE .find_null
.found_null:
  ; Y points to null, skip null + match_type + 2-byte address = 4 more bytes
  TYA
  CLC
  ADC #$04
  ADCA16 ARG_PTR16, ARG_PTR16
  JMP .try_entry
.no_match:
  SEC
  PLA                    ; Restore Y
  TAY
  RTS

; Execute handler via indirect jump
; On entry JUMP_TARGET16 contains the handler address
do_jump:
  JMP (JUMP_TARGET16)


; Copy null-terminated string from TABP16 to TOKEN
; On exit: Y contains length (excluding null terminator)
;          A is not preserved
copy_string_to_token:
  LDY #$00
.loop:
  LDA (TABP16),Y
  BEQ .done
  STA TOKEN,Y
  INY
  BNE .loop              ; A is guaranteed non-zero (BEQ .done above)
.done:
  LDA #$00
  STA TOKEN,Y          ; Null-terminate
  RTS


  .ifdef enable_debug

show_macros:
  ; Output "Macro: "
  SHOW_MESSAGEI .macro_prefix
  ; Output macro name (skip escape format header: type, scope_lo, scope_hi)
  CP16 MACRO_PTR16, TABP16
  LDY #$03
  JSR .advance_tabp
  JSR show_message
  ; Skip past the name's trailing null. TABP16 now points at the
  ; parameter count byte (post-step-2 def layout).
  INY
  JSR .advance_tabp
  ; Read the count, advance past it, then print N param names. No
  ; trailing terminator anymore -- we stop when X reaches 0.
  LDY #$00
  LDA (TABP16),Y
  TAX
  INY
  JSR .advance_tabp
  CPX #$00
  BEQ .show_params_done
  ; First param prefixed with a single space
  LDA #' '
  JSR write_d
  JSR show_message
  INY
  JSR .advance_tabp
  DEX
.show_more_params:
  CPX #$00
  BEQ .show_params_done
  LDA #','
  JSR write_d
  LDA #' '
  JSR write_d
  JSR show_message
  INY
  JSR .advance_tabp
  DEX
  JMP .show_more_params
.show_params_done:
  ; TABP16 already points at the body's first byte (no trailing null
  ; to skip in the new layout).
  LDA #'\n'
  JSR write_d
  ; Output macro body
  JMP show_message         ; Tail call
.advance_tabp:
  TYA
  CLC
  ADCA16 TABP16, TABP16
  LDY #$00
  RTS
.macro_prefix:
  .asciiz "Macro: "

  .endif
