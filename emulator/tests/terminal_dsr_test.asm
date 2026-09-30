; DSR (Device Status Report) test program
; Moves cursor to bottom-right with ESC[999;999H, then sends ESC[6n,
; reads the DSR response, and echoes it via serial_write.
; The output file will contain the command sequences plus the DSR response.

* = $0400
  JMP main
  .include asm/17/environment.asm

main:
  ; Send ESC[999;999H (move cursor to bottom-right, clamped to screen size)
  LDA #$1B
  JSR .serial_write_spin
  LDA #'['
  JSR .serial_write_spin
  LDA #'9'
  JSR .serial_write_spin
  LDA #'9'
  JSR .serial_write_spin
  LDA #'9'
  JSR .serial_write_spin
  LDA #';'
  JSR .serial_write_spin
  LDA #'9'
  JSR .serial_write_spin
  LDA #'9'
  JSR .serial_write_spin
  LDA #'9'
  JSR .serial_write_spin
  LDA #'H'
  JSR .serial_write_spin

  ; Send ESC[6n (Device Status Report request)
  LDA #$1B
  JSR .serial_write_spin
  LDA #'['
  JSR .serial_write_spin
  LDA #'6'
  JSR .serial_write_spin
  LDA #'n'
  JSR .serial_write_spin

  ; Read response bytes and echo them back
  ; Response format: ESC[{rows};{cols}R
  ; Read until we get 'R' (end of DSR response)
.read_loop:
  JSR serial_read
  BCS .read_loop          ; No data, keep polling

  PHA                     ; Save the byte
  JSR .serial_write_spin  ; Echo it to output
  PLA                     ; Restore the byte

  CMP #'R'               ; End of DSR response?
  BNE .read_loop

  ; Done - exit cleanly
  LDA #$00
  JMP exit

; Spin until serial_write accepts the byte
; A = byte to write (preserved)
.serial_write_spin:
  JSR serial_write
  BCS .serial_write_spin
  RTS

; Reset vector: last 2 bytes of binary set entry point
  .byte <main, >main
