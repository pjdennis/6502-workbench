; Render decision engine and viewport scroll optimization.
;
; render_snapshot captures pre-handler state; render_decide compares it
; against post-handler state (plus handler-set RENDER_FLAG) and picks the
; cheapest repaint, including viewport scroll-region optimization when
; VIEW_TOP / VIEW_TOP_WRAP move.  Part of the render engine; see
; render.asm for the drawing primitives and render_scroll.asm for the
; line insert/delete/range scroll paths.


; Capture state snapshot before handler runs
; Saves VIEW_TOP16, VIEW_TOP_WRAP, LINE_COUNT16, BUF_END16
render_snapshot:
  CP16 VIEW_TOP16, SNAP_VIEW_TOP16
  LDA VIEW_TOP_WRAP
  STA SNAP_VIEW_TOP_WRAP
  CP16 LINE_COUNT16, SNAP_LINE_COUNT16
  CP16 BUF_END16, SNAP_BUF_END16
  RTS

; Compare post-handler state against snapshot to decide render level
; Takes the max of handler-set RENDER_FLAG and snapshot-inferred level.
; Then dispatches to the appropriate render routine.
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
  CMP #$0B
  BEQ .full                  ; range repaint + viewport change: full
  JMP .wrap_changed
.wrap_same:

  ; Check LINE_COUNT16 changed
  CMP16 SNAP_LINE_COUNT16, LINE_COUNT16
  BEQ .line_count_same
  ; LINE_COUNT16 changed - check for scroll optimizations (range compares):
  ; $02/$06/$07/$08 delete-scroll, $03/$04/$05/$09 insert-scroll,
  ; $0A pre-computed insert-scroll, anything else full repaint
  LDA RENDER_FLAG
  CMP #$02
  BCC .full                  ; $00/$01
  BEQ .line_delete_scroll    ; $02
  CMP #$06
  BCC .do_line_insert        ; $03/$04/$05
  CMP #$09
  BCC .line_delete_scroll    ; $06/$07/$08
  BEQ .do_line_insert        ; $09
  CMP #$0A
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
  CMP #$0B
  BNE .to_current_line
  JMP render_range_repaint

.line_delete_scroll:
  ; LINE_COUNT16 decreased and RENDER_FLAG=$02/$06/$07/$08 (line delete at cursor).
  ; $08: SCROLL_DELTA pre-computed by delete_at_cursor, DELETE_SCREEN_ROWS = new cursor rows
  LDA RENDER_FLAG
  CMP #$08
  BEQ .delete_check          ; $08: SCROLL_DELTA pre-computed
  CMP #$07
  BNE .not_07
  ; $07: use SCROLL_DELTA if pre-computed, else file delta
  LDA SCROLL_DELTA
  BNE .delete_check
  BEQ .file_delta_scroll
.not_07:
  ; Use pre-computed DELETE_SCREEN_ROWS if available, else file delta.
  LDA DELETE_SCREEN_ROWS
  BNE .have_delete_rows
.file_delta_scroll:
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
  ; RENDER_FLAG=$06 (J): compute displacement-based delta
  LDX RENDER_FLAG
  CPX #$06
  BNE .dd_delete_rows
  ; --- J path: A = old_total from pre-computation ---
  STA SCROLL_DELTA          ; save old_total temporarily
  JSR file_line_rows        ; A = new_total
  STA DELETE_SCREEN_ROWS    ; store new_total for scroll region
  LDA SCROLL_DELTA          ; old_total
  SEC
  SBC DELETE_SCREEN_ROWS    ; old_total - new_total
  BEQ .j_no_scroll
  BCC .j_no_scroll          ; underflow safety
  STA SCROLL_DELTA
  BNE .delete_check          ; Always taken (A = delta > 0)
.j_no_scroll:
  ; new_total > old_total: scroll DOWN to make room for expanded line
  JSR ansi_cursor_hide
  ; Scroll region start = first_row + old_total + 1 (1-based)
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT
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
.dd_delete_rows:
  STA SCROLL_DELTA
.delete_check:
  LDA SCROLL_DELTA
  BEQ .full                  ; Delta 0, shouldn't happen

  ; Clamp delta to available rows below cursor
  JSR clamp_delta_avail
  JMP render_line_delete_scroll

