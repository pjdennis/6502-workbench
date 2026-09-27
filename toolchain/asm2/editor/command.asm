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
;              position is NNN, . or 'x (mark); with no range, the
;              current line

CMD_BUF     = $0300   ; Command buffer (128 bytes)
CMD_BUF_LEN = $007F   ; Max command length

; (zero-page variables: zp.asm)

; Enter command mode: read a command line and execute it
command_handle:
  LDA #MODE_NORMAL
  STA MODE                 ; Normal mode afterwards (a quit exits first)
  LDA #':'
  JSR read_line
  BCC command_parse
cmd_ret:
  RTS                      ; Cancelled, or done

; Parse and execute the command in CMD_BUF (an empty one does nothing)
command_parse:
  LDA CMD_BUF
  BEQ cmd_ret
  STA BUF_TEMP
  LDA #<command_parse_keys
  LDX #>command_parse_keys
  JSR dispatch_key
  BCC cmd_ret
  ; fall through: anything else is a range command or a goto

; Parse range or goto command
; Handles: :'a,.y  :'a,'bd  :1,3d  :1,.y  :.,'ay  :5,d  :,5d  :NNN and
; :N,M (goto), and a command with no range (:d :y :> :<), which works on
; the current line.  A letter that is not a command says so.
command_parse_range:
  LDX #0
  JSR parse_range_pos     ; Parse first position -> BUF_LEN16
  BCS range_mark_err
  CP16 BUF_LEN16, BUF_SRC16

  ; Comma (range), or the command char (0: none)
  LDA CMD_BUF,X
  CMP #','
  BNE range_dispatch      ; One position (:5, :.>, :5d): end = start

  INX                     ; Skip comma
  JSR parse_range_pos     ; Parse second position -> BUF_LEN16
  BCS range_mark_err
  LDA CMD_BUF,X           ; Command char
  ; fall through

; Run a range command, or with none (A = 0) go to the range's last line
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

  ; Readonly check for the editing commands (d, >, <): yank is allowed,
  ; and any other letter is an unknown command
  LDA BUF_TEMP
  BEQ range_goto          ; No command
  CMP #'d'
  BEQ .range_edit
  CMP #'>'
  BEQ .range_edit
  CMP #'<'
  BNE .range_dispatch_cmd
.range_edit:
  LDA READONLY
  BNE show_readonly_msg

.range_dispatch_cmd:
  LDA #<range_action_keys
  LDX #>range_action_keys
  JSR dispatch_key
  BCS cmd_unknown
  RTS

range_goto:
  ; :NNN and :N,M go to the last line of the range, as in vim (BUF_LEN16
  ; = 0-based line). Command mode was entered through clear_count, so the
  ; extra clear_count here changes nothing.
  CP16 BUF_LEN16, FILE_LINE16
  JMP first_nonblank_clear

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
  BNE .not_bare       ; Not just ":q"
  ; Check if modified
  LDA MODIFIED
  BEQ cmd_set_quit
  ; Show warning
  LDA #<str_no_write
  LDX #>str_no_write
  JMP show_message_ax

.not_bare:
  CMP #'!'
  BNE cmd_unknown
  LDA CMD_BUF + 2
  BNE cmd_unknown     ; Extra chars after ":q!"
cmd_set_quit:
  DEC CMD_QUIT        ; $00 -> $FF: quit
  RTS

cmd_parse_w:
  LDA READONLY
  BNE show_readonly_msg
  LDA CMD_BUF + 1
  BEQ command_write_file  ; Just ":w"
  CMP #'q'
  BNE cmd_unknown
  LDA CMD_BUF + 2
  BNE cmd_unknown     ; Extra chars after ":wq"
  ; :wq - quit once written (a failed open clears this again)
  DEC CMD_QUIT
  ; fall through

; Write (save) the file. If it cannot be opened, show an error and leave
; MODIFIED set and CMD_QUIT clear (a failed :wq does not quit).
command_write_file:
  ; Open file for writing
  LDAX16 FNAME_PTR16
  JSR openout
  TAX                 ; Handle 0: could not open
  BEQ .open_failed

  ; Write buffer contents (buf_save_file keeps the handle in FILE_HANDLE)
  JSR buf_save_file

  ; Close file
  LDA FILE_HANDLE
  JSR close

  ; Clear modified flag
  LDA #0
  STA MODIFIED

  ; Show confirmation on status line: "name" written
  JSR status_line_clear
  LDA #'"'
  JSR text_putc
  JSR write_fname
  LDA #<str_written
  LDX #>str_written
  JMP hold_message_ax

.open_failed:
  STA CMD_QUIT        ; A = 0
  LDA #<str_cant_write
  LDX #>str_cant_write
  JMP show_message_ax

; --- Command parse dispatch table ---
command_parse_keys:
  .byte 'w'    .word cmd_parse_w
  .byte 'q'    .word cmd_parse_q
  .byte 'm'    .word cmd_parse_m
  .byte 0      ; End sentinel

; Parse one range position starting at CMD_BUF[X]
; Handles: 'x (mark), . (current line), decimal number (1-based); none
; (any other char) is the current line, as in vim (:5,d = :5,.d)
; Returns: BUF_LEN16 = 0-based line number, X = updated offset
;          carry clear = success, carry set = error (mark not set)
; Clobbers: A, Y, CMD_IDX, BUF_DST16
parse_range_pos:
  LDA CMD_BUF,X
  CMP #'.'
  BNE .not_dot
  INX                     ; Skip dot
.cur_line:
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
  BCC .clamp              ; Always taken: a stale mark must not point past EOF
