; Command mode handler
;
; Commands:
;   :w       - save file
;   :q       - quit (warn if modified)
;   :wq      - save and quit
;   :q!      - quit without saving
;   :NNN     - go to line NNN

CMD_BUF     = $0300   ; Command buffer (256 bytes)
CMD_BUF_LEN = $00FF   ; Max command length

  .zeropage
CMD_IDX:     .byte     ; Current index into command buffer
CMD_QUIT:    .byte     ; Set to $FF when editor should quit

  .code

; Enter command mode - show prompt and read command
command_handle:
  LDA #0
  STA CMD_IDX

  ; Show ':' prompt on last line
  JSR command_show_prompt

.read_loop:
  JSR get_key
  STA BUF_TEMP

  LDA #<command_keys
  LDX #>command_keys
  JSR dispatch_key
  BCC .check_done

  ; No match - printable character?
  LDA BUF_TEMP
  CMP #' '
  BCC .read_loop
  CMP #$7F
  BCS .read_loop

  ; Add to buffer
  LDX CMD_IDX
  CPX #CMD_BUF_LEN
  BCS .read_loop  ; Buffer full
  STA CMD_BUF,X
  INC CMD_IDX

  ; Echo character
  JSR io_write
  JSR io_flush
  JMP .read_loop

.check_done:
  LDA MODE
  CMP #MODE_COMMAND
  BNE .done
  LDA CMD_QUIT
  BNE .done
  JMP .read_loop
.done:
  RTS

; --- Command input dispatch table ---
command_keys:
  .byte KEY_ESC     .word cmd_cancel
  .byte KEY_ENTER   .word cmd_execute
  .byte KEY_BS      .word cmd_backspace
  .byte $7F         .word cmd_backspace
  .byte 0           ; End sentinel

cmd_cancel:
  LDA #MODE_NORMAL
  STA MODE
  RTS

cmd_execute:
  ; Null-terminate the command
  LDX CMD_IDX
  LDA #0
  STA CMD_BUF,X

  ; Parse and execute
  JSR command_parse

  ; Return to normal mode (unless quitting)
  LDA CMD_QUIT
  BNE .stay
  LDA #MODE_NORMAL
  STA MODE
.stay:
  RTS

cmd_backspace:
  LDA CMD_IDX
  BEQ cmd_cancel     ; Nothing to delete, cancel
  DEC CMD_IDX
  JMP erase_char

; Show the ':' prompt on the status line
command_show_prompt:
  LDA #':'
  JMP show_prompt

; Parse and execute the command in CMD_BUF
command_parse:
  LDA CMD_BUF
  STA BUF_TEMP
  LDA #<command_parse_keys
  LDX #>command_parse_keys
  JSR dispatch_key
  BCC .done

  ; Try named commands (full string match from CMD_BUF[0])
  SET16 str_marks_cmd, STR_PTR16
  LDX #0
  JSR cmd_str_match
  BCC .do_marks

  ; Range/goto: digit
  LDA CMD_BUF
  CMP #'0'
  BCC .unknown
  CMP #':'              ; '9'+1
  BCS .unknown
  JMP command_parse_range

.do_marks:
  JMP marks_display

.unknown:
  JMP cmd_unknown

.done:
  RTS

; --- Command parse dispatch table ---
command_parse_keys:
  .byte 'w'    .word cmd_parse_w
  .byte 'q'    .word cmd_parse_q
  .byte '\''   .word command_parse_range
  .byte '.'    .word command_parse_range
  .byte '>'    .word cmd_parse_bare_shift
  .byte '<'    .word cmd_parse_bare_shift
  .byte 0      ; End sentinel

cmd_parse_w:
  LDA READONLY
  BEQ .not_readonly
  JMP show_readonly_msg
.not_readonly:
  LDA CMD_BUF + 1
  BEQ .do_write       ; Just ":w"
  CMP #'q'
  BEQ .check_wq
  JMP cmd_unknown

.check_wq:
  LDA CMD_BUF + 2
  BNE cmd_unknown     ; Extra chars after ":wq"
  ; :wq - write and quit
  JSR command_write_file
  LDA #$FF
  STA CMD_QUIT
  RTS

.do_write:
  JMP command_write_file

cmd_parse_q:
  LDA CMD_BUF + 1
  BEQ .do_quit        ; Just ":q"
  CMP #'!'
  BEQ .force_quit
  JMP cmd_unknown

.do_quit:
  ; Check if modified
  LDA MODIFIED
  BEQ .quit_ok
  ; Show warning
  LDA #<str_no_write
  LDX #>str_no_write
  JMP show_message_ax

