; Directory Listing Test Program
; Usage: opendir_test <directory_path>
;
; Opens a directory and outputs its entries to stdout.
; Each entry is output as: metadata_hex SPACE filename NEWLINE
; On error (directory not found), outputs "ERROR\n" and exits with code 1.

* = $0200

  .zeropage

TABP16:    .word
HANDLE:    .byte
META:      .byte

  .code

  .include environment.asm
  .include macros.asm

main:
  ; Check argc >= 1 (directory path)
  JSR argc
  CMP #1
  BCC error

  ; Get directory path from argv[0]
  LDA #0
  JSR argv
  ; A;X = pointer to path string
  JSR opendir
  ; A = handle (0 if not found)
  CMP #0
  BEQ error
  STA HANDLE

read_loop:
  ; Read metadata byte
  LDA HANDLE
  JSR read
  BCS done
  STA META

  ; Output metadata as two hex digits
  LDA META
  LSR
  LSR
  LSR
  LSR
  JSR print_hex_digit
  LDA META
  AND #$0F
  JSR print_hex_digit

  ; Output space
  LDA #' '
  JSR write_b

  ; Read and output filename bytes until null
.name_loop:
  LDA HANDLE
  JSR read
  BCS done
  CMP #0
  BEQ .name_done
  JSR write_b
  JMP .name_loop
.name_done:
  ; Output newline
  LDA #'\n'
  JSR write_b
  JMP read_loop

done:
  LDA HANDLE
  JSR close
  LDA #0
  JMP exit

error:
  SET16 str_error, TABP16
  LDY #0
.loop:
  LDA (TABP16),Y
  BEQ .done
  JSR write_b
  INY
  JMP .loop
.done:
  LDA #1
  JMP exit

; Print low nibble of A as hex digit
print_hex_digit:
  AND #$0F
  CMP #$0A
  BCC .digit
  CLC
  ADC #'a'-$0A
  JSR write_b
  RTS
.digit:
  CLC
  ADC #'0'
  JSR write_b
  RTS

str_error:
  .asciiz "ERROR\n"

  .word main
