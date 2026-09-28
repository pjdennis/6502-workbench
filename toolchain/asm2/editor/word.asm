; Word motion support - character classification and word boundary routines
;
; Provides char_class (classify byte), the word motions w, b, e and ^,
; and the multi-line word range routines of the word operators.

; (zero-page variables: zp.asm)

; Class of the char at the cursor while the cursor is on the line
; (LINE_LEN16): A = class (see char_class; N clear, Z set for
; whitespace).  At or past the end of the line: A = $FF (N set).
; BUF_PTR16 = the cursor's address, which next_class and prev_class
; then step with it.  Clobbers: A, X, Y
class_in_line:
  JSR get_cursor_buf_ptr
  BCC ptr_class_in_line      ; Always (C = 0 from the address add)

; Step the cursor and BUF_PTR16 (its address) right, then classify it as
; class_in_line does
next_class:
  INC16 BUF_PTR16
  INC16 CURSOR_COL16
ptr_class_in_line:
  CMP16 CURSOR_COL16, LINE_LEN16
  BCC class_at_ptr
  LDA #$FF
  RTS

; Step the cursor and BUF_PTR16 (its address) left, then classify it
; (A = class, see char_class).  Clobbers: A, Y (Y = 0)
prev_class:
  DEC16 BUF_PTR16
  JSR dec_cursor_col
  ; fall through into class_at_ptr

; Classify char at BUF_PTR16 -> A = class (see char_class)
; Clobbers: A, Y (Y = 0)
class_at_ptr:
  LDY #0
  LDA (BUF_PTR16),Y
  ; fall through into char_class

; Classify byte in A -> A = 0 (whitespace: space, tab, newline),
; 1 (word: a-zA-Z0-9_), 2 (anything else: punctuation); Z set for whitespace
char_class:
  CMP #'_'
  BEQ .word
  CMP #'0'
  BCC .below_digits
  CMP #'9' + 1
  BCC .word
  ORA #$20                ; Fold A-Z onto a-z (no other byte lands there)
  CMP #'a'
  BCC .punct
  CMP #'z' + 1
  BCC .word
.punct:
  LDA #2
  RTS
.below_digits:
  CMP #' '
  BEQ .whitespace
  CMP #'\t'
  BEQ .whitespace
  CMP #'\n'
  BNE .punct
.whitespace:
  LDA #0
  RTS
.word:
  LDA #1
  RTS

; Core word-forward motion: move cursor forward X words.  From the end of
; a line it goes on to the next line's first word, over its indentation
; and over lines of blanks (an empty line counts as a word, as in vi).
; With WORD_OP = 1 (the operators dw, cw, yw) the last word stops at the
; end of its line instead: the cursor goes to col 0 of the next line and
; the range backs up over the '\n'.
; Input: X = count of words to move
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16
word_forward_x:
.w_loop:
  STX NORMAL_TEMP         ; Save counter
  JSR get_line_len_z
  JSR class_in_line
  BMI .w_next_line        ; At/past the end (or an empty line): next line
  STA WORD_CLASS
  BEQ .w_skip_ws          ; On whitespace: just skip whitespace

  ; Skip chars of same class as current
.w_skip_same:
  JSR next_class
  BMI .w_next_line
  CMP WORD_CLASS
  BEQ .w_skip_same
  TAX                     ; Z = whitespace (X is reloaded below)
  BNE .w_done_one         ; Non-whitespace non-same class = word start

  ; Skip whitespace; a non-whitespace char is the word start
.w_skip_ws:
  JSR next_class
.w_ws_test:
  BMI .w_next_line
  BEQ .w_skip_ws

.w_done_one:
  LDX NORMAL_TEMP
  DEX
  BNE .w_loop
.w_ret:
  RTS

  ; At end of line: go on to the next line's first word
.w_next_line:
  JSR advance_next_line
  BCS .w_ret              ; No next line, stay put
  LDX NORMAL_TEMP
  CPX WORD_OP
  BEQ .w_done_one         ; An operator's last word: stop at col 0
  JSR get_line_len_z
  BEQ .w_done_one         ; An empty line counts as a word
  JSR class_in_line
  BPL .w_ws_test          ; Always (col 0 is on the line): skip indentation

; Core word-backward motion: move cursor backward X words
; Input: X = count of words to move
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16
word_backward_x:
.b_loop:
  STX NORMAL_TEMP         ; Save counter

  ; If at col 0, move to previous line end
  TST16 CURSOR_COL16
  BNE .b_not_bol

  ; At beginning of line - move to prev line end
