; File read test: opens argv[0], reads all bytes to stdout, closes, exits
* = $0400
  JMP main
  .include asm/17/environment.asm

HANDLE = $00

main:
  LDA #0
  JSR argv          ; A:X = pointer to arg 0
  JSR open          ; A = file handle
  STA HANDLE

.read_loop:
  LDA HANDLE
  JSR read
  BCS .done
  JSR write_b
  JMP .read_loop

.done:
  LDA HANDLE
  JSR close
  LDA #0
  JMP exit

  .byte <main, >main
