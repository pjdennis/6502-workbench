; I/O abstraction layer
;
; Provides io_write, io_read, io_flush, io_ready that map to either
; console I/O (write_b, con_read, con_flush, con_ready) or serial I/O
; depending on whether terminal_mode is defined, and io_wait (wait_ready,
; which waits on whichever input the emulator runs with).
; All five preserve X and Y in both builds (environment.asm);
; input.asm relies on this. Only the flags their calls name are
; defined on return.

; Wait up to A;X ms for an input byte: A=$FF (N set) if one is ready,
; $00 if the time passed, CON_EOF at end of console input. In the terminal
; build it only looks at serial input, so it is only called with no
; pushback pending (io_ready moves a byte into the pushback).
io_wait = wait_ready

  .ifndef terminal_mode

; Console mode: direct aliases (zero overhead)
io_write = write_b
io_flush = con_flush
io_read  = con_read
io_ready = con_ready

  .else

; Terminal mode: serial I/O with spin loops

; Write byte in A to serial output (blocking spin loop)
; A, X, Y preserved (same contract as write_b)
io_write:
  JSR serial_write
  BCS io_write
  RTS

; Flush - no-op for serial (data is sent immediately)
io_flush:
  RTS

; Read one byte from serial input (blocking)
; Returns byte in A. Preserves X, Y
; A byte seen by io_ready waits in input.asm's pushback, which
; input_read_byte checks before calling here.
io_read:
  JSR serial_read
  BCS io_read
  RTS

; Non-blocking check if input byte is available
; Returns: A=$FF if ready (the byte is handed to input_unread),
; A=$00 if not. Only called with no pushback pending. Preserves X, Y
io_ready:
  JSR serial_read
  BCS .not_ready
  JMP input_unread        ; Returns A=$FF
.not_ready:
  LDA #$00
  RTS

; Query terminal size via DSR (Device Status Report)
; Sends ESC[255;255H to move cursor to bottom-right (clamped by terminal)
; Then sends ESC[6n to query cursor position
; Parses response ESC[{rows};{cols}R into SCREEN_ROWS and SCREEN_COLS
; (adjacent in zp.asm, indexed by X), and sets TEXT_ROWS = SCREEN_ROWS - 1
; Asking for 255 (not 999) caps each value at 255, which fits a byte: a
; bigger terminal gets 255 rows or cols, not its size mod 256, and no step
; of value * 10 + digit carries.
; Each ESC starts the parse again, and it ends only at an 'R' after two
; runs of digits split by a ';', so keys typed before the reply arrives
; are dropped rather than read as the size.  So are those of a reply's
; shape with one row, which no screen has: xterm's F3 with a modifier
; (ESC[1;2R is Shift-F3); one with more rows is still taken as the size.
; Clobbers X, Y, STR_PTR16 via write_string_ax
query_terminal_size:
  LDA #<dsr_query_str
  LDX #>dsr_query_str
  JSR write_string_ax
.restart:
  LDX #0                  ; X = 0: SCREEN_ROWS, 1: SCREEN_COLS
.next_value:
  LDA #0
.store:
  STA SCREEN_ROWS,X
.read:
  JSR io_read             ; (preserves X)
  EOR #'0'                ; '0'-'9' -> 0-9, any other byte -> >= 10
  CMP #10
  BCS .not_digit
  PHA                     ; value = value * 10 + digit (C = 0 throughout)
  LDA SCREEN_ROWS,X
  ASL
  ASL
  ADC SCREEN_ROWS,X       ; *5
  ASL                     ; *10
  STA SCREEN_ROWS,X
  PLA
  ADC SCREEN_ROWS,X
  BCC .store              ; (always, for a reply)
.not_digit:
  CMP #$2B                ; ESC ($1B EOR '0'): a reply starts
  BEQ .restart
  LDY SCREEN_ROWS,X
  BEQ .read               ; no digits yet: skip '[' and typed-ahead keys
  CMP .ends,X             ; ';' ends the rows, 'R' the cols
  BNE .restart            ; else typed-ahead keys, not the reply
  INX
  CPX #2
  BNE .next_value
  LDX SCREEN_ROWS
  DEX
  BEQ .restart            ; One row: a key (xterm's F3), not the reply
  STX TEXT_ROWS           ; Text rows above the status bar
  RTS                     ; (the first render positions the cursor)
.ends:
  .byte $0B, $62          ; ';' and 'R' (EOR '0')

; DSR query: ESC[255;255H ESC[6n (no escape decoding in .byte strings,
; so ESC is a raw $1B byte; explicit $00 terminator required)
dsr_query_str:
  .byte $1B, "[255;255H", $1B, "[6n", $00

  .endif
