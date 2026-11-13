; Addresses
FWDREF_LIST   = $0200             ; Forward reference list (512 bytes, $0200-$03FF)
FWDREF_LIMIT  = FWDREF_LIST+$0200 ; Limit for forward reference list data
SCOPE_STACK   = $0400             ; Label scope stack for macro expansions (256 bytes, $0400-$04FF)
SCOPE_LIMIT   = SCOPE_STACK+$0100 ; Limit for scope stack
MACRO_ARG_BUF = $0500             ; Temp buffer for macro args during expansion (256 bytes)
TOKEN         = $0600             ; Buffer for the current token being read
LHASHTAB      = $0700             ; Label hash table
IFDEF_DECISIONS = $0800           ; Buffer for .ifdef decisions (255 bytes, $0800-$08FE)
IFDEF_INDEX     = $08FF           ; Current index into IFDEF_DECISIONS buffer
*             = $2000             ; Code generates here
FILE_STACK    = $F000             ; File stack will grow down from 1 below here


  .zeropage

; Zero page locations
TEMP        .data $00 ; 1 byte
PCL         .data $00 ; 2 byte program counter
PCH         .data $00 ; "
HEX1        .data $00 ; 1 byte (high byte - also aliased as OPERAND_H)
HEX2        .data $00 ; 1 byte (low byte - also aliased as OPERAND_L)
PASS        .data $00 ; 1 byte $00 = pass 1 $FF = pass 2
MEMPL       .data $00 ; 2 byte heap pointer
MEMPH       .data $00 ; "
STARTED     .data $00 ; flag to indicate output has started
CURR_FILE   .data $00 ; current file handle
CURLINEL    .data $00 ; Current line (L)
CURLINEH    .data $00 ; Current line (H)
CURR_OUT_FILE .data $00 ; Current output file (for closing on error)
IN_ZEROPAGE .data $00 ; Flag indicating if in zero page section
PC_SAVEL    .data $00 ; Save location for PC when switching sections
PC_SAVEH    .data $00 ; "
CURR_GLOBAL_HEAP_L .data $00 ; Heap address of current global label string
CURR_GLOBAL_HEAP_H .data $00 ; "
ADDR_MODE   .data $00 ; Current addressing mode
INST_PTR_L  .data $00 ; Pointer to instruction mode table entry
INST_PTR_H  .data $00 ; "
OPERAND_L = HEX2      ; Operand value (low byte) - alias for HEX2
OPERAND_H = HEX1      ; Operand value (high byte) - alias for HEX1
IS_FWDREF   .data $00 ; $FF if current label is forward ref (pass 1 only)
EXPR_ACCU_L .data $00 ; Expression accumulator low byte
EXPR_ACCU_H .data $00 ; Expression accumulator high byte
EXPR_FWDREF .data $00 ; Accumulated forward ref flag
COND_DEPTH  .data $00 ; Conditional assembly nesting depth
SKIP_DEPTH  .data $00 ; Depth where skipping started (0 = not skipping)
ARG_COUNT   .data $00 ; Total command line argument count
ARG_INDEX   .data $00 ; Current argument index being processed
NEXT_CHAR   .data $00 ; Last character read by read_char
IN_MACRO_DEF    .data $00 ; Flag: currently capturing macro body ($FF = capturing)
MACRO_DEF_PTR_L .data $00 ; Heap pointer where macro body is being stored
MACRO_DEF_PTR_H .data $00 ; "
MACRO_ENTRY_L   .data $00 ; Original macro hash entry address (for recursion check)
MACRO_ENTRY_H   .data $00 ; "

  .ifdef enable_debug
DEBUG_FLAG  .data $00 ; Non-zero if debug output enabled
FWDREF_PASS1_L .data $00 ; Forward ref pointer after pass 1 (low byte)
FWDREF_PASS1_H .data $00 ; Forward ref pointer after pass 1 (high byte)
  .endif


  .code

; Include files
  .include out/inst.asm.out   ; This goes first since the tables should start on a page boundary
  .include environment.asm
  .include common.asm
  .include label_scope.asm
FS_FILENAME    = TOKEN
FS_CURR_FILE   = CURR_FILE
FS_CURR_LINEL  = CURLINEL
FS_CURR_LINEH  = CURLINEH
FS_NEXT_CHAR   = NEXT_CHAR
FS_ERR_NO_FILE = err_no_file
FS_POP_MEMORY_HOOK = pop_label_scope
  .include file_stack.asm
read_char = file_stack_read_char
  .include errors.asm
  .include fwdref.asm



; ============================================================================
; TIER 1: PRIMITIVES
; Basic operations with no dependencies on other functions
; ============================================================================

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
  BEQ .end
  CMP #'+'             ; Plus terminates for expressions
  BEQ .end
  CMP #'-'             ; Minus terminates for expressions
  BEQ .end
  CMP #'<'             ; Less-than terminates for shift operators
  BEQ .end
  CMP #'>'             ; Greater-than terminates for shift operators
  BEQ .end
  CMP #':'             ; Colon terminates for optional label suffix
  BEQ .end
  CMP #'='             ; Equals terminates for label assignments
.end
  RTS


; Skip characters until token terminator
; On exit: A contains terminating character
skip_token
  JSR read_char
  JSR compare_end_of_token
  BNE skip_token
  RTS


; Convert hex character to associated value
; On entry, A contains a hex character A-Z|0-9
; On exit A contains the value (0-15)
;         X, Y are preserved
; Raises 'Invalid hex' error if input is not a valid hex character
convert_hex_character
  CMP #'A'
  BCS .alpha           ; >= 'A'
  ; Numeric path: '0'-'9' → 0-9
  SEC
  SBC #'0'
  CMP #'9'-'0'+$01     ; Check if result 0-9
  BCS .error           ; >= 10, invalid
  RTS
.alpha
  ; Alpha path: 'A'-'F' → 10-15
  SBC #'A'             ; Carry already set from CMP
  CMP #'F'-'A'+$01     ; Check if result 0-5
  BCS .error           ; >= 6, invalid
  ADC #'9'-'0'+$01     ; Add 10 (carry clear from CMP)
  RTS
.error
  JMP err_invalid_hex


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


; ============================================================================
; TIER 2: CHARACTER I/O & SKIPPING
; File reading and character classification
; ============================================================================

; read_char is provided by file_stack21.asm

; Read and discard space characters
; On entry NEXT_CHAR contains the next character
; On exit A contains the next character following the last space
;         X, Y are preserved
skip_spaces
  LDA NEXT_CHAR
.loop
  CMP #' '
  BNE .done
  JSR read_char
  BCC .loop
.done
  RTS


; Read and discard characters up to the end of the current line
; On entry NEXT_CHAR contains the next character
; On exit A contains "\n"
;         X, Y are preserved
skip_rest_of_line
  LDA NEXT_CHAR
.loop
  CMP #'\n'
  BEQ .done
  JSR read_char
  BCC .loop
.done
  RTS


; Skips spaces and checks for end of line and skips past if at end
; On entry NEXT_CHAR contains next character
; On exit C set if end of line, clear otherwise
;         A contains next character
;         X, Y are preserved
check_for_end_of_line
  JSR skip_spaces
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


; ============================================================================
; TIER 3: TOKEN & HEX READING
; Token and hexadecimal value parsing
; ============================================================================

; Reads 1 byte (2 character) hex value
; On entry A contains first hex character
; On exit A contains 2 character value (0-255)
;         X, Y are preserved
;         TEMP is not preserved
; Raises 'Invalid hex' error if encountering non-hex characters
read_hex_byte
  JSR convert_hex_character
  ASL
  ASL
  ASL
  ASL
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


