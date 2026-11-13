; directives.asm - Directive dispatch, data directives, conditional assembly
;
; Provides: swap_pc_with_save, process_directive, process_conditional_directive,
;           emit_quoted, set_data_mode, data_parameters_loop,
;           dir_reserve, dir_ifdef, dir_ifndef, dir_else, dir_endif
;
; Requires:
;   CURR_CHAR (asm.asm alias; backing storage in source_stack.asm)
;   TOKEN, PASS, PC16, PC_SAVE16, OPERAND16, IN_ZEROPAGE (asm.asm)
;   IFDEF_DECISIONS (asm.asm), COND_DEPTH, SKIP_DEPTH, IFDEF_INDEX (directives.asm)
;   read_char (asm.asm alias; implemented in source_stack.asm)
;   read_token, read_filename (tokenizer.asm)
;   find_in_hash_instruction, select_instruction_hash_table (common.asm/hash_table.asm)
;   skip_rest_of_line, check_for_end_of_line (tokenizer.asm)
;   select_label_hash_table (common.asm)
;   emit, advance_pc_to_hex16 (output.asm)
;   decode_escape (tokenizer.asm)
;   parse_value (expressions.asm)
;   dir_macro (macro_capture.asm)
;   do_jump, JUMP_TARGET16 (init.asm)
;   push_file_source (source_stack.asm)
;   CMPI16 (macros.asm)
;   err_* (errors.asm)

  .zeropage

DATA_MODE:       .byte        ; Data directive mode: 1=.byte 2=.word 3=.asciiz
COND_DEPTH:      .byte        ; Conditional assembly nesting depth
SKIP_DEPTH:      .byte        ; Depth where skipping started (0 = not skipping)
IFDEF_INDEX:     .byte        ; Current index into IFDEF_DECISIONS buffer
COND_INVERT:     .byte        ; Value if label NOT found ($00 for ifdef, $FF for ifndef)

  .code

; Constants
DATA_MODE_BYTE   = 1          ; 1 Byte
DATA_MODE_WORD   = 2          ; 2 Bytes
DATA_MODE_ASCIIZ = 3          ; 1 Byte, null terminated


; Swap PC16 with PC_SAVE16
; Used by .zeropage/.code directive handlers
; On exit A, Y are not preserved
;         X is preserved
swap_pc_with_save:
  ; Swap PC16 low byte with save location
  LDA PC16
  LDY PC_SAVE16
  STY PC16
  STA PC_SAVE16
  ; Swap PC16 high byte with save location
  LDA PC16 + 1
  LDY PC_SAVE16 + 1
  STY PC16 + 1
  STA PC_SAVE16 + 1
  RTS


; On entry, A contains the first character of the directive
process_directive:
  JSR read_token       ; Current char in CURR_CHAR
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCS .not_found
  ; Check for MODE_DIRECTIVE
  LDA (TABP16),Y
  CMP #MODE_DIRECTIVE
  BNE .not_found
  ; Extract handler address
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16 + 1
  JMP do_jump           ; Tail call: handler RTS returns to our caller
.not_found:
  JMP err_unknown_directive
dir_include:
  JSR check_for_end_of_line
  BCC .get_name
  JMP err_filename_expected
.get_name:
  JSR read_filename
  JSR skip_rest_of_line
  JMP push_file_source    ; Tail call
dir_zeropage:
  BIT IN_ZEROPAGE
  BMI .in_zeropage
  LDA #$FF
  STA IN_ZEROPAGE
  JSR swap_pc_with_save
.in_zeropage:
  JMP skip_rest_of_line  ; Tail call
dir_code:
  BIT IN_ZEROPAGE
  BPL .in_code
  LDA #$00
  STA IN_ZEROPAGE
  JSR swap_pc_with_save
.in_code:
  JMP skip_rest_of_line  ; Tail call
dir_byte:
  LDA #DATA_MODE_BYTE
  BIT IN_ZEROPAGE
  BMI dir_zp_alloc       ; In zeropage? check for operand-less form
  JMP set_data_mode
dir_word:
  LDA #DATA_MODE_WORD
  BIT IN_ZEROPAGE
  BMI dir_zp_alloc       ; In zeropage? check for operand-less form
  JMP set_data_mode
dir_asciiz:
  BIT IN_ZEROPAGE
  BMI .zp_asciiz_err
  LDA #DATA_MODE_ASCIIZ
  JMP set_data_mode
.zp_asciiz_err:
  JMP err_asciiz_in_zeropage
dir_endmacro:
  JMP err_endmacro_without_macro

dir_zp_alloc:
  ; A = DATA_MODE (1=byte, 2=word)
  STA DATA_MODE
  JSR check_for_end_of_line
  BCS .zp_allocate          ; EOL - operand-less form
  CMP #'.'
  BEQ .zp_allocate          ; Another directive follows - operand-less form
  JMP err_operand_in_zeropage
