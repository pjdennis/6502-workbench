; File write test: opens argv[0] for writing, writes stdin bytes to it, closes, exits
* = $0400
  JMP main
  .include asm/17/environment.asm

HANDLE = $00

main:
  LDA #0
  JSR argv          ; A:X = pointer to arg 0
  JSR openout       ; A = file handle
  STA HANDLE

.write_loop:
  JSR read_b
  BCS .done
  LDX HANDLE
  JSR write
  JMP .write_loop

.done:
  LDA HANDLE
  JSR close
  LDA #0
  JMP exit

  .byte <main, >main
