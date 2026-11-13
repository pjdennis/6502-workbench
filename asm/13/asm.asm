; Addresses
TOKEN      = $1D00      ; Buffer for the current token being read
LHASHTAB   = $1E00      ; Label hash table
*          = $2000      ; Code generates here
FILE_STACK = $F000      ; File stack will grow down from 1 below here
FWDREF_LIST  = $0200    ; Forward reference list (512 bytes, $0200-$03FF)
FWDREF_LIMIT = $03FE    ; Max pointer before add (room for entry + terminator)


  .zeropage

; Zero page locations
TEMP        DATA $00 ; 1 byte
PCL         DATA $00 ; 2 byte program counter
PCH         DATA $00 ; "
HEX1        DATA $00 ; 1 byte
HEX2        DATA $00 ; 1 byte
PASS        DATA $00 ; 1 byte $00 = pass 1 $FF = pass 2
MEMPL       DATA $00 ; 2 byte heap pointer
MEMPH       DATA $00 ; "
STARTED     DATA $00 ; flag to indicate output has started
CURR_FILE   DATA $00 ; current file handle
CURLINEL    DATA $00 ; Current line (L)
CURLINEH    DATA $00 ; Current line (H)
IN_ZEROPAGE DATA $00 ; Flag indicating if in zero page section
PC_SAVEL    DATA $00 ; Save location for PC when switching sections
PC_SAVEH    DATA $00 ; "
CURR_GLOBAL_HEAP_L DATA $00 ; Heap address of current global label string
CURR_GLOBAL_HEAP_H DATA $00 ; "
DEBUG_FLAG  DATA $00 ; Non-zero if debug output enabled
ADDR_MODE   DATA $00 ; Current addressing mode
INST_PTR_L  DATA $00 ; Pointer to instruction mode table entry
INST_PTR_H  DATA $00 ; "
OPERAND_L   DATA $00 ; Operand value (low byte)
OPERAND_H   DATA $00 ; Operand value (high byte)
IS_FWDREF   DATA $00 ; $FF if current label is forward ref (pass 1 only)
FWDREF_PASS1_L DATA $00 ; Forward ref pointer after pass 1 (low byte)
FWDREF_PASS1_H DATA $00 ; Forward ref pointer after pass 1 (high byte)

  .code


; Include files
  .include out/inst.asm.out   ; This goes first since the tables should start on a page boundary
  .include environment.asm
  .include common.asm
FS_FILENAME   = TOKEN
FS_CURR_FILE  = CURR_FILE
FS_CURR_LINEL = CURLINEL
FS_CURR_LINEH = CURLINEH
  .include file_stack.asm
  .include to_decimal.asm
  .include fwdref.asm


; Addressing mode constants (must match instgen16.asm)
MODE_NONE = $00   ; Implied (no operand)
MODE_ACC  = $01   ; Accumulator
MODE_IMM  = $02   ; Immediate
MODE_ZP   = $03   ; Zero page
MODE_ZPX  = $04   ; Zero page, X
MODE_ZPY  = $05   ; Zero page, Y
MODE_ABS  = $06   ; Absolute
MODE_ABSX = $07   ; Absolute, X
MODE_ABSY = $08   ; Absolute, Y
MODE_INDX = $09   ; Indirect, X - ($zp,X)
MODE_INDY = $0A   ; Indirect, Y - ($zp),Y
MODE_REL  = $0B   ; Relative (branches)
MODE_IND  = $0C   ; Indirect - JMP ($xxxx)
MODE_DATA = $FE   ; Pseudo-instruction (DATA)


; Error messages
err_label_not_found
  BRK
  DATA $01 "Label not found" $00

err_duplicate_label
  BRK
  DATA $02 "Duplicate label" $00

err_opcode_not_found
  BRK
  DATA $03 "Opcode not found" $00

err_branch_out_of_range
  BRK
  DATA $05 "Branch out of range" $00

err_value_out_of_range
  BRK
  DATA $06 "Value out of range" $00

err_invalid_hex
  BRK
  DATA $07 "Invalid hex" $00

err_pc_value_expected
  BRK
  DATA $08 "PC value expected" $00

err_closing_quote_not_found
  BRK
  DATA $09 "Closing quote not found" $00

err_cannot_move_pc_backwards
  BRK
  DATA $0A "Cannot move PC backwards" $00

err_unknown_directive
  BRK
  DATA $0B "Unknown directive" $00

err_filename_expected
  BRK
  DATA $0C "Filename expected" $00

err_usage
  BRK
  DATA $0D "Usage <assembler> <input> <output> [debug]" $00

err_no_file
  BRK
  DATA $0E "Attempt to read with no file open" $00

err_invalid_debug_arg
  BRK
  DATA $10 "Invalid third argument (expected 'debug')" $00

err_no_global_for_local
  BRK
  DATA $0F "No global label for local" $00

err_invalid_addressing_mode
  BRK
  DATA $11 "Invalid addressing mode for instruction" $00

err_invalid_char_literal
  BRK
  DATA $12 "Invalid character literal" $00

err_too_many_forward_refs
  BRK
  DATA $13 "Too many forward references" $00

err_fwdref_tracking
  BRK
  DATA $16 "Internal error - reference tracking" $00


; Read next character from file stack
; On entry CURR_FILE contains the current file handle
;          FILE_STACK is not empty
; On exit A contains the character read
;         C is set if at end of all file data
;         CURR_FILE is potentially updated with a new file handle
read_char
  LDA CURR_FILE
  BEQ .no_file
  JSR read
  BCS .at_end_file
  RTS
.at_end_file
  JSR pop_file_stack
  LDA CURR_FILE
  BEQ .at_end_all
  JMP read_char          ; Recursive tail call
.at_end_all
  SEC
  RTS
.no_file
  JMP err_no_file


select_label_hash_table
  LDA #<LHASHTAB
  STA HTPL
  LDA #>LHASHTAB
  STA HTPH
  RTS


; Emit value (pass 2 only) and increment PC
; On entry A contains the byte to emit
;          X contains the file handle to write to
; On exit A, X, Y are preserved
; TODO: Consolidate the PASS and IN_ZEROPAGE flags so that emit can
;       do a single check instead of two for suppression of output
emit
  INC PCL
  BNE .incremented
  INC PCH
.incremented
  BIT PASS
  BPL .skip            ; Skip writing during pass 1
  BIT IN_ZEROPAGE
  BMI .skip            ; Skip writing when in zero page section
  JMP write            ; Tail call
.skip
  RTS


; Read and discard characters up to the end of the current line
; On entry A contains the next character
; On exit A contains "\n"
;         X, Y are preserved
skip_rest_of_line
.loop
  CMP #'\n'
  BEQ .done
  JSR read_char
  JMP .loop
