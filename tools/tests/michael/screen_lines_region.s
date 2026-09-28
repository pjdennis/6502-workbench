; Rows deleted and inserted within a region on the Michael ROM's services: more rows than the
; region has from the cursor blank them, and the rows below the region stay.
  .include rom_vectors.inc

  .org $0200
start:
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
  lda #1
  ldy #3
  jsr scr_region
  goto 2, 1
  lda #9
  jsr scr_delete_lines    ; row1, -, -, row4
  print end               ; row1, end, -, row4
  goto 1, 1
  lda #1
  jsr scr_insert_lines    ; -, row1, end, row4
  jsr scr_region_reset
  jsr con_flush           ; Show the screen and stop (exit would go back to the loader)
  stp

row1:  .asciiz "row1"
row2:  .asciiz "row2"
row3:  .asciiz "row3"
row4:  .asciiz "row4"
end:   .asciiz "end"

  .include print_string.inc
