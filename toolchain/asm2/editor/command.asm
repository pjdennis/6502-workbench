; Command mode handler
;
; Commands:
;   :w       - save file
;   :q       - quit (warn if modified)
;   :wq      - save and quit
;   :q!      - quit without saving
;   :NNN     - go to line NNN
;   :marks   - list the set marks
;   :[range]d / y / > / <  - delete, yank, indent, unindent lines, where
;              range is one position or two separated by ',' and a
;              position is NNN, . or 'x (mark); bare :> and :< shift the
;              current line

CMD_BUF     = $0300   ; Command buffer (256 bytes)
CMD_BUF_LEN = $00FF   ; Max command length

  .zeropage
CMD_IDX:     .byte     ; Current index into command buffer
CMD_QUIT:    .byte     ; Set to $FF when editor should quit

  .code

; Enter command mode: read a command line and execute it
command_handle:
  LDA #MODE_NORMAL
  STA MODE                 ; Normal mode afterwards (a quit exits first)
  LDA #':'
  JSR read_line
  BCS cmd_ret              ; Cancelled
  ; fall through

; Parse and execute the command in CMD_BUF
command_parse:
  LDA CMD_BUF
  STA BUF_TEMP
  LDA #<command_parse_keys
  LDX #>command_parse_keys
  JSR dispatch_key
  BCC cmd_ret

  ; Anything else must start with a digit: range or goto
  LDA BUF_TEMP
  SEC
  SBC #'0'
  CMP #10
  BCS cmd_unknown
  ; fall through

; Parse range or goto command
; Handles: :'a,.y  :'a,'bd  :1,3d  :1,.y  :.,'ay  :NNN (goto)
command_parse_range:
  LDX #0
  JSR parse_range_pos     ; Parse first position -> BUF_LEN16
  BCS range_mark_err
  CP16 BUF_LEN16, BUF_SRC16

  ; End (goto), comma (range) or command char
  LDA CMD_BUF,X
  BEQ range_goto
  CMP #','
  BNE range_dispatch      ; Single position (e.g. :.> or :5d): end = start

  INX                     ; Skip comma
  JSR parse_range_pos     ; Parse second position -> BUF_LEN16
  BCS range_mark_err
  LDA CMD_BUF,X           ; Command char
  ; fall through

; Run a range command
; Input: A = command char, BUF_SRC16 = start line, BUF_LEN16 = end line
; (either order); the action gets BUF_SRC16 = first line, BUF_TEMP16 = count
range_dispatch:
  STA BUF_TEMP            ; Command char (dispatch key)

  ; Ensure start <= end (swap if needed)
  CMP16 BUF_LEN16, BUF_SRC16
  BCS .range_order_ok
  LDX #1
.swap:
  LDY BUF_SRC16,X
  LDA BUF_LEN16,X
  STA BUF_SRC16,X
  STY BUF_LEN16,X
  DEX
  BPL .swap
.range_order_ok:

  ; count = end - start + 1 (full 16 bits)
  SEC
  SBC16 BUF_LEN16, BUF_SRC16, BUF_TEMP16
  INC16 BUF_TEMP16

  ; Readonly check for editing commands (d, >, <) — yank allowed
  LDA BUF_TEMP
  CMP #'y'
  BEQ .range_dispatch_cmd
  LDA READONLY
  BNE show_readonly_msg

.range_dispatch_cmd:
  LDA #<range_action_keys
  LDX #>range_action_keys
  JSR dispatch_key
  BCS cmd_unknown
cmd_ret:
  RTS

range_goto:
  ; :NNN goto (BUF_SRC16 = 0-based line). Command mode was entered through
  ; clear_count, so the extra clear_count here changes nothing.
  CP16 BUF_SRC16, FILE_LINE16
  JMP zero_col_clamp_clear

range_mark_err:
  LDA #<str_mark_not_set
  LDX #>str_mark_not_set
  JMP show_message_ax

cmd_unknown:
  LDA #<str_unknown_cmd
  LDX #>str_unknown_cmd
  JMP show_message_ax

; Shared read-only rejection message (also used by cmd_parse_w)
show_readonly_msg:
  LDA #<str_readonly
  LDX #>str_readonly
  JMP show_message_ax

cmd_parse_bare_shift:
  LDAX16 FILE_LINE16      ; Start = end = current line
  STAX16 BUF_SRC16
  STAX16 BUF_LEN16
  LDA BUF_TEMP            ; '>' or '<'
  BNE range_dispatch      ; Always taken

; :marks (the only command starting with 'm'): CMD_BUF+1..+5 must be "arks",0
cmd_parse_m:
  LDX #4
