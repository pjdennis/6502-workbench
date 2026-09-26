; Word motion support - character classification and word boundary routines
;
; Provides char_class (classify byte), the word motions w, b, e and ^,
; and the multi-line word range routines of the word operators.

; (zero-page variables: zp.asm)

; Step the cursor right, then classify it as class_in_line does
next_class:
  INC16 CURSOR_COL16
  ; fall through into class_in_line

; Class of the char at the cursor while the cursor is on the line
; (LINE_LEN16): A = class (see char_class; N clear, Z set for
; whitespace).  At or past the end of the line: A = $FF (N set).
; Clobbers: A, X, Y, BUF_PTR16
class_in_line:
  CMP16 CURSOR_COL16, LINE_LEN16
  BCC class_at_cursor
  LDA #$FF
  RTS

; Classify char at cursor -> A = class (see char_class)
; Clobbers: A, X, Y (Y = 0), BUF_PTR16
class_at_cursor:
  JSR get_cursor_buf_ptr
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

; --- w command: move to start of next word ---
; Accepts count prefix.
; Skip current word-class chars, skip whitespace.
; If at EOL, move to next line col 0.
normal_word_forward:
  JSR get_batched_count
  JSR word_forward_x
  JMP clamp_and_clear_count

; Core word-forward motion: move cursor forward X words
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
  BMI .w_next_line
  BEQ .w_skip_ws

.w_done_one:
  LDX NORMAL_TEMP
  DEX
  BNE .w_loop
  RTS

  ; At end of line - go to next line col 0 (acts like reaching word start)
.w_next_line:
  JSR advance_next_line
  BCC .w_done_one
  RTS                     ; No next line, stay put

; --- b command: move to start of previous word ---
; Accepts count prefix.
normal_word_backward:
  JSR get_batched_count
  JSR word_backward_x
  JMP clamp_and_clear_count

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
  TST16 FILE_LINE16
  BEQ .b_done_final       ; Already at first line, col 0
  DEC16 FILE_LINE16
  JSR get_line_len_z      ; X = length high byte
  BEQ .b_done_one         ; Prev line is empty, at col 0
  LDA LINE_LEN16          ; Set col = line_len (one past end)
  STA CURSOR_COL16
  STX CURSOR_COL16 + 1
  ; Fall through to .b_not_bol which DECs then scans backward to word start

.b_not_bol:
  ; Move left one to start scanning
  JSR dec_cursor_col

  ; Skip whitespace backward
.b_skip_ws:
  JSR class_at_cursor
  BNE .b_found_nonws
  ; Still whitespace - move left
  TST16 CURSOR_COL16
  BEQ .b_done_one         ; Hit col 0 during whitespace skip
  JSR dec_cursor_col
  JMP .b_skip_ws

.b_found_nonws:
  ; Remember class of this non-whitespace char
  STA WORD_CLASS

  ; Scan backward through same-class chars
.b_skip_same:
  TST16 CURSOR_COL16
  BEQ .b_done_one         ; At col 0, this is the word start
  JSR dec_cursor_col
  JSR class_at_cursor
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
  ; empty line) it goes on to the next line
  JSR next_class
  BPL .e_skip_ws_test
  JSR dec_cursor_col      ; Undo the step

.e_next_line:
  ; Move to next line and find first word end
  JSR advance_next_line
  BCS .e_done_final       ; No next line
  JSR get_line_len_z
  JSR class_in_line
.e_newline_skip_ws:
  BMI .e_done_one         ; Empty or all-whitespace line counts as done for e
  BNE .e_found_nonws      ; Found non-whitespace: skip to end of this word
  JSR next_class
  JMP .e_newline_skip_ws

  ; Skip whitespace
.e_skip_ws:
  JSR next_class
  BMI .e_next_line        ; At EOL during whitespace skip
.e_skip_ws_test:
  BEQ .e_skip_ws

.e_found_nonws:
  ; Remember class
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

.e_done_one:
  LDX NORMAL_TEMP
  DEX
  BNE .e_loop
.e_done_final:
  RTS


; --- Multi-line range computation routines ---

; Compute forward word range (multi-line) for dw/yw
; Applies exclusive-linewise adjustment when motion ends at col 0 of different line
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; Side effect: cursor restored to original position
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16, BUF_DST16
compute_multiline_word_range_forward:
  JSR range_start
  JSR word_forward_x                ; move cursor forward N words
  JSR get_cursor_buf_ptr            ; BUF_PTR16 = end_buf_ptr
  ; Exclusive-linewise check: if different line AND col 0, back up past '\n'
  CMP16 FILE_LINE16, BUF_DST16      ; BUF_DST16 = start line (range_start)
  BEQ .cmwrf_no_adj                 ; same line, no adjustment
  TST16 CURSOR_COL16
  BNE .cmwrf_no_adj                 ; not at col 0, no adjustment
  DEC16 BUF_PTR16                   ; back up past '\n'
