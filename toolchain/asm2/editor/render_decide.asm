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
; PREV_LINE_ROWS = the cursor line's rows before the key.  It does not
; reset SCROLL_DELTA, so a flag that reads it needs its producer to set
; it.  ensure_cursor_visible sets CURSOR_ROW and WRAP_QUOT just before
; render_decide.  first_row = the cursor line's first screen row
; (CURSOR_ROW - WRAP_QUOT); "delta" = the change in LINE_COUNT16.
; render_decide:
;   $FF                       -> full redraw
;   viewport moved            -> line count unchanged and flag != $0B:
;                                scroll the text area, draw only the
;                                exposed rows (flag ignored); else full
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
; $05   insert-mode Enter      Cursor on the last line of the split, which
;                              began at line FILE_LINE16 - delta, of
;                              PREV_LINE_ROWS rows before the batch.
;                              INSERT_LINE_COUNT = 1: pure-Enter batch.
; $06   J, insert BS/Del       Lines joined into the cursor line.
;       join, cc, redo J/cc    DELETE_SCREEN_ROWS = all their rows before the
;                              edit (0 = use delta).  Rows shrank: scroll up
;                              below the line; same: as $01; grew: scroll
;                              down.  INSERT_LINE_COUNT: 0 = redraw the line,
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
;       undo of x/D            its rows before the split (do_char_paste
;                              measures them).
;                              INSERT_LINE_COUNT = lines to redraw.
; $0A   undo Ncc               As $03 with SCROLL_DELTA pre-set (no walk).
; $0B   >> << :N,M> <, undo    INSERT_LINE_COUNT lines changed in place from
;                              the cursor line (the first of the range);
;                              DELETE_SCREEN_ROWS = their rows before.
;                              Needs line count and viewport unchanged.
; With the line count unchanged, $03-$0A are treated as $01.


; Capture state snapshot before handler runs
; Saves VIEW_TOP16, VIEW_TOP_WRAP, LINE_COUNT16, BUF_END16
render_snapshot:
  CP16 VIEW_TOP16, SNAP_VIEW_TOP16
  LDA VIEW_TOP_WRAP
  STA SNAP_VIEW_TOP_WRAP
  CP16 LINE_COUNT16, SNAP_LINE_COUNT16
  CP16 BUF_END16, SNAP_BUF_END16
  RTS

; Compare post-handler state against the snapshot and dispatch to the
; cheapest repaint (see the summary and the RENDER_FLAG contract above)
render_decide:
  ; If handler already set $FF, skip detection (flags are $00-$0B or $FF)
  BIT RENDER_FLAG
  BMI .full

  ; Check VIEW_TOP16 changed -> try scroll optimization before full repaint
  CMP16 SNAP_VIEW_TOP16, VIEW_TOP16
  BEQ .view_same
  JMP .view_changed
.view_same:

  ; Check VIEW_TOP_WRAP changed -> try scroll optimization
  LDA SNAP_VIEW_TOP_WRAP
  CMP VIEW_TOP_WRAP
  BEQ .wrap_same
  ; VIEW_TOP_WRAP changed: require LINE_COUNT unchanged for safety
  CMP16 SNAP_LINE_COUNT16, LINE_COUNT16
  BNE .full
  LDA RENDER_FLAG
  CMP #RF_RANGE
  BEQ .full                  ; range repaint + viewport change: full
  JMP .wrap_changed
.wrap_same:

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
  ; $06: use pre-computed DELETE_SCREEN_ROWS if available, else file delta.
  LDA DELETE_SCREEN_ROWS
  BNE .have_delete_rows
  ; Fall back to file line delta
  SEC
  LDA SNAP_LINE_COUNT16
  SBC LINE_COUNT16
  STA SCROLL_DELTA
  LDA SNAP_LINE_COUNT16 + 1
  SBC LINE_COUNT16 + 1
  BNE .full                  ; Delta > 255, fall back
  BEQ .delete_check          ; Always taken