; Reads token into TOKEN (zero terminated)
; On entry A contains first character of token
; On exit NEXT_CHAR contains next character after token
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
  BCC .loop
.done
  LDA #$00
  STA TOKEN,X
  LDX TEMP
  RTS


; ============================================================================
; TIER 4: VALUE PARSING
; Parse values: hex, labels, character literals
; ============================================================================

; Parse character literal: 'x' or escape sequences
; On entry: A contains the opening quote character '
; On exit: A contains next character (for garbage checking)
;          OPERAND_L contains character value
;          OPERAND_H contains $00
;          X preserved, Y not preserved
; Raises 'Invalid character literal' error on malformed input
parse_char_literal
  JSR read_char        ; Skip opening quote
  CMP #'\''
  BEQ .char_invalid    ; Empty literal - error
  CMP #'\\'
  BEQ .char_escape
  CMP #'\n'
  BEQ .char_invalid    ; Newline without closing quote - error
  ; Regular character
  STA OPERAND_L
  JMP .char_check_close
.char_escape
  ; Escape sequence: \n \\ \'
  JSR read_char
  CMP #'n'
  BNE .esc_not_n
  LDA #'\n'            ; Only \n needs value substitution
  BNE .esc_done        ; Always taken (\n = $0A != 0)
.esc_not_n
  ; For \\ and \', character is already in A
  CMP #'\\'
  BEQ .esc_done
  CMP #'\''
  BNE .char_invalid
.esc_done
  STA OPERAND_L
.char_check_close
  JSR read_char        ; Should be closing quote
  CMP #'\''
  BNE .char_invalid
  LDA #$00
  STA OPERAND_H
  ; Read next char for garbage check
  JMP read_char        ; Tail call
.char_invalid
  JMP err_invalid_char_literal


; Check for the existance of an assigned value (read the equals sign)
; On entry NEXT_CHAR contains the next character
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
; Supports: $xx, $xxxx, label, <label, >label
read_value
  JSR read_char        ; Read the character after the "="
  JSR skip_spaces
  JSR parse_value      ; Returns value in OPERAND_L/H (aliased to HEX2/HEX1)
  ; No copy needed - OPERAND_L/H are aliased to HEX2/HEX1
  RTS


; Parse a term (single value): $12, $1234, 'x', label, <label, or >label
; On entry A contains first character
; On exit  NEXT_CHAR contains next character
;          OPERAND_L, OPERAND_H contain parsed value
;          IS_FWDREF set if bare label was forward ref (pass 1 only)
;          C=1 if bare label, C=0 otherwise
;          X is preserved
;          Y is not preserved
parse_term
  CMP #'$'
  BEQ .hex
  CMP #'\''
  BEQ .char_literal
  ; Otherwise: bare label - needs forward ref tracking
  JSR read_token       ; Next char now in NEXT_CHAR
  ; Look up the token
  JSR check_local_label
  JSR select_label_hash_table
  JSR find_in_hash
  BCC .label_found
  ; Not found - if non-local and in macro expansion, try local hash (for parameters)
  LDA IS_LOCAL_LABEL
  BNE .really_not_found      ; Already tried local hash
  LDA EXPANSION_ID_L
  ORA EXPANSION_ID_H
  BEQ .really_not_found      ; Not in macro expansion
  ; In macro expansion - try local hash (parameters are stored with local hash)
  LDA #$FF
  STA IS_LOCAL_LABEL
  JSR find_in_hash
  BCC .label_found
.really_not_found
  ; Label not found - check pass
  BIT PASS
  BMI .label_not_found_pass2
  ; Pass 1 - forward reference: use zero values
  LDY #$FF
  STY IS_FWDREF        ; Mark as forward reference
  LDY #$00
  STY HEX1
  STY HEX2
  BEQ .label_store     ; Always taken
.label_not_found_pass2
  JMP err_label_not_found
.label_found
  ; Label found - clear forward ref flag
  LDA #$00
  STA IS_FWDREF
.label_store
  ; OPERAND_L/H already set (aliased to HEX2/HEX1)
  SEC                  ; Signal 2-byte value (from bare label)
  RTS
.hex
  JSR read_char        ; Skip $
  JSR read_hex_byte_or_word  ; Returns next char in A, stores in HEX1/HEX2
  BCC .one_byte
  ; Two bytes (4 hex digits) - OPERAND_L/H already set (aliased to HEX2/HEX1)
  SEC                  ; Signal 2-byte value (4 hex digits)
  RTS
.one_byte
  ; One byte in HEX1 - need to move to OPERAND_L and zero OPERAND_H
  LDA HEX1
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  CLC                  ; Signal 1-byte value (2 hex digits)
  RTS
.char_literal
  JSR parse_char_literal
  ; Result in OPERAND_L, OPERAND_H=$00
  CLC                  ; Signal 1-byte value (character)
  RTS


; Parse a value (expression with optional byte selector prefix)
; On entry: A contains first character
; On exit: NEXT_CHAR contains next character
;          OPERAND_L/H contain result
;          IS_FWDREF set if expression contains forward ref (NOT set for byte selectors)
;          C=0 if first term is a single byte or C=1 if first term is two bytes
parse_value
  CMP #'<'
  BEQ .low_byte_selector
  CMP #'>'
  BEQ .high_byte_selector
  JMP parse_expression

.low_byte_selector
  JSR read_char        ; Skip '<'
  JSR parse_expression ; Next char now in NEXT_CHAR
  ; Apply low byte: keep OPERAND_L, zero OPERAND_H
  LDA #$00
  STA OPERAND_H
  STA IS_FWDREF        ; Byte selectors don't set fwdref (always 1 byte result)
  CLC                  ; Byte selector = C=0 (1 byte)
  RTS

.high_byte_selector
  JSR read_char        ; Skip '>'
  JSR parse_expression ; Next char now in NEXT_CHAR
  ; Apply high byte: move OPERAND_H to OPERAND_L, zero OPERAND_H
  LDA OPERAND_H
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  STA IS_FWDREF        ; Byte selectors don't set fwdref (always 1 byte result)
  CLC                  ; Byte selector = C=0 (1 byte)
  RTS


; Parse term with optional byte selector prefix
; Unlike parse_value, does NOT handle chained operators - only byte selectors
; Used for shift counts to ensure left-to-right evaluation of shifts
; On entry: A contains first character
; On exit: NEXT_CHAR contains next character
;          OPERAND_L/H contain result
;          IS_FWDREF set if term is forward ref (NOT set for byte selectors)
;          C=1 if bare label, C=0 otherwise
parse_term_with_selector
  CMP #'<'
  BEQ .tws_low_byte
  CMP #'>'
  BEQ .tws_high_byte
  JMP parse_term

.tws_low_byte
  JSR read_char        ; Skip '<'
  JSR parse_term       ; Next char now in NEXT_CHAR
  ; Apply low byte: keep OPERAND_L, zero OPERAND_H
  LDA #$00
  STA OPERAND_H
  STA IS_FWDREF        ; Byte selectors don't set fwdref
  CLC
  RTS

.tws_high_byte
  JSR read_char        ; Skip '>'
  JSR parse_term       ; Next char now in NEXT_CHAR
  ; Apply high byte: move OPERAND_H to OPERAND_L, zero OPERAND_H
  LDA OPERAND_H
  STA OPERAND_L
  LDA #$00
  STA OPERAND_H
  STA IS_FWDREF        ; Byte selectors don't set fwdref
  CLC
  RTS


