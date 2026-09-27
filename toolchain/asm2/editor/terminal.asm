; ANSI terminal output library
; All routines write escape sequences via io_write

; (zero-page variables: zp.asm)

; ANSI sequence string constants
; WARNING: ansi_seq_a loads the high byte from ansi_seq_clear only, so ALL
; of these strings (23 bytes) must start on the same 256-byte page.  They
; come first in terminal.asm, which starts early in the first code page
; in both builds (at $0403 after editor.asm's JMP, or after io.asm's
; serial routines in the terminal build), so code growth does not move
; them across a page boundary.  If that changes, escape sequences will be
; garbage and the editor test suite will fail loudly - move the block.
ansi_seq_clear:    .byte "2J", $1B, "[H", $00   ; clear, then home
ansi_seq_clreol:   .asciiz "K"
ansi_seq_show:     .asciiz "?25h"
ansi_seq_hide:     .asciiz "?25l"
ansi_seq_rev:      .byte "7"          ; "7m": shares its "m" with ansi_seq_norm
ansi_seq_norm:     .asciiz "m"        ; ESC[m: SGR's default is 0 (normal)
ansi_seq_reset_sr: .asciiz "r"

; Output ESC[ prefix
; Clobbers A
ansi_csi:
  LDA #$1B
  JSR io_write
  LDA #'['
  JMP io_write

; The sequences made of ESC[ and an ansi_seq_* string.  Each entry
; loads its string's low address byte and skips the loads of the entries
; below it: .byte $2C makes the next LDA # a BIT abs, a read of $xxA9
; with xx that byte (RAM: the strings sit low in their page).  The most
; used come last.  Clobbers A, Y, STR_PTR16 (X preserved)

; Clear entire screen and move cursor to home position: ESC[2J ESC[H
ansi_clear_screen:
  LDA #0
  STA ST_LEN                 ; status row blank: send all of the status bar
  STA CUR_VALID              ; the cursor moves home
  LDA #<ansi_seq_clear
  .byte $2C                  ; BIT abs: skip the next LDA #
; Reset scroll region to full screen: ESC[r
ansi_reset_scroll_region:
  LDA #<ansi_seq_reset_sr
  .byte $2C
; Hide cursor
ansi_cursor_hide:
  LDA #<ansi_seq_hide
  .byte $2C
; Show cursor
ansi_cursor_show:
  LDA #<ansi_seq_show
  .byte $2C
; Enable reverse video
ansi_reverse_video:
  LDA #<ansi_seq_rev
  .byte $2C
; Reset to normal video
ansi_normal_video:
  LDA #<ansi_seq_norm
  .byte $2C
; Clear from cursor to end of current line
ansi_clear_line:
  LDA #<ansi_seq_clreol
  ; fall through
; Output ESC[ + sequence string whose LOW address byte is in A.
; All ansi_seq_* strings must share one page (see warning at the strings).
ansi_seq_a:
  STA STR_PTR16
  LDA #>ansi_seq_clear
  STA STR_PTR16 + 1
  JSR ansi_csi
  JMP write_string

; Set scroll region: ANSI_ROW = top (1-based), ANSI_COL = bottom (1-based)
; Emits ESC[top;bottomr (ESC[;bottomr from the top row: see
; ansi_row_col_seq), which homes the cursor (as the ESC[r after it does)
; Clobbers A, Y, STR_PTR16, DEC_VALUE16 (X preserved)
ansi_set_scroll_region:
  LSR CUR_VALID
  LDA #'r'
  BNE ansi_row_col_seq   ; Always taken ('r' != 0)

; Move cursor to 0-based row A, column 0 (sets ANSI_ROW/ANSI_COL)
; Clobbers A, X, Y, STR_PTR16, DEC_VALUE16
ansi_goto_row0:
  LDX #0
; Move cursor to 0-based row A, 0-based column X.  Right after a frame
; (CUR_VALID = 1) the cursor is still where the frame put it, at
; ANSI_ROW/ANSI_COL: a move there sends nothing, and one a column to the
; left a backspace (never in a pending wrap: the frame ended with a move)
ansi_goto0:
  INX                        ; X = the column, Y = the row (1-based)
  TAY
  INY
  LSR CUR_VALID              ; C = the cursor is at ANSI_ROW/ANSI_COL
  BCC .move                  ; (no longer after this move)
  CPY ANSI_ROW
  BNE .move
  TXA
  SBC ANSI_COL               ; (C = 1: the same row)
  BEQ .there
  CMP #$FF
  BNE .move
  STX ANSI_COL               ; one column to the left
  LDA #'\b'
  JMP io_write
.there:
  RTS
.move:
  STX ANSI_COL
  STY ANSI_ROW
  ; fall through
; Move cursor to ANSI_ROW, ANSI_COL (both 1-based)
; Clobbers A, Y, STR_PTR16, DEC_VALUE16 (X preserved)
ansi_move_cursor:
  LDA #'H'
  ; fall through

; Shared ESC[<row>;<col><final> emitter; A = final character.  A row or
; column of 1 is the default, so it is left out: ESC[<row>H for column
; 1, ESC[;<col>H for row 1, ESC[H for both (a region's bottom row is
; never 1).  X is preserved (io_write and write_param preserve it)
ansi_row_col_seq:
  PHA
  JSR ansi_csi
  LDA ANSI_ROW
  JSR write_param
  LDY ANSI_COL
  DEY
  BEQ .final                 ; column 1: no ';1'
  LDA #';'
  JSR io_write
  LDA ANSI_COL
  JSR write_param
.final:
  PLA
  JMP io_write

; Insert A blank chars at the cursor (ICH): ESC[n@. Clobbers A, X, Y
ansi_insert_chars:
  LDX #'@'
  .byte $2C              ; BIT abs ($50A2, RAM): skip the LDX #'P'

; Delete A chars at the cursor (DCH): ESC[nP. Clobbers A, X, Y
ansi_delete_chars:
  LDX #'P'
  ; fall through

; Shared ESC[<count><final> emitter; A = count, X = final character
; (@ ICH, P DCH, S scroll up: blanks at the bottom, T scroll down:
; blanks at the top).  A count of 1 is the default and is left out.
; Clobbers A, Y (X preserved)
ansi_count_seq:
  PHA
  JSR ansi_csi
  PLA
  JSR write_param        ; preserves X
  TXA
  JMP io_write

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

; Print the filename (at FNAME_PTR16), up to 32 chars, through text_putc
; Clobbers A, X, Y
write_fname:
  LDY #0
.loop:
  LDA (FNAME_PTR16),Y
  BEQ .done
  JSR text_putc
  INY
  CPY #32
  BCC .loop
.done:
  RTS

; Move cursor to status line and clear it
; Clobbers A, X, Y, STR_PTR16, DEC_VALUE16
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
; Clobbers A, X, Y, STR_PTR16, DEC_VALUE16
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

; Decimal numbers: each digit is how many times its power of ten
; subtracts from DEC_VALUE16, from 10^4 (10^2 for a byte) down, and the
; ones digit is what is left.  Leading zeros are left out, or written as
; DEC_PAD (spaces: write_decimal_field)

; Write escape-sequence parameter A (0-255) as decimal digits, no
; leading zeros, through io_write.  A 1 is left out: a VT100 or xterm
; takes a missing parameter as its default, which is 1 for every one the
; editor sends (but a scroll region's bottom row, which is never 1).
; Clobbers A, Y, DEC_VALUE16 (X preserved: ansi_count_seq relies on it)
write_param:
  CMP #1
  BEQ dec_done
  STA DEC_VALUE16
  LDA #0
  STA DEC_VALUE16 + 1
  LDY #1                     ; From 10^2 (A < 1000)
  BNE dec_io                 ; Always (A = 0: no pad)

; Write DEC_VALUE16 through io_write, right-justified in a 5-char field
; (:marks).  Same clobbers
write_decimal_field:
  LDA #' '                   ; Leading zeros as spaces
  LDY #3                     ; From 10^4
dec_io:
  CLC                        ; Through io_write
  BCC dec_digits             ; Always

; Print DEC_VALUE16 in decimal as text (through text_putc).
; Clobbers A, X, Y, DEC_VALUE16
print_decimal:
  LDA #0                     ; No pad
  LDY #3                     ; From 10^4
  SEC                        ; Through text_putc
; Write DEC_VALUE16's digits from the power of ten dec_pow[Y], leading
; zeros as A (0: none), through text_putc if C = 1, else io_write.
; Preserves X
dec_digits:
  STA DEC_PAD
  ROR DEC_TEXT               ; Bit 7 = C
  TXA
  PHA
.digit:
  LDX #'0'
.sub:
  LDA DEC_VALUE16
  CMP dec_pow_lo,Y
  LDA DEC_VALUE16 + 1
  SBC dec_pow_hi,Y
  BCC .got
  STA DEC_VALUE16 + 1
  LDA DEC_VALUE16
  SBC dec_pow_lo,Y
  STA DEC_VALUE16
  INX
  BNE .sub                   ; Always
.got:
  TXA
  CPX #'0'
  BEQ .zero
  LDX #'0'
  STX DEC_PAD                ; The digits have begun: zeros are written
  BNE .out                   ; Always
.zero:
  LDA DEC_PAD                ; A leading zero is the pad, if any
  BEQ .next
.out:
  JSR dec_out
.next:
  DEY
  BPL .digit
  LDA DEC_VALUE16            ; The ones digit, always written
  ORA #'0'
  JSR dec_out
  PLA
  TAX
dec_done:
  RTS

; Write A through text_putc (DEC_TEXT bit 7 set) or io_write
dec_out:
  BIT DEC_TEXT
  BMI .text
  JMP io_write
.text:
  JMP text_putc

dec_pow_lo: .byte <10, <100, <1000, <10000
dec_pow_hi: .byte >10, >100, >1000, >10000

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
