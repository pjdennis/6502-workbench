; Terminal mode test program
; Reads bytes from serial, echoes them back, exits on Ctrl+D ($04)

* = $0400
  JMP main
  .include asm/17/environment.asm

main:
.loop:
  JSR serial_read
  BCS .loop           ; No data, keep polling

  CMP #$04            ; Ctrl+D (EOT)?
  BEQ .quit

.write:
  JSR serial_write    ; Echo the byte
  BCS .write          ; Retry if not accepted
  JMP .loop

.quit:
  LDA #$00
  JMP exit

; Reset vector: last 2 bytes of binary set entry point
  .byte <main, >main
