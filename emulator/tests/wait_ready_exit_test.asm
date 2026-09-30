; wait_ready test (console mode): waits up to 200 ms for a key and exits with
; the result as the exit code ($FF ready, $00 timed out, $01 input ended)
* = $0400
  JMP main
  .include asm/17/environment.asm

main:
  LDA #$C8               ; 200 ms
  LDX #$00
  JSR wait_ready
  JMP exit

  .byte <main, >main
