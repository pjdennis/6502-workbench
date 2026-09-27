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

; RENDER_FLAG values: the handler's render request, reset to RF_AUTO
; before each key (contract table in render_decide.asm).  render_decide
; range-compares them, so the order matters: RF_JOIN..RF_CHAR_JOIN are
; line-delete scrolls, RF_INS..RF_ENTER and RF_SPLIT line-insert scrolls
; ($02 is unused).
RF_AUTO       = $00   ; Infer the repaint from the snapshot
RF_LINE       = $01   ; Cursor line changed in place (from RENDER_FROM_COL16)
RF_INS        = $03   ; Lines inserted at the cursor line (o O p P, undo dd)
RF_UNJOIN     = $04   ; Undo J: lines restored below the cursor line
RF_ENTER      = $05   ; Enter (insert mode, r<Enter>, typed-ahead p) split the line
RF_JOIN       = $06   ; Lines joined into the cursor line (J, BS/Del join)
RF_DEL        = $07   ; Lines deleted (dd, undo p P o O), cursor line not redrawn
RF_CHAR_JOIN  = $08   ; Multi-line x/D (delete_at_cursor), SCROLL_DELTA set
RF_SPLIT      = $09   ; Cursor line split (multi-line char paste, undo x/D)
RF_INS_PRESET = $0A   ; As RF_INS with SCROLL_DELTA pre-set (undo Ncc)
RF_RANGE      = $0B   ; Lines changed in place from the cursor line (>> <<)
RF_FULL       = $FF   ; Full redraw

STATUS_SHADOW = $0380  ; The status bar's text (status_build), 128 bytes

; (zero-page variables: zp.asm)

; Initialize rendering state: get the screen size
; (cursor, view and mode state start at 0 from editor_main's zero-page
; clear)
render_init:
  .ifdef terminal_mode
  JMP query_terminal_size    ; (also sets TEXT_ROWS)
  .else
  JSR term_rows
  STA SCREEN_ROWS
  TAX
  DEX
  STX TEXT_ROWS              ; SCREEN_ROWS - 1: text rows above the status bar
  JSR term_cols
  STA SCREEN_COLS
  RTS
  .endif

; Full screen redraw
; Renders all visible lines plus status bar, positions cursor
; Handles line wrapping: one file line can span multiple screen rows
render_screen:
  JSR ansi_cursor_hide
; The same with the cursor already hidden
render_from_top:
  LDA #0
  STA RENDER_ROW
  JSR find_line_at_render_row  ; row 0: VIEW_TOP16 / VIEW_TOP_WRAP
  LDA #$FF
  STA SCROLL_DELTA             ; 255 rows: to the status bar
  JMP render_limited_rows

; Point RENDER_LINE16 at the cursor line (RENDER_LINE16 = FILE_LINE16),
; or in a range repaint (RF_RANGE) at the range's first line, which the
; shift recorded (UNDO_LINE16: :N,M> and :N,M< leave the cursor on the
; last).  Clobbers A, X; preserves the carry (setup_first_row)
set_render_line_to_cursor:
  LDX #FILE_LINE16
  LDA RENDER_FLAG
  EOR #RF_RANGE
  BNE render_line_from_x
  LDX #UNDO_LINE16
; RENDER_LINE16 = the 16-bit zero-page value at X.  Clobbers A; preserves
; the carry
render_line_from_x:
  LDA $00,X
  STA RENDER_LINE16
  LDA $01,X
  STA RENDER_LINE16 + 1
  RTS

; CUR_LINE_ROWS = the cursor line's screen rows, then set_first_row.
; Clobbers A, X, Y, BUF_PTR16, DIV_INPUT16
cursor_line_first_row:
  JSR file_line_rows
  STA CUR_LINE_ROWS
  ; fall through
; RENDER_ROW = the cursor line's first screen row (CURSOR_ROW - WRAP_QUOT)
; Returns C=0 if the line starts above the view.  Clobbers A
set_first_row:
  LDA CURSOR_ROW
  SEC
  SBC WRAP_QUOT
  STA RENDER_ROW
  RTS

