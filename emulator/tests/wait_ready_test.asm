; wait_ready test (standard mode): waits for each input byte and echoes it,
; writing each wait_ready result first, until a wait does not return $FF.
; Exit code 0, or 1 if the call changed X or Y.
* = $0400
  JMP main
  .include 17/environment.asm

main:
  LDY #$42
  LDA #$64               ; 100 ms
  LDX #$00
  JSR wait_ready
  JSR write_b            ; the result
  CPY #$42
  BNE .changed
  CPX #$00
  BNE .changed
  CMP #$FF
  BNE .done              ; timed out or input ended
  JSR con_read
  JSR write_b
  JMP main
.done:
  LDA #0
  JMP exit
.changed:
  LDA #1
  JMP exit

  .byte <main, >main
