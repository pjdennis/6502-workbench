; instructions.asm - Instruction lookup/emission, operand parsing
;
; Provides: lookup_mnemonic, find_opcode_for_mode, emit_instruction,
;           handle_fwdref_mode, parse_operand
;
; Requires:
;   CURR_CHAR (asm.asm alias; backing storage in source_stack.asm)
;   HEX16, OPERAND16, PC16, PASS, IS_FWDREF (asm.asm)
;   read_char (asm.asm alias; implemented in source_stack.asm)
;   read_token, skip_spaces, skip_rest_of_line, check_for_end_of_line (tokenizer.asm)
;   parse_value (expressions.asm)
;   emit (output.asm)
;   select_instruction_hash_table (common.asm)
;   find_in_hash_instruction (hash_table.asm)
;   add_forward_ref, check_forward_ref (forward_ref.asm)
;   err_* (errors.asm)

  .zeropage

ADDR_MODE:       .byte        ; Current addressing mode

  .code


; Look up mnemonic and save pointer to mode:opcode data
; On entry A contains the first character of the mnemonic
; On exit C = 0 if mnemonic or 1 if macro
;         CURR_CHAR contains the current character
;         If C = 0: INST_PTR16 points to mode:opcode data (past mnemonic)
;         If C = 1: MACRO_DEF_PTR16 points to macro param data
;         X, Y are not preserved
; Raises 'Opcode not found' error if mnemonic is not found
lookup_mnemonic:
  JSR read_token       ; Current char in CURR_CHAR
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCS .try_macro       ; Not in IHASHTAB - try LHASHTAB for macros
  ; Found in IHASHTAB - check for directive entry
  ; Calculate INST_PTR = TABP16 + Y (value start)
  TYA
  CLC
  ADCA16 TABP16, INST_PTR16
  ; Check first value byte for MODE_DIRECTIVE
  LDY #$00
  LDA (INST_PTR16),Y
  CMP #MODE_DIRECTIVE
  BEQ .try_macro       ; Directive, not an instruction - try LHASHTAB
  ; Found instruction
  CLC
  RTS
.try_macro:
  ; Try LHASHTAB for macros
  ; Save LABEL_SCOPE16 before find_macro_in_hash clobbers it
  PUSH16 LABEL_SCOPE16
  JSR select_label_hash_table
  JSR find_macro_in_hash
  ; Restore LABEL_SCOPE16
  POP16 LABEL_SCOPE16
  BCS .not_found
  ; Found macro in LHASHTAB
  ; MACRO_DEF_PTR = TABP16 + Y (value starts directly at params)
  TYA
  CLC
  ADCA16 TABP16, MACRO_DEF_PTR16
  SEC                   ; Found macro usage
  RTS
.not_found:
  JMP err_opcode_not_found


; Find opcode for addressing mode in mode:opcode list
; On entry INST_PTR16 points to mode:opcode data
;          ADDR_MODE contains the addressing mode to find
; On exit C = 0 if found, A contains opcode
;         C = 1 if not found
;         X is preserved
;         Y is not preserved
find_opcode_for_mode:
  LDY #$00
.loop:
  LDA (INST_PTR16),Y  ; Get mode byte
  CMP #MODE_END
  BEQ .not_found      ; End of list, mode not found
  CMP ADDR_MODE
  BEQ .found
  ; Not this mode, skip to next pair
  INY
  INY
  BNE .loop           ; Always taken
.found:
  INY
  LDA (INST_PTR16),Y  ; Get opcode byte
  CLC
  RTS
.not_found:
  SEC
  RTS


; Emit instruction based on addressing mode
; On entry INST_PTR16 points to mode:opcode data
;          ADDR_MODE contains the addressing mode
;          OPERAND16 contains operand value (if applicable)
; On exit X is preserved
;         A, Y are not preserved
; Raises error if addressing mode is not valid for this instruction
emit_instruction:
  ; Find opcode for this addressing mode
  JSR find_opcode_for_mode
  BCS .invalid_mode
  ; Emit the opcode
  JSR emit
  ; Now emit operand(s) based on mode
  LDA ADDR_MODE
  CMP #MODE_NONE
  BEQ .done            ; No operand for implied mode
  CMP #MODE_REL
  BEQ .emit_relative   ; Relative needs special handling
  ; Check if 1-byte or 2-byte operand
  AND #OPERAND_BYTES_1
  BNE .one_byte
  ; 2-byte operand (absolute modes)
  LDA OPERAND16
  JSR emit
  LDA OPERAND16 + 1
  JMP emit               ; Tail call
