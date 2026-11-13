; macro_capture.asm - Macro definition and body capture
;
; Provides: dir_macro, capture_macro_line, find_directive_handler
;
; Requires:
;   CURR_CHAR (asm.asm alias; backing storage in source_stack.asm)
;   TOKEN, PASS (asm.asm)
;   MACRO_DEF_PTR16 (asm.asm)
;   LABEL_TYPE (common.asm)
;   read_char (asm.asm alias; implemented in source_stack.asm)
;   read_token, compare_end_of_token, check_for_end_of_line (tokenizer.asm)
;   skip_spaces, skip_rest_of_line (tokenizer.asm)
;   advance_heap (common.asm)
;   select_instruction_hash_table (common.asm)
;   select_label_hash_table (common.asm)
;   find_in_hash_instruction, add_macro_to_hash (hash_table.asm)
;   err_* (errors.asm)

  .zeropage

IN_MACRO_DEF:    .byte        ; Flag: currently capturing macro body ($FF = capturing)

  .code


; Process .macro directive
; Syntax: .macro NAME [param1 param2 ...]
; Creates entry in LHASHTAB: [escape header][name $00][N][param1 $00]...[paramN $00][body $00]
;   The single-byte count up front lets expand_macro reserve the right
;   amount of frame payload without walking the param list (and replaces
;   the empty-string terminator the layout used pre-step-2).
dir_macro:
  ; Skip spaces and read macro name
  JSR check_for_end_of_line
  BCC .has_name
  JMP err_macro_name_expected
.has_name:
  JSR read_token       ; Macro name now in TOKEN, current char in CURR_CHAR
  ; Check for instruction collision in IHASHTAB
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCS .no_instruction_collision
  ; Found in IHASHTAB - check if it's a directive (directives can be shadowed)
  LDA (TABP16),Y
  CMP #MODE_DIRECTIVE
  BEQ .no_instruction_collision
  JMP err_macro_shadows_instruction
.no_instruction_collision:
  ; Save LABEL_SCOPE16 before add_macro_to_hash clobbers it
  PUSH16 LABEL_SCOPE16
  ; Add macro to LHASHTAB
  JSR select_label_hash_table
  JSR add_macro_to_hash
  ; Restore LABEL_SCOPE16
  POP16 LABEL_SCOPE16
  BCC .name_ok         ; C=0 means new entry added
  ; Name already exists - pass 2 expects this, pass 1 is duplicate error
  BIT PASS
  BMI .pass2_skip_add
  JMP err_duplicate_macro
.pass2_skip_add:
  ; Pass 2: skip adding, just set flag to enable body skipping
  ; (body was already captured in pass 1)
  LDA #$FF
  STA IN_MACRO_DEF
  JMP skip_rest_of_line
.name_ok:
  ; Add macro entry value
  ; MEMP16 points to location at which to store the value (directly after key)
  ; TABP16 points to the macro name on heap
  .ifdef enable_debug
  ; Supports the 'show_macros' debug option
  CP16 TABP16, MACRO_PTR16
  .endif
  ; Reserve the parameter-count byte at the start of the value region
  ; and stash its address in MACRO_DEF_PTR16. We bump (MACRO_DEF_PTR16),0
  ; in place each time we capture a parameter, then update
  ; MACRO_DEF_PTR16 to its body-start meaning at .params_done.
  CP16 MEMP16, MACRO_DEF_PTR16
  LDY #$00
  APPEND_HEAPI $00     ; Initial count = 0
  JSR advance_heap
.param_loop:
  JSR check_for_end_of_line
  BCS .params_done     ; End of line, no more params
  ; Read parameter name
  JSR read_token       ; Param name in TOKEN, current char in CURR_CHAR
  ; Store parameter name on heap (null-terminated)
  LDY #$FF
