; Keyboard info for Michael. Asks the keyboard for its ID (command $F2) and its scan code
; set (command $F0 with argument 0), then shows the lock keys and the raw bytes of keys as
; they are typed:
;
;   ID AB 83 Set 02          ID bytes (AB 83 is an MF2 keyboard) and scan code set
;   Lock Num Caps Scroll     the lock keys that are on (the keyboard's LEDs follow them)
;   E1 14 77 E1 F0 14 F0     the latest bytes from the keyboard, oldest first
;   77 1C F0 1C
;
; A reply that doesn't come within about 50 ms shows as "--" (an AT keyboard has no ID).

  .include base_config_v2.inc

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET

CP_M_DEST_P              = $00 ; 2 bytes
CP_M_SRC_P               = $02 ; 2 bytes
CP_M_LEN                 = $04 ; 2 bytes

SIMPLE_BUFFER_WRITE_PTR  = $06 ; 1 byte
SIMPLE_BUFFER_READ_PTR   = $07 ; 1 byte

DISPLAY_STRING_PARAM     = $08 ; 2 bytes

HISTORY_COUNT            = $0A ; 1 byte

KB_ZERO_PAGE_BASE        = $0B ; up to KB_ZERO_PAGE_STOP

SIMPLE_BUFFER            = $0200 ; 256 bytes
HISTORY                  = $0300 ; HISTORY_LENGTH bytes: the latest bytes received, oldest first

HISTORY_PER_LINE         = 7     ; "XX XX XX XX XX XX XX" fills a line
HISTORY_LENGTH           = HISTORY_PER_LINE * 2
REPLY_WAIT_STEPS         = 250   ; 0.2 ms each

KB_COMMAND_SCAN_CODE_SET = $f0   ; Argument 0 asks for the current set

  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
start:
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_string.inc
  .include display_hex.inc
  .include simple_buffer.inc
  .include copy_memory.inc
  .include key_codes.inc
  .include keyboard_typematic.inc
KB_BUFFER_INITIALIZE = simple_buffer_initialize
KB_BUFFER_WRITE      = simple_buffer_write
KB_BUFFER_READ       = simple_buffer_read
  .include keyboard_driver.inc


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  stz HISTORY_COUNT

  jsr reset_and_enable_display_no_cursor
  jsr keyboard_initialize

  ; ID and scan code set
  lda #<id_label
  ldx #>id_label
  jsr display_string
  lda #KB_COMMAND_READ_ID
  jsr keyboard_send_command
  jsr show_reply
  jsr display_space
  jsr show_reply

  lda #<set_label
  ldx #>set_label
  jsr display_string
  lda #KB_COMMAND_SCAN_CODE_SET
  jsr keyboard_send_command
  lda #0
  jsr keyboard_send_command
  jsr show_reply

  jsr show_locks

  ; Show each byte received, tracking the lock keys
show_bytes:
  jsr KB_BUFFER_READ
  bcs show_bytes
  jsr history_add
  jsr keyboard_decode_and_translate
  bcs .shown                     ; Not a whole key yet, or a code with no translation
  jsr keyboard_lock_keys_track
  jsr show_locks
.shown:
  jsr show_history
  bra show_bytes


; Shows the next byte from the keyboard in hex, or "--" if none comes within about 50 ms
; On exit A, X, Y are not preserved
show_reply:
  ldy #REPLY_WAIT_STEPS
.wait:
  jsr KB_BUFFER_READ
  bcc .show
  lda #2
  jsr delay_10_thousandths
  dey
  bne .wait
  lda #<no_reply
  ldx #>no_reply
  jmp display_string             ; tail call
.show:
  jmp display_hex                ; tail call


; Shows "Lock" and the names of the lock keys that are on on the second line
; On exit A, X, Y are not preserved
show_locks:
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<lock_label
  ldx #>lock_label
  jsr display_string
  lda #<num_name
  ldx #>num_name
  ldy #KB_NUM_LOCK_ON
  jsr show_lock
  lda #<caps_name
  ldx #>caps_name
  ldy #KB_CAPS_LOCK_ON
  jsr show_lock
  lda #<scroll_name
  ldx #>scroll_name
  ldy #KB_SCROLL_LOCK_ON
  ; Fall through


; On entry A, X = low and high bytes of the lock's name; Y = its KEYBOARD_LOCK_STATE mask
; On exit  the name is shown if the lock is on, or as many spaces if not
;          A, X, Y are not preserved
show_lock:
  sta DISPLAY_STRING_PARAM
  stx DISPLAY_STRING_PARAM + 1
  tya
  and KEYBOARD_LOCK_STATE
  tax                            ; X = 0 when the lock is off
  ldy #0
.next:
  lda (DISPLAY_STRING_PARAM), Y
  beq .done
  cpx #0
  bne .show
  lda #' '
.show:
  jsr display_character
  iny
  bra .next
.done:
  rts


; On entry A = byte to add to HISTORY, dropping the oldest when it is full
; On exit  A, X, Y are preserved
history_add:
  phx
  ldx HISTORY_COUNT
  cpx #HISTORY_LENGTH
  bne .append
  pha
  ldx #0
.shift:
  lda HISTORY + 1, X
  sta HISTORY, X
  inx
  cpx #HISTORY_LENGTH - 1
  bne .shift
  pla
  dec HISTORY_COUNT
.append:
  sta HISTORY, X
  inc HISTORY_COUNT
  plx
  rts


; Shows HISTORY in hex on the third and fourth lines
; On exit A, X, Y are not preserved
show_history:
  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  ldx #0
.next:
  cpx HISTORY_COUNT
  beq .done
  cpx #HISTORY_PER_LINE
  bne .not_line_start
  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  bra .show
.not_line_start:
  cpx #0
  beq .show
  jsr display_space
.show:
  lda HISTORY, X
  jsr display_hex
  inx
  bra .next
.done:
  rts


id_label:    .asciiz "ID "
set_label:   .asciiz " Set "
no_reply:    .asciiz "--"
lock_label:  .asciiz "Lock"
num_name:    .asciiz " Num"
caps_name:   .asciiz " Caps"
scroll_name: .asciiz " Scroll"
