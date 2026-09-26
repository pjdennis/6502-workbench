; Normal mode movement commands - cursor motion, search, marks, yank

; --- Movement ---

normal_move_left:
  JSR get_batched_count
  JSR move_left_x
  JMP clear_count

normal_move_right:
  JSR get_batched_count
  ; Hoist line length calculation outside loop (line doesn't change)
  STX BUF_TEMP           ; Save count
  JSR get_line_len_z
  BEQ .right_done        ; Empty line
  LDX BUF_TEMP           ; Restore count
  SEC
  SBCI16 LINE_LEN16, 1, LINE_LEN16  ; LINE_LEN16 = len - 1
  JSR move_right_x
.right_done:
  JMP clear_count

normal_move_down:
  JSR get_batched_count
  JSR move_down_x
  JMP clamp_and_clear_count

normal_move_up:
  JSR get_batched_count
  JSR move_up_x
  JMP clamp_and_clear_count

normal_page_down:
  JSR get_batched_count
  STX BUF_DELTA            ; BUF_DELTA = loop counter

  ; page_size = SCREEN_ROWS - 1 (content rows excluding status bar)
  LDA SCREEN_ROWS
  SEC
  SBC #1
  STA BUF_TEMP       ; BUF_TEMP = move amount
  STA NORMAL_TEMP    ; NORMAL_TEMP = content_rows for view clamp

.page_loop:
  JSR scroll_view_down
  DEC BUF_DELTA
  BNE .page_loop
  JMP zero_col_clamp_clear

normal_page_up:
  JSR get_batched_count
  STX BUF_DELTA            ; BUF_DELTA = loop counter

  ; page_size = SCREEN_ROWS - 1
  LDA SCREEN_ROWS
  SEC
  SBC #1
  STA BUF_TEMP       ; BUF_TEMP = move amount

.page_loop:
  JSR scroll_view_up
  DEC BUF_DELTA
  BNE .page_loop
  JMP zero_col_clamp_clear

; --- Shared scroll subroutines ---

; Scroll viewport down by BUF_TEMP lines
; Input: BUF_TEMP = lines to move FILE_LINE and VIEW_TOP
;        NORMAL_TEMP = content_rows for VIEW_TOP max clamp
; Modifies: FILE_LINE16, VIEW_TOP16, VIEW_TOP_WRAP
; Clobbers: A, X, Y, BUF_PTR16
scroll_view_down:
  ; target_line = FILE_LINE16 + BUF_TEMP, clamped to LINE_COUNT16 - 1
  CLC
  LDA FILE_LINE16
  ADC BUF_TEMP
  STA BUF_PTR16
  LDA FILE_LINE16 + 1
  ADC #0
  STA BUF_PTR16 + 1

  ; Clamp target to LINE_COUNT16 - 1
  CMP16 BUF_PTR16, LINE_COUNT16
  BCC .target_ok
  SEC
  SBCI16 LINE_COUNT16, 1, BUF_PTR16
.target_ok:

  ; VIEW_TOP16 += BUF_TEMP
  CLC
  LDA VIEW_TOP16
  ADC BUF_TEMP
  STA VIEW_TOP16
  LDA VIEW_TOP16 + 1
  ADC #0
  STA VIEW_TOP16 + 1

  ; Clamp VIEW_TOP16 to max(0, LINE_COUNT - content_rows)
  SEC
  LDA LINE_COUNT16
  SBC NORMAL_TEMP
  TAX                ; X = low byte of max view top
  LDA LINE_COUNT16 + 1
  SBC #0
  BCC .view_zero  ; LINE_COUNT < content_rows, set VIEW_TOP=0
  TAY                ; Y = high byte of max view top

  ; If VIEW_TOP16 > max, clamp it
  CPY VIEW_TOP16 + 1
  BCC .clamp_view
  BNE .set_file_line
  CPX VIEW_TOP16
  BCS .set_file_line
.clamp_view:
  STX VIEW_TOP16
  STY VIEW_TOP16 + 1
  JMP .set_file_line

.view_zero:
  LDA #0
  STA_LH16 VIEW_TOP16

.set_file_line:
  CP16 BUF_PTR16, FILE_LINE16
  LDA #0
  STA VIEW_TOP_WRAP
  RTS

; Scroll viewport up by BUF_TEMP lines
; Input: BUF_TEMP = lines to move FILE_LINE and VIEW_TOP
; Modifies: FILE_LINE16, VIEW_TOP16, VIEW_TOP_WRAP
; Clobbers: A, X, Y, BUF_PTR16
scroll_view_up:
  ; target_line = FILE_LINE16 - BUF_TEMP, clamped to 0
  SEC
  LDA FILE_LINE16
  SBC BUF_TEMP
  STA BUF_PTR16
  LDA FILE_LINE16 + 1
  SBC #0
  STA BUF_PTR16 + 1
  BCS .target_ok
  ; Underflow - clamp to 0
  LDA #0
  STA_LH16 BUF_PTR16
.target_ok:

  ; VIEW_TOP16 -= BUF_TEMP, clamped to 0
  LDA VIEW_TOP16 + 1
  BNE .can_sub  ; High byte > 0, definitely >= BUF_TEMP
  LDA VIEW_TOP16
  CMP BUF_TEMP
  BCS .can_sub

  ; VIEW_TOP16 < BUF_TEMP: set VIEW_TOP16 = 0
  LDA #0
  STA_LH16 VIEW_TOP16
  JMP .set_file_line

.can_sub:
  SEC
  LDA VIEW_TOP16
  SBC BUF_TEMP
  STA VIEW_TOP16
  LDA VIEW_TOP16 + 1
  SBC #0
  STA VIEW_TOP16 + 1

.set_file_line:
  CP16 BUF_PTR16, FILE_LINE16
  LDA #0
  STA VIEW_TOP_WRAP
  RTS

; Get half-page scroll amount into BUF_TEMP
; Uses COUNT16 if set (and remembers it), else sticky value, else default.
get_half_page_amount:
  LDA COUNT16
  ORA COUNT16 + 1
  BNE .use_count
  ; No count: use sticky if set, else compute default
  LDA SCROLL_AMOUNT
  BNE .store
  ; Default: half_page = (SCREEN_ROWS - 1) / 2
  LDA SCREEN_ROWS
  SEC
  SBC #1
  LSR
  JMP .store
.use_count:
  ; Use COUNT16 as scroll amount (cap to 8-bit), save as sticky
  LDA COUNT16 + 1
  BNE .cap
  LDA COUNT16
  JMP .save_sticky
.cap:
  LDA #$FF
.save_sticky:
  STA SCROLL_AMOUNT
.store:
  STA BUF_TEMP
  RTS

; Ctrl-D: half-page down
; Scroll down by half a screen (or count lines). Column preserved.
normal_half_page_down:
  ; Count extra Ctrl-D keys in typeahead (BUF_TEMP = key code from dispatch)
  JSR count_pending_key
  INX
  STX BUF_DELTA              ; BUF_DELTA = loop counter (1 + extras)
  JSR get_half_page_amount   ; BUF_TEMP = scroll amount
  ; NORMAL_TEMP = content_rows = SCREEN_ROWS - 1
  LDX SCREEN_ROWS
  DEX
  STX NORMAL_TEMP
.loop:
  JSR scroll_view_down
  DEC BUF_DELTA
  BNE .loop
  JMP clamp_and_clear_count

; Ctrl-U: half-page up
; Scroll up by half a screen (or count lines). Column preserved.
normal_half_page_up:
  ; Count extra Ctrl-U keys in typeahead (BUF_TEMP = key code from dispatch)
  JSR count_pending_key
  INX
  STX BUF_DELTA              ; BUF_DELTA = loop counter (1 + extras)
  JSR get_half_page_amount   ; BUF_TEMP = scroll amount
.loop:
  JSR scroll_view_up
  DEC BUF_DELTA
  BNE .loop
  JMP clamp_and_clear_count

normal_line_start:
  LDA #0
  STA_LH16 CURSOR_COL16
  JMP clear_count

normal_line_end:
  JSR get_line_len_z
  BEQ .empty
  SEC
  SBCI16 LINE_LEN16, 1, CURSOR_COL16
  JMP .ecv
.empty:
  LDA #0
  STA_LH16 CURSOR_COL16
.ecv:
  JMP clear_count

normal_goto_last:
  ; If count is set, go to line N (1-based)
  TST16 COUNT16
  BEQ .goto_end

  ; Convert 1-based count to 0-based file line
  SEC
  SBCI16 COUNT16, 1, FILE_LINE16

  ; Clamp to last line
  CMP16 FILE_LINE16, LINE_COUNT16
  BCC .goto_set
  SEC
  SBCI16 LINE_COUNT16, 1, FILE_LINE16
  JMP .goto_set

.goto_end:
  ; No count: go to last line
  SEC
  SBCI16 LINE_COUNT16, 1, FILE_LINE16

.goto_set:
  LDA #0
  STA VIEW_TOP_WRAP
  JMP zero_col_clamp_clear

; gg: go to top of file
do_gg:
  LDA #0
  STA_LH16 FILE_LINE16
  STA_LH16 VIEW_TOP16
  STA CURSOR_ROW
  STA VIEW_TOP_WRAP
  JMP zero_col_clamp_clear

; --- Yank ---

; yy: yank N lines starting at current line
; When batched (BATCH_EXTRA > 0): cap count to 1. Batched extra pairs
; have implicit count=1, and the last yy overwrites previous yanks,
; so only 1 line should be yanked.
do_yy:
  JSR get_count              ; BUF_TEMP16 = count (16-bit)
  LDA BATCH_EXTRA
  BEQ .do_yank
  JSR set_buf_temp16_one
.do_yank:
  LDAX16 FILE_LINE16
  JSR yank_add_lines
  BCS .overflow
  JMP clear_count            ; Done - don't set MODIFIED

.overflow:
  JMP show_yank_overflow

; yw: yank N words forward from cursor (character yank, multi-line)
do_yw:
  SET16 compute_multiline_word_range_forward, JUMP_TARGET16
  LDA #OP_YANK
  JMP word_op_forward

; yb: yank N words backward from cursor (character yank, multi-line)
do_yb:
  LDA #OP_YANK
  JMP word_op_backward

; ye: yank from cursor to end of word (inclusive, multi-line)
do_ye:
  SET16 compute_multiline_word_end_range_forward, JUMP_TARGET16
  LDA #OP_YANK
  JMP word_op_forward

; --- Search ---

normal_search:
  JSR search_handle
  JMP clear_count

normal_search_backward:
  JSR search_backward_handle
  JMP clear_count

normal_find_next:
  LDA SEARCH_LEN
  BEQ search_find_none
  LDA SEARCH_DIR
  JMP search_find_dir

normal_find_prev:
  LDA SEARCH_LEN
  BEQ search_find_none
  LDA SEARCH_DIR
  EOR #1

search_find_dir:
  BNE .backward
  JSR search_forward
  JMP clear_count
.backward:
  JSR search_backward
  JMP clear_count

search_find_none:
  JMP clear_count

; --- Marks ---

; Execute mark set with register letter in BUF_TEMP
do_mark_set:
  LDA BUF_TEMP
  JSR mark_set
  JMP clear_count

; Execute mark goto with register letter in BUF_TEMP
do_mark_goto:
  LDA BUF_TEMP
  JSR mark_get
  BCS .mark_not_set
  STAX16 FILE_LINE16
  JMP zero_col_clamp_clear
.mark_not_set:
  LDA #<str_mark_not_set
  LDX #>str_mark_not_set
  JSR show_message_ax
  JMP clear_count

; --- Mode switch ---

normal_enter_command:
  LDA #MODE_COMMAND
  STA MODE
  JMP clear_count
