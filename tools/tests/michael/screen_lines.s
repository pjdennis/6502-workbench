; Rows inserted and deleted at the cursor on the Michael ROM's services (IL and DL): the rows
; from the cursor's to the region's bottom move, the cursor goes to the row's first column,
; and a cursor outside the region changes nothing.
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
  goto 2, 3
  lda #1
  jsr scr_insert_lines    ; row1, -, row2, row3
  print new               ; row1, new, row2, row3
  goto 3, 5
  lda #1
  jsr scr_delete_lines    ; row1, new, row3, -
  print x                 ; row1, new, xow3, -
  lda #1
  ldy #2
  jsr scr_region
  goto 4, 1
  lda #1
  jsr scr_insert_lines    ; below the region: nothing
  print out               ; row1, new, xow3, out
  jsr scr_region_reset
  jsr con_flush           ; Show the screen and stop (exit would go back to the loader)
  stp

row1:  .asciiz "row1"
row2:  .asciiz "row2"
row3:  .asciiz "row3"
row4:  .asciiz "row4"
new:   .asciiz "new"
x:     .asciiz "x"
out:   .asciiz "out"

  .include print_string.inc
