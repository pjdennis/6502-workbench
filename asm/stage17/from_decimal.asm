; Convert decimal string to 16-bit value
;
; Requires:
;   CURR_CHAR          - zero page location for current character
;   read_char          - function to read next character
;   err_value_out_of_range - error handler for overflow

  .zeropage

FROM_DECIMAL16:          .data $0000 ; 2-byte accumulator for value being built
FROM_DECIMAL_TMP16:      .data $0000 ; 2-byte temp for multiply-by-10

  .code


; Convert decimal digit string to 16-bit value
; On entry: CURR_CHAR contains first digit character ('0'-'9')
; On exit: FROM_DECIMAL16 contains 16-bit result
;          C=0 if value <= 255, C=1 if > 255
;          CURR_CHAR contains first non-digit character
;          X is preserved
;          A, Y are not preserved
; Raises 'Value out of range' error if value > 65535
from_decimal:
  ; Initialize accumulator to 0
  LDA #$00
  STA_LH16 FROM_DECIMAL16
.loop:
  ; Multiply FROM_DECIMAL16 by 10 using: temp=val; val<<=2; val+=temp; val<<=1
  ; Step 1: temp = val
  CP16 FROM_DECIMAL16 FROM_DECIMAL_TMP16
  ; Step 2: val <<= 1
  ASL16 FROM_DECIMAL16
  BCS .overflow
  ; Step 3: val <<= 1 (now val = original * 4)
  ASL16 FROM_DECIMAL16
  BCS .overflow
  ; Step 4: val += temp (now val = original * 4 + original = original * 5)
  CLC
  ADC16 FROM_DECIMAL16 FROM_DECIMAL_TMP16 FROM_DECIMAL16
  BCS .overflow
  ; Step 5: val <<= 1 (now val = original * 10)
  ASL16 FROM_DECIMAL16
  BCS .overflow
  ; Add current digit to accumulator
  LDA CURR_CHAR
  SEC
  SBC #'0'              ; Convert ASCII digit to value 0-9
  CLC
  ADCA16 FROM_DECIMAL16 FROM_DECIMAL16
  BCS .overflow
  ; Read next character
  JSR read_char
  ; Check if it's a digit
  CMP #'0'
  BCC .done             ; < '0', not a digit
  CMP #'9'+$01
  BCC .loop             ; >= '0' and <= '9', continue
.done:
  ; Set carry based on value size: C=0 if <= 255, C=1 if > 255
  LDA FROM_DECIMAL16+$01
  BEQ .one_byte
  SEC                   ; Value > 255
  RTS
.one_byte:
  CLC                   ; Value <= 255
  RTS
.overflow:
  JMP err_value_out_of_range
