; tr_print.asm - Print helpers, summary, failure hex dumps, and error handlers


; ============================================================================
; PRINT HELPERS
; ============================================================================

; Show null-terminated message to stderr
; On entry: TR_PTR16 points to the message
tr_show_message:
  LDY #$00
.loop:
  LDA (TR_PTR16),Y
  BEQ .done
  JSR write_d
  INY
  BNE .loop
  INC TR_PTR16 + 1
  BNE .loop
.done:
  RTS

; Show decimal value to stderr
; On entry: TO_DECIMAL_VALUE16 contains the value
tr_show_decimal:
  JSR to_decimal
  SET16 TO_DECIMAL_RESULT, TR_PTR16
  JMP tr_show_message

; Print TR_EXIT_CODE as decimal
tr_print_exit_code:
  LDA TR_EXIT_CODE
  STA TO_DECIMAL_VALUE16
  LDA #$00
  STA TO_DECIMAL_VALUE16 + 1
  JMP tr_show_decimal

; Print TR_EXPECT_LEN16 as decimal
tr_print_expect_len:
  CP16 TR_EXPECT_LEN16, TO_DECIMAL_VALUE16
  JMP tr_show_decimal

; Print TR_ACTUAL_LEN16 as decimal
tr_print_actual_len:
  CP16 TR_ACTUAL_LEN16, TO_DECIMAL_VALUE16
  JMP tr_show_decimal

; Print byte in A as two hex digits
tr_print_hex_byte:
  PHA
  LSR
  LSR
  LSR
  LSR
  JSR .nibble
  PLA
  AND #$0F
.nibble:
  CMP #$0A
  BCC .digit
  CLC
  ADC #'a'-$0A
  JMP .out
.digit:
  CLC
  ADC #'0'
.out:
  STA $F002               ; Write to stderr
  RTS


; Print summary: "N passed, M failed, K skipped"
tr_print_summary:
  CP16 TR_PASS_COUNT16, TO_DECIMAL_VALUE16
  JSR tr_show_decimal
  TR_SHOW_MESSAGEI tr_msg_sum_passed
  CP16 TR_FAIL_COUNT16, TO_DECIMAL_VALUE16
  JSR tr_show_decimal
  ; Use !!failed!! if there are failures, plain "failed" otherwise
  LDA TR_FAIL_COUNT16
  ORA TR_FAIL_COUNT16 + 1
  BNE .has_failures
  TR_SHOW_MESSAGEI tr_msg_sum_failed
  JMP .print_skipped
.has_failures:
  TR_SHOW_MESSAGEI tr_msg_sum_failed_emphasis
.print_skipped:
  CP16 TR_SKIP_COUNT16, TO_DECIMAL_VALUE16
  JSR tr_show_decimal
  TR_SHOW_MESSAGEI tr_msg_sum_skipped
  RTS

tr_msg_sum_passed:          .asciiz " passed, "
tr_msg_sum_failed:          .asciiz " failed, "
tr_msg_sum_failed_emphasis: .asciiz " !!failed!!, "
tr_msg_sum_skipped:         .asciiz " skipped\n"


; ============================================================================
; FAILURE HEX DUMP DISPLAY
; ============================================================================

; Print expected and actual hex dumps on test failure
; Clobbers A, X, Y, TR_PTR16
tr_show_failure_dumps:
  TR_SHOW_MESSAGEI tr_msg_exp_prefix
  JSR tr_dump_expect_hex
  TR_SHOW_CHAR '\n'
  TR_SHOW_MESSAGEI tr_msg_got_prefix
  JSR tr_dump_actual_hex
  TR_SHOW_CHAR '\n'
  RTS

; Print expected bytes from TR_EXPECT_BUF as hex
; Uses (TR_PTR16),Y indirect addressing for 16-bit indexing
; Prints min(TR_EXPECT_LEN16, 512) bytes
tr_dump_expect_hex:
  SET16 TR_EXPECT_BUF, TR_PTR16
  LDA #$00
  STA tr_dump_pos16
  STA tr_dump_pos16 + 1
.loop:
  CMP16 tr_dump_pos16, TR_EXPECT_LEN16
  BCS .done
  LDY #$00
  LDA (TR_PTR16),Y
  JSR tr_print_hex_byte
  TR_SHOW_CHAR ' '
  INC16 TR_PTR16
  INC16 tr_dump_pos16
  JMP .loop
.done:
  RTS

; Print actual bytes: first from TR_ACTUAL_BUF, then from file if > 256
tr_dump_actual_hex:
  ; Phase 1: print from buffer (up to min(TR_ACTUAL_LEN16, 256))
  LDX #$00
.buf_loop:
  ; Check if X >= TR_ACTUAL_LEN16
  LDA TR_ACTUAL_LEN16 + 1
  BNE .buf_check_x           ; len >= 256, so X < len (X is 8-bit)
  CPX TR_ACTUAL_LEN16
  BCS .done                  ; X >= low byte and high byte is 0
.buf_check_x:
  LDA TR_ACTUAL_BUF,X
  JSR tr_print_hex_byte
  TR_SHOW_CHAR ' '
  INX
  BNE .buf_loop              ; Loop until X wraps (256 bytes max)
  ; Phase 2: if more than 256 bytes, read remaining from file
  LDA TR_ACTUAL_LEN16 + 1
  BEQ .done                  ; len <= 256, all done
  ; Reopen output file
  LDA #<TR_OUTPUT_FILE
  LDX #>TR_OUTPUT_FILE
  JSR open
  STA tr_dump_handle
  ; Skip first 256 bytes
  JSR tr_skip_file_bytes
  ; Print remaining bytes from file
.file_loop:
  LDA tr_dump_handle
  JSR read
  BCS .file_done
  JSR tr_print_hex_byte
  TR_SHOW_CHAR ' '
  JMP .file_loop
.file_done:
  LDA tr_dump_handle
  JSR close
.done:
  RTS

; Skip 256 bytes from file in tr_dump_handle
tr_skip_file_bytes:
  LDY #$00
.loop:
  LDA tr_dump_handle
  JSR read
  BCS .done
  INY
  BNE .loop                  ; Loop 256 times (Y wraps to 0)
.done:
  RTS

tr_dump_pos16:  .word 0
tr_dump_handle: .byte 0


; ============================================================================
; ERROR HANDLERS
; ============================================================================

; Fatal error: EXPECT_HEX buffer overflow (>512 bytes)
tr_err_expect_overflow:
  TR_SHOW_MESSAGEI tr_err_msg_expect_overflow
  SET16 TR_NAME_BUF, TR_PTR16
  JSR tr_show_message
  TR_SHOW_CHAR '\n'
  BRK
  .byte 1

tr_err_msg_expect_overflow:
  .asciiz "FATAL: EXPECT_HEX buffer overflow (>512 bytes) in test: "
