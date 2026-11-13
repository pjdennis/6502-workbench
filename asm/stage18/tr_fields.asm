; tr_fields.asm - Field dispatch, handlers, and prefix matching


; ============================================================================
; FIELD DISPATCH
; ============================================================================

; Check if line is a --- separator
; On exit: C clear = is separator, C set = not
tr_check_separator:
  LDA TR_LINE_LEN
  CMP #$03
  BNE .no
  LDA TR_LINE_BUF
  CMP #'-'
  BNE .no
  LDA TR_LINE_BUF + 1
  CMP #'-'
  BNE .no
  LDA TR_LINE_BUF + 2
  CMP #'-'
  BNE .no
  CLC
  RTS
.no:
  SEC
  RTS

; Field dispatch table: (prefix_ptr, handler_ptr) pairs, null-terminated
tr_field_table:
  .word tr_pfx_name,          tr_handle_name
  .word tr_pfx_input,         tr_handle_input
  .word tr_pfx_expect_hex,    tr_handle_expect_hex
  .word tr_pfx_expect_error,  tr_handle_expect_error
  .word tr_pfx_expect_line,   tr_handle_expect_line
  .word tr_pfx_expect_msg,    tr_handle_expect_msg
  .word tr_pfx_skip,          tr_handle_skip
  .word tr_pfx_args,          tr_handle_args
  .word tr_pfx_expect_stderr, tr_handle_expect_stderr
  .word 0                     ; sentinel

; Try to match field keywords. Closes input state on match.
; On exit: C clear = field matched and handled
;          C set = no field matched
tr_dispatch_field:
  SET16 tr_field_table, TR_ACTUAL_PTR16
.loop:
  ; Load prefix pointer from table
  LDY #$00
  LDA (TR_ACTUAL_PTR16),Y     ; prefix lo
  STA TR_PTR16
  INY
  LDA (TR_ACTUAL_PTR16),Y     ; prefix hi
  STA TR_PTR16 + 1
  ORA TR_PTR16                   ; null = end of table
  BEQ .no_match
  JSR tr_match_prefix
  BCC .matched
  ; Advance to next entry (+4 bytes)
  CLC
  LDA TR_ACTUAL_PTR16
  ADC #$04
  STA TR_ACTUAL_PTR16
  BCC .loop
  INC TR_ACTUAL_PTR16 + 1
  JMP .loop
.matched:
  JSR tr_close_input_state     ; preserves Y (line offset)
  STY tr_dispatch_save_y
  LDY #$02
  LDA (TR_ACTUAL_PTR16),Y     ; handler lo
  STA TR_PTR16
  INY
  LDA (TR_ACTUAL_PTR16),Y     ; handler hi
  STA TR_PTR16 + 1
  LDY tr_dispatch_save_y       ; restore line offset for handler
  JMP (TR_PTR16)                 ; indirect jump to handler
.no_match:
  SEC
  RTS

tr_dispatch_save_y: .byte 0


; ============================================================================
; FIELD HANDLERS
; ============================================================================

; Handle --- separator: finalize previous test, reset state
tr_handle_separator:
  LDA TR_HAS_TEST
  BEQ .no_prev_test
  JSR tr_finalize_test
.no_prev_test:
  JMP tr_init_test        ; Tail call - reset for next test

; Handle NAME: field - copy test name
; On entry: Y = offset past prefix
tr_handle_name:
  JSR tr_copy_field_to_name
  LDA #$01
  STA TR_HAS_TEST
  CLC
  RTS

; Handle INPUT: field - open temp file, enter input state
tr_handle_input:
  LDA #<TR_INPUT_FILE
  LDX #>TR_INPUT_FILE
  JSR openout
  STA TR_INPUT_HANDLE
  LDA #$01
  STA TR_STATE            ; Enter input state
  CLC
  RTS

; Handle an input content line (strip "N: " prefix, write to temp file)
tr_handle_input_line:
  ; Strip line number prefix: skip spaces, digits, ": "
  LDY #$00
  ; Skip leading spaces
.skip_spaces:
  CPY TR_LINE_LEN
  BCS .write
  LDA TR_LINE_BUF,Y
  CMP #' '
  BNE .skip_digits
  INY
  JMP .skip_spaces
.skip_digits:
  CPY TR_LINE_LEN
  BCS .write
  LDA TR_LINE_BUF,Y
  CMP #'0'
  BCC .write              ; Not a digit
  CMP #':'                ; ':' = $3A, after '9' = $39
  BCS .check_colon
  INY
  JMP .skip_digits
