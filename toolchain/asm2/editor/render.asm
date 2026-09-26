; Screen rendering engine
;
; Renders the editor view to the terminal using ANSI escape sequences.
; The view shows text lines starting from VIEW_TOP16, with the cursor
; at CURSOR_ROW/CURSOR_COL. The last line is a status bar.
; Long lines wrap visually across multiple screen rows (vi-style).

; Mode constants
MODE_NORMAL  = $00
MODE_INSERT  = $01
MODE_COMMAND = $02

  .zeropage

CURSOR_ROW:     .byte   ; Cursor screen row (0-based, derived from wrap computation)
CURSOR_COL16:   .word   ; Cursor column (0-based, 16-bit for lines >255 chars)
VIEW_TOP16:     .word   ; First visible line number (0-based)
SCREEN_ROWS:    .byte   ; Terminal height
SCREEN_COLS:    .byte   ; Terminal width
TEXT_ROWS:      .byte   ; SCREEN_ROWS - 1: text rows above the status bar
FILE_LINE16:    .word   ; Current file line (0-based)
MODE:           .byte   ; Current mode: MODE_NORMAL, MODE_INSERT, MODE_COMMAND
MODIFIED:       .byte   ; File modified flag ($00 = no, $FF = yes)
READONLY:       .byte   ; Read-only mode ($00 = no, $FF = yes)
RENDER_ROW:     .byte   ; Current row being rendered
RENDER_LINE16:  .word   ; Current file line being rendered
RENDER_COL:     .byte   ; Column counter during rendering
FNAME_PTR16:    .word   ; Pointer to filename string (null-terminated)
RENDER_FLAG:    .byte   ; $FF=full, $01=current line, $02/$06=line delete, $03/$04/$05=line insert, $0B=range repaint. $00=auto
VIEW_TOP_WRAP:  .byte   ; Wrap row offset for first visible line (0 = start of line)
WRAP_QUOT:      .byte   ; Scratch: quotient from CURSOR_COL / SCREEN_COLS
WRAP_REM:       .byte   ; Scratch: remainder from CURSOR_COL % SCREEN_COLS
RENDER_WRAP:    .byte   ; Current wrap row offset during rendering
DIV_INPUT16:    .word   ; Scratch for 16-bit division
PREV_LINE_ROWS: .byte   ; Screen rows the current line occupied before the edit
SNAP_VIEW_TOP16: .word  ; Snapshot of VIEW_TOP16 before handler
SNAP_VIEW_TOP_WRAP: .byte ; Snapshot of VIEW_TOP_WRAP before handler
SNAP_LINE_COUNT16: .word ; Snapshot of LINE_COUNT16 before handler
SNAP_BUF_END16: .word   ; Snapshot of BUF_END16 before handler
SCROLL_DELTA:   .byte   ; Screen rows to scroll (unsigned)
RENDER_LIMIT:   .byte   ; Max rows to render (0=unlimited)
DELETE_SCREEN_ROWS: .byte ; Pre-computed screen rows for line-delete scroll (0=use file delta)
RENDER_FROM_COL16: .word  ; First affected line column for partial render ($FFFF = full line)
INSERT_LINE_COUNT:  .byte ; Override line count for line-insert scroll (0=use file delta)
CUR_LINE_ROWS:  .byte   ; Screen rows the cursor line occupies after the edit
SHIFT_NET:      .byte   ; ICH/DCH hint: cells inserted (+) / deleted (-) at RENDER_FROM_COL16
SHIFT_WRITE:    .byte   ; ICH/DCH hint: new cells written from RENDER_FROM_COL16; $FF = no hint
RENDER_STOP:    .byte   ; render_line_chars_to: stop column (exclusive)
ROW_END:        .byte   ; shift: end of the line's content on the row (exclusive)
ROW_WEND:       .byte   ; shift: end of the cells to write on the row (exclusive)
SHIFT_DCH_COST: .byte   ; shift: byte cost of the DCH route for the row
SHIFT_REM16:    .word   ; shift: line length from the current row's start
SHIFT_IEND16:   .word   ; shift: end of the new cells from the current row's start (signed)

  .code

