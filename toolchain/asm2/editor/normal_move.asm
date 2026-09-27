; Normal mode movement commands - cursor motion, search, marks, yank

; --- Movement ---

normal_move_left:
  JSR h_l_setup
  JSR move_left_x
  JMP h_l_done

normal_move_right:
  JSR h_l_setup
  ; Move right X columns, then clamp to the last char
  TXA
  CLC
  ADCA16 CURSOR_COL16, CURSOR_COL16
  JSR clamp_cursor_col
  JMP h_l_done

; j, k, Down, Up: the whole count, as vim (and the typed-ahead presses)
normal_move_down:
  JSR get_count_pending16
  JSR move_down16
  JMP vert_col_clamp

normal_move_up:
  JSR get_count_pending16
  JSR move_up16
  JMP vert_col_clamp

; Ctrl-F and PgDn: page forward as vim does.  The top line goes to the
; line below the page (the first one not shown in full), less the
; page's last lines kept on screen (page_setup: BUF_TEMP16 of them), and
; the cursor goes to it; a page that shows the last line puts that line
; on top.  At least one line on, and with the last line on top the page
; cannot move (vim beeps: page_fail)
normal_page_down:
  JSR page_setup
.page:
  LDA TEXT_ROWS
  JSR find_line_from_top_a   ; The line below the page
  CP16 RENDER_LINE16, FILE_LINE16
  JSR clamp_file_line        ; C=1: past the last line, which goes on top
  BCS .moved
  JSR move_up16              ; Back over the lines kept
.moved:
  CMP16 VIEW_TOP16, FILE_LINE16
  BCC .on                    ; It moved on
  CP16 VIEW_TOP16, FILE_LINE16
  JSR next_line              ; One line on; C=1: the last line is on top
  BCS page_fail
.on:
  LDA #$FF                   ; The cursor line's first row on top
  JSR page_view
  DEC BUF_DELTA
  BNE .page
  BEQ page_first_nonblank    ; Always taken

; A page that cannot move changes nothing (vim beeps).  The presses
; before it went to the first non-blank as usual, unless they were the
; count's: then the column stays, clamped to the line, and so does the
; remembered column (vim's onepage skips beginline when its count runs
; out)
page_fail:
  LDA BATCH_EXTRA
  CMP BUF_DELTA              ; C=1: a typed-ahead press failed
  BCS page_first_nonblank
  ASL CURSWANT_KEEP
  JMP clamp_for_mode

