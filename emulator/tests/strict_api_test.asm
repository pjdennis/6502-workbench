; --strict-api test (run with --direct-io --strict-api): a call returns
; only the flags it names (the others come back inverted), and a screen
; call changes A and Y. After each call, writes its N V Z C flags (as
; P AND $C3), then A, X and Y.
* = $0400
  JMP main
  .include 17/environment.asm

main:
  LDX #$5A
  LDY #$A5
  CLV
  SEC
  LDA #'w'
  JSR write_b          ; N V Z C were 0 0 0 1
  JSR report
  CLV
  CLC
  LDA #0
  JSR con_read         ; reads 'q': 0 0 0 0
  JSR report
  CLV
  SEC
  LDA #$10
  JSR wait_ready       ; a key is ready: A = $FF, N set (kept)
  JSR report
  CLV
  SEC
  LDA #$11
  JSR scr_cursor_off
  JSR report
  LDA #0
  JMP exit

; Write P AND $C3 as it was at the call, then A, X, Y. Preserves X, Y
report:
  PHP
  STA saved_a
  PLA
  AND #$C3
  JSR write_b
  LDA saved_a
  JSR write_b
  TXA
  JSR write_b
  TYA
  JMP write_b

saved_a: .byte 0

  .byte <main, >main