; Initialize rendering state
render_init:
  .ifdef terminal_mode
  JSR query_terminal_size
  .else
  JSR term_rows
  STA SCREEN_ROWS
  JSR term_cols
  STA SCREEN_COLS
  .endif
  LDX SCREEN_ROWS
  DEX
  STX TEXT_ROWS
  LDA #0
  STA CURSOR_ROW
  STA_LH16 CURSOR_COL16
  STA MODE
  STA MODIFIED
  STA VIEW_TOP_WRAP
  STA_LH16 VIEW_TOP16
  STA_LH16 FILE_LINE16
  RTS

; Full screen redraw
; Renders all visible lines plus status bar, positions cursor
; Handles line wrapping: one file line can span multiple screen rows
render_screen:
  JSR ansi_cursor_hide

  LDA #0
  STA RENDER_ROW
  CP16 VIEW_TOP16, RENDER_LINE16
  LDA VIEW_TOP_WRAP
  STA RENDER_WRAP
  JMP render_from_row

; Point RENDER_LINE16 at the cursor line (RENDER_LINE16 = FILE_LINE16)
; Clobbers A
set_render_line_to_cursor:
  CP16 FILE_LINE16, RENDER_LINE16
  RTS

; RENDER_ROW = the cursor line's first screen row (CURSOR_ROW - WRAP_QUOT)
; Returns C=0 if the line starts above the view.  Clobbers A
set_first_row:
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT
  STA RENDER_ROW
  RTS

; Set RENDER_ROW to the cursor line's first screen row, then point
; RENDER_LINE16 at the cursor line with RENDER_WRAP = 0.  Clobbers A
setup_first_row:
  JSR set_first_row
  ; fall through
; Point RENDER_LINE16 at the cursor line with RENDER_WRAP = 0
setup_render_at_cursor:
  JSR set_render_line_to_cursor
  LDA #0
  STA RENDER_WRAP
  RTS

; Set up RENDER_ROW/RENDER_LINE16/RENDER_WRAP from cursor first_row,
; then fall through to render_from_row.
; Expects ansi_cursor_hide already called.
render_from_first_row_limited:
  JSR setup_first_row
  JMP render_limited_rows

render_from_first_row:
  JSR setup_first_row

; Render rows from RENDER_ROW/RENDER_LINE16/RENDER_WRAP to end of screen
; Expects ansi_cursor_hide already called
; Renders remaining text rows, status bar, positions cursor, shows cursor
render_from_row:
  LDA #$FF
  STA RENDER_LIMIT             ; no row limit: stop at the status bar
  JSR render_rows
  JMP render_finish

; Render just the status line (last row)
render_status_line:
  LDA SCREEN_ROWS
  STA ANSI_ROW
  LDA #1
  STA ANSI_COL
  JSR ansi_move_cursor
  JSR ansi_reverse_video

  ; Print filename
  JSR write_fname

  ; Print read-only indicator
  LDA READONLY
  BEQ .not_readonly
  PRINT_STR str_ro_indicator
.not_readonly:

  ; Print modified flag
  LDA MODIFIED
  BEQ .not_modified
  PRINT_STR str_mod_indicator
.not_modified:

  ; Print separator
  JSR print_separator

  ; Print mode
  LDA MODE
  ASL
  TAX
  LDA mode_strings,X
  STA STR_PTR16
  LDA mode_strings + 1,X
  STA STR_PTR16 + 1
  JSR write_string

  ; Print separator and count (if active) or line/col
  JSR print_separator

  ; Show count/pending-key prefix if active
  LDA COUNT16
  ORA COUNT16 + 1
  BNE .has_count
  LDA LAST_KEY
  BEQ .no_prefix_display
  BNE .has_key                  ; Always taken (A = LAST_KEY)
.has_count:
  CP16 COUNT16, TO_DECIMAL_VALUE16
  JSR print_decimal
  LDA LAST_KEY
  BEQ .done_prefix
.has_key:
  JSR io_write
.done_prefix:
  JSR print_separator
.no_prefix_display:

  ; Line number (1-based)
  CLC
  ADCI16 FILE_LINE16, $0001, TO_DECIMAL_VALUE16
  JSR print_decimal

  LDA #','
  JSR io_write

  ; Column (1-based, 16-bit)
  CLC
  ADCI16 CURSOR_COL16, $0001, TO_DECIMAL_VALUE16
  JSR print_decimal

  ; Print total lines
  LDA #' '
  JSR io_write
  LDA #'/'
  JSR io_write

  CP16 LINE_COUNT16, TO_DECIMAL_VALUE16
  JSR print_decimal

  ; Clear rest of status line and restore normal video
  JSR ansi_clear_line
  JMP ansi_normal_video

