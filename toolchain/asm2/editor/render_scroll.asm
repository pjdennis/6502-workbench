; Line-level scroll repaint paths and render utilities.
;
; Scroll-region repaints for line deletion, line insertion, and in-place
; range changes (RENDER_FLAG=$0B), plus the limited-row render loop,
; row/line mapping, wrap math, and cursor visibility.  Part of the
; render engine; see render.asm and render_decide.asm.


; Scroll for line deletion at cursor.
; SCROLL_DELTA = screen rows deleted.  The region from the deleted rows'
; first row to SCREEN_ROWS-1 scrolls up; that first row is first_row =
; CURSOR_ROW - WRAP_QUOT for $02 (dd: the cursor row is refilled) and pure
; newline joins (INSERT_LINE_COUNT 1-254), else first_row +
; DELETE_SCREEN_ROWS (the cursor line's rows are kept: $06/$07/$08).
; Then the changed cursor line and the exposed bottom rows are drawn.
render_line_delete_scroll:
  JSR ansi_cursor_hide
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT              ; first_row (0-based)
  LDX RENDER_FLAG
  CPX #$02
  BEQ .to_one_based
  LDX INSERT_LINE_COUNT
  INX
  CPX #2
  BCS .to_one_based          ; 1-254: pure newline join
  ADC DELETE_SCREEN_ROWS     ; C=0: skip the cursor line's rows
.to_one_based:
  CLC
  ADC #1
  LDX #'S'                     ; scroll up
  JSR scroll_region_from_a

  LDA RENDER_FLAG
  CMP #$07
  BEQ .del_bottom_rows       ; $07 (paste-below undo): cursor line unchanged
  CMP #$02
  BEQ .dd_cursor_row
  ; $06 (J) / $08 (charwise delete): redraw the joined cursor line
  ; (DELETE_SCREEN_ROWS = its rows) from the change point, unless only
  ; newlines were deleted (cursor line content unchanged).  One row (or
  ; 0: the pre-compute overflowed) is drawn like $02's cursor row.
  LDA INSERT_LINE_COUNT
  BNE .del_bottom_rows
  LDA DELETE_SCREEN_ROWS
  CMP #2
  BCC .dd_cursor_row
  STA CUR_LINE_ROWS
  LDA SCROLL_DELTA
  PHA                        ; bottom rows (clobbered by the line render)
  JSR set_first_row
  JSR render_line_from_change
  PLA
  STA SCROLL_DELTA
.del_bottom_rows:
  JMP render_bottom_rows_guarded

.dd_cursor_row:
  ; $02: redraw the cursor row (refilled by the scroll, except at EOF
  ; where the cursor moved up); a cursor on a wrap row redraws to the bottom
  LDA WRAP_QUOT
  BEQ .dd_row0
  JMP render_from_first_row
.dd_row0:
  LDA CURSOR_ROW
  STA RENDER_ROW
  LDA #0
  STA RENDER_WRAP
  ; From column 0, or from RENDER_FROM_COL16's low byte if set: a pair
  ; typed ahead in the same frame (dw then dd) leaves dw's column
  LDX RENDER_FROM_COL16
  TXA
  AND RENDER_FROM_COL16 + 1
  CMP #$FF
  BNE .dd_from_col
  LDX #0                     ; $FFFF: the whole row
.dd_from_col:
  STX WRAP_REM
  JSR render_partial_first_row
  JMP render_bottom_rows_guarded

; Scroll for line insertion at cursor.
; SCROLL_DELTA = lines inserted. CURSOR_ROW = screen row of insertion.
; Scrolls rows from cursor down, renders newly inserted rows at cursor.
render_line_insert_scroll:
  JSR ansi_cursor_hide

  ; Set scroll region start (1-based) to SCREEN_ROWS-1 (1-based)
  ; RENDER_FLAG=$03: from CURSOR_ROW+1 (includes cursor row)
  ; RENDER_FLAG=$05: from old cursor row+1 = CURSOR_ROW-SCROLL_DELTA+2
  ; RENDER_FLAG=$04/$09: skip cursor line rows
  ;   first_row = CURSOR_ROW - WRAP_QUOT
  ;   scroll_start = first_row + PREV_LINE_ROWS + 1 (1-based)
  LDA RENDER_FLAG
  CMP #$04
  BEQ .scroll_skip_cursor_ins
  CMP #$09
  BEQ .scroll_skip_cursor_ins
  CMP #$05
  BEQ .scroll_at_enter
  BNE .scroll_at_cursor
.scroll_skip_cursor_ins:
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT          ; first_row (0-based)
  CLC
  ADC PREV_LINE_ROWS     ; past end of cursor line (0-based)
  JMP .to_one_based
.scroll_at_enter:
  ; For start-of-line Enter (bit 1 set): include old cursor row in scroll
  ; scroll_start = CURSOR_ROW + 1 - SCROLL_DELTA (1-based)
  ; Otherwise: scroll_start = CURSOR_ROW + 2 - SCROLL_DELTA (1-based)
  LDA INSERT_LINE_COUNT
  AND #$02
  BNE .enter_start_scroll
  LDA CURSOR_ROW
  SEC
  SBC SCROLL_DELTA
  CLC
  ADC #2
  JMP .set_scroll_start
.enter_start_scroll:
  LDA CURSOR_ROW
  SEC
  SBC SCROLL_DELTA
  JMP .to_one_based
.scroll_at_cursor:
  LDA CURSOR_ROW
.to_one_based:
  CLC
  ADC #1           ; Convert to 1-based
.set_scroll_start:
  LDX #'T'               ; scroll down
  JSR scroll_region_from_a

  ; For Enter ($05): render split line + blank lines + cursor line
  LDA RENDER_FLAG
  CMP #$05
  BNE .no_enter_render
  ; If start/end-of-line Enter, scroll handled everything - just update status
  LDA INSERT_LINE_COUNT
  AND #$01
  BNE .enter_status_only
  ; Render SCROLL_DELTA + 1 rows starting at old cursor row
  LDA CURSOR_ROW
  SEC
  SBC SCROLL_DELTA
  STA RENDER_ROW
  INC SCROLL_DELTA           ; +1 for the split line row
  JMP find_and_render
.enter_status_only:
  JMP render_finish
.no_enter_render:

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
  DEC INSERT_LINE_COUNT
  BNE .walk_repaint

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
  LDA SCREEN_ROWS
  SEC
  SBC #1
  SEC
  SBC RENDER_ROW
  STA SCROLL_DELTA
  JSR ansi_cursor_hide
  JMP render_from_first_row_limited
.rr_full:
  JMP render_screen

; === Scroll-region helpers ===
; Set scroll region [A .. SCREEN_ROWS-1] (A = 1-based start row) and
; scroll it by SCROLL_DELTA rows: X = 'S' scrolls up, X = 'T' down.
; Skips (C=0) if the region is a single row or invalid; C=1 after a
; scroll.  Clobbers A, Y (X preserved).
scroll_region_from_a:
  STA ANSI_ROW
  ; fall through (entry with ANSI_ROW already set)
scroll_region_check:
  LDA SCREEN_ROWS
  SEC
  SBC #1
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

; Repaint the newly exposed bottom SCROLL_DELTA rows:
; RENDER_ROW = SCREEN_ROWS - 1 - SCROLL_DELTA, then find the file line
; there and render to the bottom.  The guarded entry skips the content
; repaint (status + cursor only) when RENDER_ROW <= CURSOR_ROW (those
; rows were already rendered by the caller).
render_bottom_rows_guarded:
  LDA SCREEN_ROWS
  SEC
  SBC #1
  SEC
  SBC SCROLL_DELTA
  STA RENDER_ROW
  CMP CURSOR_ROW
  BCC render_finish            ; RENDER_ROW < CURSOR_ROW (safety)
  BEQ render_finish            ; RENDER_ROW = CURSOR_ROW (already rendered)
  ; fall through (recomputes the same RENDER_ROW)
render_bottom_rows:
  LDA SCREEN_ROWS
  SEC
  SBC #1
  SEC
  SBC SCROLL_DELTA
  STA RENDER_ROW
find_and_render:
  JSR find_line_at_render_row
  ; fall through to render_limited_rows

; Render limited rows: renders SCROLL_DELTA rows starting at
; RENDER_ROW/RENDER_LINE16/RENDER_WRAP, then draws status bar + cursor.
render_limited_rows:
  JSR render_limited_loop
; Frame epilogue: status bar, cursor, show, flush (shared tail)
render_finish:
  JSR render_status_line
  JSR render_position_cursor
  JSR ansi_cursor_show
  JMP io_flush

; Render loop only: renders SCROLL_DELTA rows starting at
; RENDER_ROW/RENDER_LINE16/RENDER_WRAP, then returns.
; Caller must handle status bar, cursor positioning, etc.
render_limited_loop:
  LDA RENDER_ROW
  CLC
  ADC SCROLL_DELTA
  STA RENDER_LIMIT             ; stop at this row
; Render rows from RENDER_ROW/RENDER_LINE16/RENDER_WRAP up to (not
; including) row RENDER_LIMIT or the status bar.  A wrapped line's
; continuation rows are reached by the terminal's auto-wrap (the row
; before was written full width), so only a line's first row (and the
; first row drawn) positions the cursor.
render_rows:
.row_loop:
  JSR .row_check               ; A = RENDER_ROW + 1 (ANSI row)
  BCS .done
  STA ANSI_ROW
  LDA #1
  STA ANSI_COL
  JSR ansi_move_cursor
