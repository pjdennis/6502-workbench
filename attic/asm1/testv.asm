  .org $2000
SUBROUTINE:
  lda $42
  rts

START:
  ldx #0
LOOP:
  inx
  jmp LOOP

  .BYTE "A\"\\B"
  .BYTE $42, $43
  .WORD START
