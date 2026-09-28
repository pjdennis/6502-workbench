; --direct-io test: screen calls come out as ANSI, and ANSI key input
; comes in as key codes. Writes the screen calls' sequences, then echoes
; two keys. Exit code 0, or 1 if a call changed X.
* = $0400
  JMP main
  .include 17/environment.asm

main:
  LDX #$5A
  LDA #3
  LDY #17
  JSR scr_goto
  JSR scr_clear_eol
  LDA #2
  JSR scr_insert
  JSR con_read
  JSR write_b
  JSR con_read
  JSR write_b
  CPX #$5A
  BNE .changed
  LDA #0
  JMP exit
.changed:
  LDA #1
  JMP exit

  .byte <main, >main