.b_prev_line:
  JSR line_above_end      ; Col = its length (one past its end)
  BCC .b_done_final       ; Already at first line, col 0
  BEQ .b_done_one         ; Prev line is empty, at col 0
  ; Fall through to .b_not_bol which DECs then scans backward to word start

.b_not_bol:
  ; Move left one to start scanning (prev_class steps BUF_PTR16 with it)
  JSR get_cursor_buf_ptr

  ; Skip whitespace backward
.b_skip_ws:
  JSR prev_class
  BNE .b_found_nonws
  ; Still whitespace - move left
  TST16 CURSOR_COL16
  BEQ .b_prev_line        ; Only blanks before it: go on to the line above
  BNE .b_skip_ws          ; Always

.b_found_nonws:
  ; Remember class of this non-whitespace char
  STA WORD_CLASS

  ; Scan backward through same-class chars
.b_skip_same:
  TST16 CURSOR_COL16
  BEQ .b_done_one         ; At col 0, this is the word start
  JSR prev_class
  CMP WORD_CLASS
  BEQ .b_skip_same
  ; Different class - word start is one to the right
  JSR inc_cursor_col

.b_done_one:
  LDX NORMAL_TEMP
  DEX
  BNE .b_loop
.b_done_final:
  RTS

; --- w command: move to start of next word ---
; Accepts count prefix.
; Skip current word-class chars, skip whitespace.
; If at EOL, move on to the next line's first word.
normal_word_forward:
  JSR get_batched_count
  JSR word_forward_x
  JMP clamp_and_clear_count

; --- b command: move to start of previous word ---
; Accepts count prefix.
normal_word_backward:
  JSR get_batched_count
  JSR word_backward_x
  JMP clamp_and_clear_count

; --- e command: move to end of current/next word ---
; Accepts count prefix.
normal_word_end:
  JSR get_batched_count
  JSR word_end_x
  JMP clamp_and_clear_count

; Core word-end motion: move cursor to end of Xth word
; Input: X = count of words to move
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16
word_end_x:
.e_loop:
  STX NORMAL_TEMP         ; Save counter
  JSR get_line_len_z
  ; e moves past the cursor first; from the line's last char (or an
  ; empty line) it goes on to the next line.  (From an empty last line
  ; it goes to col -1: an operator's range there is empty.)
  BEQ .e_next_line
  JSR get_cursor_buf_ptr
  JSR next_class
  BPL .e_skip_ws_test

.e_next_line:
  ; Move to next line and skip whitespace from its start to the first word
  ; end: like vi, e passes over empty and whitespace-only lines
  JSR advance_next_line
  BCS .e_last             ; No next line
  JSR get_line_len_z
  JSR dec_cursor_col      ; Col -1: the first step lands on col 0
  JSR get_cursor_buf_ptr

  ; Skip whitespace
.e_skip_ws:
  JSR next_class
  BMI .e_next_line        ; At EOL during whitespace skip
.e_skip_ws_test:
  BEQ .e_skip_ws

  ; Found non-whitespace: remember its class
  STA WORD_CLASS

  ; Skip forward through same-class chars; the word ends one before the
  ; first char of another class or the end of the line
.e_skip_same:
  JSR next_class
  BMI .e_back
  CMP WORD_CLASS
  BEQ .e_skip_same
.e_back:
  JSR dec_cursor_col

  LDX NORMAL_TEMP
  DEX
  BNE .e_loop
  RTS

  ; No word end left: stop on the byte before the last line's newline (its
  ; last char, or col -1 on an empty line: the newline before it), where
  ; the cursor started if e could not move
.e_last:
  JMP dec_cursor_col


; --- Multi-line range computation routines ---

; Compute forward word range (multi-line) for dw/yw
; The last word stops at the end of its line (the range stops before its
; line break); from an empty line it ends on column 0 of the next line,
; and vi's exclusive rule sets OP_EXCL_LINE (see op_lines)
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; Side effect: cursor restored to original position
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16, BUF_DST16
compute_multiline_word_range_forward:
  JSR range_start
  INC WORD_OP                       ; The last word stops at its line end
  JSR word_forward_x                ; move cursor forward N words
  DEC WORD_OP
  JSR get_cursor_buf_ptr            ; BUF_PTR16 = end_buf_ptr
  ; The last word stopped at the end of its line (or w ran out of lines
  ; on an empty last line): back up past the '\n'
  CMP16 FILE_LINE16, BUF_DST16      ; BUF_DST16 = start line (range_start)
  BEQ .cmwrf_no_adj                 ; same line, no adjustment
  TST16 CURSOR_COL16
  BNE .cmwrf_no_adj                 ; not at col 0, no adjustment
  DEC16 BUF_PTR16                   ; back up past '\n'
  ; From an empty line (LINE_LEN16 = 0) vi's w ends on column 0 of the
  ; next line (from a word, on the line end): its exclusive rule applies
  TST16 LINE_LEN16
  BNE .cmwrf_no_adj
  SEC
  ROR OP_EXCL_LINE
