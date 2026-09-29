; wait_ready test (terminal mode, input "AB"): waits up to 1 s for 'A', then
; 10 ms and 50 ms for 'B', then 1 s once the input has ended. Writes each
; wait_ready result, and each byte it reads, to serial output.
* = $0400
  JMP main
  .include asm/17/environment.asm

main:
  LDA #$E8               ; 1000 ms
  LDX #$03
  JSR wait_ready
  JSR out
  JSR serial_read
  JSR out
  LDA #$0A               ; 10 ms
  LDX #$00
  JSR wait_ready
  JSR out
  LDA #$32               ; 50 ms
  LDX #$00
  JSR wait_ready
  JSR out
  JSR serial_read
  JSR out
  LDA #$E8               ; 1000 ms
  LDX #$03
  JSR wait_ready
  JSR out
  LDA #0
  JMP exit

; Write A to serial output, retrying while the buffer is full
out:
  JSR serial_write
  BCS out
  RTS

  .byte <main, >main
