; bbcbplus test: print a line through OSWRCH and OSNEWL, then return
; (the run ends with exit status 0). Loaded at PAGE ($1900).

oswrch: = $FFEE
osnewl: = $FFE7

* = $1900
start:
  LDX #$00
.loop:
  LDA msg,X
  BEQ .done
  JSR oswrch
  INX
  BNE .loop
.done:
  JSR osnewl
  RTS
msg:
  .asciiz "Hello, B+"
