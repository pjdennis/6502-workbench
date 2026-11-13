; tr_verify.asm - Hex, error, and stderr verification logic


; ============================================================================
; HEX VERIFICATION
; ============================================================================

; Verify hex test: read back output file and compare with expected bytes
; On exit: C clear = pass, C set = fail (details already printed)
tr_verify_hex:
  ; First check: assembler should have succeeded
  LDA TR_EXIT_CODE
  BEQ .exit_ok
  ; Assembler failed unexpectedly
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_fail
  TR_SHOW_MESSAGEI tr_msg_expected
  TR_SHOW_MESSAGEI tr_msg_error
  TR_SHOW_CHAR '0'
  TR_SHOW_MESSAGEI tr_msg_got
  TR_SHOW_MESSAGEI tr_msg_error
  JSR tr_print_exit_code
  TR_SHOW_MESSAGEI tr_msg_close_paren
  SEC
  RTS
.exit_ok:
  ; Open output file for reading
  LDA #<TR_OUTPUT_FILE
  LDX #>TR_OUTPUT_FILE
  JSR open
  STA tr_verify_handle
  ; Initialize comparison state
  LDA #$00
  STA_LH16 TR_ACTUAL_LEN16
  STA TR_MISMATCH_FLAG
  SET16 TR_EXPECT_BUF, TR_ACTUAL_PTR16
  ; Read loop: compare each output byte with expected
.read_loop:
  LDA tr_verify_handle
  JSR read
  BCS .eof
  STA tr_verify_byte
  ; Buffer actual byte for failure display (first 256 only)
  LDX TR_ACTUAL_LEN16 + 1
  BNE .skip_buf             ; high byte != 0 → position >= 256
  LDX TR_ACTUAL_LEN16
  STA TR_ACTUAL_BUF,X
.skip_buf:
  ; Compare if within expected range
  CMP16 TR_ACTUAL_LEN16, TR_EXPECT_LEN16
  BCS .beyond
  LDY #$00
  LDA tr_verify_byte
  CMP (TR_ACTUAL_PTR16),Y
  BEQ .match
  ; Mismatch - record if first one
  LDX TR_MISMATCH_FLAG
  BNE .match              ; Already recorded
  STA TR_MISMATCH_ACTUAL
  LDA (TR_ACTUAL_PTR16),Y
  STA TR_MISMATCH_EXPECT
  CP16 TR_ACTUAL_LEN16, TR_MISMATCH_POS16
  LDA #$01
  STA TR_MISMATCH_FLAG
.match:
  INC16 TR_ACTUAL_PTR16
.beyond:
  INC16 TR_ACTUAL_LEN16
  JMP .read_loop
.eof:
  ; Close output file
  LDA tr_verify_handle
  JSR close
  ; Check lengths match
  CMP16 TR_ACTUAL_LEN16, TR_EXPECT_LEN16
  BEQ .lengths_match
  ; Length mismatch
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_fail
  TR_SHOW_MESSAGEI tr_msg_expected
  JSR tr_print_expect_len
  TR_SHOW_MESSAGEI tr_msg_bytes
  TR_SHOW_MESSAGEI tr_msg_got
  JSR tr_print_actual_len
  TR_SHOW_MESSAGEI tr_msg_bytes
  TR_SHOW_MESSAGEI tr_msg_close_paren
  JSR tr_show_failure_dumps
  SEC
  RTS
.lengths_match:
  ; Check for byte mismatch
  LDA TR_MISMATCH_FLAG
  BEQ .hex_pass
  ; Byte mismatch - print details
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_fail
  TR_SHOW_MESSAGEI tr_msg_byte_at
  CP16 TR_MISMATCH_POS16, TO_DECIMAL_VALUE16
  JSR tr_show_decimal
  TR_SHOW_MESSAGEI tr_msg_colon_space
  LDA TR_MISMATCH_EXPECT
  JSR tr_print_hex_byte
  TR_SHOW_MESSAGEI tr_msg_got
  LDA TR_MISMATCH_ACTUAL
  JSR tr_print_hex_byte
  TR_SHOW_MESSAGEI tr_msg_close_paren
  JSR tr_show_failure_dumps
  SEC
  RTS
.hex_pass:
  CLC
  RTS

tr_verify_handle: .byte 0
tr_verify_byte:   .byte 0


; ============================================================================
; ERROR VERIFICATION
; ============================================================================

; Verify error test: check exit code, line number, and message
; On exit: C clear = pass, C set = fail (details already printed)
tr_verify_error:
  ; Check exit code
  LDA TR_EXIT_CODE
  CMP TR_EXPECT_ERROR
  BEQ .code_ok
  JMP .wrong_code
.code_ok:
  ; Check line number (if expected)
  LDA TR_EXPECT_LINE16
  ORA TR_EXPECT_LINE16 + 1
  BEQ .skip_line
  JSR tr_check_stderr_line
  BCC .skip_line
  JMP .wrong_line
