; Terminal size test: reads term_rows and term_cols, writes both to stdout
* = $0400
  JMP main
  .include asm/17/environment.asm

main:
  JSR term_rows
  JSR write_b
  JSR term_cols
  JSR write_b
  LDA #0
  JMP exit

  .byte <main, >main
