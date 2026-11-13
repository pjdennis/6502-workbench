; labels.asm - Label capture, local labels, value assignment
;
; Provides: check_for_value, read_value, read_local_label,
;           update_label_scope_from_lookup, capture_label
;
; Requires:
;   CURR_CHAR (asm.asm alias; backing storage in source_stack.asm)
;   TOKEN, PASS, OPERAND16, TEMP (asm.asm)
;   LABEL_SCOPE16 (hash_table.asm)
;   LABEL_TYPE, LABEL_TYPE_GLOBAL, LABEL_TYPE_LOCAL, LABEL_TYPE_MACRO_LOCAL (common.asm)
;   SCOPE_DEPTH (label_scope.asm)
;   read_char (asm.asm alias; implemented in source_stack.asm)
;   read_token, skip_spaces, check_for_end_of_line (tokenizer.asm)
;   parse_value (expressions.asm), update_pc (output.asm)
;   find_in_hash, hash_add, commit_cached_hash (hash_table.asm)
;   select_label_hash_table, store_hash_value (common.asm)
;   err_* (errors.asm)

  .code


; Check for the existance of an assigned value (read the equals sign)
; On entry CURR_CHAR contains the current character
; On exit C set if value exists; clear otherwise
;         A contains the current character
;         X, Y are preserved
check_for_value:
  JSR skip_spaces
  CMP #'='             ; C=1 if A='=', C=0 otherwise
  BEQ .done
  CLC                  ; A < '=', so clear carry explicitly
.done:
  RTS


; Read a value
; On entry A contains the current character
; On exit HEX16 contains the value read
;         A contains the current character
;         X is preserved
;         Y is not preserved
; Raises 'Bad hex' error if non-hex characters were encountered
; Supports: $xx, $xxxx, label, <label, >label
read_value:
  JSR read_char        ; Read the character after the "="
  JSR skip_spaces
  JMP parse_value      ; Tail call; Returns value in OPERAND16 (aliased to HEX16)


; Read a local label (dot already detected but not consumed)
; Skips dot, reads name into TOKEN, validates scope, sets LABEL_TYPE
; On exit LABEL_TYPE set to LABEL_TYPE_LOCAL or LABEL_TYPE_MACRO_LOCAL
;         CURR_CHAR contains character after token
;         A not preserved
;         X preserved, Y not preserved
read_local_label:
  JSR read_char             ; Skip '.'
  JSR read_token            ; Read name into TOKEN
  TST16 LABEL_SCOPE16
  BNE .have_scope
  JMP err_no_global_for_local
.have_scope:
  ; Determine if in macro context by checking scope depth
  LDA SCOPE_DEPTH
  BNE .in_macro
  ; Not in macro - use LOCAL type
  LDA #LABEL_TYPE_LOCAL
  BNE .store               ; Always taken (LABEL_TYPE_LOCAL != 0)
.in_macro:
  ; In macro expansion - use MACRO_LOCAL type
  LDA #LABEL_TYPE_MACRO_LOCAL
.store:
  STA LABEL_TYPE
  RTS


; Update LABEL_SCOPE16 by looking up TOKEN in hash table
; Used in pass 2 to set the scope for local label matching
; On entry TOKEN contains the global label name
;          LABEL_TYPE = 0 (global label)
; On exit LABEL_SCOPE16 points to the token string on heap
;         CACHED_HASH is set (needed for subsequent local label lookups)
;         A, Y not preserved
;         X is preserved
update_label_scope_from_lookup:
  JSR select_label_hash_table
  JSR find_in_hash       ; TABP16 now points to token string
  JSR commit_cached_hash ; Commit hash since this is a non-assignment global
  ; After find_in_hash, TABP16 points to token string (entry_start + 2)
  CP16 TABP16, LABEL_SCOPE16
  RTS


; Reads a label, and optionally an assigned value. The label is stored in the current hash table
; mapped to the assigned value (if provided) otherwise the current PC value. The special label '*'
; is not stored in the hash table but instead requires an assigned value which sets PC
; On entry A contains the first character of the label
; On exit the hash table or PC is updated accordingly
;         C is set if line fully processed, clear otherwise
;         A, X, Y are not preserved
; Raises 'PC value expected' if no value provided when setting PC via '*'
;        'Duplicate label' error if label has already been encountered
;        'Assignment uses a label defined later' (pass 2) if an assigned
;          value differs from pass 1's, which took such a label as 0
;        'Address differs between passes' (pass 2) if a label's address
;          differs from pass 1's
;        'Bad hex' error if non-hex characters were encountered
capture_label:
  CMP #'*'
  BEQ .set_pc
  CMP #'.'
  BNE .not_local
  JSR read_local_label
  JMP .after_type_set
