; ANSI terminal output library
; All routines write escape sequences via io_write

  .zeropage
ANSI_ROW:     .byte    ; Row for cursor positioning (1-based)
ANSI_COL:     .byte    ; Column for cursor positioning (1-based)
STR_PTR16:    .word    ; Pointer for write_string

  .code

; Output ESC[ prefix
; Clobbers A
ansi_csi:
  LDA #$1B
  JSR io_write
  LDA #'['
  JMP io_write

; Output ESC[ + sequence string whose LOW address byte is in A.
; All ansi_seq_* strings must share one page (see warning at the strings).
; Clobbers A, Y
ansi_seq_a:
  STA STR_PTR16
  LDA #>ansi_seq_clear
  STA STR_PTR16 + 1
  ; fall through

; Output ESC[ followed by null-terminated string at STR_PTR16
; Clobbers A, Y
ansi_write_seq:
  JSR ansi_csi
  JMP write_string

; Clear entire screen and move cursor to home position
ansi_clear_screen:
  LDA #<ansi_seq_clear
  JSR ansi_seq_a
  ; fall through to ansi_cursor_home

; Move cursor to position 1,1
ansi_cursor_home:
  LDA #<ansi_seq_home
  JMP ansi_seq_a

; Move cursor to ANSI_ROW, ANSI_COL (both 1-based)
; Clobbers A, X, Y, STR_PTR16, TO_DECIMAL state
ansi_move_cursor:
  LDA #'H'
  BNE ansi_row_col_seq   ; Always taken ('H' != 0)

; Set scroll region: ANSI_ROW = top (1-based), ANSI_COL = bottom (1-based)
; Emits ESC[top;bottomr
; Clobbers A, X, Y, STR_PTR16, TO_DECIMAL state
ansi_set_scroll_region:
  LDA #'r'
  ; fall through

; Shared ESC[<row>;<col><final> emitter; A = final character
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
; Clobbers A, Y
ansi_reset_scroll_region:
  LDA #<ansi_seq_reset_sr
  JMP ansi_seq_a

; Scroll up by A lines (content moves up, blanks at bottom of region)
; Emits ESC[nS. Input: A = count
; Clobbers A, X, Y
ansi_scroll_up:
  LDX #'S'
  BNE ansi_count_seq     ; Always taken

; Scroll down by A lines (content moves down, blanks at top of region)
; Emits ESC[nT. Input: A = count
; Clobbers A, X, Y
ansi_scroll_down:
  LDX #'T'
  ; fall through

; Shared ESC[<count><final> emitter; A = count, X = final character
; Clobbers A, X, Y
ansi_count_seq:
  PHA
  JSR ansi_csi
  PLA
  JSR write_byte_dec     ; preserves X
  TXA
  JMP io_write

; ANSI sequence string constants
; WARNING: ansi_seq_a loads the high byte from ansi_seq_clear only, so ALL
; of these strings (25 bytes) must start on the same 256-byte page. If code
; growth pushes them across a page boundary, escape sequences will be
; garbage and the editor test suite will fail loudly - move the block.
ansi_seq_clear:    .asciiz "2J"
ansi_seq_home:     .asciiz "H"
ansi_seq_clreol:   .asciiz "K"
ansi_seq_show:     .asciiz "?25h"
ansi_seq_hide:     .asciiz "?25l"
ansi_seq_rev:      .asciiz "7m"
ansi_seq_norm:     .asciiz "0m"
ansi_seq_reset_sr: .asciiz "r"

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

; Write filename from (FNAME_PTR16), up to 32 chars
; Clobbers A, Y
write_fname:
  LDY #0
.loop:
  LDA (FNAME_PTR16),Y
  BEQ .done
  JSR io_write
  INY
  CPY #32
  BCC .loop
.done:
  RTS

; Move cursor to status line and clear it
; Clobbers A, Y
status_line_clear:
  LDA SCREEN_ROWS
  STA ANSI_ROW
  LDA #1
  STA ANSI_COL
  JSR ansi_move_cursor
  JMP ansi_clear_line

; Show prompt character on status line
; A = prompt character (e.g. ':', '/')
; Clobbers A, Y
show_prompt:
  PHA
  JSR status_line_clear
  PLA
  JSR io_write
  JMP io_flush

; Erase one character on screen: backspace, space, backspace, flush
; Clobbers A
erase_char:
  LDA #'\b'
  JSR io_write
  LDA #' '
  JSR io_write
  LDA #'\b'
  JSR io_write
  JMP io_flush

; Write A (0-255) as decimal digits, no leading zeros
; Clobbers A, Y, STR_PTR16, TO_DECIMAL_VALUE16/MOD10/RESULT (X preserved)
write_byte_dec:
  STA TO_DECIMAL_VALUE16
  LDA #0
  STA TO_DECIMAL_VALUE16 + 1
  JSR to_decimal
  SET16 TO_DECIMAL_RESULT, STR_PTR16
  JMP write_string