.skip_line:
  ; Check message (if expected)
  LDA TR_EXPECT_MSG
  BEQ .pass
  JSR tr_check_stderr_msg
  BCC .pass
  JMP .wrong_msg
.pass:
  CLC
  RTS
.wrong_code:
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_fail
  TR_SHOW_MESSAGEI tr_msg_wrong_code
  TR_SHOW_MESSAGEI tr_msg_exp_prefix
  TR_SHOW_MESSAGEI tr_msg_error
  LDA TR_EXPECT_ERROR
  STA TO_DECIMAL_VALUE16
  LDA #$00
  STA TO_DECIMAL_VALUE16 + 1
  JSR tr_show_decimal
  TR_SHOW_CHAR '\n'
  TR_SHOW_MESSAGEI tr_msg_got_prefix
  TR_SHOW_MESSAGEI tr_msg_error
  JSR tr_print_exit_code
  TR_SHOW_CHAR '\n'
  SEC
  RTS
.wrong_line:
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_fail
  TR_SHOW_MESSAGEI tr_msg_wrong_line
  TR_SHOW_MESSAGEI tr_msg_exp_prefix
  TR_SHOW_MESSAGEI tr_msg_line
  CP16 TR_EXPECT_LINE16, TO_DECIMAL_VALUE16
  JSR tr_show_decimal
  TR_SHOW_CHAR '\n'
  TR_SHOW_MESSAGEI tr_msg_got_prefix
  TR_SHOW_MESSAGEI tr_msg_line
  CP16 TR_PARSE16, TO_DECIMAL_VALUE16
  JSR tr_show_decimal
  TR_SHOW_CHAR '\n'
  SEC
  RTS
.wrong_msg:
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_fail
  TR_SHOW_MESSAGEI tr_msg_wrong_msg
  TR_SHOW_MESSAGEI tr_msg_exp_prefix
  TR_SHOW_MESSAGEI tr_msg_quote
  SET16 TR_EXPECT_MSG, TR_PTR16
  JSR tr_show_message
  TR_SHOW_MESSAGEI tr_msg_quote
  TR_SHOW_CHAR '\n'
  TR_SHOW_MESSAGEI tr_msg_got_prefix
  TR_SHOW_MESSAGEI tr_msg_quote
  JSR tr_print_stderr_msg
  TR_SHOW_MESSAGEI tr_msg_quote
  TR_SHOW_CHAR '\n'
  SEC
  RTS

tr_at_line_str: .asciiz "at line "

; Check "at line N" in stderr, compare N with TR_EXPECT_LINE16
; On exit: C clear = match, C set = mismatch
;          TR_PARSE16 = parsed line number (for error reporting)
tr_check_stderr_line:
  LDY #$00
.search:
  CPY TR_STDERR_LEN
  BCS .not_found
  STY tr_ssl_start
  LDX #$00
.match_str:
  LDA tr_at_line_str,X
  BEQ .found               ; null = full match
  CPY TR_STDERR_LEN
  BCS .not_found
  CMP TR_STDERR_BUF,Y
  BNE .next
  INX
  INY
  JMP .match_str
.next:
  LDY tr_ssl_start
  INY
  JMP .search
.found:
  ; Y now points to the line number digits
  JSR tr_parse_decimal_from_stderr
  CMP16 TR_PARSE16, TR_EXPECT_LINE16
  BEQ .matched
  SEC
  RTS
.matched:
  CLC
  RTS
.not_found:
  SEC
  RTS

tr_ssl_start: .byte 0

; Check message after ": " in stderr matches TR_EXPECT_MSG
; On exit: C clear = match, C set = mismatch
tr_check_stderr_msg:
  ; Search backwards for ": " (the message delimiter)
  LDY TR_STDERR_LEN
  DEY
.search:
  CPY #$01
  BCC .not_found            ; Reached start without finding ": "
  LDA TR_STDERR_BUF - 1,Y
  CMP #':'
  BNE .dec
  LDA TR_STDERR_BUF,Y
  CMP #' '
  BEQ .found
.dec:
  DEY
  JMP .search
.found:
  INY                       ; Y past ": " → start of message
  LDX #$00
.cmp:
  LDA TR_EXPECT_MSG,X
  BEQ .end_expected
  CPY TR_STDERR_LEN
  BCS .mismatch
  CMP TR_STDERR_BUF,Y
  BNE .mismatch
  INX
  INY
  JMP .cmp
.end_expected:
  ; Expected msg fully matched; check actual has ended (newline or end)
  CPY TR_STDERR_LEN
  BCS .match
  LDA TR_STDERR_BUF,Y
  CMP #$0A
  BEQ .match
.mismatch:
.not_found:
  SEC
  RTS
.match:
  CLC
  RTS

; Print the actual error message from TR_STDERR_BUF (after last ": ")
; Searches backwards for ": " delimiter, then prints chars until newline/end
tr_print_stderr_msg:
  LDY TR_STDERR_LEN
  DEY
.search:
  CPY #$01
  BCC .not_found
  LDA TR_STDERR_BUF - 1,Y
  CMP #':'
  BNE .dec
  LDA TR_STDERR_BUF,Y
  CMP #' '
  BEQ .found