; Parse expression: term [+|-|<<|>> term]*
; On entry: A contains first character
; On exit: NEXT_CHAR contains next character
;          OPERAND_L/H contain result
;          IS_FWDREF set if any term is forward ref
;          C=1 if 2-byte value (bare label or $xxxx), C=0 if 1-byte ($xx, 'c')
;          (Carry from first term - used by .data to decide emit size)
parse_expression
  JSR parse_term       ; Parse first term, next char in NEXT_CHAR
  PHP ; Save carry flag

  ; Save IS_FWDREF from first term
  LDA IS_FWDREF
  STA EXPR_FWDREF

.loop
  LDA NEXT_CHAR
  CMP #'+'
  BEQ .add_op
  CMP #'-'
  BEQ .sub_op
  CMP #'<'
  BEQ .check_left_shift
  CMP #'>'
  BEQ .check_right_shift

  ; No more operators - restore and return
  LDA EXPR_FWDREF
  STA IS_FWDREF
  PLP ; Restore carry flag from first term
  RTS

.add_op
  ; Save current accumulator
  LDA OPERAND_L
  STA EXPR_ACCU_L
  LDA OPERAND_H
  STA EXPR_ACCU_H

  ; Parse next term (skip '+' first)
  JSR read_char        ; Skip '+'
  JSR parse_term_with_selector  ; Next char in NEXT_CHAR

  ; Accumulate forward ref flag
  LDA IS_FWDREF
  ORA EXPR_FWDREF
  STA EXPR_FWDREF

  ; Add: accumulator + OPERAND → OPERAND
  LDA EXPR_ACCU_L
  CLC
  ADC OPERAND_L
  STA OPERAND_L
  LDA EXPR_ACCU_H
  ADC OPERAND_H
  STA OPERAND_H
  JMP .loop

.sub_op
  ; Save current accumulator
  LDA OPERAND_L
  STA EXPR_ACCU_L
  LDA OPERAND_H
  STA EXPR_ACCU_H

  ; Parse next term (skip '-' first)
  JSR read_char        ; Skip '-'
  JSR parse_term_with_selector  ; Next char in NEXT_CHAR

  ; Accumulate forward ref flag
  LDA IS_FWDREF
  ORA EXPR_FWDREF
  STA EXPR_FWDREF

  ; Subtract: accumulator - OPERAND → OPERAND
  LDA EXPR_ACCU_L
  SEC
  SBC OPERAND_L
  STA OPERAND_L
  LDA EXPR_ACCU_H
  SBC OPERAND_H
  STA OPERAND_H
  JMP .loop

.check_left_shift
  ; Read next char to confirm second '<'
  JSR read_char
  CMP #'<'
  BEQ .left_shift_op
  JMP err_expected_shift    ; Single '<' in middle of expression is error

.check_right_shift
  ; Read next char to confirm second '>'
  JSR read_char
  CMP #'>'
  BEQ .right_shift_op
  JMP err_expected_shift    ; Single '>' in middle of expression is error

.left_shift_op
  ; Save current operand to EXPR_ACCU
  LDA OPERAND_L
  STA EXPR_ACCU_L
  LDA OPERAND_H
  STA EXPR_ACCU_H

  ; Parse shift count (use parse_term_with_selector to support byte selectors like <<<)
  JSR read_char        ; Read char after second '<'
  JSR parse_term_with_selector  ; Next char in NEXT_CHAR

  ; Accumulate forward ref flag
  LDA IS_FWDREF
  ORA EXPR_FWDREF
  STA EXPR_FWDREF

  ; Check if shift count >= 16 (result will be 0)
  LDA OPERAND_H
  BNE .left_shift_zero     ; High byte != 0 means shift >= 256
  LDA OPERAND_L
  CMP #$10
  BCS .left_shift_zero     ; Low byte >= 16 means shift >= 16
  TAY                      ; Transfer shift count to Y

  ; Restore value to shift from EXPR_ACCU
  LDA EXPR_ACCU_L
  STA OPERAND_L
  LDA EXPR_ACCU_H
  STA OPERAND_H

  ; Perform left shift
.left_shift_loop
  DEY
  BMI .left_shift_done
  ASL OPERAND_L
  ROL OPERAND_H
  JMP .left_shift_loop

.left_shift_zero
  ; Shift >= 16, result is 0
  LDA #$00
  STA OPERAND_L
  STA OPERAND_H

.left_shift_done
  JMP .loop

.right_shift_op
  ; Save current operand to EXPR_ACCU
  LDA OPERAND_L
  STA EXPR_ACCU_L
  LDA OPERAND_H
  STA EXPR_ACCU_H

  ; Parse shift count (use parse_term_with_selector to support byte selectors like >>>)
  JSR read_char        ; Read char after second '>'
  JSR parse_term_with_selector  ; Next char in NEXT_CHAR

  ; Accumulate forward ref flag
  LDA IS_FWDREF
  ORA EXPR_FWDREF
  STA EXPR_FWDREF

  ; Check if shift count >= 16 (result will be 0)
  LDA OPERAND_H
  BNE .right_shift_zero    ; High byte != 0 means shift >= 256
  LDA OPERAND_L
  CMP #$10
  BCS .right_shift_zero    ; Low byte >= 16 means shift >= 16
  TAY                      ; Transfer shift count to Y

  ; Restore value to shift from EXPR_ACCU
  LDA EXPR_ACCU_L
  STA OPERAND_L
  LDA EXPR_ACCU_H
  STA OPERAND_H

  ; Perform right shift (logical/unsigned)
.right_shift_loop
  DEY
  BMI .right_shift_done
  LSR OPERAND_H
  ROR OPERAND_L
  JMP .right_shift_loop

.right_shift_zero
  ; Shift >= 16, result is 0
  LDA #$00
  STA OPERAND_L
  STA OPERAND_H

.right_shift_done
  JMP .loop


; ============================================================================
; TIER 5: LABEL MANAGEMENT & HASH TABLE
; Label classification, lookup, and definition
; ============================================================================

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


select_label_hash_table
  LDA #<LHASHTAB
  STA HTPL
  LDA #>LHASHTAB
  STA HTPH
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
  CMP #'*'
  BEQ .set_pc
  JSR read_token            ; Next char in NEXT_CHAR
  LDA NEXT_CHAR             ; Check if terminated by colon
  CMP #':'
  BNE .no_colon
  JSR read_char             ; Skip past colon, update NEXT_CHAR
.no_colon
  ; Normal label
  BIT PASS
  BPL .pass_1
  ; Pass 2 - don't capture label, but must track globals for local label scoping
  ; NEXT_CHAR has the next char from read_token
  JSR check_local_label     ; Sets IS_LOCAL_LABEL, validates scope for locals
  ; Now continue with value reading
  JSR check_for_value
  BCS .has_equals_2         ; If = found, branch
  ; No = found - update global heap if this was not a local label
  ; check_for_value updated NEXT_CHAR if it called read_char
  LDA IS_LOCAL_LABEL
  BNE .was_local_2          ; If local flag != 0, skip update
  JSR update_global_heap_from_lookup  ; Set CURR_GLOBAL_HEAP for local label lookups
.was_local_2
  JMP .skip_spaces_and_return_processed_flag
.set_pc
  ; Set PC
  JSR read_char             ; Skip the *
  JSR check_for_value
  BCS .pc_value_present
  JMP err_pc_value_expected
.pc_value_present
  JSR read_value
  JSR skip_rest_of_line
  JSR update_pc
  SEC                       ; Indicate line is fully processed
  RTS
.has_equals_2
  JSR read_value
  JMP .skip_and_return_processed
