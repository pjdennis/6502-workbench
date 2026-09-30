SUBROUTINE
  LDAZ $42
  RTS

START ; This is a comment
  LDX# $00 ; another comment
LOOP
  INX ; and a comment
  JMP LOOP ; Comment

  DATA "A\"\\B"
  DATA $42 $43
  DATA START
