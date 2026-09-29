; SIGTSTP/SIGCONT screen restoration test program
; Writes "HELLO" to serial output, then loops waiting for input.
; Used to verify screen is redrawn after Ctrl+Z / fg.

* = $0400
  JMP main
  .include asm/17/environment.asm

main:
  ; Write "HELLO" to serial
  LDX #$00
.write_loop:
  LDA .msg,X
  BEQ .done_writing
.retry:
  JSR serial_write
  BCS .retry          ; Retry if not accepted
  INX
  JMP .write_loop

.done_writing:
  ; Now loop waiting for Ctrl+D to exit
.poll:
  JSR serial_read
  BCS .poll           ; No data, keep polling
  CMP #$04            ; Ctrl+D?
  BNE .poll
  LDA #$00
  JMP exit

.msg:
  .byte "HELLO", $00

; Reset vector
  .byte <main, >main