.pass_1
  ; NEXT_CHAR has the next char from read_token
  JSR check_local_label     ; Sets IS_LOCAL_LABEL, validates scope for locals
  ; Add key to hash table first (before read_value may overwrite TOKEN)
  JSR select_label_hash_table
  JSR hash_add
  BCS .duplicate_label
  ; Now read the value (TOKEN can be overwritten, but HTTPL/HTTPH preserved if no =)
  JSR check_for_value
  BCS .has_equals           ; If = found, branch
  ; No = found, save global label and use program counter
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
  JMP .skip_spaces_and_return_processed_flag
.has_equals
  JSR read_value            ; Read the value after the equals, next char in NEXT_CHAR
  JSR store_hash_value
  JMP .skip_and_return_processed
.skip_spaces_and_return_processed_flag
  JMP check_for_end_of_line ; Tail call - returns with C set if at end of line
.skip_and_return_processed
  JSR skip_rest_of_line
  SEC                       ; Indicate line is fully processed
  ; No need to retain next char as caller
  ; goes straight to next line
  RTS
.duplicate_label
  JMP err_duplicate_label


; ============================================================================
; TIER 6: PC MANAGEMENT
; Program counter manipulation and byte emission
; ============================================================================

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
  BNE .no_fill        ; Always taken
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
  BPL .no_fill        ; skip writing during pass 1
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
  BNE .loop           ; Always taken
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


; ============================================================================
; TIER 7: INSTRUCTION LOOKUP & OPCODE
; Mnemonic lookup and opcode finding
; ============================================================================

; Look up mnemonic and save pointer to mode:opcode data
; On entry A contains the first character of the mnemonic
; On exit NEXT_CHAR contains the next character
;         INST_PTR_L:INST_PTR_H points to mode:opcode data (past mnemonic)
;         X, Y are not preserved
; Raises 'Opcode not found' error if mnemonic is not found
lookup_mnemonic
  JSR read_token       ; Next char in NEXT_CHAR
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCC .found
  JMP err_opcode_not_found
.found
  ; TABPL:TABPH+Y points to mode:opcode data or macro sentinel
  ; Check for macro sentinel ($FE)
  LDA (TABPL),Y
  CMP #$FE
  BNE .is_instruction
  ; It's a macro - compute pointer to macro data and expand
  ; MACRO_DEF_PTR = TABPL + Y (points to $FE, body_ptr is at +1)
  TYA
  CLC
  ADC TABPL
  STA MACRO_DEF_PTR_L
  LDA #$00
  ADC TABPH
  STA MACRO_DEF_PTR_H
  ; Don't skip rest of line - expand_macro will parse arguments
  PLA                   ; Pop return address (we're not returning)
  PLA
  JMP expand_macro
.is_instruction
  ; Calculate INST_PTR = TABPL + Y
  TYA
  CLC
  ADC TABPL
  STA INST_PTR_L
  LDA #$00
  ADC TABPH
  STA INST_PTR_H
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
  BEQ .not_found      ; End of list, mode not found
  CMP ADDR_MODE
  BEQ .found
  ; Not this mode, skip to next pair
  INY
  INY
  BNE .loop           ; Always taken
.found
  INY
  LDA (INST_PTR_L),Y  ; Get opcode byte
  CLC
  RTS
.not_found
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


; ============================================================================
; TIER 8: INSTRUCTION EMISSION
; Emit instructions with operands
; ============================================================================

; Emit instruction based on addressing mode
; On entry INST_PTR_L:INST_PTR_H points to mode:opcode data
;          ADDR_MODE contains the addressing mode
;          OPERAND_L:OPERAND_H contains operand value (if applicable)
; On exit X is preserved
;         A, Y are not preserved
; Raises error if addressing mode is not valid for this instruction
emit_instruction
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
  CMP #MODE_IMM
  BEQ .one_byte
  CMP #MODE_ZP
  BEQ .one_byte
  CMP #MODE_ZPX
  BEQ .one_byte
  CMP #MODE_ZPY
  BEQ .one_byte
  CMP #MODE_INDX
  BEQ .one_byte
  CMP #MODE_INDY
  BEQ .one_byte
  ; 2-byte operand (absolute modes)
  LDA OPERAND_L
  JSR emit
  LDA OPERAND_H
  JSR emit
.done
  RTS
.one_byte
  ; Validate operand <= $FF
  BIT PASS
  BPL .one_byte_ok       ; Skip validation on pass 1
  LDA OPERAND_H
  BNE .one_byte_error
.one_byte_ok
  LDA OPERAND_L
  JSR emit
  RTS
.one_byte_error
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
  RTS
.invalid_mode
  JMP err_invalid_addressing_mode


; Checks mode availability, value size, and forward reference forcing
; On entry: ADDR_MODE set to ZP variant (MODE_ZP, MODE_ZPX, or MODE_ZPY)
;           INST_PTR_L/H points to instruction's mode:opcode data
;           OPERAND_H contains high byte of operand value
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


; ============================================================================
; TIER 9: OPERAND PARSING & EMISSION
; Parse operands and emit complete instructions
; ============================================================================

; Parse operand and emit instruction
; On entry A contains the next character after mnemonic
;          INST_PTR_L:INST_PTR_H points to mode:opcode data
; On exit flow continues to .line_loop
;         A, X, Y are not preserved
parse_operand_and_emit
  JSR check_for_end_of_line
  BCS .implied_mode    ; No operand = implied mode
  ; Check operand format to determine mode
  CMP #'#'
  BNE .not_imm
  JMP .immediate_mode
.not_imm
  CMP #'('
  BNE .not_ind
  JMP .indirect_mode
.not_ind
  ; Everything else: $xx, $xxxx, or label
  ; All handled uniformly by parse_term + mode selection
  JMP .value_operand

.implied_mode
  ; Next char in NEXT_CHAR (newline or semicolon)
  LDA #MODE_NONE
  STA ADDR_MODE
  LDA #$00
  STA OPERAND_L
  STA OPERAND_H
  JMP emit_instruction ; Tail call

.immediate_mode
  ; #$xx or #<label or #>label or #label or #'x'
  LDA #MODE_IMM
  STA ADDR_MODE
  JSR read_char        ; Skip #
  JSR parse_value      ; Returns next char in A, OPERAND_L/H set
  JMP emit_instruction ; Tail call

.indirect_mode
  ; ($xx),Y - indirect indexed Y (1-byte operand)
  ; ($xx,X) - indirect indexed X (1-byte operand)
  ; ($xxxx) - indirect absolute for JMP (2-byte operand)
  JSR read_char        ; Skip (
  ; Parse value ($xx, <label, >label, or label)
  JSR parse_value      ; OPERAND_L/H set, next char in NEXT_CHAR
  ; Check suffix to determine addressing mode
  LDA NEXT_CHAR        ; Load next char (should be ) or ,)
  CMP #','
  BEQ .indirect_x
  ; Must be )
  CMP #')'
  BNE .ind_err_operand
  JSR read_char        ; Read char after )
  CMP #','
  BNE .ind_no_suffix
  JSR read_char        ; Should be Y
  CMP #'Y'
  BNE .ind_err
  LDA #MODE_INDY
  STA ADDR_MODE
  JSR read_char        ; Read char after Y for garbage check
  JMP emit_instruction ; Tail call
.indirect_x
  JSR read_char        ; Should be X
  CMP #'X'
  BNE .ind_err
  JSR read_char        ; Should be )
  CMP #')'
  BNE .ind_err
  LDA #MODE_INDX
  STA ADDR_MODE
  JSR read_char        ; Read char after ) for garbage check
  JMP emit_instruction ; Tail call
.ind_no_suffix
  ; Just ($xxxx) - JMP indirect mode (must be 2-byte operand)
  ; Next char in NEXT_CHAR (after ))
  LDA #MODE_IND
  STA ADDR_MODE
  JMP emit_instruction ; Tail call
