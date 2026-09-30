; Keys as a terminal program wants them: ASCII, Enter as CR, Ctrl with a
; letter as its control code, and the special keys as the key codes of
; asm/17/environment.asm (con_read with direct_io).
;
; Requires keyboard_driver.inc (and what it requires)

KEYS_UP        = $80
KEYS_DOWN      = $81
KEYS_LEFT      = $82
KEYS_RIGHT     = $83
KEYS_HOME      = $84
KEYS_END       = $85
KEYS_PGUP      = $86
KEYS_PGDN      = $87
KEYS_DEL       = $88
KEYS_WORD_FWD  = $89            ; Ctrl+Right
KEYS_WORD_BACK = $8a            ; Ctrl+Left
KEYS_ESC       = $1b
KEYS_CR        = $0d

; The keyboard driver's codes for the special keys, and what they become
keys_special_codes:
  .byte KEY_UP,  KEY_DOWN,  KEY_LEFT,  KEY_RIGHT,  KEY_HOME,  KEY_END
  .byte KEY_PAGEUP, KEY_PAGEDOWN, KEY_DELETE, KEY_ESC
keys_special_codes_end:
keys_special_keys:
  .byte KEYS_UP, KEYS_DOWN, KEYS_LEFT, KEYS_RIGHT, KEYS_HOME, KEYS_END
  .byte KEYS_PGUP, KEYS_PGDN, KEYS_DEL,   KEYS_ESC


; On exit C set if no key is waiting, else A = the key
;         X, Y are preserved
keys_get:
  phx
.repeat:
  jsr KB_BUFFER_READ
  bcs .done                     ; Nothing waiting
  jsr keyboard_decode_and_translate
  bcs .repeat                   ; Nothing decoded so far
  jsr keyboard_lock_keys_track
  lda KEYBOARD_LATEST_META
  bit #KB_META_BREAK
  bne .repeat                   ; A key coming up
  lda KEYBOARD_LATEST_CODE
  ldx #keys_special_codes_end - keys_special_codes - 1
.find:
  cmp keys_special_codes, X
  beq .special
  dex
  bpl .find
  jsr keyboard_get_latest_ascii
  bcs .repeat                   ; No character for this key
  cmp #ASCII_LF
  bne .not_enter
  lda #KEYS_CR
.not_enter:
  cmp #'@'
  bcc .key                      ; Only @ A-Z [ \ ] ^ _ and a-z have control codes
  tax
  lda KEYBOARD_LATEST_META
  and #KB_META_CTRL
  beq .plain
  txa
  and #%00011111
  bra .key
.plain:
  txa
  bra .key
.special:
  lda keys_special_keys, X
  tax
  lda KEYBOARD_LATEST_META
  and #KB_META_CTRL
  beq .plain
  cpx #KEYS_RIGHT
  bne .not_right
  ldx #KEYS_WORD_FWD
.not_right:
  cpx #KEYS_LEFT
  bne .plain
  ldx #KEYS_WORD_BACK
  bra .plain
.key:
  clc
.done:
  plx
  rts
