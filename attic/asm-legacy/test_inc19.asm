filename
  .byte "test.txt", $00

start2
  LDA #'X'
  JSR write_d
  JMP start

  .word start2
