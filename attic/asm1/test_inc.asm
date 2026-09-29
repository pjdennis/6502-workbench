filename
  DATA "test.txt" $00

start2
  LDA# "X"
  JSR write_d
  JMP start

  DATA start2