.row:
  ; Check if line exists
  CMP16 RENDER_LINE16, LINE_COUNT16
  BCS .past_eof
  ; Line pointer advanced by RENDER_WRAP * SCREEN_COLS
  LDAX16 RENDER_LINE16
  JSR buf_get_line_ptr
  LDX RENDER_WRAP
  JSR buf_ptr_advance_x
  JSR render_line_chars
  ; A full row may continue on the next wrap row (unless at a newline)
  LDA RENDER_COL
  CMP SCREEN_COLS
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

; C=1 if RENDER_ROW reached RENDER_LIMIT or the status bar, else C=0
; with A = RENDER_ROW + 1
.row_check:
  LDA RENDER_ROW
  CMP RENDER_LIMIT
  BCS .check_done
  ADC #1                       ; C=0
  CMP SCREEN_ROWS
.check_done:
  RTS

; Walk from VIEW_TOP16 forward to find which file line corresponds
; to screen row RENDER_ROW. Sets RENDER_LINE16 and RENDER_WRAP.
; Handles wrapped lines (one file line can span multiple screen rows).
; Input: RENDER_ROW = target screen row
; Output: RENDER_LINE16 = file line at that row
;         RENDER_WRAP = wrap row offset within the line
; Clobbers: A, X
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
  BEQ .found
  JMP .walk
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

