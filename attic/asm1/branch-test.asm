M = $F000
near_start = $0010
near_end   = $FFE0

  BCC ~near_end

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
; 123
  LDA# $00
  LDA# $00
; 127
over
  LDA# $00
  BCC ~back

* = $FFE0
  BCC ~near_start