; Position cursor at the editing position (wrap-aware)
render_position_cursor:
  LDA CURSOR_ROW
  CLC
  ADC #1           ; ANSI 1-based
  STA ANSI_ROW
  ; Screen column = CURSOR_COL16 % SCREEN_COLS + 1
  CP16 CURSOR_COL16, DIV_INPUT16
  JSR div_mod_screen_cols_16
  ; A = remainder (screen col 0-based)
  CLC
  ADC #1           ; ANSI 1-based
  STA ANSI_COL
  JMP ansi_move_cursor

; Print TO_DECIMAL_VALUE16 in decimal (convert + write)
; Clobbers A, Y
print_decimal:
  JSR to_decimal
  ; fall through
; Write an already-converted TO_DECIMAL_RESULT
print_decimal_result:
  SET16 TO_DECIMAL_RESULT, STR_PTR16
  JMP write_string

; Print the status-line separator " - "
; Clobbers A, Y
print_separator:
  SET16 str_separator, STR_PTR16
  JMP write_string

; Redraw current line's wrap rows plus status bar (for single-line edits)
; If the line's row count changed, the rows below it are scrolled first to
; open or close the difference, so only the line itself (and any rows
; exposed at the bottom) are drawn.
render_current_line_and_status:
  ; WRAP_QUOT = cursor's wrap row (set by ensure_cursor_visible)
  JSR file_line_rows
  STA CUR_LINE_ROWS
  ; First screen row of the line; above the viewport -> full repaint
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT
  BPL .row_visible
  JMP render_screen
.row_visible:
  STA RENDER_ROW
; Entry: RENDER_ROW = first row of a block (cursor line or $0B range) that
; changed from PREV_LINE_ROWS to CUR_LINE_ROWS rows; draw it from its
; change point (RENDER_FROM_COL16) after scrolling the rows below it
render_rows_resized:
  JSR ansi_cursor_hide
  LDA CUR_LINE_ROWS
  CMP PREV_LINE_ROWS
  BEQ .same_rows
  BCC .rows_decreased
  ; --- Rows increased: scroll the rows below the old line end down ---
  SBC PREV_LINE_ROWS            ; C=1 from the compare
  STA SCROLL_DELTA
  LDA RENDER_ROW
  SEC                           ; +1: 1-based
  ADC PREV_LINE_ROWS
  LDX #'T'                      ; scroll down
  JSR scroll_region_from_a
.same_rows:
  JSR render_line_from_change
  JMP render_finish

.rows_decreased:
  ; --- Rows decreased: scroll the rows below the new line end up ---
  LDA PREV_LINE_ROWS
  SEC
  SBC CUR_LINE_ROWS
  STA SCROLL_DELTA
  PHA                           ; displacement, for the exposed bottom rows
  LDA RENDER_ROW
  SEC                           ; +1: 1-based
  ADC CUR_LINE_ROWS
  LDX #'S'                        ; scroll up
  JSR scroll_region_from_a
  JSR render_line_from_change
  PLA
  STA SCROLL_DELTA
  JMP render_bottom_rows_guarded

; Draw the cursor line from its change point (RENDER_FROM_COL16; $FFFF =
; whole line) to its last row, stopping at the status bar.
; Input: RENDER_ROW = the line's first screen row, CUR_LINE_ROWS = its rows
; Clobbers: A, X, Y, BUF_PTR16, RENDER_ROW/WRAP/COL/LIMIT/LINE16,
;           SCROLL_DELTA, WRAP_REM, DIV_INPUT16
render_line_from_change:
  JSR check_from_col           ; X = change wrap row, A = WRAP_REM = from col
  BCC .have_change
  LDX #0
  STX WRAP_REM
.have_change:
  CPX CUR_LINE_ROWS
  BCS .done                    ; change is past the line's last row
  STX RENDER_WRAP
  LDA CUR_LINE_ROWS
  SEC
  SBC RENDER_WRAP
  STA SCROLL_DELTA             ; rows left to draw
  TXA
  CLC
  ADC RENDER_ROW
  STA RENDER_ROW
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCS .done                    ; change row is at or below the status bar
  ; ICH/DCH hint: shift the line's rows instead of rewriting them (rows
  ; opened by the caller's scroll are blank and just get written)
  LDX SHIFT_WRITE
  INX
  BNE render_line_shift        ; $FF = no hint
  LDA WRAP_REM
  BEQ .full_rows
  JSR render_partial_first_row
  DEC SCROLL_DELTA