; Print line characters from BUF_PTR16 up to SCREEN_COLS or newline
; Control chars: tab as '>' reverse, others as '.' reverse. Clobbers A, Y.
render_line_chars:
  LDA #0
  STA RENDER_COL
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
  JMP .next
.ctrl:
  CMP #'\t'
  BNE .unprintable
  LDA #'>'
  JMP .rev_char
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
.next:
  INY
  INC RENDER_COL
  LDA RENDER_COL
  CMP RENDER_STOP
  BCC .loop
.done:
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
  LDA DIV_INPUT16            ; Reload low byte for subtraction
.can_sub:
  SEC
  LDA DIV_INPUT16
  SBC SCREEN_COLS
  STA DIV_INPUT16
  LDA DIV_INPUT16 + 1
  SBC #0
  STA DIV_INPUT16 + 1
  INX
  BEQ .cap_255               ; Quotient wrapped to 0, cap at 255
  JMP .div_loop
.cap_255:
  LDX #$FF
  LDA #0                     ; Remainder doesn't matter at cap
.div_done:
  RTS

; Walk step for the scroll-delta walks: add the screen rows of the line
; at RENDER_LINE16 to SCROLL_DELTA, then advance RENDER_LINE16.
; Clobbers A, X
render_line_rows_step:
  JSR render_line_rows
  CLC
  ADC SCROLL_DELTA
  STA SCROLL_DELTA
  INC16 RENDER_LINE16
  RTS

; Screen rows of the line at RENDER_LINE16
; Returns: A = rows. Clobbers X
render_line_rows:
  LDAX16 RENDER_LINE16
  JMP get_len_rows

; Screen rows of the line at FILE_LINE16
; Returns: A = rows. Clobbers X
file_line_rows:
  LDAX16 FILE_LINE16
  ; fall through
get_len_rows:
  JSR buf_get_line_len
  JMP line_screen_rows

; Compute number of screen rows a line occupies
; Input: A/X = 16-bit line length (A=low, X=high)
; Returns: A = number of screen rows (1 for empty/short, ceil(len/SCREEN_COLS) for longer)
; Clobbers: X
line_screen_rows:
  STA DIV_INPUT16
  STX DIV_INPUT16 + 1
  ORA DIV_INPUT16 + 1
  BNE .not_empty
  LDA #1
  RTS
.not_empty:
  JSR div_mod_screen_cols_16
  ; X = quotient, A = remainder
  STA WRAP_REM
  TXA              ; A = quotient
  LDX WRAP_REM
  CPX #0
  BEQ .exact
  CLC
  ADC #1           ; Add 1 for partial last row
.exact:
  RTS