.done:
  RTS
.one_byte:
  ; Validate operand <= $FF
  BIT PASS
  BPL .one_byte_ok       ; Skip validation on pass 1
  LDA OPERAND16 + 1
  BNE .one_byte_error
.one_byte_ok:
  LDA OPERAND16
  JMP emit                ; Tail call
.one_byte_error:
  JMP err_value_out_of_range
.emit_relative:
  ; Calculate relative offset: target - PC - 1
  BIT PASS
  BPL .emit_relative_pass1  ; Skip validation on pass 1
  CLC                  ; For the - 1
  LDA OPERAND16
  SBC PC16
  STA OPERAND16
  LDA OPERAND16 + 1
  SBC PC16 + 1
  ; Check if within range
  CMP #$00
  BEQ .forward
  CMP #$FF
  BEQ .backward
  JMP err_branch_out_of_range
.forward:
  LDA OPERAND16
  BPL .emit_relative_ok
  JMP err_branch_out_of_range
.backward:
  LDA OPERAND16
  BMI .emit_relative_ok
  JMP err_branch_out_of_range
.emit_relative_pass1:
  LDA OPERAND16
.emit_relative_ok:
  JMP emit                ; Tail call
.invalid_mode:
  JMP err_invalid_addressing_mode


; Checks mode availability, value size, and forward reference forcing
; On entry: ADDR_MODE set to ZP variant (MODE_ZP, MODE_ZPX, or MODE_ZPY)
;           INST_PTR16 points to instruction's mode:opcode data
;           OPERAND16 contains the operand value
;           IS_FWDREF set if operand is forward reference (pass 1)
;           PASS indicates current pass
; On exit: C=1 if must use ABS variant, C=0 if can use ZP variant
;          In pass 1 with forward ref: adds PC to forward ref list
;          In pass 2: consumes forward ref list entry if present
;          A, Y not preserved, X preserved
handle_fwdref_mode:
  JSR find_opcode_for_mode
  BCS .use_abs             ; No ZP mode available, must use ABS
  ; Check forward reference forcing (must be done before value check
  ; to properly consume forward ref entries in pass 2)
  BIT PASS
  BMI .pass2
  ; Pass 1 - check if this is a forward reference
  BIT IS_FWDREF
  BPL .check_value         ; Not a forward ref, check value size
  ; Forward ref in pass 1 - add to list, return C=1 (use ABS)
  JSR add_forward_ref
  SEC
  RTS
.pass2:
  ; Pass 2 - check the forward ref list
  JSR check_forward_ref    ; Returns C=1 if in list, C=0 if not
  BCS .use_abs             ; Was in list (forced to ABS), return C=1
.check_value:
  ; Check if value requires absolute addressing (>= $100)
  LDA OPERAND16 + 1
  BNE .use_abs             ; Value >= $100, must use ABS
  ; Can use ZP
  CLC
  RTS
.use_abs:
  SEC
  RTS


; Parse operand and emit instruction
; On entry A contains the current character after mnemonic
;          INST_PTR16 points to mode:opcode data
; On exit OPERAND16 contains the operand value
;         ADDR_MODE contains the addressing mode
;         A, X, Y are not preserved
parse_operand:
  JSR check_for_end_of_line
  BCS .implied_mode    ; No operand = implied mode
  ; Check operand format to determine mode
  CMP #'('
  BEQ .indirect_mode
  CMP #'#'
  BNE .other_mode      ; Everything else: $xx $xxxx or label

.immediate_mode:
  ; #$xx or #<label or #>label or #label or #'x'
  JSR read_char        ; Skip #
  JSR parse_value      ; OPERAND16 set
  LDA #MODE_IMM
  STA ADDR_MODE
  RTS