.ind_err
  JMP err_invalid_addressing_mode
.ind_err_operand
  JMP err_invalid_operand

.value_operand
  ; Parse value: $xx, $xxxx, or label
  ; All handled uniformly with appropriate mode selection
  JSR parse_value      ; Returns C=1 for bare label, OPERAND_L/H set, IS_FWDREF set, next char in NEXT_CHAR
  ; Check if this is a branch instruction
  JSR check_if_branch
  BCS .not_branch
  JMP .label_is_branch
.not_branch
  ; Not a branch - check for indexed mode
  LDA NEXT_CHAR        ; Next char (might be comma)
  CMP #','
  BNE .label_no_index
  ; Has index suffix - read X or Y
  JSR read_char
  CMP #'X'
  BEQ .label_x_index
  CMP #'Y'
  BEQ .label_y_index
  JMP err_invalid_addressing_mode
.label_x_index
  JSR read_char            ; Read char after X for garbage check, stores in NEXT_CHAR
  LDA #MODE_ZPX
  STA ADDR_MODE
  JSR handle_fwdref_mode   ; Checks mode availability, value size, forward refs
  BCS .label_use_absx      ; Must use ABSX
  ; Use ZPX mode
  JMP emit_instruction
.label_use_absx
  LDA #MODE_ABSX
  STA ADDR_MODE
  JMP emit_instruction
.label_y_index
  JSR read_char            ; Read char after Y for garbage check, stores in NEXT_CHAR
  LDA #MODE_ZPY
  STA ADDR_MODE
  JSR handle_fwdref_mode   ; Checks mode availability, value size, forward refs
  BCS .label_use_absy      ; Must use ABSY
  ; Use ZPY mode
  JMP emit_instruction
.label_use_absy
  LDA #MODE_ABSY
  STA ADDR_MODE
  JMP emit_instruction
.label_no_index
  ; Next char in NEXT_CHAR
  LDA #MODE_ZP
  STA ADDR_MODE
  JSR handle_fwdref_mode   ; Checks mode availability, value size, forward refs
  BCS .label_use_abs       ; Must use ABS
  ; Use ZP mode
  JMP emit_instruction
.label_use_abs
  LDA #MODE_ABS
  STA ADDR_MODE
  JMP emit_instruction

.label_is_branch
  LDA #MODE_REL
  STA ADDR_MODE
  JMP emit_instruction


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
  BCC .loop
.err_closing_quote
  JMP err_closing_quote_not_found
.done
  JSR read_char        ; Done; read next char
  RTS


; ============================================================================
; TIER 10: DIRECTIVE PROCESSING
; Handle assembler directives (.include, .data, etc.)
; ============================================================================

; On entry, A contains the first character of the directive
process_directive
  JSR read_token       ; Next char in NEXT_CHAR
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
  ; Check for 'data'
  LDA #<directive_data
  STA TABPL
  LDA #>directive_data
  STA TABPH
  JSR compare_token
  BEQ .data
  JSR process_conditional_directive ; Returns with C=0 if processed
  BCC .directive_done
  ; Check for 'macro'
  LDA #<directive_macro
  STA TABPL
  LDA #>directive_macro
  STA TABPH
  JSR compare_token
  BEQ .macro
  ; Check for 'endmacro'
  LDA #<directive_endmacro
  STA TABPL
  LDA #>directive_endmacro
  STA TABPH
  JSR compare_token
  BEQ .endmacro
  JMP err_unknown_directive
.directive_done
  RTS
.macro
  JMP process_macro
.endmacro
  JMP process_endmacro
.include
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
  JSR skip_rest_of_line
  RTS
.code
  BIT IN_ZEROPAGE
  BPL .in_code
  LDA #$00
  STA IN_ZEROPAGE
  JSR swap_pc_with_save
.in_code
  JSR skip_rest_of_line
  RTS
.data
  JMP data_parameters_loop_entry


; On exit C=0 if processed; C=1 if not processed
;         A is not preserved
process_conditional_directive
  ; Check for 'ifdef'
  LDA #<directive_ifdef
  STA TABPL
  LDA #>directive_ifdef
  STA TABPH
  JSR compare_token
  BEQ .ifdef
  ; Check for 'endif'
  LDA #<directive_endif
  STA TABPL
  LDA #>directive_endif
  STA TABPH
  JSR compare_token
  BEQ .endif
  SEC ; Not processed
  RTS
.ifdef
  JSR process_ifdef
  CLC
  RTS
.endif
  JSR process_endif
  CLC
  RTS


directive_include
  .data "include" $00

directive_zeropage
  .data "zeropage" $00

directive_code
  .data "code" $00

directive_data
  .data "data" $00

directive_ifdef
  .data "ifdef" $00

directive_endif
  .data "endif" $00

directive_macro
  .data "macro" $00

directive_endmacro
  .data "endmacro" $00


data_parameters_loop
data_parameters_loop_entry
  JSR check_for_end_of_line
  BCS .data_done
  CMP #'"'            ; Quoted string
  BNE .data_value
  JSR read_char
  JSR emit_quoted
  JMP data_parameters_loop
.data_value
  ; Parse value: handles $hex, 'char', label, <expr, >expr, and expressions
  JSR parse_value      ; Returns C=1 for bare label, C=0 otherwise, next char in NEXT_CHAR
  BCS .data_emit_two_bytes
  ; C=0: expression/hex/'char'/</>  - emit 1 byte from OPERAND_L
  LDA OPERAND_L
  JSR emit
  JMP data_parameters_loop
.data_emit_two_bytes
  ; C=1: bare label - emit 2 bytes (LSB, MSB)
  LDA OPERAND_L        ; Emit low byte
  JSR emit
  LDA OPERAND_H        ; Emit high byte
  JSR emit
  JMP data_parameters_loop
.data_done
  RTS


; Process .ifdef directive
process_ifdef
  INC COND_DEPTH
  LDA COND_DEPTH
  CMP #$11             ; Check for nesting limit (16 levels max, depth 17 = overflow)
  BCS .nesting_too_deep
  LDA SKIP_DEPTH
  BNE .already_skipping ; Already skipping, don't record or evaluate
  ; Not skipping - evaluate condition
  JSR check_for_end_of_line
  BCC .has_label
  JMP err_label_expected
.has_label
  JSR read_token
  ; Save X (output file handle)
  TXA
  PHA
  ; Check for pass 2 - replay stored decision
  BIT PASS
  BMI .pass2
  ; --- Pass 1: Evaluate and store decision ---
  LDX IFDEF_INDEX
  INC IFDEF_INDEX
  BEQ .overflow        ; If wrapped to 0, we've used all 256 slots
  LDA #$00
  STA IS_LOCAL_LABEL
  JSR select_label_hash_table
  JSR find_in_hash     ; C=0 if found, C=1 if not found
  LDA #$00             ; Default: not defined (skip)
  BCS .save_result     ; C=1 means not found
  LDA #$FF             ; Found: defined (assemble)
.save_result
  STA IFDEF_DECISIONS,X
  BEQ .start_skip      ; Not defined ($00) - start skipping
  BNE .done            ; Defined ($FF) - continue
  ; --- Pass 2: Replay stored decision ---
.pass2
  LDX IFDEF_INDEX
  INC IFDEF_INDEX
  LDA IFDEF_DECISIONS,X
  BEQ .start_skip
  BNE .done
.start_skip
  LDA COND_DEPTH
  STA SKIP_DEPTH
.done
  ; Restore X (output file handle)
  PLA
  TAX
  JMP skip_rest_of_line
.already_skipping
  JMP skip_rest_of_line