; Ctrl-B and PgUp: page back as vim does.  The page's first lines stay
; on screen at the bottom (BUF_TEMP16 of them, fewer near the end of the
; file) and the cursor goes to the new bottom line; with the first line
; on top the page cannot move.  A new bottom line just below a screen of
; the first lines leaves them on top, with the cursor on the line above
; it (vim's cursor_correct)
normal_page_up:
  JSR page_setup
.page:
  TST16 VIEW_TOP16
  BEQ page_fail
  CP16 VIEW_TOP16, FILE_LINE16
  JSR move_down16            ; The last line kept (or the last line)
.up:
  JSR dec_file_line          ; The line above it goes to the bottom row
  LDA #0
  JSR page_view
  LDA VIEW_TOP16
  EOR #1
  ORA VIEW_TOP16 + 1
  ORA VIEW_TOP_WRAP
  BEQ .up                    ; Line 2 on top: vim keeps line 1 there and
                             ; puts the cursor a line up
  DEC BUF_DELTA
  BNE .page
page_first_nonblank:
  JMP first_nonblank_clear

; Put the cursor line's first row on the top row (A = $FF) or on the
; bottom row, with the first line on top if it fits there (A = 0):
; ensure_row_visible scrolls to it from past it or from the first line
page_view:
  STA_LH16 VIEW_TOP16
  LDA #0
  STA VIEW_TOP_WRAP
  STA WRAP_QUOT
  JMP ensure_row_visible

; Ctrl-D: half-page down
; Scroll down by half a screen (or count lines).  On the last line vim
; refuses it: the cursor, its column and the scroll amount stay
normal_half_page_down:
  JSR lines_left
  BEQ half_page_fail
  JSR half_page_setup
  JSR scroll_view_down
  JMP first_nonblank_clear

; Ctrl-U: half-page up
; Scroll up by half a screen (or count lines), refused on line 1 (vim)
normal_half_page_up:
  LDA FILE_LINE16
  ORA FILE_LINE16 + 1
  BEQ half_page_fail
  JSR half_page_setup
  JSR scroll_view_up
  JMP first_nonblank_clear
half_page_fail:
  JMP keep_clear_count

; Page setup: BUF_DELTA = batched count (the presses), BUF_TEMP16 = the
; lines a page keeps: 2, as vim, which keeps fewer on a small screen (1
; on 4 text rows, none on 3 or less: its lines kept and the lines next to
; them take at most TEXT_ROWS - 2 rows)
page_setup:
  JSR get_batched_count
  STX BUF_DELTA
  LDX TEXT_ROWS
  CPX #4
  LDA #0
  ROL                        ; 1 from 4 text rows
  CPX #5
  ADC #0                     ; 2 from 5
  JMP set_buf_temp16_a

; Half-page scroll setup: BUF_DELTA = 1 + extra Ctrl-D/U keys in
; typeahead (BUF_TEMP = key code from dispatch), BUF_TEMP16 = scroll
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
  JMP set_buf_temp16_a

; --- Shared scroll subroutines ---

; Scroll the viewport down BUF_DELTA (>= 1) times by BUF_TEMP16 (< 256)
; lines, as
; vim's Ctrl-D: the view stops where the last line reaches the bottom
; row (LINE_COUNT - TEXT_ROWS), and a view there or past it stays (the
; cursor moves on)
; Modifies: FILE_LINE16, VIEW_TOP16, VIEW_TOP_WRAP, BUF_DELTA
; Clobbers: A, X, Y
scroll_view_down:
  JSR move_down16

  ; A:X = the room left: LINE_COUNT - TEXT_ROWS - VIEW_TOP16
  SEC
  LDA LINE_COUNT16
  SBC TEXT_ROWS
  TAX
  LDA LINE_COUNT16 + 1
  SBC #0
  BCC .next                  ; Every line fits: the view stays
  TAY
  TXA
  SBC VIEW_TOP16             ; (C=1)
  TAX
  TYA
  SBC VIEW_TOP16 + 1
  BCC .next                  ; The view is past there: it stays
  BNE .add                   ; 256 or more
  CPX BUF_TEMP16
  BCS .add
  TXA                        ; Less than BUF_TEMP16: just that far
  BCC .add_a                 ; Always taken
.add:
  LDA BUF_TEMP16
.add_a:
  ADDA16 VIEW_TOP16
.next:
  DEC BUF_DELTA
  BNE scroll_view_down

; Shared scroll tail: the new view top starts at its line's first row
view_wrap_zero:
  LDA #0
  STA VIEW_TOP_WRAP
  RTS

; Scroll the viewport up BUF_DELTA (>= 1) times by BUF_TEMP16 (< 256)
; lines
; Modifies: FILE_LINE16, VIEW_TOP16, VIEW_TOP_WRAP, BUF_DELTA
; Clobbers: A, X
scroll_view_up:
  JSR move_up16
  LDX #VIEW_TOP16
  JSR sub_count_x              ; VIEW_TOP16 -= BUF_TEMP16, clamped to 0
  DEC BUF_DELTA
  BNE scroll_view_up
  BEQ view_wrap_zero       ; Always

normal_line_start:
  LDA #0
  STA_LH16 CURSOR_COL16
  JMP clear_count

; gg: go to line count, as G does (as in vim); no count: the first line
do_gg:
  TST16 COUNT16
  BNE normal_goto_last
  INC COUNT16                ; Line 1
  ; fall through

; G: the view is left to ensure_cursor_visible, which moves it only when
; the cursor's row is off screen, as for :N and k (a partly shown top
; line stays)
normal_goto_last:
  ; FILE_LINE16 = count - 1 (1-based count; no count: 0 - 1 = $FFFF),
  ; clamped to the last line
  SEC
  SBCI16 COUNT16, 1, FILE_LINE16
  JSR clamp_file_line
  JMP first_nonblank_clear

; --- Yank ---

; yy: yank N lines starting at current line (not pair-batched: yyyy runs
; yy twice, and the last yank wins)
do_yy:
  JSR get_count_clamp_lines  ; BUF_TEMP16 = count (16-bit)
; yy of BUF_TEMP16 lines (op_lines enters here)
yy_lines:
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
  LDY #OP_YANK
  JMP word_b_op

; ye: yank from cursor to end of word (inclusive, multi-line)
do_ye:
  LDY #OP_YANK
  JMP word_end_op

; --- Search ---

; n and N: repeat the last search, N the other way (SEARCH_DIR EOR $10:
; 0 <-> $10 = '/' EOR '?').  A count finds the Nth match, as in vim
; (wrapping around as often as it takes); only the first search can find
; nothing, and then the others are not tried
normal_find_next:
  LDA #0
  BEQ search_find            ; Always taken
normal_find_prev:
  LDA #$10
search_find:
  LDX SEARCH_LEN
  BEQ search_done            ; No pattern yet
  EOR SEARCH_DIR
  STA BUF_TEMP               ; This search's direction
  JSR get_count              ; BUF_TEMP16 = count (16-bit)
.again:
  LDA BUF_TEMP
  JSR search_dir
  BCC search_done            ; Not found
  JSR dec_buf_temp16
  BNE .again
search_done:
  JMP clear_count

; / and ?: read a pattern, then search as n does
normal_search:
  LDA #'/'
  BNE search_prompt          ; Always taken
normal_search_backward:
  LDA #'?'
search_prompt:
  JSR search_input_handle
  BCS search_done            ; Cancelled
  LDA #0
  BEQ search_find            ; Always taken

; --- Marks ---

; Execute mark set with register letter in BUF_TEMP
do_mark_set:
  LDA BUF_TEMP
  JSR mark_set
  JMP keep_clear_count

; Execute mark goto with register letter in BUF_TEMP
do_mark_goto:
  LDA BUF_TEMP
  JSR mark_get
  BCS .mark_not_set
  STAX16 FILE_LINE16
  JSR clamp_file_line        ; A stale mark must not point past EOF
  JMP first_nonblank_clear
.mark_not_set:
  JSR range_mark_err         ; "Mark not set"
  JMP clear_count