.loop:
  LDA CMD_BUF + 1,X
  CMP str_marks_tail,X
  BNE cmd_unknown
  DEX
  BPL .loop
  JMP marks_display

cmd_parse_q:
  LDA CMD_BUF + 1
  BEQ .do_quit        ; Just ":q"
  CMP #'!'
  BNE cmd_unknown
  LDA CMD_BUF + 2
  BNE cmd_unknown     ; Extra chars after ":q!"
  BEQ cmd_set_quit    ; Always taken

.do_quit:
  ; Check if modified
  LDA MODIFIED
  BEQ cmd_set_quit
  ; Show warning
  LDA #<str_no_write
  LDX #>str_no_write
  JMP show_message_ax

cmd_parse_w:
  LDA READONLY
  BNE show_readonly_msg
  LDA CMD_BUF + 1
  BEQ command_write_file  ; Just ":w"
  CMP #'q'
  BNE cmd_unknown
  LDA CMD_BUF + 2
  BNE cmd_unknown     ; Extra chars after ":wq"
  ; :wq - write and quit
  JSR command_write_file
  ; fall through

cmd_set_quit:
  LDA #$FF
  STA CMD_QUIT
  RTS

; Write (save) the file
command_write_file:
  ; Open file for writing
  LDA #<FNAME_BUF
  LDX #>FNAME_BUF
  JSR openout

  ; Write buffer contents (buf_save_file keeps the handle in FILE_HANDLE)
  JSR buf_save_file

  ; Close file
  LDA FILE_HANDLE
  JSR close

  ; Clear modified flag
  LDA #0
  STA MODIFIED

  ; Show confirmation on status line: :"name" written
  JSR command_show_prompt
  LDA #'"'
  JSR io_write
  JSR write_fname
  PRINT_STR str_written
  JMP io_flush

; --- Command parse dispatch table ---
command_parse_keys:
  .byte 'w'    .word cmd_parse_w
  .byte 'q'    .word cmd_parse_q
  .byte 'm'    .word cmd_parse_m
  .byte '\''   .word command_parse_range
  .byte '.'    .word command_parse_range
  .byte '>'    .word cmd_parse_bare_shift
  .byte '<'    .word cmd_parse_bare_shift
  .byte 0      ; End sentinel

; Parse one range position starting at CMD_BUF[X]
; Handles: 'x (mark), . (current line), decimal number (1-based)
; Returns: BUF_LEN16 = 0-based line number, X = updated offset
;          carry clear = success, carry set = error (mark not set, or
;          no digits)
; Clobbers: A, Y, CMD_IDX, BUF_DST16
parse_range_pos:
  LDA CMD_BUF,X
  CMP #'.'
  BNE .not_dot
  INX                     ; Skip dot
  CP16 FILE_LINE16, BUF_LEN16
  CLC
  RTS
.not_dot:
  CMP #'\''
  BNE .number
  INX                     ; Skip quote
  LDA CMD_BUF,X
  INX                     ; Skip mark letter
  ; Save X (CMD_BUF offset), mark_get returns result in A/X
  STX CMD_IDX
  JSR mark_get            ; A = low, X = high, carry set if invalid
  BCS .error
  STAX16 BUF_LEN16
  LDX CMD_IDX
.error:
  RTS                     ; Carry clear on success
.number:
  ; Decimal number: BUF_LEN16 = BUF_LEN16 * 10 + digit (BUF_DST16 = x2)
  LDA #0
  STA_LH16 BUF_LEN16
  STX CMD_IDX             ; Save start offset
.digit_loop:
  LDA CMD_BUF,X
  SEC
  SBC #'0'
  CMP #10
  BCS .digits_done
  PHA
  ASL16 BUF_LEN16
  CP16 BUF_LEN16, BUF_DST16
  ASL16 BUF_LEN16
  ASL16 BUF_LEN16
  CLC
  ADC16 BUF_LEN16, BUF_DST16, BUF_LEN16
  PLA
  CLC
  ADCA16 BUF_LEN16, BUF_LEN16
  INX
  BNE .digit_loop         ; Always taken (CMD_BUF is null-terminated)
.digits_done:
  CPX CMD_IDX
  BEQ .error              ; No digits (carry set by the equal compare)
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

; Show the ':' prompt on the status line
command_show_prompt:
  LDA #':'
  JMP show_prompt

; Read a line on the status line into CMD_BUF
; Input: A = prompt character
; Returns: carry clear on Enter: CMD_BUF null-terminated, X = length
;          carry set on ESC, or on backspace with nothing left to delete
; Only printable characters ($20-$7E) are stored, up to CMD_BUF_LEN.
; X holds the length throughout: get_key, erase_char, io_write and
; io_flush preserve it.
; Clobbers: A, X, Y
read_line:
  JSR show_prompt
  LDX #0
