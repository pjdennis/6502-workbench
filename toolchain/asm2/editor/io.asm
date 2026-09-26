; I/O abstraction layer
;
; Provides io_write, io_read, io_flush, io_ready that map to either
; console I/O (write_b, con_read, con_flush, con_ready) or serial I/O
; depending on whether terminal_mode is defined.
; All four preserve X and Y in both builds (the console routines are
; emulator stubs that only load or store A); input.asm relies on this.

  .ifndef terminal_mode

; Console mode: direct aliases (zero overhead)
io_write = write_b
io_flush = con_flush
io_read  = con_read
io_ready = con_ready

  .else

; Terminal mode: serial I/O with spin loops

; (zero-page variables: zp.asm)

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
  BIT DSR_VALUE           ; 5-cycle pad (zp read + NOP): read_key's ESC
  NOP                     ; wait counts these polls; keep its length
  LDA #$00
  RTS

; Query terminal size via DSR (Device Status Report)
; Sends ESC[999;999H to move cursor to bottom-right (clamped by terminal)
; Then sends ESC[6n to query cursor position
; Parses response ESC[{rows};{cols}R
; Stores results in SCREEN_ROWS and SCREEN_COLS
query_terminal_size:
  ; Send ESC[999;999H (move cursor to max position, clamped by terminal)
  ; followed by ESC[6n (request cursor position)
  ; Clobbers X, Y, STR_PTR16 via write_string_ax
  LDA #<dsr_query_str
  LDX #>dsr_query_str
  JSR write_string_ax

  ; Read response: ESC[{rows};{cols}R
  JSR io_read             ; Skip ESC
  JSR io_read             ; Skip [
  JSR parse_dsr_value     ; Rows (digits up to ';')
  STA SCREEN_ROWS
  JSR parse_dsr_value     ; Cols (digits up to 'R')
  STA SCREEN_COLS
  RTS                     ; (the first render positions the cursor)

; Parse decimal digits from serial input up to and including the first
; non-digit (the ';' or 'R' of a DSR reply)
; Output: A = parsed value (mod 256)
parse_dsr_value:
  LDA #0
.next:
  STA DSR_VALUE
  JSR io_read
  EOR #'0'                ; '0'-'9' -> 0-9, any other byte -> >= 10
  CMP #10
  BCS .done
  PHA
  LDA DSR_VALUE
  ASL
  ASL
  CLC
  ADC DSR_VALUE           ; *5
  ASL                     ; *10
  STA DSR_VALUE
  PLA
  CLC
  ADC DSR_VALUE
  JMP .next
.done:
  LDA DSR_VALUE
  RTS

; DSR query: ESC[999;999H ESC[6n (no escape decoding in .byte strings,
; so ESC is a raw $1B byte; explicit $00 terminator required)
dsr_query_str:
  .byte $1B, "[999;999H", $1B, "[6n", $00

  .endif