.full_rows:
  JSR set_render_line_to_cursor
  JMP render_limited_loop
.done:
  RTS

; Draw the cursor line from its change row using the SHIFT_NET /
; SHIFT_WRITE hint: each row's old text is shifted with ICH/DCH and only
; the new cells (and cells carried across a row boundary) are written,
; wherever that is cheaper than resending the row.
; Input: RENDER_ROW/RENDER_WRAP = change row, WRAP_REM = change col,
;        SCROLL_DELTA = rows from the change row to the line's last row
; Clobbers: A, X, Y, BUF_PTR16, RENDER_ROW/WRAP/COL/STOP, SCROLL_DELTA,
;           WRAP_REM, SHIFT_REM16, SHIFT_IEND16
render_line_shift:
  ; SHIFT_REM16 = line length from the row start (row start = c0 - WRAP_REM)
  JSR get_current_line_len
  CLC
  ADC WRAP_REM
  BCC .no_carry
  INX
.no_carry:
  SEC
  SBC RENDER_FROM_COL16
  STA SHIFT_REM16
  TXA
  SBC RENDER_FROM_COL16 + 1
  STA SHIFT_REM16 + 1
  ; SHIFT_IEND16 = end of the new cells, from the row start
  LDA WRAP_REM
  CLC
  ADC SHIFT_WRITE
  STA SHIFT_IEND16
  LDA #0
  ROL
  STA SHIFT_IEND16 + 1
.row:
  JSR shift_row
  DEC SCROLL_DELTA
  BEQ .done
  INC RENDER_ROW
  LDA RENDER_ROW
  CMP TEXT_ROWS
  BCS .done                    ; reached the status bar
  INC RENDER_WRAP
  LDA #0
  STA WRAP_REM                 ; later rows change from column 0
  SEC
  SBC16_8 SHIFT_REM16, SCREEN_COLS, SHIFT_REM16
  SEC
  SBC16_8 SHIFT_IEND16, SCREEN_COLS, SHIFT_IEND16
  JMP .row
.done:
  RTS

; Draw one row of the shifted line: RENDER_ROW/RENDER_WRAP, changed from
; column WRAP_REM, with SHIFT_REM16/SHIFT_IEND16 relative to its start
; Clobbers: A, X, Y, BUF_PTR16, RENDER_COL, RENDER_STOP
shift_row:
  JSR get_current_line_ptr
  LDX RENDER_WRAP
  JSR buf_ptr_advance_x        ; BUF_PTR16 = row start
  ; ROW_END = min(cols, SHIFT_REM16): end of the row's new content
  LDA SHIFT_REM16 + 1
  BNE .row_full
  LDA SHIFT_REM16
  CMP SCREEN_COLS
  BCC .row_end_ok
.row_full:
  LDA SCREEN_COLS
.row_end_ok:
  STA ROW_END
  ; ROW_WEND = SHIFT_IEND16 clamped to 0..255: end of the new cells
  LDA SHIFT_IEND16
  LDX SHIFT_IEND16 + 1
  BEQ .iend_ok
  TXA
  ASL                          ; C = sign
  LDA #$FF
  ADC #0                       ; $FF if above 255, 0 if negative
.iend_ok:
  STA ROW_WEND
  ; Inserting: the first net cells from WRAP_REM are carried in too
  LDA SHIFT_NET
  BMI .clip
  BEQ .clip
  CLC
  ADC WRAP_REM
  BCS .clip_max
  CMP ROW_WEND
  BCC .clip
.clip_max:
  STA ROW_WEND
.clip:
  LDA ROW_WEND
  CMP ROW_END
  BCC .wend_ok
  LDA ROW_END
  STA ROW_WEND
.wend_ok:
  ; X = old text after the new cells that a rewrite would resend
  LDA ROW_END
  SEC
  SBC ROW_WEND
  TAX
  LDA SHIFT_NET
  BMI .delete
  BEQ .write_new               ; net 0: only the new cells change
  CPX #5
  BCC .write_rest              ; short (or no) tail: resending beats ICH
  JSR move_to_partial_pos
  LDA SHIFT_NET
  JSR ansi_insert_chars
  JMP write_row_cells
.write_rest:
  LDA ROW_END
  STA ROW_WEND