.done
  RTS


; Read and discard space characters
; On entry A contains the next character
; On exit A contains the next character following the last space
;         X, Y are preserved
skip_spaces
.loop
  CMP #' '
  BNE .done
  JSR read_char
  JMP .loop
.done
  RTS


; Check whether the next character (in A) is NOT a token character
; On entry A contains the next character
; On exit Z is set if current character terminates the current token, unset otherwise
;         A, X, Y are preserved
compare_end_of_token
  CMP #' '
  BEQ .end
  CMP #'\n'
  BEQ .end
  CMP #';'
  BEQ .end
  CMP #','             ; Comma terminates token for indexed modes
  BEQ .end
  CMP #')'             ; Close paren terminates for indirect modes
.end
  RTS


; Checks for end of line and skips past if at end
; On entry A contains next character
; On exit C set if end of line, clear otherwise
;         A contains next character
;         X, Y are preserved
check_for_end_of_line
  CMP #';'
  BEQ .end
  CMP #'\n'
  BEQ .done
  ; Not at end
  CLC
  RTS
.end
  JSR skip_rest_of_line
.done
  SEC
  RTS


; Reads token into TOKEN (zero terminated)
; On entry A contains first character of token
; On exit A contains next character after token
;         X is preserved
;         Y is not preserved
read_token
  STX TEMP
  LDX #$00
.loop
  JSR compare_end_of_token
  BEQ .done
  STA TOKEN,X
  INX
  JSR read_char
  JMP .loop
.done
  TAY                  ; Save next char
  LDA #$00
  STA TOKEN,X
  TYA                  ; Restore next char
  LDX TEMP
  RTS


; Check if token is a local label and set IS_LOCAL_LABEL flag
; On entry TOKEN contains the token (may start with '.')
; On exit IS_LOCAL_LABEL set appropriately ($FF if local, $00 if global)
;         TOKEN is NOT modified (no expansion)
;         A not preserved
;         X, Y are preserved
check_local_label
  LDA TOKEN
  CMP #'.'
  BNE .not_local
  ; Local label - Check if CURR_GLOBAL_HEAP is set (error check)
  LDA CURR_GLOBAL_HEAP_L
  ORA CURR_GLOBAL_HEAP_H
  BNE .have_global
  JMP err_no_global_for_local
.have_global
  LDA #$FF
  STA IS_LOCAL_LABEL
  RTS
.not_local
  LDA #$00
  STA IS_LOCAL_LABEL
  RTS


; Update CURR_GLOBAL_HEAP by looking up TOKEN in hash table
; Used in pass 2 to set the heap pointer for local label scope matching
; On entry TOKEN contains the global label name
;          IS_LOCAL_LABEL = 0 (global label)
; On exit CURR_GLOBAL_HEAP_L/H points to the token string on heap
;         CACHED_HASH is set (needed for subsequent local label lookups)
;         A, Y not preserved
;         X is preserved
update_global_heap_from_lookup
  JSR select_label_hash_table
  JSR find_in_hash       ; TABPL now points to token string
  JSR commit_cached_hash ; Commit hash since this is a non-assignment global
  ; After find_in_hash, TABPL points to token string (entry_start + 2)
  LDA TABPL
  STA CURR_GLOBAL_HEAP_L
  LDA TABPH
  STA CURR_GLOBAL_HEAP_H
  RTS


; Read a label, look up in the label hash table and return the associated value
; On entry A contains the first character of the label
; On exit HEX1 and HEX2 contains the MSB and LSB of the hash table value
;         A contains the next character following the token
;         X is preserved
;         Y is not preserved
; Raises 'Label not found' error if label is not found in hash table
read_and_find_existing_label
  JSR read_token
  PHA                  ; Save next char
  JSR check_local_label
  JSR select_label_hash_table
  JSR find_in_hash
  PLA                  ; Restore next char
  BCC .done            ; Label found
  BIT PASS
  BMI .pass2
  LDY #$00
  STY HEX1
  STY HEX2
.done
  RTS
.pass2
  JMP err_label_not_found


; Convert hex character to associated value
; On entry, A contains a hex character A-Z|0-9
; On exit A contains the value (0-15)
;         X, Y are preserved
; Raises 'Invalid hex' error if input is not a valid hex character
convert_hex_character
  CMP #'A'
  BCC .numeric         ; < 'A'
  SBC #'A'             ; Carry already set
  CMP #$06
  BCC .alpha_ok
  JMP err_invalid_hex
.alpha_ok
  CLC
  ADC #$0A             ; ADC #10
  RTS
.numeric
  SEC
  SBC #'0'
  CMP #$0A
  BCC .numeric_ok
  JMP err_invalid_hex
.numeric_ok
  RTS


; Reads 1 byte (2 character) hex value
; On entry A contains first hex character
; On exit A contains 2 character value (0-255)
;         X, Y are preserved
;         TEMP is not preserved
; Raises 'Invalid hex' error if encountering non-hex characters
read_hex_byte
  JSR convert_hex_character
  ASL A
  ASL A
  ASL A
  ASL A
  STA TEMP
  JSR read_char
  JSR convert_hex_character
  ORA TEMP
  RTS


; Reads 1 or 2 byte (2 or 4 character) hex value
; On entry, A contains the first hex character
; On exit C set if 2 bytes read clear if 1 byte read
;         A contains the next character
;         X, Y are preserved
; Rasises 'Invalid hex' error if encountering non-hex characters
read_hex_byte_or_word
  JSR read_hex_byte    ; Read 2nd hex character and convert
  STA HEX1
  JSR read_char        ; Read 3rd hex char or terminator
  JSR compare_end_of_token
  BNE .second
  CLC                  ; No second byte so return C = 0
  RTS
.second
  JSR read_hex_byte    ; Read 4th hex char and convert
  STA HEX2
  JSR read_char        ; Read next char
  SEC                  ; Second byte so return C = 1
  RTS


; Read 2 to 4 hex characters and emit 1 or 2 bytes
; When 2 bytes, emit LSB then MSB
; Uses HEX1, HEX2
; On entry A contains the first hex character
; On exit A contains next character
emit_hex
  JSR read_hex_byte_or_word ; Returns C = 1 if 2 bytes read
  TAY                       ; Save next char
  BCC .one
  LDA HEX2
  JSR emit
.one
  LDA HEX1
  JSR emit
  TYA                       ; Restore next char
  RTS


