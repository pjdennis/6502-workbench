* = $1000


  .include environment.asm


start
  LDA# <filename
  LDX# >filename
  JSR open
  STAZ FILE_HANDLE

  LDA# $09
  STAZ TO_DECIMAL_VALUE_L

loop
  LDAZ FILE_HANDLE
  JSR read
  BCS done
  JSR write_d
  JMP loop
done
  LDAZ FILE_HANDLE
  JSR close

; Show arguments
  JSR argc
  STAZ ARGC
  STAZ TO_DECIMAL_VALUE_L
  LDA# $00
  STAZ TO_DECIMAL_VALUE_H
  JSR show_decimal

  LDA# <arguments_message
  STAZ TABPL
  LDA# >arguments_message
  STAZ TABPH
  JSR show_message

  LDY# $00
arg_loop
  CPYZ ARGC
  BEQ arg_loop_done

  ; Show "  arg "
  LDA# <argument_message_prefix
  STAZ TABPL
  LDA# >argument_message_prefix
  STAZ TABPH
  JSR show_message

  ; Show argument number
  TYA
  STAZ TO_DECIMAL_VALUE_L
  LDA# $00
  STAZ TO_DECIMAL_VALUE_H
  JSR show_decimal

  ; Show ": "
  LDA# <argument_message_suffix
  STAZ TABPL
  LDA# >argument_message_suffix
  STAZ TABPH
  JSR show_message

  ; Show argument value
  TYA
  JSR argv
  STAZ TABPL
  STXZ TABPH
  JSR show_message

  ; Show "\n"
  LDA# "\n"
  JSR write_d

  INY
  JMP arg_loop

arg_loop_done

  LDA# <output_filename
  LDX# >output_filename
  JSR openout
  STAZ FILE_HANDLE

  LDA# "X"
  LDX FILE_HANDLE
  JSR write

  LDAZ FILE_HANDLE
  JSR close

  LDA# FILE_HANDLE
  STAZ TO_DECIMAL_VALUE_L
  LDA# $00
  STAZ TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA# "\n"
  JSR write_d

  LDA# <MY_LABEL
  STAZ TO_DECIMAL_VALUE_L
  LDA# >MY_LABEL
  STAZ TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA# "\n"
  JSR write_d

  LDA# <ANOTHER
  STAZ TO_DECIMAL_VALUE_L
  LDA# >ANOTHER
  STAZ TO_DECIMAL_VALUE_H
  JSR show_decimal
  LDA# "\n"
  JSR write_d

  BRK $00

output_filename          DATA "test_output.out" $00
arguments_message        DATA " arguments\n" $00
argument_message_prefix  DATA "  arg " $00
argument_message_suffix  DATA ": " $00


  .include test_inc.asm


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

  LDA# $FE

ANOTHER = MY_LABEL  ; Comment


; Show message to the error output
; On entry TABPL;TABPH points to the zero-terminated message
; On exit A, X, Y are preserved
show_message
  PHA
  TYA
  PHA
  LDY# $00
sm_loop
  LDAZ(),Y TABPL
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
  LDA# <TO_DECIMAL_RESULT
  STAZ TABPL
  LDA# >TO_DECIMAL_RESULT
  STAZ TABPH
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
  LDA# $00
  STAZ TO_DECIMAL_RESULT

to_decimal_divide
  ; Initialize the remainder to be zero
  LDA# $00
  STAZ TO_DECIMAL_MOD10
  CLC

  LDX# $10
to_decimal_divloop
  ; Rotate quotient and remainder
  ROLZ TO_DECIMAL_VALUE_L
  ROLZ TO_DECIMAL_VALUE_H
  ROLZ TO_DECIMAL_MOD10

  ; a = dividend - divisor
  SEC
  LDAZ TO_DECIMAL_MOD10
  SBC# $0A ; 10
  BCC to_decimal_ignore_result ; Branch if dividend < divisor
  STAZ TO_DECIMAL_MOD10

to_decimal_ignore_result
  DEX
  BNE to_decimal_divloop
  ROLZ TO_DECIMAL_VALUE_L
  ROLZ TO_DECIMAL_VALUE_H

  ; Shift result
to_decimal_shift
  LDX# $06
to_decimal_shift_loop
  LDAZ,X TO_DECIMAL_RESULT_MINUS_ONE
  STAZ,X TO_DECIMAL_RESULT
  DEX
  BNE to_decimal_shift_loop

  ; Save value into result
  LDAZ TO_DECIMAL_MOD10
  CLC
  ADC# "0"
  STAZ TO_DECIMAL_RESULT

  ; If value != 0 then continue dividing
  LDAZ TO_DECIMAL_VALUE_L
  ORAZ TO_DECIMAL_VALUE_H
  BNE to_decimal_divide

  RTS


  DATA start
