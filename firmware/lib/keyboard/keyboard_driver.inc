; Requires:
;   KB_BUFFER_INITIALIZE - funciton to initialize the keyboard buffer
;   KB_BUFFER_WRITE      - function to call to write to keyboard buffer
;   KB_BUFFER_READ       - function to call to read from keyboard buffer
;   copy_memory and CP_M_* parameter locations
;   INTERRUPT_ROUTINE    - location to which keyboard interrupt handler is copied
;   KB_ZERO_PAGE_BASE    - location in zero page for variables
;
; Optional:
;   callback_key_left    - callback when left arrow pressed
;   callback_key_right   - callback when right arrow pressed
;   callback_key_up      - callback when up arrow pressed
;   callback_key_down    - callback when down arrow pressed
;   callback_key_esc     - callback when Escape pressed
;   callback_key_delete  - callback when Delete pressed
;   callback_key_pageup  - callback when Page Up pressed
;   callback_key_pagedown - callback when Page Down pressed
;   callback_key_f1      - callback when F1 pressed
;   callback_kb_trace    - called at each step of keyboard_send_command, for diagnostics:
;                          'a' starting, 'b' clock pulled low, 'c' byte sent to shift register,
;                          'd' keyboard clocked the byte in, 'w' repeatedly while waiting for
;                          the ACK, 'e' ACK received.
;                          On entry A = step, X = command byte. Must preserve X and Y.

; Calls callback_kb_trace, if defined, with A = step
; On exit A, X, Y are preserved
  .macro kb_trace,step
  .ifdef callback_kb_trace
  pha
  lda #\step
  jsr callback_kb_trace
  pla
  .endif
  .endm

  .ifndef KEYBOARD_RATE_AND_DELAY
KEYBOARD_RATE_AND_DELAY = KEYBOARD_RATE_30_0_CPS | KEYBOARD_DELAY_0_50_S
  .endif

TRANSLATE_TABLE          = KB_ZERO_PAGE_BASE + $00 ; 2 bytes
KEYBOARD_RECEIVING       = KB_ZERO_PAGE_BASE + $02 ; 1 byte
KEYBOARD_DECODE_STATE    = KB_ZERO_PAGE_BASE + $03 ; 1 byte
KEYBOARD_LOCK_STATE      = KB_ZERO_PAGE_BASE + $04 ; 1 byte
KEYBOARD_MODIFIER_STATE  = KB_ZERO_PAGE_BASE + $05 ; 1 byte
KEYBOARD_LATEST_META     = KB_ZERO_PAGE_BASE + $06 ; 1 byte
KEYBOARD_LATEST_CODE     = KB_ZERO_PAGE_BASE + $07 ; 1 byte
SENDING_TO_KEYBOARD      = KB_ZERO_PAGE_BASE + $08 ; 1 byte
ACK_RECEIVED             = KB_ZERO_PAGE_BASE + $09 ; 1 byte
KB_ZERO_PAGE_STOP        = KB_ZERO_PAGE_BASE + $0A

KB_DECODE_BREAK          = %00010000
KB_DECODE_EXTENDED       = %00001000
KB_DECODE_PAUSE_SEQ      = %00000111

KB_CAPS_LOCK_ON          = %00000001
KB_SCROLL_LOCK_ON        = %00000010
KB_NUM_LOCK_ON           = %00000100
KB_CAPS_LOCK_DOWN        = %00001000
KB_SCROLL_LOCK_DOWN      = %00010000
KB_NUM_LOCK_DOWN         = %00100000

KB_MOD_L_SHIFT           = %10000000
KB_MOD_R_SHIFT           = %01000000
KB_MOD_L_CTRL            = %00100000
KB_MOD_R_CTRL            = %00010000
KB_MOD_L_ALT             = %00001000
KB_MOD_R_ALT             = %00000100
KB_MOD_L_GUI             = %00000010
KB_MOD_R_GUI             = %00000001

KB_COMMAND_SET_LEDS      = $ed
KB_COMMAND_ECHO          = $ee
KB_COMMAND_READ_ID       = $f2
KB_COMMAND_SET_TYPEMATIC = $f3
KB_COMMAND_ENABLE        = $f4
KB_COMMAND_RESET         = $ff
KB_COMMAND_ACK           = $fa