; Check for the existance of an assigned value (read the equals sign)
; On entry A contains the next character
; On exit C set if value exists; clear otherwise
;         A contains the next character
;         X, Y are preserved
check_for_value
  JSR skip_spaces
  CMP #'='
  BEQ .value
  CLC                  ; Did not find value so return C = 0
  RTS
.value
  SEC                  ; Found value so return C = 1
  RTS


; Read a value
; On entry A contains the next character
; On exit HEX2 and HEX1 contain the LSB and MSB of the value read
;         A contains the next character
;         X is preserved
;         Y is not preserved
; Raises 'Bad hex' error if non-hex characters were encountered
read_value
  JSR read_char        ; Read the character after the "="
  JSR skip_spaces
  CMP #'$'
  BEQ .hex_value
  JMP read_and_find_existing_label ; tail call
.hex_value
  JSR read_char
  JSR read_hex_byte_or_word
  BCS .done            ; 2 bytes were read
  ; 1 byte was read - shift into LSB position (HEX2)
  LDY HEX1
  STY HEX2
  LDY #$00
  STY HEX1
.done
  RTS


; Fast forward the program counter
; On entry PCL;PCH contains the current program counter
;          HEX2;HEX1 contains the new PC value
; On exit
; Raises 'Cannot move PC backwards' error if attempting to move PC backwards
update_pc
  BIT IN_ZEROPAGE
  BMI .no_fill
  BIT STARTED
  BMI .started
  DEC STARTED
  JMP .no_fill
.started
  LDA HEX1            ; High byte
  CMP PCH
  BCC .less
  BNE .notless
  LDA HEX2            ; Low byte
  CMP PCL
  BCC .less
.notless
  BIT PASS
  BPL .no_fill         ; skip writing during pass 1
.loop
  LDA HEX1
  CMP PCH
  BNE .loop_not_done
  LDA HEX2
  CMP PCL
  BEQ .loop_done
.loop_not_done
  LDA #$00
  JSR write
  INC PCL
  BNE .loop
  INC PCH
  JMP .loop
.loop_done
  RTS
.less
  JMP err_cannot_move_pc_backwards
.no_fill
  LDA HEX2
  STA PCL
  LDA HEX1
  STA PCH
.done
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
;        'Bad hex' error if non-hex characters were encountered
capture_label
  JSR read_token
  TAY                       ; Save next char
  LDA TOKEN
  CMP #'*'
  BNE .normal_label
  ; Set PC
  TYA                       ; Restore next char
  JSR check_for_value
  BCS .pc_value_present
  JMP err_pc_value_expected
.pc_value_present
  JSR read_value
  JSR skip_rest_of_line
  ; No need to retain next char as caller
  ; goes straight to next line
  JSR update_pc
  SEC                       ; Indicate line is fully processed
  RTS
.normal_label
  BIT PASS
  BPL .pass_1
  ; Pass 2 - don't capture label, but must track globals for local label scoping
  TYA
  PHA                       ; Save next char
  JSR check_local_label     ; Sets IS_LOCAL_LABEL, validates scope for locals
  ; Now continue with value reading
  PLA                       ; Restore next char
  JSR check_for_value
  BCS .has_equals_2         ; If = found, branch
  ; No = found - update global heap if this was not a local label
  PHA                       ; Save next char
  LDA IS_LOCAL_LABEL
  BNE .was_local_2          ; If local flag != 0, skip update
  JSR update_global_heap_from_lookup  ; Set CURR_GLOBAL_HEAP for local label lookups
.was_local_2
  PLA                       ; Restore next char
  JMP .skip_spaces_and_return_processed_flag
.has_equals_2
  JSR read_value
  JMP .skip_and_return_processed
.pass_1
  TYA
  PHA                       ; Save next char
  JSR check_local_label     ; Sets IS_LOCAL_LABEL, validates scope for locals
  ; Add key to hash table first (before read_value may overwrite TOKEN)
  JSR select_label_hash_table
  JSR hash_add
  BCS .duplicate_label
  ; Now read the value (TOKEN can be overwritten, but HTTPL/HTTPH preserved if no =)
  PLA                       ; Restore next char
  JSR check_for_value
  BCS .has_equals           ; If = found, branch
  ; No = found, save global label and use program counter
  PHA                       ; Save next char (before A is overwritten)
  ; Update CURR_GLOBAL_HEAP and commit hash for non-local labels
  LDA IS_LOCAL_LABEL
  BNE .was_local_1          ; If local flag != 0, skip
  ; Store the address of the current global label
  LDA TABPL
  STA CURR_GLOBAL_HEAP_L
  LDA TABPH
  STA CURR_GLOBAL_HEAP_H
  JSR commit_cached_hash    ; Commit hash for local label lookups
.was_local_1
  ; Store current program counter as the hash value
  LDA PCL
  STA HEX2
  LDA PCH
  STA HEX1
  JSR store_hash_value
  PLA                       ; Restore next char
  JMP .skip_spaces_and_return_processed_flag
.has_equals
  JSR read_value            ; Read the value after the equals
  PHA                       ; Save next char
  JSR store_hash_value
  PLA                       ; Restore next char
  JMP .skip_and_return_processed
.skip_spaces_and_return_processed_flag
  JSR skip_spaces
  JMP check_for_end_of_line ; Tail call - returns with C set if at end of line
.skip_and_return_processed
  JSR skip_rest_of_line
  SEC                       ; Indicate line is fully processed
  ; No need to retain next char as caller
  ; goes straight to next line
  RTS

.duplicate_label
  JMP err_duplicate_label


; Look up mnemonic and save pointer to mode:opcode data
; On entry A contains the first character of the mnemonic
; On exit A contains the next character
;         INST_PTR_L:INST_PTR_H points to mode:opcode data (past mnemonic)
;         X, Y are not preserved
; Raises 'Opcode not found' error if mnemonic is not found
lookup_mnemonic
  JSR read_token
  PHA                  ; Save next char
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCC .found
  JMP err_opcode_not_found
.found
  ; TABPL:TABPH points to mnemonic string (entry + 2)
  ; Skip past mnemonic to get to mode:opcode data
  LDY #$00
.skip_mnemonic
  LDA (TABPL),Y
  BEQ .end_of_mnemonic
  INY
  JMP .skip_mnemonic
.end_of_mnemonic
  ; Y points at null terminator, mode data starts at Y+1
  INY
  ; Calculate INST_PTR = TABPL + Y
  TYA
  CLC
  ADC TABPL
  STA INST_PTR_L
  LDA #$00
  ADC TABPH
  STA INST_PTR_H
  PLA                  ; Restore next char
  RTS


