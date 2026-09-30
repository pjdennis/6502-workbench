  .org $f006

  jmp read_b
  jmp write_b

read_b:
  lda $f004
  cmp #4
  beq .at_end
  clc
  rts
.at_end:
  sec
  rts

write_b:
  sta $f001
  rts