; A = the 1-based screen row below the cursor line's first A rows:
; first_row + A + 1, worked out from the cursor row, as first_row is
; negative when the line starts above the view.  $FF when that is past
; row 254 (nothing below them is on screen: a scroll from there does
; nothing), 1 (the top row) when it is above the view.  Clobbers A
row_below_rows:
  SEC
  SBC WRAP_QUOT                ; the rows from the cursor's
  BCC .above                   ; (they end above the cursor's row)
  SEC
  ADC CURSOR_ROW
  BCC .done
  LDA #$FF                     ; past row 255
.done:
  RTS
.above:
  SEC
  ADC CURSOR_ROW               ; C=0: above row 0 (1-based)
  BEQ .top
  BCS .done
.top:
  LDA #1
  RTS

; Set RENDER_ROW to the cursor line's first screen row, then point
; RENDER_LINE16 at the cursor line with RENDER_WRAP = 0.  Returns C=0 if
; the line starts above the view.  Clobbers A
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
; then render to the bottom (or SCROLL_DELTA rows: _limited) from there;
; a line starting above the view is drawn from the top row to the bottom.
; Expects ansi_cursor_hide already called.
render_from_first_row:
  LDA #$FF
  STA SCROLL_DELTA             ; 255 rows: to the status bar
render_from_first_row_limited:
  JSR setup_first_row
  BCC render_from_top          ; the line starts above the view
  JMP render_limited_rows

; The status bar (last row): status_build builds its text, then
; status_send sends the part that differs from what the row shows
; (render_finish)

; Send the status text built by status_build from its first changed
; column (nothing if it is unchanged), in reverse video, clearing the
; row's tail when the old text was longer or unknown (ST_LEN = 0).
; ST_LEN = the new length.  Clobbers A, X, Y, STR_PTR16, DEC_VALUE16
status_send:
  LDX ST_FIRST
  BMI status_ret               ; unchanged
  LDA TEXT_ROWS                ; the status row (0-based), column X
  JSR ansi_goto0
  JSR ansi_reverse_video
  LDX ST_FIRST
.loop:
  CPX ST_COL
  BCS .sent
  LDA STATUS_SHADOW,X
  JSR io_write                 ; (preserves X)
  INX
  BNE .loop                    ; Always taken (ST_COL < 128)
.sent:
  LDA ST_LEN
  BNE .normal
  JSR ansi_clear_line
.normal:
  JSR ansi_normal_video
  LDA ST_COL
  STA ST_LEN
status_ret:
  RTS

; Build the status bar's text into STATUS_SHADOW (see text_putc).  Sends
; nothing.  On return ST_COL = its length and ST_FIRST = the first column
; to send ($FF = none); ST_LEN = 0 if the row's tail must be cleared.
; A message held on the status row (STATUS_HOLD) is kept for one frame:
; the status bar is then left alone (ST_FIRST = $FF, and ST_LEN stays 0).
; Clobbers A, X, Y, STR_PTR16, DEC_VALUE16
status_build:
  LDA #$FF
  STA ST_FIRST                 ; no change found yet
  LSR STATUS_HOLD
  BCS status_ret               ; a message stays for this frame
  STA ST_BUILD                 ; text_putc stores the text
  LDA SCREEN_COLS
  STA TEXT_LEFT                ; SCREEN_COLS - 1 characters fit
  LDA #0
  STA ST_COL

  ; Print filename
  JSR write_fname

  ; Print read-only indicator
  LDA READONLY
  BEQ .not_readonly
  PRINT_TEXT str_ro_indicator
.not_readonly:

  ; Print modified flag
  LDA MODIFIED
  BEQ .not_modified
  PRINT_TEXT str_mod_indicator
.not_modified:

  ; Print separator
  JSR print_separator

  ; Print mode
  LDA MODE
  ASL
  TAY
  LDX mode_strings + 1,Y
  LDA mode_strings,Y
  JSR print_string_ax

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
  CP16 COUNT16, DEC_VALUE16
  JSR print_decimal
  LDA LAST_KEY
  BEQ .done_prefix
.has_key:
  JSR text_putc
.done_prefix:
  JSR print_separator
.no_prefix_display:

  ; Line number (1-based)
  CLC
  ADCI16 FILE_LINE16, $0001, DEC_VALUE16
  JSR print_decimal

  LDA #','
  JSR text_putc

  ; Column (1-based, 16-bit)
  CLC
  ADCI16 CURSOR_COL16, $0001, DEC_VALUE16
  JSR print_decimal

  ; Print total lines
  LDA #' '
  JSR text_putc
  LDA #'/'
  JSR text_putc

  CP16 LINE_COUNT16, DEC_VALUE16
  JSR print_decimal
  INC ST_BUILD                 ; text_putc sends again

  ; Old text longer: the row is cleared from the new text's end (or from
  ; its first change).  (Old text unknown, ST_LEN = 0: every column
  ; differs, and status_send clears the row.)
  LDX ST_COL
  CPX ST_LEN
  BCS .built
  LDA #0
  STA ST_LEN
  BIT ST_FIRST
  BPL .built
  STX ST_FIRST