.quit_ok:
  LDA #$FF
  STA CMD_QUIT
  RTS

.force_quit:
  LDA CMD_BUF + 2
  BNE cmd_unknown     ; Extra chars after ":q!"
  LDA #$FF
  STA CMD_QUIT
  RTS

cmd_parse_bare_shift:
  CP16 FILE_LINE16, BUF_SRC16
  CP16 FILE_LINE16, BUF_DST16
  LDA CMD_BUF
  JMP range_dispatch

cmd_unknown:
  LDA #<str_unknown_cmd
  LDX #>str_unknown_cmd
  JMP show_message_ax

; Parse decimal number from CMD_BUF starting at offset X
; Returns: BUF_LEN16 = parsed number, X = updated offset past digits
;          carry clear = valid number, carry set = no digits found
; Clobbers: A, BUF_LEN16, BUF_SRC16
parse_decimal:
  SET16 $0000, BUF_LEN16
  STX CMD_IDX              ; Save start offset
.loop:
  LDA CMD_BUF,X
  SEC
  SBC #'0'
  BMI .done
  CMP #10
  BCS .done

  ; Multiply BUF_LEN16 by 10 and add digit
  PHA
  ASL16 BUF_LEN16
  CP16 BUF_LEN16, BUF_SRC16
  ASL16 BUF_LEN16
  ASL16 BUF_LEN16
  CLC
  ADC16 BUF_LEN16, BUF_SRC16, BUF_LEN16
  PLA
  CLC
  ADCA16 BUF_LEN16, BUF_LEN16

  INX
  JMP .loop
.done:
  CPX CMD_IDX
  BEQ .no_digits
  CLC
  RTS
.no_digits:
  SEC
  RTS

; Parse one range position starting at CMD_BUF[X]
; Handles: 'x (mark), . (current line), decimal number (1-based)
; Returns: BUF_LEN16 = 0-based line number, X = updated offset
;          carry clear = success, carry set = error
; Clobbers: A
parse_range_pos:
  LDA CMD_BUF,X
  CMP #'\''
  BEQ .mark
  CMP #'.'
  BEQ .dot
  ; Try decimal number
  JSR parse_decimal        ; BUF_LEN16 = number, X = updated offset
  BCS .error
  ; Convert 1-based to 0-based (0 stays at 0 = first line)
  TST16 BUF_LEN16
  BEQ .num_ok
  SEC
  SBCI16 BUF_LEN16, $0001, BUF_LEN16
  ; Clamp to LINE_COUNT16-1
  CMP16 BUF_LEN16, LINE_COUNT16
  BCC .num_ok
  SEC
  SBCI16 LINE_COUNT16, $0001, BUF_LEN16
.num_ok:
  CLC
  RTS
.mark:
  INX                     ; Skip quote
  LDA CMD_BUF,X
  INX                     ; Skip mark letter
  ; Save X (CMD_BUF offset), mark_get returns result in A/X
  STX CMD_IDX
  JSR mark_get            ; A = low, X = high, carry set if invalid
  BCS .error
  STA BUF_LEN16
  STX BUF_LEN16 + 1
  LDX CMD_IDX
  CLC
  RTS
.dot:
  INX                     ; Skip dot
  CP16 FILE_LINE16, BUF_LEN16
  CLC
  RTS
.error:
  SEC
  RTS

; Write (save) the file
command_write_file:
  ; Open file for writing
  LDAX16 FNAME_PTR16
  JSR openout
  STA FILE_HANDLE

  ; Write buffer contents
  LDA FILE_HANDLE
  JSR buf_save_file

  ; Close file
  LDA FILE_HANDLE
  JSR close

  ; Clear modified flag
  LDA #0
  STA MODIFIED

  ; Show confirmation on status line
  JSR command_show_prompt
  LDA #'"'
  JSR io_write
  JSR write_fname
  LDA #'"'
  JSR io_write
  LDA #' '
  JSR io_write

  ; Print " written"
  PRINT_STR str_written

  JSR io_flush
  ; Brief pause to show message - wait for next redraw
  RTS

; Show "Buffer full" status message
show_buffer_full_msg:
  LDA #<str_buffer_full
  LDX #>str_buffer_full
  ; fall through

; Show status message with string address in A (low) / X (high)
show_message_ax:
  STA STR_PTR16
  STX STR_PTR16 + 1
  ; fall through