.dec:
  DEY
  JMP .search
.found:
  INY                       ; Y past ": " → start of message
.print:
  CPY TR_STDERR_LEN
  BCS .done
  LDA TR_STDERR_BUF,Y
  CMP #$0A
  BEQ .done
  JSR write_d
  INY
  JMP .print
.not_found:
.done:
  RTS

; Parse decimal from TR_STDERR_BUF starting at Y, result in TR_PARSE16
tr_parse_decimal_from_stderr:
  LDA #$00
  STA TR_PARSE16
  STA TR_PARSE16 + 1
.loop:
  CPY TR_STDERR_LEN
  BCS .done
  LDA TR_STDERR_BUF,Y
  CMP #'0'
  BCC .done
  CMP #':'
  BCS .done
  SEC
  SBC #'0'
  STA TR_TEMP
  CP16 TR_PARSE16, TR_SCRATCH16
  ASL16 TR_PARSE16
  ASL16 TR_PARSE16
  CLC
  ADC16 TR_PARSE16, TR_SCRATCH16, TR_PARSE16
  ASL16 TR_PARSE16
  LDA TR_TEMP
  CLC
  ADC TR_PARSE16
  STA TR_PARSE16
  BCC .no_carry
  INC TR_PARSE16 + 1
.no_carry:
  INY
  JMP .loop
.done:
  RTS


; ============================================================================
; STDERR VERIFICATION
; ============================================================================

; Verify stderr test: compare captured stderr with expected
; On exit: C clear = pass, C set = fail (details already printed)
tr_verify_stderr:
  ; Strip trailing \n from actual stderr (if present)
  LDX TR_STDERR_LEN
  BEQ .strip_expected
  DEX
  LDA TR_STDERR_BUF,X
  CMP #$0A
  BNE .strip_expected
  STX TR_STDERR_LEN          ; Trim trailing newline
.strip_expected:
  ; Strip trailing \n from expected stderr (if present)
  LDA TR_EXPECT_LEN16 + 1
  BNE .compare               ; > 255 bytes, skip this optimization
  LDX TR_EXPECT_LEN16
  BEQ .compare
  DEX
  LDA TR_EXPECT_BUF,X
  CMP #$0A
  BNE .compare
  STX TR_EXPECT_LEN16        ; Trim trailing newline
.compare:
  ; Compare lengths first
  LDA TR_EXPECT_LEN16 + 1
  BNE .long_expected          ; Expected > 255 bytes, can't match 8-bit actual
  LDA TR_STDERR_LEN
  CMP TR_EXPECT_LEN16
  BNE .fail
  ; Same length — compare byte by byte
  LDY #$00
.cmp_loop:
  CPY TR_STDERR_LEN
  BCS .pass
  LDA TR_STDERR_BUF,Y
  CMP TR_EXPECT_BUF,Y
  BNE .fail
  INY
  JMP .cmp_loop
.pass:
  CLC
  RTS
.long_expected:
.fail:
  ; Print failure details
  JSR tr_print_test_name
  TR_SHOW_MESSAGEI tr_msg_fail
  TR_SHOW_MESSAGEI tr_msg_wrong_stderr
  TR_SHOW_MESSAGEI tr_msg_exp_prefix
  JSR tr_print_expect_stderr
  TR_SHOW_CHAR '\n'
  TR_SHOW_MESSAGEI tr_msg_got_prefix
  JSR tr_print_actual_stderr
  TR_SHOW_CHAR '\n'
  SEC
  RTS

; Print buffer with continuation indent on newlines
; On entry: TR_PTR16 = buffer pointer, tr_print_len = length
tr_print_with_continuation:
  CP16 TR_PTR16, tr_print_buf16   ; save buffer ptr (TR_SHOW_MESSAGEI clobbers TR_PTR16)
  LDY #$00
.loop:
  CPY tr_print_len
  BCS .done
  LDA (TR_PTR16),Y
  CMP #$0A
  BEQ .newline
  JSR write_d
  INY
  JMP .loop
.newline:
  JSR write_d                 ; Print the \n
  STY tr_print_save_y
  TR_SHOW_MESSAGEI tr_msg_continuation
  CP16 tr_print_buf16, TR_PTR16   ; restore buffer ptr
  LDY tr_print_save_y
  INY
  JMP .loop
.done:
  RTS

tr_print_expect_stderr:
  SET16 TR_EXPECT_BUF, TR_PTR16
  LDA TR_EXPECT_LEN16
  STA tr_print_len
  JMP tr_print_with_continuation

tr_print_actual_stderr:
  SET16 TR_STDERR_BUF, TR_PTR16
  LDA TR_STDERR_LEN
  STA tr_print_len
  JMP tr_print_with_continuation

tr_print_save_y:   .byte 0
tr_print_len:      .byte 0
tr_print_buf16:    .word 0

tr_msg_wrong_stderr:  .asciiz " (stderr mismatch)\n"
tr_msg_continuation:  .asciiz "         "