.cmwrf_no_adj:
  JMP range_end

; Compute forward cw-semantics word range (multi-line) for cw, as vi:
; from whitespace the dw range; from a word, ce's range, except that on
; a word's last char that char is the count's first word (cw there
; changes just it)
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; Side effect: cursor restored to original position
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16, BUF_DST16
compute_multiline_cw_range_forward:
  STX NORMAL_TEMP
  JSR get_cursor_buf_ptr
  JSR class_at_ptr                  ; BUF_PTR16 = cursor, Y = 0
  LDX NORMAL_TEMP
  TAY
  BEQ compute_multiline_word_range_forward  ; On whitespace: the dw range
  STA WORD_CLASS
  LDY #1
  LDA (BUF_PTR16),Y
  JSR char_class                    ; The next char ('\n' at the line end)
  CMP WORD_CLASS
  BEQ compute_multiline_word_end_range_forward  ; Inside a word: ce
  DEX                               ; On its last char: the first word
  BNE compute_multiline_word_end_range_forward
  JSR range_start                   ; cw of one word there: the char
  JMP word_end_range_end

; Compute backward word range (multi-line) for db/yb/cb.  From column 0
; the range stops before the line break, and vi's exclusive rule sets
; OP_EXCL_LINE (see op_lines)
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; (at the start of the file it ends the command instead: b fails)
; Side effect: cursor STAYS at new backward position (start of range);
; from column 0, PREV_LINE_ROWS = its line's rows
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16
compute_multiline_word_range_backward:
  JSR range_start_ptr               ; BUF_SRC16 = original position (end of range)
  TST16 CURSOR_COL16
  BNE .cmwrb_col
  TST16 FILE_LINE16
  BEQ .cmwrb_fail                   ; The file start: b cannot move
  ; From column 0 (b goes to a line above), vi's exclusive rule: the
  ; range stops at the end of that line.  An edit there changes that
  ; line in place (typed-ahead presses then redraw all: dispatch_replay)
  SEC
  ROR OP_EXCL_LINE
  LDA #RF_LINE
  STA RENDER_FLAG
.cmwrb_col:
  JSR word_backward_x               ; move cursor backward N words
  BIT OP_EXCL_LINE
  BPL .cmwrb_line                   ; On the line the key started on
  JSR file_line_rows                ; The line above: its rows before the edit
  STA PREV_LINE_ROWS
.cmwrb_line:
  JSR get_cursor_buf_ptr            ; BUF_PTR16 = new position (start of range)
  LDA #$7F
  CMP OP_EXCL_LINE                  ; C = 0: the range stops before the
  SBC16 BUF_SRC16, BUF_PTR16, BUF_LEN16  ; line break (range = end - start)
  JMP range_epilogue
  ; At the file start b fails, and with it the operator, as in vim (cb
  ; does not go into insert mode): drop the return into word_op_forward
  ; and the operator it saved, and end the command there
.cmwrb_fail:
  PLA
  JMP end_command

; Compute forward word-end range (multi-line) for de/ye/ce
; e is an inclusive motion: range includes the character at the end
; position (never the buffer's final '\n': with no word end left, e stops
; on the byte before it)
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; Side effect: cursor restored to original position
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16, BUF_DST16
compute_multiline_word_end_range_forward:
  JSR range_start
  JSR word_end_x                    ; move cursor to end of Nth word
word_end_range_end:
  JSR get_cursor_buf_ptr            ; BUF_PTR16 = end_buf_ptr
  INC16 BUF_PTR16                   ; inclusive: include end char
  ; fall through into range_end

; Finish a forward range ending at BUF_PTR16: restore the cursor saved by
; range_start, BUF_LEN16 = BUF_PTR16 - BUF_SRC16; carry set if empty.
; range_len does only the latter, range_len_c takes one less for C = 0.
range_end:
  CP16 BUF_DST16, FILE_LINE16
  CP16 BUF_LEN16, CURSOR_COL16
range_len:
  SEC
range_len_c:
  SBC16 BUF_PTR16, BUF_SRC16, BUF_LEN16
  ; fall through into range_epilogue

; Shared range-computation epilogue: carry clear if BUF_LEN16 != 0
range_epilogue:
  TST16 BUF_LEN16
  BEQ .nothing
  CLC
  RTS