KB_LED_SCROLL_LOCK       = %00000001
KB_LED_NUM_LOCK          = %00000010
KB_LED_CAPS_LOCK         = %00000100

KB_CODE_BREAK            = $f0
KB_CODE_EXTENDED         = $e0
KB_CODE_EXTENDED_PAUSE   = $7e       ; Extended code for Break (Ctrl+Pause). The extended
                                     ; translation table maps it to KEY_PAUSE.
KB_CODE_EXTENDED_IGNORE  = $12       ; Part of the print screen codes. Also part of the codes generated
                                     ; by stand-alone navigation keys such as home, when numlock is on.
KB_META_SHIFT            = %10000000
KB_META_CTRL             = %01000000
KB_META_ALT              = %00100000
KB_META_GUI              = %00010000
KB_META_EXTENDED         = %00000010
KB_META_BREAK            = %00000001

  .include key_translation_tables.inc

; Code sequence for the pause/break key
kb_seq_pause        .byte $e1, $14, $77, $e1, $f0, $14, $f0, $77, $00

; Mapping from lock keys to the bit mask used for tracking lock down/up and on/off
kb_lock_codes:      .byte KEY_CAPSLOCK,      KEY_SCROLLLOCK,      KEY_NUMLOCK,     $00
kb_lock_on_masks:   .byte KB_CAPS_LOCK_ON,   KB_SCROLL_LOCK_ON,   KB_NUM_LOCK_ON,  $00
kb_lock_down_masks: .byte KB_CAPS_LOCK_DOWN, KB_SCROLL_LOCK_DOWN, KB_NUM_LOCK_DOWN
kb_lock_to_led:     .byte KB_LED_CAPS_LOCK,  KB_LED_SCROLL_LOCK,  KB_LED_NUM_LOCK

; Mapping from modifier keys to the bit mask used for tracking modifier states
kb_modifier_codes:  .byte KEY_LEFTSHIFT,   KEY_RIGHTSHIFT,  KEY_LEFTCTRL,   KEY_RIGHTCTRL
                    .byte KEY_LEFTALT,     KEY_RIGHTALT,    KEY_LEFTMETA,   KEY_RIGHTMETA, $00
kb_modifier_masks:  .byte KB_MOD_L_SHIFT,  KB_MOD_R_SHIFT,  KB_MOD_L_CTRL,  KB_MOD_R_CTRL
                    .byte KB_MOD_L_ALT,    KB_MOD_R_ALT,    KB_MOD_L_GUI,   KB_MOD_R_GUI

; Mapping from the modifier state masks for left/right modifier keys to the mask used to
; indicate at least one of the keys is pressed
kb_modifier_from:   .byte (KB_MOD_L_SHIFT | KB_MOD_R_SHIFT), (KB_MOD_L_CTRL | KB_MOD_R_CTRL)
                    .byte (KB_MOD_L_ALT   | KB_MOD_R_ALT),   (KB_MOD_L_GUI  | KB_MOD_R_GUI), $00
kb_modifier_to      .byte KB_META_SHIFT,                     KB_META_CTRL
                    .byte KB_META_ALT,                       KB_META_GUI

keyboard_initialize:
  jsr KB_BUFFER_INITIALIZE

  ; Initialize Keyboard decode state
  stz KEYBOARD_DECODE_STATE
  stz KEYBOARD_MODIFIER_STATE
  stz KEYBOARD_LOCK_STATE

  .ifndef KB_NO_INTERRUPT_HANDLER
  ; Relocate the interrupt handler. The EEPROM has a fixed address, INTERRUPT_ROUTINE
  ; for the interrupt routine so copy the handler there
  invoke_copy_memory INTERRUPT_ROUTINE,interrupt,interrupt_end
  .endif

  ; Initialize flags
  stz KEYBOARD_RECEIVING
  stz SENDING_TO_KEYBOARD
  stz ACK_RECEIVED

  ; Set up interrupts for detecting start of receipt of byte from keyboard
  lda #PCR_CA2_IND_NEG_E
  sta PCR

  lda #%10000001  ; Enable CA2 interrupt
  sta IER

  ; Enable interrupts so we start recieving data from the keyboard
  cli

  ; Initialize keyboard
  lda #KB_COMMAND_ENABLE
  jsr keyboard_send_command

  lda #KB_COMMAND_SET_TYPEMATIC
  jsr keyboard_send_command

  lda #KEYBOARD_RATE_AND_DELAY
  jsr keyboard_send_command

  lda #KB_NUM_LOCK_ON
  sta KEYBOARD_LOCK_STATE
  jsr update_lock_leds

  rts