; Find opcode for addressing mode in mode:opcode list
; On entry INST_PTR_L:INST_PTR_H points to mode:opcode data
;          ADDR_MODE contains the addressing mode to find
; On exit C = 0 if found, A contains opcode
;         C = 1 if not found
;         X is preserved
;         Y is not preserved
find_opcode_for_mode
  LDY #$00
.loop
  LDA (INST_PTR_L),Y  ; Get mode byte
  CMP #$FF
  BEQ .not_found       ; End of list, mode not found
  CMP ADDR_MODE
  BEQ .found
  ; Not this mode, skip to next pair
  INY
  INY
  JMP .loop
.found
  INY
  LDA (INST_PTR_L),Y  ; Get opcode byte
  CLC
  RTS
.not_found
  SEC
  RTS


; Emit instruction based on addressing mode
; On entry INST_PTR_L:INST_PTR_H points to mode:opcode data
;          ADDR_MODE contains the addressing mode
;          OPERAND_L:OPERAND_H contains operand value (if applicable)
;          A contains the next character after operand (preserved for caller)
; On exit X is preserved
;         A contains the next character (preserved from entry)
;         Y is not preserved
; Raises error if addressing mode is not valid for this instruction
emit_instruction
  ; Preserve A (next char after operand) for caller
  PHA
  ; Check for DATA pseudo-instruction (MODE_DATA)
  LDA ADDR_MODE
  CMP #MODE_DATA
  BEQ .done            ; DATA pseudo handled separately in parameters loop
  ; Find opcode for this addressing mode
  JSR find_opcode_for_mode
  BCS .invalid_mode
  ; Emit the opcode
  JSR emit
  ; Now emit operand(s) based on mode
  LDA ADDR_MODE
  CMP #MODE_NONE
  BEQ .done            ; No operand for implied mode
  CMP #MODE_ACC
  BEQ .done            ; No operand for accumulator mode
  CMP #MODE_REL
  BEQ .emit_relative   ; Relative needs special handling
  ; Check if 1-byte or 2-byte operand
  CMP #MODE_IMM
  BEQ .one_byte
  CMP #MODE_ZP
  BEQ .one_byte
  CMP #MODE_ZPX
  BEQ .one_byte
  CMP #MODE_ZPY
  BEQ .one_byte
  CMP #MODE_INDX
  BEQ .one_byte_zp_only
  CMP #MODE_INDY
  BEQ .one_byte_zp_only
  ; 2-byte operand (absolute modes)
  LDA OPERAND_L
  JSR emit
  LDA OPERAND_H
  JSR emit
.done
  PLA
  RTS
.one_byte_zp_only
  ; ZP-only addressing modes (INDX, INDY) - validate operand <= $FF
  BIT PASS
  BPL .one_byte          ; Skip validation on pass 1
  LDA OPERAND_H
  BNE .zp_only_error
.one_byte
  LDA OPERAND_L
  JSR emit
  PLA
  RTS
.zp_only_error
  JMP err_value_out_of_range
.emit_relative
  ; Calculate relative offset: target - PC - 1
  BIT PASS
  BPL .emit_relative_pass1  ; Skip validation on pass 1
  CLC                  ; For the - 1
  LDA OPERAND_L
  SBC PCL
  STA OPERAND_L
  LDA OPERAND_H
  SBC PCH
  ; Check if within range
  CMP #$00
  BEQ .forward
  CMP #$FF
  BEQ .backward
  JMP err_branch_out_of_range
.forward
  LDA OPERAND_L
  BPL .emit_relative_ok
  JMP err_branch_out_of_range
.backward
  LDA OPERAND_L
  BMI .emit_relative_ok
  JMP err_branch_out_of_range
.emit_relative_pass1
  LDA OPERAND_L
.emit_relative_ok
  JSR emit
  PLA
  RTS
.invalid_mode
  JMP err_invalid_addressing_mode


; Read and emit quoted ASCII
; On entry A contains the first character within quotes
; On exit A contains the next character after the closing quote
;         X, Y are preserved
; Raises 'Closing quote not found' error if closing quote not found on current line
emit_quoted
.loop
  CMP #'\n'
  BEQ .err_closing_quote
  CMP #'"'
  BEQ .done
  CMP #'\\'
  BNE .not_escaped
  JSR read_char
  CMP #'\n'
  BEQ .err_closing_quote
  CMP #'n'
  BNE .not_escaped
  LDA #'\n'            ; Escaped "n" is linefeed
.not_escaped
  JSR emit
  JSR read_char
  JMP .loop
.done
  JSR read_char        ; Done; read next char
  RTS
.err_closing_quote
  JMP err_closing_quote_not_found


; Read and emit a 2 byte label value
; On entry A contains the first character of the label
; On exit A contains the next character
;         X, Y are not preserved
; Raises 'Label not found' error if label is not found
emit_label
  JSR read_and_find_existing_label
  TAY                  ; Save next char
  ; Emit low byte then high byte from table
  LDA HEX2
  JSR emit
  LDA HEX1
  JSR emit
  TYA                  ; Restore next char
  RTS


; Read and emit a 1 byte label value
; On entry A contains the first character of the label
; On exit A contains the next character
;         X, Y are not preserved
; Raises 'Label not found' error if label is not found
;        'Value of of range' error if value is > 255 (> 1 byte)
emit_label_byte
  JSR read_and_find_existing_label
  TAY                  ; Save next char
  BIT PASS
  BPL .ok              ; Skip validation on pass 1
  LDA HEX1
  BEQ .ok
  JMP err_value_out_of_range
.ok
  ; Emit low byte
  LDA HEX2
  JSR emit
  TYA                  ; Restore next char
  RTS


; Read and emit the least significant byte of a label value
; On entry A contains the first character of the label
; On exit A contains the next character
;         X, Y are not preserved
; Raises 'Label not found' error if label is not found
emit_label_lsb
  JSR read_and_find_existing_label
  TAY                  ; Save next char
  ; Emit low byte
  LDA HEX2
  JSR emit
  TYA                  ; Restore next char
  RTS


; Read and emit the most significant byte of a label value
; On entry A contains the first character of the label
; On exit A contains the next character
;         X, Y are not preserved
; Raises 'Label not found' error if label is not found
emit_label_msb
  JSR read_and_find_existing_label
  TAY                  ; Save next char
  ; Emit high byte
  LDA HEX1
  JSR emit
  TYA                  ; Restore next character
  RTS