.not_local:
  JSR read_token            ; Current char in CURR_CHAR
  LDA #LABEL_TYPE_GLOBAL
  STA LABEL_TYPE
.after_type_set:
  LDA CURR_CHAR             ; Check if terminated by colon
  CMP #':'
  BNE .no_colon
  JSR read_char             ; Skip past colon, update CURR_CHAR
.no_colon:
  ; Normal label
  BIT PASS
  BPL .pass_1
  ; Pass 2 - don't capture label, but must track globals for local label
  ; scoping, and check each label's address against pass 1's
  ; LABEL_TYPE already set
  JSR check_for_value
  BCS .has_equals_2         ; If = found, branch
  ; No = found: look the label up (a global one sets the scope for the
  ; local labels after it); check_for_value updated CURR_CHAR if it
  ; called read_char
  LDA LABEL_TYPE
  BEQ .global_2
  JSR select_label_hash_table
  JSR find_in_hash          ; A local or macro-local label
  JMP .check_address_2
.global_2:
  JSR update_label_scope_from_lookup  ; Set LABEL_SCOPE16 for local label lookups
.check_address_2:
  ; HT_V16 = the address pass 1 gave the label: the same now, unless a
  ; * = or .reserve before it took a label not defined yet in pass 1
  CMP16 HT_V16, PC16
  BEQ .skip_spaces_and_return_processed_flag
  JMP err_address_differs
.set_pc:
  ; Set PC
  JSR read_char             ; Skip the *
  JSR check_for_value
  BCS .pc_value_present
  JMP err_pc_value_expected
.pc_value_present:
  JSR read_value
  JSR check_for_end_of_line
  BCC .err_unexpected_text
  JSR update_pc
  SEC                       ; Indicate line is fully processed
  RTS
.has_equals_2:
  ; Pass 1 stored the value, taking a label not defined yet as 0; now
  ; that every label is, the value must come out the same
  JSR select_label_hash_table
  JSR find_in_hash          ; HT_V16 = the value pass 1 stored
  LDA HT_V16 + 1
  PHA
  LDA HT_V16
  PHA
  JSR read_value            ; HEX16 = the value now (HT_V16 is HEX16)
  PLA
  EOR HEX16
  STA TEMP
  PLA
  EOR HEX16 + 1
  ORA TEMP
  BEQ .return_processed
  JMP err_assignment_of_later_label
.pass_1:
  ; LABEL_TYPE already set
  ; Add key to hash table first (before read_value may overwrite TOKEN)
  JSR select_label_hash_table
  JSR hash_add
  BCS .duplicate_label
  ; Now read the value (TOKEN can be overwritten, but HTTPL/HTTPH preserved if no =)
  JSR check_for_value
  BCS .has_equals           ; If = found, branch
  ; No = found, save global label and use program counter
  ; Update LABEL_SCOPE16 and commit hash for non-local labels
  LDA LABEL_TYPE
  BNE .was_local_1          ; If local flag != 0, skip
  ; Store the address of the current global label
  CP16 TABP16, LABEL_SCOPE16
  JSR commit_cached_hash    ; Commit hash for local label lookups
.was_local_1:
  ; Store current program counter as the hash value into HEX16
  CP16 PC16, HEX16
  JSR store_hash_value
  JMP .skip_spaces_and_return_processed_flag
.has_equals:
  JSR read_value            ; Read the value after the equals, current char in CURR_CHAR
  JSR store_hash_value
.return_processed:
  JSR check_for_end_of_line
  BCC .err_unexpected_text  ; Unexpected content after value
  ; C=1 already set by check_for_end_of_line (line fully processed)
  RTS
.skip_spaces_and_return_processed_flag:
  JMP check_for_end_of_line ; Tail call - returns with C set if at end of line
.err_unexpected_text:
  JMP err_unexpected_text
.duplicate_label:
  JMP err_duplicate_label
