  .org $2000

  lda #'['
  jsr write_b

loop:
  jsr read_b
  bcs done
  jsr write_b
  jmp loop
done:

  lda #']'
  jsr write_b

  brk

read_b:
  lda $f004
  bit $f005
  bmi .at_end
  clc
  rts
.at_end:
  sec
  rts

write_b:
  sta $f001
  rts