.built:
  RTS

; Text character A on the status row: dropped once the row is full,
; else added to the status bar's text while status_build runs, or sent.
; Text on the row stops one column short of its right edge (TEXT_LEFT,
; armed by status_line_clear and status_build): a character in the
; bottom-right cell followed by one more would scroll the whole screen.
; Preserves A, Y (and X when not building)
text_putc:
  DEC TEXT_LEFT
  BEQ .full
  BIT ST_BUILD
  BMI .build
  JMP io_write
.full:
  INC TEXT_LEFT
  RTS
  ; Add A to the status bar's text: store it at column ST_COL of
  ; STATUS_SHADOW, noting in ST_FIRST the first column that differs from
  ; the row on screen (the old text, ST_LEN long).  (The text is at most
  ; 81 characters, so it always fits STATUS_SHADOW.)  Clobbers X
.build:
  LDX ST_COL
  INC ST_COL
  BIT ST_FIRST
  BPL .store                   ; a difference was already found
  CPX ST_LEN
  BCS .differs                 ; past the old text
  CMP STATUS_SHADOW,X
  BEQ .store
.differs:
  STX ST_FIRST
.store:
  STA STATUS_SHADOW,X
  RTS

; Status-bar strings (status_build)
str_ro_indicator:  .asciiz " [RO]"
str_mod_indicator: .asciiz " [+]"
str_separator:     .asciiz " - "
str_normal:        .asciiz "NORMAL"
str_insert:        .asciiz "INSERT"
str_command:       .asciiz "COMMAND"
mode_strings:      .word str_normal, str_insert, str_command

; Print the status-line separator " - "
; Clobbers A, X, Y
print_separator:
  LDA #<str_separator
  LDX #>str_separator
  JMP print_string_ax

; Redraw current line's wrap rows plus status bar (for single-line edits)
; If the line's row count changed, the rows below it are scrolled first to
; open or close the difference, so only the line itself (and any rows
; exposed at the bottom) are drawn.
render_current_line_and_status:
  ; WRAP_QUOT = cursor's wrap row (set by ensure_cursor_visible)
  ; First screen row of the line (C=0: above the view)
  JSR cursor_line_first_row
  BCS render_rows_resized
  ; A line that starts above the view is drawn from its change if that
  ; is on screen: the rows above it keep their place (the rows below
  ; are worked out from the cursor row, as first_row is negative).
  ; Else a full repaint
  LDA WRAP_QUOT
  STA RENDER_WRAP              ; its first row, from the cursor's
  JSR change_cell_row          ; C=0: above the view
  BCS render_rows_resized
  JMP render_screen