; On exit Carry set if no result so far
;         A contains the next char
;         X, Y are preserved
keyboard_get_char:
.repeat:
  jsr KB_BUFFER_READ
  bcs .done                     ; Exit when input buffer is empty
  jsr keyboard_decode_and_translate
  bcs .repeat                   ; Nothing decoded so far so read more
  jsr keyboard_lock_keys_track
  lda KEYBOARD_LATEST_META
  bit #KB_META_BREAK
  bne .repeat                   ; Decoded key up event; ignore these so read more
  jsr handle_special_keys
  bcs .repeat                   ; Movement key handled; read more
  jsr keyboard_get_latest_ascii
  bcs .repeat                   ; No translation for code; ignore these so read more
.done:
  rts


; On entry KEYBOARD_LATEST_CODE contains the latest key code
; On exit  C is set if key was handled
;          A is not preserved
;          X, Y are preserved
handle_special_keys:
  lda KEYBOARD_LATEST_CODE

  .ifdef callback_key_left
  cmp #KEY_LEFT
  beq .key_left
  .endif

  .ifdef callback_key_right
  cmp #KEY_RIGHT
  beq .key_right
  .endif

  .ifdef callback_key_up
  cmp #KEY_UP
  beq .key_up
  .endif

  .ifdef callback_key_down
  cmp #KEY_DOWN
  beq .key_down
  .endif

  .ifdef callback_key_esc
  cmp #KEY_ESC
  beq .key_esc
  .endif

  .ifdef callback_key_delete
  cmp #KEY_DELETE
  beq .key_delete
  .endif

  .ifdef callback_key_pageup
  cmp #KEY_PAGEUP
  beq .key_pageup
  .endif

  .ifdef callback_key_pagedown
  cmp #KEY_PAGEDOWN
  beq .key_pagedown
  .endif

  .ifdef callback_key_f1
  cmp #KEY_F1
  beq .key_f1
  .endif

  lda KEYBOARD_LOCK_STATE
  bit #KB_NUM_LOCK_ON
  beq .check_keypad

  lda KEYBOARD_LATEST_META
  bit #KB_META_SHIFT
  beq .not_handled

.check_keypad:
  lda KEYBOARD_LATEST_CODE
  cmp #KEY_KP4
  beq .key_left
  cmp #KEY_KP6
  beq .key_right

.not_handled:
  clc
  rts                      ; Return - not handled

.key_left:
  .ifdef callback_key_left
  jsr callback_key_left
  .endif
  bra .handled

.key_right:
  .ifdef callback_key_right
  jsr callback_key_right
  .endif
  bra .handled

.key_up:
  .ifdef callback_key_up
  jsr callback_key_up
  .endif
  bra .handled

.key_down:
  .ifdef callback_key_down
  jsr callback_key_down
  .endif
  bra .handled

.key_esc:
  .ifdef callback_key_esc
  jsr callback_key_esc
  .endif
  bra .handled

  .ifdef callback_key_delete
.key_delete:
  jsr callback_key_delete
  bra .handled
  .endif

  .ifdef callback_key_pageup
.key_pageup:
  jsr callback_key_pageup
  bra .handled
  .endif

  .ifdef callback_key_pagedown
.key_pagedown:
  jsr callback_key_pagedown
  bra .handled
  .endif

.key_f1:
  .ifdef callback_key_f1
  jsr callback_key_f1
  .endif

.handled:
  sec
  rts                      ; Return - handled