; Read and emit a label value relative to PC
; On entry A contains the first character of the label
; On exit A contains the next character
;         X, Y are not preserved
; Raises 'Label not found' error if label is not found
;        'Branch out of range' error if distance from value to PC exceeds 1 signed byte
emit_label_relative
  JSR read_and_find_existing_label
  TAY                  ; Save next char
  BIT PASS
  BPL .ok              ; Skip calculations and validations on pass 1

  ; Calculate target - PC - 1
  CLC ; for the - 1
  LDA HEX2
  SBC PCL
  STA HEX2
  LDA HEX1
  SBC PCH

  CMP #$00
  BEQ .forward
  CMP #$FF
  BEQ .backward
  JMP err_branch_out_of_range

.forward
  LDA HEX2
  BPL .ok
  JMP err_branch_out_of_range

.backward
  LDA HEX2
  BMI .ok
  JMP err_branch_out_of_range

.ok
  JSR emit
  TYA                  ; Restore next char
  RTS


; Swap PCL;PCH with PC_SAVEL;PC_SAVEH
; On exit A, X, Y are preserved
swap_pc_with_save
  ; Swap PC L with save location
  LDA PCL
  PHA
  LDA PC_SAVEL
  STA PCL
  PLA
  STA PC_SAVEL
  ; Swap PC H with save location
  LDA PCH
  PHA
  LDA PC_SAVEH
  STA PCH
  PLA
  STA PC_SAVEH
  RTS


; On entry, A contains the first character of the directive
process_directive
  JSR read_token
  PHA                  ; Save next char
  ; Check for 'include'
  LDA #<directive_include
  STA TABPL
  LDA #>directive_include
  STA TABPH
  JSR compare_token
  BEQ .include
  ; Check for 'zeropage'
  LDA #<directive_zeropage
  STA TABPL
  LDA #>directive_zeropage
  STA TABPH
  JSR compare_token
  BEQ .zeropage
  ; Check for 'code'
  LDA #<directive_code
  STA TABPL
  LDA #>directive_code
  STA TABPH
  JSR compare_token
  BEQ .code
  ; Directive not recognized
  PLA                  ; Restore next char
  JMP err_unknown_directive
.include
  PLA                  ; Restore next char
  JSR skip_spaces
  JSR check_for_end_of_line
  BCC .get_name
  JMP err_filename_expected
.get_name
  JSR read_token
  JSR skip_rest_of_line
  JSR push_file_stack
  RTS
.zeropage
  BIT IN_ZEROPAGE
  BMI .in_zeropage
  LDA #$FF
  STA IN_ZEROPAGE
  JSR swap_pc_with_save
.in_zeropage
  PLA                  ; Restore next char
  JSR skip_rest_of_line
  RTS
.code
  BIT IN_ZEROPAGE
  BPL .in_code
  LDA #$00
  STA IN_ZEROPAGE
  JSR swap_pc_with_save
.in_code
  PLA                  ; Restore next char
  JSR skip_rest_of_line
  RTS

directive_include
  DATA "include" $00

directive_zeropage
  DATA "zeropage" $00

directive_code
  DATA "code" $00


; Read from input, assemble code and write to output
; On entry PASS indicates the current pass:
;            bit 7 clear = pass 1
;            bit 7 set = pass 2
;          X contains the file handle of the output file
; On exit X is preserved
;         A, Y are not preserved
assemble_code
  LDA #$00
  STA STARTED
  STA IN_ZEROPAGE
  STA PCL
  STA PCH
  STA PC_SAVEL
  STA PC_SAVEH
  STA CURLINEL
  STA CURLINEH
  STA CURR_GLOBAL_HEAP_L ; Initialize global heap pointer (0 = no global yet)
  STA CURR_GLOBAL_HEAP_H ; "
  STA IS_LOCAL_LABEL  ; Initialize local label flag
.line_loop
  JSR read_char
  BCC .character_read
  RTS                  ; At end of input
.character_read
  INC CURLINEL
  BNE .line_incremented
  INC CURLINEH
.line_incremented
  JSR check_for_end_of_line
  BCS .line_loop
  CMP #' '
  BEQ .line_starts_with_space
  JSR capture_label
  BCC .check_for_opcode
  JMP .line_loop
.line_starts_with_space
  JSR skip_spaces
  JSR check_for_end_of_line
  BCS .line_loop
.check_for_opcode
  CMP #'.'
  BNE .opcode
; Directive
  JSR read_char
  JSR process_directive
  JMP .line_loop
.opcode
  ; Read mnemonic and look up in instruction table
  JSR lookup_mnemonic
  ; A contains next char after mnemonic
  ; Parse operand to determine addressing mode
  JSR parse_operand_and_emit
  ; A contains next char after operand - skip to end of line
  JSR skip_spaces
  JSR check_for_end_of_line
  JMP .line_loop


; Parse operand and emit instruction
; On entry A contains the next character after mnemonic
;          INST_PTR_L:INST_PTR_H points to mode:opcode data
; On exit A contains the next character after operand
;         X, Y are not preserved
parse_operand_and_emit
  JSR skip_spaces
  JSR check_for_end_of_line
  BCS .implied_mode    ; No operand = implied mode
  ; Check for DATA pseudo-instruction
  STA TEMP            ; Save next char
  JSR check_for_data_pseudo
  BCS .not_data
  LDA TEMP            ; Restore next char for DATA processing
  JMP .data_mode
.not_data
  LDA TEMP            ; Restore next char
  ; Check operand format to determine mode
  CMP #'#'
  BNE .not_imm
  JMP .immediate_mode
.not_imm
  CMP #'('
  BNE .not_ind
  JMP .indirect_mode
.not_ind
  CMP #'$'
  BNE .not_hex
  JMP .hex_operand
.not_hex
  CMP #'<'
  BNE .not_lsb
  JMP .lsb_operand
.not_lsb
  CMP #'>'
  BNE .not_msb
  JMP .msb_operand
.not_msb
  ; Must be a label or accumulator mode
  ; Read the token first, then check if it's exactly "A"
  JMP .label_or_acc_operand

.implied_mode
  PHA                  ; Save next char (newline or semicolon)
  LDA #MODE_NONE
  STA ADDR_MODE
  LDA #$00
  STA OPERAND_L
  STA OPERAND_H
  PLA                  ; Restore next char
  JMP emit_instruction ; Tail call

.data_mode
  ; A contains next character for DATA processing
  JMP data_parameters_loop_entry

.accumulator_mode
  ; ASL A, LSR A, ROL A, ROR A
  ; Next char is on stack (from .label_or_acc_operand)
  LDA #MODE_ACC
  STA ADDR_MODE
  LDA #$00
  STA OPERAND_L
  STA OPERAND_H
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call

.immediate_mode
  ; #$xx or #<label or #>label or #label
  LDA #MODE_IMM
  STA ADDR_MODE
  JSR read_char        ; Skip #
  CMP #'$'
  BNE .imm_check_lsb
  JSR read_char
  JSR read_hex_byte
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  JSR read_char        ; Read char after hex value (for garbage check)
  JMP emit_instruction ; Tail call