.check_colon:
  CMP #':'
  BNE .write
  INY
  CPY TR_LINE_LEN
  BCS .write
  LDA TR_LINE_BUF,Y
  CMP #' '
  BNE .write
  INY                     ; Skip the space after colon
.write:
  ; Check for bracketed content [...]
  CPY TR_LINE_LEN
  BCS .write_loop
  LDA TR_LINE_BUF,Y
  CMP #'['
  BNE .write_loop
  ; Check if last char is ']'
  LDX TR_LINE_LEN
  DEX
  LDA TR_LINE_BUF,X
  CMP #']'
  BNE .write_loop
  ; Strip brackets: skip '[', exclude ']'
  INY
  STX TR_LINE_LEN          ; TR_LINE_LEN now points to ']' (excluded)
  ; Write from Y to end of line to temp file
.write_loop:
  CPY TR_LINE_LEN
  BCS .write_nl
  LDA TR_LINE_BUF,Y
  LDX TR_INPUT_HANDLE
  JSR write
  INY
  JMP .write_loop
.write_nl:
  ; If line was truncated, stream remaining bytes from test file
  LDA TR_LINE_TRUNC
  BEQ .no_trunc
  JSR tr_stream_input_overflow
.no_trunc:
  LDA #$0A
  LDX TR_INPUT_HANDLE
  JSR write
  RTS

; Stream remaining bytes of a truncated input line from test file to temp input
tr_stream_input_overflow:
.loop:
  LDA TR_FILE_HANDLE
  JSR read
  BCS .done               ; EOF
  CMP #$0A
  BEQ .done               ; Newline ends the line
  LDX TR_INPUT_HANDLE
  JSR write
  JMP .loop
.done:
  LDA #$00
  STA TR_LINE_TRUNC
  RTS

; Handle EXPECT_HEX: field - parse hex bytes
; On entry: Y = offset past prefix
tr_handle_expect_hex:
  LDA #$00
  STA TR_TEST_TYPE        ; Mark as hex test
  STA_LH16 TR_EXPECT_LEN16
  ; Parse hex bytes from buffer
  JSR tr_parse_hex_from_buf
  ; If line was truncated, continue reading hex from file
  LDA TR_LINE_TRUNC
  BEQ .done
  JSR tr_parse_hex_from_file
.done:
  CLC
  RTS

; Handle EXPECT_ERROR: field - parse decimal error code
; On entry: Y = offset past prefix
tr_handle_expect_error:
  LDA #$01
  STA TR_TEST_TYPE        ; Mark as error test
  JSR tr_parse_decimal
  LDA TR_PARSE16
  STA TR_EXPECT_ERROR
  CLC
  RTS

; Handle EXPECT_LINE: field - parse decimal line number
; On entry: Y = offset past prefix
tr_handle_expect_line:
  JSR tr_parse_decimal
  CP16 TR_PARSE16, TR_EXPECT_LINE16
  CLC
  RTS

; Handle EXPECT_MSG: field - copy message string
; On entry: Y = offset past prefix
tr_handle_expect_msg:
  LDX #$00
.loop:
  CPY TR_LINE_LEN
  BCS .done
  LDA TR_LINE_BUF,Y
  STA TR_EXPECT_MSG,X
  INY
  INX
  BNE .loop
.done:
  LDA #$00
  STA TR_EXPECT_MSG,X     ; Null-terminate
  CLC
  RTS

; Handle SKIP: field - set skip flag
tr_handle_skip:
  LDA #$01
  STA TR_SKIP_FLAG
  CLC
  RTS

; Handle ARGS: field - store args string (parsed later)
; On entry: Y = offset past prefix
tr_handle_args:
  ; Copy args to TR_ARGV_STRS for later parsing
  LDX #$00
.loop:
  CPY TR_LINE_LEN
  BCS .done
  LDA TR_LINE_BUF,Y
  STA TR_ARGV_STRS,X
  INY
  INX
  BNE .loop
.done:
  LDA #$00
  STA TR_ARGV_STRS,X      ; Null-terminate
  LDA #$01
  STA TR_ARGV_COUNT        ; Mark that args exist
  CLC
  RTS

; Handle EXPECT_STDERR: field - enter stderr collection state
tr_handle_expect_stderr:
  LDA #$02
  STA TR_TEST_TYPE           ; Mark as stderr test
  STA TR_STATE               ; Enter stderr state
  LDA #$00
  STA_LH16 TR_EXPECT_LEN16   ; Clear expected stderr length
  CLC
  RTS

