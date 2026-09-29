; to_decimal.asm - Convert 16-bit value in TO_DECIMAL_VALUE16 to decimal string
;
; Requires:
;   TO_DECIMAL_VALUE16, TO_DECIMAL_MOD10, TO_DECIMAL_RESULT buffers (to_decimal.asm)
;   ROL16, TST16 macros (macros.asm)

  .zeropage

TO_DECIMAL_VALUE16:          .word       ; 2 bytes
TO_DECIMAL_MOD10:            .byte       ; 1 byte
TO_DECIMAL_RESULT:           .reserve 6  ; 6 bytes

  .code


; On entry TO_DECIMAL_VALUE16 contains the value to convert
; On exit TO_DECIMAL_RESULT contains the result
;         X, Y are preserved
;         A is not preserved
to_decimal:
  TXA
  PHA
  ; Initialize result to empty string
  LDA #$00
  STA TO_DECIMAL_RESULT

.divide:
  ; Initialize the remainder to be zero
  LDA #$00
  STA TO_DECIMAL_MOD10
  CLC

  LDX #$10
.divloop:
  ; Rotate quotient and remainder
  ROL16 TO_DECIMAL_VALUE16
  ROL TO_DECIMAL_MOD10

  ; a = dividend - divisor
  SEC
  LDA TO_DECIMAL_MOD10
  SBC #$0A ; 10
  BCC .ignore_result ; Branch if dividend < divisor
  STA TO_DECIMAL_MOD10

.ignore_result:
  DEX
  BNE .divloop
  ROL16 TO_DECIMAL_VALUE16

  ; Shift result
.shift:
  LDX #$05
.shift_loop:
  LDA TO_DECIMAL_RESULT - 1,X
  STA TO_DECIMAL_RESULT,X
  DEX
  BNE .shift_loop

  ; Save value into result
  LDA TO_DECIMAL_MOD10
  CLC
  ADC #'0'
  STA TO_DECIMAL_RESULT

  ; If value != 0 then continue dividing
  TST16 TO_DECIMAL_VALUE16
  BNE .divide

  PLA
  TAX

  RTS
