; File unclosed test: opens argv[0] but does NOT close it, exits 0
* = $0400
  JMP main
  .include asm/17/environment.asm

main:
  LDA #0
  JSR argv          ; A:X = pointer to arg 0
  JSR open          ; Opens file (handle leaked)
  LDA #0
  JMP exit

  .byte <main, >main
