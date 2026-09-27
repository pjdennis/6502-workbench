; Keys on the Michael ROM's services: each key's code in hex until 'q'.
  .include rom_vectors.inc

  .org $0200
  ldx #$ff
  txs
  jsr argc
  goto 1, 1
.loop:
  jsr con_read
  cmp #'q'
  beq .done
  pha
  lsr
  lsr
  lsr
  lsr
  jsr write_hex_digit
  pla
  and #$0f
  jsr write_hex_digit
  bra .loop
.done:
  jsr con_flush           ; Show the screen and stop (exit would go back to the loader)
  stp

write_hex_digit:
  tax
  lda hex_digits, X
  jmp write_b

hex_digits: .byte "0123456789ABCDEF"
