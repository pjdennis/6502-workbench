; Render decision engine and viewport scroll optimization.
;
; render_snapshot captures pre-handler state; render_decide compares it
; against post-handler state (plus handler-set RENDER_FLAG) and picks the
; cheapest repaint, including viewport scroll-region optimization when
; VIEW_TOP / VIEW_TOP_WRAP move.  Part of the render engine; see
; render.asm for the drawing primitives and render_scroll.asm for the
; line insert/delete/range scroll paths.
;
; RENDER_FLAG contract.  Before each key main_loop sets RENDER_FLAG = 0,
; INSERT_LINE_COUNT = 0, DELETE_SCREEN_ROWS = 0, RENDER_FROM_COL16 =
; $FFFF (whole line), SHIFT_WRITE = $FF (no ICH/DCH hint) and
; PREV_LINE_ROWS = the cursor line's rows before the key (for u, which
; goes to the line its record names, that line's).  It does not
; reset SCROLL_DELTA, so a flag that reads it needs its producer to set
; it.  ensure_cursor_visible sets CURSOR_ROW and WRAP_QUOT just before
; render_decide.  first_row = the cursor line's first screen row
; (CURSOR_ROW - WRAP_QUOT); "delta" = the change in LINE_COUNT16.
; render_decide:
;   $FF                       -> full redraw
;   viewport moved            -> flag != $0B: scroll the text area and
;                                draw the exposed rows; moved down, from
;                                an edit's first change on (it rides
;                                along: render_scroll_up), moved up, an
;                                edit's cursor line from its change point
;                                if the line count and the rows below it
;                                are unchanged (see .view_changed); else
;                                full
;   line count changed        -> $02-$0A as below, else full
;   BUF_END16 changed or flag -> $0B range repaint, any other as $01
;   nothing                   -> status bar + cursor
;
; Flag  Set by                 Inputs / row assumptions (names: RF_* in
;                              render.asm)
; $01   in-line edits          Cursor line changed in place: redraw it from
;                              RENDER_FROM_COL16 (ICH/DCH hint in SHIFT_NET
;                              and SHIFT_WRITE), scrolling the rows below by
;                              its row change from PREV_LINE_ROWS.
; $03   o O p P, undo dd,      Delta lines inserted at FILE_LINE16, which
;       redo p/P/o/O           starts at CURSOR_ROW: scroll down from there
;                              by their rows.  INSERT_LINE_COUNT != 0:
;                              redraw that many lines, not the scrolled rows.
; $04   undo J                 As $03, but the walk starts after the cursor
;                              line (old rows: PREV_LINE_ROWS).  If the
;                              cursor line and the restored lines take no
;                              more rows than it did, they are redrawn as
;                              one block (render_rows_resized).
;                              INSERT_LINE_COUNT = lines to redraw.
; $05   insert-mode Enter,     Cursor on the last line of the split, which
;       r<Enter> and its redo, began at line FILE_LINE16 - delta, of
;       typed-ahead p (copies  PREV_LINE_ROWS rows before the batch;
;       after the line: split  RENDER_FROM_COL16 = the first column it
;       at its end)            changed.  INSERT_LINE_COUNT: pure-Enter
;                              batch at the line's end $7F, at its start
;                              $FF (see render_enter_split).
; $06   J, insert BS/Del       Lines joined into the cursor line.
;       join, cc, redo J/cc,   DELETE_SCREEN_ROWS = all their rows before the
;       undo r<Enter>          edit (0 = over 255: full redraw).  Rows
;                              shrank: scroll up below the line; same: as
;                              $01; grew: scroll down.
;                              INSERT_LINE_COUNT: 0 = redraw the line,
;                              $FF = pure join at line end (no redraw),
;                              1-254 = pure join at column 0 (scroll from
;                              first_row, no redraw).
; $07   dd and its redo,       Lines deleted from first_row (the next line
;       undo p/P/o/O           moved up into their rows) or below the
;                              cursor line (it kept its rows): the cursor
;                              line is not redrawn.
;                              SCROLL_DELTA = rows deleted ($FF: over
;                              255).  DELETE_SCREEN_ROWS = cursor line rows
;                              above the deleted lines (0 = the deleted
;                              lines began at first_row).
; $08   multi-line x/D         Charwise delete that joined lines:
;       (delete_at_cursor)     SCROLL_DELTA = rows lost (0 = full repaint),
;                              DELETE_SCREEN_ROWS = the cursor line's new
;                              rows (scroll below them, then redraw them).
; $09   multi-line char p/P,   Cursor line split: as $04, PREV_LINE_ROWS =
;       undo of x/D            its rows before the split.
;                              INSERT_LINE_COUNT = lines to redraw.
; $0A   undo Ncc               As $03 with SCROLL_DELTA pre-set (no walk).
; $0B   >> << :N,M> <, undo    INSERT_LINE_COUNT lines changed in place from
;                              the cursor line (the first of the range);
;                              DELETE_SCREEN_ROWS = their rows before.
;                              Needs line count and viewport unchanged.
;                              One line is drawn as $01, with an ICH/DCH
;                              hint at its column 0.
; With the line count unchanged, $03-$0A are treated as $01.


