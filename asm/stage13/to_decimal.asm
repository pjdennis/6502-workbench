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
  LDA #$00
  STA TO_DECIMAL_RESULT

.divide
  ; Initialize the remainder to be zero
  LDA #$00
  STA TO_DECIMAL_MOD10
  CLC

  LDX #$10
.divloop
  ; Rotate quotient and remainder
  ROL TO_DECIMAL_VALUE_L
  ROL TO_DECIMAL_VALUE_H
  ROL TO_DECIMAL_MOD10

  ; a = dividend - divisor
  SEC
  LDA TO_DECIMAL_MOD10
  SBC #$0A ; 10
  BCC .ignore_result ; Branch if dividend < divisor
  STA TO_DECIMAL_MOD10

.ignore_result
  DEX
  BNE .divloop
  ROL TO_DECIMAL_VALUE_L
  ROL TO_DECIMAL_VALUE_H

  ; Shift result
.shift
  LDX #$05
.shift_loop
  LDA TO_DECIMAL_RESULT_MINUS_ONE,X
  STA TO_DECIMAL_RESULT,X
  DEX
  BNE .shift_loop

  ; Save value into result
  LDA TO_DECIMAL_MOD10
  CLC
  ADC #'0'
  STA TO_DECIMAL_RESULT

  ; If value != 0 then continue dividing
  LDA TO_DECIMAL_VALUE_L
  ORA TO_DECIMAL_VALUE_H
  BNE .divide

  PLA
  TAX

  RTS