.write_new:
  JSR move_to_partial_pos
  JMP write_row_cells

.delete:
  ; DCH d at WRAP_REM, then the cells [TS, ROW_END) pulled up from the
  ; next row, TS = max(ROW_WEND, cols - d). Compare byte costs:
  ;   DCH:     4 + (tail ? 6 + tail : 0)
  ;   rewrite: X + (ROW_END < cols ? 3 : 0)
  LDA SCREEN_COLS
  CLC
  ADC SHIFT_NET                ; cols - d
  BCC .ts_wend                 ; d > cols: no row has a tail start past 0
  CMP ROW_WEND
  BCS .ts_ok
.ts_wend:
  LDA ROW_WEND
.ts_ok:
  STA RENDER_STOP              ; TS (stashed until the tail is written)
  LDA ROW_END
  SEC
  SBC RENDER_STOP
  BCS .tail_len
  LDA #0                       ; ROW_END < TS: no tail
.tail_len:
  TAY                          ; Y = tail cells
  BEQ .dch_cost_base
  CLC
  ADC #6                       ; tail cursor move
.dch_cost_base:
  CLC
  ADC #4                       ; ESC[nP
  STA SHIFT_DCH_COST
  TXA
  LDX ROW_END
  CPX SCREEN_COLS
  BCS .rw_cost_ok
  CLC
  ADC #3                       ; ESC[K
.rw_cost_ok:
  CMP SHIFT_DCH_COST
  BEQ .rewrite
  BCC .rewrite
  ; --- DCH ---
  TYA
  PHA                          ; tail cells
  LDA RENDER_STOP
  PHA                          ; TS
  JSR move_to_partial_pos
  LDA #0
  SEC
  SBC SHIFT_NET                ; d
  JSR ansi_delete_chars
  JSR write_row_cells          ; the new cells, from the cursor at WRAP_REM
  PLA
  STA WRAP_REM                 ; tail start (row done with WRAP_REM)
  PLA
  BNE .write_rest              ; the tail, pulled up from the next row
.dch_done:
  RTS
.rewrite:
  ; Resend the row from WRAP_REM, clearing the rest if it is not full
  JSR .write_rest
  LDA ROW_END
  CMP SCREEN_COLS
  BCS .dch_done
  JMP ansi_clear_line

; Write cells [WRAP_REM, ROW_WEND) of the row at BUF_PTR16 from the
; current cursor position (nothing if the range is empty)
; Clobbers: A, Y, RENDER_COL, RENDER_STOP
write_row_cells:
  LDA WRAP_REM
  CMP ROW_WEND
  BCS .none
  STA RENDER_COL
  LDA ROW_WEND
  STA RENDER_STOP
  JMP render_line_chars_to
.none:
  RTS

; Advance BUF_PTR16 by X * SCREEN_COLS (X wrap rows; X may be 0)
; Clobbers A, X. Preserves Y
buf_ptr_advance_x:
  CPX #0
  BEQ .done
.loop:
  CLC
  LDA BUF_PTR16
  ADC SCREEN_COLS
  STA BUF_PTR16
  BCC .no_carry
  INC BUF_PTR16 + 1
.no_carry:
  DEX
  BNE .loop
.done:
  RTS

; Position the terminal cursor at (RENDER_ROW+1, WRAP_REM+1)
; Clobbers A, X, Y
move_to_partial_pos:
  LDA RENDER_ROW
  CLC
  ADC #1
  STA ANSI_ROW
  LDA WRAP_REM
  CLC
  ADC #1
  STA ANSI_COL
  JMP ansi_move_cursor

; Render the partial first wrap row of the cursor line: position the
; cursor at (RENDER_ROW+1, WRAP_REM+1), render from column WRAP_REM,
; clear the row remainder, then step RENDER_ROW/RENDER_WRAP past it.
; Clobbers A, X, Y, BUF_PTR16, RENDER_COL
render_partial_first_row:
  JSR move_to_partial_pos
  ; Get line pointer, advance to wrap row
  JSR get_current_line_ptr
  LDX RENDER_WRAP
  JSR buf_ptr_advance_x
  LDA WRAP_REM
  STA RENDER_COL
  JSR render_line_chars_from
  LDA RENDER_COL
  CMP SCREEN_COLS
  BCS .partial_no_clear
  JSR ansi_clear_line
.partial_no_clear:
  INC RENDER_ROW
  INC RENDER_WRAP
  RTS