.line_insert_scroll:
  ; LINE_COUNT16 increased and RENDER_FLAG=$03 (line insert at cursor).
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
  CMP #$05
  BNE .do_walk
  ; --- Enter displacement: compare old vs new total screen rows ---
  ; Save file_delta (RENDER_LIMIT will be overwritten with old_total)
  LDA RENDER_LIMIT
  PHA
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
  ; old_length = len_above + len_cursor
  LDA SCROLL_DELTA           ; reload len_cursor_lo
  CLC
  ADC RENDER_LINE16
  TAY
  LDA DELETE_SCREEN_ROWS
  ADC RENDER_LINE16 + 1
  TAX
  TYA                       ; A/X = old_length
  JSR line_screen_rows      ; A = old_total
  STA RENDER_LIMIT          ; save old_total
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
  STA SCROLL_DELTA           ; temp save
  PLA                        ; file_delta
  SEC
  SBC #1                     ; file_delta - 1 (blank lines)
  CLC
  ADC SCROLL_DELTA           ; A = rows_above + rows_cursor + file_delta - 1
  ; displacement = new_total - old_total
  SEC
  SBC RENDER_LIMIT
  BEQ .enter_no_disp
  BCC .enter_no_disp         ; safety: can't be negative
  STA SCROLL_DELTA
  JMP .walk_done
.enter_no_disp:
  JMP .ins_full
.do_walk:
  JSR set_render_line_to_cursor
  ; For $04 (J undo), skip cursor line — only count restored lines
  LDA RENDER_FLAG
  CMP #$04
  BNE .no_skip_cursor
  INC16 RENDER_LINE16
.no_skip_cursor:
  LDA #0
  STA SCROLL_DELTA
.walk_ins:
  JSR render_line_rows_step
  DEC RENDER_LIMIT
  BNE .walk_ins
.walk_done:

  ; For $04 (J undo), adjust SCROLL_DELTA for cursor line size change
  ; The cursor line may have changed wrap count (e.g., joined 2-row line
  ; becomes unwrapped 1-row line after undo), so net displacement differs
  ; from the raw sum of restored line rows.
  LDA RENDER_FLAG
  CMP #$04
  BNE .no_disp_adjust
  JSR file_line_rows         ; A = new cursor line screen rows
  PHA
  CLC
  ADC SCROLL_DELTA           ; + restored rows
  SEC
  SBC PREV_LINE_ROWS         ; - old cursor rows = net displacement
  BEQ .disp_exact_zero
  BCC .disp_negative          ; underflow -> need scroll UP
  STA SCROLL_DELTA
  PLA
  STA PREV_LINE_ROWS
  JMP .no_disp_adjust
.disp_exact_zero:
  PLA                        ; new_cursor_rows (discard value)
  LDA PREV_LINE_ROWS         ; old cursor rows = total rows to render
  STA SCROLL_DELTA
  JSR ansi_cursor_hide
  JMP render_from_first_row_limited
.disp_negative:
  ; Old cursor line was taller than restored lines + new cursor combined.
  ; Scroll UP to fill freed rows.
  ; Stack: new_cursor_rows. SCROLL_DELTA = restored rows. PREV_LINE_ROWS = old cursor rows.
  PLA                        ; new_cursor_rows
  STA RENDER_LIMIT           ; temp save
  ; Reverse delta = PREV_LINE_ROWS - new_cursor_rows - SCROLL_DELTA
  LDA PREV_LINE_ROWS
  SEC
  SBC RENDER_LIMIT
  SEC
  SBC SCROLL_DELTA
  BEQ .ins_full
  STA SCROLL_DELTA           ; reverse_delta
  JSR ansi_cursor_hide
  ; new_content_rows = PREV_LINE_ROWS - reverse_delta
  ; Scroll region start = first_row + new_content_rows + 1 (1-based)
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT
  SEC                        ; +1: 1-based
  ADC PREV_LINE_ROWS
  SEC
  SBC SCROLL_DELTA           ; adjust: start after new content, not old
  LDX #'S'                     ; scroll up
  JSR scroll_region_from_a
  BCC .disp_neg_skip_scroll  ; region too small: no scroll happened
  ; Render new content area from first_row, then bottom exposed rows
  LDA SCROLL_DELTA
  PHA                        ; save reverse_delta for bottom rows
  LDA PREV_LINE_ROWS
  SEC
  SBC SCROLL_DELTA           ; new_content_rows
  STA SCROLL_DELTA
  JSR setup_first_row
  JSR render_limited_loop
  ; Render bottom exposed rows
  PLA
  STA SCROLL_DELTA           ; reverse_delta = bottom rows
  JMP render_bottom_rows
.disp_neg_skip_scroll:
  JMP render_from_first_row
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
  CMP #$0B
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

  ; Render newly exposed top rows.
  ; RENDER_ROW = 0, RENDER_LINE16 = VIEW_TOP16, RENDER_WRAP = VIEW_TOP_WRAP
  LDA #0
  STA RENDER_ROW
  LDA VIEW_TOP_WRAP
  STA RENDER_WRAP
  LDA SCROLL_DELTA
  STA RENDER_LIMIT
  CP16 VIEW_TOP16, RENDER_LINE16
  JMP render_limited_rows

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