.imm_check_lsb
  CMP #'<'
  BNE .imm_check_msb
  ; #<label - low byte of label
  JSR read_char        ; Skip <
  JSR read_and_find_existing_label
  PHA                  ; Save next char
  LDA HEX2            ; Low byte
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char
  JMP emit_instruction ; Tail call
.imm_check_msb
  CMP #'>'
  BNE .imm_check_char
  ; #>label - high byte of label
  JSR read_char        ; Skip >
  JSR read_and_find_existing_label
  PHA                  ; Save next char
  LDA HEX1            ; High byte
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char
  JMP emit_instruction ; Tail call
.imm_check_char
  CMP #'\''
  BNE .imm_label
  ; #'x' - character literal (must be exactly 1 char)
  JSR read_char        ; Skip opening quote
  CMP #'\''
  BEQ .imm_char_empty  ; Empty literal - error
  CMP #'\\'
  BEQ .imm_char_escape
  ; Regular character
  STA OPERAND_L
  JMP .imm_char_check_close
.imm_char_escape
  ; Escape sequence: \n \\ \' \"
  JSR read_char
  CMP #'n'
  BNE .imm_esc_not_n
  LDA #'\n'            ; Newline
  JMP .imm_esc_done
.imm_esc_not_n
  CMP #'\\'
  BNE .imm_esc_not_bs
  LDA #'\\'            ; Backslash
  JMP .imm_esc_done
.imm_esc_not_bs
  CMP #'\''
  BNE .imm_esc_not_sq
  LDA #'\''             ; Single quote
  JMP .imm_esc_done
.imm_esc_not_sq
  CMP #'"'
  BNE .imm_esc_invalid
  LDA #'"'            ; Double quote (optional escape)
.imm_esc_done
  STA OPERAND_L
.imm_char_check_close
  JSR read_char        ; Should be closing quote
  CMP #'\''
  BNE .imm_char_too_long
  LDA #$00
  STA OPERAND_H
  JSR read_char        ; Read next char for garbage check
  JMP emit_instruction ; Tail call
.imm_char_empty
  JMP err_invalid_char_literal
.imm_char_too_long
  JMP err_invalid_char_literal
.imm_esc_invalid
  JMP err_invalid_char_literal
.imm_label
  JSR read_and_find_existing_label
  PHA                  ; Save next char
  LDA HEX2            ; Low byte of label value
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H       ; Immediate only uses low byte
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call

.indirect_mode
  ; ($xx),Y - indirect indexed Y (1-byte operand)
  ; ($xx,X) - indirect indexed X (1-byte operand)
  ; ($xxxx) - indirect absolute for JMP (2-byte operand)
  JSR read_char        ; Skip (
  CMP #'$'
  BNE .ind_label
  JSR read_char
  JSR read_hex_byte_or_word
  ; C = 1 if 2 bytes, C = 0 if 1 byte
  ; A contains next char after hex value
  BCC .ind_hex_one_byte
  ; 2 byte value - store operand and set flag
  PHA                  ; Save next char
  LDA HEX2
  STA OPERAND_L
  LDA HEX1
  STA OPERAND_H
  LDA #$FF             ; Flag: 2-byte operand
  STA TEMP
  PLA                  ; Restore next char
  JMP .indirect_check_suffix
.ind_hex_one_byte
  ; 1 byte value
  PHA                  ; Save next char
  LDA HEX1
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  STA TEMP            ; Flag: 1-byte operand (0)
  PLA                  ; Restore next char
  JMP .indirect_check_suffix
.ind_label
  JSR read_and_find_existing_label
  PHA                  ; Save next char
  LDA HEX2
  STA OPERAND_L
  LDA HEX1
  STA OPERAND_H
  ; For labels, check if high byte is non-zero to determine size
  ORA HEX1            ; A = HEX1
  BNE .ind_label_2byte
  LDA #$00             ; Flag: 1-byte (ZP label)
  JMP .ind_label_done
.ind_label_2byte
  LDA #$FF             ; Flag: 2-byte (ABS label)
.ind_label_done
  STA TEMP
  PLA                  ; Restore next char
.indirect_check_suffix
  ; A contains next char (should be ) or ,)
  CMP #','
  BEQ .indirect_x
  ; Assume ), check for ,Y or just )
  JSR read_char        ; Read char after )
  CMP #','
  BNE .ind_no_suffix
  JSR read_char        ; Should be Y
  CMP #'Y'
  BNE .ind_err
  JSR read_char        ; Read char after Y for garbage check
  PHA
  LDA #MODE_INDY
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.indirect_x
  JSR read_char        ; Should be X
  CMP #'X'
  BNE .ind_err
  JSR read_char        ; Should be )
  CMP #')'
  BNE .ind_err
  JSR read_char        ; Read char after ) for garbage check
  PHA
  LDA #MODE_INDX
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.ind_no_suffix
  ; Just ($xxxx) - JMP indirect mode (must be 2-byte operand)
  ; A already contains next char (after ))
  PHA                  ; Save next char
  LDA #MODE_IND
  STA ADDR_MODE
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call
.ind_err
  JMP err_invalid_addressing_mode

.hex_operand
  ; $xx or $xxxx, possibly with ,X or ,Y suffix
  JSR read_char        ; Skip $
  JSR read_hex_byte_or_word
  ; C = 1 if 2 bytes, C = 0 if 1 byte
  PHA                  ; Save next char
  BCC .hex_one_byte
  ; 2 byte value - check for indexed modes
  LDA HEX2
  STA OPERAND_L
  LDA HEX1
  STA OPERAND_H
  PLA                  ; Restore next char
  JMP .check_index_suffix_abs
.hex_one_byte
  ; 1 byte value - could be zero page or absolute (check index suffix)
  LDA HEX1
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char
  JMP .check_index_suffix_zp

.check_index_suffix_zp
  ; Check for ,X or ,Y on zero page value
  CMP #','
  BNE .zp_no_index
  JSR read_char        ; X or Y
  CMP #'X'
  BEQ .zpx
  CMP #'Y'
  BEQ .zpy
  JMP err_invalid_addressing_mode
.zpx
  JSR read_char        ; Read char after X for garbage check
  PHA
  LDA #MODE_ZPX
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.zpy
  JSR read_char        ; Read char after Y for garbage check
  PHA
  LDA #MODE_ZPY
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.zp_no_index
  ; A contains next char for garbage check
  PHA                  ; Save next char
  ; Check if this is a branch instruction (MODE_REL)
  JSR check_if_branch
  BCC .is_branch_zp
  ; Not a branch - use zero page mode
  LDA #MODE_ZP
  STA ADDR_MODE
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call
.is_branch_zp
  LDA #MODE_REL
  STA ADDR_MODE
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call

