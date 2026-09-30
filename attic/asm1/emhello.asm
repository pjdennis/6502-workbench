read_b  = $f006
write_b = $f009

  .org $2000

  lda #'('
  jsr write_b 

loop:
  jsr read_b
  bcs done
  jsr write_b
  jmp loop
done:

  lda #')'
  jsr write_b

  brk