; On entry KEYBOARD_LATEST_META contains shift state
;          KEYBOARD_LATEST_CODE contains current key code
; On exit  Carry set if no translation
;          A contains translated code if translation occurred
keyboard_get_latest_ascii:
  phx
  phy

  lda KEYBOARD_LATEST_CODE
  and #%11000000
  cmp #%10000000
  bne .check_main_ascii

  lda KEYBOARD_LATEST_CODE
  and #%01111111
  cmp #'0'
  bcs .check_numlock
  cmp #'.'
  bne .translate_kp

.check_numlock:
  lda KEYBOARD_LOCK_STATE
  bit #KB_NUM_LOCK_ON
  beq .check_main_ascii

  lda KEYBOARD_LATEST_META
  bit #KB_META_SHIFT
  bne .check_main_ascii

.translate_kp:
  lda KEYBOARD_LATEST_CODE
  and #%01111111
  clc
  bra .done

.check_main_ascii:
  lda KEYBOARD_LATEST_CODE
  sec
  bit #%10000000
  bne .done

  tax
  lda KEYBOARD_LATEST_META
  bit #KB_META_SHIFT
  bne .translate_shifted
  lda KEYBOARD_LOCK_STATE
  bit #KB_CAPS_LOCK_ON
  bne .translate_to_upper
; Unshifted
  txa
  bra .translated
.translate_shifted:
  txa
  ldx #<kb_shift_translation_table
  ldy #>kb_shift_translation_table
  jsr code_translate
  tax
.translate_to_upper:
  txa
  cmp #'a'
  bcc .translated
  cmp #('z' + 1)
  bcs .translated
  sec
  sbc #('a' - 'A')
.translated
  clc ; translation found
.done:
  ply
  plx
  rts


; On entry A contains the byte from the keyboard
; On exit Carry set if no result so far
;         A is the latest translated key code if found
;         X, Y are preserved
;         KEYBOARD_LATEST_META contains metadata for latest key event
;         KEYBOARD_LATEST_CODE contains code for latest key event
keyboard_decode_and_translate:
  jsr keyboard_decode
  bcs .decode_done              ; No data so we are done
  lda KEYBOARD_LATEST_META
  bit #KB_META_EXTENDED
  bne .decode_extended
; Decode normal
  lda KEYBOARD_LATEST_CODE
  jsr keyboard_translate_normal
  bra .translate_done
.decode_extended:
  and #~KB_META_EXTENDED
  sta KEYBOARD_LATEST_META
  lda KEYBOARD_LATEST_CODE
  jsr keyboard_translate_extended
.translate_done:
  bcs .decode_done ; No translation
; Code found
  sta KEYBOARD_LATEST_CODE
  jsr keyboard_modifier_track
  jsr keyboard_update_modifiers
  clc
.decode_done:
  rts


; On entry KEYBOARD_LATEST_META contains latest state (make/break)
;          KEYBOARD_LATEST_CODE contains latest key code
;          KEYBOARD_LOCK_STATE contains current state of lock keys
; On exit  KEYBOARD_LOCK_STATE contains the new state of lock keys
;          A, X, Y are preserved
keyboard_lock_keys_track:
  pha
  phx
  ldx #$ff
.repeat
  inx
  lda kb_lock_codes, X
  beq .done
  cmp KEYBOARD_LATEST_CODE
  bne .repeat
; Code found
  lda KEYBOARD_LATEST_META
  bit #KB_META_BREAK
  bne .key_break
; Key make
  lda kb_lock_down_masks, X
  bit KEYBOARD_LOCK_STATE
  bne .done                    ; Nothing to do - key was already down
; Key going down
  tsb KEYBOARD_LOCK_STATE      ; Set the 'down' flag
  lda kb_lock_on_masks, X
  eor KEYBOARD_LOCK_STATE      ; Toggle the 'on' flag
  sta KEYBOARD_LOCK_STATE
  jsr update_lock_leds
  bra .done
.key_break:
  lda kb_lock_down_masks, X
  trb KEYBOARD_LOCK_STATE
.done:
  plx
  pla
  rts


; On entry KEYBOARD_LOCK_STATE contains the current state of lock keys
; On exit  A, X, Y are preserved
update_lock_leds:
  pha
  phx
  phy
  ldy #0                        ; Y stores the keyboard LED mask
  ldx #$ff
