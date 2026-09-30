* = $1000


  .include 11/environment.asm


start
  LDA #<filename
  LDX #>filename
  JSR open
  STA FILE_HANDLE

  LDA #$09
  STA TO_DECIMAL_VALUE_L

loop
  LDA FILE_HANDLE
  JSR read
  BCS done
  JSR write_d
  JMP loop
done
  LDA FILE_HANDLE
  JSR close

; Show arguments
  JSR argc
  STA ARGC
  STA TO_DECIMAL_VALUE_L
  LDA #$00
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal

  LDA #<arguments_message
  STA TABPL
  LDA #>arguments_message
  STA TABPH
  JSR show_message

  LDY #$00
arg_loop
  CPY ARGC
  BEQ arg_loop_done

  ; Show "  arg "
  LDA #<argument_message_prefix
  STA TABPL
  LDA #>argument_message_prefix
  STA TABPH
  JSR show_message

  ; Show argument number
  TYA
  STA TO_DECIMAL_VALUE_L
  LDA #$00
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal

  ; Show ": "
  LDA #<argument_message_suffix
  STA TABPL
  LDA #>argument_message_suffix
  STA TABPH
  JSR show_message

  ; Show argument value
  TYA
  JSR argv
  STA TABPL
  STX TABPH
  JSR show_message

  ; Show "\n"
  LDA #'\n'
  JSR write_d

  INY
  JMP arg_loop

arg_loop_done

  LDA #<output_filename
  LDX #>output_filename
  JSR openout
  STA FILE_HANDLE

  LDA #'X'
  LDX FILE_HANDLE
  JSR write

  LDA FILE_HANDLE
  JSR close

  LDA #FILE_HANDLE
  STA TO_DECIMAL_VALUE_L
  LDA #$00
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA #'\n'
  JSR write_d

  LDA #<MY_LABEL
  STA TO_DECIMAL_VALUE_L
  LDA #>MY_LABEL
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA #'\n'
  JSR write_d

  LDA #<ANOTHER
  STA TO_DECIMAL_VALUE_L
  LDA #>ANOTHER
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA #'\n'
  JSR write_d

; Test local labels - two globals with same local label names
test_local_1
.value = $11               ; test_local_1.value = $11 (17 decimal)
  LDA #<.value
  STA TO_DECIMAL_VALUE_L
  LDA #>.value
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA #'\n'
  JSR write_d

test_local_2
.value = $22               ; test_local_2.value = $22 (34 decimal)
  LDA #<.value
  STA TO_DECIMAL_VALUE_L
  LDA #>.value
  STA TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA #'\n'
  JSR write_d

  BRK
  DATA $00

output_filename          DATA "out/test_output.out" $00
arguments_message        DATA " arguments\n" $00
argument_message_prefix  DATA "  arg " $00
argument_message_suffix  DATA ": " $00


  .include test_inc17.asm


  .zeropage
  .zeropage

* = $01

FILE_HANDLE                 DATA $00 ; 1 byte
TABPL                       DATA $00 ; 2 byte table pointer
TABPH                       DATA $00 ; "
ARGC                        DATA $00 ; 1 byte

  .code
  .code


MY_LABEL = $1234

  LDA #$FE

ANOTHER = MY_LABEL  ; Comment


; Show message to the error output
; On entry TABPL;TABPH points to the zero-terminated message
; On exit A, X, Y are preserved
show_message
  PHA
  TYA
  PHA
  LDY #$00
sm_loop
  LDA (TABPL),Y
  BEQ sm_done
  JSR write_d
  INY
  JMP sm_loop
sm_done
  PLA
  TAY
  PLA
  RTS


  .zeropage

TO_DECIMAL_VALUE_L          DATA $00 ; 1 byte
TO_DECIMAL_VALUE_H          DATA $00 ; 1 byte
TO_DECIMAL_RESULT_MINUS_ONE
TO_DECIMAL_MOD10            DATA $00 ; 1 byte
TO_DECIMAL_RESULT           DATA $00 $00 $00 $00 $00 $00 ; 6 bytes

  .code


; Show a decimal value to the error ouptut
; On entry TO_DECIMAL_VALUE_L;TO_DECIMAL_VALUE_H contains the value to show
; On exit A, X, Y are preserved
;         Decimal number string stored at TO_DECIMAL_RESULT
show_decimal
  PHA
  TXA
  PHA
  JSR to_decimal
  LDA #<TO_DECIMAL_RESULT
  STA TABPL
  LDA #>TO_DECIMAL_RESULT
  STA TABPH
  PLA
  TAX
  PLA
  JMP show_message ; tail call


; On entry TO_DECIMAL_VALUE_L;TO_DECIMAL_VALUE_H contains the value to convert
; On exit TO_DECIMAL_RESULT contains the result
;         Y is preserved
;         A, X are not preserved
to_decimal
  ; Initialize result to empty string
  LDA #$00
  STA TO_DECIMAL_RESULT

to_decimal_divide
  ; Initialize the remainder to be zero
  LDA #$00
  STA TO_DECIMAL_MOD10
  CLC

  LDX #$10
to_decimal_divloop
  ; Rotate quotient and remainder
  ROL TO_DECIMAL_VALUE_L
  ROL TO_DECIMAL_VALUE_H
  ROL TO_DECIMAL_MOD10

  ; a = dividend - divisor
  SEC
  LDA TO_DECIMAL_MOD10
  SBC #$0A ; 10
  BCC to_decimal_ignore_result ; Branch if dividend < divisor
  STA TO_DECIMAL_MOD10

to_decimal_ignore_result
  DEX
  BNE to_decimal_divloop
  ROL TO_DECIMAL_VALUE_L
  ROL TO_DECIMAL_VALUE_H

  ; Shift result
to_decimal_shift
  LDX #$06
to_decimal_shift_loop
  LDA TO_DECIMAL_RESULT_MINUS_ONE,X
  STA TO_DECIMAL_RESULT,X
  DEX
  BNE to_decimal_shift_loop

  ; Save value into result
  LDA TO_DECIMAL_MOD10
  CLC
  ADC #'0'
  STA TO_DECIMAL_RESULT

  ; If value != 0 then continue dividing
  LDA TO_DECIMAL_VALUE_L
  ORA TO_DECIMAL_VALUE_H
  BNE to_decimal_divide

  RTS


  DATA start