.have_delete_rows:
  ; A = old_total from pre-computation: compute displacement-based delta
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
  JSR set_first_row
  SEC                       ; +1: 1-based
  ADC SCROLL_DELTA          ; + old_total (still in SCROLL_DELTA)
  STA ANSI_ROW
  ; Displacement = new_total - old_total
  LDA DELETE_SCREEN_ROWS
  SEC
  SBC SCROLL_DELTA
  BEQ .j_really_no_scroll
  STA SCROLL_DELTA
  ; Scroll region end = SCREEN_ROWS - 1; guarded (skip if region too small)
  LDX #'T'                  ; scroll down
  JSR scroll_region_check
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
  ; RENDER_FLAG=$05: Enter(s), compute displacement from wrapped line split
  ; RENDER_FLAG=$03/$04: walk inserted lines at FILE_LINE16
  LDA RENDER_FLAG
  CMP #RF_ENTER
  BNE .do_walk
  ; --- Enter displacement: compare old vs new total screen rows ---
  ; len(line_above), line above = FILE_LINE16 - file_delta
  LDX FILE_LINE16 + 1
  LDA FILE_LINE16
  SEC
  SBC RENDER_LIMIT           ; file_delta
  BCS .above_ok
  DEX
.above_ok:
  JSR buf_get_line_len      ; A/X = len(above)
  STA RENDER_LINE16
  STX RENDER_LINE16 + 1
  ; Get len(cursor_line)
  LDAX16 FILE_LINE16
  JSR buf_get_line_len      ; A/X = len(cursor)
  STA SCROLL_DELTA          ; len_cursor_lo (temp)
  STX DELETE_SCREEN_ROWS    ; len_cursor_hi (temp)
  ; Detect start/end-of-line optimization for pure Enter batches.
  ; INSERT_LINE_COUNT is pre-set to $01 by insert.asm for pure Enter batches
  ; (all bytes are newlines). Mixed batches leave it at $00.
  ; bit 0 = skip content render, bit 1 = include old cursor row in scroll
  LDX #$00                   ; middle split: normal render
  LDA INSERT_LINE_COUNT
  BEQ .save_enter_type       ; Not pure Enter, always need content render
  LDX #$03                   ; start of line: skip render + adjust scroll
  LDA RENDER_LINE16          ; len_above_lo
  ORA RENDER_LINE16 + 1      ; len_above_hi
  BEQ .save_enter_type
  LDX #$01                   ; end of line: skip render only
  LDA SCROLL_DELTA           ; len_cursor_lo
  ORA DELETE_SCREEN_ROWS     ; len_cursor_hi
  BEQ .save_enter_type
  LDX #$00                   ; middle split
.save_enter_type:
  STX INSERT_LINE_COUNT
  ; rows_above = screen_rows(len_above)
  LDAX16 RENDER_LINE16
  JSR line_screen_rows
  STA RENDER_LINE16         ; repurpose: rows_above
  ; rows_cursor = screen_rows(len_cursor)
  LDA SCROLL_DELTA
  LDX DELETE_SCREEN_ROWS
  JSR line_screen_rows      ; A = rows_cursor
  ; new_total = rows_above + rows_cursor + (file_delta - 1) blank lines
  CLC
  ADC RENDER_LINE16          ; A = rows_above + rows_cursor
  CLC
  ADC RENDER_LIMIT           ; + file_delta
  ; displacement = new_total - old_total, the line's rows before the
  ; batch (typed or deleted chars may have changed its length)
  CLC
  SBC PREV_LINE_ROWS         ; - 1 - old_total
  BEQ .enter_no_disp
  BCC .enter_no_disp         ; shrank (BS/Del in the batch)
  STA SCROLL_DELTA
  BNE .no_disp_adjust        ; Always taken (A > 0)
.enter_no_disp:
  JMP .ins_full
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
  PHA
  CLC
  ADC SCROLL_DELTA           ; + the lines after it: the block's rows now
  STA CUR_LINE_ROWS
  SEC
  SBC PREV_LINE_ROWS         ; - the old line's rows = net displacement
  BEQ .disp_not_positive
  BCC .disp_not_positive
  STA SCROLL_DELTA
  ; The region scrolls from below min(new cursor line rows, old rows):
  ; the rows above it are redrawn, and the old line's must all be in it
  PLA
  CMP PREV_LINE_ROWS
  BCS .no_disp_adjust
  STA PREV_LINE_ROWS
  BCC .no_disp_adjust        ; Always taken
.disp_not_positive:
  ; The block takes no more rows than the old line did: redraw it as one
  ; block that shrank from PREV_LINE_ROWS to CUR_LINE_ROWS rows (or kept
  ; them)
  PLA                        ; (new cursor line rows)
  JSR set_first_row
  JMP render_rows_resized