.nothing:
  SEC
  RTS

; Start a forward range at the cursor: save the cursor for range_end
; (line -> BUF_DST16, col -> BUF_LEN16; the motions leave both alone),
; then BUF_SRC16 = BUF_PTR16 = the cursor's buffer address.
; range_start_ptr does only the latter.  Preserves X (the word count).
; Clobbers: A, Y
range_start:
  CP16 FILE_LINE16, BUF_DST16
  CP16 CURSOR_COL16, BUF_LEN16
range_start_ptr:
  TXA
  PHA
  JSR get_cursor_src
  PLA
  TAX
  RTS

; Move cursor to start of next line, if any
; Output: carry set if no next line (cursor unchanged), clear if advanced
; Clobbers: A
advance_next_line:
  JSR next_line
  BCS next_line_ret
  LDA #0
  STA_LH16 CURSOR_COL16
  RTS

; --- ^, and the tail of the commands that go to another line (G, gg,
; :N, 'a, Ctrl-F/B/D/U): the cursor to the first non-blank char, as in
; vi and in vim with its default 'startofline', then clear the count ---
first_nonblank_clear:
  JSR first_nonblank
  JMP clear_count

; Cursor to the first non-blank char of its line (blanks: spaces and
; tabs).  On a line of blanks it goes to the last one, as in vim; on an
; empty line to col 0.  The remembered column starts over (vim's
; beginline), after a : command too.  Clobbers A, X, Y, BUF_PTR16
first_nonblank:
  LSR CURSWANT_KEEP
  LDA #$FF
  STA_LH16 CURSOR_COL16        ; No limit: the scan ends on the line
; The same, but not right of the cursor: its column if only blanks lie
; left of it (where vim starts a linewise operator, as >>, on its line)
nonblank_left:
  JSR in_indent                ; X/Y = the column
  STY CURSOR_COL16
  STX CURSOR_COL16 + 1
  RTS

; Carry set if only blanks lie left of the cursor (vim's inindent), X/Y
; = its column; else carry clear and X/Y = the column (high/low) of the
; line's first non-blank (on a line of blanks with the cursor past its
; end, the last blank; col 0 on an empty line).  Clobbers A, BUF_PTR16
in_indent:
  JSR get_current_line_ptr     ; BUF_PTR16 = start of line
  LDX #0                       ; X/Y = column (high/low)
  LDY #0
.scan:
  CPY CURSOR_COL16
  BNE .char
  CPX CURSOR_COL16 + 1
  BEQ .done                    ; Only blanks left of the cursor
.char:
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .blank_line
  JSR char_class               ; (keeps X, Y)
  BNE .found
  INY
  BNE .scan
  INC BUF_PTR16 + 1            ; Next page of the line
  INX
  BNE .scan                    ; Always
.blank_line:
  ; Only blanks: the last one (col 0 on an empty line)
  TYA
  BNE .last
  TXA
  BEQ .found                   ; Empty line: col 0
  DEX
.last:
  DEY
.found:
  CLC                          ; First non-blank at column X/Y
.done:
  RTS

; --- Shared small helpers ---

; The cursor past the end of the line above (column = its length): C = 0
; on the first line (nothing moves), else C = 1 and Z = 1 if that line is
; empty.  Clobbers A, X, Y, BUF_PTR16
line_above_end:
  LDA FILE_LINE16
  ORA FILE_LINE16 + 1
  CMP #1                  ; C = 0: the first line
  BCC next_line_ret
  JSR dec_file_line
  JSR insert_end          ; A/X = its length (C = 1 from the subtract)
  ORA CURSOR_COL16 + 1
  RTS

; FILE_LINE16 to the next line, if any: carry set if there is none
; (FILE_LINE16 unchanged).  dec_file_line: FILE_LINE16 - 1.  Clobbers A
next_line:
  INC16 FILE_LINE16
  CMP16 FILE_LINE16, LINE_COUNT16
  BCC next_line_ret
dec_file_line:
  DEC16 FILE_LINE16       ; (C unchanged)
next_line_ret:
  RTS

; Get current line length into LINE_LEN16
; Output: LINE_LEN16 = length, X = its high byte, Z set if the line is
; empty (A = low | high)
get_line_len_z:
  JSR get_current_line_len
  STAX16 LINE_LEN16
  ORA LINE_LEN16 + 1           ; A still holds the low byte
  RTS

; Increment / decrement CURSOR_COL16 (JSR-able to save macro bytes)
inc_cursor_col:
  INC16 CURSOR_COL16
  RTS
dec_cursor_col:
  DEC16 CURSOR_COL16
  RTS