; Show a status message and wait for keypress
; STR_PTR16 must be set to the message string before calling
show_status_message:
  ; Save message pointer (command_show_prompt clobbers STR_PTR16)
  PUSH16 STR_PTR16
  JSR command_show_prompt
  POP16 STR_PTR16
  JSR write_string
  JMP flush_get_key

; Compare CMD_BUF (starting at offset X) against asciiz string at STR_PTR16
; Input: X = starting offset in CMD_BUF, STR_PTR16 = string to match
; Returns: carry clear = match, carry set = no match
; Clobbers: A, X, Y
cmd_str_match:
  LDY #0
.loop:
  LDA (STR_PTR16),Y
  BEQ .check_end
  CMP CMD_BUF,X
  BNE .no_match
  INX
  INY
  JMP .loop
.check_end:
  LDA CMD_BUF,X
  BNE .no_match
  CLC
  RTS
.no_match:
  SEC
  RTS

; Parse range or goto command
; Handles: :'a,.y  :'a,'bd  :1,3d  :1,.y  :.,'ay  :NNN (goto)
command_parse_range:
  LDX #0
  JSR parse_range_pos     ; Parse first position -> BUF_LEN16
  BCC .range_first_ok
  JMP range_mark_err
.range_first_ok:
  CP16 BUF_LEN16, BUF_SRC16

  ; Check for comma (range) or end (goto)
  LDA CMD_BUF,X
  CMP #','
  BEQ .range_has_comma

  ; No comma: maybe :NNN goto
  CMP #0
  BEQ .range_goto

  ; Single-position + command (e.g. :.> or :5d)
  CP16 BUF_SRC16, BUF_DST16   ; end = start
  LDA CMD_BUF,X                ; command char
  JMP range_dispatch

.range_goto:
  ; :NNN goto (BUF_SRC16 = 0-based line)
  CP16 BUF_SRC16, FILE_LINE16
  LDA #0
  STA_LH16 CURSOR_COL16
  JMP clamp_cursor_col

.range_has_comma:
  INX                     ; Skip comma
  PUSH16 BUF_SRC16        ; Save first position (parse_decimal clobbers BUF_SRC16)
  JSR parse_range_pos     ; Parse second position -> BUF_LEN16
  POP16 BUF_SRC16         ; PLA preserves carry on 6502
  BCC .range_second_ok
  JMP range_mark_err
.range_second_ok:
  CP16 BUF_LEN16, BUF_DST16

  ; Get command char
  LDA CMD_BUF,X
  JMP range_dispatch

range_dispatch:
  ; A = command char
  STA CMD_IDX              ; Save command char

  ; Ensure start <= end (swap if needed)
  CMP16 BUF_SRC16, BUF_DST16
  BCC .range_order_ok
  BEQ .range_order_ok
  ; Swap BUF_SRC16 and BUF_DST16
  LDA BUF_SRC16
  PHA
  LDA BUF_DST16
  STA BUF_SRC16
  PLA
  STA BUF_DST16
  LDA BUF_SRC16 + 1
  PHA
  LDA BUF_DST16 + 1
  STA BUF_SRC16 + 1
  PLA
  STA BUF_DST16 + 1
.range_order_ok:

  ; count = end - start + 1
  SEC
  SBC16 BUF_DST16, BUF_SRC16, BUF_LEN16
  INC16 BUF_LEN16

  ; Copy full 16-bit count to BUF_TEMP16 (no 255 cap)
  CP16 BUF_LEN16, BUF_TEMP16

  ; Readonly check for editing commands (d, >, <) — yank allowed
  LDA CMD_IDX
  CMP #'y'
  BEQ .range_dispatch_cmd
  LDA READONLY
  BNE show_readonly_msg

.range_dispatch_cmd:
  LDA CMD_IDX
  STA BUF_TEMP
  LDA #<range_action_keys
  LDX #>range_action_keys
  JSR dispatch_key
  BCC .done
  JMP cmd_unknown
.done:
  RTS

; Shared read-only rejection message (also used by cmd_parse_w)
show_readonly_msg:
  LDA #<str_readonly
  LDX #>str_readonly
  JMP show_message_ax

; --- Range action dispatch table ---
range_action_keys:
  .byte 'y'   .word range_do_yank
  .byte 'd'   .word range_do_delete
  .byte '>'   .word range_do_indent
  .byte '<'   .word range_do_unindent
  .byte 0     ; End sentinel

  ; --- Range yank ---
range_do_yank:
  JSR yank_clear
  LDAX16 BUF_SRC16
  JSR yank_add_lines
  BCS range_yank_full

  ; Show "N lines yanked"
  LDA #<str_lines_yanked
  LDX #>str_lines_yanked
  JMP report_yank_lines_ax