.overflow
  JMP err_too_many_ifdefs
.nesting_too_deep
  JMP err_conditional_nesting_too_deep


; Process .endif directive
process_endif
  LDA COND_DEPTH
  BNE .pe_has_ifdef    ; In a conditional block
  JMP err_endif_without_ifdef
.pe_has_ifdef
  DEC COND_DEPTH
  ; Check if this ends our skip block
  LDA SKIP_DEPTH
  BEQ .pe_done         ; Not skipping, just decrement depth
  ; Currently skipping - check if we should stop
  LDA COND_DEPTH
  CMP SKIP_DEPTH
  BCS .pe_done         ; Still in nested block (COND_DEPTH >= SKIP_DEPTH)
  ; COND_DEPTH < SKIP_DEPTH, stop skipping
  LDA #$00
  STA SKIP_DEPTH
.pe_done
  JMP skip_rest_of_line ; Tail call


; Process .macro directive
; Syntax: .macro NAME [param1 param2 ...]
; Creates entry in IHASHTAB: [name $00][$FE][body_ptr_L][body_ptr_H][params...][\0]
process_macro
  ; Skip spaces and read macro name
  JSR check_for_end_of_line
  BCC .pm_has_name
  JMP err_macro_name_expected
.pm_has_name
  JSR read_token       ; Macro name now in TOKEN, next char in NEXT_CHAR
  ; Check for instruction collision or duplicate macro
  JSR select_instruction_hash_table
  JSR find_in_hash_instruction
  BCS .pm_name_ok      ; C=1 means not found, good
  ; Found something - is it an instruction or existing macro?
  ; Check first byte of value - $FE means macro, else instruction
  LDA (TABPL),Y
  CMP #$FE
  BEQ .pm_is_macro
  JMP err_macro_shadows_instruction
.pm_is_macro
  ; It's a macro - in pass 2 this is expected, just skip to capturing
  BIT PASS
  BMI .pm_pass2_skip_add
  JMP err_duplicate_macro
.pm_pass2_skip_add
  ; Pass 2: skip adding, just set flag and skip line
  ; The macro body will be re-captured (but discarded in Phase 1B capture mode)
  LDA #$FF
  STA IN_MACRO_DEF
  JMP skip_rest_of_line
.pm_name_ok
  ; Add macro entry to instruction hash table
  ; HASH is still set from find_in_hash_instruction
  ; Use similar logic to hash_add but for instruction table
  JSR hash_entry_empty
  BEQ .pm_hash_empty
  ; Entry exists - find end of chain
  JSR load_hash_entry
  JSR find_token
  ; TABPL;TABPH,Y points to 'next' pointer at end of chain
  JSR store_table_entry  ; Store MEMPL at end of chain
  JMP .pm_store_entry
.pm_hash_empty
  JSR store_hash_entry   ; Store MEMPL in hash table
.pm_store_entry
  JSR store_token        ; Stores name on heap, MEMPL now points to value location
  ; Store $FE sentinel
  LDY #$00
  LDA #$FE
  STA (MEMPL),Y
  INY
  JSR advance_heap
  ; Save location for body_ptr (will fill in after params are parsed)
  LDA MEMPL
  STA MACRO_DEF_PTR_L
  LDA MEMPH
  STA MACRO_DEF_PTR_H
  ; Advance past body_ptr space (2 bytes)
  LDY #$02
  JSR advance_heap
  ; Parse parameters (if any) - stored as zero-terminated list
.pm_param_loop
  JSR check_for_end_of_line
  BCS .pm_params_done  ; End of line, no more params
  ; Read parameter name
  JSR read_token       ; Param name in TOKEN, next char in NEXT_CHAR
  ; Store parameter name on heap (null-terminated)
  LDY #$FF
.pm_copy_param
  INY
  LDA TOKEN,Y
  STA (MEMPL),Y
  BNE .pm_copy_param
  INY
  JSR advance_heap
  JMP .pm_param_loop
.pm_params_done
  ; Write empty string terminator for parameter list
  LDY #$00
  LDA #$00
  STA (MEMPL),Y
  INY
  JSR advance_heap
  ; Write body_ptr (current MEMPL) into the saved location
  LDA MACRO_DEF_PTR_L
  STA TABPL
  LDA MACRO_DEF_PTR_H
  STA TABPH
  LDY #$00
  LDA MEMPL
  STA (TABPL),Y
  INY
  LDA MEMPH
  STA (TABPL),Y
  ; Update MACRO_DEF_PTR to point where body will be stored
  LDA MEMPL
  STA MACRO_DEF_PTR_L
  LDA MEMPH
  STA MACRO_DEF_PTR_H
  ; Set IN_MACRO_DEF flag to start capturing
  LDA #$FF
  STA IN_MACRO_DEF
  ; Skip rest of line (already done by check_for_end_of_line)
  RTS


; Process .endmacro directive
process_endmacro
  ; Check if we're in a macro definition
  LDA IN_MACRO_DEF
  BNE .pem_in_macro
  JMP err_endmacro_without_macro
.pem_in_macro
  ; Write $00 terminator to body (body_ptr was already set in process_macro)
  LDY #$00
  LDA #$00
  STA (MEMPL),Y
  INY
  JSR advance_heap
  ; Clear the capturing flag
  LDA #$00
  STA IN_MACRO_DEF
  JMP skip_rest_of_line


; Check if macro is already being expanded (recursion check)
; Walks the scope stack comparing 2-byte macro entry addresses
; On entry: MACRO_ENTRY_L/H contains the macro's hash table entry address
; On exit: Returns normally if no recursion, jumps to err_recursive_macro if found
;          Uses TABPL/TABPH as walk pointer, A/Y clobbered, X preserved
check_macro_recursion
  ; Walk scope stack from bottom to current position
  LDA #<SCOPE_STACK
  STA TABPL
  LDA #>SCOPE_STACK
  STA TABPH
.cmr_loop
  ; Check if we've reached current scope pointer
  LDA TABPL
  CMP SCOPE_PTR_L
  BNE .cmr_check_entry
  LDA TABPH
  CMP SCOPE_PTR_H
  BEQ .cmr_done             ; Reached current position, no recursion
.cmr_check_entry
  ; Compare macro address at offset +3 with MACRO_ENTRY
  LDY #$03
  LDA (TABPL),Y
  CMP MACRO_ENTRY_L
  BNE .cmr_next
  INY
  LDA (TABPL),Y
  CMP MACRO_ENTRY_H
  BNE .cmr_next
  ; Match found - recursion detected
  JMP err_recursive_macro
.cmr_next
  ; Advance to next entry (+5 bytes)
  LDA TABPL
  CLC
  ADC #$05
  STA TABPL
  BCC .cmr_loop
  INC TABPH
  JMP .cmr_loop
.cmr_done
  RTS