.cmwrf_no_adj:
  JMP range_end

; Compute forward cw-semantics word range (multi-line) for cw
; Like word range but strips trailing whitespace when cursor starts on non-whitespace
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; Side effect: cursor restored to original position
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16, BUF_DST16
compute_multiline_cw_range_forward:
  JSR range_start                   ; BUF_PTR16 = cursor address
  JSR class_at_ptr                  ; class of char under cursor (keeps X)
  PHA
  JSR word_forward_x                ; move cursor forward N words
  JSR get_cursor_buf_ptr            ; BUF_PTR16 = end_buf_ptr
  ; No exclusive-linewise adjustment for cw:
  ; non-ws path strips trailing ws (handles it); ws path extends past word
  PLA                               ; original char class
  BEQ .cmcrf_on_ws                  ; cursor was on whitespace: extend past word
  ; Non-whitespace: strip trailing whitespace (ce semantics)
.cmcrf_strip_loop:
  CMP16 BUF_PTR16, BUF_SRC16       ; would range become 0?
  BEQ range_end
  DEC16 BUF_PTR16                   ; back up
  JSR class_at_ptr
  BEQ .cmcrf_strip_loop             ; still whitespace, keep stripping
  INC16 BUF_PTR16                   ; non-ws, include this char
  JMP range_end
.cmcrf_on_ws:
  ; On whitespace: w landed at start of next word, extend past same-class chars
  JSR class_at_ptr
  STA WORD_CLASS
.cmcrf_ws_extend:
  INC16 BUF_PTR16
  JSR class_at_ptr
  CMP WORD_CLASS
  BEQ .cmcrf_ws_extend
  JMP range_end

; Compute backward word range (multi-line) for db/yb/cb
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; Side effect: cursor STAYS at new backward position (start of range)
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16
compute_multiline_word_range_backward:
  JSR range_start_ptr               ; BUF_SRC16 = original position (end of range)
  JSR word_backward_x               ; move cursor backward N words
  JSR get_cursor_buf_ptr            ; BUF_PTR16 = new position (start of range)
  SEC
  SBC16 BUF_SRC16, BUF_PTR16, BUF_LEN16  ; range = end - start
  JMP range_epilogue

; Compute forward word-end range (multi-line) for de/ye/ce
; e is an inclusive motion: range includes the character at the end position.
; Input: X = word count
; Output: BUF_LEN16 = byte count, carry set if nothing to operate on
; Side effect: cursor restored to original position
; Clobbers: A, X, Y, NORMAL_TEMP, WORD_CLASS, LINE_LEN16, BUF_PTR16,
;           BUF_SRC16, BUF_DST16
compute_multiline_word_end_range_forward:
  JSR range_start
  JSR word_end_x                    ; move cursor to end of Nth word
  JSR get_cursor_buf_ptr            ; BUF_PTR16 = end_buf_ptr
  INC16 BUF_PTR16                   ; inclusive: include end char
  ; fall through into range_end

; Finish a forward range ending at BUF_PTR16: restore the cursor saved by
; range_start, BUF_LEN16 = BUF_PTR16 - BUF_SRC16; carry set if empty
range_end:
  CP16 BUF_DST16, FILE_LINE16
  CP16 BUF_LEN16, CURSOR_COL16
  SEC
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
  JSR get_cursor_buf_ptr
  CP16 BUF_PTR16, BUF_SRC16
  PLA
  TAX
  RTS

; --- ^ command: move to first non-blank character ---
; An empty or all-space line leaves the cursor at col 0 (its first byte, or
; the first non-space, is the newline)
normal_first_nonblank:
  LDA #0
  STA_LH16 CURSOR_COL16
  JSR get_current_line_ptr     ; BUF_PTR16 = start of line
  LDY #0
.scan:
  LDA (BUF_PTR16),Y
  CMP #' '
  BNE .not_space
  INY
  BNE .scan               ; (256 spaces: Y = 0, lands on col 0 below)
.not_space:
  CMP #'\n'
  BEQ .done               ; Empty or all-space line: col 0
  STY CURSOR_COL16        ; First non-blank at offset Y
.done:
  JMP clear_count

; --- Shared small helpers ---

; Move cursor to start of next line, if any
; Output: carry set if no next line (cursor unchanged), clear if advanced
; Clobbers: A, BUF_PTR16
advance_next_line:
  CLC
  ADCI16 FILE_LINE16, 1, BUF_PTR16
  CMP16 BUF_PTR16, LINE_COUNT16
  BCS .no_next            ; No next line
  INC16 FILE_LINE16
  LDA #0
  STA_LH16 CURSOR_COL16
.no_next:
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
