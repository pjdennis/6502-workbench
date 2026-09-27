; Line-level scroll repaint paths and render utilities.
;
; Scroll repaints (DL/IL) for line deletion, line insertion, and in-place
; range changes (RF_RANGE), plus the limited-row render loop,
; row/line mapping, wrap math, and cursor visibility.  Part of the
; render engine; see render.asm and render_decide.asm.


; === Scroll helpers ===
; The rows from 1-based row A to the last text row (TEXT_ROWS) move up
; ('M') or down ('L') by SCROLL_DELTA rows, with DL and IL: no scroll
; region is set, and the status bar keeps its place (see
; scroll_region_check).
; Line-delete scroll: the rows [A .. TEXT_ROWS] lost SCROLL_DELTA rows
; from their top (screen rows deleted, or a line's lost rows), so the
; rows below them move up and the bottom rows are exposed.  SCROLL_DELTA
; is first clamped to their height (0 if A is at or past the status
; bar): the rows exposed never reach above them.  They move up by that
; many rows, unless that is all of them: then nothing is sent, as the
; caller repaints them all anyway.  The caller draws its own rows above
; A first and ends with render_bottom_rows (which draws nothing for
; SCROLL_DELTA = 0), so the drawing starts where IL left the cursor.
; scroll_clamped does the same in the direction X ('M' up, 'L' down:
; the rows exposed are then at the top, from row A).
; In: A, SCROLL_DELTA (>= 1).  Out: SCROLL_DELTA = rows exposed.
; Clobbers A, X, Y
scroll_up_clamped:
  LDX #'M'                     ; rows move up
scroll_clamped:
  TAY                          ; Y = the first row that moves
  EOR #$FF
  SEC
  ADC SCREEN_ROWS              ; their height
  BCS .height
  LDA #0                       ; they start past the status bar
.height:
  CMP SCROLL_DELTA
  BCC .all_exposed
  BNE scroll_region_check      ; height > SCROLL_DELTA: scroll
.all_exposed:
  STA SCROLL_DELTA
  RTS

; Move the rows [A .. TEXT_ROWS] (A = 1-based) by SCROLL_DELTA rows, or
; blank them all when it is more: X = 'M' moves them up, X = 'L' down.
; The rows that go are deleted with DL (ESC[nM) and blank rows inserted
; with IL (ESC[nL), from the bottom text row R = TEXT_ROWS + 1 - n: up,
; DL at A (the status bar moves up to R) then IL at R (it moves back);
; down, DL at R then IL at A.  Each is sent at column 1 of its row,
; which IL and DL leave the cursor at on any terminal: the cursor is
; left at the first row opened, where a frame that draws from there sends
; no move (CUR_VALID).  Skips (C=0) if the rows are a single row (Z=1:
; that row is left as it was, not blanked) or none (Z=0); C=1 after a
; scroll.  Clobbers A, X, Y
scroll_region_from_a:
  TAY
  ; fall through (entry with the start row in Y)
scroll_region_check:
  CPY TEXT_ROWS
  BCS .skip                    ; a single row (Z=1): nothing to shift, or
                               ; none (Z=0)
  TYA
  EOR #$FF
  SEC
  ADC TEXT_ROWS                ; the rows below row A
  CMP SCROLL_DELTA
  BCS .count                   ; SCROLL_DELTA of them move
  ADC #1                       ; (C=0) fewer: all the rows are blanked
  .byte $2C                    ; BIT abs: skip the LDA
.count:
  LDA SCROLL_DELTA
  STA SCROLL_N                 ; the count for DL and IL (and the rows
                               ; IL opens from SCROLL_ROW2: render_rows)
  EOR #$FF
  SEC
  ADC TEXT_ROWS                ; R - 1 (0-based)
  DEY                          ; A - 1
  CPX #'M'
  BEQ .up
  STY SCROLL_ROW2              ; down: DL at R, IL at A
  TAY
  .byte $2C                    ; BIT abs: skip the STA
.up:
  STA SCROLL_ROW2              ; up: DL at A, IL at R
  LDA #'M'
  JSR .line_op
  LDY SCROLL_ROW2
  LDA #'L'
  JSR .line_op
  SEC
  RTS
.skip:
  CLC                          ; (Z kept)
  RTS
; ESC[<row>H ESC[<n><A> for 0-based row Y, n = SCROLL_N, A = 'M' or 'L'
.line_op:
  PHA
  TYA
  JSR ansi_goto_row0
  PLA
  TAX
  LDA SCROLL_N
  JSR ansi_count_seq
  INC CUR_VALID                ; the cursor is at column 1 of that row
  RTS

; Range repaint (RF_RANGE): INSERT_LINE_COUNT lines changed in
; place starting at UNDO_LINE16 (line count unchanged; wrap rows may
; differ).  DELETE_SCREEN_ROWS = the range's screen rows before the edit.
; The cursor sits on the first line of the range, or on its last after
; :N,M> and :N,M< (as in vim): WRAP_QUOT takes the rows of the range's
; lines above the cursor's too, so that CURSOR_ROW - WRAP_QUOT is the
; range's first screen row, and set_render_line_to_cursor points at the
; range's first line.  The range is then redrawn as a block of lines of
; PREV_LINE_ROWS -> CUR_LINE_ROWS rows (render_block_and_status; both
; are free here: main_loop recomputes PREV_LINE_ROWS every key): the
; region below scrolls to open/close the difference, and
; RENDER_FROM_COL16 = $FFFF redraws every row of the range.  A range of
; one line (>> or << of the cursor line, their undo) is drawn as an edit
; of that line: an ICH/DCH hint at its column 0 for the blanks it gained
; or lost, the change in the text's length.
render_range_repaint:
  LDA DELETE_SCREEN_ROWS
  STA PREV_LINE_ROWS           ; the range's rows before the edit
  LDX INSERT_LINE_COUNT
  DEX
  BNE .range
  STX RENDER_FROM_COL16
  STX RENDER_FROM_COL16 + 1
  LDA BUF_END16
  SEC
  SBC SNAP_BUF_END16
  STA SHIFT_NET
  BMI .hint                    ; blanks removed: no new cells
  TAX
.hint:
  STX SHIFT_WRITE
  JMP render_current_line_and_status
.range:
  SEC
  LDA FILE_LINE16
  SBC UNDO_LINE16              ; The range's lines above the cursor's
  BEQ .first_row               ; (fewer than 256)
  JSR compute_delete_rows_at_cursor
  BCS .rr_full                 ; Over 255 rows
  ADC WRAP_QUOT                ; (C = 0)
  BCS .rr_full
  STA WRAP_QUOT
.first_row:
  LDA INSERT_LINE_COUNT
  JSR compute_delete_rows_at_cursor
  BCS .rr_full                 ; the range's rows now: over 255
  STA CUR_LINE_ROWS
  JMP render_block_and_status
.rr_full:
  JMP render_screen

; RENDER_WRAP = the rows from the first row of the line RENDER_LIMIT
; lines above the cursor line (0: the cursor line) to the cursor's row:
; WRAP_QUOT plus the rows of the lines between (DELETE_SCREEN_ROWS).
; C=1 if that is past 255.  Clobbers A, X, Y, RENDER_LIMIT,
; RENDER_LINE16, BUF_PTR16, DIV_INPUT16
rows_to_cursor:
  LDA #0
  CLC
  LDX RENDER_LIMIT
  BEQ .rows
  SEC
  SBC16_8 FILE_LINE16, RENDER_LIMIT, RENDER_LINE16
  LDA RENDER_LIMIT
  JSR compute_delete_screen_rows  ; A = their rows (C=1: over 255)
  BCS .done
.rows:
  ADC WRAP_QUOT
  STA RENDER_WRAP
.done:
  RTS

; A = the screen row of the first changed cell of a line that starts
; RENDER_WRAP rows above the cursor's row (rows_to_cursor): its row in
; the line (check_from_col; $FFFF: the line's first cell) counted from
; there, or the cursor's row for a cell at or below it (drawing from a
; cell before the first change is as right); WRAP_REM = its column.
; C=0 if it is above the view.  Clobbers A, X, DIV_INPUT16
change_cell_row:
  JSR check_from_col           ; X = its row in the line
  BCC .have
  LDX #0
  STX WRAP_REM
.have:
  TXA
  SEC
  SBC RENDER_WRAP              ; C=0: above the cursor's row
  BCS .cursor_row
  ADC CURSOR_ROW               ; C=1: on screen
  RTS
.cursor_row:
  LDA CURSOR_ROW               ; (C=1)
  RTS

; Enter batch (RF_ENTER): the batch deleted no newline, so it
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
  ; RENDER_WRAP = CURSOR_ROW - F = WRAP_QUOT + the rows of the fd lines
  ; above the cursor line
  JSR rows_to_cursor
  BCS .full                    ; over 255
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
  LDX INSERT_LINE_COUNT
  BNE .pure
  ; Not a pure Enter batch at either end: its rows are drawn, so a
  ; growth that fills the region below sends no scroll
  LDX #'L'                     ; scroll down
  JSR scroll_clamped
  JMP .draw
.pure:
  LDX #'L'                     ; scroll down
  JSR scroll_region_from_a     ; C=0: not scrolled
  BCS render_finish
  JMP render_from_first_row_limited  ; the one row (SCROLL_DELTA = 1)
.full:
  JMP render_from_top
.draw:
  ; Draw from the first changed cell, row F + q and column WRAP_REM (the
  ; top row from column 0 if that is above the view), to the last new row
  JSR change_cell_row          ; (the column is never $FFFF)
  BCS draw_rows_from
  LDA #0
  STA WRAP_REM
  ; fall through
; Draw from row A, column WRAP_REM, to the row before 1-based row
; RENDER_ROW ($FF: to the status bar), then end the frame
draw_rows_from:
  STA RENDER_COL
  LDA RENDER_ROW
  CLC
  SBC RENDER_COL
  STA SCROLL_DELTA             ; rows from there to the last one
  LDA RENDER_COL
  STA RENDER_ROW
  JSR find_line_at_render_row
  LDA WRAP_REM
  JMP render_limited_rows_from_col

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
  JSR status_build
render_finish_send:
  JSR status_send
render_finish_cursor:
  ; The cursor to the editing position (wrap-aware): screen column =
  ; CURSOR_COL16 % SCREEN_COLS
  JSR cursor_col_div
  TAX                          ; X = remainder (screen col, 0-based)
  LDA CURSOR_ROW
  JSR ansi_goto0
  INC CUR_VALID                ; the next frame starts with it there
  JSR ansi_cursor_show
  STA SCROLL_N                 ; (A = 0) the rows its scroll opened are
  JMP io_flush                 ; drawn: none is blank now

; Render just the status bar and reposition the cursor (no content
; redraw).  An unchanged status bar sends nothing, so the cursor need not
; be hidden.
render_cursor_and_status:
  JSR status_build
  LDA ST_FIRST
  BMI render_finish_cursor     ; unchanged
  JSR ansi_cursor_hide
  BEQ render_finish_send       ; Always taken (write_string returns A = 0)

; Render loop only: renders SCROLL_DELTA rows starting at
; RENDER_ROW/RENDER_LINE16/RENDER_WRAP, the first of them from column A,
; then returns.  Caller must handle status bar, cursor positioning, etc.
render_limited_from_col:
  STA RENDER_COL
  LDA RENDER_ROW
  CLC
  ADC SCROLL_DELTA
  BCC .limit
  LDA #$FF                     ; past row 255 (a line running past the
.limit:                        ; screen): stop at the status bar
  STA RENDER_LIMIT             ; stop at this row
; Render rows from RENDER_ROW/RENDER_LINE16/RENDER_WRAP up to (not
; including) row RENDER_LIMIT or the status bar, the first from column
; RENDER_COL and the rest from column 0.  Only the first row drawn needs
; a cursor move: a wrapped line's continuation rows are reached by the
; terminal's auto-wrap (the row before was written full width), and a
; row after a short row or '~' by CR LF.  A short row or '~' ends with
; ESC[K, unless the frame's scroll opened it (IL left it blank).  A
; row after one that ended its line exactly full gets a move, as
; terminals differ in where the cursor is then.  No LF leaves the last
; text row (the loop stops there), so none can scroll the screen.
render_rows:
  LDX #0                       ; the first row: a cursor move
.row_loop:
  JSR .row_check               ; A = RENDER_ROW
  BCS .done
  DEX
  BNE .move                    ; X was 0: a cursor move
  LDA #'\r'                    ; X was 1: CR LF
  JSR io_write
  LDA #'\n'
  JSR io_write
  BNE .row                     ; Always (A = LF)
.move:
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
.advance:
  JSR buf_ptr_advance_x        ; (X = 0 after it)
  JSR render_line_chars_from   ; Y = the column after the last char (X kept)
  STX RENDER_COL               ; the rows after it from column 0 (X = 0)
  ; A full row may continue on the next wrap row (unless at a newline)
  CPY SCREEN_COLS
  BNE .line_done
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .line_ended              ; X = 0: a cursor move to the next row
  INC RENDER_ROW
  JSR .row_check               ; (X kept)
  INX                          ; the next row starts a row on (X = 1)
  BCC .advance                 ; the terminal has wrapped to the next row
.done:
  RTS

.past_eof:
  LDA #'~'
  JSR io_write
.line_done:
  LDA RENDER_ROW               ; no ESC[K on a row the frame's scroll
  SEC                          ; opened (SCROLL_N rows from SCROLL_ROW2):
  SBC SCROLL_ROW2              ; IL left it blank
  CMP SCROLL_N
  BCC .blank
  JSR ansi_clear_line          ; (X kept)
.blank:
  LDX #1                       ; the next row by CR LF
.line_ended:
  INC16 RENDER_LINE16          ; (past the end it stays past the end)
  LDA #0
  STA RENDER_WRAP
  INC RENDER_ROW
  JMP .row_loop

; C=1 if RENDER_ROW reached RENDER_LIMIT or the status bar, else C=0;
; A = RENDER_ROW
.row_check:
  LDA RENDER_ROW
  CMP RENDER_LIMIT
  BCS .check_done
  CMP TEXT_ROWS                ; (RENDER_ROW < RENDER_LIMIT: never 255)
.check_done:
  RTS

; Walk forward to find which file line corresponds to screen row
; RENDER_ROW: from the cursor line for a row at or below its first
; (CURSOR_ROW - WRAP_QUOT, above the view if the line starts there), else
; from the top of the view (VIEW_TOP16, VIEW_TOP_WRAP).  A range repaint
; (RF_RANGE) always walks from the top: it may have made WRAP_QUOT count
; the rows of the range's lines above the cursor's.  Sets RENDER_LINE16
; and RENDER_WRAP.
; Handles wrapped lines (one file line can span multiple screen rows).
; Input: RENDER_ROW = target screen row; CURSOR_ROW and WRAP_QUOT as
;        ensure_cursor_visible set them for the view
; Output: RENDER_LINE16 = file line at that row
;         RENDER_WRAP = wrap row offset within the line
; find_line_from_top_a: the same for row A, always walking from the top
; of the view (CURSOR_ROW and WRAP_QUOT are not used: Ctrl-F)
; Clobbers: A, X, Y, BUF_PTR16, DIV_INPUT16, RENDER_LIMIT
find_line_at_render_row:
  LDA RENDER_FLAG
  CMP #RF_RANGE
  BEQ .from_top
  LDA RENDER_ROW
  CLC
  ADC WRAP_QUOT
  BCS .from_top
  SEC
  SBC CURSOR_ROW           ; the rows below the cursor line's first
  BCC .from_top
  LDX #FILE_LINE16
  LDY #0
  BCS find_line_walk       ; Always (C = 1: no borrow)
.from_top:
  LDA RENDER_ROW
find_line_from_top_a:
  LDX #VIEW_TOP16
  LDY VIEW_TOP_WRAP
find_line_walk:
  STA RENDER_LIMIT         ; remaining rows to skip
  STY RENDER_WRAP
  JSR render_line_from_x   ; RENDER_LINE16 = the line to walk from
  LDA RENDER_LIMIT
  BEQ .found
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
  LDX #0
  STX RENDER_WRAP           ; subsequent lines start at wrap 0
  TAX                       ; (A = RENDER_LIMIT)
  BNE .walk
  RTS
.within_line:
  ; Target is within this line: wrap = base_wrap + remaining
  LDA RENDER_WRAP
  CLC
  ADC RENDER_LIMIT
  STA RENDER_WRAP
.found:
  RTS

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

; Print line characters from BUF_PTR16 + RENDER_COL up to SCREEN_COLS or
; newline.  Control chars: tab as '>' reverse, others (and DEL and bytes
; >= $80, which a terminal would not show in one cell) as '?' reverse; a
; run of them shares one ESC[7m ... ESC[m, which ends in the row.
; Returns RENDER_COL = Y = column after the last char printed.
; Clobbers A, Y (X kept).
render_line_chars_from:
  LDA SCREEN_COLS
  STA RENDER_STOP
; Entry with RENDER_COL and RENDER_STOP (exclusive) set by the caller
render_line_chars_to:
  LDY RENDER_COL
.loop:
  LDA (BUF_PTR16),Y
  CMP #$7F
  BCS .special                 ; DEL or the high bit
  CMP #' '
  BCC .ctrl                    ; a control char or the newline
  JSR io_write
.next:
  INY
.check:
  CPY RENDER_STOP
  BCC .loop
.done:
  STY RENDER_COL
  RTS
.ctrl:
  CMP #'\n'
  BEQ .done
.special:
  ; A run of special chars in reverse video, up to a normal char, the
  ; newline or the stop column
  STY RENDER_COL
  JSR ansi_reverse_video
  LDY RENDER_COL
.rev_loop:
  LDA (BUF_PTR16),Y
  CMP #'\t'
  BEQ .tab
  CMP #$7F
  BCS .unprintable
  CMP #' '
  BCS .rev_end                 ; a normal char
  CMP #'\n'
  BEQ .rev_end
.unprintable:
  LDA #'?'
  .byte $2C                    ; BIT abs ($3EA9, RAM): skip the LDA #'>'
.tab:
  LDA #'>'
  JSR io_write
  INY
  CPY RENDER_STOP
  BCC .rev_loop
.rev_end:
  STY RENDER_COL
  JSR ansi_normal_video
  LDY RENDER_COL               ; (not 0: a special char was printed)
  BNE .check                   ; Always taken

; === Wrap utility functions ===

; Divide CURSOR_COL16 by SCREEN_COLS (as below): X = the cursor's wrap
; row, A = its screen column.  Clobbers DIV_INPUT16
cursor_col_div:
  CP16 CURSOR_COL16, DIV_INPUT16
  ; fall through

; Divide the 16-bit value in DIV_INPUT16 by SCREEN_COLS: repeated
; subtraction below 256 (at most 255 / SCREEN_COLS steps), eight
; shift-and-subtract steps above
; Returns: X = quotient (capped at 255), A = remainder (0 when capped)
; Clobbers DIV_INPUT16
div_mod_screen_cols_16:
  LDX #0
  LDA DIV_INPUT16 + 1
  BNE .long
  LDA DIV_INPUT16
.sub_loop:
  CMP SCREEN_COLS
  BCC .div_done
  SBC SCREEN_COLS            ; (C = 1)
  INX
  BNE .sub_loop              ; Always: the quotient stays below 256
.long:
  ; The quotient fits in 8 bits only if the high byte is below SCREEN_COLS
  CMP SCREEN_COLS
  BCS .cap_255
  ; A = the partial remainder; DIV_INPUT16's low byte shifts the dividend
  ; out and the quotient in
  LDX #8
.div_loop:
  ASL DIV_INPUT16
  ROL
  BCS .sub                   ; A nine-bit remainder: past SCREEN_COLS
  CMP SCREEN_COLS
  BCC .next
.sub:
  SBC SCREEN_COLS            ; (C = 1)
  INC DIV_INPUT16            ; A quotient bit
.next:
  DEX
  BNE .div_loop
  LDX DIV_INPUT16            ; X = quotient
  RTS
.cap_255:
  LDX #$FF
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
; '~' row, which the walks below the last line pass through); any_line_rows:
; the same for line number A/X (low/high)
; Returns: A = rows. Clobbers X, Y, BUF_PTR16, DIV_INPUT16
render_line_rows:
  LDAX16 RENDER_LINE16
any_line_rows:
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
; Returns: A = number of screen rows (1 for empty/short, ceil(len/SCREEN_COLS)
;          for longer, at most 255)
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
  BCC .done
  LDA #$FF                     ; 255 full rows and a partial one: 255,
.done:                         ; as the quotient's cap gives longer ones
  RTS

; Pre-compute screen rows of lines for line-delete scroll.
; Entries: _temp16 walks BUF_TEMP16 lines from the cursor line (0 rows if
; > 255), at most SCREEN_ROWS of them: each takes a row, so they already
; fill any scroll region; _join walks the cursor line plus the A lines
; after it; _at_cursor walks A lines from the cursor line; the base entry
; walks A lines from RENDER_LINE16.
; Output: DELETE_SCREEN_ROWS set (0 on overflow = fall back to file delta);
; compute_delete_screen_rows also returns it in A, with C=1 on overflow
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
  PHA
  JSR set_render_line_to_cursor
  PLA
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
  JSR cursor_col_div
  STX WRAP_QUOT      ; cursor_wrap_row
; The same for the cursor on its line's row WRAP_QUOT (Ctrl-F, Ctrl-B)
ensure_row_visible:

  ; Check if cursor is above view
  ; FILE_LINE16 < VIEW_TOP16?
  CMP16 FILE_LINE16, VIEW_TOP16
  BCC .scroll_up
  BNE .not_above     ; FILE_LINE16 > VIEW_TOP16

  ; FILE_LINE16 == VIEW_TOP16: check wrap row
  LDA WRAP_QUOT
  CMP VIEW_TOP_WRAP
  BCC .scroll_up
  BNE .not_above
  TAX
  BEQ .not_above     ; the top row is the line's first
  ; The cursor is on the top row, which may be past the line's last row
  ; (an insert C or Del can shorten the line under it): as above it

.scroll_up:
  ; Scroll up: the cursor's row becomes the top row.  An insert cursor on
  ; the virtual row past a line that fills its last row (col = len =
  ; k * SCREEN_COLS) shows at the start of the next row, as mid-screen:
  ; the line's last row goes on top and the cursor one row below it
  JSR file_line_rows
  SEC
  SBC #1             ; the line's last row
  CMP WRAP_QUOT      ; C=0: the cursor is past it
  LDA #0
  BCS .set_top       ; the top row
  LDA #1
  BNE .set_top       ; Always taken

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
  CMP TEXT_ROWS
  BCS .need_scroll_down  ; the rows above the cursor line fill the view
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

  ; Check if cursor is below view (CURSOR_ROW >= TEXT_ROWS)
  CMP TEXT_ROWS
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
