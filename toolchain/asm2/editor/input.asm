; Keyboard input library with escape sequence parsing
;
; Arrow keys are returned as high-bit codes:
KEY_UP    = $80
KEY_DOWN  = $81
KEY_LEFT  = $82
KEY_RIGHT = $83
KEY_HOME  = $84
KEY_END   = $85
KEY_PGUP  = $86
KEY_PGDN  = $87
KEY_DEL       = $88
KEY_WORD_FWD  = $89    ; Ctrl+Right (ESC[1;5C)
KEY_WORD_BACK = $8A    ; Ctrl+Left  (ESC[1;5D)
KEY_ESC   = $1B
ESC_WAIT_MS = $0064   ; 100 ms for the rest of an escape sequence: at 300
                      ; baud its next byte comes 33 ms after the ESC
KEY_ENTER = $0D
KEY_BS    = $08
KEY_TAB   = $09

; (zero-page variables: zp.asm)
; The HAS_ flags are only ever $00 or $FF: INC clears them

  .ifndef direct_io
; Read one byte from input, with pushback support
; Returns byte in A. Preserves X, Y (read_key relies on this)
input_read_byte:
  LDA PUSHBACK_COUNT
  BEQ .no_pushback
  DEC PUSHBACK_COUNT
  LDA PUSHBACK            ; Pop the top...
  PHA
  LDA PUSHBACK + 1        ; ...and move the byte below it up
  STA PUSHBACK
  PLA
  RTS
.no_pushback:
  JMP io_read

; Push back one byte into the input stream (at most two deep)
; A = byte to push back. Returns A=$FF. Preserves X, Y
input_unread:
  PHA
  LDA PUSHBACK
  STA PUSHBACK + 1
  PLA
  STA PUSHBACK
  INC PUSHBACK_COUNT
  LDA #$FF
  RTS

; Wait up to ESC_WAIT_MS for the next byte of an escape sequence.
; N set if one came in time. Clobbers X. Only called with no pushback
; pending: read_key gets an ESC from the pushback only as its last byte.
wait_esc_byte:
  LDA #<ESC_WAIT_MS
  LDX #>ESC_WAIT_MS
  JMP io_wait

  .endif

; Count and consume pending keys matching BUF_TEMP
; Input: BUF_TEMP = key code to match
; Returns: X = count of matching keys (0 to BATCH_MAX)
; A non-matching key stays buffered
count_pending_key:
  LDX #0
.loop:
  JSR key_peek
  BCC .done
  CMP BUF_TEMP
  BNE .done
  INC HAS_KEY_DECODED     ; Consume it ($FF -> $00)
  INX
  CPX #BATCH_MAX
  BNE .loop
.done:
  RTS

  .ifdef direct_io
; Read one key: con_read returns key codes itself (environment.asm).
; (Not io_read: io.asm comes later, and asm17 takes a forward symbol in
; an equate as the wrong value, without an error)
read_key = con_read
  .else
; Read one key, decoding escape sequences
; Returns key code in A: KEY_* codes for special keys, bare ESC as KEY_ESC,
; $7F normalized to KEY_BS, $00 (no-op) for ignored input
; Clobbers X; preserves Y (io_read and io_ready preserve X and Y)
read_key:
  JSR input_read_byte
  CMP #KEY_ESC
  BEQ .esc
  CMP #$7F
  BCC .done               ; Other ASCII: the key itself
  ; Skip non-ASCII bytes (>= $80): UTF-8 multi-byte sequences
  ; would collide with the KEY_* codes
  BNE .noop
  LDA #KEY_BS
  RTS
.esc:
  ; Got ESC - wait a while for the rest of an escape sequence
  JSR wait_esc_byte
  BMI .got_more
  LDA #KEY_ESC            ; Nothing followed: bare ESC
  RTS

.got_more:
  JSR input_read_byte
  CMP #'['
  BNE .not_csi
  JSR input_read_byte
  ; ESC[A-D arrows, ESC[F End, ESC[H Home (table lookup)
  CMP #'A'
  BCC .not_letter
  CMP #'H' + 1
  BCS .eat                ; Other final byte: unknown, no-op
  TAX
  LDA .final_tbl - 'A',X
  RTS
.not_letter:
  ; ESC[N~ (see .tilde_tbl), or ESC[N;5C / ESC[N;5D = Ctrl+Right / Ctrl+Left
  CMP #'1'
  BCC .eat
  CMP #'9'
  BCS .eat
  TAX                     ; X = digit (input_read_byte preserves X)
  JSR input_read_byte
  CMP #'~'
  BEQ .tilde
  CMP #';'
  BNE .eat
  JSR input_read_byte
  CMP #'5'                ; Ctrl modifier?
  BNE .eat
  JSR input_read_byte
  CMP #'C'
  BEQ .word_fwd
  CMP #'D'
  BNE .eat
  LDA #KEY_WORD_BACK
  RTS
.word_fwd:
  LDA #KEY_WORD_FWD
  RTS
.tilde:
  LDA .tilde_tbl - '1',X
  RTS

; Unknown CSI sequence: A = last byte read.  CSI final bytes are >= $40
; ('@'-'~'); parameter/intermediate bytes are < $40.  Drain through the
; final byte, or a $00 (what the console build reads at end of input),
; then return no-op.
.eat_loop:
  JSR input_read_byte
.eat:
  TAX
  BEQ .done               ; $00: no-op
  CMP #$40
  BCC .eat_loop
.noop:
  LDA #$00         ; Harmless: no dispatch match, not printable (< $20)
.done:
  RTS

.not_csi:
  ; ESC O P..S are F1-F4 (SS3) on some terminals: no-op. Anything else
  ; after ESC O, or nothing within the wait, is vi's Escape then O typed
  ; quickly: push back what followed and the O, and return a bare ESC
  CMP #'O'
  BNE .unread_esc
  JSR wait_esc_byte
  BPL .esc_then_o         ; Nothing more in time
  JSR input_read_byte
  CMP #'P'
  BCC .esc_then_byte
  CMP #'S' + 1
  BCC .noop               ; F1-F4
.esc_then_byte:
  JSR input_unread
.esc_then_o:
  LDA #'O'
.unread_esc:
  ; A byte that does not continue an escape sequence: push it back and
  ; return a bare ESC
  JSR input_unread
  LDA #KEY_ESC
  RTS

.final_tbl:               ; ESC[A .. ESC[H
  .byte KEY_UP, KEY_DOWN, KEY_RIGHT, KEY_LEFT, $00, KEY_END, $00, KEY_HOME
.tilde_tbl:               ; ESC[1~ .. ESC[8~ ($00 = no-op: 2 is Insert)
  .byte KEY_HOME, $00, KEY_DEL, KEY_END, KEY_PGUP, KEY_PGDN
  .byte KEY_HOME, KEY_END ; rxvt's 7 and 8 (1 and 4 elsewhere)
  .endif

; Check for a decoded key without consuming it (non-blocking)
; Returns: C=1 and A = key if one is available (it stays buffered;
;          INC HAS_KEY_DECODED consumes it), C=0 if not. Preserves X, Y.
key_peek:
  LDA HAS_KEY_DECODED
  BNE .have
  LDA PUSHBACK_COUNT
  BNE .decode
  JSR io_ready
  CMP #$FF
  BNE .none               ; C=0 (A < $FF)
.decode:
  JSR decode_key
.have:
  LDA KEY_DECODED
  SEC
.none:
  RTS

; Flush output, then wait for a key (get_key)
flush_get_key:
  JSR io_flush
  ; fall through

; Read one decoded key (blocking). Returns key code in A. Preserves X, Y.
; The console build exits instead if the read hit end of input, so no
; loop that waits for a key (a ':' or '/' prompt) spins forever
get_key:
  LDA HAS_KEY_DECODED
  BNE .have
  JSR decode_key
.have:
  INC HAS_KEY_DECODED     ; Consume it ($FF -> $00)
  .ifndef terminal_mode
  JSR exit_at_eof
  .endif
  LDA KEY_DECODED
  RTS

; Decode the next key (blocking) into the decoded-key buffer
; Preserves X, Y (read_key leaves Y alone)
decode_key:
  TXA
  PHA
  JSR read_key
  STA KEY_DECODED
  PLA
  TAX
  LDA KEY_DECODED
  ; fall through

; Push back one decoded key
; A = key to push back. Preserves X, Y.
unget_key:
  STA KEY_DECODED
  LDA #$FF
  STA HAS_KEY_DECODED
  RTS