.check_index_suffix_abs
  ; Check for ,X or ,Y on absolute value
  CMP #','
  BNE .abs_no_index
  JSR read_char        ; X or Y
  CMP #'X'
  BEQ .absx
  CMP #'Y'
  BEQ .absy
  JMP err_invalid_addressing_mode
.absx
  JSR read_char        ; Read char after X for garbage check
  PHA
  LDA #MODE_ABSX
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.absy
  JSR read_char        ; Read char after Y for garbage check
  PHA
  LDA #MODE_ABSY
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.abs_no_index
  ; A contains next char for garbage check
  PHA                  ; Save next char
  ; Check if this is a branch instruction (MODE_REL)
  JSR check_if_branch
  BCC .is_branch_abs
  ; Not a branch - use absolute mode
  LDA #MODE_ABS
  STA ADDR_MODE
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call
.is_branch_abs
  LDA #MODE_REL
  STA ADDR_MODE
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call

.lsb_operand
  ; <label - emit low byte of label
  JSR read_char        ; Skip <
  LDA #MODE_IMM
  STA ADDR_MODE
  JSR read_and_find_existing_label
  PHA                  ; Save next char
  LDA HEX2
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call

.msb_operand
  ; >label - emit high byte of label
  JSR read_char        ; Skip >
  LDA #MODE_IMM
  STA ADDR_MODE
  JSR read_and_find_existing_label
  PHA                  ; Save next char
  LDA HEX1
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call

.label_or_acc_operand
  ; Could be accumulator mode (just "A") or a label
  ; Read the token first
  JSR read_token
  PHA                  ; Save next char
  ; Check if token is exactly "A" (accumulator mode)
  ; Use Y for indexed addressing (X holds output file handle globally)
  LDY #$00
  LDA TOKEN,Y
  CMP #'A'
  BNE .is_label        ; First char not A, must be label
  INY
  LDA TOKEN,Y
  BNE .is_label        ; Second char not null, must be label like "ABSOLUTE"
  ; Token is exactly "A" - accumulator mode
  ; Next char stays on stack for .accumulator_mode
  JMP .accumulator_mode
.is_label
  ; Look up the token we already read (TOKEN already contains it)
  JSR check_local_label
  JSR select_label_hash_table
  JSR find_in_hash
  BCC .label_found
  ; Label not found - check pass
  BIT PASS
  BMI .label_not_found_pass2
  ; Pass 1 - forward reference: set IS_FWDREF
  LDY #$FF
  STY IS_FWDREF
  LDY #$00
  STY HEX1
  STY HEX2
  JMP .label_continue
.label_not_found_pass2
  JMP err_label_not_found
.label_found
  ; Label found - clear forward ref flag
  LDY #$00
  STY IS_FWDREF
.label_continue
  ; Next char is still on stack from earlier PHA
  LDA HEX2
  STA OPERAND_L
  LDA HEX1
  STA OPERAND_H
  ; Check if this is a branch instruction
  JSR check_if_branch
  BCC .label_is_branch
  ; Not a branch - check for indexed mode BEFORE emitting
  ; Labels always use absolute addressing (conservative for forward refs)
  PLA                  ; Restore next char (might be comma)
  CMP #','
  BNE .label_abs_no_index
  ; Has index suffix - read X or Y
  JSR read_char
  CMP #'X'
  BEQ .label_absx
  CMP #'Y'
  BEQ .label_absy
  JMP err_invalid_addressing_mode
.label_absx
  JSR read_char        ; Read char after X for garbage check
  PHA
  LDA #MODE_ZPX
  STA ADDR_MODE
  JSR handle_fwdref_mode
  BCS .label_absx_use_abs
  PLA
  JMP emit_instruction ; Tail call
.label_absx_use_abs
  LDA #MODE_ABSX
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.label_absy
  JSR read_char        ; Read char after Y for garbage check
  PHA
  LDA #MODE_ZPY
  STA ADDR_MODE
  JSR handle_fwdref_mode
  BCS .label_absy_use_abs
  PLA
  JMP emit_instruction ; Tail call
.label_absy_use_abs
  LDA #MODE_ABSY
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.label_abs_no_index
  ; A contains next char for garbage check
  PHA
  LDA #MODE_ZP
  STA ADDR_MODE
  JSR handle_fwdref_mode
  BCS .label_use_abs
  PLA
  JMP emit_instruction ; Tail call
.label_use_abs
  LDA #MODE_ABS
  STA ADDR_MODE
  PLA
  JMP emit_instruction ; Tail call
.label_is_branch
  ; Next char is still on stack
  LDA #MODE_REL
  STA ADDR_MODE
  PLA                  ; Restore next char for garbage check
  JMP emit_instruction ; Tail call


; Determine whether to use ZP or ABS addressing for a label operand
; Considers: ZP mode availability, forward ref status, operand value
; On entry: ADDR_MODE set to ZP variant (MODE_ZP, MODE_ZPX, MODE_ZPY)
;           OPERAND_L:OPERAND_H contain operand value
;           IS_FWDREF set if operand is forward reference (pass 1)
;           PASS indicates current pass
; On exit: C=1 if must use ABS variant, C=0 if can use ZP variant
;          In pass 1 with forward ref: adds PC to forward ref list
;          In pass 2: consumes forward ref list entry if present
;          A, Y not preserved, X preserved
handle_fwdref_mode
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
.pass2
  ; Pass 2 - check the forward ref list
  JSR check_forward_ref    ; Returns C=1 if in list, C=0 if not
  BCS .use_abs             ; Was in list (forced to ABS), return C=1
.check_value
  ; Check if value requires absolute addressing (>= $100)
  LDA OPERAND_H
  BNE .use_abs             ; Value >= $100, must use ABS
  ; Can use ZP
  CLC
  RTS
.use_abs
  SEC
  RTS


; Check if current instruction is a branch (supports MODE_REL)
; On entry INST_PTR_L:INST_PTR_H points to mode:opcode data
; On exit C = 0 if branch, C = 1 if not branch
;         A, Y not preserved, X preserved
check_if_branch
  LDY #$00
.loop
  LDA (INST_PTR_L),Y
  CMP #$FF
  BEQ .not_branch
  CMP #MODE_REL
  BEQ .is_branch
  INY
  INY
  JMP .loop
.is_branch
  CLC
  RTS
.not_branch
  SEC
  RTS


