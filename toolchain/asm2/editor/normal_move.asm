; Normal mode movement commands - cursor motion, search, marks, yank

; --- Movement ---

normal_move_left:
  JSR get_batched_count
  JSR move_left_x
  JMP clear_count

normal_move_right:
  JSR get_batched_count
  ; Move right X columns (X = 0: 256), then clamp to the last char
  DEX
  TXA
  SEC
  ADCA16 CURSOR_COL16, CURSOR_COL16
  JMP clamp_and_clear_count

normal_move_down:
  JSR get_batched_count
  JSR move_down_x
  JMP clamp_and_clear_count

normal_move_up:
  JSR get_batched_count
  JSR move_up_x
  JMP clamp_and_clear_count

normal_page_down:
  JSR page_setup
  JSR scroll_view_down
  JMP zero_col_clamp_clear

normal_page_up:
  JSR page_setup
  JSR scroll_view_up
  JMP zero_col_clamp_clear

; Ctrl-D: half-page down
; Scroll down by half a screen (or count lines). Column preserved.
normal_half_page_down:
  JSR half_page_setup
  JSR scroll_view_down
  JMP clamp_and_clear_count

; Ctrl-U: half-page up
; Scroll up by half a screen (or count lines). Column preserved.
normal_half_page_up:
  JSR half_page_setup
  JSR scroll_view_up
  JMP clamp_and_clear_count

; Page scroll setup: BUF_DELTA = batched count (repeats, 0 = 256),
; BUF_TEMP = page size = content rows (TEXT_ROWS)
page_setup:
  JSR get_batched_count
  STX BUF_DELTA
  LDX TEXT_ROWS
  STX BUF_TEMP
  RTS

; Half-page scroll setup: BUF_DELTA = 1 + extra Ctrl-D/U keys in
; typeahead (BUF_TEMP = key code from dispatch), BUF_TEMP = scroll
; amount: COUNT16 if set (and remembered), else the sticky value, else
; half a page
half_page_setup:
  JSR count_pending_key
  INX
  STX BUF_DELTA
  LDA COUNT16
  ORA COUNT16 + 1
  BNE .use_count
  ; No count: use sticky if set, else compute default
  LDA SCROLL_AMOUNT
  BNE .store
  ; Default: half_page = TEXT_ROWS / 2
  LDA TEXT_ROWS
  LSR
  BPL .store                 ; Always
.use_count:
  ; Use COUNT16 as scroll amount (cap to 8-bit), save as sticky
  LDA COUNT16
  LDX COUNT16 + 1
  BEQ .save_sticky
  LDA #$FF
.save_sticky:
  STA SCROLL_AMOUNT
.store:
  STA BUF_TEMP
  RTS

; --- Shared scroll subroutines ---

; Scroll the viewport down BUF_DELTA times (0 = 256) by BUF_TEMP lines
; Modifies: FILE_LINE16, VIEW_TOP16, VIEW_TOP_WRAP, BUF_DELTA
; Clobbers: A, X, Y
scroll_view_down:
  ; FILE_LINE16 += BUF_TEMP, clamped to the last line
  LDA BUF_TEMP
  CLC
  JSR add_file_line

  ; VIEW_TOP16 += BUF_TEMP
  LDA BUF_TEMP
  ADDA16 VIEW_TOP16

  ; Clamp VIEW_TOP16 to max(0, LINE_COUNT - TEXT_ROWS)
  SEC
  LDA LINE_COUNT16
  SBC TEXT_ROWS
  TAX
  LDA LINE_COUNT16 + 1
  SBC #0
  BCC .view_zero     ; LINE_COUNT < TEXT_ROWS, set VIEW_TOP=0
  TAY                ; Y:X = max view top

  ; If VIEW_TOP16 > max, clamp it
  CPY VIEW_TOP16 + 1
  BCC .clamp_view
  BNE .next
  CPX VIEW_TOP16
  BCS .next
.clamp_view:
  STX VIEW_TOP16
  STY VIEW_TOP16 + 1
  BCC .next                ; Always (C = 0 here)

.view_zero:
  LDA #0
  STA_LH16 VIEW_TOP16
.next:
  DEC BUF_DELTA
  BNE scroll_view_down

; Shared scroll tail: the new view top starts at its line's first row
view_wrap_zero:
  LDA #0
  STA VIEW_TOP_WRAP
  RTS

; Scroll the viewport up BUF_DELTA times (0 = 256) by BUF_TEMP lines
; Modifies: FILE_LINE16, VIEW_TOP16, VIEW_TOP_WRAP, BUF_DELTA
; Clobbers: A
scroll_view_up:
  ; FILE_LINE16 -= BUF_TEMP, clamped to 0
  SEC
  JSR sub_file_line

  ; VIEW_TOP16 -= BUF_TEMP, clamped to 0
  SEC
  LDA VIEW_TOP16
  SBC BUF_TEMP
  STA VIEW_TOP16
  LDA VIEW_TOP16 + 1
  SBC #0
  STA VIEW_TOP16 + 1
  BCS .next
  LDA #0
  STA_LH16 VIEW_TOP16
.next:
  DEC BUF_DELTA
  BNE scroll_view_up
  BEQ view_wrap_zero       ; Always

normal_line_start:
  LDA #0
  STA_LH16 CURSOR_COL16
  JMP clear_count

normal_line_end:
  LDA #$FF
  STA_LH16 CURSOR_COL16      ; Past any line end; clamp to the last char
  JMP clamp_and_clear_count

normal_goto_last:
  ; FILE_LINE16 = count - 1 (1-based count; no count: 0 - 1 = $FFFF),
  ; clamped to the last line
  SEC
  SBCI16 COUNT16, 1, FILE_LINE16
  JSR clamp_file_line
  LDA #0
  STA VIEW_TOP_WRAP
  JMP zero_col_clamp_clear

; gg: go to top of file
; (ensure_cursor_visible then scrolls the view to the top)
do_gg:
  LDA #0
  STA_LH16 FILE_LINE16
  JMP zero_col_clamp_clear

; --- Yank ---

; yy: yank N lines starting at current line (not pair-batched: yyyy runs
; yy twice, and the last yank wins)
do_yy:
  JSR get_count              ; BUF_TEMP16 = count (16-bit)
  JSR yank_current_lines
  BCS .overflow
  JMP clear_count            ; Done - don't set MODIFIED

.overflow:
  JMP show_yank_overflow

; yw: yank N words forward from cursor (character yank, multi-line)
do_yw:
  LDY #OP_YANK
  JMP word_w_op

; yb: yank N words backward from cursor (character yank, multi-line)
do_yb:
  LDA #OP_YANK
  JMP word_op_backward

; ye: yank from cursor to end of word (inclusive, multi-line)
do_ye:
  LDY #OP_YANK
  JMP word_end_op

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
  EOR #$10                   ; Flip the direction (0 <-> $10 = '/' EOR '?')

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
  JSR clamp_file_line        ; A stale mark must not point past EOF
  JMP zero_col_clamp_clear
.mark_not_set:
  JSR range_mark_err         ; "Mark not set"
  JMP clear_count

; --- Mode switch ---

normal_enter_command:
  LDA #MODE_COMMAND
  STA MODE
  JMP clear_count
