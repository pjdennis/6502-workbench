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
KEY_ENTER = $0D
KEY_BS    = $08
KEY_TAB   = $09

  .zeropage

PUSHBACK:         .byte  ; Pushback byte ($00 = none)
HAS_PUSHBACK:     .byte  ; $FF if pushback has a byte
KEY_DECODED:      .byte  ; Buffered decoded key
HAS_KEY_DECODED:  .byte  ; $FF if KEY_DECODED has a value

  .code

; Read one byte from input, with pushback support
; Returns byte in A. Preserves X, Y (read_key relies on this)
input_read_byte:
  LDA HAS_PUSHBACK
  BEQ .no_pushback
  LDA #0
  STA HAS_PUSHBACK
  LDA PUSHBACK
  RTS
.no_pushback:
  JMP io_read

; Push back one byte into the input stream
; A = byte to push back
input_unread:
  STA PUSHBACK
  LDA #$FF
  STA HAS_PUSHBACK
  RTS

; Check if input is available (non-blocking)
; Returns: A=$FF if ready, A=$00 if not
input_ready:
  LDA HAS_PUSHBACK
  BNE .ready          ; Pushback byte waiting - ready
  JSR io_ready       ; Non-blocking poll
  RTS
.ready:
  LDA #$FF
  RTS

; Count pending keys matching BUF_TEMP
; Input: BUF_TEMP = key code to match
; Returns: X = count of matching keys (0 to BATCH_MAX)
; Non-matching key is pushed back
count_pending_key:
  LDX #0
.loop:
  JSR key_ready
  CMP #$FF
  BNE .done
  JSR get_key
  CMP BUF_TEMP
  BEQ .match
  ; Push back the non-matching key
  JSR unget_key
  JMP .done
.match:
  INX
  CPX #BATCH_MAX
  BEQ .done
  JMP .loop
.done:
  RTS

; Read one key, decoding escape sequences
; Returns key code in A: KEY_* codes for special keys, bare ESC as KEY_ESC,
; $7F normalized to KEY_BS, $00 (no-op) for ignored input
; Clobbers X
read_key:
  JSR input_read_byte
  CMP #$7F
  BCC .ascii
  BEQ .del_bs
  ; Skip non-ASCII bytes (>= $80): UTF-8 multi-byte sequences
  ; would collide with the KEY_* codes
.noop:
  LDA #$00         ; Harmless: no dispatch match, not printable (< $20)
  RTS
.del_bs:
  LDA #KEY_BS
  RTS
.ascii:
  CMP #KEY_ESC
  BEQ .esc
  RTS
.esc:
  ; Got ESC - spin briefly (255 polls) for the rest of an escape sequence
  LDX #$FF
.spin:
  JSR io_ready            ; preserves X
  CMP #$FF
  BEQ .got_more
  BIT PUSHBACK            ; 3-cycle pad (zp read): keeps each poll as long as the
                          ; old DEC-counter loop (same ESC timeout)
  DEX
  BNE .spin
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
  CMP #'7'
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
; final byte, then return no-op.
.eat_loop:
  JSR input_read_byte
.eat:
  CMP #$40
  BCC .eat_loop
  BCS .noop               ; Always taken

.not_csi:
  ; SS3 sequences: ESC O <final byte> (F1-F4 on some terminals)
  CMP #'O'
  BNE .not_ss3
  JSR input_read_byte    ; Read and discard the final byte
  JMP .noop
.not_ss3:
  ; Unknown byte after ESC - push it back and return bare ESC
  JSR input_unread
  LDA #KEY_ESC
  RTS

.final_tbl:               ; ESC[A .. ESC[H
  .byte KEY_UP, KEY_DOWN, KEY_RIGHT, KEY_LEFT, $00, KEY_END, $00, KEY_HOME
.tilde_tbl:               ; ESC[1~ .. ESC[6~ ($00 = no-op)
  .byte $00, $00, KEY_DEL, $00, KEY_PGUP, KEY_PGDN

; Read one decoded key (with decoded pushback support)
; Returns key code in A. Preserves X, Y.
get_key:
  LDA HAS_KEY_DECODED
  BEQ .no_decoded
  LDA #0
  STA HAS_KEY_DECODED
  LDA KEY_DECODED
  RTS
.no_decoded:
  TXA
  PHA
  TYA
  PHA
  JSR read_key
  STA KEY_DECODED
  PLA
  TAY
  PLA
  TAX
  LDA KEY_DECODED
  RTS

; Push back one decoded key
; A = key to push back. Preserves X, Y.
unget_key:
  STA KEY_DECODED
  LDA #$FF
  STA HAS_KEY_DECODED
  RTS

; Check if a decoded key is available (non-blocking)
; Returns: A=$FF if ready, A=$00 if not. Preserves X, Y.
key_ready:
  LDA HAS_KEY_DECODED
  BNE .ready
  JSR input_ready
  CMP #$FF
  BNE .not_ready
  ; Raw input available - speculatively decode
  TXA
  PHA
  TYA
  PHA
  JSR read_key
  STA KEY_DECODED
  LDA #$FF
  STA HAS_KEY_DECODED
  PLA
  TAY
  PLA
  TAX
.ready:
  LDA #$FF
  RTS
.not_ready:
  LDA #0
  RTS