.loop:
  JSR get_key              ; ($7F arrives as KEY_BS)
  CMP #KEY_ENTER
  BEQ .enter
  CMP #KEY_ESC
  BEQ .ret                 ; Cancel (carry set by the equal compare)
  CMP #KEY_BS
  BNE .char
  TXA
  BEQ .ret                 ; Nothing to delete: cancel (carry still set)
  DEX
  JSR erase_char
  JMP .loop
.char:
  CMP #' '
  BCC .loop                ; Ignore control characters...
  CMP #$7F
  BCS .loop                ; ...and special keys ($80+)
  CPX #CMD_BUF_LEN
  BCS .loop                ; Buffer full
  STA CMD_BUF,X
  INX
  JSR io_write             ; Echo
  JSR io_flush
  JMP .loop
.enter:
  LDA #0
  STA CMD_BUF,X            ; Null-terminate
  CLC
.ret:
  RTS

; Show "Buffer full" status message
show_buffer_full_msg:
  LDA #<str_buffer_full
  LDX #>str_buffer_full
  ; fall through

; Show status message with string address in A (low) / X (high)
; and wait for a keypress
show_message_ax:
  ; Keep the address on the stack: command_show_prompt clobbers STR_PTR16
  PHA
  TXA
  PHA
  JSR command_show_prompt
  PLA
  TAX
  PLA
  JSR write_string_ax
  JMP flush_get_key

; --- Range action dispatch table ---
range_action_keys:
  .byte 'y'   .word range_do_yank
  .byte 'd'   .word range_do_delete
  .byte '>'   .word range_do_indent
  .byte '<'   .word range_do_unindent
  .byte 0     ; End sentinel

  ; --- Range yank ---
range_do_yank:
  LDAX16 BUF_SRC16
  JSR yank_add_lines
  BCS range_yank_full

  ; Show "N lines yanked"
  LDA #<str_lines_yanked
  LDX #>str_lines_yanked
  JMP report_yank_lines_ax

range_yank_full:                 ; (yank_add_lines left the buffer empty)
  LDA #<str_yank_full
  LDX #>str_yank_full
  JMP show_message_ax

  ; --- Range delete ---
range_do_delete:
  ; Yank lines first (so user can paste them back)
  ; Save first line (yank_add_lines clobbers BUF_SRC16)
  PUSH16 BUF_SRC16
  LDAX16 BUF_SRC16
  JSR yank_add_lines
  POP16 BUF_SRC16          ; PLA preserves carry on 6502
  BCS range_yank_full

  ; Adjust marks, delete the lines and clamp, as dd does (no undo record)
  CP16 BUF_SRC16, FILE_LINE16  ; Cursor to the first deleted line
  CP16 YANK_LINES16, BUF_TEMP16
  JSR delete_current_lines
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
  JMP shift_setup_tail

range_shift_finish:
  JSR clamp_cursor_col         ; Clamp (unindent may shorten line)
  CP16 UNDO_RANGE_LINES16, TO_DECIMAL_VALUE16
  LDA #<str_lines_shifted
  LDX #>str_lines_shifted
  ; fall through

; Report count on the status line: "N <suffix>"
; Input: A/X = suffix string, TO_DECIMAL_VALUE16 = count
report_lines_ax:
  ; command_show_prompt clobbers STR_PTR16 and TO_DECIMAL state
  ; (its cursor positioning goes through write_byte_dec/to_decimal)
  PHA
  TXA
  PHA
  PUSH16 TO_DECIMAL_VALUE16
  JSR command_show_prompt
  POP16 TO_DECIMAL_VALUE16
  JSR print_decimal
  PLA
  TAX
  PLA
  JSR write_string_ax
  JMP io_flush

; Same, with count taken from YANK_LINES16
report_yank_lines_ax:
  TAY
  CP16 YANK_LINES16, TO_DECIMAL_VALUE16
  TYA
  JMP report_lines_ax

str_lines_yanked:  .asciiz " lines yanked"
str_lines_deleted: .asciiz " lines deleted"
str_lines_shifted: .asciiz " lines shifted"
str_marks_tail:    .asciiz "arks"

; === String constants ===
str_unknown_cmd: .asciiz "Unknown command"
str_no_write:    .asciiz "No write since last change (use :q! to override)"
str_written:     .byte '"'         ; Closing quote after the file name
                 .asciiz " written"
str_buffer_full: .asciiz "Buffer full"
str_readonly:    .asciiz "Read-only (file truncated)"
str_truncated:   .asciiz "WARNING: File too large - read only"
str_yank_full:   .asciiz "Yank buffer full"
str_mark_not_set: .asciiz "Mark not set"
