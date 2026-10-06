; Choosing the graphic screen after the LCD has started: the LCD keeps what it shows, and the graphic
; screen starts at once.
  .include rom_vectors.inc

  .org $0200
start:
  ldx #$ff
  txs
  jsr argc                ; the services, on the LCD
  print lcd
  jsr con_flush
  lda #1
  jsr screen_select
  print graphic
  jsr con_flush
  stp

lcd:             .asciiz "lcd"
graphic:         .asciiz "graphic"

  .include print_string.inc