; Pre-compute screen rows of lines for line-delete scroll.
; Entries: _temp16 walks BUF_TEMP16 lines from the cursor line (0 rows if
; > 255); _join walks the cursor line plus the A lines after it; _at_cursor
; walks A lines from the cursor line; the base entry walks A lines from
; RENDER_LINE16.
; Output: DELETE_SCREEN_ROWS set (0 on overflow = fall back to file delta)
; Clobbers: A, X, Y, RENDER_LIMIT, RENDER_LINE16, BUF_PTR16, DIV_INPUT16
compute_delete_rows_temp16:
  LDA BUF_TEMP16
  LDX BUF_TEMP16 + 1
  BNE cdsr_overflow            ; > 255 lines
  BEQ compute_delete_rows_at_cursor  ; Always taken
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
  STA WRAP_REM       ; not used here but available

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
  ; Scroll up: VIEW_TOP16 = FILE_LINE16, VIEW_TOP_WRAP = cursor_wrap_row
  CP16 FILE_LINE16, VIEW_TOP16
  LDA WRAP_QUOT
  STA VIEW_TOP_WRAP
  LDA #0
  STA CURSOR_ROW
  RTS

.not_above:
  ; Walk from (VIEW_TOP16, VIEW_TOP_WRAP) to (FILE_LINE16, cursor_wrap_row)
  ; summing screen rows to compute CURSOR_ROW

  ; Start with screen_row = 0
  LDA #0
  STA CURSOR_ROW

  ; current_line = VIEW_TOP16
  CP16 VIEW_TOP16, RENDER_LINE16

  ; If VIEW_TOP16 == FILE_LINE16, just compute cursor_wrap - VIEW_TOP_WRAP
  CMP16 RENDER_LINE16, FILE_LINE16
  BNE .walk_top

  ; Same line
  SEC
  LDA WRAP_QUOT
  SBC VIEW_TOP_WRAP
  STA CURSOR_ROW
  JMP .check_below

.walk_top:
  ; Add screen rows for VIEW_TOP16 line (minus VIEW_TOP_WRAP)
  JSR render_line_rows
  ; A = total screen rows for this line
  SEC
  SBC VIEW_TOP_WRAP
  STA CURSOR_ROW

  ; Advance to next line
  INC16 RENDER_LINE16

.walk_loop:
  ; Are we at FILE_LINE16?
  CMP16 RENDER_LINE16, FILE_LINE16
  BEQ .at_cursor

  ; Add screen rows for this intermediate line
  JSR render_line_rows
  CLC
  ADC CURSOR_ROW
  BCS .need_scroll_down  ; 8-bit overflow: cursor far below screen
  STA CURSOR_ROW

  INC16 RENDER_LINE16
  JMP .walk_loop

.at_cursor:
  ; Add cursor's wrap row within FILE_LINE16
  LDA CURSOR_ROW
  CLC
  ADC WRAP_QUOT
  BCS .need_scroll_down  ; 8-bit overflow
  STA CURSOR_ROW

.check_below:
  ; Check if cursor is below view (CURSOR_ROW >= SCREEN_ROWS - 1)
  LDA CURSOR_ROW
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCC .visible

.need_scroll_down:
  ; Cursor is below visible area
  ; Walk backward from FILE_LINE16 to find correct VIEW_TOP16

  LDA SCREEN_ROWS
  SEC
  SBC #2
  STA CURSOR_ROW      ; Target: cursor at row SCREEN_ROWS - 2
  STA RENDER_ROW      ; Rows to walk back

  ; Start from cursor position
  CP16 FILE_LINE16, VIEW_TOP16
  LDA WRAP_QUOT
  STA VIEW_TOP_WRAP

.walk_back:
  LDA RENDER_ROW
  BEQ .visible

  ; Can we go back within current line?
  LDA VIEW_TOP_WRAP
  BEQ .prev_line
  DEC VIEW_TOP_WRAP
  DEC RENDER_ROW
  JMP .walk_back

.prev_line:
  TST16 VIEW_TOP16
  BEQ .at_top
  DEC16 VIEW_TOP16
  LDAX16 VIEW_TOP16
  JSR buf_get_line_len
  JSR line_screen_rows
  SEC
  SBC #1
  STA VIEW_TOP_WRAP
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

; === String constants ===
str_ro_indicator:  .asciiz " [RO]"
str_mod_indicator: .asciiz " [+]"
str_separator:     .asciiz " - "
str_normal:        .asciiz "NORMAL"
str_insert:        .asciiz "INSERT"
str_command:       .asciiz "COMMAND"
mode_strings:      .word str_normal, str_insert, str_command
