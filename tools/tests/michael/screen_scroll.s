; Scrolling on the Michael ROM's services: a region scrolled up, the whole
; screen scrolled down, and a one-row region ignored.
  .include rom_vectors.inc

  .org $0200
  ldx #$ff
  txs
  jsr argc

  goto 1, 1
  print row1
  goto 2, 1
  print row2
  goto 3, 1
  print row3
  goto 4, 1
  print row4
  lda #2
  ldy #3
  jsr scr_region
  lda #1
  jsr scr_scroll_up       ; row1, row3, -, row4
  lda #3
  ldy #3
  jsr scr_region          ; one row: ignored, region stays 2-3
  lda #9
  jsr scr_scroll_down     ; more rows than the region: blanks it
  jsr scr_region_reset
  goto 2, 1
  print again             ; row1, again, -, row4
  lda #1
  jsr scr_scroll_down     ; -, row1, again, -
  jsr con_flush           ; Show the screen and stop (exit would go back to the loader)
  stp

row1:  .asciiz "row1"
row2:  .asciiz "row2"
row3:  .asciiz "row3"
row4:  .asciiz "row4"
again: .asciiz "again"

  .include print_string.inc