; Expand a macro invocation
; On entry: MACRO_DEF_PTR points to the $FE sentinel in macro entry
;           ($FE, body_ptr_L, body_ptr_H, param1\0, param2\0, ..., \0)
;           TOKEN contains the macro name
;           NEXT_CHAR contains character after macro name
; On exit: Memory source pushed, jumps to asm_line_loop
expand_macro
  ; Save original macro entry address before MACRO_DEF_PTR is modified
  LDA MACRO_DEF_PTR_L
  STA MACRO_ENTRY_L
  LDA MACRO_DEF_PTR_H
  STA MACRO_ENTRY_H
  ; Check for recursive macro invocation
  JSR check_macro_recursion
  ; Save X (output file handle) - we'll use X as index into MACRO_ARG_BUF
  TXA
  PHA
  ; Get body_ptr from MACRO_DEF_PTR+1 and save on 6502 stack
  LDY #$01
  LDA (MACRO_DEF_PTR_L),Y
  PHA                   ; Save body start low
  INY
  LDA (MACRO_DEF_PTR_L),Y
  PHA                   ; Save body start high
  ; DON'T push label scope yet - we need parent's scope to look up arguments
  ; Parse arguments first, storing values in fixed buffer
  ; MACRO_DEF_PTR+3 points to first parameter name (or empty string if none)
  LDA MACRO_DEF_PTR_L
  CLC
  ADC #$03
  STA MACRO_DEF_PTR_L
  LDA MACRO_DEF_PTR_H
  ADC #$00
  STA MACRO_DEF_PTR_H
  ; Save start of params (MACRO_DEF_PTR)
  LDA MACRO_DEF_PTR_L
  PHA
  LDA MACRO_DEF_PTR_H
  PHA
  ; X = index into MACRO_ARG_BUF for storing values
  ; Each entry: [value_L][value_H][is_fwdref] = 3 bytes
  LDX #$00
.em_parse_loop
  ; Check if we're at end of parameter list (empty string)
  LDY #$00
  LDA (MACRO_DEF_PTR_L),Y
  BEQ .em_parse_done
  ; Skip past parameter name
  LDY #$FF
.em_skip_param
  INY
  LDA (MACRO_DEF_PTR_L),Y
  BNE .em_skip_param
  ; Advance MACRO_DEF_PTR past the null terminator
  TYA
  SEC                   ; +1 for null
  ADC MACRO_DEF_PTR_L
  STA MACRO_DEF_PTR_L
  LDA #$00
  ADC MACRO_DEF_PTR_H
  STA MACRO_DEF_PTR_H
  ; Check for argument in input
  JSR check_for_end_of_line
  BCC .em_have_arg
  JMP err_too_few_arguments
