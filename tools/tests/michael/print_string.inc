print_string:
  ldy #0
.loop:
  lda (TEXT_PTR), Y
  beq .done
  jsr write_b
  iny
  bne .loop
.done:
  rts