.repeat
  inx
  lda kb_lock_on_masks, X
  beq .set_leds
  bit KEYBOARD_LOCK_STATE
  beq .repeat
; LED on
  tya
  ora kb_lock_to_led, X
  tay
  bra .repeat
.set_leds:
  tya
  jsr keyboard_set_leds
  ply
  plx
  pla
  rts


; On entry KEYBOARD_LATEST_META contains latest state (make/break)
;          KEYBOARD_LATEST_CODE contains latest key code
;          KEYBOARD_MODIFIER_STATE contains the current state of modifier keys
; On exit  KEYBOARD_MODIFIER_STATE contains the updated state of modifier keys
;          A, X, Y are preserverd
keyboard_modifier_track:
  pha
  phx
  ldx #$ff
.repeat:
  inx
  lda kb_modifier_codes, X
  beq .done
  cmp KEYBOARD_LATEST_CODE
  bne .repeat
; Code found
  lda KEYBOARD_LATEST_META
  bit #KB_META_BREAK
  bne .key_break
; Key make
  lda kb_modifier_masks, X
  tsb KEYBOARD_MODIFIER_STATE
  bra .done
.key_break:
  lda kb_modifier_masks, X
  trb KEYBOARD_MODIFIER_STATE
.done:
  plx
  pla
  rts


; On entry KEYBOARD_MODIFIER_STATE contains the current state of modifiers
;          KEYBOARD_LATEST_META contains current meta state without modifiers
; On exit  KEYBOARD_LATEST_META contains new meta state with modifiers
;          A, X, Y are preserved
keyboard_update_modifiers:
  pha
  phx
  ldx #$ff
.repeat:
  inx
  lda kb_modifier_from, X
  beq .done
  bit KEYBOARD_MODIFIER_STATE
  beq .key_break
; Key make
  lda kb_modifier_to, X
  tsb KEYBOARD_LATEST_META
  bra .repeat
.key_break:
  lda kb_modifier_to, X
  trb KEYBOARD_LATEST_META
  bra .repeat
.done:
  plx
  pla
  rts


; On entry  A contains the byte from the keyboard
;           KEYBOARD_DECODE_STATE contains the current state of the decode state machine
; On exit   Carry set if no result so far
;           X, Y are preserved
;           A is not preserved
;           KEYBOARD_LATEST_META contains metadata for latest key event
;           KEYBOARD_LATEST_CODE contains code for latest key event
; Variables KEYBOARD_DECODE_STATE is utlilized and then updated with the new state
keyboard_decode:
  phx
  tax                          ; X <- latest byte from keyboard
  ; Branch to the handler code for the current state
  lda KEYBOARD_DECODE_STATE
  bit #KB_DECODE_PAUSE_SEQ
  bne .state_pause
  bit #KB_DECODE_BREAK
  bne .state_break
  bit #KB_DECODE_EXTENDED
  bne .state_extended
  ; Fall through to the initial state (waiting for first byte of sequence)
.state_waiting:
  cpx #KB_CODE_BREAK
  beq .to_break
  cpx #KB_CODE_EXTENDED
  beq .to_extended
  cpx kb_seq_pause             ; The first value in the pause key sequence
  beq .to_pause
  ; No special codes identified so current byte is a single byte sequence
  lda #0                       ; Emit non-extended make code
  bra .emit

; ---- Handlers for the states ----

; The pause state indicates we are recieving the 8 byte pause sequence
; A = current KEYBOARD_DECODE_STATE
.state_pause:
  and #KB_DECODE_PAUSE_SEQ
  phx                          ; Stack <- latest byte from keyboard
  tax                          ; X <- index of current code in sequence
  pla                          ; A <- latest byte from keyboard
  cmp kb_seq_pause, X
  bne .pause_error
  inx
  lda kb_seq_pause, X
  beq .pause_emit               ; Branch if we reached the last code in sequence
  txa                           ; New pause seq index becomes new state
  bra .no_emit