.implied_mode:
  STA_LH16 OPERAND16
  LDA #MODE_NONE
  STA ADDR_MODE
  RTS

.indirect_mode:
  ; ($xx),Y - indirect indexed Y (1-byte operand)
  ; ($xx,X) - indirect indexed X (1-byte operand)
  ; ($xxxx) - indirect absolute for JMP (2-byte operand)
  JSR read_char        ; Skip (
  ; Parse value ($xx, <label, >label, or label)
  JSR parse_value      ; OPERAND16 set, current char in CURR_CHAR
  ; Check suffix to determine addressing mode
  LDA CURR_CHAR        ; Load current char (should be ) or ,)
  CMP #','
  BEQ .ind_x_mode
  ; Must be )
  CMP #')'
  BNE .ind_err_operand
  JSR read_char        ; Read char after )
  CMP #','
  BNE .ind_mode
  JSR read_char        ; Should be Y
  CMP #'Y'
  BNE .ind_err
; ind_y_mode
  JSR read_char        ; Read char after Y for garbage check
  LDA #MODE_INDY
  STA ADDR_MODE
  RTS

.ind_x_mode:
  JSR read_char        ; Should be X
  CMP #'X'
  BNE .ind_err
  JSR read_char        ; Should be )
  CMP #')'
  BNE .ind_err
  JSR read_char        ; Read char after ) for garbage check
  LDA #MODE_INDX
  STA ADDR_MODE
  RTS

.ind_mode:
  ; Just ($xxxx) - JMP indirect mode (must be 2-byte operand)
  ; Current char in CURR_CHAR (after ))
  LDA #MODE_IND
  STA ADDR_MODE
  RTS

.ind_err:
  JMP err_invalid_addressing_mode
.ind_err_operand:
  JMP err_invalid_operand

.other_mode:
  ; Parse value: $xx, $xxxx, or label
  ; All handled uniformly with appropriate mode selection
  JSR parse_value      ; Returns C=1 for bare label, OPERAND16 set, IS_FWDREF set, current char in CURR_CHAR
  ; Check if this is a branch instruction
  LDA #MODE_REL
  STA ADDR_MODE
  JSR find_opcode_for_mode ; Set C=0 if found (relative implies branch)
  BCC .relative_mode
  ; Not a branch - check for indexed mode
  LDA CURR_CHAR        ; Current char (might be comma)
  CMP #','
  BNE .non_index_mode
  ; Has index suffix - read X or Y
  JSR read_char
  CMP #'X'
  BEQ .x_index_mode
  CMP #'Y'
  BEQ .y_index_mode
  JMP err_invalid_addressing_mode

.relative_mode:
  ; MODE_REL already stored to ADDR_MODE
  RTS

.non_index_mode:
  ; Current char in CURR_CHAR
  LDA #MODE_ZP
  STA ADDR_MODE
  JSR handle_fwdref_mode   ; Checks mode availability, value size, forward refs
  BCS .abs_mode            ; Must use ABS
  ; Use ZP mode
  RTS

.abs_mode:
  LDA #MODE_ABS
  STA ADDR_MODE
  RTS

.x_index_mode:
  JSR read_char            ; Read char after X for garbage check, stores in CURR_CHAR
  LDA #MODE_ZPX
  STA ADDR_MODE
  JSR handle_fwdref_mode   ; Checks mode availability, value size, forward refs
  BCS .absx_index_mode     ; Must use ABSX
  ; Use ZPX mode
  RTS

.absx_index_mode:
  LDA #MODE_ABSX
  STA ADDR_MODE
  RTS

.y_index_mode:
  JSR read_char            ; Read char after Y for garbage check, stores in CURR_CHAR
  LDA #MODE_ZPY
  STA ADDR_MODE
  JSR handle_fwdref_mode   ; Checks mode availability, value size, forward refs
  BCS .absy_index_mode     ; Must use ABSY
  ; Use ZPY mode
  RTS

.absy_index_mode:
  LDA #MODE_ABSY
  STA ADDR_MODE
  RTS
