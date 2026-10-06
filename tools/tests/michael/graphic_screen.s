; The graphic screen (SVC_SCREEN_SELECT, the FPGA's text mode) behind the same screen calls as the LCD:
; writes, positioning, insert and delete, wrapping past the last column but clipping on the bottom row,
; reverse video, and term_rows and term_cols. Without an FPGA with text mode, the choice fails and the
; program says so on the LCD.
  .include rom_vectors.inc

  .org $0200
start:
  ldx #$ff
  txs
  lda #1
  jsr screen_select       ; before the services start
  bcc .graphic
  jsr argc
  print no_fpga
  jsr con_flush
  stp
.graphic:
  jsr argc                ; starts the services: the graphic screen

  goto 1, 1
  print hello             ; "Hello, world"
  goto 1, 6
  lda #1
  jsr scr_delete          ; "Hello world"
  goto 1, 6
  lda #2
  jsr scr_insert
  print xy                ; "HelloXY world"
  goto 2, 3
  print alphabet          ; wraps onto row 3 after column 20
  goto 5, 1
  jsr scr_reverse
  print reverse
  jsr scr_normal
  goto 7, 1
  jsr term_rows
  jsr print_hex
  jsr term_cols
  jsr print_hex           ; "1414": 20 and 20
  goto 20, 15
  print alphabet          ; clipped at column 20
  jsr scr_cursor_on
  jsr con_flush
  stp

; A as two hex digits
print_hex:
  pha
  lsr
  lsr
  lsr
  lsr
  jsr .digit
  pla
  and #$0f
.digit:
  ora #'0'
  cmp #'9' + 1
  bcc .out
  adc #6                  ; 'A' - '9' - 1, with the carry
.out:
  jmp write_b

hello:           .asciiz "Hello, world"
xy:              .asciiz "XY"
alphabet:        .asciiz "abcdefghijklmnopqrstuvwxyz"
reverse:         .asciiz "REV"
no_fpga:         .asciiz "NO FPGA"

  .include print_string.inc
