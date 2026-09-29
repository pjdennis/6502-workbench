M = $F000
X = $FFFF
Y = $0000

  BCC ~X


  LDA# $00

  BCC ~over

; 0
  JMP M
back
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
; 24
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
; 48
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
; 72
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
; 96
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
  JMP M
; 120
  JMP M
  JMP M
; 126
  LDA# $00
; 128
over

* = $FFE0
  BCC ~Y