.copy_param:
  INY
  LDA TOKEN,Y
  STA (MEMP16),Y
  BNE .copy_param
  INY
  JSR advance_heap
  ; Bump the count byte at MACRO_DEF_PTR16. (No INC indirect on 6502,
  ; so do an explicit RMW.) Enforce the MACRO_MAX_ARGS cap here too:
  ; raise err_too_many_arguments at definition time rather than letting
  ; the count byte silently overflow if someone wrote 256+ params.
  LDY #$00
  LDA (MACRO_DEF_PTR16),Y
  CLC
  ADC #$01
  CMP #MACRO_MAX_ARGS + 1
  BCC .count_ok
  JMP err_too_many_arguments
.count_ok:
  STA (MACRO_DEF_PTR16),Y
  JSR check_for_end_of_line
  BCS .params_done
  CMP #','
  BNE .param_err_comma
  JSR read_char
  JMP .param_loop
.param_err_comma:
  JMP err_comma_expected
.params_done:
  ; Update MACRO_DEF_PTR to point where body will be stored. The count
  ; byte already has its final value; no end-of-params terminator needed.
  CP16 MEMP16, MACRO_DEF_PTR16
  ; Set IN_MACRO_DEF flag to start capturing
  LDA #$FF
  STA IN_MACRO_DEF
  ; Skip rest of line (already done by check_for_end_of_line)
  RTS


; Look up TOKEN in IHASHTAB and extract directive handler address
; On entry: TOKEN contains the directive name
; On exit: C=0 if found, JUMP_TARGET16 contains handler address
;          C=1 if not found (not in IHASHTAB or not a directive)
;          A, Y are not preserved, X is preserved
find_directive_handler:
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCS .not_found
  LDA (TABP16),Y
  CMP #MODE_DIRECTIVE
  BNE .not_found_set_carry
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16 + 1
  CLC
  RTS
.not_found_set_carry:
  SEC
.not_found:
  RTS


; Capture a line during macro definition
; On entry: CURR_CHAR contains first character of line
; On exit: Line copied to heap (with '\n'), or .endmacro processed
;
; Strategy: Copy whole line to heap, then check if it was .endmacro.
; If so, undo the copy and process .endmacro normally.
; In pass 2, skip heap copy - just scan for .endmacro detection.
capture_macro_line:
  TXA                    ; Save output file handle
  PHA
  BIT PASS
  BPL .pass1
  JMP .pass2
.pass1:
  ; === Pass 1: Copy to heap with compression ===
  ; Comments stripped, consecutive spaces collapsed (except in strings)
  CP16 MEMP16, MACRO_DEF_PTR16 ; Save heap pos for potential undo
  LDX #$00               ; Space indicator - $01 if last char was a space, $00 otherwise
  LDY #0                 ; Capture index
  LDA CURR_CHAR
  BNE .process           ; Always taken
.capture:
  APPEND_HEAPA_ADVANCE
.next:
  JSR read_char
  BCS .eof_error
.process:
  CMP #';'
  BNE .not_semi
  JSR skip_rest_of_line  ; A = '\n'
.not_semi:
  CMP #'\n'
  BEQ .newline
  CMP #'"'
  BEQ .string_lit
  CMP #'\''
  BEQ .char_lit
  CMP #' '
  BEQ .space
  ; Regular character
  LDX #$00               ; Clear last space indicator (sets Z)
  BEQ .capture           ; Always taken
.eof_error:
  JMP err_unclosed_macro
.space:
  ; Space, so check for consecutives
  CPX #$01                 ; Check if last character was a space
  BEQ .next                ; Last char was a space so skip this one
  INX                      ; Set indicator that last character was a space
  BNE .capture             ; Always taken
.string_lit:
  ; Output string definition from opening " through closing "
  LDX #$00                 ; Clear last_space
  APPEND_HEAPA             ; Capture the opening quote
.string_lit_loop:
  JSR read_char            ; Read the current char and capture it
  BCS .eof_error
  APPEND_HEAPA
  ; Conditionally advance heap while preserving current character
  BPL .string_lit_no_advance
  JSR advance_heap
  LDA CURR_CHAR
.string_lit_no_advance:
  CMP #'\\'                ; Was it the escape character?
  BNE .string_lit_not_escape
  ; Escape character so read and capture the next char too
  JSR read_char
  BCS .eof_error
  APPEND_HEAPA
  BNE .string_lit_loop     ; Always taken