; Capture state snapshot before handler runs
; Saves VIEW_TOP16, VIEW_TOP_WRAP, LINE_COUNT16, BUF_END16, and the
; cursor (snapshot_cursor: also before each typed-ahead press
; dispatch_replay runs)
render_snapshot:
  CP16 VIEW_TOP16, SNAP_VIEW_TOP16
  LDA VIEW_TOP_WRAP
  STA SNAP_VIEW_TOP_WRAP
  CP16 LINE_COUNT16, SNAP_LINE_COUNT16
  CP16 BUF_END16, SNAP_BUF_END16
snapshot_cursor:
  CP16 FILE_LINE16, SNAP_LINE16
  CP16 CURSOR_COL16, SNAP_COL16
  RTS

; Compare post-handler state against the snapshot and dispatch to the
; cheapest repaint (see the summary and the RENDER_FLAG contract above)
render_decide:
  ; If handler already set $FF, skip detection (flags are $00-$0B or $FF)
  BIT RENDER_FLAG
  BMI .full

  ; The view moved (VIEW_TOP16 or VIEW_TOP_WRAP changed): try a scroll
  CMP16 SNAP_VIEW_TOP16, VIEW_TOP16
  BNE .view_moved
  LDA SNAP_VIEW_TOP_WRAP
  CMP VIEW_TOP_WRAP
  BEQ .view_same
.view_moved:
  JMP .view_changed
.view_same:

  ; Check LINE_COUNT16 changed
  CMP16 SNAP_LINE_COUNT16, LINE_COUNT16
  BEQ .line_count_same
  ; LINE_COUNT16 changed - check for scroll optimizations (range compares):
  ; $06/$07/$08 delete-scroll, $03/$04/$05/$09 insert-scroll,
  ; $0A pre-computed insert-scroll, anything else full repaint
  LDA RENDER_FLAG
  CMP #RF_INS
  BCC .full                  ; $00-$02
  CMP #RF_JOIN
  BCC .do_line_insert        ; $03/$04/$05
  CMP #RF_SPLIT
  BCC .line_delete_scroll    ; $06/$07/$08
  BEQ .do_line_insert        ; $09
  CMP #RF_INS_PRESET
  BNE .full                  ; $0B and up
  ; $0A: insert-scroll with SCROLL_DELTA/INSERT_LINE_COUNT pre-set by caller
  JMP .no_disp_adjust
.do_line_insert:
  JMP .line_insert_scroll
.line_count_same:

  ; Check BUF_END16 changed -> current line repaint (at least)
  CMP16 SNAP_BUF_END16, BUF_END16
  BNE .current_line

  ; No snapshot changes detected; use handler's RENDER_FLAG as-is
  LDA RENDER_FLAG
  BNE .current_line       ; $01 from handler -> current line
  JMP render_cursor_and_status

.full:
  JMP render_screen

.current_line:
  LDA RENDER_FLAG
  CMP #RF_RANGE
  BNE .to_current_line
  JMP render_range_repaint

.line_delete_scroll:
  ; LINE_COUNT16 decreased and RENDER_FLAG=$06/$07/$08 (line delete at cursor).
  ; $07/$08: SCROLL_DELTA pre-computed by the handler
  ; (precompute_delete_scroll, delete_at_cursor)
  LDA RENDER_FLAG
  CMP #RF_JOIN
  BNE .delete_check          ; $07/$08
  ; $06: DELETE_SCREEN_ROWS = the joined lines' rows before (old_total;
  ; 0 = over 255: they ran past the bottom row, so all is redrawn)
  LDA DELETE_SCREEN_ROWS
  BEQ .full
  ; Compute the displacement-based delta
  STA SCROLL_DELTA          ; save old_total temporarily
  JSR file_line_rows        ; A = new_total
  STA DELETE_SCREEN_ROWS    ; store new_total for scroll region
  LDA SCROLL_DELTA          ; old_total
  SEC
  SBC DELETE_SCREEN_ROWS    ; old_total - new_total
  BEQ .j_no_scroll          ; same rows
  BCC .j_no_scroll          ; new_total > old_total
  STA SCROLL_DELTA
  BNE .delete_check          ; Always taken (A = delta > 0)
