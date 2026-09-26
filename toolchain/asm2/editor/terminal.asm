; ANSI terminal output library
; All routines write escape sequences via io_write

; (zero-page variables: zp.asm)

; Output ESC[ prefix
; Clobbers A
ansi_csi:
  LDA #$1B
  JSR io_write
  LDA #'['
  JMP io_write

; Output ESC[ + sequence string whose LOW address byte is in A.
; All ansi_seq_* strings must share one page (see warning at the strings).
; Clobbers A, Y, STR_PTR16
ansi_seq_a:
  STA STR_PTR16
  LDA #>ansi_seq_clear
  STA STR_PTR16 + 1
  JSR ansi_csi
  JMP write_string

; Clear entire screen and move cursor to home position: ESC[2J ESC[H
ansi_clear_screen:
  LDA #0
  STA ST_LEN                 ; status row blank: send all of the status bar
  LDA #<ansi_seq_clear
  JMP ansi_seq_a

; Set scroll region: ANSI_ROW = top (1-based), ANSI_COL = bottom (1-based)
; Emits ESC[top;bottomr
; Clobbers A, Y, STR_PTR16, TO_DECIMAL state (X preserved)
ansi_set_scroll_region:
  LDA #'r'
  BNE ansi_row_col_seq   ; Always taken ('r' != 0)

; Move cursor to 0-based row A, column 0 (sets ANSI_ROW/ANSI_COL)
; Clobbers A, X, Y, STR_PTR16, TO_DECIMAL state
ansi_goto_row0:
  LDX #0
; Move cursor to 0-based row A, 0-based column X
ansi_goto0:
  INX
  STX ANSI_COL
  TAX
  INX
  STX ANSI_ROW
  ; fall through
; Move cursor to ANSI_ROW, ANSI_COL (both 1-based)
; Clobbers A, Y, STR_PTR16, TO_DECIMAL state (X preserved)
ansi_move_cursor:
  LDA #'H'
  ; fall through

; Shared ESC[<row>;<col><final> emitter; A = final character.  X is
; preserved (io_write and write_byte_dec preserve it)
ansi_row_col_seq:
  PHA
  JSR ansi_csi
  LDA ANSI_ROW
  JSR write_byte_dec
  LDA #';'
  JSR io_write
  LDA ANSI_COL
  JSR write_byte_dec
  PLA
  JMP io_write

; Clear from cursor to end of current line
ansi_clear_line:
  LDA #<ansi_seq_clreol
  JMP ansi_seq_a

; Show cursor
ansi_cursor_show:
  LDA #<ansi_seq_show
  JMP ansi_seq_a

; Hide cursor
ansi_cursor_hide:
  LDA #<ansi_seq_hide
  JMP ansi_seq_a

; Enable reverse video
ansi_reverse_video:
  LDA #<ansi_seq_rev
  JMP ansi_seq_a

; Reset to normal video
ansi_normal_video:
  LDA #<ansi_seq_norm
  JMP ansi_seq_a

; Reset scroll region to full screen: ESC[r
; Clobbers A, Y, STR_PTR16
ansi_reset_scroll_region:
  LDA #<ansi_seq_reset_sr
  JMP ansi_seq_a

; Insert A blank chars at the cursor (ICH): ESC[n@. Clobbers A, X, Y
ansi_insert_chars:
  LDX #'@'
  BNE ansi_count_seq     ; Always taken

; Delete A chars at the cursor (DCH): ESC[nP. Clobbers A, X, Y
ansi_delete_chars:
  LDX #'P'
  ; fall through

; Shared ESC[<count><final> emitter; A = count, X = final character
; (@ ICH, P DCH, S scroll up: blanks at the bottom, T scroll down:
; blanks at the top).  Clobbers A, Y (X preserved)
ansi_count_seq:
  PHA
  JSR ansi_csi
  PLA
  JSR write_byte_dec     ; preserves X
  TXA
  JMP io_write

; ANSI sequence string constants
; WARNING: ansi_seq_a loads the high byte from ansi_seq_clear only, so ALL
; of these strings (26 bytes) must start on the same 256-byte page. If code
; growth pushes them across a page boundary, escape sequences will be
; garbage and the editor test suite will fail loudly - move the block.
ansi_seq_clear:    .byte "2J", $1B, "[H", $00   ; clear, then home
ansi_seq_clreol:   .asciiz "K"
ansi_seq_show:     .asciiz "?25h"
ansi_seq_hide:     .asciiz "?25l"
ansi_seq_rev:      .asciiz "7m"
ansi_seq_norm:     .asciiz "0m"
ansi_seq_reset_sr: .asciiz "r"

; Write null-terminated string at A (low) / X (high)
; Clobbers A, Y, STR_PTR16 (X preserved)
write_string_ax:
  STA STR_PTR16
  STX STR_PTR16 + 1
  ; fall through
; Write null-terminated string pointed to by STR_PTR16
; Clobbers A, Y
write_string:
  LDY #0
.loop:
  LDA (STR_PTR16),Y
  BEQ .done
  JSR io_write
  INY
  BNE .loop
.done:
  RTS

; Print the filename (FNAME_BUF), up to 32 chars, through text_putc
; Clobbers A, X, Y
write_fname:
  LDY #0
.loop:
  LDA FNAME_BUF,Y
  BEQ .done
  JSR text_putc
  INY
  CPY #32
  BCC .loop
.done:
  RTS

; Move cursor to status line and clear it
; Clobbers A, X, Y, STR_PTR16, TO_DECIMAL state
status_line_clear:
  LDA #0
  STA ST_LEN                 ; status row overwritten: send all of the status bar
  LDA SCREEN_COLS
  STA TEXT_LEFT              ; text_putc: SCREEN_COLS - 1 characters fit
  LDA TEXT_ROWS              ; The status row (0-based)
  JSR ansi_goto_row0
  JMP ansi_clear_line

; Show prompt character on status line
; A = prompt character (e.g. ':', '/')
; Clobbers A, X, Y, STR_PTR16, TO_DECIMAL state
show_prompt:
  PHA
  JSR status_line_clear
  PLA
  ; fall through
; Print A as text (text_putc: dropped once the status row is full), then
; flush output.  Preserves X, Y
text_flush:
  JSR text_putc
  JMP io_flush

; Erase the last input character on the status row (backspace, space,
; backspace, flush), giving its column back to text_putc
; Clobbers A
erase_char:
  INC TEXT_LEFT
  LDA #'\b'
  JSR io_write
  LDA #' '
  JSR io_write
  LDA #'\b'
  JSR io_write
  JMP io_flush

; Write A (0-255) as decimal digits, no leading zeros (escape sequences)
; Clobbers A, Y, STR_PTR16, TO_DECIMAL_VALUE16/MOD10/RESULT (X preserved:
; ansi_count_seq relies on it)
write_byte_dec:
  STA TO_DECIMAL_VALUE16
  LDA #0
  STA TO_DECIMAL_VALUE16 + 1
  JSR to_decimal
  ; fall through
; Write an already-converted TO_DECIMAL_RESULT
write_decimal_result:
  SET16 TO_DECIMAL_RESULT, STR_PTR16
  JMP write_string

; Print TO_DECIMAL_VALUE16 in decimal as text (through text_putc)
; Clobbers A, X, Y, STR_PTR16, TO_DECIMAL_VALUE16/MOD10/RESULT
print_decimal:
  JSR to_decimal
  LDA #<TO_DECIMAL_RESULT
  LDX #>TO_DECIMAL_RESULT
  ; fall through
; Print the null-terminated text at A (low) / X (high) through text_putc
print_string_ax:
  STA STR_PTR16
  STX STR_PTR16 + 1
  ; fall through
; Print the null-terminated text at STR_PTR16 through text_putc (text:
; write_string sends escape sequences).  Clobbers A, X, Y
print_string:
  LDY #0
.loop:
  LDA (STR_PTR16),Y
  BEQ .done
  JSR text_putc
  INY
  BNE .loop
.done:
  RTS