.pause_emit:
  lda #KB_META_EXTENDED         ; Emit pause as the extended make code for Break, since
  ldx #KB_CODE_EXTENDED_PAUSE   ; it is translated from a PS/2 code like any other key
  bra .emit
; A = latest byte from keyboard
.pause_error:
  ; Reset state and reprocess with the current code
  tax
  lda #0
  sta KEYBOARD_DECODE_STATE
  bra .state_waiting

.state_break:
  bit #KB_DECODE_EXTENDED
  bne .state_extended_break
  lda #KB_META_BREAK             ; Emit non-extended break code
  bra .emit

.state_extended:
  cpx #KB_CODE_BREAK
  beq .to_extended_break
  cpx #KB_CODE_EXTENDED_IGNORE
  beq .ignore
  lda #KB_META_EXTENDED
  bra .emit

.state_extended_break:
  cpx #KB_CODE_EXTENDED_IGNORE
  beq .ignore
  lda #(KB_META_BREAK | KB_META_EXTENDED)
  bra .emit

; ---- State transitions ----

.to_break:
  lda #KB_DECODE_BREAK
  bra .no_emit

.to_extended:
  lda #KB_DECODE_EXTENDED
  bra .no_emit

.to_extended_break:
  lda #(KB_DECODE_EXTENDED | KB_DECODE_BREAK)
  bra .no_emit

.to_pause:
  lda #%00000001                 ; Start pause sequence counter at 1
  bra .no_emit

; ---- Exiting the routine with result or no result ----

; A = Metadata
; X = code
.emit:
  sta KEYBOARD_LATEST_META
  stx KEYBOARD_LATEST_CODE
  stz KEYBOARD_DECODE_STATE
  clc
  bra .done

; Ignore current code and go back to initial state
.ignore:
  lda #0
  ; Fall through

; A = new decode state
.no_emit:
  sta KEYBOARD_DECODE_STATE
  sec
  ; Fall through

.done:
  plx
  rts


; On entry A contains the PS/2 set 2 non-extended "normal" keyboard code
; On exit  Carry is set if no translation was found
;          A contains the translated code or original code if no translation found
;          X, Y are preserverd
keyboard_translate_normal:
  phx
  phy
  ldx #<kb_normal_translation_table
  ldy #>kb_normal_translation_table
  jsr code_translate
  ply
  plx
  rts


; On entry A contains the PS/2 set 2 extended keyboard code
; On exit  Carry is set if no translation was found
;          A contains the translated code or original code if no translation found
;          X, Y are preserverd
keyboard_translate_extended:
  phx
  phy
  ldx #<kb_extended_translation_table
  ldy #>kb_extended_translation_table
  jsr code_translate
  ply
  plx
  rts


; On entry A contains the code
;          X, Y contains the address of the translation table
; On exit  Carry is set if no translation was found
;          A contains the translated code or original code if no translation found
;          X, Y are not preserved
code_translate:
  stx TRANSLATE_TABLE
  sty TRANSLATE_TABLE + 1
  tax
  ldy #0
  bra .repeat_entry
.repeat:
  iny
  iny
.repeat_entry:
  lda (TRANSLATE_TABLE), Y
  beq .not_found
  txa
  cmp (TRANSLATE_TABLE), Y
  bne .repeat
  ; Code found
  iny
  lda (TRANSLATE_TABLE), Y
  clc
  bra .done
.not_found:
  txa
  sec
.done:
  rts


; On entry A = LED flags to set
; On exit  A, X, Y are preserved
keyboard_set_leds:
  phx
  tax
  lda #KB_COMMAND_SET_LEDS
  jsr keyboard_send_command
  txa
  jsr keyboard_send_command
  plx
  rts


; On entry A = command byte to send
; On exit  X, Y are preserverd
;          A is not preserved
keyboard_send_command:
  phx
  phy
  tax                            ; Save command byte in X
  kb_trace 'a'
.wait_for_not_receiving:
  sei
  lda KEYBOARD_RECEIVING
  beq .not_receiving
  cli
  bra .wait_for_not_receiving
.not_receiving:
  lda #SOLB
  trb PORTA                      ; Pull clock low
  lda #ICA2