.em_have_arg
  ; Parse argument expression (using PARENT's scope for lookups)
  JSR parse_expression
  ; Store value and fwdref flag in fixed buffer
  LDA OPERAND_L
  STA MACRO_ARG_BUF,X
  INX
  LDA OPERAND_H
  STA MACRO_ARG_BUF,X
  INX
  LDA IS_FWDREF
  STA MACRO_ARG_BUF,X
  INX
  JMP .em_parse_loop
.em_parse_done
  ; Check for extra arguments (should be at end of line now)
  JSR check_for_end_of_line
  BCC .em_too_many
  ; NOW push label scope for the child macro
  JSR push_label_scope
  ; Pop params start to MACRO_DEF_PTR
  PLA
  STA MACRO_DEF_PTR_H
  PLA
  STA MACRO_DEF_PTR_L
  ; Reset X to read values from start of buffer
  LDX #$00
  ; Now iterate through params and add to hash with stored values
.em_add_loop
  ; Check if at end of parameter list
  LDY #$00
  LDA (MACRO_DEF_PTR_L),Y
  BEQ .em_add_done
  ; Copy param name to TOKEN
  LDY #$FF
.em_copy_param
  INY
  LDA (MACRO_DEF_PTR_L),Y
  STA TOKEN,Y
  BNE .em_copy_param
  ; Advance MACRO_DEF_PTR past param name
  TYA
  SEC
  ADC MACRO_DEF_PTR_L
  STA MACRO_DEF_PTR_L
  LDA #$00
  ADC MACRO_DEF_PTR_H
  STA MACRO_DEF_PTR_H
  ; Load value and fwdref from buffer
  LDA MACRO_ARG_BUF,X
  STA OPERAND_L
  INX
  LDA MACRO_ARG_BUF,X
  STA OPERAND_H
  INX
  LDA MACRO_ARG_BUF,X
  STA IS_FWDREF
  INX
  ; Skip adding if forward ref in pass 1
  LDA IS_FWDREF
  BEQ .em_do_add
  BIT PASS
  BMI .em_do_add        ; Pass 2: always add
  JMP .em_add_loop      ; Pass 1 fwdref: skip
.em_do_add
  ; Add parameter to local scope
  LDA #$FF
  STA IS_LOCAL_LABEL
  JSR select_label_hash_table
  JSR hash_add
  BCS .em_add_loop      ; Already exists (pass 1), skip store
  ; Store value (OPERAND_L/H aliased to HEX2/HEX1)
  JSR store_hash_value
  JMP .em_add_loop
.em_add_done
  ; Push memory source and set up pointers
  JSR push_memory_source
  ; Restore body pointer from 6502 stack
  PLA                   ; Body start high
  STA FS_MEM_PTR_H
  PLA                   ; Body start low
  STA FS_MEM_PTR_L
  ; Restore X (output file handle)
  PLA
  TAX
  JMP asm_line_loop
.em_too_many
  JMP err_too_many_arguments


; Capture a line during macro definition
; On entry: A contains first character of line
; On exit: Line copied to heap (with $0A), or .endmacro processed
;          Returns to caller (who should JMP .line_loop)
;
; Strategy: Copy whole line to heap, then check if it was .endmacro.
; If so, undo the copy and process .endmacro normally.
capture_macro_line
  ; Save first char (in A from read_char) and X (output file handle)
  PHA
  TXA
  PHA
  ; Save heap position in case we need to undo (for .endmacro)
  ; Use MACRO_DEF_PTR since we're not using it during capture
  LDA MEMPL
  STA MACRO_DEF_PTR_L
  LDA MEMPH
  STA MACRO_DEF_PTR_H
  ; Restore first char (X saved below A on stack)
  TSX
  LDA $0102,X
  ; Copy whole line to heap including newline
.cml_copy_loop
  LDY #$00
  STA (MEMPL),Y
  CMP #'\n'
  BEQ .cml_line_done
  INY
  JSR advance_heap
  JSR read_char
  BCC .cml_copy_loop
  ; EOF during macro - error
  JMP err_unclosed_macro
.cml_line_done
  INY
  JSR advance_heap     ; Advance past newline
  ; Now check if this line was .endmacro
  LDA MACRO_DEF_PTR_L
  STA TABPL
  LDA MACRO_DEF_PTR_H
  STA TABPH
  ; Skip leading spaces
  LDY #$00
.cml_skip_space
  LDA (TABPL),Y
  CMP #' '
  BNE .cml_check_dot
  INY
  BNE .cml_skip_space
.cml_check_dot
  CMP #'.'
  BNE .cml_keep_line
  ; Check if it's "endmacro" (case sensitive)
  INY
  LDX #$00
.cml_cmp_loop
  LDA directive_endmacro,X
  BEQ .cml_check_end     ; End of "endmacro" string
  CMP (TABPL),Y
  BNE .cml_keep_line
  INY
  INX
  BNE .cml_cmp_loop
.cml_check_end
  ; Matched "endmacro" - verify next char is space, $0A, or similar
  LDA (TABPL),Y
  CMP #' '
  BEQ .cml_found_endmacro
  CMP #'\n'
  BEQ .cml_found_endmacro
  CMP #';'               ; Comment
  BEQ .cml_found_endmacro
  BNE .cml_keep_line     ; Not end of token - keep as macro body
.cml_found_endmacro
  ; Restore heap to undo the copy
  LDA MACRO_DEF_PTR_L
  STA MEMPL
  LDA MACRO_DEF_PTR_H
  STA MEMPH
  ; Restore X (output file handle) - pop saved X and A
  PLA
  TAX
  PLA                 ; Discard saved A
  JMP process_endmacro
.cml_keep_line
  ; Restore X (output file handle)
  PLA
  TAX
  PLA                 ; Discard saved A
  RTS


; ============================================================================
; TIER 11: ASSEMBLY ORCHESTRATION
; Main assembly loop
; ============================================================================

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
  STA COND_DEPTH      ; Clear conditional depth
  STA SKIP_DEPTH      ; Clear skip depth
  STA IFDEF_INDEX     ; Clear .ifdef decision index
  STA IN_MACRO_DEF    ; Clear macro definition flag
asm_line_loop                 ; Global entry for macro expansion
.line_loop
  JSR read_char
  BCC .character_read
  ; End of input - check for unclosed conditional
  LDA COND_DEPTH
  BEQ .no_unclosed_ifdef
  JMP err_unclosed_ifdef
.no_unclosed_ifdef
  ; Check for unclosed macro definition
  LDA IN_MACRO_DEF
  BEQ .no_unclosed_macro
  JMP err_unclosed_macro
.no_unclosed_macro
  RTS
.character_read
  INC CURLINEL
  BNE .line_incremented
  INC CURLINEH
.line_incremented
  ; Check if we're capturing macro body
  LDY IN_MACRO_DEF
  BEQ .not_capturing_macro
  JSR capture_macro_line
  JMP .line_loop
.not_capturing_macro
  ; Check if we're skipping (conditional assembly)
  LDY SKIP_DEPTH
  BEQ .not_skipping
  ; --- Skipping mode: only process .ifdef/.endif ---
  CMP #' '
  BNE .skip_not_space
  ; Line starts with space - skip spaces to find directive
  JSR check_for_end_of_line
  BCS .line_loop
  JMP .skip_check_directive
.skip_not_space
  JSR check_for_end_of_line
  BCS .line_loop
  ; Line starts with non-space - skip label, check for directive
  JSR skip_token
  JSR check_for_end_of_line
  BCS .line_loop
.skip_check_directive
  CMP #'.'
  BNE .skip_line
  ; It's a directive - only process ifdef/endif
  JSR read_char
  JSR read_token
  JSR process_conditional_directive
  BCC .back_to_line_loop ; directive processed; already skipped line
.skip_line
  JSR skip_rest_of_line
  JMP .line_loop
.not_skipping
  CMP #' '
  BEQ .line_starts_with_space
  JSR check_for_end_of_line
  BCS .back_to_line_loop
  JSR capture_label
  BCC .check_for_opcode
  BCS .back_to_line_loop   ; Always taken
.line_starts_with_space
  JSR check_for_end_of_line
  BCS .back_to_line_loop
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
  ; A contains next char after operand - check for garbage
  ; Skip trailing spaces, then check for end of line (handles comments)
  JSR check_for_end_of_line
  BCS .back_to_line_loop
  JMP err_unexpected_text
.back_to_line_loop
  JMP .line_loop


; ============================================================================
; TIER 12: INITIALIZATION & I/O
; Program initialization and file operations
; ============================================================================

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


  .ifdef enable_debug
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
  .data "debug" $00
  .endif

str_define
  .data "define:" $00


; Check if string at TABPL;TABPH starts with "define:"
; On exit C = 0 if prefix matches (TABPL;TABPH updated to point past prefix)
;         C = 1 if no match
;         A, Y are not preserved
check_define_prefix
  LDY #$00
.loop
  LDA str_define,Y
  BEQ .matched         ; End of prefix string - matched!
  CMP (TABPL),Y
  BNE .not_matched
  INY
  JMP .loop
.matched
  ; Advance TABPL;TABPH past the prefix
  TYA
  CLC
  ADC TABPL
  STA TABPL
  BCC .no_carry
  INC TABPH
.no_carry
  CLC
  RTS
.not_matched
  SEC
  RTS


; Copy null-terminated string from TABPL;TABPH to TOKEN
; On exit: Y contains length (excluding null terminator)
;          A is not preserved
copy_string_to_token
  LDY #$00
.loop
  LDA (TABPL),Y
  BEQ .done
  STA TOKEN,Y
  INY
  JMP .loop
.done
  LDA #$00
  STA TOKEN,Y          ; Null-terminate
  RTS


; ============================================================================
; TIER 13: ENTRY POINT
; Program entry and main control flow
; ============================================================================

; Entry point
start
  ; Initialize output file handle to 0
  LDA #$00
  STA CURR_OUT_FILE
  .ifdef enable_debug
  ; Initialize debug flag to 0
  STA DEBUG_FLAG
  .endif
  ; Initialize file stack early so interrupt handler works correctly
  JSR file_stack_init
  ; Initialize scope stack for macro expansions
  JSR init_scope_stack
  ; Check argument count (must be at least 2)
  JSR argc
  CMP #$02
  BCC .err_usage         ; Less than 2 args
  STA ARG_COUNT          ; Save total arg count
  ; Initialize heap and hash table early for define: args
  JSR init_heap
  JSR select_label_hash_table
  JSR init_hash_table
  ; Process arguments 2 onwards (arg 0 = input, arg 1 = output)
  LDA #$02
  STA ARG_INDEX
.arg_loop
  LDA ARG_INDEX
  CMP ARG_COUNT
  BCS .args_done         ; Processed all args
  JSR argv               ; Get arg[ARG_INDEX]
  STA TABPL
  STX TABPH
  .ifdef enable_debug
  ; Check for "debug"
  JSR check_debug_string
  BCC .found_debug
  .endif
  ; Check for "define:" prefix
  JSR check_define_prefix
  BCC .found_define
  ; Unknown argument
  JMP err_invalid_arg
  .ifdef enable_debug
.found_debug
  LDA #$FF
  STA DEBUG_FLAG
  BNE .next_arg          ; Always branches
  .endif
.found_define
  ; TABPL;TABPH now points past "define:" to label name
  JSR copy_string_to_token
  LDA #$01
  STA HEX2               ; Value = $0001
  LDA #$00
  STA HEX1
  STA IS_LOCAL_LABEL     ; Not a local label
  JSR hash_add
.next_arg
  INC ARG_INDEX
  JMP .arg_loop
.err_usage
  JMP err_usage
.args_done
  LDA #$00
  STA CURR_FILE
  STA PASS            ; Bit 7 = 0 (pass 1)
  JSR init_fwdref_list
  JSR open_input

  ; Open output file
  LDA #$01
  JSR argv
  JSR openout
  STA CURR_OUT_FILE
  TAX

  JSR assemble_code
  JSR finalize_fwdref_list

  .ifdef enable_debug
  ; Capture forward ref pointer after pass 1
  LDA FWDREF_L
  STA FWDREF_PASS1_L
  LDA FWDREF_H
  STA FWDREF_PASS1_H
  .endif

  LDA #$FF
  STA PASS            ; Bit 7 = 1 (pass 2)
  JSR reset_fwdref_ptr
  JSR reset_scope_stack   ; Reset so pass 2 uses same scope IDs as pass 1
  JSR open_input
  JSR assemble_code

  .ifdef enable_debug
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
  .endif

  ; Close output file
  TXA
  JSR close
  LDA #$00
  STA CURR_OUT_FILE

  .ifdef enable_debug
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
  ; Divide by 2 (16-bit right shift)
  LSR TO_DECIMAL_VALUE_H
  ROR TO_DECIMAL_VALUE_L
  JSR show_decimal
  LDA #'\n'
  JSR write_d
.skip_debug_output
  .endif

  BRK
  .data $00             ; Success code


  .ifdef enable_debug
msg_heap_used
  .data "Heap used: " $00
msg_bytes
  .data " bytes\n" $00
msg_fwdref_count
  .data "Forward references forced to absolute: " $00
  .endif


HEAP                   ; Heap goes after the program code


* = $FFFC
  .data start           ; Reset vector
  .data interrupt       ; Interrupt vector