.error:
  RTS                     ; Carry set: no such mark
.number:
  ; Decimal number into BUF_LEN16 (from 6400 on, further digits are
  ; ignored: it means the last line all the same)
  LDA #0
  STA_LH16 BUF_LEN16
  STX CMD_IDX             ; Save start offset
.digit_loop:
  LDA CMD_BUF,X
  SEC
  SBC #'0'
  CMP #10
  BCS .digits_done
  JSR mul10_add           ; BUF_LEN16 = BUF_LEN16 * 10 + digit
  INX
  BNE .digit_loop         ; Always taken (CMD_BUF is null-terminated)
.digits_done:
  CPX CMD_IDX
  BEQ .cur_line           ; No digits: the current line
  ; Convert 1-based to 0-based (0 stays at 0 = first line)
  TST16 BUF_LEN16
  BEQ .num_ok
  DEC16 BUF_LEN16
.clamp:
  ; Clamp to LINE_COUNT16-1
  CMP16 BUF_LEN16, LINE_COUNT16
  BCC .num_ok
  SEC
  SBCI16 LINE_COUNT16, $0001, BUF_LEN16
.num_ok:
  CLC
  RTS

; Read a line on the status line into CMD_BUF (the ':' and the '/' '?'
; prompts)
; Input: A = prompt character
; Returns: carry clear on Enter: CMD_BUF null-terminated, X = length
;          carry set on ESC, or on backspace with nothing left to delete
; Only printable characters ($20-$7E) are stored, up to CMD_BUF_LEN and
; as many as fit the status row after the prompt (SCREEN_COLS - 2).
; X holds the length throughout: get_key, erase_char and text_flush
; preserve it.
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
  LDY TEXT_LEFT
  DEY
  BEQ .loop                ; Status row full
  STA CMD_BUF,X
  INX
  JSR text_flush           ; Echo
  JMP .loop
.enter:
  LDA #0
  STA CMD_BUF,X            ; Null-terminate
  CLC
.ret:
  RTS

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

; A yank that does not fit changes nothing: the yank buffer, the text,
; and the cursor, which goes back where the command was typed (d0, db,
; cb, yb and :d moved it to the start of their range first)
range_yank_full:
  CP16 SNAP_LINE16, FILE_LINE16
  CP16 SNAP_COL16, CURSOR_COL16
  LDA #<str_yank_full
  LDX #>str_yank_full
  JMP show_message_ax

  ; --- Range delete ---
  ; Same as dd with the cursor moved to the range start: yanks the lines,
  ; records undo, adjusts marks, deletes and clamps FILE_LINE16. A yank
  ; that does not fit changes nothing (range_yank_full).
range_do_delete:
  CP16 BUF_SRC16, FILE_LINE16  ; BUF_TEMP16 = count already
  JSR first_nonblank           ; (where u returns, as in vim)
  JSR yank_delete_current_lines
  BCS range_yank_full
  JSR set_modified
  JSR first_nonblank

  ; Show "N lines deleted"
  LDA #<str_lines_deleted
  LDX #>str_lines_deleted
  JMP report_yank_lines_ax

  ; --- Range indent ---
  ; The shift starts on the first non-blank of the range's first line
  ; (as vim does, and u returns there); the cursor then goes to the first
  ; non-blank of its last line, as in vim.
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
  CP16 BUF_SRC16, FILE_LINE16  ; Range start (BUF_TEMP16 = count already)
  JSR first_nonblank
  JMP shift_unit_setup

range_shift_finish:
  SEC
  SBCI16 LINE_LEN16, 1, FILE_LINE16  ; The range's last line
  JSR first_nonblank_clear     ; (the cores total the shift in COUNT16)
  CP16 SHIFT_LINES16, TO_DECIMAL_VALUE16
  LDA #<str_lines_shifted
  LDX #>str_lines_shifted
  ; fall through

; Report count on the status line: "N <suffix>"
; Input: A/X = suffix string, TO_DECIMAL_VALUE16 = count
report_lines_ax:
  ; status_line_clear clobbers STR_PTR16 and TO_DECIMAL state
  ; (its cursor positioning goes through write_byte_dec/to_decimal)
  PHA
  TXA
  PHA
  PUSH16 TO_DECIMAL_VALUE16
  JSR status_line_clear
  POP16 TO_DECIMAL_VALUE16
  JSR print_decimal
  BEQ pop_hold_message        ; Always taken (print_string ends with Z = 1)

; Show "Buffer full" status message
show_buffer_full_msg:
  LDA #<str_buffer_full
  LDX #>str_buffer_full
  ; fall through

; Show the message at A (low) / X (high) on the status row, held there
; until the next key, which then runs as usual (as in vim)
show_message_ax:
  ; Keep the address on the stack: status_line_clear clobbers STR_PTR16
  PHA
  TXA
  PHA
  JSR status_line_clear
pop_hold_message:
  PLA
  TAX
  PLA
  ; fall through

; Print the text at A (low) / X (high) after a message on the status row
; and keep it there until the next key: the frame that ends the command
; leaves the status bar alone (status_build)
hold_message_ax:
  INC STATUS_HOLD
  JMP print_string_ax

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
str_cant_write:  .asciiz "Can't open file for writing"
str_buffer_full: .asciiz "Buffer full"
str_readonly:    .asciiz "Read-only (file truncated)"
str_truncated:   .asciiz "WARNING: File too large - read only"
str_yank_full:   .asciiz "Yank buffer full"
str_mark_not_set: .asciiz "Mark not set"
