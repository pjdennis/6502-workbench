  .zeropage

TO_DECIMAL_VALUE_L          DATA $00 ; 1 byte
TO_DECIMAL_VALUE_H          DATA $00 ; 1 byte
TO_DECIMAL_MOD10
TO_DECIMAL_RESULT_MINUS_ONE DATA $00 ; 1 byte
TO_DECIMAL_RESULT           DATA $00 $00 $00 $00 $00 $00 ; 6 bytes

  .code


; On entry TO_DECIMAL_VALUE_L;TO_DECIMAL_VALUE_H contains the value to convert
; On exit TO_DECIMAL_RESULT contains the result
;         X, Y are preserved
;         A is not preserved
to_decimal
  TXA
  PHA
  ; Initialize result to empty string
  LDA# $00
  STAZ TO_DECIMAL_RESULT

td_divide
  ; Initialize the remainder to be zero
  LDA# $00
  STAZ TO_DECIMAL_MOD10
  CLC

  LDX# $10
td_divloop
  ; Rotate quotient and remainder
  ROLZ TO_DECIMAL_VALUE_L
  ROLZ TO_DECIMAL_VALUE_H
  ROLZ TO_DECIMAL_MOD10

  ; a = dividend - divisor
  SEC
  LDAZ TO_DECIMAL_MOD10
  SBC# $0A ; 10
  BCC td_ignore_result ; Branch if dividend < divisor
  STAZ TO_DECIMAL_MOD10

td_ignore_result
  DEX
  BNE td_divloop
  ROLZ TO_DECIMAL_VALUE_L
  ROLZ TO_DECIMAL_VALUE_H

  ; Shift result
td_shift
  LDX# $05
td_shift_loop
  LDAZ,X TO_DECIMAL_RESULT_MINUS_ONE
  STAZ,X TO_DECIMAL_RESULT
  DEX
  BNE td_shift_loop

  ; Save value into result
  LDAZ TO_DECIMAL_MOD10
  CLC
  ADC# "0"
  STAZ TO_DECIMAL_RESULT

  ; If value != 0 then continue dividing
  LDAZ TO_DECIMAL_VALUE_L
  ORAZ TO_DECIMAL_VALUE_H
  BNE td_divide

  PLA
  TAX

  RTS