.string_lit_not_escape:
  CMP #'"'                 ; Was it the terminating string character?
  BNE .string_lit_loop     ; No so process the next character
  ; Terminator character so we are done with the string
  BEQ .next                ; Always taken (Z set from CMP match)
.char_lit:
  ; Output char definition from opening ' through closing '
  LDX #$00                 ; Clear last_space
  APPEND_HEAPA             ; Capture the opening quote
  JSR read_char            ; Read the next char and write it
  BCS .eof_error
  APPEND_HEAPA
  CMP #'\\'                ; Was it the escape character?
  BNE .char_lit_not_escape
  ; Escape character so read and capture the next char too
  JSR read_char
  BCS .eof_error
  APPEND_HEAPA
.char_lit_not_escape:
  JSR read_char            ; Read the next character
  BCS .eof_error
  ; It should be a closing single quote
  CMP #'\''
  BEQ .capture
  JMP err_invalid_char_literal
.newline:
  APPEND_HEAPA             ; Capture the newline
  JSR advance_heap
  ; Now check if this line was .endmacro or .macro
  CP16 MACRO_DEF_PTR16, TABP16
  ; Skip leading spaces
  LDY #0
.skip_space:
  LDA (TABP16),Y
  CMP #' '
  BNE .check_dot
  INY
  BNE .skip_space
.check_dot:
  CMP #'.'
  BNE .keep_line
  CPY #$00
  BEQ .keep_line           ; Column 0 = local label, not directive
  ; It's a directive
  TYA
  SEC                      ; +1
  ADCA16 TABP16, TABP16 ; Advance TABP16 to point to the start of the directive
  ; Copy directive name from heap (TABP16) to TOKEN
  LDY #$00
.copy_dir:
  LDA (TABP16),Y
  JSR compare_end_of_token
  BCC .copy_dir_done          ; End of token character
  STA TOKEN,Y
  INY
  BNE .copy_dir
.copy_dir_done:
  LDA #$00
  STA TOKEN,Y                 ; Null-terminate
  ; Look up in IHASHTAB
  JSR find_directive_handler
  BCS .keep_line              ; Not found - not a known directive
  ; Check for .endmacro
  CMPI16 JUMP_TARGET16, dir_endmacro
  BEQ .found_endmacro
  ; Check for .macro (nested = error)
  CMPI16 JUMP_TARGET16, dir_macro
  BNE .keep_line              ; Other directive - keep as macro body
  JMP err_nested_macro_definition
.found_endmacro:
  ; Found .endmacro. Restore heap to undo the copy
  CP16 MACRO_DEF_PTR16, MEMP16
  ; At end of macro definition. Write $00 terminator to body
  LDY #0
  APPEND_HEAPI $00
  JSR advance_heap
  ; The debug version of the assembler supports displaying the captured macro
  .ifdef enable_debug
  LDA SHOW_MACROS
  BEQ .not_showing_macros
  JSR show_macros
.not_showing_macros:
  .endif
  ; Clear the capturing flag
  LDA #$00
  STA IN_MACRO_DEF
.keep_line:
  ; Restore X (output file handle)
  PLA
  TAX
  JMP skip_rest_of_line    ; No-op in pass 1 (already at '\n'), skips line in pass 2

  ; === Pass 2: Skip without copying to heap ===
  ; Just detect .endmacro to clear IN_MACRO_DEF flag
.pass2:
  LDA CURR_CHAR
  CMP #' '
  BNE .keep_line ; First column - not a directive (even if '.')
  JSR skip_spaces
  LDA CURR_CHAR
  CMP #'.'
  BNE .keep_line           ; Not a directive
  ; Check if directive is .endmacro
  JSR read_char            ; Read char after '.'
  JSR read_token           ; Read directive name into TOKEN
  JSR find_directive_handler
  BCS .keep_line           ; Not found
  CMPI16 JUMP_TARGET16, dir_endmacro
  BNE .keep_line           ; Not .endmacro
  LDA #$00                 ; Clear the capturing flag
  STA IN_MACRO_DEF
  BEQ .keep_line           ; Always taken (A = 0)