range_yank_full:
  JSR yank_clear
  LDA #<str_yank_full
  LDX #>str_yank_full
  JMP show_message_ax

  ; --- Range delete ---
range_do_delete:
  ; Yank lines first (so user can paste them back)
  ; Save first line (yank_add_lines clobbers BUF_SRC16)
  PUSH16 BUF_SRC16
  JSR yank_clear
  LDAX16 BUF_SRC16
  JSR yank_add_lines
  POP16 BUF_SRC16          ; PLA preserves carry on 6502
  BCS range_yank_full

  ; Adjust marks before deletion (mark_adjust_delete clobbers BUF_SRC16/BUF_DST16)
  CP16 YANK_LINES16, BUF_TEMP16
  PUSH16 BUF_SRC16
  LDAX16 BUF_SRC16
  JSR mark_adjust_delete
  POP16 BUF_SRC16

  ; Delete lines (buf_delete_lines clobbers BUF_SRC16)
  CP16 YANK_LINES16, BUF_TEMP16
  PUSH16 BUF_SRC16
  LDAX16 BUF_SRC16
  JSR buf_delete_lines
  POP16 BUF_SRC16

  ; Move cursor to first deleted line position
  CP16 BUF_SRC16, FILE_LINE16

  ; Clamp cursor if past end of file
  CMP16 FILE_LINE16, LINE_COUNT16
  BCC .range_del_ok
  SEC
  SBCI16 LINE_COUNT16, $0001, FILE_LINE16
.range_del_ok:
  LDA #$FF
  STA MODIFIED
  JSR clamp_cursor_col

  ; Show "N lines deleted"
  LDA #<str_lines_deleted
  LDX #>str_lines_deleted
  JMP report_yank_lines_ax

  ; --- Range indent ---
  ; The cores adjust the cursor column when the cursor's line is inside
  ; the range; the cursor line itself never moves.
range_do_indent:
  JSR range_shift_setup
  JSR insert_spaces_core
  JMP range_shift_finish

  ; --- Range unindent ---
range_do_unindent:
  JSR range_shift_setup
  JSR remove_spaces_core
  JMP range_shift_finish

range_shift_setup:
  CP16 BUF_SRC16, UNDO_LINE16  ; Range start (BUF_TEMP16 = count already)
  LDA #INDENT_WIDTH
  STA BUF_DELTA
  STA SHIFT_UNDO_WIDTH
  LDA #0
  STA SHIFT_MODE
  RTS

range_shift_finish:
  JSR clamp_cursor_col         ; Clamp (unindent may shorten line)
  CP16 UNDO_PASTE_COUNT16, TO_DECIMAL_VALUE16
  LDA #<str_lines_shifted
  LDX #>str_lines_shifted
  ; fall through

; Report count on the status line: "N <suffix>"
; Input: A/X = suffix string, TO_DECIMAL_VALUE16 = count
report_lines_ax:
  STA STR_PTR16
  STX STR_PTR16 + 1
report_lines:
  ; command_show_prompt clobbers STR_PTR16 and TO_DECIMAL state
  ; (its cursor positioning goes through write_byte_dec/to_decimal)
  PUSH16 STR_PTR16
  PUSH16 TO_DECIMAL_VALUE16
  JSR command_show_prompt
  POP16 TO_DECIMAL_VALUE16
  JSR print_decimal
  POP16 STR_PTR16
  JSR write_string
  JMP io_flush

; Same, with count taken from YANK_LINES16
report_yank_lines_ax:
  STA STR_PTR16
  STX STR_PTR16 + 1
  CP16 YANK_LINES16, TO_DECIMAL_VALUE16
  JMP report_lines

range_mark_err:
  LDA #<str_mark_not_set
  LDX #>str_mark_not_set
  JMP show_message_ax

str_lines_yanked:  .asciiz " lines yanked"
str_lines_deleted: .asciiz " lines deleted"
str_lines_shifted: .asciiz " lines shifted"
str_marks_cmd:     .asciiz "marks"

; === String constants ===
str_unknown_cmd: .asciiz "Unknown command"
str_no_write:    .asciiz "No write since last change (use :q! to override)"
str_written:     .asciiz "written"
str_buffer_full: .asciiz "Buffer full"
str_readonly:    .asciiz "Read-only (file truncated)"
str_truncated:   .asciiz "WARNING: File too large - read only"
str_yank_full:   .asciiz "Yank buffer full"
str_mark_not_set: .asciiz "Mark not set"