; Check if instruction is DATA pseudo
; On entry INST_PTR_L:INST_PTR_H points to mode:opcode data
; On exit C = 0 if DATA, C = 1 if not DATA
;         A, Y not preserved, X preserved
check_for_data_pseudo
  LDY #$00
  LDA (INST_PTR_L),Y
  CMP #MODE_DATA
  BEQ .is_data
  SEC
  RTS
.is_data
  CLC
  RTS


; DATA pseudo-instruction parameter loop
data_parameters_loop
data_parameters_loop_entry
  JSR skip_spaces
  JSR check_for_end_of_line
  BCS .data_done
  CMP #'"'            ; Quoted string
  BNE .data_check_hex
  JSR read_char
  JSR emit_quoted
  JMP data_parameters_loop
.data_check_hex
  CMP #'$'             ; Hex value
  BNE .data_check_lsb
  JSR read_char
  JSR emit_hex
  JMP data_parameters_loop
.data_check_lsb
  CMP #'<'             ; LSB of label
  BNE .data_check_msb
  JSR read_char
  JSR emit_label_lsb
  JMP data_parameters_loop
.data_check_msb
  CMP #'>'             ; MSB of label
  BNE .data_label
  JSR read_char
  JSR emit_label_msb
  JMP data_parameters_loop
.data_label
  JSR emit_label       ; Full 2-byte label value
  JMP data_parameters_loop
.data_done
  RTS


; Opens the file with name from the first command line argument, pushing
; to the file stack
; On exit X is preserved
open_input
  TXA
  PHA
  LDA #$00
  JSR argv
  STA TABPL
  STX TABPH
  PLA
  TAX
  LDY #$FF
.loop
  INY
  LDA (TABPL),Y
  STA TOKEN,Y
  BNE .loop
  JMP push_file_stack ; tail call


; Check if string at TABPL;TABPH equals "debug"
; On exit C = 0 if equal, C = 1 if not equal
;         A, Y are not preserved
check_debug_string
  LDY #$00
.loop
  LDA (TABPL),Y
  CMP str_debug,Y
  BNE .not_equal
  CMP #$00
  BEQ .equal
  INY
  JMP .loop
.equal
  CLC
  RTS
.not_equal
  SEC
  RTS

str_debug
  DATA "debug" $00


; Entry point
start
  ; Initialize file stack early so interrupt handler works correctly
  JSR file_stack_init
  ; Initialize debug flag to 0
  LDA #$00
  STA DEBUG_FLAG
  ; Check argument count (must be 2 or 3)
  JSR argc
  CMP #$02
  BEQ .args_ok
  CMP #$03
  BEQ .check_debug_arg
  JMP err_usage
.check_debug_arg
  ; Third argument present - must be "debug"
  LDA #$02
  JSR argv
  STA TABPL
  STX TABPH
  JSR check_debug_string
  BCS .invalid_debug_arg
  ; Valid "debug" argument - set flag
  LDA #$FF
  STA DEBUG_FLAG
  JMP .args_ok
.invalid_debug_arg
  JMP err_invalid_debug_arg
.args_ok
  JSR init_heap
  JSR select_label_hash_table
  JSR init_hash_table

  LDA #$00
  STA CURR_FILE
  STA PASS            ; Bit 7 = 0 (pass 1)
  JSR init_fwdref_list
  JSR open_input

  ; Open output file
  LDA #$01
  JSR argv
  JSR openout
  TAX

  JSR assemble_code
  JSR finalize_fwdref_list
  ; Capture forward ref pointer after pass 1
  LDA FWDREF_L
  STA FWDREF_PASS1_L
  LDA FWDREF_H
  STA FWDREF_PASS1_H

  LDA #$FF
  STA PASS            ; Bit 7 = 1 (pass 2)
  JSR reset_fwdref_ptr
  JSR open_input
  JSR assemble_code
  ; Verify forward ref pointer matches pass 1
  LDA FWDREF_L
  CMP FWDREF_PASS1_L
  BNE .fwdref_error
  LDA FWDREF_H
  CMP FWDREF_PASS1_H
  BNE .fwdref_error
  JMP .fwdref_ok
.fwdref_error
  JMP err_fwdref_tracking
.fwdref_ok

  ; Close output file
  TXA
  JSR close

  ; Print heap usage if debug flag is set
  LDA DEBUG_FLAG
  BEQ .skip_debug_output
  LDA #<msg_heap_used
  STA TABPL
  LDA #>msg_heap_used
  STA TABPH
  JSR show_message
  ; Calculate heap used: MEMPL - HEAP
  SEC
  LDA MEMPL
  SBC #<HEAP
  STA TO_DECIMAL_VALUE_L
  LDA MEMPH
  SBC #>HEAP
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA #<msg_bytes
  STA TABPL
  LDA #>msg_bytes
  STA TABPH
  JSR show_message
  ; Print forward reference count
  LDA #<msg_fwdref_count
  STA TABPL
  LDA #>msg_fwdref_count
  STA TABPH
  JSR show_message
  ; Calculate forward ref count: (FWDREF_PASS1 - FWDREF_LIST) / 2
  SEC
  LDA FWDREF_PASS1_L
  SBC #<FWDREF_LIST
  STA TO_DECIMAL_VALUE_L
  LDA FWDREF_PASS1_H
  SBC #>FWDREF_LIST
  STA TO_DECIMAL_VALUE_H
  ; Divide by 2 (16-bit right shift, match v11 workaround for identical binary)
  LDA TO_DECIMAL_VALUE_H
  LSR A                      ; carry = old bit 0 of H
  STA TO_DECIMAL_VALUE_H     ; H >> 1 (always 0)
  LDA TO_DECIMAL_VALUE_L     ; carry preserved (LDA doesn't affect C)
  BCC .no_high_bit
  LSR A                      ; L >> 1
  CLC
  ADC #$80                   ; bring in carry from H as bit 7
  JMP .store_count
.no_high_bit
  LSR A                      ; L >> 1, bit 7 = 0
.store_count
  STA TO_DECIMAL_VALUE_L
  JSR show_decimal
  LDA #'\n'
  JSR write_d
.skip_debug_output

  BRK
  DATA $00             ; Success code


; Interrupt handler, entered upon BRK
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
  DATA "Error " $00
msg_error_line
  DATA " at line " $00
msg_error_file
  DATA " in file " $00
msg_heap_used
  DATA "Heap used: " $00
msg_bytes
  DATA " bytes\n" $00
msg_fwdref_count
  DATA "Forward references forced to absolute: " $00


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


HEAP                   ; Heap goes after the program code


* = $FFFC
  DATA start           ; Reset vector
  DATA interrupt       ; Interrupt vector