; Handle a line inside EXPECT_STDERR section
; Copies line bytes to TR_EXPECT_BUF, appending \n between lines
tr_handle_stderr_line:
  ; Check for bracketed content [...]
  LDY #$00
  CPY TR_LINE_LEN
  BCS .no_brackets
  LDA TR_LINE_BUF,Y
  CMP #'['
  BNE .no_brackets
  LDX TR_LINE_LEN
  DEX
  LDA TR_LINE_BUF,X
  CMP #']'
  BNE .no_brackets
  ; Strip brackets: skip '[', exclude ']'
  INY
  STX TR_LINE_LEN
.no_brackets:
  STY tr_stderr_start_y
  ; If not the first line, prepend \n
  LDA TR_EXPECT_LEN16
  ORA TR_EXPECT_LEN16 + 1
  BEQ .no_separator
  LDA #$0A
  JSR tr_store_expect_byte
.no_separator:
  LDY tr_stderr_start_y
.copy:
  CPY TR_LINE_LEN
  BCS .done
  LDA TR_LINE_BUF,Y
  CMP #'{'
  BEQ .check_placeholder
  JSR tr_store_expect_byte
  INY
  JMP .copy
.check_placeholder:
  ; Check if {{MAIN_FILE}} starts at Y
  JSR tr_check_main_file
  BCS .not_placeholder
  ; Substitute _tr_in.tmp
  STY tr_stderr_save_y        ; Save Y (past the placeholder)
  LDY #$00
.sub_loop:
  LDA TR_INPUT_FILE,Y
  BEQ .sub_done
  JSR tr_store_expect_byte
  INY
  JMP .sub_loop
.sub_done:
  LDY tr_stderr_save_y
  JMP .copy
.not_placeholder:
  LDA #'{'
  JSR tr_store_expect_byte
  INY
  JMP .copy
.done:
  RTS

tr_stderr_save_y:  .byte 0
tr_stderr_start_y: .byte 0

; Check if {{MAIN_FILE}} starts at TR_LINE_BUF[Y]
; On entry: Y = index of first '{' in TR_LINE_BUF
; On exit: C clear = matched, Y advanced past '}}'
;          C set = no match, Y unchanged
tr_check_main_file:
  STY tr_cmf_save_y
  LDX #$00
.loop:
  LDA tr_main_file_pattern,X
  BEQ .matched
  CPY TR_LINE_LEN
  BCS .no_match
  CMP TR_LINE_BUF,Y
  BNE .no_match
  INY
  INX
  JMP .loop
.matched:
  CLC
  RTS
.no_match:
  LDY tr_cmf_save_y
  SEC
  RTS

tr_cmf_save_y: .byte 0
tr_main_file_pattern: .asciiz "{{MAIN_FILE}}"

; Close input/stderr state (close temp file if input was being written)
; Preserves Y (callers depend on Y being the prefix offset)
tr_close_input_state:
  LDA TR_STATE
  BEQ .done
  CMP #$02
  BEQ .close_stderr
  TYA
  PHA                       ; Save Y
  LDA TR_INPUT_HANDLE
  JSR close
  LDA #$00
  STA TR_STATE
  PLA
  TAY                       ; Restore Y
.done:
  RTS
.close_stderr:
  LDA #$00
  STA TR_STATE
  RTS


; ============================================================================
; FIELD MATCHING
; ============================================================================

; Check if TR_LINE_BUF starts with the string at (TR_PTR16)
; On entry: TR_PTR16 points to null-terminated prefix string
; On exit: C clear = match, Y = offset past prefix in TR_LINE_BUF
;          C set = no match
tr_match_prefix:
  LDY #$00
.loop:
  LDA (TR_PTR16),Y
  BEQ .match              ; End of prefix → match
  CPY TR_LINE_LEN
  BCS .no_match           ; Line shorter than prefix
  CMP TR_LINE_BUF,Y
  BNE .no_match
  INY
  BNE .loop
.no_match:
  SEC
  RTS
.match:
  CLC
  RTS

; Field prefix strings
tr_pfx_name:          .asciiz "NAME: "
tr_pfx_input:         .asciiz "INPUT:"
tr_pfx_expect_hex:    .asciiz "EXPECT_HEX: "
tr_pfx_expect_error:  .asciiz "EXPECT_ERROR: "
tr_pfx_expect_line:   .asciiz "EXPECT_LINE: "
tr_pfx_expect_msg:    .asciiz "EXPECT_MSG: "
tr_pfx_skip:          .asciiz "SKIP:"
tr_pfx_args:          .asciiz "ARGS: "
tr_pfx_expect_stderr: .asciiz "EXPECT_STDERR:"
