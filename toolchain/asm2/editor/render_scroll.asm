; Line-level scroll repaint paths and render utilities.
;
; Scroll-region repaints for line deletion, line insertion, and in-place
; range changes (RENDER_FLAG=$0B), plus the limited-row render loop,
; row/line mapping, wrap math, and cursor visibility.  Part of the
; render engine; see render.asm and render_decide.asm.


; Scroll for line deletion at cursor.
; SCROLL_DELTA = screen rows deleted.  The rows below the ones this path
; redraws scroll up (scroll_up_clamped): from first_row (= CURSOR_ROW -
; WRAP_QUOT) for pure newline joins (INSERT_LINE_COUNT 1-254), else from
; first_row + DELETE_SCREEN_ROWS (the cursor line's rows that are kept:
; $06/$08, and for $07 those of a cursor line above the deleted lines),
; or from the top row if that is above the view.  Then the changed
; cursor line ($06/$08) and the exposed bottom rows are drawn.
render_line_delete_scroll:
  JSR ansi_cursor_hide
  JSR set_first_row          ; first_row (0-based)
  BCS .first_row_ok
  ; The line starts above the view (it is the view's top line): lines
  ; deleted from its first row scroll from the top row
  LDX DELETE_SCREEN_ROWS
  BNE .first_row_ok          ; (the rows kept reach into the view)
  TXA
.first_row_ok:
  LDX INSERT_LINE_COUNT
  INX
  CPX #2
  BCS .to_one_based          ; 1-254: pure newline join
  ADC DELETE_SCREEN_ROWS     ; C=0: skip the cursor line's rows
.to_one_based:
  CLC
  ADC #1                     ; 1-based
  JSR scroll_up_clamped      ; SCROLL_DELTA = rows exposed at the bottom

  LDA RENDER_FLAG
  CMP #RF_DEL
  BEQ .del_bottom_rows       ; $07: the cursor line is not redrawn
  ; $06 (J) / $08 (charwise delete): redraw the joined cursor line
  ; (DELETE_SCREEN_ROWS = its rows) from the change point, unless only
  ; newlines were deleted (cursor line content unchanged).  One row (or
  ; 0: the pre-compute overflowed) is drawn as a one-row line from the
  ; change point; a cursor on a wrap row redraws to the bottom.
  LDA INSERT_LINE_COUNT
  BNE .del_bottom_rows
  LDA DELETE_SCREEN_ROWS
  CMP #2
  BCS .draw_line
  LDA WRAP_QUOT
  BEQ .one_row
.from_first_row:
  JMP render_from_first_row
.one_row:
  LDA #1
.draw_line:
  STA CUR_LINE_ROWS
  JSR set_first_row
  BCS .draw_change
  ; The line starts above the view.  A change point is on a visible row
  ; (at or after the cursor's), but a whole-line change is drawn from
  ; the top row
  JSR check_from_col
  BCS .from_first_row        ; $FFFF: the whole line
.draw_change:
  LDA SCROLL_DELTA
  PHA                        ; bottom rows (clobbered by the line render)
  JSR render_line_from_change
  PLA
  STA SCROLL_DELTA
.del_bottom_rows:
  JMP render_bottom_rows

; Scroll for line insertion at cursor.
; SCROLL_DELTA = lines inserted. CURSOR_ROW = screen row of insertion.
; Scrolls rows from cursor down, renders newly inserted rows at cursor.
render_line_insert_scroll:
  JSR ansi_cursor_hide

  ; Scroll the region from its start row (1-based) to SCREEN_ROWS-1 down:
  ;   $03/$0A: from CURSOR_ROW+1 (includes the cursor row)
  ;   $04/$09: from first_row + PREV_LINE_ROWS + 1 (skip the rows the
  ;            cursor line keeps)
  LDA CURSOR_ROW
  LDX RENDER_FLAG
  CPX #RF_UNJOIN
  BEQ .scroll_skip_cursor_ins
  CPX #RF_SPLIT
  BNE .to_one_based
.scroll_skip_cursor_ins:
  JSR set_first_row
  CLC
  ADC PREV_LINE_ROWS     ; past end of cursor line (0-based)
.to_one_based:
  CLC
  ADC #1           ; Convert to 1-based
  LDX #'T'               ; scroll down
  JSR scroll_region_from_a

  ; If INSERT_LINE_COUNT is set, the actual repaint needs more rows than the
  ; scroll (e.g., cc undo: net file delta < inserted line count).
  ; Walk INSERT_LINE_COUNT lines to compute repaint screen rows.
  LDA INSERT_LINE_COUNT
  BEQ .ins_repaint_default

  JSR set_render_line_to_cursor
  LDA #0
  STA SCROLL_DELTA           ; Recompute as repaint row count
.walk_repaint:
  JSR render_line_rows_step
  BCS .repaint_clamp         ; they fill the text rows
  DEC INSERT_LINE_COUNT
  BNE .walk_repaint
.repaint_clamp:
  JSR clamp_delta_avail      ; (the rows from the cursor row down)

.ins_repaint_default:
  ; Render SCROLL_DELTA rows at CURSOR_ROW (newly inserted content).
  LDA CURSOR_ROW
  STA RENDER_ROW
  JMP find_and_render

; Range repaint (RENDER_FLAG=$0B): INSERT_LINE_COUNT lines changed in
; place starting at FILE_LINE16 (line count unchanged; wrap rows may
; differ).  DELETE_SCREEN_ROWS = the range's screen rows before the edit.
; The cursor sits on the first line of the range, so the range's first
; screen row is CURSOR_ROW - WRAP_QUOT.  The range is then redrawn like a
; single changed line of PREV_LINE_ROWS -> CUR_LINE_ROWS rows (see
; render_rows_resized; both are free here: main_loop recomputes
; PREV_LINE_ROWS every key): the region below scrolls to open/close the
; difference, and RENDER_FROM_COL16 = $FFFF redraws every row of the
; range.  A range reaching the status bar repaints to the bottom.
render_range_repaint:
  JSR set_first_row            ; RENDER_ROW = first_row
  BCC .rr_full                 ; line starts above the view
  LDA DELETE_SCREEN_ROWS
  STA PREV_LINE_ROWS           ; the range's rows before the edit
  LDA INSERT_LINE_COUNT
  JSR compute_delete_rows_at_cursor
  LDA DELETE_SCREEN_ROWS       ; the range's rows now (0 = overflow)
  BEQ .rr_full
  STA CUR_LINE_ROWS
  ; Bounds: first_row + max(old, new) must fit above the status bar
  CMP PREV_LINE_ROWS
  BCS .max_is_new
  LDA PREV_LINE_ROWS
.max_is_new:
  CLC
  ADC RENDER_ROW
  BCS .rr_to_bottom            ; 8-bit overflow
  CMP SCREEN_ROWS
  BCS .rr_to_bottom
  JMP render_rows_resized
.rr_to_bottom:
  ; Repaint everything from first_row to the bottom of the screen
  LDA TEXT_ROWS
  SEC
  SBC RENDER_ROW
  STA SCROLL_DELTA
  JSR ansi_cursor_hide
  JMP render_from_first_row_limited
.rr_full:
  JMP render_screen

; Enter batch (RENDER_FLAG=$05): the batch deleted no newline, so it
; began on one line of PREV_LINE_ROWS rows from screen row F and split it
; into the fd + 1 lines that end at the cursor line (fd = RENDER_LIMIT).
; The rows below the old line scroll down by the growth in rows, then the
; new lines are drawn from the first cell the batch changed
; (RENDER_FROM_COL16) to their end.  The rows are worked out from the
; cursor row, as F is negative when the old line starts above the view
; (its later rows on screen); the drawing then starts at the top row.  A
; pure Enter batch at the start of the line (INSERT_LINE_COUNT = $FF)
; scrolls from F instead, moving the whole line down, and one at its end
; ($7F) opens the new empty lines: both are drawn by the scroll alone,
; unless its region was one row that could not be scrolled (only at the
; end of the line: the cursor line is then drawn there).  Text that
; shrank (BS/Del in the batch) or new lines reaching past row 254 are
; drawn in full.
render_enter_split:
  JSR ansi_cursor_hide
  ; RENDER_LINE16 = the first line of the split = FILE_LINE16 - fd
  SEC
  SBC16_8 FILE_LINE16, RENDER_LIMIT, RENDER_LINE16
  ; RENDER_WRAP = CURSOR_ROW - F = WRAP_QUOT + the rows of the fd lines
  ; above the cursor line
  LDA RENDER_LIMIT
  JSR compute_delete_screen_rows
  LDA DELETE_SCREEN_ROWS
  BEQ .full                    ; over 255
  CLC
  ADC WRAP_QUOT
  BCS .full
  STA RENDER_WRAP
  ; CUR_LINE_ROWS = the new lines' rows (those and the cursor line's)
  JSR file_line_rows
  CLC
  ADC DELETE_SCREEN_ROWS
  BCS .full
  STA CUR_LINE_ROWS
  ; RENDER_ROW = the 1-based row after them = F + CUR_LINE_ROWS + 1
  SEC
  SBC RENDER_WRAP              ; (the cursor line's rows from the cursor)
  SEC
  ADC CURSOR_ROW
  BCS .full
  STA RENDER_ROW
  ; SCROLL_DELTA = the growth
  LDA CUR_LINE_ROWS
  SEC
  SBC PREV_LINE_ROWS
  BCC .full                    ; shrank
  STA SCROLL_DELTA
  BEQ .draw                    ; the same height: nothing to scroll
  ; Scroll down from below the old line, RENDER_ROW - the growth (from F,
  ; RENDER_ROW - CUR_LINE_ROWS, at the line's start)
  LDX INSERT_LINE_COUNT
  BPL .scroll
  LDA CUR_LINE_ROWS
.scroll:
  EOR #$FF
  SEC
  ADC RENDER_ROW
  LDX #'T'                     ; scroll down
  JSR scroll_region_from_a     ; C=0: not scrolled
  LDX INSERT_LINE_COUNT
  BEQ .draw                    ; not a pure Enter batch at either end
  BCS render_finish
  JMP render_from_first_row_limited  ; the one row (SCROLL_DELTA = 1)
.draw:
  ; Draw from the first changed cell, row F + q and column WRAP_REM (the
  ; top row from column 0 if that is above the view), to the last new row
  JSR check_from_col           ; X = q (the column is never $FFFF)
  STX RENDER_COL
  LDA RENDER_WRAP
  SEC
  SBC RENDER_COL               ; CURSOR_ROW - (F + q) >= 0
  EOR #$FF
  SEC
  ADC CURSOR_ROW               ; F + q; C=0: above the view
  BCS .from_row
  LDA #0
  STA WRAP_REM
.from_row:
  STA RENDER_COL
  LDA RENDER_ROW
  CLC
  SBC RENDER_COL
  STA SCROLL_DELTA             ; rows from there to the last new row
  LDA RENDER_COL
  STA RENDER_ROW
  JSR find_line_at_render_row
  LDA WRAP_REM
  JMP render_limited_rows_from_col
.full:
  JMP render_from_top

; === Scroll-region helpers ===
; Line-delete scroll: the region [A .. SCREEN_ROWS-1] (A = 1-based first
; row) lost SCROLL_DELTA rows from its top (screen rows deleted, or a
; line's lost rows), so the rows below them move up and the bottom rows
; are exposed.  SCROLL_DELTA is first clamped to the region's height
; (0 if A is at or past the status bar): the rows exposed never reach
; above the region.  The region is scrolled up by that many rows, unless
; they are all of it: then nothing is sent, as the caller repaints them
; all anyway.  The caller then draws its own rows above the region and
; ends with render_bottom_rows (which draws nothing for SCROLL_DELTA = 0).
; scroll_clamped does the same in the direction X ('S' up, 'T' down:
; the rows exposed are then at the region's top).
; In: A, SCROLL_DELTA (>= 1).  Out: SCROLL_DELTA = rows exposed.
; Clobbers A, X, Y
scroll_up_clamped:
  LDX #'S'                     ; scroll up
scroll_clamped:
  STA ANSI_ROW
  LDA SCREEN_ROWS
  SEC
  SBC ANSI_ROW                 ; the region's height
  BCS .height
  LDA #0                       ; the region starts past the status bar
.height:
  CMP SCROLL_DELTA
  BCC .all_exposed
  BNE scroll_region_check      ; height > SCROLL_DELTA: scroll
.all_exposed:
  STA SCROLL_DELTA
  RTS

; Set scroll region [A .. SCREEN_ROWS-1] (A = 1-based start row) and
; scroll it by SCROLL_DELTA rows: X = 'S' scrolls up, X = 'T' down.
; Skips (C=0) if the region is a single row (Z=1: that row is left as it
; was, not blanked) or invalid (Z=0); C=1 after a scroll.  Clobbers A, Y
; (X preserved).
scroll_region_from_a:
  STA ANSI_ROW
  ; fall through (entry with ANSI_ROW already set)
scroll_region_check:
  LDA TEXT_ROWS
  STA ANSI_COL
  CMP ANSI_ROW
  BEQ .skip                    ; single row: nothing to shift
  BCC .skip                    ; empty region
  JSR ansi_set_scroll_region   ; preserves X
  LDA SCROLL_DELTA
  JSR ansi_count_seq           ; ESC[nS / ESC[nT
  JSR ansi_reset_scroll_region
  SEC
  RTS
.skip:
  CLC
  RTS

; Repaint the newly exposed bottom SCROLL_DELTA rows (none for 0):
; RENDER_ROW = TEXT_ROWS - SCROLL_DELTA, then find the file line there
; and render to the bottom
render_bottom_rows:
  LDX SCROLL_DELTA
  BEQ render_finish            ; nothing exposed
  LDA TEXT_ROWS
  SEC
  SBC SCROLL_DELTA
  STA RENDER_ROW
find_and_render:
  JSR find_line_at_render_row
  ; fall through to render_limited_rows

; Render limited rows: renders SCROLL_DELTA rows starting at
; RENDER_ROW/RENDER_LINE16/RENDER_WRAP, then draws status bar + cursor;
; _from_col draws the first of them from column A.
render_limited_rows:
  LDA #0
render_limited_rows_from_col:
  JSR render_limited_from_col
; Frame epilogue: status bar, cursor, show, flush (shared tail)
render_finish:
  JSR render_status_line
  JSR render_position_cursor
  JSR ansi_cursor_show
  JMP io_flush

; Render loop only: renders SCROLL_DELTA rows starting at
; RENDER_ROW/RENDER_LINE16/RENDER_WRAP, the first of them from column A,
; then returns.  Caller must handle status bar, cursor positioning, etc.
render_limited_from_col:
  STA RENDER_COL
  LDA RENDER_ROW
  CLC
  ADC SCROLL_DELTA
  STA RENDER_LIMIT             ; stop at this row
; Render rows from RENDER_ROW/RENDER_LINE16/RENDER_WRAP up to (not
; including) row RENDER_LIMIT or the status bar, the first from column
; RENDER_COL and the rest from column 0.  A wrapped line's continuation
; rows are reached by the terminal's auto-wrap (the row before was
; written full width), so only a line's first row (and the first row
; drawn) positions the cursor.
render_rows:
.row_loop:
  JSR .row_check               ; A = RENDER_ROW
  BCS .done
  LDX RENDER_COL
  JSR ansi_goto0
.row:
  ; Check if line exists
  CMP16 RENDER_LINE16, LINE_COUNT16
  BCS .past_eof
  ; Line pointer advanced by RENDER_WRAP * SCREEN_COLS
  LDAX16 RENDER_LINE16
  JSR buf_get_line_ptr
  LDX RENDER_WRAP
  JSR buf_ptr_advance_x
  JSR render_line_chars_from   ; Y = the column after the last char
  LDA #0
  STA RENDER_COL               ; the rows after it from column 0
  ; A full row may continue on the next wrap row (unless at a newline)
  CPY SCREEN_COLS
  BNE .line_done
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .line_ended
  INC RENDER_WRAP
  INC RENDER_ROW
  JSR .row_check
  BCC .row                     ; the terminal has wrapped to the next row
.done:
  RTS

.line_done:
  JSR ansi_clear_line
.line_ended:
  INC16 RENDER_LINE16
  LDA #0
  STA RENDER_WRAP
.next_row:
  INC RENDER_ROW
  JMP .row_loop

.past_eof:
  LDA #'~'
  JSR io_write
  JSR ansi_clear_line
  JMP .next_row

; C=1 if RENDER_ROW reached RENDER_LIMIT or the status bar, else C=0;
; A = RENDER_ROW
.row_check:
  LDA RENDER_ROW
  CMP RENDER_LIMIT
  BCS .check_done
  CMP TEXT_ROWS                ; (RENDER_ROW < RENDER_LIMIT: never 255)
.check_done:
  RTS

; Walk from VIEW_TOP16 forward to find which file line corresponds
; to screen row RENDER_ROW. Sets RENDER_LINE16 and RENDER_WRAP.
; Handles wrapped lines (one file line can span multiple screen rows).
; Input: RENDER_ROW = target screen row
; Output: RENDER_LINE16 = file line at that row
;         RENDER_WRAP = wrap row offset within the line
; Clobbers: A, X, Y, BUF_PTR16, DIV_INPUT16, RENDER_LIMIT
find_line_at_render_row:
  CP16 VIEW_TOP16, RENDER_LINE16
  LDA VIEW_TOP_WRAP
  STA RENDER_WRAP
  LDA RENDER_ROW
  BEQ .found
  STA RENDER_LIMIT         ; remaining rows to skip
.walk:
  JSR render_line_rows     ; A = total screen rows for this line
  SEC
  SBC RENDER_WRAP           ; visible rows = total - RENDER_WRAP
  CMP RENDER_LIMIT
  BEQ .skip_line           ; exactly consumes remaining → next line
  BCS .within_line         ; target is within this wrapped line
.skip_line:
  ; Subtract visible rows (A) from RENDER_LIMIT
  EOR #$FF
  SEC
  ADC RENDER_LIMIT         ; RENDER_LIMIT - visible_rows
  STA RENDER_LIMIT
  INC16 RENDER_LINE16
  LDA #0
  STA RENDER_WRAP           ; subsequent lines start at wrap 0
  LDA RENDER_LIMIT
  BNE .walk
  BEQ .found                 ; Always taken
.within_line:
  ; Target is within this line: wrap = base_wrap + remaining
  LDA RENDER_WRAP
  CLC
  ADC RENDER_LIMIT
  STA RENDER_WRAP
.found:
  RTS

; Render just the status bar and reposition cursor (no content redraw)
render_cursor_and_status:
  JSR ansi_cursor_hide
  JMP render_finish

; Print line characters from BUF_PTR16 + RENDER_COL up to SCREEN_COLS or
; newline.  Control chars: tab as '>' reverse, others (and bytes >= $80)
; as '?' reverse.  Returns RENDER_COL = Y = column after the last char
; printed.  Clobbers A, Y.
render_line_chars_from:
  LDA SCREEN_COLS
  STA RENDER_STOP
; Entry with RENDER_COL and RENDER_STOP (exclusive) set by the caller
render_line_chars_to:
  LDY RENDER_COL
.loop:
  LDA (BUF_PTR16),Y
  BMI .unprintable
  CMP #'\n'
  BEQ .done
  CMP #' '
  BCC .ctrl
  JSR io_write
.next:
  INY
  CPY RENDER_STOP
  BCC .loop
.done:
  STY RENDER_COL
  RTS
.ctrl:
  CMP #'\t'
  BNE .unprintable
  LDA #'>'
  BNE .rev_char                ; Always taken
.unprintable:
  LDA #'?'
.rev_char:
  STA BUF_TEMP
  TYA
  PHA
  JSR ansi_reverse_video
  LDA BUF_TEMP
  JSR io_write
  JSR ansi_normal_video
  PLA
  TAY
  JMP .next

; Check RENDER_FROM_COL16 for the partial-render paths.
; Returns C=1 if $FFFF (unknown change: render the full line).
; Otherwise returns C=0 with X = from_wrap and A = WRAP_REM = from_col.
; Clobbers DIV_INPUT16
check_from_col:
  LDA RENDER_FROM_COL16 + 1
  AND RENDER_FROM_COL16
  CMP #$FF
  BEQ .ffff                    ; $FFFF: CMP left C=1
  CP16 RENDER_FROM_COL16, DIV_INPUT16
  JSR div_mod_screen_cols_16   ; X = from_wrap, A = from_col
  STA WRAP_REM                 ; save from_col
  CLC                          ; div can exit with C=1 on the cap path
.ffff:
  RTS

; === Wrap utility functions ===

; Divide 16-bit value in DIV_INPUT16 by SCREEN_COLS using repeated subtraction
; Returns: X = quotient (capped at 255), A = remainder
; Clobbers: X
div_mod_screen_cols_16:
  LDX #0
.div_loop:
  LDA DIV_INPUT16 + 1
  BNE .can_sub               ; High byte > 0, definitely >= SCREEN_COLS
  LDA DIV_INPUT16
  CMP SCREEN_COLS
  BCC .div_done              ; Value < SCREEN_COLS, done
.can_sub:
  LDA DIV_INPUT16
  SEC
  SBC SCREEN_COLS
  STA DIV_INPUT16
  BCS .no_borrow
  DEC DIV_INPUT16 + 1
.no_borrow:
  INX
  BNE .div_loop
  DEX                        ; Quotient wrapped to 0: cap at 255
  LDA #0                     ; Remainder doesn't matter at cap
.div_done:
  RTS

; Walk step for the scroll-delta walks: add the screen rows of the line
; at RENDER_LINE16 to SCROLL_DELTA (scroll_delta_add), then advance
; RENDER_LINE16.
; Clobbers A, X, Y, BUF_PTR16, DIV_INPUT16
render_line_rows_step:
  JSR render_line_rows
  INC16 RENDER_LINE16          ; (keeps A)
  ; fall through
; Add A to SCROLL_DELTA, stopping at 255.  Returns C=1 if the sum is
; TEXT_ROWS or more: the rows fill the text area (a view move that far
; draws every row, and inserted rows that far fill the rows below the
; cursor, whatever the rest of the sum).  Clobbers A
scroll_delta_add:
  CLC
  ADC SCROLL_DELTA
  BCC .sum
  LDA #$FF                     ; over 255
.sum:
  STA SCROLL_DELTA
  CMP TEXT_ROWS
  RTS

; Screen rows of the line at RENDER_LINE16 (1 for a line past the end: a
; '~' row, which the walks below the last line pass through)
; Returns: A = rows. Clobbers X, Y, BUF_PTR16, DIV_INPUT16
render_line_rows:
  LDAX16 RENDER_LINE16
  CMP LINE_COUNT16
  PHA
  TXA
  SBC LINE_COUNT16 + 1
  PLA
  BCC get_len_rows           ; A line of the buffer
  LDA #1
  RTS

; Screen rows of the line at FILE_LINE16
; Returns: A = rows. Clobbers X, Y, BUF_PTR16, DIV_INPUT16
; get_len_rows: the same for line number A/X (low/high)
file_line_rows:
  LDAX16 FILE_LINE16
  ; fall through
get_len_rows:
  JSR buf_get_line_len
  ; fall through

; Compute number of screen rows a line occupies
; Input: A/X = 16-bit line length (A=low, X=high)
; Returns: A = number of screen rows (1 for empty/short, ceil(len/SCREEN_COLS) for longer)
; Clobbers: X, DIV_INPUT16
line_screen_rows:
  STA DIV_INPUT16
  STX DIV_INPUT16 + 1
  ORA DIV_INPUT16 + 1
  BNE .not_empty
  LDA #1
  RTS
.not_empty:
  JSR div_mod_screen_cols_16   ; X = quotient, A = remainder
  CMP #1                       ; C=1: partial last row
  TXA
  ADC #0
  RTS

; Pre-compute screen rows of lines for line-delete scroll.
; Entries: _temp16 walks BUF_TEMP16 lines from the cursor line (0 rows if
; > 255), at most SCREEN_ROWS of them: each takes a row, so they already
; fill any scroll region; _join walks the cursor line plus the A lines
; after it; _at_cursor walks A lines from the cursor line; the base entry
; walks A lines from RENDER_LINE16.
; Output: DELETE_SCREEN_ROWS set (0 on overflow = fall back to file delta)
; Clobbers: A, X, Y, RENDER_LIMIT, RENDER_LINE16, BUF_PTR16, DIV_INPUT16
compute_delete_rows_temp16:
  LDA BUF_TEMP16
  LDX BUF_TEMP16 + 1
  BNE cdsr_overflow            ; > 255 lines
  CMP SCREEN_ROWS
  BCC compute_delete_rows_at_cursor
  LDA SCREEN_ROWS
  BCS compute_delete_rows_at_cursor  ; Always taken
compute_delete_rows_join:
  CLC
  ADC #1                       ; + the cursor line
compute_delete_rows_at_cursor:
  TAX
  JSR set_render_line_to_cursor
  TXA
compute_delete_screen_rows:
  STA RENDER_LIMIT
  LDA #0
  STA DELETE_SCREEN_ROWS
.loop:
  JSR render_line_rows
  CLC
  ADC DELETE_SCREEN_ROWS
  BCS .overflow              ; > 255
  STA DELETE_SCREEN_ROWS
  INC16 RENDER_LINE16
  DEC RENDER_LIMIT
  BNE .loop
  RTS
.overflow:
cdsr_overflow:
  LDA #0
  STA DELETE_SCREEN_ROWS     ; Signal fall back to file delta
  RTS

; Ensure cursor is visible on screen (wrap-aware)
; Updates CURSOR_ROW from FILE_LINE16 and VIEW_TOP16
; Scrolls VIEW_TOP16 if needed (render_decide detects the change)
ensure_cursor_visible:
  ; Compute cursor's wrap row: CURSOR_COL16 / SCREEN_COLS
  CP16 CURSOR_COL16, DIV_INPUT16
  JSR div_mod_screen_cols_16
  STX WRAP_QUOT      ; cursor_wrap_row

  ; Check if cursor is above view
  ; FILE_LINE16 < VIEW_TOP16?
  CMP16 FILE_LINE16, VIEW_TOP16
  BCC .scroll_up
  BNE .not_above     ; FILE_LINE16 > VIEW_TOP16

  ; FILE_LINE16 == VIEW_TOP16: check wrap row
  LDA WRAP_QUOT
  CMP VIEW_TOP_WRAP
  BCS .not_above

.scroll_up:
  ; Scroll up: the cursor's row becomes the top row
  LDA #0
  BEQ .set_top       ; Always taken

.not_above:
  ; CURSOR_ROW = screen rows of the lines from (VIEW_TOP16, VIEW_TOP_WRAP)
  ; up to FILE_LINE16, plus the cursor's wrap row.  RENDER_WRAP = rows of
  ; the current line hidden above the view (VIEW_TOP_WRAP for the top line)
  CP16 VIEW_TOP16, RENDER_LINE16
  LDA VIEW_TOP_WRAP
  STA RENDER_WRAP
  LDA #0
  STA CURSOR_ROW
.walk_loop:
  CMP16 RENDER_LINE16, FILE_LINE16
  BEQ .at_cursor
  JSR render_line_rows
  SEC
  SBC RENDER_WRAP              ; visible rows of this line
  BEQ .top_gone
  BCS .visible_rows
.top_gone:
  ; The view began past the top line's last row: an Enter at or before
  ; the view's first cell cut the line short there.  The view starts at
  ; the next line, whose text the top rows showed
  INC16 VIEW_TOP16
  LDA #0
  STA VIEW_TOP_WRAP
.visible_rows:
  CLC
  ADC CURSOR_ROW
  BCS .need_scroll_down  ; 8-bit overflow: cursor far below screen
  STA CURSOR_ROW
  LDA #0
  STA RENDER_WRAP
  INC16 RENDER_LINE16
  JMP .walk_loop

.at_cursor:
  ; Add cursor's wrap row within FILE_LINE16
  LDA WRAP_QUOT
  SEC
  SBC RENDER_WRAP
  CLC
  ADC CURSOR_ROW
  BCS .need_scroll_down  ; 8-bit overflow
  STA CURSOR_ROW

  ; Check if cursor is below view (CURSOR_ROW >= SCREEN_ROWS - 1)
  ADC #1                 ; C=0
  CMP SCREEN_ROWS
  BCC .visible

.need_scroll_down:
  ; Cursor is below visible area: walk back TEXT_ROWS - 1 rows from
  ; the cursor's row to find the new VIEW_TOP16 / VIEW_TOP_WRAP
  LDX TEXT_ROWS
  DEX
  TXA                    ; Target: cursor at row TEXT_ROWS - 1
.set_top:
  STA CURSOR_ROW
  STA RENDER_ROW      ; Rows to walk back
  CP16 FILE_LINE16, VIEW_TOP16
  LDA WRAP_QUOT
  STA VIEW_TOP_WRAP

.walk_back:
  LDA RENDER_ROW
  BEQ .visible
  ; Can we go back within current line?
  LDA VIEW_TOP_WRAP
  BNE .back_one_row
  TST16 VIEW_TOP16
  BEQ .at_top
  DEC16 VIEW_TOP16
  LDAX16 VIEW_TOP16
  JSR get_len_rows
  STA VIEW_TOP_WRAP      ; its last row (decremented below)
.back_one_row:
  DEC VIEW_TOP_WRAP
  DEC RENDER_ROW
  JMP .walk_back

.at_top:
  ; Hit beginning of file - adjust cursor row
  LDA CURSOR_ROW
  SEC
  SBC RENDER_ROW
  STA CURSOR_ROW

.visible:
  RTS