.no_disp_adjust:

  ; Clamp delta to available rows below cursor
  LDA SCROLL_DELTA
  BEQ .ins_full
  JSR clamp_delta_avail
  JMP render_line_insert_scroll
.ins_full:
  JMP .full

.wrap_changed:
  ; VIEW_TOP16 same, VIEW_TOP_WRAP different. LINE_COUNT unchanged.
  ; Scroll amount = |new_wrap - old_wrap|
  LDA SNAP_VIEW_TOP_WRAP
  CMP VIEW_TOP_WRAP
  BCC .wrap_scrolled_down

  ; old_wrap > new_wrap → viewport moved UP → scroll DOWN (new rows at top)
  SBC VIEW_TOP_WRAP          ; C=1 from the compare
  STA SCROLL_DELTA
  ; Safety check: delta + 1 < SCREEN_ROWS
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCS .wrap_full
  JMP render_scroll_down

.wrap_scrolled_down:
  ; new_wrap > old_wrap → viewport moved DOWN → scroll UP (new rows at bottom)
  LDA VIEW_TOP_WRAP
  SEC
  SBC SNAP_VIEW_TOP_WRAP
  STA SCROLL_DELTA
  ; Safety check
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCS .wrap_full
  JMP render_scroll_up

.wrap_full:
  JMP render_screen

.view_changed:
  ; VIEW_TOP16 changed. Try scroll optimization.
  ; Requirement: LINE_COUNT16 unchanged (content not structurally modified)
  CMP16 SNAP_LINE_COUNT16, LINE_COUNT16
  BNE .ins_full
  ; Range repaint can't combine with a viewport change: full repaint
  LDA RENDER_FLAG
  CMP #RF_RANGE
  BEQ .ins_full

  ; Determine direction: new > old = scrolled down (scroll up on screen)
  CMP16 VIEW_TOP16, SNAP_VIEW_TOP16
  BCC .scroll_down_detect    ; VIEW_TOP16 < SNAP → scrolled up (screen scrolls down)

  ; Scrolled down: walk from (SNAP_VIEW_TOP16, SNAP_VIEW_TOP_WRAP) to
  ; (VIEW_TOP16, VIEW_TOP_WRAP), summing visible screen rows.
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
  JMP .scroll_up_walk

.scroll_up_add_wrap:
  ; Add hidden rows of new top line (VIEW_TOP_WRAP)
  LDA SCROLL_DELTA
  CLC
  ADC VIEW_TOP_WRAP
  BCS .scroll_full           ; overflow → full repaint
  STA SCROLL_DELTA

  ; Check delta < SCREEN_ROWS - 1 (else full repaint is better)
  LDA SCROLL_DELTA
  BEQ .scroll_full           ; Delta 0 shouldn't happen, but safety
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCS .scroll_full           ; Delta >= SCREEN_ROWS-1, full repaint
  JMP render_scroll_up

.scroll_full:
  JMP render_screen

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
  JMP .scroll_down_walk

.scroll_down_add_wrap:
  ; Add hidden rows of old top line (SNAP_VIEW_TOP_WRAP)
  LDA SCROLL_DELTA
  CLC
  ADC SNAP_VIEW_TOP_WRAP
  BCS .scroll_full           ; overflow → full repaint
  STA SCROLL_DELTA

  LDA SCROLL_DELTA
  BEQ .scroll_full
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCS .scroll_full
  JMP render_scroll_down

; Scroll screen up and render newly exposed bottom rows.
; SCROLL_DELTA = number of rows to scroll.
; Content moves up, blanks appear at bottom of scroll region.
render_scroll_up:
  JSR ansi_cursor_hide

  ; Scroll region rows 1 to SCREEN_ROWS-1 (excludes status bar), scroll up
  LDA #1
  LDX #'S'                     ; scroll up
  JSR scroll_region_from_a

  ; Render newly exposed bottom rows.
  JMP render_bottom_rows

; Scroll screen down and render newly exposed top rows.
; SCROLL_DELTA = number of rows to scroll.
; Content moves down, blanks appear at top of scroll region.
render_scroll_down:
  JSR ansi_cursor_hide

  ; Scroll region rows 1 to SCREEN_ROWS-1 (excludes status bar), scroll down
  LDA #1
  LDX #'T'                     ; scroll down
  JSR scroll_region_from_a

  ; Render the newly exposed top SCROLL_DELTA rows (row 0 = the view top)
  LDA #0
  STA RENDER_ROW
  JMP find_and_render

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