.zp_allocate:
  ; Emit dummy bytes (1 for .byte, 2 for .word)
  LDA #$00
  JSR emit                  ; Advance ZP PC by 1
  LDA DATA_MODE
  CMP #DATA_MODE_WORD
  BNE .zp_done
  LDA #$00
  JSR emit                  ; Advance ZP PC by 2nd byte for .word
.zp_done:
  RTS


; On exit C=0 if processed; C=1 if not processed
;         A is not preserved
process_conditional_directive:
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCS .not_conditional       ; Not found in IHASHTAB
  ; Check for MODE_DIRECTIVE
  LDA (TABP16),Y
  CMP #MODE_DIRECTIVE
  BNE .not_conditional
  ; Extract handler address
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16
  INY
  LDA (TABP16),Y
  STA JUMP_TARGET16 + 1
  ; Check if it's one of the 4 conditional directives
  CMPI16 JUMP_TARGET16, dir_ifdef
  BEQ .found
  CMPI16 JUMP_TARGET16, dir_ifndef
  BEQ .found
  CMPI16 JUMP_TARGET16, dir_else
  BEQ .found
  CMPI16 JUMP_TARGET16, dir_endif
  BEQ .found
.not_conditional:
  SEC                        ; Not a conditional directive
  RTS
.found:
  JSR do_jump                ; Call handler via trampoline
  CLC                        ; Processed
  RTS


; Read and emit quoted ASCII
; On entry A contains the first character within quotes
; On exit A contains the current character after the closing quote
;         X, Y are preserved
; Raises 'Closing quote not found' error if closing quote not found on current line
emit_quoted:
.loop:
  CMP #'\n'
  BEQ .err_closing_quote
  CMP #'"'
  BEQ .done
  CMP #'\\'
  BNE .not_escaped
  JSR read_char
  CMP #'\n'
  BEQ .err_closing_quote
  JSR decode_escape
.not_escaped:
  JSR emit
  JSR read_char
  BCC .loop
.err_closing_quote:
  JMP err_closing_quote_not_found
.done:
  JMP read_char        ; Tail call; read char after closing quote


; Handle .reserve N directive
; Reserves N bytes: zero-fill in .code, PC advance in .zeropage
dir_reserve:
  JSR skip_spaces
  JSR parse_value
  ; HEX16 (= OPERAND16) now holds the count
  ; Compute target: HEX16 = PC16 + count
  CLC
  ADC16 HEX16, PC16, HEX16
  JSR advance_pc_to_hex16
  JMP skip_rest_of_line


set_data_mode:
  STA DATA_MODE
data_parameters_loop:
  JSR check_for_end_of_line
  BCS .data_done
  CMP #'"'            ; Quoted string
  BNE .data_value
  JSR read_char
  JSR emit_quoted
  LDA DATA_MODE
  CMP #DATA_MODE_ASCIIZ
  BNE .data_check_more
  LDA #$00
  JSR emit
  JMP .data_check_more
.data_value:
  JSR parse_value
  LDA DATA_MODE
  CMP #DATA_MODE_WORD
  BEQ .data_emit_two_bytes  ; Mode 2 (.word): force 2 bytes
  ; Mode 1 (.byte) or Mode 3 (.asciiz): validate + emit 1 byte
  BIT PASS
  BPL .data_emit_one_byte   ; Skip validation on pass 1
  LDA OPERAND16 + 1
  BEQ .data_emit_one_byte   ; Not an error
  JMP err_value_out_of_range
.data_emit_one_byte:
  LDA OPERAND16
  JSR emit
  JMP .data_check_more
.data_emit_two_bytes:
  LDA OPERAND16          ; Emit low byte
  JSR emit
  LDA OPERAND16 + 1      ; Emit high byte
  JSR emit
.data_check_more:
  JSR check_for_end_of_line
  BCS .data_done
  CMP #','
  BEQ .data_comma
  CMP #'.'
  BEQ .data_done           ; Another directive follows - return to caller
  JMP err_comma_expected
.data_comma:
  JSR read_char
  JMP data_parameters_loop
.data_done:
  RTS


; Process .ifdef directive
; Records decision in pass 1, replays in pass 2 for consistency with forward refs
dir_ifdef:
  LDA #$00
  STA COND_INVERT          ; Value if label NOT found (skip for ifdef)
  JMP process_conditional_common


; Process .ifndef directive
; Records decision in pass 1, replays in pass 2 for consistency with forward refs
; Inverse of .ifdef: assembles if label NOT defined
dir_ifndef:
  LDA #$FF
  STA COND_INVERT          ; Value if label NOT found (assemble for ifndef)
  ; Fall through to process_conditional_common