.j_no_scroll:
  ; new_total >= old_total: scroll DOWN to make room for an expanded line
  ; (equal: .j_really_no_scroll repaints just the line)
  JSR ansi_cursor_hide
  ; Scroll region start = first_row + old_total + 1 (1-based)
  LDA SCROLL_DELTA          ; old_total
  JSR row_below_rows
  TAY
  ; Displacement = new_total - old_total
  LDA DELETE_SCREEN_ROWS
  SEC
  SBC SCROLL_DELTA
  BEQ .j_really_no_scroll
  STA SCROLL_DELTA
  ; Scroll region end = SCREEN_ROWS - 1; guarded (skip if region too small)
  LDX #'T'                  ; scroll down
  JSR scroll_region_check   ; (the region's first row in Y)
  LDA DELETE_SCREEN_ROWS     ; new_total (cursor line's screen rows)
  STA SCROLL_DELTA           ; number of rows to render
  JMP render_from_first_row_limited
.j_really_no_scroll:
  LDA DELETE_SCREEN_ROWS     ; new_total
  STA PREV_LINE_ROWS
.to_current_line:
  JMP render_current_line_and_status
.delete_check:
  LDA SCROLL_DELTA
  BEQ .full                  ; 0 (e.g. $08 over 255 old rows): full repaint
  JMP render_line_delete_scroll  ; (clamps the delta to its scroll region)

.line_insert_scroll:
  ; LINE_COUNT16 increased and RENDER_FLAG=$03/$04/$05/$09 (line insert;
  ; $0A skips the walk: it enters at .no_disp_adjust).
  ; Compute file delta = LINE_COUNT16 - SNAP_LINE_COUNT16
  SEC
  LDA LINE_COUNT16
  SBC SNAP_LINE_COUNT16
  STA RENDER_LIMIT           ; file_delta (temp)
  LDA LINE_COUNT16 + 1
  SBC SNAP_LINE_COUNT16 + 1
  BEQ .delta_ok              ; Delta high byte = 0, OK (low byte non-zero:
  JMP .full                  ; the count changed); delta > 255, fall back
.delta_ok:

  ; Walk lines to compute SCROLL_DELTA (screen rows to scroll).
  ; RENDER_FLAG=$05: Enter batch, see render_enter_split
  ; RENDER_FLAG=$03/$04/$09: walk inserted lines at FILE_LINE16
  LDA RENDER_FLAG
  CMP #RF_ENTER
  BNE .do_walk
  JMP render_enter_split
.do_walk:
  JSR set_render_line_to_cursor
  ; $04 (J undo) / $09 (line split): the cursor line and the lines after
  ; it replace one line of PREV_LINE_ROWS rows; walk the lines after it
  LDA RENDER_FLAG
  CMP #RF_INS
  BEQ .no_skip_cursor
  INC16 RENDER_LINE16
.no_skip_cursor:
  LDA #0
  STA SCROLL_DELTA
.walk_ins:
  JSR render_line_rows_step
  DEC RENDER_LIMIT
  BNE .walk_ins

  ; $04/$09: the displacement is the block's rows now (the walked rows
  ; plus the cursor line's, whose wrap count may have changed) minus
  ; the old line's
  LDA RENDER_FLAG
  CMP #RF_INS
  BEQ .no_disp_adjust
  JSR file_line_rows         ; A = new cursor line screen rows
  TAX
  CLC
  ADC SCROLL_DELTA           ; + the lines after it: the block's rows now
  BCS .ins_full              ; over 255 rows
  STA CUR_LINE_ROWS
  SEC
  SBC PREV_LINE_ROWS         ; - the old line's rows = net displacement
  BEQ .disp_not_positive
  BCC .disp_not_positive
  STA SCROLL_DELTA
  ; The region scrolls from below min(new cursor line rows, old rows):
  ; the rows above it are redrawn, and the old line's must all be in it
  TXA
  CMP PREV_LINE_ROWS
  BCS .no_disp_adjust
  STA PREV_LINE_ROWS
  BCC .no_disp_adjust        ; Always taken
.disp_not_positive:
  ; The block takes no more rows than the old line did: redraw it as one
  ; block that shrank from PREV_LINE_ROWS to CUR_LINE_ROWS rows (or kept
  ; them), unless it starts above the view (J undo can leave the cursor
  ; on a later row of a long line): then redraw in full
  JSR set_first_row
  BCC .ins_full
  JMP render_rows_resized
.no_disp_adjust:

  ; Clamp delta to available rows below cursor
  LDA SCROLL_DELTA
  BEQ .ins_full
  JSR clamp_delta_avail
  JMP render_line_insert_scroll
.ins_full:
  JMP .full

.view_changed:
  ; The view moved: scroll the text rows by the rows it moved and draw
  ; the rows that exposes (render_scroll_up and _down), with an edit
  ; (RENDER_FLAG set, or the line count or BUF_END16 changed: then
  ; CUR_LINE_ROWS != 0) drawn after the scroll.  A move up takes an edit
  ; of the cursor line with the line count unchanged (RENDER_ROW = its
  ; first row, CUR_LINE_ROWS = its rows) if its first row is on screen
  ; and the rows below it keep their place: it has the rows it had, or
  ; it reaches the status bar (its cells are then rewritten, as its rows
  ; moved); any other edit sets RENDER_ROW = $FF (full redraw).  A
  ; range repaint, or a line count change with no flag, redraws in full
  CMP16 SNAP_LINE_COUNT16, LINE_COUNT16
  BNE .count_changed
  CMP16 SNAP_BUF_END16, BUF_END16
  BNE .edited
  LDA RENDER_FLAG
  STA RENDER_ROW             ; (not $FF)
  STA CUR_LINE_ROWS          ; 0: no edit
  BEQ .scroll_view
.edited:
  LDA RENDER_FLAG
  CMP #RF_RANGE
  BEQ .ins_full
  JSR cursor_line_first_row  ; RENDER_ROW = its first row, CUR_LINE_ROWS
  BCC .down_only             ; the line starts above the view
  LDA CUR_LINE_ROWS
  CMP PREV_LINE_ROWS
  BEQ .scroll_view           ; the same rows
  CLC
  ADC RENDER_ROW
  BCS .rewrite
  CMP TEXT_ROWS
  BCC .down_only             ; the rows below it would move
.rewrite:
  LDA #$FF
  STA SHIFT_WRITE            ; no ICH/DCH hint
  BNE .scroll_view           ; Always
.count_changed:
  LDA RENDER_FLAG
  BEQ .ins_full
.down_only:
  LDA #$FF
  STA RENDER_ROW             ; only a move down scrolls
  STA CUR_LINE_ROWS          ; (an edit)
.scroll_view:

  ; Determine direction: new > old = scrolled down (scroll up on screen)
  CMP16 VIEW_TOP16, SNAP_VIEW_TOP16
  BEQ .wrap_changed          ; the same line: only VIEW_TOP_WRAP moved
  BCC .scroll_down_detect    ; VIEW_TOP16 < SNAP → scrolled up (screen scrolls down)

  ; Scrolled down: walk from (SNAP_VIEW_TOP16, SNAP_VIEW_TOP_WRAP) to
  ; (VIEW_TOP16, VIEW_TOP_WRAP), summing visible screen rows.  The walk
  ; stops once they fill the text rows: render_scroll_up/down then draw
  ; every row.
  CP16 SNAP_VIEW_TOP16, RENDER_LINE16

  ; First line: visible rows = screen_rows - SNAP_VIEW_TOP_WRAP
  JSR render_line_rows
  SEC
  SBC SNAP_VIEW_TOP_WRAP
  STA SCROLL_DELTA
  INC16 RENDER_LINE16

  ; Walk intermediate lines (full screen_rows each)
.scroll_up_walk:
  CMP16 RENDER_LINE16, VIEW_TOP16
  BEQ .scroll_up_add_wrap
  JSR render_line_rows_step
  BCC .scroll_up_walk

.scroll_up_add_wrap:
  ; Add hidden rows of new top line (VIEW_TOP_WRAP)
  LDA VIEW_TOP_WRAP
  JSR scroll_delta_add
  JMP render_scroll_up

.scroll_down_detect:
  ; Scrolled up: walk from (VIEW_TOP16, VIEW_TOP_WRAP) to
  ; (SNAP_VIEW_TOP16, SNAP_VIEW_TOP_WRAP)
  CP16 VIEW_TOP16, RENDER_LINE16

  ; First line: visible rows = screen_rows - VIEW_TOP_WRAP
  JSR render_line_rows
  SEC
  SBC VIEW_TOP_WRAP
  STA SCROLL_DELTA
  INC16 RENDER_LINE16

.scroll_down_walk:
  CMP16 RENDER_LINE16, SNAP_VIEW_TOP16
  BEQ .scroll_down_add_wrap
  JSR render_line_rows_step
  BCC .scroll_down_walk

.scroll_down_add_wrap:
  ; Add hidden rows of old top line (SNAP_VIEW_TOP_WRAP)
  LDA SNAP_VIEW_TOP_WRAP
  JSR scroll_delta_add
.to_scroll_down:
  JMP render_scroll_down

.wrap_changed:
  ; VIEW_TOP16 same, VIEW_TOP_WRAP different: scroll by the difference
  LDA SNAP_VIEW_TOP_WRAP
  SEC
  SBC VIEW_TOP_WRAP
  STA SCROLL_DELTA
  BCS .to_scroll_down        ; old_wrap > new_wrap: the view moved up
  ; new_wrap > old_wrap: the view moved down
  EOR #$FF
  ADC #1                     ; C=0: new_wrap - old_wrap
  STA SCROLL_DELTA
  ; fall through

; Scroll screen up and render newly exposed bottom rows.
; SCROLL_DELTA = number of rows to scroll (1-255): one that fills the
; text rows sends no scroll and draws them all.
; Content moves up, blanks appear at bottom of scroll region.
; An edit (CUR_LINE_ROWS != 0) rides along: the text before its first
; changed cell is as it was, so every row above that cell's keeps its
; place in the scroll, and the rows from the cell (or from the first
; row exposed, if that comes first) to the bottom are drawn.  A first
; change on the top row or above the view: full redraw (no row keeps
; its place)
render_scroll_up:
  LDA #$FF                     ; no edit: past every row
  LDX CUR_LINE_ROWS
  BEQ .change_row
  ; The first changed cell is in the cursor line at RENDER_FROM_COL16,
  ; or for an Enter batch ($05) in the line it split: the lines it added
  ; (at most 65) lie above the cursor line
  LDX #0
  LDA RENDER_FLAG
  CMP #RF_ENTER
  BNE .rows
  LDA LINE_COUNT16
  SEC
  SBC SNAP_LINE_COUNT16
  TAX
.rows:
  STX RENDER_LIMIT
  JSR rows_to_cursor           ; RENDER_WRAP (C=1: past 255)
  BCS view_full
  JSR change_cell_row          ; A = its row, WRAP_REM = its column
  BCC view_full                ; above the view
  BEQ view_full                ; the top row: no row keeps its place
.change_row:
  STA RENDER_ROW
  JSR ansi_cursor_hide

  ; Scroll region rows 1 to SCREEN_ROWS-1 (excludes status bar), scroll up
  LDA #1
  JSR scroll_up_clamped        ; SCROLL_DELTA = rows exposed at the bottom

  ; Draw from the change, or from the first exposed row (column 0) if
  ; that comes first, to the bottom
  LDA TEXT_ROWS
  SEC
  SBC SCROLL_DELTA             ; the first row exposed
  CMP RENDER_ROW
  BCC .from_exposed
  BEQ .from_exposed
  LDA RENDER_ROW
  BCS .draw                    ; Always
.from_exposed:
  LDX #0
  STX WRAP_REM
.draw:
  LDX #$FF
  STX RENDER_ROW
  JMP draw_rows_from

; Scroll screen down and render newly exposed top rows.
; SCROLL_DELTA = number of rows to scroll, as for render_scroll_up.
; Content moves down, blanks appear at top of scroll region.
; An edit (CUR_LINE_ROWS != 0) is drawn from its change point after the
; scroll (RENDER_ROW = the line's first row; $FF: a full redraw, see
; .view_changed)
render_scroll_down:
  LDX RENDER_ROW
  INX
  BEQ view_full

  JSR ansi_cursor_hide

  ; Scroll region rows 1 to SCREEN_ROWS-1 (excludes status bar), scroll down
  LDA #1
  LDX #'T'                     ; scroll down
  JSR scroll_clamped           ; SCROLL_DELTA = rows exposed at the top
  JSR render_line_keep_delta   ; the edited line (RENDER_ROW, CUR_LINE_ROWS)

  ; Render the newly exposed top SCROLL_DELTA rows (row 0 = the view top)
  LDA #0
  STA RENDER_ROW
  JMP find_and_render
view_full:
  JMP render_screen

; Clamp SCROLL_DELTA to the rows available below the cursor
; (available = TEXT_ROWS - CURSOR_ROW).  Clobbers A
clamp_delta_avail:
  LDA TEXT_ROWS
  SEC
  SBC CURSOR_ROW
  CMP SCROLL_DELTA
  BCS .ok                    ; available >= delta, OK
  STA SCROLL_DELTA           ; clamp delta to available
.ok:
  RTS
