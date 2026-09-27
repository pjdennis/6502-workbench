; Keys on the Michael editor services: each key's code in hex until 'q'.
  .include michael_editor_layout.inc
  .include editor_vectors.inc

  .org $0400
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
  jmp exit

write_hex_digit:
  tax
  lda hex_digits, X
  jmp write_b

hex_digits: .byte "0123456789ABCDEF"