; Common conditional processing for .ifdef and .ifndef
; On entry: COND_INVERT = value if label NOT found ($00 for ifdef, $FF for ifndef)
; This consolidates the nearly-identical logic between ifdef and ifndef
process_conditional_common:
  INC COND_DEPTH
  LDA COND_DEPTH
  CMP #17                  ; Check for nesting limit (16 levels max)
  BCS .nesting_too_deep
  LDA SKIP_DEPTH
  BNE .already_skipping    ; Already skipping, don't record or evaluate
  ; Evaluate condition
  JSR check_for_end_of_line
  BCC .has_label
  JMP err_label_expected
.has_label:
  JSR read_token           ; Expects current char in A
  ; Save X (global output file handle)
  TXA
  PHA
  ; Check for pass 2 - no need to look up label in pass 2
  BIT PASS
  BMI .pass2
  ; --- Pass 1: Evaluate and store decision ---
  LDX IFDEF_INDEX
  ; Increment and check for overflow (wrap from 255 to 0 = buffer full)
  INC IFDEF_INDEX
  BEQ .overflow            ; If wrapped to 0, we've used all 256 slots
  LDA #LABEL_TYPE_GLOBAL
  STA LABEL_TYPE
  JSR select_label_hash_table
  JSR find_in_hash         ; C=0 if found, C=1 if not found
  ; COND_INVERT contains the "not found" value
  LDA COND_INVERT
  BCS .save_result         ; C=1 means not found, use value as-is
  EOR #$FF                 ; C=0 means found, flip the value
.save_result:
  STA IFDEF_DECISIONS,X
  ; Branch based on decision value
  BEQ .start_skip          ; $00 - start skipping
  BNE .done                ; $FF - continue (no skip)
  ; --- Pass 2: Replay stored decision ---
.pass2:
  LDX IFDEF_INDEX
  INC IFDEF_INDEX
  LDA IFDEF_DECISIONS,X
  BEQ .start_skip
  BNE .done
.start_skip:
  LDA COND_DEPTH
  STA SKIP_DEPTH
.done:
  ; Restore X (global output file handle)
  PLA
  TAX
.already_skipping:
  JMP skip_rest_of_line
.overflow:
  JMP err_too_many_ifdefs
.nesting_too_deep:
  JMP err_conditional_nesting_too_deep


; Process .else directive
; Toggles skip state for current conditional block
dir_else:
  ; 1. Validate we're in a conditional block
  LDA COND_DEPTH
  BEQ .error_else_without_ifdef
  ; 2. Check if this conditional already has .else. The -1 biased
  ; access maps COND_DEPTH (1..16) onto array entries 0..15.
  TAY                          ; Y = COND_DEPTH (use Y, not X!)
  LDA ELSE_SEEN_ARRAY - 1,Y
  BNE .error_duplicate_else
  ; 3. Mark .else seen at this depth
  LDA #$FF
  STA ELSE_SEEN_ARRAY - 1,Y
  ; 4. Toggle skip state
  LDA SKIP_DEPTH
  BNE .currently_skipping
  ; Currently assembling - start skipping
  LDA COND_DEPTH
  STA SKIP_DEPTH
  JMP skip_rest_of_line
.currently_skipping:
  ; Check if skipping at THIS level
  CMP COND_DEPTH
  BNE .skip_at_outer_level     ; Skipping at outer level, stay skipped
  ; Skipping at this level - stop skipping
  LDA #$00
  STA SKIP_DEPTH
.skip_at_outer_level:
  JMP skip_rest_of_line
.error_else_without_ifdef:
  JMP err_else_without_ifdef
.error_duplicate_else:
  JMP err_duplicate_else


; Process .endif directive
dir_endif:
  LDA COND_DEPTH
  BNE .has_ifdef       ; In a conditional block
  JMP err_endif_without_ifdef
.has_ifdef:
  ; Clear ELSE_SEEN_ARRAY entry for this depth (-1 biased access)
  ; before decrementing
  TAY                  ; Y = COND_DEPTH (use Y, not X!)
  LDA #$00
  STA ELSE_SEEN_ARRAY - 1,Y
  DEC COND_DEPTH
  ; Check if this ends our skip block
  LDA SKIP_DEPTH
  BEQ .done            ; Not skipping, just decrement depth
  ; Currently skipping - check if we should stop
  LDA COND_DEPTH
  CMP SKIP_DEPTH
  BCS .done            ; Still in nested block (COND_DEPTH >= SKIP_DEPTH)
  ; COND_DEPTH < SKIP_DEPTH, stop skipping
  LDA #$00
  STA SKIP_DEPTH
.done:
  JMP skip_rest_of_line ; Tail call
