  .org $0200

  jsr read_b
;  lda #$a2

  jsr write_b
  brk


read_b:
  lda $f004
  beq read_b
  rts


write_b
  pha
  lsr
  lsr
  lsr
  lsr
  jsr write_hex_digit
  pla
write_hex_digit:
  and #$0f
  cmp #10
  bcs write_hex_digit_low
  adc #'0'
  jsr _write_b
  rts
write_hex_digit_low:
  clc
  adc #'A'
  sec
  sbc #10
  jsr _write_b
  rts


_write_b:
  sta $f001
  rts
