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
;   viewport moved            -> flag != RF_RANGE: scroll the text area
;                                and draw the exposed rows; moved down,
;                                from an edit's first change on (it rides
;                                along: render_scroll_up), moved up, an
;                                edit's cursor line from its change point
;                                if the line count and the rows below it
;                                are unchanged (see .view_changed); else
;                                full
;   line count changed        -> RF_INS..RF_DEL as below, else full
;   BUF_END16 changed or flag -> RF_RANGE range repaint, any other as
;                                RF_LINE
;   nothing                   -> status bar + cursor
;
; Flag (render.asm)  Set by   Inputs / row assumptions
; $01 RF_LINE   in-line edits  Cursor line changed in place: redraw it from
;                              RENDER_FROM_COL16 (ICH/DCH hint in SHIFT_NET
;                              and SHIFT_WRITE), scrolling the rows below by
;                              its row change from PREV_LINE_ROWS
;                              (render_current_line_and_status).
; $02 RF_INS    o O p P, u of  Delta lines inserted at the cursor line: as
;               dd, redo of p  RF_LINE for a block of those lines that had
;               P o O          no rows before (PREV_LINE_ROWS = 0).
; $03 RF_SPLIT  u of J, char   The cursor line and the delta lines after it
;               p/P over line  replace the line of PREV_LINE_ROWS rows: as
;               breaks, u of   RF_LINE for a block of those lines, from
;               x/D over them, RENDER_FROM_COL16 in the first.
;               u of cc and of
;               dd of every
;               line, redo of
;               typed breaks
; $04 RF_ENTER  insert-mode    Cursor on the last line of the split, which
;               Enter, r<Enter> began at line FILE_LINE16 - delta, of
;               and its redo,  PREV_LINE_ROWS rows before the batch;
;               typed-ahead p  RENDER_FROM_COL16 = the first column it
;               (copies after  changed.  INSERT_LINE_COUNT: pure-Enter
;               the line: a    batch at the line's end $7F, at its start
;               split at its   $FF (see render_enter_split).
;               end)
; $05 RF_JOIN   J, insert      Lines joined into the cursor line: as
;               BS/Del join,   RF_LINE, with PREV_LINE_ROWS =
;               cc, redo J/cc, DELETE_SCREEN_ROWS, all their rows before
;               u of r<Enter>, the edit (0 = over 255: full redraw).
;               x/D over line
;               breaks
;               (delete_at_cursor)
; $06 RF_DEL    dd and its     Lines deleted from first_row (the next line
;               redo, :d, u of moved up into their rows) or below the
;               p/P/o/O, insert cursor line (it kept its rows): the cursor
;               BS/Del joining line is not redrawn.
;               only empty     SCROLL_DELTA = rows deleted ($FF: over
;               lines          255).  DELETE_SCREEN_ROWS = cursor line rows
;                              above the deleted lines (0 = the deleted
;                              lines began at first_row).
; $07 RF_RANGE  >> << :N,M> <, INSERT_LINE_COUNT lines changed in place from
;               their undo     the cursor line (the first of the range);
;                              DELETE_SCREEN_ROWS = their rows before.
;                              Needs line count and viewport unchanged.
;                              One line is drawn as RF_LINE, with an
;                              ICH/DCH hint at its column 0.
; With the line count unchanged, RF_INS..RF_DEL are treated as RF_LINE.


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
  ; If handler already set $FF, skip detection (flags are $00-$07 or $FF)
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
  ; LINE_COUNT16 changed: the line insert, join and delete flags draw
  ; only what moved (range compares), any other redraws in full
  LDA RENDER_FLAG
  CMP #RF_INS
  BCC .full                  ; RF_AUTO, RF_LINE
  CMP #RF_JOIN
  BCC .line_insert           ; RF_INS, RF_SPLIT, RF_ENTER
  BEQ .join
  CMP #RF_DEL
  BNE .full                  ; RF_RANGE
  ; RF_DEL: SCROLL_DELTA rows deleted below the cursor line's first
  ; DELETE_SCREEN_ROWS rows (precompute_delete_scroll): they close up,
  ; and the cursor line is not redrawn
  JSR ansi_cursor_hide
  LDA DELETE_SCREEN_ROWS
  JMP rows_close_below

.line_count_same:
  ; Check BUF_END16 changed -> current line repaint (at least)
  CMP16 SNAP_BUF_END16, BUF_END16
  BNE .current_line

  ; No snapshot changes detected; use handler's RENDER_FLAG as-is
  LDA RENDER_FLAG
  BNE .current_line       ; $01 from handler -> current line
  JMP render_cursor_and_status

.current_line:
  LDA RENDER_FLAG
  CMP #RF_RANGE
  BNE .to_current_line
  JMP render_range_repaint

.join:
  ; RF_JOIN: an in-line edit of the joined lines' rows before
  ; (DELETE_SCREEN_ROWS; 0 = over 255: they ran past the bottom row, so
  ; all is redrawn)
  LDA DELETE_SCREEN_ROWS
  BEQ .full
  STA PREV_LINE_ROWS
.to_current_line:
  JMP render_current_line_and_status
.full:
  JMP render_screen

.line_insert:
  ; The delta = LINE_COUNT16 - SNAP_LINE_COUNT16 lines came in (over
  ; 255, or fewer lines: full)
  SEC
  LDA LINE_COUNT16
  SBC SNAP_LINE_COUNT16
  STA RENDER_LIMIT
  LDA LINE_COUNT16 + 1
  SBC SNAP_LINE_COUNT16 + 1
  BNE .full
  LDA RENDER_FLAG
  CMP #RF_ENTER
  BNE .block
  JMP render_enter_split
.block:
  ; A block of lines from the cursor line's: RF_INS, the delta lines
  ; that went in there (none of their rows were there before); RF_SPLIT,
  ; the cursor line and the delta lines after it, which replace the line
  ; of PREV_LINE_ROWS rows.  Drawn as one line of their rows
  LSR                        ; C = RF_SPLIT
  LDA #0
  BCS .split
  STA PREV_LINE_ROWS
.split:
  ADC RENDER_LIMIT           ; the block's lines (C=1: 256)
  BCS .full
  JSR compute_delete_rows_at_cursor  ; A = their rows (C=1: over 255)
  BCC .rows
  JSR set_first_row          ; Over 255: they fill the rows below the
  BCC .full                  ; block's first if that is on screen, else
  LDA #$FF                   ; full
.rows:
  STA CUR_LINE_ROWS
  JMP render_block_and_status

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
  BEQ .full
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
  BEQ .full
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
; Content moves up, blank rows appear at the bottom of the text rows.
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
  ; or for an Enter batch (RF_ENTER) in the line it split: the lines it
  ; added (at most 65) lie above the cursor line
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

  ; The text rows move up (the status bar stays)
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
; Content moves down, blank rows appear at the top.
; An edit (CUR_LINE_ROWS != 0) is drawn from its change point after the
; scroll (RENDER_ROW = the line's first row; $FF: a full redraw, see
; .view_changed)
render_scroll_down:
  LDX RENDER_ROW
  INX
  BEQ view_full

  JSR ansi_cursor_hide

  ; The text rows move down (the status bar stays)
  LDA #1
  LDX #'L'                     ; scroll down
  JSR scroll_clamped           ; SCROLL_DELTA = rows exposed at the top
  JSR render_line_keep_delta   ; the edited line (RENDER_ROW, CUR_LINE_ROWS)

  ; Render the newly exposed top SCROLL_DELTA rows (row 0 = the view top)
  LDA #0
  STA RENDER_ROW
  JMP find_and_render
view_full:
  JMP render_screen
