; A character screen kept in RAM and shown on an HD44780 panel: the screen
; calls of the editor's direct_io build (asm/17/environment.asm,
; scr_*), plus writing characters at the cursor. They change the copy in RAM
; and mark its rows dirty; lcd_screen_flush writes the dirty rows to the LCD
; and places the LCD's cursor.
;
; Behaves like the editor's reference terminal (editor/tests/ansi_screen.py),
; which wraps to the next row after the last column, except that on the
; bottom row a character past the last column is dropped (so the bottom
; row never scrolls the screen) and reverse video is not shown.
;
; Requires:
;   LCD_SCREEN        - DISPLAY_WIDTH * DISPLAY_HEIGHT bytes: the characters
;   LCD_SCREEN_STATE  - 9 bytes (below)
;   display_command, display_character (display_routines.inc; with
;   EXTEND_CHARACTER_SET, '~' and '\' show as custom characters)
;   DISPLAY_WIDTH, DISPLAY_HEIGHT (4), DISPLAY_*_LINE (base config)
;   ASCII.inc
;
; Rows and columns passed in are 1-based. Every call preserves X; the
; ones that say so also preserve A and Y.

LCD_SCREEN_ROW    = LCD_SCREEN_STATE + 0 ; Cursor row (0-based)
LCD_SCREEN_COL    = LCD_SCREEN_STATE + 1 ; Cursor column (0-based; DISPLAY_WIDTH = past the end)
LCD_SCREEN_TOP    = LCD_SCREEN_STATE + 2 ; Scroll region, first row (0-based)
LCD_SCREEN_BOTTOM = LCD_SCREEN_STATE + 3 ; Scroll region, last row (0-based)
LCD_SCREEN_CURSOR = LCD_SCREEN_STATE + 4 ; $00 cursor hidden, else shown
LCD_SCREEN_DIRTY  = LCD_SCREEN_STATE + 5 ; Bit n set: row n needs writing to the LCD
LCD_SCREEN_CELL   = LCD_SCREEN_STATE + 6 ; Shifts: first cell of the span
LCD_SCREEN_END    = LCD_SCREEN_STATE + 7 ;         one past its last cell
LCD_SCREEN_COUNT  = LCD_SCREEN_STATE + 8 ;         cells to shift by

LCD_SCREEN_SIZE   = DISPLAY_WIDTH * DISPLAY_HEIGHT
LCD_SCREEN_CR     = $0d

; Index of each row's first cell, and one past the last row
lcd_screen_row_offsets:
  .byte 0, DISPLAY_WIDTH, DISPLAY_WIDTH * 2, DISPLAY_WIDTH * 3, LCD_SCREEN_SIZE
lcd_screen_row_addresses:
  .byte CMD_SET_DDRAM_ADDRESS | DISPLAY_FIRST_LINE, CMD_SET_DDRAM_ADDRESS | DISPLAY_SECOND_LINE
  .byte CMD_SET_DDRAM_ADDRESS | DISPLAY_THIRD_LINE, CMD_SET_DDRAM_ADDRESS | DISPLAY_FOURTH_LINE
lcd_screen_bits:
  .byte %0001, %0010, %0100, %1000


; Hide the cursor, make the scroll region the whole screen, then clear it
lcd_screen_initialize:
  stz LCD_SCREEN_CURSOR
  jsr lcd_screen_region_reset
  ; fall through

; Clear the screen; cursor to the top left
lcd_screen_clear:
  ldy #LCD_SCREEN_SIZE - 1
  lda #' '
.loop:
  sta LCD_SCREEN, Y
  dey
  bpl .loop
  jsr lcd_screen_all_dirty
  ; fall through

; Cursor to the top left
lcd_screen_home:
  lda #1
  tay
  ; fall through

; Move the cursor to row A, column Y
lcd_screen_goto:
  dec
  cmp #DISPLAY_HEIGHT
  bcc .row_ok
  lda #DISPLAY_HEIGHT - 1
.row_ok:
  sta LCD_SCREEN_ROW
  tya
  dec
  cmp #DISPLAY_WIDTH
  bcc .col_ok
  lda #DISPLAY_WIDTH
.col_ok:
  sta LCD_SCREEN_COL
  rts


; Scroll region the whole screen; cursor to the top left
lcd_screen_region_reset:
  lda #1
  ldy #DISPLAY_HEIGHT
  ; fall through

; Scroll region rows A to Y; cursor to the top left. A region of fewer
; than two rows is ignored
lcd_screen_region:
  dec
  cpy #DISPLAY_HEIGHT + 1
  bcc .bottom_ok
  ldy #DISPLAY_HEIGHT
.bottom_ok:
  dey
  sty LCD_SCREEN_COUNT
  cmp LCD_SCREEN_COUNT
  bcs .ignored                     ; top >= bottom
  sta LCD_SCREEN_TOP
  sty LCD_SCREEN_BOTTOM
  bra lcd_screen_home
.ignored:
  rts


lcd_screen_cursor_on:
  lda #$ff
  .byte $2c                        ; bit abs: skips the lda #0
lcd_screen_cursor_off:
  lda #0
  sta LCD_SCREEN_CURSOR
lcd_screen_nothing:                ; reverse and normal video
  rts


; Mark every row dirty
; On exit A is not preserved
lcd_screen_all_dirty:
  lda #%1111
  sta LCD_SCREEN_DIRTY
  rts


; Mark the cursor's row dirty
; On exit Y = the index of the cursor's cell, A = the index of its row's
;         first cell
lcd_screen_cursor_cell:
  phx
  ldx LCD_SCREEN_ROW
  lda lcd_screen_bits, X
  tsb LCD_SCREEN_DIRTY
  lda lcd_screen_row_offsets, X
  plx
  pha
  clc
  adc LCD_SCREEN_COL
  tay
  pla
  rts


; Write the character in A at the cursor and move right, to the next row
; after the last column but on the bottom row past it (dropping characters
; written there). BS moves left, CR to the first column, LF to the first
; column of the next row; other control codes are dropped
; On exit A, X, Y are preserved
lcd_screen_write:
  phy
  pha
  cmp #' '
  bcs .printable
  cmp #ASCII_BACKSPACE
  bne .not_backspace
  lda LCD_SCREEN_COL
  beq .done
  dec LCD_SCREEN_COL
  bra .done
.not_backspace:
  cmp #ASCII_LF
  bne .not_lf
  lda LCD_SCREEN_ROW
  cmp #DISPLAY_HEIGHT - 1
  bcs .cr
  inc LCD_SCREEN_ROW
  bra .cr
.not_lf:
  cmp #LCD_SCREEN_CR
  bne .done
.cr:
  stz LCD_SCREEN_COL
  bra .done
.printable:
  lda LCD_SCREEN_COL
  cmp #DISPLAY_WIDTH
  bcs .done
  jsr lcd_screen_cursor_cell
  pla
  pha
  sta LCD_SCREEN, Y
  inc LCD_SCREEN_COL
  lda LCD_SCREEN_COL
  cmp #DISPLAY_WIDTH
  bcc .done
  lda LCD_SCREEN_ROW
  cmp #DISPLAY_HEIGHT - 1
  bcs .done                        ; Bottom row: stay past the end
  inc LCD_SCREEN_ROW
  stz LCD_SCREEN_COL
.done:
  pla
  ply
  rts


; Clear from the cursor to the end of its row
lcd_screen_clear_eol:
  lda #DISPLAY_WIDTH
  ; Shifting the row's rest left by at least its length blanks it all
  ; fall through

; Delete A characters at the cursor, shifting the rest of the row left
; and blanking the end; the cursor stays
lcd_screen_delete:
  jsr lcd_screen_cursor_span
  bne lcd_screen_shift_left
  rts

; Insert A blanks at the cursor, shifting the rest of the row right
; (characters pushed past its end are lost); the cursor stays
lcd_screen_insert:
  jsr lcd_screen_cursor_span
  bne lcd_screen_shift_right
  rts

; Scroll the region up A rows, blank rows coming in at the bottom
lcd_screen_scroll_up:
  jsr lcd_screen_region_span
  bne lcd_screen_shift_left
  rts

; Scroll the region down A rows, blank rows coming in at the top
lcd_screen_scroll_down:
  jsr lcd_screen_region_span
  bne lcd_screen_shift_right
  rts

; Insert A blank rows at the cursor's row, it and the rows below it in the
; region moving down (rows pushed past the region's bottom are lost); the
; cursor goes to the row's first column. Nothing when the cursor is outside
; the region
lcd_screen_insert_lines:
  ldy LCD_SCREEN_TOP
  phy
  jsr lcd_screen_lines_region
  bcs lcd_screen_lines_done
  jsr lcd_screen_scroll_down
  bra lcd_screen_lines_done

; Delete A rows at the cursor's row, the rows below it in the region moving
; up (blank rows coming in at the region's bottom); the cursor goes to the
; row's first column. Nothing when the cursor is outside the region
lcd_screen_delete_lines:
  ldy LCD_SCREEN_TOP
  phy
  jsr lcd_screen_lines_region
  bcs lcd_screen_lines_done
  jsr lcd_screen_scroll_up
lcd_screen_lines_done:
  ply
  sty LCD_SCREEN_TOP
  rts

; Make the region start at the cursor's row, and the cursor go to its first
; column; C set (and nothing changed) if the cursor is outside the region
; On exit A is preserved
lcd_screen_lines_region:
  ldy LCD_SCREEN_ROW
  cpy LCD_SCREEN_TOP
  bcc .outside
  cpy LCD_SCREEN_BOTTOM
  beq .inside
  bcs .outside
.inside:
  sty LCD_SCREEN_TOP
  stz LCD_SCREEN_COL
  clc
  rts
.outside:
  sec
  rts


; Move the span's cells left by the count, blanking the cells freed at its end
lcd_screen_shift_left:
  phx
  ldx LCD_SCREEN_CELL              ; X = destination
.copy:
  txa
  clc
  adc LCD_SCREEN_COUNT             ; source = destination + count
  cmp LCD_SCREEN_END
  bcs .blank
  tay
  lda LCD_SCREEN, Y
  sta LCD_SCREEN, X
  inx
  bra .copy
.blank:
  lda #' '
.blank_loop:
  cpx LCD_SCREEN_END
  bcs .done
  sta LCD_SCREEN, X
  inx
  bra .blank_loop
.done:
  plx
  rts


; Move the span's cells right by the count, blanking the cells freed at its start
lcd_screen_shift_right:
  phx
  ldx LCD_SCREEN_END
.copy:
  dex                              ; X = destination
  txa
  sec
  sbc LCD_SCREEN_COUNT             ; source = destination - count
  bcc .blank
  cmp LCD_SCREEN_CELL
  bcc .blank
  tay
  lda LCD_SCREEN, Y
  sta LCD_SCREEN, X
  bra .copy
.blank:
  lda #' '
.blank_loop:
  sta LCD_SCREEN, X
  cpx LCD_SCREEN_CELL
  beq .done
  dex
  bra .blank_loop
.done:
  plx
  rts


; Span = the cursor's cell to its row's end; count = A, at most the span
; On exit A = the count, Z set if it is 0
lcd_screen_cursor_span:
  sta LCD_SCREEN_COUNT
  jsr lcd_screen_cursor_cell
  sty LCD_SCREEN_CELL
  clc
  adc #DISPLAY_WIDTH
  sta LCD_SCREEN_END
  sec
  sbc LCD_SCREEN_CELL
  cmp LCD_SCREEN_COUNT
  bcs .count_ok
  sta LCD_SCREEN_COUNT
.count_ok:
  lda LCD_SCREEN_COUNT
  rts


; Span = the scroll region's cells; count = A rows' cells, at most the
; region; every row dirty
; On exit A = the count, Z set if it is 0
lcd_screen_region_span:
  phx
  sta LCD_SCREEN_COUNT
  jsr lcd_screen_all_dirty
  lda LCD_SCREEN_BOTTOM
  sec
  sbc LCD_SCREEN_TOP
  inc                              ; the region's height
  cmp LCD_SCREEN_COUNT
  bcs .rows_ok
  sta LCD_SCREEN_COUNT
.rows_ok:
  ldx LCD_SCREEN_COUNT
  lda lcd_screen_row_offsets, X    ; rows * DISPLAY_WIDTH
  sta LCD_SCREEN_COUNT
  ldx LCD_SCREEN_TOP
  lda lcd_screen_row_offsets, X
  sta LCD_SCREEN_CELL
  ldx LCD_SCREEN_BOTTOM
  lda lcd_screen_row_offsets + 1, X
  sta LCD_SCREEN_END
  plx
  lda LCD_SCREEN_COUNT
  rts


; Write the dirty rows to the LCD, then show the cursor where it is, or
; hide it
; On exit A, X, Y are preserved
lcd_screen_flush:
  pha
  phx
  phy
  ldx #0
.row:
  lda lcd_screen_bits, X
  bit LCD_SCREEN_DIRTY
  beq .next_row
  trb LCD_SCREEN_DIRTY
  lda lcd_screen_row_addresses, X
  jsr display_command
  lda lcd_screen_row_offsets + 1, X
  sta LCD_SCREEN_END
  ldy lcd_screen_row_offsets, X
.char:
  lda LCD_SCREEN, Y
  jsr display_character
  iny
  cpy LCD_SCREEN_END
  bne .char
.next_row:
  inx
  cpx #DISPLAY_HEIGHT
  bne .row
  lda LCD_SCREEN_CURSOR
  beq .hide
  lda LCD_SCREEN_COL
  cmp #DISPLAY_WIDTH
  bcs .hide                        ; past the end: nowhere to show it
  ldx LCD_SCREEN_ROW
  clc
  adc lcd_screen_row_addresses, X
  jsr display_command
  lda #(CMD_DISPLAY_ON_OFF_CONTROL | CMD_PARAM_DISPLAY_ON | CMD_PARAM_CURSOR_ON)
  bra .show
.hide:
  lda #(CMD_DISPLAY_ON_OFF_CONTROL | CMD_PARAM_DISPLAY_ON)
.show:
  jsr display_command
  ply
  plx
  pla
  rts
