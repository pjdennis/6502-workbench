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
PREV_LINE_FULL: .byte   ; Non-zero if old line's last row was full (len % cols == 0)
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

; Set RENDER_ROW to the cursor line's first screen row, then point
; RENDER_LINE16 at the cursor line with RENDER_WRAP = 0.  Clobbers A
setup_first_row:
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT
  STA RENDER_ROW
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
.row_loop:
  ; Position cursor at start of this row
  LDA RENDER_ROW
  CLC
  ADC #1           ; ANSI rows are 1-based
  STA ANSI_ROW
  LDA #1
  STA ANSI_COL
  JSR ansi_move_cursor
.row_no_cursor:

  ; Check if this is the status line row (last row)
  LDA RENDER_ROW
  CLC
  ADC #1
  CMP SCREEN_ROWS
  BCS .row_done    ; At or past last row = done with text

  ; Check if line exists
  CMP16 RENDER_LINE16, LINE_COUNT16
  BCS .past_eof

  ; Get line pointer
  LDAX16 RENDER_LINE16
  JSR buf_get_line_ptr

  ; Advance BUF_PTR16 by RENDER_WRAP * SCREEN_COLS
  LDX RENDER_WRAP
  JSR buf_ptr_advance_x

  JSR render_line_chars

  ; Check if the line has more wrap rows
  ; After render_line_chars, if it printed exactly SCREEN_COLS chars
  ; (RENDER_COL == SCREEN_COLS), check if there are more chars to wrap
  ; Note: must check before ansi_clear_line which clobbers Y
  LDA RENDER_COL
  CMP SCREEN_COLS
  BNE .line_done
  ; Check if next char is newline (line boundary at exact multiple)
  LDA (BUF_PTR16),Y
  CMP #'\n'
  BEQ .line_ended
  ; More wrap rows remain (row is full, no clear needed)
  INC RENDER_WRAP
  INC RENDER_ROW
  JMP .row_no_cursor

.line_done:
  ; Row not full (RENDER_COL < SCREEN_COLS) - clear remainder
  JSR ansi_clear_line

.line_ended:
  ; Line ended (newline or fewer than SCREEN_COLS chars)
  ; Advance to next file line
  INC RENDER_ROW
  INC16 RENDER_LINE16
  LDA #0
  STA RENDER_WRAP
  JMP .row_loop

.past_eof:
  ; Draw tilde for lines past end of file
  LDA #'~'
  JSR io_write
  JSR ansi_clear_line

  INC RENDER_ROW
  JMP .row_loop

.row_done:
  ; Status line, cursor, show, flush
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
  BNE .has_pending_no_count
  JMP .no_prefix_display
.has_count:
  CP16 COUNT16, TO_DECIMAL_VALUE16
  JSR print_decimal
.has_pending_no_count:
  LDA LAST_KEY
  BEQ .done_prefix
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
  ; Compute cursor's wrap row from CURSOR_COL16
  CP16 CURSOR_COL16, DIV_INPUT16
  JSR div_mod_screen_cols_16
  STX WRAP_QUOT
  JSR get_current_line_len
  JSR line_screen_rows
  STA CUR_LINE_ROWS
  ; First screen row of the line; above the viewport -> full repaint
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT
  BPL .row_visible
  JMP render_screen
.row_visible:
  STA RENDER_ROW
  JSR ansi_cursor_hide
  LDA CUR_LINE_ROWS
  CMP PREV_LINE_ROWS
  BEQ .same_rows
  BCC .rows_decreased
  ; --- Rows increased: scroll the rows below the old line end down ---
  SEC
  SBC PREV_LINE_ROWS
  STA SCROLL_DELTA
  LDA RENDER_ROW
  CLC
  ADC PREV_LINE_ROWS
  CLC
  ADC #1                        ; 1-based
  LDX #$FF                      ; scroll down
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
  CLC
  ADC CUR_LINE_ROWS
  CLC
  ADC #1                        ; 1-based
  LDX #0                        ; scroll up
  JSR scroll_region_from_a
  JSR render_line_from_change
  PLA
  STA SCROLL_DELTA
  LDA #0
  STA DELETE_SCREEN_ROWS        ; reset for next frame
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
  ; ICH/DCH hint: shift single-row lines instead of rewriting them
  LDA SHIFT_WRITE
  CMP #$FF
  BEQ .no_shift
  LDA CUR_LINE_ROWS
  CMP #1
  BNE .no_shift
  LDA PREV_LINE_ROWS
  CMP #1
  BNE .no_shift
  JSR shift_change_row
  BCC .done