; Entry: RENDER_ROW = first_row (set_first_row), the first row of a block
; (cursor line, $0B range, or a J undo's cursor line and restored lines)
; that changed from PREV_LINE_ROWS to CUR_LINE_ROWS rows; draw it from its
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
  LDA PREV_LINE_ROWS
  JSR row_below_rows
  LDX #'T'                      ; scroll down
  JSR scroll_region_from_a
  BCS .same_rows
  BNE .same_rows                ; region past the screen: no row opened
  ; A one-row region (the last content row) is not scrolled, so it still
  ; holds the next line: rewrite the rows (ESC[K) instead of shifting
  LDA #$FF
  STA SHIFT_WRITE
.same_rows:
  JSR render_line_from_change
  JMP render_finish

.rows_decreased:
  ; --- Rows decreased: scroll the rows below the new line end up ---
  LDA PREV_LINE_ROWS
  SEC
  SBC CUR_LINE_ROWS
  STA SCROLL_DELTA
  LDA CUR_LINE_ROWS
  JSR row_below_rows
  JSR scroll_up_clamped         ; SCROLL_DELTA = rows exposed at the bottom
  JSR render_line_keep_delta
  JMP render_bottom_rows

; render_line_from_change, keeping SCROLL_DELTA (the rows a scroll
; exposed, drawn after the line)
render_line_keep_delta:
  LDA SCROLL_DELTA
  PHA
  JSR render_line_from_change
  PLA
  STA SCROLL_DELTA
  RTS

; Draw the cursor line (or a block of lines from it) from its change
; point (RENDER_FROM_COL16; $FFFF = whole line) to its last row, stopping
; at the status bar.
; Input: RENDER_ROW = the line's first screen row, CUR_LINE_ROWS = the
; rows of the line (block)
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
  CMP TEXT_ROWS
  BCS .done                    ; change row is at or below the status bar
  ; ICH/DCH hint: shift the line's rows instead of rewriting them (rows
  ; opened by the caller's scroll are blank and just get written)
  LDX SHIFT_WRITE
  INX
  BNE render_line_shift        ; $FF = no hint
  ; Rewrite the rows, the change row from the change column
  JSR set_render_line_to_cursor
  LDA WRAP_REM
  JMP render_limited_from_col
.done:
  RTS

; Draw the cursor line from its change row using the SHIFT_NET /
; SHIFT_WRITE hint: each row's old text is shifted with ICH/DCH and only
; the new cells (and cells carried across a row boundary) are written,
; wherever that is cheaper than resending the row.  The row's start is
; worked out once and then stepped a row at a time.
; Input: RENDER_ROW/RENDER_WRAP = change row, WRAP_REM = change col,
;        SCROLL_DELTA = rows from the change row to the line's last row
; Clobbers: A, X, Y, BUF_PTR16, RENDER_ROW/COL/STOP, SCROLL_DELTA,
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
  STA RENDER_COL               ; (0 or 1) the first row starts with a move
  JSR get_current_line_ptr
  LDX RENDER_WRAP
.next_ptr:
  JSR buf_ptr_advance_x        ; BUF_PTR16 = the row's start
  JSR shift_row
  DEC SCROLL_DELTA
  BEQ .done
  INC RENDER_ROW
  LDA RENDER_ROW
  CMP TEXT_ROWS
  BCS .done                    ; reached the status bar
  LDA #0
  STA WRAP_REM                 ; later rows change from column 0
  SEC
  SBC16_8 SHIFT_REM16, SCREEN_COLS, SHIFT_REM16
  SEC
  SBC16_8 SHIFT_IEND16, SCREEN_COLS, SHIFT_IEND16
  LDX #1
  BNE .next_ptr                ; Always: the next row starts a row on
.done:
  RTS

; Draw one row of the shifted line: RENDER_ROW, starting at BUF_PTR16,
; changed from column WRAP_REM, with SHIFT_REM16/SHIFT_IEND16 relative
; to its start
; Clobbers: A, X, Y, RENDER_COL, RENDER_STOP, SCROLL_DELTA (net 0)
shift_row:
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
  BCS .wend_max                ; past 255: past the row end too
  CMP ROW_WEND
  BCC .clip
  STA ROW_WEND
.clip:
  LDA ROW_WEND
  CMP ROW_END
  BCC .wend_ok
.wend_max:
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
  BEQ .net_zero
  CPX #5
  BCC .write_rest              ; short (or no) tail: resending beats ICH
  JSR move_to_partial_pos
  LDA SHIFT_NET
  JSR ansi_insert_chars
  JMP write_row_cells
.net_zero:
  ; Net 0: only the new cells change, and once a row has none, no row
  ; after it has any: SCROLL_DELTA = 1 makes this the line's last row
  LDA ROW_WEND
  CMP WRAP_REM
  BNE .write_new
  LDA #1
  STA SCROLL_DELTA
  RTS
.write_rest:
  LDA ROW_END
  STA ROW_WEND
.write_new:
  ; The row before written to its end by chars (RENDER_COL = cols): the
  ; terminal wraps to this row's column 0 by itself, as in render_rows
  LDA RENDER_COL
  CMP SCREEN_COLS
  BNE .move_new
  LDA WRAP_REM
  BEQ write_row_cells
.move_new:
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
  LDX WRAP_REM
  JMP ansi_goto0