.wait_for_interrupt:
  bit IFR
  beq .wait_for_interrupt
  sta IFR
  cli
  stz PCR
  kb_trace 'b'

  lda #1                         ; 100 microseconds = 0.1 milliseconds = 1 1/10,000 of a second
  jsr delay_10_thousandths

  ldy PORTA                      ; Save PORTA value to Y

  lda #(PARITY | START)
  trb PORTA                      ; Clear parity and start bits

  txa                            ; Retrieve command byte from X
  jsr calculate_parity
  bcs odd_parity
; even parity
  lda #PARITY
  bra parity_mask_ready
odd_parity:
  lda #0
parity_mask_ready:               ; Mask is in A
  tsb PORTA
  stx PORTB                      ; Command byte
  lda #1
  sta SENDING_TO_KEYBOARD        ; Set flag to indicate we are sending
  lda #SOLB
  tsb PORTA                      ; Allow clock to float high; latch output data
  tya
  ora #SOLB
  sta PORTA                      ; Restore PORTA

  lda #3                         ; Wait for long enough that clock line has gone high
  jsr delay_10_thousandths

  lda #PCR_CA2_IND_POS_E
  sta PCR
  lda #1
  sta KEYBOARD_RECEIVING
  kb_trace 'c'

  ; Wait for send to complete
.wait_for_send:
  lda SENDING_TO_KEYBOARD
  bne .wait_for_send
  kb_trace 'd'

  ; Wait for ACK
.wait_for_ack:
  kb_trace 'w'
  lda ACK_RECEIVED
  beq .wait_for_ack
  kb_trace 'e'

  ply
  plx
  rts


; On entry A = value to calculate parity for
; On exit Carry set for odd parity or clear for even parity
;         A, X, Y are preserved
calculate_parity:
  pha
  phx
  phy

  ldy #0
  ldx #8
.repeat:
  lsr
  bcc .parity_updated            ; Current bit is 0 - do not increment parity
  iny                            ; Current bit is 1 - increment parity
.parity_updated:
  dex
  bne .repeat
  tya
  lsr ; shift parity into carry flag

  ply
  plx
  pla
  rts


  .ifndef KB_NO_INTERRUPT_HANDLER
interrupt:
  pha
  jsr handle_keyboard_interrupt
  pla
  rti
interrupt_end:
  .endif


handle_keyboard_interrupt:
  lda #%00000001  ; Clear the CA2 interrupt
  bit IFR
  bne .is_keyboard
  rts
.is_keyboard:
  sta IFR

  lda KEYBOARD_RECEIVING
  beq .start_receiving
  lda #PCR_CA2_IND_NEG_E
  sta PCR
  STZ KEYBOARD_RECEIVING

; Save PORTA data and direction to stack
  lda PORTA
  pha
  lda DDRA
  pha
; Save PORTB data and direction to stack
  lda PORTB
  pha
  lda DDRB
  pha

  lda #%00000000
  sta DDRB                       ; Set PORTB to input

  lda #(ACK | PARITY)
  trb DDRA                       ; Input from the ACK and parity bits

  lda #SOEB
  trb PORTA                      ; Enable shift register output

  lda SENDING_TO_KEYBOARD
  beq .not_sending
;Sending
  dec SENDING_TO_KEYBOARD
  bne .done_checking_send        ; Skip first interrupt which results from pulling clock low
;Sent
  stz ACK_RECEIVED
  bra .done_checking_send
.not_sending:
  lda PORTB
  eor #$ff
  cmp #KB_COMMAND_ACK
  beq .ack_received
;Not ACK
  jsr KB_BUFFER_WRITE
  bra .done_checking_ack
.ack_received:
  inc ACK_RECEIVED
.done_checking_ack:
.done_checking_send:
  lda #SOEB
  tsb PORTA                      ; Disable shift register output

; Restore PORTB direction and data from stack
  pla
  sta DDRB
  pla
  sta PORTB
; Restore PORTA direction and data from stack
  pla
  sta DDRA
  pla
  sta PORTA

  bra .done

.start_receiving:
  lda #PCR_CA2_IND_POS_E
  sta PCR
  lda #1
  sta KEYBOARD_RECEIVING

.done:
  rts