.no_shift:
  LDA WRAP_REM
  BEQ .full_rows
  JSR render_partial_first_row
  DEC SCROLL_DELTA
.full_rows:
  JSR set_render_line_to_cursor
  JMP render_limited_loop
.done:
  RTS

; Draw the change row using the SHIFT_NET/SHIFT_WRITE hint: shift the
; old text with ICH/DCH and write only the new cells, when that is
; cheaper than rewriting the rest of the row.
; Input: RENDER_ROW/RENDER_WRAP = the change row, WRAP_REM = change col
; Returns: C=0 if the row was drawn, C=1 to draw it the usual way
; Clobbers: A, X, Y, BUF_PTR16, RENDER_COL, RENDER_STOP, DIV_INPUT16
shift_change_row:
  ; ROW_END = min(cols, len - row_start); row_start = from_col - WRAP_REM
  JSR get_current_line_len
  SEC
  SBC RENDER_FROM_COL16
  STA DIV_INPUT16
  TXA
  SBC RENDER_FROM_COL16 + 1
  STA DIV_INPUT16 + 1
  LDA WRAP_REM
  CLC
  ADCA16 DIV_INPUT16, DIV_INPUT16
  LDA DIV_INPUT16 + 1
  BNE .row_full
  LDA DIV_INPUT16
  CMP SCREEN_COLS
  BCC .row_end_ok
.row_full:
  LDA SCREEN_COLS
.row_end_ok:
  STA ROW_END
  ; ROW_WEND = min(ROW_END, WRAP_REM + SHIFT_WRITE): end of the new cells
  LDA WRAP_REM
  CLC
  ADC SHIFT_WRITE
  BCS .wend_clip
  CMP ROW_END
  BCC .wend_ok
.wend_clip:
  LDA ROW_END
.wend_ok:
  STA ROW_WEND
  ; X = old text after the new cells that a rewrite would resend
  LDA ROW_END
  SEC
  SBC ROW_WEND
  TAX
  LDA SHIFT_NET
  BMI .delete
  BEQ .write_new               ; net 0: only the new cells change
  CPX #0
  BEQ .write_new               ; nothing after the new cells
  CPX #5
  BCC .write_rest              ; short tail: resending beats ICH
  JSR move_to_partial_pos
  LDA SHIFT_NET
  JSR ansi_insert_chars
  JMP .write_cells
.write_rest:
  LDA ROW_END
  STA ROW_WEND
.write_new:
  JSR move_to_partial_pos
.write_cells:
  ; Write cells [WRAP_REM, ROW_WEND) of the row
  LDA ROW_WEND
  CMP WRAP_REM
  BEQ .drawn                   ; nothing to write
  JSR get_current_line_ptr
  LDX RENDER_WRAP
  JSR buf_ptr_advance_x
  LDA WRAP_REM
  STA RENDER_COL
  LDA ROW_WEND
  STA RENDER_STOP
  JSR render_line_chars_to
.drawn:
  CLC
  RTS
.delete:
  ; Rewriting costs the tail plus ESC[K; DCH costs about 4 bytes
  CPX #2
  BCC .decline
  JSR move_to_partial_pos
  LDA SHIFT_NET
  EOR #$FF
  CLC
  ADC #1                       ; |net|
  JSR ansi_delete_chars
  JMP .write_cells
.decline:
  SEC
  RTS

; Advance BUF_PTR16 by SCREEN_COLS (one wrap row)
; Clobbers A. Preserves X, Y
buf_add_cols:
  CLC
  LDA BUF_PTR16
  ADC SCREEN_COLS
  STA BUF_PTR16
  LDA BUF_PTR16 + 1
  ADC #0
  STA BUF_PTR16 + 1
  RTS

; Advance BUF_PTR16 by X * SCREEN_COLS (X wrap rows; X may be 0)
; Clobbers A, X. Preserves Y
buf_ptr_advance_x:
  CPX #0
  BEQ .done
.loop:
  JSR buf_add_cols
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
